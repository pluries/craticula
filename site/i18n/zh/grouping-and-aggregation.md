---
translates: grouping-and-aggregation
title: 分组与聚合
description: 分组网格如何一次请求一层，以及聚合的行为方式。
source_fingerprint: 10e3bdf6eb7dc0f59a4e20738237bb2f9f7ebac06181756626f1c01f952450a5
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# 分组与聚合 {#grouping-and-aggregation}

本页介绍行分组与聚合：分组网格如何一次请求一层，Craticula 如何回答每一层，以及 schema 必须允许什么。本页面向网格需要对行分组并显示合计的开发者。行分组和聚合是 AG Grid Enterprise 的功能。

## 每个请求一层 {#one-level-per-request}

分组网格不会请求整棵树。它一次只请求一层，且每个请求都携带到目前为止的路径。

请求中的两个列表描述该路径：

- `rowGroupCols` 按顺序列出网格用于分组的列。
- `groupKeys` 列出用户已展开的分组，每一层对应一个键。

Craticula 比较两者的长度：

- **键少于列。** 请求要求的是一个分组层。Craticula 只按下一个尚无键的列分组，并为每个分组计算聚合。
- **键与列一样多。** 每一层都已展开。请求要求的是最后一个分组内部的行。Craticula 返回普通行，不做分组。
- **键多于列。** 请求格式错误，会被拒绝。

不支持透视模式。`pivotMode` 设为 `true` 的请求，或带有任何 `pivotCols` 的请求，都会被拒绝。

## 一个例子 {#an-example}

假设网格依次按 `region`、`segment`、`product` 分组，并对 `amount` 求和。用户已展开 `EMEA` 区域。网格现在请求 `EMEA` 内部的各个 segment。

对于 PostgreSQL，Craticula 写出：

```sql
SELECT "segment" AS "segment", COALESCE(SUM("amount"), 0) AS "amount_sum" FROM "sales_fact" WHERE "region" = $1 GROUP BY "segment" ORDER BY "segment" ASC NULLS LAST LIMIT $2 OFFSET $3
-- parameters: 'EMEA', 100, 0
```

已展开的分组变成了 `WHERE "region" = $1`。下一列 `segment` 变成了 `GROUP BY`。聚合被命名为 `amount_sum`。

## 分组键以带类型的值到达 {#group-keys-arrive-as-typed-values}

Craticula 将 `groupKeys` 中的每个条目读取为带类型的值，其类型与列声明的类型一致，而不是 AG Grid 发送的普通字符串：

```json
"groupKeys": [ { "type": "string", "value": "EMEA" } ]
```

您的页面必须在发送请求之前转换这些键。演示在 `examples/demo/web/src/datasource.ts` 的 `toWireRequest` 中完成这一步。它还会在返回途中重命名聚合列，因为响应将其命名为 `amount_sum`，而网格读取的是 `amount`。如果您复制演示，请两个步骤都复制。

## 可以使用哪些函数 {#which-functions-you-can-use}

Craticula 支持五个聚合函数：`sum`、`min`、`max`、`avg` 和 `count`。其他函数，例如 `first`，会被拒绝。没有 `aggFunc` 的 `valueCols` 条目同样会被拒绝。

结果中每个聚合的名称：当列 id 与字段名不同时，使用列 id；否则使用字段名、一个下划线和函数名，例如 `amount_sum`。

以下细节对数值很重要：

- `count` 统计字段不为空的行。它不统计行数。若要统计每一行，请统计稳定键，它绝不为空。
- 对没有值的分组求 `sum`，在每个后端上都是 `0`。SQL 编译器会包装 `sum` 以便与之一致。
- 对没有值的分组求 `avg`、`min` 和 `max`，结果为空。

## schema 必须允许什么 {#what-the-schema-must-allow}

schema 决定哪些列可以被分组和聚合。这两个标志默认都是关闭的。

```json
"region": { "type": "string", "groupable": true, "physical": { "sql": { "column": "region" } } },
"amount": { "type": "decimal", "aggregatable": ["sum", "avg"], "physical": { "sql": { "column": "amount" } } }
```

- 分组列必须在 schema 中，并标记为 `groupable`。
- 聚合必须指定 schema 中的一个列，以及该列的 `aggregatable` 列表中的一个函数。
- 已展开的列，即其键位于 `groupKeys` 中的列，也必须是 `filterable`。展开一个分组等同于按单个值进行过滤。

以上每一项在 Strict 和 Lenient 两种模式下都会被拒绝。丢弃分组列或分组键，会给网格一个与其请求不同的结果。参见 [Strict 与 Lenient](strict-and-lenient.html)。

## 展开分组时精确匹配 {#opening-a-group-matches-exactly}

展开一个分组时，其键会成为分组列上的精确匹配。分组、展开分组和对分组排序都使用精确比较，因此 `EMEA` 和 `emea` 是两个分组。如果分组不是精确匹配，其合计就无法与父级对上。

只有当数据库默认进行精确比较时，这一点才成立。PostgreSQL 和 SQLite 如此。SQL Server、MySQL 和 Oracle 通常会忽略大小写，因此请为每个用于分组的列声明二进制排序规则（collation）。参见[索引与数据库指南](index-guidance.html)。

MongoDB 对整个查询只有一个排序规则。分组请求不携带排序规则，因此同一请求中的过滤器在那里区分大小写进行比较。SQL 数据库则在该过滤器中忽略大小写。

## 空的分组键 {#null-group-keys}

分组值为空的行构成一个分组。要展开它，请发送键 `{ "type": "null" }`。Craticula 会为它写出一个空值测试，例如 `"region" IS NULL`。

空字符串与空值是不同的分组，因此它的行不会并入空值分组。Oracle 是例外，因为 Oracle 把空字符串存储为空值。

## 对分组层排序和计数 {#sorting-and-counting-a-grouped-level}

分组层可以按其分组列或其某个聚合排序。按任何其他列排序都会被拒绝。分组列充当稳定键，因此分组顺序是稳定的。在排序中列于分组列之后的聚合不起作用，会被丢弃。

分组层的行数是分组的数量，而不是其中行的数量。

OpenSearch 和 Elasticsearch 在这里有两项限制：

- 它们无法按聚合对分组层排序。此类请求会被拒绝。
- 包含空值的分组始终排在最前，无论方向如何。

## 导出忽略分组 {#exports-ignore-grouping}

导出返回普通行。适配器会从导出请求中丢弃 `rowGroupCols`、`valueCols` 和 `groupKeys`。参见 [CSV 导出](csv-export.html)。

## 内容来源 {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/group-aggregation](../../spec/fixtures/group-aggregation/README.md)
- [csharp/src/Craticula.Core/Ir/Aggregation.cs](../../csharp/src/Craticula.Core/Ir/Aggregation.cs)
- [csharp/src/Craticula.Core/Ir/GroupingPlan.cs](../../csharp/src/Craticula.Core/Ir/GroupingPlan.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
- [examples/demo/web/src/datasource.ts](../../examples/demo/web/src/datasource.ts)
- 相关页面：[分页与排序](paging-and-sorting.html)、[GridSchema](the-gridschema.html)、[请求如何变成查询](request-to-query.html)
