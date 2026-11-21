---
translates: the-gridschema
title: GridSchema
description: 列出表格可以触及哪些内容的 schema，以及它的哪些标志目前真正生效。
source_fingerprint: cdf6e47e0fa6a2ef7b974c3b2ac02ea7892b7f9a31ffa33a18595708e80d8a45
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# GridSchema {#the-gridschema}

本页说明你为每个表格编写的 schema：它包含什么，Craticula 目前强制执行其中的哪些设置，以及如何着手编写。本页面向即将向 Craticula 描述一张表、一个集合或一个索引的开发者。完整的成员列表，请参见 [GridSchema 参考](grid-schema.html)。

## schema 的用途 {#what-the-schema-is-for}

schema 是请求与你的数据之间的边界。它是一份由你编写、并保存在服务器上的 JSON 文档。它指明表、集合或索引的名称，列出表格可以触及的每一列，并为每一列给出类型以及它在你的数据库中的物理名称。

不在 schema 中的列，绝不可能进入查询。查询中的表名和列名来自 schema，绝不来自请求。参见 [安全模型](safety-model.html)。

任何请求都不能携带 schema。表格按其表格 id 发送列，Craticula 逐个查找它们。

## 一个小示例 {#a-small-example}

这是快速入门中的 schema。它描述一张 `orders` 表。

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": {
    "id":       { "type": "int64",    "sortable": true, "physical": { "sql": { "column": "id" } } },
    "customer": { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "customer" } } },
    "amount":   { "type": "decimal",  "filterable": true, "sortable": true, "physical": { "sql": { "column": "amount" } } },
    "status":   { "type": "string",   "filterable": true, "sortable": true, "physical": { "sql": { "column": "status" } } }
  }
}
```

在 C# 中，使用 `GridSchema.Parse(json)` 加载它。

## 整个 schema 的成员 {#the-members-of-the-whole-schema}

| 成员 | 作用 |
|---|---|
| `mode` | `strict` 或 `lenient`。JSON Schema 要求提供它；缺失时，C# 解析器默认为 strict。参见 [Strict 与 Lenient](strict-and-lenient.html)。 |
| `source` | 表或视图、MongoDB 集合，或 OpenSearch 索引。不能为空白。 |
| `stableKey` | 取值唯一的列。它必须是 `fields` 之一。 |
| `fields` | 允许清单，以表格的列 id 为键。至少需要一个字段。 |
| `staticFilter` | 添加到每个查询的过滤器。可选。 |

`GridSchema.Parse` 会拒绝违反这些规则的 schema。它还会拒绝未知成员、重复的键，以及没有恰好设置 `column`、`qualifiedColumn` 和 `expression` 之一的 `physical.sql`。

## 单个字段的成员 {#the-members-of-one-field}

| 成员 | 作用 |
|---|---|
| `type` | `string`、`int64`、`decimal`、`double`、`boolean`、`date` 或 `datetime`。Craticula 会把每个请求值转换为该类型。 |
| `physical` | 列所在的位置：`sql`、`mongo`、`search`，或三者都有。 |
| `text` | 对 `string` 而言：`caseSensitivity`（默认为 `insensitive`）和 `searchMode`。 |
| `filterable`、`sortable`、`groupable`、`aggregatable` | 表格可以对该列做什么。见下文。 |
| `exportable`、`label`、`format` | 该列在 CSV 导出中如何呈现。参见 [CSV 导出](csv-export.html)。 |

你只需要为所用的后端提供映射。SQL 映射是一个普通的列。MongoDB 映射是一个文档路径。搜索映射指明索引字段，还可以指明一个 `keywordSubField` 和一个 `normalizedSubField`。完全没有映射的字段，使用它的列 id 作为名称。

## 各标志目前的作用 {#what-each-flag-does-today}

不要以为每个标志都会被强制执行。以下是代码目前的实际行为：

| 标志 | 默认值 | 是否强制执行？ |
|---|---|---|
| `filterable` | `true` | 是。对标记为 `false` 的列的过滤，在 Strict 模式下被拒绝，在 Lenient 模式下被丢弃。集合过滤器取值列表所在的列，以及用户已展开的分组键，必须是可过滤的，两种模式下都会被拒绝。 |
| `groupable` | `false` | 是。分组列必须是可分组的。两种模式下都会被拒绝。 |
| `aggregatable` | 无 | 是。聚合必须使用此列表中的函数。两种模式下都会被拒绝。 |
| `exportable` | `true` | 是。它决定默认的导出列，并且标记为 `false` 的列不能在 `exportColumns` 中被指名。 |
| `sortable` | `true` | **否。** 目前没有任何地方读取它。无论该标志如何设置，schema 中的列都可以被排序。 |

`aggregatable` 列表可以包含 `sum`、`min`、`max`、`avg` 和 `count` 中的任意几项。参见 [分组与聚合](grouping-and-aggregation.html)。

如果你必须阻止某一列被排序，请把它从 schema 中去掉，或者依靠你自己的检查。该标志做不到这一点。

## 稳定键 {#the-stable-key}

`stableKey` 是分页保持顺序的依据。Craticula 会把它添加到每个排序的末尾。它必须指向一个取值唯一的列。请在你的数据库中把该列声明为 `NOT NULL`，因为大多数数据库允许唯一列中出现多个 null，而这会破坏这一保证。参见 [分页与排序](paging-and-sorting.html)。

## 静态过滤器 {#the-static-filter}

`staticFilter` 是 Craticula 用 AND 添加到每个查询的条件。租户 id 或软删除标志应放在这里。请求无法更改或移除它。

```json
"staticFilter": {
  "type": "comparison",
  "op": "eq",
  "field": "tenantId",
  "value": { "type": "int64", "value": 42 }
}
```

`staticFilter` 所指名的字段也必须在 `fields` 中声明，以便编译器找到它的列。该条件属于 schema 的一部分，因此请求无法触及它。决定过滤器应该是什么，是你的工作。Craticula 只负责应用它。参见 [安全模型](safety-model.html)。

## 字段顺序 {#field-order}

文档中字段的顺序是有意义的。没有列列表的导出请求，会按该顺序得到可导出的字段。已展开分组内部的行，也按该顺序返回。

## 本页的依据 {#where-this-comes-from}

- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchema.cs](../../csharp/src/Craticula.Core/Schema/GridSchema.cs)
- [csharp/src/Craticula.Core/Schema/FieldConfig.cs](../../csharp/src/Craticula.Core/Schema/FieldConfig.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/fixtures/schemas](../../spec/fixtures/schemas)
- 相关页面：[限制](limits.html)、[方言与提供程序](dialects-and-providers.html)、[请求如何变成查询](request-to-query.html)
