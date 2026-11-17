using System.Text.Json.Nodes;
using Craticula.Conformance.Driver;
using Craticula.Mongo;
using Craticula.Search;
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

    [Fact]
    public void A_Count_Request_On_Mongo_Compiles_To_A_Pipeline_Ending_In_Count()
    {
        var query = Assert.IsType<MongoQuery>(
            RequestCompiler.Compile("mongo", Read(FlatCase, "schema.json"), Read(FlatCase, "agGridRequest.json")));

        Assert.Equal("""{"$count":"count"}""", query.Pipeline[^1].ToJsonString());
        Assert.DoesNotContain(query.Pipeline, stage => stage.First().Key is "$sort" or "$skip" or "$limit");
    }

    [Fact]
    public void A_Count_Request_On_Search_Compiles_To_A_Body_Without_Rows()
    {
        var query = Assert.IsType<SearchQuery>(
            RequestCompiler.Compile("search", Read(FlatCase, "schema.json"), Read(FlatCase, "agGridRequest.json")));

        var body = query.ToArtifact();
        Assert.Equal(0, body["size"]!.GetValue<int>());
        Assert.False(body.ContainsKey("sort"));
        Assert.False(body.ContainsKey("from"));
    }

    [Theory]
    [InlineData("postgres")]
    [InlineData("mongo")]
    [InlineData("search")]
    public void Count_Mode_On_A_Set_Values_Request_Is_An_Error(string backend)
    {
        var request = JsonNode.Parse("""{"setValuesRequest":{"colId":"lastName"},"requestContext":{"compileMode":"count"}}""")!.ToJsonString();

        Assert.Throws<NotSupportedException>(
            () => RequestCompiler.Compile(backend, Read(FlatCase, "schema.json"), request));
    }
}
