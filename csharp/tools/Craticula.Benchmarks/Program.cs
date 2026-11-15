using BenchmarkDotNet.Configs;
using BenchmarkDotNet.Exporters.Json;
using BenchmarkDotNet.Running;
using Craticula.Benchmarks;

// list                 the named shapes
// run --out <dir>      run the benchmark, save the raw BenchmarkDotNet output under <dir>, print one line per shape and backend against PERF-1
// report <json file>   print those lines again from a saved <name>-report-full.json
if (args is ["list"])
{
    foreach (var shape in Shapes.All)
    {
        Console.WriteLine($"{shape.Name}  (spec/fixtures/{shape.Fixture})");
    }

    return 0;
}

if (args is ["report", var path])
{
    foreach (var line in Perf1Report.Lines(File.ReadAllText(path)))
    {
        Console.WriteLine(line);
    }

    return 0;
}

if (args is ["run", "--out", var output])
{
    var config = DefaultConfig.Instance.WithArtifactsPath(output).AddExporter(JsonExporter.Full);
    BenchmarkRunner.Run<CompileBenchmarks>(config);
    var json = Directory.GetFiles(Path.Combine(output, "results"), "*-report-full.json").Single();
    Console.WriteLine();
    foreach (var line in Perf1Report.Lines(File.ReadAllText(json)))
    {
        Console.WriteLine(line);
    }

    return 0;
}

Console.Error.WriteLine("usage: Craticula.Benchmarks list | run --out <dir> | report <report-full.json>");
return 2;
