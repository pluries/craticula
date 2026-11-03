# The GridSchema

This page explains the schema you write for each grid: what it holds, which of its settings Craticula enforces today, and how to start one. It is for a developer who is about to describe a table, a collection or an index to Craticula. For the full list of members, see the [GridSchema reference](grid-schema.html).

## What the schema is for

The schema is the boundary between the request and your data. It is a JSON document that you write and keep on the server. It names the table, collection or index. It lists every column the grid may touch. For each column it gives a type and the physical name in your database.

A column that is not in the schema can never reach a query. Table names and column names in a query come from the schema, never from the request. See [The safety model](safety-model.html).

No request can carry a schema. The grid sends columns by their grid id, and Craticula looks each one up.

## A small example

This is the schema from the quickstart. It describes an `orders` table.

```json
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
```

In C#, load it with `GridSchema.Parse(json)`.

## The members of the whole schema

| Member | What it does |
|---|---|
| `mode` | `strict` or `lenient`. The JSON Schema requires it; the C# parser defaults to strict when it is missing. See [Strict and Lenient](strict-and-lenient.html). |
| `source` | The table or view, the MongoDB collection, or the OpenSearch index. It cannot be blank. |
| `stableKey` | A column with unique values. It must be one of the `fields`. |
| `fields` | The allowlist, keyed by the grid's column id. It needs at least one field. |
| `staticFilter` | A filter added to every query. Optional. |

`GridSchema.Parse` refuses a schema that breaks these rules. It also refuses unknown members, duplicate keys, and a `physical.sql` that does not set exactly one of `column`, `qualifiedColumn` and `expression`.

## The members of one field

| Member | What it does |
|---|---|
| `type` | `string`, `int64`, `decimal`, `double`, `boolean`, `date` or `datetime`. Craticula converts every request value to this type. |
| `physical` | Where the column lives: `sql`, `mongo`, `search`, or all three. |
| `text` | For a `string`: `caseSensitivity` (`insensitive` by default) and `searchMode`. |
| `filterable`, `sortable`, `groupable`, `aggregatable` | What the grid may do with the column. See below. |
| `exportable`, `label`, `format` | How the column appears in a CSV export. See [CSV export](csv-export.html). |

You only need the mappings for the backends you use. A SQL mapping is a plain column. A MongoDB mapping is a document path. A search mapping names the index field, and can name a `keywordSubField` and a `normalizedSubField` too. A field with no mapping at all uses its column id as the name.

## What each flag does today

Do not assume that every flag is enforced. This is what the code does today:

| Flag | Default | Enforced? |
|---|---|---|
| `filterable` | `true` | Yes. A filter on a column marked `false` is refused in Strict mode and dropped in Lenient mode. The column of a set filter's value list, and a group key the user has opened, must be filterable and are refused in both modes. |
| `groupable` | `false` | Yes. A group column must be groupable. Refused in both modes. |
| `aggregatable` | none | Yes. An aggregation must use a function in this list. Refused in both modes. |
| `exportable` | `true` | Yes. It decides the default export columns, and a column marked `false` cannot be named in `exportColumns`. |
| `sortable` | `true` | **No.** Nothing reads it today. A column in the schema can be sorted whatever the flag says. |

The `aggregatable` list holds any of `sum`, `min`, `max`, `avg` and `count`. See [Grouping and aggregation](grouping-and-aggregation.html).

If you must stop a column from being sorted, leave it out of the schema, or rely on a check of your own. The flag will not do it.

## The stable key

The `stableKey` is how paging stays in order. Craticula adds it to the end of every sort. It must name a column whose values are unique. Declare the column `NOT NULL` in your database, because most databases allow many nulls in a unique column and that breaks the guarantee. See [Paging and sorting](paging-and-sorting.html).

## The static filter

`staticFilter` is a condition that Craticula adds to every query with AND. It is the place for a tenant id or a soft-delete flag. The request cannot change it or remove it.

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

The field a `staticFilter` names must also be declared in `fields`, so the compiler can find its column. The condition is part of the schema, so the request cannot reach it. Deciding what the filter should be is your job. Craticula only applies it. See [The safety model](safety-model.html).

## Field order

The order of the fields in the document counts. An export request with no column list gets the exportable fields in that order. The rows inside an opened group are also returned in that order.

## Where this comes from

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- Related pages: [Limits](limits.html), [Dialects and providers](dialects-and-providers.html), [How a request becomes a query](request-to-query.html)
