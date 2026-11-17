using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Search.Tests;

/// <summary>
/// CNT-1..CNT-4 and CNT-7 for <see cref="SearchQueryBuilder.BuildCount"/>, graded against the
/// <c>count-mode</c> fixtures' Search artifacts, which were derived from the page artifacts and not
/// from this implementation.
/// </summary>
public class SearchCountTests
{
    private const string Category = "count-mode";

    private static readonly string[] ForbiddenCountMembers = ["sort", "from", "search_after", "pit"];

    public static TheoryData<string> CountableFixtures =>
    [
        "001-flat-no-filter-sort-ignored",
        "002-flat-number-filter",
        "003-flat-set-filter",
        "004-flat-text-filter",
        "005-window-above-page-limit-ignored",
        "006-grouped-level",
        "007-grouped-level-drill-down-and-filters",
        "008-drill-down-leaf"
    ];

    /// <summary>The page path's pipeline with CNT-3's one difference: the window is never given to it.</summary>
    private static SearchQuery CompileCount(string fixtureDir, int? maxQueryTimeMs = null)
    {
        var schema = GridSchema.Parse(SearchFixtureCompiler.Read(Category, fixtureDir, "schema.json"));
        var parsed = AgGridRequestParser.Parse(
            SearchFixtureCompiler.Read(Category, fixtureDir, "agGridRequest.json"),
            new AgGridParseOptions { Schema = schema });

        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            new NonePage(),
            schema,
            new ResourceLimits(),
            parsed.Group,
            parsed.Aggregations);

        return SearchQueryBuilder.BuildCount(
            new SearchQueryRequest
            {
                Schema = schema,
                Filter = filter,
                Sort = parsed.Sort,
                Page = new NonePage(),
                Group = parsed.Group,
                Aggregations = parsed.Aggregations,
                MaxQueryTimeMs = maxQueryTimeMs
            });
    }

    // T1
    [Theory]
    [MemberData(nameof(CountableFixtures))]
    public void BuildCount_Compiles_To_The_Body_Its_Own_Artifact_Pins(string fixtureDir)
    {
        var actual = CompileCount(fixtureDir);

        Assert.Equal(
            SearchFixtureCompiler.CanonicalJson(
                SearchFixtureCompiler.Read(Category, fixtureDir, "expected", "search.artifact.json")),
            SearchFixtureCompiler.CanonicalJson(actual.ToArtifact()));
    }

    // T2
    [Fact]
    public void BuildCount_Ignores_A_Window_Above_The_Page_Limit_And_The_Sort()
    {
        var artifact = CompileCount("005-window-above-page-limit-ignored").ToArtifact();

        Assert.Equal(0, (int)artifact["size"]!);
        Assert.All(
            ForbiddenCountMembers,
            member => Assert.False(artifact.ContainsKey(member), $"count body must not carry '{member}'"));
    }

    // T2, the refusal the page path gives for the same window
    [Fact]
    public void The_Page_Path_Refuses_Fixture_005s_Window_So_Count_Mode_Not_Giving_It_To_The_Pipeline_Matters()
    {
        Assert.Throws<ResourceLimitExceededException>(() =>
            SearchFixtureCompiler.PrepareRowFetch(Category, "005-window-above-page-limit-ignored"));
    }

    // T3
    [Fact]
    public void BuildCount_Refuses_An_Unknown_Column_As_The_Page_Path_Does()
    {
        var pageFailure = Record.Exception(() =>
            SearchFixtureCompiler.Compile("adversarial", "001-unknown-colid-filter-model"));
        var countFailure = Record.Exception(() => CompileCount("009-rejection-unknown-column"));

        Assert.NotNull(pageFailure);
        Assert.NotNull(countFailure);
        Assert.IsNotType<NotImplementedException>(countFailure);
        Assert.Equal(pageFailure.GetType(), countFailure.GetType());
    }

    // T4
    [Theory]
    [MemberData(nameof(CountableFixtures))]
    public void BuildCount_Never_Emits_Track_Total_Hits(string fixtureDir)
    {
        var json = SearchFixtureCompiler.CanonicalJson(CompileCount(fixtureDir).ToArtifact());

        Assert.DoesNotContain("track_total_hits", json, StringComparison.Ordinal);
    }

    // T4, TL-2
    [Theory]
    [InlineData("002-flat-number-filter")]
    [InlineData("006-grouped-level")]
    public void BuildCount_Keeps_The_Query_Time_Limit_Member(string fixtureDir)
    {
        var artifact = CompileCount(fixtureDir, maxQueryTimeMs: 2000).ToArtifact();

        Assert.Equal("2000ms", (string)artifact["timeout"]!);

        using var expected = JsonDocument.Parse(
            SearchFixtureCompiler.Read(Category, fixtureDir, "expected", "search.artifact.json"));
        artifact.Remove("timeout");
        Assert.Equal(
            SearchFixtureCompiler.CanonicalJson(expected.RootElement.GetRawText()),
            SearchFixtureCompiler.CanonicalJson(artifact));
    }
}
