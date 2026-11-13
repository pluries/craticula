using Craticula.Core.Schema;
using Craticula.EntityFrameworkCore;
using Demo.Api.Errors;
using Demo.Api.Grid;
using Demo.Api.Public;
using Demo.Api.Routes;
using Demo.Api.Seed;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Storage;
using MongoDB.Driver;
using Npgsql;

namespace Demo.Api;

/// <summary>Builds the web application. Kept out of Program.cs so the tests can start the same host on a free port.</summary>
public static class DemoApp
{
    public const string SchemaFile = "orders.schema.json";

    private static readonly string[] AllowedOrigins =
        ["http://localhost:5173", "http://127.0.0.1:5173"];

    /// <param name="configure">Runs after the always-on registrations and before the optional ones, so it can also set
    /// a provider's setting with <c>builder.Configuration["DEMO_X"] = ...</c> (environment variables are part of the
    /// configuration) without touching the real environment.</param>
    /// <param name="extraOptionalProviders">Added to <see cref="OptionalProviders.All"/>; tests use it to add a fake engine.</param>
    public static WebApplication Build(
        string[] args,
        Action<WebApplicationBuilder>? configure = null,
        IReadOnlyList<OptionalProvider>? extraOptionalProviders = null)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions
        {
            Args = args,
            ContentRootPath = AppContext.BaseDirectory
        });

        // Loaded once; the schema is declared in a file and never taken from a request.
        var schema = GridSchema.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, SchemaFile)));
        var preparer = new GridRequestPreparer(schema, DemoLimits.Default);

        // Connections are lazy: the API starts with the databases down and answers 503 until they are up.
        var postgres = new NpgsqlConnectionStringBuilder(DemoSettings.Postgres) { Timeout = 5 };
        var mongoSettings = MongoClientSettings.FromConnectionString(DemoSettings.Mongo);
        mongoSettings.ServerSelectionTimeout = TimeSpan.FromSeconds(3);
        mongoSettings.ConnectTimeout = TimeSpan.FromSeconds(3);

        builder.Services.AddSingleton(preparer);
        builder.Services.AddSingleton(NpgsqlDataSource.Create(postgres.ConnectionString));
        builder.Services.AddSingleton<IMongoDatabase>(
            new MongoClient(mongoSettings).GetDatabase(DemoSettings.MongoDatabase));
        builder.Services.AddSingleton(schema);
        // One context per call from a factory: the services are singletons. The same NpgsqlDataSource as the Dapper
        // provider. The Npgsql provider's default execution strategy wraps a connection failure in an InvalidOperationException
        // even without EnableRetryOnFailure, which would answer 500; NonRetryingExecutionStrategy lets the NpgsqlException
        // through, so a down database answers 503 like the other providers.
        builder.Services.AddDbContextFactory<OrdersDbContext>((services, options) => options
            .UseNpgsql(services.GetRequiredService<NpgsqlDataSource>(),
                npgsql => npgsql.ExecutionStrategy(dependencies => new NonRetryingExecutionStrategy(dependencies)))
            .ReplaceService<IModelCacheKeyFactory, GridSchemaModelCacheKeyFactory>());
        builder.Services.AddSingleton<IGridService, PostgresGridService>();
        builder.Services.AddSingleton<IGridService, EfGridService>();
        // In public mode the database cuts a slow MongoDB query itself (the library's maxTimeMS); locally there is no limit.
        builder.Services.AddSingleton<IGridService>(services => new MongoGridService(
            services.GetRequiredService<IMongoDatabase>(),
            services.GetRequiredService<GridRequestPreparer>(),
            services.GetService<PublicSettings>() is null ? null : PublicSettings.QueryTimeoutMs));
        // SQLite is a file, so it is always on. The path is read when the service is first built, after `configure` ran:
        // DEMO_SQLITE from the configuration (the environment is part of it), else data/demo.sqlite under the demo folder.
        builder.Services.AddSingleton<IGridService>(services => new SqliteGridService(
            SqlitePath(services),
            services.GetRequiredService<GridRequestPreparer>()));
        // EF Core on the same SQLite file (route ef-sqlite): always on like sqlite. The path is read when the factory first builds a context.
        builder.Services.AddDbContextFactory<SqliteOrdersDbContext>((services, options) => options
            .UseSqlite(SqliteGridService.ConnectionStringFor(SqlitePath(services)))
            .ReplaceService<IModelCacheKeyFactory, GridSchemaModelCacheKeyFactory>());
        builder.Services.AddSingleton<IGridService>(services => new EfGridService<SqliteOrdersDbContext>(
            "ef-sqlite",
            "ef-sqlite",
            EfCoreProviderSemantics.Sqlite,
            services.GetRequiredService<IDbContextFactory<SqliteOrdersDbContext>>(),
            new SqliteGridService(SqlitePath(services), services.GetRequiredService<GridRequestPreparer>()).FetchSetValuesAsync,
            services.GetRequiredService<GridRequestPreparer>()));
        builder.Services.AddSingleton<ProviderRegistry>();
        // The EF routes build their model before the first visitor (task #3843); the host is ready only after this ran.
        builder.Services.AddHostedService<EfWarmUp>();

        builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
            policy.WithOrigins(AllowedOrigins).WithMethods("GET", "POST").WithHeaders("Content-Type")));

        builder.WebHost.ConfigureKestrel(kestrel => kestrel.Limits.MaxRequestBodySize = 1_048_576);

        configure?.Invoke(builder);

        // An optional engine is registered only when its setting is present; health and the 404 text list what is registered.
        OptionalProviders.RegisterConfigured(
            builder.Services, [.. OptionalProviders.All, .. extraOptionalProviders ?? []], name => builder.Configuration[name]);

        if (builder.Configuration[PublicSettings.EnabledKey] == "1")
        {
            PublicMode.Register(builder);
        }

        var app = builder.Build();

        if (app.Configuration[PublicSettings.EnabledKey] == "1")
        {
            PublicMode.Use(app);
        }

        app.UseMiddleware<ApiErrorMiddleware>();
        app.UseCors();

        HealthRoutes.Map(app);
        GridRoutes.Map(app);

        return app;
    }

    /// <summary>DEMO_SQLITE from the configuration (the environment is part of it), else data/demo.sqlite under the demo folder.</summary>
    private static string SqlitePath(IServiceProvider services) =>
        DemoSettings.ResolveSqlitePath(services.GetRequiredService<IConfiguration>()[DemoSettings.SqliteEnvVar]);
}
