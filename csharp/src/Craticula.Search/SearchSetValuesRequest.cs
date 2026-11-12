using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.Search;

/// <summary>
/// Everything <see cref="SearchQueryBuilder.BuildSetValues"/> needs to compile one BM-3
/// distinct-values query — the counterpart of <see cref="SearchQueryRequest"/>, and a separate record
/// for the same reason <c>Craticula.Sql.SqlSetValuesRequest</c> and
/// <c>Craticula.Mongo.MongoSetValuesRequest</c> are: a distinct-values query has no page (GRP-6's cap
/// is a ceiling, not a window), no user sort (it orders by the distinct column, always) and no
/// aggregation.
/// </summary>
public sealed record SearchSetValuesRequest
{
    /// <summary>SC-1..SC-5: the field allowlist, physical mappings and the index
    /// (<see cref="GridSchema.Source"/>). <see cref="GridSchema.StableKey"/> is NOT read — GRP-6(e)
    /// appends no tiebreaker, the distinct key being unique across the result buckets by
    /// construction.</summary>
    public required GridSchema Schema { get; init; }

    /// <summary>GRP-6: the column whose distinct values this query returns — the <c>terms</c>
    /// aggregation's <c>field</c> and, through AGG-4, its <c>_key</c> ordering. Client-controlled, and
    /// it must reach here already allowlisted by
    /// <see cref="GridFilterPipeline.ProcessSetValues"/>, which applies SC-1 in every schema
    /// mode.</summary>
    public required string ColId { get; init; }

    /// <summary>The filter <see cref="GridFilterPipeline.ProcessSetValues"/> returns — GRP-6(b)'s
    /// own-field exclusion applied and GRP-6(c)'s search-prefix predicate already merged in. The
    /// prefix is taken back out here; see <see cref="SearchPrefix"/>.</summary>
    public FilterNode? Filter { get; init; }

    /// <summary>
    /// GRP-6(c)'s raw search-prefix text, or <see langword="null"/> when the set filter's search box
    /// is empty. <b>Passed separately although <see cref="Filter"/> already contains it</b>, and this
    /// is the one input no other backend's request record needs.
    ///
    /// <para><b>Why.</b> GRP-6(c) models the prefix as an ordinary <c>startsWith</c> predicate, which
    /// SQL and MongoDB then render as an ordinary predicate — so for them the merge
    /// <see cref="GridFilterPipeline.ProcessSetValues"/> performs is free. This backend renders it as
    /// the <c>terms</c> aggregation's <c>include</c> parameter instead (OSE-12): a Lucene regex
    /// evaluated at aggregation time, which is where the accepted case-sensitivity divergence
    /// <c>spec/fixtures/group-aggregation/018</c> records comes from. So this compiler has to know
    /// <em>which leaf</em> the prefix is, and GRP-5 names recovering that from the merged tree's shape
    /// as a trap. It is therefore carried as provenance, exactly as
    /// <see cref="SearchQueryRequest.Group"/> carries the drill-down's.</para>
    ///
    /// <para><b>Recorded asymmetry in <c>Craticula.Core</c>, worked around rather than fixed here.</b>
    /// <see cref="GridFilterPipeline.Process"/> deliberately does NOT merge GRP-5's drill-down into
    /// the tree it returns — it only charges it against SEC-3 — precisely so a compiler can keep the
    /// provenance GRP-2 needs. <see cref="GridFilterPipeline.ProcessSetValues"/> does merge GRP-6(c)'s
    /// prefix. The two are the same kind of synthesised predicate and the asymmetry only became
    /// visible with a third backend that renders one of them somewhere other than the query. Closing
    /// it (returning the prefix beside the tree, as <c>Process</c> effectively does for the
    /// drill-down) is a <c>Craticula.Core</c> change and belongs to a story of its own; until then
    /// <see cref="SearchQueryBuilder.BuildSetValues"/> re-mints the predicate through
    /// <see cref="SetValuesFilter.SearchPrefixPredicate"/> and removes the first node equal to it,
    /// refusing to compile only if it is not found at all. A DUPLICATE is left in place rather than
    /// refused: SC-5's static filter is injected after the prefix, so a host whose static filter
    /// spells the identical <c>startsWith</c> on the same column produces two equal nodes, and a
    /// duplicated conjunct is inert — failing compilation over a redundancy would be a worse answer
    /// than compiling it as the ordinary clause it is.</para>
    /// </summary>
    public string? SearchPrefix { get; init; }

    /// <summary>GRP-6(d)/SEC-3: how many distinct values the query may return, <b>already
    /// resolved</b> by <see cref="ResourceLimitsValidator.ResolveSetValuesLimit"/>. "No cap" is not
    /// one of the answers, so this is not nullable.</summary>
    public required int RowLimit { get; init; }

    /// <summary>TL-2: the host's <see cref="ResourceLimits.MaxQueryTimeMs"/>, carried into the body as <c>timeout</c>.</summary>
    public int? MaxQueryTimeMs { get; init; }
}
