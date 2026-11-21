---
translates: safety-model
title: 安全模型
description: 值、标识符和限制如何保证编译出的查询安全，以及哪些事情留给您。
source_fingerprint: cad40472e319059d27fe5a7517ac79ed14efb07866e1630c2883f9c7419a959c
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# 安全模型 {#the-safety-model}

本页列出 Craticula 为防止恶意请求损害您的数据库所做的事情，以及它不做的事情。本页面向需要判断 Craticula 是否适合面向公众系统的开发者或审阅者。

## 值就是参数 {#values-are-parameters}

请求中的每个值都以参数的形式进入查询。它绝不会被粘贴进文本。

对于 SQL，语句中包含 `$1` 之类的占位符，而值通过单独的列表传递。对于快速入门中的请求，文本中既没有 "acme"，也没有 100。参见[请求如何变成查询](request-to-query.html)。

规范对 MongoDB 和 OpenSearch 采用同样的思路。在那里，值作为数据进入管道或查询文档。包含模式字符的文本搜索值会被转义。编译器为此提供了辅助函数。

在普通文本过滤器中发送的 `'; DROP TABLE users; --` 之类的值，只是一个字符串。它被用于比较，不会产生其他任何效果。对抗性测试用例（fixture）针对的是请求的结构，而不是字符串的内容。

## 标识符来自您的 schema {#identifiers-come-from-your-schema}

表名、集合名和列名只来自您编写的 schema。请求从不提供其中任何一个。

请求以网格 id（如 `customer`）来指称列。Craticula 在 schema 中查找该 id，并使用您声明的物理名称。对于 SQL，名称会按方言加引号，名称内部的引号字符会被重复一次（转义）。

## 未知列会被拒绝 {#unknown-columns-are-refused}

不在 schema 中的列会在任何查询生成之前就被拒绝。快速入门展示了对 `password` 的过滤被拒绝。

不在 schema 中的列，在任何模式下都不能用于分组、聚合或排序。对此类列的过滤在 Strict 模式下被拒绝，在 Lenient 模式下被丢弃；参见 [Strict 与 Lenient](strict-and-lenient.html)。schema 还可以将某列标记为不可过滤、不可分组或不可导出。

## 格式错误的输入会被拒绝 {#malformed-input-is-refused}

适配器和各项检查会拒绝它们无法识别的输入：

- 未知的过滤运算符，包括拼写错误或 `regex`；
- 在应为单个值的位置发送了对象或数组的过滤值；
- JSON 中的重复键；
- 与列类型不符的值，例如数字列中的文本；
- 聚合的输出名称重复。

以上每一种都有一个期望干净拒绝的测试用例（fixture）。

## 资源限制 {#resource-limits}

请求不能要求无限的工作量。以下是 `ResourceLimits` 中的默认值：

| 限制 | 默认值 |
|---|---|
| 过滤树深度 | 8 |
| 整个过滤器中的条件数 | 64 |
| 一个 in 或 not-in 列表中的值数 | 1000 |
| 一页中的行数 | 1000 |
| 去重值请求返回的行数 | 最多 10000 |
| 未发送行窗口的请求中的行数 | 默认一页 100 行（仅导出或您开启的标志才会返回所有行） |
| MongoDB 和 Search 上的查询时间 | 未设置；由您设置，并由数据库强制执行 |

每一项都可以调高或调低。您不能关闭某项限制，只有查询时间限制例外：它是可选的，在您设置之前一直处于未设置状态。设置时，零或负数会被拒绝。参见[限制](limits.html)。

测试用例（fixture）会在每项限制的边界之外再多走一步进行测试，也会用极端值测试，例如包含 5000 个值的列表或一百万行的页面。

## Craticula 不防护什么 {#what-craticula-does-not-protect-against}

- **数据库账户。** Craticula 不控制账户能做什么。请授予运行这些查询的账户所需的最小权限，例如仅对那一张表只读。
- **运行查询。** Craticula 绝不运行查询。连接处理、成本限制以及您如何运行语句都由您负责。对于 MongoDB 和 Search，您可以让编译出的查询携带由数据库强制执行的时间限制（`MaxQueryTimeMs`）；对于 SQL，请在连接或账户上设置语句超时。
- **谁可以使用网格。** 身份认证和按用户的访问控制不在其范围之内。schema 可以为每个查询添加一个固定的过滤器，但该过滤器应该是什么由您决定。
- **错误的 schema。** 如果您的 schema 列出了应保持隐藏的列，Craticula 就会提供该列。
- **慢查询。** 如果某列没有索引，即使在限制之内的请求也可能很慢。参见[索引指南](index-guidance.html)。

## 内容来源 {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
- [csharp/src/Craticula.Core/Schema/ResourceLimits.cs](../../csharp/src/Craticula.Core/Schema/ResourceLimits.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [csharp/src/Craticula.Sql/PostgresDialect.cs](../../csharp/src/Craticula.Sql/PostgresDialect.cs)
- [csharp/samples/Craticula.Quickstart/Program.cs](../../csharp/samples/Craticula.Quickstart/Program.cs)
