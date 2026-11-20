using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>
/// The engine-neutral "count equals the unpaged rows" comparison (CNT-3, CNT-6, CNT-7). A counted fixture is one the engine is
/// expected to answer, so a refusal, a wrong count or a wrong row number fails; a mismatch is a finding, never an exception (FR-012).
/// </summary>
internal static class CountComparison
{
    public static Task AssertCountEqualsUnpagedRowsAsync(ICountParityEngine engine, string name) =>
        AssertCountEqualsUnpagedRowsAsync(engine, ExecutionFixture.Load(name));

    public static async Task AssertCountEqualsUnpagedRowsAsync(ICountParityEngine engine, ExecutionFixture fixture)
    {
        ArgumentNullException.ThrowIfNull(engine);
        ArgumentNullException.ThrowIfNull(fixture);
        if (ReturnsWhenNotCounted(engine, fixture))
        {
            return;
        }

        var run = await RunEngine(engine, fixture).ConfigureAwait(false);
        CompareToUnpaged(engine, fixture, run);
        CompareToExpectedRows(engine, fixture, run);
    }

    internal static string FailureMessage(string name, string label, long count, int unpaged, string countedQuery) =>
        $"{name} on {label}: the count says {count} but the unpaged request returns {unpaged} row(s).\n  count query: {countedQuery}";

    private static string Label(ICountParityEngine engine) => engine.Engine ?? engine.Backend;

    private static bool ReturnsWhenNotCounted(ICountParityEngine engine, ExecutionFixture fixture) =>
        !CountedFixtures.IsCounted(fixture, engine.Backend, engine.Engine);

    private static async Task<CountParityRun> RunEngine(ICountParityEngine engine, ExecutionFixture fixture)
    {
        try
        {
            return await engine.RunAsync(fixture).ConfigureAwait(false);
        }
        catch (EngineRefusedException exception)
        {
            Assert.Fail($"{fixture.Name} on {Label(engine)}: the engine refused the query although the fixture declares no refusal: {exception.Message}");
            throw;
        }
    }

    private static void CompareToUnpaged(ICountParityEngine engine, ExecutionFixture fixture, CountParityRun run)
    {
        var count = run.Count ?? 0;
        Assert.True(count == run.UnpagedRows, FailureMessage(fixture.Name, Label(engine), count, run.UnpagedRows, run.CountedQuery));
    }

    private static void CompareToExpectedRows(ICountParityEngine engine, ExecutionFixture fixture, CountParityRun run)
    {
        var expectedRows = ((ExpectRows)fixture.ExpectationFor(engine.Backend, engine.Engine)).Result.Rows.Count;
        var ownPage = PreparedRequest.For(fixture, fixture.Schema).Parsed!.Page;
        if (CountedFixtures.OwnWindowTruncates(ownPage, expectedRows))
        {
            return;
        }

        Assert.True(
            run.UnpagedRows == expectedRows,
            $"{fixture.Name} on {Label(engine)}: the unpaged request returns {run.UnpagedRows} row(s) but the fixture expects {expectedRows}.\n  count query: {run.CountedQuery}");
    }
}
