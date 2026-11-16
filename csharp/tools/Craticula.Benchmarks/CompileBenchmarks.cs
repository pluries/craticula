using BenchmarkDotNet.Attributes;

namespace Craticula.Benchmarks;

/// <summary>Mean time and allocation of one compile (parse, validate, build the query) per named shape and backend, on two paths: <c>full-compile</c> parses the schema from JSON on every call (as the conformance driver does), <c>prepared-schema</c> uses a schema built once (as a host does). Nothing is executed: the compiled query is plain data.</summary>
[MemoryDiagnoser]
public class CompileBenchmarks
{
    private LoadedShape _loaded = null!;
    private PreparedShape _prepared = null!;

    public static IEnumerable<string> SchemaPaths => ["full-compile", "prepared-schema"];

    public static IEnumerable<string> ShapeNames => Shapes.All.Select(shape => shape.Name);

    public static IEnumerable<string> BackendNames => Shapes.Backends;

    [ParamsSource(nameof(ShapeNames))]
    public string Shape { get; set; } = "";

    [ParamsSource(nameof(BackendNames))]
    public string Backend { get; set; } = "";

    [ParamsSource(nameof(SchemaPaths))]
    public string SchemaPath { get; set; } = "";

    [GlobalSetup]
    public void Setup()
    {
        _loaded = Shapes.Load(Shape);
        _prepared = Shapes.Prepare(_loaded);
    }

    [Benchmark]
    public object Compile() => SchemaPath == "prepared-schema" ? Shapes.CompilePrepared(_prepared, Backend) : Shapes.Compile(_loaded, Backend);
}
