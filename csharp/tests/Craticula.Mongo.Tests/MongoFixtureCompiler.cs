using System.Text.Json;
using System.Text.Json.Nodes;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo.Tests;

/// <summary>
/// The one place a conformance test turns a fixture directory into a compiled artifact. Deliberately
/// the same shape as <c>Craticula.Sql.Tests.FixtureCompiler</c> (internal to that assembly, so not
/// reusable from here): the two suites must differ ONLY in which compiler they call and which
/// artifact they compare against.
///
/// <para>The parse-and-pipeline half is factored out as <see cref="PrepareRowFetch"/> /
/// <see cref="PrepareSetValues"/> so that <see cref="CrossCompilerGroupingTests"/> can drive the SQL
/// and Mongo compilers from the <em>same</em> resolved IR object rather than from two harnesses that
/// merely look alike. That is what makes a difference between the two outputs evidence about the
/// compilers instead of about the harness.</para>
/// </summary>
internal static class MongoFixtureCompiler
{
    /// <summary>Everything a row-fetch request resolves to before any backend sees it — the exact
    /// output of the path a host runs: <see cref="AgGridRequestParser.Parse"/> then
    /// <see cref="GridFilterPipeline.Process"/>.</summary>
    public sealed record RowFetch(GridSchema Schema, AgGridParsedRequest Parsed, FilterNode? Filter);

    /// <summary>The same, for BM-3's distinct-values envelope, with GRP-6(d)'s cap already
    /// resolved.</summary>
    public sealed record SetValues(GridSchema Schema, SetValuesSpec Spec, FilterNode? Filter, int RowLimit);

    public static bool IsSetValuesFixture(string category, string fixtureDir)
    {
        using var document = JsonDocument.Parse(Read(category, fixtureDir, "agGridRequest.json"));
        return document.RootElement.ValueKind == JsonValueKind.Object
            && document.RootElement.TryGetProperty("setValuesRequest", out _);
    }

    public static RowFetch PrepareRowFetch(string category, string fixtureDir)
    {
        var schema = GridSchema.Parse(Read(category, fixtureDir, "schema.json"));
        var parsed = AgGridRequestParser.Parse(
            Read(category, fixtureDir, "agGridRequest.json"), OptionsFor(category, fixtureDir, schema));

        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            parsed.Page,
            schema,
            LimitsFor(category, fixtureDir),
            parsed.Group,
            parsed.Aggregations);

        return new RowFetch(schema, parsed, filter);
    }

    public static SetValues PrepareSetValues(string category, string fixtureDir)
    {
        var limits = LimitsFor(category, fixtureDir);
        var schema = GridSchema.Parse(Read(category, fixtureDir, "schema.json"));
        var parsed = AgGridRequestParser.ParseSetValues(
            Read(category, fixtureDir, "agGridRequest.json"), OptionsFor(category, fixtureDir, schema));

        var filter = GridFilterPipeline.ProcessSetValues(
            parsed.NativeFilter, parsed.CustomFilters, parsed.SetValues, schema, limits);

        return new SetValues(
            schema,
            parsed.SetValues,
            filter,
            ResourceLimitsValidator.ResolveSetValuesLimit(parsed.SetValues.Limit, limits));
    }

    /// <summary>
    /// The exact pipeline a host runs, with nothing stubbed. Dispatches on the request document
    /// itself, exactly as a host endpoint would — a <c>setValuesRequest</c> envelope is BM-3's
    /// distinct-values query, anything else is a row fetch.
    /// </summary>
    public static MongoQuery Compile(string category, string fixtureDir)
    {
        if (IsSetValuesFixture(category, fixtureDir))
        {
            var request = PrepareSetValues(category, fixtureDir);

            return MongoPipelineBuilder.BuildSetValues(new MongoSetValuesRequest
            {
                Schema = request.Schema,
                ColId = request.Spec.ColId,
                Filter = request.Filter,
                RowLimit = request.RowLimit,
                MaxQueryTimeMs = LimitsFor(category, fixtureDir).MaxQueryTimeMs
            });
        }

        var row = PrepareRowFetch(category, fixtureDir);

        return MongoPipelineBuilder.Build(new MongoQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
            Projection = row.Parsed.Export?.ProjectionColumns,
            MaxQueryTimeMs = LimitsFor(category, fixtureDir).MaxQueryTimeMs
        });
    }

    /// <summary>
    /// The harness setup a port must reproduce: the fixture's own <c>GridSchema</c> always (a date
    /// filter's wire value is typed from it), plus a clock pinned to <c>requestContext.now</c> for
    /// the cases that declare one. That <c>now</c> is an instruction to the harness, not a field the
    /// parser reads.
    /// </summary>
    /// <summary>TL-4's harness instruction: <c>requestContext.maxQueryTimeMs</c> sets the host's maximum
    /// query time; no parser reads it.</summary>
    private static ResourceLimits LimitsFor(string category, string fixtureDir)
    {
        using var request = JsonDocument.Parse(Read(category, fixtureDir, "agGridRequest.json"));

        return new ResourceLimits
        {
            MaxQueryTimeMs = request.RootElement.TryGetProperty("requestContext", out var context)
                && context.ValueKind == JsonValueKind.Object
                && context.TryGetProperty("maxQueryTimeMs", out var limit)
                && limit.ValueKind == JsonValueKind.Number
                    ? limit.GetInt32()
                    : null
        };
    }

    private static AgGridParseOptions OptionsFor(string category, string fixtureDir, GridSchema schema)
    {
        using var request = JsonDocument.Parse(Read(category, fixtureDir, "agGridRequest.json"));

        var pinnedNow = request.RootElement.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("now", out var now)
            && now.ValueKind == JsonValueKind.String
                ? now.GetString()
                : null;

        return new AgGridParseOptions
        {
            Schema = schema,
            Clock = pinnedNow is null ? TimeProvider.System : FixedClock.At(pinnedNow)
        };
    }

    public static string Read(string category, string fixtureDir, params string[] rest) =>
        File.ReadAllText(RepoPaths.Fixture([category, fixtureDir, .. rest]));

    /// <summary>
    /// Both sides of an artifact comparison go through the identical writer, so the assertion is on
    /// JSON <em>values</em> — including each key's position, which is load-bearing for a
    /// <c>$sort</c> document (MongoDB sorts by the keys in the order they appear) — without being
    /// sensitive to the fixture file's own indentation.
    /// <see cref="JsonNode.Parse(string, JsonNodeOptions?, JsonDocumentOptions)"/> preserves property
    /// order, so re-serializing compactly normalises whitespace alone.
    /// </summary>
    public static string CanonicalJson(JsonNode? node) => node?.ToJsonString(CanonicalOptions) ?? "null";

    public static string CanonicalJson(string json) => CanonicalJson(JsonNode.Parse(json));

    private static readonly JsonSerializerOptions CanonicalOptions = new() { WriteIndented = false };
}
