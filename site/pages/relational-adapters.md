# Entity Framework Core and Dapper

This page covers the two optional packages that run Craticula queries on a relational database: `Craticula.Dapper` and `Craticula.EntityFrameworkCore`. It is for a developer who has a SQL database and wants Craticula to run the query as well as write it.

## Why adapters exist

The core packages only compile. They never open a connection and never run anything. An adapter closes that gap for one data access library. It compiles the request, runs it, and gives you rows.

Adapters are optional. The core packages never depend on them. You can skip them and run the compiled statement yourself with any library you like.

Nothing is published yet. Build the packages from the repository and reference the projects. See [the C# quickstart](quickstart-csharp.html).

## Dapper

`Craticula.Dapper` compiles with `Craticula.Sql` and runs the statement on a connection you hand in. Use it when you want to see and control the SQL.

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

What it gives you:

- `DapperGridQuery.FetchPageAsync` returns one page. `DapperGridPage` has the `Columns`, the `Rows` and an optional `RowCount`.
- `DapperGridQuery.CountAsync` runs only the count.
- `DapperExportStream.StreamAsync` streams every matching row for an export. See [CSV export](csv-export.html).

What it needs from you:

- An open `IDbConnection`. The adapter never opens or closes it.
- The dialect that matches your database. See [Dialects and providers](dialects-and-providers.html).
- Dapper itself, in the range `[2.1.89, 3.0)`.

Grouped requests work through the same method. The SQL compiler already writes the grouped statement, so the adapter just runs it.

## Entity Framework Core

`Craticula.EntityFrameworkCore` does not write SQL text. It builds `IQueryable<T>` expression trees, and the EF Core provider turns them into SQL. Use it when you already have a `DbContext` and want its global query filters, such as a tenant filter, to apply.

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

What it gives you:

- `EfCoreGridQuery.FetchPageAsync` returns one page, in an `EfCoreGridPage` shaped like Dapper's.
- `EfCoreGridQuery.CountAsync` runs only the count.
- `EfCoreExportStream.StreamAsync` streams rows for an export.

What it needs from you:

- **A source query.** Pass a `DbSet<T>`, or `GridSchemaPropertyBag.Query(context, schema)` if you have no entity classes. For the second form, call `GridSchemaPropertyBag.Configure` in `OnModelCreating`.
- **Matching property names.** Each field is read as an EF property named after its `physical.sql.column`, or after the column id when there is none. A class that renames its columns with `HasColumnName` must line up with that.
- **An `EfCoreProviderSemantics` value.** It states five facts about your database that EF cannot tell Craticula, such as the name of the case-insensitive collation. Only `EfCoreProviderSemantics.Sqlite` ships, because it is the only one that has been measured. For another engine you declare your own, once, next to your `DbContext`.

The fields of the schema must use a plain `physical.sql.column`. A field with `qualifiedColumn` or `expression` is refused, because neither has a form in an expression tree.

If one `DbContext` type can be built from more than one schema, register `GridSchemaModelCacheKeyFactory` and implement `IGridSchemaModel` on the context. Without that, EF reuses the first schema's model for the next schema and fails with errors that do not mention caching.

### Two silent traps

Both of these give wrong rows without an error. The adapter cannot see your model or your collations, so it cannot guard against them.

- **SQLite date and time values.** Store a `datetime` as `yyyy-MM-ddTHH:mm:ss.fffZ` text and map every `DateTime` to and from that text in your `DbContext`. EF's own mapping uses a different form, and SQLite compares text character by character.
- **`PatternMatchFoldsCase`.** It says whether the engine's `LIKE` ignores case. Use `true` for SQLite. For SQL Server and MySQL use `false`, unless every searchable column has a collation that ignores case. A binary-collated column otherwise matches only the exact case.

Date and time cells leave a page or an export as UTC values whatever the provider returned.

## What both adapters share

- **Row counts are opt-in.** The count is a second round trip, so it is off unless you pass `includeRowCount`. A grid needs it once per filter change, not once per block.
- **Exports never use an offset.** They read the rows in chunks of 5,000 by walking the sort keys, so a late chunk costs the same as an early one. `DapperExportOptions` and `EfCoreExportOptions` have a `ChunkSize` to change that. The export needs a truly unique stable key. A duplicate is detected and raises an exception.
- **Dapper refuses some exports.** `DapperExportStream` refuses a schema whose stable key is a text column. It also refuses an export where a text sort key holds an empty string in the exported rows, on every dialect except Oracle. In both cases use a numeric or date stable key, or fetch the data page by page with `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` has no such check.
- **A page-scoped export is refused.** The export streams take the whole result. A bounded page goes through the page method.
- **A neutral result.** Each page has a `ToGridPageResult()` extension. The OpenSearch one also takes the `SearchQueryRequest` you used. `LoadSuccessParamsMapper.Map` in `Craticula.AgGrid` turns that into the shape AG Grid expects.

## What they never do

- They never open, close or pool a connection, and they never start a transaction.
- They never retry a failed query or set a timeout. The connection and the command settings are yours.
- They never enforce a maximum number of exported rows.
- They never apply your resource limits or the column checks of your schema. Run `GridFilterPipeline.Process` first, as the quickstart does. See [The safety model](safety-model.html).

## Which one to pick

| You have | Use |
|---|---|
| A plain `IDbConnection` and want to see the SQL | Dapper |
| Any of the five SQL dialects, with no extra code | Dapper |
| A `DbContext` with global query filters you want to keep | Entity Framework Core |

The demo runs both on PostgreSQL, so you can compare them on the same data.

## Where this comes from

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Related pages: [CSV export](csv-export.html), [MongoDB and OpenSearch adapters](search-adapters.html), [Paging and sorting](paging-and-sorting.html)
