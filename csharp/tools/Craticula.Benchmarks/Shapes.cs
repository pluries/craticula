using Craticula.Conformance.Driver;

namespace Craticula.Benchmarks;

internal sealed record Shape(string Name, string Fixture);

internal sealed record LoadedShape(string Name, string SchemaJson, string RequestJson);

internal sealed record PreparedShape(string Name, Craticula.Core.Schema.GridSchema Schema, string RequestJson);

/// <summary>The named request shapes of the compile benchmark: each is a conformance fixture (<c>spec/fixtures/&lt;family&gt;/&lt;case&gt;</c>), so a shape's request and schema are the ones the compilers are already graded on.</summary>
internal static class Shapes
{
    public static readonly IReadOnlyList<Shape> All =
    [
        new("plain-page", "sort-paging/001-single-key-string-asc-nulls-last-default"),
        new("filter-tree", "filter-tree/001-implicit-and-four-columns"),
        new("deep-filter", "filter-tree/012-customfilters-depth-5"),
        new("group-aggregate", "group-aggregation/001-group-top-level-no-keys-consumed"),
        // count mode (CNT-8): the request carries requestContext.compileMode "count", so the same entry point answers the count question
        new("count", "count-mode/002-flat-number-filter")
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

    /// <summary>The schema built once, as a host does at start-up; <see cref="CompilePrepared"/> then pays only for the request.</summary>
    public static PreparedShape Prepare(LoadedShape shape) =>
        new(shape.Name, Craticula.Core.Schema.GridSchema.Parse(shape.SchemaJson), shape.RequestJson);

    public static object CompilePrepared(PreparedShape shape, string backend) =>
        RequestCompiler.Compile(backend, shape.Schema, shape.RequestJson);

    /// <summary>The compiled query as the conformance artifact text, so two compiles can be compared exactly.</summary>
    public static string Describe(object compiled)
    {
        using var stream = new MemoryStream();
        using (var writer = new System.Text.Json.Utf8JsonWriter(stream))
        {
            ArtifactWriter.Write(writer, compiled);
        }

        return System.Text.Encoding.UTF8.GetString(stream.ToArray());
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
