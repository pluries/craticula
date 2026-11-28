using Craticula.Core.Ir;

namespace Craticula.Core.Tests.Ir;

/// <summary>
/// Feature 011 (ADR-0015, follow-up F-1): the hour 24 is refused whatever the runtime's date parser does. The .NET 11
/// runtime's <c>DateTimeOffset.TryParse</c> accepts <c>24:00:00</c> where the .NET 10 one refused it, so both parsing
/// sites refuse it themselves. Scenarios US1-AS1 (the existing <c>FilterNodeValidatorIsoInstantTests</c> row), US1-AS2,
/// US1-AS3, US1-AS4.
/// </summary>
public class IsoInstantHourTwentyFourTests
{
    [Theory]
    [InlineData("2026-01-01T24:00:00Z")]
    [InlineData("2026-01-01T24:00:00+01:00")]
    [InlineData("2026-01-01T24:00:00.000Z")]
    [InlineData("2026-01-01T24:30:00Z")]
    public void US1_AS2_An_Instant_With_The_Hour_24_Is_Not_An_Iso_Instant(string raw) =>
        Assert.False(FilterNodeValidator.IsIsoInstant(raw));

    [Theory]
    [InlineData("2026-01-01T24:00:00Z")]
    [InlineData("2026-01-01T24:00:00+01:00")]
    [InlineData("2026-01-01T24:00:00.000Z")]
    [InlineData("2026-01-01T24:30:00Z")]
    public void US1_AS3_The_Other_Parsing_Site_Refuses_The_Same_Texts(string raw)
    {
        Assert.False(IsoInstant.TryParseUtc(raw, out var utc));
        Assert.Equal(default, utc);
    }

    [Theory]
    [InlineData("2026-01-01T23:59:59Z", "2026-01-01T23:59:59.0000000Z")]
    [InlineData("2026-01-01T00:00:00+02:00", "2025-12-31T22:00:00.0000000Z")]
    [InlineData("2026-12-31T23:59:59.999Z", "2026-12-31T23:59:59.9990000Z")]
    public void US1_AS4_A_Valid_Instant_Is_Still_Accepted_And_Parses_To_The_Same_Value(string raw, string expectedUtc)
    {
        Assert.True(FilterNodeValidator.IsIsoInstant(raw));
        Assert.True(IsoInstant.TryParseUtc(raw, out var utc));
        Assert.Equal(DateTimeKind.Utc, utc.Kind);
        Assert.Equal(expectedUtc, utc.ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ", System.Globalization.CultureInfo.InvariantCulture));
    }
}
