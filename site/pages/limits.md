# Limits

This page lists the resource limits that Craticula puts on every request, what each one protects, and how to change it. It is for a developer who runs a public grid, or who wants to know why a large request was refused.

## Why there are limits

A request is input from a stranger. Without limits, a request could ask for a filter tree nested a thousand levels deep, a list of a million values, or a page of ten million rows. Each of those costs your database a lot of work.

Craticula refuses such a request before it builds a query.

## The limits and their defaults

| Setting | Default | What it limits |
|---|---|---|
| `MaxDepth` | 8 | How deeply filters can nest. A single condition is depth 1. |
| `MaxLeaves` | 64 | The number of conditions in the whole filter, added up across every branch. |
| `MaxInValues` | 1000 | The number of values in one "in" or "not in" list. |
| `MaxPageSize` | 1000 | The number of rows in one page, that is `endRow - startRow`. |
| `MaxSetValuesResults` | 10000 | The most values one distinct-values request can return, however many the grid asks for. |
| `DefaultSetValuesResults` | 1000 | How many values that request returns when the grid does not say. |
| `MaxQueryTimeMs` | not set | How long a MongoDB or Search query may run, in milliseconds. The one optional limit; see [The query time limit](#the-query-time-limit). |

These are properties of `ResourceLimits`.

The first four are checks: a request over the limit is refused. The next two are caps. `MaxQueryTimeMs` is neither: it is carried into the query, and the database enforces it. A distinct-values request for a set filter is never refused for being too large. Craticula clamps it to the cap, and uses the default when the grid sends no number.

A request that sends no `startRow` and no `endRow` is not unlimited either: it gets a default page of 100 rows (`AgGridParseOptions.DefaultPageSize`), and the page size limit checks that page like any other. See [Paging and sorting](paging-and-sorting.html).

The page size limit does not apply to an export of the whole result (`exportScope` set to `"all"`), which has no page. A page-scoped export keeps its row range, and the page size limit applies to it. See [CSV export](csv-export.html).

Craticula counts the groups a user has opened together with the filters. Each opened group is one more condition, and a grouped request counts one level more than it writes, so its effective depth limit is 7 with the default.

## Limits that are fixed

A few bounds are built in and cannot be changed:

- at most 64 group columns in a request;
- a text value in a filter of at most 8192 characters;
- a decimal value of at most 128 characters;
- a column id of at most 256 characters, in a sort key, a group column, an aggregation or the column of a set filter.

## What a refusal looks like

When a request breaks a limit, `GridFilterPipeline.Process` throws a `ResourceLimitExceededException`. Its `Violations` list names every limit that was broken, with the actual number and the maximum. Catch it in your endpoint and return a client error. If a request breaks two limits, you see both.

## How to change a limit

The limits are not part of the schema file. They are code, and you pass them in. This is how the demo sets its own:

```csharp
public static ResourceLimits Default { get; } = new()
{
    MaxPageSize = 500,
    MaxDepth = 6,
    MaxLeaves = 32,
    MaxInValues = 200,
    MaxSetValuesResults = 1_000,
    DefaultSetValuesResults = 200
};
```

Then pass the value to the calls that take one. The quickstart passes `new ResourceLimits()`, which means the defaults.

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

A distinct-values request goes through `GridFilterPipeline.ProcessSetValues`, and its cap comes from `ResourceLimitsValidator.ResolveSetValuesLimit`.

You can raise a limit as high as you like. There is no upper bound check. Choose numbers your database can carry.

## The query time limit

`MaxQueryTimeMs` is for a host whose database is shared or public. The other limits bound the shape of a request; this one bounds the work the database does for it. Set it to a whole number of milliseconds, from 1 to 2,147,483,647, and the compilers put it into the query:

| Engine | What the query carries | What happens when the time is up |
|---|---|---|
| MongoDB | `maxTimeMS` on the aggregate command | MongoDB cancels the operation, and the adapter throws `QueryTimeoutException`. |
| OpenSearch and Elasticsearch | a `timeout` member of the search body, for example `"2000ms"` | The engine stops at its next check (a soft limit) and answers with `timed_out: true`. The adapter throws `QueryTimeoutException` and never returns the partial hits as a page. |

The limit comes from your code only. A request cannot set, raise or remove it, and a `maxQueryTimeMs` in a request is ignored. An export carries no limit, because it is long by design; stop an export with the cancellation token. The SQL engines have no compiled limit: set a statement timeout on the connection or the database account instead (the public demo does, for PostgreSQL).

Leave it unset and nothing changes: the queries are exactly what they were. A zero or negative value throws when you build the `ResourceLimits`, and the compilers refuse it too if you fill a request by hand. See the rules in [Query time limit](query-time-limit.html).

## You cannot turn a limit off

Every limit but one is a plain positive number, and there is no "unlimited" value. Setting a limit to zero or less throws an `ArgumentOutOfRangeException` when you build the `ResourceLimits`. The exception is `MaxQueryTimeMs`, which is unset by default because the library cannot know how slow your database is; setting it to a number never turns anything off.

That is on purpose. A limit of zero would not mean "no limit". It would refuse every request, and a setting that was left blank by mistake could do that without anyone noticing.

## Where the checks run

The limits are checked by `GridFilterPipeline.Process`. The adapter that reads the AG Grid request does not check them, and neither do the compilers. If you skip the pipeline and call a compiler yourself, no limit is checked. The quickstart calls the pipeline for that reason. See [How a request becomes a query](request-to-query.html).

## Where this comes from

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md), the addenda on the query time limit and the default page size
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- Related pages: [The safety model](safety-model.html), [Paging and sorting](paging-and-sorting.html), [The GridSchema](the-gridschema.html)
