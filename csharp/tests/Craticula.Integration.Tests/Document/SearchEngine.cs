using System.Globalization;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Integration.Tests.Docker;
using Craticula.Integration.Tests.Oracle;
using Craticula.Search;
using DotNet.Testcontainers.Builders;
using DotNet.Testcontainers.Containers;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>One single-node OpenSearch or Elasticsearch container, security off, over plain HTTP.</summary>
public abstract class SearchEngineFixture : IAsyncLifetime
{
    private IContainer? container;

    /// <summary>XEQ-4's <c>engine</c> name: <c>opensearch</c> or <c>elasticsearch</c>.</summary>
    public abstract string EngineName { get; }

    public abstract string Image { get; }

    protected abstract IReadOnlyDictionary<string, string> Environment { get; }

    internal HttpClient? Http { get; private set; }

    public string? StartupFailure { get; private set; }

    public async Task InitializeAsync()
    {
        if (!DockerAvailability.IsAvailable)
        {
            return;
        }

        try
        {
            container = new ContainerBuilder(Image)
                .WithEnvironment(Environment)
                .WithPortBinding(9200, true)
                .Build();
            using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(10));
            await container.StartAsync(timeout.Token).ConfigureAwait(false);
            var http = new HttpClient { BaseAddress = new Uri($"http://{container.Hostname}:{container.GetMappedPublicPort(9200)}/"), Timeout = TimeSpan.FromMinutes(2) };
            await WaitForYellowAsync(http, timeout.Token).ConfigureAwait(false);
            Http = http;
        }
        catch (Exception exception)
        {
            StartupFailure = exception.ToString();
        }
    }

    // The engine's JVM takes tens of seconds to answer; poll the cluster health ourselves (a wait strategy's own
    // timeout and query-string handling proved less reliable than an explicit loop).
    private static async Task WaitForYellowAsync(HttpClient http, CancellationToken cancellationToken)
    {
        while (true)
        {
            try
            {
                using var response = await http.GetAsync("_cluster/health?wait_for_status=yellow&timeout=30s", cancellationToken).ConfigureAwait(false);
                if (response.IsSuccessStatusCode)
                {
                    return;
                }
            }
            catch (HttpRequestException)
            {
                // Not listening yet.
            }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                // The health call itself timed out; ask again.
            }

            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task DisposeAsync()
    {
        Http?.Dispose();
        if (container is not null)
        {
            await container.DisposeAsync().ConfigureAwait(false);
        }
    }

    internal HttpClient Require() =>
        Http ?? throw new InvalidOperationException($"The {EngineName} container ({Image}) did not start: {StartupFailure}");
}

/// <summary>OpenSearch 2.x, single node, security plugin off.</summary>
public sealed class OpenSearchEngineFixture : SearchEngineFixture
{
    public override string EngineName => "opensearch";

    public override string Image => "opensearchproject/opensearch:2.19.1";

    protected override IReadOnlyDictionary<string, string> Environment { get; } = new Dictionary<string, string>
    {
        ["discovery.type"] = "single-node",
        ["DISABLE_SECURITY_PLUGIN"] = "true",
        ["DISABLE_INSTALL_DEMO_CONFIG"] = "true",
        // The disk watermarks look at the whole host disk, not at this throwaway container: on a shared, nearly full machine
        // they leave the primary shard inactive (about 90%) or block index creation (95%) and fail the tests (#3142).
        ["cluster.routing.allocation.disk.threshold_enabled"] = "false",
        ["OPENSEARCH_JAVA_OPTS"] = "-Xms512m -Xmx512m"
    };
}

/// <summary>Elasticsearch 8.x, single node, security off.</summary>
public sealed class ElasticsearchEngineFixture : SearchEngineFixture
{
    public override string EngineName => "elasticsearch";

    public override string Image => "docker.elastic.co/elasticsearch/elasticsearch:8.17.4";

    protected override IReadOnlyDictionary<string, string> Environment { get; } = new Dictionary<string, string>
    {
        ["discovery.type"] = "single-node",
        ["xpack.security.enabled"] = "false",
        // Same reason as for OpenSearch above (#3142).
        ["cluster.routing.allocation.disk.threshold_enabled"] = "false",
        ["ES_JAVA_OPTS"] = "-Xms512m -Xmx512m"
    };
}

/// <summary>
/// The Search side of T-1b, shared by both engines because <c>search.artifact.json</c> is one artifact that runs on both
/// (OQ-7, XEQ-4): create a fresh index mapped from the schema, bulk-seed it, compile with
/// <see cref="SearchQueryBuilder"/>, POST the body to <c>_search</c> over HttpClient and map hits / composite buckets /
/// terms buckets onto the logical column list.
///
/// <para><b>Composite paging.</b> A grouped level's compiled window is <c>size = endRow - startRow</c> with no
/// <c>after</c> key, and the compiler REFUSES a non-zero <c>startRow</c> (OSE-11(d)'s documented first-page-only limit),
/// so the first response IS the whole window. The harness asserts that rather than assuming it: a grouped fixture whose
/// request starts past 0 fails as a compiler refusal, and a window that the engine reports as full is checked against
/// the number of buckets the window asked for.</para>
/// </summary>
internal static class SearchEngine
{
    private const int ExportWindow = 10_000;

    public static async Task<EngineRows> RunAsync(HttpClient http, ExecutionFixture fixture)
    {
        var index = "xeq_" + Guid.NewGuid().ToString("N");
        try
        {
            await SeedAsync(http, index, fixture).ConfigureAwait(false);
            return await QueryAsync(http, index, fixture).ConfigureAwait(false);
        }
        finally
        {
            try
            {
                await http.DeleteAsync(index).ConfigureAwait(false);
            }
            catch (HttpRequestException)
            {
                // Best-effort: a leaked index costs the container's memory, never another fixture's result.
            }
        }
    }

    /// <summary>Creates the index named <paramref name="index"/> mapped from the fixture's schema and bulk-seeds it; the caller owns (and deletes) it.</summary>
    public static async Task SeedAsync(HttpClient http, string index, ExecutionFixture fixture)
    {
        var schema = fixture.Schema with { Source = index };
        await Send(http, HttpMethod.Put, index, BuildMapping(schema).ToJsonString(), "application/json", "create index").ConfigureAwait(false);
        await Seed(http, index, schema, fixture).ConfigureAwait(false);
    }

    /// <summary>Compiles the fixture's request against <paramref name="index"/>, runs it and maps the hits or buckets onto the logical columns.</summary>
    public static Task<EngineRows> QueryAsync(HttpClient http, string index, ExecutionFixture fixture) =>
        QueryAsync(http, index, fixture, PreparedRequest.For(fixture, fixture.Schema with { Source = index }));

    /// <summary>The page path over an already prepared request; <paramref name="inspect"/> sees the raw response before it is mapped.</summary>
    public static async Task<EngineRows> QueryAsync(
        HttpClient http, string index, ExecutionFixture fixture, PreparedRequest request, Action<JsonElement>? inspect = null)
    {
        ArgumentNullException.ThrowIfNull(fixture);
        ArgumentNullException.ThrowIfNull(request);
        var compiled = Compile(request);
        var body = compiled.ToArtifact();

        // EXP-2's `page: none` compiles to a hit query with NO `size`, which the engine answers with its default
        // of 10 hits; the adapter streams such an export (PIT + search_after). The harness reads the whole result
        // in one request instead, and asserts it fits, so a truncated export can never pass as a short one.
        var unpaged = body["size"] is null && body["aggs"] is null;
        if (unpaged)
        {
            body["size"] = ExportWindow;
            body["track_total_hits"] = true;
        }

        var response = await SearchAsync(http, index, body).ConfigureAwait(false);
        using var document = JsonDocument.Parse(response);
        if (unpaged)
        {
            var total = document.RootElement.GetProperty("hits").GetProperty("total").GetProperty("value").GetInt64();
            Assert.True(total <= ExportWindow, $"the unpaginated result has {total} hits, more than the harness's single-request window of {ExportWindow}");
        }

        inspect?.Invoke(document.RootElement);
        return Map(document.RootElement, request, compiled);
    }

    /// <summary>Posts <paramref name="body"/> to the index's <c>_search</c> and returns the response text.</summary>
    internal static Task<string> SearchAsync(HttpClient http, string index, JsonObject body)
    {
        ArgumentNullException.ThrowIfNull(body);
        return Send(http, HttpMethod.Post, $"{index}/_search", body.ToJsonString(), "application/json", "search", refuse: true);
    }

    private static SearchQuery Compile(PreparedRequest request)
    {
        try
        {
            if (request.IsSetValues)
            {
                return SearchQueryBuilder.BuildSetValues(new SearchSetValuesRequest
                {
                    Schema = request.Schema,
                    ColId = request.SetValues!.ColId,
                    Filter = request.Filter,
                    SearchPrefix = request.SetValues.SearchPrefix,
                    RowLimit = request.RowLimit
                });
            }

            var parsed = request.Parsed!;
            return SearchQueryBuilder.Build(new SearchQueryRequest
            {
                Schema = request.Schema,
                Filter = request.Filter,
                Sort = parsed.Sort,
                Page = parsed.Page,
                Group = parsed.Group,
                Aggregations = parsed.Aggregations
            });
        }
        catch (SearchCompilationException exception)
        {
            throw new EngineRefusedException($"The Search compiler refused the request: {exception.Message}", exception);
        }
    }

    // ---- mapping and seed ---------------------------------------------------------------------------------

    private static string PathOf(string colId, FieldConfig field) => field.Physical?.Search?.Field ?? colId;

    /// <summary>
    /// The mapping the compiler's conventions assume (SC-3, <c>semantics.md</c> OSE table): a <c>keyword</c> base field
    /// (a <c>text</c> one only for <c>searchMode: analyzed</c>) with the declared <c>keywordSubField</c> as a plain
    /// <c>keyword</c> and the declared <c>normalizedSubField</c> as a <c>keyword</c> with a lowercase normalizer;
    /// <c>decimal</c> maps to <c>double</c> (SearchJson.Encode's documented host choice, the live suites' too).
    /// </summary>
    private static JsonObject BuildMapping(GridSchema schema)
    {
        var properties = new JsonObject();
        var normalizers = new JsonObject();
        foreach (var (colId, field) in schema.Fields)
        {
            properties[PathOf(colId, field)] = field.Type switch
            {
                FieldType.String => StringMapping(field, normalizers),
                FieldType.Int64 => new JsonObject { ["type"] = "long" },
                FieldType.Decimal or FieldType.Double => new JsonObject { ["type"] = "double" },
                FieldType.Boolean => new JsonObject { ["type"] = "boolean" },
                FieldType.Date => new JsonObject { ["type"] = "date", ["format"] = "strict_date" },
                FieldType.Datetime => new JsonObject { ["type"] = "date", ["format"] = "strict_date_optional_time" },
                _ => throw new InvalidOperationException($"Unmapped FieldType '{field.Type}'.")
            };
        }

        var mapping = new JsonObject { ["mappings"] = new JsonObject { ["properties"] = properties } };
        if (normalizers.Count > 0)
        {
            mapping["settings"] = new JsonObject { ["analysis"] = new JsonObject { ["normalizer"] = normalizers } };
        }

        return mapping;
    }

    private static JsonObject StringMapping(FieldConfig field, JsonObject normalizers)
    {
        var mapping = new JsonObject { ["type"] = field.Text?.SearchMode == SearchMode.Analyzed ? "text" : "keyword" };
        var search = field.Physical?.Search;
        var subFields = new JsonObject();
        if (search?.KeywordSubField is { } keyword)
        {
            subFields[keyword.Split('.')[^1]] = new JsonObject { ["type"] = "keyword" };
        }

        if (search?.NormalizedSubField is { } normalized)
        {
            normalizers["lowercase_normalizer"] = new JsonObject { ["type"] = "custom", ["filter"] = new JsonArray("lowercase") };
            subFields[normalized.Split('.')[^1]] = new JsonObject { ["type"] = "keyword", ["normalizer"] = "lowercase_normalizer" };
        }

        if (subFields.Count > 0)
        {
            mapping["fields"] = subFields;
        }

        return mapping;
    }

    private static async Task Seed(HttpClient http, string index, GridSchema schema, ExecutionFixture fixture)
    {
        if (fixture.Seed.Count == 0)
        {
            return;
        }

        var bulk = new StringBuilder();
        foreach (var row in fixture.Seed)
        {
            // XEQ-2: a decimal stays a JSON number token (kept verbatim in _source), date and datetime stay their ISO
            // strings, an absent value is an explicit JSON null.
            var document = new JsonObject();
            foreach (var (colId, field) in schema.Fields)
            {
                var cell = row.Cells[colId];
                document[PathOf(colId, field)] = cell.ValueKind == JsonValueKind.Null
                    ? null
                    : field.Type == FieldType.Decimal ? JsonNode.Parse(cell.GetString()!) : JsonNode.Parse(cell.GetRawText());
            }

            bulk.Append("{\"index\":{}}\n").Append(document.ToJsonString()).Append('\n');
        }

        var result = await Send(http, HttpMethod.Post, $"{index}/_bulk?refresh=true", bulk.ToString(), "application/x-ndjson", "bulk index").ConfigureAwait(false);
        if (result.Contains("\"errors\":true", StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Bulk indexing into '{index}' reported per-item errors: {result}");
        }
    }

    private static async Task<string> Send(
        HttpClient http, HttpMethod method, string path, string body, string contentType, string action, bool refuse = false)
    {
        using var message = new HttpRequestMessage(method, path) { Content = new StringContent(body, Encoding.UTF8) };
        message.Content.Headers.ContentType = new MediaTypeHeaderValue(contentType);
        using var response = await http.SendAsync(message).ConfigureAwait(false);
        var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
        if (response.IsSuccessStatusCode)
        {
            return text;
        }

        var failure = $"{action} failed (HTTP {(int)response.StatusCode}): {Truncate(text)}";
        throw refuse && (int)response.StatusCode is >= 400 and < 500
            ? new EngineRefusedException($"The engine rejected the query. {failure}")
            : new InvalidOperationException(failure);
    }

    private static string Truncate(string text) => text.Length <= 700 ? text : text[..700] + "...";

    // ---- result mapping -----------------------------------------------------------------------------------

    private static EngineRows Map(JsonElement root, PreparedRequest request, SearchQuery compiled)
    {
        var columns = request.LogicalColumns();

        if (request.IsSetValues)
        {
            var colId = request.SetValues!.ColId;
            var type = request.Schema.Fields[colId].Type;
            var rows = root.GetProperty("aggregations").GetProperty(colId).GetProperty("buckets").EnumerateArray()
                .Select(bucket => (IReadOnlyList<object?>)[TermsKey(bucket, type)])
                .ToList();
            return new EngineRows(columns, rows);
        }

        var plan = request.Plan;
        if (plan is { GroupColumn: { } groupColumn })
        {
            var composite = root.GetProperty("aggregations").GetProperty(groupColumn);
            var buckets = composite.GetProperty("buckets").EnumerateArray().ToList();

            // The documented first-page-only window: the compiled size is endRow - 0, so a longer list would mean
            // the engine ignored it; a full window with an after_key just means more buckets exist beyond endRow.
            var size = compiled.Aggs![groupColumn]!["composite"]!["size"]!.GetValue<int>();
            Assert.True(buckets.Count <= size, $"the engine returned {buckets.Count} composite buckets for a window of {size}");

            var rows = buckets.Select(bucket =>
            {
                var cells = new object?[columns.Count];
                cells[0] = ScalarOrNull(bucket.GetProperty("key").GetProperty(groupColumn), request.Schema.Fields[groupColumn].Type);
                for (var i = 0; i < plan.Aggregations.Count; i++)
                {
                    cells[i + 1] = Metric(bucket, plan.Aggregations[i], request.Schema);
                }

                return (IReadOnlyList<object?>)cells;
            }).ToList();
            return new EngineRows(columns, rows);
        }

        var hitRows = root.GetProperty("hits").GetProperty("hits").EnumerateArray()
            .Select(hit =>
            {
                var source = hit.GetProperty("_source");
                return (IReadOnlyList<object?>)columns.Select(column =>
                {
                    var field = request.Schema.Fields[column];
                    return source.TryGetProperty(PathOf(column, field), out var raw) ? ScalarOrNull(raw, field.Type) : null;
                }).ToList();
            })
            .ToList();
        return new EngineRows(columns, hitRows);
    }

    private static object? TermsKey(JsonElement bucket, FieldType type) =>
        type is FieldType.Boolean or FieldType.Date or FieldType.Datetime && bucket.TryGetProperty("key_as_string", out var text)
            ? ScalarOrNull(text, type)
            : ScalarOrNull(bucket.GetProperty("key"), type);

    private static object? Metric(JsonElement bucket, Aggregation aggregation, GridSchema schema)
    {
        var metric = bucket.GetProperty(aggregation.OutputName);
        var sourceType = aggregation.Func == AggregationFunc.Count ? FieldType.Int64 : schema.Fields[aggregation.Field].Type;

        if (aggregation.Func != AggregationFunc.Count && aggregation.Func != AggregationFunc.Avg
            && sourceType is FieldType.Date or FieldType.Datetime)
        {
            return metric.TryGetProperty("value_as_string", out var formatted) && formatted.ValueKind == JsonValueKind.String
                ? formatted.GetString()
                : null;
        }

        var value = metric.GetProperty("value");
        if (value.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        var number = value.GetDouble();
        return aggregation.Func switch
        {
            AggregationFunc.Count => (long)number,
            AggregationFunc.Avg => number,
            _ => sourceType switch
            {
                FieldType.Int64 => (long)number,
                FieldType.Decimal => Convert.ToDecimal(number, CultureInfo.InvariantCulture),
                _ => number
            }
        };
    }

    /// <summary>A JSON scalar as the CLR value <see cref="RowComparer"/> reads for <paramref name="type"/>.</summary>
    private static object? ScalarOrNull(JsonElement raw, FieldType type)
    {
        if (raw.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        return type switch
        {
            FieldType.String => raw.ValueKind == JsonValueKind.String ? raw.GetString() : raw.GetRawText(),
            FieldType.Int64 => raw.ValueKind == JsonValueKind.Number ? raw.GetInt64() : long.Parse(raw.GetString()!, CultureInfo.InvariantCulture),
            FieldType.Decimal => decimal.Parse(raw.ValueKind == JsonValueKind.String ? raw.GetString()! : raw.GetRawText(), NumberStyles.Float, CultureInfo.InvariantCulture),
            FieldType.Double => raw.GetDouble(),
            FieldType.Boolean => raw.ValueKind switch
            {
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                _ => raw.GetString() == "true" || raw.GetRawText() == "1"
            },
            FieldType.Date or FieldType.Datetime => raw.GetString(),
            _ => throw new InvalidOperationException($"Unmapped FieldType '{type}'.")
        };
    }
}
