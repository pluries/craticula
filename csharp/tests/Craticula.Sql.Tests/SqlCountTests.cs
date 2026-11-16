using System.Text.Json;
using Craticula.AgGrid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Sql.Tests;

/// <summary>
/// CNT-1..CNT-5 for <see cref="SqlQueryBuilder.BuildCount"/>, graded against the <c>count-mode</c>
/// fixtures' artifacts, which were derived from the page artifacts and not from this implementation.
/// </summary>
public class SqlCountTests
{
    private const string Category = "count-mode";

    private static readonly (string Name, ISqlDialect Dialect)[] Dialects =
    [
        ("postgres", PostgresDialect.Instance),
        ("mssql", MssqlDialect.Instance),
        ("mysql", MySqlDialect.Instance),
        ("oracle", OracleDialect.Instance),
        ("sqlite", SqliteDialect.Instance)
    ];

    private static readonly string[] CountableFixtures =
    [
        "001-flat-no-filter-sort-ignored",
        "002-flat-number-filter",
        "003-flat-set-filter",
        "004-flat-text-filter",
        "005-window-above-page-limit-ignored",
        "006-grouped-level",
        "007-grouped-level-filter-aggregate-sort",
        "008-drill-down-leaf"
    ];

    public static TheoryData<string, string> Arms
    {
        get
        {
            var data = new TheoryData<string, string>();
            foreach (var fixture in CountableFixtures)
            {
                foreach (var (name, _) in Dialects)
                {
                    data.Add(name, fixture);
                }
            }

            return data;
        }
    }

    private static ISqlDialect DialectNamed(string name) =>
        Dialects.Single(entry => entry.Name == name).Dialect;

    /// <summary>The page path's pipeline with CNT-3's one difference: the window is never given to it.</summary>
    private static SqlQuery CompileCount(string category, string fixtureDir, ISqlDialect dialect, bool pageWindow = false)
    {
        var schema = GridSchema.Parse(FixtureCompiler.Read(category, fixtureDir, "schema.json"));
        var parsed = AgGridRequestParser.Parse(
            FixtureCompiler.Read(category, fixtureDir, "agGridRequest.json"),
            new AgGridParseOptions { Schema = schema });

        var filter = GridFilterPipeline.Process(
            parsed.NativeFilter,
            parsed.CustomFilters,
            pageWindow ? parsed.Page : new NonePage(),
            schema,
            new ResourceLimits(),
            parsed.Group,
            parsed.Aggregations);

        return SqlQueryBuilder.BuildCount(
            new SqlQueryRequest
            {
                Schema = schema,
                Filter = filter,
                Sort = parsed.Sort,
                Page = new NonePage(),
                Group = parsed.Group,
                Aggregations = parsed.Aggregations
            },
            dialect);
    }

    // T1
    [Theory]
    [MemberData(nameof(Arms))]
    public void BuildCount_Compiles_To_The_Sql_And_Params_Its_Own_Artifact_Pins(string dialect, string fixtureDir)
    {
        var actual = CompileCount(Category, fixtureDir, DialectNamed(dialect));
        using var expected = JsonDocument.Parse(
            FixtureCompiler.Read(Category, fixtureDir, "expected", $"{dialect}.artifact.json"));

        Assert.Equal(expected.RootElement.GetProperty("dialect").GetString(), actual.Dialect);
        Assert.Equal(expected.RootElement.GetProperty("sql").GetString(), actual.Sql);
        Assert.Equal(
            FixtureCompiler.CanonicalJson(expected.RootElement.GetProperty("params")),
            FixtureCompiler.CanonicalJson(actual.Parameters));
    }

    // T2
    [Theory]
    [InlineData("postgres")]
    [InlineData("mssql")]
    [InlineData("mysql")]
    [InlineData("oracle")]
    [InlineData("sqlite")]
    public void BuildCount_Ignores_A_Window_Above_The_Page_Limit_And_The_Sort(string dialect)
    {
        var oversized = CompileCount(Category, "005-window-above-page-limit-ignored", DialectNamed(dialect));

        Assert.DoesNotContain("ORDER BY", oversized.Sql, StringComparison.Ordinal);
        Assert.Empty(oversized.Parameters);
    }

    // T2, the refusal the page path gives for the same window
    [Fact]
    public void The_Page_Path_Refuses_Fixture_005s_Window_So_Count_Mode_Not_Giving_It_To_The_Pipeline_Matters()
    {
        Assert.Throws<ResourceLimitExceededException>(() =>
            CompileCount(Category, "005-window-above-page-limit-ignored", PostgresDialect.Instance, pageWindow: true));
    }

    // T3
    [Theory]
    [InlineData("postgres")]
    [InlineData("mssql")]
    [InlineData("mysql")]
    [InlineData("oracle")]
    [InlineData("sqlite")]
    public void BuildCount_Refuses_An_Unknown_Column_As_The_Page_Path_Does(string dialect)
    {
        var pageFailure = Record.Exception(() =>
            FixtureCompiler.Compile("adversarial", "001-unknown-colid-filter-model", DialectNamed(dialect)));
        var countFailure = Record.Exception(() =>
            CompileCount(Category, "009-rejection-unknown-column", DialectNamed(dialect)));

        Assert.NotNull(pageFailure);
        Assert.NotNull(countFailure);
        Assert.Equal(pageFailure.GetType(), countFailure.GetType());
    }
}
