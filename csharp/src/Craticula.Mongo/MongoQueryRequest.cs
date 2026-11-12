using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo;

/// <summary>
/// Everything <see cref="MongoPipelineBuilder.Build"/> needs to compile one leaf query — the exact
/// counterpart of <c>Craticula.Sql.SqlQueryRequest</c>, property for property, and deliberately so:
/// the two compilers consume the identical IR produced by the identical
/// <c>Craticula.AgGrid.AgGridRequestParser</c> -&gt; <see cref="GridFilterPipeline.Process"/> path,
/// so anything one of them needs and the other does not would be a semantics decision that had
/// leaked into a backend.
/// </summary>
public sealed record MongoQueryRequest
{
    /// <summary>SC-1..SC-5: the field allowlist, physical mappings, <see cref="GridSchema.Source"/>
    /// (the collection) and <see cref="GridSchema.StableKey"/> (SEM-6's tiebreaker).</summary>
    public required GridSchema Schema { get; init; }

    /// <summary>The final filter tree — merged, allowlisted, limit-checked, coerced and
    /// static-filter-injected by <see cref="GridFilterPipeline.Process"/>. <see langword="null"/>
    /// compiles to no <c>$match</c> stage at all.</summary>
    public FilterNode? Filter { get; init; }

    /// <summary>The request's own sort keys, before SEM-6's tiebreaker (which
    /// <see cref="MongoPipelineBuilder"/> appends via
    /// <see cref="SemanticsResolver.AppendStableKeyTiebreaker(IReadOnlyList{SortItem}?, string)"/>).</summary>
    public IReadOnlyList<SortItem>? Sort { get; init; }

    public required PageSpec Page { get; init; }

    /// <summary>
    /// BM-2's row-group state, and the switch <see cref="MongoPipelineBuilder"/> dispatches on
    /// (GRP-1): <see langword="null"/> compiles the plain row pipeline, fewer
    /// <see cref="GroupSpec.GroupKeys"/> than <see cref="GroupSpec.GroupCols"/> compiles the grouped
    /// level (a <c>$group</c> stage), and equal counts compile the drill-down leaf (raw documents,
    /// with GRP-3's explicit <c>$project</c>).
    ///
    /// <para><b>Client-controlled input that must reach here already allowlisted</b>, exactly like
    /// <see cref="Filter"/>: pass it and <see cref="Aggregations"/> to
    /// <see cref="GridFilterPipeline.Process"/>, which applies SC-1, SC-2's
    /// <c>groupable</c>/<c>aggregatable</c> flags and SEC-3's leaf budget over the <c>groupKeys</c>
    /// drill-down.</para>
    /// </summary>
    public GroupSpec? Group { get; init; }

    /// <summary>AR-8's <c>valueCols</c>, compiled into the <c>$group</c> stage's accumulators
    /// alongside <c>_id</c>. Ignored on the drill-down leaf and on an ungrouped request, both of
    /// which return documents rather than aggregates. Subject to the same allowlist precondition as
    /// <see cref="Group"/>.</summary>
    public IReadOnlyList<Aggregation>? Aggregations { get; init; }

    /// <summary>
    /// EXP-1(b): the export's output fields, in the order they must appear —
    /// <c>Craticula.AgGrid.ExportSpec.ProjectionColumns</c>, already resolved. <see langword="null"/>
    /// (the default) is an ordinary row query, which emits no <c>$project</c> stage at all, exactly
    /// as its SQL counterpart renders <c>SELECT *</c> (GRP-3).
    ///
    /// <para>Property-for-property the same member <c>Craticula.Sql.SqlQueryRequest</c> carries, and
    /// deliberately so — the two compilers consume the identical resolved list, so neither can
    /// disagree with the other about which columns an export contains or what order they are in.
    /// Both compilers refuse the same two shapes: a projection beside a <see cref="Group"/>, and an
    /// EMPTY projection — here it would emit <c>{"$project": {"_id": 0}}</c>, a stage that suppresses
    /// every field rather than projecting none.</para>
    /// </summary>
    public IReadOnlyList<string>? Projection { get; init; }

    /// <summary>TL-1: the host's <see cref="ResourceLimits.MaxQueryTimeMs"/>, carried into the artifact as
    /// <c>maxTimeMS</c>. Ignored for an unpaginated (export) page, TL-3.</summary>
    public int? MaxQueryTimeMs { get; init; }
}
