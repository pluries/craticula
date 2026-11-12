# Craticula.MongoDB.Driver

The MongoDB execution adapter of Craticula. It compiles the canonical IR with `Craticula.Mongo` and runs the
aggregation pipeline through the official MongoDB .NET driver, with paging, counts and streamed export.

## Install

```
dotnet add package Craticula.MongoDB.Driver
```

Depends on `MongoDB.Driver` `[3.13.0, 4.0)` and `Craticula.Mongo`.

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;
using Craticula.MongoDB.Driver;
using MongoDB.Driver;

public static class Example
{
    public static Task<MongoGridPage> Fetch(
        IMongoDatabase database, GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page) =>
        MongoGridQuery.FetchPageAsync(
            database,
            new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
            includeRowCount: true);
}
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
