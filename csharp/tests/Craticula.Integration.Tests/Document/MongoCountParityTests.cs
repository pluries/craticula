using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Docker;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>Story #3863 on MongoDB 7.0: the count equals the number of rows the same request returns without a window (US1, FR-001).</summary>
[Collection(MongoCollection.Name)]
public sealed class MongoCountParityTests(MongoEngineFixture engine)
{
    public static TheoryData<string> Fixtures() => CountedFixtures.TheoryDataFor(EngineNames.Mongo, null);

    [DockerTheory]
    [MemberData(nameof(Fixtures))]
    public Task Count_Equals_The_Unpaged_Rows_On_MongoDb(string name) =>
        CountComparison.AssertCountEqualsUnpagedRowsAsync(new MongoCountEngine(engine.Require()), name);
}
