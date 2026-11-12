# Paging and sorting

This page covers how the row range and the sort order of an AG Grid request become paging and ordering in the query. It is for a developer who wants to know why rows come back in a given order, and what each backend does to page through them.

## From startRow and endRow to a page

AG Grid asks for a block of rows with `startRow` and `endRow`. `endRow` is exclusive. The page size is `endRow - startRow`.

Craticula turns that into a row count and an offset. The count is the page size. The offset is `startRow`. A request for rows 50 to 100 asks for 50 rows after skipping 50.

The adapter refuses a window that makes no sense:

- a negative `startRow`;
- an `endRow` below `startRow`;
- an `endRow` equal to `startRow`, which is an empty window.

A page also has a maximum size. The default is 1000 rows. See [Limits](limits.html).

## A request with no window

Some requests send no `startRow` and no `endRow`: a custom client, or a request built by hand. Since version 1.2.0 such a request gets a default page of 100 rows, `[0, 100)`. The size is `AgGridParseOptions.DefaultPageSize`, and the page size limit checks it like any other window. Before 1.2.0 a request without a window meant every matching row.

There are two ways to ask for every row, and both are deliberate:

- **An export of everything** (`exportScope` set to `"all"`). It has no page and the adapters stream it chunk by chunk. See [CSV export](csv-export.html).
- **The flag `ignorePageLimit: true`**, which works only when your host has switched on `AgGridParseOptions.AllowUnboundedRows` (off by default). Without that switch the request is refused with the parse error `unbounded-not-allowed`; it is never quietly capped. A request that carries a window keeps its window and the flag changes nothing.

The adapters read an all-rows request by streaming. The paged `FetchPageAsync` of the MongoDB, Dapper, EF Core and OpenSearch adapters refuses the unpaginated page, so no call loads the whole result into memory. Use the export stream for those requests. The rules are PG-1 to PG-5 in [Default page size](default-page-size.html).

## What each backend does

| Backend | How the page is written |
|---|---|
| PostgreSQL, MySQL, SQLite | `LIMIT n OFFSET m` |
| SQL Server, Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | a `$skip` stage, then a `$limit` stage |
| OpenSearch and Elasticsearch | `from` and `size` |

For SQL, the two numbers are parameters, not part of the text. SQL Server and Oracle bind the offset before the row count. PostgreSQL, MySQL and SQLite bind the row count first. You do not have to care, because the parameter list is in the order the placeholders appear.

An export of everything has no page at all. It asks for every matching row and gets no paging clause. See [CSV export](csv-export.html).

## Sort order

The grid sends a list of sort keys in `sortModel`. Craticula keeps them in that order. Each key has a column and a direction, `asc` or `desc`.

A sort on a column that the schema does not list is refused, in Strict and in Lenient mode. The refusal comes from the compiler, which throws its own compilation exception. See [Strict and Lenient](strict-and-lenient.html).

The schema has a `sortable` flag for each column. Nothing reads it (as of this version). A column that is in the schema can be sorted whatever its flag says. Do not rely on the flag to stop a column from being sorted.

## Where nulls go

AG Grid does not say where null values should sort. Craticula decides, and it decides the same way for every backend:

- an ascending sort puts nulls last;
- a descending sort puts nulls first.

Databases disagree about this by default, so Craticula never leaves it to the database. It writes the position into every sort key.

PostgreSQL, SQLite and Oracle have `NULLS FIRST` and `NULLS LAST`, and Craticula uses them. SQLite needs version 3.30.0 or later for that. SQL Server and MySQL have no such syntax, so Craticula adds a leading test that puts null rows in their own bucket: `CASE WHEN ... IS NULL` on SQL Server and `ISNULL(...)` on MySQL. MongoDB gets a helper field per sort key that is removed again after the sort. OpenSearch gets `"missing": "_last"` or `"_first"`.

## Text sorts without regard to case

A text column compares without regard to case by default. Sorting follows the same rule, so `apple` and `Apple` sort together. A column can ask for exact case in the schema with `text.caseSensitivity` set to `sensitive`.

Each engine reaches the same result in its own way:

- PostgreSQL names a collation, `craticula_ci`, that you create once.
- SQL Server and SQLite name a collation inline in the query.
- MySQL uses the collation of the column itself.
- MongoDB sets a collation on the whole query.
- OpenSearch sorts on a normalized sub-field that you map in the index.

What you have to set up for each database is on [Index and database guidance](index-guidance.html).

## The stable key keeps paging in order

Paging is only reliable if the order is total. If two rows tie on every sort key, the database may return them in either order, and a row can appear on two pages or on none.

To prevent that, the schema names a `stableKey`, a column whose values are unique. When the sort does not already end in that key, Craticula adds it at the end, ascending, nulls last.

The quickstart request sorts by `amount` descending. The statement ends like this:

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

Craticula also tidies the sort before it adds anything:

- a column named twice keeps only its first appearance;
- if the stable key sorts exactly, every key after it is dropped, because no tie is left to break.

A text stable key that ignores case is the exception. Two keys that differ only in case compare as equal, so the later keys stay and an exact tiebreaker is added.

This only works if the stable key is truly unique. Most databases let a unique column hold many nulls, which breaks the guarantee. Declare the key `NOT NULL`. See [Index and database guidance](index-guidance.html).

## Deep paging

SQL and MongoDB grid pages use an offset. The database has to walk past every skipped row, so a page deep in a large table is slower than a page near the start. Index your filters and measure.

OpenSearch refuses plain `from` and `size` past 10,000 rows. The OpenSearch adapter handles this for you. Past that point it switches to a point in time and `search_after`, and it keeps a cursor between requests. Three things follow:

- You must give it one cursor cache that lives as long as the grid session. `InMemorySearchCursorCache` is the one that ships. A new cache for every request defeats the cursor.
- The first request that crosses the threshold walks forward from row zero. The blocks after it are quick.
- The total row count above 10,000 is reported as unknown unless you ask for the exact count, which costs a full count on each first request.

See [MongoDB and OpenSearch adapters](search-adapters.html).

## Where this comes from

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- Related pages: [How a request becomes a query](request-to-query.html), [Grouping and aggregation](grouping-and-aggregation.html), [Dialects and providers](dialects-and-providers.html)
