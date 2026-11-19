using System.Globalization;
using System.Text.Json;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Integration.Tests.Docker;
using Craticula.Integration.Tests.Oracle;
using Craticula.Mongo;
using MongoDB.Bson;
using MongoDB.Driver;
using Testcontainers.MongoDb;

namespace Craticula.Integration.Tests.Containers.Document;

/// <summary>One MongoDB 7.0 container for the whole run (the repo's documented version, pinned).</summary>
public sealed class MongoEngineFixture : IAsyncLifetime
{
    public const string Image = "mongo:7.0.14";

    private MongoDbContainer? container;

    internal IMongoClient? Client { get; private set; }

    public string? StartupFailure { get; private set; }

    public async Task InitializeAsync()
    {
        if (!DockerAvailability.IsAvailable)
        {
            return;
        }

        try
        {
            container = new MongoDbBuilder(Image).Build();
            using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(10));
            await container.StartAsync(timeout.Token).ConfigureAwait(false);
            Client = new MongoClient(container.GetConnectionString());
        }
        catch (Exception exception)
        {
            StartupFailure = exception.ToString();
        }
    }

    public async Task DisposeAsync()
    {
        if (container is not null)
        {
            await container.DisposeAsync().ConfigureAwait(false);
        }
    }

    internal IMongoClient Require() =>
        Client ?? throw new InvalidOperationException($"The MongoDB container ({Image}) did not start: {StartupFailure}");
}

/// <summary>
/// The MongoDB side of T-1b: seed a fresh database from <c>dataset.json</c>, compile the fixture's request with
/// <see cref="MongoPipelineBuilder"/>, run the pipeline (and its query-level collation) and map the documents onto the
/// logical column list.
/// </summary>
internal static class MongoEngine
{
    public static async Task<EngineRows> RunAsync(IMongoClient client, ExecutionFixture fixture)
    {
        var databaseName = "xeq_" + Guid.NewGuid().ToString("N");
        try
        {
            var collection = await SeedAsync(client, databaseName, fixture).ConfigureAwait(false);
            return await QueryAsync(collection, fixture).ConfigureAwait(false);
        }
        finally
        {
            await client.DropDatabaseAsync(databaseName).ConfigureAwait(false);
        }
    }

    /// <summary>Seeds a collection from the fixture's schema and seed rows; the caller owns (and drops) the database.</summary>
    public static async Task<IMongoCollection<BsonDocument>> SeedAsync(IMongoClient client, string databaseName, ExecutionFixture fixture)
    {
        var schema = fixture.Schema;
        var collection = client.GetDatabase(databaseName).GetCollection<BsonDocument>(schema.Source);
        var documents = fixture.Seed.Select(row => ToDocument(schema, row)).ToList();
        if (documents.Count > 0)
        {
            await collection.InsertManyAsync(documents).ConfigureAwait(false);
        }

        return collection;
    }

    /// <summary>Compiles the fixture's request, runs it against an already seeded collection and maps the documents onto the logical columns.</summary>
    public static Task<EngineRows> QueryAsync(IMongoCollection<BsonDocument> collection, ExecutionFixture fixture) =>
        QueryAsync(collection, fixture, PreparedRequest.For(fixture, fixture.Schema));

    /// <summary>The page path over an already prepared request (the count check prepares its own, unpaged one).</summary>
    public static async Task<EngineRows> QueryAsync(IMongoCollection<BsonDocument> collection, ExecutionFixture fixture, PreparedRequest request)
    {
        ArgumentNullException.ThrowIfNull(fixture);
        var (query, columns) = Compile(request);
        var results = await AggregateAsync(collection, query).ConfigureAwait(false);

        // XEQ-3: map onto the LOGICAL columns, dropping _id (kept only where it IS the group key / BM-3 value).
        var plan = request.Plan;
        var keys = request.IsSetValues
            ? ["_id"]
            : plan is { GroupColumn: not null } ? ["_id", .. plan.Aggregations.Select(a => a.OutputName)] : columns;
        var rows = results
            .Select(document => (IReadOnlyList<object?>)keys
                .Select(key => ToClr(document.TryGetValue(key, out var value) ? value : BsonNull.Value))
                .ToList())
            .ToList();
        return new EngineRows(columns, rows);
    }

    /// <summary>Runs one compiled pipeline (with its query-level collation) and maps a driver failure to <see cref="EngineRefusedException"/>.</summary>
    internal static async Task<List<BsonDocument>> AggregateAsync(IMongoCollection<BsonDocument> collection, MongoQuery query)
    {
        var stages = query.Pipeline.Select(stage => BsonDocument.Parse(stage.ToJsonString())).ToList();
        var options = query.Collation is null
            ? null
            : new AggregateOptions { Collation = Collation.FromBsonDocument(BsonDocument.Parse(query.Collation.ToJsonString())) };

        try
        {
            return await collection.Aggregate<BsonDocument>(stages, options).ToListAsync().ConfigureAwait(false);
        }
        catch (MongoException exception)
        {
            throw new EngineRefusedException($"MongoDB rejected the pipeline: {exception.Message}", exception);
        }
    }

    private static (MongoQuery Query, IReadOnlyList<string> Columns) Compile(PreparedRequest request)
    {
        try
        {
            if (request.IsSetValues)
            {
                return (
                    MongoPipelineBuilder.BuildSetValues(new MongoSetValuesRequest
                    {
                        Schema = request.Schema,
                        ColId = request.SetValues!.ColId,
                        Filter = request.Filter,
                        RowLimit = request.RowLimit
                    }),
                    request.LogicalColumns());
            }

            var parsed = request.Parsed!;

            // The adapter's own rule (MongoGridQuery.WithExplicitProjection): an ordinary or export fetch projects
            // the logical columns explicitly so the documents come back keyed by colId, not by physical path.
            var projection = parsed.Group is null ? parsed.Export?.ProjectionColumns ?? request.Schema.FieldOrder : null;
            return (
                MongoPipelineBuilder.Build(new MongoQueryRequest
                {
                    Schema = request.Schema,
                    Filter = request.Filter,
                    Sort = parsed.Sort,
                    Page = parsed.Page,
                    Group = parsed.Group,
                    Aggregations = parsed.Aggregations,
                    Projection = projection
                }),
                request.LogicalColumns());
        }
        catch (MongoCompilationException exception)
        {
            throw new EngineRefusedException($"The Mongo compiler refused the request: {exception.Message}", exception);
        }
    }

    /// <summary>One seed row as a document, each cell encoded the way the compiler's artifacts expect (XEQ-2).</summary>
    private static BsonDocument ToDocument(GridSchema schema, SeedRow row)
    {
        var document = new BsonDocument();
        foreach (var (colId, field) in schema.Fields)
        {
            var path = field.Physical?.Mongo?.Path ?? colId;
            var value = Encode(field.Type, row.Cells[colId]);
            var segments = path.Split('.');
            var target = document;
            for (var index = 0; index < segments.Length - 1; index++)
            {
                if (!target.TryGetValue(segments[index], out var child))
                {
                    child = new BsonDocument();
                    target[segments[index]] = child;
                }

                target = child.AsBsonDocument;
            }

            target[segments[^1]] = value;
        }

        return document;
    }

    /// <summary>
    /// XEQ-2 to BSON: int64 a BSON long, double a BSON double, decimal a Decimal128 (the <c>$numberDecimal</c> the
    /// artifacts compare against), a <c>date</c> the plain ISO string (SEM-4, never a BSON Date), a <c>datetime</c> a
    /// BSON Date, null an explicit BSON null.
    /// </summary>
    private static BsonValue Encode(FieldType type, JsonElement cell)
    {
        if (cell.ValueKind == JsonValueKind.Null)
        {
            return BsonNull.Value;
        }

        return type switch
        {
            FieldType.Int64 => new BsonInt64(cell.GetInt64()),
            FieldType.Double => new BsonDouble(cell.GetDouble()),
            FieldType.Decimal => new BsonDecimal128(Decimal128.Parse(cell.GetString()!)),
            FieldType.Boolean => new BsonBoolean(cell.GetBoolean()),
            FieldType.String => new BsonString(cell.GetString()!),
            FieldType.Date => new BsonString(cell.GetString()!),
            FieldType.Datetime => new BsonDateTime(DateTimeOffset.Parse(
                cell.GetString()!, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal).UtcDateTime),
            _ => throw new InvalidOperationException($"Unmapped FieldType '{type}'.")
        };
    }

    private static object? ToClr(BsonValue value) => value.BsonType switch
    {
        BsonType.Null or BsonType.Undefined => null,
        BsonType.String => value.AsString,
        BsonType.Int32 => (long)value.AsInt32,
        BsonType.Int64 => value.AsInt64,
        BsonType.Double => value.AsDouble,
        BsonType.Decimal128 => Decimal128.ToDecimal(value.AsDecimal128),
        BsonType.Boolean => value.AsBoolean,
        BsonType.DateTime => DateTime.SpecifyKind(value.ToUniversalTime(), DateTimeKind.Utc),
        _ => throw new InvalidOperationException($"Unexpected BSON type {value.BsonType} in a result cell.")
    };
}
