---
translates: index-guidance
title: 索引指南
description: 哪些数据库索引和设置能让编译出的查询既快又准确。
source_fingerprint: 3d3bf891b84587e5732e82a2bb52c06b0c2ee549efb1865d1fc2d889fe36ebf5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# 索引与数据库指南 {#index-and-database-guidance}

Craticula 只编译查询；它绝不创建表、索引或排序规则（collation）。本页针对每种数据库，列出**你自己**必须准备哪些东西，编译出的查询才能返回正确的行并且运行得快。其背后的规则见[语义](semantics.html)；固定各数据库语句的夹具位于 [`spec/fixtures/dialect-parity`](../../spec/fixtures/dialect-parity/README.md)。

下面会出现两类义务，二者的区别很重要：

- **显式失败（loud）：** 数据库拒绝该语句（缺少排序规则、服务器版本过旧）。你会立刻发现。
- **静默出错（silent）：** 语句照常运行，却返回错误的行（某一列在不该忽略大小写时忽略了大小写）。没有任何提示，所以这类情况要读两遍。

## 一览 {#at-a-glance}

| 数据库 | 你必须提供 | 否则 |
|---|---|---|
| PostgreSQL | 12 或更高版本并带 ICU；`craticula_ci` 排序规则；日期时间使用 `timestamptz` | 前两项会显式失败（每一次不区分大小写的比较都失败），`timestamp` 则静默出错 |
| SQL Server | 分组列使用二进制或区分大小写的排序规则；用 `datetime2` 存放 UTC | 静默出错：`EMEA` 和 `emea` 落入同一个分组 |
| MySQL / MariaDB | 区分大小写的列和分组列使用 `_bin` 或 `_as_cs` 排序规则；用 `DATETIME` 存放 UTC | 静默出错：该声明被忽略 |
| SQLite | 3.30.0 或更高版本；日期时间存为 `yyyy-MM-ddTHH:mm:ss.fffZ` | 版本问题会显式失败，日期时间文本问题则静默出错 |
| Oracle | 12.2 或更高版本；带引号的标识符；分组列使用二进制排序规则（默认的会话设置） | 前两项显式失败，最后一项静默出错 |
| MongoDB | 服务器 4.2 或更高版本 | 显式失败：管道被拒绝 |
| OpenSearch / Elasticsearch | `keyword` 子字段；用于不区分大小写排序的 normalizer；用于十进制数的精确数值类型 | 过滤中缺少 `keyword` 子字段会静默出错（没有行匹配），排序时则显式失败；舍入问题静默出错 |

每种引擎还要求 schema 的**稳定键唯一，且至多有一个 `NULL`**（[Deterministic paging](semantics.html#sem-6)）。大多数引擎允许唯一约束包含多个 `NULL`，这会破坏分页保证；请把该键声明为 `NOT NULL`。在 MySQL 和 SQL Server 上，如果文本类型的稳定键不区分大小写，还需要对它使用二进制或区分大小写的排序规则，否则仅大小写不同的两个键会并列。

## 适用于所有数据库的索引 {#indexes-for-every-database}

- **过滤。** 文本字段默认不区分大小写比较（[Case sensitivity](semantics.html#sem-1)）。这条规则的设计使得普通列索引仍可用于等值比较：编译器在比较上指明排序规则，而不是用 `lower()` 包裹该列。请让索引与该排序规则一致（见下文）。子串匹配（`contains`、`endsWith`）以通配符开头，任何普通 B 树索引都无法支持；请参阅各引擎的说明。
- **排序。** 每个有序查询都以 schema 的稳定键结尾，升序且空值在后（[Deterministic paging](semantics.html#sem-6)），空值的位置由 Craticula 自己写明（[Null ordering](semantics.html#sem-3)）。只有与这个确切顺序一致的索引才能支持该排序。在 PostgreSQL、SQLite 和 Oracle 上，快速入门中的排序是 `amount DESC NULLS FIRST, id ASC NULLS LAST`，所以匹配的索引是 `(amount DESC NULLS FIRST, id ASC NULLS LAST)`；普通的 `(amount, id)` 索引与降序排序不匹配。在 SQL Server 和 MySQL 上，语句先按空值测试排序（`CASE WHEN ... IS NULL`、`ISNULL(...)`），任何列索引都无法支持它；在 MongoDB 上，排序作用于计算出的辅助字段。因此在这些引擎上，请为你的**过滤**建立索引，并预期排序发生在过滤之后。请在你自己的数据上检查执行计划（`EXPLAIN`）；Craticula 无从知道你的表有多大。
- **分页。** `OFFSET` 通常是页越深越慢。CSV 导出按键的顺序遍历结果，不使用 `OFFSET`。

## PostgreSQL {#postgresql}

需要 PostgreSQL 12 或更高版本，且编译时带有 ICU（非确定性排序规则）。一次性设置，在存放你的表的数据库中执行：

```sql
CREATE COLLATION craticula_ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
```

没有它，每一个不区分大小写的 `=`、`IN`、范围比较和 `ORDER BY` 都会因排序规则未知而失败（[Case sensitivity](semantics.html#sem-1)）。

- **等值比较和排序**：对不区分大小写的文本字段，语句指明 `craticula_ci`。用该排序规则创建的索引（`CREATE INDEX ... ON orders (customer COLLATE craticula_ci)`）才是匹配的那一个；请用 `EXPLAIN` 确认。
- **`contains`、`startsWith`、`endsWith`** 编译为 `ILIKE`。请用三元组索引支持它们：`CREATE EXTENSION pg_trgm;`，然后 `CREATE INDEX ... USING gin (customer gin_trgm_ops);`。
- **日期：** 把 `datetime` 列声明为 `timestamptz`。使用普通 `timestamp` 时，服务器会按会话时区比较，行会在没有任何错误的情况下发生偏移（[Dates and time zones](semantics.html#sem-4)）。
- 分组列不需要排序规则：PostgreSQL 的默认排序规则是确定性的，所以 `EMEA` 和 `emea` 是两个分组，正如[Grouping and drill-down](semantics.html#grp-2) 所要求的。

## SQL Server {#sql-server}

过滤不需要设置排序规则：语句内联携带 `COLLATE Latin1_General_CI_AS`（对你声明为区分大小写的字段则是 `Latin1_General_CS_AS`），因此两个方向都不依赖数据库自身的排序规则。

- **分组列，静默义务。** `GROUP BY` 和下钻必须是精确的（[Grouping and drill-down](semantics.html#grp-2)），而语句在那里不指明任何排序规则。SQL Server 常见的默认值（`SQL_Latin1_General_CP1_CI_AS`）会忽略大小写，所以用它声明的分组列会把 `EMEA` 和 `emea` 放进同一个分组。请为每个可分组的列（以及文本类型的稳定键）声明二进制或区分大小写的排序规则。列定义例如：

  ```sql
  country nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL
  ```

  对该列的过滤仍然不区分大小写地比较，因为过滤自己内联指明了排序规则。代价是速度：指明的排序规则与列的排序规则不同的比较，通常无法在该列上做索引查找（seek），所以请对一个同时用于分组的列，测量其不区分大小写的过滤。
- **日期。** `datetime2` 没有时区。请存放 UTC 读数；编译器直接用 UTC 时刻与之比较，结果也以 UTC 返回（[Dates and time zones](semantics.html#sem-4)）。
- **Entity Framework Core：** 除非每个可搜索列的排序规则都忽略大小写，否则请在提供程序语义上设置 `PatternMatchFoldsCase = false`；设为 `true` 会发送裸的 `LIKE`，而在二进制排序规则的列上，它只匹配完全相同的大小写。参见[适配器的 README](../../csharp/src/Craticula.EntityFrameworkCore/README.md)。

## MySQL 与 MariaDB {#mysql-and-mariadb}

在这两者中，大小写敏感性属于**列的**排序规则，语句无法以可移植的方式覆盖它。

- **不区分大小写的字段**（默认）适用于任何 `_ci` 列，例如 `utf8mb4_0900_ai_ci`，并且列上的普通索引可以支持对它们的等值比较（子串匹配以通配符开头，不在此列）。
- **区分大小写的字段，静默义务。** 声明为 `caseSensitivity: "sensitive"` 的字段需要 `_bin` 或 `_as_cs` 列排序规则（`utf8mb4_bin`、`utf8mb4_0900_as_cs`）。在 `_ci` 列上，该声明不起作用，比较仍然不区分大小写；编译出的语句不会告诉你这一点。
- **分组列** 需要同样的二进制或 `_as_cs` 排序规则才能得到精确的分组（[Grouping and drill-down](semantics.html#grp-2)）：

  ```sql
  country varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
  ```

  一列只有一个排序规则，所以把可分组的列设为二进制，也会让同一列上不区分大小写的过滤和前缀匹配悄悄变成区分大小写（GRP-2 所接受的差异 #4）。如果同一字段两者都需要，请决定哪个更重要；编译器无法从一列同时提供两者。
- **Entity Framework Core：** 与 SQL Server 相同，除非每个可搜索列的排序规则都忽略大小写，否则请设置 `PatternMatchFoldsCase = false`。
- **日期。** `DATETIME` 没有时区：请存放 UTC。若使用 MySqlConnector，请保持 `DateTimeKind` 为默认值或设为 UTC；`Local` 只是给值贴上标签，会让每个时刻都偏移服务器的时差（[Dates and time zones](semantics.html#sem-4)）。

## SQLite {#sqlite}

- **3.30.0 或更高版本**，用于 `NULLS FIRST` / `NULLS LAST`。较旧的库会拒绝该语句。
- **不区分大小写**的字段使用 `COLLATE NOCASE`，它只忽略 ASCII 字母的大小写（`É` 和 `é` 仍然不同）。声明为 `(customer COLLATE NOCASE)` 的索引可以支持它们。
- **日期时间，静默义务。** SQLite 没有时间戳类型，并且逐字符比较文本。请把每个 `datetime` 严格存为 `yyyy-MM-ddTHH:mm:ss.fffZ`，使用 UTC，并带三位小数（[Dates and time zones](semantics.html#sem-4)）。其他宽度（`...:00Z`、`yyyy-MM-dd HH:mm:ss`）会在没有任何错误的情况下返回错误的行。
- **Entity Framework Core** 以它自己的 `yyyy-MM-dd HH:mm:ss` 形式绑定 `DateTime`，所以请在你的 `DbContext` 中，把每个日期时间与存储的文本互相映射。没有这个映射，`eq` 什么也找不到，范围边界会把整个日期算作更晚，按日期时间排序的导出也可能重复行。详情见[适配器的 README](../../csharp/src/Craticula.EntityFrameworkCore/README.md)。

## Oracle {#oracle}

- **服务器 12.2 或更高版本。** 语句使用 `COLLATE BINARY_CI` 和 `COLLATE BINARY`；较旧的服务器会拒绝它们。Oracle 的文档将 `COMPATIBLE >= 12.2` 和 `MAX_STRING_SIZE = EXTENDED` 列为数据绑定排序规则的前提条件。
- **验证过什么。** 编译出的语句在容器中的 Oracle Database Free 23.26.3 上运行过（`gvenzl/oracle-free:23.26.3-slim-faststart`、`COMPATIBLE = 23.6.0`、`MAX_STRING_SIZE = STANDARD`）：全部 45 个 Oracle 夹具都返回预期的行，并且在八种引擎中包含 Oracle 的跨后端一致性属性测试也通过。在该服务器上，语句内部的 `COLLATE` 运算符无需 `EXTENDED` 即可工作；只有在列上**声明**排序规则才会失败（`ORA-43929`）。Oracle 12.2 到 21c **没有**运行过：上述下限来自 Oracle 的文档，而不是测量结果。
- **带引号的标识符。** 请用带引号的名称创建表和每一列，其拼写要与 schema 的 `source` 和 `column` 完全一致。Oracle 会把不带引号的名称转为大写，而编译出的语句会给每个标识符加引号（二者不一致时出现 `ORA-00942`）。
- **会话设置。** 编译出的语句把日期、日期时间和十进制数当作文本传递，并且不加类型转换，所以 Oracle 按会话的设置转换它们。请在连接上设置 `NLS_DATE_FORMAT = 'YYYY-MM-DD'`、`NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF"Z"'` 和 `NLS_NUMERIC_CHARACTERS = '.,'`；没有它们，每一个日期、日期时间或十进制数过滤都会失败（`ORA-01861`、`ORA-01722`），而使用逗号作小数点的客户端区域设置可能只在部分机器上引发这个问题。
- **分组列，静默义务。** 让会话使用 `NLS_COMP = BINARY` 和 `NLS_SORT = BINARY`（英文客户端的默认值；也是验证过的设置），或者在 `MAX_STRING_SIZE = EXTENDED` 的服务器上，为每个可分组的列和稳定键声明 `COLLATE BINARY`。默认排序规则跟随会话，可能会忽略大小写。列定义例如：

  ```sql
  "country" VARCHAR2(100) COLLATE BINARY
  ```

## MongoDB {#mongodb}

- **服务器 4.2 或更高版本**，因为每个有排序的管道都使用 `$unset` 阶段来丢弃其空值位置辅助字段。
- **不区分大小写**的字段编译为查询级排序规则（`locale: "en"`、`strength: 2`）。只有用相同排序规则创建的索引才能支持带排序规则的查询：`createIndex({ customer: 1 }, { collation: { locale: "en", strength: 2 } })`。
- **`contains`、`startsWith`、`endsWith`** 编译为经过转义的 `$regex`（MongoDB 中没有对排序规则友好的子串运算符）。正则表达式不会像等值比较那样使用感知排序规则的索引，所以在大型集合上预期会全表扫描，并请自行测量。
- **排序。** 排序作用于保存空值位置的计算辅助字段，因此没有任何索引能整体支持它；请为你的过滤建立索引（[Null ordering](semantics.html#sem-3)）。
- **分组请求区分大小写地比较。** MongoDB 每个查询只有一个排序规则。分组请求必须保持其分组桶精确，所以它的管道不带排序规则，同一请求中的用户过滤因此区分大小写地比较（GRP-2 所接受的差异 #3）。其他数据库在该过滤中会忽略大小写。

## OpenSearch 与 Elasticsearch {#opensearch-and-elasticsearch}

一个编译器同时服务于两者。索引映射由你负责，编译出的查询会引用你的 schema 所声明的子字段。

- **版本：** Elasticsearch 7.10 或更高版本，OpenSearch 1.0 或更高版本（用于 `term` 和 `wildcard` 上的 `case_insensitive`）。
- **`keyword` 子字段，在过滤中静默出错。** 每个被过滤、排序或分组的文本字段，都需要你声明为 `physical.search.keywordSubField` 的 `keyword` 子字段，它是索引映射中的一个多字段（multi-field）。如果缺失，对它的过滤会在没有任何错误的情况下匹配**零行**；只有对它的排序会失败。
- **不区分大小写的排序和范围。** 请声明 `physical.search.normalizedSubField`，并将其映射为带有忽略大小写 `normalizer` 的 `keyword`。这会占用索引空间，并且是对文本字段做不区分大小写的排序或比较的唯一途径；对于没有声明它的字段，编译器会拒绝编译这样的请求。
- **十进制数。** 把 `decimal` 字段映射为带足够 `scaling_factor` 的 `scaled_float`；如果只做等值比较，则映射为 `keyword`。`double` 映射会静默舍入。
- **深度分页和计数。** 超过 `max_result_window`（10,000 行）后，客户端使用时间点（point-in-time）和 `search_after` 分页；对 Elasticsearch，请在深度分页选项**和**导出选项上都把 `Flavour` 设为 `Elasticsearch`，否则每次导出都会以 HTTP 400 失败。超过 10,000 的总行数会报告为未知，除非你选择启用精确计数，而精确计数会在每次首次请求时统计所有匹配项。
- **`contains`** 是作用于 `keyword` 字段的通配符；以通配符开头会遍历词项字典，所以请在大型索引上测量它。

## 本页不涉及的内容 {#what-stays-out-of-this-page}

各引擎的具体调优（分区、覆盖索引、分片数量）取决于你的数据和工作负载。编译出的语句位于[一致性夹具](../../spec/fixtures/)中，每个用例一个文件夹，其中是各数据库收到的确切文本；请针对你自己的表，对这些语句运行 `EXPLAIN`。
