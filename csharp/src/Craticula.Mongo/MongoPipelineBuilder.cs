using System.Text.Json.Nodes;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo;

/// <summary>
/// Compiles the IR into a MongoDB aggregation pipeline — the first non-SQL backend, and therefore
/// the first thing that tests <see cref="SemanticsResolver"/>'s claim to be backend-neutral rather
/// than SQL-shaped.
///
/// <para><b>Where the seam is, and why there is no <c>IMongoDialect</c>.</b> The SQL compiler needs
/// <c>ISqlDialect</c> because five engines spell the same decision differently. MongoDB is one
/// engine, so an interface here would have exactly one implementation — the mirror image of the BM-1
/// smell <c>docs/architecture/c4-components-sql-compiler.md</c> warns about, and the same reason
/// <c>SqlQueryBuilder</c> composes <c>SUM(...)</c> itself instead of asking a dialect. The seam this
/// project sits behind is the one that already exists: every SEM-* <em>decision</em> is made in
/// <c>Craticula.Core</c> (<see cref="SemanticsResolver"/>, <see cref="GridFilterPipeline"/>,
/// <see cref="DrillDownFilter"/>, the validators) and this assembly only renders them, exactly as
/// <c>Craticula.Sql</c> does. Nothing in <c>Craticula.Core</c> changed to make this compiler
/// possible, which is the property this story exists to check.</para>
///
/// <para><b>Semantics are never re-derived here.</b> Case-sensitivity mechanism and mode, the
/// <c>blank</c> condition, null-inclusivity, the SEM-6 tiebreaker and GRP-2's bucket-identity
/// exactness all come from <see cref="SemanticsResolver"/>. What IS this compiler's own
/// responsibility is the pipeline <em>shape</em> those decisions render into: which stages, in what
/// order, and MongoDB's two artifact forms (see <see cref="MongoQuery.Collation"/>).</para>
///
/// <para><b>The stage order, once, since every method below assumes it.</b>
/// <c>$match</c> (the pre-aggregation row filter, AR-5, plus GRP-5's drill-down) →
/// <c>$group</c> (a grouped level only) →
/// <c>$addFields</c>/<c>$sort</c>/<c>$unset</c> (SEM-3's null-bucket emulation) →
/// <c>$skip</c>/<c>$limit</c> (AG-3's row window; absent under EXP-2's <c>page: none</c>) →
/// <c>$project</c> (a drill-down leaf, GRP-3, or an export, EXP-1(b) — never an ordinary row query,
/// which returns whole documents exactly as its SQL counterpart renders <c>SELECT *</c>).</para>
/// </summary>
public static class MongoPipelineBuilder
{
    /// <summary>
    /// SEM-1's case-insensitive mechanism on MongoDB. <c>strength: 2</c> is the level that folds case
    /// while still distinguishing base characters, and it keeps a supporting index usable — which is
    /// SEM-1's whole point (the rejected alternative, wrapping the field in a lowercasing expression,
    /// is what makes the predicate non-sargable).
    ///
    /// <para>The locale is fixed at <c>"en"</c>: <c>grid-schema.schema.json</c> carries no locale
    /// declaration, so there is nothing host-supplied to read, and every artifact in
    /// <c>spec/fixtures/</c> pins this pair. Making it configurable is a schema change, not a
    /// compiler one.</para>
    /// </summary>
    private static JsonObject NewCollation() => new()
    {
        ["locale"] = "en",
        ["strength"] = 2
    };

    /// <summary>
    /// Compiles <paramref name="request"/> into its aggregation pipeline. Re-runs the IR's own
    /// structural validators first — the same defense in depth every other public entry point in this
    /// codebase performs, since a caller can reach this method with a hand-built tree that never went
    /// through <see cref="GridFilterPipeline"/>.
    /// </summary>
    /// <exception cref="MongoCompilationException">A structurally valid shape this compiler has no
    /// defined rendering for — a field the <see cref="GridSchema"/> does not declare, or a value
    /// whose variant disagrees with that field's declared type.</exception>
    public static MongoQuery Build(MongoQueryRequest request)
    {
        var query = BuildPipeline(request);

        // TL-3: an export (EXP-2's unpaginated page) is long by design and never carries the limit.
        return request.Page is NonePage ? query : query with { MaxTimeMs = request.MaxQueryTimeMs };
    }

    private static MongoQuery BuildPipeline(MongoQueryRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        FilterNodeValidator.Validate(request.Filter);
        PageSpecValidator.Validate(request.Page);
        GroupSpecValidator.Validate(request.Group);
        AggregationValidator.Validate(request.Aggregations);

        // EXP-1's group-export carve-out means the adapter has already nulled the group state on any
        // export, so the two are mutually exclusive by construction. Checked rather than assumed, and
        // for the same reason Craticula.Sql checks it: a hand-built request could set both, and there
        // is no defined shape for an export projection over a $group's bucket-and-aggregate output.
        if (request.Projection is not null && request.Group is not null)
        {
            throw new MongoCompilationException(
                "A request carries both a GroupSpec and an EXP-1(b) export projection. An export emits leaf rows " +
                "and discards group state (EXP-1's carve-out, applied by AgGridRequestParser), so the two never " +
                "arrive together from the adapter.");
        }

        // Same population as the guard above — a hand-built request, since AgGridRequestParser refuses
        // an empty 'exportColumns' at the wire. An empty list would render `{"$project": {"_id": 0}}`,
        // which is not "project nothing" but a stage that suppresses everything, and which older server
        // versions reject outright ("specification must have at least one field").
        if (request.Projection is { Count: 0 })
        {
            throw new MongoCompilationException(
                "A request carries an empty EXP-1(b) export projection. An export of no columns has no compiled " +
                "form; leave Projection null for GRP-3's whole-document read / the schema-order default.");
        }

        // GRP-2's divergence #3: a grouping request at any level computes bucket identity, so no
        // collation is emitted whatever the filter wants — which also means the escape below can
        // never be needed there.
        var suppress = request.Group is not null;

        var sink = new CollationSink();
        var stages = Compose(request, new Context(request.Schema, sink));

        if (!sink.Required || suppress)
        {
            return Assemble(request.Schema, stages, sink, suppress);
        }

        // MDB-9, the part with no rendering: a query-level collation reaches $sort too, and MongoDB
        // has no aggregation-expression form of "order these documents" the way it has one for "are
        // these two values equal". So this one combination is refused rather than rendered — the same
        // choice SQL-7(b) makes for an empty bound value on Oracle, and for the same reason: a
        // plausible pipeline returning rows in the wrong order is worse than a compiler error naming
        // the conflict.
        if (sink.ExactStringSortKeys.Count > 0)
        {
            throw new MongoCompilationException(
                $"The sort orders '{string.Join("', '", sink.ExactStringSortKeys)}', declared " +
                "caseSensitivity: \"sensitive\" (SC-3), while another construct in the same request needs " +
                "SEM-1's case-insensitive collation. MongoDB's collation is a query-level option with no " +
                "per-stage form, and unlike a comparison a $sort has no aggregation-expression escape, so " +
                "the two cannot both be honoured (spec/semantics.md, MDB-9). Split the request, or declare " +
                "the fields with one case sensitivity.");
        }

        // MDB-9: recompile with the escape on. A second pass rather than a look-ahead because
        // "does this pipeline carry a collation" is a property of the WHOLE walk — the CI comparison
        // that forces it may sit in a subtree rendered after the case-sensitive one — and a
        // pre-analysis able to answer it would have to duplicate the walk's own field resolution and
        // could then disagree with it.
        if (!sink.ExactStringComparisons)
        {
            return Assemble(request.Schema, stages, sink, suppress);
        }

        var escaped = new CollationSink();
        return Assemble(
            request.Schema,
            Compose(request, new Context(request.Schema, escaped, ExactStringComparison: true)),
            escaped,
            suppress);
    }

    /// <summary>The stage list for one pass over <paramref name="request"/>. Pure: the only state it
    /// touches is <paramref name="context"/>'s own sink, so <see cref="Build"/> can run it twice.</summary>
    private static List<JsonObject> Compose(MongoQueryRequest request, Context context)
    {
        var grouping = GroupingPlan.Resolve(request.Group, request.Aggregations);

        var stages = new List<JsonObject>();

        if (RenderMatch(request.Filter, grouping?.DrillDown, context) is { } match)
        {
            stages.Add(Stage("$match", match));
        }

        // GRP-1: only a grouped level buckets. The fully-consumed drill-down leaf emits raw
        // documents and never reaches $group.
        if (grouping?.GroupColumn is { } groupColumn)
        {
            stages.Add(Stage("$group", RenderGroup(groupColumn, grouping.Aggregations, context)));
        }

        AppendSortStages(stages, ResolveSortPlan(request.Sort, grouping, context));
        AppendPagingStages(stages, request.Page);

        // GRP-3: a grouping request names its output at every level. A grouped level already does —
        // $group's own output keys are `_id` plus the aggregate names — so the explicit stage is the
        // LEAF's, which would otherwise return whole stored documents (Mongo's `SELECT *`).
        // EXP-1(b) adds the second case that names its output: an export, whose column list the adapter
        // has already resolved. Both land LAST, after any $skip/$limit — the paging window is over
        // rows, not over fields, and the sort keys a $project may drop (page-export/008 orders on the
        // stableKey it does not export) must still be readable when the $sort runs.
        if (grouping is { GroupColumn: null })
        {
            stages.Add(Stage("$project", RenderProjection(context.Schema.FieldOrder, context)));
        }
        else if (grouping is null && request.Projection is { } projection)
        {
            stages.Add(Stage("$project", RenderProjection(projection, context)));
        }

        return stages;
    }

    /// <summary>
    /// GRP-6/BM-3: compiles the set-filter distinct-values pipeline —
    /// <c>[$match?, $group{_id}, &lt;null-bucket sort&gt;, $limit]</c>.
    ///
    /// <para>A separate entry point rather than a mode of <see cref="Build"/>, mirroring
    /// <c>Craticula.Sql.SqlQueryBuilder.BuildSetValues</c>. Three things about it are GRP-6's, not
    /// this compiler's invention:</para>
    /// <list type="bullet">
    /// <item><description><b>It is a bucket query</b> (GRP-6(a)). <c>$group</c> on <c>_id</c>
    /// computes a distinct set exactly as a grouped level does, so its key and its <c>$sort</c> are
    /// exact — no collation, on a case-insensitive string too. The values are handed straight back to
    /// the grid to be sent again as an <c>in</c> value or a <c>groupKey</c>, which GRP-2 then matches
    /// exactly; a folded entry would select neither original document.</description></item>
    /// <item><description><b>No <c>$skip</c>, and no SEM-6 tiebreaker</b> (GRP-6(e)). The cap is a
    /// ceiling, not a window — the list is fetched once. The distinct key is already unique across
    /// the result documents, and the schema's <c>stableKey</c> is not in the output at all.</description></item>
    /// <item><description><b>The cap is applied, never enforced</b> (GRP-6(d)). It arrives already
    /// clamped from <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>; this method only
    /// re-checks it is positive.</description></item>
    /// </list>
    /// </summary>
    /// <exception cref="MongoCompilationException">A field the <see cref="GridSchema"/> does not
    /// declare, or a non-positive <see cref="MongoSetValuesRequest.RowLimit"/>.</exception>
    public static MongoQuery BuildSetValues(MongoSetValuesRequest request) =>
        BuildSetValuesPipeline(request) with { MaxTimeMs = request.MaxQueryTimeMs };

    private static MongoQuery BuildSetValuesPipeline(MongoSetValuesRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        FilterNodeValidator.Validate(request.Filter);

        // Defense in depth against a caller that skipped ResourceLimitsValidator: a zero or negative
        // $limit is not an error on MongoDB the way T-SQL's `FETCH NEXT 0` is — `{$limit: 0}` is
        // rejected by the server, and a negative one is undefined — so refusing here is what keeps
        // the failure legible instead of surfacing as a driver error at execution time.
        if (request.RowLimit <= 0)
        {
            throw new MongoCompilationException(
                $"A set-values row limit must be positive, got {request.RowLimit} — resolve it through " +
                "ResourceLimitsValidator.ResolveSetValuesLimit, which clamps the client's request to the host's " +
                "configured maximum and never yields a non-positive answer.");
        }

        var collation = new CollationSink();
        var context = new Context(request.Schema, collation);

        var path = ResolvePath(request.ColId, context);

        var stages = new List<JsonObject>();

        if (RenderMatch(request.Filter, drillDown: null, context) is { } match)
        {
            stages.Add(Stage("$match", match));
        }

        stages.Add(Stage("$group", new JsonObject { ["_id"] = FieldReference(path) }));

        // GRP-6(a): the distinct key and its ordering are EXACT, on a case-insensitive string too —
        // which needs no resolver call to establish, because `Assemble(suppress: true)` below is what
        // realises it for the whole pipeline. (An earlier draft asked
        // ResolveOrderingAndGroupKeyCaseSensitivity(field, Grouped) here and fed the answer to
        // RecordCollationNeed. That mode returns NotApplicable unconditionally, so the call could
        // never record anything — it read as a live guard on an unreachable branch, which is worse
        // than the comment it was standing in for.)
        //
        // Ascending / nulls-last is MINTED here rather than read from a request — there is no sort
        // model to read — which is why SEM-3's "never re-derive nullsPosition from direction" does
        // not apply: nothing carried one.
        AppendSortStages(stages, [new SortKeyPlan(GroupKeyBucket, GroupKeyPath, SortDirection.Asc, NullsPosition.Last)]);
        stages.Add(Stage("$limit", request.RowLimit));

        return Assemble(request.Schema, stages, collation, suppress: true);
    }

    // ---- assembly ---------------------------------------------------------------------------------

    /// <summary>
    /// GRP-2's accepted divergence #3, in one place: <paramref name="suppress"/> is true for every
    /// pipeline that computes bucket identity — a grouping request at any level (including the
    /// drill-down leaf, whose <c>$match</c> reproduces the bucket being expanded) and a BM-3
    /// distinct-values query. MongoDB's <c>collation</c> is a query-level option governing
    /// <c>$match</c>, <c>$group</c> and <c>$sort</c> together with no per-stage form, so it cannot
    /// serve SEM-1 on a user's filter and GRP-2 on the protocol's keys at once. The protocol's keys
    /// win, and the fact that a collation was wanted survives on
    /// <see cref="MongoQuery.CollationSuppressedByBucketIdentity"/> instead of vanishing.
    /// </summary>
    private static MongoQuery Assemble(GridSchema schema, List<JsonObject> stages, CollationSink collation, bool suppress) =>
        new()
        {
            Collection = schema.Source,
            Pipeline = stages,
            Collation = collation.Required && !suppress ? NewCollation() : null,
            CollationSuppressedByBucketIdentity = collation.Required && suppress
        };

    private static JsonObject Stage(string name, JsonNode? body) => new() { [name] = body };

    /// <summary>
    /// The per-compilation state threaded through the tree walk.
    ///
    /// <para><paramref name="IsGroupKeyMatch"/> carries <em>provenance</em>, not shape, exactly as
    /// the SQL builder's does: the drill-down predicates and the user's own filter are both ordinary
    /// IR (GRP-5) and indistinguishable by inspection, yet they resolve case sensitivity by different
    /// rules. It is set once, by <see cref="RenderMatch"/>, on the context the drill-down subtree is
    /// walked under — never re-derived from a node, and never recovered by reference identity, which
    /// GRP-5 names as a trap that any later node-rebuilding change would spring silently.</para>
    ///
    /// <para><paramref name="ExactStringComparison"/> is MDB-9's escape, set for the whole of
    /// <see cref="Build"/>'s second pass: this pipeline WILL carry a query-level collation, so a
    /// comparison SEM-1 resolved <em>case-sensitive</em> has to be rendered somewhere the collation
    /// does not reach.</para>
    /// </summary>
    private readonly record struct Context(
        GridSchema Schema,
        CollationSink Collation,
        bool IsGroupKeyMatch = false,
        bool ExactStringComparison = false);

    /// <summary>
    /// What one pass over the tree observed about SEM-1, which is what decides between
    /// <c>mongo-artifact.schema.json</c>'s two shapes and whether MDB-9's second pass is needed. A
    /// mutable sink rather than a return value because every answer here is a property of the whole
    /// pipeline while the observations are scattered across the filter walk and the sort walk —
    /// threading them back through every renderer's signature would put three rendering-unrelated
    /// out-parameters on all of them.
    /// </summary>
    private sealed class CollationSink
    {
        /// <summary>Some construct resolved to SEM-1's collation mechanism, case-insensitively.</summary>
        public bool Required { get; set; }

        /// <summary>Some comparison resolved case-<b>sensitive</b> on a <c>string</c> field, so it
        /// needs MDB-9's <c>$expr</c> escape if <see cref="Required"/> also holds.</summary>
        public bool ExactStringComparisons { get; set; }

        /// <summary>The sort keys that resolved case-<b>sensitive</b> on a <c>string</c> field. They
        /// have no escape (MDB-9), so this list is what <see cref="Build"/> refuses on rather than
        /// silently folding.</summary>
        public List<string> ExactStringSortKeys { get; } = [];
    }

    private static void RecordCollationNeed(SemanticsResolver.CaseSensitivityMode mode, Context context)
    {
        if (mode == SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            context.Collation.Required = true;
        }
    }

    // ---- grouping (BM-2) --------------------------------------------------------------------------

    /// <summary>
    /// The grouped level's <c>$group</c> stage: <c>_id</c> is the bucket key, followed by one
    /// accumulator per <c>valueCol</c> under its GRP-4 output name.
    ///
    /// <para>The bucket key stays <c>_id</c> and is not renamed to the logical field name. That is
    /// MongoDB's own output contract for the stage rather than a physical column name leaking into
    /// the response — GRP-3's argument (a grid that asked for <c>fiscalYear</c> cannot read a
    /// <c>fiscal_year</c> key) is about physical mappings, and <c>_id</c> is not one. Every grouped
    /// artifact in <c>spec/fixtures/group-aggregation/</c> pins this shape.</para>
    /// </summary>
    private static JsonObject RenderGroup(string groupColumn, IReadOnlyList<Aggregation> aggregations, Context context)
    {
        var group = new JsonObject { ["_id"] = FieldReference(ResolvePath(groupColumn, context)) };

        foreach (var aggregation in aggregations)
        {
            var output = aggregation.OutputName;

            // MDB-10: a stage document is a map, so a repeated key is LAST-WINS rather than an error
            // — one accumulator would vanish from a syntactically perfect pipeline, and the grid
            // would read a column that silently holds another column's number.
            //
            // NOT fully covered by #1886's upstream AggregationValidator, and still load-bearing —
            // do not delete this as "made redundant". Core's check only compares aggregations
            // against EACH OTHER; it has no notion of "_id", which is this stage's bucket key and is
            // seeded into `group` before this loop runs. An aggregation whose OutputName resolves to
            // "_id" — reachable from the wire via an explicit alias, e.g. {"id":"_id","field":"amount",
            // "aggFunc":"sum"}, which "^[A-Za-z_][A-Za-z0-9_]*$" (ir.schema.json's own alias pattern)
            // permits and AggregationValidator therefore accepts — collides with the seed rather than
            // with another aggregation, and only this ContainsKey check (which runs against the
            // pre-seeded dictionary, not a fresh one) catches it. Measured: the request above throws
            // here rather than silently overwriting the bucket key.
            if (group.ContainsKey(output))
            {
                throw new MongoCompilationException(
                    $"An aggregation resolves to the output name '{output}', which collides with either " +
                    "another aggregation's output name or the grouped level's own bucket key (GRP-4: an " +
                    "alias, or the <field>_<func> default). A $group stage is a document, so the later " +
                    "one would silently replace the earlier — the request names an output column the " +
                    "same as something else in this stage.");
            }

            group[output] = RenderAccumulator(aggregation, context);
        }

        return group;
    }

    /// <summary>
    /// AR-8's closed v1 function set, and AGG-1's one non-obvious member.
    ///
    /// <para><b><c>count</c> is a conditional sum, never <c>{"$sum": 1}</c>.</b> AR-8's aggregation
    /// is <c>(field, func)</c> and the field is not decorative: <c>count</c> means "how many
    /// documents have a non-null value for this field", identically to SQL's <c>COUNT(field)</c>
    /// (which already skips NULLs) and Elasticsearch's <c>value_count</c> (which already skips
    /// missing). <c>{"$sum": 1}</c> counts every document in the bucket regardless, so it silently
    /// answers a different question the moment the aggregated field can be null — and it is the form
    /// a port reaches for first, which is why AGG-1 exists as a rule rather than a note.</para>
    /// </summary>
    private static JsonObject RenderAccumulator(Aggregation aggregation, Context context)
    {
        var reference = FieldReference(ResolvePath(aggregation.Field, context));

        return aggregation.Func switch
        {
            AggregationFunc.Sum => new JsonObject { ["$sum"] = reference },
            AggregationFunc.Min => new JsonObject { ["$min"] = reference },
            AggregationFunc.Max => new JsonObject { ["$max"] = reference },
            AggregationFunc.Avg => new JsonObject { ["$avg"] = reference },
            AggregationFunc.Count => new JsonObject { ["$sum"] = NullSafeCount(reference) },
            _ => throw new MongoCompilationException($"Unknown aggregation function '{aggregation.Func}'.")
        };
    }

    private static JsonObject NullSafeCount(JsonNode reference) => new()
    {
        ["$cond"] = new JsonArray(IsNullExpression(reference), 0, 1)
    };

    /// <summary>
    /// The <c>$project</c> body for an ordered list of logical field names — GRP-3's drill-down leaf
    /// (every declared field, in <see cref="GridSchema.FieldOrder"/>) and EXP-1(b)'s export (the resolved
    /// export columns, in request order) share it, because they answer the same question about the
    /// same schema. A field whose physical path differs from its logical name is re-keyed
    /// (<c>"fiscalYear": "$fiscal_year"</c>); one whose path matches is a plain inclusion (<c>1</c>).
    ///
    /// <para>"Declaration order" is <see cref="GridSchema.FieldOrder"/>, read from the schema
    /// document, never <c>Fields.Keys</c> — that dictionary's enumeration order is unspecified by
    /// .NET, and <c>group-aggregation/005</c>/<c>006</c> compare this stage key for key.</para>
    ///
    /// <para><b><c>_id: 0</c> is written LAST, after the output fields.</b> MongoDB accepts the
    /// suppression anywhere in the document, so this is a spelling choice — but the keys before it are
    /// the OUTPUT list, whose order is normative (GRP-3/EXP-1(b)) and byte-compared, and interleaving a
    /// key that names no output column into that list would make the artifact's own ordering claim
    /// harder to read. Pinned by <c>group-aggregation/005</c>/<c>006</c> and, in this category,
    /// <c>page-export/008</c>.</para>
    /// </summary>
    private static JsonObject RenderProjection(IReadOnlyList<string> fields, Context context)
    {
        var projection = new JsonObject();

        foreach (var field in fields)
        {
            var path = ResolvePath(field, context);
            projection[field] = path == field ? 1 : FieldReference(path);
        }

        projection["_id"] = 0;

        return projection;
    }

    // ---- filter tree ------------------------------------------------------------------------------

    /// <summary>
    /// GRP-5: the whole <c>$match</c> body — the synthesised drill-down composed with the request's
    /// own filter, drill-down first, so the stage reads along the group path before the user's own
    /// predicates.
    ///
    /// <para><b>The two halves are two separate walks, not one walk over a merged tree.</b> They
    /// resolve case sensitivity by different rules (GRP-2 versus SEM-1) and are indistinguishable by
    /// shape once merged — a <c>groupKeys</c> match on <c>region</c> and a user <c>eq</c> on
    /// <c>region</c> are the same node. The only thing that could tell them apart in a single walk is
    /// reference identity, which GRP-5 names explicitly as a trap: any later change that rebuilds
    /// nodes between synthesis and rendering would silently give the drill-down the user's mechanism,
    /// <c>"EMEA"</c> would start matching <c>"emea"</c>, and child rows would stop summing to the
    /// parent with no exception and no failing artifact.</para>
    ///
    /// <para><b>The composition is <c>$and</c>, not two keys in one document.</b> GRP-5 settles this:
    /// the drill-down is ordinary IR merged through the same primitive as <c>customFilters</c> and
    /// static filters, so a compiler that reuses its filter renderer for it — which is every sensible
    /// one — gets the composite form for free. The alternative reading, that a synthesised
    /// conjunction is not an IR construct and may be flattened, is the one GRP-5 rejects by
    /// name.</para>
    /// </summary>
    private static JsonObject? RenderMatch(FilterNode? filter, FilterNode? drillDown, Context context)
    {
        var groupPath = drillDown is null ? null : RenderNode(drillDown, context with { IsGroupKeyMatch = true });
        var userFilter = filter is null ? null : RenderNode(filter, context);

        return (groupPath, userFilter) switch
        {
            (null, null) => null,
            ({ } path, null) => path,
            (null, { } user) => user,
            ({ } path, { } user) => new JsonObject { ["$and"] = new JsonArray(path, user) }
        };
    }

    private static JsonObject RenderNode(FilterNode node, Context context) => node switch
    {
        AndNode and => RenderComposite("$and", and, context),
        OrNode or => RenderComposite("$or", or, context),
        NotNode not => RenderNot(not, context),
        ComparisonNode comparison => RenderComparison(comparison, context),
        _ => throw new MongoCompilationException($"Unknown FilterNode type '{node.GetType().Name}'.")
    };

    /// <summary>
    /// AR-5's composites. A single-child composite is NOT collapsed — <c>{"$and": [x]}</c>, mirroring
    /// SQL-2's <c>(x)</c> — because the tree's own depth is what
    /// <c>spec/fixtures/filter-tree/011</c>-<c>013</c> pin, and collapsing it would make a
    /// SEC-3-boundary fixture indistinguishable from a shallower one.
    /// </summary>
    private static JsonObject RenderComposite(string @operator, CompositeFilterNode composite, Context context)
    {
        var children = new JsonArray();
        foreach (var child in composite.Nodes)
        {
            children.Add(RenderNode(child, context));
        }

        return new JsonObject { [@operator] = children };
    }

    /// <summary>
    /// SEM-2/MDB-2: a tree-level <c>NOT</c>, at every nesting depth, is null-inclusive exactly as
    /// SQL-2's third bullet — one <c>{field: null}</c> clause per distinct field referenced in the
    /// child subtree, in first-appearance order, OUTSIDE the <c>$nor</c>. <c>$nor</c> alone returns a
    /// null document only when the child fails to match it, and <c>neq</c>, <c>blank</c>, an inner
    /// <c>not</c> or an <c>or</c> whose other field matches all match one. The clause is the
    /// <em>inclusion</em> SEM-2 requires, not the <c>{field: {$ne: null}}</c> guard its second
    /// MongoDB Must-NOT forbids.
    /// </summary>
    private static JsonObject RenderNot(NotNode not, Context context)
    {
        var clauses = new JsonArray(new JsonObject { ["$nor"] = new JsonArray(RenderNode(not.Node, context)) });
        foreach (var field in FilterNodeFields.DistinctInOrder(not.Node))
        {
            clauses.Add(new JsonObject { [ResolvePath(field, context)] = null });
        }

        return new JsonObject { ["$or"] = clauses };
    }

    private static JsonObject RenderComparison(ComparisonNode node, Context context)
    {
        var field = ResolveField(node.Field, context);
        var path = ResolvePath(node.Field, context);

        return node.Op switch
        {
            ComparisonOperator.Blank => RenderBlank(path, field),
            ComparisonOperator.NotBlank => RenderNotBlank(path, field),

            // AR-6's unary boolean shorthand carries no value of its own, so the compiler mints one
            // and routes it through the ordinary equality path rather than spelling a second form.
            ComparisonOperator.True =>
                RenderScalar(path, field, node.Field, ComparisonOperator.Eq, new BooleanValue { Value = true }, context),
            ComparisonOperator.False =>
                RenderScalar(path, field, node.Field, ComparisonOperator.Eq, new BooleanValue { Value = false }, context),

            ComparisonOperator.Eq or ComparisonOperator.Neq
                or ComparisonOperator.Gt or ComparisonOperator.Gte
                or ComparisonOperator.Lt or ComparisonOperator.Lte =>
                NullInclusive(RenderScalar(path, field, node.Field, node.Op, RequireValue(node), context), node.Op, path),

            ComparisonOperator.Contains or ComparisonOperator.NotContains
                or ComparisonOperator.StartsWith or ComparisonOperator.EndsWith =>
                NullInclusive(RenderSubstring(path, field, node, context), node.Op, path),

            // SEM-8: empty list = constant. `$in: []` matches nothing, `$nin: []` matches every document,
            // missing field included, so neither needs the null disjunct; no string comparison happens, so
            // no collation is requested.
            ComparisonOperator.In or ComparisonOperator.NotIn when node.Values is { Count: 0 } =>
                new JsonObject
                {
                    [path] = new JsonObject
                    {
                        [node.Op == ComparisonOperator.NotIn ? "$nin" : "$in"] = new JsonArray()
                    }
                },

            ComparisonOperator.In or ComparisonOperator.NotIn =>
                NullInclusive(RenderSet(path, field, node, context), node.Op, path),

            ComparisonOperator.InRange => RenderRange(path, field, node, context),

            _ => throw new MongoCompilationException($"Unknown comparison operator '{node.Op}'.")
        };
    }

    /// <summary>
    /// SEM-2: <c>neq</c>/<c>notContains</c>/<c>notIn</c> must match null-valued and missing
    /// documents, spelled as an explicit <c>$or</c> with a <c>{field: null}</c> clause.
    ///
    /// <para>SEM-2's own worked example is emphatic that this composition is emitted <b>even though
    /// the naive single-clause form happens to be correct</b> in MongoDB's plain query language
    /// (<c>$ne</c> already matches a missing field): it keeps the compiled shape parallel to the SQL
    /// and ES forms, and it stays correct inside an <c>$expr</c>/aggregation-expression context,
    /// where the query language's implicit missing-field handling no longer applies. Equally
    /// emphatic is the mirror-image Must-NOT: never add a defensive <c>{field: {$ne: null}}</c> guard
    /// "for parity with SQL" — that would <em>exclude</em> null documents from a negative comparison,
    /// which is the opposite of this rule.</para>
    /// </summary>
    private static JsonObject NullInclusive(JsonObject predicate, ComparisonOperator op, string path) =>
        SemanticsResolver.IsNullInclusive(op)
            ? new JsonObject { ["$or"] = new JsonArray(predicate, new JsonObject { [path] = null }) }
            : predicate;

    /// <summary>
    /// SEM-2: <c>blank</c> is "null or empty string" for a text field and "null" for every other
    /// type. <c>{field: null}</c> already covers a missing field as well as a stored null, so the
    /// non-text arm needs nothing more; the text arm adds <c>""</c> as a second member of the same
    /// <c>$in</c>.
    ///
    /// <para>There is no MongoDB counterpart to SQL-7's second question ("does this engine treat
    /// <c>''</c> as NULL?"): MongoDB stores the empty string as a distinct value from null, so the
    /// field-type half is the whole answer — which is exactly what
    /// <see cref="SemanticsResolver.ResolveBlankCondition"/>'s own doc anticipates when it says a
    /// Mongo compiler "will have its own second half or none".</para>
    /// </summary>
    private static JsonObject RenderBlank(string path, FieldConfig field) =>
        SemanticsResolver.ResolveBlankCondition(field.Type) switch
        {
            SemanticsResolver.BlankCondition.NullOrEmptyString =>
                new JsonObject { [path] = new JsonObject { ["$in"] = new JsonArray(null, "") } },
            SemanticsResolver.BlankCondition.NullOnly =>
                new JsonObject { [path] = null },
            var condition => throw new MongoCompilationException($"Unknown blank condition '{condition}'.")
        };

    /// <summary>
    /// SEM-2: <c>notBlank</c> is <c>blank</c>'s exact Boolean negation, never a separately-derived
    /// condition that could disagree with it at the edges. MongoDB has an operator-level negation for
    /// each arm — <c>$nin</c> is <c>$in</c>'s and <c>$ne</c> is the implicit equality's — so the
    /// negation is applied to the very operator <see cref="RenderBlank"/> chose rather than to some
    /// re-derived predicate, which is what makes the two impossible to drift.
    /// </summary>
    private static JsonObject RenderNotBlank(string path, FieldConfig field) =>
        SemanticsResolver.ResolveBlankCondition(field.Type) switch
        {
            SemanticsResolver.BlankCondition.NullOrEmptyString =>
                new JsonObject { [path] = new JsonObject { ["$nin"] = new JsonArray(null, "") } },
            SemanticsResolver.BlankCondition.NullOnly =>
                new JsonObject { [path] = new JsonObject { ["$ne"] = null } },
            var condition => throw new MongoCompilationException($"Unknown blank condition '{condition}'.")
        };

    /// <summary>
    /// SEM-1: the resolver decides how the comparison treats case and, when it folds it, by which
    /// mechanism; this compiler only realizes that decision. <paramref name="family"/> is the
    /// mechanism the CALLER is about to render, and a mismatch is a compiler bug rather than a client
    /// error — an insensitive field whose operator resolves to
    /// <see cref="SemanticsResolver.CaseSensitivityMechanism.PatternMatch"/> must never reach the
    /// collation path, and vice versa. It is unreachable by construction, so it fails loudly instead
    /// of degrading to "no mechanism", which would be a plausible-looking artifact that folds case in
    /// the wrong place.
    ///
    /// <para>A predicate inside the synthesised drill-down is not a filter at all: it is a group-key
    /// MATCH, and GRP-2 requires it to agree with the <c>$group</c> that produced the bucket label
    /// being expanded. It therefore resolves through
    /// <see cref="SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity"/>, from the provenance
    /// on <see cref="Context.IsGroupKeyMatch"/>.</para>
    /// </summary>
    private static SemanticsResolver.CaseSensitivityMode ResolveCaseSensitivity(
        FieldConfig field, string fieldName, ComparisonOperator op,
        SemanticsResolver.CaseSensitivityMechanism family, Context context)
    {
        SemanticsResolver.CaseSensitivityMode mode;

        if (context.IsGroupKeyMatch)
        {
            mode = SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(field, SemanticsResolver.GroupingMode.Grouped)
                .Mode;
        }
        else
        {
            var decision = SemanticsResolver.ResolveCaseSensitivity(field, op);

            if (decision.Mode == SemanticsResolver.CaseSensitivityMode.Insensitive && decision.Mechanism != family)
            {
                throw new MongoCompilationException(
                    $"Operator '{op}' on field '{fieldName}' resolves to the '{decision.Mechanism}' case-insensitivity " +
                    $"mechanism, but is being rendered through the '{family}' family — SEM-1 requires one mechanism " +
                    "per field across every context.");
            }

            mode = decision.Mode;
        }

        // Only the collation family reaches the query-level option; $regex carries its own "i" — and,
        // by the same token, only the collation family can be caught BY a collation it did not ask
        // for, which is the observation MDB-9's escape rests on.
        if (family == SemanticsResolver.CaseSensitivityMechanism.Collation)
        {
            RecordCollationNeed(mode, context);

            if (mode == SemanticsResolver.CaseSensitivityMode.Sensitive)
            {
                context.Collation.ExactStringComparisons = true;
            }
        }

        return mode;
    }

    /// <summary>
    /// MDB-9: whether this comparison must be rendered as an aggregation expression to escape a
    /// collation the rest of the pipeline needs. <see cref="SemanticsResolver.CaseSensitivityMode.Sensitive"/>
    /// is reachable only for a <c>string</c> field, so no separate type test is needed — and no
    /// other mode wants the escape: a non-text comparison is unaffected by a collation in the first
    /// place, and an insensitive one is what asked for it.
    /// </summary>
    private static bool NeedsExactStringEscape(SemanticsResolver.CaseSensitivityMode mode, Context context) =>
        context.ExactStringComparison && mode == SemanticsResolver.CaseSensitivityMode.Sensitive;

    /// <summary>
    /// MDB-9's rendering: the same comparison, moved out of the query language and into an
    /// aggregation expression, where MongoDB compares values by simple binary comparison and the
    /// query-level <c>collation</c> does not apply. SEM-2's own MongoDB paragraph already names this
    /// property — it is why that paragraph reaches for <c>$strcasecmp</c> to get a case-INSENSITIVE
    /// comparison inside an <c>$expr</c>, which would be pointless if the collation reached there.
    ///
    /// <para>The field becomes a path reference (<c>"$employeeCode"</c>) and the operator takes an
    /// array of two operands, which is the only form the aggregation language has: there is no
    /// <c>{field: {$eq: v}}</c> spelling here. That parallel is the second reason SEM-2 gives for
    /// spelling <c>$eq</c>/<c>$ne</c> explicitly in the query language too (see
    /// <see cref="ScalarOperator"/>) — the two renderings differ only in how the field is
    /// addressed.</para>
    ///
    /// <para><b>The two operands are not symmetric and must not be built the same way.</b> The field
    /// operand is a path reference by design; the value operand has to be bound with
    /// <see cref="Literal"/>, because this language reads a <c>$</c>-prefixed string as a path too.</para>
    /// </summary>
    private static JsonObject Expr(JsonNode expression) => new() { ["$expr"] = expression };

    /// <summary>
    /// MDB-9's binding. Inside an aggregation expression a string beginning with <c>$</c> is a
    /// <b>field path reference</b>, not a string — MongoDB's own <c>$literal</c> reference states it
    /// outright and gives this very example: <c>{"$eq": ["$price", "$1"]}</c> compares the
    /// <c>price</c> field against the field named <c>1</c>. So an IR value of <c>"$salary"</c>
    /// dropped raw into <see cref="Expr"/>'s operand array stops being a comparison against a string
    /// and becomes a comparison against another field — silently wrong rows, and a client naming any
    /// path it likes (<c>"$salary.amount"</c>, <c>"$$ROOT"</c>) in a request that never exposed it.
    /// <c>{"$literal": v}</c> is the aggregation language's answer, and it is the same discipline
    /// SEC-2 states for SQL: every compared value is bound. The query language has no such rewriting
    /// — a <c>$</c>-prefixed string in <c>{c: {"$eq": v}}</c> is just a string — which is why only
    /// the <c>$expr</c> sites need this and none of the ordinary field documents do.
    ///
    /// <para><b>Applied to every IR value, whatever its type — no carve-out.</b> Only a string can
    /// spell a path today, but the conditional version is a second rule (MDB-1 and SQL-1 both reject
    /// exactly that shape of exception), and "only strings are at risk" is already false at the JSON
    /// level: <see cref="MongoExtendedJson.Encode"/> renders a <c>decimal</c> as
    /// <c>{"$numberDecimal": "1000"}</c>, a document whose first key starts with <c>$</c>, which in
    /// expression position is an operator position rather than a value. That is unreachable only
    /// because <see cref="SemanticsResolver.CaseSensitivityMode.Sensitive"/> is string-only — an
    /// invariant of another class that a port has no reason to preserve. Wrapping unconditionally
    /// costs nothing (<c>$literal</c> returns any BSON value unevaluated) and needs no type table to
    /// state or to port.</para>
    ///
    /// <para>The FIELD operand is never wrapped: <see cref="FieldReference"/> mints it from the
    /// schema and it is meant to resolve as a path.</para>
    /// </summary>
    private static JsonObject Literal(JsonNode? value) => new() { ["$literal"] = value };

    private static JsonObject RenderScalar(
        string path, FieldConfig field, string fieldName, ComparisonOperator op, TypedValue value, Context context)
    {
        var mode = ResolveCaseSensitivity(
            field, fieldName, op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var encoded = MongoExtendedJson.Encode(value, field, fieldName);

        if (NeedsExactStringEscape(mode, context))
        {
            return Expr(new JsonObject
            {
                [ScalarOperator(op)] = new JsonArray(FieldReference(path), Literal(encoded))
            });
        }

        return new JsonObject
        {
            [path] = new JsonObject { [ScalarOperator(op)] = encoded }
        };
    }

    /// <summary>
    /// SEM-7: the substring family compiles to <c>$regex</c> — MongoDB has no non-regex substring
    /// operator, which is also why SEM-1 assigns it the pattern-match mechanism rather than the
    /// collation one (a query-level collation does not reach a <c>$regex</c> at all).
    ///
    /// <para>The pattern is built from an already-escaped literal, never from client-supplied regex
    /// syntax (SEC-5), and the escape set is <see cref="MongoRegexEscaping"/>'s full one rather than
    /// SEC-4's four <c>LIKE</c>/wildcard characters — SEM-7 makes that conflation an explicit
    /// Must-NOT. The <c>^</c>/<c>$</c> anchors are added around the escaped value, so a literal
    /// <c>^</c> the user typed cannot become one.</para>
    ///
    /// <para><b>This family needs no MDB-9 escape, and that is a property of <c>$regex</c> rather
    /// than an omission.</b> A query-level collation does not reach a <c>$regex</c> at all — MongoDB
    /// refuses to use a case-insensitive collation for one and matches by the pattern's own rules —
    /// which is the same fact SEM-1 leans on when it assigns the substring family the pattern-match
    /// mechanism instead. So a case-sensitive <c>contains</c> is already exact beside a collation,
    /// and moving it into <c>$regexMatch</c> would change the rendering without changing the
    /// semantics.</para>
    /// </summary>
    private static JsonObject RenderSubstring(string path, FieldConfig field, ComparisonNode node, Context context)
    {
        var mode = ResolveCaseSensitivity(
            field, node.Field, node.Op, SemanticsResolver.CaseSensitivityMechanism.PatternMatch, context);

        // There is no portable meaning for "does this number contain that substring", and guessing
        // one would silently change both semantics and index usage. The DECLARED type decides that —
        // checked first and separately from the value's variant, because a caller that skipped SEM-5
        // coercion can hand a StringValue to an int64/date field, and rendering it would produce a
        // case-SENSITIVE $regex against a numeric field (SemanticsResolver only resolves the
        // pattern-match mechanism for a `string` field). This is the one operator path that never
        // reaches MongoExtendedJson.Encode, so it carries its own type check.
        if (field.Type != FieldType.String)
        {
            throw new MongoCompilationException(
                $"Field '{node.Field}' is declared '{field.Type}', but operator '{node.Op}' is a substring match " +
                "and only has a defined rendering against a 'string' field.");
        }

        if (RequireValue(node) is not StringValue pattern)
        {
            throw new MongoCompilationException(
                $"Operator '{node.Op}' on field '{node.Field}' is a substring match, so its value must be a " +
                "stringValue — run TypeCoercionValidator (SEM-5) before compiling.");
        }

        var escaped = MongoRegexEscaping.Escape(pattern.Value);

        var regex = new JsonObject
        {
            ["$regex"] = node.Op switch
            {
                ComparisonOperator.StartsWith => $"^{escaped}",
                ComparisonOperator.EndsWith => $"{escaped}$",
                _ => escaped
            }
        };

        // SC-3's case-SENSITIVE opt-in spells nothing: MongoDB's own default regex matching is
        // case-sensitive, so "no $options" is exact here — unlike the SQL engines whose default
        // collation folds case and where SQL-6 makes the sensitive direction an explicit token.
        if (mode == SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            regex["$options"] = "i";
        }

        // SQL-3's rule, reached on MongoDB by a different route: the negation stays ON the operator
        // (`{field: {$not: {$regex: ...}}}`) rather than becoming an outer `$nor` around the whole
        // clause. `$nor` is the rendering of a tree-level notNode — an arbitrary subtree — and
        // spelling notContains that way would make one comparison's negation indistinguishable from
        // a one-child NOT node in the artifact, on top of losing the field-scoped form MongoDB can
        // index. The null-inclusive `$or` NullInclusive adds around this is a separate, outer thing:
        // `$not` on its own excludes documents where the field is missing.
        return new JsonObject
        {
            [path] = node.Op == ComparisonOperator.NotContains
                ? new JsonObject { ["$not"] = regex }
                : regex
        };
    }

    private static JsonObject RenderSet(string path, FieldConfig field, ComparisonNode node, Context context)
    {
        var mode = ResolveCaseSensitivity(
            field, node.Field, node.Op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var values = node.Values
            ?? throw new MongoCompilationException($"Operator '{node.Op}' on field '{node.Field}' requires 'values'.");

        if (NeedsExactStringEscape(mode, context))
        {
            // The aggregation `$in` is `{$in: [<expression>, <array>]}` — operand order reversed from
            // the query language's field document — and it has no `$nin` counterpart at all, so the
            // negation is composed with `$not`. That is not SQL-3's outer-NOT spelling reappearing:
            // `$nin` simply does not exist in this language, and the negation still applies to this
            // one comparison rather than to a subtree.
            //
            // The membership array is an ARRAY EXPRESSION, so its elements are parsed as expressions
            // too — a `$`-prefixed member would resolve as a field path exactly as a scalar operand
            // would. Each member is therefore wrapped individually (MDB-9): the rule is "every IR
            // value in expression position", the same unit the scalar and range escapes use, and the
            // array itself is compiler-minted structure rather than a value.
            var members = new JsonArray();
            foreach (var value in values)
            {
                members.Add(Literal(MongoExtendedJson.Encode(value, field, node.Field)));
            }

            var membership = new JsonObject { ["$in"] = new JsonArray(FieldReference(path), members) };

            return Expr(node.Op == ComparisonOperator.NotIn
                ? new JsonObject { ["$not"] = new JsonArray(membership) }
                : membership);
        }

        var encoded = new JsonArray();
        foreach (var value in values)
        {
            encoded.Add(MongoExtendedJson.Encode(value, field, node.Field));
        }

        return new JsonObject
        {
            [path] = new JsonObject { [node.Op == ComparisonOperator.NotIn ? "$nin" : "$in"] = encoded }
        };
    }

    /// <summary>
    /// SEM-4: <c>inRange</c> compiles to both bounds' comparisons, each spelled from its EXPLICIT
    /// inclusivity flag — never a guessed default, and never SQL <c>BETWEEN</c>'s familiar
    /// inclusive-inclusive assumption.
    ///
    /// <para>MongoDB expresses both bounds as two operators on ONE field document
    /// (<c>{amount: {$gte: a, $lt: b}}</c>) rather than as a two-clause <c>$and</c>. That is not the
    /// composite-flattening GRP-5 rejects for the drill-down: this is a single <c>rangeComparisonNode</c>
    /// — one IR leaf, not an <c>and</c> of two — and the field-document form is the only place in
    /// MongoDB's query language where two constraints on one field compose without a
    /// composite.</para>
    /// </summary>
    private static JsonObject RenderRange(string path, FieldConfig field, ComparisonNode node, Context context)
    {
        if (node.From is null || node.To is null || node.FromInclusive is null || node.ToInclusive is null)
        {
            throw new MongoCompilationException(
                $"Operator 'inRange' on field '{node.Field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.");
        }

        var lowerOp = node.FromInclusive.Value ? ComparisonOperator.Gte : ComparisonOperator.Gt;
        var upperOp = node.ToInclusive.Value ? ComparisonOperator.Lte : ComparisonOperator.Lt;

        var mode = ResolveCaseSensitivity(
            field, node.Field, lowerOp, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var lower = MongoExtendedJson.Encode(node.From, field, node.Field);
        var upper = MongoExtendedJson.Encode(node.To, field, node.Field);

        if (NeedsExactStringEscape(mode, context))
        {
            // The one-field-document form has no aggregation-expression counterpart — an expression
            // operator takes operands, not a field to hang two of them off — so MDB-9's escape is the
            // one place `inRange` DOES render as a conjunction. It is still one IR leaf; the `$and`
            // here is the expression language's only way to spell two bounds, not the composite GRP-5
            // talks about.
            return Expr(new JsonObject
            {
                ["$and"] = new JsonArray(
                    new JsonObject { [ScalarOperator(lowerOp)] = new JsonArray(FieldReference(path), Literal(lower)) },
                    new JsonObject { [ScalarOperator(upperOp)] = new JsonArray(FieldReference(path), Literal(upper)) })
            });
        }

        return new JsonObject
        {
            [path] = new JsonObject
            {
                [ScalarOperator(lowerOp)] = lower,
                [ScalarOperator(upperOp)] = upper
            }
        };
    }

    private static TypedValue RequireValue(ComparisonNode node) =>
        node.Value ?? throw new MongoCompilationException($"Operator '{node.Op}' on field '{node.Field}' requires 'value'.");

    /// <summary>
    /// The comparison operators, one uniform table with no carve-out — including <c>$eq</c>, which
    /// MongoDB also admits in the implicit <c>{field: value}</c> form.
    ///
    /// <para><b>The implicit form is deliberately not used.</b> SEM-2's Mongo worked example settles
    /// the general question for this backend: it emits the explicit composed form for <c>neq</c>
    /// <em>even though</em> the naive one is correct, "to keep the compiled shape parallel to the SQL
    /// and ES forms" and to stay valid in an <c>$expr</c> context, where only <c>{"$eq": [...]}</c>
    /// exists at all. Spelling the operator everywhere is also the rule with no second rule, the same
    /// reason SQL-1 quotes every identifier rather than only the ones that need it.</para>
    ///
    /// <para><b>This is the story's one genuinely contested call and it is not settled by the fixture
    /// suite</b>, which spells <c>eq</c> both ways in adjacent cases of the same category
    /// (<c>operators/001</c> explicit, <c>operators/003</c>/<c>005</c>/<c>007</c>/<c>046</c>
    /// implicit) — see <c>docs/feat/1643/context.md</c>. The two forms are semantically identical for
    /// every value the IR can carry, so nothing but the artifact text depends on it; if the project
    /// settles on the implicit form instead, this table is the only place that changes.</para>
    /// </summary>
    private static string ScalarOperator(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Eq => "$eq",
        ComparisonOperator.Neq => "$ne",
        ComparisonOperator.Gt => "$gt",
        ComparisonOperator.Gte => "$gte",
        ComparisonOperator.Lt => "$lt",
        ComparisonOperator.Lte => "$lte",
        _ => throw new MongoCompilationException($"Operator '{op}' is not a scalar comparison.")
    };

    // ---- sorting (SEM-3 / SEM-6) --------------------------------------------------------------------

    /// <summary>The bucket name a grouped level's or a distinct-values query's <c>_id</c> key uses.
    /// Named for the ROLE rather than for the group column, because the column changes per level
    /// while the key it lands on does not.
    ///
    /// <para>SEM-3 names the per-field form <c>__&lt;field&gt;NullBucket</c> and says nothing about
    /// the two names a grouping request needs, so MDB-10 pins them: this one for the <c>_id</c> key,
    /// and <c>__&lt;aggregate output name&gt;NullBucket</c> for an aggregate. The two share one flat
    /// namespace and an aggregate's half of it is client-controlled (AGG-2 takes the output name from
    /// <c>valueCols[].id</c>), so a <c>valueCols</c> entry named <c>group</c> lands on this very
    /// string. That is not a name clash to shrug at: <c>$addFields</c>, <c>$sort</c> and
    /// <c>$unset</c> are all documents, so the collision is silent and the <em>primary</em> sort key
    /// changes. <see cref="AppendSortStages"/> refuses it rather than renaming either side, which
    /// would make the emitted bucket name depend on what else the request happened to
    /// contain.</para></summary>
    private const string GroupKeyBucket = "__groupNullBucket";

    private const string GroupKeyPath = "_id";

    /// <summary>One resolved sort key: which synthetic bucket field emulates its null placement, what
    /// the pipeline actually sorts on, and the two directions.</summary>
    /// <param name="Bucket">The synthetic field that emulates the key's null placement.</param>
    /// <param name="Path">What the pipeline sorts on.</param>
    /// <param name="Direction">The key's direction.</param>
    /// <param name="NullsPosition">Where nulls sort.</param>
    /// <param name="ExactField">MDB-10 / #2809: set only on SEM-6's appended exact tiebreaker when an earlier key of the same sort already
    /// names the same path (a case-insensitive text stable key with keys after it). A <c>$sort</c> document cannot list a path twice, so the
    /// exact key sorts on this synthetic field instead, which holds <c>$toHashedIndexKey</c> of the path: a non-string value, so the
    /// query's collation cannot fold it, and a total, stable order on distinct strings (not a lexical one).</param>
    private readonly record struct SortKeyPlan(
        string Bucket, string Path, SortDirection Direction, NullsPosition NullsPosition, string? ExactField = null);

    /// <summary>
    /// SEM-6/SEM-3/GRP-4: the request's own keys in order, then a trailing tiebreaker unless the sort
    /// already reaches it, after SEM-6's reduction — resolved to what the pipeline can actually sort on at this stage.
    ///
    /// <para>GRP-4: on a grouped level the tiebreaker is the <b>group column</b>, not the schema's
    /// <see cref="GridSchema.StableKey"/>, which is not in the grouped output at all; the group
    /// column's values are unique across the level's documents by construction. A drill-down leaf
    /// returns documents, so it keeps the stable key unchanged.</para>
    ///
    /// <para>GRP-2, at its narrowed scope: a grouped level's keys order the very buckets
    /// <c>$group</c> produced and so must agree with it (<see cref="SemanticsResolver.GroupingMode.Grouped"/>),
    /// while a drill-down LEAF has no buckets — it orders raw documents by whatever field the user
    /// picked, which need not be a group column at all — so it is
    /// <see cref="SemanticsResolver.GroupingMode.Ungrouped"/> and SEM-1 governs it. On MongoDB that
    /// distinction is what a leaf's suppressed collation records (divergence #3's second shape): the
    /// key WANTS the collation and cannot have it, which is not the same as not wanting it.</para>
    /// </summary>
    private static IReadOnlyList<SortKeyPlan> ResolveSortPlan(
        IReadOnlyList<SortItem>? sort, GroupingPlan? grouping, Context context)
    {
        var groupColumn = grouping?.GroupColumn;

        var keys = SemanticsResolver.AppendStableKeyTiebreaker(
            sort, context.Schema, groupColumn, out var tiebreakerAppended,
            aggregateColumnIds: grouping?.Aggregations.Select(aggregation => aggregation.ColumnId).ToArray());

        var ordering = groupColumn is null
            ? SemanticsResolver.GroupingMode.Ungrouped
            : SemanticsResolver.GroupingMode.Grouped;

        var plan = new List<SortKeyPlan>(keys.Count);

        for (var i = 0; i < keys.Count; i++)
        {
            var key = keys[i];

            var (bucket, path, field) = groupColumn is null
                ? ($"__{key.Field}NullBucket", ResolvePath(key.Field, context), ResolveField(key.Field, context))
                : ResolveGroupedSortTarget(key.Field, groupColumn, grouping!.Aggregations, context);

            // The tiebreaker is always the LAST key when there is one — SEM-6's own rule, enforced by
            // AppendStableKeyTiebreaker above and reported by it, not re-derived here by comparing
            // the last field to the stable key (the minted key and a user key on that field are the
            // identical SortItem).
            var provenance = tiebreakerAppended && i == keys.Count - 1
                ? SemanticsResolver.SortKeyProvenance.AppendedTiebreaker
                : SemanticsResolver.SortKeyProvenance.Request;

            var mode = SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(field, ordering, provenance)
                .Mode;

            RecordCollationNeed(mode, context);

            // MDB-9: recorded, not rendered. A case-sensitive ORDER BY spells nothing on MongoDB the
            // way it spells nothing on Postgres — binary comparison is the default — but "nothing" is
            // only exact while no collation is present, and unlike a comparison this key has no
            // $expr form to move into. Build() is what decides whether the conflict materialised.
            if (mode == SemanticsResolver.CaseSensitivityMode.Sensitive)
            {
                context.Collation.ExactStringSortKeys.Add(key.Field);
            }

            // #2809: the appended exact tiebreaker on a path an earlier key already sorts on cannot be a second `$sort` entry on that path.
            var repeatsAPath = provenance == SemanticsResolver.SortKeyProvenance.AppendedTiebreaker
                && plan.Any(earlier => earlier.Path == path);

            plan.Add(repeatsAPath
                ? new SortKeyPlan(bucket, path, key.Direction, key.NullsPosition, ExactField: $"__{key.Field}ExactKey")
                : new SortKeyPlan(bucket, path, key.Direction, key.NullsPosition));
        }

        return plan;
    }

    /// <summary>
    /// GRP-4: what a grouped level's sort key actually addresses. A <c>$group</c> stage's output
    /// documents contain <c>_id</c> and the accumulator names and nothing else, so a key naming the
    /// raw aggregated field would sort on a field that no longer exists — MongoDB would silently
    /// treat it as missing and order every document equally, which is worse than SQL's outright
    /// rejection and is why this is checked rather than passed through.
    ///
    /// <para>The match is against <see cref="Aggregation.ColumnId"/>, AGG-2's <c>ColumnVO.id</c>
    /// reconstructed: the grid sends the <em>column's</em> id in <c>sortModel</c>, and AGG-2 sets the
    /// alias from that id exactly when it differs from the field. What the resolved key then
    /// <em>addresses</em> is the aggregate's <see cref="Aggregation.OutputName"/>, and the two are
    /// different values whenever there is no alias — see those members' own docs.</para>
    ///
    /// <para>Addressing the output name is a MongoDB-only liberty: after <c>$group</c> the aggregate
    /// IS a real field of the document a later <c>$sort</c> stage reads, not an alias in a
    /// <c>SELECT</c> scope, so GRP-4's "repeat the expression, do not refer back to the output name"
    /// is a SQL rule and explicitly does not reach here.</para>
    ///
    /// <para><b>More than one match is rejected, not picked.</b> #1886's output-name uniqueness does
    /// not imply column-id uniqueness (see <see cref="GroupedSortTarget"/>'s own remarks): two
    /// unaliased functions over one field share a column id while resolving to distinct, legal output
    /// names. The FIRST match here used to win silently — Sql's byte-identical copy of this method had
    /// the same gap, which is why the matching itself is shared now rather than compiler-local.</para>
    ///
    /// <para><b>A single match does not end the check either — the group column is a candidate too.</b>
    /// A request that groups by field X and also aggregates X unaliased (or aliases an aggregate
    /// explicitly back onto X) makes <c><paramref name="sortField"/> == <paramref name="groupColumn"/></c>
    /// true at the same time an aggregation's <see cref="Aggregation.ColumnId"/> matches it. This
    /// method used to return the aggregate's bucket the moment it found one, never asking whether the
    /// group column matched too — Sql's copy had the identical ordering bug, and SEM-6's own
    /// tiebreaker (minted from <paramref name="groupColumn"/> because its values are unique per bucket)
    /// is what reaches this branch on the most ordinary grouped request of all, with no explicit sort
    /// at all. <see cref="GroupedSortTarget.MatchesGroupColumnToo"/> is the shared check.</para>
    /// </summary>
    private static (string Bucket, string Path, FieldConfig Field) ResolveGroupedSortTarget(
        string sortField, string groupColumn, IReadOnlyList<Aggregation> aggregations, Context context)
    {
        var matches = GroupedSortTarget.MatchingByColumnId(sortField, aggregations);

        if (matches.Count > 1)
        {
            throw new MongoCompilationException(
                $"Ambiguous $sort target for a grouped level. {GroupedSortTarget.DescribeAmbiguity(sortField, matches)}");
        }

        if (GroupedSortTarget.MatchesGroupColumnToo(sortField, groupColumn, matches))
        {
            throw new MongoCompilationException(
                $"Ambiguous $sort target for a grouped level. {GroupedSortTarget.DescribeGroupColumnAmbiguity(sortField, matches)}");
        }

        if (matches.Count == 1)
        {
            var output = matches[0].OutputName;
            return ($"__{output}NullBucket", output, ResolveField(matches[0].Field, context));
        }

        if (sortField == groupColumn)
        {
            return (GroupKeyBucket, GroupKeyPath, ResolveField(sortField, context));
        }

        throw new MongoCompilationException(
            $"A grouped query can be ordered only by its group column ('{groupColumn}') or by one of its " +
            $"aggregations, but the request sorts on '{sortField}', which the $group stage does not produce.");
    }

    /// <summary>
    /// SEM-3's null-bucket emulation, in the three stages it always takes.
    ///
    /// <para>MongoDB has no native nulls-first/nulls-last <c>$sort</c> option — BSON has its own
    /// type-ordering rules in which null sorts before numbers, whatever the requested direction — so
    /// null placement is emulated with a synthetic per-key field computed upstream. One
    /// <c>$addFields</c> stage computes every bucket, one <c>$sort</c> lists each
    /// <b>(bucket, field) pair in that order</b> — bucket first, so it resolves null-vs-non-null
    /// placement before the field's own value breaks ties among the non-nulls — and one
    /// <c>$unset</c> removes every bucket again.</para>
    ///
    /// <para><b>The <c>$unset</c> is mandatory, not tidy-up.</b> SEM-3 pins it: a result document
    /// carrying <c>__amountNullBucket</c> alongside the real fields is a shape divergence from the
    /// Postgres and Search results for the identical IR, on top of leaking a compiler-internal
    /// detail. It comes immediately after the <c>$sort</c> that used the buckets and before the
    /// pipeline's <c>$skip</c>/<c>$limit</c> — hence this method emitting all three together rather
    /// than leaving the caller to remember the third.</para>
    ///
    /// <para>The bucket's own sort direction is <c>1</c> for nulls-last and <c>-1</c> for
    /// nulls-first, INDEPENDENT of the field's direction: the bucket is <c>1</c> for null and
    /// <c>0</c> otherwise, so ascending on it puts nulls after everything, whichever way the real key
    /// runs. Every key gets one unconditionally, including SEM-6's appended tiebreaker — SEM-6's
    /// fourth Must-NOT is explicit that "the stable key is probably never null" is never a licence to
    /// omit the mechanism, since <c>grid-schema.schema.json</c> has no way to declare NOT NULL and so
    /// there is no schema state a compiler could check.</para>
    /// </summary>
    private static void AppendSortStages(List<JsonObject> stages, IReadOnlyList<SortKeyPlan> keys)
    {
        var buckets = new JsonObject();
        var sort = new JsonObject();
        var unset = new List<string>(keys.Count);
        var claimed = new Dictionary<string, string>(keys.Count, StringComparer.Ordinal);

        foreach (var key in keys)
        {
            // #2809: the exact tiebreaker of a repeated path sorts on its own synthetic field. The user's key before it already carries
            // the path's null bucket, so nothing is added for nulls: they tie there and the hash of a null is as stable as any other.
            if (key.ExactField is { } exactField)
            {
                if (!claimed.TryAdd(exactField, key.Path))
                {
                    throw new MongoCompilationException(
                        $"The sort key '{key.Path}' needs the exact-tiebreaker field '{exactField}' more than once (MDB-10).");
                }

                buckets[exactField] = new JsonObject { ["$toHashedIndexKey"] = FieldReference(key.Path) };
                sort[exactField] = key.Direction == SortDirection.Asc ? 1 : -1;
                unset.Add(exactField);
                continue;
            }

            // MDB-10: all three stages below are DOCUMENTS, whose repeated key is last-wins. A second
            // key landing on an already-claimed bucket therefore does not merely add nothing — it
            // overwrites the FIRST key's entry in `$sort`, promoting the later key to primary, and it
            // lists the same name twice in `$unset`. Three ways to get there: AGG-2 lets
            // `valueCols[].id` name the reserved `__groupNullBucket`; two different fields could claim
            // one bucket. (A case-insensitive TEXT stable key with keys after it, where SEM-6 keeps the user's key and appends the
            // exact tiebreaker on the same field, no longer reaches here: it takes the ExactField branch above, #2809.) A repeated
            // colId in `sortModel` no longer reaches this point: SEM-6's reduction (Bug #2565) drops
            // a later occurrence of a field first. Renaming one side would make the emitted bucket name
            // depend on the rest of the request, so the request is refused instead — GRP-4's "a sort key
            // the projection does not contain is rejected rather than rendered", one register down.
            if (claimed.TryGetValue(key.Bucket, out var owner))
            {
                throw new MongoCompilationException(owner == key.Path
                    ? $"The sort names '{key.Path}' twice outside SEM-6's exact tiebreaker (MDB-10): a $sort document holds a path once."
                    : $"The sort key '{key.Path}' and the sort key '{owner}' both emulate null placement " +
                      $"through the bucket field '{key.Bucket}', which can only hold one of them. " +
                      $"'{GroupKeyBucket}' is reserved for a grouped level's own _id key (MDB-10); rename the " +
                      "aggregation whose output name is 'group'.");
            }

            claimed.Add(key.Bucket, key.Path);

            buckets[key.Bucket] = new JsonObject
            {
                ["$cond"] = new JsonArray(IsNullExpression(FieldReference(key.Path)), 1, 0)
            };

            sort[key.Bucket] = key.NullsPosition == NullsPosition.Last ? 1 : -1;
            sort[key.Path] = key.Direction == SortDirection.Asc ? 1 : -1;

            unset.Add(key.Bucket);
        }

        stages.Add(Stage("$addFields", buckets));
        stages.Add(Stage("$sort", sort));

        // One bucket unsets by name, several by array — both are valid `$unset` spellings and both
        // validate against mongo-artifact.schema.json.
        stages.Add(Stage("$unset", unset.Count == 1
            ? JsonValue.Create(unset[0])
            : new JsonArray([.. unset.Select(name => (JsonNode?)JsonValue.Create(name))])));
    }

    // ---- paging (AG-3 / EXP-2) ----------------------------------------------------------------------

    /// <summary>
    /// AG-3: <c>$skip</c> takes <c>startRow</c> and <c>$limit</c> the row COUNT, which is
    /// <c>endRow - startRow</c> because <c>endRow</c> is exclusive — a semantic fact about the AG Grid
    /// request contract, and a compiler that passed <c>endRow</c> straight through would emit a
    /// perfectly plausible pipeline returning the wrong documents.
    ///
    /// <para>EXP-2: <c>page: none</c> emits neither stage, so the pipeline ends after the
    /// <c>$unset</c>. Both stages are emitted for a range page even when the offset is zero — the
    /// artifact for the first page pins <c>{"$skip": 0}</c> rather than omitting it, and a
    /// conditional would be a second rule about when the window is expressed.</para>
    /// </summary>
    private static void AppendPagingStages(List<JsonObject> stages, PageSpec page)
    {
        switch (page)
        {
            case NonePage:
                return;

            case RangePage range:
                stages.Add(Stage("$skip", range.StartRow));
                stages.Add(Stage("$limit", range.EndRow - range.StartRow));
                return;

            default:
                throw new MongoCompilationException($"Unknown PageSpec type '{page.GetType().Name}'.");
        }
    }

    // ---- schema resolution --------------------------------------------------------------------------

    private static FieldConfig ResolveField(string field, Context context) =>
        context.Schema.Fields.TryGetValue(field, out var config)
            ? config
            : throw new MongoCompilationException(
                $"Field '{field}' is not declared in the GridSchema (SC-1/SC-2) — a compiler is reached only after " +
                "FieldAllowlistValidator, so this is a caller precondition failure, not a client error.");

    /// <summary>
    /// SC-4: the field's physical document path (<c>"customer.name"</c> for a nested one). A field
    /// with no <see cref="MongoMapping"/> falls back to its own colId, which is the identity mapping
    /// the schema is implicitly declaring by omitting one — the same fallback the SQL compiler makes
    /// for a missing <see cref="SqlMapping"/>.
    /// </summary>
    private static string ResolvePath(string field, Context context) =>
        ResolveField(field, context).Physical?.Mongo?.Path ?? field;

    /// <summary>A field path as an aggregation-expression reference (<c>"$amount"</c>) — the form
    /// <c>$group</c>, <c>$cond</c> and <c>$project</c>'s re-keying use, as opposed to the bare path a
    /// <c>$match</c> or <c>$sort</c> key is.</summary>
    private static JsonNode FieldReference(string path) => JsonValue.Create($"${path}")!;

    /// <summary>
    /// <c>{"$eq": ["$path", null]}</c> — the aggregation-expression null test shared by SEM-3's null
    /// buckets and AGG-1's conditional count. Composed once because the two must agree: both are
    /// asking "is this field null or absent", and in an aggregation expression a missing field
    /// evaluates to <c>$$MISSING</c>, which <c>$eq</c> against <c>null</c> reports as true — which is
    /// what makes a missing value sort and count as null rather than as its own third state.
    /// </summary>
    private static JsonObject IsNullExpression(JsonNode reference) => new()
    {
        ["$eq"] = new JsonArray(reference, null)
    };
}
