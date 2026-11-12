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

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
