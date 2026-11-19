using Craticula.Integration.Tests.CountParity;
using Craticula.Integration.Tests.Oracle;
using Craticula.Mongo;
using MongoDB.Driver;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>Skeleton (T012): the live MongoDB adapter of the count check.</summary>
internal sealed class MongoCountEngine(IMongoClient client) : ICountParityEngine
{
    public string Backend => EngineNames.Mongo;

    public string? Engine => null;

    public Task<CountParityRun> RunAsync(ExecutionFixture fixture) =>
        client is null ? throw new ArgumentNullException(nameof(client)) : throw new NotImplementedException();

    internal static MongoQuery CompileCount(PreparedRequest request) => throw new NotImplementedException();
}
