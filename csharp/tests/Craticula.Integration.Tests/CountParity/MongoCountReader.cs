using MongoDB.Bson;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Reads the count the compiled MongoDB count pipeline returns (CNT-6).</summary>
internal static class MongoCountReader
{
    /// <summary>Null when MongoDB sent no document (nothing matched, or no collection); the caller reads that as 0 (FR-004).</summary>
    public static long? Read(IReadOnlyList<BsonDocument> results)
    {
        ArgumentNullException.ThrowIfNull(results);
        if (results.Count == 0)
        {
            return null;
        }

        if (results.Count > 1)
        {
            throw new InvalidOperationException($"A count pipeline returns at most one document, got {results.Count}.");
        }

        return results[0]["count"].ToInt64();
    }
}
