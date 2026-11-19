using Craticula.Core.Ir;
using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Oracle;
using Craticula.Search;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>Skeleton (T017): the live OpenSearch / Elasticsearch adapter of the count check.</summary>
internal sealed class SearchCountEngine(HttpClient http, string engineName) : ICountParityEngine
{
    internal const int GroupWindow = 1000;

    public string Backend => EngineNames.Search;

    public string? Engine => engineName;

    public Task<CountParityRun> RunAsync(ExecutionFixture fixture) =>
        http is null ? throw new ArgumentNullException(nameof(http)) : throw new NotImplementedException();

    internal static void RefuseGroupedUntilD006(PreparedRequest own) => throw new NotImplementedException();

    internal static PageSpec UnpagedPageFor(PreparedRequest own) => throw new NotImplementedException();

    internal static SearchQuery CompileCount(PreparedRequest request) => throw new NotImplementedException();
}
