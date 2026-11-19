using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>Skeleton (T007): the engine-neutral "count equals the unpaged rows" comparison.</summary>
internal static class CountComparison
{
    public static Task AssertCountEqualsUnpagedRowsAsync(ICountParityEngine engine, string name) => throw new NotImplementedException();

    public static Task AssertCountEqualsUnpagedRowsAsync(ICountParityEngine engine, ExecutionFixture fixture) => throw new NotImplementedException();

    internal static string FailureMessage(string name, string label, long count, int unpaged, string countedQuery) => throw new NotImplementedException();
}
