---
translates: paging-and-sorting
title: 分页与排序
description: 行如何开窗和排序，以及分页为何是确定性的。
source_fingerprint: c01a09b912527d1a95923a5776c7b4abb3290f980e8c9111c4751565b710b445
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# 分页与排序 {#paging-and-sorting}

本页介绍 AG Grid 请求中的行范围和排序顺序如何变成查询中的分页和排序。本页面向想知道行为何以某种顺序返回、以及各后端如何对其分页的开发者。

## 从 startRow 和 endRow 到页面 {#from-startrow-and-endrow-to-a-page}

AG Grid 通过 `startRow` 和 `endRow` 请求一块行。`endRow` 不包含在内。页面大小为 `endRow - startRow`。

Craticula 将其转换为行数和偏移量。行数就是页面大小，偏移量是 `startRow`。请求第 50 到 100 行，意味着跳过 50 行后取 50 行。

适配器会拒绝没有意义的窗口：

- 负的 `startRow`；
- 小于 `startRow` 的 `endRow`；
- 等于 `startRow` 的 `endRow`，即空窗口。

页面也有最大大小。默认值为 1000 行。参见[限制](limits.html)。

## 没有窗口的请求 {#a-request-with-no-window}

有些请求既不发送 `startRow`，也不发送 `endRow`：例如自定义客户端，或手工构造的请求。自 1.2.0 版本起，此类请求会得到默认的 100 行页面，即 `[0, 100)`。其大小为 `AgGridParseOptions.DefaultPageSize`，页面大小限制会像对待其他窗口一样检查它。在 1.2.0 之前，没有窗口的请求意味着返回所有匹配的行。

请求所有行有两种方式，两者都是有意为之：

- **导出全部内容**（`exportScope` 设为 `"all"`）。它没有页面，适配器会分块流式传输。参见 [CSV 导出](csv-export.html)。
- **标志 `ignorePageLimit: true`**，仅当您的宿主开启了 `AgGridParseOptions.AllowUnboundedRows`（默认关闭）时才有效。没有该开关时，请求会被拒绝并给出解析错误 `unbounded-not-allowed`；它绝不会被悄悄截断。带有窗口的请求保留其窗口，该标志不起作用。

适配器通过流式方式读取请求所有行的请求。MongoDB、Dapper、EF Core 和 OpenSearch 适配器的分页方法 `FetchPageAsync` 会拒绝未分页的页面，因此任何调用都不会把整个结果加载到内存中。此类请求请使用导出流。相关规则见[默认页面大小](default-page-size.html)。

## 各后端的做法 {#what-each-backend-does}

| 后端 | 页面的写法 |
|---|---|
| PostgreSQL、MySQL、SQLite | `LIMIT n OFFSET m` |
| SQL Server、Oracle | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| MongoDB | 一个 `$skip` 阶段，接着一个 `$limit` 阶段 |
| OpenSearch 和 Elasticsearch | `from` 和 `size` |

对于 SQL，这两个数字是参数，不是文本的一部分。SQL Server 和 Oracle 先绑定偏移量，再绑定行数。PostgreSQL、MySQL 和 SQLite 先绑定行数。您无需关心这一点，因为参数列表的顺序与占位符出现的顺序一致。

导出全部内容完全没有页面。它请求所有匹配的行，且没有分页子句。参见 [CSV 导出](csv-export.html)。

## 排序顺序 {#sort-order}

网格在 `sortModel` 中发送一个排序键列表。Craticula 保持它们的顺序。每个键都有一个列和一个方向，即 `asc` 或 `desc`。

对 schema 中未列出的列进行排序会被拒绝，无论是 Strict 还是 Lenient 模式。拒绝来自编译器，它会抛出自己的编译异常。参见 [Strict 与 Lenient](strict-and-lenient.html)。

schema 为每一列提供了 `sortable` 标志。目前（就此版本而言）没有任何代码读取它。只要列在 schema 中，无论其标志如何，都可以被排序。请不要依赖该标志来阻止某列被排序。

## 空值排在哪里 {#where-nulls-go}

AG Grid 没有说明空值应排在哪里。由 Craticula 决定，并且对每个后端的决定都相同：

- 升序排序将空值放在最后；
- 降序排序将空值放在最前。

各数据库在这一点上的默认行为并不一致，所以 Craticula 绝不把它交给数据库。它会把位置写入每个排序键。

PostgreSQL、SQLite 和 Oracle 有 `NULLS FIRST` 和 `NULLS LAST`，Craticula 会使用它们。SQLite 需要 3.30.0 或更高版本才能使用。SQL Server 和 MySQL 没有这样的语法，因此 Craticula 会在前面加一个测试，把空值行归入单独的一组：SQL Server 上是 `CASE WHEN ... IS NULL`，MySQL 上是 `ISNULL(...)`。对于 MongoDB，每个排序键会得到一个辅助字段，排序之后会再将其移除。OpenSearch 得到的是 `"missing": "_last"` 或 `"_first"`。

## 文本排序不区分大小写 {#text-sorts-without-regard-to-case}

文本列默认比较时不区分大小写。排序遵循同样的规则，因此 `apple` 和 `Apple` 排在一起。列可以在 schema 中通过将 `text.caseSensitivity` 设为 `sensitive` 来要求精确区分大小写。

各引擎以各自的方式得到同样的结果：

- PostgreSQL 指定一个排序规则（collation）`craticula_ci`，需要您创建一次。
- SQL Server 和 SQLite 在查询中以内联方式指定排序规则。
- MySQL 使用列自身的排序规则。
- MongoDB 为整个查询设置一个排序规则。
- OpenSearch 在一个规范化的子字段上排序，该子字段由您在索引中映射。

每个数据库需要您配置什么，请见[索引与数据库指南](index-guidance.html)。

## 稳定键使分页保持有序 {#the-stable-key-keeps-paging-in-order}

只有顺序是全序时，分页才可靠。如果两行在每个排序键上都相同，数据库可能以任意顺序返回它们，于是一行可能出现在两页中，也可能一页都不出现。

为防止这种情况，schema 指定一个 `stableKey`，即取值唯一的列。当排序尚未以该键结尾时，Craticula 会在末尾追加它，升序，空值在后。

快速入门中的请求按 `amount` 降序排序。语句的结尾如下：

```sql
ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST
```

在追加任何内容之前，Craticula 还会整理排序：

- 被指定两次的列只保留其第一次出现；
- 如果稳定键是精确排序，则其后的所有键都会被丢弃，因为已经没有需要打破的并列。

不区分大小写的文本稳定键是个例外。仅大小写不同的两个键在比较时被视为相等，因此后面的键会保留，并追加一个精确的决胜键。

只有稳定键真正唯一，这才有效。大多数数据库允许唯一列包含多个空值，这会破坏保证。请将该键声明为 `NOT NULL`。参见[索引与数据库指南](index-guidance.html)。

## 深度分页 {#deep-paging}

SQL 和 MongoDB 的网格页面使用偏移量。数据库必须扫过每一个被跳过的行，所以大表中靠后的页面比靠前的页面更慢。请为您的过滤条件建立索引并进行测量。

OpenSearch 拒绝超过 10,000 行的普通 `from` 和 `size`。OpenSearch 适配器会为您处理这一点。超过该点之后，它会切换为时间点（point in time）和 `search_after`，并在请求之间保留一个游标。由此产生三点：

- 您必须为它提供一个与网格会话同寿命的游标缓存。随库提供的是 `InMemorySearchCursorCache`。为每个请求新建一个缓存会使游标失去作用。
- 第一个跨过阈值的请求要从第零行向前遍历。其后的块则很快。
- 超过 10,000 的总行数会被报告为未知，除非您要求精确计数，而这在每个首次请求上都需要一次完整计数，代价较高。

参见 [MongoDB 和 OpenSearch 适配器](search-adapters.html)。

## 内容来源 {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/sort-paging](../../spec/fixtures/sort-paging/README.md)
- [csharp/src/Craticula.Core/Schema/SemanticsResolver.cs](../../csharp/src/Craticula.Core/Schema/SemanticsResolver.cs)
- [csharp/src/Craticula.Core/Ir/PageSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/PageSpecValidator.cs)
- [csharp/src/Craticula.Sql](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs](../../csharp/src/Craticula.OpenSearch.Client/OpenSearchGridQuery.cs)
- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- 相关页面：[请求如何变成查询](request-to-query.html)、[分组与聚合](grouping-and-aggregation.html)、[方言与提供程序](dialects-and-providers.html)
