using System.Text.Json;
using System.Text.Json.Nodes;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Reads the count out of a Search count response (FR-005, FR-006, CNT-7).</summary>
internal static class SearchCountReader
{
    public const int CardinalityPrecisionThreshold = 3000;

    private const string Hits = "hits";
    private const string Total = "total";
    private const string Value = "value";
    private const string Relation = "relation";
    private const string Exact = "eq";
    private const string Aggregations = "aggregations";
    private const string BucketCount = "bucket_count";
    private const string MissingGroupValues = "missing_group_values";
    private const string DocCount = "doc_count";
    private const string Buckets = "buckets";

    /// <summary>No cardinality-threshold check here: it lives in <see cref="AssertCardinalityBelowThreshold"/>, which the engine calls on the count response.</summary>
    public static long Read(JsonElement root, bool grouped) => grouped ? ReadGrouped(root) : ReadFlat(root);

    private static long ReadFlat(JsonElement root)
    {
        var total = root.GetProperty(Hits).GetProperty(Total);
        var relation = total.GetProperty(Relation).GetString();
        if (relation != Exact)
        {
            throw new InvalidOperationException($"The engine reported the total as a lower bound (relation '{relation}'), not a count.");
        }

        return total.GetProperty(Value).GetInt64();
    }

    private static long ReadGrouped(JsonElement root)
    {
        var aggregations = root.GetProperty(Aggregations);
        var groups = aggregations.GetProperty(BucketCount).GetProperty(Value).GetInt64();
        var missing = aggregations.GetProperty(MissingGroupValues).GetProperty(DocCount).GetInt64();
        return missing > 0 ? groups + 1 : groups;
    }

    /// <summary>
    /// US2-AS6, FR-007a: the group window must hold every group. The page response of a grouped level carries no
    /// <c>bucket_count</c>, so the cardinality check runs here only when the response has one (the engine runs it on the
    /// count response through <see cref="AssertCardinalityBelowThreshold"/>).
    /// </summary>
    public static void AssertGroupWindowComplete(JsonElement root, string groupColumn, int window)
    {
        var aggregations = root.GetProperty(Aggregations);
        if (aggregations.TryGetProperty(BucketCount, out _))
        {
            AssertCardinalityBelowThreshold(root);
        }

        var returned = aggregations.GetProperty(groupColumn).GetProperty(Buckets).GetArrayLength();
        if (returned >= window)
        {
            throw new InvalidOperationException(
                $"The group window of {window} returned {returned} buckets for '{groupColumn}': further groups may not all have been read, so the unpaged rows are not a complete list (FR-007a).");
        }
    }

    /// <summary>US2-AS6: a cardinality at the precision threshold is an estimate, not a count.</summary>
    public static void AssertCardinalityBelowThreshold(JsonElement root)
    {
        var groups = root.GetProperty(Aggregations).GetProperty(BucketCount).GetProperty(Value).GetInt64();
        if (groups >= CardinalityPrecisionThreshold)
        {
            throw new InvalidOperationException(
                $"The group count {groups} reaches the cardinality precision threshold of {CardinalityPrecisionThreshold}: the engine's figure is no longer exact (US2-AS6).");
        }
    }
}

/// <summary>The compiled count body plus the exact-total member.</summary>
internal static class SearchCountBody
{
    public const string TrackTotalHitsKey = "track_total_hits";

    public static JsonObject WithExactTotal(JsonObject compiled)
    {
        ArgumentNullException.ThrowIfNull(compiled);
        if (compiled.ContainsKey(TrackTotalHitsKey))
        {
            throw new InvalidOperationException($"The compiled count body already sets '{TrackTotalHitsKey}'; the harness must not overwrite it silently.");
        }

        var sent = (JsonObject)compiled.DeepClone();
        sent[TrackTotalHitsKey] = true;
        return sent;
    }
}
