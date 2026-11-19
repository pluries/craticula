---
translates: search-adapters
title: Adaptateurs MongoDB et OpenSearch
description: Exécutez les requêtes MongoDB et OpenSearch compilées avec les adaptateurs facultatifs, y compris la pagination profonde.
source_fingerprint: 48d257e31e0add276e9f93959d7b0b4c8302bb0209dc059498cdbe72961005ce
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Adaptateurs MongoDB et OpenSearch {#mongodb-and-opensearch-adapters}

Cette page présente les deux paquets facultatifs qui exécutent les requêtes Craticula sur un magasin de documents : `Craticula.MongoDB.Driver` pour MongoDB et `Craticula.OpenSearch.Client` pour OpenSearch et Elasticsearch. Elle s'adresse au développeur qui utilise l'un de ces magasins et veut que Craticula exécute la requête en plus de l'écrire.

## Ce que le cœur apporte et ce qu'ajoutent les adaptateurs {#what-the-core-gives-you-and-what-the-adapters-add}

Les compilateurs écrivent la requête et s'arrêtent là.

- `Craticula.Mongo` transforme une requête en pipeline d'agrégation. `MongoPipelineBuilder.Build` renvoie un `MongoQuery` contenant le nom de la collection et les étapes du pipeline.
- `Craticula.Search` transforme une requête en corps de recherche. `SearchQueryBuilder.Build` renvoie un `SearchQuery` contenant le nom de l'index et le corps, que `ToArtifact()` vous donne en JSON.

Aucun des deux compilateurs ne dépend d'une bibliothèque cliente, et aucun n'ouvre de connexion. Vous pouvez exécuter vous-même leur sortie.

Les adaptateurs l'exécutent pour vous. Installez-les depuis NuGet : `dotnet add package Craticula.MongoDB.Driver` ou `dotnet add package Craticula.OpenSearch.Client`. Voir [le guide de démarrage C#](quickstart-csharp.html).

## MongoDB {#mongodb}

`Craticula.MongoDB.Driver` compile avec `Craticula.Mongo` et exécute le pipeline par le pilote officiel de MongoDB, dans la plage `[3.13.0, 4.0)`.

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

Ce qu'il vous donne :

- `MongoGridQuery.FetchPageAsync` renvoie un `MongoGridPage` avec `Columns`, `Rows` et un `RowCount` facultatif.
- `MongoGridQuery.CountAsync` n'exécute que le comptage. Le comptage est une agrégation distincte qui abandonne le tri et la fenêtre de page, car un comptage n'a besoin ni de l'un ni de l'autre.
- `MongoExportStream.StreamAsync` diffuse en flux tous les documents correspondants pour un export. Il lit le curseur du pilote lot après lot, sans décalage à parcourir. Voir [Export CSV](csv-export.html).
- Une limite de temps, si vous en définissez une. Avec `ResourceLimits.MaxQueryTimeMs`, l'agrégation compilée porte `maxTimeMS`, MongoDB annule une requête qui dure plus longtemps, et l'adaptateur lève `QueryTimeoutException`. Le comptage reçoit lui aussi la limite, mais pas un export. Voir [Limites](limits.html).
- `FetchPageAsync` refuse la page non paginée. Une requête portant sur toutes les lignes passe par `MongoExportStream`, qui ne retient jamais le résultat complet.

Ce dont il a besoin de votre part :

- Une `IMongoDatabase` ouverte. L'adaptateur ne l'ouvre ni ne la ferme jamais.
- Un schéma qui associe chaque champ à un chemin de document, comme `"physical": { "mongo": { "path": "address.city" } }`, et une `source` qui nomme la collection.
- MongoDB 4.2 ou ultérieur. Voir [Dialectes et fournisseurs](dialects-and-providers.html).

## OpenSearch et Elasticsearch {#opensearch-and-elasticsearch}

`Craticula.OpenSearch.Client` compile avec `Craticula.Search` et exécute le corps par le client de bas niveau d'`OpenSearch.Client`, dans la plage `[2.2.0, 3.0)`. Il envoie le JSON compilé tel quel. Il ne reconstruit pas la requête une seconde fois avec le client typé.

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

Ici, `client` est un `IOpenSearchLowLevelClient`, `gridSessionId` est une chaîne que vous choisissez pour la session de grille, et `cache` est un `ISearchCursorCache`.

Ce qu'il vous donne :

- `OpenSearchGridQuery.FetchPageAsync` renvoie un `OpenSearchGridPage` avec `Columns`, `Rows`, un `RowCount` qui peut être nul et un indicateur `LastRow`.
- `OpenSearchExportStream.StreamAsync` diffuse en flux tous les résultats correspondants pour un export. Il écrit toujours chaque colonne du schéma, dans l'ordre de `schema.FieldOrder`, car le compilateur de recherche n'a pas de projection de colonnes. Passez à `CsvWriter` un `ExportColumn` par champ de `schema.FieldOrder` ; une liste plus étroite le fait échouer sur un nombre de cellules qui ne correspond pas.
- Une limite de temps, si vous en définissez une. Avec `ResourceLimits.MaxQueryTimeMs`, chaque corps de recherche porte `timeout`. Une recherche qui dépasse son temps répond quand même avec les résultats trouvés et `timed_out: true` ; l'adaptateur le transforme en `QueryTimeoutException` et ne renvoie jamais les résultats partiels comme une page, ni dans une page de grille ni dans un bloc d'export. Les requêtes propres à un export ne portent pas de `timeout`. `FetchPageAsync` refuse la page non paginée ; utilisez `OpenSearchExportStream`.

Ce dont il a besoin de votre part :

- Un client ouvert. L'adaptateur ne le construit ni ne le ferme jamais.
- Un mappage d'index qui correspond à votre schéma. Les requêtes compilées nomment les sous-champs que déclare votre schéma, comme un champ `keyword`. Un champ manquant peut faire qu'un filtre ne retourne aucune ligne, sans erreur. Voir [Conseils sur les index et les bases](index-guidance.html).
- Un cache de curseurs qui vit aussi longtemps que la session de grille. Voir ci-dessous.

### Le cache de curseurs {#the-cursor-cache}

OpenSearch refuse la pagination simple au-delà de 10,000 lignes. L'adaptateur bascule alors sur un point dans le temps et `search_after`, et il mémorise où le dernier bloc s'est terminé. Cette mémoire est l'`ISearchCursorCache` que vous lui passez.

`InMemorySearchCursorCache` est celui qui est fourni. Créez-le une seule fois pour le processus et partagez-le. Un nouveau cache par requête fait redémarrer chaque page profonde à partir de la ligne zéro. `InMemorySearchCursorCache` conserve ses entrées dans un seul processus. Si les requêtes d'une même session de grille peuvent atteindre plusieurs serveurs, une page profonde sur un autre serveur n'a pas de curseur et repart de la ligne zéro. Un cache partagé par tous les serveurs l'éviterait, mais aucun n'est fourni.

Le même curseur sert les niveaux groupés. Un niveau groupé utilise une agrégation composite, qui ne peut pas démarrer à une ligne non nulle. L'adaptateur conserve la clé du dernier groupe et la renvoie pour demander le bloc suivant.

### Options {#options}

`OpenSearchDeepPagingOptions` modifie la pagination :

| Réglage | Valeur par défaut | Effet |
|---|---|---|
| `MaxResultWindow` | 10,000 | Le nombre de lignes au-delà duquel l'adaptateur bascule sur le curseur. |
| `WalkBatchSize` | 1,000 | De combien de lignes avance une étape de rattrapage. |
| `PitKeepAlive` | 5 minutes | Combien de temps un curseur inactif reste valide. |
| `ExactRowCount` | `false` | Demander au moteur le comptage exact lorsque vous demandez un comptage de lignes. |
| `Flavour` | `OpenSearch` | Le moteur, `OpenSearch` ou `Elasticsearch`. |

Sans `ExactRowCount`, un comptage au-delà de la fenêtre est signalé comme inconnu, ce qui est peu coûteux. Avec cette option, le moteur compte chaque correspondance à chaque première requête.

### Elasticsearch {#elasticsearch}

La requête compilée est la même pour les deux moteurs. Seuls les appels qui ouvrent et ferment un point dans le temps diffèrent. Définissez la variante sur les deux enregistrements d'options lorsque le cluster est Elasticsearch :

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

Avec la variante par défaut face à Elasticsearch, une fenêtre au-delà de 10,000 lignes et chaque export échouent avec une erreur HTTP 400.

## Ce qu'ils ne font jamais {#what-they-never-do}

- Ils n'ouvrent, ne ferment ni ne configurent jamais une connexion ou un client.
- Ils ne relancent jamais une requête échouée et ne fixent jamais de délai d'expiration.
- Ils n'imposent jamais un nombre maximal de lignes exportées.
- Ils n'appliquent jamais vos limites de ressources ni les contrôles de colonnes de votre schéma. Exécutez d'abord `GridFilterPipeline.Process`. Voir [Le modèle de sécurité](safety-model.html).
- Ils n'exportent jamais un résultat groupé. Un export est une liste de lignes à plat, et les flux d'export refusent une requête qui porte un groupe.

## D'où vient cette page {#where-this-comes-from}

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- Pages liées : [Entity Framework Core et Dapper](relational-adapters.html), [Pagination et tri](paging-and-sorting.html), [Regroupement et agrégation](grouping-and-aggregation.html)
