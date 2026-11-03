# How a request becomes a query

This page follows one AG Grid request through Craticula, step by step, until it becomes a query with parameters. It is for a developer who wants to know what happens between the grid and the database, and why there are several steps.

## The path

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **Request JSON.** The grid sends it. Craticula does not change what the grid sends.
2. **Adapter.** The AG Grid adapter reads the JSON and turns it into the canonical form. It rejects JSON it does not understand.
3. **Canonical form.** The project calls it the IR, short for intermediate representation. It is one description of filters, sorting, grouping and paging that does not depend on AG Grid or on any database.
4. **Checks.** Before compiling, Craticula checks the canonical form against your schema and the resource limits. It also converts each value to the type the schema declares.
5. **Compiler.** One compiler per backend writes the query. The SQL compiler has one writer per database dialect.
6. **Query and parameters.** For SQL, you get statement text plus a list of values. The values are never part of the text.

Because every backend reads the same canonical form, the same request means the same thing everywhere. The rules for details such as null handling and case sensitivity are written once, in the specification, and every compiler follows them.

## The schema is the boundary

The schema is a JSON document you write. It names the table or collection and the columns the grid may use. Each column has a type and a physical name in the database. It also names a stable key, a column with unique values that Craticula uses to keep paging in a fixed order.

A column that is not in the schema cannot reach a query. See [The safety model](safety-model.html) for how that works.

## What the request can ask for

- **Paging.** The grid asks for a range of rows, such as the first 50. Craticula turns that into a limit and an offset, or the equivalent for your backend. A page has a maximum size.
- **Sorting.** Sorting runs in the order the grid sent. Craticula adds the stable key at the end so that rows with equal values always come back in the same order.
- **Filtering.** Text, number and date filters become comparisons joined with AND or OR. Case-insensitive matching is the default for text.
- **Grouping.** For grouped grids, the request carries the group columns, the group keys already opened and the aggregations to compute. Craticula builds the grouped query for the level being asked about.

## A small example

This is the request from the quickstart. It asks for customers containing "acme" with an amount above 100, biggest amounts first, rows 0 to 50.

```json
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
```

For PostgreSQL, the quickstart program prints this statement and these parameters:

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

Look at what happened:

- "acme" and 100 are not in the text. They are the parameters.
- The table and column names come from the schema, not from the request.
- The sort ends with `id`, the schema's stable key.
- The page range became `LIMIT 50 OFFSET 0`.

SQL Server gets a different statement from the same request, because it spells case-insensitive matching and null ordering differently. The [C# quickstart](quickstart-csharp.html) shows both.

## What you write in C#

In the quickstart, the code does four things in this order:

1. Parse the schema with `GridSchema.Parse`.
2. Parse the request with `AgGridRequestParser.Parse`.
3. Validate with `GridFilterPipeline.Process`. This applies the column check, the limits and the type conversion.
4. Compile with `SqlQueryBuilder.Build` and a dialect such as `PostgresDialect.Instance`.

MongoDB and OpenSearch have their own builders, `MongoPipelineBuilder` and `SearchQueryBuilder`.

## Where this comes from

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
