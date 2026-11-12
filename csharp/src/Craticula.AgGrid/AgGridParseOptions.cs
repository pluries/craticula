using Craticula.Core.Schema;

namespace Craticula.AgGrid;

/// <summary>
/// AG-2: the ambient context <see cref="AgGridRequestParser.Parse(string, AgGridParseOptions?)"/>
/// needs to resolve an AG Grid <em>date preset</em> (<c>today</c>, <c>last7Days</c>, ...) into an
/// absolute range — a clock, a zone, a week-start policy, and the schema whose declared field type
/// decides whether the resolved bounds are <c>dateValue</c>s or <c>datetimeValue</c>s.
///
/// <para>Passed as an OPTIONAL parameter so every pre-existing call site and fixture test keeps
/// working unchanged: a request carrying no date preset never touches any member of this class, and
/// the defaults below are the ones a preset-free request would have used anyway. A request that DOES
/// carry a preset but was parsed without a <see cref="Schema"/> is rejected cleanly rather than
/// silently resolved against a guessed field type — see
/// <see cref="DatePresetResolver"/>'s own doc for why the schema is load-bearing here.</para>
///
/// <para><b>Zero added NuGet packages (AR-3).</b> <see cref="System.TimeProvider"/>,
/// <see cref="System.TimeZoneInfo"/> and <see cref="System.DayOfWeek"/> are all BCL types (net8+),
/// so injecting a clock needs no test/abstraction package — a test substitutes a
/// <see cref="TimeProvider"/> whose <see cref="TimeProvider.GetUtcNow"/> returns a pinned instant.</para>
/// </summary>
public sealed record AgGridParseOptions
{
    /// <summary>
    /// The injected clock a preset resolves "now" against. Defaults to
    /// <see cref="TimeProvider.System"/>. Only <see cref="TimeProvider.GetUtcNow"/> is used — the
    /// parser deliberately never reads <see cref="TimeProvider.LocalTimeZone"/>, since SEM-4 forbids
    /// resolving a date against "the server process's local timezone"; the zone comes from
    /// <see cref="DefaultZone"/> or the request's own <c>requestContext.zone</c> instead.
    /// </summary>
    public TimeProvider Clock { get; init; } = TimeProvider.System;

    /// <summary>
    /// The zone every preset's day/week/month/quarter/year boundary is computed in, when the request
    /// itself carries no <c>requestContext.zone</c>. Defaults to <see cref="TimeZoneInfo.Utc"/>.
    /// The request's own <c>requestContext.zone</c> takes precedence when present; an id that does
    /// not resolve is rejected cleanly (<see cref="AgGridRequestParseException"/>) rather than
    /// silently falling back to this value — a silent fallback would return a different day's rows
    /// than the grid shows, with nothing in the response saying so.
    ///
    /// <para>Must be an IANA-id-backed zone (e.g. <c>Europe/Paris</c>, <c>UTC</c>), since its
    /// <see cref="TimeZoneInfo.Id"/> becomes the emitted <see cref="Craticula.Core.Ir.DatetimeValue.Zone"/>
    /// provenance, and <c>ir.schema.json</c> pins that field to the IANA id shape. A Windows-id zone
    /// (<c>"Romance Standard Time"</c>) is caught by <see cref="Craticula.Core.Ir.FilterNodeValidator"/>
    /// on the parser's own output rather than silently emitted; on .NET 8+ every platform accepts
    /// IANA ids in <see cref="TimeZoneInfo.FindSystemTimeZoneById"/>, so this is a configuration
    /// mistake, not a platform limitation.</para>
    /// </summary>
    public TimeZoneInfo DefaultZone { get; init; } = TimeZoneInfo.Utc;

    /// <summary>
    /// The first day of the week used by the <c>thisWeek</c>/<c>lastWeek</c>/<c>nextWeek</c> presets.
    /// Defaults to <see cref="DayOfWeek.Monday"/>, matching AG Grid's own
    /// <c>DEFAULT_FIRST_DAY_OF_WEEK = 1</c>.
    ///
    /// <para><b>Why this has to be an explicit policy rather than "just do what AG Grid does".</b>
    /// AG Grid derives the week start in the browser, from the user's locale, via
    /// <c>Intl.Locale.prototype.getWeekInfo()</c> — a Web/ECMA-402 API with no server-side
    /// equivalent, and (crucially) no wire representation: the SSRM request carries the preset name
    /// and nothing else, so the server cannot recover the value the browser used even in principle.
    /// Any server-side resolution therefore <em>has</em> to pick a policy. This one picks AG Grid's
    /// own documented default and makes it configurable, so a host whose users are all in a
    /// Sunday-start (or Saturday-start) locale can align the server with what those users see
    /// instead of silently returning a week shifted by a day or two.</para>
    /// </summary>
    public DayOfWeek FirstDayOfWeek { get; init; } = DayOfWeek.Monday;

    /// <summary>
    /// The grid's schema, used for exactly ONE purpose: looking up the filtered field's declared
    /// <see cref="FieldType"/> so a resolved preset range can be emitted as the correct
    /// <see cref="Craticula.Core.Ir.TypedValue"/> variant (SEM-4 — see
    /// <see cref="DatePresetResolver"/>). It is NOT an allowlist gate here: SC-1 allowlisting stays
    /// <see cref="FieldAllowlistValidator"/>'s job, run downstream by
    /// <see cref="GridFilterPipeline"/> over the whole parsed tree, exactly as before this option
    /// existed. <see langword="null"/> (the default) is fine for any request without a date preset.
    /// </summary>
    public GridSchema? Schema { get; init; }

    private readonly int _defaultPageSize = 100;

    /// <summary>
    /// PG-1: the page a row request gets when it sends no <c>startRow</c>/<c>endRow</c> and is not an export of
    /// everything: the range <c>[0, DefaultPageSize)</c>. Default 100 (AG Grid's own block size). It is checked
    /// against SEC-3's maximum page size like any window, so a value above it is refused downstream, not
    /// clamped here. A value of 0 or less is rejected at configuration.
    /// </summary>
    public int DefaultPageSize
    {
        get => _defaultPageSize;
        init => _defaultPageSize = value > 0
            ? value
            : throw new ArgumentOutOfRangeException(nameof(DefaultPageSize), value, "DefaultPageSize must be a positive integer.");
    }

    /// <summary>
    /// PG-3: the host's switch for the wire flag <c>ignorePageLimit</c>. Off by default: a request carrying
    /// <c>ignorePageLimit: true</c> is then refused (<c>unbounded-not-allowed</c>) rather than silently capped.
    /// On, such a request with no window is the unpaginated page. Asking for every row is for the host to
    /// allow, on purpose; an export of everything needs no switch (PG-2).
    /// </summary>
    public bool AllowUnboundedRows { get; init; }

    /// <summary>The defaults, reused rather than re-allocated for every preset-free request.</summary>
    internal static readonly AgGridParseOptions Default = new();
}
