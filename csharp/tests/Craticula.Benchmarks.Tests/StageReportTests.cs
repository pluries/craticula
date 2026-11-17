namespace Craticula.Benchmarks.Tests;

// Traceability: PERF-1, AC-4 of story #3856
public class StageReportTests
{
    private const string Json = """
        { "Benchmarks": [
          { "Parameters": "Shape=group-aggregate&StageName=parse-schema", "Statistics": { "Mean": 9000.0 }, "Memory": { "BytesAllocatedPerOperation": 4096 } },
          { "Parameters": "Shape=group-aggregate&StageName=build-query", "Statistics": { "Mean": 21500.0 }, "Memory": { "BytesAllocatedPerOperation": 8192 } },
          { "Parameters": "Shape=group-aggregate&StageName=all", "Statistics": { "Mean": 52000.0 }, "Memory": { "BytesAllocatedPerOperation": 16384 } }
        ] }
        """;

    [Fact]
    public void Lines_GiveShapeStageMeanAndAllocation()
    {
        var lines = StageReport.Lines(Json);

        Assert.Equal(3, lines.Count);
        Assert.Contains("group-aggregate", lines[0]);
        Assert.Contains("parse-schema", lines[0]);
        Assert.Contains("9.0 µs", lines[0]);
        Assert.Contains("4.0 KiB", lines[0]);
    }

    [Fact]
    public void Lines_SayWhatShareOfTheFullCompileEachStageIs()
    {
        var lines = StageReport.Lines(Json);

        Assert.Contains("17%", lines[0]);   // 9.0 of 52.0 µs
        Assert.Contains("41%", lines[1]);   // 21.5 of 52.0 µs
    }

    [Fact]
    public void Lines_JsonWithoutBenchmarks_Throws()
    {
        Assert.Throws<InvalidOperationException>(() => StageReport.Lines("{ }"));
    }
}
