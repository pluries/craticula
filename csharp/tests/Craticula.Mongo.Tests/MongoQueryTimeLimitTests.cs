using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo.Tests;

public class MongoQueryTimeLimitTests
{
    private static FieldConfig Field(FieldType type, CaseSensitivity? caseSensitivity = null) => new()
    {
        Type = type,
        Text = caseSensitivity is null ? null : new TextOptions { CaseSensitivity = caseSensitivity.Value }
    };

    private static readonly GridSchema Schema = new()
    {
        Source = "employees",
        StableKey = "id",
        Fields = new Dictionary<string, FieldConfig>
        {
            ["id"] = Field(FieldType.Int64),
            ["lastName"] = Field(FieldType.String),
            ["age"] = Field(FieldType.Int64)
        }
    };

    private static readonly FilterNode CaseInsensitiveEq = new ComparisonNode
    {
        Field = "lastName",
        Op = ComparisonOperator.Eq,
        Value = new StringValue { Value = "smith" }
    };

    private static MongoQuery Rows(int? limit, FilterNode? filter = null, PageSpec? page = null) =>
        MongoPipelineBuilder.Build(new MongoQueryRequest
        {
            Schema = Schema,
            Filter = filter,
            Page = page ?? new RangePage { StartRow = 0, EndRow = 100 },
            MaxQueryTimeMs = limit
        });

    private static MongoQuery SetValues(int? limit) =>
        MongoPipelineBuilder.BuildSetValues(new MongoSetValuesRequest
        {
            Schema = Schema,
            ColId = "lastName",
            RowLimit = 1000,
            MaxQueryTimeMs = limit
        });

    private static string Json(MongoQuery query) => MongoFixtureCompiler.CanonicalJson(query.ToArtifact());

    [Fact]
    public void A_Limit_Without_A_Collation_Makes_The_Wrapper_With_MaxTimeMS()
    {
        var artifact = Rows(2000).ToArtifact().AsObject();

        Assert.Equal(["pipeline", "maxTimeMS"], artifact.Select(p => p.Key).ToArray());
        Assert.Equal(2000, (int)artifact["maxTimeMS"]!);
    }

    [Fact]
    public void A_Limit_With_A_Collation_Orders_Pipeline_Collation_MaxTimeMS()
    {
        var artifact = Rows(2000, CaseInsensitiveEq).ToArtifact().AsObject();

        Assert.Equal(["pipeline", "collation", "maxTimeMS"], artifact.Select(p => p.Key).ToArray());
    }

    [Fact]
    public void No_Limit_Keeps_The_Bare_Array()
    {
        Assert.IsType<System.Text.Json.Nodes.JsonArray>(Rows(null).ToArtifact());
    }

    [Fact]
    public void No_Limit_With_A_Collation_Is_The_Pipeline_And_Collation_Wrapper_Only()
    {
        var artifact = Rows(null, CaseInsensitiveEq).ToArtifact().AsObject();

        Assert.Equal(["pipeline", "collation"], artifact.Select(p => p.Key).ToArray());
    }

    [Fact]
    public void The_Pipeline_Is_The_Same_With_And_Without_A_Limit()
    {
        var with = Rows(2000).ToArtifact().AsObject()["pipeline"]!.ToJsonString();
        var without = Rows(null).ToArtifact().ToJsonString();

        Assert.Equal(without, with);
    }

    [Fact]
    public void A_Set_Values_Query_Carries_The_Limit()
    {
        var artifact = SetValues(1500).ToArtifact().AsObject();

        Assert.Equal(1500, (int)artifact["maxTimeMS"]!);
    }

    [Fact]
    public void An_Unpaginated_Export_Page_Never_Carries_The_Limit()
    {
        var query = Rows(2000, page: new NonePage());

        Assert.Null(query.MaxTimeMs);
        Assert.IsType<System.Text.Json.Nodes.JsonArray>(query.ToArtifact());
    }

    [Fact]
    public void A_Set_Values_Query_Without_A_Limit_Has_No_MaxTimeMS_And_Is_The_Bare_Array()
    {
        var artifact = SetValues(null).ToArtifact();

        Assert.IsType<System.Text.Json.Nodes.JsonArray>(artifact);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void A_Zero_Or_Negative_Limit_Is_Refused_By_Both_Entry_Points(int limit)
    {
        Assert.Throws<MongoCompilationException>(() => Rows(limit));
        Assert.Throws<MongoCompilationException>(() => SetValues(limit));
    }
}
