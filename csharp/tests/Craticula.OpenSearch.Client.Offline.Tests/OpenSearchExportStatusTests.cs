using System.Text;
using Craticula.Core.Ir;
using OpenSearch.Client;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client.Offline.Tests;

/// <summary>
/// Bug #2523: <c>OpenSearchExportStream</c> built its failure exception without the HTTP status that
/// <c>OpenSearchGridQuery</c> already passes, so a host could not tell an overloaded cluster (503/429: retry
/// later, answer "unavailable") from a bug (500). OFFLINE: the low-level client runs on an in-memory
/// connection that answers a fixed status, so no engine is needed (unlike the rest of this project, which is
/// excluded from the offline suite because it needs a live cluster; run these with
/// <c>dotnet test --filter OpenSearchExportStatusTests</c>).
/// </summary>
public sealed class OpenSearchExportStatusTests
{
    private static IOpenSearchLowLevelClient ClientAnswering(int status) =>
        new OpenSearchClient(new ConnectionSettings(
            new SingleNodeConnectionPool(new Uri("http://localhost:9200")),
            new InMemoryConnection(Encoding.UTF8.GetBytes("{\"error\":\"overloaded\"}"), status))).LowLevel;

    /// <summary>Answers 200 to the point-in-time calls (create and close) and <paramref name="searchStatus"/> to
    /// <c>_search</c>, so the failure happens on the second call of the export, after a PIT is open.</summary>
    private sealed class PitThenSearchFails(int searchStatus) : InMemoryConnection
    {
        public override async Task<TResponse> RequestAsync<TResponse>(RequestData requestData, CancellationToken cancellationToken)
        {
            var path = requestData.PathAndQuery;
            var (body, status) = path.Contains("_search", StringComparison.Ordinal) && !path.Contains("point_in_time", StringComparison.Ordinal)
                ? ("{\"error\":\"overloaded\"}", searchStatus)
                : ("{\"pit_id\":\"pit-1\"}", 200);
            var inner = new InMemoryConnection(Encoding.UTF8.GetBytes(body), status);
            return await inner.RequestAsync<TResponse>(requestData, cancellationToken).ConfigureAwait(false);
        }
    }

    private static async Task<OpenSearchClientCompilationException> ExportFailureAsync(IOpenSearchLowLevelClient client)
    {
        var fixture = FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));
        var request = fixture.Request with { Page = new NonePage() };
        return await Assert.ThrowsAsync<OpenSearchClientCompilationException>(async () =>
        {
            await foreach (var _ in OpenSearchExportStream.StreamAsync(client, request))
            {
            }
        });
    }

    private static Task<OpenSearchClientCompilationException> ExportFailureAsync(int status) =>
        ExportFailureAsync(ClientAnswering(status));

    [Theory]
    [InlineData(503)]
    [InlineData(429)]
    [InlineData(500)]
    [InlineData(404)]
    public async Task A_Failed_Export_Call_Carries_The_Http_Status_Of_The_Response(int status)
    {
        var failure = await ExportFailureAsync(status);

        Assert.Equal(status, failure.HttpStatusCode);
        Assert.Contains($"HTTP {status}", failure.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(503)]
    [InlineData(429)]
    public async Task A_Failed_Search_After_The_Pit_Is_Open_Carries_The_Status_And_The_Close_Does_Not_Hide_It(int status)
    {
        var client = new OpenSearchClient(new ConnectionSettings(
            new SingleNodeConnectionPool(new Uri("http://localhost:9200")), new PitThenSearchFails(status))).LowLevel;

        var failure = await ExportFailureAsync(client);

        Assert.Equal(status, failure.HttpStatusCode);
    }
}
