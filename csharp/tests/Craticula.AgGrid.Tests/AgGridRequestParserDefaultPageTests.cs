using Craticula.AgGrid;
using Craticula.Core.Ir;

namespace Craticula.AgGrid.Tests;

/// <summary>PG-1..PG-4 (#3816): a request with no row window gets a default page; every row is only ever
/// asked for on purpose.</summary>
public class AgGridRequestParserDefaultPageTests
{
    private const string Template =
        """{"rowGroupCols":[],"valueCols":[],"pivotCols":[],"pivotMode":false,"groupKeys":[],"filterModel":null,"sortModel":[]%EXTRA%}""";

    private static AgGridParsedRequest Parse(string extra, AgGridParseOptions? options = null) =>
        AgGridRequestParser.Parse(Template.Replace("%EXTRA%", extra), options);

    private static void AssertRange(PageSpec page, int start, int end)
    {
        var range = Assert.IsType<RangePage>(page);
        Assert.Equal(start, range.StartRow);
        Assert.Equal(end, range.EndRow);
    }

    [Theory]
    [InlineData("")]
    [InlineData(""","startRow":null,"endRow":null""")]
    public void No_Window_Gets_The_Default_Page_Of_100(string extra) => AssertRange(Parse(extra).Page, 0, 100);

    [Fact]
    public void The_Default_Page_Size_Is_A_Host_Setting() =>
        AssertRange(Parse("", new AgGridParseOptions { DefaultPageSize = 25 }).Page, 0, 25);

    [Fact]
    public void A_Given_Window_Is_Unchanged() =>
        AssertRange(Parse(""","startRow":200,"endRow":250""").Page, 200, 250);

    [Fact]
    public void A_Half_Supplied_Window_Is_Still_Malformed()
    {
        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(""","startRow":10"""));
        Assert.Equal("malformed-request", ex.Reason);
    }

    [Fact]
    public void An_Allowed_Ignore_Page_Limit_Is_Unpaginated() =>
        Assert.IsType<NonePage>(
            Parse(""","ignorePageLimit":true""", new AgGridParseOptions { AllowUnboundedRows = true }).Page);

    [Fact]
    public void Ignore_Page_Limit_Without_The_Host_Switch_Is_Refused_Not_Capped()
    {
        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(""","ignorePageLimit":true"""));
        Assert.Equal("unbounded-not-allowed", ex.Reason);
    }

    [Fact]
    public void Ignore_Page_Limit_False_Or_Null_Changes_Nothing()
    {
        AssertRange(Parse(""","ignorePageLimit":false""").Page, 0, 100);
        AssertRange(Parse(""","ignorePageLimit":null""").Page, 0, 100);
    }

    [Fact]
    public void A_Window_Wins_Over_An_Allowed_Ignore_Page_Limit() =>
        AssertRange(
            Parse(""","startRow":0,"endRow":50,"ignorePageLimit":true""", new AgGridParseOptions { AllowUnboundedRows = true }).Page,
            0, 50);

    [Theory]
    [InlineData(""""
        ,"ignorePageLimit":"yes"
        """")]
    [InlineData(""","ignorePageLimit":1""")]
    public void A_Non_Boolean_Ignore_Page_Limit_Is_Malformed(string extra)
    {
        var ex = Assert.Throws<AgGridRequestParseException>(
            () => Parse(extra, new AgGridParseOptions { AllowUnboundedRows = true }));
        Assert.Equal("malformed-request", ex.Reason);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-5)]
    public void The_Default_Page_Size_Must_Be_Positive(int value) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new AgGridParseOptions { DefaultPageSize = value });
}
