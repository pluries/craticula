# Dialects and providers

This page lists the databases Craticula can write queries for, how their queries differ, and which versions are tested. It is for a developer who is choosing a database or a dialect, or who wants to know why the same request gives different text on each.

## What a dialect is

The same request means the same thing on every backend. Craticula decides what it means once, in the canonical form. Then one writer per database spells it in that database's language.

For SQL, that writer is a dialect. A dialect class has a single shared `Instance`, such as `PostgresDialect.Instance`. You pass it to `SqlQueryBuilder.Build`. There are five:

| Database | Dialect class |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL (MariaDB goes through the same dialect but has never been tested) | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB and OpenSearch have their own compilers, `MongoPipelineBuilder` and `SearchQueryBuilder`. They do not take a dialect. See [MongoDB and OpenSearch adapters](search-adapters.html).

## How the SQL differs

| Database | Placeholder | Quoting | Paging |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` and `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` and `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` and `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

In every case the values are parameters, listed in the order the placeholders appear. Every table and column name is quoted, and a quote character inside a name is doubled. See [The safety model](safety-model.html).

PostgreSQL passes an "in" list as one array parameter. The other databases write one placeholder for each value.

## Null ordering

Craticula states where nulls sort in every query, so the order does not depend on the database's default. The way it says so depends on the database:

- PostgreSQL, SQLite and Oracle have `NULLS FIRST` and `NULLS LAST`. SQLite needs version 3.30.0 or later.
- SQL Server has no such syntax. The query sorts first on `CASE WHEN column IS NULL THEN 1 ELSE 0 END`, then on the column.
- MySQL has none either. The query sorts first on `ISNULL(column)`, then on the column.
- MongoDB sorts on a helper field that marks nulls, which the query removes afterwards.
- OpenSearch uses `"missing": "_first"` or `"_last"`.

See [Paging and sorting](paging-and-sorting.html).

## Case-insensitive comparison

A text field compares without regard to case unless the schema says otherwise. Each database gets there differently:

| Database | How it ignores case |
|---|---|
| PostgreSQL | `COLLATE craticula_ci` on comparisons and sorts, which you create once. `ILIKE` for `contains`, `startsWith` and `endsWith`. |
| SQL Server | `COLLATE Latin1_General_CI_AS` in the query. A case-sensitive field gets `Latin1_General_CS_AS`. |
| MySQL | Nothing in the query. The column's own collation decides. A case-sensitive field needs a `_bin` or `_as_cs` column. |
| SQLite | `COLLATE NOCASE`, which folds ASCII letters only. |
| Oracle | `COLLATE BINARY_CI`. A case-sensitive field gets `COLLATE BINARY`. |
| MongoDB | A collation on the whole query, with locale `en` and strength 2. |
| OpenSearch and Elasticsearch | The `case_insensitive` option on term and wildcard queries, and a normalized sub-field for sorting and ranges. |

Two cases are silent: a case-sensitive field on MySQL, and the grouping columns on SQL Server, MySQL and Oracle. The statement runs and returns wrong rows if the column's collation is not the one Craticula assumes. Index and database guidance lists what to set for each: [Index and database guidance](index-guidance.html).

## Versions

These are the lowest versions the compiled queries need, taken from the specification and the vendors' documentation, not from a test run. Only the tested column was run. The Elasticsearch adapter is documented for 8.x.

| Database | Minimum | What the tests ran against |
|---|---|---|
| PostgreSQL | 12, with ICU | 16 |
| SQL Server | none stated | 2022 |
| MySQL | none stated | 8.4 |
| SQLite | 3.30.0 | not recorded |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

"None stated" means the code and the specification set no floor, not that every old release has been tried. MariaDB uses the MySQL dialect, but no test runs on MariaDB.

The tests run the compiled queries against real databases in containers. That run needs Docker and is not part of the quick test run, so check the repository for the latest state.

## Oracle's status

Oracle is supported as a community-tested dialect, not as a v1 core dialect. It is graded the same way as the others: every statement is compared with a stored expected text. The difference is coverage. It is checked against a smaller set of examples than the other four, 45 in all. Those 45 also run against a real Oracle Database Free 23ai server.

Oracle 12.2 to 21c have not been run. The 12.2 minimum comes from Oracle's documentation, not from a measurement.

Three Oracle facts shape the output:

- **Empty text is null.** A text value of `""` in a comparison would silently match the wrong rows, so the Oracle dialect refuses it. Use the blank and not-blank operators instead.
- **Names must be quoted.** Create the table and its columns with quoted names that match the schema exactly.
- **Session settings.** Date, timestamp and number formats come from the session, so set them as [Index and database guidance](index-guidance.html) describes.

## Providers

A provider here means the library that actually talks to the database. Craticula does not choose one for you.

- For SQL, `Craticula.Dapper` runs any dialect on an open `IDbConnection`, whichever ADO.NET provider made it.
- `Craticula.EntityFrameworkCore` uses the provider of your `DbContext`. It needs an `EfCoreProviderSemantics` that describes your engine, and only the SQLite one is supplied. See [Entity Framework Core and Dapper](relational-adapters.html).
- MongoDB runs through the official MongoDB .NET driver, and OpenSearch through the `OpenSearch.Client` low-level client.

The repository has a demo app in `examples/demo` that you run yourself. It reads the same synthetic orders from several of these databases and compares the answers.

## Where this comes from

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- Related pages: [Index and database guidance](index-guidance.html), [Paging and sorting](paging-and-sorting.html), [The GridSchema](the-gridschema.html)
