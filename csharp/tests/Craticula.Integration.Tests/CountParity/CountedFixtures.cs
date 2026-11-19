using Craticula.Core.Ir;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Skeleton (T006): the one rule that picks the fixtures whose count is checked (FR-003).</summary>
internal static class CountedFixtures
{
    public static bool IsSetValues(ExecutionFixture fixture) => throw new NotImplementedException();

    public static bool IsCounted(ExecutionFixture fixture, string backend, string? engine) => throw new NotImplementedException();

    public static bool OwnWindowTruncates(PageSpec ownPage, int expectedRows) => throw new NotImplementedException();

    public static bool IsGroupedLevel(ExecutionFixture fixture) => throw new NotImplementedException();

    public static IReadOnlyList<string> NamesFor(string backend, string? engine, bool? grouped = null) => throw new NotImplementedException();

    public static TheoryData<string> TheoryDataFor(string backend, string? engine, bool? grouped = null) => throw new NotImplementedException();
}
