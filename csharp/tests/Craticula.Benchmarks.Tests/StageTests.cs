using Craticula.Sql;

namespace Craticula.Benchmarks.Tests;

// Traceability: PERF-1, AC-4 of story #3856
public class StageTests
{
    public static TheoryData<string, string> EveryShapeAndStage()
    {
        var data = new TheoryData<string, string>();
        foreach (var shape in Shapes.All)
        {
            foreach (var stage in Stages.Names)
            {
                data.Add(shape.Name, stage);
            }
        }

        return data;
    }

    [Theory]
    [MemberData(nameof(EveryShapeAndStage))]
    public void Run_EveryStageOfEveryShape_RunsWithoutError(string shape, string stage)
    {
        var inputs = Stages.Prepare(Shapes.Load(shape));

        // the filter stage returns nothing for a request that has no filter: that is a result, not a failure
        Assert.Null(Record.Exception(() => Stages.Run(inputs, stage)));
    }

    [Fact]
    public void Run_TheStagesInOrder_GiveTheSameSqlAsTheFullCompile()
    {
        foreach (var shape in Shapes.All)
        {
            var loaded = Shapes.Load(shape.Name);
            var inputs = Stages.Prepare(loaded);

            var viaStages = (SqlQuery)Stages.RunAll(inputs);
            var full = (SqlQuery)Shapes.Compile(loaded, "postgres");

            Assert.Equal(full.Sql, viaStages.Sql);
        }
    }

    // Traceability: #3873 AC-2 (the stage breakdown gives the same SQL as the full compile for the count shape)
    [Fact]
    public void Run_TheCountShape_BuildsTheCountAndNotThePage()
    {
        var inputs = Stages.Prepare(Shapes.Load("count"));

        var built = (SqlQuery)Stages.Run(inputs, "build-query");

        Assert.Equal("SELECT COUNT(*) FROM \"employees\" WHERE (\"age\" <> $1 OR \"age\" IS NULL)", built.Sql);
    }

    [Fact]
    public void Run_AnUnknownStage_ThrowsAndNamesTheStages()
    {
        var inputs = Stages.Prepare(Shapes.Load(Shapes.All[0].Name));

        var error = Assert.Throws<ArgumentException>(() => Stages.Run(inputs, "no-such-stage"));

        Assert.Contains("no-such-stage", error.Message);
        foreach (var name in Stages.Names)
        {
            Assert.Contains(name, error.Message);
        }
    }

    [Fact]
    public void Names_AreTheFourStagesInOrder()
    {
        Assert.Equal(["parse-schema", "parse-request", "filter-pipeline", "build-query"], Stages.Names);
    }
}
