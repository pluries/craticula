using Craticula.AgGrid;

namespace Craticula.AgGrid.Tests;

/// <summary>FR-5 / TL-4 (#3794): no member of a request sets the query time limit; the parser ignores
/// a <c>maxQueryTimeMs</c> on the wire, at the top level or in <c>requestContext</c>, as it ignores
/// <c>requestContext.now</c> (SEM-4).</summary>
public class AgGridRequestParserQueryTimeLimitTests
{
    private const string Plain =
        """{"startRow":0,"endRow":100,"rowGroupCols":[],"valueCols":[],"pivotCols":[],"pivotMode":false,"groupKeys":[],"filterModel":null,"sortModel":[]%EXTRA%}""";

    private static AgGridParsedRequest Parse(string extra) =>
        AgGridRequestParser.Parse(Plain.Replace("%EXTRA%", extra));

    [Theory]
    [InlineData("")]
    [InlineData(""","maxQueryTimeMs":1""")]
    [InlineData(""","requestContext":{"maxQueryTimeMs":1}""")]
    [InlineData(""","maxQueryTimeMs":1,"requestContext":{"zone":"UTC","maxQueryTimeMs":99999}""")]
    public void A_Wire_Time_Limit_Changes_Nothing_In_The_Parsed_Request(string extra)
    {
        var baseline = Parse("");
        var parsed = Parse(extra);

        Assert.Equal(baseline.Page, parsed.Page);
        Assert.Equal(baseline.Sort, parsed.Sort);
        Assert.Equal(baseline.NativeFilter, parsed.NativeFilter);
    }
}
