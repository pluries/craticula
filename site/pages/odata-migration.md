# Migrating from OData

This page is for a team whose grid talks to an OData service today and wants to move to Craticula. It shows, construct by
construct, what you wrote in OData and the request Craticula takes instead. Every example is a file that a test compiles, so the
request and the statement under it are real and cannot go stale.

Two things are different from the start:

- **Craticula takes the request AG Grid already sends.** There is no URL query string to build. The grid's server-side row model
  posts a JSON body (`filterModel`, `sortModel`, `startRow`, `endRow`, `rowGroupCols`, `valueCols`, `groupKeys`), and Craticula
  compiles it. The "OData" side below is what your service received; the "Craticula" side is what the grid sends.
- **Craticula compiles; it does not serve.** It returns a statement and its parameters. You run it with your own driver, and you
  write the endpoint (see the [C# quickstart](quickstart-csharp.html)).

All examples use one small synthetic schema, `orders` (id, customer, amount, active, status, region, country), and print the
PostgreSQL statement. The other databases get their own spelling of the same request.

{{include site/examples/odata/schema.json json}}

## `$filter`

### A comparison on one column

OData: `$filter=status eq 'active'`. The same holds for `ne`, `gt`, `ge`, `lt`, `le`: they become the filter types `equals`,
`notEqual`, `greaterThan`, `greaterThanOrEqual`, `lessThan`, `lessThanOrEqual`.

{{include site/examples/odata/01-filter-equals.json json}}

{{include site/examples/odata/01-filter-equals.sql.txt sql}}

The comparison is `COLLATE craticula_ci`: **text compares case-insensitively by default** ([Case sensitivity](semantics.html#sem-1)). In OData
the result usually depends on the service and its database. If your users relied on exact case, declare the field
`caseSensitivity: "sensitive"` in the schema.

### `contains`, `startswith`, `endswith`, and `and` across columns

OData: `$filter=contains(customer,'acme') and amount gt 100`. The text functions are the filter types `contains`, `startsWith`
and `endsWith`; `notContains` is the only negation the grid's text filter has. Filters on different columns are joined with AND,
one `filterModel` entry per column.

{{include site/examples/odata/02-filter-two-columns.json json}}

{{include site/examples/odata/02-filter-two-columns.sql.txt sql}}

The `contains` match is escaped: the user's `%` and `_` are literal characters, never wildcards ([Substring matching on OpenSearch](semantics.html#sem-7)).

### `or` on one column

OData: `$filter=amount gt 100 or amount lt 10`. Two conditions on the same column go in the column's `conditions` array with
`operator: "OR"` (or `"AND"`).

{{include site/examples/odata/03-filter-or-on-one-column.json json}}

{{include site/examples/odata/03-filter-or-on-one-column.sql.txt sql}}

### `in`

OData (4.01): `$filter=status in ('active','pending')`. This is the grid's set filter.

{{include site/examples/odata/04-filter-in-list.json json}}

{{include site/examples/odata/04-filter-in-list.sql.txt sql}}

### `ne` and `not`

OData: `$filter=status ne 'blocked'` or `$filter=not (status eq 'blocked')`. In the grid this is the `notEqual` filter type.

{{include site/examples/odata/05-filter-not-equal.json json}}

{{include site/examples/odata/05-filter-not-equal.sql.txt sql}}

Read the statement closely. `status ne 'blocked'` also returns the rows where `status` is `NULL`. Craticula's negative operators
include null rows on purpose ([Null handling](semantics.html#sem-2)), so the grid behaves like AG Grid's own in-memory filter. SQL's
three-valued logic would drop those rows, and an OData service may or may not. Check the old behaviour with a test before you
migrate a filter that excludes values.

### `eq null` and `ne null`

OData: `$filter=region eq null`. There are two forms, and they differ for text columns.

- The grid's `blank` filter type: null **or the empty string** on a text column, only `NULL` on a number or date column.

{{include site/examples/odata/06-filter-null.json json}}

{{include site/examples/odata/06-filter-null.sql.txt sql}}

- An `eq` with a null value, written in the `customFilters` extension: exactly `NULL`, and nothing else
  ([Grouping and drill-down](semantics.html#grp-7)). This is OData's `eq null`.

{{include site/examples/odata/13-filter-exactly-null.json json}}

{{include site/examples/odata/13-filter-exactly-null.sql.txt sql}}

`ne null` has no exact form on a text column. `notBlank` returns the rows that are neither null nor empty. Do not write
`neq` with a null value (it returns only the null rows, as SQL's three-valued logic and SEM-2 combine) or `not` around the null
test (it returns every row).

### Ranges and booleans

`$filter=amount ge 10 and amount le 20` is two conditions on one column joined by AND.

{{include site/examples/odata/10-filter-range.json json}}

{{include site/examples/odata/10-filter-range.sql.txt sql}}

The grid's own in-range option is refused because its two bounds carry no inclusivity; the `customFilters` extension has an `inRange`
operator with the inclusivity written out. A boolean property, `$filter=active eq true`, is the set filter on a boolean column, which
compiles to the `true` operator.

{{include site/examples/odata/11-filter-boolean.json json}}

{{include site/examples/odata/11-filter-boolean.sql.txt sql}}

### Dates and date-times

A date filter takes the grid's wire form: `yyyy-MM-dd`, or `yyyy-MM-dd HH:mm:ss` as a wall-clock time read in the zone the request
carries (`requestContext.zone`) or the parser options name, UTC by default ([Dates and time zones](semantics.html#sem-4)). An OData literal such as
`2026-01-01T00:00:00Z` or one with an offset does not fit that form. Convert it to the request's zone, or send the exact instant
through `customFilters` as a typed `datetime` value that names its zone.

### Anything else: a tree of `and`, `or`, `not`

AG Grid's filters cover one column at a time. For a nesting such as `not startswith(customer,'test') and (status eq 'active' or
amount gt 1000)`, Craticula accepts an extension next to `filterModel`: `customFilters`, a tree of `and`, `or`, `not` and
comparison nodes over the closed set of 17 operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `notContains`,
`startsWith`, `endsWith`, `in`, `notIn`, `inRange`, `blank`, `notBlank`, `true`, `false`. It is also where a negated `startsWith` or
`endsWith` lives, because the grid has no such filter type. The tree is merged with `filterModel` by AND. Its depth and size are
limited (the resource limits of SEC-3), so a huge `$filter` is refused instead of compiled.

{{include site/examples/odata/14-filter-nested-tree.json json}}

{{include site/examples/odata/14-filter-nested-tree.sql.txt sql}}

## `$orderby`, `$top`, `$skip`, `$count`

OData: `$orderby=amount desc,id&$top=20&$skip=40`. `$orderby` is `sortModel`, first entry first. `$skip` is `startRow` and
`$skip + $top` is `endRow` (exclusive), so `$skip=40&$top=20` is `startRow: 40`, `endRow: 60`.

{{include site/examples/odata/07-orderby-and-paging.json json}}

{{include site/examples/odata/07-orderby-and-paging.sql.txt sql}}

Two differences:

- **Null placement.** OData's standard sorts null as the lowest value: first when ascending, last when descending. The grid
  sends no null position, so Craticula uses the opposite, fixed rule: **last when ascending, first when descending**
  ([Null ordering](semantics.html#sem-3)), shown above as `amount DESC NULLS FIRST`. Every ascending sort on a column that holds nulls
  returns those rows in a different place after the migration.
- **A stable order.** A service has to keep `$skip`/`$top` stable between requests. Craticula guarantees it whatever the grid sorts by:
  it always ends the sort with the schema's **stable key** ([Deterministic paging](semantics.html#sem-6)), so two rows never trade places between
  pages.

`$count=true` (the `@odata.count` of the answer) is the row count the execution adapters return next to the page when you ask for it
(`includeRowCount`: `RowCount`, and AG Grid's `lastRow`). On SQL and MongoDB it is a second query. On OpenSearch and Elasticsearch it is
capped by default and reported as unknown above 10,000 rows (see [index guidance](index-guidance.html)).

## `$apply`: `groupby` and `aggregate`

OData: `$apply=groupby((country),aggregate(amount with sum as total))`. The grid's row grouping sends `rowGroupCols` (the group
columns, outermost first), `valueCols` (the aggregates: `sum`, `min`, `max`, `avg`, `count`) and `groupKeys` (the groups the user has
opened).

{{include site/examples/odata/08-apply-groupby-aggregate.json json}}

{{include site/examples/odata/08-apply-groupby-aggregate.sql.txt sql}}

A request returns **one level**. With `groupby((country,region))` the grid asks for the countries first. When the user opens Germany
it sends the group key `Germany` and gets the regions of Germany:

{{include site/examples/odata/09-apply-open-a-group.json json}}

{{include site/examples/odata/09-apply-open-a-group.sql.txt sql}}

One level further, with both keys consumed, it gets the rows:

{{include site/examples/odata/12-apply-leaf-rows.json json}}

{{include site/examples/odata/12-apply-leaf-rows.sql.txt sql}}

AG Grid's own request carries the keys as plain strings (`groupKeys: ["Germany"]`). The parser Craticula ships takes each key as a
typed value (`{"type": "string", "value": "Germany"}`), so a small step in your frontend adapter types the keys from the column
types before the request is parsed. The demo's `toWireRequest` ([`datasource.ts`](../../examples/demo/web/src/datasource.ts)) is ten lines that do it, a null key included.

Differences to know:

- `count` counts the non-null values of a column, not rows ([AGG-1](semantics.html#agg-1)), and the column must list `count` in its
  `aggregatable` setting. To count rows, count the stable key.
- The sum of a group with no values is `0`, and `avg`, `min`, `max` are `NULL` ([AGG-6](semantics.html#agg-6)).
- The group whose key is null is a group of its own, and you open it with a null group key ([Grouping and drill-down](semantics.html#grp-7)).
- The aggregate comes back named `<field>_<function>` (`amount_sum`) unless the grid's column id says otherwise.
- Ordering the groups by an aggregate is not available on the search engines (a composite aggregation lists groups in key order only).

## What has no equivalent

| OData | Why not, and what to do |
|---|---|
| `$expand`, navigation properties, `$filter` across a relationship | A schema reads one source (a table, a collection or an index) and every column is a field of it. Build a view or an index that joins the data and declare the view as the source. |
| `$select` | The columns are the schema's. A request cannot ask for a subset of them, and the **execution adapters** return only the declared fields. With the bare compiler an ordinary row query is `SELECT *`, so a column you do not declare is still in the result: leave it out of the view you declare as the source. An export can name its columns. |
| `$search` | There is no free-text search across fields. Use the text filter on a column, or a search engine index with the `contains` filter. |
| `any` and `all` (lambda operators) | They need a collection property, which a flat source does not have. Denormalize, or filter in a view. |
| Arithmetic (`add`, `sub`, `mul`, `div`, `mod`) and `$compute` | The operator set is closed so every operator has a tested meaning on every database (AR-6 of the technical requirements). Expose the computed value as a column of the source. |
| Functions in `$filter` and `$orderby` (`tolower`, `toupper`, `trim`, `concat`, `substring`, `length`, `indexof`, `year`, `month`, `day`, `round`, `now`) | The same reason. Case-insensitivity is already the default for text, and a date part is a column or a range on the date. |
| `$apply=filter(...)` **before** `groupby` | Put it in `filterModel` or `customFilters`: it filters the rows before they are grouped, as OData does. |
| `$apply` with a filter **after** `aggregate` (the SQL `HAVING`), `topcount`, `concat`, `join`, `compute`, `rollup` | One grouping request has one level and the five aggregates, and `filterModel` always filters rows before they are aggregated. Filter the groups after the query. |
| `countdistinct`, `$count` inside `aggregate`, custom aggregates | The aggregate set is closed: `sum`, `min`, `max`, `avg`, `count`. |
| `$batch`, `$format`, `$metadata`, `$value`, actions and functions | They are about the transport and the service, not the query. Craticula compiles a query and has no service layer. |

## Next

- The rules these examples rely on: [semantics](semantics.html).
- Every setting of the schema: the [GridSchema reference](grid-schema.html).
- Run the same requests on a real database: the [C# quickstart](quickstart-csharp.html).
