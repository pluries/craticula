using BenchmarkDotNet.Configs;
using BenchmarkDotNet.Exporters.Json;
using BenchmarkDotNet.Running;
using Craticula.Benchmarks;

// list                 the named shapes
// run --out <dir>      run the benchmark, save the raw BenchmarkDotNet output under <dir>, print one line per shape and backend against PERF-1
// report <json file>   print those lines again from a saved <name>-report-full.json
// stages --out <dir>   where the compile time goes: each stage alone and the full compile from raw JSON, per shape (PostgreSQL)
if (args is ["list"])
{
    foreach (var shape in Shapes.All)
    {
        await Console.Out.WriteLineAsync($"{shape.Name}  (spec/fixtures/{shape.Fixture})");
    }

    return 0;
}

if (args is ["report", var path])
{
    foreach (var line in Perf1Report.Lines(await File.ReadAllTextAsync(path)))
    {
        await Console.Out.WriteLineAsync(line);
    }

    return 0;
}

if (args is ["stages", "--out", var stagesOutput])
{
    var stagesConfig = DefaultConfig.Instance.WithArtifactsPath(stagesOutput).AddExporter(JsonExporter.Full);
    BenchmarkRunner.Run<StageBenchmarks>(stagesConfig);
    var stagesJson = Directory.GetFiles(Path.Combine(stagesOutput, "results"), "*StageBenchmarks-report-full.json").Single();
    await Console.Out.WriteLineAsync();
    foreach (var line in StageReport.Lines(await File.ReadAllTextAsync(stagesJson)))
    {
        await Console.Out.WriteLineAsync(line);
    }

    return 0;
}

if (args is ["run", "--out", var output])
{
    var config = DefaultConfig.Instance.WithArtifactsPath(output).AddExporter(JsonExporter.Full);
    BenchmarkRunner.Run<CompileBenchmarks>(config);
    var json = Directory.GetFiles(Path.Combine(output, "results"), "*-report-full.json").Single();
    await Console.Out.WriteLineAsync();
    foreach (var line in Perf1Report.Lines(await File.ReadAllTextAsync(json)))
    {
        await Console.Out.WriteLineAsync(line);
    }

    return 0;
}

await Console.Error.WriteLineAsync("usage: Craticula.Benchmarks list | run --out <dir> | stages --out <dir> | report <report-full.json>");
return 2;
