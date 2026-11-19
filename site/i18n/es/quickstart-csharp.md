---
translates: quickstart-csharp
title: C#
description: Compile una solicitud de cuadrícula a SQL y MongoDB desde C#.
source_fingerprint: b1a5412bec8769ab8737adfd5828f36a3502b6b49ca68c2ba7f883125d5e6756
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Inicio rápido: C# {#quickstart-c}

Esta página le lleva de una solicitud de AG Grid a la sentencia SQL parametrizada que la responde, en un programa pequeño. No requiere base de
datos ni controlador: Craticula compila la consulta y nunca la ejecuta.

Los paquetes están en NuGet. Esta página usa tres:

```
dotnet add package Craticula.Core
dotnet add package Craticula.AgGrid
dotnet add package Craticula.Sql
```

Cada paquete tiene su propia página en nuget.org, por ejemplo [Craticula.Core](https://www.nuget.org/packages/Craticula.Core). El programa
de abajo también está en el repositorio, donde la solución lo compila; por eso esta página se verificó ejecutándolo desde allí.

## Lo que necesita {#what-you-need}

- el SDK de .NET 10;
- el repositorio, para ejecutar el ejemplo tal cual: clone o descargue <https://github.com/pluries/craticula>. Para usar la biblioteca en
  su propio proyecto, instale en su lugar los paquetes indicados arriba.

## Ejecútelo {#run-it}

Desde la carpeta `csharp` del repositorio:

```
dotnet run --project samples/Craticula.Quickstart
```

El programa es el archivo de abajo. La solución lo compila, así que un cambio en la biblioteca que lo rompa hace fallar la compilación. Hace
cinco cosas: declara un esquema (la lista de permitidos), toma una solicitud de AG Grid, la analiza hasta obtener la IR canónica, la compila para
dos bases de datos y, por último, muestra cómo se rechaza una solicitud sobre una columna no declarada.

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

## Lo que debería ver {#what-you-should-see}

La misma solicitud da a cada base de datos su propia sentencia. Los valores nunca forman parte del texto: son los parámetros que figuran
bajo cada sentencia, en el orden en que aparecen los marcadores. La última línea muestra el rechazo de la columna que no está en el
esquema.

````text
-- PostgreSQL
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0

-- SQL Server
SELECT * FROM [orders] WHERE ([customer] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\' AND [amount] > @p2) ORDER BY CASE WHEN [amount] IS NULL THEN 1 ELSE 0 END DESC, [amount] DESC, CASE WHEN [id] IS NULL THEN 1 ELSE 0 END ASC, [id] ASC OFFSET @p3 ROWS FETCH NEXT @p4 ROWS ONLY
-- parameters: 'acme', '100', 0, 50

-- refused: UnknownFieldException: Field allowlist check failed (SC-1/SC-2) for 1 colId(s): password
````

## Cómo leer la salida {#read-the-output}

- `ILIKE` y `COLLATE Latin1_General_CI_AS` son la forma en que cada base de datos escribe la comparación predeterminada que no distingue mayúsculas de minúsculas
  ([Case sensitivity](semantics.html#sem-1)); las dos sentencias coinciden en las filas que devuelven.
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` termina en `id`, la clave estable del esquema, de modo que la paginación es determinista
  ([Deterministic paging](semantics.html#sem-6)). SQL Server no tiene `NULLS FIRST`; por eso escribe el mismo orden con un `CASE` al principio
  ([Null ordering](semantics.html#sem-3)).
- El decimal `100` se muestra como `'100'` porque un parámetro decimal viaja como cadena, de modo que no se pierde precisión en el camino
  hacia el controlador (AR-7). Enlácelo como decimal en su controlador.
- `"password"` se rechazó porque el esquema no declara ninguna columna con ese nombre; la solicitud nunca llegó a un compilador.

## Ejecútelo en una base de datos real {#run-it-on-a-real-database}

Compile y ejecute en una sola llamada con un adaptador de ejecución, que recibe de su parte una conexión abierta o un `DbContext`. Instale el adaptador que
necesite desde NuGet (`Craticula.Dapper`, `Craticula.EntityFrameworkCore`, `Craticula.MongoDB.Driver` o `Craticula.OpenSearch.Client`);
el README de cada uno indica su línea de instalación.

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md): ejecuta la sentencia
  sobre una `IDbConnection`, con paginación, recuento de filas y exportación CSV en flujo.
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md):
  construye árboles de expresiones `IQueryable`; lea primero sus dos obligaciones para el host.
- MongoDB y OpenSearch tienen sus propios compiladores y clientes (`Craticula.Mongo`, `Craticula.MongoDB.Driver`,
  `Craticula.Search`, `Craticula.OpenSearch.Client`).

Para el recorrido completo, con una cuadrícula en un navegador, diez proveedores sobre siete motores de base de datos y un script que los compara entre sí, siga la
[demo](../../examples/demo/README.md), o pruébela en línea en [PostgreSQL](https://craticula-pg.pluries.dev) y
[MongoDB](https://craticula-mongo.pluries.dev).

## Siguientes pasos {#next}

- Lo que cada base de datos espera de usted para que las sentencias sean correctas: la [guía de índices y bases de datos](index-guidance.html).
- Las reglas que hay detrás de la salida: la [semántica](semantics.html).
- Cada ajuste del esquema: la [referencia de GridSchema](grid-schema.html).
