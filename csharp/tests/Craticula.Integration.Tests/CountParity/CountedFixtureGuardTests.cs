using System.Text.Json;
using Xunit.Abstractions;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>
/// FR-014, US3-AS7: the number of counted fixtures per engine is derived here from the fixture files alone and compared
/// with the rule (<see cref="CountedFixtures"/>), by name. It does not use <c>ExecutionFixture</c> or
/// <c>CountedFixtures.IsCounted</c>, so it cannot repeat a bug of the rule. The run prints the number per engine.
/// </summary>
public sealed class CountedFixtureGuardTests(ITestOutputHelper output)
{
    private const string DatasetFile = "dataset.json";
    private const string ExpectedRowsFile = "expectedRows.json";
    private const string RequestFile = "agGridRequest.json";
    private const string ArtifactSuffix = ".artifact.json";
    private const string ExpectedDirectory = "expected";
    private const string Divergences = "allowedDivergence";
    private const string BackendKey = "backend";
    private const string EngineKey = "engine";
    private const string OutcomeKey = "outcome";
    private const string ErrorOutcome = "error";

    public static TheoryData<string> Engines() => new()
    {
        EngineNames.Mongo,
        EngineNames.OpenSearch,
        EngineNames.Elasticsearch
    };

    // US3-AS7, FR-014, SC-001
    [Theory]
    [MemberData(nameof(Engines))]
    public void Counted_Fixtures_Match_The_Independent_Derivation(string engineName)
    {
        var (backend, engine) = engineName == EngineNames.Mongo
            ? (EngineNames.Mongo, (string?)null)
            : (EngineNames.Search, engineName);

        var derived = DeriveCountedNames(backend, engine);
        var rule = CountedFixtures.NamesFor(backend, engine);
        var grouped = CountedFixtures.NamesFor(backend, engine, grouped: true).Count;
        var flat = CountedFixtures.NamesFor(backend, engine, grouped: false).Count;
        var report = $"counted fixtures on {engineName}: {rule.Count} (derived {derived.Count}; grouped {grouped}, flat {flat})";

        output.WriteLine(report);

        Assert.True(derived.Count > 0, report);
        Assert.True(
            derived.SequenceEqual(rule),
            $"{report}; only derived: [{string.Join(", ", derived.Except(rule))}]; only in rule: [{string.Join(", ", rule.Except(derived))}]");
        Assert.True(rule.Count > 0, report);
        Assert.True(grouped + flat == rule.Count, report);
    }

    private static List<string> DeriveCountedNames(string backend, string? engine) =>
        FixtureDirectories()
            .Where(dir => HasArtifact(dir, backend))
            .Where(dir => !HasSetValuesRequest(dir))
            .Where(dir => !DeclaresError(dir, backend, engine))
            .Select(dir => Path.GetRelativePath(Root(), dir).Replace('\\', '/'))
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

    private static string Root() => RepoPaths.Fixture();

    private static IEnumerable<string> FixtureDirectories() =>
        Directory.EnumerateFiles(Root(), ExpectedRowsFile, SearchOption.AllDirectories)
            .Select(file => Path.GetDirectoryName(file)!)
            .Where(dir => File.Exists(Path.Combine(dir, DatasetFile)));

    private static bool HasArtifact(string dir, string backend) =>
        File.Exists(Path.Combine(dir, ExpectedDirectory, backend + ArtifactSuffix));

    private static bool HasSetValuesRequest(string dir)
    {
        using var request = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, RequestFile)));
        return request.RootElement.ValueKind == JsonValueKind.Object
            && request.RootElement.TryGetProperty("setValuesRequest", out _);
    }

    /// <summary>The same fall-through as <c>ExecutionFixture.ExpectationFor</c>: the exact engine entry first, else the backend-wide one.</summary>
    private static bool DeclaresError(string dir, string backend, string? engine)
    {
        using var expected = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, ExpectedRowsFile)));
        if (!expected.RootElement.TryGetProperty(Divergences, out var list))
        {
            return false;
        }

        var entries = list.EnumerateArray().Where(entry => ReadString(entry, BackendKey) == backend).ToList();
        var exact = entries.Where(entry => ReadString(entry, EngineKey) == engine).Select(entry => (JsonElement?)entry).FirstOrDefault();
        var chosen = exact ?? entries.Where(entry => ReadString(entry, EngineKey) is null).Select(entry => (JsonElement?)entry).FirstOrDefault();

        return chosen is { } entryFound && ReadString(entryFound, OutcomeKey) == ErrorOutcome;
    }

    private static string? ReadString(JsonElement entry, string property) =>
        entry.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}
