namespace Craticula.Benchmarks.Tests;

// Traceability: FR-17, AC-1
public class ShapeTests
{
    public static TheoryData<string, string> EveryShapeOnEveryBackend()
    {
        var data = new TheoryData<string, string>();
        foreach (var shape in Shapes.All)
        {
            foreach (var backend in Shapes.Backends)
            {
                data.Add(shape.Name, backend);
            }
        }

        return data;
    }

    [Theory]
    [MemberData(nameof(EveryShapeOnEveryBackend))]
    public void Compile_ANamedShape_LoadsItsFixtureAndCompilesOnTheBackend(string shape, string backend)
    {
        var compiled = Shapes.Compile(Shapes.Load(shape), backend);

        Assert.NotNull(compiled);
    }

    [Theory]
    [MemberData(nameof(EveryShapeOnEveryBackend))]
    public void CompilePrepared_AnAlreadyBuiltSchema_GivesExactlyTheArtifactOfTheFullCompile(string shape, string backend)
    {
        var loaded = Shapes.Load(shape);
        var prepared = Shapes.Prepare(loaded);

        var viaPrepared = Shapes.Describe(Shapes.CompilePrepared(prepared, backend));
        var viaFull = Shapes.Describe(Shapes.Compile(loaded, backend));

        Assert.False(string.IsNullOrEmpty(viaFull));
        Assert.Equal(viaFull, viaPrepared);
    }

    [Fact]
    public void CompilePrepared_AnUnknownBackend_Throws()
    {
        var prepared = Shapes.Prepare(Shapes.Load(Shapes.All[0].Name));

        Assert.Throws<NotSupportedException>(() => Shapes.CompilePrepared(prepared, "oracle-cloud"));
    }

    [Fact]
    public void Load_AnUnknownName_ThrowsAndNamesTheAvailableShapes()
    {
        var error = Assert.Throws<ArgumentException>(() => Shapes.Load("no-such-shape"));

        Assert.Contains("no-such-shape", error.Message);
        foreach (var shape in Shapes.All)
        {
            Assert.Contains(shape.Name, error.Message);
        }
    }

    [Fact]
    public void Compile_AnUnknownBackend_Throws()
    {
        Assert.Throws<NotSupportedException>(() => Shapes.Compile(Shapes.Load(Shapes.All[0].Name), "oracle-cloud"));
    }
}
