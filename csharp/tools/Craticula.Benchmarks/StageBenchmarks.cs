using BenchmarkDotNet.Attributes;

namespace Craticula.Benchmarks;

/// <summary>Where the compile time of a shape goes: each stage alone from prepared inputs (PostgreSQL), and "all" = the four stages from raw JSON, the cost of a compile that builds its schema every time.</summary>
[MemoryDiagnoser]
public class StageBenchmarks
{
    private StageInputs _inputs = null!;

    public static IEnumerable<string> ShapeNames => Shapes.All.Select(shape => shape.Name);

    public static IEnumerable<string> StageNames => [.. Stages.Names, "all"];

    [ParamsSource(nameof(ShapeNames))]
    public string Shape { get; set; } = "";

    [ParamsSource(nameof(StageNames))]
    public string StageName { get; set; } = "";

    [GlobalSetup]
    public void Setup() => _inputs = Stages.Prepare(Shapes.Load(Shape));

    [Benchmark]
    public object Run() => StageName == "all" ? Stages.RunAll(_inputs) : Stages.Run(_inputs, StageName);
}
