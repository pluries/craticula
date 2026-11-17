using System.Globalization;
using System.Text.Json;

namespace Craticula.Benchmarks;

/// <summary>One line per shape and stage: mean, allocation and the share of the full compile from raw JSON (the stage named "all").</summary>
internal static class StageReport
{
    public static IReadOnlyList<string> Lines(string benchmarkJson)
    {
        using var document = JsonDocument.Parse(benchmarkJson);
        if (!document.RootElement.TryGetProperty("Benchmarks", out var benchmarks) || benchmarks.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidOperationException("The benchmark JSON has no Benchmarks array.");
        }

        var rows = new List<(string Shape, string Stage, double Mean, double Allocated)>();
        foreach (var benchmark in benchmarks.EnumerateArray())
        {
            var parameters = new Dictionary<string, string>();
            foreach (var pair in benchmark.GetProperty("Parameters").GetString()!.Split('&'))
            {
                var parts = pair.Split('=', 2);
                parameters[parts[0]] = parts[1];
            }

            rows.Add((
                parameters["Shape"],
                parameters["StageName"],
                benchmark.GetProperty("Statistics").GetProperty("Mean").GetDouble(),
                benchmark.GetProperty("Memory").GetProperty("BytesAllocatedPerOperation").GetDouble()));
        }

        var lines = new List<string>();
        foreach (var row in rows)
        {
            var total = rows.FirstOrDefault(other => other.Shape == row.Shape && other.Stage == "all").Mean;
            var share = total > 0 ? string.Create(CultureInfo.InvariantCulture, $", {row.Mean / total * 100:0}% of the full compile") : "";
            lines.Add(string.Create(CultureInfo.InvariantCulture,
                $"{row.Shape}/{row.Stage}: mean {row.Mean / 1000:0.0} µs, {Kib(row.Allocated)} allocated{share}"));
        }

        return lines;
    }

    private static string Kib(double bytes) => bytes >= 1024
        ? string.Create(CultureInfo.InvariantCulture, $"{bytes / 1024:0.0} KiB")
        : string.Create(CultureInfo.InvariantCulture, $"{bytes:0} B");
}
