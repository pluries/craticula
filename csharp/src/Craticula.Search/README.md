# Craticula.Search

The search compiler of Craticula. It turns the canonical IR into an OpenSearch or Elasticsearch search request body
(plain JSON). It has no client dependency and never opens a connection (use `Craticula.OpenSearch.Client` to run it
against OpenSearch).

## Install

```
dotnet add package Craticula.Search
```

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Search;

public static class Example
{
    public static SearchQuery Compile(GridSchema schema, FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page)
    {
        SearchQuery query = SearchQueryBuilder.Build(
            new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page });

        // query.Index names the index; query.ToArtifact() is the request body.
        return query;
    }
}
```

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
