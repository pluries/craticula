using System.Globalization;
using System.Text;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Sql;

/// <summary>
/// BM-1's dialect-agnostic query builder: walks the IR filter/group/sort/page spec and emits
/// <c>SELECT &lt;projection&gt; FROM &lt;source&gt; [WHERE &lt;tree&gt;] [GROUP BY &lt;key&gt;]
/// ORDER BY &lt;keys&gt; [&lt;paging&gt;]</c> as a <see cref="SqlQuery"/>. Every token that differs
/// between SQL dialects goes through <see cref="ISqlDialect"/>; nothing in this file switches on
/// which dialect it was handed, which is what makes "adding a dialect requires zero builder changes"
/// checkable rather than aspirational (see <c>docs/architecture/c4-components-sql-compiler.md</c>).
///
/// <para><b>Semantics are never re-derived here.</b> Case-sensitivity mechanism, null-inclusivity,
/// the <c>blank</c> condition and the SEM-6 tiebreaker all come from
/// <see cref="SemanticsResolver"/> (#1634) — the one place SEM-* rules live, so the SQL, Mongo and
/// Search compilers cannot drift apart (G3/G4). What IS this compiler's own responsibility is the
/// SQL <em>shape</em> those decisions render into: <c>spec/semantics.md</c>'s SQL-0..SQL-8 addendum,
/// and specifically the tree-level <c>NOT</c> fan-out, which SemanticsResolver deliberately has no
/// method for because it is a statement about tree shape rather than about one operator.</para>
///
/// <para><b>Grouping (#1640, BM-2).</b> A request carrying a <see cref="GroupSpec"/> compiles under
/// <c>spec/semantics.md</c>'s grouping addendum (GRP-1..GRP-5): <see cref="GroupingPlan"/> decides
/// between the grouped level and the fully-consumed drill-down leaf, the consumed <c>groupKeys</c>
/// become real IR predicates merged through <see cref="FilterTreeMerge"/> (so SQL-2's wrap applies
/// to them exactly as it does to a user's own <c>and</c>), and none of the protocol's own keys fold
/// case (GRP-2). Everything grouping adds to the emitted text is ANSI —
/// <c>GROUP BY</c>, <c>SUM</c>/<c>MIN</c>/<c>MAX</c>/<c>AVG</c>/<c>COUNT</c>, <c>AS</c>, and #1886's
/// AGG-6 <c>COALESCE</c> around the first of those (see <see cref="AggregateCall"/>) — so BM-2
/// needed <b>no</b> new <see cref="ISqlDialect"/> member; the drill-down predicate and the ordering
/// keys reuse <see cref="ISqlDialect.RenderScalarComparison"/> and
/// <see cref="ISqlDialect.RenderSortKey"/> unchanged.</para>
///
/// <para><b>Set-filter values (#1641, BM-3).</b> <see cref="BuildSetValues"/> is the second entry
/// point, compiling <c>spec/semantics.md</c>'s GRP-6 — a distinct-values query over one column, its
/// own filter dropped, capped by SEC-3. It is a separate method rather than a mode of
/// <see cref="Build"/> because it shares every clause renderer but none of the request shape (no
/// page, no sort model, no aggregation); see <see cref="SqlSetValuesRequest"/>.</para>
///
/// <para><b>Export (#1650, EXP-1/EXP-2).</b> <c>exportScope</c> reaches this builder only as the
/// <see cref="PageSpec"/> the adapter already resolved it to (<c>all</c> is EXP-2's
/// <see cref="NonePage"/>), and the export's column list as <see cref="SqlQueryRequest.Projection"/>
/// — the one thing that widens the <c>SELECT</c> list. An <em>ordinary</em> row query still projects
/// <c>SELECT *</c> (GRP-3): only an export names its output columns, which is what EXP-1(b) in
/// <c>spec/semantics.md</c> pins.</para>
/// </summary>
public static class SqlQueryBuilder
{
    /// <summary>
    /// Count mode (CNT-1..CNT-5): compiles the statement that counts the rows (or, for a grouped
    /// level, the groups) <see cref="Build"/> would page over. Ignores <c>Page</c>, <c>Sort</c> and
    /// <c>Projection</c>.
    /// </summary>
    public static SqlQuery BuildCount(SqlQueryRequest request, ISqlDialect dialect)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(dialect);

        FilterNodeValidator.Validate(request.Filter);
        GroupSpecValidator.Validate(request.Group);
        AggregationValidator.Validate(request.Aggregations);

        var parameters = new SqlParameterBag(dialect);
        var grouping = GroupingPlan.Resolve(request.Group, request.Aggregations);
        var context = new Context(request.Schema, dialect, parameters);

        var inner = new StringBuilder();
        if (grouping?.GroupColumn is { } groupColumn)
        {
            inner.Append("SELECT ").Append(ResolveColumn(groupColumn, context));
        }
        else
        {
            inner.Append("SELECT COUNT(*)");
        }

        inner.Append(" FROM ").Append(dialect.QuoteIdentifier(request.Schema.Source));

        if (RenderWhere(request.Filter, grouping?.DrillDown, context) is { } predicate)
        {
            inner.Append(" WHERE ").Append(predicate);
        }

        string sql;
        if (grouping?.GroupColumn is { } grouped)
        {
            inner.Append(" GROUP BY ").Append(ResolveColumn(grouped, context));

            // CNT-5: no AS before the derived-table alias, Oracle rejects it.
            sql = $"SELECT COUNT(*) FROM ({inner}) {CountSqlShape.DerivedTableAlias}";
        }
        else
        {
            sql = inner.ToString();
        }

        return new SqlQuery
        {
            Dialect = dialect.Name,
            Sql = sql,
            Parameters = parameters.Values
        };
    }

    /// <summary>
    /// Compiles <paramref name="request"/> into <paramref name="dialect"/>'s SQL text plus its
    /// ordered parameters. Re-runs the IR's own structural validators first — the same
    /// defense-in-depth every other public entry point in this codebase performs
    /// (<see cref="TypeCoercionValidator.Coerce"/>, <see cref="ResourceLimitsValidator.Validate"/>,
    /// <see cref="SemanticsResolver.AppendStableKeyTiebreaker(IReadOnlyList{SortItem}?, string)"/>), since a caller can reach this
    /// method with a hand-built tree that never went through <see cref="GridFilterPipeline"/>.
    /// </summary>
    /// <exception cref="SqlCompilationException">A structurally valid shape this compiler has no
    /// defined rendering for — an unsupported <see cref="SqlMapping"/> form, or a field the
    /// <see cref="GridSchema"/> does not declare.</exception>
    public static SqlQuery Build(SqlQueryRequest request, ISqlDialect dialect)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(dialect);

        FilterNodeValidator.Validate(request.Filter);
        PageSpecValidator.Validate(request.Page);
        GroupSpecValidator.Validate(request.Group);
        AggregationValidator.Validate(request.Aggregations);

        // EXP-1's group-export carve-out means the adapter has already nulled the group state on any
        // export, so the two are mutually exclusive by construction. Checked rather than assumed:
        // a caller building the request by hand could set both, and there is no defined shape for
        // "project these columns" over a GROUP BY that projects a bucket key and its aggregates.
        if (request.Projection is not null && request.Group is not null)
        {
            throw new SqlCompilationException(
                "A request carries both a GroupSpec and an EXP-1(b) export projection. An export emits leaf rows " +
                "and discards group state (EXP-1's carve-out, applied by AgGridRequestParser), so the two never " +
                "arrive together from the adapter.");
        }

        // Same population as the guard above — a hand-built request, since AgGridRequestParser refuses
        // an empty 'exportColumns' at the wire. An empty list is not "project nothing": it renders
        // `SELECT  FROM ...`, which is not SQL at all, and the driver would be the first thing to say
        // so. EXP-1(b)'s "omit the property to get the default projection" is the shape that means it.
        if (request.Projection is { Count: 0 })
        {
            throw new SqlCompilationException(
                "A request carries an empty EXP-1(b) export projection. An export of no columns has no compiled " +
                "form; leave Projection null for GRP-3's SELECT * / the schema-order default.");
        }

        var parameters = new SqlParameterBag(dialect);
        var grouping = GroupingPlan.Resolve(request.Group, request.Aggregations);
        var context = new Context(request.Schema, dialect, parameters);

        var sql = new StringBuilder("SELECT ")
            .Append(RenderProjection(grouping, request.Projection, context))
            .Append(" FROM ")
            .Append(dialect.QuoteIdentifier(request.Schema.Source));

        if (RenderWhere(request.Filter, grouping?.DrillDown, context) is { } predicate)
        {
            sql.Append(" WHERE ").Append(predicate);
        }

        // GRP-1: only the grouped level buckets; the fully-consumed drill-down leaf emits raw rows.
        if (grouping?.GroupColumn is { } groupColumn)
        {
            sql.Append(" GROUP BY ").Append(ResolveColumn(groupColumn, context));
        }

        sql.Append(" ORDER BY ").Append(RenderOrderBy(request.Sort, grouping, context));

        // EXP-2: an unpaginated request renders nothing at all, so the statement ends after ORDER BY.
        if (ResolveRowWindow(request.Page) is { } window)
        {
            sql.Append(' ').Append(dialect.RenderPaging(window.Offset, window.Limit, parameters));
        }

        return new SqlQuery
        {
            Dialect = dialect.Name,
            Sql = sql.ToString(),
            Parameters = parameters.Values
        };
    }

    /// <summary>
    /// GRP-6/BM-3: compiles the set-filter distinct-values query —
    /// <c>SELECT DISTINCT &lt;column&gt; FROM &lt;source&gt; [WHERE &lt;tree&gt;]
    /// ORDER BY &lt;column&gt; &lt;cap&gt;</c>. DISTINCT is the default; a dialect with
    /// <see cref="ISqlDialect.DistinctValuesUseGroupBy"/> (SQL Server) emits <c>GROUP BY &lt;column&gt;</c>
    /// in its place (GRP-6(f)).
    ///
    /// <para>Everything that varies from <see cref="Build"/> is in this method; every clause it emits
    /// is rendered by the same members. <c>DISTINCT</c> is ANSI and spelled identically on every
    /// dialect, so it is the builder's to emit — the row cap is the one thing BM-3 had to add to
    /// <see cref="ISqlDialect"/>, and that member's own doc says why it could not be
    /// <see cref="ISqlDialect.RenderPaging"/> with a zero offset.</para>
    ///
    /// <list type="bullet">
    /// <item><description><b>No projection alias.</b> A distinct-values query returns one column of
    /// scalars, not rows a grid maps by key, so GRP-3's naming rule — which exists because
    /// <c>SELECT *</c> hands back physical column names — has nothing to name here.
    /// <c>group-aggregation/016</c> pins the bare form.</description></item>
    /// <item><description><b>No SEM-6 tiebreaker.</b> The single <c>ORDER BY</c> key is the distinct
    /// column itself, whose values are unique across the result rows by construction — appending the
    /// schema's <see cref="GridSchema.StableKey"/> would order by a column the statement does not
    /// select, which is the same invalid SQL GRP-4 avoids at a grouped level.</description></item>
    /// <item><description><b>Neither the <c>DISTINCT</c> nor its <c>ORDER BY</c> folds case</b>
    /// (GRP-6), even on a case-insensitive string: they compute and order a distinct set exactly as a
    /// <c>GROUP BY</c> does, and the values are handed straight back to the grid to be sent again as
    /// <c>in</c> values or a <c>groupKey</c>, which GRP-2 matches exactly.</description></item>
    /// </list>
    /// </summary>
    /// <exception cref="SqlCompilationException">A field the <see cref="GridSchema"/> does not
    /// declare, an unsupported <see cref="SqlMapping"/> form, or a non-positive
    /// <see cref="SqlSetValuesRequest.RowLimit"/>.</exception>
    public static SqlQuery BuildSetValues(SqlSetValuesRequest request, ISqlDialect dialect)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(dialect);

        FilterNodeValidator.Validate(request.Filter);

        // Defense in depth against a caller that skipped ResourceLimitsValidator.ResolveSetValuesLimit:
        // a zero or negative cap compiles to a statement that can never return a value, and on SQL
        // Server `FETCH NEXT 0 ROWS ONLY` is an outright error (msg 10744) rather than an empty result.
        if (request.RowLimit <= 0)
        {
            throw new SqlCompilationException(
                $"A set-values row limit must be positive, got {request.RowLimit} — resolve it through " +
                "ResourceLimitsValidator.ResolveSetValuesLimit, which clamps the client's request to the host's " +
                "configured maximum and never yields a non-positive answer.");
        }

        var parameters = new SqlParameterBag(dialect);
        var context = new Context(request.Schema, dialect, parameters);

        var column = ResolveColumn(request.ColId, context);
        var field = ResolveField(request.ColId, context);

        // GRP-6(f): the same set, spelled GROUP BY where the engine cannot ORDER a DISTINCT by an expression.
        var sql = new StringBuilder(dialect.DistinctValuesUseGroupBy ? "SELECT " : "SELECT DISTINCT ")
            .Append(column)
            .Append(" FROM ")
            .Append(dialect.QuoteIdentifier(request.Schema.Source));

        if (RenderWhere(request.Filter, drillDown: null, context) is { } predicate)
        {
            sql.Append(" WHERE ").Append(predicate);
        }

        if (dialect.DistinctValuesUseGroupBy)
        {
            sql.Append(" GROUP BY ").Append(column);
        }

        // GRP-6, through GRP-2's own resolver: the distinct key decides bucket identity exactly as a
        // GROUP BY key does, so it resolves Grouped and folds no case. Ascending / nulls last is
        // MINTED here rather than read from a request — there is no sort model to read — which is the
        // same thing AppendStableKeyTiebreaker does for the key it mints, and is why SEM-3's "never
        // re-derive nullsPosition from direction" does not apply: nothing carried one to begin with.
        var caseSensitivity = SemanticsResolver
            .ResolveOrderingAndGroupKeyCaseSensitivity(field, SemanticsResolver.GroupingMode.Grouped)
            .Mode;

        sql.Append(" ORDER BY ")
            .Append(dialect.RenderSortKey(column, SortDirection.Asc, NullsPosition.Last, caseSensitivity))
            .Append(' ')
            .Append(dialect.RenderRowLimit(request.RowLimit, parameters));

        return new SqlQuery
        {
            Dialect = dialect.Name,
            Sql = sql.ToString(),
            Parameters = parameters.Values
        };
    }

    /// <summary>
    /// The per-compilation state threaded through the tree walk, so no rendering method needs four
    /// parameters of plumbing.
    ///
    /// <para><paramref name="IsGroupKeyMatch"/> carries <em>provenance</em>, not shape: the drill-down
    /// predicates and the user's own filter are both ordinary IR (GRP-5), and yet the two resolve
    /// their case sensitivity by different rules — GRP-2 for the group-key matches, SEM-1 for the
    /// user's own predicates. It is set once, by <see cref="RenderWhere"/>, on the context the
    /// drill-down subtree is rendered under, and is never re-derived from a node: the two halves are
    /// rendered as two separate walks precisely so that nothing downstream has to distinguish them by
    /// inspecting a tree they have both been merged into.</para>
    /// </summary>
    private readonly record struct Context(
        GridSchema Schema,
        ISqlDialect Dialect,
        ISqlParameterSink Parameters,
        bool IsGroupKeyMatch = false);

    // ---- grouping (BM-2) --------------------------------------------------------------------------

    /// <summary>
    /// GRP-3: what the statement selects.
    ///
    /// <list type="bullet">
    /// <item><description><b>Grouped level</b> — the group column aliased to its logical field name
    /// (always, even when the two coincide), then one aggregate per <c>valueCol</c> under its own
    /// output name. <see cref="GroupingPlan.Resolve"/> already rejects a request whose aggregation
    /// output name collides with this level's own group column — moved there in #1887's review of
    /// this method's own #1886 fix, once EF Core became a fourth backend the collision is reachable
    /// from (every backend's grid row is the identical flat, colId-keyed shape, so this was never
    /// really SQL-specific): by the time this method runs, <paramref name="grouping"/> is guaranteed to
    /// carry no such aggregation. See <see cref="ResolveGroupedSortTarget"/>'s remarks for the second,
    /// sharper failure this same shape produces in the <c>ORDER BY</c> — matched through the shared
    /// <see cref="GroupedSortTarget"/> helper, but still rendered and refused by each compiler's own
    /// <c>ResolveGroupedSortTarget</c> rather than by <see cref="GroupingPlan.Resolve"/> (that rejection
    /// depends on the request's <em>sort</em>, which this dispatch does not see).</description></item>
    /// <item><description><b>Drill-down leaf</b> — every declared field, in the schema's own
    /// declaration order, aliased back to its logical name only where the physical column differs.
    /// A grouping request's rows are named at every level, which <c>SELECT *</c> cannot do: it
    /// returns the physical column names, so a schema whose <c>fiscalYear</c> lives in
    /// <c>fiscal_year</c> would hand the grid a key it does not know.</description></item>
    /// <item><description><b>Export</b> (EXP-1(b), <see cref="SqlQueryRequest.Projection"/>) — the
    /// resolved export columns, in the order the request asked for them, under the same
    /// alias-only-where-it-differs rule as the leaf. The list arrives already resolved from the
    /// adapter, so this branch decides nothing about WHICH columns; it renders the ones it is
    /// given.</description></item>
    /// <item><description><b>Ordinary row query</b> — <c>SELECT *</c>, #1638's inherited form and
    /// GRP-3's explicit carve-out. Only an export widens it: <c>page-export/001</c>-<c>003</c> are
    /// the category's plain-paging baseline, carry no export field, and render <c>*</c> like every
    /// other row query in the suite.</description></item>
    /// </list>
    /// </summary>
    private static string RenderProjection(GroupingPlan? grouping, IReadOnlyList<string>? projection, Context context)
    {
        if (grouping is null)
        {
            return projection is null ? "*" : RenderColumnList(projection, context);
        }

        if (grouping.GroupColumn is { } groupColumn)
        {
            var items = new List<string> { Alias(ResolveColumn(groupColumn, context), groupColumn, context) };

            // No output-name-vs-group-column collision guard here: GroupingPlan.Resolve (Core) already
            // rejected it — Build calls it, above, strictly before this method is ever reached — so
            // `grouping.Aggregations` is provably free of one by the time this loop runs (#1887).
            foreach (var aggregation in grouping.Aggregations)
            {
                items.Add($"{AggregateCall(aggregation, context)} AS {context.Dialect.QuoteIdentifier(aggregation.OutputName)}");
            }

            return string.Join(", ", items);
        }

        // GRP-3's "in declaration order" comes from GridSchema.FieldOrder, never from Fields.Keys:
        // that dictionary's enumeration order is unspecified by .NET, and 005/006 compare this column
        // list byte-for-byte.
        return RenderColumnList(context.Schema.FieldOrder, context);
    }

    /// <summary>An ordered list of logical field names as a <c>SELECT</c> list, each aliased back to
    /// its logical name only where the physical column differs (<c>"fiscal_year" AS "fiscalYear"</c>,
    /// but plain <c>"region"</c>) — GRP-3's rule, shared by the drill-down leaf and EXP-1(b)'s export
    /// because they answer the same question about the same schema.</summary>
    private static string RenderColumnList(IReadOnlyList<string> fields, Context context)
    {
        var items = new List<string>(fields.Count);

        foreach (var field in fields)
        {
            var column = ResolveColumn(field, context);
            var alias = context.Dialect.QuoteIdentifier(field);
            items.Add(column == alias ? column : $"{column} AS {alias}");
        }

        return string.Join(", ", items);
    }

    private static string Alias(string expression, string logicalName, Context context) =>
        $"{expression} AS {context.Dialect.QuoteIdentifier(logicalName)}";

    /// <summary>The aggregate expression itself — <c>AVG("amount")</c>, or AGG-6's
    /// <c>COALESCE(SUM("amount"), 0)</c>. Composed in one place because it is emitted twice: once in
    /// the projection under its output name, and once in the <c>ORDER BY</c> (see
    /// <see cref="ResolveGroupedSortTarget"/> for why the ordering repeats the expression rather than
    /// referring back to the name) — so the wrap reaching both is a property of this method, not two
    /// call sites agreeing.
    ///
    /// <para><b>AGG-6, and the reason it is <c>sum</c> alone.</b> The rule and the whole argument for
    /// it live in <c>spec/semantics.md</c>; what a reader here needs is only that SQL is the one
    /// backend of four whose engine answer disagrees with it, and that <c>AVG</c>/<c>MIN</c>/<c>MAX</c>
    /// already agree and must therefore stay bare. Wrapping them too would read as tidier and would
    /// fabricate a <c>0</c> for a group that has nothing to average.</para></summary>
    private static string AggregateCall(Aggregation aggregation, Context context)
    {
        var call = $"{Function(aggregation.Func)}({ResolveColumn(aggregation.Field, context)})";

        // Two arguments and a literal zero, identical on all five dialects because it is ANSI — an
        // ISqlDialect member for it would be the duplicate-instead-of-share smell that interface's own
        // note warns about.
        return aggregation.Func is AggregationFunc.Sum ? $"COALESCE({call}, 0)" : call;
    }

    /// <summary>
    /// AR-8's closed v1 function set. These five spellings are ANSI SQL and identical on every
    /// dialect this project implements, which is why the aggregate call is composed here rather than behind
    /// an <see cref="ISqlDialect"/> member: an override point no dialect would ever use differently
    /// is the mirror image of the BM-1 smell — see <see cref="ISqlDialect"/>'s own note on why
    /// <c>IS NULL</c> and <c>= ''</c> likewise stay in the builder (with the one engine fact that
    /// decides whether the second appears at all arriving as
    /// <see cref="ISqlDialect.EmptyStringIsNull"/>, SQL-7).
    /// </summary>
    private static string Function(AggregationFunc func) => func switch
    {
        AggregationFunc.Sum => "SUM",
        AggregationFunc.Min => "MIN",
        AggregationFunc.Max => "MAX",
        AggregationFunc.Avg => "AVG",

        // AGG-1: COUNT(<field>) counts non-null occurrences of that field, never rows — SQL's own
        // COUNT(expr) already skips NULLs, so the portable form is simply never COUNT(*).
        AggregationFunc.Count => "COUNT",

        _ => throw new SqlCompilationException($"Unknown aggregation function '{func}'.")
    };

    // ---- filter tree ----------------------------------------------------------------------------

    /// <summary>
    /// GRP-5: the whole <c>WHERE</c> clause — the synthesised drill-down <c>and</c>-composed with the
    /// request's own filter, drill-down first, so the statement reads along the group path before it
    /// reads the user's own predicates. Nothing in the fixture suite pins that order (no case carries
    /// both), and GRP-5 states it rather than leaving a port to guess, because the choice is visible
    /// in <c>params</c>.
    ///
    /// <para><b>Why the two halves are composed here rather than merged into one tree and walked
    /// once.</b> They resolve case sensitivity by different rules (GRP-2 versus SEM-1), so a single
    /// walk over a merged tree needs some way to tell a group-key match from a user predicate that is
    /// spelled identically — and the only thing that can, once both are ordinary IR, is the node's
    /// reference identity. That is a non-local invariant with no guard: any later change that
    /// rebuilds nodes between synthesis and rendering (a flatten-nested-<c>and</c>s optimisation in
    /// <see cref="FilterTreeMerge"/>, or routing the group columns through
    /// <see cref="GridFilterPipeline"/>, whose <see cref="FieldAllowlistValidator.Strip"/> and
    /// <see cref="TypeCoercionValidator.Coerce"/> both do) would silently give the drill-down the
    /// user's mechanism, and <c>"EMEA"</c> would start matching <c>"emea"</c> with no exception and no
    /// failing artifact. Rendering each half under its own <see cref="Context"/> removes the
    /// invariant instead of documenting it; the composition below is exactly what
    /// <see cref="RenderComposite"/> produces for the equivalent <see cref="AndNode"/>, so the emitted
    /// text and the parameter order are unchanged.</para>
    /// </summary>
    private static string? RenderWhere(FilterNode? filter, FilterNode? drillDown, Context context)
    {
        // Rendered in this order, not merely joined in it: the parameter bag binds in call order, so
        // the drill-down's keys take the leading placeholders exactly as they would inside an AndNode.
        var groupPath = drillDown is null ? null : RenderNode(drillDown, context with { IsGroupKeyMatch = true });
        var userFilter = filter is null ? null : RenderNode(filter, context);

        return (groupPath, userFilter) switch
        {
            (null, null) => null,
            ({ } path, null) => path,
            (null, { } user) => user,

            // SQL-2's wrap, identical to the AndNode form: `(a AND b)`, children bare.
            ({ } path, { } user) => $"({path} AND {user})"
        };
    }

    private static string RenderNode(FilterNode node, Context context) =>
        node switch
        {
            AndNode and => RenderComposite(and, " AND ", context),
            OrNode or => RenderComposite(or, " OR ", context),
            NotNode not => RenderNot(not, context),
            ComparisonNode comparison => RenderComparison(comparison, context),
            _ => throw new SqlCompilationException($"Unknown FilterNode type '{node.GetType().Name}'.")
        };

    /// <summary>
    /// SQL-2: a composite is wrapped and its children are rendered bare — <c>(a AND b)</c>, never
    /// <c>(a) AND (b)</c>. A single-child composite still wraps (<c>(x)</c>), which is what makes
    /// <c>spec/fixtures/filter-tree/011</c>-<c>013</c>'s nesting depths reproducible rather than
    /// collapsed away.
    /// </summary>
    private static string RenderComposite(CompositeFilterNode composite, string separator, Context context)
    {
        var rendered = new List<string>(composite.Nodes.Count);
        foreach (var child in composite.Nodes)
        {
            rendered.Add(RenderNode(child, context));
        }

        return "(" + string.Join(separator, rendered) + ")";
    }

    /// <summary>
    /// SEM-2/SQL-2: a tree-level <c>NOT</c> is null-inclusive one syntax level up from the negative
    /// operators — <c>(NOT (&lt;child&gt;) OR &lt;col&gt; IS NULL [OR ...])</c>, with one disjunct per
    /// distinct field referenced anywhere in the child subtree, in first-appearance order. Without
    /// them, SQL's three-valued logic drops every NULL row from the negation, which is the exact bug
    /// SEM-2 exists to prevent — <c>NOT (col ILIKE ...)</c> and a bare <c>col &lt;&gt; ...</c> fail
    /// identically.
    ///
    /// <para>This is the one SEM-2 shape <see cref="SemanticsResolver"/> deliberately has no method
    /// for (see <see cref="SemanticsResolver.IsNullInclusive"/>'s own doc): it is a statement about
    /// the tree, not about an operator, so the compiler owns it.</para>
    /// </summary>
    private static string RenderNot(NotNode not, Context context)
    {
        // Rendered BEFORE the IS NULL disjuncts so the child's own parameters keep first-appearance
        // order; the disjuncts bind nothing.
        var child = RenderNode(not.Node, context);

        var negation = new StringBuilder("(NOT (").Append(child).Append(')');

        // WHICH fields get a disjunct, and in which order, is SEM-2's rule rather than this
        // compiler's: since #1645 the EF Core execution adapter emits the same fan-out over the same
        // tree (AR-4), and a second copy of the walk would diverge in the one direction nothing
        // catches — a missed field yields a valid query returning fewer rows. See
        // FilterNodeFields.DistinctInOrder.
        foreach (var field in FilterNodeFields.DistinctInOrder(not.Node))
        {
            negation.Append(" OR ").Append(ResolveColumn(field, context)).Append(" IS NULL");
        }

        return negation.Append(')').ToString();
    }

    private static string RenderComparison(ComparisonNode node, Context context)
    {
        var field = ResolveField(node.Field, context);
        var column = ResolveColumn(node.Field, context);

        return node.Op switch
        {
            ComparisonOperator.Blank => RenderBlank(column, field, context),
            ComparisonOperator.NotBlank => $"NOT ({RenderBlank(column, field, context)})",

            // AR-6's unary boolean shorthand carries no value of its own, so the compiler mints one
            // rather than inlining a `TRUE`/`FALSE` literal — SEC-2 wants every compared value bound,
            // and the fixtures pin the parameterized form (`"is_active" = $1`, params [true]).
            ComparisonOperator.True => RenderScalar(column, field, ComparisonOperator.Eq, new BooleanValue { Value = true }, context),
            ComparisonOperator.False => RenderScalar(column, field, ComparisonOperator.Eq, new BooleanValue { Value = false }, context),

            // GRP-7: an equality against a nullValue is the null test, exactly and with no parameter. It is how the null group of a
            // grouped level is expanded (DrillDownFilter), where `= NULL` would match no row. Only `eq`: GRP-5 emits nothing else.
            ComparisonOperator.Eq when node.Value is NullValue => $"{column} IS NULL",

            ComparisonOperator.Eq or ComparisonOperator.Neq
                or ComparisonOperator.Gt or ComparisonOperator.Gte
                or ComparisonOperator.Lt or ComparisonOperator.Lte =>
                NullInclusive(RenderScalar(column, field, node.Op, RequireValue(node), context), node.Op, column),

            ComparisonOperator.Contains or ComparisonOperator.NotContains
                or ComparisonOperator.StartsWith or ComparisonOperator.EndsWith =>
                NullInclusive(RenderSubstring(column, field, node, context), node.Op, column),

            // SEM-8: an empty list is a constant, never `IN ()` and never a bound array; the constant is already
            // true for NULL rows (notIn) or false for them (in), so no null disjunct is added.
            ComparisonOperator.In or ComparisonOperator.NotIn when node.Values is { Count: 0 } =>
                node.Op == ComparisonOperator.NotIn ? "1 = 1" : "1 = 0",

            ComparisonOperator.In or ComparisonOperator.NotIn =>
                NullInclusive(RenderSet(column, field, node, context), node.Op, column),

            ComparisonOperator.InRange => RenderRange(column, field, node, context),

            _ => throw new SqlCompilationException($"Unknown comparison operator '{node.Op}'.")
        };
    }

    /// <summary>
    /// SEM-2/SQL-2: a negative operator's match set includes NULL-valued rows, and the resulting
    /// disjunction is ALWAYS wrapped — even when it is the whole <c>WHERE</c> clause. The
    /// unconditional wrap is what makes the leaf safe to drop into any parent without the parent
    /// knowing what it contains; a top-level <c>OR</c> left bare inside an <c>AND</c> parent is a
    /// silent correctness bug, and wrapping always removes the entire class.
    /// </summary>
    private static string NullInclusive(string predicate, ComparisonOperator op, string column) =>
        SemanticsResolver.IsNullInclusive(op) ? $"({predicate} OR {column} IS NULL)" : predicate;

    /// <summary>
    /// SEM-2: <c>blank</c> is <c>IS NULL OR = ''</c> for a text field and <c>IS NULL</c> for every
    /// other type. <c>notBlank</c> negates THIS text literally (giving the doubled parentheses in the
    /// string case, SQL-2) rather than re-deriving <c>IS NOT NULL AND &lt;&gt; ''</c> independently,
    /// so the two can never drift apart at the edges.
    ///
    /// <para>SQL-7: on an engine that treats <c>''</c> as NULL the text arm collapses to the
    /// non-text one, because the <c>= ''</c> disjunct is not merely redundant there but UNKNOWN for
    /// every row — which leaves <c>notBlank</c> matching nothing at all. That is the single engine
    /// fact <see cref="ISqlDialect.EmptyStringIsNull"/> supplies; the composition stays here, so
    /// <c>blank</c> and <c>notBlank</c> still cannot disagree on any dialect. Note this is NOT a
    /// dialect-specific branch of the BM-1 kind: the builder asks a question and never learns which
    /// engine answered it.</para>
    /// </summary>
    private static string RenderBlank(string column, FieldConfig field, Context context) =>
        SemanticsResolver.ResolveBlankCondition(field.Type) switch
        {
            SemanticsResolver.BlankCondition.NullOrEmptyString when !context.Dialect.EmptyStringIsNull =>
                $"({column} IS NULL OR {column} = '')",
            SemanticsResolver.BlankCondition.NullOrEmptyString or SemanticsResolver.BlankCondition.NullOnly =>
                $"{column} IS NULL",
            var condition => throw new SqlCompilationException($"Unknown blank condition '{condition}'.")
        };

    /// <summary>
    /// SEM-1: the resolver decides HOW the comparison treats case and, when it folds it, BY WHICH
    /// MECHANISM; the dialect only spells that decision. The three-valued answer is passed through
    /// intact — collapsing it to "insensitive or not" here is exactly the conflation that let a
    /// schema-declared case-SENSITIVE field render bare on an engine whose default collation folds
    /// case (see <see cref="SemanticsResolver.CaseSensitivityMode"/>).
    ///
    /// <para><paramref name="family"/> is the mechanism family the CALLER is about to render, and
    /// mismatching it is a compiler bug rather than a client error: an insensitive field whose
    /// operator resolves to <see cref="SemanticsResolver.CaseSensitivityMechanism.PatternMatch"/> must
    /// never reach the collation rendering, and vice versa. It is unreachable by construction — the
    /// scalar/set call sites only ever pass SEM-1's collation-family operators and the substring one
    /// only its pattern-family operators — so it fails loudly instead of silently degrading to "no
    /// mechanism", which would be a plausible-looking artifact that folds case in the wrong place.</para>
    ///
    /// <para>A predicate inside the synthesised drill-down is not a filter at all: it is a group-key
    /// MATCH, and GRP-2 requires it to agree with the <c>GROUP BY</c> that produced the bucket label
    /// being expanded — otherwise expanding <c>"EMEA"</c> also pulls <c>"emea"</c>'s rows and the
    /// children stop summing to the parent's total. It therefore resolves through
    /// <see cref="SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity"/>, in this one place
    /// rather than at each call site, so there is a single answer to "does this fold case". The
    /// provenance comes from <see cref="Context.IsGroupKeyMatch"/>, which
    /// <see cref="RenderWhere"/> sets on the walk it starts over the drill-down — never inferred from
    /// the node itself.</para>
    /// </summary>
    private static SemanticsResolver.CaseSensitivityMode ResolveCaseSensitivity(
        FieldConfig field, ComparisonOperator op, SemanticsResolver.CaseSensitivityMechanism family, Context context)
    {
        if (context.IsGroupKeyMatch)
        {
            return SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(field, SemanticsResolver.GroupingMode.Grouped)
                .Mode;
        }

        var decision = SemanticsResolver.ResolveCaseSensitivity(field, op);

        if (decision.Mode == SemanticsResolver.CaseSensitivityMode.Insensitive && decision.Mechanism != family)
        {
            throw new SqlCompilationException(
                $"Operator '{op}' resolves to the '{decision.Mechanism}' case-insensitivity mechanism, but is being " +
                $"rendered through the '{family}' family — SEM-1 requires one mechanism per field across every context.");
        }

        return decision.Mode;
    }

    private static string RenderScalar(string column, FieldConfig field, ComparisonOperator op, TypedValue value, Context context)
    {
        var caseSensitivity = ResolveCaseSensitivity(field, op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        return context.Dialect.RenderScalarComparison(
            column, ScalarComparison(op), EncodeValue(value, field, context.Dialect, BoundRounding(op)), field.Type, caseSensitivity,
            context.Parameters);
    }

    /// <summary>
    /// SEM-4 (SQLite): how a sub-millisecond datetime bound is rounded to the stored millisecond, by the operator
    /// that compares it. <c>gt</c>/<c>lte</c> floor, <c>gte</c>/<c>lt</c> ceil, everything else keeps the full value.
    /// <c>inRange</c> reaches here through its two bounds' own operators, so inclusivity decides each side.
    /// Only a dialect with <see cref="ISqlDialect.DatetimeBoundsAreFixedWidth"/> acts on it.
    /// </summary>
    private static BoundRoundingMode BoundRounding(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Gt or ComparisonOperator.Lte => BoundRoundingMode.Floor,
        ComparisonOperator.Gte or ComparisonOperator.Lt => BoundRoundingMode.Ceiling,
        _ => BoundRoundingMode.None
    };

    private enum BoundRoundingMode { None, Floor, Ceiling }

    private static string RenderSubstring(string column, FieldConfig field, ComparisonNode node, Context context)
    {
        var caseSensitivity = ResolveCaseSensitivity(field, node.Op, SemanticsResolver.CaseSensitivityMechanism.PatternMatch, context);

        // There is no portable meaning for "does this number contain that substring", and guessing
        // one (casting the column to text) would silently change both semantics and index usage. The
        // DECLARED type is what decides that — checked first and separately from the value's variant,
        // because a caller that skipped SEM-5 coercion can hand a StringValue to an int64/date field,
        // and rendering it would produce a case-SENSITIVE substring match against a numeric column
        // (SemanticsResolver only resolves the pattern-match mechanism for a `string` field) — a
        // plausible-looking artifact that is exactly the guess this refuses to make. This is the one
        // operator path that never reaches EncodeValue, so it carries its own type check.
        if (field.Type != FieldType.String)
        {
            throw new SqlCompilationException(
                $"Field '{node.Field}' is declared '{field.Type}', but operator '{node.Op}' is a substring match " +
                "and only has a defined rendering against a 'string' field.");
        }

        if (RequireValue(node) is not StringValue pattern)
        {
            throw new SqlCompilationException(
                $"Operator '{node.Op}' on field '{node.Field}' is a substring match, so its value must be a " +
                "stringValue — run TypeCoercionValidator (SEM-5) before compiling.");
        }

        return context.Dialect.RenderSubstringMatch(
            column, SubstringAnchor(node.Op), negated: node.Op == ComparisonOperator.NotContains,
            pattern.Value, caseSensitivity, context.Parameters);
    }

    private static string RenderSet(string column, FieldConfig field, ComparisonNode node, Context context)
    {
        var caseSensitivity = ResolveCaseSensitivity(field, node.Op, SemanticsResolver.CaseSensitivityMechanism.Collation, context);

        var values = node.Values
            ?? throw new SqlCompilationException($"Operator '{node.Op}' on field '{node.Field}' requires 'values'.");

        var encoded = new List<object?>(values.Count);
        foreach (var value in values)
        {
            encoded.Add(EncodeValue(value, field, context.Dialect));
        }

        return context.Dialect.RenderSetMembership(column, negated: node.Op == ComparisonOperator.NotIn, encoded, field.Type, caseSensitivity, context.Parameters);
    }

    /// <summary>
    /// SEM-4: <c>inRange</c> compiles to the two bounds' own comparisons, each spelled from its
    /// EXPLICIT inclusivity flag — never a guessed default — composed with the same wrapped-composite
    /// shape SQL-2 gives an <c>and</c> node.
    /// </summary>
    private static string RenderRange(string column, FieldConfig field, ComparisonNode node, Context context)
    {
        if (node.From is null || node.To is null || node.FromInclusive is null || node.ToInclusive is null)
        {
            throw new SqlCompilationException(
                $"Operator 'inRange' on field '{node.Field}' requires 'from', 'to', 'fromInclusive' and 'toInclusive'.");
        }

        var lower = RenderScalar(column, field, node.FromInclusive.Value ? ComparisonOperator.Gte : ComparisonOperator.Gt, node.From, context);
        var upper = RenderScalar(column, field, node.ToInclusive.Value ? ComparisonOperator.Lte : ComparisonOperator.Lt, node.To, context);

        return $"({lower} AND {upper})";
    }

    private static TypedValue RequireValue(ComparisonNode node) =>
        node.Value ?? throw new SqlCompilationException($"Operator '{node.Op}' on field '{node.Field}' requires 'value'.");

    private static SqlScalarComparison ScalarComparison(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Eq => SqlScalarComparison.Equal,
        ComparisonOperator.Neq => SqlScalarComparison.NotEqual,
        ComparisonOperator.Gt => SqlScalarComparison.GreaterThan,
        ComparisonOperator.Gte => SqlScalarComparison.GreaterThanOrEqual,
        ComparisonOperator.Lt => SqlScalarComparison.LessThan,
        ComparisonOperator.Lte => SqlScalarComparison.LessThanOrEqual,
        _ => throw new SqlCompilationException($"Operator '{op}' is not a scalar comparison.")
    };

    private static SqlSubstringAnchor SubstringAnchor(ComparisonOperator op) => op switch
    {
        ComparisonOperator.Contains or ComparisonOperator.NotContains => SqlSubstringAnchor.Anywhere,
        ComparisonOperator.StartsWith => SqlSubstringAnchor.Start,
        ComparisonOperator.EndsWith => SqlSubstringAnchor.End,
        _ => throw new SqlCompilationException($"Operator '{op}' is not a substring match.")
    };

    // ---- ORDER BY -------------------------------------------------------------------------------

    /// <summary>
    /// SEM-6/SEM-3: the request's own keys in order, then a trailing tiebreaker (unless the sort
    /// already reaches it, after SEM-6's reduction), each key carrying its explicit <see cref="NullsPosition"/>. Never empty —
    /// the tiebreaker guarantees at least one key, so every compiled query has a total, reproducible
    /// order and server-side paging is stable.
    ///
    /// <para>GRP-4: on a grouped level the tiebreaker is the <em>group column</em>, not the schema's
    /// <see cref="GridSchema.StableKey"/>. The stable key is not in the grouped projection at all, so
    /// ordering by it is not merely undesirable but invalid SQL; the group column takes its place and
    /// plays the same role exactly, since its values are unique across the result rows by
    /// construction. The drill-down leaf projects rows, so it keeps SEM-6's stable key
    /// unchanged.</para>
    ///
    /// <para>SEM-6: the APPENDED tiebreaker resolves exact whatever the query's shape — it establishes
    /// row identity rather than comparing text, and collating it under a non-deterministic collation
    /// would leave the very ties it exists to break unbroken. That is a semantics decision, so it is
    /// made by <see cref="SemanticsResolver.ResolveOrderingAndGroupKeyCaseSensitivity"/> from the
    /// provenance this method reports, never re-derived here by comparing the last key's field to the
    /// stable key.</para>
    /// </summary>
    private static string RenderOrderBy(IReadOnlyList<SortItem>? sort, GroupingPlan? grouping, Context context)
    {
        var groupColumn = grouping?.GroupColumn;
        var keys = SemanticsResolver.AppendStableKeyTiebreaker(
            sort, context.Schema, groupColumn, out var tiebreakerAppended,
            aggregateColumnIds: grouping?.Aggregations.Select(aggregation => aggregation.ColumnId).ToArray());

        // GRP-2, at its narrowed scope: exactness covers the protocol's OWN keys, and a grouped
        // level's ORDER BY is one of them — it orders the very buckets the GROUP BY produced, so it
        // has to agree with it. A drill-down LEAF has no GROUP BY and no buckets: it orders raw rows
        // by whatever column the user picked, which need not be a group column at all
        // (spec/fixtures/group-aggregation/005 sorts on `product`, neither a group column nor a group
        // key). Nothing about bucket identity is at stake there, so it is an ordinary query in this
        // respect and SEM-1 governs it — which also stops a leaf that filters and sorts the SAME
        // field from spelling two different mechanisms in one statement, the mix SEM-1 forbids
        // outright. The drill-down WHERE stays exact either way; that is the provenance decision
        // ResolveCaseSensitivity makes, not this one.
        var ordering = groupColumn is null
            ? SemanticsResolver.GroupingMode.Ungrouped
            : SemanticsResolver.GroupingMode.Grouped;

        var rendered = new List<string>(keys.Count);
        var orderedColumns = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i < keys.Count; i++)
        {
            var key = keys[i];

            var (column, field) = groupColumn is null
                ? (ResolveColumn(key.Field, context), ResolveField(key.Field, context))
                : ResolveGroupedSortTarget(key.Field, groupColumn, grouping!.Aggregations, context);

            // The tiebreaker is always the LAST key when there is one — SEM-6's own rule, which
            // AppendStableKeyTiebreaker enforced above.
            var provenance = tiebreakerAppended && i == keys.Count - 1
                ? SemanticsResolver.SortKeyProvenance.AppendedTiebreaker
                : SemanticsResolver.SortKeyProvenance.Request;

            var caseSensitivity = SemanticsResolver
                .ResolveOrderingAndGroupKeyCaseSensitivity(field, ordering, provenance)
                .Mode;

            // #2809 (SEM-6's exception): the appended exact tiebreaker on a column an earlier key already orders by. SQL Server refuses
            // one expression twice (error 169) and accepts the second spelled with a collation, so the repeated tiebreaker is
            // rendered with the field's case-SENSITIVE mechanism (SC-3's own spelling, the dialect's collation where it has one), which is
            // also what makes it exact on an engine whose default folds case. The dialect renders it; nothing here names a collation.
            var firstUseOfColumn = orderedColumns.Add(column);
            if (provenance == SemanticsResolver.SortKeyProvenance.AppendedTiebreaker && !firstUseOfColumn && field.Type == FieldType.String)
            {
                caseSensitivity = SemanticsResolver.CaseSensitivityMode.Sensitive;
            }

            rendered.Add(context.Dialect.RenderSortKey(column, key.Direction, key.NullsPosition, caseSensitivity));
        }

        return string.Join(", ", rendered);
    }

    /// <summary>
    /// AR-9/GRP-4: what a grouped level's sort key actually orders by. A grouped statement can only
    /// order by something it produces, which is the group column or one of the aggregates — never
    /// the raw aggregated column (<c>ORDER BY "amount"</c> is not in the projection and would be
    /// invalid).
    ///
    /// <para><b>The ordering repeats the aggregate EXPRESSION — <c>SUM("amount")</c>, or
    /// <c>COALESCE(SUM("amount"), 0)</c> for a <c>sum</c> since AGG-6 (<see cref="AggregateCall"/>
    /// applies uniformly to the projection and the <c>ORDER BY</c>, so the two can never disagree) —
    /// rather than referring back to its select-list alias.</b> An output name is only conditionally usable in
    /// <c>ORDER BY</c>: PostgreSQL's <c>SELECT</c> documentation states that an output column name
    /// "has to stand alone, that is, it cannot be used in an expression", and T-SQL binds the same
    /// way — an alias inside a <c>CASE</c> resolves against the <c>FROM</c> scope and raises "Invalid
    /// column name". That matters here and not in the projection because SEM-3's null placement is
    /// EMULATED on two of the five dialects: <see cref="MssqlDialect"/> wraps every sort key in
    /// <c>CASE WHEN … IS NULL</c> and <see cref="MySqlDialect"/> in <c>ISNULL(…)</c>, so on those two
    /// the ordering target is never standing alone. Emitting the expression is unambiguously legal in
    /// both positions on every engine, so it is done uniformly rather than only where the wrapper
    /// forces it — a per-dialect split here would be a semantic difference dressed as a spelling one,
    /// which is exactly what <see cref="ISqlDialect"/>'s seam exists to keep out.</para>
    ///
    /// <para>The match is against <see cref="Aggregation.ColumnId"/>, AGG-2's <c>ColumnVO.id</c>
    /// reconstructed: the grid sends the <em>column's</em> id in <c>sortModel</c>, and AGG-2 sets
    /// <see cref="Aggregation.Alias"/> from that id exactly when it differs from the field. Note it is
    /// NOT <see cref="Aggregation.OutputName"/> — the two coincide only when an alias is set, and an
    /// unaliased aggregation's column id is the bare field while its output name is
    /// <c>&lt;field&gt;_&lt;func&gt;</c>. Anything else is rejected rather than rendered — a
    /// plausible-looking statement the engine refuses is worse than a compiler error naming the
    /// reason.</para>
    ///
    /// <para><b>More than one match is that same rejection, not a pick.</b> #1886's output-name
    /// uniqueness does not imply column-id uniqueness (see <see cref="GroupedSortTarget"/>'s own
    /// remarks): two unaliased functions over one field share a column id while resolving to distinct,
    /// legal output names. The FIRST match here used to win silently; now every match is required to
    /// be the only one.</para>
    ///
    /// <para><b>A match among the aggregations does not end the check either — the group column
    /// itself is a candidate too</b>, and matching both is the same silent-pick failure one register
    /// up: a request that groups by field X and also aggregates X unaliased (or aliases an aggregate
    /// explicitly back onto X) makes <c><paramref name="sortField"/> == <paramref name="groupColumn"/></c>
    /// true at the same time an aggregation's <see cref="Aggregation.ColumnId"/> matches it. This
    /// method used to return the aggregate the moment it found one, without ever asking whether the
    /// group column matched too — the exact shape of bug #1886 (Mongo's copy has the identical
    /// ordering). SEM-6's own tiebreaker is what reaches this branch on the most ordinary grouped
    /// request of all (no explicit sort, tiebreaker alone): it is minted from
    /// <paramref name="groupColumn"/> precisely because the group column's values are unique per
    /// bucket by construction, so silently redirecting it to an aggregate defeats the one guarantee it
    /// exists to provide. <see cref="GroupedSortTarget.MatchesGroupColumnToo"/> is the shared check,
    /// since Mongo's compiler needed the identical fix.</para>
    /// </summary>
    private static (string Column, FieldConfig Field) ResolveGroupedSortTarget(
        string sortField, string groupColumn, IReadOnlyList<Aggregation> aggregations, Context context)
    {
        var matches = GroupedSortTarget.MatchingByColumnId(sortField, aggregations);

        if (matches.Count > 1)
        {
            throw new SqlCompilationException(
                $"Ambiguous ORDER BY target for a grouped level. {GroupedSortTarget.DescribeAmbiguity(sortField, matches)}");
        }

        if (GroupedSortTarget.MatchesGroupColumnToo(sortField, groupColumn, matches))
        {
            throw new SqlCompilationException(
                $"Ambiguous ORDER BY target for a grouped level. {GroupedSortTarget.DescribeGroupColumnAmbiguity(sortField, matches)}");
        }

        if (matches.Count == 1)
        {
            return (AggregateCall(matches[0], context), ResolveField(matches[0].Field, context));
        }

        if (sortField == groupColumn)
        {
            return (ResolveColumn(sortField, context), ResolveField(sortField, context));
        }

        throw new SqlCompilationException(
            $"A grouped query can be ordered only by its group column ('{groupColumn}') or by one of its " +
            $"aggregations, but the request sorts on '{sortField}', which the grouped projection does not contain.");
    }

    // ---- paging ---------------------------------------------------------------------------------

    /// <summary>
    /// AG-3/EXP-2: resolves a <see cref="PageSpec"/> to the row window a paging clause renders —
    /// <see langword="null"/> for <see cref="NonePage"/> (no clause at all), otherwise the offset and
    /// the row count.
    ///
    /// <para>The subtraction is deliberately NOT a dialect's job. That
    /// <see cref="RangePage.EndRow"/> is <em>exclusive</em> is a semantic fact about the AG Grid
    /// request contract, not a spelling, and a dialect that bound <c>EndRow</c> instead would emit a
    /// perfectly plausible statement returning the wrong rows — the failure mode
    /// <see cref="ISqlDialect"/>'s "rendering only, never semantics" line exists to prevent, and one
    /// that would otherwise be re-typed into each of #1639's four dialects.</para>
    /// </summary>
    private static (int Offset, int Limit)? ResolveRowWindow(PageSpec page) => page switch
    {
        NonePage => null,
        RangePage range => (range.StartRow, range.EndRow - range.StartRow),
        _ => throw new SqlCompilationException($"Unknown PageSpec type '{page.GetType().Name}'.")
    };

    // ---- schema resolution ----------------------------------------------------------------------

    private static FieldConfig ResolveField(string field, Context context) =>
        context.Schema.Fields.TryGetValue(field, out var config)
            ? config
            : throw new SqlCompilationException(
                $"Field '{field}' is not declared in the GridSchema (SC-1/SC-2) — a compiler is reached only after " +
                "FieldAllowlistValidator, so this is a caller precondition failure, not a client error.");

    /// <summary>
    /// SC-4: the field's physical SQL column, quoted per SQL-1. A field with no
    /// <see cref="PhysicalMapping"/> at all falls back to its own colId, which is the identity
    /// mapping the schema is implicitly declaring by omitting one.
    /// </summary>
    private static string ResolveColumn(string field, Context context)
    {
        var mapping = ResolveField(field, context).Physical?.Sql;

        if (mapping is null)
        {
            return context.Dialect.QuoteIdentifier(field);
        }

        // #1638 deliberately implements only the plain `column` form: 752/752 field declarations in
        // spec/fixtures/ use it, so the other two SqlMapping shapes have no oracle at all and any
        // rendering chosen for them here would be unverifiable guesswork (does `qualifiedColumn`
        // quote both halves? does `expression` get parenthesised? does a collation attach to it?).
        // Rejecting cleanly keeps the gap visible until fixtures exist for it.
        if (mapping.QualifiedColumn is not null)
        {
            throw new SqlCompilationException(
                $"Field '{field}' declares physical.sql.qualifiedColumn, which this compiler does not implement " +
                "(#1638: no conformance fixture pins its rendering — see spec/fixtures/, where every field uses " +
                "the plain 'column' form).");
        }

        if (mapping.Expression is not null)
        {
            throw new SqlCompilationException(
                $"Field '{field}' declares physical.sql.expression, which this compiler does not implement " +
                "(#1638: no conformance fixture pins its rendering — see spec/fixtures/, where every field uses " +
                "the plain 'column' form).");
        }

        return context.Dialect.QuoteIdentifier(mapping.Column ?? field);
    }

    // ---- parameter encoding ---------------------------------------------------------------------

    /// <summary>
    /// AR-7/SEM-4: turns a <see cref="TypedValue"/> into the CLR value bound as a parameter. The one
    /// non-obvious case is <see cref="DecimalValue"/>, which stays a <see cref="string"/>: it and
    /// <see cref="DoubleValue"/> are the same wire shape and differ only by the schema's declared
    /// type, so binding a decimal through a floating type would be a silent precision loss no test
    /// output would show. <paramref name="field"/> is taken for that reason — the declared type, not
    /// the value's surface shape, is the authority — and is asserted against the value here rather
    /// than trusted, since a caller may have skipped <see cref="TypeCoercionValidator"/>.
    /// </summary>
    private static object? EncodeValue(TypedValue value, FieldConfig field, ISqlDialect dialect, BoundRoundingMode rounding = BoundRoundingMode.None)
    {
        RequireDeclaredType(value, field);

        return value switch
        {
            StringValue s => s.Value,
            Int64Value i => i.Value,
            DecimalValue d => d.Value,
            DoubleValue d => d.Value,
            BooleanValue b => b.Value,
            DateValue d => d.Value,
            DatetimeValue dt => NormalizeInstant(dt.Value, dialect.DatetimeBoundsAreFixedWidth, rounding),

            // AR-7's nullValue. An eq against it never reaches here: GRP-7 renders it as IS NULL. The other
            // operators bind it as a NULL parameter, which matches no row under SQL's three-valued logic.
            NullValue => null,

            _ => throw new SqlCompilationException($"Unknown TypedValue type '{value.GetType().Name}'.")
        };
    }

    /// <summary>
    /// SEM-4: a <c>datetime</c> parameter is the absolute instant, normalised to UTC with a trailing
    /// <c>Z</c>, and the <see cref="DatetimeValue.Zone"/> is NOT carried into the SQL or the
    /// parameter — it is provenance recording how the wire string was resolved, never an instruction
    /// to the database. Normalising rather than emitting the value verbatim is what stops the same
    /// instant written <c>+02:00</c> and written <c>Z</c> from producing two different artifacts.
    /// Sub-second precision is preserved when present, and dropped from the text when absent, so the
    /// common whole-second case round-trips to exactly the form the fixtures pin. On a dialect whose
    /// <see cref="ISqlDialect.DatetimeBoundsAreFixedWidth"/> is true (SQLite, which compares the column
    /// as text) a whole-millisecond instant is spelled with exactly three fractional digits instead, and a sub-millisecond one is
    /// first rounded to the millisecond by the comparing operator (<paramref name="rounding"/>).
    ///
    /// <para><b>Load-bearing dependency:</b> this is safe from local-time drift only because
    /// <see cref="Build"/> runs <see cref="FilterNodeValidator"/> first, and its
    /// <c>DatetimePattern</c> mandates a trailing <c>Z</c> or an explicit offset. Without that
    /// guarantee the parse would assume the MACHINE's local zone for a zone-less string, and the same
    /// fixture would compile to a different instant on a different host. That parse is
    /// <see cref="IsoInstant.TryParseUtc"/> since #1645 — the EF Core execution adapter reads the
    /// same value as a <see cref="DateTime"/> it hands a provider, and AR-4 makes "which instant is
    /// this?" a question the two paths may not answer separately. Only the TEXT below is this
    /// compiler's, because only its artifacts pin one.</para>
    /// </summary>
    private static string NormalizeInstant(string value, bool fixedWidth, BoundRoundingMode rounding)
    {
        // Zone-less input cannot reach here — FilterNodeValidator (run by Build) rejects it — which
        // is what makes the local-time assumption inside TryParseUtc unreachable rather than merely
        // unlikely. The failure is reported in THIS compiler's vocabulary, which is why the shared
        // helper is a Try- method rather than a throwing one.
        if (!IsoInstant.TryParseUtc(value, out var utc))
        {
            throw new SqlCompilationException(
                $"datetimeValue '{value}' is not an ISO-8601 instant (FilterNodeValidator should have rejected it upstream).");
        }

        // SEM-4 (SQLite): a text-comparing engine needs the stored width, three fractional digits. Stored values are
        // millisecond-aligned, so a sub-millisecond bound is rounded by its operator (x > b <=> s > floor(b),
        // x <= b <=> s <= floor(b), x >= b <=> s >= ceil(b), x < b <=> s < ceil(b)); eq / neq / set membership keep
        // the full value, which can never equal a stored one.
        if (fixedWidth && rounding != BoundRoundingMode.None && utc.Ticks % TimeSpan.TicksPerMillisecond != 0)
        {
            var floorTicks = utc.Ticks - utc.Ticks % TimeSpan.TicksPerMillisecond;
            utc = new DateTime(rounding == BoundRoundingMode.Floor ? floorTicks : floorTicks + TimeSpan.TicksPerMillisecond, DateTimeKind.Utc);
        }

        var format = fixedWidth && utc.Ticks % TimeSpan.TicksPerMillisecond == 0 ? "yyyy-MM-dd'T'HH:mm:ss.fff'Z'"
            : utc.Ticks % TimeSpan.TicksPerSecond == 0 ? "yyyy-MM-dd'T'HH:mm:ss'Z'"
            : "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF'Z'";
        return utc.ToString(format, CultureInfo.InvariantCulture);
    }

    /// <summary>
    /// Defense in depth against a caller that skipped SEM-5 coercion: binding a value whose variant
    /// disagrees with the field's declared type is precisely the <c>decimal</c>-vs-<c>double</c>
    /// silent-divergence risk <see cref="EncodeValue"/> exists to prevent, so it fails loudly here
    /// instead of producing a plausible-looking artifact. <see cref="NullValue"/> is accepted against
    /// any declared type, matching <see cref="TypeCoercionValidator"/>'s own rule.
    /// </summary>
    private static void RequireDeclaredType(TypedValue value, FieldConfig field)
    {
        var matches = (value, field.Type) switch
        {
            (NullValue, _) => true,
            (StringValue, FieldType.String) => true,
            (Int64Value, FieldType.Int64) => true,
            (DecimalValue, FieldType.Decimal) => true,
            (DoubleValue, FieldType.Double) => true,
            (BooleanValue, FieldType.Boolean) => true,
            (DateValue, FieldType.Date) => true,
            (DatetimeValue, FieldType.Datetime) => true,
            _ => false
        };

        if (!matches)
        {
            throw new SqlCompilationException(
                $"A '{value.GetType().Name}' cannot be bound against a field declared '{field.Type}' — run " +
                "TypeCoercionValidator (SEM-5) before compiling.");
        }
    }
}
