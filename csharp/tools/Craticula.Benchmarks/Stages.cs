using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Sql;

namespace Craticula.Benchmarks;

/// <summary>Everything a stage needs, built once, so each stage can be timed alone: the raw texts and the output of each earlier stage.</summary>
internal sealed record StageInputs(
    string SchemaJson,
    string RequestJson,
    GridSchema Schema,
    AgGridParseOptions Options,
    ResourceLimits Limits,
    AgGridParsedRequest Parsed,
    FilterNode? Filter,
    bool CountMode);

/// <summary>The row-fetch compile for PostgreSQL split into its four stages (the same calls as <c>RequestCompiler</c>): the schema from JSON, the request from JSON, the filter pipeline, the query builder. A host builds its schema once; the first stage is what a per-request compile from raw JSON adds.</summary>
internal static class Stages
{
    public static readonly IReadOnlyList<string> Names = ["parse-schema", "parse-request", "filter-pipeline", "build-query"];

    public static StageInputs Prepare(LoadedShape shape)
    {
        var schema = GridSchema.Parse(shape.SchemaJson);
        var options = OptionsFor(schema);
        var limits = new ResourceLimits();
        var parsed = AgGridRequestParser.Parse(shape.RequestJson, options);
        var countMode = ReadCountMode(shape.RequestJson);
        var filter = Filter(parsed, schema, limits, countMode);

        return new StageInputs(shape.SchemaJson, shape.RequestJson, schema, options, limits, parsed, filter, countMode);
    }

    public static object Run(StageInputs inputs, string stage) => stage switch
    {
        "parse-schema" => GridSchema.Parse(inputs.SchemaJson),
        "parse-request" => AgGridRequestParser.Parse(inputs.RequestJson, inputs.Options),
        "filter-pipeline" => Filter(inputs.Parsed, inputs.Schema, inputs.Limits, inputs.CountMode)!,
        "build-query" => Build(inputs.Schema, inputs.Parsed, inputs.Filter, inputs.CountMode),
        _ => throw new ArgumentException($"Unknown stage '{stage}'. Available stages: {string.Join(", ", Names)}.", nameof(stage))
    };

    /// <summary>All four stages in order from the raw texts, as a compile from JSON does.</summary>
    public static object RunAll(StageInputs inputs)
    {
        var schema = GridSchema.Parse(inputs.SchemaJson);
        var parsed = AgGridRequestParser.Parse(inputs.RequestJson, OptionsFor(schema));
        var filter = Filter(parsed, schema, inputs.Limits, inputs.CountMode);

        return Build(schema, parsed, filter, inputs.CountMode);
    }

    private static AgGridParseOptions OptionsFor(GridSchema schema) =>
        new() { Schema = schema, Clock = TimeProvider.System, DefaultPageSize = 100, AllowUnboundedRows = false };

    // CNT-3: the page-size check runs inside the pipeline, so a count is processed with the unpaginated page.
    private static FilterNode? Filter(AgGridParsedRequest parsed, GridSchema schema, ResourceLimits limits, bool countMode) =>
        GridFilterPipeline.Process(
            parsed.NativeFilter, parsed.CustomFilters, countMode ? new NonePage() : parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);

    private static SqlQuery Build(GridSchema schema, AgGridParsedRequest parsed, FilterNode? filter, bool countMode)
    {
        var request = new SqlQueryRequest
        {
            Schema = schema,
            Filter = filter,
            Sort = parsed.Sort,
            Page = parsed.Page,
            Group = parsed.Group,
            Aggregations = parsed.Aggregations,
            Projection = parsed.Export?.ProjectionColumns
        };

        return countMode ? SqlQueryBuilder.BuildCount(request, PostgresDialect.Instance) : SqlQueryBuilder.Build(request, PostgresDialect.Instance);
    }

    /// <summary>CNT-8's harness instruction, read as the conformance driver reads it: <c>requestContext.compileMode</c> "count" selects count mode, absent means the page, any other value is refused.</summary>
    private static bool ReadCountMode(string requestJson)
    {
        using var document = JsonDocument.Parse(requestJson);
        var root = document.RootElement;

        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("requestContext", out var context)
            || context.ValueKind != JsonValueKind.Object
            || !context.TryGetProperty("compileMode", out var mode))
        {
            return false;
        }

        if (mode.ValueKind == JsonValueKind.String && mode.GetString() == "count")
        {
            return true;
        }

        throw new ArgumentException("requestContext.compileMode is not recognised; the only value is \"count\" (CNT-8).");
    }
}
