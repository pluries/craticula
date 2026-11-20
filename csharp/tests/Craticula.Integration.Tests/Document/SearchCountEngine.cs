using System.Text.Json;
using Craticula.Core.Ir;
using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Oracle;
using Craticula.Search;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>
/// The live OpenSearch / Elasticsearch adapter of the count check: one seed into a fresh index, then the unpaged page request
/// and the compiled count body (CNT-7) on it. Both requests use the schema redirected to that index.
/// </summary>
internal sealed class SearchCountEngine(HttpClient http, string engineName) : ICountParityEngine
{
    // ResourceLimits.MaxPageSize's default (SEC-3), the widest RangePage the compiler accepts; the library exposes it only as an instance property.
    internal const int GroupWindow = 1000;

    public string Backend => EngineNames.Search;

    public string? Engine => engineName;

    public async Task<CountParityRun> RunAsync(ExecutionFixture fixture)
    {
        ArgumentNullException.ThrowIfNull(fixture);
        var index = "cnt_" + Guid.NewGuid().ToString("N");
        try
        {
            await SearchEngine.SeedAsync(http, index, fixture).ConfigureAwait(false);
            var unpaged = await ReadUnpaged(fixture, index).ConfigureAwait(false);
            var (count, countedQuery) = await ReadCount(fixture, index).ConfigureAwait(false);
            return new CountParityRun(count, unpaged, countedQuery);
        }
        finally
        {
            await CleanUpAsync(index).ConfigureAwait(false);
        }
    }

    /// <summary>FR-007a: a grouped level cannot compile without a window, so it is read through one of <see cref="GroupWindow"/> groups.</summary>
    internal static PageSpec UnpagedPageFor(PreparedRequest own)
    {
        ArgumentNullException.ThrowIfNull(own);
        return own.Plan is { GroupColumn: not null }
            ? new RangePage { StartRow = 0, EndRow = GroupWindow }
            : new NonePage();
    }

    internal static SearchQuery CompileCount(PreparedRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        try
        {
            var parsed = request.Parsed!;
            return SearchQueryBuilder.BuildCount(new SearchQueryRequest
            {
                Schema = request.Schema,
                Filter = request.Filter,
                Page = new NonePage(),
                Group = parsed.Group,
                Aggregations = parsed.Aggregations
            });
        }
        catch (SearchCompilationException exception)
        {
            throw new EngineRefusedException($"The Search compiler refused the request: {exception.Message}", exception);
        }
    }

    private async Task<int> ReadUnpaged(ExecutionFixture fixture, string index)
    {
        var schema = fixture.Schema with { Source = index };
        var own = PreparedRequest.For(fixture, schema);
        var request = PreparedRequest.For(fixture, schema, UnpagedPageFor(own));
        var groupColumn = own.Plan?.GroupColumn;
        Action<JsonElement>? inspect = groupColumn is null
            ? null
            : root => SearchCountReader.AssertGroupWindowComplete(root, groupColumn, GroupWindow);
        var rows = await SearchEngine.QueryAsync(http, index, fixture, request, inspect).ConfigureAwait(false);
        return rows.Rows.Count;
    }

    private async Task<(long? Count, string Query)> ReadCount(ExecutionFixture fixture, string index)
    {
        var prepared = PreparedRequest.For(fixture, fixture.Schema with { Source = index }, new NonePage());
        var body = SearchCountBody.WithExactTotal(CompileCount(prepared).ToArtifact());
        var response = await SearchEngine.SearchAsync(http, index, body).ConfigureAwait(false);
        using var document = JsonDocument.Parse(response);
        var grouped = prepared.Plan is { GroupColumn: not null };
        if (grouped)
        {
            SearchCountReader.AssertCardinalityBelowThreshold(document.RootElement);
        }

        return (SearchCountReader.Read(document.RootElement, grouped), body.ToJsonString());
    }

    private async Task CleanUpAsync(string index)
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
