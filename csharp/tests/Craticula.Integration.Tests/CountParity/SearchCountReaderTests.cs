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
}
