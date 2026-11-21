using System.Text.Json;
using Craticula.Integration.Tests.Containers.Document;
using Craticula.Integration.Tests.Oracle;
using Xunit.Sdk;

namespace Craticula.Integration.Tests.CountParity;

/// <summary>
/// The engine-neutral comparison, proved with a stub engine (FR-015): the failure message (US3-AS1, FR-008), the zero reading
/// (FR-004), the refusal rule (US1-AS4, US2-AS5) and the expected-rows oracle (FR-013). A ROW-FETCH request of a real
/// fixture is the stub's request, so its own window is read and the oracle path is not masked by a missing page.
/// </summary>
public sealed class CountParityComparisonTests
{
    private const string BaseFixture = "sort-paging/001-single-key-string-asc-nulls-last-default";
    private const string StubName = "stub/count-case";
    private const string EngineLabel = "opensearch";
    private const string CountedQuery = "{\"size\":0,\"track_total_hits\":true}";
    private const string RefusalReason = "declared refusal";
    private const string OwnStart = "\"startRow\": 0";

    // US3-AS1, FR-008
    [Fact]
    public async Task A_Count_One_Too_High_Fails_With_The_Fixture_Engine_Both_Numbers_And_The_Query()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(4, 3, CountedQuery));
        var fixture = Stub(expectedRows: 3);

        var failure = await Assert.ThrowsAnyAsync<XunitException>(() => CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, fixture));

        Assert.Contains(StubName, failure.Message, StringComparison.Ordinal);
        Assert.Contains(EngineLabel, failure.Message, StringComparison.Ordinal);
        Assert.Contains("4", failure.Message, StringComparison.Ordinal);
        Assert.Contains("3", failure.Message, StringComparison.Ordinal);
        Assert.Contains(CountedQuery, failure.Message, StringComparison.Ordinal);
    }

    // US3-AS2
    [Fact]
    public async Task A_Count_That_Equals_The_Unpaged_Rows_Passes()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(3, 3, CountedQuery));

        await CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 3));

        Assert.Equal(1, engine.Calls);
    }

    // US3-AS3, US1-AS2, FR-004
    [Fact]
    public async Task A_Missing_Count_Is_Read_As_Zero()
    {
        var engine = new StubEngine(null, new CountParityRun(null, 0, CountedQuery), EngineNames.Mongo);

        await CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 0));

        Assert.Equal(1, engine.Calls);
    }

    // US1-AS2, FR-004: a missing count is 0, so rows in the unpaged result are a mismatch
    [Fact]
    public async Task A_Missing_Count_With_Rows_Expected_Fails()
    {
        var engine = new StubEngine(null, new CountParityRun(null, 2, CountedQuery), EngineNames.Mongo);

        await Assert.ThrowsAnyAsync<XunitException>(() => CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 2)));
    }

    // US3-AS5, US1-AS4, US2-AS5: a fixture whose backend declares an XEQ-4 refusal is not compared, the engine is not asked
    [Fact]
    public async Task A_Declared_Refusal_Is_Not_Compared()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(9, 1, CountedQuery));

        await CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 1, declaresRefusal: true));

        Assert.Equal(0, engine.Calls);
    }

    // US3-AS5: the same stub without the declaration is compared, and its wrong count fails
    [Fact]
    public async Task The_Same_Stub_With_Rows_Is_Compared()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(9, 1, CountedQuery));

        await Assert.ThrowsAnyAsync<XunitException>(() => CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 1)));

        Assert.Equal(1, engine.Calls);
    }

    // US1-AS6, US2-AS7, FR-013: count and unpaged agree on a wrong number, the own window (0..100) does not truncate
    [Fact]
    public async Task The_Expected_Rows_Are_An_Oracle_When_The_Window_Does_Not_Truncate()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(5, 5, CountedQuery));

        var failure = await Assert.ThrowsAnyAsync<XunitException>(() => CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 3)));

        Assert.Contains(StubName, failure.Message, StringComparison.Ordinal);
    }

    // US1-AS5: the own window starts at row 5, so the expected rows are a page, not the whole match set
    [Fact]
    public async Task A_Window_That_Truncates_Skips_The_Oracle()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(5, 5, CountedQuery));

        await CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 3, ownStart: 5));

        Assert.Equal(1, engine.Calls);
    }

    // The plan's RunEngine step: an engine refusal on a counted fixture is a failure naming fixture and engine
    [Fact]
    public async Task A_Refusal_By_A_Counted_Fixtures_Engine_Fails_Naming_The_Fixture_And_The_Engine()
    {
        var engine = new StubEngine(EngineLabel, new CountParityRun(0, 0, CountedQuery)) { Refusal = new EngineRefusedException(RefusalReason) };

        var failure = await Assert.ThrowsAnyAsync<XunitException>(() => CountComparison.AssertCountEqualsUnpagedRowsAsync(engine, Stub(expectedRows: 0)));

        Assert.Contains(StubName, failure.Message, StringComparison.Ordinal);
        Assert.Contains(EngineLabel, failure.Message, StringComparison.Ordinal);
    }

    private static ExecutionFixture Stub(int expectedRows, bool declaresRefusal = false, int ownStart = 0)
    {
        var template = ExecutionFixture.Load(BaseFixture);
        var request = template.Request.GetRawText().Replace(OwnStart, $"\"startRow\": {ownStart}", StringComparison.Ordinal);
        var cell = JsonDocument.Parse("1").RootElement.Clone();
        var rows = Enumerable.Range(0, expectedRows).Select(_ => (IReadOnlyList<JsonElement>)[cell]).ToList();
        IReadOnlyList<Divergence> divergences = declaresRefusal
            ? [new Divergence(EngineNames.Search, EngineNames.OpenSearch, RefusalReason, new ExpectError(RefusalReason))]
            : [];
        return ExecutionFixture.FromMemory(StubName, template.Schema, request, [], new ExpectedResult(["id"], rows), divergences);
    }

    private sealed class StubEngine(string? engine, CountParityRun run, string backend = EngineNames.Search) : ICountParityEngine
    {
        public string Backend => backend;

        public string? Engine => engine;

        public int Calls { get; private set; }

        public Exception? Refusal { get; init; }

        public Task<CountParityRun> RunAsync(ExecutionFixture fixture)
        {
            Calls++;
            return Refusal is null ? Task.FromResult(run) : Task.FromException<CountParityRun>(Refusal);
        }
    }
}
