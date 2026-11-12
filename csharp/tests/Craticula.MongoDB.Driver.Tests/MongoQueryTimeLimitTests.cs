using Craticula.Core;
using Craticula.Core.Ir;
using Craticula.Mongo;
using MongoDB.Bson;

namespace Craticula.MongoDB.Driver.Tests;

/// <summary>TL-5 / FR-6 (#3794) against a real MongoDB: the compiled <c>maxTimeMS</c> reaches the
/// server, and "maximum time expired" (code 50) comes back as <see cref="QueryTimeoutException"/>.</summary>
public sealed class MongoQueryTimeLimitTests
{
    private const int Documents = 60_000;

    private static List<BsonDocument> LargeCollection()
    {
        var filler = new string('x', 400);
        var documents = new List<BsonDocument>(Documents);
        for (var id = 1L; id <= Documents; id++)
        {
            documents.Add(new BsonDocument
            {
                ["_id"] = id,
                ["orderDate"] = BsonNull.Value,
                ["customer"] = new BsonDocument { ["name"] = filler },
                ["totalAmount"] = BsonNull.Value,
                ["status"] = filler,
                ["region"] = filler,
                ["notes"] = filler
            });
        }

        return documents;
    }

    private static MongoQueryRequest ScanRequest(Craticula.Core.Schema.GridSchema schema, int? limit) => new()
    {
        Schema = schema,
        Filter = new ComparisonNode
        {
            Field = "notes",
            Op = ComparisonOperator.Contains,
            Value = new StringValue { Value = "never-present-needle" }
        },
        Page = new RangePage { StartRow = 0, EndRow = 100 },
        MaxQueryTimeMs = limit
    };

    private static FixtureRequest Fixture() =>
        FixtureRequest.Load("page-export", FixtureRequest.ResolveDirectory("page-export", "008"));

    [Fact]
    public async Task A_Query_That_Runs_Out_Of_Time_Is_A_Query_Timeout_Exception()
    {
        await using var database = await MongoFixtureDatabase.CreateAsync(Fixture().Schema, LargeCollection());

        var clock = System.Diagnostics.Stopwatch.StartNew();
        var ex = await Assert.ThrowsAsync<QueryTimeoutException>(
            () => MongoGridQuery.FetchPageAsync(database.Database, ScanRequest(database.Schema, 1)));
        clock.Stop();

        // SC-1: cancelled by the server within the limit plus two seconds.
        Assert.True(clock.Elapsed < TimeSpan.FromMilliseconds(1 + 2000), $"took {clock.Elapsed}");
        Assert.Equal("query-timeout", QueryTimeoutException.ErrorKind);
        Assert.DoesNotContain("never-present-needle", ex.Message);
    }

    [Fact]
    public async Task The_Row_Count_Honours_The_Limit_Too()
    {
        await using var database = await MongoFixtureDatabase.CreateAsync(Fixture().Schema, LargeCollection());

        await Assert.ThrowsAsync<QueryTimeoutException>(
            () => MongoGridQuery.CountAsync(database.Database, ScanRequest(database.Schema, 1)));
    }

    [Fact]
    public async Task Without_A_Limit_The_Same_Query_Completes()
    {
        await using var database = await MongoFixtureDatabase.CreateAsync(Fixture().Schema, LargeCollection());

        var page = await MongoGridQuery.FetchPageAsync(database.Database, ScanRequest(database.Schema, null));

        Assert.Empty(page.Rows);
    }

    [Fact]
    public async Task A_Generous_Limit_Does_Not_Cut_A_Quick_Query()
    {
        await using var database = await MongoFixtureDatabase.CreateAsync(Fixture().Schema, Datasets.ExportableOrders());

        var page = await MongoGridQuery.FetchPageAsync(
            database.Database,
            new MongoQueryRequest
            {
                Schema = database.Schema,
                Page = new RangePage { StartRow = 0, EndRow = 100 },
                MaxQueryTimeMs = 30_000
            });

        Assert.Equal(5, page.Rows.Count);
    }
}
