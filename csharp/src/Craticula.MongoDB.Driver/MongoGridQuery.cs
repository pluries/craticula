using System.Text.Json.Nodes;
using Craticula.Core;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Mongo;
using MongoDB.Bson;
using MongoDB.Driver;

namespace Craticula.MongoDB.Driver;

/// <summary>
/// The <b>grid</b> entry point: one page of documents for an AG Grid SSRM block, optionally with the
/// filtered total — <c>Craticula.Mongo.MongoPipelineBuilder.Build</c>'s pipeline executed via
/// <c>IMongoCollection{BsonDocument}.AggregateAsync</c> against an already-open
/// <see cref="IMongoDatabase"/> the host owns. <b>Connection ownership stays with the host</b>: this
/// package never constructs a <see cref="MongoClient"/> or opens a connection itself — the driver's own
/// idiomatic shape is a database handle rather than a raw connection, since a <see cref="MongoClient"/>
/// already manages its own connection pooling internally.
///
/// <para><b>Grouping/aggregation need almost no special handling here, mirroring
/// <c>Craticula.Dapper.DapperGridQuery</c>'s own argument.</b> <c>Craticula.Mongo.MongoPipelineBuilder</c>
/// already fully resolves grouped/aggregated/drill-down requests internally (BM-2) — this method
/// executes whatever pipeline it produces and never re-derives a <c>$group</c>/<c>$project</c> shape of
/// its own. The ONE thing this package still needs, which SQL's own aliasing makes unnecessary for
/// Dapper, is resolving <see cref="Craticula.Core.Ir.GroupingPlan"/> to know what a grouped level's
/// literal <c>_id</c> output key actually MEANS — see <see cref="MongoGridPage"/>'s own remarks for why
/// that is reading back a decision the compiler already made, not making a new one.</para>
/// </summary>
public static class MongoGridQuery
{
    /// <summary>
    /// Compiles and executes one grid page: filter, order, row window, projection — whatever shape
    /// <c>MongoPipelineBuilder.Build</c> resolves <paramref name="request"/> to.
    /// </summary>
    /// <param name="database">An already-open database handle. Never opened or closed here.</param>
    /// <param name="request">The validated IR — the same shape <c>MongoPipelineBuilder.Build</c> itself
    /// accepts, since this method's whole job is executing what that compiler produces.</param>
    /// <param name="includeRowCount">Whether to also run the <c>$count</c> aggregation
    /// (<see cref="MongoGridPage.RowCount"/>). Defaults to <see langword="false"/>: it is a second round
    /// trip, and a grid needs the total once per filter change rather than once per block.</param>
    /// <param name="cancellationToken">EXP-7's cancellation hook, observed by both aggregations.</param>
    public static async Task<MongoGridPage> FetchPageAsync(
        IMongoDatabase database,
        MongoQueryRequest request,
        bool includeRowCount = false,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentNullException.ThrowIfNull(request);

        // PG-5: every row is read by streaming; a paged call never loads the whole result.
        if (request.Page is NonePage)
        {
            throw new MongoDriverCompilationException(
                "FetchPageAsync returns one window of rows and refuses EXP-2's unpaginated page, which would load " +
                "every row into memory (PG-5). Read every row with MongoExportStream.StreamAsync.");
        }

        var effective = WithExplicitProjection(request);
        var query = MongoPipelineBuilder.Build(effective);
        var plan = GroupingPlan.Resolve(effective.Group, effective.Aggregations);

        var columns = ResolveColumns(effective, plan);
        var types = ResolveColumnTypes(columns, effective.Schema, plan);

        var collection = database.GetCollection<BsonDocument>(query.Collection);
        var stages = MongoPipelineTranslator.Translate(query.Pipeline);
        var options = MongoPipelineTranslator.Options(query);

        var rows = new List<IReadOnlyList<object?>>();

        try
        {
            using var cursor = await collection.AggregateAsync<BsonDocument>(stages, options, cancellationToken)
                .ConfigureAwait(false);
            while (await cursor.MoveNextAsync(cancellationToken).ConfigureAwait(false))
            {
                foreach (var document in cursor.Current)
                {
                    var cells = new object?[columns.Count];
                    for (var index = 0; index < columns.Count; index++)
                    {
                        cells[index] = MongoValueReader.Read(document, DocumentKey(columns, plan, index), types[index]);
                    }

                    rows.Add(cells);
                }
            }
        }
        catch (MongoExecutionTimeoutException ex)
        {
            throw new QueryTimeoutException(ex);
        }

        var rowCount = includeRowCount
            ? await CountAsync(database, effective, cancellationToken).ConfigureAwait(false)
            : (long?)null;

        return new MongoGridPage { Columns = columns, Rows = rows, RowCount = rowCount };
    }

    /// <summary>
    /// The filtered document count on its own — the same question <see cref="FetchPageAsync"/> answers
    /// when asked, exposed so that asking for it separately cannot mean asking a different question. For
    /// a grouped level this is the BUCKET count, automatically: see <see cref="MongoGridPage"/>'s own
    /// remarks.
    ///
    /// <para><b>How, given <c>Craticula.Mongo</c> exposes no count-mode build.</b> The standard MongoDB
    /// idiom — a <c>$count</c> stage appended to a copy of the pipeline with its row-window, ordering and
    /// projection stages removed, run as a SEPARATE aggregation — since <c>MongoPipelineBuilder</c> has
    /// no public "the pipeline up to but not including the page window" entry point to ask for instead
    /// (checked directly in that file: only <c>Build</c> and <c>BuildSetValues</c> are public).
    /// <c>$skip</c>/<c>$limit</c> are dropped because they bound the WINDOW, not the filtered total,
    /// <c>$project</c> is dropped because <c>$count</c> needs no particular document shape to count
    /// documents, and <c>$sort</c>/<c>$addFields</c>/<c>$unset</c> are dropped because a document COUNT
    /// is order-independent by definition and the two bucket-labeling stages exist only to feed that
    /// sort — none of these five can appear before a grouped level's own <c>$group</c> (the compiler's
    /// own fixed stage order), so dropping them never removes a stage the count still needs.</para>
    ///
    /// <para><b>Why dropping <c>$sort</c> specifically matters, not just "one fewer stage."</b> SEM-6
    /// guarantees at least one sort key on EVERY compiled pipeline, so every count built from a naive
    /// "drop the window, keep everything else" filter would still carry a full <c>$sort</c> of the
    /// entire filtered set. The page pipeline's own trailing <c>$skip</c>/<c>$limit</c> let the server
    /// run a bounded top-k sort; stripping them while leaving <c>$sort</c> removes exactly that bound, so
    /// a scalar count — which owes the client no ordering at all — would pay for an unbounded blocking
    /// sort on every filter change, and could fail outright with
    /// <c>QueryExceededMemoryLimitNoDiskUseAllowed</c> on a server version/dataset size where the
    /// equivalent page fetch succeeds fine (this package sets no <c>AllowDiskUse</c>). Found by this
    /// story's own review, not by a fixture: none of the 174 compiled pipelines happens to exercise a
    /// dataset large enough to trip the memory limit, but 174 of 174 count pipelines carried the
    /// unbounded sort before this fix.</para>
    ///
    /// <para><b>A load-bearing MongoDB fact this method exists to hide:</b> <c>$count</c> emits NO output
    /// document at all when zero documents reach it — unlike SQL's <c>COUNT(*)</c>, which always returns
    /// exactly one row, <c>0</c> included. An absent result is therefore read as the answer <c>0</c>, not
    /// as a signal to retry or an error.</para>
    /// </summary>
    public static async Task<long> CountAsync(
        IMongoDatabase database, MongoQueryRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentNullException.ThrowIfNull(request);

        var query = MongoPipelineBuilder.Build(request);
        var countPipeline = BuildCountPipeline(query.Pipeline);

        var collection = database.GetCollection<BsonDocument>(query.Collection);
        var stages = MongoPipelineTranslator.Translate(countPipeline);
        var options = MongoPipelineTranslator.Options(query);

        BsonDocument? document = null;

        try
        {
            using var cursor = await collection.AggregateAsync<BsonDocument>(stages, options, cancellationToken)
                .ConfigureAwait(false);
            if (await cursor.MoveNextAsync(cancellationToken).ConfigureAwait(false))
            {
                document = cursor.Current.FirstOrDefault();
            }
        }
        catch (MongoExecutionTimeoutException ex)
        {
            throw new QueryTimeoutException(ex);
        }

        return document is null ? 0L : document["count"].ToInt64();
    }

    /// <summary>
    /// Forces an EXPLICIT projection when the request has neither a <see cref="GroupSpec"/> nor its own
    /// <see cref="MongoQueryRequest.Projection"/> — the ordinary, unprojected grid page.
    ///
    /// <para><b>Why: an ordinary request's compiled pipeline has no <c>$project</c> stage at all</b>
    /// (<c>MongoPipelineBuilder</c>'s own "never an ordinary row query, which returns whole documents
    /// exactly as its SQL counterpart renders <c>SELECT *</c>"). A whole document can carry a NESTED
    /// shape for any field whose <c>physical.mongo.path</c> differs from its colId
    /// (<c>"customer.name"</c>), or sit under the document's own <c>_id</c> key rather than its logical
    /// name — this package would then have no flat, colId-keyed shape to read cells back from at all.
    /// <c>Craticula.Dapper.DapperGridQuery.WithExplicitProjection</c>'s identical argument, restated for
    /// a driver that returns documents rather than rows. Every other branch (a grouped level, a
    /// drill-down leaf, an explicit export projection) already emits an explicit, re-keyed
    /// <c>$project</c>, so only this one case needs forcing.</para>
    /// </summary>
    private static MongoQueryRequest WithExplicitProjection(MongoQueryRequest request) =>
        request.Group is null && request.Projection is null
            ? request with { Projection = request.Schema.FieldOrder }
            : request;

    /// <summary>
    /// The compiled pipeline's own output field names, in the order they appear on each document —
    /// resolved from the request's own already-settled shape (never read off a returned document; see
    /// <see cref="MongoGridPage.Columns"/> for why). <paramref name="plan"/> is the SAME
    /// <see cref="GroupingPlan"/> <c>MongoPipelineBuilder.Build</c> itself resolved, so these names
    /// cannot disagree with the pipeline's own <c>$group</c>/<c>$project</c> stage.
    /// </summary>
    private static IReadOnlyList<string> ResolveColumns(MongoQueryRequest request, GroupingPlan? plan) =>
        plan switch
        {
            { GroupColumn: { } column } => [column, .. plan.Aggregations.Select(a => a.OutputName)],
            { GroupColumn: null } => request.Schema.FieldOrder, // the drill-down leaf's own $project (GRP-3)
            null => request.Projection ?? request.Schema.FieldOrder // ordinary/export; WithExplicitProjection already forced this
        };

    /// <summary>The document key backing <paramref name="columns"/>[<paramref name="index"/>] —
    /// <c>_id</c> for a grouped level's bucket column (index 0 only, and only when grouped; see
    /// <see cref="MongoGridPage"/>'s own remarks on the rename), the column's own name everywhere
    /// else.</summary>
    private static string DocumentKey(IReadOnlyList<string> columns, GroupingPlan? plan, int index) =>
        plan is { GroupColumn: not null } && index == 0 ? "_id" : columns[index];

    /// <summary>
    /// Which <see cref="FieldType"/> each of <paramref name="columns"/> materializes as: a real schema
    /// field's own declared type, or — for a column that is not one (an aggregate's output name) — the
    /// aggregation at the matching POSITION in <paramref name="plan"/>'s own aggregation list, resolved
    /// per <see cref="ResolveAggregationType"/>. Mirrors
    /// <c>Craticula.Dapper.DapperGridQuery.ResolveColumnTypes</c>: a grouped level's renamed bucket
    /// column (index 0) is a real field and is found here directly, so the position-based fallback below
    /// only ever needs to resolve an aggregate output.
    /// </summary>
    private static FieldType[] ResolveColumnTypes(IReadOnlyList<string> columns, GridSchema schema, GroupingPlan? plan)
    {
        var types = new FieldType[columns.Count];

        for (var index = 0; index < columns.Count; index++)
        {
            if (schema.Fields.TryGetValue(columns[index], out var field))
            {
                types[index] = field.Type;
                continue;
            }

            var aggregationIndex = index - 1;
            if (plan is null || aggregationIndex < 0 || aggregationIndex >= plan.Aggregations.Count)
            {
                throw new MongoDriverCompilationException(
                    $"Column '{columns[index]}' at position {index} is neither a declared schema field nor a " +
                    "resolvable aggregation output — the compiled pipeline's own shape disagrees with the " +
                    "request that produced it.");
            }

            types[index] = ResolveAggregationType(plan.Aggregations[aggregationIndex], schema);
        }

        return types;
    }

    /// <summary>
    /// AGG-1's rule for <see cref="AggregationFunc.Count"/> (always an integer; this package's own
    /// <c>$sum</c>-of-<c>$cond</c> rendering can hand back a driver <see cref="BsonInt32"/> for a small
    /// bucket, which <see cref="MongoValueReader"/>'s <c>Int64</c> arm widens) plus the one non-obvious
    /// member <c>Craticula.Dapper.DapperGridQuery</c>'s own review found: <see cref="AggregationFunc.Avg"/>
    /// does NOT keep the source field's declared type the way <c>sum</c>/<c>min</c>/<c>max</c> genuinely
    /// do — MongoDB's <c>$avg</c> over an integer or floating field always returns a fractional
    /// <see cref="BsonDouble"/>, so reading it back as <see cref="FieldType.Int64"/> would truncate a
    /// real average. Widened to <see cref="FieldType.Double"/> for every non-<see cref="FieldType.Decimal"/>
    /// source, matching Dapper's own rule (a decimal source's own precision is worth preserving; every
    /// other numeric source already loses no meaningful precision going through <see cref="double"/>).
    ///
    /// <para><b>Unlike the SQL story, there is no per-engine residual here to record.</b> Every MongoDB
    /// server returns the same fractional <c>$avg</c> regardless of the source field's storage type — no
    /// counterpart to SQL Server's own T-SQL numeric-promotion rule that truncates <c>AVG(bigint)</c> to
    /// <c>bigint</c> at the engine itself.</para>
    /// </summary>
    private static FieldType ResolveAggregationType(Aggregation aggregation, GridSchema schema)
    {
        if (aggregation.Func == AggregationFunc.Count)
        {
            return FieldType.Int64;
        }

        var sourceType = schema.Fields[aggregation.Field].Type;
        return aggregation.Func == AggregationFunc.Avg && sourceType != FieldType.Decimal
            ? FieldType.Double
            : sourceType;
    }

    /// <summary>
    /// <paramref name="pipeline"/> with its row-window, ordering and projection stages removed, plus a
    /// trailing <c>{"$count": "count"}</c> — see <see cref="CountAsync"/>'s own remarks for why these
    /// five and no others (a document count is order-independent, so <c>$sort</c> and the two
    /// bucket-labeling stages that exist only to feed it are dropped alongside the row window).
    /// </summary>
    private static List<JsonObject> BuildCountPipeline(IReadOnlyList<JsonObject> pipeline)
    {
        var stages = new List<JsonObject>(pipeline.Count + 1);

        foreach (var stage in pipeline)
        {
            // Every stage is a single-key document (Craticula.Mongo.MongoPipelineBuilder's own stage
            // order remarks), so its one property name IS the stage's operator.
            var name = stage.First().Key;
            if (name is "$skip" or "$limit" or "$project" or "$sort" or "$addFields" or "$unset")
            {
                continue;
            }

            stages.Add(stage);
        }

        stages.Add(new JsonObject { ["$count"] = "count" });

        return stages;
    }
}
