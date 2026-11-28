using Craticula.Core.Schema;

namespace Craticula.AgGrid.Tests;

/// <summary>
/// Feature 009 (US1-AS5): the exception names the validation stage and reason the fixture oracle
/// (<c>rejection.schema.json</c>) uses, so a conformance driver reports the spec's pair without reading
/// message text. <see cref="AgGridRequestParseException.Reason"/> itself is unchanged.
/// </summary>
public class AgGridRequestParseExceptionStageTests
{
    [Fact]
    public void An_Unparseable_Date_Text_Is_Rejected_At_Type_Coercion_As_The_Fixture_Oracle_Says()
    {
        const string fixtureDir = "013-malformed-date-string-date-field";
        var schema = GridSchema.Parse(File.ReadAllText(RepoPaths.Fixture("adversarial", fixtureDir, "schema.json")));
        var request = File.ReadAllText(RepoPaths.Fixture("adversarial", fixtureDir, "agGridRequest.json"));

        var ex = Assert.Throws<AgGridRequestParseException>(
            () => AgGridRequestParser.Parse(request, new AgGridParseOptions { Schema = schema }));

        Assert.Equal("malformed-request", ex.Reason);
        Assert.Equal("typeCoercion", ex.RejectedAt);
        Assert.Equal("uncoercible-value", ex.RejectionReason);
    }

    [Fact]
    public void Any_Other_Parse_Failure_Is_Rejected_At_Request_Parsing_With_Its_Own_Reason()
    {
        var request = File.ReadAllText(RepoPaths.Fixture("adversarial", "016-unknown-operator-regex", "agGridRequest.json"));

        var ex = Assert.Throws<AgGridRequestParseException>(() => AgGridRequestParser.Parse(request));

        Assert.Equal("unknown-operator", ex.Reason);
        Assert.Equal("requestParsing", ex.RejectedAt);
        Assert.Equal("unknown-operator", ex.RejectionReason);
    }
}
