---
translates: quickstart-csharp
title: C#
description: Compiler une requête de grille en SQL et en MongoDB depuis C#.
source_fingerprint: b1a5412bec8769ab8737adfd5828f36a3502b6b49ca68c2ba7f883125d5e6756
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Démarrage rapide : C# {#quickstart-c}

Cette page vous mène d'une requête AG Grid au SQL paramétré qui y répond, dans un petit programme. Elle n'exige ni base de
données ni pilote : Craticula compile la requête et ne l'exécute jamais.

Les paquets sont sur NuGet. Cette page en utilise trois :

```
dotnet add package Craticula.Core
dotnet add package Craticula.AgGrid
dotnet add package Craticula.Sql
```

Chaque paquet a sa propre page sur nuget.org, par exemple [Craticula.Core](https://www.nuget.org/packages/Craticula.Core). Le programme
ci-dessous se trouve aussi dans le dépôt, où la solution le compile ; cette page a donc été vérifiée en l'exécutant depuis là.

## Ce qu'il vous faut {#what-you-need}

- le SDK .NET 10 ;
- le dépôt, pour exécuter l'exemple tel quel : clonez ou téléchargez <https://github.com/pluries/craticula>. Pour utiliser la bibliothèque dans
  votre propre projet, installez plutôt les paquets ci-dessus.

## L'exécuter {#run-it}

Depuis le dossier `csharp` du dépôt :

```
dotnet run --project samples/Craticula.Quickstart
```

Le programme est le fichier ci-dessous. La solution le compile : une modification de la bibliothèque qui le casse fait donc échouer la compilation. Il
fait cinq choses : il déclare un schéma (la liste autorisée), prend une requête AG Grid, l'analyse en IR canonique, la compile pour
deux bases de données, puis montre le refus d'une requête portant sur une colonne non déclarée.

````csharp
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Sql;

// 1. The schema is the allowlist: a column that is not listed here can never reach a query, and every identifier in the
//    statement comes from `physical.sql.column`, never from the request.
const string schemaJson = """
    {
      "mode": "strict",
      "source": "orders",
      "stableKey": "id",
      "fields": {
        "id":       { "type": "int64",    "sortable": true, "physical": { "sql": { "column": "id" } } },
        "customer": { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "customer" } } },
        "amount":   { "type": "decimal",  "filterable": true, "sortable": true, "physical": { "sql": { "column": "amount" } } },
        "status":   { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "status" } } }
      }
    }
    """;

// 2. A request exactly as AG Grid's server-side row model sends it: customers containing "acme", amount above 100,
//    biggest amounts first, the first 50 rows.
const string requestJson = """
    {
      "startRow": 0,
      "endRow": 50,
      "rowGroupCols": [],
      "valueCols": [],
      "pivotCols": [],
      "pivotMode": false,
      "groupKeys": [],
      "filterModel": {
        "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
        "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
      },
      "sortModel": [ { "colId": "amount", "sort": "desc" } ]
    }
    """;

GridSchema schema = GridSchema.Parse(schemaJson);

// 3. Parse the request into the canonical IR, then validate it against the schema and the resource limits.
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits(), parsed.Group, parsed.Aggregations);

// 4. Compile: the same IR gives each database its own statement. Values travel as parameters, never inside the text.
foreach ((string name, ISqlDialect dialect) in new (string, ISqlDialect)[]
         {
             ("PostgreSQL", PostgresDialect.Instance),
             ("SQL Server", MssqlDialect.Instance),
         })
{
    SqlQuery query = SqlQueryBuilder.Build(
        new SqlQueryRequest { Schema = schema, Filter = filter, Sort = parsed.Sort, Page = parsed.Page }, dialect);

    Console.WriteLine($"-- {name}");
    Console.WriteLine(query.Sql);
    Console.WriteLine($"-- parameters: {string.Join(", ", query.Parameters.Select(value => value is string text ? $"'{text}'" : value?.ToString() ?? "NULL"))}");
    Console.WriteLine();
}

// 5. A column the schema does not list is refused before any query exists. Here the grid asks to filter on `password`.
const string hostileJson = """
    { "startRow": 0, "endRow": 50, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
      "filterModel": { "password": { "filterType": "text", "type": "equals", "filter": "x" } }, "sortModel": [] }
    """;

try
{
    AgGridParsedRequest bad = AgGridRequestParser.Parse(hostileJson, new AgGridParseOptions { Schema = schema });
    GridFilterPipeline.Process(bad.NativeFilter, bad.CustomFilters, bad.Page, schema, new ResourceLimits(), bad.Group, bad.Aggregations);
    Console.WriteLine("-- the unknown column was NOT refused");
}
catch (UnknownFieldException error)
{
    Console.WriteLine($"-- refused: {error.GetType().Name}: {error.Message}");
}
````

## Ce que vous devriez voir {#what-you-should-see}

La même requête donne à chaque base de données son propre énoncé. Les valeurs ne font jamais partie du texte : ce sont les paramètres listés
sous chaque énoncé, dans l'ordre où apparaissent les marqueurs. La dernière ligne montre le refus de la colonne qui ne figure pas dans le
schéma.

````text
-- PostgreSQL
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0

-- SQL Server
SELECT * FROM [orders] WHERE ([customer] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\' AND [amount] > @p2) ORDER BY CASE WHEN [amount] IS NULL THEN 1 ELSE 0 END DESC, [amount] DESC, CASE WHEN [id] IS NULL THEN 1 ELSE 0 END ASC, [id] ASC OFFSET @p3 ROWS FETCH NEXT @p4 ROWS ONLY
-- parameters: 'acme', '100', 0, 50

-- refused: UnknownFieldException: Field allowlist check failed (SC-1/SC-2) for 1 colId(s): password
````

## Lire la sortie {#read-the-output}

- `ILIKE` et `COLLATE Latin1_General_CI_AS` sont la façon dont chaque base de données écrit la comparaison par défaut insensible à la casse
  ([Case sensitivity](semantics.html#sem-1)) ; les deux énoncés s'accordent sur les lignes qu'ils renvoient.
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` se termine par `id`, la clé stable du schéma, de sorte que la pagination est déterministe
  ([Deterministic paging](semantics.html#sem-6)). SQL Server n'a pas de `NULLS FIRST` ; il écrit donc le même ordre avec un `CASE` en tête
  ([Null ordering](semantics.html#sem-3)).
- Le décimal `100` est affiché `'100'` parce qu'un paramètre décimal est transporté sous forme de chaîne, de sorte qu'aucune précision n'est perdue en route
  vers le pilote (AR-7). Liez-le comme décimal dans votre pilote.
- `"password"` a été refusé parce que le schéma ne liste aucune colonne de ce nom ; la requête n'a jamais atteint un compilateur.

## L'exécuter sur une vraie base de données {#run-it-on-a-real-database}

Compilez et exécutez en un seul appel avec un adaptateur d'exécution, qui prend de votre part une connexion ouverte ou un `DbContext`. Installez l'adaptateur dont vous
avez besoin depuis NuGet (`Craticula.Dapper`, `Craticula.EntityFrameworkCore`, `Craticula.MongoDB.Driver` ou `Craticula.OpenSearch.Client`) ;
chaque README indique sa ligne d'installation.

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md) : exécute l'énoncé
  sur une `IDbConnection`, avec pagination, comptage de lignes et export CSV en flux.
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md) :
  construit des arbres d'expressions `IQueryable` ; lisez d'abord ses deux obligations pour l'hôte.
- MongoDB et OpenSearch ont leurs propres compilateurs et clients (`Craticula.Mongo`, `Craticula.MongoDB.Driver`,
  `Craticula.Search`, `Craticula.OpenSearch.Client`).

Pour le parcours complet avec une grille dans un navigateur, dix fournisseurs sur sept moteurs de base de données et un script qui les compare entre eux, suivez la
[démo](../../examples/demo/README.md), ou essayez-la en ligne sur [PostgreSQL](https://craticula-pg.pluries.dev) et
[MongoDB](https://craticula-mongo.pluries.dev).

## Suite {#next}

- Ce que chaque base de données attend de vous pour que les énoncés soient justes : [conseils sur les index et les bases de données](index-guidance.html).
- Les règles derrière la sortie : [sémantique](semantics.html).
- Chaque paramètre du schéma : la [référence GridSchema](grid-schema.html).
