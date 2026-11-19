---
translates: limits
title: 限制
description: 默认的资源限制、每项限制的作用，以及如何更改它们。
source_fingerprint: 4ebb0479bf2bf034db02fbe9221ed719f6f737678d26a8c1dee647b249dba066
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# 限制 {#limits}

本页列出 Craticula 对每个请求施加的资源限制，说明每项限制保护什么，以及如何更改。本页面向运行公开表格的开发者，或想知道为什么某个大请求被拒绝的开发者。

## 为什么要有限制 {#why-there-are-limits}

请求是来自陌生人的输入。没有限制的话，一个请求可以要求嵌套一千层的过滤树、包含一百万个值的列表，或者一千万行的页。每一种都会让你的数据库付出大量工作。

Craticula 会在构建查询之前就拒绝这样的请求。

## 各项限制及其默认值 {#the-limits-and-their-defaults}

| 设置 | 默认值 | 限制的内容 |
|---|---|---|
| `MaxDepth` | 8 | 过滤器最多可以嵌套多深。单个条件的深度为 1。 |
| `MaxLeaves` | 64 | 整个过滤器中的条件数量，跨所有分支累计。 |
| `MaxInValues` | 1000 | 一个“in”或“not in”列表中的值的数量。 |
| `MaxPageSize` | 1000 | 一页中的行数，即 `endRow - startRow`。 |
| `MaxSetValuesResults` | 10000 | 一次取不同值的请求最多可返回的值的数量，无论表格要求多少。 |
| `DefaultSetValuesResults` | 1000 | 表格没有说明时，该请求返回多少个值。 |
| `MaxQueryTimeMs` | 未设置 | MongoDB 或 Search 查询可以运行多久，单位为毫秒。这是唯一的可选限制；参见 [查询时间限制](#the-query-time-limit)。 |

这些都是 `ResourceLimits` 的属性。

前四项是检查：超出限制的请求会被拒绝。接下来两项是上限。`MaxQueryTimeMs` 两者都不是：它被带入查询，由数据库来强制执行。针对集合过滤器的取不同值请求，绝不会因为过大而被拒绝。Craticula 会把它限制到上限，而在表格没有发送数字时使用默认值。

不发送 `startRow` 和 `endRow` 的请求也并非没有限制：它会得到一个 100 行的默认页（`AgGridParseOptions.DefaultPageSize`），页大小限制会像检查其他页一样检查该页。参见 [分页与排序](paging-and-sorting.html)。

页大小限制不适用于导出完整结果（`exportScope` 为 `"all"`），因为这种导出没有页。按页导出保留其行范围，页大小限制对其生效。参见 [CSV 导出](csv-export.html)。

Craticula 会把用户已展开的分组与过滤器一起计数。每个已展开的分组算作多一个条件，而分组请求计算的层级比它写出的多一层，因此在默认值下，它的有效深度限制是 7。

## 固定的限制 {#limits-that-are-fixed}

有一些界限是内置的，不能更改：

- 一个请求中最多 64 个分组列；
- 过滤器中的文本值最多 8192 个字符；
- decimal 值最多 128 个字符；
- 列 id 最多 256 个字符，适用于排序键、分组列、聚合或集合过滤器的列。

## 拒绝是什么样子 {#what-a-refusal-looks-like}

当请求违反某项限制时，`GridFilterPipeline.Process` 会抛出 `ResourceLimitExceededException`。它的 `Violations` 列表会指明每一项被违反的限制，以及实际数值和最大值。请在你的端点中捕获它，并返回客户端错误。如果一个请求同时违反两项限制，你会同时看到两项。

## 如何更改限制 {#how-to-change-a-limit}

这些限制不在 schema 文件中。它们是代码，由你传入。演示程序就是这样设置自己的限制的：

```csharp
public static ResourceLimits Default { get; } = new()
{
    MaxPageSize = 500,
    MaxDepth = 6,
    MaxLeaves = 32,
    MaxInValues = 200,
    MaxSetValuesResults = 1_000,
    DefaultSetValuesResults = 200
};
```

然后把该值传给接受它的调用。快速入门传入的是 `new ResourceLimits()`，即使用默认值。

```csharp
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);
```

取不同值的请求通过 `GridFilterPipeline.ProcessSetValues` 处理，其上限来自 `ResourceLimitsValidator.ResolveSetValuesLimit`。

你可以把限制提高到任意高度。没有上界检查。请选择你的数据库承受得起的数字。

## 查询时间限制 {#the-query-time-limit}

`MaxQueryTimeMs` 适用于数据库为共享或公开的宿主程序。其他限制约束请求的形状；这一项则约束数据库为该请求所做的工作。把它设为 1 到 2,147,483,647 之间的整数毫秒数，编译器就会把它放入查询：

| 引擎 | 查询携带的内容 | 时间到了会发生什么 |
|---|---|---|
| MongoDB | 聚合命令上的 `maxTimeMS` | MongoDB 取消该操作，适配器抛出 `QueryTimeoutException`。 |
| OpenSearch 与 Elasticsearch | 搜索请求体中的 `timeout` 成员，例如 `"2000ms"` | 引擎在下一次检查时停止（软限制），并以 `timed_out: true` 作答。适配器抛出 `QueryTimeoutException`，绝不会把部分命中当作一页返回。 |

该限制只来自你的代码。请求无法设置、提高或移除它，请求中的 `maxQueryTimeMs` 会被忽略。导出不带限制，因为导出按设计就很耗时；请用取消令牌（cancellation token）来停止导出。SQL 引擎没有编译出的限制：请改为在连接或数据库账户上设置语句超时（公开演示对 PostgreSQL 就是这样做的）。

不设置它，则一切保持不变：查询与原来完全一样。零或负值会在你构建 `ResourceLimits` 时抛出异常；如果你手工填写请求，编译器也会拒绝它。相关规则参见 [查询时间限制](query-time-limit.html)。

## 你无法关闭限制 {#you-cannot-turn-a-limit-off}

除一项以外，每项限制都是普通的正数，没有“无限制”这个值。把限制设为零或更小，会在你构建 `ResourceLimits` 时抛出 `ArgumentOutOfRangeException`。例外是 `MaxQueryTimeMs`，它默认未设置，因为库无法知道你的数据库有多慢；把它设为某个数字，绝不会关闭任何东西。

这是有意为之。零不会意味着“没有限制”。它会拒绝每一个请求，而被误留空的设置可能在无人察觉的情况下造成这种后果。

## 检查在何处运行 {#where-the-checks-run}

限制由 `GridFilterPipeline.Process` 检查。读取 AG Grid 请求的适配器不检查它们，编译器也不检查。如果你跳过管道、自行调用编译器，就不会检查任何限制。快速入门正是出于这个原因调用该管道。参见 [请求如何变成查询](request-to-query.html)。

## 本页的依据 {#where-this-comes-from}

- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimitsValidator.cs)
- [csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs](../../csharp/src/Craticula.Core/Schema/GridFilterPipeline.cs)
- [csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs](../../csharp/src/Craticula.Core/Ir/GroupSpecValidator.cs)
- [spec/semantics.md](../../spec/semantics.md)，其中关于查询时间限制和默认页大小的附录
- [examples/demo/Api/Grid/DemoLimits.cs](../../examples/demo/Api/Grid/DemoLimits.cs)
- [spec/ir.schema.json](../../spec/ir.schema.json)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- 相关页面：[安全模型](safety-model.html)、[分页与排序](paging-and-sorting.html)、[GridSchema](the-gridschema.html)
