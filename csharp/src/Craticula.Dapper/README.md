# Craticula.Dapper

The Dapper execution adapter of Craticula. It compiles the canonical IR with `Craticula.Sql` and runs the resulting
parameterized statement on an open `IDbConnection`, with paging, row counts and streamed export.

## Install

```
dotnet add package Craticula.Dapper
```

Depends on `Dapper` `[2.1.89, 3.0)` and `Craticula.Sql`.

## Example

```csharp
using System.Data;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Dapper;
using Craticula.Sql;

public static class Example
{
    public static Task<DapperGridPage> Fetch(
        IDbConnection openConnection, GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page) =>
        DapperGridQuery.FetchPageAsync(
            openConnection,
            new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
            PostgresDialect.Instance,
            includeRowCount: true);
}
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
