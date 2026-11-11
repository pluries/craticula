using System.Globalization;
using System.Text.Json;
using Craticula.Core.Export;
using Craticula.Core.Ir;
using Craticula.Core.Schema;

namespace Craticula.AgGrid;

/// <summary>
/// AR-2.1/AG-1: parses an AG Grid SSRM <c>IServerSideGetRowsRequest</c> (see
/// <c>spec/fixtures/README.md</c>'s wire-shape reference, grounded in the real
/// <c>github/ag-grid</c> TypeScript source) into <see cref="AgGridParsedRequest"/> — the adapter that
/// isolates every other backend/adapter from AG Grid's own wire quirks. Reads the request via
/// <see cref="JsonElement"/> directly rather than a full-document <c>JsonSerializer.Deserialize</c>,
/// since the wire shape itself is not one of <c>ir.schema.json</c>'s own shapes (only the
/// <c>customFilters</c>/<c>groupKeys</c> fragments are) — the two exceptions below reuse
/// <see cref="Craticula.Core.Schema.GridSchemaJson.Options"/> for exactly those two fragments instead
/// of hand-parsing them.
///
/// <para><b>The adapter never performs type coercion (SEM-5's job, downstream).</b> Every scalar
/// filter value (text/number <c>filter</c> — even when the wire value is a JSON <em>number</em> — a
/// date condition's <c>dateFrom</c>, a set condition's <c>values</c> elements) is emitted as a
/// <see cref="StringValue"/> verbatim. <c>groupKeys</c> is the one exception: the wire already
/// carries it pre-typed as <c>{type, value}</c> objects (a real frontend adapter resolves each raw
/// wire string using the group column's declared schema type before building the request this
/// parser consumes), so it deserializes directly as <see cref="TypedValue"/>.</para>
///
/// <para><b>AG-2 date presets ARE resolved here (#1636), not rejected.</b> A <c>date</c> condition
/// whose <c>type</c> is one of AG Grid's 22 presets (<c>today</c>, <c>last7Days</c>, ...) is turned
/// into an absolute half-open <c>inRange</c> against an injected clock + zone by
/// <see cref="DatePresetResolver"/> — see <see cref="AgGridParseOptions"/> for the injection points
/// and that resolver's own doc for the resolution table and its SEM-4 rationale. A compiler therefore
/// never sees an unresolved preset. Everything else in the <c>type</c> slot that isn't in AR-6's
/// closed operator set is still rejected exactly as before.</para>
///
/// <para><b>Explicitly rejected, never silently mis-parsed (AG-1/AG-5's Definition of Done):</b> a
/// native <c>inRange</c> condition (no inclusivity-flag wire path — use <c>customFilters</c>), any
/// unrecognized condition <c>type</c>/<c>filterType</c>/<c>aggFunc</c> (as a side effect of requiring
/// a recognized <c>filterType</c> per entry, this also covers an Advanced Filter model root — no
/// dedicated shape check for it exists, since no ground truth is available to verify one against), a
/// date preset the request gives the adapter no way to type (no <see cref="AgGridParseOptions.Schema"/>,
/// or a field that is neither <c>date</c> nor <c>datetime</c>), an unresolvable
/// <c>requestContext.zone</c>, <c>pivotMode:true</c>/non-empty <c>pivotCols</c> (AG-5, out of scope),
/// and — from <see cref="Parse"/> specifically — the distinct <c>setValuesRequest</c> envelope, which
/// is not a row-fetch request. See <see cref="AgGridRequestParseException"/> for the two reason codes
/// these rejections carry.</para>
///
/// <para><b>EXP-1's export extension IS read here (#1650).</b> <c>exportFormat</c>,
/// <c>exportScope</c> and <c>exportColumns</c> sit beside the ordinary SSRM fields and resolve to
/// <see cref="AgGridParsedRequest.Export"/> — plus three effects on the rest of the parsed request:
/// <c>exportScope: "all"</c> becomes EXP-2's <see cref="NonePage"/> (discarding <c>startRow</c>/
/// <c>endRow</c>), the group/aggregation state is discarded outright (EXP-1's leaf-row carve-out),
/// and the projection is resolved against the schema's <c>exportable</c> flags. See
/// <see cref="ParseExport"/> and <see cref="ApplyExportCarveOut"/>; the compiled shape those
/// decisions render into is <c>spec/semantics.md</c>'s EXP-* addendum.</para>
///
/// <para><b>Two entry points, one per request kind (#1641).</b> <see cref="Parse"/> reads AG Grid's
/// own <c>IServerSideGetRowsRequest</c>; <see cref="ParseSetValues"/> reads BM-3's
/// <c>setValuesRequest</c> envelope, which is Craticula's own shape and shares only the
/// <c>filterModel</c> grammar. Keeping them apart is what lets each one's output record carry exactly
/// the fields its request actually has.</para>
/// </summary>
public static class AgGridRequestParser
{
    /// <summary>
    /// Parses <paramref name="requestJson"/> into an <see cref="AgGridParsedRequest"/>. Runs the same
    /// defense-in-depth structural validation every other public IR entry point in this codebase
    /// runs on its own output (<see cref="FilterNodeValidator"/>, <see cref="SortItemValidator"/>,
    /// <see cref="GroupSpecValidator"/>, <see cref="AggregationValidator"/>, <see cref="PageSpecValidator"/>)
    /// before returning, since this is the very first entry point a request passes through.
    ///
    /// <para><paramref name="options"/> (AG-2, #1636) supplies the clock/zone/week-start/schema a date
    /// preset needs. It is optional: a request carrying no preset never reads any of it, so every
    /// pre-existing call site keeps its exact previous behavior.</para>
    /// </summary>
    public static AgGridParsedRequest Parse(string requestJson, AgGridParseOptions? options = null)
    {
        options ??= AgGridParseOptions.Default;

        using var document = ParseDocument(requestJson);
        var root = document.RootElement;

        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new AgGridRequestParseException("malformed-request", "The AG Grid SSRM request root must be a JSON object.");
        }

        if (root.TryGetProperty("setValuesRequest", out _))
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "'setValuesRequest' is BM-3's distinct set-filter-values envelope, not the row-fetch " +
                "request this method parses — call ParseSetValues instead (see " +
                "spec/fixtures/group-aggregation/README.md for the envelope's shape).");
        }

        if (root.TryGetProperty("pivotMode", out var pivotModeEl) && pivotModeEl.ValueKind == JsonValueKind.True)
        {
            throw new AgGridRequestParseException(
                "malformed-request", "'pivotMode: true' requests are not supported (AG-5 pivot mode is out of scope for this adapter).");
        }

        if (root.TryGetProperty("pivotCols", out var pivotColsEl)
            && pivotColsEl.ValueKind == JsonValueKind.Array
            && pivotColsEl.GetArrayLength() > 0)
        {
            throw new AgGridRequestParseException(
                "malformed-request", "A non-empty 'pivotCols' is not supported (AG-5 pivot mode is out of scope for this adapter).");
        }

        var nativeFilter = ParseFilterModel(root, DateResolutionContext.From(root, options));
        var customFilters = ParseCustomFilters(root);

        var export = ParseExport(root, options);

        // Group state is parsed BEFORE the sort model, not merely beside it: AG Grid addresses a
        // grouped sort through the row-group DISPLAY column's colId, which only the group state can
        // resolve to a real field (see ResolveAutoGroupColumn).
        var (group, aggregations, rowGroupCols) = ParseGroupAndAggregations(root);

        // ...and the sort model is resolved against the group state the WIRE sent, even on an export
        // that is about to discard it (below): AG-6's `ag-Grid-AutoColumn` is a colId in AG Grid's
        // column space, so a grouped grid whose user hits "export" still sends it, and discarding the
        // group state first would leave a sort key naming no schema field at all.
        var sort = ParseSortModel(root, group, rowGroupCols);
        var page = ParsePage(root, export, options);

        // EXP-1(a) is applied BEFORE the validators below, and the order is deliberate: an export's
        // group state and valueCols are discarded, so they are never held to GroupSpecValidator's or
        // AggregationValidator's invariants — including the #1886 output-name uniqueness check.
        // `page-export/011` sends two valueCols on `totalAmount` (sum + avg); its output names
        // differ, so it happens to pass that check unaided and does not depend on this ordering
        // today. What the ordering guards against is a request an export legitimately carries but a
        // grid never would — e.g. two identical (field, func) pairs — which would otherwise be
        // rejected before the carve-out ever got to discard it. Validating first would decide the
        // fate of aggregations the compiled IR does not contain. See ApplyExportCarveOut for what
        // "discarded" covers.
        (group, aggregations) = ApplyExportCarveOut(export, group, aggregations);

        FilterNodeValidator.Validate(nativeFilter);
        FilterNodeValidator.Validate(customFilters);
        SortItemValidator.Validate(sort);
        GroupSpecValidator.Validate(group);
        AggregationValidator.Validate(aggregations);
        PageSpecValidator.ValidateRequestWindow(page);

        return new AgGridParsedRequest
        {
            NativeFilter = nativeFilter,
            CustomFilters = customFilters,
            Sort = sort,
            Group = group,
            Aggregations = aggregations,
            Page = page,
            Export = export
        };
    }

    /// <summary>
    /// BM-3: parses the distinct <c>setValuesRequest</c> envelope — the set filter's "which values may
    /// I offer?" request — into an <see cref="AgGridParsedSetValuesRequest"/>.
    ///
    /// <para>A second entry point rather than a branch inside <see cref="Parse"/>, because the two
    /// documents share nothing but their <c>filterModel</c>: this one carries no
    /// <c>startRow</c>/<c>endRow</c>, no <c>sortModel</c> and no <c>rowGroupCols</c>, and
    /// <see cref="Parse"/> continues to reject it for exactly that reason. Its shape is Craticula's
    /// own (<c>spec/fixtures/group-aggregation/README.md</c>), not AG Grid's — AG Grid Community has
    /// no wire type for set-filter values at all, delegating the whole job to a host-supplied
    /// <c>SetFilterParams.values</c> callback.</para>
    ///
    /// <para>The <c>filterModel</c> is parsed by the identical machinery the row-fetch path uses, so
    /// every AG-1 condition shape, AG-2's date presets (which read
    /// <c>requestContext</c> from the document ROOT, beside the envelope, as they do for a row fetch)
    /// and the boolean set-filter rewrite all behave the same here. The <b>own-field exclusion is
    /// deliberately not applied here</b> — see <see cref="AgGridParsedSetValuesRequest.NativeFilter"/>.</para>
    /// </summary>
    public static AgGridParsedSetValuesRequest ParseSetValues(string requestJson, AgGridParseOptions? options = null)
    {
        options ??= AgGridParseOptions.Default;

        using var document = ParseDocument(requestJson);
        var root = document.RootElement;

        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new AgGridRequestParseException("malformed-request", "The set-filter values request root must be a JSON object.");
        }

        if (!root.TryGetProperty("setValuesRequest", out var envelope) || envelope.ValueKind != JsonValueKind.Object)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "A set-filter values request must carry a 'setValuesRequest' object (BM-3's envelope) — a row-fetch " +
                "IServerSideGetRowsRequest goes through Parse instead.");
        }

        var setValues = ParseSetValuesSpec(envelope);

        // The envelope's own filterModel/customFilters, not the document root's: everything BM-3
        // filters by lives inside the envelope, and a stray root-level filterModel is not part of
        // this shape.
        var nativeFilter = ParseFilterModel(envelope, DateResolutionContext.From(root, options));
        var customFilters = ParseCustomFilters(envelope);

        FilterNodeValidator.Validate(nativeFilter);
        FilterNodeValidator.Validate(customFilters);
        SetValuesSpecValidator.Validate(setValues);

        return new AgGridParsedSetValuesRequest
        {
            SetValues = setValues,
            NativeFilter = nativeFilter,
            CustomFilters = customFilters
        };
    }

    /// <summary>
    /// Reads the envelope's own four properties. <c>colId</c> and <c>filterModel</c> are required (the
    /// latter may be <c>{}</c> or JSON <c>null</c> — "the grid has no other active filters"), while
    /// <c>searchPrefix</c> and <c>limit</c> are optional. A required-but-absent <c>filterModel</c> is
    /// rejected rather than read as <c>{}</c>: the two mean the same thing to a compiler, but
    /// accepting the absence would make the envelope's documented contract untrue and leave a client
    /// unable to tell a dropped property from an empty one.
    /// </summary>
    private static SetValuesSpec ParseSetValuesSpec(JsonElement envelope)
    {
        // Spelled out rather than routed through ReadRequiredString, whose message is built around a
        // column name ("Column 'x': expected a string …") and would here read
        // "Column '<setValuesRequest>'", as though a column were literally called that. This property
        // names the column, so there is no column to name in the error; the three checks below are the
        // house style for this envelope and this one now matches them.
        if (!envelope.TryGetProperty("colId", out var colIdEl) || colIdEl.ValueKind != JsonValueKind.String)
        {
            var found = envelope.TryGetProperty("colId", out var actual) ? actual.ValueKind.ToString() : "no property";
            throw new AgGridRequestParseException(
                "malformed-request",
                $"'setValuesRequest.colId' is required and must be a string (the column whose distinct values are being requested), got {found}.");
        }

        var colId = colIdEl.GetString()!;

        if (!envelope.TryGetProperty("filterModel", out var filterModelEl))
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "'setValuesRequest.filterModel' is required — send {} when the grid has no other active filters.");
        }

        if (filterModelEl.ValueKind is not (JsonValueKind.Object or JsonValueKind.Null))
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"'setValuesRequest.filterModel' must be a JSON object or null, got {filterModelEl.ValueKind}.");
        }

        string? searchPrefix = null;
        if (envelope.TryGetProperty("searchPrefix", out var searchPrefixEl) && searchPrefixEl.ValueKind != JsonValueKind.Null)
        {
            if (searchPrefixEl.ValueKind != JsonValueKind.String)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"'setValuesRequest.searchPrefix' must be a string or null, got {searchPrefixEl.ValueKind}.");
            }

            searchPrefix = searchPrefixEl.GetString();
        }

        return new SetValuesSpec
        {
            ColId = colId,
            SearchPrefix = searchPrefix,
            Limit = ReadOptionalInt(envelope, "limit")
        };
    }

    /// <summary>
    /// Parses the request's raw JSON, converting a malformed-JSON <see cref="JsonException"/> (e.g.
    /// duplicate keys, per <c>spec/fixtures/adversarial/021-duplicate-json-keys-deserializer-fuzz</c>'s
    /// own pinned <c>{"rejectedAt":"requestParsing","reason":"malformed-request"}</c> oracle) into the
    /// same typed <see cref="AgGridRequestParseException"/> every other rejection in this file uses —
    /// a raw <see cref="JsonException"/> escaping here would carry no <see cref="AgGridRequestParseException.Reason"/>
    /// a caller could map to that oracle.
    /// </summary>
    private static JsonDocument ParseDocument(string requestJson)
    {
        try
        {
            return JsonDocument.Parse(requestJson, new JsonDocumentOptions { AllowDuplicateProperties = false });
        }
        catch (JsonException ex)
        {
            throw new AgGridRequestParseException("malformed-request", $"The AG Grid SSRM request is not valid JSON: {ex.Message}", ex);
        }
    }

    // ---- requestContext / date-preset resolution context (AG-2) ---------------------------------

    /// <summary>
    /// Everything <see cref="ParseDateCondition"/> needs to resolve an AG-2 date preset, threaded
    /// through the <c>filterModel</c> dispatch chain as one parameter rather than four. Built once per
    /// request by <see cref="From"/>.
    /// </summary>
    private readonly record struct DateResolutionContext(AgGridParseOptions Options, TimeZoneInfo Zone, DateTimeOffset Now)
    {
        /// <summary>
        /// Resolves the request's effective zone and "now".
        ///
        /// <para><b>Zone</b>: the request's own <c>requestContext.zone</c> (the documented fixture-suite
        /// extension — see <c>spec/fixtures/README.md</c>) wins over
        /// <see cref="AgGridParseOptions.DefaultZone"/>, and an id that does not resolve is a clean
        /// rejection, never a silent fallback (a fallback would quietly answer with a different day's
        /// rows than the grid shows). Resolved EAGERLY, for every request rather than only for requests
        /// carrying a preset: a request that declares a zone the server cannot resolve is malformed
        /// whether or not this particular filter happens to depend on it, and failing at the same point
        /// every time is far easier to diagnose than failing only on some filter shapes.</para>
        ///
        /// <para><b>Now</b>: always <see cref="AgGridParseOptions.Clock"/>, never the wire. The fixture
        /// suite pins a <c>requestContext.now</c> alongside <c>zone</c> so preset cases are reproducible
        /// (see <c>spec/fixtures/date-presets/README.md</c>), but that is an instruction to the
        /// conformance harness about what to set its injected clock to — deliberately NOT a field this
        /// parser reads. Honoring it would let any client dictate what "last 7 days" means, turning a
        /// server-side, auditable clock into a client-supplied parameter for no gain: a real frontend
        /// has no reason to send one.</para>
        /// </summary>
        public static DateResolutionContext From(JsonElement root, AgGridParseOptions options) =>
            new(options, ResolveZone(root, options), options.Clock.GetUtcNow());

        private static TimeZoneInfo ResolveZone(JsonElement root, AgGridParseOptions options)
        {
            if (!root.TryGetProperty("requestContext", out var contextEl) || contextEl.ValueKind == JsonValueKind.Null)
            {
                return options.DefaultZone;
            }

            if (contextEl.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"'requestContext' must be a JSON object or null, got {contextEl.ValueKind}.");
            }

            if (!contextEl.TryGetProperty("zone", out var zoneEl) || zoneEl.ValueKind == JsonValueKind.Null)
            {
                return options.DefaultZone;
            }

            if (zoneEl.ValueKind != JsonValueKind.String)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"'requestContext.zone' must be a string IANA time zone id, got {zoneEl.ValueKind}.");
            }

            var zoneId = zoneEl.GetString()!;

            // Shape- and denylist-check BEFORE resolving, because TimeZoneInfo.FindSystemTimeZoneById
            // accepts considerably more than IANA ids and two classes of accepted-but-wrong input are
            // reachable straight from the wire:
            //
            //   * a Windows id ("Romance Standard Time") resolves on .NET 6+/Linux and keeps its
            //     Windows spelling in TimeZoneInfo.Id, which would then be minted verbatim into
            //     DatetimeValue.Zone and fail FilterNodeValidator's IANA-shape check — turning a
            //     malformed *request* into a structural-invariant failure with no Reason a host could
            //     map onto rejection.schema.json's requestParsing stage (SEC-6 wants one clean,
            //     reason-coded rejection);
            //   * the tzdata artifacts 'localtime', 'Factory' and 'posixrules' resolve AND satisfy the
            //     IANA shape, so the shape check alone cannot catch them. 'localtime' is the worse of
            //     the three: it resolves to whatever zone the SERVER process is configured for, which
            //     would let a client silently make every preset boundary resolve in the server's zone
            //     — exactly the "must NOT assume a fixed server or database default timezone" that
            //     SEM-4 forbids, and undetectable downstream since the id itself looks well-formed.
            if (!FilterNodeValidator.IsIanaZoneIdShape(zoneId) || NonZoneTzdataArtifacts.Contains(zoneId))
            {
                throw new AgGridRequestParseException(
                    "malformed-request",
                    $"'requestContext.zone' must be an IANA time zone id such as 'UTC' or 'Europe/Paris', got '{zoneId}'.");
            }

            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(zoneId);
            }
            catch (Exception ex) when (ex is TimeZoneNotFoundException or InvalidTimeZoneException)
            {
                throw new AgGridRequestParseException(
                    "malformed-request",
                    $"'requestContext.zone' names a time zone id this host cannot resolve: '{zoneId}' " +
                    $"(expected an IANA id such as 'UTC' or 'Europe/Paris').",
                    ex);
            }
        }

        /// <summary>Entries in a tzdata install that resolve and look IANA-shaped but are not zones:
        /// <c>localtime</c> (the server's own configured zone), <c>Factory</c> (the deliberately-unset
        /// placeholder) and <c>posixrules</c> (a legacy POSIX-TZ artifact). Compared ordinally and
        /// case-insensitively, since a case variant would resolve on a case-insensitive filesystem.</summary>
        private static readonly HashSet<string> NonZoneTzdataArtifacts =
            new(["localtime", "Factory", "posixrules"], StringComparer.OrdinalIgnoreCase);
    }

    // ---- filterModel --------------------------------------------------------------------------

    /// <summary>
    /// Builds the native filter tree from <c>filterModel</c> (a map of colId -> per-column entry):
    /// an <see cref="AndNode"/> across columns when more than one column has a filter, unwrapped when
    /// exactly one, <see langword="null"/> when <c>filterModel</c> is absent/JSON-null/empty.
    /// </summary>
    private static FilterNode? ParseFilterModel(JsonElement root, DateResolutionContext context)
    {
        if (!root.TryGetProperty("filterModel", out var filterModelEl) || filterModelEl.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (filterModelEl.ValueKind != JsonValueKind.Object)
        {
            throw new AgGridRequestParseException("malformed-request", "'filterModel' must be a JSON object or null.");
        }

        var columnNodes = new List<FilterNode>();
        foreach (var property in filterModelEl.EnumerateObject())
        {
            var field = property.Name;
            var entry = property.Value;

            if (entry.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"filterModel['{field}'] must be a JSON object, got {entry.ValueKind}.");
            }

            var node = ParseColumnEntry(field, entry, context);
            if (node is not null)
            {
                columnNodes.Add(node);
            }
        }

        return columnNodes.Count == 0 ? null : Combine(columnNodes, isAnd: true, "filterModel");
    }

    /// <summary>
    /// Dispatches one <c>filterModel[colId]</c> entry. <c>multi</c> is handled here (never inside
    /// <see cref="ParseConditionOrCombined"/>, since AG Grid's real <c>filterModels</c> stack is
    /// itself never nested); everything else is a single condition or a combined form, handled by
    /// <see cref="ParseConditionOrCombined"/>. Returns <see langword="null"/> only when a <c>multi</c>
    /// entry's every slot is inactive (see below) — this column then contributes nothing to the
    /// overall filter, rather than throwing for a legitimately "no active filter on this column" state.
    /// </summary>
    private static FilterNode? ParseColumnEntry(string field, JsonElement entry, DateResolutionContext context)
    {
        var filterType = ReadRequiredString(entry, "filterType", field);

        if (filterType != "multi")
        {
            return ParseConditionOrCombined(field, entry, context);
        }

        if (!entry.TryGetProperty("filterModels", out var modelsEl) || modelsEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}': 'multi' filterType requires a 'filterModels' array.");
        }

        // AG Grid's real MultiFilter carries one slot per stacked child filter UI; an inactive child
        // occupies its slot as JSON null (packages/ag-grid-enterprise's multiFilterUtil.ts) — only
        // when EVERY slot is null does the column have no active filter at all. Each active slot is a
        // full child filter model in its own right (it can itself be a combined form), so it's routed
        // through the same ParseConditionOrCombined dispatch as any other filterModel entry — never
        // ParseSingleCondition directly, or a slot using the conditions/condition1 form would 400.
        var nodes = new List<FilterNode>();
        foreach (var model in modelsEl.EnumerateArray())
        {
            if (model.ValueKind == JsonValueKind.Null)
            {
                continue;
            }

            if (model.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"Column '{field}': a 'multi' filterModels entry must be an object or null, got {model.ValueKind}.");
            }

            var node = ParseConditionOrCombined(field, model, context);
            if (node is not null)
            {
                nodes.Add(node);
            }
        }

        return nodes.Count == 0 ? null : Combine(nodes, isAnd: true, field);
    }

    /// <summary>
    /// Dispatches one condition-or-combined-form object that is NOT itself a <c>multi</c> wrapper: a
    /// <c>conditions</c> array or legacy <c>condition1</c>/<c>condition2</c> pair combines via the
    /// entry's own <c>operator</c>, otherwise the entry itself is a single bare condition. Shared by
    /// <see cref="ParseFilterModel"/>'s top-level entries and by each active <c>multi</c> slot in
    /// <see cref="ParseColumnEntry"/>, so both dispatch through the identical combination logic.
    /// </summary>
    private static FilterNode ParseConditionOrCombined(string field, JsonElement entry, DateResolutionContext context)
    {
        if (entry.TryGetProperty("conditions", out var conditionsEl))
        {
            if (conditionsEl.ValueKind != JsonValueKind.Array)
            {
                throw new AgGridRequestParseException("malformed-request", $"Column '{field}': 'conditions' must be an array.");
            }

            var nodes = new List<FilterNode>();
            foreach (var condition in conditionsEl.EnumerateArray())
            {
                if (condition.ValueKind != JsonValueKind.Object)
                {
                    throw new AgGridRequestParseException(
                        "malformed-request", $"Column '{field}': a 'conditions' entry must be an object, got {condition.ValueKind}.");
                }

                nodes.Add(ParseSingleCondition(field, condition, context));
            }

            return CombineByOperator(field, entry, nodes);
        }

        if (entry.TryGetProperty("condition1", out var condition1El))
        {
            if (!entry.TryGetProperty("condition2", out var condition2El))
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"Column '{field}': legacy combined form has 'condition1' but is missing 'condition2'.");
            }

            var nodes = new List<FilterNode>
            {
                ParseSingleCondition(field, condition1El, context),
                ParseSingleCondition(field, condition2El, context)
            };

            return CombineByOperator(field, entry, nodes);
        }

        return ParseSingleCondition(field, entry, context);
    }

    private static FilterNode CombineByOperator(string field, JsonElement entry, IReadOnlyList<FilterNode> nodes)
    {
        var op = ReadRequiredString(entry, "operator", field);
        return op switch
        {
            "AND" => Combine(nodes, isAnd: true, field),
            "OR" => Combine(nodes, isAnd: false, field),
            _ => throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}': combined filter has an unrecognized 'operator' value '{op}' (expected 'AND' or 'OR').")
        };
    }

    /// <summary>Combines <paramref name="nodes"/> per AR-5: 2+ wraps in <see cref="AndNode"/>/
    /// <see cref="OrNode"/>, exactly 1 is returned unwrapped (no spurious single-child composite,
    /// mirroring <see cref="FilterTreeMerge.And"/>'s own convention), 0 is a malformed request.</summary>
    private static FilterNode Combine(IReadOnlyList<FilterNode> nodes, bool isAnd, string field)
    {
        if (nodes.Count == 0)
        {
            throw new AgGridRequestParseException("malformed-request", $"Column '{field}': a combined filter has no conditions.");
        }

        if (nodes.Count == 1)
        {
            return nodes[0];
        }

        return isAnd ? new AndNode { Nodes = nodes } : new OrNode { Nodes = nodes };
    }

    /// <summary>
    /// Dispatches one self-describing SINGLE condition object (a bare <c>filterModel</c> entry, or one
    /// element of a <c>conditions</c> array / a legacy <c>condition1</c>/<c>condition2</c> slot) by its
    /// own <c>filterType</c> — never <c>"multi"</c> here, since AG Grid never nests a <c>multi</c>
    /// inside another <c>multi</c>'s stack. Reached only via <see cref="ParseConditionOrCombined"/>,
    /// which is itself what handles a <c>multi</c> slot that turns out to BE a combined form (a
    /// <c>multi</c> slot is a full child filter model, not guaranteed to be a bare single condition).
    /// </summary>
    private static FilterNode ParseSingleCondition(string field, JsonElement condition, DateResolutionContext context)
    {
        var filterType = ReadRequiredString(condition, "filterType", field);
        return filterType switch
        {
            "text" => ParseTextCondition(field, condition),
            "number" => ParseNumberCondition(field, condition),
            "date" => ParseDateCondition(field, condition, context),
            "set" => ParseSetCondition(field, condition, context),
            _ => throw UnknownOperator(field, filterType, type: null)
        };
    }

    // ---- per-filterType single-condition parsing -----------------------------------------------

    private static ComparisonNode ParseTextCondition(string field, JsonElement condition)
    {
        var type = ReadRequiredString(condition, "type", field);
        var op = type switch
        {
            "equals" => ComparisonOperator.Eq,
            "notEqual" => ComparisonOperator.Neq,
            "contains" => ComparisonOperator.Contains,
            "notContains" => ComparisonOperator.NotContains,
            "startsWith" => ComparisonOperator.StartsWith,
            "endsWith" => ComparisonOperator.EndsWith,
            "blank" => ComparisonOperator.Blank,
            "notBlank" => ComparisonOperator.NotBlank,
            _ => throw UnknownOperator(field, "text", type)
        };

        if (op is ComparisonOperator.Blank or ComparisonOperator.NotBlank)
        {
            return new ComparisonNode { Field = field, Op = op };
        }

        return new ComparisonNode { Field = field, Op = op, Value = ReadStringValue(condition, "filter", field, "text") };
    }

    private static ComparisonNode ParseNumberCondition(string field, JsonElement condition)
    {
        var type = ReadRequiredString(condition, "type", field);
        if (type == "inRange")
        {
            throw InRangeNotSupported(field);
        }

        var op = type switch
        {
            "equals" => ComparisonOperator.Eq,
            "notEqual" => ComparisonOperator.Neq,
            "lessThan" => ComparisonOperator.Lt,
            "lessThanOrEqual" => ComparisonOperator.Lte,
            "greaterThan" => ComparisonOperator.Gt,
            "greaterThanOrEqual" => ComparisonOperator.Gte,
            "blank" => ComparisonOperator.Blank,
            "notBlank" => ComparisonOperator.NotBlank,
            _ => throw UnknownOperator(field, "number", type)
        };

        if (op is ComparisonOperator.Blank or ComparisonOperator.NotBlank)
        {
            return new ComparisonNode { Field = field, Op = op };
        }

        return new ComparisonNode { Field = field, Op = op, Value = ReadNumericStringValue(condition, "filter", field) };
    }

    private static ComparisonNode ParseDateCondition(string field, JsonElement condition, DateResolutionContext context)
    {
        var type = ReadRequiredString(condition, "type", field);
        if (type == "inRange")
        {
            throw InRangeNotSupported(field);
        }

        // AG-2 (#1636): a preset arrives in this very same 'type' slot, carrying no bound of its own
        // (AG Grid's zeroInputTypes) — on the wire that means dateFrom/dateTo are present and
        // explicitly null, NOT absent, whatever PresetDateRangeFilterModel's doc comment claims.
        // Either way nothing here reads them. Checked BEFORE the operator switch so the switch's
        // default arm keeps its original meaning — a genuinely unknown condition type — and still
        // rejects it exactly as it did before presets were supported.
        if (DatePresetResolver.TryResolve(type, context.Now, context.Zone, context.Options.FirstDayOfWeek, out var range))
        {
            return ResolveDatePreset(field, type, range, context);
        }

        var op = type switch
        {
            "equals" => ComparisonOperator.Eq,
            "notEqual" => ComparisonOperator.Neq,
            "lessThan" => ComparisonOperator.Lt,
            "lessThanOrEqual" => ComparisonOperator.Lte,
            "greaterThan" => ComparisonOperator.Gt,
            "greaterThanOrEqual" => ComparisonOperator.Gte,
            "blank" => ComparisonOperator.Blank,
            "notBlank" => ComparisonOperator.NotBlank,
            _ => throw UnknownOperator(field, "date", type)
        };

        if (op is ComparisonOperator.Blank or ComparisonOperator.NotBlank)
        {
            return new ComparisonNode { Field = field, Op = op };
        }

        return new ComparisonNode { Field = field, Op = op, Value = ResolveDateWireValue(field, condition, "dateFrom", context) };
    }

    /// <summary>
    /// Turns AG Grid's wire date string into the <see cref="TypedValue"/> the field's schema-declared
    /// type calls for — SEM-4's "resolving one of those strings into a <c>dateValue</c> or
    /// <c>datetimeValue</c> is exclusively the frontend adapter's job, using BOTH the field's
    /// schema-declared type and the request context's zone."
    ///
    /// <para><b>Why this is needed at all — a real bug #1637's per-major payloads exposed.</b> AG Grid
    /// serialises a date filter's bound with <c>_serialiseDate(date, includeTime = true)</c>, i.e.
    /// <c>"YYYY-MM-DD hh:mm:ss"</c>, in EVERY supported major: v31-v35 call it with no override at all,
    /// and v36 still defaults its new <c>includeTime</c> to <see langword="true"/> (date-only appears
    /// only for a column explicitly configured <c>cellDataType: 'date'</c> or <c>includeTime: false</c>).
    /// Emitting that string verbatim left it uncoercible downstream — <c>TypeCoercionValidator</c>
    /// accepts only a canonical <c>YYYY-MM-DD</c> for a <c>date</c> field and an ISO-8601 instant for a
    /// <c>datetime</c> one — so the single most ordinary thing a user can do, typing a date into a date
    /// column's filter, was rejected end-to-end on every major. The suite missed it because the parser's
    /// own tests stop at <c>Parse</c> (which succeeded, verbatim) and the pre-existing <c>operators/</c>
    /// date fixtures use a date-only string AG Grid does not actually emit by default.</para>
    ///
    /// <para><b>This does not weaken #1635's "the adapter never coerces client values" rule</b> — the
    /// same distinction <see cref="ResolveDatePreset"/> already draws. Coercing would be picking a type
    /// for an arbitrary client string; this is decoding a wire format whose grammar AG Grid publishes
    /// and whose meaning is fixed by the field's declared type. Doing it anywhere else is impossible:
    /// Core cannot know AG Grid's format without AR-2.1's vendor-neutral layer learning a vendor quirk.</para>
    ///
    /// <para>Falls back to the verbatim <see cref="StringValue"/> whenever the type cannot be
    /// established — no <see cref="AgGridParseOptions.Schema"/> supplied, the field absent from it, or
    /// a non-date declared type. That keeps every pre-schema caller behaving exactly as before, and
    /// leaves an unlisted field's fate to <c>FieldAllowlistValidator</c> downstream (where Lenient mode
    /// can still strip it) rather than deciding it here.</para>
    /// </summary>
    private static TypedValue ResolveDateWireValue(
        string field, JsonElement condition, string propertyName, DateResolutionContext context)
    {
        var raw = ReadStringValue(condition, propertyName, field, "date").Value;

        if (context.Options.Schema is not { } schema
            || !schema.Fields.TryGetValue(field, out var fieldConfig)
            || fieldConfig.Type is not (FieldType.Date or FieldType.Datetime))
        {
            return new StringValue { Value = raw };
        }

        return ResolveWireDateText(field, propertyName, raw, fieldConfig.Type, context);
    }

    /// <summary>
    /// The shared resolution of one AG Grid wire date text (<c>YYYY-MM-DD</c> or
    /// <c>YYYY-MM-DD hh:mm:ss</c>) into the typed value a <c>date</c> or <c>datetime</c> field calls for,
    /// with the request's zone. Used by the comparison path (<see cref="ResolveDateWireValue"/>) and by a
    /// set filter's <c>values</c> (<see cref="ParseSetCondition"/>), so the two follow one rule (SEM-4).
    /// Throws <c>malformed-request</c> for any other text and for a non-midnight time on a <c>date</c> field.
    /// </summary>
    private static TypedValue ResolveWireDateText(
        string field, string propertyName, string raw, FieldType fieldType, DateResolutionContext context)
    {
        if (!TryParseAgGridWireDate(raw, out var wallClock, out var hasTime))
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}': '{propertyName}' value '{raw}' is not one of AG Grid's date-filter wire " +
                $"formats ('YYYY-MM-DD' or 'YYYY-MM-DD hh:mm:ss').");
        }

        if (fieldType is FieldType.Datetime)
        {
            DateTimeOffset instant;
            try
            {
                instant = DatePresetResolver.LocalDateTimeToInstant(wallClock, context.Zone);
            }
            catch (ArgumentOutOfRangeException ex)
            {
                // SEC-6: a wall clock at the edge of the calendar can fall outside the representable instant
                // range once the zone's offset is applied — one typed, reason-coded rejection, never an
                // untyped exception out of Parse.
                throw new AgGridRequestParseException(
                    "malformed-request",
                    $"Column '{field}': '{propertyName}' value '{raw}' is outside the range of instants that zone " +
                    $"'{context.Zone.Id}' can resolve.",
                    ex);
            }

            return new DatetimeValue
            {
                Value = instant.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture),
                Zone = context.Zone.Id
            };
        }

        // FieldType.Date. AG Grid's date picker has no time input, so a date column's bound is always
        // serialised at midnight — a NON-midnight time against a date-declared field is genuinely
        // ambiguous (which day did the user mean, in which zone?) and is rejected rather than silently
        // truncated, per SEM-4's "must NOT conflate dateValue and datetimeValue".
        if (hasTime && wallClock.TimeOfDay != TimeSpan.Zero)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}' is declared 'date', but '{propertyName}' carries a non-midnight time " +
                $"('{raw}'). Truncating it would silently discard what the client asked for (SEM-4 forbids " +
                $"conflating a local date with an instant) — declare the field 'datetime' if the time matters.");
        }

        return new DateValue { Value = DateOnly.FromDateTime(wallClock).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) };
    }

    /// <summary>
    /// Parses AG Grid's two date-filter wire forms, exactly as <c>_serialiseDate</c> emits them:
    /// <c>YYYY-MM-DD</c> and <c>YYYY-MM-DD hh:mm:ss</c> (a single space separator, zero-padded parts).
    /// Deliberately exact rather than a lenient <c>DateTime.TryParse</c>: a lenient parse would
    /// accept locale-shaped strings AG Grid never sends and quietly succeed on input this adapter
    /// should be rejecting.
    /// </summary>
    private static bool TryParseAgGridWireDate(string raw, out DateTime wallClock, out bool hasTime)
    {
        if (DateTime.TryParseExact(raw, "yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.None, out wallClock))
        {
            hasTime = true;
            return true;
        }

        hasTime = false;
        return DateTime.TryParseExact(raw, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out wallClock);
    }

    /// <summary>
    /// AG-2: turns an already-resolved preset <paramref name="range"/> into the half-open
    /// <c>inRange</c> node AG Grid's own spec table describes — <c>fromInclusive: true</c>,
    /// <c>toInclusive: false</c>, both flags explicit on the node per SEM-4. These two values are NOT
    /// a guessed AG Grid default (which is precisely what SEM-4 and <c>spec/fixtures/README.md</c>
    /// forbid, and why a NATIVE <c>inRange</c> is still rejected a few lines above): they are read
    /// from AG Grid's published <c>[from, to)</c> preset spec — see
    /// <see cref="DatePresetResolver"/>'s doc comment for the full distinction before considering
    /// "fixing" this into a rejection.
    ///
    /// <para>The bounds' typed representation comes from the field's schema-declared type
    /// (<see cref="DatePresetResolver.ToTypedBounds"/>), so both rejections below are about the
    /// adapter having no honest way to type a value it is GENERATING — not about it declining to
    /// coerce a client value, which remains this parser's rule everywhere else.</para>
    /// </summary>
    private static ComparisonNode ResolveDatePreset(
        string field, string preset, DatePresetRange range, DateResolutionContext context)
    {
        if (context.Options.Schema is not { } schema)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}': the date preset '{preset}' cannot be resolved because no GridSchema was supplied — " +
                $"pass AgGridParseOptions.Schema so the field's declared type (date vs datetime) can select the " +
                $"resolved bounds' typedValue representation (SEM-4).");
        }

        if (!schema.Fields.TryGetValue(field, out var fieldConfig))
        {
            // Deliberately NOT an SC-1 allowlist decision (that stays FieldAllowlistValidator's job,
            // downstream, where a Lenient schema can still strip the node instead of throwing): this
            // is the narrower statement that a preset the adapter must TYPE cannot be typed at all
            // when the field it targets is undeclared. Silently emitting a StringValue instead would
            // reintroduce SEM-4's forbidden local-date-to-instant promotion one layer down.
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}': the date preset '{preset}' targets a field the GridSchema does not declare, " +
                $"so its resolved bounds cannot be typed (SEM-4 requires the field's declared type).");
        }

        try
        {
            var (from, to) = DatePresetResolver.ToTypedBounds(range, fieldConfig.Type, context.Zone);

            return new ComparisonNode
            {
                Field = field,
                Op = ComparisonOperator.InRange,
                From = from,
                To = to,
                FromInclusive = true,
                ToInclusive = false
            };
        }
        catch (ArgumentOutOfRangeException ex)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}': the date preset '{preset}' targets a field declared as " +
                $"'{fieldConfig.Type}' — a preset only resolves against a 'date' or 'datetime' field.",
                ex);
        }
    }

    /// <summary>
    /// Parses a <c>set</c> condition into <see cref="ComparisonOperator.In"/> — with ONE documented
    /// exception, below.
    ///
    /// <para><b>A boolean column's single-value selection becomes AR-6's unary <c>true</c>/<c>false</c>.</b>
    /// AG Grid core has no dedicated boolean filter type (<c>iSetFilter.ts</c>: <c>SetFilterModel</c>
    /// is the only wire shape available for any column type), so <c>spec/fixtures/README.md</c> pins
    /// the modeling convention — a boolean column is filtered as <c>{filterType:"set",
    /// values:["true"]}</c> — and <c>spec/fixtures/operators/README.md</c> pins the adapter's side of
    /// it: "the adapter compiles a boolean column's single-value Set Filter selection to the
    /// dedicated unary <c>true</c>/<c>false</c> operators (see 044/045), never to generic
    /// <c>eq</c>/<c>neq</c>". #1635 left this as a deliberate documented gap for "a later semantic
    /// stage"; #1638 found there is no such stage — a compiler receiving <c>in ["true"]</c> emits
    /// <c>= ANY($1)</c> against a one-element array where <c>operators/044</c>'s and
    /// <c>filter-tree/001</c>'s artifacts pin <c>= $1</c>, and no layer downstream of the adapter has
    /// the AG Grid knowledge to tell a boolean set selection apart from a genuine one-element
    /// <c>in</c>. So the rewrite lands here, where the spec says it belongs.</para>
    ///
    /// <para>Gated on the field being declared <see cref="FieldType.Boolean"/> in
    /// <see cref="AgGridParseOptions.Schema"/>: without that, <c>values:["true"]</c> on a
    /// <em>string</em> column is a perfectly ordinary set membership against the literal text
    /// <c>"true"</c>, and rewriting it would be a silent semantic change. Absent a schema the parser
    /// keeps its previous behavior exactly (the same fallback <see cref="ResolveDateWireValue"/>
    /// uses), so this is strictly additive. The two literals are matched ordinally and exactly, as
    /// <c>spec/fixtures/README.md</c> spells them — accepting <c>"TRUE"</c> too would be a
    /// port-divergence risk for no known input. A two-value <c>["true","false"]</c> selection has no
    /// unary operator that can express it and stays an <c>in</c>.</para>
    /// </summary>
    private static ComparisonNode ParseSetCondition(string field, JsonElement condition, DateResolutionContext context)
    {
        if (!condition.TryGetProperty("values", out var valuesEl) || valuesEl.ValueKind == JsonValueKind.Null)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}': a 'set' filter requires a non-null 'values' array.");
        }

        if (valuesEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}': a 'set' filter's 'values' must be an array, got {valuesEl.ValueKind}.");
        }

        var values = new List<TypedValue>();
        foreach (var element in valuesEl.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.String)
            {
                // AG Grid's real SetFilterModelValue also allows a null element (the "(Blanks)"
                // pseudo-value) — no fixture in this suite exercises it, and the plan does not ask
                // for it, so it is rejected here rather than silently mis-mapped to some guessed
                // representation.
                throw new AgGridRequestParseException(
                    "malformed-request", $"Column '{field}': a 'set' filter's 'values' entry must be a string, got {element.ValueKind}.");
            }

            values.Add(ResolveSetDateValue(field, element.GetString()!, context));
        }

        if (BooleanSelectionOperator(field, values, context) is { } unaryOp)
        {
            return new ComparisonNode { Field = field, Op = unaryOp };
        }

        return new ComparisonNode { Field = field, Op = ComparisonOperator.In, Values = values };
    }

    /// <summary>
    /// A set filter's value on a <c>date</c> or <c>datetime</c> field takes the comparison filter's two wire
    /// spellings (SEM-4 / SEM-5), resolved here with the request's zone, plus — on a <c>datetime</c> field
    /// only — an ISO-8601 instant, which stays the verbatim string (Core coerces it); anything
    /// else is <c>malformed-request</c>. Without a schema, or for any other field type, the verbatim
    /// <see cref="StringValue"/> is kept.
    /// </summary>
    private static TypedValue ResolveSetDateValue(string field, string raw, DateResolutionContext context)
    {
        if (context.Options.Schema is not { } schema
            || !schema.Fields.TryGetValue(field, out var fieldConfig)
            || fieldConfig.Type is not (FieldType.Date or FieldType.Datetime))
        {
            return new StringValue { Value = raw };
        }

        if (fieldConfig.Type is FieldType.Datetime && FilterNodeValidator.IsIsoInstant(raw))
        {
            return new StringValue { Value = raw };
        }

        return ResolveWireDateText(field, "values", raw, fieldConfig.Type, context);
    }

    /// <summary>AR-6's unary operator a boolean column's single-value Set Filter selection maps to,
    /// or <see langword="null"/> when this is an ordinary set membership — see
    /// <see cref="ParseSetCondition"/> for the convention and its gating.</summary>
    private static ComparisonOperator? BooleanSelectionOperator(
        string field, IReadOnlyList<TypedValue> values, DateResolutionContext context)
    {
        if (values.Count != 1
            || context.Options.Schema is not { } schema
            || !schema.Fields.TryGetValue(field, out var fieldConfig)
            || fieldConfig.Type != FieldType.Boolean)
        {
            return null;
        }

        return ((StringValue)values[0]).Value switch
        {
            "true" => ComparisonOperator.True,
            "false" => ComparisonOperator.False,
            _ => null
        };
    }

    private static AgGridRequestParseException InRangeNotSupported(string field) => new(
        "unknown-operator",
        $"Column '{field}': native 'inRange' carries no boundary-inclusivity flags (SEM-4) — use the 'customFilters' extension instead.");

    private static AgGridRequestParseException UnknownOperator(string field, string filterType, string? type) => new(
        "unknown-operator",
        type is null
            ? $"Column '{field}': unrecognized filterType '{filterType}' (AG-1 supports text/number/date/set/multi)."
            : $"Column '{field}': '{filterType}' filterType does not recognize condition type '{type}' (AR-6's closed operator set).");

    // ---- customFilters (OQ-11) -------------------------------------------------------------------

    private static FilterNode? ParseCustomFilters(JsonElement root)
    {
        if (!root.TryGetProperty("customFilters", out var el) || el.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<FilterNode>(el.GetRawText(), Craticula.Core.Schema.GridSchemaJson.Options)
                ?? throw new AgGridRequestParseException("malformed-request", "'customFilters' deserialized to null.");
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException)
        {
            // STJ throws JsonException for an unrecognized 'type' discriminator and
            // NotSupportedException when the discriminator is absent entirely — both mean the same
            // thing here: 'customFilters' doesn't conform to the filterNode wire shape.
            throw new AgGridRequestParseException("malformed-request", $"'customFilters' is not a valid filterNode: {ex.Message}", ex);
        }
    }

    // ---- sortModel ----------------------------------------------------------------------------

    private static IReadOnlyList<SortItem>? ParseSortModel(
        JsonElement root, GroupSpec? group, IReadOnlyList<ColumnVo> rowGroupCols)
    {
        if (!root.TryGetProperty("sortModel", out var sortModelEl) || sortModelEl.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (sortModelEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException("malformed-request", "'sortModel' must be an array.");
        }

        var items = new List<SortItem>();

        // Every field an already-seen row-group display column stands for — see the collapse below.
        var coupledToAutoColumn = new HashSet<string>(StringComparer.Ordinal);

        foreach (var element in sortModelEl.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"A 'sortModel' entry must be an object, got {element.ValueKind}.");
            }

            var colId = ReadRequiredString(element, "colId", "<sortModel>");
            var sortRaw = ReadRequiredString(element, "sort", colId);
            var direction = sortRaw switch
            {
                "asc" => SortDirection.Asc,
                "desc" => SortDirection.Desc,
                _ => throw new AgGridRequestParseException(
                    "malformed-request",
                    $"sortModel entry for colId '{colId}' has an unrecognized 'sort' value '{sortRaw}' (expected 'asc' or 'desc').")
            };

            var isAutoColumn = IsAutoGroupColumnId(colId);
            if (isAutoColumn)
            {
                if (ResolveAutoGroupColumn(colId, group, rowGroupCols) is not { } resolution)
                {
                    // Every group column is consumed: this is the drill-down leaf, whose rows all
                    // share the whole group path, so the display column shows nothing to order by
                    // and the key would be a constant. Dropped rather than mapped to some level's
                    // column, which would be an ordering the user did not ask for. This is the ONLY
                    // silent drop on this path — see ResolveAutoGroupColumn for why the two other
                    // ways a display column can fail to name a level are carried through instead.
                    continue;
                }

                foreach (var coupled in resolution.CoupledFields)
                {
                    coupledToAutoColumn.Add(coupled);
                }

                colId = resolution.Field;
            }
            else if (coupledToAutoColumn.Contains(colId))
            {
                // AG Grid's sort COUPLING (gridOptionsUtils._isColumnsSortingCoupledToGroup, on by
                // default) sets the sort on the display column AND on every source column
                // showRowGroupCols.getSourceColumnsForGroupColumn returns for it, and
                // sortService.getIndexedSortMap gives them all the display column's index — so one
                // user click on the group header emits the display column followed by the WHOLE
                // coupled set (for the default single auto column, that is every row-group column:
                // its colDef carries `showRowGroup: true`, which that service answers with
                // `rowGroupColsSvc.columns.slice(0)`). They are one logical key, already represented
                // by the entry the display column resolved to, so the rest are dropped. Deliberately
                // narrow: only entries the resolution itself accounts for, and only AFTER the
                // display column that named them — a key the client sent on its own is left alone.
                continue;
            }

            // A repeat of the resolved key itself: keep the FIRST occurrence, so the user's own key
            // precedence is preserved exactly and the unreachable later tiebreak is dropped.
            if (isAutoColumn && items.Any(item => string.Equals(item.Field, colId, StringComparison.Ordinal)))
            {
                continue;
            }

            // SEM-3: nullsPosition is always explicit in the IR, never left to a backend's default —
            // AG Grid's own SortModelItem carries no null-placement signal at all, so the adapter
            // fills it itself via #1634's shared SemanticsResolver rule (never re-derived ad hoc here).
            items.Add(new SortItem
            {
                Field = colId,
                Direction = direction,
                NullsPosition = Craticula.Core.Schema.SemanticsResolver.DefaultNullsPosition(direction)
            });
        }

        return items.Count == 0 ? null : items;
    }

    /// <summary>
    /// AG Grid's row-group display column id — <c>columnUtils.ts</c>'s
    /// <c>GROUP_AUTO_COLUMN_ID = 'ag-Grid-AutoColumn'</c>, matched by PREFIX exactly as AG Grid's own
    /// <c>isColumnGroupAutoCol</c> does, because <c>groupDisplayType: 'multipleColumns'</c> mints one
    /// column per row-group column and suffixes each with that column's id
    /// (<c>autoColService.createOneAutoCol</c>: <c>`${GROUP_AUTO_COLUMN_ID}-${rowGroupCol.getId()}`</c>).
    /// </summary>
    private const string GroupAutoColumnId = "ag-Grid-AutoColumn";

    private static bool IsAutoGroupColumnId(string colId) =>
        colId.StartsWith(GroupAutoColumnId, StringComparison.Ordinal);

    /// <summary>What a row-group display column's colId stands for.</summary>
    /// <param name="Field">The schema field the display column resolves to — or, when it resolves to
    /// nothing at all, the colId itself, unchanged (see <see cref="ResolveAutoGroupColumn"/>).</param>
    /// <param name="CoupledFields">Every row-group field AG Grid's sort coupling emits <em>beside</em>
    /// this display column, which the sort model must therefore collapse back into it. Empty when the
    /// colId resolved to nothing, since nothing is coupled to a column AG Grid never minted.</param>
    private readonly record struct AutoColumnResolution(string Field, IReadOnlyList<string> CoupledFields);

    /// <summary>
    /// AG-6/GRP-4: resolves a row-group display column's colId to the schema field it stands for, plus
    /// the source fields AG Grid couples to it. <see langword="null"/> means <b>drop the key</b>, and
    /// exactly one condition produces it: the drill-down leaf.
    ///
    /// <para><b>Why this has to exist at all.</b> When a user sorts the group column of an SSRM grid —
    /// the single most common interaction a grouped grid has — <c>sortService.getSortModel</c> writes
    /// <c>column.getId()</c>, and for the auto column that id is <c>ag-Grid-AutoColumn</c>, matching
    /// no schema field. It is a colId in AG GRID's column space, not in the host's, so translating it
    /// is the adapter's job by definition: nothing downstream knows AG Grid mints display columns.</para>
    ///
    /// <list type="bullet">
    /// <item><description><b><c>ag-Grid-AutoColumn</c></b> (the single display column, AG Grid's
    /// default) shows the whole group path, so what the request can actually order by is the level it
    /// is itself producing — <c>groupCols[groupKeys.length]</c>, exactly GRP-1's dispatch. Its
    /// coupled set is the <b>whole</b> <c>rowGroupCols</c> field list, not just that level's:
    /// <c>autoColService.createBaseColDef</c> gives the single auto column
    /// <c>showRowGroup: rowGroupCol?.getColId() ?? true</c>, i.e. <c>true</c>, and
    /// <c>showRowGroupColsService.getSourceColumnsForGroupColumn</c> answers <c>true</c> with
    /// <c>rowGroupColsSvc.columns.slice(0)</c> — every row-group column. AG Grid treats them as one
    /// logical key and sorts them together.</description></item>
    /// <item><description><b><c>ag-Grid-AutoColumn-&lt;id&gt;</c></b> (<c>multipleColumns</c>) names
    /// its source column explicitly, so it resolves to THAT column, nothing is inferred, and its
    /// coupled set is that one column — <c>showRowGroup</c> is the column's id there, the string arm
    /// of the same service method. The suffix is the <c>ColumnVO.id</c>, which is why it is looked up
    /// against the <c>rowGroupCols</c> entries' ids rather than their fields — the two differ whenever
    /// a host gives a grouped column its own id. If it names a level this request is not producing,
    /// the resolved field simply is not a legal sort target and GRP-4 rejects it downstream, naming
    /// the reason — which is correct: a level bucketed by <c>region</c> genuinely cannot be ordered by
    /// <c>segment</c>.</description></item>
    /// </list>
    ///
    /// <para><b>Two ways a display column can name no level at all, and neither is silent.</b> A
    /// suffix matching no <c>rowGroupCols</c> entry, and an auto-column colId on a request carrying no
    /// group state whatsoever, both carry the colId through <b>unchanged</b>, so it fails downstream
    /// as the unknown colId it is rather than vanishing. Dropping either would delete a sort key the
    /// grid's own header still shows, ordering the response differently from the UI with no rejection
    /// and no log — and the auto-column prefix would be the only colId in this adapter with such a
    /// path, since any other bogus colId reaches a compiler and is refused there. The refusal comes
    /// from the compiler (<c>SqlQueryBuilder</c> resolves every sort field against
    /// <see cref="GridSchema.Fields"/>), NOT from <c>FieldAllowlistValidator</c>: sort colIds have no
    /// allowlist stage yet — see <see cref="Craticula.Core.Schema.SemanticsResolver.AppendStableKeyTiebreaker(IReadOnlyList{SortItem}?, string)"/>'s
    /// own note on the orchestrator that does not exist.</para>
    /// </summary>
    private static AutoColumnResolution? ResolveAutoGroupColumn(
        string colId, GroupSpec? group, IReadOnlyList<ColumnVo> rowGroupCols)
    {
        if (colId.Length > GroupAutoColumnId.Length)
        {
            // The '-' separator plus the source column's ColumnVO.id.
            var sourceId = colId[(GroupAutoColumnId.Length + 1)..];

            foreach (var vo in rowGroupCols)
            {
                if (string.Equals(vo.Id, sourceId, StringComparison.Ordinal))
                {
                    return new AutoColumnResolution(vo.Field, [vo.Field]);
                }
            }

            return new AutoColumnResolution(colId, []);
        }

        if (group is null)
        {
            return new AutoColumnResolution(colId, []);
        }

        var level = group.GroupKeys.Count;
        if (level >= group.GroupCols.Count)
        {
            return null;
        }

        return new AutoColumnResolution(group.GroupCols[level], rowGroupCols.Select(vo => vo.Field).ToList());
    }

    // ---- rowGroupCols / groupKeys / valueCols --------------------------------------------------

    private readonly record struct ColumnVo(string Id, string Field, string? AggFunc);

    private static (GroupSpec? Group, IReadOnlyList<Aggregation>? Aggregations, IReadOnlyList<ColumnVo> RowGroupCols)
        ParseGroupAndAggregations(JsonElement root)
    {
        var groupCols = ReadColumnVoList(root, "rowGroupCols");
        var valueCols = ReadColumnVoList(root, "valueCols");
        var groupKeys = ParseGroupKeys(root);

        GroupSpec? group = null;
        if (groupCols.Count > 0)
        {
            group = new GroupSpec
            {
                GroupCols = groupCols.Select(vo => vo.Field).ToList(),
                GroupKeys = groupKeys
            };
        }
        else if (groupKeys.Count > 0)
        {
            // A drill-down key with no group columns to drill into is meaningless — and silently
            // dropping it would WIDEN the query (BM-2: a group key restricts the result set to that
            // bucket), the opposite of AG-1/AG-5's "explicitly rejected, never silently mis-parsed".
            throw new AgGridRequestParseException(
                "malformed-request", "'groupKeys' is non-empty but 'rowGroupCols' is empty — a drill-down key requires a group column to drill into.");
        }

        IReadOnlyList<Aggregation>? aggregations = null;
        if (valueCols.Count > 0)
        {
            aggregations = valueCols.Select(vo =>
            {
                if (vo.AggFunc is null)
                {
                    throw new AgGridRequestParseException(
                        "malformed-request", $"valueCols entry for field '{vo.Field}' is missing 'aggFunc'.");
                }

                return new Aggregation
                {
                    Field = vo.Field,
                    Func = ParseAggFunc(vo.AggFunc, vo.Field),
                    Alias = vo.Id != vo.Field ? vo.Id : null
                };
            }).ToList();
        }

        return (group, aggregations, groupCols);
    }

    /// <summary>Reads a <c>ColumnVO[]</c> property (<c>rowGroupCols</c>/<c>valueCols</c>), using each
    /// entry's <c>field</c> (never <c>id</c>/<c>displayName</c>) per the plan. Absent/JSON-null is an
    /// empty list, matching how AG Grid always sends <c>[]</c> rather than omitting these arrays.</summary>
    private static IReadOnlyList<ColumnVo> ReadColumnVoList(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var arrayEl) || arrayEl.ValueKind == JsonValueKind.Null)
        {
            return [];
        }

        if (arrayEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException("malformed-request", $"'{propertyName}' must be an array.");
        }

        var result = new List<ColumnVo>();
        foreach (var element in arrayEl.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"A '{propertyName}' entry must be an object, got {element.ValueKind}.");
            }

            var id = ReadRequiredString(element, "id", propertyName);

            // AG Grid's own ColumnVO declares 'field' optional (a valueGetter-backed column has no
            // plain field path) — 'id' is always present and is what GridSchema's allowlist keys on
            // anyway, so it's the correct fallback rather than rejecting a legitimate request.
            var field = element.TryGetProperty("field", out var fieldEl) && fieldEl.ValueKind == JsonValueKind.String
                ? fieldEl.GetString()!
                : id;

            var aggFunc = element.TryGetProperty("aggFunc", out var aggFuncEl) && aggFuncEl.ValueKind == JsonValueKind.String
                ? aggFuncEl.GetString()
                : null;

            result.Add(new ColumnVo(id, field, aggFunc));
        }

        return result;
    }

    /// <summary>
    /// Deserializes <c>groupKeys</c> directly as <see cref="TypedValue"/> — the wire already carries
    /// each key pre-typed as a <c>{type, value}</c> object (confirmed against the real
    /// <c>spec/fixtures/group-aggregation/*/agGridRequest.json</c> fixtures, not just the fixtures
    /// README's simplified <c>string[]</c> annotation), so no hand-written resolution is needed here,
    /// the same "no hand-written parsing code" rationale <see cref="TypedValue"/>'s own doc gives.
    /// </summary>
    private static IReadOnlyList<TypedValue> ParseGroupKeys(JsonElement root)
    {
        if (!root.TryGetProperty("groupKeys", out var groupKeysEl) || groupKeysEl.ValueKind == JsonValueKind.Null)
        {
            return [];
        }

        if (groupKeysEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException("malformed-request", "'groupKeys' must be an array.");
        }

        var keys = new List<TypedValue>();
        foreach (var element in groupKeysEl.EnumerateArray())
        {
            try
            {
                keys.Add(JsonSerializer.Deserialize<TypedValue>(element.GetRawText(), Craticula.Core.Schema.GridSchemaJson.Options)
                    ?? throw new AgGridRequestParseException("malformed-request", "A 'groupKeys' entry deserialized to null."));
            }
            catch (Exception ex) when (ex is JsonException or NotSupportedException)
            {
                throw new AgGridRequestParseException("malformed-request", $"A 'groupKeys' entry is not a valid typedValue: {ex.Message}", ex);
            }
        }

        return keys;
    }

    private static AggregationFunc ParseAggFunc(string raw, string field) => raw switch
    {
        "sum" => AggregationFunc.Sum,
        "min" => AggregationFunc.Min,
        "max" => AggregationFunc.Max,
        "avg" => AggregationFunc.Avg,
        "count" => AggregationFunc.Count,
        _ => throw new AgGridRequestParseException(
            "unknown-operator",
            $"valueCols entry for field '{field}' has an unrecognized aggFunc '{raw}' (AR-8's closed v1 function set is sum/min/max/avg/count).")
    };

    // ---- exportFormat / exportScope / exportColumns (EXP-1) --------------------------------------

    /// <summary>
    /// EXP-1's wire-contract extension: <c>exportFormat: "csv" | "tsv"</c>,
    /// <c>exportScope: "all" | "page"</c> (default <c>"all"</c>) and an optional ordered
    /// <c>exportColumns: [{ colId, header? }]</c>, sitting BESIDE the ordinary SSRM fields rather
    /// than replacing them — <c>filterModel</c> and <c>sortModel</c> are always honored, which is why
    /// nothing else in this parser changes shape for an export.
    ///
    /// <para><b><c>exportFormat</c> is what marks a request as an export</b>, so <c>exportScope</c>
    /// or <c>exportColumns</c> arriving without it is rejected rather than read as an ordinary row
    /// fetch with two stray properties: EXP-1 declares the format non-optional, and silently ignoring
    /// a scope would return one page where the client asked for the whole result set — the widening/
    /// narrowing class of silent mis-parse AG-1/AG-5 exist to rule out.</para>
    ///
    /// <para><b>The projection is RESOLVED here, not echoed</b> (EXP-1(b)). An explicit
    /// <c>exportColumns</c> is taken in request order; an absent one expands to every field the schema
    /// declares <see cref="FieldConfig.Exportable"/>, in GRP-3's declaration order
    /// (<see cref="GridSchema.FieldOrder"/>, read from the schema document — never a
    /// <see cref="Dictionary{TKey,TValue}"/>'s unspecified enumeration order). Doing it once, here,
    /// is what stops the SQL and Mongo compilers from being able to disagree about the default. Each
    /// resolved column carries the two things a compiler never sees and a writer cannot re-derive: its
    /// header (EXP-1(b)) and, since #1653, its <see cref="FieldConfig.Format"/> (EXP-5's per-field date
    /// pattern and decimal separator).</para>
    ///
    /// <para><b>Why this reads the schema although "the adapter is not an allowlist gate" (#1635).</b>
    /// Exactly <see cref="ResolveDatePreset"/>'s distinction: SC-1 allowlisting stays
    /// <see cref="FieldAllowlistValidator"/>'s job, and this is the narrower statement that a column
    /// the adapter must PROJECT cannot be resolved when the schema does not declare it — and that
    /// <see cref="FieldConfig.Exportable"/>, a flag whose only consumer is this contract, has to be
    /// honored by whoever reads that contract. Both refusals are hard in EVERY
    /// <see cref="GridSchemaMode"/>: Lenient's contract is that an unknown filter CONDITION vanishes
    /// and the result merely widens, while a dropped export column hands the user a file missing a
    /// column they explicitly asked for — the same reasoning that keeps #1640's group columns and
    /// aggregations hard failures in Lenient mode.</para>
    /// </summary>
    private static ExportSpec? ParseExport(JsonElement root, AgGridParseOptions options)
    {
        var format = ReadOptionalString(root, "exportFormat");
        var scope = ReadOptionalString(root, "exportScope");
        var hasColumns = root.TryGetProperty("exportColumns", out var columnsEl)
            && columnsEl.ValueKind != JsonValueKind.Null;

        if (format is null)
        {
            if (scope is null && !hasColumns)
            {
                return null;
            }

            throw new AgGridRequestParseException(
                "malformed-request",
                "'exportScope'/'exportColumns' are part of EXP-1's export extension and require an " +
                "'exportFormat' (\"csv\" or \"tsv\") on the same request — a row fetch carries none of the three.");
        }

        if (options.Schema is not { } schema)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "An export request cannot be resolved because no GridSchema was supplied — pass " +
                "AgGridParseOptions.Schema so EXP-1(b)'s projection (the declared 'exportable' fields, or the " +
                "'exportColumns' the request names) can be resolved.");
        }

        return new ExportSpec
        {
            Format = format switch
            {
                "csv" => ExportFormat.Csv,
                "tsv" => ExportFormat.Tsv,
                _ => throw new AgGridRequestParseException(
                    "malformed-request", $"'exportFormat' must be \"csv\" or \"tsv\", got '{format}'.")
            },

            // EXP-1 pins the default explicitly: an export with no stated scope streams the whole
            // filtered+sorted result, it does not fall back to whatever page the grid last fetched.
            Scope = (scope ?? "all") switch
            {
                "all" => ExportScope.All,
                "page" => ExportScope.Page,
                _ => throw new AgGridRequestParseException(
                    "malformed-request", $"'exportScope' must be \"all\" or \"page\", got '{scope}'.")
            },

            Columns = hasColumns
                ? ParseExportColumns(columnsEl, schema)
                : DefaultExportColumns(schema)
        };
    }

    /// <summary>The wire's own ordered <c>exportColumns</c>, each resolved against the schema.</summary>
    private static IReadOnlyList<ExportColumn> ParseExportColumns(JsonElement columnsEl, GridSchema schema)
    {
        if (columnsEl.ValueKind != JsonValueKind.Array)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"'exportColumns' must be an array or null, got {columnsEl.ValueKind}.");
        }

        var columns = new List<ExportColumn>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        foreach (var element in columnsEl.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object)
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"An 'exportColumns' entry must be an object, got {element.ValueKind}.");
            }

            var colId = ReadRequiredString(element, "colId", "<exportColumns>");

            if (!schema.Fields.TryGetValue(colId, out var config))
            {
                throw new AgGridRequestParseException(
                    "malformed-request",
                    $"'exportColumns' names '{colId}', which the GridSchema does not declare — there is no " +
                    "physical column to project it from.");
            }

            if (!config.Exportable)
            {
                throw new AgGridRequestParseException(
                    "malformed-request",
                    $"'exportColumns' names '{colId}', which the GridSchema declares 'exportable: false'.");
            }

            // A repeated colId is refused rather than deduplicated: on SQL it would emit the same
            // output name twice, and on MongoDB a $project is a JSON object, so the second entry
            // simply overwrites the first (MDB-10's last-wins collision) and the client would get
            // one column back where it asked for two, with nothing saying so.
            if (!seen.Add(colId))
            {
                throw new AgGridRequestParseException(
                    "malformed-request", $"'exportColumns' names '{colId}' more than once.");
            }

            var header = element.TryGetProperty("header", out var headerEl) && headerEl.ValueKind == JsonValueKind.String
                ? headerEl.GetString()!
                : config.Label ?? colId;

            // The format is the field's own (EXP-5 puts the override in schema config, so unlike the
            // header there is nothing on the wire to merge with it) and travels on the column because
            // the writer is handed nothing else per field.
            columns.Add(new ExportColumn(colId, header, config.Format));
        }

        if (columns.Count == 0)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "'exportColumns' is present but empty — an export of no columns has no compiled form. Omit the " +
                "property entirely to get EXP-1(b)'s default projection.");
        }

        return columns;
    }

    /// <summary>EXP-1's default projection: "all schema fields flagged exportable are emitted in
    /// schema order, headers from schema labels" — plus EXP-5's per-field format, resolved on the same
    /// pass and from the same <see cref="FieldConfig"/>, so the two projections cannot disagree about
    /// which columns carry an override.</summary>
    private static IReadOnlyList<ExportColumn> DefaultExportColumns(GridSchema schema)
    {
        var columns = schema.FieldOrder
            .Where(field => schema.Fields[field].Exportable)
            .Select(field => new ExportColumn(field, schema.Fields[field].Label ?? field, schema.Fields[field].Format))
            .ToList();

        if (columns.Count == 0)
        {
            throw new AgGridRequestParseException(
                "malformed-request",
                "The GridSchema declares no exportable field, so an export with no 'exportColumns' has nothing " +
                "to project.");
        }

        return columns;
    }

    /// <summary>
    /// EXP-1's group-export carve-out: an export emits <b>leaf rows</b> under the current filter and
    /// sort, so <c>rowGroupCols</c>, <c>valueCols</c> and <c>groupKeys</c> are all discarded outright —
    /// the compiled IR carries no <c>group</c> and no <c>aggregations</c>, and the grouping dispatch
    /// every compiler runs (GRP-1) is therefore never entered. <c>page-export/010</c>, <c>/011</c> and
    /// <c>/024</c> send a fully populated single-level, two-level and drilled-into group state and pin
    /// flat, ungrouped artifacts on all three backends. Group-structured and pivot exports are
    /// explicitly out of scope for v1.
    ///
    /// <para>Applied to <b>any</b> export, not only an <see cref="ExportScope.All"/> one: the output
    /// is a flat delimited row stream either way, and the scope decides only how many rows go into
    /// it.</para>
    ///
    /// <para><b><c>groupKeys</c> is discarded with the other two, not refused.</b> All three members
    /// describe the same thing — the group state of the view being exported — and EXP-1(a) discards
    /// that state entirely. Dropping a drill-down key does export more rows than the grid is
    /// showing, but so does dropping <c>rowGroupCols</c>, which is mandated; the distinction does not
    /// survive that. The deciding case is the obvious host integration: an export request built by
    /// copying the grid's last <c>getRows</c> payload and adding <c>exportFormat</c> would otherwise
    /// hard-fail whenever a user had expanded a group node. <c>page-export/024</c> pins the discard
    /// end to end.</para>
    ///
    /// <para>A <c>groupKeys</c> with an EMPTY <c>rowGroupCols</c> is still rejected on an export, in
    /// <see cref="ParseGroupAndAggregations"/> and before this method runs. That is not the same rule
    /// wearing a different answer: there the request is structurally malformed — AG Grid cannot
    /// produce it, since a drill-down path is a prefix of the group columns — whereas here the
    /// request is well formed and its group state is deliberately dropped.</para>
    /// </summary>
    private static (GroupSpec? Group, IReadOnlyList<Aggregation>? Aggregations) ApplyExportCarveOut(
        ExportSpec? export, GroupSpec? group, IReadOnlyList<Aggregation>? aggregations)
        => export is null ? (group, aggregations) : (null, null);

    // ---- startRow / endRow ---------------------------------------------------------------------

    /// <summary>
    /// AG-3/EXP-2. <c>startRow</c>/<c>endRow</c> resolve to a <see cref="RangePage"/> exactly as
    /// before — <b>except</b> under EXP-1's <c>exportScope: "all"</c>, which is EXP-2's
    /// <c>page: { mode: "none" }</c> and discards whatever those two numbers said. That discard is
    /// pinned, not inferred: <c>page-export/006</c> sends <c>startRow: 200, endRow: 250</c> beside
    /// <c>exportScope: "all"</c> and its artifacts carry no row-range clause on any backend, while
    /// <c>/007</c> sends the identical pair under <c>exportScope: "page"</c> and keeps it.
    ///
    /// <para>The pair is still shape-checked before being overridden, so a half-supplied
    /// <c>startRow</c> is a malformed request whether or not this particular scope would have used
    /// it — the same reason <see cref="DateResolutionContext.From"/> resolves the zone eagerly.</para>
    /// </summary>
    private static PageSpec ParsePage(JsonElement root, ExportSpec? export, AgGridParseOptions options)
    {
        var startRow = ReadOptionalInt(root, "startRow");
        var endRow = ReadOptionalInt(root, "endRow");
        var ignorePageLimit = ReadOptionalBool(root, "ignorePageLimit");

        if (ignorePageLimit == true && !options.AllowUnboundedRows)
        {
            throw new AgGridRequestParseException(
                "unbounded-not-allowed",
                "'ignorePageLimit' asks for every row, and this host has not allowed that (AgGridParseOptions.AllowUnboundedRows).");
        }

        var page = (startRow, endRow) switch
        {
            ({ } s, { } e) => (PageSpec)new RangePage { StartRow = s, EndRow = e },
            (null, null) => ignorePageLimit == true
                ? new NonePage()
                : new RangePage { StartRow = 0, EndRow = options.DefaultPageSize },
            _ => throw new AgGridRequestParseException(
                "malformed-request",
                $"'startRow'/'endRow' must both be present or both be null (got startRow={Render(startRow)}, endRow={Render(endRow)}).")
        };

        return export is { Scope: ExportScope.All } ? new NonePage() : page;
    }

    private static bool? ReadOptionalBool(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var el) || el.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        return el.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => throw new AgGridRequestParseException(
                "malformed-request", $"'{propertyName}' must be a boolean or null, got {el.ValueKind}.")
        };
    }

    private static string Render(int? value) => value?.ToString() ?? "null";

    private static int? ReadOptionalInt(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var el) || el.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (el.ValueKind != JsonValueKind.Number || !el.TryGetInt32(out var value))
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"'{propertyName}' must be a 32-bit integer or null, got '{el.GetRawText()}'.");
        }

        return value;
    }

    // ---- shared JsonElement helpers -------------------------------------------------------------

    /// <summary>Reads an optional top-level string property. Absent and explicit JSON <c>null</c> are
    /// the same thing (AG Grid nulls out rather than omits — <c>startRow: null</c> is the same wire
    /// habit); any other value kind is a malformed request rather than a silently ignored one.</summary>
    private static string? ReadOptionalString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var el) || el.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (el.ValueKind != JsonValueKind.String)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"'{propertyName}' must be a string or null, got {el.ValueKind}.");
        }

        return el.GetString()!;
    }

    private static string ReadRequiredString(JsonElement obj, string propertyName, string field)
    {
        if (!obj.TryGetProperty(propertyName, out var prop) || prop.ValueKind != JsonValueKind.String)
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}': expected a string '{propertyName}' property.");
        }

        return prop.GetString()!;
    }

    private static StringValue ReadStringValue(JsonElement condition, string propertyName, string field, string filterTypeLabel)
    {
        if (!condition.TryGetProperty(propertyName, out var prop) || prop.ValueKind != JsonValueKind.String)
        {
            var found = condition.TryGetProperty(propertyName, out var actual) ? actual.ValueKind.ToString() : "no property";
            throw new AgGridRequestParseException(
                "malformed-request",
                $"Column '{field}' ('{filterTypeLabel}' filter): expected a string '{propertyName}' value, got {found}.");
        }

        return new StringValue { Value = prop.GetString()! };
    }

    /// <summary>
    /// Reads a <c>number</c> filter's scalar property and carries it forward as a
    /// <see cref="StringValue"/>. Accepts BOTH a JSON number (the well-formed wire shape — carried
    /// via the literal's own raw text, never parsed through a floating type first, so it can't
    /// introduce the float round-tripping loss <see cref="Craticula.Core.Ir.DecimalValue"/>'s own doc
    /// warns against) AND a JSON string: two real conformance fixtures
    /// (<c>spec/fixtures/adversarial/012-non-numeric-string-int64-field</c>,
    /// <c>015-malformed-decimal-string-decimal-field</c>) deliberately send an adversarial STRING
    /// value against a <c>number</c> filterType, expecting rejection at the <c>typeCoercion</c> stage
    /// (<see cref="Craticula.Core.Schema.TypeCoercionValidator"/>, SEM-5) — not here at
    /// <c>requestParsing</c>. Rejecting a string here would 400 at the wrong stage for a request the
    /// conformance suite pins as valid-shaped-but-uncoercible. AR-7 coercion into the field's actual
    /// declared type happens later, downstream — never here, for either representation.
    /// </summary>
    private static StringValue ReadNumericStringValue(JsonElement condition, string propertyName, string field)
    {
        if (!condition.TryGetProperty(propertyName, out var prop))
        {
            throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}' ('number' filter): expected a numeric or string '{propertyName}' value, got no property.");
        }

        return prop.ValueKind switch
        {
            JsonValueKind.Number => new StringValue { Value = prop.GetRawText() },
            JsonValueKind.String => new StringValue { Value = prop.GetString()! },
            _ => throw new AgGridRequestParseException(
                "malformed-request", $"Column '{field}' ('number' filter): expected a numeric or string '{propertyName}' value, got {prop.ValueKind}.")
        };
    }
}
