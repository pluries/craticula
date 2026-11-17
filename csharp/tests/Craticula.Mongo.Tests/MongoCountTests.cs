using System.Text.Json.Nodes;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo.Tests;

/// <summary>
/// CNT-6 for <see cref="MongoPipelineBuilder.BuildCount"/>, graded against the <c>count-mode</c> fixtures'
/// artifacts, which were derived from the page artifacts and not from this implementation.
/// </summary>
public class MongoCountTests
{
    private const string Category = "count-mode";

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
    private static MongoQueryRequest CountRequest(string fixtureDir, int? maxQueryTimeMs = null)
    {
        var schema = GridSchema.Parse(MongoFixtureCompiler.Read(Category, fixtureDir, "schema.json"));
        var parsed = AgGridRequestParser.Parse(
            MongoFixtureCompiler.Read(Category, fixtureDir, "agGridRequest.json"),
            new AgGridParseOptions { Schema = schema });

        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            new NonePage(),
            schema,
            new ResourceLimits(),
            parsed.Group,
            parsed.Aggregations);

        return new MongoQueryRequest
        {
            Schema = schema,
            Filter = filter,
            Sort = parsed.Sort,
            Page = new NonePage(),
            Group = parsed.Group,
            Aggregations = parsed.Aggregations,
            MaxQueryTimeMs = maxQueryTimeMs
        };
    }

    private static MongoQuery CompileCount(string fixtureDir) =>
        MongoPipelineBuilder.BuildCount(CountRequest(fixtureDir));

    // T1
    [Theory]
    [MemberData(nameof(CountableFixtures))]
    public void BuildCount_Compiles_To_The_Pipeline_Its_Own_Artifact_Pins(string fixtureDir)
    {
        var actual = CompileCount(fixtureDir);

        Assert.Equal(
            MongoFixtureCompiler.CanonicalJson(
                MongoFixtureCompiler.Read(Category, fixtureDir, "expected", "mongo.artifact.json")),
            MongoFixtureCompiler.CanonicalJson(actual.ToArtifact()));
    }

    // T2
    [Fact]
    public void BuildCount_Ignores_A_Window_Above_The_Page_Limit_And_The_Sort()
    {
        var query = CompileCount("005-window-above-page-limit-ignored");

        Assert.DoesNotContain(query.Pipeline, stage =>
            stage.ContainsKey("$sort") || stage.ContainsKey("$skip") || stage.ContainsKey("$limit"));
        Assert.Equal(
            MongoFixtureCompiler.CanonicalJson("""{"$count":"count"}"""),
            MongoFixtureCompiler.CanonicalJson(query.Pipeline[^1]));
    }

    // T3
    [Fact]
    public void BuildCount_Refuses_An_Unknown_Column_As_The_Page_Path_Does()
    {
        var pageFailure = Record.Exception(() =>
            MongoFixtureCompiler.Compile("adversarial", "001-unknown-colid-filter-model"));
        var countFailure = Record.Exception(() => CompileCount("009-rejection-unknown-column"));

        Assert.NotNull(pageFailure);
        Assert.NotNull(countFailure);
        Assert.Equal(pageFailure.GetType(), countFailure.GetType());
    }

    // T4
    [Fact]
    public void BuildCount_Keeps_The_Query_Time_Limit_In_The_Wrapper_Although_The_Count_Has_No_Window()
    {
        var query = MongoPipelineBuilder.BuildCount(CountRequest("002-flat-number-filter", maxQueryTimeMs: 250));

        var artifact = Assert.IsType<JsonObject>(query.ToArtifact());
        Assert.Equal(250, artifact["maxTimeMS"]!.GetValue<int>());
        var pipeline = Assert.IsType<JsonArray>(artifact["pipeline"]);
        Assert.Equal(
            MongoFixtureCompiler.CanonicalJson("""{"$count":"count"}"""),
            MongoFixtureCompiler.CanonicalJson(pipeline[^1]));
    }
}
