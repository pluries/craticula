using System.Globalization;
using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Export;
using Craticula.Core.Schema;
using Craticula.Export.Csv;

namespace Craticula.Conformance.Driver;

/// <summary>
/// Answers a writer request (<c>conformance-runner.md</c> §2.2): resolves the output columns from the schema and the
/// export request exactly as a host would (EXP-1(b)), decodes the row stream into the CLR values an execution adapter
/// would yield, writes it with the CSV/TSV writer under the host's configuration, and returns the bytes.
///
/// <para>A copy of what <c>Craticula.Export.Csv.Tests.WriterFixture</c> does for the unit suite, kept here rather than
/// shared for the reason <see cref="RequestCompiler"/> gives: that helper is internal to its test assembly. The runner
/// and the xUnit suite grade both against the same expected bytes, so drift cannot hide.</para>
/// </summary>
internal static class WriterRequest
{
    public static byte[] Write(string schemaJson, string agGridRequestJson, JsonElement rowStream, JsonElement? writerConfig)
    {
        var schema = GridSchema.Parse(schemaJson);
        var export = AgGridRequestParser.Parse(agGridRequestJson, new AgGridParseOptions { Schema = schema }).Export
            ?? throw new InvalidOperationException("A writer request must carry an export request (exportFormat, EXP-1).");

        var options = Options(export.Format, writerConfig);
        var rows = Rows(rowStream, schema, export);

        using var bytes = new MemoryStream();
        CsvWriter.Write(rows, export.Columns, options, bytes);
        return bytes.ToArray();
    }

    private static CsvWriterOptions Options(ExportFormat format, JsonElement? config)
    {
        var options = CsvWriterOptions.ForFormat(format);
        if (config is not { } root)
        {
            return options;
        }

        if (root.TryGetProperty("delimiter", out var delimiter))
        {
            options = options with { Delimiter = Single(delimiter, "delimiter") };
        }

        if (root.TryGetProperty("decimalSeparator", out var decimalSeparator))
        {
            options = options with { DecimalSeparator = Single(decimalSeparator, "decimalSeparator") };
        }

        if (root.TryGetProperty("bom", out var bom))
        {
            options = options with { WriteByteOrderMark = bom.GetBoolean() };
        }

        if (root.TryGetProperty("headerRow", out var headerRow))
        {
            options = options with { IncludeHeaderRow = headerRow.GetBoolean() };
        }

        return options;
    }

    private static List<ExportRow> Rows(JsonElement rowStream, GridSchema schema, ExportSpec export)
    {
        var rows = new List<ExportRow>();
        foreach (var element in rowStream.GetProperty("rows").EnumerateArray())
        {
            var cells = new Dictionary<string, object?>(StringComparer.Ordinal);
            foreach (var colId in export.Columns.Select(column => column.ColId))
            {
                cells[colId] = element.TryGetProperty(colId, out var value)
                    ? Decode(value, schema.Fields[colId].Type, colId)
                    : null;
            }

            rows.Add(ExportRow.FromCells(cells, export.Columns));
        }

        return rows;
    }

    private static object? Decode(JsonElement value, FieldType type, string colId) => value.ValueKind switch
    {
        JsonValueKind.Null => null,
        _ => type switch
        {
            FieldType.String => value.GetString(),
            FieldType.Int64 => value.GetInt64(),
            FieldType.Double => value.GetDouble(),
            FieldType.Boolean => value.GetBoolean(),

            // A decimal, a date and a datetime are JSON strings in a row stream (row-stream.schema.json): a JSON
            // number would let the parser pick the scale of "1234.50" before the writer sees it.
            FieldType.Decimal => decimal.Parse(RequireString(value, colId), CultureInfo.InvariantCulture),
            FieldType.Date => DateOnly.ParseExact(RequireString(value, colId), "yyyy-MM-dd", CultureInfo.InvariantCulture),
            FieldType.Datetime => DateTimeOffset.Parse(
                RequireString(value, colId), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind),
            _ => throw new InvalidOperationException($"No row-stream decoding defined for field type {type}.")
        }
    };

    private static string RequireString(JsonElement value, string colId) =>
        value.ValueKind == JsonValueKind.String
            ? value.GetString()!
            : throw new InvalidOperationException($"Cell '{colId}' must be a JSON string, not {value.ValueKind}.");

    private static char Single(JsonElement value, string property) =>
        value.GetString() is { Length: 1 } text
            ? text[0]
            : throw new InvalidOperationException($"writerConfig.json's '{property}' must be exactly one character.");
}
