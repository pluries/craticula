---
translates: csv-export
title: CSV 导出
description: 使用同一套请求模型和同样的检查，把表格的行以流的方式导出为 CSV。
source_fingerprint: fa1523a098455aba885855279c19504be3084b49be415b2a066c79e11c573ace
drafter: claude
drafted_on: 2026-11-19
status: machine-drafted
---
# CSV 导出 {#csv-export}

本页说明 Craticula 如何把表格中显示的行导出为 CSV 或 TSV 文件：哪一部分由 Craticula 负责，哪一部分由你负责，以及哪些设置会改变文件内容。本页面向为基于 Craticula 的表格添加导出按钮的开发者。

## 两个部分，中间一条流 {#two-parts-one-stream-between-them}

导出分为两步，由 Craticula 的两个组件分别完成。

1. **读取行。** 执行适配器运行查询，并返回一条行流。`DapperExportStream`、`EfCoreExportStream`、`MongoExportStream` 和 `OpenSearchExportStream` 分别为各自的后端完成这项工作。参见 [Entity Framework Core 与 Dapper](relational-adapters.html) 和 [MongoDB 与 OpenSearch 适配器](search-adapters.html)。
2. **写入文件。** 软件包 `Craticula.Export.Csv` 接收这条流并写出字节。它对数据库一无所知。`CsvWriter` 是它的入口。

由于写入器一次只读取一行，并在读取的同时写出每条记录，导出一百万行所用的内存与导出十行大致相同。关系型适配器和 OpenSearch 适配器按块读取行（默认每块 5,000 行）；MongoDB 适配器则按批次逐批读取同一个游标，绝不使用不断增长的偏移量；分页的 `FetchPageAsync` 调用会拒绝“全部行”的请求，因此只有导出流才能读取完整结果。下载变慢时，读取随之变慢，而不会占满内存。

## 表格发送的内容 {#what-the-grid-sends}

导出请求就是一个普通的表格请求，外加最多三个成员：

- `exportFormat`，取值为 `"csv"` 或 `"tsv"`。它把请求标记为导出。只发送另外两个成员而不发送它，请求会被拒绝。
- `exportScope`，取值为 `"all"` 或 `"page"`。默认值为 `"all"`：导出所有符合过滤和排序条件的行，不论 `startRow` 和 `endRow` 是多少。`"page"` 则保留请求的行范围。既不发送窗口、又不是导出的请求，会得到一个 100 行的默认页；参见 [分页与排序](paging-and-sorting.html)。
- `exportColumns`，一个可选列表，其条目形如 `{ "colId": "...", "header": "..." }`。

过滤和排序始终生效。

## 导出哪些列，表头写什么 {#which-columns-and-what-the-headers-say}

如果请求没有 `exportColumns`，导出的就是 schema 中标记为 `exportable` 的所有列，顺序与 schema 声明的顺序一致。除非 schema 写明 `"exportable": false`，否则列都是可导出的。

如果请求带有 `exportColumns`，导出的就是这些列，并按该顺序排列。列不在 schema 中、不可导出、被列出两次，或者列表为空，请求都会被拒绝。无论在 Strict 模式还是 Lenient 模式下都是如此。

某一列的表头按以下顺序取值：

1. 请求中的 `header`；
2. schema 中的 `label`；
3. 列 id。

解析器只计算一次，并把结果放入 `ExportSpec.Columns`。

## 分组会被丢弃 {#grouping-is-dropped}

导出是一份扁平的行列表。适配器会从导出请求中丢弃 `rowGroupCols`、`valueCols` 和 `groupKeys`，因此对分组表格的导出，返回的是当前过滤和排序下的普通行。

## 组合起来 {#putting-it-together}

解析器需要 schema 才能解析导出请求，因此请通过 `AgGridParseOptions` 传入它。这段示例处理 `exportScope` 为 `"all"` 的情况。对于 `"page"`，`parsed.Page` 是一个行范围，`StreamAsync` 会拒绝它。示例使用 Dapper 和 PostgreSQL。`connection` 是一个已打开的 `IDbConnection`，`destination` 是一个 `Stream`，例如 HTTP 响应体。

```csharp
// using Craticula.AgGrid; using Craticula.Core.Export; using Craticula.Core.Ir;
// using Craticula.Core.Schema; using Craticula.Dapper; using Craticula.Export.Csv; using Craticula.Sql;
AgGridParsedRequest parsed = AgGridRequestParser.Parse(requestJson, new AgGridParseOptions { Schema = schema });
ExportSpec export = parsed.Export!;

FilterNode? filter = GridFilterPipeline.Process(
    parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, new ResourceLimits());

IAsyncEnumerable<ExportRow> rows = DapperExportStream.StreamAsync(
    connection,
    new SqlQueryRequest
    {
        Schema = schema,
        Filter = filter,
        Sort = parsed.Sort,
        Page = parsed.Page,
        Projection = export.ProjectionColumns
    },
    PostgresDialect.Instance);

long rowsWritten = await CsvWriter.WriteAsync(
    rows, export.Columns, CsvWriterOptions.ForFormat(export.Format), destination);
```

`CsvWriterOptions.ForFormat` 是把所请求的格式传递到文件的途径。它为 CSV 选用逗号，为 TSV 选用制表符。写入器从不接触请求本身，因此无法自行完成这一步。任务的结果是写入的数据行数，不包括表头行。

适配器的导出流只接受完整结果（`exportScope` 为 `"all"`）。按页导出是一个有界的块，与表格块运行的查询相同。请用适配器的分页方法获取它，再自行写出这些行。

## 文件的样子 {#what-the-file-looks-like}

默认情况下：

- 表头行排在最前面；
- 字段以逗号分隔，每行以回车符加换行符结束；
- 含有分隔符、双引号或换行的字段，会用双引号括起来；
- 文件以字节顺序标记开头，因为 Excel 在没有该标记时会误读 Unicode 文本；
- null 是一个空字段；
- 布尔值写作 `true` 和 `false`；
- 日期写作 `2026-01-05`，日期时间值写作 `2026-01-05T14:30:45`，值带有偏移量时一并写出；
- decimal 保留其自身小数点后的位数。

## 可以更改的内容 {#what-you-can-change}

`CsvWriterOptions` 有以下设置：

| 设置 | 默认值 | 作用 |
|---|---|---|
| `Delimiter` | `,` | 字段分隔符。 |
| `IncludeHeaderRow` | `true` | 是否写入表头行。 |
| `WriteByteOrderMark` | `true` | 是否以字节顺序标记开头。 |
| `DecimalSeparator` | `.` | 小数中的分隔符。 |
| `HardenFormulaInjection` | `true` | 见下文。 |

`CsvWriterOptions.SemicolonPreset` 会把分隔符设为分号，适用于 Excel 期望使用分号的区域设置。

schema 可以通过 `format` 块覆盖单个列的格式：

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

写入器会拒绝与分隔符相同的小数分隔符。两处都用逗号，会把每个小数都变成带引号的文本。它也会拒绝无法应用的日期格式。`GridSchema.Parse` 在加载 schema 时就会检查该格式，因此错误的格式会在启动时失败，而不是在下载进行到一半时才失败。

## 防范电子表格公式 {#protection-against-spreadsheet-formulas}

电子表格会把以 `=`、`+`、`-`、`@`、制表符或回车符开头的单元格当作公式。这样，用户输入的值就可能在打开导出文件的人的电子表格中运行。

默认情况下，写入器会在这类文本前加一个撇号。这适用于每个表头和每个文本单元格。它不会改动由写入器自己格式化的数字、日期或布尔值，因此负数仍然是数字。

可以用 `HardenFormulaInjection = false` 将其关闭。撇号之后无法再去掉，所以只有在文件由程序读取、没有人会用电子表格打开它时，才应关闭。

## 由你负责的部分 {#what-stays-with-you}

- **行数上限。** 适配器和写入器都不会对导出的最大行数做限制。如果导出对外公开，请自行添加限制。
- **页大小限制。** 它不适用于导出完整结果（`exportScope` 为 `"all"`），因为这种导出没有页。按页导出保留其行范围，页大小限制对其生效。参见 [限制](limits.html)。
- **Dapper 会拒绝某些导出。** `DapperExportStream` 会拒绝稳定键是文本列的 schema，也会拒绝这样的导出：被导出的行中，某个文本排序键含有空字符串（除 Oracle 外的所有方言）。请使用数值或日期类型的稳定键，或者用 `DapperGridQuery.FetchPageAsync` 逐页获取数据。`EfCoreExportStream` 没有这种检查。
- **下载。** 内容类型、文件名和连接由你负责。演示程序在 `examples/demo/Api/Routes/GridRoutes.cs` 中设置了它们。
- **OpenSearch 的列列表。** OpenSearch 导出始终写出 schema 的每一列，顺序为 `schema.FieldOrder` 的顺序。请向 `CsvWriter` 传入完整列表，即 `schema.FieldOrder` 中每个字段对应一个 `ExportColumn`。较窄的 `export.Columns` 会使 `CsvWriter` 因单元格数量不匹配而以 `CsvWriterException` 失败。

## 本页的依据 {#where-this-comes-from}

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- 相关页面：[分页与排序](paging-and-sorting.html)、[GridSchema](the-gridschema.html)、[安全模型](safety-model.html)
