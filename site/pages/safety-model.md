# The safety model

This page lists what Craticula does to keep a hostile request from hurting your database, and what it does not do. It is for a developer or reviewer who needs to judge whether Craticula fits a system that faces the public.

## Values are parameters

Every value from the request goes into the query as a parameter. It is never pasted into the text.

For SQL, the statement holds placeholders such as `$1` and the values travel in a separate list. For the quickstart request, the text contains no "acme" and no 100. See [How a request becomes a query](request-to-query.html).

The specification applies the same idea to MongoDB and OpenSearch. There, values go into the pipeline or query document as data. A text search value that holds pattern characters is escaped. The compilers have helpers for that.

A value such as `'; DROP TABLE users; --` sent in an ordinary text filter is just a string. It is compared and does nothing else. The adversarial fixtures are about the shape of the request, not about string contents.

## Identifiers come from your schema

Table names, collection names and column names come only from the schema you wrote. The request never supplies one.

The request names columns by their grid id, such as `customer`. Craticula looks that id up in the schema and uses the physical name you declared. For SQL, the name is quoted for the dialect, and a quote character inside a name is doubled.

## Unknown columns are refused

A column that is not in the schema is refused before any query exists. The quickstart shows a filter on `password` being rejected.

A column that is not in the schema cannot be used to group, aggregate or sort, in any mode. A filter on such a column is refused in Strict mode and dropped in Lenient mode; see [Strict and Lenient](strict-and-lenient.html). A schema can also mark a column as not filterable, groupable or exportable.

## Malformed input is refused

The adapter and the checks reject input they do not recognise:

- an unknown filter operator, including a typo or `regex`;
- a filter value sent as an object or an array where a single value is expected;
- duplicate keys in the JSON;
- a value that does not fit the column type, such as text in a number column;
- duplicate output names for aggregations.

Each of these has a fixture that expects a clean rejection.

## Resource limits

A request cannot ask for unlimited work. These are the defaults in `ResourceLimits`:

| Limit | Default |
|---|---|
| Filter tree depth | 8 |
| Conditions in the whole filter | 64 |
| Values in one in or not-in list | 1000 |
| Rows in one page | 1000 |
| Rows returned by a distinct-values request | at most 10000 |

You can set each one higher or lower. You cannot turn a limit off. Zero or a negative number is refused when you set it.

The fixtures test each limit one step past the edge, and with extreme values such as a 5000-value list or a page of one million rows.

## What Craticula does not protect against

- **The database account.** Craticula does not control what the account can do. Give the account that runs these queries the least rights it needs, such as read-only on the one table.
- **Running the query.** Craticula never runs it. Connection handling, timeouts, cost limits and how you run the statement are yours.
- **Who may use the grid.** Authentication and per-user access are outside its scope. The schema can add a fixed filter to every query, but it is up to you to decide what that filter should be.
- **A wrong schema.** If your schema lists a column that should stay hidden, Craticula will serve it.
- **Slow queries.** A request inside the limits can still be slow if the column has no index. See the [index guidance](index-guidance.html).

## Where this comes from

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
