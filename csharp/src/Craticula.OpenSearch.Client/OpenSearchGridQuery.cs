using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Craticula.Core;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Search;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client;

/// <summary>
/// The <b>grid</b> entry point: one page of hits/buckets for an AG Grid SSRM block —
/// <c>Craticula.Search.SearchQueryBuilder.Build</c>'s search body executed via
/// <see cref="IOpenSearchLowLevelClient"/>'s LOW-LEVEL, raw-JSON surface against a client the host owns
/// and this package never constructs, opens, or closes.
///
/// <para><b>Execution style: the low-level client, raw JSON — never the high-level typed request
/// builder.</b> <c>SearchQuery.ToArtifact()</c> already produces the exact body every fixture pins;
/// re-deriving that shape through <c>OpenSearch.Client</c>'s strongly-typed <c>SearchDescriptor</c>
/// would be a second, divergence-prone spelling of the same query — the same trap
/// <c>Craticula.MongoDB.Driver</c>'s adapter avoided by round-tripping through
/// <c>BsonDocument.Parse(document.ToJsonString())</c> rather than the driver's fluent builder. This
/// package does the same: <c>PostData.String(json)</c> against <c>IOpenSearchLowLevelClient.SearchAsync</c>,
/// raw response bodies parsed with <c>System.Text.Json</c>.</para>
///
/// <para><b>This is the first genuinely STATEFUL adapter (#1622's own scope note).</b> EF/Dapper/Mongo
/// are all stateless per call; this one owns cross-request state — an open PIT and the last-seen
/// <c>sort</c>/<c>after</c> cursor — that MUST survive between one grid page request and the next for
/// PERF-2 to mean anything. The host is responsible for constructing ONE <see cref="ISearchCursorCache"/>
/// and keeping it alive/shared across requests for the SAME logical grid session; a fresh instance per
/// call silently defeats deep paging entirely (every deep page would cold-walk from zero).</para>
///
/// <para><b>The hard part — PERF-2's deep-paging cursor cache.</b> <c>Craticula.Search</c> deliberately
/// never emits <c>search_after</c>, <c>pit</c>, or <c>track_total_hits</c> (confirmed directly in
/// <c>SearchQuery.cs</c>/<c>SearchQueryBuilder.cs</c>): all of that is execution-adapter-owned state, by
/// explicit design. Two structurally different paging problems share ONE mechanism here:</para>
///
/// <list type="number">
/// <item><description><b>Row-level deep paging (OSE-10).</b> Beyond
/// <see cref="OpenSearchDeepPagingOptions.MaxResultWindow"/>, plain <c>from</c>/<c>size</c> is refused
/// by the engine. This adapter switches to PIT + <c>search_after</c>, where the cursor is the LAST
/// returned hit's own <c>sort</c> array.</description></item>
/// <item><description><b>Grouped-level paging (OSE-11(d)).</b> The compiler's <c>composite</c>
/// aggregation refuses ANY non-zero <c>startRow</c> outright (<c>RequireBucketWindow</c> throws) — a
/// FIRST-PAGE-ONLY limit, not a deep one: it bites on the SECOND block of any grouped grid (AG Grid's
/// default block size is 100), not just deep scrolls. This adapter compiles the synthetic
/// <c>RangePage { StartRow = 0, EndRow = blockSize }</c> that the compiler CAN answer, then splices the
/// previous response's own bucket <c>key</c> in as <c>composite.after</c> before executing. The cursor
/// here is that bucket key object, not a PIT — a composite's own <c>after</c> paging needs no point in
/// time at all, so a grouped-level <see cref="SearchCursorEntry.PitId"/> is always the empty
/// string.</description></item>
/// </list>
///
/// <para><b>The cache key</b> is <see cref="ComputeCursorKey"/>'s hash of the compiled
/// <c>{query, sort}</c> (row-level) or <c>{query, composite.sources}</c> (grouped-level) — which already
/// IS "sort+filter hash" (PERF-2's own phrase), since two structurally identical requests compile to
/// byte-identical JSON, and a sort/filter change is therefore simply a cache miss (see
/// <see cref="ISearchCursorCache"/>'s own remarks on why that is sufficient for correctness, and what
/// still needs explicit handling).</para>
///
/// <para><b>The adapter's own decision on every fetch, not the cache's</b>: whether the request's
/// offset matches the cache's own <c>UpToRow</c> exactly (reuse the cursor directly, O(1) round trip),
/// is AHEAD of it with a gap (walk forward internally in
/// <see cref="OpenSearchDeepPagingOptions.WalkBatchSize"/>-sized batches, advancing
/// <c>search_after</c>/<c>after</c> without yielding those rows, caching progress as it goes), or is
/// BEHIND it (AG Grid never pages backward mid-session in a way that matters here — treated as a cold
/// start: the outgoing entry's PIT is best-effort closed via <see cref="ISearchCursorCache.RemoveAsync"/>,
/// and a fresh walk begins from row/bucket zero). The FIRST request that crosses the deep-paging
/// threshold in a given (session, hash) always pays a full walk from zero — nothing is cached yet, since
/// every prior block used plain <c>from</c>/<c>size</c> — and every subsequent SEQUENTIAL block is O(1).
/// This is inherent to how <c>search_after</c>/<c>composite.after</c> work (no engine can jump to an
/// arbitrary rank without walking) and is the real trade-off PERF-2 accepts, not a shortcut this
/// adapter takes.</para>
/// </summary>
public static class OpenSearchGridQuery
{
    /// <summary>
    /// Compiles and executes one grid page.
    /// </summary>
    /// <param name="client">An already-open low-level client. Never constructed, opened, or closed
    /// here — connection ownership stays with the host, mirroring every sibling adapter's own
    /// rule.</param>
    /// <param name="request">The validated IR — the same shape <c>SearchQueryBuilder.Build</c> itself
    /// accepts. <see cref="SearchQueryRequest.Page"/> must be a <see cref="RangePage"/>; a
    /// <see cref="NonePage"/> is an export and goes through <see cref="OpenSearchExportStream"/>
    /// instead.</param>
    /// <param name="gridSessionId">The host's own identifier for the logical grid session this request
    /// belongs to — half of PERF-2's cache key (grid session, sort+filter hash), alongside the compiled
    /// shape <see cref="ComputeCursorKey"/> hashes.</param>
    /// <param name="cursorCache">The SHARED cache the host keeps alive across requests for
    /// <paramref name="gridSessionId"/> — see this type's own remarks on why a fresh instance per call
    /// defeats PERF-2 entirely.</param>
    /// <param name="options">Deep-paging configuration; <see langword="null"/> takes the defaults.</param>
    /// <param name="includeRowCount">Whether to also resolve <see cref="OpenSearchGridPage.RowCount"/> —
    /// see that property's own remarks for the cost this opts into.</param>
    /// <param name="cancellationToken">EXP-7's cancellation hook.</param>
    /// <exception cref="OpenSearchClientCompilationException">The request carries a
    /// <see cref="NonePage"/>.</exception>
    public static async Task<OpenSearchGridPage> FetchPageAsync(
        IOpenSearchLowLevelClient client,
        SearchQueryRequest request,
        string gridSessionId,
        ISearchCursorCache cursorCache,
        OpenSearchDeepPagingOptions? options = null,
        bool includeRowCount = false,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(gridSessionId);
        ArgumentNullException.ThrowIfNull(cursorCache);

        if (request.Page is not RangePage page)
        {
            throw new OpenSearchClientCompilationException(
                $"A grid page fetch requires a RangePage, but this request carries " +
                $"'{request.Page.GetType().Name}'. An unpaginated request (page: none) is an export — call " +
                "OpenSearchExportStream.StreamAsync instead.");
        }

        var deepPaging = options ?? OpenSearchDeepPagingOptions.Default;
        deepPaging.Validate();

        // GRP-1's dispatch, read back from the SAME IR pieces the compiler itself resolves it from —
        // not re-derived, exactly like Craticula.MongoDB.Driver.MongoGridQuery's identical reuse.
        var plan = GroupingPlan.Resolve(request.Group, request.Aggregations);

        return plan is { GroupColumn: { } groupColumn }
            ? await FetchGroupedPageAsync(
                client, request, groupColumn, plan, page, gridSessionId, cursorCache, deepPaging, includeRowCount, cancellationToken)
                .ConfigureAwait(false)
            : await FetchRowPageAsync(
                client, request, page, gridSessionId, cursorCache, deepPaging, includeRowCount, cancellationToken)
                .ConfigureAwait(false);
    }

    // ---- ungrouped: plain from/size, or PIT + search_after beyond MaxResultWindow -------------------

    private static async Task<OpenSearchGridPage> FetchRowPageAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, RangePage page, string gridSessionId,
        ISearchCursorCache cursorCache, OpenSearchDeepPagingOptions options, bool includeRowCount,
        CancellationToken cancellationToken)
    {
        var columns = request.Schema.FieldOrder;
        var types = ResolveFieldTypes(columns, request.Schema);

        // SC-4's physical field mapping, resolved the SAME way ResolveGroupFieldTarget already does for
        // the grouped path (review finding) — a colId's own `_source` key can differ from its logical
        // name when a schema declares `physical.search.field`, and reading `_source[colId]` directly
        // would silently return null for a remapped column even though the compiler correctly filtered
        // and sorted against the real underlying field.
        var sourceFields = ResolveSourceFields(columns, request.Schema);

        var pageSize = page.EndRow - page.StartRow;

        // AG-3's Lazy trick: fetch one MORE than requested so a full window means "there might be
        // more" and a short one means "this is the end" — applied uniformly whether or not this
        // particular fetch crosses the deep-paging threshold.
        var fetchSize = pageSize + 1;

        var batch = page.StartRow + fetchSize <= options.MaxResultWindow
            ? await FetchPlainWindowAsync(client, request, sourceFields, types, page.StartRow, fetchSize, cancellationToken).ConfigureAwait(false)
            : await FetchDeepWindowAsync(
                client, request, sourceFields, types, page.StartRow, fetchSize, gridSessionId, cursorCache, options, cancellationToken)
                .ConfigureAwait(false);

        var lastRow = batch.Rows.Count <= pageSize;
        var rows = lastRow ? batch.Rows : batch.Rows.Take(pageSize).ToList();

        long? rowCount = includeRowCount
            ? await CountRowsAsync(client, request, options, cancellationToken).ConfigureAwait(false)
            : null;

        return new OpenSearchGridPage { Columns = columns, Rows = rows, RowCount = rowCount, LastRow = lastRow };
    }

    private static async Task<HitBatch> FetchPlainWindowAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, IReadOnlyList<string> sourceFields, FieldType[] types,
        int startRow, int size, CancellationToken cancellationToken)
    {
        var compiled = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = startRow, EndRow = startRow + size } });
        var body = compiled.ToArtifact();

        var response = await client
            .SearchAsync<StringResponse>(request.Schema.Source, PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        return ReadHitBatch(response, sourceFields, types, fallbackPitId: string.Empty);
    }

    /// <summary>OSE-10: the PIT + <c>search_after</c> path — reused for the walk-forward catch-up steps
    /// and the final page fetch alike (see <see cref="FetchDeepWindowAsync"/>).</summary>
    private static async Task<HitBatch> FetchPitWindowAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, IReadOnlyList<string> sourceFields, FieldType[] types,
        string pitId, JsonNode? afterCursor, int size, TimeSpan keepAlive, CancellationToken cancellationToken)
    {
        var compiled = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = size } });
        var body = compiled.ToArtifact();

        // `from` has no meaning together with a PIT/search_after (the engine rejects a nonzero one
        // outright, and a literal 0 is inert but misleading) — the window's start is entirely carried
        // by `search_after` instead.
        body.Remove("from");
        body["pit"] = new JsonObject { ["id"] = pitId, ["keep_alive"] = FormatKeepAlive(keepAlive) };

        if (afterCursor is not null)
        {
            body["search_after"] = afterCursor.DeepClone();
        }

        // A PIT-scoped search omits the index entirely — the PIT itself already carries which index(es)
        // it was opened against; ES/OpenSearch reject a request naming BOTH.
        var response = await client.SearchAsync<StringResponse>(PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        return ReadHitBatch(response, sourceFields, types, fallbackPitId: pitId);
    }

    private static async Task<HitBatch> FetchDeepWindowAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, IReadOnlyList<string> sourceFields, FieldType[] types,
        int startRow, int size, string gridSessionId, ISearchCursorCache cursorCache, OpenSearchDeepPagingOptions options,
        CancellationToken cancellationToken)
    {
        // The cache key's own shape excludes `from`/`size` by construction (ComputeCursorKey reads only
        // {query, sort} off the compiled artifact) — StartRow/EndRow here are arbitrary placeholders
        // that satisfy PageSpecValidator, never reflected in the key.
        var shape = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = 1 } });
        var cacheKey = ComputeCursorKey(gridSessionId, shape);

        var cached = await cursorCache.TryGetAsync(cacheKey, cancellationToken).ConfigureAwait(false);

        string pitId;
        JsonNode? afterCursor;
        var currentRow = 0;

        // Tracks whether `pitId` has ever reached the cache (via a successful SetAsync below) —
        // review finding: a PIT opened in the cold-start branch is unprotected between PointInTime.OpenAsync
        // returning and the FIRST successful SetAsync; any failure in that window (cancellation,
        // transport error, a non-2xx response) must close THIS call's own PIT explicitly, since
        // RemoveAsync in the catch below cannot find something that was never written.
        var pitReachedCache = false;

        if (cached is not null && cached.UpToRow <= startRow)
        {
            // Exact match (O(1) reuse) or ahead-with-a-gap (the walk below closes it) — both continue
            // the SAME PIT, so nothing is closed here.
            pitId = cached.PitId;
            afterCursor = cached.Cursor;
            currentRow = cached.UpToRow;
            pitReachedCache = true;
        }
        else
        {
            // Absent, expired, or the request moved backward of the cached position — AG Grid never
            // pages backward mid-session in a way that matters here, so this is treated as a cold
            // start. Whatever was physically cached is popped and its PIT best-effort closed before a
            // fresh one is opened; RemoveAsync (not TryGetAsync) is what hands the stale entry back
            // specifically so an EXPIRED-but-still-present one can still be closed (see
            // ISearchCursorCache's own remarks).
            var previous = await cursorCache.RemoveAsync(cacheKey, cancellationToken).ConfigureAwait(false);
            if (previous is { PitId.Length: > 0 })
            {
                await PointInTime.TryCloseAsync(client, previous.PitId, options.Flavour).ConfigureAwait(false);
            }

            pitId = await PointInTime.OpenAsync(client, request.Schema.Source, options.PitKeepAlive, options.Flavour, cancellationToken).ConfigureAwait(false);
            afterCursor = null;
        }

        try
        {
            // Walk forward in WalkBatchSize-sized batches, discarding the hits, until reaching the
            // requested offset. A batch shorter than requested means the dataset ended inside it; the
            // loop naturally converges on the `Rows.Count == 0` case below on its next iteration rather
            // than needing a separate early-exit branch.
            while (currentRow < startRow)
            {
                var step = Math.Min(options.WalkBatchSize, startRow - currentRow);
                var stepBatch = await FetchPitWindowAsync(client, request, sourceFields, types, pitId, afterCursor, step, options.PitKeepAlive, cancellationToken)
                    .ConfigureAwait(false);
                pitId = stepBatch.PitId;

                if (stepBatch.Rows.Count == 0)
                {
                    if (afterCursor is not null)
                    {
                        await cursorCache.SetAsync(
                            cacheKey, new SearchCursorEntry(pitId, currentRow, afterCursor, Expiry(options)), cancellationToken)
                            .ConfigureAwait(false);
                        pitReachedCache = true;
                    }
                    else
                    {
                        // Nothing to remember: a cold walk's very first step already found zero hits, so
                        // there is no real search_after boundary to cache — review finding: caching a
                        // placeholder `new JsonArray()` here is NEVER a valid search_after payload, and
                        // every future page request for this (session, hash) would 400 against it for
                        // the rest of PitKeepAlive's window. Close the PIT this call opened instead.
                        await PointInTime.TryCloseAsync(client, pitId, options.Flavour).ConfigureAwait(false);
                    }

                    return new HitBatch([], [], pitId);
                }

                afterCursor = stepBatch.SortKeys[^1];
                currentRow += stepBatch.Rows.Count;

                await cursorCache.SetAsync(cacheKey, new SearchCursorEntry(pitId, currentRow, afterCursor, Expiry(options)), cancellationToken)
                    .ConfigureAwait(false);
                pitReachedCache = true;
            }

            var final = await FetchPitWindowAsync(client, request, sourceFields, types, pitId, afterCursor, size, options.PitKeepAlive, cancellationToken)
                .ConfigureAwait(false);

            // Cache the boundary AFTER the page actually returned to the caller (size - 1 = the requested
            // pageSize, per AG-3's own +1 trick), never the probe row's own boundary — the same subtlety
            // Craticula.Dapper.DapperExportStream's own keyset walk has to get right for its own probe row.
            var pageSize = size - 1;
            var kept = Math.Min(final.Rows.Count, pageSize);
            if (kept > 0)
            {
                await cursorCache.SetAsync(
                    cacheKey, new SearchCursorEntry(final.PitId, startRow + kept, final.SortKeys[kept - 1], Expiry(options)), cancellationToken)
                    .ConfigureAwait(false);
                pitReachedCache = true;
            }

            return final;
        }
        catch (Exception ex)
        {
            // Review finding: a PIT-scoped fetch failure must not leave this (session, hash)'s cache
            // entry pointing at a cursor the engine just refused — without eviction, TryGetAsync keeps
            // handing it back and every subsequent page request fails identically until PitKeepAlive
            // lapses. But eviction is warranted ONLY when the engine actually REJECTED this cursor
            // (IsCursorRejection's own remarks) — a 5xx/transport failure or a cancellation says nothing
            // about the cursor's own validity, and evicting on those would throw away a perfectly
            // healthy, already-cached cursor (forcing every subsequent deep page to cold-walk from zero
            // for no reason — exactly the round-trip cost PERF-2 exists to avoid) and, under concurrency,
            // could destroy or close a DIFFERENT in-flight request's still-live PIT if it raced ahead and
            // overwrote this entry first.
            string? toClose = null;

            if (IsCursorRejection(ex))
            {
                var orphaned = await cursorCache.RemoveAsync(cacheKey, CancellationToken.None).ConfigureAwait(false);
                toClose = orphaned?.PitId;
            }

            if (string.IsNullOrEmpty(toClose) && !pitReachedCache)
            {
                // Pure resource hygiene, decoupled from the eviction decision above and applied under
                // ANY failure (including cancellation): the PIT this call itself opened never reached the
                // cache, so nothing else will ever close it if this call does not.
                toClose = pitId;
            }

            if (!string.IsNullOrEmpty(toClose))
            {
                await PointInTime.TryCloseAsync(client, toClose, options.Flavour).ConfigureAwait(false);
            }

            throw;
        }
    }

    private static async Task<long?> CountRowsAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, OpenSearchDeepPagingOptions options, CancellationToken cancellationToken)
    {
        var compiled = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = 0 } });
        var body = compiled.ToArtifact();

        // PERF-3: capped by default, never the uncapped `true` unless the host opted in (OSE-16, ExactRowCount) — see
        // OpenSearchGridPage.RowCount's own remarks for why MaxResultWindow is reused as the cap rather than a second knob.
        body["track_total_hits"] = options.ExactRowCount ? true : options.MaxResultWindow;

        var response = await client.SearchAsync<StringResponse>(request.Schema.Source, PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        using var document = JsonDocument.Parse(response.Body!);
        var total = document.RootElement.GetProperty("hits").GetProperty("total");

        // A capped track_total_hits makes the engine clamp `value` at the cap and report a `relation`
        // of "gte" (never "eq") once the true count exceeds it — review finding: reading `value` alone
        // would report the capped number as though it were EXACT, right at the boundary where PERF-2's
        // own deep-paging feature is supposed to let the grid keep going past it. OpenSearchGridPage's
        // own RowCount doc names this exact case (case 2 of its two null cases) as "unknown, keep
        // asking" — this is that documented contract, kept.
        return total.GetProperty("relation").GetString() == "eq" ? total.GetProperty("value").GetInt64() : null;
    }

    // ---- grouped: first block direct, later blocks via the synthetic-zero-page + after splice --------

    private static async Task<OpenSearchGridPage> FetchGroupedPageAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, string groupColumn, GroupingPlan plan, RangePage page,
        string gridSessionId, ISearchCursorCache cursorCache, OpenSearchDeepPagingOptions options, bool includeRowCount,
        CancellationToken cancellationToken)
    {
        var columns = new List<string>(1 + plan.Aggregations.Count) { groupColumn };
        columns.AddRange(plan.Aggregations.Select(a => a.OutputName));
        var types = ResolveGroupedColumnTypes(columns, plan, request.Schema);

        var blockSize = page.EndRow - page.StartRow;

        // The cache key's own shape excludes `composite.size`/`after` by construction
        // (ComputeCursorKey reads only {query, composite.sources}) — the block size below is never
        // reflected in it, matching the row-level path's identical exclusion of `from`/`size`.
        var shape = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = 1 } });
        var cacheKey = ComputeCursorKey(gridSessionId, shape);

        var (rows, lastRow) = await FetchGroupedWindowAsync(
                client, request, groupColumn, plan, columns, types, page, blockSize, cursorCache, cacheKey, options, cancellationToken)
            .ConfigureAwait(false);

        // Review finding: deliberately OUTSIDE the try/catch FetchGroupedWindowAsync owns.
        // CountBucketsAsync is a SEPARATE call that runs AFTER the page fetch (and its own SetAsync)
        // already succeeded — a failure here says nothing about the cursor's own validity and must never
        // evict a cache entry a moment-earlier successful fetch just wrote. It is an opt-in value
        // (includeRowCount); if it fails, let it fail on its own terms without touching the cursor cache.
        long? rowCount = includeRowCount
            ? await CountBucketsAsync(client, request, groupColumn, cancellationToken).ConfigureAwait(false)
            : null;

        return new OpenSearchGridPage { Columns = columns, Rows = rows, RowCount = rowCount, LastRow = lastRow };
    }

    /// <summary>
    /// The cursor-dependent half of <see cref="FetchGroupedPageAsync"/>: the walk-forward-then-final-fetch
    /// sequence and the try/catch that guards it. Split out specifically so <see cref="CountBucketsAsync"/>
    /// (an unrelated, separately-failable call) can run OUTSIDE this scope in the caller — see this
    /// method's own catch block and <see cref="FetchGroupedPageAsync"/>'s own remarks.
    /// </summary>
    private static async Task<(IReadOnlyList<IReadOnlyList<object?>> Rows, bool LastRow)> FetchGroupedWindowAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, string groupColumn, GroupingPlan plan,
        IReadOnlyList<string> columns, FieldType[] types, RangePage page, int blockSize, ISearchCursorCache cursorCache,
        string cacheKey, OpenSearchDeepPagingOptions options, CancellationToken cancellationToken)
    {
        JsonNode? afterCursor = null;
        var currentRow = 0;

        if (page.StartRow > 0)
        {
            var cached = await cursorCache.TryGetAsync(cacheKey, cancellationToken).ConfigureAwait(false);

            if (cached is not null && cached.UpToRow <= page.StartRow)
            {
                afterCursor = cached.Cursor;
                currentRow = cached.UpToRow;
            }
            else
            {
                // Absent, expired, or behind the request. Composite paging carries no PIT to close
                // (see this type's own remarks) — RemoveAsync here only clears the stale slot.
                await cursorCache.RemoveAsync(cacheKey, cancellationToken).ConfigureAwait(false);
            }
        }

        try
        {
            while (currentRow < page.StartRow)
            {
                var step = Math.Min(options.WalkBatchSize, page.StartRow - currentRow);
                var stepBatch = await FetchBucketWindowAsync(client, request, groupColumn, plan, columns, types, step, afterCursor, cancellationToken)
                    .ConfigureAwait(false);

                if (stepBatch.Rows.Count == 0)
                {
                    if (afterCursor is not null)
                    {
                        await cursorCache.SetAsync(
                            cacheKey, new SearchCursorEntry(string.Empty, currentRow, afterCursor, Expiry(options)), cancellationToken)
                            .ConfigureAwait(false);
                    }

                    // Else: a cold walk's very first step already found zero buckets — there is no real
                    // `after` key to remember, and caching a placeholder `new JsonObject()` here is
                    // exactly the never-a-valid-cursor entry the review flagged (the engine 400s on
                    // reuse for the rest of PitKeepAlive's window).

                    return ([], true);
                }

                afterCursor = stepBatch.Keys[^1];
                currentRow += stepBatch.Rows.Count;

                await cursorCache.SetAsync(cacheKey, new SearchCursorEntry(string.Empty, currentRow, afterCursor, Expiry(options)), cancellationToken)
                    .ConfigureAwait(false);
            }

            var final = await FetchBucketWindowAsync(client, request, groupColumn, plan, columns, types, blockSize + 1, afterCursor, cancellationToken)
                .ConfigureAwait(false);

            var lastRow = final.Rows.Count <= blockSize;
            var kept = lastRow ? final.Rows.Count : blockSize;
            var rows = lastRow ? final.Rows : final.Rows.Take(blockSize).ToList();

            if (kept > 0)
            {
                await cursorCache.SetAsync(
                    cacheKey, new SearchCursorEntry(string.Empty, page.StartRow + kept, final.Keys[kept - 1], Expiry(options)), cancellationToken)
                    .ConfigureAwait(false);
            }

            return (rows, lastRow);
        }
        catch (Exception ex)
        {
            // Mirrors the row-level path's own eviction discipline (see FetchDeepWindowAsync's own
            // remarks): evict ONLY when the engine actually REJECTED this composite `after` key (a
            // 4xx-range status via IsCursorRejection) — a poisoned/invalid `after` must not keep failing
            // every subsequent page request for this (session, hash) until PitKeepAlive lapses. A
            // 5xx/transport failure or a cancellation says nothing about the cursor's own validity and
            // must not discard an already-cached, healthy one. No PIT to close for a grouped entry (its
            // PitId is always the empty string), so eviction alone is this path's own equivalent.
            if (IsCursorRejection(ex))
            {
                await cursorCache.RemoveAsync(cacheKey, CancellationToken.None).ConfigureAwait(false);
            }

            throw;
        }
    }

    private static async Task<BucketBatch> FetchBucketWindowAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, string groupColumn, GroupingPlan plan,
        IReadOnlyList<string> columns, FieldType[] types, int size, JsonNode? after, CancellationToken cancellationToken)
    {
        var compiled = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = size } });
        var body = compiled.ToArtifact();

        if (after is not null)
        {
            SpliceAfter(body, groupColumn, after);
        }

        var response = await client.SearchAsync<StringResponse>(request.Schema.Source, PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        using var document = JsonDocument.Parse(response.Body!);
        var bucketsElement = document.RootElement.GetProperty("aggregations").GetProperty(groupColumn).GetProperty("buckets");

        var rows = new List<IReadOnlyList<object?>>(bucketsElement.GetArrayLength());
        var keys = new List<JsonNode>(bucketsElement.GetArrayLength());

        foreach (var bucket in bucketsElement.EnumerateArray())
        {
            keys.Add(JsonNode.Parse(bucket.GetProperty("key").GetRawText())!);

            var cells = new object?[columns.Count];
            cells[0] = OpenSearchValueReader.ReadBucketKey(bucket, groupColumn, types[0]);
            for (var i = 0; i < plan.Aggregations.Count; i++)
            {
                cells[i + 1] = OpenSearchValueReader.ReadMetric(bucket, plan.Aggregations[i].OutputName, types[i + 1]);
            }

            rows.Add(cells);
        }

        return new BucketBatch(rows, keys);
    }

    /// <summary>
    /// OSE-11(d)'s splice: <c>{"after": &lt;bucket key&gt;}</c> injected into the compiled
    /// <c>composite</c> object — the one piece of the search body <c>Craticula.Search</c> has no
    /// rendering for at all (the compiler refuses ANY non-zero <see cref="RangePage.StartRow"/> for a
    /// grouped level, which is exactly why the request compiled here is the SYNTHETIC zero-page one).
    /// </summary>
    private static void SpliceAfter(JsonObject body, string groupColumn, JsonNode after)
    {
        var level = body["aggs"]!.AsObject()[groupColumn]!.AsObject();
        level["composite"]!.AsObject()["after"] = after.DeepClone();
    }

    /// <summary>
    /// AR-8/BM-2's null bucket accounted for, not just the distinct-value count. <c>missing_bucket:
    /// true</c> (<c>Craticula.Search.SearchQueryBuilder.RenderGroupedAggregations</c>'s own rendering)
    /// gives a null/missing group value its OWN bucket rather than dropping it — but <c>cardinality</c>
    /// only counts distinct values among documents that HAVE the field, so whenever any document is
    /// missing it, the composite returns N buckets (including the missing-value one) while this count
    /// alone would report N-1, and the grid would never request the last group's row (review finding).
    /// A sibling <c>missing</c> aggregation on the SAME field reports how many documents lack it; its
    /// <c>doc_count</c> contributes at most ONE extra bucket, matching <c>missing_bucket</c>'s own
    /// single null bucket.
    /// </summary>
    private static async Task<long> CountBucketsAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, string groupColumn, CancellationToken cancellationToken)
    {
        // Reuses the compiler's OWN query wrapping (GRP-5's drill-down + the user's filter, already
        // conjoined into `bool.filter`) rather than re-deriving it — the same "read back a decision
        // already made" discipline this package applies to GroupingPlan itself. Only `aggs`/`size` are
        // overridden below; `RangePage` here is an arbitrary valid placeholder (RequireBucketWindow only
        // needs StartRow == 0), discarded along with the rest of the composite it produced.
        var compiled = SearchQueryBuilder.Build(request with { Page = new RangePage { StartRow = 0, EndRow = 1 } });
        var body = compiled.ToArtifact();
        body.Remove("from");
        body["size"] = 0;

        var groupField = ResolveGroupFieldTarget(request.Schema, groupColumn);
        body["aggs"] = new JsonObject
        {
            ["bucket_count"] = new JsonObject { ["cardinality"] = new JsonObject { ["field"] = groupField } },
            ["missing_group_values"] = new JsonObject { ["missing"] = new JsonObject { ["field"] = groupField } }
        };

        var response = await client.SearchAsync<StringResponse>(request.Schema.Source, PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        using var document = JsonDocument.Parse(response.Body!);
        var aggregations = document.RootElement.GetProperty("aggregations");
        var distinctCount = aggregations.GetProperty("bucket_count").GetProperty("value").GetInt64();
        var missingCount = aggregations.GetProperty("missing_group_values").GetProperty("doc_count").GetInt64();

        return distinctCount + (missingCount > 0 ? 1 : 0);
    }

    /// <summary>SC-4/SC-3's field-target rule, replicated here because
    /// <c>Craticula.Search.SearchQueryBuilder</c>'s own field resolver is private: a group column's
    /// bucket key targets its keyword sub-field when it is a string (falling back to the raw field when
    /// the schema declares none), the raw field for everything else — exactly
    /// <c>SearchQueryBuilder.RenderGroupedAggregations</c>'s own choice for the composite source.</summary>
    private static string ResolveGroupFieldTarget(GridSchema schema, string groupColumn)
    {
        var field = schema.Fields[groupColumn];
        var mapping = field.Physical?.Search;
        var raw = mapping?.Field ?? groupColumn;
        return field.Type == FieldType.String ? mapping?.KeywordSubField ?? raw : raw;
    }

    // ---- PIT lifecycle -------------------------------------------------------------------------------

    // ---- shared plumbing -------------------------------------------------------------------------------

    /// <summary>One row-level batch: materialized cells, each row's own <c>sort</c> array (for the NEXT
    /// batch's <c>search_after</c>), and the PIT id the response itself echoed back (which can rotate
    /// between calls — always use the LATEST one, never the one that opened the PIT).</summary>
    private readonly record struct HitBatch(IReadOnlyList<IReadOnlyList<object?>> Rows, IReadOnlyList<JsonNode> SortKeys, string PitId);

    /// <summary>One grouped-level batch: materialized cells and each bucket's own composite <c>key</c>
    /// (for the NEXT batch's <c>composite.after</c>).</summary>
    private readonly record struct BucketBatch(IReadOnlyList<IReadOnlyList<object?>> Rows, IReadOnlyList<JsonNode> Keys);

    /// <summary><paramref name="sourceFields"/> is the SC-4 PHYSICAL name each column's <c>_source</c>
    /// cell is actually keyed under (see <see cref="ResolveSourceFields"/>) — not necessarily the same
    /// string as the logical colId a caller ultimately reports the cell under, which is why this method
    /// takes no <c>columns</c> parameter of its own at all.</summary>
    private static HitBatch ReadHitBatch(StringResponse response, IReadOnlyList<string> sourceFields, FieldType[] types, string fallbackPitId)
    {
        using var document = JsonDocument.Parse(response.Body!);
        var root = document.RootElement;
        var pitId = root.TryGetProperty("pit_id", out var pitElement) ? pitElement.GetString()! : fallbackPitId;
        var hitsElement = root.GetProperty("hits").GetProperty("hits");

        var rows = new List<IReadOnlyList<object?>>(hitsElement.GetArrayLength());
        var sortKeys = new List<JsonNode>(hitsElement.GetArrayLength());

        foreach (var hit in hitsElement.EnumerateArray())
        {
            var source = hit.GetProperty("_source");
            var cells = new object?[sourceFields.Count];
            for (var i = 0; i < sourceFields.Count; i++)
            {
                cells[i] = OpenSearchValueReader.Read(source, sourceFields[i], types[i]);
            }

            rows.Add(cells);

            if (hit.TryGetProperty("sort", out var sortElement))
            {
                sortKeys.Add(JsonNode.Parse(sortElement.GetRawText())!);
            }
        }

        return new HitBatch(rows, sortKeys, pitId);
    }

    private static DateTimeOffset Expiry(OpenSearchDeepPagingOptions options) => DateTimeOffset.UtcNow + options.PitKeepAlive;

    private static string FormatKeepAlive(TimeSpan value) => $"{Math.Max(1, (long)value.TotalSeconds)}s";

    /// <summary>
    /// Deliberately checks the raw HTTP status rather than <c>StringResponse.Success</c> — found
    /// by this story's own review: <c>OpenSearch.Net</c>'s low-level client whitelists certain non-2xx
    /// statuses as "known" per endpoint (a 404 on <c>_search</c>, the exact shape a stale/closed PIT
    /// returns, reads back as <see langword="true"/> for <c>Success</c>), which would silently let a
    /// genuine engine error flow into this package's own JSON parsing instead of surfacing as this
    /// exception — the same "a plausible-looking success that is actually a failure" register SQL-7(b)
    /// and MDB-9 refuse for a compiled request, reached here for a TRANSPORT response instead.
    /// </summary>
    internal static void RequireSuccess(StringResponse response)
    {
        if (response.HttpStatusCode is >= 200 and < 300)
        {
            ThrowIfTimedOut(response.Body);
            return;
        }

        throw new OpenSearchClientCompilationException(
            $"The OpenSearch/Elasticsearch call failed (HTTP {response.HttpStatusCode?.ToString() ?? "n/a"}): " +
            Truncate(response.Body ?? response.DebugInformation, 500),
            response.OriginalException ?? new InvalidOperationException("The call did not succeed."),
            response.HttpStatusCode);
    }

    /// <summary>
    /// TL-5 / FR-7: a search that ran out of time still answers 200, with the hits it had found and
    /// <c>"timed_out": true</c>. Returning them would show a partial page as a complete one, so the answer is
    /// an error. Only the top-level members are read; the first of them that is <c>timed_out</c> decides.
    /// </summary>
    internal static void ThrowIfTimedOut(string? body)
    {
        if (string.IsNullOrEmpty(body))
        {
            return;
        }

        var reader = new Utf8JsonReader(Encoding.UTF8.GetBytes(body));
        if (!reader.Read() || reader.TokenType != JsonTokenType.StartObject)
        {
            return;
        }

        while (reader.Read() && reader.TokenType == JsonTokenType.PropertyName)
        {
            var isTimedOut = reader.ValueTextEquals("timed_out");
            reader.Read();
            if (isTimedOut)
            {
                if (reader.TokenType == JsonTokenType.True)
                {
                    throw new QueryTimeoutException();
                }

                return;
            }

            reader.Skip();
        }
    }

    /// <summary>
    /// The eviction test <see cref="FetchDeepWindowAsync"/>/<see cref="FetchGroupedWindowAsync"/>'s own
    /// catch blocks apply: only a 4xx-range status from <see cref="RequireSuccess"/> means the engine
    /// REJECTED this specific cursor/request outright — a stale/invalid <c>search_after</c> payload, a
    /// closed PIT. A 5xx/transport failure, an <see cref="OperationCanceledException"/>, or (on the
    /// grouped path) a failure in the SEPARATE <see cref="CountBucketsAsync"/> call that runs AFTER a
    /// page fetch whose own <c>SetAsync</c> already succeeded, says nothing about the cursor's own
    /// validity and must never evict a perfectly healthy, already-cached entry.
    /// </summary>
    private static bool IsCursorRejection(Exception ex) =>
        ex is OpenSearchClientCompilationException { HttpStatusCode: >= 400 and < 500 };

    private static string Truncate(string? text, int max)
    {
        text ??= string.Empty;
        return text.Length <= max ? text : text[..max] + "...";
    }

    private static FieldType[] ResolveFieldTypes(IReadOnlyList<string> columns, GridSchema schema)
    {
        var types = new FieldType[columns.Count];
        for (var i = 0; i < columns.Count; i++)
        {
            types[i] = schema.Fields.TryGetValue(columns[i], out var field)
                ? field.Type
                : throw new OpenSearchClientCompilationException($"Field '{columns[i]}' is not declared in the GridSchema.");
        }

        return types;
    }

    /// <summary>
    /// SC-4's physical mapping for an ORDINARY <c>_source</c> read: <c>physical.search.field</c> when a
    /// field declares one, the colId itself otherwise — the same <c>mapping?.Field ?? field</c> rule
    /// <c>Craticula.Search.SearchQueryBuilder.Resolve</c> (private to that package) and this package's
    /// own <see cref="ResolveGroupFieldTarget"/> both already apply for FILTERING/SORTING and for a
    /// group column's composite source respectively. Review finding: <see cref="ReadHitBatch"/> used to
    /// read <c>_source</c> by colId directly, so a remapped column's cells all silently came back
    /// <see langword="null"/> (a missing <see cref="JsonElement"/> property, per
    /// <see cref="OpenSearchValueReader.Read"/>'s own contract) even though the compiler correctly
    /// filtered/sorted against the real underlying field. No keyword-sub-field fallback here, unlike
    /// <see cref="ResolveGroupFieldTarget"/>: <c>_source</c> is the document's own verbatim stored field,
    /// never the search/aggregation-only multi-field a keyword sub-field addresses.
    /// </summary>
    private static string[] ResolveSourceFields(IReadOnlyList<string> columns, GridSchema schema)
    {
        var fields = new string[columns.Count];
        for (var i = 0; i < columns.Count; i++)
        {
            fields[i] = schema.Fields[columns[i]].Physical?.Search?.Field ?? columns[i];
        }

        return fields;
    }

    /// <summary>Mirrors <c>Craticula.MongoDB.Driver.MongoGridQuery.ResolveColumnTypes</c>'s own rule:
    /// the bucket column (index 0) is a real schema field, resolved directly; every remaining column is
    /// an aggregation output, resolved by position against <paramref name="plan"/>'s own aggregation
    /// list.</summary>
    private static FieldType[] ResolveGroupedColumnTypes(IReadOnlyList<string> columns, GroupingPlan plan, GridSchema schema)
    {
        var types = new FieldType[columns.Count];
        types[0] = schema.Fields[columns[0]].Type;

        for (var i = 0; i < plan.Aggregations.Count; i++)
        {
            types[i + 1] = ResolveAggregationType(plan.Aggregations[i], schema);
        }

        return types;
    }

    /// <summary>AGG-1's rule for <see cref="AggregationFunc.Count"/> (always an integer) plus the
    /// identical <see cref="AggregationFunc.Avg"/> widening every sibling adapter applies
    /// (<c>Craticula.Dapper.DapperGridQuery.ResolveAggregationType</c>,
    /// <c>Craticula.MongoDB.Driver.MongoGridQuery.ResolveAggregationType</c>): the DECLARED output type
    /// is widened to <see cref="FieldType.Double"/> unless the source is already
    /// <see cref="FieldType.Decimal"/>.
    ///
    /// <para><b>This package's own review previously argued the widening was unnecessary here —
    /// that was wrong.</b> The reasoning ("every metric already materializes through double-precision
    /// floating point on the wire") is true of the ENGINE's response but does not describe what THIS
    /// reader does with it: <see cref="OpenSearchValueReader.ReadMetric"/>'s <see cref="FieldType.Int64"/>
    /// arm does <c>checked((long)value.GetDouble())</c>, so an <c>avg</c> over an
    /// <see cref="FieldType.Int64"/>-declared source (which, unwidened, resolves its OUTPUT type to that
    /// same <see cref="FieldType.Int64"/>) truncates a genuine fractional average (the engine returns
    /// <c>1.5</c>, the grid receives <c>1</c>) — exactly the failure every sibling's own widening exists
    /// to prevent. Widening the DECLARED output type is what routes the value through
    /// <see cref="OpenSearchValueReader.ReadMetric"/>'s <see cref="FieldType.Double"/> arm instead, which
    /// keeps the fraction.</para>
    /// </summary>
    private static FieldType ResolveAggregationType(Aggregation aggregation, GridSchema schema)
    {
        if (aggregation.Func == AggregationFunc.Count)
        {
            return FieldType.Int64;
        }

        var sourceType = schema.Fields[aggregation.Field].Type;
        return aggregation.Func == AggregationFunc.Avg && sourceType != FieldType.Decimal
            ? FieldType.Double
            : sourceType;
    }

    // ---- PERF-2's cache key ----------------------------------------------------------------------------

    /// <summary>
    /// PERF-2's cache key: <paramref name="gridSessionId"/> plus a stable hash of the compiled shape
    /// that determines whether a cursor can be reused — <c>{index, query, sort}</c> for an ungrouped
    /// request, <c>{index, query, composite.sources}</c> for a grouped one (the index is included
    /// specifically so two indices sharing an otherwise-identical shape never collide under one
    /// session — see this method's own remarks). Deliberately EXCLUDES <c>from</c>/<c>size</c>
    /// and <c>composite.size</c>/<c>after</c>: two requests differing only in WHICH page/block they ask
    /// for still address the SAME logical walk, and must hash identically for PERF-2's reuse to ever
    /// fire at all.
    ///
    /// <para><b>Why this is a pure, <see langword="internal"/> helper.</b> Unit-tested directly via
    /// <c>InternalsVisibleTo</c> (mirroring <c>Craticula.Dapper.DapperParameterBinder.ToTypedArray</c>'s
    /// own precedent) rather than only indirectly through a live-cluster round trip: the determinism
    /// property PERF-2/the DoD asks for — same request compiles to the same key, a changed sort or
    /// filter compiles to a DIFFERENT one — is exactly a property of THIS function, not of the cluster,
    /// and is cheap to pin without one.</para>
    /// </summary>
    internal static string ComputeCursorKey(string gridSessionId, SearchQuery compiled)
    {
        ArgumentNullException.ThrowIfNull(gridSessionId);
        ArgumentNullException.ThrowIfNull(compiled);

        var shape = new JsonObject
        {
            // Two different indices sharing an otherwise-identical {query, sort}/{query, sources} shape
            // is a real multi-tenant pattern (orders_tenant_a / orders_tenant_b) -- without the index in
            // the key, they collide under one gridSessionId and a reused cursor silently serves the
            // WRONG index's rows against the new request (FetchPitWindowAsync deliberately omits the
            // index from the request body, since the PIT itself already carries it -- the cache key is
            // the only place left that must still distinguish them).
            ["index"] = compiled.Index
        };

        if (compiled.Query is not null)
        {
            shape["query"] = compiled.Query.DeepClone();
        }

        if (compiled.Aggs is not null)
        {
            var level = compiled.Aggs.DeepClone()!.AsObject().First().Value!.AsObject();
            shape["sources"] = level["composite"]!.AsObject()["sources"]!.DeepClone();
        }
        else if (compiled.Sort is not null)
        {
            shape["sort"] = compiled.Sort.DeepClone();
        }

        var canonical = Canonicalize(shape)!.ToJsonString();
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(canonical));
        return $"{gridSessionId}:{Convert.ToHexString(hash)}";
    }

    /// <summary>Object keys sorted, array order preserved — mirrors
    /// <c>Craticula.Search.Tests.SearchFixtureCompiler.CanonicalJson</c>'s own reasoning: no object key
    /// in this DSL is order-sensitive (OSE-0), but <c>sort</c>'s element order and
    /// <c>composite.sources</c>' element order both ARE. Not load-bearing for THIS compiler's own output
    /// (which is already deterministic) so much as a defensive guarantee that the hash cannot drift if a
    /// future change ever made object key order incidental.</summary>
    private static JsonNode? Canonicalize(JsonNode? node) => node switch
    {
        JsonObject o => new JsonObject(o
            .OrderBy(property => property.Key, StringComparer.Ordinal)
            .Select(property => KeyValuePair.Create(property.Key, Canonicalize(property.Value)))),
        JsonArray a => new JsonArray([.. a.Select(Canonicalize)]),
        _ => node?.DeepClone()
    };
}
