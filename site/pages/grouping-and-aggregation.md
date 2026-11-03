# Grouping and aggregation

This page covers row grouping and aggregation: how a grouped grid asks for one level at a time, how Craticula answers each level, and what the schema has to allow. It is for a developer whose grid groups rows and shows totals. Row grouping and aggregation are AG Grid Enterprise features.

## One level per request

A grouped grid does not ask for the whole tree. It asks for one level at a time, and every request carries the path so far.

Two lists in the request describe that path:

- `rowGroupCols` lists the columns the grid groups by, in order.
- `groupKeys` lists the groups the user has already opened, one key for each level.

Craticula compares the two lengths:

- **Fewer keys than columns.** The request asks for a grouped level. Craticula groups by the next column that has no key yet, and only that one. It computes the aggregations for each group.
- **As many keys as columns.** Every level is open. The request asks for the rows inside the last group. Craticula returns plain rows and does no grouping.
- **More keys than columns.** The request is malformed and is refused.

Pivot mode is not supported. A request with `pivotMode` set to `true`, or with any `pivotCols`, is refused.

## An example

Take a grid grouped by `region`, then `segment`, then `product`, with a sum of `amount`. The user has opened the `EMEA` region. The grid now asks for the segments inside `EMEA`.

For PostgreSQL, Craticula writes:

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

The opened group became `WHERE "region" = $1`. The next column, `segment`, became the `GROUP BY`. The aggregate is named `amount_sum`.

## Group keys arrive as typed values

Craticula reads each entry in `groupKeys` as a typed value, typed to match the column's declared type, not as the plain string AG Grid sends:

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

Your page has to convert the keys before it posts the request. The demo does it in `toWireRequest` in `examples/demo/web/src/datasource.ts`. It also renames the aggregate columns on the way back, because the response names them `amount_sum` and the grid reads `amount`. If you copy the demo, copy both steps.

## Which functions you can use

Craticula supports five aggregation functions: `sum`, `min`, `max`, `avg` and `count`. Another function, such as `first`, is refused. So is a `valueCols` entry with no `aggFunc`.

The name of each aggregate in the result is the column id when it differs from the field name. Otherwise it is the field name, an underscore and the function, such as `amount_sum`.

Some details that matter for the numbers:

- `count` counts the rows where the field is not null. It does not count rows. To count every row, count the stable key, which is never null.
- A `sum` over a group with no values is `0` on every backend. The SQL compilers wrap `sum` so that it matches.
- `avg`, `min` and `max` over a group with no values are null.

## What the schema must allow

The schema decides which columns may be grouped and aggregated. Both flags are off by default.

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- A group column must be in the schema and marked `groupable`.
- An aggregation must name a column in the schema and a function in that column's `aggregatable` list.
- A column that has been opened, so that its key is in `groupKeys`, must also be `filterable`. Opening a group is the same as filtering on one value.

Each of these is refused in both modes, Strict and Lenient. Dropping a group column or a key would hand the grid a different answer than the one it asked for. See [Strict and Lenient](strict-and-lenient.html).

## Opening a group matches exactly

When a group is opened, its key becomes an exact match on the group column. Grouping, opening a group and ordering the groups all use exact comparison, so `EMEA` and `emea` are two groups. A group that did not match exactly would not add up to its parent.

That is only true if the database compares exactly by default. PostgreSQL and SQLite do. SQL Server, MySQL and Oracle usually fold case, so declare each column you group by with a binary collation. See [Index and database guidance](index-guidance.html).

MongoDB has one collation for the whole query. A grouping request carries none, so a filter in the same request compares case-sensitively there. The SQL databases fold case in that filter.

## Null group keys

Rows with a null group value form one group. To open it, send a key of `{ "type": "null" }`. Craticula writes a null test for it, such as `"region" IS NULL`.

The empty string is a different group from null, so its rows do not join the null group. Oracle is the exception, because Oracle stores an empty string as null.

## Sorting and counting a grouped level

A grouped level can be sorted by its group column or by one of its aggregates. A sort on any other column is refused. The group column acts as the stable key, so group order is stable. An aggregate listed after the group column in the sort has no effect and is dropped.

The row count for a grouped level is the number of groups, not the number of rows inside them.

OpenSearch and Elasticsearch have two limits here:

- They cannot order a grouped level by an aggregate. Such a request is refused.
- The group that holds null values always sorts first, whatever the direction.

## Exports ignore grouping

An export returns plain rows. The adapter drops `rowGroupCols`, `valueCols` and `groupKeys` from an export request. See [CSV export](csv-export.html).

## Where this comes from

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- Related pages: [Paging and sorting](paging-and-sorting.html), [The GridSchema](the-gridschema.html), [How a request becomes a query](request-to-query.html)
