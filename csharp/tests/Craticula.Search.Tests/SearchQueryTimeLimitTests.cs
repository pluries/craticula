using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Search.Tests;

public class SearchQueryTimeLimitTests
{
    private static GridSchema Schema { get; } = SearchTestSchema.Of(
        ("id", SearchTestSchema.Id),
        ("region", SearchTestSchema.Field(FieldType.String, "region", keyword: "region.keyword")));

    private static SearchQuery Rows(int? limit, PageSpec? page = null) =>
        SearchQueryBuilder.Build(new SearchQueryRequest
        {
            Schema = Schema,
            Page = page ?? SearchTestSchema.FirstPage,
            MaxQueryTimeMs = limit
        });

    private static SearchQuery SetValues(int? limit) =>
        SearchQueryBuilder.BuildSetValues(new SearchSetValuesRequest
        {
            Schema = Schema,
            ColId = "region",
            RowLimit = 1000,
            MaxQueryTimeMs = limit
        });

    [Fact]
    public void A_Limit_Adds_The_Timeout_Member_In_Milliseconds() =>
        Assert.Equal("2000ms", (string)Rows(2000).ToArtifact()["timeout"]!);

    [Fact]
    public void The_Timeout_Sits_Beside_Query_Sort_From_And_Size()
    {
        var artifact = Rows(2000).ToArtifact();

        Assert.NotNull(artifact["query"]);
        Assert.NotNull(artifact["sort"]);
        Assert.NotNull(artifact["from"]);
        Assert.NotNull(artifact["size"]);
    }

    [Fact]
    public void No_Limit_Means_No_Timeout_Member() =>
        Assert.False(Rows(null).ToArtifact().ContainsKey("timeout"));

    [Fact]
    public void The_Rest_Of_The_Body_Is_The_Same_With_And_Without_A_Limit()
    {
        var with = Rows(2000).ToArtifact();
        with.Remove("timeout");

        Assert.Equal(Rows(null).ToArtifact().ToJsonString(), with.ToJsonString());
    }

    [Fact]
    public void A_Set_Values_Body_Carries_The_Timeout() =>
        Assert.Equal("1500ms", (string)SetValues(1500).ToArtifact()["timeout"]!);

    [Fact]
    public void A_Set_Values_Body_Without_A_Limit_Has_No_Timeout() =>
        Assert.False(SetValues(null).ToArtifact().ContainsKey("timeout"));

    [Fact]
    public void An_Unpaginated_Export_Page_Never_Carries_The_Limit()
    {
        var query = Rows(2000, new NonePage());

        Assert.Null(query.TimeoutMs);
        Assert.False(query.ToArtifact().ContainsKey("timeout"));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void A_Zero_Or_Negative_Limit_Is_Refused_By_Both_Entry_Points(int limit)
    {
        Assert.Throws<SearchCompilationException>(() => Rows(limit));
        Assert.Throws<SearchCompilationException>(() => SetValues(limit));
    }
}
