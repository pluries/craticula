---
translates: quickstart-csharp
title: C#
description: 用 C# 把网格请求编译为 SQL 和 MongoDB 查询。
source_fingerprint: b1a5412bec8769ab8737adfd5828f36a3502b6b49ca68c2ba7f883125d5e6756
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# 快速入门：C# {#quickstart-c}

本页用一个小程序，带你从一个 AG Grid 请求走到回答它的参数化 SQL。它既不需要数据库，也不需要驱动程序：Craticula 只编译请求，绝不执行它。

软件包发布在 NuGet 上。本页用到其中三个：

```
dotnet add package Craticula.Core
dotnet add package Craticula.AgGrid
dotnet add package Craticula.Sql
```

每个软件包在 nuget.org 上都有自己的页面，例如 [Craticula.Core](https://www.nuget.org/packages/Craticula.Core)。下面的程序同样位于代码仓库中，由解决方案负责编译；因此本页是通过从那里运行它来验证的。

## 你需要什么 {#what-you-need}

- .NET 10 SDK；
- 代码仓库，用于原样运行这个示例：克隆或下载 <https://github.com/pluries/craticula>。若要在自己的项目中使用该库，请改为安装上面的软件包。

## 运行它 {#run-it}

在仓库的 `csharp` 文件夹中：

```
dotnet run --project samples/Craticula.Quickstart
```

程序就是下面这个文件。解决方案会编译它：因此，任何破坏它的库改动都会使构建失败。它做五件事：声明一个 schema（允许列表），取一个 AG Grid 请求，把它解析为规范 IR，为两种数据库分别编译，最后展示一个涉及未声明列的请求如何被拒绝。

````csharp
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Sql;

// 1. The schema is the allowlist: a column that is not listed here can never reach a query, and every identifier in the
//    statement comes from `physical.sql.column`, never from the request.
const string schemaJson = """
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
    """;

// 2. A request exactly as AG Grid's server-side row model sends it: customers containing "acme", amount above 100,
//    biggest amounts first, the first 50 rows.
const string requestJson = """
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
    """;

GridSchema schema = GridSchema.Parse(schemaJson);

// 3. Parse the request into the canonical IR, then validate it against the schema and the resource limits.
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits(), parsed.Group, parsed.Aggregations);

// 4. Compile: the same IR gives each database its own statement. Values travel as parameters, never inside the text.
foreach ((string name, ISqlDialect dialect) in new (string, ISqlDialect)[]
         {
             ("PostgreSQL", PostgresDialect.Instance),
             ("SQL Server", MssqlDialect.Instance),
         })
{
    SqlQuery query = SqlQueryBuilder.Build(
        new SqlQueryRequest { Schema = schema, Filter = filter, Sort = parsed.Sort, Page = parsed.Page }, dialect);

    Console.WriteLine($"-- {name}");
    Console.WriteLine(query.Sql);
    Console.WriteLine($"-- parameters: {string.Join(", ", query.Parameters.Select(value => value is string text ? $"'{text}'" : value?.ToString() ?? "NULL"))}");
    Console.WriteLine();
}

// 5. A column the schema does not list is refused before any query exists. Here the grid asks to filter on `password`.
const string hostileJson = """
    { "startRow": 0, "endRow": 50, "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
      "filterModel": { "password": { "filterType": "text", "type": "equals", "filter": "x" } }, "sortModel": [] }
    """;

try
{
    AgGridParsedRequest bad = AgGridRequestParser.Parse(hostileJson, new AgGridParseOptions { Schema = schema });
    GridFilterPipeline.Process(bad.NativeFilter, bad.CustomFilters, bad.Page, schema, new ResourceLimits(), bad.Group, bad.Aggregations);
    Console.WriteLine("-- the unknown column was NOT refused");
}
catch (UnknownFieldException error)
{
    Console.WriteLine($"-- refused: {error.GetType().Name}: {error.Message}");
}
````

## 你应该看到什么 {#what-you-should-see}

同一个请求会为每种数据库生成各自的语句。值绝不会成为语句文本的一部分：它们是列在每条语句下面的参数，顺序与占位符出现的顺序一致。最后一行展示了对 schema 中不存在的那一列的拒绝。

````text
-- PostgreSQL
SELECT * FROM "orders" WHERE ("customer" ILIKE '%' || $1 || '%' ESCAPE '\' AND "amount" > $2::numeric) ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST LIMIT $3 OFFSET $4
-- parameters: 'acme', '100', 50, 0

-- SQL Server
SELECT * FROM [orders] WHERE ([customer] COLLATE Latin1_General_CI_AS LIKE '%' + @p1 + '%' ESCAPE '\' AND [amount] > @p2) ORDER BY CASE WHEN [amount] IS NULL THEN 1 ELSE 0 END DESC, [amount] DESC, CASE WHEN [id] IS NULL THEN 1 ELSE 0 END ASC, [id] ASC OFFSET @p3 ROWS FETCH NEXT @p4 ROWS ONLY
-- parameters: 'acme', '100', 0, 50

-- refused: UnknownFieldException: Field allowlist check failed (SC-1/SC-2) for 1 colId(s): password
````

## 读懂输出 {#read-the-output}

- `ILIKE` 和 `COLLATE Latin1_General_CI_AS` 是各数据库书写默认的不区分大小写比较的方式（[Case sensitivity](semantics.html#sem-1)）；两条语句返回的行是一致的。
- `ORDER BY "amount" DESC NULLS FIRST, "id" ASC NULLS LAST` 以 `id`（schema 的稳定键）结尾，因此分页是确定的（[Deterministic paging](semantics.html#sem-6)）。SQL Server 没有 `NULLS FIRST`，所以它在前面加一个 `CASE`，写出同样的顺序（[Null ordering](semantics.html#sem-3)）。
- 十进制数 `100` 显示为 `'100'`，因为十进制参数以字符串形式传输，这样在传到驱动程序的途中不会损失精度（AR-7）。请在你的驱动程序中把它绑定为十进制数。
- `"password"` 被拒绝，是因为 schema 中没有列出这样的列；该请求从未到达任何编译器。

## 在真实数据库上运行 {#run-it-on-a-real-database}

使用执行适配器，可以在一次调用中完成编译和执行；它接收你提供的已打开连接或 `DbContext`。请从 NuGet 安装你需要的适配器（`Craticula.Dapper`、`Craticula.EntityFrameworkCore`、`Craticula.MongoDB.Driver` 或 `Craticula.OpenSearch.Client`）；每个适配器的 README 都给出了它的安装命令。

- [`Craticula.Dapper`](../../csharp/src/Craticula.Dapper/README.md)：在 `IDbConnection` 上执行语句，支持分页、行计数和流式 CSV 导出。
- [`Craticula.EntityFrameworkCore`](../../csharp/src/Craticula.EntityFrameworkCore/README.md)：构建 `IQueryable` 表达式树；请先阅读它对宿主提出的两项要求。
- MongoDB 和 OpenSearch 有各自的编译器和客户端（`Craticula.Mongo`、`Craticula.MongoDB.Driver`、`Craticula.Search`、`Craticula.OpenSearch.Client`）。

若想看包含浏览器中网格、七种数据库引擎上十个提供程序，以及一个让它们相互比对的脚本的完整流程，请跟着[演示](../../examples/demo/README.md)走一遍，或者在线试用 [PostgreSQL](https://craticula-pg.pluries.dev) 版和 [MongoDB](https://craticula-mongo.pluries.dev) 版。

## 下一步 {#next}

- 各数据库需要你做哪些准备，语句才能返回正确结果：[索引与数据库指南](index-guidance.html)。
- 输出背后的规则：[语义](semantics.html)。
- schema 的每一项设置：[GridSchema 参考](grid-schema.html)。
