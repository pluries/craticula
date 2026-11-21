---
translates: dialects-and-providers
title: 方言与提供程序
description: 各数据库引擎在引号、分页、null 排序和不区分大小写匹配方面有何不同。
source_fingerprint: e3cadc85fee286141cd8091c6103e2780064d51e19a1428afa783d8f20b83081
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# 方言与提供程序 {#dialects-and-providers}

本页列出 Craticula 可以为哪些数据库编写查询，这些查询有何不同，以及测试过哪些版本。本页面向正在选择数据库或方言的开发者，或想知道同一个请求为什么在每种数据库上产生不同文本的开发者。

## 什么是方言 {#what-a-dialect-is}

同一个请求在每个后端上含义相同。Craticula 以规范形式一次性确定它的含义，然后由每个数据库对应的一个写出器，用该数据库自己的语言把它表达出来。

对于 SQL，这个写出器就是方言。方言类有一个共享的 `Instance`，例如 `PostgresDialect.Instance`。你把它传给 `SqlQueryBuilder.Build`。一共有五种：

| 数据库 | 方言类 |
|---|---|
| PostgreSQL | `PostgresDialect` |
| SQL Server | `MssqlDialect` |
| MySQL（MariaDB 使用同一个方言，但从未测试过） | `MySqlDialect` |
| SQLite | `SqliteDialect` |
| Oracle | `OracleDialect` |

MongoDB 和 OpenSearch 有各自的编译器，即 `MongoPipelineBuilder` 和 `SearchQueryBuilder`。它们不接受方言。参见 [MongoDB 与 OpenSearch 适配器](search-adapters.html)。

## SQL 有何不同 {#how-the-sql-differs}

| 数据库 | 占位符 | 引号 | 分页 |
|---|---|---|---|
| PostgreSQL | `$1`, `$2` | `"name"` | `LIMIT` 和 `OFFSET` |
| SQL Server | `@p1`, `@p2` | `[name]` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |
| MySQL | `?` | `` `name` `` | `LIMIT` 和 `OFFSET` |
| SQLite | `?` | `"name"` | `LIMIT` 和 `OFFSET` |
| Oracle | `:p1`, `:p2` | `"name"` | `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` |

在每种情况下，值都是参数，并按占位符出现的顺序列出。每个表名和列名都带引号，名称内部的引号字符会被加倍。参见 [安全模型](safety-model.html)。

PostgreSQL 把“in”列表作为一个数组参数传递。其他数据库则为每个值写一个占位符。

## null 的排序 {#null-ordering}

Craticula 在每个查询中都明确说明 null 排在哪里，因此排序不依赖数据库的默认值。具体说法取决于数据库：

- PostgreSQL、SQLite 和 Oracle 有 `NULLS FIRST` 和 `NULLS LAST`。SQLite 需要 3.30.0 或更高版本。
- SQL Server 没有这样的语法。查询先按 `CASE WHEN column IS NULL THEN 1 ELSE 0 END` 排序，再按该列排序。
- MySQL 同样没有。查询先按 `ISNULL(column)` 排序，再按该列排序。
- MongoDB 按一个标记 null 的辅助字段排序，查询随后会把它移除。
- OpenSearch 使用 `"missing": "_first"` 或 `"_last"`。

参见 [分页与排序](paging-and-sorting.html)。

## 不区分大小写的比较 {#case-insensitive-comparison}

除非 schema 另有说明，文本字段比较时不区分大小写。各数据库达到这一点的方式不同：

| 数据库 | 如何忽略大小写 |
|---|---|
| PostgreSQL | 在比较和排序上使用 `COLLATE craticula_ci`，你需要一次性创建它。`contains`、`startsWith` 和 `endsWith` 使用 `ILIKE`。 |
| SQL Server | 查询中使用 `COLLATE Latin1_General_CI_AS`。区分大小写的字段使用 `Latin1_General_CS_AS`。 |
| MySQL | 查询中什么都没有。由列自身的排序规则决定。区分大小写的字段需要 `_bin` 或 `_as_cs` 列。 |
| SQLite | `COLLATE NOCASE`，它只折叠 ASCII 字母。 |
| Oracle | `COLLATE BINARY_CI`。区分大小写的字段使用 `COLLATE BINARY`。 |
| MongoDB | 整个查询使用一个排序规则（collation），区域设置为 `en`，强度为 2。 |
| OpenSearch 与 Elasticsearch | term 和 wildcard 查询上的 `case_insensitive` 选项，以及用于排序和范围的规范化子字段。 |

有两种情况是无声的：MySQL 上区分大小写的字段，以及 SQL Server、MySQL 和 Oracle 上的分组列。如果列的排序规则不是 Craticula 所假定的那一种，语句仍会运行，但返回错误的行。索引与数据库指南列出了每种情况应设置什么：[索引与数据库指南](index-guidance.html)。

## 版本 {#versions}

这些是编译出的查询所需的最低版本，取自规范和厂商文档，而不是取自测试运行。只有“测试所用版本”这一列是实际运行过的。Elasticsearch 适配器的文档适用于 8.x。

| 数据库 | 最低版本 | 测试所针对的版本 |
|---|---|---|
| PostgreSQL | 12，带 ICU | 16 |
| SQL Server | 未说明 | 2022 |
| MySQL | 未说明 | 8.4 |
| SQLite | 3.30.0 | 未记录 |
| Oracle | 12.2 | Database Free 23ai |
| MongoDB | 4.2 | 7.0 |
| OpenSearch | 1.0 | 2.19 |
| Elasticsearch | 7.10 | 8.17 |

“未说明”表示代码和规范没有设定下限，并不表示每个旧版本都经过尝试。MariaDB 使用 MySQL 方言，但没有任何测试在 MariaDB 上运行。

这些测试在容器中针对真实数据库运行编译出的查询。该运行需要 Docker，不属于快速测试运行，因此请到仓库中查看最新状态。

## Oracle 的状态 {#oracles-status}

Oracle 是作为社区测试的方言受到支持的，而不是 v1 的核心方言。它的评分方式与其他方言相同：每条语句都与存储的预期文本比较。区别在于覆盖范围。它所检查的示例集比其他四种方言小，一共 45 个。这 45 个也会针对真实的 Oracle Database Free 23ai 服务器运行。

Oracle 12.2 到 21c 尚未运行过。12.2 这一最低版本来自 Oracle 的文档，而不是来自实测。

三个 Oracle 事实决定了输出：

- **空文本即 null。** 比较中的文本值 `""` 会悄无声息地匹配到错误的行，因此 Oracle 方言会拒绝它。请改用“空白”和“非空白”运算符。
- **名称必须带引号。** 请用与 schema 完全一致的带引号名称创建表及其列。
- **会话设置。** 日期、时间戳和数字的格式来自会话，因此请按 [索引与数据库指南](index-guidance.html) 的说明进行设置。

## 提供程序 {#providers}

这里的提供程序，指实际与数据库通信的库。Craticula 不会替你选择。

- 对于 SQL，`Craticula.Dapper` 在已打开的 `IDbConnection` 上运行任何方言，不论该连接由哪个 ADO.NET 提供程序创建。
- `Craticula.EntityFrameworkCore` 使用你的 `DbContext` 的提供程序。它需要一个描述你的引擎的 `EfCoreProviderSemantics`，目前只提供 SQLite 的那一个。参见 [Entity Framework Core 与 Dapper](relational-adapters.html)。
- MongoDB 通过官方的 MongoDB .NET 驱动运行，OpenSearch 则通过 `OpenSearch.Client` 的低层客户端运行。

仓库在 `examples/demo` 中有一个由你自己运行的演示应用。它从其中几种数据库读取同样的合成订单，并比较各自的答案。

## 本页的依据 {#where-this-comes-from}

- [csharp/src/Craticula.Sql/README.md](../../csharp/src/Craticula.Sql/README.md)
- [csharp/src/Craticula.Sql/OracleDialect.cs](../../csharp/src/Craticula.Sql/OracleDialect.cs)
- [csharp/src/Craticula.Sql/MssqlDialect.cs](../../csharp/src/Craticula.Sql/MssqlDialect.cs)
- [spec/fixtures/dialect-parity](../../spec/fixtures/dialect-parity/README.md)
- [spec/fixtures/README.md](../../spec/fixtures/README.md)
- [spec/semantics.md](../../spec/semantics.md)
- [csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs](../../csharp/tests/Craticula.Integration.Tests/Sql/SqlEngine.cs)
- [examples/demo/README.md](../../examples/demo/README.md)
- 相关页面：[索引与数据库指南](index-guidance.html)、[分页与排序](paging-and-sorting.html)、[GridSchema](the-gridschema.html)
