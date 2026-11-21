---
translates: request-to-query
title: 请求如何变成查询
description: 从 AG Grid 请求到带参数语句的完整路径。
source_fingerprint: 6c0315a52de692dbf39fc149aa86390474630dd3c2eb2282d8985f93da818dc0
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# 请求如何变成查询 {#how-a-request-becomes-a-query}

本页逐步跟随一个 AG Grid 请求经过 Craticula，直到它变成带参数的查询。本页面向想知道网格与数据库之间发生了什么、以及为什么需要多个步骤的开发者。

## 路径 {#the-path}

```text
request JSON -> adapter -> canonical form -> compiler -> query + parameters
```

1. **请求 JSON。** 由网格发送。Craticula 不会改动网格发送的内容。
2. **适配器。** AG Grid 适配器读取该 JSON，并将其转换为规范形式。它会拒绝无法理解的 JSON。
3. **规范形式。** 项目称之为 IR，即中间表示（intermediate representation）。它是对过滤、排序、分组和分页的统一描述，既不依赖 AG Grid，也不依赖任何数据库。
4. **检查。** 编译之前，Craticula 会依据您的 schema 和资源限制检查规范形式。它还会把每个值转换为 schema 所声明的类型。
5. **编译器。** 每个后端有一个编译器来生成查询。SQL 编译器为每种数据库方言提供一个写入器。
6. **查询与参数。** 对于 SQL，您得到语句文本和一个值列表。这些值绝不会成为文本的一部分。

由于每个后端读取的都是同一种规范形式，同一个请求在任何地方含义相同。空值处理和大小写敏感性等细节的规则只在规范中写一次，所有编译器都遵循它。

## schema 是边界 {#the-schema-is-the-boundary}

schema 是您编写的一份 JSON 文档。它指明表或集合，以及网格可以使用的列。每一列都有类型和在数据库中的物理名称。它还指明一个稳定键（stable key），即取值唯一的列，Craticula 用它使分页保持固定顺序。

不在 schema 中的列无法进入查询。其工作方式参见[安全模型](safety-model.html)。

## 请求可以要求什么 {#what-the-request-can-ask-for}

- **分页。** 网格请求一个行范围，例如前 50 行。Craticula 将其转换为 limit 和 offset，或您的后端对应的等价形式。页面有最大大小。
- **排序。** 排序按网格发送的顺序执行。Craticula 在末尾追加稳定键，使取值相同的行始终以相同的顺序返回。
- **过滤。** 文本、数字和日期过滤器会变成以 AND 或 OR 连接的比较。文本默认不区分大小写进行匹配。
- **分组。** 对于分组网格，请求携带分组列、已展开的分组键以及要计算的聚合。Craticula 为被请求的那一层构建分组查询。

## 一个小例子 {#a-small-example}

这是快速入门中的请求。它要求查找包含 "acme" 且金额大于 100 的客户，金额最大的在前，行 0 至 50。

```json
{
  "startRow": 0,
  "endRow": 50,
  "rowGroupCols": [],
  "valueCols": [],
  "pivotCols": [],
  "pivotMode": false,
  "groupKeys": [],
  "filterModel": {
    "customer": { "filterType": "text", "type": "contains", "filter": "acme" },
    "amount": { "filterType": "number", "type": "greaterThan", "filter": 100 }
  },
  "sortModel": [ { "colId": "amount", "sort": "desc" } ]
}
```

对于 PostgreSQL，快速入门程序会打印如下语句和参数：

```sql
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0
```

请看发生了什么：

- "acme" 和 100 不在文本中。它们是参数。
- 表名和列名来自 schema，而不是来自请求。
- 排序以 `id` 结尾，即 schema 的稳定键。
- 页面范围变成了 `LIMIT 50 OFFSET 0`。

对于同一个请求，SQL Server 会得到不同的语句，因为它对不区分大小写的匹配和空值排序的写法不同。[C# 快速入门](quickstart-csharp.html)展示了两者。

## 您在 C# 中要写什么 {#what-you-write-in-c}

在快速入门中，代码按以下顺序做四件事：

1. 用 `GridSchema.Parse` 解析 schema。
2. 用 `AgGridRequestParser.Parse` 解析请求。
3. 用 `GridFilterPipeline.Process` 进行验证。它会执行列检查、限制检查和类型转换。
4. 用 `SqlQueryBuilder.Build` 和某个方言（如 `PostgresDialect.Instance`）进行编译。

MongoDB 和 OpenSearch 有各自的构建器，即 `MongoPipelineBuilder` 和 `SearchQueryBuilder`。

若要在页面旁显示总行数，每个编译器还提供 `BuildCount`。它使用相同的过滤条件，但不带排序和行窗口，因为计数不需要它们。进行计数时，请给 `GridFilterPipeline.Process` 传入 `NonePage`，这样较大的页面大小就不会使其失败。

## 内容来源 {#where-this-comes-from}

- [site/pages/quickstart-csharp.md](quickstart-csharp.md)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [spec/fixtures/operators](../../spec/fixtures/operators/001-eq-string/description.md)
