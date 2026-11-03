# MongoDB and OpenSearch adapters

This page covers the two optional packages that run Craticula queries on a document store: `Craticula.MongoDB.Driver` for MongoDB and `Craticula.OpenSearch.Client` for OpenSearch and Elasticsearch. It is for a developer who uses one of those stores and wants Craticula to run the query as well as write it.

## What the core gives you, and what the adapters add

The compilers write the query and stop there.

- `Craticula.Mongo` turns a request into an aggregation pipeline. `MongoPipelineBuilder.Build` returns a `MongoQuery` with the collection name and the pipeline stages.
- `Craticula.Search` turns a request into a search body. `SearchQueryBuilder.Build` returns a `SearchQuery` with the index name and the body, which `ToArtifact()` gives you as JSON.

Neither compiler depends on a client library, and neither opens a connection. You can run their output yourself.

The adapters run it for you. Nothing is published yet. Build the packages from the repository and reference the projects. See [the C# quickstart](quickstart-csharp.html).

## MongoDB

`Craticula.MongoDB.Driver` compiles with `Craticula.Mongo` and runs the pipeline through the official MongoDB driver, in the range `[3.13.0, 4.0)`.

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

What it gives you:

- `MongoGridQuery.FetchPageAsync` returns a `MongoGridPage` with `Columns`, `Rows` and an optional `RowCount`.
- `MongoGridQuery.CountAsync` runs only the count. The count is a separate aggregation that drops the sort and the page window, because a count needs neither.
- `MongoExportStream.StreamAsync` streams every matching document for an export. It reads the driver's cursor batch by batch, with no offset to walk. See [CSV export](csv-export.html).

What it needs from you:

- An open `IMongoDatabase`. The adapter never opens or closes it.
- A schema that maps each field to a document path, such as `"physical": { "mongo": { "path": "address.city" } }`, and a `source` that names the collection.
- MongoDB 4.2 or later. See [Dialects and providers](dialects-and-providers.html).

## OpenSearch and Elasticsearch

`Craticula.OpenSearch.Client` compiles with `Craticula.Search` and runs the body through the low-level client of `OpenSearch.Client`, in the range `[2.2.0, 3.0)`. It sends the compiled JSON as it is. It does not build the request a second time with the typed client.

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

Here `client` is an `IOpenSearchLowLevelClient`, `gridSessionId` is a string you choose for the grid session, and `cache` is an `ISearchCursorCache`.

What it gives you:

- `OpenSearchGridQuery.FetchPageAsync` returns an `OpenSearchGridPage` with `Columns`, `Rows`, a `RowCount` that may be null, and a `LastRow` flag.
- `OpenSearchExportStream.StreamAsync` streams every matching hit for an export. It always writes every schema column, in the order of `schema.FieldOrder`, because the search compiler has no column projection. Pass `CsvWriter` one `ExportColumn` per field in `schema.FieldOrder`; a narrower list makes it fail on a cell-count mismatch.

What it needs from you:

- An open client. The adapter never builds or closes it.
- An index mapping that matches your schema. The compiled queries name the sub-fields your schema declares, such as a `keyword` field. A missing one can make a filter match no rows without an error. See [Index and database guidance](index-guidance.html).
- One cursor cache that lives as long as the grid session. See below.

### The cursor cache

OpenSearch refuses plain paging past 10,000 rows. The adapter switches to a point in time and `search_after`, and it remembers where the last block ended. That memory is the `ISearchCursorCache` you pass in.

`InMemorySearchCursorCache` is the one that ships. Create it once for the process and share it. A new cache for each request makes every deep page start again from row zero. `InMemorySearchCursorCache` keeps its entries in one process. If the requests of one grid session can reach several servers, a deep page on another server has no cursor and walks from row zero again. A cache that all servers share would avoid that, but none ships.

The same cursor serves grouped levels. A grouped level uses a composite aggregation, which cannot start at a non-zero row. The adapter keeps the key of the last group and sends it back to ask for the next block.

### Options

`OpenSearchDeepPagingOptions` changes the paging:

| Setting | Default | What it does |
|---|---|---|
| `MaxResultWindow` | 10,000 | The row count after which the adapter switches to the cursor. |
| `WalkBatchSize` | 1,000 | How many rows one catch-up step advances. |
| `PitKeepAlive` | 5 minutes | How long an idle cursor stays valid. |
| `ExactRowCount` | `false` | Ask the engine for the exact count when you request a row count. |
| `Flavour` | `OpenSearch` | The engine, `OpenSearch` or `Elasticsearch`. |

Without `ExactRowCount`, a count above the window is reported as unknown, which is cheap. With it, the engine counts every match on each first request.

### Elasticsearch

The compiled request is the same for both engines. Only the calls that open and close a point in time differ. Set the flavour on both option records when the cluster is Elasticsearch:

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

With the default flavour against Elasticsearch, a window past 10,000 rows and every export fail with HTTP 400.

## What they never do

- They never open, close or configure a connection or a client.
- They never retry a failed request or set a timeout.
- They never enforce a maximum number of exported rows.
- They never apply your resource limits or the column checks of your schema. Run `GridFilterPipeline.Process` first. See [The safety model](safety-model.html).
- They never export a grouped result. An export is a flat list of rows, and the export streams refuse a request that carries a group.

## Where this comes from

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- Related pages: [Entity Framework Core and Dapper](relational-adapters.html), [Paging and sorting](paging-and-sorting.html), [Grouping and aggregation](grouping-and-aggregation.html)
