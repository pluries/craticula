using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Docker;

namespace Craticula.Integration.Tests.Containers.Document;

// Story #3863 on the Search engines (US2, FR-002). The static MemberData methods use the EngineNames constants, which equal the
// fixtures' EngineName ("opensearch", "elasticsearch"): a static method cannot read the primary-constructor parameter.
// The grouped levels are parked (D-006): one skipped test per class stands for them until the owner decides.

/// <summary>OpenSearch 2.x: the non-grouped fixtures.</summary>
[Collection(OpenSearchCollection.Name)]
public sealed class OpenSearchCountParityTests(OpenSearchEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.OpenSearch, grouped: false);

    public static TheoryData<string> GroupedFixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.OpenSearch, grouped: true);

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_OpenSearch(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new SearchCountEngine(engine.Require(), engine.EngineName), name);

    [Theory(Skip = "PARKED D-006: a grouped Search level needs the unpaged window (OSE-11(d)); see decisions.md D-006")]
    [MemberData(nameof(GroupedFixtures))]
    public void Grouped_Count_Is_Not_Compared_Until_D006(string name) => Assert.NotNull(name);
}

/// <summary>Elasticsearch 8.x: the same fixtures, one artifact for two engines (OQ-7).</summary>
[Collection(ElasticsearchCollection.Name)]
public sealed class ElasticsearchCountParityTests(ElasticsearchEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.Elasticsearch, grouped: false);

    public static TheoryData<string> GroupedFixtures() => CountedFixtures.TheoryDataFor(EngineNames.Search, EngineNames.Elasticsearch, grouped: true);

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_Elasticsearch(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new SearchCountEngine(engine.Require(), engine.EngineName), name);

    [Theory(Skip = "PARKED D-006: a grouped Search level needs the unpaged window (OSE-11(d)); see decisions.md D-006")]
    [MemberData(nameof(GroupedFixtures))]
    public void Grouped_Count_Is_Not_Compared_Until_D006(string name) => Assert.NotNull(name);
}
