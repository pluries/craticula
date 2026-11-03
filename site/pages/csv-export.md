# CSV export

This page covers how Craticula exports the rows a grid shows as a CSV or TSV file: which part is Craticula's job, which part is yours, and the settings that change the file. It is for a developer who adds an export button to a Craticula-backed grid.

## Two parts, one stream between them

An export takes two steps, and two pieces of Craticula do them.

1. **Reading the rows.** An execution adapter runs the query and hands back a stream of rows. `DapperExportStream`, `EfCoreExportStream`, `MongoExportStream` and `OpenSearchExportStream` do this for their backends. See [Entity Framework Core and Dapper](relational-adapters.html) and [MongoDB and OpenSearch adapters](search-adapters.html).
2. **Writing the file.** The package `Craticula.Export.Csv` takes that stream and writes the bytes. It knows nothing about the database. `CsvWriter` is its entry point.

Because the writer reads one row at a time and writes each record as it goes, a million-row export uses about the same memory as a ten-row one. A slow download slows the read down instead of filling memory.

## What the grid sends

An export request is an ordinary grid request with up to three more members:

- `exportFormat`, either `"csv"` or `"tsv"`. It marks the request as an export. Sending the other two members without it is refused.
- `exportScope`, either `"all"` or `"page"`. The default is `"all"`: every row that matches the filter and sort, whatever `startRow` and `endRow` say. `"page"` keeps the row range of the request.
- `exportColumns`, an optional list of `{ "colId": "...", "header": "..." }` entries.

The filter and the sort are always honoured.

## Which columns, and what the headers say

If the request has no `exportColumns`, the export has every column the schema marks `exportable`, in the order the schema declares them. A column is exportable unless the schema says `"exportable": false`.

If the request has `exportColumns`, the export has those columns, in that order. A column that is not in the schema, is not exportable, is listed twice, or an empty list is refused. That holds in Strict and in Lenient mode.

The header for a column comes from, in order:

1. the `header` in the request;
2. the `label` in the schema;
3. the column id.

The parser works this out once and puts it in `ExportSpec.Columns`.

## Grouping is dropped

An export is a flat list of rows. The adapter drops `rowGroupCols`, `valueCols` and `groupKeys` from an export request, so an export of a grouped grid returns plain rows under the current filter and sort.

## Putting it together

The parser needs the schema to resolve an export, so pass it in `AgGridParseOptions`. This sketch handles `exportScope` set to `"all"`. For `"page"`, `parsed.Page` is a row range and `StreamAsync` refuses it. It uses Dapper and PostgreSQL. The `connection` is an open `IDbConnection` and `destination` is a `Stream`, such as the HTTP response body.

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

`CsvWriterOptions.ForFormat` is how the requested format reaches the file. It picks a comma for CSV and a tab for TSV. The writer never sees the request, so it cannot do this itself. The task result is the number of data rows written, not counting the header row.

The export streams of the adapters accept only the whole result (`exportScope` set to `"all"`). A page-scoped export is one bounded block, the same query a grid block runs. Fetch it with the adapter's page method and write those rows yourself.

## What the file looks like

By default:

- a header row comes first;
- fields are separated by a comma, and rows end in a carriage return and a line feed;
- a field that holds the delimiter, a double quote or a line break is wrapped in double quotes;
- the file starts with a byte order mark, because Excel misreads Unicode text without one;
- a null is an empty field;
- booleans are `true` and `false`;
- dates are written as `2026-01-05`, and date and time values as `2026-01-05T14:30:45`, with the offset when the value has one;
- a decimal keeps its own number of digits after the point.

## What you can change

`CsvWriterOptions` has these settings:

| Setting | Default | What it does |
|---|---|---|
| `Delimiter` | `,` | The field separator. |
| `IncludeHeaderRow` | `true` | Whether to write the header row. |
| `WriteByteOrderMark` | `true` | Whether to start the file with a byte order mark. |
| `DecimalSeparator` | `.` | The separator in fractional numbers. |
| `HardenFormulaInjection` | `true` | See below. |

`CsvWriterOptions.SemicolonPreset` sets the delimiter to a semicolon, for locales where Excel expects one.

The schema can override the format of a single column with a `format` block:

```json
"orderDate": { "type": "date", "format": { "datePattern": "dd/MM/yyyy" } },
"amount": { "type": "decimal", "format": { "decimalSeparator": "," } }
```

The writer refuses a decimal separator that equals the delimiter. A comma in both places would turn every fractional number into quoted text. It also refuses a date pattern it cannot apply. `GridSchema.Parse` checks the pattern when you load the schema, so a bad one fails at start-up and not halfway through a download.

## Protection against spreadsheet formulas

A spreadsheet treats a cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return as a formula. A value a user typed can then run in the spreadsheet of whoever opens the export.

By default the writer puts an apostrophe in front of such text. This covers every header and every text cell. It does not touch numbers, dates or booleans that the writer formatted itself, so a negative number stays a number.

You can turn it off with `HardenFormulaInjection = false`. The apostrophe cannot be taken away again afterwards, so turn it off only when a program reads the file and no person opens it in a spreadsheet.

## What stays with you

- **The row cap.** Neither the adapters nor the writer enforce a maximum number of exported rows. Add your own limit if the export is public.
- **The page size limit.** It does not apply to an export of the whole result (`exportScope` set to `"all"`), which has no page. A page-scoped export keeps its row range, and the page size limit applies to it. See [Limits](limits.html).
- **Dapper refuses some exports.** `DapperExportStream` refuses a schema whose stable key is a text column, and an export where a text sort key holds an empty string in the exported rows (every dialect except Oracle). Use a numeric or date stable key, or fetch the data page by page with `DapperGridQuery.FetchPageAsync`. `EfCoreExportStream` has no such check.
- **The download.** The content type, the file name and the connection are yours. The demo sets them in `examples/demo/Api/Routes/GridRoutes.cs`.
- **The OpenSearch column list.** The OpenSearch export always writes every schema column, in the order of `schema.FieldOrder`. Pass `CsvWriter` the full list, one `ExportColumn` per field in `schema.FieldOrder`. A narrower `export.Columns` makes `CsvWriter` fail with a `CsvWriterException`, because the cell count does not match.

## Where this comes from

- [csharp/src/Craticula.Export.Csv/README.md](../../csharp/src/Craticula.Export.Csv/README.md)
- [csharp/src/Craticula.Export.Csv/CsvWriter.cs](../../csharp/src/Craticula.Export.Csv/CsvWriter.cs)
- [csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs](../../csharp/src/Craticula.Export.Csv/CsvWriterOptions.cs)
- [csharp/src/Craticula.AgGrid/ExportSpec.cs](../../csharp/src/Craticula.AgGrid/ExportSpec.cs)
- [spec/semantics.md](../../spec/semantics.md)
- [spec/fixtures/page-export](../../spec/fixtures/page-export/README.md)
- [examples/demo/Api/Routes/GridRoutes.cs](../../examples/demo/Api/Routes/GridRoutes.cs)
- Related pages: [Paging and sorting](paging-and-sorting.html), [The GridSchema](the-gridschema.html), [Safety model](safety-model.html)
