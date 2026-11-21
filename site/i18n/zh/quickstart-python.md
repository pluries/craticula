---
translates: quickstart-python
title: Python
description: Python 移植版将遵循的内容。
source_fingerprint: 1a16c930083a5f86f8097b39f7a061a955f53e1df4f9037186cd267905f2c2ba
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# 快速入门：Python {#quickstart-python}

**目前还没有 Python 实现。** 本页特意这样说明，以免你去寻找一个并不存在的软件包。

## 为什么 {#why}

Craticula 以规范为先：`spec/` 中的规则和一致性测试夹具（conformance fixtures）先行，每一种语言的实现都必须通过同一批夹具。Python 移植版计划在**规范冻结之后**进行（规范在 1.0 时冻结）。在此之前规范仍可能变化，现在写出的移植版就得重写。

目前没有为 Python 发布任何东西：没有软件包，也没有安装命令。

## 你现在可以做什么 {#what-you-can-do-today}

- 使用 C# 库，它是参考实现：[快速入门：C#](quickstart-csharp.html)。
- 阅读 Python 移植版必须遵循的规则：[语义](semantics.html)，以及 schema 参考（[GridSchema](grid-schema.html)、[IR](ir-schema.html)）。
- 看看移植版必须通过的测试：一致性夹具（`spec/fixtures`）以及 [`spec/conformance-runner.md`](../../spec/conformance-runner.md) 中描述的与语言无关的运行器。任何语言写的驱动程序都可以回答运行器的请求，由运行器对这些回答评分。
