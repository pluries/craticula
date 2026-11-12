using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Mongo;

/// <summary>
/// Everything <see cref="MongoPipelineBuilder.BuildSetValues"/> needs to compile one BM-3
/// distinct-values query — the counterpart of <see cref="MongoQueryRequest"/>, and a separate record
/// for the same reason <c>Craticula.Sql.SqlSetValuesRequest</c> is: a distinct-values query has no
/// page (GRP-6's cap is a ceiling, not a window), no user sort (it orders by the distinct column,
/// always) and no aggregation, so folding the two together would mean every caller passing three
/// ignored properties and one dummy one.
/// </summary>
public sealed record MongoSetValuesRequest
{
    /// <summary>SC-1..SC-5: the field allowlist, physical mappings and the collection
    /// (<see cref="GridSchema.Source"/>). <see cref="GridSchema.StableKey"/> is NOT read — GRP-6(e)
    /// appends no tiebreaker, the distinct key being unique across the result documents by
    /// construction.</summary>
    public required GridSchema Schema { get; init; }

    /// <summary>GRP-6: the column whose distinct values this pipeline returns — the <c>$group</c>
    /// <c>_id</c> expression and the sole <c>$sort</c> key. Client-controlled, and it must reach here
    /// already allowlisted by <see cref="GridFilterPipeline.ProcessSetValues"/>, which applies SC-1
    /// in every schema mode.</summary>
    public required string ColId { get; init; }

    /// <summary>The filter that survives GRP-6(b)'s own-field exclusion, with GRP-6(c)'s
    /// search-prefix predicate already folded in — i.e. what
    /// <see cref="GridFilterPipeline.ProcessSetValues"/> returns. <see langword="null"/> compiles to
    /// no <c>$match</c> stage at all.</summary>
    public FilterNode? Filter { get; init; }

    /// <summary>GRP-6(d)/SEC-3: how many distinct values the pipeline may return, <b>already
    /// resolved</b> by <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>. "No cap" is not
    /// one of the answers, so this is not nullable.</summary>
    public required int RowLimit { get; init; }

    /// <summary>TL-1: the host's <see cref="ResourceLimits.MaxQueryTimeMs"/>, carried into the artifact as <c>maxTimeMS</c>.</summary>
    public int? MaxQueryTimeMs { get; init; }
}
