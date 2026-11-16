using BenchmarkDotNet.Attributes;

namespace Craticula.Benchmarks;

/// <summary>Mean time and allocation of one compile (parse, validate, build the query) per named shape and backend. Nothing is executed: the compiled query is plain data.</summary>
[MemoryDiagnoser]
public class CompileBenchmarks
{
    private LoadedShape _loaded = null!;

    public static IEnumerable<string> ShapeNames => Shapes.All.Select(shape => shape.Name);

    public static IEnumerable<string> BackendNames => Shapes.Backends;

    [ParamsSource(nameof(ShapeNames))]
    public string Shape { get; set; } = "";

    [ParamsSource(nameof(BackendNames))]
    public string Backend { get; set; } = "";

    [GlobalSetup]
    public void Setup() => _loaded = Shapes.Load(Shape);

    [Benchmark]
    public object Compile() => Shapes.Compile(_loaded, Backend);
}
