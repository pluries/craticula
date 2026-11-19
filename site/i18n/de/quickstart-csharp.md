---
translates: quickstart-csharp
title: C#
description: Eine Grid-Anfrage aus C# in SQL und MongoDB kompilieren.
source_fingerprint: b1a5412bec8769ab8737adfd5828f36a3502b6b49ca68c2ba7f883125d5e6756
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Schnellstart: C# {#quickstart-c}

Diese Seite führt Sie in einem kleinen Programm von einer AG Grid-Anfrage zum parametrisierten SQL, das sie beantwortet. Sie braucht weder eine
Datenbank noch einen Treiber: Craticula kompiliert die Abfrage und führt sie nie aus.

Die Pakete liegen auf NuGet. Diese Seite verwendet drei davon:

```
dotnet add package Craticula.Core
dotnet add package Craticula.AgGrid
dotnet add package Craticula.Sql
```

Jedes Paket hat auf nuget.org eine eigene Seite, zum Beispiel [Craticula.Core](https://www.nuget.org/packages/Craticula.Core). Das Programm
unten liegt auch im Repository, wo die Solution es baut; diese Seite wurde also geprüft, indem es von dort aus ausgeführt wurde.

## Was Sie brauchen {#what-you-need}

- das .NET 10 SDK;
- das Repository, um das Beispiel unverändert auszuführen: Klonen oder laden Sie <https://github.com/pluries/craticula> herunter. Wenn Sie die Bibliothek in
  Ihrem eigenen Projekt verwenden möchten, installieren Sie stattdessen die oben genannten Pakete.

## Ausführen {#run-it}

Aus dem Ordner `csharp` des Repositorys:

```
dotnet run --project samples/Craticula.Quickstart
```

Das Programm ist die Datei unten. Die Solution baut es: Eine Änderung an der Bibliothek, die es bricht, lässt den Build fehlschlagen. Es
tut fünf Dinge: Es deklariert ein Schema (die Allowlist), nimmt eine AG Grid-Anfrage entgegen, parst sie in die kanonische IR, kompiliert sie für
zwei Datenbanken und zeigt dann, wie eine Anfrage mit einer nicht deklarierten Spalte abgelehnt wird.

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

## Was Sie sehen sollten {#what-you-should-see}

Dieselbe Anfrage ergibt für jede Datenbank eine eigene Anweisung. Die Werte sind nie Teil des Textes: Sie sind die Parameter, die unter jeder Anweisung
aufgelistet sind, in der Reihenfolge, in der die Platzhalter erscheinen. Die letzte Zeile zeigt, wie die Spalte abgelehnt wird, die nicht im
Schema steht.

````text
-- PostgreSQL
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0

-- SQL Server
SELECT * FROM [orders] WHERE ([customer] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\' AND [amount] > @p2) ORDER BY CASE WHEN [amount] IS NULL THEN 1 ELSE 0 END DESC, [amount] DESC, CASE WHEN [id] IS NULL THEN 1 ELSE 0 END ASC, [id] ASC OFFSET @p3 ROWS FETCH NEXT @p4 ROWS ONLY
-- parameters: 'acme', '100', 0, 50

-- refused: UnknownFieldException: Field allowlist check failed (SC-1/SC-2) for 1 colId(s): password
````

## Die Ausgabe lesen {#read-the-output}

- `ILIKE` und `COLLATE Latin1_General_CI_AS` sind die Schreibweisen, mit denen die jeweilige Datenbank den standardmäßigen Vergleich ohne Beachtung der Groß- und Kleinschreibung ausdrückt
  ([Case sensitivity](semantics.html#sem-1)); beide Anweisungen liefern dieselben Zeilen.
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` endet mit `id`, dem stabilen Schlüssel des Schemas, sodass das Paging deterministisch ist
  ([Deterministic paging](semantics.html#sem-6)). SQL Server kennt kein `NULLS FIRST`; es schreibt dieselbe Reihenfolge daher mit einem vorangestellten `CASE`
  ([Null ordering](semantics.html#sem-3)).
- Die Dezimalzahl `100` wird als `'100'` ausgegeben, weil ein Dezimalparameter als Zeichenfolge übertragen wird, damit auf dem Weg
  zum Treiber keine Genauigkeit verloren geht (AR-7). Binden Sie ihn in Ihrem Treiber als Dezimalzahl.
- `"password"` wurde abgelehnt, weil das Schema keine Spalte dieses Namens aufführt; die Anfrage hat nie einen Compiler erreicht.

## Auf einer echten Datenbank ausführen {#run-it-on-a-real-database}

Kompilieren und ausführen in einem einzigen Aufruf geht mit einem Ausführungsadapter, der von Ihnen eine geöffnete Verbindung oder einen `DbContext` entgegennimmt. Installieren Sie den Adapter, den Sie
brauchen, von NuGet (`Craticula.Dapper`, `Craticula.EntityFrameworkCore`, `Craticula.MongoDB.Driver` oder `Craticula.OpenSearch.Client`);
die jeweilige README nennt die Installationszeile.

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md): führt die Anweisung
  auf einer `IDbConnection` aus, mit Paging, Zeilenzählung und gestreamtem CSV-Export.
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md):
  baut `IQueryable`-Ausdrucksbäume auf; lesen Sie zuerst seine beiden Pflichten für den Host.
- MongoDB und OpenSearch haben eigene Compiler und Clients (`Craticula.Mongo`, `Craticula.MongoDB.Driver`,
  `Craticula.Search`, `Craticula.OpenSearch.Client`).

Für den vollständigen Durchgang mit einem Grid im Browser, zehn Providern auf sieben Datenbank-Engines und einem Skript, das sie miteinander vergleicht, folgen Sie der
[Demo](../../examples/demo/README.md) oder probieren Sie sie online auf [PostgreSQL](https://craticula-pg.pluries.dev) und
[MongoDB](https://craticula-mongo.pluries.dev) aus.

## Weiter {#next}

- Was jede Datenbank von Ihnen erwartet, damit die Anweisungen korrekt sind: [Hinweise zu Indizes und Datenbanken](index-guidance.html).
- Die Regeln hinter der Ausgabe: [Semantik](semantics.html).
- Jede Einstellung im Schema: die [GridSchema-Referenz](grid-schema.html).
