using System.Text.Json.Nodes;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>The exact-total member is the only difference between the compiled count body and the one sent (US3-AS6, US2-AS4).</summary>
public sealed class SearchCountBodyTests
{
    private const string Compiled = """{"size":0,"query":{"match_all":{}},"aggs":{"bucket_count":{"cardinality":{"field":"region"}}}}""";

    // US3-AS6, FR-006
    [Fact]
    public void The_Body_Is_The_Compiled_Count_Plus_Only_The_Exact_Total()
    {
        var compiled = (JsonObject)JsonNode.Parse(Compiled)!;

        var sent = SearchCountBody.WithExactTotal(compiled);

        Assert.True(sent[SearchCountBody.TrackTotalHitsKey]!.GetValue<bool>());
        var withoutTheMember = (JsonObject)sent.DeepClone();
        withoutTheMember.Remove(SearchCountBody.TrackTotalHitsKey);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(Compiled), withoutTheMember));
        Assert.False(compiled.ContainsKey(SearchCountBody.TrackTotalHitsKey));
    }

    // US2-AS4: a compiler that starts setting the member itself must not be overwritten silently (InvalidOperationException)
    [Fact]
    public void A_Body_That_Already_Sets_The_Total_Fails()
    {
        var compiled = (JsonObject)JsonNode.Parse(Compiled)!;
        compiled[SearchCountBody.TrackTotalHitsKey] = false;

        Assert.Throws<InvalidOperationException>(() => SearchCountBody.WithExactTotal(compiled));
    }
}
