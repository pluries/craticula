using System.Text;
using System.Text.Json.Nodes;
using Craticula.Core;
using Craticula.Core.Ir;
using Craticula.Search;
using OpenSearch.Client;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client.Tests;

/// <summary>
/// FR-7 / FR-9 / TL-5 (#3794). OFFLINE: a recording in-memory connection plays the engine, so a recorded
/// <c>timed_out</c> answer and the request body's <c>timeout</c> are asserted without a cluster (run with
/// <c>dotnet test --filter OpenSearchQueryTimeLimitTests</c>; this project is excluded from the offline gate
/// because the rest of it needs a cluster).
/// </summary>
public sealed class OpenSearchQueryTimeLimitTests
{
    private sealed class Engine(bool timedOut) : InMemoryConnection
    {
        public List<JsonNode> Bodies { get; } = [];

        public override async Task<TResponse> RequestAsync<TResponse>(RequestData requestData, CancellationToken cancellationToken)
        {
            if (requestData.PostData is not null)
            {
                using var stream = new MemoryStream();
                requestData.PostData.Write(stream, requestData.ConnectionSettings);
                var text = Encoding.UTF8.GetString(stream.ToArray());
                if (text.Length > 0)
                {
                    Bodies.Add(JsonNode.Parse(text)!);
                }
            }

            var path = requestData.PathAndQuery;
            var body = path.Contains("point_in_time", StringComparison.Ordinal)
                ? "{\"pit_id\":\"pit-1\"}"
                : $"{{\"took\":3,\"timed_out\":{(timedOut ? "true" : "false")},\"hits\":{{\"hits\":[],\"total\":{{\"value\":0,\"relation\":\"eq\"}}}}}}";
            var inner = new InMemoryConnection(Encoding.UTF8.GetBytes(body), 200);
            return await inner.RequestAsync<TResponse>(requestData, cancellationToken).ConfigureAwait(false);
        }
    }

    private static IOpenSearchLowLevelClient ClientFor(Engine engine) =>
        new OpenSearchClient(new ConnectionSettings(new SingleNodeConnectionPool(new Uri("http://localhost:9200")), engine)).LowLevel;

    private static SearchQueryRequest Rows(int? limit)
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        return fixture.Request with { Page = new RangePage { StartRow = 0, EndRow = 100 }, MaxQueryTimeMs = limit };
    }

    [Fact]
    public async Task A_Timed_Out_Answer_Is_A_Query_Timeout_Exception_Never_A_Page()
    {
        var engine = new Engine(timedOut: true);

        await Assert.ThrowsAsync<QueryTimeoutException>(() =>
            OpenSearchGridQuery.FetchPageAsync(ClientFor(engine), Rows(2000), "s", new InMemorySearchCursorCache()));

        Assert.Equal("query-timeout", QueryTimeoutException.ErrorKind);
    }

    [Fact]
    public async Task A_Timed_Out_Answer_Is_An_Error_Even_When_No_Limit_Was_Configured()
    {
        var engine = new Engine(timedOut: true);

        await Assert.ThrowsAsync<QueryTimeoutException>(() =>
            OpenSearchGridQuery.FetchPageAsync(ClientFor(engine), Rows(null), "s", new InMemorySearchCursorCache()));
    }

    [Fact]
    public async Task An_Answer_That_Did_Not_Time_Out_Is_A_Normal_Page()
    {
        var engine = new Engine(timedOut: false);

        var page = await OpenSearchGridQuery.FetchPageAsync(ClientFor(engine), Rows(2000), "s", new InMemorySearchCursorCache());

        Assert.Empty(page.Rows);
    }

    [Fact]
    public async Task The_Search_Body_Carries_The_Timeout_When_A_Limit_Is_Set()
    {
        var engine = new Engine(timedOut: false);

        await OpenSearchGridQuery.FetchPageAsync(ClientFor(engine), Rows(2000), "s", new InMemorySearchCursorCache());

        Assert.All(engine.Bodies, body => Assert.Equal("2000ms", (string?)body["timeout"]));
        Assert.NotEmpty(engine.Bodies);
    }

    [Fact]
    public async Task Without_A_Limit_No_Search_Body_Carries_A_Timeout()
    {
        var engine = new Engine(timedOut: false);

        await OpenSearchGridQuery.FetchPageAsync(ClientFor(engine), Rows(null), "s", new InMemorySearchCursorCache());

        Assert.All(engine.Bodies, body => Assert.Null(body["timeout"]));
    }

    [Fact]
    public async Task An_Export_Never_Carries_The_Timeout_Even_When_A_Limit_Is_Set()
    {
        var engine = new Engine(timedOut: false);
        var request = Rows(2000) with { Page = new NonePage() };

        await foreach (var _ in OpenSearchExportStream.StreamAsync(ClientFor(engine), request))
        {
        }

        Assert.NotEmpty(engine.Bodies);
        Assert.All(engine.Bodies, body => Assert.Null(body["timeout"]));
    }

    [Fact]
    public async Task A_Timed_Out_Export_Chunk_Is_An_Error_Not_A_Silently_Short_Export()
    {
        var engine = new Engine(timedOut: true);
        var request = Rows(null) with { Page = new NonePage() };

        await Assert.ThrowsAsync<QueryTimeoutException>(async () =>
        {
            await foreach (var _ in OpenSearchExportStream.StreamAsync(ClientFor(engine), request))
            {
            }
        });
    }
}
