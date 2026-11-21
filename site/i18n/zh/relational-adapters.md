---
translates: relational-adapters
title: Entity Framework Core 与 Dapper
description: 两个关系型适配器能为你做什么、需要什么，以及绝不会做什么。
source_fingerprint: c7c6226b52fe85563de296ccf30f4b6133346e53ef471b90257c33696e64481f
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Entity Framework Core 与 Dapper {#entity-framework-core-and-dapper}

本页介绍在关系型数据库上运行 Craticula 查询的两个可选软件包：`Craticula.Dapper` 和 `Craticula.EntityFrameworkCore`。本页面向拥有 SQL 数据库、并希望 Craticula 不仅生成查询、还负责运行查询的开发者。

## 为什么需要适配器 {#why-adapters-exist}

核心软件包只负责编译。它们绝不打开连接，也绝不运行任何东西。适配器针对某一个数据访问库弥补这一空缺：它编译请求、运行请求，并把行交给你。

适配器是可选的。核心软件包绝不依赖它们。你可以不使用适配器，用自己喜欢的任何库来运行编译出的语句。

请通过 NuGet 安装：`dotnet add package Craticula.Dapper` 或 `dotnet add package Craticula.EntityFrameworkCore`。参见 [C# 快速入门](quickstart-csharp.html)。

## Dapper {#dapper}

`Craticula.Dapper` 使用 `Craticula.Sql` 编译，并在你传入的连接上运行语句。如果你想看到并掌控 SQL，请使用它。

```csharp
DapperGridPage result = await DapperGridQuery.FetchPageAsync(
    openConnection,
    new SqlQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page },
    PostgresDialect.Instance,
    includeRowCount: true);
```

它提供的内容：

- `DapperGridQuery.FetchPageAsync` 返回一页。`DapperGridPage` 含有 `Columns`、`Rows` 和一个可选的 `RowCount`。
- `DapperGridQuery.CountAsync` 只运行计数。
- `DapperExportStream.StreamAsync` 为导出以流的方式输出每一条匹配的行。参见 [CSV 导出](csv-export.html)。
- `FetchPageAsync` 会拒绝未分页的页（`NonePage`），因此一次调用绝不会把所有行都加载到内存中。要获取所有行的请求，应通过 `DapperExportStream` 处理。

它需要你提供的内容：

- 一个已打开的 `IDbConnection`。适配器绝不会打开或关闭它。
- 与你的数据库相匹配的方言。参见 [方言与提供程序](dialects-and-providers.html)。
- Dapper 本身，版本范围为 `[2.1.89, 3.0)`。

分组请求通过同一个方法工作。SQL 编译器已经写好了分组语句，适配器只是运行它。

## Entity Framework Core {#entity-framework-core}

`Craticula.EntityFrameworkCore` 不编写 SQL 文本。它构建 `IQueryable<T>` 表达式树，再由 EF Core 提供程序把它们转换为 SQL。如果你已经有一个 `DbContext`，并希望应用它的全局查询过滤器（例如租户过滤器），请使用它。

```csharp
var request = new EfCoreQueryRequest { Schema = schema, Filter = filter, Sort = sort, Page = page };

EfCoreGridPage result = await EfCoreGridQuery.FetchPageAsync(
    source, request, EfCoreProviderSemantics.Sqlite, includeRowCount: true);
```

它提供的内容：

- `EfCoreGridQuery.FetchPageAsync` 返回一页，放在与 Dapper 相同形态的 `EfCoreGridPage` 中。
- `EfCoreGridQuery.CountAsync` 只运行计数。
- `EfCoreExportStream.StreamAsync` 为导出以流的方式输出行。
- `FetchPageAsync` 与 Dapper 适配器一样，会拒绝未分页的页。要获取所有行的请求，应通过 `EfCoreExportStream` 处理。

它需要你提供的内容：

- **一个源查询。** 传入 `DbSet<T>`；如果你没有实体类，则传入 `GridSchemaPropertyBag.Query(context, schema)`。对于第二种形式，请在 `OnModelCreating` 中调用 `GridSchemaPropertyBag.Configure`。
- **匹配的属性名。** 每个字段都被读取为一个 EF 属性，其名称取自它的 `physical.sql.column`，没有该项时则取自列 id。用 `HasColumnName` 重命名列的类必须与之对齐。
- **一个 `EfCoreProviderSemantics` 值。** 它说明关于你的数据库的五项事实，这些事实 EF 无法告诉 Craticula，例如不区分大小写的排序规则（collation）的名称。目前只提供 `EfCoreProviderSemantics.Sqlite`，因为只有它经过了实测。对于其他引擎，你需要在 `DbContext` 旁边自行声明一次。

schema 的字段必须使用普通的 `physical.sql.column`。带有 `qualifiedColumn` 或 `expression` 的字段会被拒绝，因为两者在表达式树中都没有对应的形式。

如果同一个 `DbContext` 类型可以由多个 schema 构建，请注册 `GridSchemaModelCacheKeyFactory`，并在该上下文上实现 `IGridSchemaModel`。否则，EF 会把第一个 schema 的模型复用于下一个 schema，并以不提及缓存的错误失败。

### 两个无声的陷阱 {#two-silent-traps}

这两个陷阱都会在没有任何错误的情况下返回错误的行。适配器看不到你的模型或排序规则，因此无法防范它们。

- **SQLite 的日期和时间值。** 请把 `datetime` 存为 `yyyy-MM-ddTHH:mm:ss.fffZ` 形式的文本，并在你的 `DbContext` 中把每个 `DateTime` 与该文本相互映射。EF 自己的映射使用另一种形式，而 SQLite 是逐字符比较文本的。
- **`PatternMatchFoldsCase`。** 它说明引擎的 `LIKE` 是否忽略大小写。对 SQLite 使用 `true`。对 SQL Server 和 MySQL 使用 `false`，除非每个可搜索的列都有忽略大小写的排序规则。否则，二进制排序规则的列只会匹配完全相同的大小写。

日期和时间单元格离开页或导出时，无论提供程序返回什么，都是 UTC 值。

## 两个适配器的共同点 {#what-both-adapters-share}

- **行数统计需要主动开启。** 计数是第二次往返，因此除非你传入 `includeRowCount`，否则它是关闭的。表格每次过滤条件改变时需要一次计数，而不是每个块都需要。
- **导出绝不使用偏移量。** 它们按 5,000 行一块读取，方式是沿着排序键向前推进，因此靠后的块与靠前的块代价相同。`DapperExportOptions` 和 `EfCoreExportOptions` 有一个 `ChunkSize` 可以更改它。导出需要一个真正唯一的稳定键。重复值会被检测到，并引发异常。
- **Dapper 会拒绝某些导出。** `DapperExportStream` 会拒绝稳定键是文本列的 schema。它也会拒绝这样的导出：被导出的行中，某个文本排序键含有空字符串（除 Oracle 外的所有方言）。两种情况下，都应使用数值或日期类型的稳定键，或者用 `DapperGridQuery.FetchPageAsync` 逐页获取数据。`EfCoreExportStream` 没有这种检查。
- **按页导出会被拒绝。** 导出流接受的是完整结果。有界的页应通过分页方法处理。
- **中立的结果。** 每一页都有一个 `ToGridPageResult()` 扩展方法。OpenSearch 的那个还接受你所使用的 `SearchQueryRequest`。`Craticula.AgGrid` 中的 `LoadSuccessParamsMapper.Map` 会把它转换为 AG Grid 所期望的形态。

## 它们绝不会做的事 {#what-they-never-do}

- 它们绝不打开、关闭或池化连接，也绝不启动事务。
- 它们绝不重试失败的查询，也绝不设置超时。连接和命令的设置由你负责。
- 它们绝不会限制导出的最大行数。
- 它们绝不应用你的资源限制或 schema 的列检查。请先运行 `GridFilterPipeline.Process`，就像快速入门那样。参见 [安全模型](safety-model.html)。

## 如何选择 {#which-one-to-pick}

| 你拥有的条件 | 使用 |
|---|---|
| 一个普通的 `IDbConnection`，并想看到 SQL | Dapper |
| 五种 SQL 方言中的任意一种，无需额外代码 | Dapper |
| 一个带有全局查询过滤器、且你想保留这些过滤器的 `DbContext` | Entity Framework Core |

演示程序在 PostgreSQL 上同时运行两者，因此你可以在同一份数据上比较它们。

## 本页的依据 {#where-this-comes-from}

- [csharp/src/Craticula.Dapper/README.md](../../csharp/src/Craticula.Dapper/README.md)
- [csharp/src/Craticula.EntityFrameworkCore/README.md](../../csharp/src/Craticula.EntityFrameworkCore/README.md)
- [csharp/src/Craticula.Dapper/DapperGridQuery.cs](../../csharp/src/Craticula.Dapper/DapperGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreGridQuery.cs)
- [csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs](../../csharp/src/Craticula.EntityFrameworkCore/EfCoreProviderSemantics.cs)
- [csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs](../../csharp/src/Craticula.EntityFrameworkCore/GridSchemaPropertyBag.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- 相关页面：[CSV 导出](csv-export.html)、[MongoDB 与 OpenSearch 适配器](search-adapters.html)、[分页与排序](paging-and-sorting.html)
