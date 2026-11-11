using System.Text.Json.Nodes;

namespace Craticula.Search;

/// <summary>
/// A compiled OpenSearch/Elasticsearch artifact: the body of one <c>_search</c> request, exactly what
/// every <c>spec/fixtures/*/expected/search.artifact.json</c> pins.
///
/// <para><b>One artifact, both engines (OQ-7).</b> There is no target flag and no second compiler.
/// Every construct this class can hold — <c>bool</c>/<c>term</c>/<c>terms</c>/<c>range</c>/
/// <c>wildcard</c>/<c>match</c>/<c>exists</c>, <c>sort</c>'s <c>missing</c>, <c>from</c>/<c>size</c>,
/// and <c>composite</c>/<c>terms</c> aggregations with
/// <c>missing_bucket</c>/<c>include</c>/<c>order</c> — predates the 7.10 fork and is spelled
/// identically on both sides of it, so
/// the shared subset is not a compromise between two dialects but simply the intersection's
/// interior. See <see cref="SearchQueryBuilder"/>'s remarks for the one parameter that had to be
/// checked (<c>case_insensitive</c>, 7.10 on Elasticsearch and OpenSearch 1.0's inherited baseline)
/// and why it still needs no flag.</para>
///
/// <para><b>What is deliberately absent.</b> No <c>_source</c> filtering (GRP-3 has no ES
/// counterpart — <c>spec/fixtures/schemas/search-artifact.schema.json</c> forbids the member
/// outright), no <c>track_total_hits</c>, and no <c>search_after</c>: PERF-2 scopes that to deep
/// paging beyond <c>max_result_window</c> with a cursor cache the <b>execution adapter</b> owns
/// (Feature #1622), and neither the window nor the cursor exists in this compiler's inputs. All 160
/// in-scope artifacts pin the <c>from</c>/<c>size</c> offset form this class emits.</para>
/// </summary>
public sealed record SearchQuery
{
    /// <summary>SQL-0: the index this request runs against, taken from
    /// <c>GridSchema.Source</c> and never from the request. Not part of the artifact — the fixture's
    /// <c>search.artifact.json</c> pins the request body alone — but a host needs it to build the
    /// URL, so it is carried rather than dropped.</summary>
    public required string Index { get; init; }

    /// <summary>OSE-2: the compiled query tree. <see langword="null"/> only on an aggregation
    /// request with no predicate at all; a hit-returning request with no filter carries
    /// <c>{"match_all": {}}</c> instead (OSE-3).</summary>
    public JsonObject? Query { get; init; }

    /// <summary>SEM-3/SEM-6: the ordered sort array, whose ELEMENT order is the tiebreak order.
    /// <see langword="null"/> on an aggregation request, which returns no hits to order.</summary>
    public JsonArray? Sort { get; init; }

    /// <summary>AG-3: the row window's offset. <see langword="null"/> under EXP-2's
    /// <c>page: none</c> and on an aggregation request.</summary>
    public int? From { get; init; }

    /// <summary>AG-3: the row window's size — <c>0</c> on an aggregation request, which wants
    /// buckets and no hits. <see langword="null"/> under EXP-2's <c>page: none</c>.</summary>
    public int? Size { get; init; }

    /// <summary>BM-2/BM-3: the <c>composite</c> (grouped level) or <c>terms</c> (distinct values)
    /// aggregation, with its sub-aggregations. <see langword="null"/> on a row query.</summary>
    public JsonObject? Aggs { get; init; }

    /// <summary>TL-2: the host's maximum query time in milliseconds, rendered as the top-level
    /// <c>timeout</c> member (<c>"&lt;N&gt;ms"</c>); <see langword="null"/> when none is configured, and always for an
    /// export. A soft limit: the shards stop at their next check, not at once.</summary>
    public int? TimeoutMs { get; init; }

    /// <summary>
    /// GRP-2, made observable rather than inferred from an absence — the counterpart of
    /// <c>Craticula.Mongo.MongoQuery.CollationSuppressedByBucketIdentity</c>, but <b>a constant of
    /// this type rather than a computed one</b>: it is always <see langword="false"/>, by
    /// construction, and there is no state on this record that could make it anything else. Asserting
    /// it per compiled request would therefore assert nothing; the structural claim it stands for is
    /// asserted once, in
    /// <c>SearchConformanceFixtureTests.Satisfies_SEM1_And_GRP2_In_The_One_Request_MongoDB_Must_Choose_Between</c>.
    ///
    /// <para>MongoDB's <c>collation</c> is a query-level option, so a grouping request there cannot
    /// spell SEM-1's mechanism on a user's filter and GRP-2's exactness on the protocol's keys at
    /// once, and the protocol wins (accepted divergence #3). ES/OpenSearch has per-clause
    /// granularity: <c>case_insensitive</c> sits on the individual <c>term</c>/<c>wildcard</c> that
    /// wants it, while a <c>composite</c> source and a drill-down <c>term</c> simply do not carry the
    /// parameter — so both demands are satisfied in the same request and nothing is suppressed. This
    /// property is carried rather than assumed so a cross-compiler test can assert the divergence is
    /// <em>absent here</em> instead of silently agreeing with a query that had no string in it.</para>
    /// </summary>
    public bool CaseInsensitivitySuppressedByBucketIdentity => false;

    /// <summary>
    /// The artifact document itself, in this compiler's pinned member order
    /// (<c>query</c>, <c>sort</c>, <c>from</c>, <c>size</c>, <c>aggs</c>) with absent members
    /// omitted. Returns a fresh deep clone on every call — <see cref="JsonNode"/> is single-parented,
    /// so handing out the live nodes would make the second caller's assignment throw.
    ///
    /// <para><b>Member order is deterministic here and is NOT part of the artifact contract</b>
    /// (OSE-0). No object key anywhere in this DSL is order-sensitive — unlike MongoDB's <c>$sort</c>
    /// document, whose key order IS the tiebreak order — and the hand-authored suite spells the same
    /// two members in both orders across categories. So the conformance comparison canonicalises
    /// object key order and this method fixes one, rather than 128 artifacts being re-authored to
    /// agree about something the engines never read.</para>
    /// </summary>
    public JsonObject ToArtifact()
    {
        var artifact = new JsonObject();

        if (Query is not null)
        {
            artifact["query"] = Query.DeepClone();
        }

        if (Sort is not null)
        {
            artifact["sort"] = Sort.DeepClone();
        }

        if (From is { } from)
        {
            artifact["from"] = from;
        }

        if (Size is { } size)
        {
            artifact["size"] = size;
        }

        if (Aggs is not null)
        {
            artifact["aggs"] = Aggs.DeepClone();
        }

        if (TimeoutMs is { } timeoutMs)
        {
            artifact["timeout"] = $"{timeoutMs}ms";
        }

        return artifact;
    }
}
