using System.Text.Json.Nodes;
using Craticula.Search;

namespace Craticula.OpenSearch.Client.Offline.Tests;

/// <summary>
/// <see cref="OpenSearchGridQuery.ComputeCursorKey"/>'s own determinism contract — PERF-2/the DoD's
/// "cursor cache invalidation verified" — proven directly against the pure hashing function via
/// <c>InternalsVisibleTo</c>, mirroring <c>Craticula.Dapper.Tests</c>' access to
/// <c>DapperParameterBinder.ToTypedArray</c> for the identical reason: no live cluster is needed to pin
/// this function's own behavior.
/// </summary>
public sealed class OpenSearchGridQueryComputeCursorKeyTests
{
    private static readonly JsonObject Query = new() { ["term"] = new JsonObject { ["region.keyword"] = "EMEA" } };
    private static readonly JsonArray Sort = new(new JsonObject { ["id"] = new JsonObject { ["order"] = "asc" } });

    private static SearchQuery RowQuery(JsonObject query, JsonArray sort, int from = 0, int size = 100) => new()
    {
        Index = "orders",
        Query = query,
        Sort = sort,
        From = from,
        Size = size
    };

    private static SearchQuery GroupedQuery(JsonArray sources, int compositeSize = 100) => new()
    {
        Index = "sales_fact",
        Size = 0,
        Aggs = new JsonObject
        {
            ["region"] = new JsonObject
            {
                ["composite"] = new JsonObject { ["size"] = compositeSize, ["sources"] = sources.DeepClone() }
            }
        }
    };

    [Fact]
    public void The_Same_Compiled_Shape_Hashes_To_The_Same_Key()
    {
        var a = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()));
        var b = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()));

        Assert.Equal(a, b);
    }

    /// <summary>PERF-2's own phrase: a sort change is what "invalidation" means here — a different hash,
    /// not a cache mutation.</summary>
    [Fact]
    public void A_Different_Sort_Hashes_To_A_Different_Key()
    {
        var original = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()));

        var changedSort = new JsonArray(new JsonObject { ["id"] = new JsonObject { ["order"] = "desc" } });
        var changed = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), changedSort));

        Assert.NotEqual(original, changed);
    }

    [Fact]
    public void A_Different_Filter_Hashes_To_A_Different_Key()
    {
        var original = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()));

        var changedQuery = new JsonObject { ["term"] = new JsonObject { ["region.keyword"] = "APAC" } };
        var changed = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(changedQuery, Sort.DeepClone()!.AsArray()));

        Assert.NotEqual(original, changed);
    }

    /// <summary>Half of PERF-2's own key shape: (grid session, sort+filter hash) — the SAME compiled
    /// shape under two different sessions must not collide.</summary>
    [Fact]
    public void A_Different_Grid_Session_Hashes_To_A_Different_Key()
    {
        var query = RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray());

        var sessionA = OpenSearchGridQuery.ComputeCursorKey("session-A", query);
        var sessionB = OpenSearchGridQuery.ComputeCursorKey("session-B", query);

        Assert.NotEqual(sessionA, sessionB);
    }

    /// <summary>The cache key deliberately EXCLUDES <c>from</c>/<c>size</c> — two requests differing
    /// only in which page they ask for must address the SAME logical walk, or PERF-2's reuse could
    /// never fire at all.</summary>
    [Fact]
    public void From_And_Size_Do_Not_Affect_The_Row_Level_Key()
    {
        var page1 = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray(), from: 0, size: 100));
        var page2 = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray(), from: 10_000, size: 37));

        Assert.Equal(page1, page2);
    }

    /// <summary>The grouped-level mirror of the same exclusion: <c>composite.size</c>/<c>after</c> are
    /// never reflected in the key, only <c>composite.sources</c> — this is what lets a second grouped
    /// block reuse the first block's own cursor entry.</summary>
    [Fact]
    public void Composite_Size_Does_Not_Affect_The_Grouped_Level_Key()
    {
        var sources = new JsonArray(new JsonObject { ["region"] = new JsonObject { ["terms"] = new JsonObject { ["field"] = "region.keyword" } } });

        var block1 = OpenSearchGridQuery.ComputeCursorKey("session-1", GroupedQuery(sources, compositeSize: 100));
        var block2 = OpenSearchGridQuery.ComputeCursorKey("session-1", GroupedQuery(sources, compositeSize: 101));

        Assert.Equal(block1, block2);
    }

    /// <summary>A different <c>composite.sources</c> (a different group column) must hash differently —
    /// the grouped-level counterpart of "a different sort hashes differently".</summary>
    [Fact]
    public void A_Different_Composite_Source_Hashes_To_A_Different_Key()
    {
        var sourcesA = new JsonArray(new JsonObject { ["region"] = new JsonObject { ["terms"] = new JsonObject { ["field"] = "region.keyword" } } });
        var sourcesB = new JsonArray(new JsonObject { ["segment"] = new JsonObject { ["terms"] = new JsonObject { ["field"] = "segment.keyword" } } });

        var a = OpenSearchGridQuery.ComputeCursorKey("session-1", GroupedQuery(sourcesA));
        var b = OpenSearchGridQuery.ComputeCursorKey("session-1", GroupedQuery(sourcesB));

        Assert.NotEqual(a, b);
    }

    /// <summary>An ungrouped and a grouped request over an otherwise-identical query must never collide
    /// — they hash two structurally different member sets (<c>sort</c> versus <c>sources</c>).</summary>
    [Fact]
    public void An_Ungrouped_And_A_Grouped_Shape_Never_Collide()
    {
        var row = OpenSearchGridQuery.ComputeCursorKey("session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()));

        var sources = new JsonArray(new JsonObject { ["region"] = new JsonObject { ["terms"] = new JsonObject { ["field"] = "region.keyword" } } });
        var grouped = OpenSearchGridQuery.ComputeCursorKey("session-1", GroupedQuery(sources));

        Assert.NotEqual(row, grouped);
    }

    /// <summary>Security review finding: TWO DIFFERENT INDICES sharing an otherwise byte-identical
    /// {query, sort} shape — a real multi-tenant pattern (<c>orders_tenant_a</c>/<c>orders_tenant_b</c>)
    /// — must never collide under one <c>gridSessionId</c>. Before this fix, <c>ComputeCursorKey</c>
    /// never read <see cref="SearchQuery.Index"/> off the compiled artifact at all, so a reused cache
    /// entry would silently serve the WRONG index's rows against the new request (a cache key omission,
    /// not a rendering gap — <c>FetchPitWindowAsync</c> deliberately omits the index from the request
    /// BODY, since the PIT itself already carries it, but the cache KEY has no such excuse).</summary>
    [Fact]
    public void A_Different_Index_Hashes_To_A_Different_Key_Even_With_An_Otherwise_Identical_Shape()
    {
        var a = OpenSearchGridQuery.ComputeCursorKey(
            "session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()) with { Index = "orders_tenant_a" });
        var b = OpenSearchGridQuery.ComputeCursorKey(
            "session-1", RowQuery(Query.DeepClone()!.AsObject(), Sort.DeepClone()!.AsArray()) with { Index = "orders_tenant_b" });

        Assert.NotEqual(a, b);
    }
}
