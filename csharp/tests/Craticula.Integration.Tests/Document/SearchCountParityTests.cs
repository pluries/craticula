using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Docker;

namespace Craticula.Integration.Tests.Containers.Document;

// Story #3863 on the Search engines (US2, FR-002). The static MemberData methods use the EngineNames constants, which equal the
// fixtures' EngineName ("opensearch", "elasticsearch"): a static method cannot read the primary-constructor parameter.
// The grouped levels are read through the group window (FR-007a, OSE-11(d)) and compared like any other.

/// <summary>OpenSearch 2.x: every counted fixture, grouped levels included.</summary>
[Collection(OpenSearchCollection.Name)]
public sealed class OpenSearchCountParityTests(OpenSearchEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.OpenSearch, grouped: null);

    // US2-AS1, US2-AS8 (the export fixtures are counted like any other); US3-AS4 via [DockerTheory].

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_OpenSearch(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new SearchCountEngine(engine.Require(), engine.EngineName), name);
}

/// <summary>Elasticsearch 8.x: the same fixtures, one artifact for two engines (OQ-7).</summary>
[Collection(ElasticsearchCollection.Name)]
public sealed class ElasticsearchCountParityTests(ElasticsearchEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.Elasticsearch, grouped: null);

    // US2-AS2 (the same rule on Elasticsearch 8.17), US2-AS8; US3-AS4 via [DockerTheory].

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Elasticsearch(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new SearchCountEngine(engine.Require(), engine.EngineName), name);
}
