---
translates: paging-and-sorting
title: Pagination et tri
description: Comment les lignes sont fenêtrées et ordonnées, et pourquoi la pagination est déterministe.
source_fingerprint: c01a09b912527d1a95923a5776c7b4abb3290f980e8c9111c4751565b710b445
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Pagination et tri {#paging-and-sorting}

Cette page explique comment la plage de lignes et l'ordre de tri d'une requête AG Grid deviennent la pagination et l'ordonnancement de la requête. Elle s'adresse à un développeur qui veut savoir pourquoi les lignes reviennent dans un certain ordre, et ce que fait chaque backend pour les parcourir page par page.

## De startRow et endRow à une page {#from-startrow-and-endrow-to-a-page}

AG Grid demande un bloc de lignes avec `startRow` et `endRow`. `endRow` est exclusif. La taille de la page est `endRow - startRow`.

Craticula en fait un nombre de lignes et un décalage. Le nombre est la taille de la page. Le décalage est `startRow`. Une requête pour les lignes 50 à 100 demande 50 lignes après en avoir sauté 50.

L'adaptateur refuse une fenêtre qui n'a pas de sens :

- un `startRow` négatif ;
- un `endRow` inférieur à `startRow` ;
- un `endRow` égal à `startRow`, c'est-à-dire une fenêtre vide.

Une page a aussi une taille maximale. La valeur par défaut est de 1000 lignes. Voir [Limites](limits.html).

## Une requête sans fenêtre {#a-request-with-no-window}

Certaines requêtes n'envoient ni `startRow` ni `endRow` : un client personnalisé, ou une requête construite à la main. Depuis la version 1.2.0, une telle requête reçoit une page par défaut de 100 lignes, `[0, 100)`. La taille est `AgGridParseOptions.DefaultPageSize`, et la limite de taille de page la vérifie comme n'importe quelle autre fenêtre. Avant la version 1.2.0, une requête sans fenêtre signifiait toutes les lignes correspondantes.

Il y a deux façons de demander toutes les lignes, et les deux sont délibérées :

- **Un export de tout** (`exportScope` défini à `"all"`). Il n'a pas de page et les adaptateurs le diffusent par morceaux. Voir [Export CSV](csv-export.html).
- **L'indicateur `ignorePageLimit: true`**, qui ne fonctionne que si votre hôte a activé `AgGridParseOptions.AllowUnboundedRows` (désactivé par défaut). Sans cet interrupteur, la requête est refusée avec l'erreur d'analyse `unbounded-not-allowed` ; elle n'est jamais plafonnée discrètement. Une requête qui porte une fenêtre garde sa fenêtre et l'indicateur ne change rien.

Les adaptateurs lisent une requête de toutes les lignes en flux. La méthode paginée `FetchPageAsync` des adaptateurs MongoDB, Dapper, EF Core et OpenSearch refuse la page non paginée, de sorte qu'aucun appel ne charge le résultat entier en mémoire. Utilisez le flux d'export pour ces requêtes. Les règles figurent dans [Taille de page par défaut](default-page-size.html).

## Ce que fait chaque backend {#what-each-backend-does}

| Backend | Comment la page est écrite |
|---|---|
| PostgreSQL, MySQL, SQLite | `LIMIT n OFFSET m` |
| SQL Server, Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | une étape `$skip`, puis une étape `$limit` |
| OpenSearch et Elasticsearch | `from` et `size` |

Pour SQL, les deux nombres sont des paramètres, pas une partie du texte. SQL Server et Oracle lient le décalage avant le nombre de lignes. PostgreSQL, MySQL et SQLite lient d'abord le nombre de lignes. Vous n'avez pas à vous en soucier, car la liste de paramètres suit l'ordre d'apparition des marqueurs.

Un export de tout n'a aucune page. Il demande toutes les lignes correspondantes et n'obtient aucune clause de pagination. Voir [Export CSV](csv-export.html).

## Ordre de tri {#sort-order}

La grille envoie une liste de clés de tri dans `sortModel`. Craticula les garde dans cet ordre. Chaque clé a une colonne et une direction, `asc` ou `desc`.

Un tri sur une colonne que le schéma ne liste pas est refusé, en mode Strict comme en mode Lenient. Le refus vient du compilateur, qui lève sa propre exception de compilation. Voir [Strict et Lenient](strict-and-lenient.html).

Le schéma a un indicateur `sortable` pour chaque colonne. Rien ne le lit (à la date de cette version). Une colonne qui figure dans le schéma peut être triée quelle que soit la valeur de son indicateur. Ne comptez pas sur l'indicateur pour empêcher le tri d'une colonne.

## Où vont les valeurs nulles {#where-nulls-go}

AG Grid ne dit pas où les valeurs nulles doivent se placer dans un tri. Craticula le décide, et de la même façon pour tous les backends :

- un tri croissant place les valeurs nulles en dernier ;
- un tri décroissant place les valeurs nulles en premier.

Les bases de données ne s'accordent pas là-dessus par défaut, c'est pourquoi Craticula ne le laisse jamais à la base de données. Il écrit la position dans chaque clé de tri.

PostgreSQL, SQLite et Oracle ont `NULLS FIRST` et `NULLS LAST`, et Craticula les utilise. SQLite exige pour cela la version 3.30.0 ou une version ultérieure. SQL Server et MySQL n'ont pas cette syntaxe : Craticula ajoute donc un test en tête qui place les lignes nulles dans leur propre groupe : `CASE WHEN ... IS NULL` sur SQL Server et `ISNULL(...)` sur MySQL. MongoDB reçoit un champ auxiliaire par clé de tri, retiré à nouveau après le tri. OpenSearch reçoit `"missing": "_last"` ou `"_first"`.

## Le tri du texte ignore la casse {#text-sorts-without-regard-to-case}

Une colonne de texte se compare par défaut sans tenir compte de la casse. Le tri suit la même règle, de sorte que `apple` et `Apple` sont triés ensemble. Une colonne peut demander la casse exacte dans le schéma avec `text.caseSensitivity` défini à `sensitive`.

Chaque moteur atteint le même résultat à sa manière :

- PostgreSQL nomme un classement (collation), `craticula_ci`, que vous créez une fois.
- SQL Server et SQLite nomment un classement directement dans la requête.
- MySQL utilise le classement de la colonne elle-même.
- MongoDB définit un classement pour toute la requête.
- OpenSearch trie sur un sous-champ normalisé que vous déclarez dans l'index.

Ce que vous devez configurer pour chaque base de données se trouve dans [Conseils sur les index et les bases de données](index-guidance.html).

## La clé stable garde la pagination en ordre {#the-stable-key-keeps-paging-in-order}

La pagination n'est fiable que si l'ordre est total. Si deux lignes sont à égalité sur toutes les clés de tri, la base de données peut les renvoyer dans l'un ou l'autre ordre, et une ligne peut apparaître sur deux pages ou sur aucune.

Pour l'éviter, le schéma nomme une `stableKey`, une colonne dont les valeurs sont uniques. Lorsque le tri ne se termine pas déjà par cette clé, Craticula l'ajoute à la fin, en ordre croissant, valeurs nulles en dernier.

La requête du guide de démarrage rapide trie par `amount` décroissant. L'instruction se termine ainsi :

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

Craticula nettoie aussi le tri avant d'ajouter quoi que ce soit :

- une colonne nommée deux fois ne garde que sa première apparition ;
- si la clé stable trie exactement, toutes les clés qui la suivent sont abandonnées, car il ne reste aucune égalité à départager.

Une clé stable de texte qui ignore la casse fait exception. Deux clés qui ne diffèrent que par la casse se comparent comme égales : les clés suivantes sont donc conservées et un départage exact est ajouté.

Cela ne fonctionne que si la clé stable est réellement unique. La plupart des bases de données permettent à une colonne unique de contenir de nombreuses valeurs nulles, ce qui rompt la garantie. Déclarez la clé `NOT NULL`. Voir [Conseils sur les index et les bases de données](index-guidance.html).

## Pagination profonde {#deep-paging}

Les pages de grille SQL et MongoDB utilisent un décalage. La base de données doit parcourir chaque ligne sautée : une page profonde dans une grande table est donc plus lente qu'une page proche du début. Indexez vos filtres et mesurez.

OpenSearch refuse les simples `from` et `size` au-delà de 10,000 lignes. L'adaptateur OpenSearch s'en charge pour vous. Au-delà de ce seuil, il passe à un point dans le temps (point in time) et à `search_after`, et il garde un curseur entre les requêtes. Trois conséquences en découlent :

- Vous devez lui fournir un seul cache de curseurs qui vit aussi longtemps que la session de la grille. `InMemorySearchCursorCache` est celui qui est livré. Un nouveau cache à chaque requête annule l'effet du curseur.
- La première requête qui franchit le seuil avance depuis la ligne zéro. Les blocs suivants sont rapides.
- Le nombre total de lignes au-dessus de 10,000 est signalé comme inconnu, sauf si vous demandez le décompte exact, ce qui coûte un décompte complet à chaque première requête.

Voir [Adaptateurs MongoDB et OpenSearch](search-adapters.html).

## D'où cela provient {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- Pages liées : [Comment une requête devient une requête](request-to-query.html), [Regroupement et agrégation](grouping-and-aggregation.html), [Dialectes et fournisseurs](dialects-and-providers.html)
