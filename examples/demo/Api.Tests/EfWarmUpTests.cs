using Craticula.Core.Export;
using Craticula.Core.Grid;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Demo.Api.Grid;
using Microsoft.Extensions.Logging.Abstractions;

namespace Demo.Api.Tests;

/// <summary>Task #3843: the EF route builds its model when the API starts, so the first request after a restart cannot time out.</summary>
public class EfWarmUpTests
{
    private static GridRequestPreparer Preparer() =>
        new(GridSchema.Parse(File.ReadAllText(TestPaths.SchemaFile())), DemoLimits.Default);

    [Fact]
    public async Task Start_compiles_one_query_on_every_route_whose_name_starts_with_ef_and_on_no_other()
    {
        var ef = new FakeService("ef");
        var efSqlite = new FakeService("ef-sqlite");
        var postgres = new FakeService("postgres");
        var mongo = new FakeService("mongo");
        var warmUp = new EfWarmUp([ef, efSqlite, postgres, mongo], Preparer(), NullLogger<EfWarmUp>.Instance);

        await warmUp.StartAsync(CancellationToken.None);

        Assert.Equal(1, ef.Compiles);
        Assert.Equal(1, efSqlite.Compiles);
        Assert.Equal(0, postgres.Compiles);
        Assert.Equal(0, mongo.Compiles);
    }

    [Fact]
    public async Task A_failing_warm_up_never_stops_the_API_from_starting_and_the_other_routes_still_warm()
    {
        var broken = new FakeService("ef", throwOnCompile: true);
        var healthy = new FakeService("ef-sqlite");
        var warmUp = new EfWarmUp([broken, healthy], Preparer(), NullLogger<EfWarmUp>.Instance);

        await warmUp.StartAsync(CancellationToken.None);

        Assert.Equal(1, broken.Compiles);
        Assert.Equal(1, healthy.Compiles);
    }

    [Fact]
    public async Task The_warm_up_request_is_a_small_valid_page_that_names_no_database()
    {
        var ef = new FakeService("ef");
        await new EfWarmUp([ef], Preparer(), NullLogger<EfWarmUp>.Instance).StartAsync(CancellationToken.None);

        var page = Assert.IsType<RangePage>(ef.LastRequest!.Parsed.Page);
        Assert.Equal(0, page.StartRow);
        Assert.True(page.EndRow <= 50);
    }

    [Fact]
    public async Task Stop_does_nothing()
    {
        var warmUp = new EfWarmUp([], Preparer(), NullLogger<EfWarmUp>.Instance);
        await warmUp.StopAsync(CancellationToken.None);
    }

    private sealed class FakeService(string name, bool throwOnCompile = false) : IGridService
    {
        public int Compiles { get; private set; }

        public PreparedRows? LastRequest { get; private set; }

        public string Name => name;

        public CompiledQueryView Compile(PreparedRows request)
        {
            Compiles++;
            LastRequest = request;
            return throwOnCompile ? throw new InvalidOperationException("model failed") : new CompiledQueryView("sql", "fake", "SELECT 1", []);
        }

        public Task<GridPageResult> FetchRowsAsync(PreparedRows request, CancellationToken cancellationToken) =>
            throw new NotSupportedException("a warm-up must not run a query");

        public Task<IReadOnlyList<object?>> FetchSetValuesAsync(PreparedSetValues request, CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        public IAsyncEnumerable<ExportRow> StreamExportAsync(PreparedRows request, CancellationToken cancellationToken) =>
            throw new NotSupportedException();
    }
}
