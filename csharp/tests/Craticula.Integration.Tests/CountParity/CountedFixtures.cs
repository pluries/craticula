using System.Text.Json;
using Craticula.Core.Ir;
using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>The one rule that picks the fixtures whose count is checked, the same for every engine (FR-003).</summary>
internal static class CountedFixtures
{
    public static bool IsSetValues(ExecutionFixture fixture) =>
        fixture.Request.ValueKind == JsonValueKind.Object && fixture.Request.TryGetProperty("setValuesRequest", out _);

    /// <summary>A row fetch the engine is expected to answer: not a distinct-values request, no declared refusal (XEQ-4).</summary>
    public static bool IsCounted(ExecutionFixture fixture, string backend, string? engine) =>
        !IsSetValues(fixture) && fixture.ExpectationFor(backend, engine) is not ExpectError;

    /// <summary>
    /// FR-013: the fixture's expected rows are the whole match set only when its own window cannot have cut them off:
    /// no window, or one that starts at row 0 and is not filled.
    /// </summary>
    public static bool OwnWindowTruncates(PageSpec ownPage, int expectedRows) => ownPage switch
    {
        RangePage range => range.StartRow != 0 || expectedRows >= range.EndRow,
        _ => false
    };

    public static bool IsGroupedLevel(ExecutionFixture fixture) =>
        PreparedRequest.For(fixture, fixture.Schema).Plan is { GroupColumn: not null };

    public static IReadOnlyList<string> NamesFor(string backend, string? engine, bool? grouped = null) =>
        ExecutionFixture.All()
            .Select(ExecutionFixture.Load)
            .Where(fixture => fixture.Backends.Contains(backend) && IsCounted(fixture, backend, engine))
            .Where(fixture => grouped is null || IsGroupedLevel(fixture) == grouped)
            .Select(fixture => fixture.Name)
            .ToList();

    public static TheoryData<string> TheoryDataFor(string backend, string? engine, bool? grouped = null)
    {
        var data = new TheoryData<string>();
        foreach (var name in NamesFor(backend, engine, grouped))
        {
            data.Add(name);
        }

        return data;
    }
}
