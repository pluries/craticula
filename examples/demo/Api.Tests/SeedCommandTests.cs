using Demo.Api.Seed;
using Microsoft.Data.Sqlite;

namespace Demo.Api.Tests;

/// <summary>The seed command's argument parsing and orchestration, with fake seeders: no database is needed.</summary>
public sealed class SeedCommandTests
{
    private static SeedTarget Target(string name, Func<IReadOnlyList<OrderRow>, Task<long>> seed, bool isDefault = true) =>
        new(name, seed, count => $"{name}: {count} rows.", $"hint for {name}", isDefault);

    private static SeedTarget Ok(string name, bool isDefault = true) => Target(name, rows => Task.FromResult((long)rows.Count), isDefault);

    private static SeedTarget Down(string name) =>
        Target(name, _ => throw new TimeoutException($"{name} is down"));

    // A refused password, a refused connection and a missing database are setting problems (like MySQL 1045): the provider fails with its hint
    // and the next one still runs. A statement error is a bug and ends the command.
    [Theory]
    [InlineData("28P01", 2)]
    [InlineData("28000", 2)]
    [InlineData("3D000", 2)]
    [InlineData("57P01", 2)]
    public async Task Run_WhenPostgresRefusesOrIsGoingAway_TheNextStillRunsAndTheExitIs2(string sqlState, int expectedExit)
    {
        var next = false;
        var targets = new[]
        {
            Target("postgres", _ => throw new Npgsql.PostgresException("the server said so", "FATAL", "FATAL", sqlState)),
            Target("mongo", rows => { next = true; return Task.FromResult((long)rows.Count); })
        };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync([], targets, output, error);

        Assert.Equal(expectedExit, exit);
        Assert.True(next);
        Assert.Contains("hint for postgres", error.ToString());
    }

    [Fact]
    public async Task Run_WhenPostgresSaysAStatementIsWrong_TheCommandEnds()
    {
        var targets = new[] { Target("postgres", _ => throw new Npgsql.PostgresException("syntax error", "ERROR", "ERROR", "42601")) };
        using var output = new StringWriter();
        using var error = new StringWriter();

        await Assert.ThrowsAsync<Npgsql.PostgresException>(() => SeedCommand.RunAsync([], targets, output, error));
    }

    [Fact]
    public void SplitRows_WithoutTheOption_KeepsTheNamesAndTheDefaultCount()
    {
        var split = SeedCommand.SplitRows(["mongo", "postgres"]);

        Assert.Null(split.Error);
        Assert.Equal(OrderGenerator.DefaultCount, split.Rows);
        Assert.Equal(["mongo", "postgres"], split.Names);
    }

    [Theory]
    [InlineData("--rows", "1000000", "postgres")]
    [InlineData("postgres", "--rows", "1000000")]
    public void SplitRows_TakesTheCountFromAnyPosition_AndLeavesTheNames(params string[] args)
    {
        var split = SeedCommand.SplitRows(args);

        Assert.Null(split.Error);
        Assert.Equal(1_000_000, split.Rows);
        Assert.Equal(["postgres"], split.Names);
    }

    [Theory]
    [InlineData("--rows")]
    [InlineData("--rows", "ten")]
    [InlineData("--rows", "0")]
    [InlineData("--rows", "-5")]
    [InlineData("--rows", "1", "--rows", "2")]
    public void SplitRows_RefusesAMissingZeroNegativeNonNumericOrRepeatedCount(params string[] args)
    {
        var split = SeedCommand.SplitRows(args);

        Assert.NotNull(split.Error);
        Assert.Contains("--rows", split.Error);
    }

    [Fact]
    public async Task Run_WithACount_GeneratesThatManyRows()
    {
        long seen = 0;
        var targets = new[] { Target("postgres", rows => { seen = rows.Count; return Task.FromResult((long)rows.Count); }) };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync([], targets, output, error, rowCount: 1234);

        Assert.Equal(0, exit);
        Assert.Equal(1234, seen);
        Assert.Contains("Generated 1234 orders", output.ToString());
    }

    [Fact]
    public void Parse_WithNoArgument_GivesTheDefaultTargetsOnly()
    {
        var plan = SeedCommand.Parse([], [Ok("postgres"), Ok("mongo"), Ok("later", isDefault: false)]);

        Assert.Equal(["postgres", "mongo"], plan.Targets.Select(t => t.Name));
        Assert.Empty(plan.Unknown);
    }

    [Fact]
    public void Parse_TheRealTargets_AreTodaysDefaultPostgresMongoThenSqlite()
    {
        Assert.Equal(["postgres", "mongo", "sqlite"], SeedCommand.Parse([], SeedTargets.All).Targets.Select(t => t.Name));
    }

    [Fact]
    public void Parse_WithNames_GivesThatSubsetInTheOrderGivenWithoutRepeats()
    {
        var plan = SeedCommand.Parse(["mongo", "Later", "mongo"], [Ok("postgres"), Ok("mongo"), Ok("later", isDefault: false)]);

        Assert.Equal(["mongo", "later"], plan.Targets.Select(t => t.Name));
        Assert.Empty(plan.Unknown);
    }

    [Fact]
    public async Task Run_WithAnUnknownName_Exits2ListingTheKnownNamesAndSeedsNothing()
    {
        var seeded = false;
        var known = new[] { Target("postgres", _ => { seeded = true; return Task.FromResult(0L); }), Ok("mongo") };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync(["postgres", "nosuch"], known, output, error);

        Assert.Equal(2, exit);
        Assert.False(seeded);
        Assert.Contains("nosuch", error.ToString());
        Assert.Contains("postgres, mongo", error.ToString());
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public async Task Run_WhenOneSeederFails_TheNextStillRunsAndTheExitIs2()
    {
        var second = 0;
        var known = new[] { Down("postgres"), Target("mongo", rows => { second++; return Task.FromResult((long)rows.Count); }) };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync([], known, output, error);

        Assert.Equal(2, exit);
        Assert.Equal(1, second);
        Assert.Contains("mongo: 20000 rows.", output.ToString());
        Assert.Contains("Seed failed for postgres: postgres is down", error.ToString());
        Assert.Contains("hint for postgres", error.ToString());
    }

    [Fact]
    public async Task Run_WhenASqliteFileIsReadOnly_ReportsThatProviderAndTheNextStillRuns()
    {
        var next = 0;
        var known = new[]
        {
            Target("sqlite", _ => throw new SqliteException("attempt to write a readonly database", 8)),
            Target("postgres", rows => { next++; return Task.FromResult((long)rows.Count); })
        };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync(["sqlite", "postgres"], known, output, error);

        Assert.Equal(2, exit);
        Assert.Equal(1, next);
        Assert.Contains("Seed failed for sqlite:", error.ToString());
        Assert.Contains("hint for sqlite", error.ToString());
    }

    [Fact]
    public async Task Run_WhenTheDataFolderCannotBeWritten_ReportsThatProviderAndExits2()
    {
        var known = new[] { Target("sqlite", _ => throw new UnauthorizedAccessException("Access to the path is denied.")), Ok("postgres") };
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync(["sqlite", "postgres"], known, output, error);

        Assert.Equal(2, exit);
        Assert.Contains("postgres: 20000 rows.", output.ToString());
        Assert.Contains("Seed failed for sqlite: Access to the path is denied.", error.ToString());
    }

    [Fact]
    public async Task Run_AnUnexpectedExceptionStillEndsTheCommand()
    {
        var known = new[] { Target("sqlite", _ => throw new InvalidCastException("a bug")), Ok("postgres") };
        using var output = new StringWriter();
        using var error = new StringWriter();

        await Assert.ThrowsAsync<InvalidCastException>(() => SeedCommand.RunAsync(["sqlite", "postgres"], known, output, error));
    }

    [Fact]
    public async Task Run_WhenAllSeededWithTheRightCounts_Exits0AndPrintsEachLine()
    {
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync([], [Ok("postgres"), Ok("mongo")], output, error);

        Assert.Equal(0, exit);
        Assert.Contains("Generated 20000 orders", output.ToString());
        Assert.Contains("postgres: 20000 rows.", output.ToString());
        Assert.Equal("", error.ToString());
    }

    [Fact]
    public async Task Run_WhenACountDiffers_Exits1()
    {
        var known = new[] { Ok("postgres"), Target("mongo", _ => Task.FromResult(5L)) };
        using var output = new StringWriter();
        using var error = new StringWriter();

        Assert.Equal(1, await SeedCommand.RunAsync([], known, output, error));
    }

    [Fact]
    public async Task Run_AFailureOutranksACountMismatch()
    {
        var known = new[] { Target("postgres", _ => Task.FromResult(5L)), Down("mongo") };
        using var output = new StringWriter();
        using var error = new StringWriter();

        Assert.Equal(2, await SeedCommand.RunAsync([], known, output, error));
    }
}
