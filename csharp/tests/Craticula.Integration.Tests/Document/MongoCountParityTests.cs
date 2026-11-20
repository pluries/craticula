using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Docker;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>Story #3863 on MongoDB 7.0: the count equals the number of rows the same request returns without a window (US1, FR-001).</summary>
[Collection(MongoCollection.Name)]
public sealed class MongoCountParityTests(MongoEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Mongo, null);

    // US1-AS1, US1-AS3 (grouped levels are in the data); US3-AS4: skipped with a reason when Docker is down ([DockerTheory]).

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_MongoDb(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new MongoCountEngine(engine.Require()), name);
}
