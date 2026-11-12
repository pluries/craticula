using System.Text.Json.Nodes;

namespace Craticula.OpenSearch.Client.Offline.Tests;

/// <summary>
/// <see cref="InMemorySearchCursorCache"/>'s own pure expiry/self-cleaning contract — no live cluster
/// needed, mirroring <c>OpenSearchGridQueryComputeCursorKeyTests</c>'s own reasoning for testing a pure
/// piece of this package directly rather than only indirectly through a real PIT. Uses a small mutable
/// <see cref="TimeProvider"/> double (hand-written, matching every other test project's own
/// <c>FixedClock</c> precedent — AR-3 keeps this solution at zero third-party time-testing packages)
/// since this suite needs to observe the SAME cache both before and after an entry's own expiry.
/// </summary>
public sealed class InMemorySearchCursorCacheTests
{
    private sealed class MutableClock : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = DateTimeOffset.UtcNow;

        public override DateTimeOffset GetUtcNow() => Now;
    }

    private static SearchCursorEntry Entry(DateTimeOffset expiresAt) =>
        new("pit-1", UpToRow: 10, new JsonArray(10L), expiresAt);

    [Fact]
    public async Task TryGetAsync_Returns_The_Entry_Before_Its_Own_Expiry()
    {
        var clock = new MutableClock { Now = DateTimeOffset.UnixEpoch };
        var cache = new InMemorySearchCursorCache(clock);
        await cache.SetAsync("key", Entry(clock.Now + TimeSpan.FromMinutes(1)), CancellationToken.None);

        var found = await cache.TryGetAsync("key", CancellationToken.None);

        Assert.NotNull(found);
        Assert.Equal(10, found!.UpToRow);
    }

    /// <summary>
    /// Review finding: <c>TryGetAsync</c> used to leave an expired entry sitting in the dictionary
    /// forever (unbounded growth for a long-lived host) — this asserts BOTH halves of the fix: the
    /// expired entry reads as absent (unchanged contract), AND it no longer physically remains
    /// afterward, proven by <see cref="ISearchCursorCache.RemoveAsync"/> finding nothing where a
    /// pre-fix cache would still have handed back the stale entry.
    /// </summary>
    [Fact]
    public async Task TryGetAsync_Self_Cleans_An_Entry_Past_Its_Own_Expiry()
    {
        var clock = new MutableClock { Now = DateTimeOffset.UnixEpoch };
        var cache = new InMemorySearchCursorCache(clock);
        await cache.SetAsync("key", Entry(clock.Now + TimeSpan.FromSeconds(1)), CancellationToken.None);

        clock.Now += TimeSpan.FromSeconds(2); // past the entry's own ExpiresAt.

        var found = await cache.TryGetAsync("key", CancellationToken.None);
        Assert.Null(found);

        // Self-cleaned: nothing left for RemoveAsync to find either.
        var removed = await cache.RemoveAsync("key", CancellationToken.None);
        Assert.Null(removed);
    }

    /// <summary>The compare-and-remove in the fix must not clobber a fresh entry a concurrent
    /// <c>SetAsync</c> wrote in between an expired read and its own cleanup — simulated here
    /// sequentially (SetAsync always happens-before the next TryGetAsync in this single-threaded test),
    /// but the assertion is the same one a race would need to hold: a NEWLY-set, non-expired entry
    /// under the same key must survive a <c>TryGetAsync</c> call that would have cleaned up the OLD,
    /// expired one.</summary>
    [Fact]
    public async Task TryGetAsync_Never_Removes_A_Freshly_Set_Entry_Under_The_Same_Key()
    {
        var clock = new MutableClock { Now = DateTimeOffset.UnixEpoch };
        var cache = new InMemorySearchCursorCache(clock);
        await cache.SetAsync("key", Entry(clock.Now + TimeSpan.FromSeconds(1)), CancellationToken.None);

        clock.Now += TimeSpan.FromSeconds(2);

        // A fresh entry replaces the expired one BEFORE anything reads it as expired.
        var fresh = new SearchCursorEntry("pit-2", UpToRow: 99, new JsonArray(99L), clock.Now + TimeSpan.FromMinutes(1));
        await cache.SetAsync("key", fresh, CancellationToken.None);

        var found = await cache.TryGetAsync("key", CancellationToken.None);

        Assert.NotNull(found);
        Assert.Equal(99, found!.UpToRow);
    }

    [Fact]
    public async Task TryGetAsync_Returns_Null_When_The_Key_Was_Never_Set()
    {
        var cache = new InMemorySearchCursorCache();

        var found = await cache.TryGetAsync("missing", CancellationToken.None);

        Assert.Null(found);
    }
}
