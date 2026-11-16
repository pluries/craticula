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
    FilterNode? Filter);

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
        var filter = Filter(parsed, schema, limits);

        return new StageInputs(shape.SchemaJson, shape.RequestJson, schema, options, limits, parsed, filter);
    }

    public static object Run(StageInputs inputs, string stage) => stage switch
    {
        "parse-schema" => GridSchema.Parse(inputs.SchemaJson),
        "parse-request" => AgGridRequestParser.Parse(inputs.RequestJson, inputs.Options),
        "filter-pipeline" => Filter(inputs.Parsed, inputs.Schema, inputs.Limits)!,
        "build-query" => Build(inputs.Schema, inputs.Parsed, inputs.Filter),
        _ => throw new ArgumentException($"Unknown stage '{stage}'. Available stages: {string.Join(", ", Names)}.", nameof(stage))
    };

    /// <summary>All four stages in order from the raw texts, as a compile from JSON does.</summary>
    public static object RunAll(StageInputs inputs)
    {
        var schema = GridSchema.Parse(inputs.SchemaJson);
        var parsed = AgGridRequestParser.Parse(inputs.RequestJson, OptionsFor(schema));
        var filter = Filter(parsed, schema, inputs.Limits);

        return Build(schema, parsed, filter);
    }

    private static AgGridParseOptions OptionsFor(GridSchema schema) =>
        new() { Schema = schema, Clock = TimeProvider.System, DefaultPageSize = 100, AllowUnboundedRows = false };

    private static FilterNode? Filter(AgGridParsedRequest parsed, GridSchema schema, ResourceLimits limits) =>
        GridFilterPipeline.Process(
            parsed.NativeFilter, parsed.CustomFilters, parsed.Page, schema, limits, parsed.Group, parsed.Aggregations);

    private static SqlQuery Build(GridSchema schema, AgGridParsedRequest parsed, FilterNode? filter) =>
        SqlQueryBuilder.Build(
            new SqlQueryRequest
            {
                Schema = schema,
                Filter = filter,
                Sort = parsed.Sort,
                Page = parsed.Page,
                Group = parsed.Group,
                Aggregations = parsed.Aggregations,
                Projection = parsed.Export?.ProjectionColumns
            },
            PostgresDialect.Instance);
}
