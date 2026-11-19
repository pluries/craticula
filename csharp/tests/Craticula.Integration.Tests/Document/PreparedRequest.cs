using System.Globalization;
using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>
/// One execution-equality fixture's request, resolved the way a host resolves it (parse, then the filter pipeline,
/// SEC-3's default limits, nothing stubbed) against a schema whose <c>Source</c> the harness may have redirected
/// to a fresh per-fixture collection or index. A <c>setValuesRequest</c> envelope is BM-3's distinct-values query;
/// anything else is a row fetch (ordinary, grouped level, drill-down leaf, or export).
/// </summary>
internal sealed record PreparedRequest(
    GridSchema Schema,
    bool IsSetValues,
    AgGridParsedRequest? Parsed,
    FilterNode? Filter,
    SetValuesSpec? SetValues,
    int RowLimit)
{
    /// <summary>The grouping decision GRP-1 makes, read back from the same IR pieces the compilers use.</summary>
    public GroupingPlan? Plan => IsSetValues ? null : GroupingPlan.Resolve(Parsed!.Group, Parsed.Aggregations);

    /// <summary>The logical column list XEQ-3 compares (see <see cref="ColumnTypes"/>).</summary>
    public IReadOnlyList<string> LogicalColumns()
    {
        if (IsSetValues)
        {
            return [SetValues!.ColId];
        }

        var plan = Plan;
        if (plan is { GroupColumn: { } groupColumn })
        {
            // The aggregate's LOGICAL name is its valueCols id (Aggregation.ColumnId); the engine's own key is OutputName.
            return [groupColumn, .. plan.Aggregations.Select(a => a.ColumnId)];
        }

        // An ordinary row, a drill-down leaf (GRP-3: the schema's fields in declaration order) or an export (its own list).
        return Parsed!.Export?.ProjectionColumns ?? Schema.FieldOrder;
    }

    // A given page replaces the request's own window (FR-007: the count check prepares both queries unpaged); null keeps the request's own.
    public static PreparedRequest For(ExecutionFixture fixture, GridSchema schema, PageSpec? page = null)
    {
        var requestJson = fixture.Request.GetRawText();
        var options = new AgGridParseOptions { Schema = schema, Clock = ClockFor(fixture.Request), AllowUnboundedRows = HarnessFlag(fixture.Request, "allowUnboundedRows") };
        var limits = new ResourceLimits();

        if (fixture.Request.ValueKind == JsonValueKind.Object && fixture.Request.TryGetProperty("setValuesRequest", out _))
        {
            var parsed = AgGridRequestParser.ParseSetValues(requestJson, options);
            var filter = GridFilterPipeline.ProcessSetValues(
                parsed.NativeFilter, parsed.CustomFilters, parsed.SetValues, schema, limits);
            return new PreparedRequest(
                schema, true, null, filter, parsed.SetValues,
                ResourceLimitsValidator.ResolveSetValuesLimit(parsed.SetValues.Limit, limits));
        }

        var parsedRow = AgGridRequestParser.Parse(requestJson, options);
        var row = page is null ? parsedRow : parsedRow with { Page = page };
        var rowFilter = GridFilterPipeline.Process(
            row.NativeFilter, row.CustomFilters, row.Page, schema, limits, row.Group, row.Aggregations);
        return new PreparedRequest(schema, false, row, rowFilter, null, 0);
    }

    // The harness setup a port must reproduce: the host's switch for an unbounded request (PG-3), set by requestContext.allowUnboundedRows.
    private static bool HarnessFlag(JsonElement request, string member) =>
        request.ValueKind == JsonValueKind.Object
        && request.TryGetProperty("requestContext", out var context)
        && context.ValueKind == JsonValueKind.Object
        && context.TryGetProperty(member, out var value)
        && value.ValueKind == JsonValueKind.True;

    // The harness setup a port must reproduce: a clock pinned to requestContext.now for the cases that declare one.
    private static TimeProvider ClockFor(JsonElement request)
    {
        if (request.ValueKind == JsonValueKind.Object
            && request.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("now", out var now)
            && now.ValueKind == JsonValueKind.String)
        {
            return new FixedClock(DateTimeOffset.Parse(now.GetString()!, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind));
        }

        return TimeProvider.System;
    }

    private sealed class FixedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}

/// <summary>An engine's rows mapped onto the logical column list (XEQ-3), as CLR values for <see cref="RowComparer"/>.</summary>
internal sealed record EngineRows(IReadOnlyList<string> Columns, IReadOnlyList<IReadOnlyList<object?>> Rows);

/// <summary>The engine (or the compiler in front of it) refused the query; what an XEQ-4 <c>error</c> entry asserts.</summary>
internal sealed class EngineRefusedException(string message, Exception? inner = null) : Exception(message, inner);
