---
translates: search-adapters
title: MongoDB 与 OpenSearch 适配器
description: 使用可选适配器运行编译出的 MongoDB 和 OpenSearch 查询，包括深度分页。
source_fingerprint: 1e0376b06a8003383dd7effa6610d3efd908287637f20d9f94dff2c5a69ef485
drafter: claude
drafted_on: 2026-11-23
status: approved
---
# MongoDB 与 OpenSearch 适配器 {#mongodb-and-opensearch-adapters}

本页介绍在文档存储上运行 Craticula 查询的两个可选软件包：用于 MongoDB 的 `Craticula.MongoDB.Driver`，以及用于 OpenSearch 和 Elasticsearch 的 `Craticula.OpenSearch.Client`。本页面向使用其中某个存储、并希望 Craticula 不仅生成查询、还负责运行查询的开发者。

## 核心提供什么，适配器又增加什么 {#what-the-core-gives-you-and-what-the-adapters-add}

编译器只负责写出查询，到此为止。

- `Craticula.Mongo` 把请求转换为聚合管道。`MongoPipelineBuilder.Build` 返回一个 `MongoQuery`，其中包含集合名称和管道阶段。
- `Craticula.Search` 把请求转换为搜索请求体。`SearchQueryBuilder.Build` 返回一个 `SearchQuery`，其中包含索引名称和请求体，`ToArtifact()` 会把它以 JSON 形式给你。

两个编译器都不依赖客户端库，也都不打开连接。你可以自己运行它们的输出。

适配器则替你运行。请通过 NuGet 安装：`dotnet add package Craticula.MongoDB.Driver` 或 `dotnet add package Craticula.OpenSearch.Client`。参见 [C# 快速入门](quickstart-csharp.html)。

## MongoDB {#mongodb}

`Craticula.MongoDB.Driver` 使用 `Craticula.Mongo` 编译，并通过官方 MongoDB 驱动运行管道，驱动版本范围为 `[3.14.1, 4.0)`。

```csharp
MongoGridPage result = await MongoGridQuery.FetchPageAsync(
    database,
    new MongoQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    includeRowCount: true);
```

它提供的内容：

- `MongoGridQuery.FetchPageAsync` 返回一个 `MongoGridPage`，含有 `Columns`、`Rows` 和一个可选的 `RowCount`。
- `MongoGridQuery.CountAsync` 只运行计数。计数是一个单独的聚合，它会去掉排序和页窗口，因为计数不需要它们。
- `MongoExportStream.StreamAsync` 为导出以流的方式输出每一个匹配的文档。它逐批读取驱动的游标，无需沿着偏移量前进。参见 [CSV 导出](csv-export.html)。
- 时间限制（如果你设置了的话）。设置 `ResourceLimits.MaxQueryTimeMs` 后，编译出的聚合会带上 `maxTimeMS`，MongoDB 会取消运行时间过长的查询，适配器则抛出 `QueryTimeoutException`。计数同样受该限制约束，而导出不受约束。参见 [限制](limits.html)。
- `FetchPageAsync` 会拒绝未分页的页。要获取所有行的请求，应通过 `MongoExportStream` 处理，它绝不会持有完整结果。

它需要你提供的内容：

- 一个已打开的 `IMongoDatabase`。适配器绝不会打开或关闭它。
- 一个把每个字段映射到文档路径的 schema，例如 `"physical": { "mongo": { "path": "address.city" } }`，以及一个指明集合的 `source`。
- MongoDB 4.2 或更高版本。参见 [方言与提供程序](dialects-and-providers.html)。

## OpenSearch 与 Elasticsearch {#opensearch-and-elasticsearch}

`Craticula.OpenSearch.Client` 使用 `Craticula.Search` 编译，并通过 `OpenSearch.Client` 的低层客户端运行请求体，版本范围为 `[2.2.0, 3.0)`。它原样发送编译出的 JSON，不会再用类型化客户端第二次构建请求。

```csharp
OpenSearchGridPage result = await OpenSearchGridQuery.FetchPageAsync(
    client,
    new SearchQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    gridSessionId,
    cache);
```

其中 `client` 是一个 `IOpenSearchLowLevelClient`，`gridSessionId` 是你为该表格会话选定的字符串，`cache` 是一个 `ISearchCursorCache`。

它提供的内容：

- `OpenSearchGridQuery.FetchPageAsync` 返回一个 `OpenSearchGridPage`，含有 `Columns`、`Rows`、可能为 null 的 `RowCount`，以及一个 `LastRow` 标志。
- `OpenSearchExportStream.StreamAsync` 为导出以流的方式输出每一条匹配的命中。它始终写出 schema 的每一列，顺序为 `schema.FieldOrder` 的顺序，因为搜索编译器没有列投影。请向 `CsvWriter` 传入 `schema.FieldOrder` 中每个字段对应的一个 `ExportColumn`；较窄的列表会使它因单元格数量不匹配而失败。
- 时间限制（如果你设置了的话）。设置 `ResourceLimits.MaxQueryTimeMs` 后，每个搜索请求体都带有 `timeout`。超时的搜索仍会返回它已找到的命中，并带上 `timed_out: true`；适配器会把它转换为 `QueryTimeoutException`，绝不会把部分命中当作一页返回，无论是表格页还是导出块。导出自身的请求不带 `timeout`。`FetchPageAsync` 会拒绝未分页的页；请使用 `OpenSearchExportStream`。

它需要你提供的内容：

- 一个已打开的客户端。适配器绝不会构建或关闭它。
- 与你的 schema 相匹配的索引映射。编译出的查询会指名你的 schema 所声明的子字段，例如 `keyword` 字段。缺少某个子字段，可能导致过滤器在没有任何错误的情况下匹配不到任何行。参见 [索引与数据库指南](index-guidance.html)。
- 一个与表格会话存续时间一样长的游标缓存。见下文。

### 游标缓存 {#the-cursor-cache}

OpenSearch 会拒绝超过 10,000 行的普通分页。适配器会切换为时间点（point in time）加 `search_after`，并记住上一个块在哪里结束。这份记忆就是你传入的 `ISearchCursorCache`。

随库提供的是 `InMemorySearchCursorCache`。请在进程中只创建一次并共享它。每个请求都新建一个缓存，会使每个深层页都从第零行重新开始。`InMemorySearchCursorCache` 把条目保存在单个进程中。如果同一个表格会话的请求可能到达多台服务器，那么另一台服务器上的深层页没有游标，只能再次从第零行开始遍历。所有服务器共享的缓存可以避免这种情况，但目前没有提供。

同一个游标也服务于分组层级。分组层级使用复合聚合（composite aggregation），它无法从非零行开始。适配器会保存最后一个分组的键，并把它发回去，以请求下一个块。

### 选项 {#options}

`OpenSearchDeepPagingOptions` 用于更改分页：

| 设置 | 默认值 | 作用 |
|---|---|---|
| `MaxResultWindow` | 10,000 | 超过该行数后，适配器切换为游标。 |
| `WalkBatchSize` | 1,000 | 一次追赶步骤前进多少行。 |
| `PitKeepAlive` | 5 分钟 | 空闲游标保持有效的时间。 |
| `ExactRowCount` | `false` | 当你请求行数时，向引擎索取精确的计数。 |
| `Flavour` | `OpenSearch` | 引擎，`OpenSearch` 或 `Elasticsearch`。 |

没有 `ExactRowCount` 时，超过窗口的计数会被报告为未知，这样开销很低。有了它，引擎会在每次首次请求时统计所有匹配项。

### Elasticsearch {#elasticsearch}

两种引擎编译出的请求相同。只有打开和关闭时间点的调用不同。如果集群是 Elasticsearch，请在两个选项记录上都设置 flavour：

```csharp
var paging = new OpenSearchDeepPagingOptions { Flavour = SearchEngineFlavour.Elasticsearch };
var export = new OpenSearchExportOptions { Flavour = SearchEngineFlavour.Elasticsearch };
```

对 Elasticsearch 使用默认的 flavour 时，超过 10,000 行的窗口以及每一次导出都会以 HTTP 400 失败。

## 它们绝不会做的事 {#what-they-never-do}

- 它们绝不打开、关闭或配置连接或客户端。
- 它们绝不重试失败的请求，也绝不设置超时。
- 它们绝不会限制导出的最大行数。
- 它们绝不应用你的资源限制或 schema 的列检查。请先运行 `GridFilterPipeline.Process`。参见 [安全模型](safety-model.html)。
- 它们绝不导出分组结果。导出是一份扁平的行列表，导出流会拒绝带有分组的请求。

## 本页的依据 {#where-this-comes-from}

- [csharp/src/Craticula.MongoDB.Driver/README.md](../../csharp/src/Craticula.MongoDB.Driver/README.md)
- [csharp/src/Craticula.OpenSearch.Client/README.md](../../csharp/src/Craticula.OpenSearch.Client/README.md)
- [csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs](../../csharp/src/Craticula.MongoDB.Driver/MongoGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchDeepPagingOptions.cs)
- [csharp/src/Craticula.Mongo/README.md](../../csharp/src/Craticula.Mongo/README.md)
- [csharp/src/Craticula.Search/README.md](../../csharp/src/Craticula.Search/README.md)
- 相关页面：[Entity Framework Core 与 Dapper](relational-adapters.html)、[分页与排序](paging-and-sorting.html)、[分组与聚合](grouping-and-aggregation.html)
