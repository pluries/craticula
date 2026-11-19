---
translates: strict-and-lenient
title: Strict 与 Lenient
description: 两种 schema 模式如何处理 schema 不允许的列。
source_fingerprint: 20ab3fa199820cb9e052565112f509257cd8428bafaf7eced343e56e4ea4c25a
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# Strict 与 Lenient {#strict-and-lenient}

本页说明 schema 可以运行的两种模式，以及当请求中出现 schema 不允许的列时，每种模式会怎么做。本页面向正在编写 schema 并需要选择模式的开发者。

简要结论：除非有特别的理由，否则请使用 Strict。Strict 是默认值。

## 在哪里设置模式 {#where-you-set-the-mode}

模式是 schema 中的一个设置，取值为 `strict` 和 `lenient`。

```json
{
  "mode": "strict",
  "source": "orders",
  "stableKey": "id",
  "fields": { }
}
```

在 C# 中，`GridSchema.Mode` 默认为 `Strict`。该文件的 JSON schema 将 `mode` 列为必填项，因此请在您的 schema 文件中明确写出。

## Strict {#strict}

在 Strict 模式下，对 schema 中未列出的列进行过滤会被拒绝。Craticula 会抛出 `UnknownFieldException`，其中列出所有被拒绝的列。不会生成任何查询。

对于 schema 中列出、但标记为 `filterable: false` 的列，情况相同。Craticula 将其视为未知列。

对抗性测试用例（fixture）展示了这一点。对未知列的过滤、排序和行分组都会被拒绝。过滤和行分组抛出 `UnknownFieldException`；排序则由编译器拒绝（见下文最后一点）。由 SQL 构成的列名，例如 `amount'); DROP TABLE users; --`，同样会被拒绝。

## Lenient {#lenient}

在 Lenient 模式下，Craticula 会丢弃针对未知或不可过滤列的过滤条件，并继续处理其余部分。

丢弃条件会使结果范围变宽。网格得到的行可能比它所请求的更多。只有在您接受这一点时才应选择 Lenient。

关于被丢弃的条件如何移除，有以下细节：

- 失去全部条件的 AND 或 OR 组会消失。
- 只剩一个条件的组会变成该条件本身。
- 条件消失的 NOT 也会消失。它不会变成“匹配全部”或“不匹配任何”。

## 任何模式都不会放宽的内容 {#what-no-mode-relaxes}

Lenient 只会宽容过滤条件。规范规定，凡是决定结果形状的内容，在每种模式下都会被拒绝：

- 不在 schema 中、或未标记为 groupable 的分组列；
- 深入到不可过滤列的分组键；
- 针对不在 schema 中的列、或不允许使用该函数的列的聚合；
- 集合过滤器的去重值请求所涉及的列；
- 未知、不可导出、重复或为空列表的导出列。

原因在于，丢弃这些内容会在没有任何错误的情况下，给网格一个与其请求不同的结果。被丢弃的分组键可能会在网格期望的标签下返回另一个分组的行。

模式对其他检查也没有影响。过深、过宽、请求行数过多，或值与列类型不符的请求，在两种模式下都会被拒绝。参见[安全模型](safety-model.html)。

还有一点：对 schema 中未列出的列进行排序，在两种模式下都会被拒绝。拒绝来自编译器，它抛出的是自己的编译异常，而不是 `UnknownFieldException`，因此请在您的端点中同时捕获两者，并返回客户端错误。

## 如何选择 {#how-to-choose}

- 如果网格由您自己掌控，且未知列意味着缺陷或攻击，请选择 **Strict**。您会立即发现问题。
- 只有当您接受“请求中出现未知或不可过滤的列时返回更多行而不是报错”时，才选择 **Lenient**。

如果拿不准，请使用 Strict。

## 内容来源 {#where-this-comes-from}

- [spec/semantics.md](../../spec/semantics.md)
- [spec/grid-schema.schema.json](../../spec/grid-schema.schema.json)
- [csharp/src/Craticula.Core/Schema/GridSchemaMode.cs](../../csharp/src/Craticula.Core/Schema/GridSchemaMode.cs)
- [csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs](../../csharp/src/Craticula.Core/Schema/FieldAllowlistValidator.cs)
- [spec/fixtures/adversarial](../../spec/fixtures/adversarial/README.md)
