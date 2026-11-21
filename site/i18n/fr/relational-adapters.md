---
translates: relational-adapters
title: Entity Framework Core et Dapper
description: Ce qu'apportent les deux adaptateurs relationnels, ce dont ils ont besoin et ce qu'ils ne font jamais.
source_fingerprint: c7c6226b52fe85563de296ccf30f4b6133346e53ef471b90257c33696e64481f
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Entity Framework Core et Dapper {#entity-framework-core-and-dapper}

Cette page présente les deux paquets facultatifs qui exécutent les requêtes Craticula sur une base de données relationnelle : `Craticula.Dapper` et `Craticula.EntityFrameworkCore`. Elle s'adresse au développeur qui dispose d'une base SQL et veut que Craticula exécute la requête en plus de l'écrire.

## Pourquoi les adaptateurs existent {#why-adapters-exist}

Les paquets du cœur ne font que compiler. Ils n'ouvrent jamais de connexion et n'exécutent jamais rien. Un adaptateur comble cet écart pour une bibliothèque d'accès aux données. Il compile la requête, l'exécute et vous renvoie des lignes.

Les adaptateurs sont facultatifs. Les paquets du cœur n'en dépendent jamais. Vous pouvez vous en passer et exécuter vous-même l'instruction compilée avec la bibliothèque de votre choix.

Installez-les depuis NuGet : `dotnet add package Craticula.Dapper` ou `dotnet add package Craticula.EntityFrameworkCore`. Voir [le guide de démarrage C#](quickstart-csharp.html).

## Dapper {#dapper}

`Craticula.Dapper` compile avec `Craticula.Sql` et exécute l'instruction sur une connexion que vous lui remettez. Utilisez-le lorsque vous voulez voir et contrôler le SQL.

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

Ce qu'il vous donne :

- `DapperGridQuery.FetchPageAsync` renvoie une page. `DapperGridPage` contient les `Columns`, les `Rows` et un `RowCount` facultatif.
- `DapperGridQuery.CountAsync` n'exécute que le comptage.
- `DapperExportStream.StreamAsync` diffuse en flux toutes les lignes correspondantes pour un export. Voir [Export CSV](csv-export.html).
- `FetchPageAsync` refuse la page non paginée (`NonePage`) : un appel ne charge donc jamais toutes les lignes en mémoire. Une requête portant sur toutes les lignes passe par `DapperExportStream`.

Ce dont il a besoin de votre part :

- Une `IDbConnection` ouverte. L'adaptateur ne l'ouvre ni ne la ferme jamais.
- Le dialecte qui correspond à votre base de données. Voir [Dialectes et fournisseurs](dialects-and-providers.html).
- Dapper lui-même, dans la plage `[2.1.89, 3.0)`.

Les requêtes groupées passent par la même méthode. Le compilateur SQL écrit déjà l'instruction groupée ; l'adaptateur se contente de l'exécuter.

## Entity Framework Core {#entity-framework-core}

`Craticula.EntityFrameworkCore` n'écrit pas de texte SQL. Il construit des arbres d'expressions `IQueryable<T>`, et le fournisseur EF Core les transforme en SQL. Utilisez-le lorsque vous avez déjà un `DbContext` et que vous voulez que ses filtres de requête globaux, comme un filtre de locataire, s'appliquent.

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

Ce qu'il vous donne :

- `EfCoreGridQuery.FetchPageAsync` renvoie une page, dans un `EfCoreGridPage` construit comme celui de Dapper.
- `EfCoreGridQuery.CountAsync` n'exécute que le comptage.
- `EfCoreExportStream.StreamAsync` diffuse des lignes en flux pour un export.
- `FetchPageAsync` refuse la page non paginée, comme le fait l'adaptateur Dapper. Une requête portant sur toutes les lignes passe par `EfCoreExportStream`.

Ce dont il a besoin de votre part :

- **Une requête source.** Passez un `DbSet<T>`, ou `GridSchemaPropertyBag.Query(context, schema)` si vous n'avez pas de classes d'entités. Pour la seconde forme, appelez `GridSchemaPropertyBag.Configure` dans `OnModelCreating`.
- **Des noms de propriétés concordants.** Chaque champ est lu comme une propriété EF nommée d'après son `physical.sql.column`, ou d'après l'identifiant de la colonne s'il n'y en a pas. Une classe qui renomme ses colonnes avec `HasColumnName` doit s'y conformer.
- **Une valeur `EfCoreProviderSemantics`.** Elle énonce cinq faits sur votre base de données qu'EF ne peut pas communiquer à Craticula, comme le nom de la collation insensible à la casse. Seule `EfCoreProviderSemantics.Sqlite` est fournie, car c'est la seule qui ait été mesurée. Pour un autre moteur, vous déclarez la vôtre, une seule fois, à côté de votre `DbContext`.

Les champs du schéma doivent utiliser un `physical.sql.column` simple. Un champ avec `qualifiedColumn` ou `expression` est refusé, car ni l'un ni l'autre n'a de forme dans un arbre d'expressions.

Si un type de `DbContext` peut être construit à partir de plusieurs schémas, enregistrez `GridSchemaModelCacheKeyFactory` et implémentez `IGridSchemaModel` sur le contexte. Sans cela, EF réutilise le modèle du premier schéma pour le suivant et échoue avec des erreurs qui ne mentionnent pas le cache.

### Deux pièges silencieux {#two-silent-traps}

Ces deux pièges renvoient de mauvaises lignes sans erreur. L'adaptateur ne voit ni votre modèle ni vos collations ; il ne peut donc pas s'en prémunir.

- **Valeurs de date et heure SQLite.** Stockez un `datetime` sous forme de texte `yyyy-MM-ddTHH:mm:ss.fffZ` et faites correspondre chaque `DateTime` à ce texte, dans les deux sens, dans votre `DbContext`. Le mappage propre à EF utilise une autre forme, et SQLite compare le texte caractère par caractère.
- **`PatternMatchFoldsCase`.** Il indique si le `LIKE` du moteur ignore la casse. Utilisez `true` pour SQLite. Pour SQL Server et MySQL, utilisez `false`, sauf si chaque colonne interrogeable a une collation qui ignore la casse. Sinon, une colonne à collation binaire ne correspond qu'à la casse exacte.

Les cellules de date et heure sortent d'une page ou d'un export sous forme de valeurs UTC, quoi qu'ait renvoyé le fournisseur.

## Ce que les deux adaptateurs ont en commun {#what-both-adapters-share}

- **Les comptages de lignes sont à activer.** Le comptage est un second aller-retour : il est désactivé sauf si vous passez `includeRowCount`. Une grille en a besoin une fois par changement de filtre, pas une fois par bloc.
- **Les exports n'utilisent jamais de décalage.** Ils lisent les lignes par blocs de 5,000 en parcourant les clés de tri, de sorte qu'un bloc tardif coûte autant qu'un bloc précoce. `DapperExportOptions` et `EfCoreExportOptions` ont un `ChunkSize` pour modifier cela. L'export a besoin d'une clé stable véritablement unique. Un doublon est détecté et lève une exception.
- **Dapper refuse certains exports.** `DapperExportStream` refuse un schéma dont la clé stable est une colonne de texte. Il refuse aussi un export où une clé de tri textuelle contient une chaîne vide dans les lignes exportées, sur tous les dialectes sauf Oracle. Dans les deux cas, utilisez une clé stable numérique ou de date, ou récupérez les données page par page avec `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` n'a pas de telle vérification.
- **Un export limité à une page est refusé.** Les flux d'export prennent le résultat complet. Une page bornée passe par la méthode de page.
- **Un résultat neutre.** Chaque page a une extension `ToGridPageResult()`. Celle d'OpenSearch prend aussi le `SearchQueryRequest` que vous avez utilisé. `LoadSuccessParamsMapper.Map` dans `Craticula.AgGrid` la transforme dans la forme qu'attend AG Grid.

## Ce qu'ils ne font jamais {#what-they-never-do}

- Ils n'ouvrent, ne ferment ni ne mettent jamais en pool une connexion, et ils ne démarrent jamais de transaction.
- Ils ne relancent jamais une requête échouée et ne fixent jamais de délai d'expiration. La connexion et les réglages de commande vous appartiennent.
- Ils n'imposent jamais un nombre maximal de lignes exportées.
- Ils n'appliquent jamais vos limites de ressources ni les contrôles de colonnes de votre schéma. Exécutez d'abord `GridFilterPipeline.Process`, comme le fait le guide de démarrage. Voir [Le modèle de sécurité](safety-model.html).

## Lequel choisir {#which-one-to-pick}

| Vous avez | Utilisez |
|---|---|
| Une `IDbConnection` simple et vous voulez voir le SQL | Dapper |
| N'importe lequel des cinq dialectes SQL, sans code supplémentaire | Dapper |
| Un `DbContext` avec des filtres de requête globaux que vous voulez conserver | Entity Framework Core |

La démo exécute les deux sur PostgreSQL, ce qui vous permet de les comparer sur les mêmes données.

## D'où vient cette page {#where-this-comes-from}

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Pages liées : [Export CSV](csv-export.html), [Adaptateurs MongoDB et OpenSearch](search-adapters.html), [Pagination et tri](paging-and-sorting.html)
