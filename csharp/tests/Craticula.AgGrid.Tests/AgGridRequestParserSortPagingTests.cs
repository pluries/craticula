using Craticula.Core.Ir;

namespace Craticula.AgGrid.Tests;

/// <summary>
/// Hand-built boundary tests for <see cref="AgGridRequestParser.Parse"/>'s <c>sortModel</c> and
/// <c>startRow</c>/<c>endRow</c> dispatch — real-fixture-driven coverage lives in
/// <see cref="AgGridRequestParserSortPagingFixtureTests"/>.
/// </summary>
public class AgGridRequestParserSortPagingTests
{
    private static AgGridParsedRequest Parse(string request) => AgGridRequestParser.Parse(request);

    private const string Envelope = """
        {{
          "startRow": {0}, "endRow": {1},
          "rowGroupCols": [], "valueCols": [], "pivotCols": [], "pivotMode": false, "groupKeys": [],
          "filterModel": null,
          "sortModel": {2}
        }}
        """;

    [Fact]
    public void Empty_SortModel_Produces_Null_Sort()
    {
        var request = string.Format(Envelope, "0", "100", "[]");

        Assert.Null(Parse(request).Sort);
    }

    [Fact]
    public void Asc_Direction_Defaults_To_NullsPosition_Last()
    {
        var request = string.Format(Envelope, "0", "100", """[ { "colId": "lastName", "sort": "asc" } ]""");

        var sort = Parse(request).Sort!;
        Assert.Single(sort);
        Assert.Equal("lastName", sort[0].Field);
        Assert.Equal(SortDirection.Asc, sort[0].Direction);
        Assert.Equal(NullsPosition.Last, sort[0].NullsPosition);
    }

    [Fact]
    public void Desc_Direction_Defaults_To_NullsPosition_First()
    {
        var request = string.Format(Envelope, "0", "100", """[ { "colId": "lastName", "sort": "desc" } ]""");

        var sort = Parse(request).Sort!;
        Assert.Equal(SortDirection.Desc, sort[0].Direction);
        Assert.Equal(NullsPosition.First, sort[0].NullsPosition);
    }

    [Fact]
    public void Multiple_Keys_Preserve_Array_Order_And_Compute_Defaults_Independently()
    {
        var request = string.Format(Envelope, "0", "100", """
            [
              { "colId": "department", "sort": "asc" },
              { "colId": "age", "sort": "desc" },
              { "colId": "hireDate", "sort": "asc" }
            ]
            """);

        var sort = Parse(request).Sort!;
        Assert.Equal(3, sort.Count);
        Assert.Equal("department", sort[0].Field);
        Assert.Equal(NullsPosition.Last, sort[0].NullsPosition);
        Assert.Equal("age", sort[1].Field);
        Assert.Equal(NullsPosition.First, sort[1].NullsPosition);
        Assert.Equal("hireDate", sort[2].Field);
        Assert.Equal(NullsPosition.Last, sort[2].NullsPosition);
    }

    [Fact]
    public void Unrecognized_Sort_Direction_Throws_MalformedRequest()
    {
        var request = string.Format(Envelope, "0", "100", """[ { "colId": "lastName", "sort": "ascending" } ]""");

        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(request));
        Assert.Equal("malformed-request", ex.Reason);
    }

    [Fact]
    public void Both_StartRow_And_EndRow_Present_Produce_RangePage()
    {
        var request = string.Format(Envelope, "20", "40", "[]");

        var page = Assert.IsType<RangePage>(Parse(request).Page);
        Assert.Equal(20, page.StartRow);
        Assert.Equal(40, page.EndRow);
    }

    [Fact]
    public void Both_StartRow_And_EndRow_Null_Produce_The_Default_Page()
    {
        // PG-1 (#3816) replaced "no window means every row": the unpaginated page now needs an export of everything or an allowed ignorePageLimit.
        var request = string.Format(Envelope, "null", "null", "[]");

        Assert.Equal(new RangePage { StartRow = 0, EndRow = 100 }, Parse(request).Page);
    }

    [Fact]
    public void One_Null_One_Present_Throws_MalformedRequest()
    {
        var request = string.Format(Envelope, "0", "null", "[]");

        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(request));
        Assert.Equal("malformed-request", ex.Reason);
    }

    [Fact]
    public void Negative_StartRow_Throws_PageSpecValidationException()
    {
        // Parse() runs PageSpecValidator on its own minted Page, the same defense-in-depth precedent
        // every other public entry point that mints an IR value follows in this codebase.
        var request = string.Format(Envelope, "-5", "100", "[]");

        Assert.Throws<PageSpecValidationException>(() => Parse(request));
    }

    [Fact]
    public void EndRow_Before_StartRow_Throws_PageSpecValidationException()
    {
        var request = string.Format(Envelope, "100", "0", "[]");

        Assert.Throws<PageSpecValidationException>(() => Parse(request));
    }

    [Fact]
    public void Zero_Width_Window_Throws_PageSpecValidationException()
    {
        var request = string.Format(Envelope, "100", "100", "[]");

        Assert.Throws<PageSpecValidationException>(() => Parse(request));
    }

    [Fact]
    public void Adversarial_027_Zero_Width_Window_Is_Refused_Before_Compilation()
    {
        var path = RepoPaths.Fixture("adversarial", "027-zero-width-page-window", "agGridRequest.json");

        Assert.Throws<PageSpecValidationException>(() => AgGridRequestParser.Parse(File.ReadAllText(path)));
    }

    [Fact]
    public void EndRow_Beyond_Int32_Range_Throws_MalformedRequest_Not_An_Unhandled_FormatException()
    {
        var request = string.Format(Envelope, "0", "99999999999", "[]");

        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(request));
        Assert.Equal("malformed-request", ex.Reason);
    }

    [Fact]
    public void Fractional_EndRow_Throws_MalformedRequest_Not_An_Unhandled_FormatException()
    {
        var request = string.Format(Envelope, "0", "1.5", "[]");

        var ex = Assert.Throws<AgGridRequestParseException>(() => Parse(request));
        Assert.Equal("malformed-request", ex.Reason);
    }
}
