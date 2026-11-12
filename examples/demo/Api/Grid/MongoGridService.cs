using Craticula.Core;
using Craticula.Core.Export;
using Craticula.Core.Grid;
using Craticula.Mongo;
using Craticula.MongoDB.Driver;
using MongoDB.Bson;
using MongoDB.Driver;

namespace Demo.Api.Grid;

/// <summary>MongoDB through <c>Craticula.MongoDB.Driver</c>. <paramref name="maxQueryTimeMs"/> is the host's query time limit: the library puts
/// it into the artifact as <c>maxTimeMS</c> and MongoDB cancels a slower query itself (null: no limit, as in the local demo).</summary>
public sealed class MongoGridService(IMongoDatabase database, GridRequestPreparer preparer, int? maxQueryTimeMs = null) : IGridService
{
    public string Name => "mongo";

    public async Task<GridPageResult> FetchRowsAsync(PreparedRows request, CancellationToken cancellationToken)
    {
        var page = await MongoGridQuery.FetchPageAsync(
            database, ToMongoRequest(request), includeRowCount: true, cancellationToken);
        return page.ToGridPageResult();
    }

    /// <summary>
    /// The Mongo adapter has no entry point for BM-3's distinct values, so this compiles with
    /// <c>MongoPipelineBuilder.BuildSetValues</c> and runs ONLY that pipeline (and collation), translated to BSON the
    /// way the adapter does it: each stage's JSON text parsed as Extended JSON. Each result document is <c>{ _id: value }</c>.
    /// </summary>
    public async Task<IReadOnlyList<object?>> FetchSetValuesAsync(PreparedSetValues request, CancellationToken cancellationToken)
    {
        var query = MongoPipelineBuilder.BuildSetValues(
            new MongoSetValuesRequest
            {
                Schema = preparer.Schema,
                ColId = request.ColId,
                Filter = request.Filter,
                RowLimit = request.RowLimit,
                MaxQueryTimeMs = maxQueryTimeMs
            });

        var stages = query.Pipeline.Select(stage => BsonDocument.Parse(stage.ToJsonString())).ToArray();
        var options = OptionsFor(query);

        var values = new List<object?>();
        var collection = database.GetCollection<BsonDocument>(query.Collection);
        try
        {
            using var cursor = await collection.AggregateAsync<BsonDocument>(stages, options, cancellationToken);
            while (await cursor.MoveNextAsync(cancellationToken))
            {
                values.AddRange(cursor.Current.Select(document => ToClr(document["_id"])));
            }
        }
        catch (MongoExecutionTimeoutException ex)
        {
            throw new QueryTimeoutException(ex);
        }

        return values;
    }

    public IAsyncEnumerable<ExportRow> StreamExportAsync(PreparedRows request, CancellationToken cancellationToken) =>
        MongoExportStream.StreamAsync(database, ToMongoRequest(request), cancellationToken);

    public CompiledQueryView Compile(PreparedRows request)
    {
        var mongoRequest = ToMongoRequest(request);
        if (mongoRequest.Group is null && mongoRequest.Projection is null)
        {
            mongoRequest = mongoRequest with { Projection = preparer.Schema.FieldOrder };
        }

        var query = MongoPipelineBuilder.Build(mongoRequest);
        var text = query.ToArtifact().ToJsonString(new System.Text.Json.JsonSerializerOptions { WriteIndented = true });

        // MongoDB has no bind parameters: values travel inside the pipeline as data, never as concatenated text.
        return new CompiledQueryView("mongo", "mongodb", text, []);
    }

    /// <summary>The command options of a compiled query: its collation and its <c>maxTimeMS</c>, translated the way the adapter does it.</summary>
    public static AggregateOptions OptionsFor(MongoQuery query)
    {
        var options = new AggregateOptions();
        if (query.Collation is not null)
        {
            options.Collation = Collation.FromBsonDocument(BsonDocument.Parse(query.Collation.ToJsonString()));
        }

        if (query.MaxTimeMs is { } maxTimeMs)
        {
            options.MaxTime = TimeSpan.FromMilliseconds(maxTimeMs);
        }

        return options;
    }

    private MongoQueryRequest ToMongoRequest(PreparedRows request) => new()
    {
        Schema = preparer.Schema,
        Filter = request.Filter,
        Sort = request.Parsed.Sort,
        Page = request.Parsed.Page,
        Group = request.Parsed.Group,
        Aggregations = request.Parsed.Aggregations,
        Projection = request.Parsed.Export?.ProjectionColumns,
        MaxQueryTimeMs = maxQueryTimeMs
    };

    private static object? ToClr(BsonValue value) => value switch
    {
        { IsBsonNull: true } => null,
        BsonDecimal128 d => Decimal128.ToDecimal(d.Value),
        BsonDateTime t => t.ToUniversalTime(),
        _ => BsonTypeMapper.MapToDotNetValue(value)
    };
}
