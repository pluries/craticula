using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;
using Craticula.Search;
using Craticula.Sql;

namespace Craticula.Conformance.Driver;

/// <summary>
/// Turns one conformance request — its <c>backend</c> and the raw JSON of its <c>schema</c> and
/// <c>agGridRequest</c> — into the compiled query for that backend, with the inputs of
/// <c>spec/conformance-runner.md</c> §3 pinned (TRD T-1(a), ML-3).
///
/// <para>A fourth copy of the pipeline the C# conformance tests run —
/// <c>Craticula.Sql.Tests.FixtureCompiler</c>, <c>Craticula.Mongo.Tests.MongoFixtureCompiler</c> and
/// <c>Craticula.Search.Tests.SearchFixtureCompiler</c> — kept here rather than shared:
/// those helpers are internal to their test assemblies, and moving them would put test code in a
/// shipped-looking project. Drift between the copies cannot hide, because the runner and the xUnit
/// suites grade both against the same expected artifacts. Change one, change the others.</para>
/// </summary>
internal static class RequestCompiler
{
    /// <summary>The backends this driver compiles, in the order its hello declares them (§2.1): the
    /// five SQL dialects, then MongoDB, then the one shared OpenSearch/Elasticsearch artifact.</summary>
    public static readonly string[] Backends = ["postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search"];

    /// <summary>Everything a request resolves to before any backend sees it: the schema and the
    /// parse options a host would build, plus which entry point the request takes.</summary>
    private sealed record Prepared(GridSchema Schema, string RequestJson, AgGridParseOptions Options, bool IsSetValues, ResourceLimits Limits);

    /// <summary>A row-fetch request after <see cref="AgGridRequestParser.Parse"/> and
    /// <see cref="GridFilterPipeline.Process"/> — the helpers' <c>RowFetch</c>.</summary>
    private sealed record RowFetch(GridSchema Schema, AgGridParsedRequest Parsed, FilterNode? Filter);

    /// <summary>BM-3's distinct-values request after the same two steps, with GRP-6(d)'s cap
    /// already resolved — the helpers' <c>SetValues</c>.</summary>
    private sealed record SetValues(GridSchema Schema, SetValuesSpec Spec, FilterNode? Filter, int RowLimit);

    /// <summary>
    /// Compiles one request end to end, with nothing stubbed, and returns the backend's compiled
    /// query — a <see cref="SqlQuery"/>, a <see cref="MongoQuery"/> or a <see cref="SearchQuery"/> —
    /// for <see cref="ArtifactWriter"/> to print. Any refusal surfaces as the exception the library
    /// throws; the caller turns it into an <c>error</c> answer (§2.2).
    /// </summary>
    public static object Compile(string backend, string schemaJson, string agGridRequestJson)
    {
        if (!Backends.Contains(backend))
        {
            throw new NotSupportedException(
                $"Backend '{backend}' is not one this driver declares ({string.Join(", ", Backends)}).");
        }

        var request = Prepare(schemaJson, agGridRequestJson);

        return backend switch
        {
            "postgres" => CompileSql(request, PostgresDialect.Instance),
            "mssql" => CompileSql(request, MssqlDialect.Instance),
            "mysql" => CompileSql(request, MySqlDialect.Instance),
            "oracle" => CompileSql(request, OracleDialect.Instance),
            "sqlite" => CompileSql(request, SqliteDialect.Instance),
            "mongo" => CompileMongo(request),
            "search" => CompileSearch(request),
            _ => throw new UnreachableException($"Backend '{backend}' passed the check above.")
        };
    }

    private static SqlQuery CompileSql(Prepared request, ISqlDialect dialect)
    {
        if (request.IsSetValues)
        {
            var values = PrepareSetValues(request);

            return SqlQueryBuilder.BuildSetValues(
                new SqlSetValuesRequest
                {
                    Schema = values.Schema,
                    ColId = values.Spec.ColId,
                    Filter = values.Filter,
                    RowLimit = values.RowLimit
                },
                dialect);
        }

        var row = PrepareRowFetch(request);

        return SqlQueryBuilder.Build(
            new SqlQueryRequest
            {
                Schema = row.Schema,
                Filter = row.Filter,
                Sort = row.Parsed.Sort,
                Page = row.Parsed.Page,
                Group = row.Parsed.Group,
                Aggregations = row.Parsed.Aggregations,
                Projection = row.Parsed.Export?.ProjectionColumns
            },
            dialect);
    }

    private static MongoQuery CompileMongo(Prepared request)
    {
        if (request.IsSetValues)
        {
            var values = PrepareSetValues(request);

            return MongoPipelineBuilder.BuildSetValues(new MongoSetValuesRequest
            {
                Schema = values.Schema,
                ColId = values.Spec.ColId,
                Filter = values.Filter,
                RowLimit = values.RowLimit,
                MaxQueryTimeMs = request.Limits.MaxQueryTimeMs
            });
        }

        var row = PrepareRowFetch(request);

        return MongoPipelineBuilder.Build(new MongoQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
            Projection = row.Parsed.Export?.ProjectionColumns,
            MaxQueryTimeMs = request.Limits.MaxQueryTimeMs
        });
    }

    /// <summary>No <c>Projection</c> on the row-fetch path, exactly as <c>SearchFixtureCompiler</c>:
    /// <see cref="SearchQueryRequest"/> has no such member (OSE-13).</summary>
    private static SearchQuery CompileSearch(Prepared request)
    {
        if (request.IsSetValues)
        {
            var values = PrepareSetValues(request);

            return SearchQueryBuilder.BuildSetValues(new SearchSetValuesRequest
            {
                Schema = values.Schema,
                ColId = values.Spec.ColId,
                Filter = values.Filter,
                SearchPrefix = values.Spec.SearchPrefix,
                RowLimit = values.RowLimit
            });
        }

        var row = PrepareRowFetch(request);

        return SearchQueryBuilder.Build(new SearchQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations
        });
    }

    /// <summary>SEC-3's default <see cref="ResourceLimits"/>, never raised or lowered, plus the harness's TL-4 query time limit when the fixture declares one (§3).</summary>
    private static RowFetch PrepareRowFetch(Prepared request)
    {
        var parsed = AgGridRequestParser.Parse(request.RequestJson, request.Options);

        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            parsed.Page,
            request.Schema,
            request.Limits,
            parsed.Group,
            parsed.Aggregations);

        return new RowFetch(request.Schema, parsed, filter);
    }

    /// <summary>The same defaults, which also carry GRP-6(d)'s default and maximum value counts.</summary>
    private static SetValues PrepareSetValues(Prepared request)
    {
        var limits = request.Limits;
        var parsed = AgGridRequestParser.ParseSetValues(request.RequestJson, request.Options);

        var filter = GridFilterPipeline.ProcessSetValues(
            parsed.NativeFilter, parsed.CustomFilters, parsed.SetValues, request.Schema, limits);

        return new SetValues(
            request.Schema,
            parsed.SetValues,
            filter,
            ResourceLimitsValidator.ResolveSetValuesLimit(parsed.SetValues.Limit, limits));
    }

    /// <summary>
    /// The harness setup of §3, read from one parse of the request: the fixture's own
    /// <see cref="GridSchema"/> always (a date filter's wire value is typed from it), the entry point
    /// (a top-level <c>setValuesRequest</c> member is BM-3's distinct-values request), and a clock
    /// pinned to <c>requestContext.now</c> when the request declares one. That <c>now</c> is SEM-4's
    /// harness instruction — a production host never reads it from the wire; this driver is the
    /// harness, so it does. <c>requestContext.zone</c> needs nothing here: the parser itself reads it,
    /// as it does for any request.
    /// </summary>
    private static Prepared Prepare(string schemaJson, string agGridRequestJson)
    {
        var schema = GridSchema.Parse(schemaJson);

        using var document = JsonDocument.Parse(agGridRequestJson);
        var root = document.RootElement;
        var isObject = root.ValueKind == JsonValueKind.Object;

        var pinnedNow = isObject
            && root.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("now", out var now)
            && now.ValueKind == JsonValueKind.String
                ? now.GetString()
                : null;

        var options = new AgGridParseOptions
        {
            Schema = schema,
            Clock = pinnedNow is null ? TimeProvider.System : PinnedClock.At(pinnedNow)
        };

        return new Prepared(
            schema,
            agGridRequestJson,
            options,
            isObject && root.TryGetProperty("setValuesRequest", out _),
            new ResourceLimits { MaxQueryTimeMs = ReadHarnessQueryTimeLimit(root) });
    }

    /// <summary>
    /// TL-4's harness instruction: <c>requestContext.maxQueryTimeMs</c>, a whole number, sets the host's
    /// maximum query time for this compile (<c>conformance-runner.md</c> §3). Like <c>now</c>, a
    /// production host never reads it from the wire; this driver is the harness, so it does. Only
    /// <c>requestContext</c> counts: a top-level <c>maxQueryTimeMs</c> is just a request member the
    /// parser ignores (fixture <c>query-time-limit/006</c>). An invalid value is refused by
    /// <see cref="ResourceLimits"/>, as it would be for a host.
    /// </summary>
    private static int? ReadHarnessQueryTimeLimit(JsonElement root) =>
        root.ValueKind == JsonValueKind.Object
            && root.TryGetProperty("requestContext", out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("maxQueryTimeMs", out var limit)
            && limit.ValueKind == JsonValueKind.Number
                ? limit.GetInt32()
                : null;

    /// <summary>
    /// A <see cref="TimeProvider"/> pinned to one instant, so a request carrying
    /// <c>requestContext.now</c> resolves its AG-2 date presets reproducibly (SEM-4). Parses exactly
    /// as the test projects' <c>FixedClock.At</c>, which lives only there; hand-written rather than
    /// taken from <c>Microsoft.Extensions.TimeProvider.Testing</c> (no package).
    /// </summary>
    private sealed class PinnedClock(DateTimeOffset now) : TimeProvider
    {
        // `System.Globalization.X` cannot be written unqualified inside a TimeProvider subclass —
        // `System` binds to the inherited TimeProvider.System property first. Hence the using above.
        public static PinnedClock At(string iso8601Instant) =>
            new(DateTimeOffset.Parse(iso8601Instant, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind));

        public override DateTimeOffset GetUtcNow() => now;
    }
}
