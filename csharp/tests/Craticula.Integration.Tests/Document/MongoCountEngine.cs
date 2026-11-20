using System.Text.Json.Nodes;
using Craticula.Core.Ir;
using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Oracle;
using Craticula.Mongo;
using MongoDB.Bson;
using MongoDB.Driver;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>
/// The live MongoDB adapter of the count check: one seed, then the unpaged page request and the compiled count pipeline
/// (CNT-6) on the same collection. The schema is used as is, no source redirect (the database is per fixture).
/// </summary>
internal sealed class MongoCountEngine(IMongoClient client) : ICountParityEngine
{
    public string Backend => EngineNames.Mongo;

    public string? Engine => null;

    public async Task<CountParityRun> RunAsync(ExecutionFixture fixture)
    {
        ArgumentNullException.ThrowIfNull(fixture);
        var databaseName = "cnt_" + Guid.NewGuid().ToString("N");
        try
        {
            var collection = await MongoEngine.SeedAsync(client, databaseName, fixture).ConfigureAwait(false);
            var unpaged = await ReadUnpaged(collection, fixture).ConfigureAwait(false);
            var (count, countedQuery) = await ReadCount(collection, fixture).ConfigureAwait(false);
            return new CountParityRun(count, unpaged, countedQuery);
        }
        finally
        {
            await CleanUpAsync(databaseName).ConfigureAwait(false);
        }
    }

    internal static MongoQuery CompileCount(PreparedRequest request)
    {
        try
        {
            var parsed = request.Parsed!;
            return MongoPipelineBuilder.BuildCount(new MongoQueryRequest
            {
                Schema = request.Schema,
                Filter = request.Filter,
                Page = parsed.Page,
                Group = parsed.Group,
                Aggregations = parsed.Aggregations
            });
        }
        catch (MongoCompilationException exception)
        {
            throw new EngineRefusedException($"The Mongo compiler refused the request: {exception.Message}", exception);
        }
    }

    private static async Task<int> ReadUnpaged(IMongoCollection<BsonDocument> collection, ExecutionFixture fixture)
    {
        var request = PreparedRequest.For(fixture, fixture.Schema, new NonePage());
        var rows = await MongoEngine.QueryAsync(collection, fixture, request).ConfigureAwait(false);
        return rows.Rows.Count;
    }

    private static async Task<(long? Count, string Query)> ReadCount(IMongoCollection<BsonDocument> collection, ExecutionFixture fixture)
    {
        var query = CompileCount(PreparedRequest.For(fixture, fixture.Schema, new NonePage()));
        var results = await MongoEngine.AggregateAsync(collection, query).ConfigureAwait(false);
        return (MongoCountReader.Read(results), query.ToArtifact().ToJsonString());
    }

    private Task CleanUpAsync(string databaseName) => client.DropDatabaseAsync(databaseName);
}
