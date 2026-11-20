using System.Globalization;
using System.Text.Json;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Reads the count out of literal Search responses (US2-AS3, US2-AS4, FR-005, FR-006); <c>Read</c> has no threshold check.</summary>
public sealed class SearchCountReaderTests
{
    // US2-AS1: the flat count is the exact total
    [Fact]
    public void A_Flat_Count_Reads_The_Total()
    {
        using var response = JsonDocument.Parse("""{"hits":{"total":{"value":42,"relation":"eq"},"hits":[]}}""");

        Assert.Equal(42L, SearchCountReader.Read(response.RootElement, grouped: false));
    }

    // US2-AS4, FR-006: a lower-bound total is never a count (InvalidOperationException)
    [Fact]
    public void A_Total_That_Is_A_Lower_Bound_Fails()
    {
        using var response = JsonDocument.Parse("""{"hits":{"total":{"value":10000,"relation":"gte"},"hits":[]}}""");

        Assert.Throws<InvalidOperationException>(() => SearchCountReader.Read(response.RootElement, grouped: false));
    }

    // US2-AS3, FR-005, CNT-7: the cardinality counts the non-null groups, the missing bucket adds the null group
    [Theory]
    [InlineData(2, 5)]
    [InlineData(0, 4)]
    public void A_Grouped_Count_Adds_The_Null_Group(int missingDocuments, long expected)
    {
        var missing = missingDocuments.ToString(CultureInfo.InvariantCulture);
        using var response = JsonDocument.Parse(
            """{"aggregations":{"bucket_count":{"value":4},"missing_group_values":{"doc_count":""" + missing + "}}}");

        Assert.Equal(expected, SearchCountReader.Read(response.RootElement, grouped: true));
    }

    private const string GroupColumn = "category";
    private const int Window = 1000;

    private static string GroupedResponse(int cardinality, int buckets)
    {
        var items = string.Join(",", Enumerable.Range(0, buckets).Select(i => "{\"key\":{\"g\":" + i.ToString(CultureInfo.InvariantCulture) + "},\"doc_count\":1}"));
        return "{\"aggregations\":{\"bucket_count\":{\"value\":" + cardinality.ToString(CultureInfo.InvariantCulture)
            + "},\"" + GroupColumn + "\":{\"buckets\":[" + items + "]}}}";
    }

    // US2-AS6: a cardinality at the precision threshold (3000) is no longer exact, so it fails; one below passes
    [Fact]
    public void A_Cardinality_At_The_Threshold_Fails()
    {
        using var atThreshold = JsonDocument.Parse(GroupedResponse(SearchCountReader.CardinalityPrecisionThreshold, buckets: 3));
        using var below = JsonDocument.Parse(GroupedResponse(SearchCountReader.CardinalityPrecisionThreshold - 1, buckets: 3));

        var refusal = Assert.Throws<InvalidOperationException>(() =>
            SearchCountReader.AssertGroupWindowComplete(atThreshold.RootElement, GroupColumn, Window));
        Assert.Contains("precision threshold", refusal.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Null(Record.Exception(() => SearchCountReader.AssertGroupWindowComplete(below.RootElement, GroupColumn, Window)));
    }

    // FR-007a: as many buckets as the window may hide further groups, so it fails
    [Fact]
    public void A_Full_Group_Window_Fails()
    {
        using var response = JsonDocument.Parse(GroupedResponse(cardinality: 1000, buckets: Window));

        var refusal = Assert.Throws<InvalidOperationException>(() =>
            SearchCountReader.AssertGroupWindowComplete(response.RootElement, GroupColumn, Window));
        Assert.Contains("may not all have been read", refusal.Message, StringComparison.OrdinalIgnoreCase);
    }

    // FR-007a: fewer buckets than the window means every group was read
    [Fact]
    public void A_Short_Window_Passes()
    {
        using var response = JsonDocument.Parse(GroupedResponse(cardinality: Window - 1, buckets: Window - 1));

        Assert.Null(Record.Exception(() => SearchCountReader.AssertGroupWindowComplete(response.RootElement, GroupColumn, Window)));
    }
}
