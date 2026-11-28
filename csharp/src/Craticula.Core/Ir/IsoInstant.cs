using System.Globalization;

namespace Craticula.Core.Ir;

/// <summary>
/// SEM-4: reading a <see cref="DatetimeValue"/> as the absolute instant it denotes.
///
/// <para><b>The rule this owns, in one sentence:</b> a <c>datetimeValue</c>'s
/// <see cref="DatetimeValue.Value"/> is an instant, its <see cref="DatetimeValue.Zone"/> is
/// <em>provenance</em> recording how a wire string was resolved into that instant, and the zone is
/// never an instruction to a backend. Two requests naming the same moment as <c>…T12:00:00+02:00</c>
/// and as <c>…T10:00:00Z</c> must therefore reach every backend as one value.</para>
///
/// <para><b>Why it is here rather than in each compiler (#1645).</b> The SQL compiler needs the
/// instant so it can bind the canonical <c>…Z</c> text its artifacts pin; the EF Core execution
/// adapter needs the same instant as a real <see cref="DateTime"/> so a provider can bind it as a
/// timestamp. Those are two different <em>renderings</em> of one <em>reading</em>, and AR-4 requires
/// the reading to be identical: an adapter that parsed with <see cref="DateTimeStyles.None"/> would
/// resolve a zone-less string against the machine's local time and silently return different rows on
/// a differently-configured host than the compiler it is supposed to agree with. So the parse lives
/// once, and the formatting stays with whoever needs a particular text.</para>
///
/// <para><b>Non-throwing on purpose.</b> Each caller reports a malformed value in its own
/// vocabulary — <c>SqlCompilationException</c>, <c>EfCoreCompilationException</c> — and every one of
/// them runs <see cref="FilterNodeValidator"/> first, whose <c>datetime</c> pattern already mandates
/// a trailing <c>Z</c> or an explicit offset. A failure here is therefore a caller precondition
/// failure rather than a client error, and the caller is the layer that can say so.</para>
/// </summary>
public static class IsoInstant
{
    /// <summary>
    /// Parses an ISO-8601 timestamp carrying an explicit offset (or <c>Z</c>) and returns it as a
    /// UTC <see cref="DateTime"/> — <see cref="DateTimeKind.Utc"/>, sub-second precision preserved.
    ///
    /// <para><see cref="DateTimeStyles.RoundtripKind"/> is what makes the offset in the text the
    /// authority. A zone-less string cannot reach a caller that validated its input, and if one did
    /// it would be interpreted as local time by any style short of
    /// <see cref="DateTimeStyles.AssumeUniversal"/> — which is deliberately NOT used here, because
    /// silently assuming UTC for a string that never said so would turn the upstream validator's job
    /// into a formality and make the same fixture compile to two different instants depending on
    /// which layer happened to run.</para>
    /// </summary>
    /// <returns><see langword="true"/> and the instant in UTC; <see langword="false"/> and
    /// <see langword="default"/> when <paramref name="value"/> is not an ISO-8601 instant.</returns>
    public static bool TryParseUtc(string? value, out DateTime utc)
    {
        if (value is not null
            && !HasHourTwentyFour(value)
            && DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var instant))
        {
            utc = instant.UtcDateTime;
            return true;
        }

        utc = default;
        return false;
    }

    /// <summary>
    /// Whether <paramref name="value"/> writes the hour as <c>24</c> (<c>T24:00:00Z</c>). It is not a real instant, the
    /// documented rule refuses it, and the runtime's own parser cannot be trusted to: .NET 10 refuses it, .NET 11 accepts it
    /// (ADR-0015). Both parsing sites of this assembly ask here first, so the answer does not depend on the runtime.
    /// </summary>
    internal static bool HasHourTwentyFour(string value)
    {
        for (var at = value.IndexOf("24:", StringComparison.Ordinal); at > 0; at = value.IndexOf("24:", at + 1, StringComparison.Ordinal))
        {
            if (value[at - 1] is 'T' or 't' or ' ')
            {
                return true;
            }
        }

        return false;
    }
}
