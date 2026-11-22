---
translates: overview
title: 概览
description: Craticula 是什么、它编译什么，以及目前进展到哪一步。
source_fingerprint: c3dad5cf6df4a66c49bd0d2e9d8c4a27f6d981379f463a98eadd2a7b96c4a407
drafter: claude
drafted_on: 2026-11-22
status: approved
---
# Craticula {#craticula}

[![CI](https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![coverage gate](https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25%20per%20assembly-brightgreen)](https://github.com/pluries/craticula/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/pluries/craticula)](LICENSE)
[![spec version](https://img.shields.io/badge/spec-0.3.0-blue)](spec/VERSION)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pluries/craticula/badge)](https://scorecard.dev/viewer/?uri=github.com/pluries/craticula)

> 它是编译器，而不是客户端：把 AG Grid Server-Side Row Model 请求翻译成原生、
> 安全的后端查询——SQL、MongoDB、OpenSearch/Elasticsearch——全部来自同一个规范的 IR，
> 覆盖四种语言。

**维护者：** Christian Stephan（[cstephan.dev](https://cstephan.dev)、[LinkedIn](https://www.linkedin.com/in/christian-stephan)、[GitHub](https://github.com/cstephan-dev)）。Craticula 是基于 Apache-2.0 许可的开源项目；
项目网站是 [craticula.pluries.dev](https://craticula.pluries.dev)。

**状态：** 早期设计阶段。维护者在内部保管一份技术需求文档（TRD：架构、
安全模型、路线图、未决问题）；其需求编号（AR-1、SEM-1、GRP-7 等）
在本仓库中随处被引用，规范性规则见 [`spec/semantics.md`](spec/semantics.md)。

## 为什么 {#why}

每个后端团队都要重新实现把 AG Grid SSRM 请求
（`filterModel`、`sortModel`、`rowGroupCols`、`groupKeys`、`valueCols`、`startRow`/`endRow`）
翻译成数据库查询的工作，通常借助字符串形式的 DSL 中间层，结果是运算符缺失、
空值和大小写语义有缺陷、存在注入风险，并且不支持分组和搜索引擎。目前没有任何
持续维护的开源库能端到端地覆盖这些需求。

## 工作原理 {#how-it-works}

![一个请求如何变成查询：AG Grid 请求经过请求适配器进入规范的 IR，查询编译器再把它转换为查询产物（带参数的 SQL、MongoDB 聚合管道或 OpenSearch 查询），整个过程都对照 GridSchema 进行检查；可选的执行适配器负责运行该产物，并把行重新整理为表格响应。](site/diagrams/how-it-works.svg)

核心从不打开连接：编译是一个纯函数，输入是一个表格请求
加上一份架构配置（安全与类型的边界），输出是一个普通的查询产物。
执行——运行该产物，并把结果重新整理为表格响应——
由独立且可选的适配器包负责，每个生态系统一个。

## 范围 (v1) {#scope-v1}

- **请求适配器**（规范称之为 *frontend adapter*；它是编译器的输入端，运行在你的服务器中，而不是浏览器里）：AG Grid SSRM (v31–v36)。AG Grid Community 的 Infinite Row Model 支持扁平表格
  （排序、文本、数字和日期过滤器、分页；见 [`spec/fixtures/community-infinite`](spec/fixtures/community-infinite/README.md)）。
  行分组、聚合、透视和集合过滤器属于 Enterprise 功能，不在这项承诺之内。
- **查询编译器**（规范中的 *backend compilers*，同样运行在你的服务器中）：PostgreSQL、SQL Server、MySQL/MariaDB、SQLite、MongoDB、OpenSearch、
  Elasticsearch。Oracle 由社区测试：使用同一条 SQL 管道，分页采用 `FETCH FIRST`（12c 及更高版本）。
- **参考实现：** C#/.NET，在规范于 1.0 冻结之后
  移植到 TypeScript、Python 和 Go。
- **语义**（大小写敏感性、空值的处理与排序、日期与时区、确定性
  分页）是规范性的，并由一套共享的、与语言无关的一致性测试用例套件强制执行。
- CSV/TSV 流式导出共用同一个仅编译的输入模型。

TRD 的 §2.2（非目标）和 §14（路线图）说明了哪些内容明确不属于 v1 的范围。

## 仓库布局（规划中） {#repository-layout-planned}

```
spec/         IR JSON Schema, semantics.md, conformance fixtures — the source of truth
csharp/       reference implementation (Core, AgGrid adapter, compilers, execution adapters)
typescript/   TypeScript port (after spec freeze)
python/       Python port (after spec freeze)
go/           Go port (after spec freeze)
docs/adr/     architecture decision records (why the design is the way it is)
examples/     demo app (React + AG Grid + one sample backend)
```

## 打包 {#packaging}

C# 实现被拆分为十个 NuGet 包，全部发布在 nuget.org 上：

[![NuGet](https://img.shields.io/nuget/v/Craticula.Core?label=nuget)](https://www.nuget.org/packages/Craticula.Core)

[`Craticula.Core`](https://www.nuget.org/packages/Craticula.Core)、
[`Craticula.AgGrid`](https://www.nuget.org/packages/Craticula.AgGrid)、
[`Craticula.Sql`](https://www.nuget.org/packages/Craticula.Sql)、
[`Craticula.Mongo`](https://www.nuget.org/packages/Craticula.Mongo)、
[`Craticula.Search`](https://www.nuget.org/packages/Craticula.Search)、
[`Craticula.Export.Csv`](https://www.nuget.org/packages/Craticula.Export.Csv)、
[`Craticula.EntityFrameworkCore`](https://www.nuget.org/packages/Craticula.EntityFrameworkCore)、
[`Craticula.Dapper`](https://www.nuget.org/packages/Craticula.Dapper)、
[`Craticula.MongoDB.Driver`](https://www.nuget.org/packages/Craticula.MongoDB.Driver) 和
[`Craticula.OpenSearch.Client`](https://www.nuget.org/packages/Craticula.OpenSearch.Client)。
使用 `dotnet add package <name>` 安装其中任意一个。要检查这些包能否构建，以及一个干净的使用方项目能否针对它们编译，请运行
`bash scripts/pack-smoke.sh`（需要 Python 3.10+ 和 .NET 10 SDK；大约 3 分钟）。

## Claude 技能 {#claude-skill}

Claude 技能（skill）会引导你从零开始，直到编译出第一个网格请求，并让 Claude 拒绝那些不安全的捷径。将它作为 Claude Code 插件安装：

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

或者将文件夹 [`skills/craticula`](skills/craticula/SKILL.md) 复制到 `~/.claude/skills/craticula/`。该技能就是文本：Claude 的行为无法得到保证。参见 [Claude 技能页面](https://craticula.pluries.dev/claude-skill.html)。

## 依赖项许可证 {#dependency-licenses}

`csharp/` 下的每个 NuGet 包，包括传递依赖和测试项目，都必须带有本项目接受的许可证。
`python3 scripts/check-licenses.py` 会对此进行检查（需要 Python 3.10+、.NET 10 SDK 和 nuget.org；请先在 `csharp/` 中用
`dotnet restore Craticula.sln` 还原解决方案，再在同一目录用 `dotnet tool restore` 还原固定版本的工具）。同一个脚本会在每个 pull request 的
`license-check` 作业中运行，在包缓存已预热的情况下只需几秒钟。

- **允许：** MIT、Apache-2.0、BSD-2-Clause、BSD-3-Clause、ISC、0BSD、Unlicense、PostgreSQL、Zlib
  （[`scripts/license-allowlist.json`](scripts/license-allowlist.json)）。
- **拒绝：** GPL、LGPL、AGPL、SSPL、BUSL、Elastic、Commons Clause 以及任何非商业许可证。失败信息会指明
  包名、版本、许可证和项目。
- **MPL-2.0：** 仅当 `docs/adr/` 中有一份已接受的 ADR（含 `Status: Accepted` 一行）点名 MPL-2.0 和该包时才允许。
  该检查按设计采取默认拒绝：没有这样的 ADR，MPL-2.0 包就会被拒绝。
- **覆盖项：** 当工具无法读取许可证（给出的是许可证文件或一个裸 URL，而不是 SPDX 标识符）时，请在
  [`scripts/license-overrides.json`](scripts/license-overrides.json) 中添加一条记录，写明包、其确切版本、真实的许可证以及一份
  书面理由。该许可证必须是允许的 SPDX 标识符（或者对供应商自有的非 SPDX 条款使用 `"vendor_terms": true`）。覆盖项
  绝不会解除工具读出为被拒绝或 MPL-2.0 的许可证。没有理由的记录会导致检查失败，不再对应
  任何包的记录同样会失败。
- **陷阱：** `MySql.Data`（GPL）按名称被拒绝：请使用 `MySqlConnector`。Oracle 驱动 `Oracle.ManagedDataAccess.Core` 和
  `Testcontainers.Oracle` 只在 `csharp/tests` 下的测试项目中被接受，绝不允许出现在 `csharp/src` 下的任何包中。

## 演示 {#demo}

在线试用：[PostgreSQL](https://craticula-pg.pluries.dev) 和 [MongoDB](https://craticula-mongo.pluries.dev)。两者通过同一个 AG Grid 页面展示相同的
合成订单数据；它们是只读的，并且有速率限制。

[`examples/demo`](examples/demo/README.md) 是它们背后的应用：一个 AG Grid 页面，通过基于本库构建的 C# API，从 PostgreSQL 或
MongoDB 读取相同的订单。要自己运行它，需要 Docker、.NET 10 SDK 和 Node 20.19 或更新版本。它是一个
展示项目，像本库的普通用户一样，从 nuget.org 安装已发布的包。

## 兼容性 {#compatibility}

| 规范版本 | .NET 目标 |
|---|---|
| 0.3.0 | net10.0 |

规范版本即 [`spec/VERSION`](spec/VERSION) 中的版本；每个包都在自己的 README 中注明它。
版本如何选定，见 [VERSIONING.md](VERSIONING.md)。
这些包为其封装的库声明版本范围，绝不声明某个确切的单一版本。

## 许可证 {#license}

Apache License 2.0——参见 [LICENSE](LICENSE)。
