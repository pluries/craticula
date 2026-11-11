namespace Demo.Api.Seed;

/// <summary>Connection strings for the demo databases. PostgreSQL and MongoDB have defaults that match docker-compose.yml;
/// an optional engine has none: it is on only when its environment variable is set (see <see cref="OptionalSetting"/>).</summary>
public static class DemoSettings
{
    public static string Postgres =>
        Environment.GetEnvironmentVariable("DEMO_PG")
        ?? "Host=127.0.0.1;Port=55433;Username=demo;Password=demo;Database=demo";

    public static string Mongo =>
        Environment.GetEnvironmentVariable("DEMO_MONGO")
        ?? "mongodb://127.0.0.1:57017";

    public const string MongoDatabase = "demo";

    /// <summary>The environment variable holding the password of the read-only account (<see cref="ReadOnlyAccount"/>). When set, <c>seed postgres</c> and
    /// <c>seed mongo</c> create that account after loading the rows; the API container gets the account's connection string and never the admin one.</summary>
    public const string ReadOnlyPasswordEnvVar = "DEMO_READONLY_PASSWORD";

    /// <summary>The environment variable holding the SQL Server connection string; the engine is on only when it is set.
    /// There is no default in code: README.md gives the one that matches docker-compose.yml.</summary>
    public const string SqlServerEnvVar = "DEMO_SQLSERVER";

    /// <summary>The environment variable holding an administrator's SQL Server connection string, used by <c>seed sqlserver</c> only
    /// (it creates the database and the table, then the read-only login that <see cref="SqlServerEnvVar"/> names). Optional: when unset,
    /// the seed uses <see cref="SqlServerEnvVar"/> itself, as before. The API never reads it.</summary>
    public const string SqlServerAdminEnvVar = "DEMO_SQLSERVER_ADMIN";

    /// <summary>The environment variable holding the MySQL connection string; the engine is on only when it is set.
    /// There is no default in code: README.md gives the one that matches docker-compose.yml.</summary>
    public const string MySqlEnvVar = "DEMO_MYSQL";

    /// <summary>The environment variable holding the OpenSearch URL (for example <c>http://127.0.0.1:59200</c>); the engine is on only
    /// when it is set. The compose service has its security plugin off, so there is no credential in it.</summary>
    public const string OpenSearchEnvVar = "DEMO_OPENSEARCH";

    /// <summary>The environment variable holding the Elasticsearch URL (for example <c>http://127.0.0.1:59201</c>); the engine is on only when it
    /// is set. The compose service has security off, so there is no credential in it. It is a second engine for the same OpenSearch client and the
    /// same seeder, so it answers to a name of its own (<c>elasticsearch</c>).</summary>
    public const string ElasticsearchEnvVar = "DEMO_ELASTICSEARCH";

    /// <summary>The environment variable that moves the SQLite file.</summary>
    public const string SqliteEnvVar = "DEMO_SQLITE";

    /// <summary>The SQLite database file: <c>DEMO_SQLITE</c> when set, else <c>data/demo.sqlite</c> under the demo folder.</summary>
    public static string SqlitePath => ResolveSqlitePath(Environment.GetEnvironmentVariable(SqliteEnvVar));

    /// <summary>A configured path (blank counts as unset), or the default file under the demo folder. The API passes its own
    /// configuration value here so a test can point it at a temporary file without touching the environment.</summary>
    public static string ResolveSqlitePath(string? configured) =>
        NullIfBlank(configured) ?? Path.Combine(DemoFolder(), "data", "demo.sqlite");

    // The folder holding docker-compose.yml, found by walking up from the app folder (bin/Debug/... under Api); the
    // current directory when the app runs from somewhere else (a published copy).
    private static string DemoFolder()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            if (File.Exists(Path.Combine(dir.FullName, "docker-compose.yml")))
            {
                return dir.FullName;
            }
        }

        return Directory.GetCurrentDirectory();
    }

    /// <summary>The value of an optional engine's variable, or null when it is unset or blank (the engine is not configured).</summary>
    public static string? OptionalSetting(string envVar) =>
        NullIfBlank(Environment.GetEnvironmentVariable(envVar));

    /// <summary>True when an optional engine's variable is set.</summary>
    public static bool IsConfigured(string envVar) => OptionalSetting(envVar) is not null;

    private static string? NullIfBlank(string? value) => string.IsNullOrWhiteSpace(value) ? null : value;
}
