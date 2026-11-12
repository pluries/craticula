using Craticula.Core.Ir;
using Microsoft.EntityFrameworkCore;

namespace Craticula.EntityFrameworkCore;

/// <summary>
/// The <b>grid</b> entry point: one page of rows for an AG Grid SSRM block, optionally with the
/// filtered total.
///
/// <para><b>Why this is a separate type from <see cref="EfCoreExportStream"/> rather than a mode of one
/// entry point.</b> The two answer the same IR against the same table and differ in exactly one thing
/// that matters: this one may use <c>OFFSET</c> and the export path may not (EXP-3). A single method
/// with a flag would put that distinction in a boolean somebody can pass wrongly, and the symptom —
/// an export that OFFSET-walks — is not an error but a download that gets quadratically slower and
/// still returns the right bytes on the small dataset a test would use. Two types make the rule
/// structural: this one calls <c>ApplyRowWindow</c>, that one has no offset to give it, and a test
/// reads its source to prove <c>Skip</c> never appears there.</para>
///
/// <para>It is also the shape of the difference in the request: a grid page is defined BY its
/// <see cref="Craticula.Core.Ir.RangePage"/>, while an export's page is EXP-2's
/// <see cref="Craticula.Core.Ir.NonePage"/> and its chunking is the adapter's own concern rather than
/// the client's.</para>
/// </summary>
public static class EfCoreGridQuery
{
    /// <summary>
    /// Compiles and executes one grid page: filter, order, row window, projection.
    ///
    /// <para>The clause order is the order a reader of <c>SqlQueryBuilder.Build</c> would expect, and
    /// two of the four steps are not interchangeable. The row window must come after the ordering (a
    /// <c>Skip</c>/<c>Take</c> over an unordered query returns an arbitrary page — which is what SEM-6's
    /// tiebreaker exists to prevent, and why <c>ApplyOrdering</c> can never return an empty key list),
    /// and the projection must come last so that a field the request sorts or filters on but does not
    /// project is still available to the clauses that need it.</para>
    ///
    /// <para><b>#1887: dispatches internally on <see cref="GroupingPlan.Resolve"/>.</b> No new public
    /// entry point and no change to <see cref="EfCoreGridPage"/>'s shape: a drill-down leaf still
    /// compiles through the ordinary per-row pipeline above, and a grouped level's
    /// <c>Columns</c> is <c>[groupColumn, ...aggregations.Select(a =&gt; a.OutputName)]</c>, which
    /// <c>Columns</c> + <c>Rows</c> + <c>RowCount</c> already fit without a new member.</para>
    /// </summary>
    /// <param name="source">The <c>FROM</c> target — a <c>DbSet</c>, or
    /// <see cref="GridSchemaPropertyBag.Query"/> for a host with no entity classes. Any EF global query
    /// filter already on it composes with everything below, which is AR-4's reason for existing.</param>
    /// <param name="request">The validated IR. Its <see cref="EfCoreQueryRequest.Page"/> is honoured
    /// here, unlike on the export path.</param>
    /// <param name="semantics">The five engine facts SEM-1/SEM-7/SEC-4/SQL-7 need.</param>
    /// <param name="includeRowCount">Whether to also run the count query
    /// (<see cref="EfCoreGridPage.RowCount"/>). Defaults to <see langword="false"/>: it is a second
    /// round trip, and a grid needs the total once per filter change rather than once per block.</param>
    /// <param name="cancellationToken">EXP-7's cancellation hook, observed by both queries.</param>
    public static Task<EfCoreGridPage> FetchPageAsync<TRow>(
        IQueryable<TRow> source,
        EfCoreQueryRequest request,
        EfCoreProviderSemantics semantics,
        bool includeRowCount = false,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(semantics);

        // PG-5: every row is read by streaming; a paged call never loads the whole result.
        if (request.Page is NonePage)
        {
            throw new EfCoreCompilationException(
                "FetchPageAsync returns one window of rows and refuses EXP-2's unpaginated page, which would load " +
                "every row into memory (PG-5). Read every row with EfCoreExportStream.StreamAsync.");
        }

        // Mirrors Craticula.Sql.SqlQueryBuilder.Build's identical guard: EXP-1's group-export
        // carve-out means AgGridRequestParser has already nulled the group state on any export, so
        // the two are mutually exclusive by construction — checked rather than assumed, since a
        // caller building the request by hand could set both, and there is no defined shape for
        // "project these columns" over a grouped level that projects a bucket key and its aggregates.
        if (request.Projection is not null && request.Group is not null)
        {
            throw new EfCoreCompilationException(
                "A request carries both a GroupSpec and an EXP-1(b) export projection. An export emits leaf rows " +
                "and discards group state (EXP-1's carve-out, applied by AgGridRequestParser), so the two never " +
                "arrive together from the adapter.");
        }

        var grouping = GroupingPlan.Resolve(request.Group, request.Aggregations);

        return grouping switch
        {
            null => FetchUngroupedPageAsync(source, request, semantics, includeRowCount, cancellationToken),

            // GRP-1: every group column consumed — the drill-down leaf, raw rows restricted by the
            // already-consumed groupKeys.
            { GroupColumn: null } => FetchDrillDownLeafPageAsync(source, request, semantics, grouping, includeRowCount, cancellationToken),

            // A grouped level: GroupBy + aggregate selectors.
            _ => FetchGroupedLevelPageAsync(source, request, semantics, grouping, includeRowCount, cancellationToken)
        };
    }

    /// <summary>
    /// The filtered row count on its own, for a host that fetches the total on a different cadence from
    /// the blocks — the same query <see cref="FetchPageAsync{TRow}"/> runs when asked, exposed so that
    /// asking for it separately cannot mean asking a different question.
    ///
    /// <para><b>Ungrouped only, deliberately unchanged by #1887.</b> A grouped request still reaches
    /// <see cref="EfCoreQueryBuilder.ApplyFilter{TRow}"/>'s own refusal here — no grouped count use is
    /// required by this ticket's DoD, and a grouped level's own count
    /// (<see cref="EfCoreQueryBuilder.CountGroupsAsync{TRow}"/>, a BUCKET count) answers a different
    /// question from this method's row count, so widening this one's meaning silently would be exactly
    /// the "right shape, wrong answer" failure the rest of this file refuses elsewhere.</para>
    /// </summary>
    public static Task<long> CountAsync<TRow>(
        IQueryable<TRow> source,
        EfCoreQueryRequest request,
        EfCoreProviderSemantics semantics,
        CancellationToken cancellationToken = default) =>
        EfCoreQueryBuilder.ApplyFilter(source, request, semantics).LongCountAsync(cancellationToken);

    // ---- the three branches -------------------------------------------------------------------------

    /// <summary>Today's path, unchanged: filter, order, row window, projection.</summary>
    private static async Task<EfCoreGridPage> FetchUngroupedPageAsync<TRow>(
        IQueryable<TRow> source,
        EfCoreQueryRequest request,
        EfCoreProviderSemantics semantics,
        bool includeRowCount,
        CancellationToken cancellationToken)
    {
        var filtered = EfCoreQueryBuilder.ApplyFilter(source, request, semantics);

        // Counted on the FILTERED query with no ordering and no row window — AG Grid's rowCount is "how
        // many rows match", not "how many are on this page". Ordering a count is wasted work every
        // engine would have to plan around, and applying the window would make the answer the page size.
        var rowCount = includeRowCount
            ? await filtered.LongCountAsync(cancellationToken).ConfigureAwait(false)
            : (long?)null;

        var columns = EfCoreQueryBuilder.ResolveProjection(request);

        var page = EfCoreQueryBuilder.ApplyProjection(
            EfCoreQueryBuilder.ApplyRowWindow(
                EfCoreQueryBuilder.ApplyOrdering(filtered, request, semantics),
                request.Page),
            request.Schema,
            columns);

        return new EfCoreGridPage
        {
            Columns = columns,
            Rows = await MaterializeRowsAsync(page, cancellationToken).ConfigureAwait(false),
            RowCount = rowCount
        };
    }

    /// <summary>
    /// GRP-1's drill-down leaf: the already-consumed <c>groupKeys</c> (<paramref name="grouping"/>'s
    /// own <see cref="GroupingPlan.DrillDown"/>) AND-composed with the request's own filter, then the
    /// EXISTING per-row pipeline — ordering, row window, projection — unchanged. GRP-3's leaf projects
    /// every declared field under its logical name (the same <see cref="EfCoreQueryBuilder.ResolveProjection"/>
    /// fallback the ungrouped path uses), and its <c>ORDER BY</c> stays ordinary SEM-1/Ungrouped (only
    /// the drill-down predicate itself is GRP-2-exact) — <see cref="EfCoreQueryBuilder.ResolveSortKeys(EfCoreQueryRequest)"/>
    /// is reused unchanged for that reason.
    /// </summary>
    private static async Task<EfCoreGridPage> FetchDrillDownLeafPageAsync<TRow>(
        IQueryable<TRow> source,
        EfCoreQueryRequest request,
        EfCoreProviderSemantics semantics,
        GroupingPlan grouping,
        bool includeRowCount,
        CancellationToken cancellationToken)
    {
        var context = EfCoreQueryBuilder.ValidateAndBuildRowContext(request, semantics, typeof(TRow));

        var filtered = EfCoreQueryBuilder.ApplyGroupedFilter(source, grouping.DrillDown, request.Filter, context);

        var rowCount = includeRowCount
            ? await filtered.LongCountAsync(cancellationToken).ConfigureAwait(false)
            : (long?)null;

        var columns = EfCoreQueryBuilder.ResolveProjection(request);

        var page = EfCoreQueryBuilder.ApplyProjection(
            EfCoreQueryBuilder.ApplyRowWindow(
                EfCoreQueryBuilder.ApplyOrdering(filtered, EfCoreQueryBuilder.ResolveSortKeys(request), context),
                request.Page),
            request.Schema,
            columns);

        return new EfCoreGridPage
        {
            Columns = columns,
            Rows = await MaterializeRowsAsync(page, cancellationToken).ConfigureAwait(false),
            RowCount = rowCount
        };
    }

    /// <summary>
    /// A grouped level: the same drill-down + user-filter composition as the leaf (GRP-5's own
    /// "already-consumed keys"), then <see cref="EfCoreQueryBuilder.ApplyGroupedLevel{TRow}"/>'s
    /// <c>GroupBy</c>/aggregate composition, the ordinary <see cref="EfCoreQueryBuilder.ApplyRowWindow{TRow}"/>
    /// (instantiated with <c>TRow = object?[]</c> — it has no dependency on what a row IS), and
    /// <c>Columns = [groupColumn, ...aggregations.Select(a =&gt; a.OutputName)]</c>. The row count is a
    /// BUCKET count (<see cref="EfCoreQueryBuilder.CountGroupsAsync{TRow}"/>), not a row count — no
    /// <c>groupLevelInfo</c>-style metadata (#1649's, explicitly out of scope here).
    /// </summary>
    private static async Task<EfCoreGridPage> FetchGroupedLevelPageAsync<TRow>(
        IQueryable<TRow> source,
        EfCoreQueryRequest request,
        EfCoreProviderSemantics semantics,
        GroupingPlan grouping,
        bool includeRowCount,
        CancellationToken cancellationToken)
    {
        var context = EfCoreQueryBuilder.ValidateAndBuildRowContext(request, semantics, typeof(TRow));
        var groupColumn = grouping.GroupColumn!;

        var filtered = EfCoreQueryBuilder.ApplyGroupedFilter(source, grouping.DrillDown, request.Filter, context);

        var rowCount = includeRowCount
            ? await EfCoreQueryBuilder.CountGroupsAsync(filtered, groupColumn, context, cancellationToken).ConfigureAwait(false)
            : (long?)null;

        var page = EfCoreQueryBuilder.ApplyRowWindow(
            EfCoreQueryBuilder.ApplyGroupedLevel(filtered, groupColumn, grouping.Aggregations, request.Sort, context),
            request.Page);

        var columns = new List<string>(1 + grouping.Aggregations.Count) { groupColumn };
        columns.AddRange(grouping.Aggregations.Select(aggregation => aggregation.OutputName));

        return new EfCoreGridPage
        {
            Columns = columns,
            Rows = await MaterializeRowsAsync(page, cancellationToken).ConfigureAwait(false),
            RowCount = rowCount
        };
    }

    private static async Task<List<IReadOnlyList<object?>>> MaterializeRowsAsync(
        IQueryable<object?[]> page, CancellationToken cancellationToken)
    {
        var rows = new List<IReadOnlyList<object?>>();
        await foreach (var cells in page.AsAsyncEnumerable().WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            EfCoreValueNormalizer.NormalizeInPlace(cells, cells.Length);
            rows.Add(cells);
        }

        return rows;
    }
}
