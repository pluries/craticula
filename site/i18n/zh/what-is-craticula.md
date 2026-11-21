---
translates: what-is-craticula
title: Craticula 是什么
description: Craticula 编译什么、绝不做什么，以及目前的进展。
source_fingerprint: e8f756cfd41d5e8621dce7f0e9a10a459e2c9061e1f4434abe57c82e8adc1664
drafter: claude
drafted_on: 2026-11-19
status: approved
---
# Craticula 是什么 {#what-craticula-is}

本页说明 Craticula 做什么、把什么留给您，以及项目目前的进展。本页面向已有 AG Grid 服务端网格、但从未见过 Craticula 的开发者。

Craticula 是一个 .NET 库，它把 AG Grid Server-Side Row Model 请求转换为数据库查询。它支持 SQL、MongoDB 和 OpenSearch。

## 它解决的问题 {#the-problem-it-solves}

AG Grid 服务端网格会向您的服务器发送一个 JSON 请求。该请求说明网格需要哪些行、如何排序、如何过滤以及如何分组。

每个后端团队最终都要编写同样的代码，把这个 JSON 转换为查询。这类代码很容易出错。空值处理、大小写敏感性、分页和注入安全都需要格外小心。

Craticula 就是这一转换，只写一次，并用共享的示例进行测试。

## 它编译什么 {#what-it-compiles}

您向 Craticula 提供两样东西：

- 与 AG Grid 发出时完全一致的请求；
- 一个 schema，列出网格可以访问的列，以及这些列如何映射到您的数据库。

Craticula 返回一个您可以运行的查询：

- 对于 SQL，返回一条语句和一个参数列表；
- 对于 MongoDB，返回一个聚合管道；
- 对于 OpenSearch 和 Elasticsearch，返回以其 JSON 查询语言编写的查询。

## 它绝不做什么 {#what-it-never-does}

Craticula 是编译器，而不是客户端。

- 它绝不打开数据库连接。
- 它绝不运行查询。
- 它绝不读取您的数据。

运行查询是您的职责。可选的适配器包可以代您完成，但它们与核心相互独立。核心包绝不依赖它们。

## 支持的后端与 AG Grid 版本 {#supported-backends-and-ag-grid-versions}

第一个版本面向以下后端：

- PostgreSQL
- SQL Server
- MySQL 和 MariaDB
- SQLite
- MongoDB
- OpenSearch
- Elasticsearch

Oracle 不在 v1 的清单中，项目将其视为一个悬而未决的问题。仓库中包含 Oracle 方言，但它不属于承诺范围。

在网格一侧，README 列出的是 AG Grid Server-Side Row Model 31 至 36 版本。它还支持用于平面网格的 Community 无限行模型，即排序、文本、数字和日期过滤器以及分页。行分组、聚合、透视和集合过滤器属于 Enterprise 功能，不在 Community 的承诺范围内。

不支持透视模式。请求解析器会拒绝开启透视模式的请求。

## 当前状态 {#current-state}

Craticula 处于预发布阶段。目前尚未发布任何包，也没有人为访客运行演示。仓库中有一个需要您自行运行的演示应用（`examples/demo`），它需要 Docker、.NET 10 SDK 和 Node。

若要试用，请从源代码构建。[C# 快速入门](quickstart-csharp.html)介绍了具体方法。C# 库是参考实现。仓库说明 TypeScript、Python 和 Go 的移植版本计划在规范冻结之后进行，目前均尚不存在。

## 下一步 {#where-to-go-next}

- [请求如何变成查询](request-to-query.html)带您跟随一个请求走完整个流水线。
- [Strict 与 Lenient](strict-and-lenient.html)说明处理未知列的两种方式。
- [安全模型](safety-model.html)列出 Craticula 保护什么、不保护什么。

## 内容来源 {#where-this-comes-from}

- [README.md](../../README.md)
- [spec/README.md](../../spec/README.md)
- [csharp/src/Craticula.Core/README.md](../../csharp/src/Craticula.Core/README.md)
- [csharp/src/Craticula.AgGrid/AgGridRequestParser.cs](../../csharp/src/Craticula.AgGrid/AgGridRequestParser.cs)
