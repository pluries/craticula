using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using Craticula.Core.Export;
using Craticula.Core.Ir;
using Craticula.Core.Schema;
using Craticula.Search;
using OpenSearch.Net;

namespace Craticula.OpenSearch.Client;

/// <summary>
/// The <b>export</b> entry point: every declared field for every matching hit, streamed as
/// <see cref="ExportRow"/>s a writer consumes directly — <c>CsvWriter.WriteAsync(stream, columns,
/// options, destination, ct)</c>.
///
/// <para><b>No session, no cache — a single self-contained walk, unlike the grid path.</b> Export needs
/// no cross-request state at all: it opens ONE PIT, loops <c>_search</c> calls with <c>search_after</c>
/// advancing from the previous batch's own last hit, and closes the PIT in a <c>finally</c> — best
/// effort, even on cancellation or an exception — so nothing outlives this one call's lifetime. This
/// mirrors <c>Craticula.MongoDB.Driver.MongoExportStream</c>'s own "no keyset chunking" simplification
/// on its SQL-executing siblings, for the SAME underlying reason restated for this execution model:
/// <c>Craticula.Search.SearchQueryBuilder.Build</c> renders <c>sort</c> (ending in the SEM-6 stableKey
/// tiebreaker) for ANY row-returning request regardless of <see cref="PageSpec"/> — verified directly in
/// that method's source (only <c>From</c>/<c>Size</c> go <see langword="null"/> under
/// <see cref="NonePage"/>) — so a full, deterministic sort order is already guaranteed with no extra
/// tiebreaker work needed here, and <c>search_after</c> needs exactly that.</para>
///
/// <para><b>Columns are always <c>Schema.FieldOrder</c> — EXP-1(b)'s selectable export column subset has
/// no counterpart on this backend.</b> <see cref="OpenSearchGridPage"/>'s own remarks give the full
/// reasoning: <see cref="SearchQueryRequest"/> carries no <c>Projection</c> member at all (OSE-13: "no
/// <c>_source</c> filtering exists on this backend" runs one layer deeper than the compiled artifact —
/// the IR itself carries no projection to read), so this method has no narrower column list to honour
/// even in principle. A genuine, documented capability gap against
/// <c>Craticula.Dapper.DapperExportStream</c>/<c>Craticula.EntityFrameworkCore.EfCoreExportStream</c>,
/// not an oversight of this story.</para>
///
/// <para><b>Streaming is a contract here, matching the writer's own.</b> Each batch is read off one
/// <c>_search</c> response and yielded row by row rather than buffered into one giant list, so the
/// memory held at any moment is one <see cref="OpenSearchExportOptions.ChunkSize"/>-worth of hits plus
/// one row — a million-hit export costs what a ten-hit one costs, chunk size aside.</para>
///
/// <para><b>Scope, per <c>spec/semantics.md</c>'s EXP-1 v1 scoping</b> ("Group-structured and pivot
/// exports are out of scope for v1"): this method refuses a request carrying a <see cref="GroupSpec"/> —
/// <c>Craticula.AgGrid.AgGridRequestParser</c> already discards group state on any export it resolves,
/// so a caller reaching this method with one has built the request by hand.</para>
///
/// <para><b>What this deliberately does NOT do: enforce EXP-7's row cap.</b> Same reasoning every
/// sibling export stream gives: nothing in the spec or the fixture suite pins whether the cap truncates
/// or fails, and picking one here would bake an unpinned policy into the layer everything else depends
/// on. <see cref="CancellationToken"/> is EXP-7's other half and is implemented, observed once per row
/// yielded.</para>
/// </summary>
public static class OpenSearchExportStream
{
    /// <summary>
    /// Streams every hit matching <paramref name="request"/>, in schema declaration order.
    /// </summary>
    /// <param name="client">An already-open low-level client. Never constructed, opened, or closed
    /// here.</param>
    /// <param name="request">The validated IR. Its <see cref="SearchQueryRequest.Page"/> must be
    /// <see cref="NonePage"/>, and its <see cref="SearchQueryRequest.Group"/> must be
    /// <see langword="null"/>; see the exceptions below.</param>
    /// <param name="options">Chunking configuration; <see langword="null"/> takes EXP-3's 5,000-row
    /// default.</param>
    /// <param name="cancellationToken">EXP-7's cancellation hook. Observed between rows, so cancelling
    /// stops PULLING rather than only stopping whoever was writing — and still runs the PIT close in
    /// this method's own <c>finally</c>.</param>
    /// <exception cref="OpenSearchClientCompilationException">The request carries a
    /// <see cref="RangePage"/> (use <see cref="OpenSearchGridQuery.FetchPageAsync"/>) or a
    /// <see cref="GroupSpec"/> (out of scope for v1).</exception>
    public static async IAsyncEnumerable<ExportRow> StreamAsync(
        IOpenSearchLowLevelClient client,
        SearchQueryRequest request,
        OpenSearchExportOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(request);

        var chunking = options ?? OpenSearchExportOptions.Default;
        chunking.Validate();

        // EXP-1/EXP-2: `exportScope: "all"` is the scope this method serves. A RangePage means
        // `exportScope: "page"`, one bounded window — the identical query a grid block runs — so it is
        // served by the grid entry point rather than run here unbounded. Refusing keeps this file's
        // "no row window, ever" property total instead of true-except-once.
        if (request.Page is not NonePage)
        {
            throw new OpenSearchClientCompilationException(
                $"An export stream requires EXP-2's NonePage, but this request carries " +
                $"'{request.Page.GetType().Name}'. A page-scoped export (exportScope: 'page') is one bounded " +
                "window and is the same query as a grid block: call OpenSearchGridQuery.FetchPageAsync and wrap " +
                "its rows. This method may never apply a row window (EXP-3), so it has no arm for a row range.");
        }

        // EXP-1 v1 scoping: "Group-structured and pivot exports are out of scope for v1." Refused rather
        // than silently flattened — AgGridRequestParser already discards group state on any export it
        // resolves, so a caller reaching this method with one has built the request by hand.
        if (request.Group is not null)
        {
            throw new OpenSearchClientCompilationException(
                "An export stream requires an ungrouped request (spec/semantics.md's EXP-1 v1 scoping: " +
                "group-structured and pivot exports are out of scope). AgGridRequestParser already discards " +
                "group state on any export it resolves — a caller reaching this method with a GroupSpec has " +
                "built the request by hand.");
        }

        var columns = request.Schema.FieldOrder;
        var types = ResolveFieldTypes(columns, request.Schema);

        // SC-4's physical field mapping — see OpenSearchGridQuery.ResolveSourceFields's own remarks:
        // `_source` is keyed by a column's PHYSICAL name, which can differ from its logical colId.
        var sourceFields = ResolveSourceFields(columns, request.Schema);

        var pitId = await PointInTime.OpenAsync(client, request.Schema.Source, chunking.PitKeepAlive, chunking.Flavour, cancellationToken).ConfigureAwait(false);

        try
        {
            JsonNode? afterCursor = null;

            while (true)
            {
                var batch = await FetchChunkAsync(client, request, sourceFields, types, pitId, afterCursor, chunking, cancellationToken)
                    .ConfigureAwait(false);
                pitId = batch.PitId;

                foreach (var row in batch.Rows)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    yield return new ExportRow(row);
                }

                if (batch.Rows.Count < chunking.ChunkSize)
                {
                    yield break;
                }

                afterCursor = batch.SortKeys[^1];
            }
        }
        finally
        {
            await PointInTime.TryCloseAsync(client, pitId, chunking.Flavour).ConfigureAwait(false);
        }
    }

    private static async Task<(IReadOnlyList<IReadOnlyList<object?>> Rows, IReadOnlyList<JsonNode> SortKeys, string PitId)> FetchChunkAsync(
        IOpenSearchLowLevelClient client, SearchQueryRequest request, IReadOnlyList<string> sourceFields, FieldType[] types,
        string pitId, JsonNode? afterCursor, OpenSearchExportOptions chunking, CancellationToken cancellationToken)
    {
        // TL-3: an export never carries the host's query time limit, even though its chunks are range pages.
        var compiled = SearchQueryBuilder.Build(
            request with { Page = new RangePage { StartRow = 0, EndRow = chunking.ChunkSize }, MaxQueryTimeMs = null });
        var body = compiled.ToArtifact();
        body.Remove("from");
        body["pit"] = new JsonObject { ["id"] = pitId, ["keep_alive"] = FormatKeepAlive(chunking.PitKeepAlive) };

        if (afterCursor is not null)
        {
            body["search_after"] = afterCursor.DeepClone();
        }

        var response = await client.SearchAsync<StringResponse>(PostData.String(body.ToJsonString()), null, cancellationToken)
            .ConfigureAwait(false);
        RequireSuccess(response);

        using var document = JsonDocument.Parse(response.Body!);
        var root = document.RootElement;
        var newPitId = root.TryGetProperty("pit_id", out var pitElement) ? pitElement.GetString()! : pitId;
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

        return (rows, sortKeys, newPitId);
    }

    private static string FormatKeepAlive(TimeSpan value) => $"{Math.Max(1, (long)value.TotalSeconds)}s";

    /// <summary>Checks the raw HTTP status rather than <c>StringResponse.Success</c> — see
    /// <c>OpenSearchGridQuery.RequireSuccess</c>'s own remarks for why <c>Success</c> alone is not
    /// trustworthy here (a 404 on <c>_search</c> reads back as <see langword="true"/>). The status travels on the
    /// exception (<see cref="OpenSearchClientCompilationException.HttpStatusCode"/>), exactly as in
    /// <c>OpenSearchGridQuery</c>, so a host can tell an overloaded cluster (503/429) from a bug (#2523).</summary>
    private static void RequireSuccess(StringResponse response)
    {
        if (response.HttpStatusCode is >= 200 and < 300)
        {
            OpenSearchGridQuery.ThrowIfTimedOut(response.Body);
            return;
        }

        throw new OpenSearchClientCompilationException(
            $"The OpenSearch/Elasticsearch call failed (HTTP {response.HttpStatusCode?.ToString() ?? "n/a"}): " +
            Truncate(response.Body ?? response.DebugInformation, 500),
            response.OriginalException ?? new InvalidOperationException("The call did not succeed."),
            response.HttpStatusCode);
    }

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

    /// <summary>SC-4's physical mapping for an ORDINARY <c>_source</c> read — see
    /// <c>OpenSearchGridQuery.ResolveSourceFields</c>'s own remarks (this package's own duplication
    /// convention, mirroring every other small helper shared in shape but not in code between this type
    /// and <c>OpenSearchGridQuery</c>): <c>physical.search.field</c> when a field declares one, the
    /// colId itself otherwise. Review finding: <see cref="FetchChunkAsync"/> used to read <c>_source</c>
    /// by colId directly, so a remapped column's cells all silently came back <see langword="null"/>.</summary>
    private static string[] ResolveSourceFields(IReadOnlyList<string> columns, GridSchema schema)
    {
        var fields = new string[columns.Count];
        for (var i = 0; i < columns.Count; i++)
        {
            fields[i] = schema.Fields[columns[i]].Physical?.Search?.Field ?? columns[i];
        }

        return fields;
    }
}
