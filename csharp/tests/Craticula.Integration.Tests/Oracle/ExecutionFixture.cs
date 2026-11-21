using System.Text.Json;
using Craticula.Core.Schema;

namespace Craticula.Integration.Tests.Oracle;

/// <summary>What a backend must do for a fixture (XEQ-1, XEQ-4): return rows, or refuse the query.</summary>
public abstract record Expectation;

/// <summary>The backend returns these rows (the fixture's main result, or an XEQ-4 <c>rows</c> override).</summary>
public sealed record ExpectRows(ExpectedResult Result) : Expectation;

/// <summary>The backend refuses the query (an XEQ-4 <c>error</c> entry); the harness asserts that it does.</summary>
public sealed record ExpectError(string Reason) : Expectation;

public sealed record ExpectedResult(IReadOnlyList<string> Columns, IReadOnlyList<IReadOnlyList<JsonElement>> Rows);

/// <summary>One XEQ-4 entry: <c>Engine</c> is null for a backend-wide entry (or for <c>opensearch</c>/<c>elasticsearch</c> on search).</summary>
public sealed record Divergence(string Backend, string? Engine, string Reason, Expectation Expectation);

/// <summary>One seed row, keyed by LOGICAL colId, with the reason the row is there.</summary>
public sealed record SeedRow(IReadOnlyDictionary<string, JsonElement> Cells, string? Why);

/// <summary>
/// One execution-equality fixture (<c>spec/semantics.md</c> XEQ-1..XEQ-4): the schema, the AG Grid request, the
/// seed and the hand-derived expected result, plus the backends the fixture has a compiled artifact for.
/// Parsed from the fixture's own files and nothing else, so the harnesses (#2206/#2207) cannot drift from the
/// oracle's shape.
/// </summary>
public sealed class ExecutionFixture
{
    public required string Name { get; init; }

    public required string Directory { get; init; }

    public required GridSchema Schema { get; init; }

    public required JsonElement Request { get; init; }

    public required IReadOnlyList<SeedRow> Seed { get; init; }

    public required ExpectedResult Expected { get; init; }

    public required IReadOnlyList<Divergence> Divergences { get; init; }

    /// <summary>The <c>expected/&lt;backend&gt;.artifact.json</c> stems: the backends the tier applies to (XEQ-1).</summary>
    public required IReadOnlyList<string> Backends { get; init; }

    /// <summary>Every fixture directory carrying the pair, as <c>category/slug</c>, ordinally sorted.</summary>
    public static IReadOnlyList<string> All() =>
        System.IO.Directory.EnumerateFiles(RepoPaths.Fixture(), "expectedRows.json", SearchOption.AllDirectories)
            .Select(file => Path.GetRelativePath(RepoPaths.Fixture(), Path.GetDirectoryName(file)!).Replace('\\', '/'))
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

    public static ExecutionFixture Load(string name)
    {
        var dir = RepoPaths.Fixture(name.Split('/'));
        var schema = GridSchema.Parse(File.ReadAllText(Path.Combine(dir, "schema.json")));
        var request = Parse(Path.Combine(dir, "agGridRequest.json")).RootElement.Clone();

        var seed = ReadSeed(Parse(Path.Combine(dir, "dataset.json")).RootElement);

        var expectedRoot = Parse(Path.Combine(dir, "expectedRows.json")).RootElement;
        var divergences = expectedRoot.TryGetProperty("allowedDivergence", out var list)
            ? list.EnumerateArray().Select(ReadDivergence).ToList()
            : [];

        var expectedDir = Path.Combine(dir, "expected");
        var backends = System.IO.Directory.Exists(expectedDir)
            ? System.IO.Directory.EnumerateFiles(expectedDir, "*.artifact.json")
                .Select(file => Path.GetFileName(file)[..^".artifact.json".Length])
                .OrderBy(stem => stem, StringComparer.Ordinal)
                .ToList()
            : [];

        return new ExecutionFixture
        {
            Name = name,
            Directory = dir,
            Schema = schema,
            Request = request,
            Seed = seed,
            Expected = ReadResult(expectedRoot),
            Divergences = divergences,
            Backends = backends
        };
    }

    /// <summary>The seed rows of a <c>dataset.json</c> document (the shape of <c>fixtures/schemas/dataset.schema.json</c>).</summary>
    public static IReadOnlyList<SeedRow> ReadSeed(JsonElement dataset) =>
        dataset.GetProperty("rows").EnumerateArray()
            .Select(entry => new SeedRow(
                entry.GetProperty("row").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.Clone(), StringComparer.Ordinal),
                entry.TryGetProperty("why", out var why) ? why.GetString() : null))
            .ToList();

    /// <summary>
    /// A fixture built in memory (the parity property's generated cases, T-3, PAR-1): a schema, a request and a seed with no
    /// directory behind them and no expectation, because the property compares engines with each other, not with an oracle.
    /// <see cref="Load"/> is the only way a fixture reads files; nothing here touches the disk.
    /// </summary>
    public static ExecutionFixture FromMemory(
        string name,
        GridSchema schema,
        string requestJson,
        IReadOnlyList<SeedRow> seed,
        ExpectedResult? expected = null,
        IReadOnlyList<Divergence>? divergences = null) =>
        new()
        {
            Name = name,
            Directory = string.Empty,
            Schema = schema,
            Request = Parse(requestJson, isText: true).RootElement.Clone(),
            Seed = seed,
            Expected = expected ?? new ExpectedResult([], []),
            Divergences = divergences ?? [],
            Backends = []
        };

    /// <summary>
    /// What <paramref name="backend"/> (and, on search, <paramref name="engine"/>) must do: the fixture's own
    /// XEQ-4 entry when it has one, else the main result. An entry without an engine covers both search engines.
    /// </summary>
    public Expectation ExpectationFor(string backend, string? engine = null)
    {
        var entry = Divergences.FirstOrDefault(d => d.Backend == backend && d.Engine == engine)
            ?? Divergences.FirstOrDefault(d => d.Backend == backend && d.Engine is null);
        return entry?.Expectation ?? new ExpectRows(Expected);
    }

    private static Divergence ReadDivergence(JsonElement entry)
    {
        var outcome = entry.GetProperty("outcome").GetString();
        var reason = entry.GetProperty("reason").GetString()!;
        Expectation expectation = outcome switch
        {
            "rows" => new ExpectRows(ReadResult(entry.GetProperty("expected"))),
            "error" => new ExpectError(reason),
            _ => throw new InvalidOperationException($"Unknown allowedDivergence outcome '{outcome}'.")
        };

        return new Divergence(
            entry.GetProperty("backend").GetString()!,
            entry.TryGetProperty("engine", out var engine) ? engine.GetString() : null,
            reason,
            expectation);
    }

    private static ExpectedResult ReadResult(JsonElement element) =>
        new(
            element.GetProperty("columns").EnumerateArray().Select(c => c.GetString()!).ToList(),
            element.GetProperty("rows").EnumerateArray()
                .Select(row => (IReadOnlyList<JsonElement>)row.EnumerateArray().Select(c => c.Clone()).ToList())
                .ToList());

    private static JsonDocument Parse(string pathOrText, bool isText = false) =>
        JsonDocument.Parse(isText ? pathOrText : File.ReadAllText(pathOrText));
}
