using System.Text.Json.Nodes;
using Craticula.Conformance.Driver;
using Craticula.Sql;

namespace Craticula.Conformance.Tests;

/// <summary>
/// The driver's side of count mode (CNT-3, CNT-8; <c>conformance-runner.md</c> §3, story #3863 task #3867): the harness member
/// <c>requestContext.compileMode</c> selects the count entry point, an unknown value or a backend without a count builder is an
/// error, and no member means the page, as before.
/// </summary>
public class CompileModeTests
{
    private const string FlatCase = "001-flat-no-filter-sort-ignored";
    private const string WindowCase = "005-window-above-page-limit-ignored";

    private static string Read(string fixture, string file) =>
        File.ReadAllText(RepoPaths.Fixture("count-mode", fixture, file));

    private static string WithCompileMode(string requestJson, string? mode)
    {
        var request = JsonNode.Parse(requestJson)!.AsObject();
        var context = request["requestContext"]!.AsObject();
        if (mode is null)
        {
            request.Remove("requestContext");
        }
        else
        {
            context["compileMode"] = mode;
        }

        return request.ToJsonString();
    }

    [Fact]
    public void A_Count_Request_Compiles_To_The_Count_Artifact()
    {
        var query = Assert.IsType<SqlQuery>(
            RequestCompiler.Compile("postgres", Read(FlatCase, "schema.json"), Read(FlatCase, "agGridRequest.json")));

        Assert.Equal("SELECT COUNT(*) FROM \"employees\"", query.Sql);
        Assert.Empty(query.Parameters);
    }

    [Fact]
    public void An_Unknown_Compile_Mode_Is_An_Error_Naming_The_Allowed_Value()
    {
        var request = WithCompileMode(Read(FlatCase, "agGridRequest.json"), "nonsense");

        var error = Assert.Throws<ArgumentException>(
            () => RequestCompiler.Compile("postgres", Read(FlatCase, "schema.json"), request));

        Assert.Contains("count", error.Message);
    }

    [Fact]
    public void Without_A_Compile_Mode_The_Request_Compiles_As_The_Page()
    {
        var request = WithCompileMode(Read(FlatCase, "agGridRequest.json"), mode: null);

        var query = Assert.IsType<SqlQuery>(RequestCompiler.Compile("postgres", Read(FlatCase, "schema.json"), request));

        Assert.Contains("ORDER BY", query.Sql);
    }

    [Fact]
    public void A_Count_With_A_Window_Above_The_Page_Limit_Is_Not_Refused()
    {
        var query = Assert.IsType<SqlQuery>(
            RequestCompiler.Compile("postgres", Read(WindowCase, "schema.json"), Read(WindowCase, "agGridRequest.json")));

        Assert.DoesNotContain("ORDER BY", query.Sql);
        Assert.Empty(query.Parameters);
    }

    [Theory]
    [InlineData("mongo")]
    [InlineData("search")]
    public void Count_Mode_On_A_Backend_Without_A_Count_Builder_Is_An_Error_Not_A_Page_Artifact(string backend)
    {
        Assert.Throws<NotSupportedException>(
            () => RequestCompiler.Compile(backend, Read(FlatCase, "schema.json"), Read(FlatCase, "agGridRequest.json")));
    }
}
