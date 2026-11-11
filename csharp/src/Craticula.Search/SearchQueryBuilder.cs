using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Search;

/// <summary>
/// Compiles the IR into an OpenSearch/Elasticsearch <c>_search</c> body — the third backend, and the
/// second one to test <see cref="SemanticsResolver"/>'s claim to be backend-neutral rather than
/// SQL-shaped.
///
/// <para><b>One compiler, both engines, and no target flag (OQ-7 / the #1621 DoD).</b> The DoD asks
/// for divergences to sit "behind a target flag, not a second compiler". <b>There are none in the
/// pinned 7.10-era subset</b>, so this class has no flag and no target parameter — a
/// one-implementation switch is the same smell as the one-implementation dialect seam
/// <c>Craticula.Mongo</c> refused (BM-1). Every construct emitted here predates the OpenSearch fork
/// (which forked Elasticsearch 7.10.2) and is spelled identically on both sides of it: <c>bool</c>'s
/// four clause arrays, <c>term</c>/<c>terms</c>/<c>range</c>/<c>wildcard</c>/<c>match</c>/
/// <c>exists</c>, <c>sort</c>'s <c>missing</c>, <c>from</c>/<c>size</c>, and the <c>composite</c> and
/// <c>terms</c> aggregations with <c>missing_bucket</c>/<c>include</c>/<c>order</c>. The one parameter
/// worth checking is
/// <c>case_insensitive</c> (SEM-1's mechanism on this backend), which Elasticsearch added in 7.10 —
/// the very release OpenSearch forked from — so OpenSearch 1.0 inherited it and every supported
/// version of both engines has it. A flag would therefore have exactly one setting, which is the
/// definition of a flag that should not exist. If a future construct genuinely does diverge, the seam
/// to add is the one this project already uses for that shape of problem
/// (<c>Craticula.Sql.ISqlDialect</c>) — not a boolean threaded through this class.</para>
///
/// <para><b>Semantics are never re-derived here.</b> Case-sensitivity mechanism and mode, the
/// <c>blank</c> condition, null-inclusivity, the SEM-6 tiebreaker and GRP-2's bucket-identity
/// exactness all come from <see cref="SemanticsResolver"/>; the drill-down comes from
/// <see cref="DrillDownFilter"/> and the search prefix from <see cref="SetValuesFilter"/>. What IS
/// this compiler's own responsibility is the request <em>shape</em> those decisions render into —
/// which query type, which sub-field, and the DSL's two structurally different request forms (hits
/// with <c>sort</c>/<c>from</c>/<c>size</c>, or buckets with <c>size: 0</c> and <c>aggs</c>).</para>
///
/// <para><b>The rendering rules are pinned in <c>spec/semantics.md</c>'s
/// "Addendum — canonical OpenSearch/Elasticsearch rendering (OSE-0..OSE-14)"</b>, the exact parallel
/// of the SQL (SQL-0..SQL-8) and MongoDB (MDB-1..MDB-12) addenda, and for the same reason: the
/// hand-authored fixture suite spelled several of these constructs more than one way from identical
/// inputs, and no single compiler can satisfy contradictory oracles.</para>
/// </summary>
public static class SearchQueryBuilder
{
    /// <summary>
    /// Compiles <paramref name="request"/> into its search body. Re-runs the IR's own structural
    /// validators first — the same defense in depth every other public entry point in this codebase
    /// performs, since a caller can reach this method with a hand-built tree that never went through
    /// <see cref="GridFilterPipeline"/>.
    /// </summary>
    /// <exception cref="SearchCompilationException">A structurally valid shape this compiler has no
    /// defined rendering for — a field the <see cref="GridSchema"/> does not declare, a value whose
    /// variant disagrees with that field's declared type, a case-insensitive ordering key on a field
    /// declaring no <c>search.normalizedSubField</c> (SEM-1), a <c>searchMode: analyzed</c>
    /// <c>contains</c> on a field declared case-<b>sensitive</b> (SEM-1), or a grouped level asked for
    /// an ordering or a row window a <c>composite</c> aggregation cannot express
    /// (OSE-11(c)/(d)).</exception>
    public static SearchQuery Build(SearchQueryRequest request)
    {
        var query = BuildBody(request);

        // TL-3: an export (EXP-2's unpaginated page) never carries the limit.
        return request.Page is NonePage ? query : query with { TimeoutMs = request.MaxQueryTimeMs };
    }

    private static SearchQuery BuildBody(SearchQueryRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        FilterNodeValidator.Validate(request.Filter);
        PageSpecValidator.Validate(request.Page);
        GroupSpecValidator.Validate(request.Group);
        AggregationValidator.Validate(request.Aggregations);

        var context = new Context(request.Schema);
        var grouping = GroupingPlan.Resolve(request.Group, request.Aggregations);

        // OSE-3: a grouping request's clauses come from two provenances that must be conjoined
        // (GRP-5's drill-down and the user's own filter), and `bool.filter` is this DSL's conjunction
        // container — and its non-scoring one, which is what an aggregation request wants. An
        // ordinary row query has one source and renders as the tree itself.
        var query = RenderQuery(request.Filter, grouping?.DrillDown, protocol: grouping is not null, context);

        if (grouping is { GroupColumn: { } groupColumn })
        {
            return new SearchQuery
            {
                Index = request.Schema.Source,
                Query = query,
                // A grouped level wants buckets and no hits at all. `size: 0` is what says so, and it
                // is unrelated to the composite's own `size`, which is the bucket window.
                Size = 0,
                Aggs = RenderGroupedAggregations(groupColumn, grouping.Aggregations, request, context)
            };
        }

        // A drill-down LEAF reaches here too, and keeps SEM-6's stableKey — GRP-4's last bullet: it
        // projects rows, so the group column has no unique-by-construction role to play.
        var sort = RenderSort(ResolveSortPlan(request.Sort, context));
        var (from, size) = ResolveWindow(request.Page);

        return new SearchQuery
        {
            Index = request.Schema.Source,
            // OSE-3: a hit-returning request always carries an explicit query, so `match_all` is the
            // "no predicate" spelling rather than an omitted member.
            Query = query ?? new JsonObject { ["match_all"] = new JsonObject() },
            Sort = sort,
            From = from,
            Size = size
        };
    }

    /// <summary>
    /// GRP-6/BM-3: compiles the set-filter distinct-values request — <c>size: 0</c> plus a
    /// <c>terms</c> aggregation over the target column.
    ///
    /// <para>A separate entry point rather than a mode of <see cref="Build"/>, mirroring
    /// <c>Craticula.Sql.SqlQueryBuilder.BuildSetValues</c> and
    /// <c>Craticula.Mongo.MongoPipelineBuilder.BuildSetValues</c>. Four things about it are GRP-6's,
    /// not this compiler's invention:</para>
    /// <list type="bullet">
    /// <item><description><b>It is a bucket query</b> (GRP-6(a)). A <c>terms</c> aggregation computes
    /// a distinct set exactly as a <c>GROUP BY</c> does, so its key is exact — no
    /// <c>case_insensitive</c>, on a case-insensitive string too. (On this backend that costs nothing
    /// to arrange: an aggregation has no such parameter in the first place.) The values are handed
    /// straight back to the grid to be sent again as an <c>in</c> value or a <c>groupKey</c>, which
    /// GRP-2 then matches exactly.</description></item>
    /// <item><description><b>AGG-4's ordering is explicit</b>: <c>"order": {"_key": "asc"}</c>, never
    /// the engine's own doc-count-descending default, which would put the values in a different order
    /// from Postgres's <c>ORDER BY</c> and Mongo's <c>$sort</c> on the identical request.</description></item>
    /// <item><description><b>No <c>from</c>, and no SEM-6 tiebreaker</b> (GRP-6(e)). The cap is a
    /// ceiling, not a window.</description></item>
    /// <item><description><b>The cap is applied, never enforced</b> (GRP-6(d)). It arrives already
    /// clamped from <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>; this method only
    /// re-checks it is positive.</description></item>
    /// </list>
    /// </summary>
    /// <exception cref="SearchCompilationException">A field the <see cref="GridSchema"/> does not
    /// declare, a non-positive <see cref="SearchSetValuesRequest.RowLimit"/>, a
    /// <see cref="SearchSetValuesRequest.SearchPrefix"/> whose predicate is absent from
    /// <see cref="SearchSetValuesRequest.Filter"/>, or a target column not declared
    /// <c>string</c>.</exception>
    public static SearchQuery BuildSetValues(SearchSetValuesRequest request) =>
        BuildSetValuesBody(request) with { TimeoutMs = request.MaxQueryTimeMs };

    private static SearchQuery BuildSetValuesBody(SearchSetValuesRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        FilterNodeValidator.Validate(request.Filter);

        // Defense in depth against a caller that skipped ResourceLimitsValidator. A `terms`
        // aggregation with `size: 0` is rejected by both engines, and a negative one is nonsense, so
        // refusing here keeps the failure legible instead of surfacing as a 400 at execution time.
        if (request.RowLimit <= 0)
        {
            throw new SearchCompilationException(
                $"A set-values row limit must be positive, got {request.RowLimit} — resolve it through " +
                "ResourceLimitsValidator.ResolveSetValuesLimit, which clamps the client's request to the host's " +
                "configured maximum and never yields a non-positive answer.");
        }

        var context = new Context(request.Schema);
        var target = Resolve(request.ColId, context);

        // GRP-6(c) is rejected upstream for a non-text column (GridFilterPipeline.RequireTextTarget),
        // but the DISTINCT key itself is only ever a string here for a different reason: `include` is
        // a term-level regex and the `.keyword` sub-field selection below assumes text. Checked
        // rather than assumed, since a host may build the IR directly.
        if (target.Config.Type != FieldType.String)
        {
            throw new SearchCompilationException(
                $"Set-filter values are resolved for field '{request.ColId}', declared '{target.Config.Type}'. " +
                "A terms aggregation's buckets are handed back to the grid as filter values and its `include` " +
                "parameter is a term-level regex, so this path is defined for a 'string' column only.");
        }

        var terms = new JsonObject
        {
            ["field"] = target.Keyword,
            ["size"] = request.RowLimit
        };

        if (RenderSearchPrefixInclude(request) is { } include)
        {
            terms["include"] = include;
        }

        // AGG-4, spelled explicitly and unconditionally.
        terms["order"] = new JsonObject { ["_key"] = "asc" };

        return new SearchQuery
        {
            Index = request.Schema.Source,
            Query = RenderQuery(StripSearchPrefixPredicate(request), drillDown: null, protocol: true, context),
            Size = 0,
            Aggs = new JsonObject
            {
                [RequireAggregationName(request.ColId, "the distinct-values")] = new JsonObject { ["terms"] = terms }
            }
        };
    }

    // ---- shared state -----------------------------------------------------------------------------

    /// <summary>
    /// The per-compilation state threaded through the tree walk.
    ///
    /// <para><paramref name="IsGroupKeyMatch"/> carries <em>provenance</em>, not shape, exactly as the
    /// SQL and Mongo builders' does: the drill-down predicates and the user's own filter are both
    /// ordinary IR (GRP-5) and indistinguishable by inspection, yet they resolve case sensitivity by
    /// different rules. It is set once, by <see cref="RenderQuery"/>, on the context the drill-down
    /// subtree is walked under — never re-derived from a node, and never recovered by reference
    /// identity, which GRP-5 names as a trap that any later node-rebuilding change would spring
    /// silently.</para>
    ///
    /// <para>Unlike <c>Craticula.Mongo</c>'s, this record needs no collation sink: SEM-1's mechanism
    /// here is a <em>per-clause</em> parameter, so nothing about one clause's rendering depends on
    /// what the rest of the request contains. That absence is the whole of GRP-2's "its per-clause
    /// granularity means it can satisfy the scope carve-outs exactly", and it is why MongoDB's
    /// accepted divergence #3 has no counterpart on this backend.</para>
    /// </summary>
    private readonly record struct Context(GridSchema Schema, bool IsGroupKeyMatch = false);

    /// <summary>
    /// SC-4/SC-3: the three field names one logical column can have on this backend, resolved once.
    ///
    /// <para><paramref name="Raw"/> is <c>search.field</c> — the analyzed/base field, which is what
    /// <c>exists</c>, a numeric/date comparison, an aggregation metric and a <c>searchMode: analyzed</c>
    /// <c>match</c> all address. <paramref name="Keyword"/> is <c>search.keywordSubField</c>, the
    /// exact-match sub-field SEM-1 names for <c>term</c>/<c>terms</c>/<c>wildcard</c>, falling back to
    /// <paramref name="Raw"/> when a schema declares none (the identity the schema is implicitly
    /// declaring by omitting it, the same fallback the other two compilers make for a missing
    /// mapping). <paramref name="Normalized"/> is <c>search.normalizedSubField</c>, SEM-1's
    /// index-time-folded sub-field for case-insensitive ORDERING, and it has no fallback at all — see
    /// <see cref="OrderingTarget"/>.</para>
    /// </summary>
    private readonly record struct FieldTarget(FieldConfig Config, string Raw, string Keyword, string? Normalized);

    private static FieldTarget Resolve(string field, Context context)
    {
        var config = context.Schema.Fields.TryGetValue(field, out var declared)
            ? declared
            : throw new SearchCompilationException(
                $"Field '{field}' is not declared in the GridSchema (SC-1/SC-2) — a compiler is reached only after " +
                "FieldAllowlistValidator, so this is a caller precondition failure, not a client error.");

        var mapping = config.Physical?.Search;
        var raw = mapping?.Field ?? field;

        return new FieldTarget(config, raw, mapping?.KeywordSubField ?? raw, mapping?.NormalizedSubField);
    }

    // ---- the query tree ---------------------------------------------------------------------------

    /// <summary>
    /// OSE-3: the <c>query</c> member, in the two forms the suite pins.
    ///
    /// <para>An ordinary row query (<paramref name="protocol"/> <see langword="false"/>) renders its
    /// filter tree directly, so a top-level <c>and</c> is a <c>bool.must</c> like any other. A
    /// grouping or distinct-values request wraps everything in <c>bool.filter</c>: its clauses come
    /// from two provenances that have to be conjoined (GRP-5's drill-down leads, the user's own filter
    /// follows — GRP-5 pins that order), and <c>filter</c> is both this DSL's conjunction container
    /// and its non-scoring context, which is what a request asking for buckets rather than ranked hits
    /// wants. A top-level <c>and</c> on either side contributes its children directly, because the
    /// array already IS the conjunction — <c>spec/fixtures/ag-grid-majors/004</c> pins two range
    /// clauses side by side and <c>group-aggregation/003</c>/<c>004</c> pin the drill-down's two and
    /// three. That is not SQL-2's "every composite wraps" being readmitted through the back door: the
    /// wrap is still there, spelled as the <c>filter</c> array itself.</para>
    /// </summary>
    private static JsonObject? RenderQuery(FilterNode? filter, FilterNode? drillDown, bool protocol, Context context)
    {
        if (!protocol)
        {
            return filter is null ? null : RenderNode(filter, context);
        }

        var clauses = new JsonArray();

        if (drillDown is not null)
        {
            AppendConjuncts(clauses, drillDown, context with { IsGroupKeyMatch = true });
        }

        if (filter is not null)
        {
            AppendConjuncts(clauses, filter, context);
        }

        return clauses.Count == 0
            ? null
            : new JsonObject { ["bool"] = new JsonObject { ["filter"] = clauses } };
    }

    private static void AppendConjuncts(JsonArray clauses, FilterNode node, Context context)
    {
        if (node is AndNode and)
        {
            foreach (var child in and.Nodes)
            {
                clauses.Add(RenderNode(child, context));
            }

            return;
        }

        clauses.Add(RenderNode(node, context));
    }

    private static JsonObject RenderNode(FilterNode node, Context context) => node switch
    {
        AndNode and => new JsonObject { ["bool"] = new JsonObject { ["must"] = RenderChildren(and, context) } },
        OrNode or => Should(RenderChildren(or, context)),
        NotNode not => RenderNot(not, context),
        ComparisonNode comparison => RenderComparison(comparison, context),
        _ => throw new SearchCompilationException($"Unknown FilterNode type '{node.GetType().Name}'.")
    };

    /// <summary>
    /// AR-5's composites. A single-child composite is NOT collapsed — <c>{"bool": {"must": [x]}}</c>,
    /// mirroring SQL-2's <c>(x)</c> and MDB-2's <c>{"$and": [x]}</c> — because the tree's own depth is
    /// what <c>spec/fixtures/filter-tree/011</c>-<c>013</c> pin against SEC-3's budget, and collapsing
    /// it would make a boundary fixture indistinguishable from a shallower one.
    /// </summary>
    private static JsonArray RenderChildren(CompositeFilterNode composite, Context context)
    {
        var children = new JsonArray();
        foreach (var child in composite.Nodes)
        {
            children.Add(RenderNode(child, context));
        }

        return children;
    }

    /// <summary>
    /// OSE-2: a disjunction is <c>should</c> plus an <b>explicit</b> <c>minimum_should_match: 1</c>.
    /// The parameter is not decoration: a <c>bool</c> that also carries <c>must</c> or <c>filter</c>
    /// defaults <c>minimum_should_match</c> to <b>0</b>, so its <c>should</c> clauses become pure
    /// scoring hints that constrain nothing. Every <c>or</c> this compiler emits is a real
    /// constraint, and spelling the parameter unconditionally means the same subtree renders the same
    /// way wherever it lands in the tree — SQL-2's "one rule per construct, applied always".
    /// </summary>
    private static JsonObject Should(JsonArray clauses) => new()
    {
        ["bool"] = new JsonObject
        {
            ["should"] = clauses,
            ["minimum_should_match"] = 1
        }
    };

    /// <summary>
    /// SEM-2/OSE-2/OSE-4: a tree-level <c>NOT</c>, at every nesting depth, is <c>must_not</c> with the
    /// child in an ARRAY, plus the null fan-out of SQL-2's third bullet: one <c>exists</c> complement
    /// on the RAW field per distinct field referenced in the child subtree, in first-appearance
    /// order, as sibling <c>should</c> clauses. A bare <c>must_not</c> matches a document with a
    /// missing field only when the child cannot match it, which <c>neq</c>, <c>blank</c>, an inner
    /// <c>not</c> or an <c>or</c> over two fields can.
    ///
    /// <para>The array is what distinguishes the inner negation, in the artifact, from the negations
    /// this compiler composes itself (<see cref="NullInclusive"/>'s inner clause, <c>notBlank</c>, and
    /// the <c>exists</c> complement), all of which take a single clause object — MDB-2/MDB-4's
    /// <c>$nor</c>-versus-<c>$not</c> distinction on a DSL that has only one negation keyword.</para>
    /// </summary>
    private static JsonObject RenderNot(NotNode not, Context context)
    {
        var clauses = new JsonArray
        {
            new JsonObject
            {
                ["bool"] = new JsonObject { ["must_not"] = new JsonArray(RenderNode(not.Node, context)) }
            }
        };
        foreach (var field in FilterNodeFields.DistinctInOrder(not.Node))
        {
            clauses.Add(MustNot(Exists(Resolve(field, context).Raw)));
        }

        return Should(clauses);
    }

    /// <summary>A negation this compiler composed itself, spelled with a single clause rather than an
    /// array — see <see cref="RenderNot"/> for why the two differ.</summary>
    private static JsonObject MustNot(JsonObject clause) => new()
    {
        ["bool"] = new JsonObject { ["must_not"] = clause }
    };

    private static JsonObject Exists(string rawField) => new()
    {
        ["exists"] = new JsonObject { ["field"] = rawField }
    };

    private static JsonObject RenderComparison(ComparisonNode node, Context context)
    {
        var target = Resolve(node.Field, context);

        return node.Op switch
        {
            ComparisonOperator.Blank => RenderBlank(target),
            ComparisonOperator.NotBlank => MustNot(RenderBlank(target)),

            // AR-6's unary boolean shorthand carries no value of its own, so the compiler mints one
            // and routes it through the ordinary equality path rather than spelling a second form.
            ComparisonOperator.True =>
                RenderTerm(target, node.Field, ComparisonOperator.Eq, new BooleanValue { Value = true }, context),
            ComparisonOperator.False =>
                RenderTerm(target, node.Field, ComparisonOperator.Eq, new BooleanValue { Value = false }, context),

            // GRP-7: an equality against a nullValue is the null test. A `term` with a null value is a 400 on the engine; the null group
            // of a grouped level is expanded with this.
            ComparisonOperator.Eq when node.Value is NullValue => MustNot(Exists(target.Raw)),

            ComparisonOperator.Eq or ComparisonOperator.Neq =>
                NullInclusive(RenderTerm(target, node.Field, node.Op, RequireValue(node), context), node.Op, target),

            ComparisonOperator.Gt or ComparisonOperator.Gte
                or ComparisonOperator.Lt or ComparisonOperator.Lte =>
                RenderRange(target, node, context),

            ComparisonOperator.Contains or ComparisonOperator.NotContains
                or ComparisonOperator.StartsWith or ComparisonOperator.EndsWith =>
                NullInclusive(RenderSubstring(target, node, context), node.Op, target),

            // SEM-8: empty list = constant. `match_none` / `match_all`; the constant already covers NULL rows.
            ComparisonOperator.In or ComparisonOperator.NotIn when node.Values is { Count: 0 } =>
                new JsonObject
                {
                    [node.Op == ComparisonOperator.NotIn ? "match_all" : "match_none"] = new JsonObject()
                },

            ComparisonOperator.In or ComparisonOperator.NotIn =>
                NullInclusive(RenderSet(target, node, context), node.Op, target),

            ComparisonOperator.InRange => RenderRange(target, node, context),

            _ => throw new SearchCompilationException($"Unknown comparison operator '{node.Op}'.")
        };
    }

    /// <summary>
    /// SEM-2: <c>neq</c>/<c>notContains</c>/<c>notIn</c> must match null-valued and missing documents.
    /// The AFFIRMATIVE form is compiled first and then negated — SEM-2's own construction, so the two
    /// directions cannot drift — and the "field is absent" arm is a second <c>should</c> clause.
    ///
    /// <para>SEM-2's own ES worked example spells both clauses and says why: the first alone
    /// <em>happens</em> to cover the missing-field case for a <c>term</c> query, because a
    /// <c>must_not</c> around a query that cannot match a missing document is true for that document
    /// — but that is a property of <c>term</c> specifically and is not guaranteed for every query type
    /// an operator might compile to. The compiler does not lean on it silently; the second clause is
    /// explicit, on every operator, unconditionally.</para>
    ///
    /// <para>The <c>exists</c> clause names the <b>raw</b> field, never a sub-field: a
    /// <c>.keyword</c> sub-field's own doc-values existence is an indexing detail (<c>ignore_above</c>
    /// can drop a long value from it while the base field still holds one), so asking about the base
    /// field is the only form that means "this document has no value for this column".</para>
    /// </summary>
    private static JsonObject NullInclusive(JsonObject affirmative, ComparisonOperator op, FieldTarget target) =>
        SemanticsResolver.IsNullInclusive(op)
            ? Should([MustNot(affirmative), MustNot(Exists(target.Raw))])
            : affirmative;

    /// <summary>
    /// SEM-2/OSE-4: <c>blank</c> is "absent or the empty string" for a text field and "absent" for
    /// every other type. <c>notBlank</c> is this exact clause under a <c>must_not</c>
    /// (<see cref="RenderComparison"/>), never a separately-derived condition — SEM-2's third
    /// Must-NOT, satisfied structurally rather than by two renderings that happen to agree.
    ///
    /// <para>There is no counterpart here to SQL-7's second question ("does this engine treat
    /// <c>''</c> as NULL?"): both engines store the empty string as an ordinary term distinct from a
    /// missing field, so the field-type half is the whole answer — which is exactly what
    /// <see cref="SemanticsResolver.ResolveBlankCondition"/>'s own doc anticipates when it says a
    /// Mongo or Search compiler "will have its own second half or none".</para>
    ///
    /// <para><b>The empty-string term carries no <c>case_insensitive</c>, whatever the field
    /// declares.</b> That is not the conditional spelling OSE-1 forbids: the parameter governs how a
    /// CLIENT's value is compared, and this value is not one — it is the sentinel SEM-2's own
    /// definition of <c>blank</c> mints. An empty string has no case to fold, so the parameter would
    /// be provably inert, and GRP-2's precedent is that a compiler-minted key spells no mechanism.
    /// <c>spec/fixtures/operators/029</c>/<c>030</c> and <c>dialect-parity/019</c> pin it.</para>
    /// </summary>
    private static JsonObject RenderBlank(FieldTarget target) =>
        SemanticsResolver.ResolveBlankCondition(target.Config.Type) switch
        {
            SemanticsResolver.BlankCondition.NullOrEmptyString => Should(
            [
                MustNot(Exists(target.Raw)),
                new JsonObject
                {
                    ["term"] = new JsonObject
                    {
                        [target.Keyword] = new JsonObject { ["value"] = "" }
                    }
                }
            ]),
            SemanticsResolver.BlankCondition.NullOnly => MustNot(Exists(target.Raw)),
            var condition => throw new SearchCompilationException($"Unknown blank condition '{condition}'.")
        };

    /// <summary>
    /// SEM-1: the resolver decides how a comparison treats case and, when it folds it, by which
    /// mechanism; this compiler only realizes that decision. <paramref name="family"/> is the
    /// mechanism the CALLER is about to render, and a mismatch is a compiler bug rather than a client
    /// error, so it fails loudly instead of degrading to "no mechanism" — which would be a
    /// plausible-looking artifact that folds case in the wrong place.
    ///
    /// <para>A predicate inside the synthesised drill-down is not a filter at all: it is a group-key
    /// MATCH, and GRP-2 requires it to agree with the aggregation that produced the bucket label being
    /// expanded. It therefore resolves through
    /// <see cref="SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity"/>, from the provenance
    /// on <see cref="Context.IsGroupKeyMatch"/> — which on this backend simply means the
    /// <c>case_insensitive</c> parameter is dropped from that <c>term</c>, leaving the exact form
    /// GRP-2 names by hand and <c>dialect-parity/014</c> already used.</para>
    /// </summary>
    private static SemanticsResolver.CaseSensitivityMode ResolveCaseSensitivity(
        FieldTarget target, string fieldName, ComparisonOperator op,
        SemanticsResolver.CaseSensitivityMechanism family, Context context)
    {
        if (context.IsGroupKeyMatch)
        {
            return SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(target.Config, SemanticsResolver.GroupingMode.Grouped)
                .Mode;
        }

        var decision = SemanticsResolver.ResolveCaseSensitivity(target.Config, op);

        if (decision.Mode == SemanticsResolver.CaseSensitivityMode.Insensitive && decision.Mechanism != family)
        {
            throw new SearchCompilationException(
                $"Operator '{op}' on field '{fieldName}' resolves to the '{decision.Mechanism}' case-insensitivity " +
                $"mechanism, but is being rendered through the '{family}' family — SEM-1 requires one mechanism " +
                "per field across every context.");
        }

        return decision.Mode;
    }

    /// <summary>
    /// OSE-1: a <c>term</c> query, in the one form a <c>string</c> field ever takes and the one form
    /// every other type ever takes.
    ///
    /// <para><b>A string spells the long form</b> — <c>{"field.keyword": {"value": v}}</c>, with
    /// <c>"case_insensitive": true</c> beside it when SEM-1 folds case. The spelling is decided by the
    /// field's declared TYPE and not by whether the parameter happens to be present, which is what
    /// stops one field from having two spellings depending on its <c>caseSensitivity</c>: GRP-2 pins
    /// the parameterless string form by hand (<c>{"term": {"&lt;field&gt;.keyword": {"value":
    /// "EMEA"}}}</c> for a drill-down) and <c>dialect-parity/014</c> uses the identical shape for the
    /// case-sensitive opt-in.</para>
    ///
    /// <para><b>Every other type spells the short form</b> — <c>{"age": 30}</c>. SEM-1 governs
    /// <c>stringValue</c> comparisons only, so no non-text term can ever acquire the parameter the
    /// long form exists to carry, and the suite spells all thirteen of them plain.</para>
    /// </summary>
    private static JsonObject RenderTerm(
        FieldTarget target, string fieldName, ComparisonOperator op, TypedValue value, Context context)
    {
        var mode = ResolveCaseSensitivity(
            target, fieldName, op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var encoded = SearchJson.Encode(value, target.Config, fieldName);

        if (target.Config.Type != FieldType.String)
        {
            return new JsonObject { ["term"] = new JsonObject { [target.Raw] = encoded } };
        }

        var body = new JsonObject { ["value"] = encoded };

        if (mode == SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            body["case_insensitive"] = true;
        }

        return new JsonObject { ["term"] = new JsonObject { [target.Keyword] = body } };
    }

    /// <summary>
    /// OSE-7: set membership is a <c>terms</c> query — except on a case-INSENSITIVE string, where it
    /// is a <c>should</c> of <c>term</c> queries instead.
    ///
    /// <para>That is not a stylistic split. <c>terms</c> has <b>no <c>case_insensitive</c>
    /// parameter</b> in the pinned 7.10-era subset (the parameter exists on <c>term</c>,
    /// <c>prefix</c>, <c>wildcard</c> and <c>regexp</c> only), so it cannot realize SEM-1's mechanism
    /// at all; emitting it anyway would silently make <c>in</c> case-sensitive on a field the schema
    /// declared insensitive, which is SEM-1's second Must-NOT. The disjunction of single-term queries
    /// is the same set membership with the parameter available on each member.
    /// <c>spec/fixtures/operators/035</c> and <c>dialect-parity/016</c> pin the disjunction;
    /// <c>operators/037</c> and <c>dialect-parity/018</c> (a <c>sensitive</c> column) pin the compact
    /// form.</para>
    /// </summary>
    private static JsonObject RenderSet(FieldTarget target, ComparisonNode node, Context context)
    {
        var mode = ResolveCaseSensitivity(
            target, node.Field, node.Op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var values = node.Values
            ?? throw new SearchCompilationException($"Operator '{node.Op}' on field '{node.Field}' requires 'values'.");

        var isText = target.Config.Type == FieldType.String;

        if (isText && mode == SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            var members = new JsonArray();
            foreach (var value in values)
            {
                members.Add(new JsonObject
                {
                    ["term"] = new JsonObject
                    {
                        [target.Keyword] = new JsonObject
                        {
                            ["value"] = SearchJson.Encode(value, target.Config, node.Field),
                            ["case_insensitive"] = true
                        }
                    }
                });
            }

            return Should(members);
        }

        var encoded = new JsonArray();
        foreach (var value in values)
        {
            encoded.Add(SearchJson.Encode(value, target.Config, node.Field));
        }

        return new JsonObject
        {
            ["terms"] = new JsonObject { [isText ? target.Keyword : target.Raw] = encoded }
        };
    }

    /// <summary>
    /// SEM-4/OSE-8: the ordering comparisons and <c>inRange</c>, both of which are one <c>range</c>
    /// query carrying its bounds — <c>inRange</c> included, because it is a single
    /// <c>rangeComparisonNode</c> (one IR leaf, not an <c>and</c> of two), the same argument MDB-6
    /// makes for MongoDB's single field document. An AG Grid within-column AND of two conditions IS
    /// two leaves and does render as two clauses (<c>ag-grid-majors/002</c>).
    ///
    /// <para>Each bound is spelled from its OWN explicit inclusivity flag, read from the node —
    /// never SQL <c>BETWEEN</c>'s familiar inclusive-inclusive assumption (SEM-4's fourth
    /// Must-NOT).</para>
    ///
    /// <para>The <c>format</c> parameter is emitted for a date/datetime field and for nothing else
    /// (<see cref="SearchJson.FormatFor"/>). No <c>time_zone</c> is ever emitted: SEM-4's second
    /// Must-NOT names that parameter explicitly, and it would be inert anyway — <c>time_zone</c>
    /// only shifts <em>unqualified</em> date-math strings, and every boundary reaching here is
    /// already an absolute instant or a calendar date.</para>
    /// </summary>
    private static JsonObject RenderRange(FieldTarget target, ComparisonNode node, Context context)
    {
        var body = new JsonObject();
        ComparisonOperator mechanismOp;

        if (node.Op == ComparisonOperator.InRange)
        {
            if (node.From is null || node.To is null || node.FromInclusive is null || node.ToInclusive is null)
            {
                throw new SearchCompilationException(
                    $"Operator 'inRange' on field '{node.Field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.");
            }

            var lower = node.FromInclusive.Value ? ComparisonOperator.Gte : ComparisonOperator.Gt;
            var upper = node.ToInclusive.Value ? ComparisonOperator.Lte : ComparisonOperator.Lt;

            body[BoundName(lower)] = SearchJson.Encode(node.From, target.Config, node.Field);
            body[BoundName(upper)] = SearchJson.Encode(node.To, target.Config, node.Field);

            // SEM-1 assigns `inRange` no mechanism of its own (it is not in $defs/binaryOperator), so
            // the field's mechanism is resolved through the bound's own operator — the same
            // substitution Craticula.Mongo makes, and for the same reason: a case-insensitive string
            // range still has to reach the ordering sub-field below.
            mechanismOp = lower;
        }
        else
        {
            body[BoundName(node.Op)] = SearchJson.Encode(RequireValue(node), target.Config, node.Field);
            mechanismOp = node.Op;
        }

        var mode = ResolveCaseSensitivity(
            target, node.Field, mechanismOp, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        if (SearchJson.FormatFor(target.Config.Type) is { } format)
        {
            body["format"] = format;
        }

        return new JsonObject
        {
            ["range"] = new JsonObject { [OrderingTarget(target, mode, node.Field, "range query")] = body }
        };
    }

    private static string BoundName(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Gt => "gt",
        ComparisonOperator.Gte => "gte",
        ComparisonOperator.Lt => "lt",
        ComparisonOperator.Lte => "lte",
        _ => throw new SearchCompilationException($"Operator '{op}' is not a range bound.")
    };

    /// <summary>
    /// SEM-1's "one real gap", which is this backend's alone: <c>range</c> has no
    /// <c>case_insensitive</c> parameter in the pinned subset and there is no query-time equivalent,
    /// so a case-insensitive ordering comparison or sort key must target a schema-declared,
    /// index-time-folded <c>search.normalizedSubField</c> instead.
    ///
    /// <para><b>Its absence is a compiler error, not a silent fallback.</b> SEM-1 states the
    /// requirement as a MUST on the schema ("A field that needs case-insensitive ordering on
    /// ES/OpenSearch MUST declare <c>search.normalizedSubField</c>"), and the alternatives are both
    /// wrong in the way this project refuses: falling back to <c>.keyword</c> orders <c>"Zebra"</c>
    /// before <c>"apple"</c> on a field the schema declared case-insensitive — wrong rows in the
    /// wrong order, invisible to the artifact tier — and falling back to the analyzed base field is
    /// not sortable at all. SQL-7(b)'s and MDB-9's register: a plausible query returning the wrong
    /// answer is worse than a refusal naming the declaration that is missing.</para>
    ///
    /// <para>A case-SENSITIVE or non-text key needs no folding and takes the exact-comparison
    /// sub-field / the raw field, which is the same target the <c>term</c> family uses — SEM-1's
    /// "the same class of mechanism in every context on that field".</para>
    /// </summary>
    private static string OrderingTarget(
        FieldTarget target, SemanticsResolver.CaseSensitivityMode mode, string fieldName, string construct)
    {
        if (target.Config.Type != FieldType.String)
        {
            return target.Raw;
        }

        if (mode != SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            return target.Keyword;
        }

        return target.Normalized
            ?? throw new SearchCompilationException(
                $"Field '{fieldName}' is a case-insensitive string and this {construct} orders by it, but the schema " +
                "declares no 'physical.search.normalizedSubField'. A range query has no `case_insensitive` parameter " +
                "in the pinned 7.10-era subset and there is no query-time equivalent, so case-insensitive ordering is " +
                "an index-time cost this field has not paid (SEM-1, SC-3). Declare the normalizer sub-field, or " +
                "declare the field caseSensitivity: \"sensitive\".");
    }

    /// <summary>
    /// SEM-7: the substring family, pinned to SUBSTRING semantics — a <c>wildcard</c> query against
    /// the exact-match sub-field, never a tokenized <c>match</c>. <c>contains: "art"</c> finds
    /// <c>"Smart Watch"</c> here exactly as SQL's <c>LIKE '%art%'</c> and Mongo's <c>$regex</c> do,
    /// which the tokenized form would not (its analyzer produces the whole tokens <c>smart</c> and
    /// <c>watch</c>, neither of which is <c>art</c>) — the single most consequential trap on this
    /// backend, and the one SEM-7 exists for.
    ///
    /// <para><b><c>searchMode: analyzed</c> is the explicit per-field opt-in</b> (SC-3), and it is
    /// scoped to <c>contains</c>/<c>notContains</c>, which is what SEM-7 names. It compiles to
    /// <c>{"match": {field: {"query": v, "operator": "and"}}}</c> against the ANALYZED base field —
    /// <c>operator: "and"</c> because a relevance-style default of <c>or</c> would match a document
    /// sharing any single token, which is not "contains" under any reading. <c>startsWith</c> and
    /// <c>endsWith</c> keep the wildcard form on such a field: an anchored affix has no tokenized
    /// meaning, and SEM-7's opt-in is described as an escape hatch for "relevance-style full-text
    /// matching", which those two never are.</para>
    ///
    /// <para><b>The <c>analyzed</c> opt-in on a case-SENSITIVE field is refused</b> (OSE-6). A
    /// <c>match</c> has no <c>case_insensitive</c> parameter and no case control of any kind: it is
    /// resolved entirely by the field's own analyzer, and every stock text analyzer in both engines
    /// lowercases. So the combination would emit a query that folds case on a field the schema
    /// declared sensitive — SEM-1's second Must-NOT, and the exact failure
    /// <see cref="OrderingTarget"/> refuses in the other direction. There is no third rendering to
    /// fall back to (a <c>wildcard</c> would honour the case and lose the tokenization the opt-in was
    /// asked for), and the two are contradictory declarations rather than a compilable combination, so
    /// the schema is what has to change.</para>
    ///
    /// <para>The <c>*</c> anchors are composed around the ESCAPED value
    /// (<see cref="SearchWildcardEscaping"/>), so a literal <c>*</c> the user typed cannot become
    /// one. The declared type is checked first and separately from the value's variant: there is no
    /// portable meaning for "does this number contain that substring", and a caller that skipped
    /// SEM-5 coercion could otherwise hand a <see cref="StringValue"/> to an <c>int64</c> field and
    /// get a case-SENSITIVE wildcard against a numeric field, since
    /// <see cref="SemanticsResolver"/> only resolves the pattern-match mechanism for a
    /// <c>string</c>.</para>
    /// </summary>
    private static JsonObject RenderSubstring(FieldTarget target, ComparisonNode node, Context context)
    {
        if (target.Config.Type != FieldType.String)
        {
            throw new SearchCompilationException(
                $"Field '{node.Field}' is declared '{target.Config.Type}', but operator '{node.Op}' is a substring " +
                "match and only has a defined rendering against a 'string' field.");
        }

        var mode = ResolveCaseSensitivity(
            target, node.Field, node.Op, SemanticsResolver.CaseSensitivityMechanism.PatternMatch, context);

        if (RequireValue(node) is not StringValue pattern)
        {
            throw new SearchCompilationException(
                $"Operator '{node.Op}' on field '{node.Field}' is a substring match, so its value must be a " +
                "stringValue — run TypeCoercionValidator (SEM-5) before compiling.");
        }

        if (target.Config.Text?.SearchMode == SearchMode.Analyzed
            && node.Op is ComparisonOperator.Contains or ComparisonOperator.NotContains)
        {
            if (mode != SemanticsResolver.CaseSensitivityMode.Insensitive)
            {
                throw new SearchCompilationException(
                    $"Field '{node.Field}' declares searchMode 'analyzed' and caseSensitivity 'sensitive', and " +
                    $"operator '{node.Op}' has no rendering that satisfies both. SEM-7's opt-in compiles to a " +
                    "`match`, which carries no `case_insensitive` parameter and is resolved by the field's own " +
                    "analyzer — every stock text analyzer in both engines lowercases — so the query would compare " +
                    "case-insensitively on a field the schema declared sensitive (SEM-1's second Must-NOT). Declare " +
                    "searchMode 'substring' to keep the case, or caseSensitivity 'insensitive' to keep the " +
                    "tokenization.");
            }

            return new JsonObject
            {
                ["match"] = new JsonObject
                {
                    [target.Raw] = new JsonObject
                    {
                        ["query"] = pattern.Value,
                        ["operator"] = "and"
                    }
                }
            };
        }

        var escaped = SearchWildcardEscaping.Escape(pattern.Value);

        var body = new JsonObject
        {
            ["value"] = node.Op switch
            {
                ComparisonOperator.StartsWith => $"{escaped}*",
                ComparisonOperator.EndsWith => $"*{escaped}",
                _ => $"*{escaped}*"
            }
        };

        if (mode == SemanticsResolver.CaseSensitivityMode.Insensitive)
        {
            body["case_insensitive"] = true;
        }

        return new JsonObject { ["wildcard"] = new JsonObject { [target.Keyword] = body } };
    }

    private static TypedValue RequireValue(ComparisonNode node) =>
        node.Value ?? throw new SearchCompilationException(
            $"Operator '{node.Op}' on field '{node.Field}' requires 'value'.");

    // ---- sorting (SEM-3 / SEM-6) --------------------------------------------------------------------

    /// <summary>One resolved sort key: the field path the request actually orders by, and the two
    /// directions.</summary>
    private readonly record struct SortKeyPlan(string Path, SortDirection Direction, NullsPosition NullsPosition);

    /// <summary>
    /// SEM-6/SEM-3/GRP-2: the request's own keys in order, then a trailing tiebreaker unless the sort
    /// already reaches it, after SEM-6's reduction — resolved to the sub-field each one can actually be ordered on.
    ///
    /// <para>GRP-2, at its narrowed scope: a drill-down LEAF has no buckets — it orders raw hits by
    /// whatever field the user picked, which need not be a group column at all — so it is
    /// <see cref="SemanticsResolver.GroupingMode.Ungrouped"/> and SEM-1 governs it, collation
    /// included. <c>spec/fixtures/group-aggregation/005</c> sorts a leaf on <c>product</c> and pins
    /// <c>product.normalized</c> for exactly that reason, beside an exact drill-down <c>term</c> on
    /// <c>region</c> in the same request — the per-clause granularity that lets this backend satisfy
    /// GRP-2 and SEM-1 at once where MongoDB cannot.</para>
    ///
    /// <para><b>A repeated sort key never reaches this method</b> (SEM-6, Bug #2565):
    /// <see cref="SemanticsResolver.AppendStableKeyTiebreaker(IReadOnlyList{SortItem}?, string, out bool)"/> drops a later
    /// occurrence of a field, and everything after the stable key, so there is nothing to reject or to
    /// tolerate here or in MDB-10's first collision. This DSL's <c>sort</c> is an ARRAY, where a repeat
    /// would only have been redundant; a MongoDB <c>$sort</c> document would have replaced the first entry.</para>
    /// </summary>
    private static IReadOnlyList<SortKeyPlan> ResolveSortPlan(IReadOnlyList<SortItem>? sort, Context context)
    {
        var keys = SemanticsResolver.AppendStableKeyTiebreaker(sort, context.Schema, groupColumn: null, out var appended);

        var plan = new List<SortKeyPlan>(keys.Count);

        for (var i = 0; i < keys.Count; i++)
        {
            var key = keys[i];
            var target = Resolve(key.Field, context);

            // The tiebreaker is always the LAST key when there is one — SEM-6's own rule, enforced
            // and reported by AppendStableKeyTiebreaker, not re-derived here by comparing the last
            // field to the stable key (the minted key and a user key on that field are the identical
            // SortItem).
            var provenance = appended && i == keys.Count - 1
                ? SemanticsResolver.SortKeyProvenance.AppendedTiebreaker
                : SemanticsResolver.SortKeyProvenance.Request;

            var mode = SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(
                    target.Config, SemanticsResolver.GroupingMode.Ungrouped, provenance)
                .Mode;

            plan.Add(new SortKeyPlan(
                OrderingTarget(target, mode, key.Field, "sort key"), key.Direction, key.NullsPosition));
        }

        return plan;
    }

    /// <summary>
    /// SEM-3: null placement is a native <c>sort</c> parameter on this backend — <c>missing</c>,
    /// <c>_last</c> or <c>_first</c> — so there is no emulation to arrange and nothing to unset
    /// afterwards, unlike MySQL's <c>ISNULL</c> prefix key or MongoDB's synthetic bucket. It is
    /// spelled on EVERY key unconditionally, including SEM-6's appended tiebreaker: SEM-3's first
    /// Must-NOT forbids relying on a dialect's implicit default even when it happens to match today,
    /// and SEM-6's fourth forbids "the stable key is probably never null" as a licence to omit it.
    /// </summary>
    private static JsonArray RenderSort(IReadOnlyList<SortKeyPlan> plan)
    {
        var sort = new JsonArray();

        foreach (var key in plan)
        {
            sort.Add(new JsonObject
            {
                [key.Path] = new JsonObject
                {
                    ["order"] = key.Direction == SortDirection.Asc ? "asc" : "desc",
                    ["missing"] = key.NullsPosition == NullsPosition.Last ? "_last" : "_first"
                }
            });
        }

        return sort;
    }

    // ---- paging (AG-3 / EXP-2) ----------------------------------------------------------------------

    /// <summary>
    /// AG-3: <c>from</c> takes <c>startRow</c> and <c>size</c> the row COUNT, which is
    /// <c>endRow - startRow</c> because <c>endRow</c> is exclusive — a semantic fact about the AG Grid
    /// request contract, and a compiler that passed <c>endRow</c> straight through would emit a
    /// perfectly plausible request returning the wrong hits.
    ///
    /// <para>EXP-2: <c>page: none</c> emits neither member, so the body ends after <c>sort</c>
    /// (<c>spec/fixtures/sort-paging/012</c>). Both are emitted for a range page even when the offset
    /// is zero — the first-page artifact pins <c>"from": 0</c> rather than omitting it, and a
    /// conditional would be a second rule about when the window is expressed.</para>
    /// </summary>
    private static (int? From, int? Size) ResolveWindow(PageSpec page) => page switch
    {
        NonePage => (null, null),
        RangePage range => (range.StartRow, range.EndRow - range.StartRow),
        _ => throw new SearchCompilationException($"Unknown PageSpec type '{page.GetType().Name}'.")
    };

    // ---- grouping (BM-2) --------------------------------------------------------------------------

    /// <summary>
    /// BM-2/AGG-5/OSE-11: the grouped level's <c>composite</c> aggregation and its sub-aggregations.
    ///
    /// <para><b>Why <c>composite</c> and not <c>terms</c>.</b> A grouped level is paged — the grid
    /// asks for one window of buckets at a time — and <c>composite</c> is the only bucket aggregation
    /// in this subset that enumerates every bucket in key order rather than returning an approximate
    /// top-N by doc count. It is also the only one with <c>missing_bucket</c>, which is what keeps a
    /// null group key from being silently dropped (AR-8/BM-2's intent, and SEM-3's concern one level
    /// up).</para>
    ///
    /// <para><b>AGG-5's accepted divergence, honoured rather than worked around.</b>
    /// <c>missing_bucket: true</c> has no <c>missing_order</c> control in the pinned 7.10-era subset:
    /// the null bucket sorts <b>first regardless of the direction requested</b>, while Postgres
    /// (<c>NULLS LAST</c>/<c>NULLS FIRST</c>) and MongoDB (its bucket emulation) both honour it. So
    /// the group key's own <see cref="NullsPosition"/> has nothing to compile to here and is
    /// deliberately not rendered. A client-side reorder would defeat server-side paging's whole
    /// purpose for the grouped case, which is why AGG-5 records this as a host-visible divergence
    /// instead.</para>
    ///
    /// <para><b>AGG-4 does not reach the composite's source</b>, and the distinction is worth
    /// stating because the two spell <c>order</c> differently. AGG-4 exists because a bare
    /// <c>terms</c> aggregation defaults to doc-count-descending, an order no other backend would
    /// produce; a composite source is ordered by its key <em>by construction</em>, so there is no
    /// wrong default to guard against, and the parameter here carries the DIRECTION the request asked
    /// for (GRP-4) rather than a fixed <c>asc</c>. It is spelled only for <c>desc</c>, the source's
    /// documented default being ascending — <c>group-aggregation/021</c> pins the one, the other
    /// fifteen composite artifacts pin its absence.</para>
    /// </summary>
    private static JsonObject RenderGroupedAggregations(
        string groupColumn, IReadOnlyList<Aggregation> aggregations, SearchQueryRequest request, Context context)
    {
        var target = Resolve(groupColumn, context);
        var direction = RequireBucketOrder(groupColumn, aggregations, request, context);

        var source = new JsonObject
        {
            ["field"] = target.Config.Type == FieldType.String ? target.Keyword : target.Raw,
            ["missing_bucket"] = true
        };

        if (direction == SortDirection.Desc)
        {
            source["order"] = "desc";
        }

        var composite = new JsonObject
        {
            ["size"] = RequireBucketWindow(request.Page),
            ["sources"] = new JsonArray(new JsonObject { [groupColumn] = new JsonObject { ["terms"] = source } })
        };

        var level = new JsonObject { ["composite"] = composite };
        var children = RenderAggregations(aggregations, context);

        if (children.Count > 0)
        {
            level["aggs"] = children;
        }

        return new JsonObject { [RequireAggregationName(groupColumn, "the grouped level")] = level };
    }

    /// <summary>
    /// OSE-11(d): a grouped level's bucket window. A <c>composite</c> aggregation pages with an
    /// <c>after</c> key rather than an offset, so a non-zero <c>startRow</c> has no rendering at all
    /// and an unpaginated grouped request has no bucket count to give.
    ///
    /// <para>Both are REFUSED rather than approximated. Rendering <c>size</c> alone and ignoring the
    /// offset would return the first page of buckets for every page the grid asks for — a plausible
    /// request answering a different question, silently, which is the failure SQL-7(b) and MDB-9 both
    /// refuse in the same register.</para>
    ///
    /// <para><b>This is a FIRST-PAGE-ONLY limitation, not a deep-paging one</b>, and the difference
    /// matters when scoping #1622. PERF-2's <c>search_after</c> escalates only beyond
    /// <c>max_result_window</c> (10 000 rows by default), so an ordinary grid never reaches it; AG Grid
    /// SSRM's default block size is <b>100 rows</b>, so the <em>second block of any grouped level</em>
    /// — the moment a user scrolls one screen past the first hundred groups — lands here. Every
    /// grouped grid on this backend hits it, not only the deep ones. The owner is still the execution
    /// adapter (#1622), because the <c>after</c> key is the previous response's own
    /// <c>after_key</c> and neither <c>PageSpec</c> nor <c>GridSchema</c> can carry it, but the
    /// urgency is not <c>search_after</c>'s.</para>
    /// </summary>
    private static int RequireBucketWindow(PageSpec page) => page switch
    {
        // The window's COUNT, as AG-3 defines it (`endRow` is exclusive) — which the pattern above
        // has just pinned to `endRow - 0`. Written the long way anyway, so the arithmetic reads the
        // same here as in ResolveWindow rather than looking like `endRow` being passed straight
        // through, which is exactly the mistake AG-3 exists to prevent.
        RangePage { StartRow: 0 } range => range.EndRow - range.StartRow,
        RangePage range => throw new SearchCompilationException(
            $"A grouped level was asked for rows {range.StartRow}..{range.EndRow}, but a composite aggregation has " +
            "no offset — it pages forward with an `after` key carried between requests, which neither PageSpec nor " +
            "this compiler's inputs hold. This is the SECOND BLOCK of a grouped level, not a deep page: AG Grid " +
            "SSRM's default block is 100 rows, so every grouped grid reaches it as soon as the user scrolls. " +
            "Carrying the after key is the execution adapter's (#1622)."),
        NonePage => throw new SearchCompilationException(
            "A grouped level was asked for an unpaginated page (EXP-2's page: none), but a composite aggregation " +
            "always returns at most `size` buckets and has no unbounded form. Only a request built outside " +
            "AgGridRequestParser reaches this combination: since #1650 the export path discards group state before " +
            "compiling (EXP-1(a)), so an export never arrives carrying a GroupSpec."),
        _ => throw new SearchCompilationException($"Unknown PageSpec type '{page.GetType().Name}'.")
    };

    /// <summary>AR-8's closed v1 function set. AGG-1's non-obvious member needs no special
    /// construction here: <c>value_count</c> already counts documents holding a non-null value for the
    /// named field, which is what <c>count</c> means — identically to SQL's <c>COUNT(field)</c>, and
    /// unlike MongoDB's naive <c>{"$sum": 1}</c>, which AGG-1 has to forbid by name.</summary>
    private static JsonObject RenderAggregations(IReadOnlyList<Aggregation> aggregations, Context context)
    {
        var aggs = new JsonObject();

        foreach (var aggregation in aggregations)
        {
            var output = RequireOutputName(aggregation);

            // The `aggs` container is a JSON object, so a repeated key is last-wins rather than an
            // error — MDB-10's third collision, reached on a different backend by the same mechanism.
            // The grid would read one column holding another column's number.
            //
            // Fully redundant, not merely narrowed: #1886 moved the same check upstream into
            // Craticula.Core's AggregationValidator, which every entry point runs, because
            // Craticula.Sql had no equivalent and the condition is a property of the request rather
            // than of this container's shape. RenderAggregations has exactly one caller, this
            // method's own Build, which validates first — so unlike RenderGroup's "_id" guard in
            // Craticula.Mongo (a genuinely different collision Core's check cannot see), there is no
            // "host that builds IR directly" this branch still protects. Kept anyway as a second,
            // free-standing statement of MDB-10's third instance, not as reachable code.
            if (aggs.ContainsKey(output))
            {
                throw new SearchCompilationException(
                    $"Two aggregations resolve to the output name '{output}' (GRP-4: an alias, or the " +
                    "<field>_<func> default). An aggregation container is a JSON object, so the second would " +
                    "silently replace the first — the request names the same output column twice.");
            }

            var field = new JsonObject { ["field"] = Resolve(aggregation.Field, context).Raw };

            aggs[output] = new JsonObject
            {
                [aggregation.Func switch
                {
                    AggregationFunc.Sum => "sum",
                    AggregationFunc.Min => "min",
                    AggregationFunc.Max => "max",
                    AggregationFunc.Avg => "avg",
                    AggregationFunc.Count => "value_count",
                    _ => throw new SearchCompilationException($"Unknown aggregation function '{aggregation.Func}'.")
                }] = field
            };
        }

        return aggs;
    }

    /// <summary>
    /// GRP-4/OSE-11: an aggregate's <see cref="Aggregation.OutputName"/> — the shared GRP-4 rule,
    /// which is AGG-2's <see cref="Aggregation.Alias"/> when the adapter set one
    /// (<c>ColumnVO.id</c> differed from <c>ColumnVO.field</c>) and otherwise the compiler default
    /// <c>&lt;field&gt;_&lt;func&gt;</c> — <b>validated against the very pattern
    /// <c>ir.schema.json</c> already imposes on <c>alias</c></b> (<c>^[A-Za-z_][A-Za-z0-9_]*$</c>).
    /// The composition is not repeated here; only the check this backend needs on top of it is, which
    /// is why the wrapper survived #1885's extraction while the two other compilers' copies did not.
    ///
    /// <para>The default is where the guard was missing. <see cref="AggregationValidator"/> checks an
    /// explicit alias precisely because it "lands in generated query text as an identifier … where
    /// SEC-2's values-are-parameters rule cannot apply", but <c>$defs/fieldName</c> carries no pattern
    /// at all, so a nested colId such as <c>customer.name</c> composes a default name
    /// <c>customer.name_sum</c> that no validator has ever seen. On this backend an aggregation name
    /// is not merely cosmetic: it is addressed through a <c>buckets_path</c> mini-language in which
    /// <c>&gt;</c> navigates into a sub-aggregation and <c>.</c> selects a metric, and both engines
    /// reject <c>[</c>, <c>]</c> and <c>&gt;</c> in an aggregation name outright. So the default is
    /// held to the same standard as the alias it substitutes for, rather than to a looser one nobody
    /// wrote down.</para>
    /// </summary>
    private static string RequireOutputName(Aggregation aggregation)
    {
        var name = aggregation.OutputName;

        if (aggregation.Alias is null && !IdentifierPattern.IsMatch(name))
        {
            throw new SearchCompilationException(
                $"The default output name '{name}' for the '{aggregation.Func}' of '{aggregation.Field}' is not a " +
                "legal aggregation name: ir.schema.json holds an explicit `alias` to ^[A-Za-z_][A-Za-z0-9_]*$ " +
                "precisely because the name lands in query text as an identifier, but `fieldName` has no pattern, so " +
                "the <field>_<func> default can inherit characters the alias slot forbids. An aggregation name is " +
                "read here through a buckets_path mini-language ('>' navigates, '.' selects a metric) and both " +
                "engines reject '[', ']' and '>' outright. Send an explicit `alias` (AG Grid's ColumnVO.id) for this " +
                "column.");
        }

        return name;
    }

    /// <summary>
    /// The name of a BUCKET aggregation — the grouped level's composite (named for the group column)
    /// and BM-3's <c>terms</c> (named for the target colId). Both come from a colId, which
    /// <c>ir.schema.json</c>'s <c>$defs/fieldName</c> constrains only in length, and a colId that is
    /// legal everywhere else in this project can still be a name both engines reject.
    ///
    /// <para>The check here is the engines' own, not the alias pattern <see cref="RequireOutputName"/>
    /// applies: a dotted colId is a perfectly good aggregation name and refusing it would break a
    /// nested-document schema for no reason, whereas <c>[</c>, <c>]</c> and <c>&gt;</c> are reserved
    /// by the <c>buckets_path</c> syntax and produce a 400 at execution time. The two names are held
    /// to different standards because they are read by different things — one is an identifier the
    /// grid reads a NUMBER back by, the other is only ever a container key.</para>
    /// </summary>
    private static string RequireAggregationName(string colId, string role)
    {
        if (colId.AsSpan().IndexOfAny('[', ']', '>') >= 0)
        {
            throw new SearchCompilationException(
                $"The column '{colId}' names {role}'s aggregation, but '[', ']' and '>' are reserved by the " +
                "buckets_path syntax and both engines reject an aggregation name containing them. A colId reaches " +
                "here unfiltered — ir.schema.json's $defs/fieldName bounds its length and nothing else — so this is " +
                "checked rather than assumed.");
        }

        return colId;
    }

    // Copied verbatim from spec/ir.schema.json's $defs/aggregation.alias pattern, which
    // AggregationValidator already enforces on an EXPLICIT alias.
    private static readonly Regex IdentifierPattern = new(@"^[A-Za-z_][A-Za-z0-9_]*$");

    /// <summary>
    /// GRP-4/OSE-11(c): a grouped level's ordering direction — and the refusal of every ordering a
    /// <c>composite</c> aggregation cannot actually express.
    ///
    /// <para><b>A composite orders by its own key and by nothing else</b>, and that is not a
    /// limitation a pipeline aggregation can lift. A <c>bucket_sort</c> under a composite reorders
    /// only the buckets the composite has ALREADY returned — the first <c>size</c> of them in
    /// composite-key order — so "the 100 largest regions by revenue" would compile to "the first 100
    /// regions alphabetically, rearranged by revenue". With more distinct regions than the window,
    /// those are different groups, and the request that asked for the first answer would silently get
    /// the second. Elasticsearch's own composite documentation states the general form of this: a
    /// composite is not compatible with pipeline aggregations, for exactly this reason.</para>
    ///
    /// <para>So ordering a grouped level by an aggregate — or by anything other than the group column
    /// alone — is a <b>compiler error</b>, in the register OSE-11(d)'s row window, SQL-7(b) and MDB-9
    /// already established: a plausible request answering a different question, silently, is the one
    /// failure mode this project refuses at every fork. It is a real, user-visible capability gap and
    /// is recorded as one; closing it needs a different grouped-ordering strategy (a two-pass
    /// terms-then-composite plan, or client-side reordering of a full bucket enumeration), which is
    /// the execution adapter's business (#1622) and belongs behind a live cluster (#1624).</para>
    ///
    /// <para>Every accepted key still resolves through
    /// <see cref="SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity"/> with
    /// <see cref="SemanticsResolver.GroupingMode.Grouped"/>, which is GRP-2's exactness: a grouped
    /// level's keys order the very buckets the aggregation produced and so must agree with it. On this
    /// backend that resolves to "spell nothing", and there is nothing to spell — a composite source has
    /// no case parameter at all — so the call is made for the invariant rather than for a value, and
    /// any future construct that DOES have one inherits the right answer.</para>
    ///
    /// <para>SEM-6's tiebreaker applies with the GROUP COLUMN in the stable key's role (GRP-4): the
    /// schema's <c>stableKey</c> is not in a bucket at all, while the group column's values are unique
    /// across the level's buckets by construction — which is also why a single group-column key needs
    /// no tiebreaker after it and why an accepted plan is always exactly one key long.</para>
    /// </summary>
    private static SortDirection RequireBucketOrder(
        string groupColumn, IReadOnlyList<Aggregation> aggregations, SearchQueryRequest request, Context context)
    {
        var keys = SemanticsResolver.AppendStableKeyTiebreaker(
            request.Sort, context.Schema, groupColumn, out _,
            aggregateColumnIds: aggregations.Select(aggregation => aggregation.ColumnId).ToArray());

        foreach (var key in keys)
        {
            if (key.Field == groupColumn)
            {
                continue;
            }

            // GRP-4: matched against Aggregation.ColumnId, AGG-2's ColumnVO.id reconstructed — the
            // grid sends the COLUMN's id in sortModel, and AGG-2 sets the alias from that id exactly
            // when it differs from the field. Not OutputName: an unaliased aggregation's column id is
            // the bare field, so matching on the output name would misreport the request that this
            // backend actually cannot express as one it merely does not recognise.
            throw aggregations.Any(a => a.ColumnId == key.Field)
                ? new SearchCompilationException(
                    $"The grouped level on '{groupColumn}' is ordered by the aggregate '{key.Field}', which a " +
                    "composite aggregation cannot express. A composite enumerates buckets in composite-key order " +
                    "and returns `size` of them; a bucket_sort would only reorder that page, so the answer would be " +
                    "the first N groups by key, rearranged — not the top N by the aggregate. Elasticsearch states " +
                    "the general rule: a composite aggregation is not compatible with pipeline aggregations. " +
                    "Ordering a grouped level by an aggregate is a capability this backend does not have (OSE-11(c)); " +
                    "it needs a different grouped-ordering strategy, owned by #1622 and gradeable only against a live " +
                    "cluster (#1624).")
                : new SearchCompilationException(
                    $"A grouped query can be ordered only by its group column ('{groupColumn}'), but the request " +
                    $"sorts on '{key.Field}', which this level does not produce.");
        }

        if (keys.Count != 1)
        {
            throw new SearchCompilationException(
                $"The grouped level on '{groupColumn}' resolves to {keys.Count} ordering keys on that one column. A " +
                "composite source carries a single `order`, so a second criterion on the same key has no rendering — " +
                "and no meaning either, the first key already being total over the level's buckets.");
        }

        _ = SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity(
            Resolve(keys[0].Field, context).Config, SemanticsResolver.GroupingMode.Grouped);

        return keys[0].Direction;
    }

    // ---- BM-3's search prefix -----------------------------------------------------------------------

    /// <summary>
    /// GRP-6(c)/OSE-12: the set filter's search box, compiled to the <c>terms</c> aggregation's
    /// <c>include</c> — a Lucene regex evaluated at aggregation time, anchored implicitly (it must
    /// match a whole term), so a prefix is the escaped text followed by <c>.*</c>.
    ///
    /// <para><b>The accepted divergence this creates, recorded rather than worked around.</b>
    /// <c>include</c> has <b>no case-insensitivity option</b> in the pinned 7.10-era subset — unlike
    /// the query-time <c>case_insensitive</c> on <c>term</c>/<c>wildcard</c>/<c>prefix</c>/
    /// <c>regexp</c> — so the prefix matches case-sensitively as typed, where Postgres's <c>ILIKE</c>
    /// and Mongo's <c>$regex</c>/<c>i</c> fold. That is a documented, host-visible divergence in the
    /// same register as AGG-5, stated in <c>spec/fixtures/group-aggregation/018</c>'s own description;
    /// a field needing a case-insensitive value search would have to fold at index time, which is
    /// SEM-1's <c>search.normalizedSubField</c> obligation reappearing on the bucket side.</para>
    ///
    /// <para>Filtering the BUCKETS rather than the documents is equivalent for this one construct —
    /// a bucket exists exactly when some document holds its value, and the predicate is on the very
    /// column being bucketed — so nothing is lost by moving it, and <c>018</c>/<c>022</c> pin the
    /// move.</para>
    /// </summary>
    private static string? RenderSearchPrefixInclude(SearchSetValuesRequest request) =>
        request.SearchPrefix is { } prefix ? $"{SearchRegexEscaping.Escape(prefix)}.*" : null;

    /// <summary>
    /// Takes GRP-6(c)'s prefix predicate back out of the tree
    /// <see cref="GridFilterPipeline.ProcessSetValues"/> merged it into, so it is not compiled twice —
    /// once as an <c>include</c> and once as a query clause.
    ///
    /// <para><b>By value, against a freshly minted copy, and never by shape.</b> The node is re-made
    /// through <see cref="SetValuesFilter.SearchPrefixPredicate"/> — the same Core primitive that made
    /// the one in the tree — and removed by record equality. Locating it by field name instead
    /// (<c>SetValuesFilter.ExcludeOwnField</c>) would be wrong in a way no fixture would show: SC-5's
    /// static filter is injected AFTER the prefix and may legitimately carry its own condition on the
    /// same column, and dropping a host's static filter is a security regression, not a rendering
    /// one. Locating it by position would be GRP-5's named trap.</para>
    ///
    /// <para>Not finding it AT ALL is a refusal rather than a fallback: it means this method's
    /// premise about what <see cref="GridFilterPipeline.ProcessSetValues"/> returns no longer holds,
    /// and the two plausible recoveries — compiling the prefix twice, or dropping it — are both
    /// silently wrong answers. Finding it more than once is <b>not</b> an error, and the distinction
    /// was a real defect: SC-5's static filter is injected after the prefix, so a host whose static
    /// filter happens to spell the identical <c>startsWith</c> predicate on the same column produces a
    /// tree with two equal nodes, and a duplicated conjunct is semantically inert. Refusing that would
    /// have failed compilation over a redundancy. Exactly ONE node is removed — the first match — so
    /// the host's own copy survives into the query as an ordinary clause, which is what it is.</para>
    /// </summary>
    private static FilterNode? StripSearchPrefixPredicate(SearchSetValuesRequest request)
    {
        if (request.SearchPrefix is null)
        {
            return request.Filter;
        }

        var predicate = SetValuesFilter.SearchPrefixPredicate(new SetValuesSpec
        {
            ColId = request.ColId,
            SearchPrefix = request.SearchPrefix
        })!;

        var removed = 0;
        var stripped = Remove(request.Filter, predicate, ref removed);

        if (removed == 0)
        {
            throw new SearchCompilationException(
                $"The search prefix '{request.SearchPrefix}' on '{request.ColId}' compiles to the terms " +
                "aggregation's `include` (GRP-6(c)), so its predicate must appear in the filter " +
                "GridFilterPipeline.ProcessSetValues produced — it appeared nowhere. Pass that method's own output " +
                "as `Filter`, unmodified.");
        }

        return stripped;
    }

    /// <summary>
    /// Removes the FIRST node equal to <paramref name="predicate"/> and leaves any duplicate in place,
    /// with the same three edge cases <see cref="FieldAllowlistValidator.Strip"/> already settles for
    /// pruning a tree: a composite that loses every child disappears rather than becoming an empty
    /// node, one that loses down to a single child is unwrapped, and a <see cref="NotNode"/> whose
    /// child vanishes vanishes with it rather than negating nothing.
    /// </summary>
    private static FilterNode? Remove(FilterNode? node, ComparisonNode predicate, ref int removed)
    {
        switch (node)
        {
            case null:
                return null;

            case ComparisonNode comparison when removed == 0 && comparison == predicate:
                removed++;
                return null;

            case CompositeFilterNode composite:
            {
                var kept = new List<FilterNode>(composite.Nodes.Count);
                foreach (var child in composite.Nodes)
                {
                    if (Remove(child, predicate, ref removed) is { } survivor)
                    {
                        kept.Add(survivor);
                    }
                }

                return kept.Count switch
                {
                    0 => null,
                    1 => kept[0],
                    _ => composite is AndNode ? new AndNode { Nodes = kept } : new OrNode { Nodes = kept }
                };
            }

            case NotNode not:
                return Remove(not.Node, predicate, ref removed) is { } inner ? new NotNode { Node = inner } : null;

            default:
                return node;
        }
    }
}
