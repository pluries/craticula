# Craticula.Sql

The SQL compiler of Craticula. It turns the canonical IR into a parameterized statement (`{ sql, params[] }`) for
PostgreSQL, SQL Server, MySQL/MariaDB, SQLite and Oracle. Values are always bound as parameters and identifiers come
only from your `GridSchema` allowlist. It compiles; it never opens a connection (use `Craticula.Dapper` or
`Craticula.EntityFrameworkCore` to run it).

## Install

```
dotnet add package Craticula.Sql
```

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Sql;

public static class Example
{
    public static SqlQuery Compile(GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page)
    {
        SqlQuery query = SqlQueryBuilder.Build(
            new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
            PostgresDialect.Instance);

        // query.Sql is the statement text, query.Parameters the values to bind in order.
        return query;
    }
}
```

Dialects: `PostgresDialect`, `MssqlDialect`, `MySqlDialect`, `SqliteDialect`, `OracleDialect`.

## Counting rows

`SqlQueryBuilder.BuildCount` compiles the total a grid shows next to a page: the same filter, but no sort and no row window, so the database does not order rows it only counts. Pass `GridFilterPipeline.Process` a `NonePage` for a count, so the page-size limit does not apply to it. A grouped level counts its groups. At a million rows this made the PostgreSQL count 3.6 to 5.5 times faster for filters that match many rows.

## Compatibility

Implements Craticula spec version 1.0.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
