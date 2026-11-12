# Craticula.OpenSearch.Client

The OpenSearch execution adapter of Craticula. It compiles the canonical IR with `Craticula.Search` and runs the
search body through `OpenSearch.Client`'s low-level client, with deep paging (point in time and a cursor cache)
and streamed export.

## Install

```
dotnet add package Craticula.OpenSearch.Client
```

Depends on `OpenSearch.Client` `[2.2.0, 3.0)` and `Craticula.Search`.

## Example

```csharp
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.OpenSearch.Client;
using Craticula.Search;
using OpenSearch.Net;

public static class Example
{
    // One cache per host process, shared by every request of a grid session.
    private static readonly InMemorySearchCursorCache Cache = new();

    public static Task<OpenSearchGridPage> Fetch(
        IOpenSearchLowLevelClient client, string gridSessionId, GridSchema schema,
        FilterNode? filter, IReadOnlyList<SortItem>? sort, PageSpec page) =>
        OpenSearchGridQuery.FetchPageAsync(
            client,
            new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
            gridSessionId,
            Cache);
}
```

## Row count above 10,000

By default a count above the window (`MaxResultWindow`, 10,000) is reported as unknown (`RowCount` is `null`), which is cheap and lets
the grid keep asking for blocks. To get the total, opt in: `new OpenSearchDeepPagingOptions { ExactRowCount = true }` makes the
count request send `track_total_hits: true`. The engine then counts every matching document on each first-block request, so choose it
knowingly. The page query and the compiled request do not change.

## Elasticsearch

The compiled request is the same for OpenSearch and Elasticsearch (OSE-14). Only the point-in-time calls that deep paging and
the export make differ (OSE-15), so the client takes a flavour. Set it on both options records when the cluster is Elasticsearch 8:

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

The default is `SearchEngineFlavour.OpenSearch`. Against Elasticsearch with the default, a window past 10,000 rows and every export
fail with HTTP 400, loudly.

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
