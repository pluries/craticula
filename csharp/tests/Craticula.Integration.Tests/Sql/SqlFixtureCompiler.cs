using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Integration.Tests.Oracle;
using Craticula.Sql;

namespace Craticula.Integration.Tests.Containers.Sql;

/// <summary>
/// Turns a fixture's own <c>agGridRequest.json</c> into the compiled <see cref="SqlQuery"/> an engine runs,
/// through the real pipeline with nothing stubbed (parser, <see cref="GridFilterPipeline"/>, SEC-3's default
/// <see cref="ResourceLimits"/>, <see cref="SqlQueryBuilder"/>). Dispatches on the request document like a host
/// endpoint: a <c>setValuesRequest</c> envelope is BM-3's distinct-values query, anything else a row fetch
/// (ordinary, grouped, drill-down leaf or export projection). Mirrors <c>Craticula.Sql.Tests.FixtureCompiler</c>,
/// which is internal to its own assembly.
/// </summary>
internal static class SqlFixtureCompiler
{
    public static SqlQuery Compile(ExecutionFixture fixture, ISqlDialect dialect) =>
        Compile(File.ReadAllText(Path.Combine(fixture.Directory, "agGridRequest.json")), fixture.Schema, dialect);

    /// <summary>The same pipeline for a request that is text rather than a fixture file (the parity property's generated cases).</summary>
    public static SqlQuery Compile(string requestJson, GridSchema schema, ISqlDialect dialect)
    {
        var options = new AgGridParseOptions { Schema = schema, Clock = ClockFor(requestJson), AllowUnboundedRows = HarnessFlag(requestJson, "allowUnboundedRows") };

        return IsSetValuesRequest(requestJson)
            ? CompileSetValues(requestJson, options, schema, dialect)
            : CompileRowFetch(requestJson, options, schema, dialect);
    }

    private static SqlQuery CompileRowFetch(string requestJson, AgGridParseOptions options, GridSchema schema, ISqlDialect dialect)
    {
        var parsed = AgGridRequestParser.Parse(requestJson, options);
        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            parsed.Page,
            schema,
            new ResourceLimits(),
            parsed.Group,
            parsed.Aggregations);

        return SqlQueryBuilder.Build(
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
            dialect);
    }

    /// <summary>A row fetch (ordinary, grouped or drill-down leaf), as opposed to BM-3's distinct-values request, which has no count.</summary>
    public static bool IsRowFetch(ExecutionFixture fixture) =>
        !IsSetValuesRequest(File.ReadAllText(Path.Combine(fixture.Directory, "agGridRequest.json")));

    /// <summary>The fixture's row fetch with no window at all (EXP-2's unpaginated page): every row the request matches, or every group of a grouped level.</summary>
    public static SqlQuery CompileUnpaged(ExecutionFixture fixture, ISqlDialect dialect) => CompileUnpagedOrCount(fixture, dialect, count: false);

    /// <summary>The fixture's request in count mode (CNT-1..CNT-5): the pipeline gets the unpaginated page, as CNT-3 requires of a host.</summary>
    public static SqlQuery CompileCount(ExecutionFixture fixture, ISqlDialect dialect) => CompileUnpagedOrCount(fixture, dialect, count: true);

    private static SqlQuery CompileUnpagedOrCount(ExecutionFixture fixture, ISqlDialect dialect, bool count)
    {
        var requestJson = File.ReadAllText(Path.Combine(fixture.Directory, "agGridRequest.json"));
        var schema = fixture.Schema;
        var parsed = AgGridRequestParser.Parse(
            requestJson,
            new AgGridParseOptions { Schema = schema, Clock = ClockFor(requestJson), AllowUnboundedRows = HarnessFlag(requestJson, "allowUnboundedRows") });
        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter, parsed.CustomFilters, new NonePage(), schema, new ResourceLimits(), parsed.Group, parsed.Aggregations);
        var request = new SqlQueryRequest
        {
            Schema = schema,
            Filter = filter,
            Sort = parsed.Sort,
            Page = new NonePage(),
            Group = parsed.Group,
            Aggregations = parsed.Aggregations,
            Projection = parsed.Export?.ProjectionColumns
        };

        return count ? SqlQueryBuilder.BuildCount(request, dialect) : SqlQueryBuilder.Build(request, dialect);
    }

    private static SqlQuery CompileSetValues(string requestJson, AgGridParseOptions options, GridSchema schema, ISqlDialect dialect)
    {
        var limits = new ResourceLimits();
        var parsed = AgGridRequestParser.ParseSetValues(requestJson, options);
        var filter = GridFilterPipeline.ProcessSetValues(parsed.NativeFilter, parsed.CustomFilters, parsed.SetValues, schema, limits);

        return SqlQueryBuilder.BuildSetValues(
            new SqlSetValuesRequest
            {
                Schema = schema,
                ColId = parsed.SetValues.ColId,
                Filter = filter,
                RowLimit = ResourceLimitsValidator.ResolveSetValuesLimit(parsed.SetValues.Limit, limits)
            },
            dialect);
    }

    // requestContext.allowUnboundedRows is the harness's switch for ignorePageLimit (conformance-runner.md section 3), not a wire field.
    private static bool HarnessFlag(string requestJson, string member)
    {
        using var document = JsonDocument.Parse(requestJson);
        return document.RootElement.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty(member, out var value)
            && value.ValueKind == JsonValueKind.True;
    }

    private static bool IsSetValuesRequest(string requestJson)
    {
        using var document = JsonDocument.Parse(requestJson);
        return document.RootElement.ValueKind == JsonValueKind.Object
            && document.RootElement.TryGetProperty("setValuesRequest", out _);
    }

    // A fixture's requestContext.now is an instruction to the harness (AgGridParseOptions.Clock), not a field the
    // parser reads: pin the clock to it so date presets resolve as the fixture's author derived them.
    private static TimeProvider ClockFor(string requestJson)
    {
        using var document = JsonDocument.Parse(requestJson);
        return document.RootElement.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("now", out var now)
            && now.ValueKind == JsonValueKind.String
                ? new PinnedClock(DateTimeOffset.Parse(now.GetString()!, System.Globalization.CultureInfo.InvariantCulture))
                : TimeProvider.System;
    }

    private sealed class PinnedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now.ToUniversalTime();
    }
}
