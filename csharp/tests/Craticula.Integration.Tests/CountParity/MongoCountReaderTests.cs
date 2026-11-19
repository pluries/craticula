using MongoDB.Bson;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Reads the one document a MongoDB count pipeline returns (US1-AS2, FR-004).</summary>
public sealed class MongoCountReaderTests
{
    private const string CountField = "count";

    // US1-AS2: a missing collection or an empty result sends no document; the caller reads that as 0
    [Fact]
    public void No_Result_Document_Reads_As_Null()
    {
        Assert.Null(MongoCountReader.Read([]));
    }

    // US1-AS2: the driver returns the count as Int32 or Int64 depending on its size
    [Fact]
    public void One_Document_Reads_Its_Count_Field()
    {
        Assert.Equal(7L, MongoCountReader.Read([new BsonDocument(CountField, new BsonInt32(7))]));
        Assert.Equal(5_000_000_000L, MongoCountReader.Read([new BsonDocument(CountField, new BsonInt64(5_000_000_000L))]));
    }

    // The contract: a count pipeline never returns two documents, so two are an error (InvalidOperationException), not a guess
    [Fact]
    public void More_Than_One_Document_Fails()
    {
        BsonDocument[] results = [new BsonDocument(CountField, 1), new BsonDocument(CountField, 2)];

        Assert.Throws<InvalidOperationException>(() => MongoCountReader.Read(results));
    }
}
