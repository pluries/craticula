namespace Craticula.Benchmarks.Tests;

// Traceability: FR-17, AC-1, AC-6, PERF-1
public class Perf1ReportTests
{
    [Fact]
    public void Line_AMeanBelowFiftyMicroseconds_SaysItMeetsPerf1()
    {
        var line = Perf1Report.Line("plain-page", "postgres", meanNanoseconds: 12_000, allocatedBytes: 4096);

        Assert.Contains("meets PERF-1", line);
        Assert.DoesNotContain("does not meet", line);
        Assert.Contains("12.0 µs", line);
    }

    [Fact]
    public void Line_AMeanAboveFiftyMicroseconds_SaysItDoesNotMeetPerf1WithTheNumber()
    {
        var line = Perf1Report.Line("deep-filter", "mongo", meanNanoseconds: 80_250, allocatedBytes: 10_240);

        Assert.Contains("does not meet PERF-1", line);
        Assert.Contains("80.3 µs", line);
    }

    [Fact]
    public void Line_ExactlyFiftyMicroseconds_DoesNotMeetTheStrictTarget()
    {
        Assert.Contains("does not meet PERF-1", Perf1Report.Line("plain-page", "search", 50_000, 1));
    }

    [Fact]
    public void Lines_ReadTheMeanAndTheAllocationFromTheBenchmarkJson()
    {
        const string json = """
            { "Benchmarks": [
              { "Parameters": "Shape=plain-page&Backend=postgres", "Statistics": { "Mean": 12345.6 }, "Memory": { "BytesAllocatedPerOperation": 2048 } },
              { "Parameters": "Shape=deep-filter&Backend=mongo", "Statistics": { "Mean": 90000.0 }, "Memory": { "BytesAllocatedPerOperation": 8192 } }
            ] }
            """;

        var lines = Perf1Report.Lines(json);

        Assert.Equal(2, lines.Count);
        Assert.Contains("plain-page", lines[0]);
        Assert.Contains("postgres", lines[0]);
        Assert.Contains("meets PERF-1", lines[0]);
        Assert.Contains("2.0 KiB", lines[0]);
        Assert.Contains("does not meet PERF-1", lines[1]);
    }

    [Fact]
    public void Lines_JsonWithoutBenchmarks_Throws()
    {
        Assert.Throws<InvalidOperationException>(() => Perf1Report.Lines("{ }"));
    }
}
