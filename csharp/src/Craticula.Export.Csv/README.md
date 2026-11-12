# Craticula.Export.Csv

The CSV and TSV writer of Craticula. It streams the rows of a grid export to a `Stream`, with per-column formats and
protection against spreadsheet formula injection (a text cell that starts with `=`, `+`, `-` or `@` is prefixed
with an apostrophe). It knows nothing about the data backend: any row stream from a Craticula execution adapter works.

## Install

```
dotnet add package Craticula.Export.Csv
```

## Example

```csharp
using Craticula.Core.Export;
using Craticula.Export.Csv;

public static class Example
{
    public static Task<long> Write(
        IAsyncEnumerable<ExportRow> rows, IReadOnlyList<ExportColumn> columns, Stream destination) =>
        CsvWriter.WriteAsync(rows, columns, CsvWriterOptions.Default, destination);
}
```

`rows` comes from an adapter such as `DapperExportStream.StreamAsync`. The task result is the number of rows written.

## Compatibility

Implements Craticula spec version 0.2.0 (the language-neutral semantics and conformance fixtures in the
[repository](https://github.com/pluries/craticula), `spec/`). Targets .NET 10.

## License

Apache-2.0. Source and issues: <https://github.com/pluries/craticula>.
