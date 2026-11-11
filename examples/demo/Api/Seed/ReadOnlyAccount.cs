using MongoDB.Bson;
using MongoDB.Driver;
using Npgsql;

namespace Demo.Api.Seed;

/// <summary>
/// The read-only account the public API connects with. The seed creates it with the admin connection and, when
/// <c>DEMO_READONLY_PASSWORD</c> is set, calls both Create methods after loading the rows; the API container never gets the admin credentials.
/// Both Create methods are idempotent.
/// </summary>
public static class ReadOnlyAccount
{
    public const string UserName = "demo_ro";

    public static readonly TimeSpan PostgresStatementTimeout = TimeSpan.FromSeconds(2);

    /// <summary>Role <see cref="UserName"/> with LOGIN, <c>GRANT SELECT</c> on table orders only, and <c>statement_timeout</c> of <see cref="PostgresStatementTimeout"/> set on the role.</summary>
    public static async Task CreatePostgresAsync(string adminConnectionString, string password)
    {
        await using var connection = new NpgsqlConnection(adminConnectionString);
        await connection.OpenAsync();

        // CREATE/ALTER ROLE take no parameters: the server quotes the identifier and the password itself (format %I, %L).
        await using (var exists = new NpgsqlCommand("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = @name)", connection))
        {
            exists.Parameters.AddWithValue("name", UserName);
            var verb = (bool)(await exists.ExecuteScalarAsync())! ? "ALTER" : "CREATE";
            await using var statement = new NpgsqlCommand($"SELECT format('{verb} ROLE %I LOGIN PASSWORD %L', @name, @password)", connection);
            statement.Parameters.AddWithValue("name", UserName);
            statement.Parameters.AddWithValue("password", password);
            var sql = (string)(await statement.ExecuteScalarAsync())!;
            await using var run = new NpgsqlCommand(sql, connection);
            await run.ExecuteNonQueryAsync();
        }

        var timeoutMs = (int)PostgresStatementTimeout.TotalMilliseconds;
        await using var grants = new NpgsqlCommand($"""
            ALTER ROLE {UserName} SET statement_timeout = {timeoutMs};
            GRANT USAGE ON SCHEMA public TO {UserName};
            GRANT SELECT ON TABLE orders TO {UserName};
            """, connection);
        await grants.ExecuteNonQueryAsync();

        // PUBLIC may create temporary tables by default; the account's whole surface is SELECT on orders.
        await using var revoke = new NpgsqlCommand("SELECT format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database())", connection);
        await using var revokeRun = new NpgsqlCommand((string)(await revoke.ExecuteScalarAsync())!, connection);
        await revokeRun.ExecuteNonQueryAsync();
    }

    /// <summary>User <see cref="UserName"/> created in database <see cref="DemoSettings.MongoDatabase"/> with the single role <c>read</c> on that database.</summary>
    public static async Task CreateMongoAsync(string adminConnectionString, string password)
    {
        var database = new MongoClient(adminConnectionString).GetDatabase(DemoSettings.MongoDatabase);
        var info = await database.RunCommandAsync<BsonDocument>(new BsonDocument("usersInfo", UserName));
        var roles = new BsonArray { new BsonDocument { ["role"] = "read", ["db"] = DemoSettings.MongoDatabase } };
        var command = new BsonDocument
        {
            [info["users"].AsBsonArray.Count > 0 ? "updateUser" : "createUser"] = UserName,
            ["pwd"] = password,
            ["roles"] = roles
        };
        await database.RunCommandAsync<BsonDocument>(command);
    }

    /// <summary>The admin connection string with the user and password replaced: same host, port and database.</summary>
    public static string PostgresConnectionString(string adminConnectionString, string pass) =>
        new NpgsqlConnectionStringBuilder(adminConnectionString) { Username = UserName, Password = pass }.ConnectionString;

    /// <summary>The admin connection string with the credentials added and <c>authSource</c> set to <see cref="DemoSettings.MongoDatabase"/>.</summary>
    public static string MongoConnectionString(string adminConnectionString, string pass) =>
        new MongoUrlBuilder(adminConnectionString)
        {
            Username = UserName,
            Password = pass,
            AuthenticationSource = DemoSettings.MongoDatabase
        }.ToString();
}
