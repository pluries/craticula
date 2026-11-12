using System.Text.Json.Nodes;

namespace Craticula.Mongo;

/// <summary>
/// A compiled MongoDB artifact: the aggregation pipeline plus the query-level <c>collation</c>
/// option, if any — exactly what every <c>spec/fixtures/*/expected/mongo.artifact.json</c> pins.
///
/// <para><b>Two artifact shapes, and the rule is not cosmetic.</b> MongoDB's <c>collation</c> is an
/// <c>aggregate()</c> <em>command</em> option, not a pipeline stage, so it cannot be an element of
/// the pipeline array. <c>spec/fixtures/schemas/mongo-artifact.schema.json</c> therefore admits a
/// bare array <em>or</em> a <c>{ pipeline, collation }</c> wrapper object, and
/// <see cref="ToArtifact"/> emits the wrapper <b>if and only if</b> a collation or a query time limit (TL-1) is present — which
/// is what <see cref="Collation"/>'s own remarks describe.</para>
///
/// <para>The nodes are hand-built Extended JSON (AR-3: no driver package), so a host hands
/// <see cref="Pipeline"/> straight to its driver's <c>aggregate</c> after parsing it into whatever
/// document type that driver uses.</para>
/// </summary>
public sealed record MongoQuery
{
    /// <summary>SQL-0: the collection this pipeline runs against, taken from
    /// <c>GridSchema.Source</c> and never from the request. Not part of the artifact — the fixture's
    /// <c>mongo.artifact.json</c> pins the pipeline alone — but a host needs it to run the query, so
    /// it is carried rather than dropped.</summary>
    public required string Collection { get; init; }

    /// <summary>The ordered aggregation stages, each a single-key document
    /// (<c>$match</c>, <c>$group</c>, <c>$addFields</c>, <c>$sort</c>, <c>$unset</c>, <c>$skip</c>,
    /// <c>$limit</c>, <c>$project</c>).</summary>
    public required IReadOnlyList<JsonObject> Pipeline { get; init; }

    /// <summary>
    /// SEM-1's case-insensitive mechanism on MongoDB — <c>{ locale, strength: 2 }</c> — present only
    /// when some construct this query renders actually resolved to
    /// <c>CaseSensitivityMechanism.Collation</c> with <c>CaseSensitivityMode.Insensitive</c>: a
    /// user's own <c>$eq</c>/<c>$ne</c>/<c>$gt</c>/<c>$gte</c>/<c>$lt</c>/<c>$lte</c>/<c>$in</c>/
    /// <c>$nin</c> against a case-insensitive <c>string</c>, or a <c>$sort</c> key on one.
    /// <c>$regex</c> never contributes: SEM-1 pins the substring family to the pattern-match
    /// mechanism, which carries its own <c>$options: "i"</c> and which a query-level collation does
    /// not reach.
    ///
    /// <para>It is also <see langword="null"/> whenever
    /// <see cref="CollationSuppressedByBucketIdentity"/> is <see langword="true"/> — see there.</para>
    /// </summary>
    public JsonObject? Collation { get; init; }

    /// <summary>TL-1: the host's maximum query time in milliseconds, the <c>aggregate()</c> command option
    /// <c>maxTimeMS</c>; <see langword="null"/> when none is configured, and always for an export.</summary>
    public int? MaxTimeMs { get; init; }

    /// <summary>
    /// GRP-2's <b>accepted divergence #3</b>, made observable rather than inferred from an absence.
    /// <see langword="true"/> means some construct in this query did resolve to SEM-1's collation
    /// mechanism and the collation was nonetheless <em>not</em> emitted, because the pipeline also
    /// computes bucket identity (a grouping request at any level, or a BM-3 distinct-values query).
    ///
    /// <para>MongoDB's <c>collation</c> is query-level: it governs <c>$match</c>, <c>$group</c> and
    /// <c>$sort</c> together and has no per-stage form, so the two demands cannot both be satisfied.
    /// The protocol's keys win — bucket identity is a correctness property (get it wrong and a child
    /// level stops summing to its parent's aggregate, silently), while a case-folded filter or sort
    /// is a narrower, visible difference. So on MongoDB a user's own filter inside a grouping request
    /// compares case-<b>sensitively</b>, and a drill-down leaf's <c>$sort</c> orders
    /// case-sensitively, where the five SQL dialects collate both.</para>
    ///
    /// <para>Distinguishing "suppressed" from "never wanted" is what lets a cross-compiler test
    /// assert the divergence as an <em>expected difference</em> against the SQL arm's
    /// <c>COLLATE craticula_ci</c>, instead of silently agreeing with a pipeline that simply had no
    /// string in it.</para>
    /// </summary>
    public required bool CollationSuppressedByBucketIdentity { get; init; }

    /// <summary>
    /// The artifact document itself: the bare pipeline array, or the
    /// <c>{ pipeline, collation }</c> wrapper when <see cref="Collation"/> is present. Returns a
    /// fresh deep clone on every call — <see cref="JsonNode"/> is single-parented, so handing out the
    /// live nodes would make the second caller's assignment throw.
    /// </summary>
    public JsonNode ToArtifact()
    {
        var pipeline = new JsonArray();
        foreach (var stage in Pipeline)
        {
            pipeline.Add(stage.DeepClone());
        }

        if (Collation is null && MaxTimeMs is null)
        {
            return pipeline;
        }

        var artifact = new JsonObject { ["pipeline"] = pipeline };
        if (Collation is not null)
        {
            artifact["collation"] = Collation.DeepClone();
        }

        if (MaxTimeMs is { } maxTimeMs)
        {
            artifact["maxTimeMS"] = maxTimeMs;
        }

        return artifact;
    }
}
