using System.Text;
using Craticula.Core.Ir;
using OpenSearch.Client;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client.Offline.Tests;

/// <summary>
/// OSE-15 / #2559: the point-in-time lifecycle of both engines. OFFLINE: a recording in-memory connection plays the
/// engine, so the exact calls the client makes are asserted without a cluster (run with
/// <c>dotnet test --filter SearchEngineFlavourTests</c>; like the neighbouring status tests, this project is
/// excluded from the offline suite because the rest of it needs a live cluster).
/// </summary>
public sealed class SearchEngineFlavourTests
{
    private sealed record Call(string Method, string Path, string? Body, string Url);

    /// <summary>Answers the create call with the engine's own key, the close with 200 and every search with no hits.</summary>
    private sealed class RecordingEngine(string createdKey) : InMemoryConnection
    {
        public List<Call> Calls { get; } = [];

        public override async Task<TResponse> RequestAsync<TResponse>(RequestData requestData, CancellationToken cancellationToken)
        {
            var path = requestData.PathAndQuery;
            string? sent = null;
            if (requestData.PostData is not null)
            {
                using var stream = new MemoryStream();
                requestData.PostData.Write(stream, requestData.ConnectionSettings);
                sent = Encoding.UTF8.GetString(stream.ToArray());
            }

            Calls.Add(new Call(requestData.Method.ToString(), path, sent, requestData.Uri.ToString()));

            var isCreate = requestData.Method == global::OpenSearch.Net.HttpMethod.POST && (path.Contains("point_in_time", StringComparison.Ordinal) || path.Contains("/_pit", StringComparison.Ordinal));
            var body = isCreate
                ? $"{{\"{createdKey}\":\"pit-1\"}}"
                : "{\"hits\":{\"hits\":[],\"total\":{\"value\":0,\"relation\":\"eq\"}}}";
            var inner = new InMemoryConnection(Encoding.UTF8.GetBytes(body), 200);
            return await inner.RequestAsync<TResponse>(requestData, cancellationToken).ConfigureAwait(false);
        }
    }

    private static IOpenSearchLowLevelClient ClientOn(RecordingEngine engine, string baseUrl = "http://localhost:9200") =>
        new OpenSearchClient(new ConnectionSettings(new SingleNodeConnectionPool(new Uri(baseUrl)), engine)).LowLevel;

    private static async Task ExportAsync(IOpenSearchLowLevelClient client, SearchEngineFlavour? flavour)
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var request = fixture.Request with { Page = new NonePage() };
        var options = flavour is { } f ? new OpenSearchExportOptions { Flavour = f } : null;
        await foreach (var _ in OpenSearchExportStream.StreamAsync(client, request, options))
        {
        }
    }

    private static async Task DeepPageAsync(IOpenSearchLowLevelClient client, SearchEngineFlavour? flavour)
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var request = fixture.Request with { Page = new RangePage { StartRow = 10_000, EndRow = 10_100 } };
        var options = flavour is { } f ? new OpenSearchDeepPagingOptions { Flavour = f } : null;
        await OpenSearchGridQuery.FetchPageAsync(client, request, "session-1", new InMemorySearchCursorCache(), options);
    }

    [Fact]
    public async Task Export_On_The_Default_Flavour_Uses_The_OpenSearch_Point_In_Time_Calls()
    {
        var engine = new RecordingEngine("pit_id");
        await ExportAsync(ClientOn(engine), flavour: null);

        var create = Assert.Single(engine.Calls, c => c.Method == "POST" && c.Path.Contains("point_in_time", StringComparison.Ordinal));
        Assert.Contains("keep_alive=", create.Path, StringComparison.Ordinal);
        var close = Assert.Single(engine.Calls, c => c.Method == "DELETE");
        Assert.Contains("point_in_time", close.Path, StringComparison.Ordinal);
        Assert.Equal("{\"pit_id\":[\"pit-1\"]}", close.Body);
    }

    [Fact]
    public async Task Export_On_The_Elasticsearch_Flavour_Uses_The_Pit_Calls_And_The_Id_Key()
    {
        var engine = new RecordingEngine("id");
        await ExportAsync(ClientOn(engine), SearchEngineFlavour.Elasticsearch);

        var create = Assert.Single(engine.Calls, c => c.Method == "POST" && c.Path.Contains("_pit", StringComparison.Ordinal));
        Assert.Matches(@"^/?[^/]+/_pit\?keep_alive=\d+[smh]$", create.Path);
        Assert.DoesNotContain(engine.Calls, c => c.Path.Contains("point_in_time", StringComparison.Ordinal));
        var close = Assert.Single(engine.Calls, c => c.Method == "DELETE");
        Assert.EndsWith("/_pit", close.Url, StringComparison.Ordinal);
        Assert.Equal("{\"id\":\"pit-1\"}", close.Body);

        var search = Assert.Single(engine.Calls, c => c.Method == "POST" && c.Path.Contains("_search", StringComparison.Ordinal));
        Assert.Contains("\"id\":\"pit-1\"", search.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Deep_Paging_On_The_Elasticsearch_Flavour_Opens_And_Closes_The_Pit_The_Elasticsearch_Way()
    {
        var engine = new RecordingEngine("id");
        await DeepPageAsync(ClientOn(engine), SearchEngineFlavour.Elasticsearch);

        Assert.Single(engine.Calls, c => c.Method == "POST" && c.Path.Contains("_pit", StringComparison.Ordinal));
        Assert.DoesNotContain(engine.Calls, c => c.Path.Contains("point_in_time", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Deep_Paging_On_The_Default_Flavour_Opens_The_Pit_The_OpenSearch_Way()
    {
        var engine = new RecordingEngine("pit_id");
        await DeepPageAsync(ClientOn(engine), flavour: null);

        Assert.Single(engine.Calls, c => c.Method == "POST" && c.Path.Contains("point_in_time", StringComparison.Ordinal));
        Assert.DoesNotContain(engine.Calls, c => c.Path.Contains("_pit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task The_Elasticsearch_Flavour_Against_An_Answer_Without_An_Id_Key_Fails_Loudly()
    {
        var engine = new RecordingEngine("pit_id");
        await Assert.ThrowsAnyAsync<Exception>(() => ExportAsync(ClientOn(engine), SearchEngineFlavour.Elasticsearch));
    }

    [Fact]
    public async Task The_Elasticsearch_Flavour_Keeps_A_Base_Path_In_The_Cluster_Url()
    {
        var engine = new RecordingEngine("id");
        await ExportAsync(ClientOn(engine, "http://proxy:9200/es/"), SearchEngineFlavour.Elasticsearch);

        Assert.StartsWith("http://proxy:9200/es/", engine.Calls.Single(c => c.Method == "POST" && c.Path.Contains("_pit", StringComparison.Ordinal)).Url, StringComparison.Ordinal);
        Assert.Equal("http://proxy:9200/es/_pit", engine.Calls.Single(c => c.Method == "DELETE").Url);
    }

    [Fact]
    public async Task A_Flavour_Outside_The_Enum_Is_Refused_Before_Any_Call()
    {
        var engine = new RecordingEngine("pit_id");
        await Assert.ThrowsAsync<OpenSearchClientCompilationException>(() => ExportAsync(ClientOn(engine), (SearchEngineFlavour)7));
        Assert.Empty(engine.Calls);
    }
}
