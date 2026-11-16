using System.Globalization;
using System.Text.Json;

namespace Craticula.Benchmarks;

/// <summary>The result of the compile benchmark against PERF-1 (TRD: under 50 µs per typical request, benchmarked and not enforced): the number is reported whether the target is met or not.</summary>
internal static class Perf1Report
{
    private const double TargetNanoseconds = 50_000;

    public static string Line(string shape, string backend, double meanNanoseconds, double allocatedBytes)
    {
        var verdict = meanNanoseconds < TargetNanoseconds ? "meets PERF-1" : "does not meet PERF-1";
        var allocation = allocatedBytes >= 1024
            ? string.Create(CultureInfo.InvariantCulture, $"{allocatedBytes / 1024:0.0} KiB")
            : string.Create(CultureInfo.InvariantCulture, $"{allocatedBytes:0} B");

        return string.Create(CultureInfo.InvariantCulture,
            $"{backend}/{shape}: mean {meanNanoseconds / 1000:0.0} µs, {allocation} allocated per request, {verdict} (target under 50 µs)");
    }

    public static IReadOnlyList<string> Lines(string benchmarkJson)
    {
        using var document = JsonDocument.Parse(benchmarkJson);
        if (!document.RootElement.TryGetProperty("Benchmarks", out var benchmarks) || benchmarks.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidOperationException("The benchmark JSON has no Benchmarks array.");
        }

        var lines = new List<string>();
        foreach (var benchmark in benchmarks.EnumerateArray())
        {
            var parameters = benchmark.GetProperty("Parameters").GetString()!
                .Split('&')
                .Select(pair => pair.Split('=', 2))
                .ToDictionary(pair => pair[0], pair => pair[1]);
            lines.Add(Line(
                parameters["Shape"],
                parameters["Backend"],
                benchmark.GetProperty("Statistics").GetProperty("Mean").GetDouble(),
                benchmark.GetProperty("Memory").GetProperty("BytesAllocatedPerOperation").GetDouble()));
        }

        return lines;
    }
}
