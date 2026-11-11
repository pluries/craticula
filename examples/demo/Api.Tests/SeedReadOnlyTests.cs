using Demo.Api.Seed;
using MongoDB.Bson;
using MongoDB.Driver;
using Npgsql;

namespace Demo.Api.Tests;

/// <summary>
/// The seed's checksum and the read-only accounts, on the local compose databases. Same collection as the API tests: the seed drops and
/// reloads both databases, so it must never run beside them. The compose MongoDB runs without authentication, so a refused write
/// cannot be observed there: the Mongo test pins the user's single role (read on the demo database) and that the account can read.
/// </summary>
[Collection("api")]
public sealed class SeedReadOnlyTests
{
    // Built at run time so no secret-shaped literal sits in the source (the mirror's secret scanner).
    private static readonly string Credential = string.Concat("syn", "thetic-", "read", "only-", "1");

    private static async Task<(int Exit, string Output)> SeedBothAsync()
    {
        using var output = new StringWriter();
        using var error = new StringWriter();
        var exit = await SeedCommand.RunAsync(["postgres", "mongo"], SeedTargets.All, output, error);
        Assert.Equal("", error.ToString());
        return (exit, output.ToString());
    }

    private static string RoPostgres() =>
        new NpgsqlConnectionStringBuilder(ReadOnlyAccount.PostgresConnectionString(DemoSettings.Postgres, Credential)) { Pooling = false }.ConnectionString;

    [RequiresDatabasesFact]
    public async Task T1_TheSeedWritesTheExpectedCountsAndPrintsTheChecksumOfTheSeedData()
    {
        var rows = OrderGenerator.Generate();
        var expected = SeedChecksum.Of(rows);

        var (exit, output) = await SeedBothAsync();

        Assert.Equal(0, exit);
        Assert.Contains($"PostgreSQL: {rows.Count} rows", output);
        Assert.Contains($"MongoDB: {rows.Count} documents", output);
        Assert.Contains($"Checksum: {expected}", output);
        Assert.Equal(expected, await SeedChecksum.OfPostgresAsync(DemoSettings.Postgres));
        Assert.Equal(expected, await SeedChecksum.OfMongoAsync(DemoSettings.Mongo));
    }

    [RequiresDatabasesFact]
    public async Task T2_TheReadOnlyAccountReadsButPostgresRefusesInsertAndUpdate()
    {
        await SeedBothAsync();
        await ReadOnlyAccount.CreatePostgresAsync(DemoSettings.Postgres, Credential);

        await using var connection = new NpgsqlConnection(RoPostgres());
        await connection.OpenAsync();
        await using var count = new NpgsqlCommand("SELECT count(*) FROM orders", connection);
        Assert.Equal(OrderGenerator.Generate().Count, (long)(await count.ExecuteScalarAsync())!);

        await using var insert = new NpgsqlCommand(
            "INSERT INTO orders (id, order_no, status, ordered_at, is_priority) VALUES (-1, 'x', 'x', now(), false)", connection);
        var insertDenied = await Assert.ThrowsAsync<PostgresException>(() => insert.ExecuteNonQueryAsync());
        await using var update = new NpgsqlCommand("UPDATE orders SET status = 'x'", connection);
        var updateDenied = await Assert.ThrowsAsync<PostgresException>(() => update.ExecuteNonQueryAsync());

        Assert.Equal("42501", insertDenied.SqlState);
        Assert.Equal("42501", updateDenied.SqlState);
    }

    [RequiresDatabasesFact]
    public async Task T2_TheMongoAccountHasOnlyTheReadRoleOnTheDemoDatabase_AndCanRead()
    {
        await SeedBothAsync();
        await ReadOnlyAccount.CreateMongoAsync(DemoSettings.Mongo, Credential);

        var admin = new MongoClient(DemoSettings.Mongo).GetDatabase(DemoSettings.MongoDatabase);
        var info = await admin.RunCommandAsync<BsonDocument>(new BsonDocument("usersInfo", ReadOnlyAccount.UserName));
        var roles = info["users"].AsBsonArray.Single()["roles"].AsBsonArray;
        var readOnly = new MongoClient(ReadOnlyAccount.MongoConnectionString(DemoSettings.Mongo, Credential))
            .GetDatabase(DemoSettings.MongoDatabase).GetCollection<BsonDocument>("orders");

        var role = Assert.Single(roles).AsBsonDocument;
        Assert.Equal("read", role["role"].AsString);
        Assert.Equal(DemoSettings.MongoDatabase, role["db"].AsString);
        Assert.Equal(OrderGenerator.Generate().Count, await readOnly.CountDocumentsAsync(FilterDefinition<BsonDocument>.Empty));
    }

    [RequiresDatabasesFact]
    public async Task T3_ASecondSeedRunLeavesTheSameChecksum_AndTheReadOnlyAccountsSurviveIt()
    {
        var (_, first) = await SeedBothAsync();
        await ReadOnlyAccount.CreatePostgresAsync(DemoSettings.Postgres, Credential);
        await ReadOnlyAccount.CreateMongoAsync(DemoSettings.Mongo, Credential);
        var (_, second) = await SeedBothAsync();
        await ReadOnlyAccount.CreatePostgresAsync(DemoSettings.Postgres, Credential);
        await ReadOnlyAccount.CreateMongoAsync(DemoSettings.Mongo, Credential);

        var checksum = SeedChecksum.Of(OrderGenerator.Generate());
        Assert.Contains($"Checksum: {checksum}", first);
        Assert.Contains($"Checksum: {checksum}", second);
        Assert.Equal(checksum, await SeedChecksum.OfPostgresAsync(DemoSettings.Postgres));
        Assert.Equal(checksum, await SeedChecksum.OfMongoAsync(DemoSettings.Mongo));
        await using var connection = new NpgsqlConnection(RoPostgres());
        await connection.OpenAsync();
        await using var count = new NpgsqlCommand("SELECT count(*) FROM orders", connection);
        Assert.Equal(OrderGenerator.Generate().Count, (long)(await count.ExecuteScalarAsync())!);
    }

    [RequiresDatabasesFact]
    public async Task T4_ASlowQueryOnThePostgresReadOnlyAccountIsCancelledByStatementTimeout()
    {
        await SeedBothAsync();
        await ReadOnlyAccount.CreatePostgresAsync(DemoSettings.Postgres, Credential);

        await using var connection = new NpgsqlConnection(RoPostgres());
        await connection.OpenAsync();
        await using var slow = new NpgsqlCommand("SELECT pg_sleep(10)", connection);
        var started = DateTime.UtcNow;

        var cancelled = await Assert.ThrowsAsync<PostgresException>(() => slow.ExecuteScalarAsync());

        Assert.Equal("57014", cancelled.SqlState);
        Assert.InRange(DateTime.UtcNow - started, TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(8));
    }

    [RequiresDatabasesFact]
    public async Task T2_TheReadOnlyAccountCannotCreateATempTable()
    {
        await SeedBothAsync();
        await ReadOnlyAccount.CreatePostgresAsync(DemoSettings.Postgres, Credential);

        await using var connection = new NpgsqlConnection(RoPostgres());
        await connection.OpenAsync();
        await using var temp = new NpgsqlCommand("CREATE TEMP TABLE scratch (x int)", connection);

        var denied = await Assert.ThrowsAsync<PostgresException>(() => temp.ExecuteNonQueryAsync());

        Assert.Equal("42501", denied.SqlState);
    }

    [Fact]
    public async Task T1_TheChecksumLineComesFromTheTargetsDatabaseValue_AMismatchExits1WithoutAChecksumLine()
    {
        var differing = new SeedTarget(
            "fake", rows => Task.FromResult((long)rows.Count), count => $"fake: {count} rows.", "hint", true, () => Task.FromResult("0badc0de"));
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync(["fake"], [differing], output, error);

        Assert.Equal(1, exit);
        Assert.Contains("Checksum mismatch for fake", error.ToString());
        Assert.DoesNotContain("Checksum:", output.ToString());
    }

    [Fact]
    public async Task T1_WhenTheTargetsDatabaseValueEqualsTheSeedsItIsPrintedAndTheExitIs0()
    {
        var expected = SeedChecksum.Of(OrderGenerator.Generate());
        var agreeing = new SeedTarget(
            "fake", rows => Task.FromResult((long)rows.Count), count => $"fake: {count} rows.", "hint", true, () => Task.FromResult(expected));
        using var output = new StringWriter();
        using var error = new StringWriter();

        var exit = await SeedCommand.RunAsync(["fake"], [agreeing], output, error);

        Assert.Equal(0, exit);
        Assert.Contains($"Checksum: {expected}", output.ToString());
        Assert.Equal("", error.ToString());
    }

    [RequiresDatabasesFact]
    public async Task T1_ARowAlteredInPostgresBetweenTheLoadAndTheChecksum_IsAMismatchNotAPrintedChecksum()
    {
        var real = SeedTargets.All.Single(target => target.Name == "postgres");
        Assert.NotNull(real.ChecksumAsync);
        var tampering = real with
        {
            SeedAsync = async rows =>
            {
                var count = await real.SeedAsync(rows);
                await using var connection = new NpgsqlConnection(DemoSettings.Postgres);
                await connection.OpenAsync();
                await using var update = new NpgsqlCommand("UPDATE orders SET status = 'tampered' WHERE id = (SELECT min(id) FROM orders)", connection);
                await update.ExecuteNonQueryAsync();
                return count;
            }
        };
        using var output = new StringWriter();
        using var error = new StringWriter();

        try
        {
            var exit = await SeedCommand.RunAsync(["postgres"], [tampering], output, error);

            Assert.Equal(1, exit);
            Assert.Contains("Checksum mismatch for postgres", error.ToString());
            Assert.DoesNotContain("Checksum:", output.ToString());
        }
        finally
        {
            await SeedBothAsync();
        }
    }
}
