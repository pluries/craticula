# Craticula.Mongo

The MongoDB compiler of Craticula. It turns the canonical IR into a MongoDB aggregation pipeline, written as Extended
JSON with `System.Text.Json`. It has no MongoDB driver dependency and never opens a connection (use
`Craticula.MongoDB.Driver` to run it).

## Install

```
dotnet add package Craticula.Mongo
```

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;

public static class Example
{
    public static MongoQuery Compile(GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page)
    {
        MongoQuery query = MongoPipelineBuilder.Build(
            new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page });

        // query.Collection names the collection, query.Pipeline holds the stages.
        return query;
    }
}
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
