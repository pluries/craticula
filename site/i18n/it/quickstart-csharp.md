---
translates: quickstart-csharp
title: C#
description: Compilare una richiesta della griglia in SQL e MongoDB da C#.
source_fingerprint: b1a5412bec8769ab8737adfd5828f36a3502b6b49ca68c2ba7f883125d5e6756
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Guida rapida: C# {#quickstart-c}

Questa pagina porta da una richiesta AG Grid all'SQL parametrizzato che vi risponde, in un piccolo programma. Non servono né un
database né un driver: Craticula compila la query e non la esegue mai.

I pacchetti sono su NuGet. Questa pagina ne usa tre:

```
dotnet add package Craticula.Core
dotnet add package Craticula.AgGrid
dotnet add package Craticula.Sql
```

Ogni pacchetto ha una propria pagina su nuget.org, ad esempio [Craticula.Core](https://www.nuget.org/packages/Craticula.Core). Il programma
riportato sotto si trova anche nel repository, dove la solution lo compila: questa pagina è quindi stata verificata eseguendolo da lì.

## Che cosa serve {#what-you-need}

- l'SDK .NET 10;
- il repository, per eseguire l'esempio così com'è: clonare o scaricare <https://github.com/pluries/craticula>. Per usare la libreria nel
  proprio progetto, installare invece i pacchetti indicati sopra.

## Eseguirlo {#run-it}

Dalla cartella `csharp` del repository:

```
dotnet run --project samples/Craticula.Quickstart
```

Il programma è il file riportato sotto. La solution lo compila, quindi una modifica della libreria che lo rompe fa fallire la build. Fa
cinque cose: dichiara uno schema (la lista consentita), riceve una richiesta AG Grid, la analizza nell'IR canonica, la compila per
due database e mostra il rifiuto di una richiesta che cita una colonna non elencata.

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

## Che cosa si dovrebbe vedere {#what-you-should-see}

La stessa richiesta produce per ogni database un'istruzione propria. I valori non fanno mai parte del testo: sono i parametri elencati
sotto ogni istruzione, nell'ordine in cui compaiono i segnaposto. L'ultima riga mostra il rifiuto della colonna che non è presente
nello schema.

````text
-- PostgreSQL
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0

-- SQL Server
SELECT * FROM [orders] WHERE ([customer] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\' AND [amount] > @p2) ORDER BY CASE WHEN [amount] IS NULL THEN 1 ELSE 0 END DESC, [amount] DESC, CASE WHEN [id] IS NULL THEN 1 ELSE 0 END ASC, [id] ASC OFFSET @p3 ROWS FETCH NEXT @p4 ROWS ONLY
-- parameters: 'acme', '100', 0, 50

-- refused: UnknownFieldException: Field allowlist check failed (SC-1/SC-2) for 1 colId(s): password
````

## Leggere l'output {#read-the-output}

- `ILIKE` e `COLLATE Latin1_General_CI_AS` sono il modo in cui ciascun database scrive il confronto predefinito senza distinzione tra maiuscole e minuscole
  ([Case sensitivity](semantics.html#sem-1)); le due istruzioni concordano sulle righe che restituiscono.
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` termina con `id`, la chiave stabile dello schema, quindi la paginazione è deterministica
  ([Deterministic paging](semantics.html#sem-6)). SQL Server non ha `NULLS FIRST`, perciò scrive lo stesso ordine con un `CASE` iniziale
  ([Null ordering](semantics.html#sem-3)).
- Il decimale `100` è stampato come `'100'` perché un parametro decimale viaggia come stringa, così nessuna precisione va persa lungo il percorso
  verso il driver (AR-7). Associarlo come decimale nel proprio driver.
- `"password"` è stato rifiutato perché lo schema non elenca alcuna colonna con quel nome; la richiesta non ha mai raggiunto un compilatore.

## Eseguirlo su un database reale {#run-it-on-a-real-database}

Compilare ed eseguire in una sola chiamata con un adapter di esecuzione, che riceve da voi una connessione aperta o un `DbContext`. Installare l'adapter
necessario da NuGet (`Craticula.Dapper`, `Craticula.EntityFrameworkCore`, `Craticula.MongoDB.Driver` oppure `Craticula.OpenSearch.Client`);
ogni README indica la propria riga di installazione.

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md): esegue l'istruzione
  su una `IDbConnection`, con paginazione, conteggio delle righe ed esportazione CSV in streaming.
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md):
  costruisce alberi di espressioni `IQueryable`; leggere prima i suoi due obblighi per l'host.
- MongoDB e OpenSearch hanno compilatori e client propri (`Craticula.Mongo`, `Craticula.MongoDB.Driver`,
  `Craticula.Search`, `Craticula.OpenSearch.Client`).

Per il percorso completo con una griglia in un browser, dieci provider su sette motori di database e uno script che li confronta tra loro, seguire la
[demo](../../examples/demo/README.md), oppure provarla online su [PostgreSQL](https://craticula-pg.pluries.dev) e
[MongoDB](https://craticula-mongo.pluries.dev).

## Passi successivi {#next}

- Che cosa richiede ciascun database perché le istruzioni siano corrette: [guida a indici e database](index-guidance.html).
- Le regole alla base dell'output: [semantica](semantics.html).
- Ogni impostazione dello schema: il [riferimento GridSchema](grid-schema.html).
