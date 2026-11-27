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
    private const string RequestContextMember = "requestContext";

    /// <summary>The backends this driver compiles, in the order its hello declares them (§2.1): the
    /// five SQL dialects, then MongoDB, then the one shared OpenSearch/Elasticsearch artifact.</summary>
    public static readonly string[] Backends = ["postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search"];

    /// <summary>Everything a request resolves to before any backend sees it: the schema and the
    /// parse options a host would build, plus which entry point the request takes.</summary>
    private sealed record Prepared(GridSchema Schema, string RequestJson, AgGridParseOptions Options, bool IsSetValues, ResourceLimits Limits, bool CountMode);

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
    public static object Compile(string backend, string schemaJson, string agGridRequestJson) =>
        Compile(backend, GridSchema.Parse(schemaJson), agGridRequestJson);

    /// <summary>
    /// A rejection request (<c>conformance-runner.md</c> §2.2) names no backend: the refusal comes before any compiler.
    /// The driver acts as the host does. It checks every sort colId against the schema first, because the library has no
    /// allowlist stage for them (a compiler is reached only after the host's check, and refuses an undeclared field with a
    /// <see cref="SqlCompilationException"/> no oracle names), then runs the request through the pinned compile on one
    /// backend. A request that compiles is answered with its artifact, which the runner fails (§4.1).
    /// </summary>
    public static object CompileForRejection(string schemaJson, string agGridRequestJson)
    {
        var schema = GridSchema.Parse(schemaJson);
        RequireDeclaredSortColIds(schema, agGridRequestJson);
        return Compile(Backends[0], schema, agGridRequestJson);
    }

    private static void RequireDeclaredSortColIds(GridSchema schema, string agGridRequestJson)
    {
        using var document = JsonDocument.Parse(agGridRequestJson, new JsonDocumentOptions { MaxDepth = 1_000 });
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !document.RootElement.TryGetProperty("sortModel", out var sortModel)
            || sortModel.ValueKind != JsonValueKind.Array)
        {
            return;
        }

        var unknown = sortModel.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.Object
                && item.TryGetProperty("colId", out var colId) && colId.ValueKind == JsonValueKind.String)
            .Select(item => item.GetProperty("colId").GetString()!)
            .Where(colId => !colId.StartsWith(GroupAutoColumnPrefix, StringComparison.Ordinal)
                && !schema.Fields.ContainsKey(colId))
            .Distinct(StringComparer.Ordinal)
            .Select(colId => new AllowlistViolation(colId, colId, "unknown-field"))
            .ToArray();

        if (unknown.Length > 0)
        {
            throw new UnknownFieldException(unknown);
        }
    }

    /// <summary>AG Grid's id prefix for the auto group column; a sort on it is a group sort, not a schema field.</summary>
    private const string GroupAutoColumnPrefix = "ag-Grid-AutoColumn";

    /// <summary>The same compile for a schema the caller already built, as a host that builds its <see cref="GridSchema"/> once does; the compile benchmark times it next to the string path.</summary>
    public static object Compile(string backend, GridSchema schema, string agGridRequestJson)
    {
        if (!Backends.Contains(backend))
        {
            throw new NotSupportedException(
                $"Backend '{backend}' is not one this driver declares ({string.Join(", ", Backends)}).");
        }

        var request = Prepare(schema, agGridRequestJson);

        if (request.CountMode && request.IsSetValues)
        {
            throw new NotSupportedException(
                "Count mode (requestContext.compileMode \"count\") counts the rows of a row request; a set-values request has no count.");
        }

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

        var sqlRequest = new SqlQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
            Projection = row.Parsed.Export?.ProjectionColumns
        };

        return request.CountMode ? SqlQueryBuilder.BuildCount(sqlRequest, dialect) : SqlQueryBuilder.Build(sqlRequest, dialect);
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

        var mongoRequest = new MongoQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
            Projection = row.Parsed.Export?.ProjectionColumns,
            MaxQueryTimeMs = request.Limits.MaxQueryTimeMs
        };

        return request.CountMode ? MongoPipelineBuilder.BuildCount(mongoRequest) : MongoPipelineBuilder.Build(mongoRequest);
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
                RowLimit = values.RowLimit,
                MaxQueryTimeMs = request.Limits.MaxQueryTimeMs
            });
        }

        var row = PrepareRowFetch(request);

        var searchRequest = new SearchQueryRequest
        {
            Schema = row.Schema,
            Filter = row.Filter,
            Sort = row.Parsed.Sort,
            Page = row.Parsed.Page,
            Group = row.Parsed.Group,
            Aggregations = row.Parsed.Aggregations,
            MaxQueryTimeMs = request.Limits.MaxQueryTimeMs
        };

        return request.CountMode ? SearchQueryBuilder.BuildCount(searchRequest) : SearchQueryBuilder.Build(searchRequest);
    }

    /// <summary>SEC-3's default <see cref="ResourceLimits"/>, never raised or lowered, plus the harness's TL-4 query time limit when the fixture declares one (§3).</summary>
    private static RowFetch PrepareRowFetch(Prepared request)
    {
        var parsed = AgGridRequestParser.Parse(request.RequestJson, request.Options);

        // CNT-3: SEC-3's page-size check runs inside the pipeline, so a count is processed with the unpaginated page.
        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            request.CountMode ? new NonePage() : parsed.Page,
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
    private static Prepared Prepare(GridSchema schema, string agGridRequestJson)
    {
        using var document = JsonDocument.Parse(agGridRequestJson);
        var root = document.RootElement;
        var isObject = root.ValueKind == JsonValueKind.Object;

        var pinnedNow = isObject
            && root.TryGetProperty(RequestContextMember, out var context)
            && context.ValueKind == JsonValueKind.Object
            && context.TryGetProperty("now", out var now)
            && now.ValueKind == JsonValueKind.String
                ? now.GetString()
                : null;

        var options = new AgGridParseOptions
        {
            Schema = schema,
            Clock = pinnedNow is null ? TimeProvider.System : PinnedClock.At(pinnedNow),
            DefaultPageSize = HarnessInt(root, "defaultPageSize") ?? 100,
            AllowUnboundedRows = HarnessFlag(root, "allowUnboundedRows")
        };

        return new Prepared(
            schema,
            agGridRequestJson,
            options,
            isObject && root.TryGetProperty("setValuesRequest", out _),
            new ResourceLimits { MaxQueryTimeMs = ReadHarnessQueryTimeLimit(root) },
            ReadHarnessCountMode(root));
    }

    /// <summary>
    /// CNT-8's harness instruction: <c>requestContext.compileMode</c> set to <c>"count"</c> selects count mode
    /// (<c>conformance-runner.md</c> §3). Absent means the page; any other value is refused rather than ignored, so a typo
    /// can never silently grade a page artifact against a count expectation.
    /// </summary>
    private static bool ReadHarnessCountMode(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty(RequestContextMember, out var context)
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
            && root.TryGetProperty(RequestContextMember, out var context)
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

    private static int? HarnessInt(JsonElement root, string name) =>
        root.ValueKind == JsonValueKind.Object
        && root.TryGetProperty(RequestContextMember, out var context)
        && context.ValueKind == JsonValueKind.Object
        && context.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.Number
            ? value.GetInt32()
            : null;

    private static bool HarnessFlag(JsonElement root, string name) =>
        root.ValueKind == JsonValueKind.Object
        && root.TryGetProperty(RequestContextMember, out var context)
        && context.ValueKind == JsonValueKind.Object
        && context.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.True;
}
