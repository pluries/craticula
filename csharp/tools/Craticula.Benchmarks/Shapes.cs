using Craticula.Conformance.Driver;

namespace Craticula.Benchmarks;

internal sealed record Shape(string Name, string Fixture);

internal sealed record LoadedShape(string Name, string SchemaJson, string RequestJson);

/// <summary>The named request shapes of the compile benchmark: each is a conformance fixture (<c>spec/fixtures/&lt;family&gt;/&lt;case&gt;</c>), so a shape's request and schema are the ones the compilers are already graded on.</summary>
internal static class Shapes
{
    public static readonly IReadOnlyList<Shape> All =
    [
        new("plain-page", "sort-paging/001-single-key-string-asc-nulls-last-default"),
        new("filter-tree", "filter-tree/001-implicit-and-four-columns"),
        new("deep-filter", "filter-tree/012-customfilters-depth-5"),
        new("group-aggregate", "group-aggregation/001-group-top-level-no-keys-consumed")
    ];

    public static readonly IReadOnlyList<string> Backends = ["postgres", "mongo", "search"];

    public static LoadedShape Load(string name)
    {
        var shape = All.FirstOrDefault(candidate => candidate.Name == name)
            ?? throw new ArgumentException($"Unknown shape '{name}'. Available shapes: {string.Join(", ", All.Select(candidate => candidate.Name))}.", nameof(name));
        var folder = Path.Combine(RepositoryRoot(), "spec", "fixtures", shape.Fixture);

        return new LoadedShape(
            shape.Name,
            File.ReadAllText(Path.Combine(folder, "schema.json")),
            File.ReadAllText(Path.Combine(folder, "agGridRequest.json")));
    }

    public static object Compile(LoadedShape shape, string backend) =>
        RequestCompiler.Compile(backend, shape.SchemaJson, shape.RequestJson);

    private static string RepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, "spec", "fixtures")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException("spec/fixtures was not found above " + AppContext.BaseDirectory);
    }
}
