using System.Text.Json;
using System.Text.Json.Nodes;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Search.Tests;

/// <summary>
/// The one place a conformance test turns a fixture directory into a compiled artifact. Deliberately
/// the same shape as <c>Craticula.Sql.Tests.FixtureCompiler</c> and
/// <c>Craticula.Mongo.Tests.MongoFixtureCompiler</c> (both internal to their own assemblies, so
/// neither is reusable from here): the three suites must differ ONLY in which compiler they call and
/// which artifact they compare against.
///
/// <para>The parse-and-pipeline half is factored out as <see cref="PrepareRowFetch"/> /
/// <see cref="PrepareSetValues"/> so that <see cref="CrossCompilerGroupingTests"/> can drive the SQL,
/// Mongo and Search compilers from the <em>same</em> resolved IR object rather than from three
/// harnesses that merely look alike. That is what makes a difference between the outputs evidence
/// about the compilers instead of about the harness.</para>
/// </summary>
internal static class SearchFixtureCompiler
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
    public static SearchQuery Compile(string category, string fixtureDir)
    {
        if (IsSetValuesFixture(category, fixtureDir))
        {
            var request = PrepareSetValues(category, fixtureDir);

            return SearchQueryBuilder.BuildSetValues(new SearchSetValuesRequest
            {
                Schema = request.Schema,
                ColId = request.Spec.ColId,
                Filter = request.Filter,
                SearchPrefix = request.Spec.SearchPrefix,
                RowLimit = request.RowLimit,
                MaxQueryTimeMs = LimitsFor(category, fixtureDir).MaxQueryTimeMs
            });
        }

        var row = PrepareRowFetch(category, fixtureDir);

        return SearchQueryBuilder.Build(new SearchQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
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
    /// Both sides of an artifact comparison go through the identical canonicalisation, so the
    /// assertion is on JSON <em>values</em> without being sensitive to the fixture file's own
    /// indentation — or to object key order, which this DSL never reads (OSE-0).
    ///
    /// <para><b>Object keys are SORTED and array order is preserved, and the asymmetry is the whole
    /// point.</b> Nowhere in an OpenSearch/Elasticsearch request body does an object's key order
    /// carry meaning — unlike MongoDB's <c>$sort</c> document, whose key order IS the tiebreak order,
    /// which is why <c>MongoFixtureCompiler.CanonicalJson</c> deliberately compares order-sensitively.
    /// Arrays, on the other hand, do carry meaning here: <c>sort</c>'s element order is the tiebreak
    /// order and <c>composite.sources</c>' is the bucket key order, so they are compared as
    /// written.</para>
    ///
    /// <para>Doing it this way rather than re-authoring artifacts is a decision, not a convenience:
    /// the hand-authored suite spells <c>size</c> before <c>from</c> in 78 files and after it in 50,
    /// and neither is more correct. Making one of them "the" order would have re-authored half the
    /// suite to agree about something no engine reads, while leaving the compiler's OWN order
    /// unpinned. <see cref="SearchQuery.ToArtifact"/> fixes that order instead, and
    /// <see cref="SearchQueryShapeTests"/> asserts it verbatim.</para>
    /// </summary>
    public static string CanonicalJson(JsonNode? node) =>
        Canonicalize(node)?.ToJsonString(CanonicalOptions) ?? "null";

    public static string CanonicalJson(string json) => CanonicalJson(JsonNode.Parse(json));

    private static JsonNode? Canonicalize(JsonNode? node) => node switch
    {
        JsonObject o => new JsonObject(o
            .OrderBy(property => property.Key, StringComparer.Ordinal)
            .Select(property => KeyValuePair.Create(property.Key, Canonicalize(property.Value)))),
        JsonArray a => new JsonArray([.. a.Select(Canonicalize)]),
        _ => node?.DeepClone()
    };

    private static readonly JsonSerializerOptions CanonicalOptions = new() { WriteIndented = false };
}
