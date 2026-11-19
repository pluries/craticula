using System.Text.Json;
using System.Text.Json.Nodes;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Skeleton (T015): reads the count out of a Search count response.</summary>
internal static class SearchCountReader
{
    public const int CardinalityPrecisionThreshold = 3000;

    public static long Read(JsonElement root, bool grouped) => throw new NotImplementedException();

    public static void AssertGroupWindowComplete(JsonElement root, string groupColumn, int window) => throw new NotImplementedException();
}

/// <summary>Skeleton (T015): the compiled count body plus the exact-total member.</summary>
internal static class SearchCountBody
{
    public const string TrackTotalHitsKey = "track_total_hits";

    public static JsonObject WithExactTotal(JsonObject compiled) => throw new NotImplementedException();
}
