using Craticula.Core.Ir;
using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>The one rule that picks the counted fixtures (FR-003), the own-window rule (FR-013) and the page override (FR-007).</summary>
public sealed class CountedFixturesTests
{
    private const string RowFetch = "sort-paging/001-single-key-string-asc-nulls-last-default";
    private const string SetValues = "group-aggregation/016-set-filter-values-no-active-filters";
    private const string Grouped = "group-aggregation/001-group-top-level-no-keys-consumed";
    private const string Reason = "declared refusal";

    // US1-AS4, US2-AS5, FR-003
    [Fact]
    public void A_Set_Values_Request_Is_Not_Counted()
    {
        var setValues = ExecutionFixture.Load(SetValues);
        var rowFetch = ExecutionFixture.Load(RowFetch);

        Assert.True(CountedFixtures.IsSetValues(setValues));
        Assert.False(CountedFixtures.IsCounted(setValues, EngineNames.Mongo, null));
        Assert.False(CountedFixtures.IsSetValues(rowFetch));
        Assert.True(CountedFixtures.IsCounted(rowFetch, EngineNames.Mongo, null));
    }

    // US1-AS4, US2-AS5: an XEQ-4 error entry takes the fixture out for its backend and engine only
    [Fact]
    public void A_Declared_Error_Is_Not_Counted()
    {
        var template = ExecutionFixture.Load(RowFetch);
        var request = template.Request.GetRawText();
        var onOpenSearch = ExecutionFixture.FromMemory(
            "stub/error-opensearch", template.Schema, request, [], null,
            [new Divergence(EngineNames.Search, EngineNames.OpenSearch, Reason, new ExpectError(Reason))]);
        var onBothSearchEngines = ExecutionFixture.FromMemory(
            "stub/error-search", template.Schema, request, [], null,
            [new Divergence(EngineNames.Search, null, Reason, new ExpectError(Reason))]);

        Assert.False(CountedFixtures.IsCounted(onOpenSearch, EngineNames.Search, EngineNames.OpenSearch));
        Assert.True(CountedFixtures.IsCounted(onOpenSearch, EngineNames.Search, EngineNames.Elasticsearch));
        Assert.True(CountedFixtures.IsCounted(onOpenSearch, EngineNames.Mongo, null));
        Assert.False(CountedFixtures.IsCounted(onBothSearchEngines, EngineNames.Search, EngineNames.OpenSearch));
        Assert.False(CountedFixtures.IsCounted(onBothSearchEngines, EngineNames.Search, EngineNames.Elasticsearch));
    }

    public static TheoryData<int?, int?, int, bool> Windows() => new()
    {
        { null, null, 5, false },
        { 0, 100, 3, false },
        { 0, 100, 100, true },
        { 5, 100, 3, true }
    };

    // US1-AS6, US2-AS7, FR-013: start, end, expected rows, truncates
    [Theory]
    [MemberData(nameof(Windows))]
    public void OwnWindowTruncates_Follows_The_Window_And_The_Expected_Rows(int? start, int? end, int expectedRows, bool truncates)
    {
        PageSpec page = start is null || end is null
            ? new NonePage()
            : new RangePage { StartRow = start.Value, EndRow = end.Value };

        Assert.Equal(truncates, CountedFixtures.OwnWindowTruncates(page, expectedRows));
    }

    // US1-AS5, FR-007
    [Fact]
    public void An_Unpaged_Override_Replaces_The_Own_Window()
    {
        var fixture = ExecutionFixture.Load(RowFetch);

        var own = PreparedRequest.For(fixture, fixture.Schema);
        var unpaged = PreparedRequest.For(fixture, fixture.Schema, new NonePage());

        var ownPage = Assert.IsType<RangePage>(own.Parsed!.Page);
        Assert.Equal(0, ownPage.StartRow);
        Assert.Equal(100, ownPage.EndRow);
        Assert.IsType<NonePage>(unpaged.Parsed!.Page);
    }

    // FR-003: a grouped level is recognised through the same plan the compilers use
    [Fact]
    public void A_Grouped_Level_Is_Recognised()
    {
        Assert.True(CountedFixtures.IsGroupedLevel(ExecutionFixture.Load(Grouped)));
        Assert.False(CountedFixtures.IsGroupedLevel(ExecutionFixture.Load(RowFetch)));
    }
}
