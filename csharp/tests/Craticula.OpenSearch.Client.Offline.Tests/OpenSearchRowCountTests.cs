using System.Text;
using System.Text.Json.Nodes;
using Craticula.Core.Ir;
using OpenSearch.Client;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client.Offline.Tests;

/// <summary>
/// OSE-16 / #2524: the row count above <c>max_result_window</c> is unknown by default and exact when the host opts in. OFFLINE: a recording
/// in-memory connection plays the engine and answers every search with an empty page and a configured <c>hits.total</c>, so the
/// count request's <c>track_total_hits</c> and the way the answer is read are asserted without a cluster (run with
/// <c>dotnet test --filter OpenSearchRowCountTests</c>; this project is excluded from the offline gate because the rest of it needs a cluster).
/// </summary>
public sealed class OpenSearchRowCountTests
{
    private sealed class CountingEngine(long total, string relation) : InMemoryConnection
    {
        public List<JsonNode> Bodies { get; } = [];

        public override async Task<TResponse> RequestAsync<TResponse>(RequestData requestData, CancellationToken cancellationToken)
        {
            if (requestData.PostData is not null)
            {
                using var stream = new MemoryStream();
                requestData.PostData.Write(stream, requestData.ConnectionSettings);
                Bodies.Add(JsonNode.Parse(Encoding.UTF8.GetString(stream.ToArray()))!);
            }

            var body = $"{{\"hits\":{{\"hits\":[],\"total\":{{\"value\":{total},\"relation\":\"{relation}\"}}}}}}";
            var inner = new InMemoryConnection(Encoding.UTF8.GetBytes(body), 200);
            return await inner.RequestAsync<TResponse>(requestData, cancellationToken).ConfigureAwait(false);
        }
    }

    private static async Task<(long? RowCount, JsonNode CountBody)> CountAsync(long total, string relation, OpenSearchDeepPagingOptions? options)
    {
        var engine = new CountingEngine(total, relation);
        IOpenSearchLowLevelClient client =
            new OpenSearchClient(new ConnectionSettings(new SingleNodeConnectionPool(new Uri("http://localhost:9200")), engine)).LowLevel;
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var request = fixture.Request with { Page = new RangePage { StartRow = 0, EndRow = 100 } };

        var page = await OpenSearchGridQuery.FetchPageAsync(
            client, request, "session-1", new InMemorySearchCursorCache(), options, includeRowCount: true);

        return (page.RowCount, engine.Bodies.Single(body => body["track_total_hits"] is not null));
    }

    [Fact]
    public async Task By_Default_The_Count_Is_Capped_At_The_Window_And_Unknown_Above_It()
    {
        var (rowCount, body) = await CountAsync(10_000, "gte", options: null);

        Assert.Equal(10_000, body["track_total_hits"]!.GetValue<int>());
        Assert.Null(rowCount);
    }

    [Fact]
    public async Task By_Default_A_Count_Below_The_Window_Is_Exact()
    {
        var (rowCount, body) = await CountAsync(137, "eq", options: null);

        Assert.Equal(10_000, body["track_total_hits"]!.GetValue<int>());
        Assert.Equal(137, rowCount);
    }

    [Fact]
    public async Task With_ExactRowCount_The_Count_Request_Asks_For_Every_Hit_And_The_Total_Is_Reported()
    {
        var (rowCount, body) = await CountAsync(19_425, "eq", new OpenSearchDeepPagingOptions { ExactRowCount = true });

        Assert.True(body["track_total_hits"]!.GetValue<bool>());
        Assert.Equal(19_425, rowCount);
    }

    [Fact]
    public async Task ExactRowCount_Changes_Only_The_Count_Request()
    {
        var (_, exactBody) = await CountAsync(19_425, "eq", new OpenSearchDeepPagingOptions { ExactRowCount = true });
        var (_, cappedBody) = await CountAsync(19_425, "eq", options: null);

        exactBody["track_total_hits"] = cappedBody["track_total_hits"]!.DeepClone();
        Assert.Equal(cappedBody.ToJsonString(), exactBody.ToJsonString());
    }
}
