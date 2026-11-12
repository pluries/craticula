using Craticula.Core.Ir;
using FieldType = Craticula.Core.Schema.FieldType;

namespace Craticula.AgGrid.Tests;

/// <summary>
/// Hand-built coverage of <see cref="DatePresetResolver"/> as a pure function — every one of AG
/// Grid's 22 presets against the fixture suite's pinned <c>now</c>, plus the arithmetic edges the
/// fixtures deliberately steer clear of so that each fixture stays unambiguous: month-end clamping in
/// the <c>lastNMonths</c> family, leap days, year boundaries, the configurable first-day-of-week
/// policy, non-UTC zones, and both DST discontinuities in <see cref="DatePresetResolver.StartOfDayInstant"/>.
/// </summary>
public class DatePresetResolverTests
{
    private static readonly TimeZoneInfo Utc = TimeZoneInfo.Utc;
    private static readonly TimeZoneInfo Paris = TimeZoneInfo.FindSystemTimeZoneById("Europe/Paris");
    private static readonly TimeZoneInfo NewYork = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");

    /// <summary>The instant <c>spec/fixtures/date-presets/001-022</c> pin: Wednesday 2026-08-12,
    /// mid-week, mid-month, mid-quarter, far from both year boundaries.</summary>
    private const string FixtureNow = "2026-08-12T14:37:00Z";

    private static DateTimeOffset At(string instant) =>
        DateTimeOffset.Parse(instant, System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.RoundtripKind);

    private static DatePresetRange Resolve(
        string preset, string now, TimeZoneInfo? zone = null, DayOfWeek firstDayOfWeek = DayOfWeek.Monday) =>
        DatePresetResolver.Resolve(preset, At(now), zone ?? Utc, firstDayOfWeek);

    private static void AssertRange(DatePresetRange range, string from, string to)
    {
        Assert.Equal(DateOnly.Parse(from, System.Globalization.CultureInfo.InvariantCulture), range.From);
        Assert.Equal(DateOnly.Parse(to, System.Globalization.CultureInfo.InvariantCulture), range.To);
    }

    // ---- The vocabulary itself -------------------------------------------------------------------

    [Fact]
    public void PresetNames_Is_The_Closed_22_Member_Vocabulary_With_No_Duplicates()
    {
        // 22, not 21: some prose (including #1636's own planning notes) says 21, but AG Grid's
        // ISimpleFilterModelPresetType union and its @Spec resolution table both list 22.
        Assert.Equal(22, DatePresetResolver.PresetNames.Count);
        Assert.Equal(22, DatePresetResolver.PresetNames.Distinct(StringComparer.Ordinal).Count());
    }

    [Fact]
    public void Every_Name_In_The_Vocabulary_Actually_Resolves()
    {
        // Guards the one failure mode a per-preset test table cannot catch on its own: a member added
        // to PresetNames but never given a row in the resolution switch.
        foreach (var preset in DatePresetResolver.PresetNames)
        {
            Assert.True(DatePresetResolver.IsPreset(preset));
            Assert.True(DatePresetResolver.TryResolve(preset, At(FixtureNow), Utc, DayOfWeek.Monday, out var range));
            Assert.True(range.From < range.To, $"'{preset}' resolved to an empty or inverted range.");
        }
    }

    [Theory]
    [InlineData("equals")]
    [InlineData("inRange")]
    [InlineData("blank")]
    [InlineData("")]
    [InlineData("Today")]        // wrong case: a TypeScript string-literal union is case-sensitive
    [InlineData("TODAY")]
    [InlineData("last8Days")]    // plausible-looking, but not in AG Grid's closed set
    [InlineData("lastQuarterly")]
    public void Non_Preset_Names_Are_Not_Presets(string type)
    {
        Assert.False(DatePresetResolver.IsPreset(type));
        Assert.False(DatePresetResolver.TryResolve(type, At(FixtureNow), Utc, DayOfWeek.Monday, out var range));
        Assert.Equal(default, range);
    }

    [Fact]
    public void Resolve_Throws_For_A_Non_Preset_Name()
    {
        var ex = Assert.Throws<ArgumentOutOfRangeException>(() => Resolve("notAPreset", FixtureNow));

        Assert.Contains("today", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Resolution_Is_Deterministic_For_Identical_Inputs()
    {
        Assert.Equal(Resolve("last90Days", FixtureNow), Resolve("last90Days", FixtureNow));
    }

    // ---- The full 22-row table, against the fixture suite's pinned now ---------------------------

    [Theory]
    [InlineData("today", "2026-08-12", "2026-08-13")]
    [InlineData("yesterday", "2026-08-11", "2026-08-12")]
    [InlineData("tomorrow", "2026-08-13", "2026-08-14")]
    [InlineData("thisWeek", "2026-08-10", "2026-08-17")]
    [InlineData("lastWeek", "2026-08-03", "2026-08-10")]
    [InlineData("nextWeek", "2026-08-17", "2026-08-24")]
    [InlineData("thisMonth", "2026-08-01", "2026-09-01")]
    [InlineData("lastMonth", "2026-07-01", "2026-08-01")]
    [InlineData("nextMonth", "2026-09-01", "2026-10-01")]
    [InlineData("thisQuarter", "2026-07-01", "2026-10-01")]
    [InlineData("lastQuarter", "2026-04-01", "2026-07-01")]
    [InlineData("nextQuarter", "2026-10-01", "2027-01-01")]
    [InlineData("thisYear", "2026-01-01", "2027-01-01")]
    [InlineData("lastYear", "2025-01-01", "2026-01-01")]
    [InlineData("nextYear", "2027-01-01", "2028-01-01")]
    [InlineData("yearToDate", "2026-01-01", "2026-08-13")]
    [InlineData("last7Days", "2026-08-05", "2026-08-13")]
    [InlineData("last30Days", "2026-07-13", "2026-08-13")]
    [InlineData("last90Days", "2026-05-14", "2026-08-13")]
    [InlineData("last6Months", "2026-02-12", "2026-08-13")]
    [InlineData("last12Months", "2025-08-12", "2026-08-13")]
    [InlineData("last24Months", "2024-08-12", "2026-08-13")]
    public void Every_Preset_Resolves_Per_AgGrids_Spec_Table(string preset, string from, string to) =>
        AssertRange(Resolve(preset, FixtureNow), from, to);

    [Fact]
    public void Adjacent_Week_Presets_Abut_Exactly_With_No_Gap_And_No_Overlap()
    {
        // The half-open [from, to) convention's whole payoff: lastWeek/thisWeek/nextWeek tile the
        // timeline perfectly. An inclusive upper bound would make each pair overlap by a day.
        var last = Resolve("lastWeek", FixtureNow);
        var current = Resolve("thisWeek", FixtureNow);
        var next = Resolve("nextWeek", FixtureNow);

        Assert.Equal(current.From, last.To);
        Assert.Equal(next.From, current.To);
    }

    [Fact]
    public void Adjacent_Month_Quarter_And_Year_Presets_Abut_Exactly()
    {
        Assert.Equal(Resolve("thisMonth", FixtureNow).From, Resolve("lastMonth", FixtureNow).To);
        Assert.Equal(Resolve("nextMonth", FixtureNow).From, Resolve("thisMonth", FixtureNow).To);
        Assert.Equal(Resolve("thisQuarter", FixtureNow).From, Resolve("lastQuarter", FixtureNow).To);
        Assert.Equal(Resolve("nextQuarter", FixtureNow).From, Resolve("thisQuarter", FixtureNow).To);
        Assert.Equal(Resolve("thisYear", FixtureNow).From, Resolve("lastYear", FixtureNow).To);
        Assert.Equal(Resolve("nextYear", FixtureNow).From, Resolve("thisYear", FixtureNow).To);
    }

    [Fact]
    public void Rolling_LastN_Presets_All_Share_StartOfTomorrow_As_Their_Upper_Bound()
    {
        // AG Grid's spec table ends every "last N" row at startOfTomorrow, not startOfToday: today is
        // always fully included. last7Days therefore spans 8 calendar days, which is the definition,
        // not an off-by-one.
        var tomorrow = new DateOnly(2026, 8, 13);
        foreach (var preset in new[] { "last7Days", "last30Days", "last90Days", "last6Months", "last12Months", "last24Months", "yearToDate" })
        {
            Assert.Equal(tomorrow, Resolve(preset, FixtureNow).To);
        }

        Assert.Equal(8, Resolve("last7Days", FixtureNow).To.DayNumber - Resolve("last7Days", FixtureNow).From.DayNumber);
    }

    // ---- First-day-of-week policy ---------------------------------------------------------------

    [Theory]
    [InlineData(DayOfWeek.Monday, "2026-08-10", "2026-08-17")]
    [InlineData(DayOfWeek.Sunday, "2026-08-09", "2026-08-16")]
    [InlineData(DayOfWeek.Saturday, "2026-08-08", "2026-08-15")]
    [InlineData(DayOfWeek.Wednesday, "2026-08-12", "2026-08-19")]
    public void ThisWeek_Honours_The_Configured_First_Day_Of_Week(DayOfWeek firstDayOfWeek, string from, string to) =>
        AssertRange(Resolve("thisWeek", FixtureNow, firstDayOfWeek: firstDayOfWeek), from, to);

    [Fact]
    public void A_Sunday_Belongs_To_The_Previous_Week_Under_Monday_Start_And_Starts_One_Under_Sunday_Start()
    {
        // The single day where the Monday/Sunday policies disagree most visibly, and the reason the
        // policy has to be explicit at all (AG Grid reads it from the browser's Intl.Locale, which has
        // no server-side equivalent and no wire representation).
        const string sundayNoon = "2026-08-16T12:00:00Z";

        AssertRange(Resolve("thisWeek", sundayNoon, firstDayOfWeek: DayOfWeek.Monday), "2026-08-10", "2026-08-17");
        AssertRange(Resolve("thisWeek", sundayNoon, firstDayOfWeek: DayOfWeek.Sunday), "2026-08-16", "2026-08-23");
    }

    [Fact]
    public void When_Today_Is_Already_The_First_Day_Of_The_Week_ThisWeek_Starts_Today()
    {
        // Guards the modulo: a naive (dow - first) with no wrap sends this a week backwards.
        AssertRange(Resolve("thisWeek", "2026-08-10T12:00:00Z"), "2026-08-10", "2026-08-17");
    }

    [Fact]
    public void A_Week_Preset_Crossing_The_Year_Boundary_Spans_Both_Years()
    {
        // Thursday 2026-12-31 -> the Monday-start week runs 2026-12-28 .. 2027-01-04.
        AssertRange(Resolve("thisWeek", "2026-12-31T12:00:00Z"), "2026-12-28", "2027-01-04");
        AssertRange(Resolve("nextWeek", "2026-12-31T12:00:00Z"), "2027-01-04", "2027-01-11");
    }

    // ---- Quarter boundaries ---------------------------------------------------------------------

    [Theory]
    [InlineData("2026-01-15T12:00:00Z", "2026-01-01", "2026-04-01")]
    [InlineData("2026-03-31T12:00:00Z", "2026-01-01", "2026-04-01")]
    [InlineData("2026-04-01T12:00:00Z", "2026-04-01", "2026-07-01")]
    [InlineData("2026-06-30T12:00:00Z", "2026-04-01", "2026-07-01")]
    [InlineData("2026-07-01T12:00:00Z", "2026-07-01", "2026-10-01")]
    [InlineData("2026-09-30T12:00:00Z", "2026-07-01", "2026-10-01")]
    [InlineData("2026-10-01T12:00:00Z", "2026-10-01", "2027-01-01")]
    [InlineData("2026-12-31T12:00:00Z", "2026-10-01", "2027-01-01")]
    public void ThisQuarter_Uses_Calendar_Quarters_On_Every_Boundary_Month(string now, string from, string to) =>
        AssertRange(Resolve("thisQuarter", now), from, to);

    [Fact]
    public void Quarter_Presets_Cross_The_Year_Boundary_In_Both_Directions()
    {
        AssertRange(Resolve("nextQuarter", "2026-11-15T12:00:00Z"), "2027-01-01", "2027-04-01");
        AssertRange(Resolve("lastQuarter", "2026-02-15T12:00:00Z"), "2025-10-01", "2026-01-01");
    }

    // ---- Month-end clamping in the lastNMonths family --------------------------------------------

    [Theory]
    [InlineData("last6Months", "2026-08-31T12:00:00Z", "2026-02-28")]   // Feb 31 does not exist -> clamp
    [InlineData("last6Months", "2028-08-31T12:00:00Z", "2028-02-29")]   // ...and 2028 is a leap year
    [InlineData("last6Months", "2026-08-30T12:00:00Z", "2026-02-28")]   // Feb 30 clamps to the same day
    [InlineData("last12Months", "2028-02-29T12:00:00Z", "2027-02-28")]  // leap day, 12 months back
    [InlineData("last24Months", "2028-02-29T12:00:00Z", "2026-02-28")]  // leap day, 24 months back
    [InlineData("last6Months", "2026-07-31T12:00:00Z", "2026-01-31")]   // 31 exists in January: no clamp
    public void LastNMonths_Uses_Calendar_Month_Arithmetic_With_End_Of_Month_Clamping(
        string preset, string now, string expectedFrom)
    {
        // Not a fixed day count: 6 months back from 2026-08-12 is 181 days, from 2026-03-12 it is 182.
        // And the target day-of-month may simply not exist, which clamps rather than overflowing into
        // the following month. NOTE this is a deliberate divergence from the AG Grid client on
        // month-end days — its raw JS `setMonth` overflows instead of clamping — see the extended
        // comment on DatePresetResolver's own "last N months" arm for which presets/days differ and
        // why the published @Spec table is the chosen oracle.
        Assert.Equal(
            DateOnly.Parse(expectedFrom, System.Globalization.CultureInfo.InvariantCulture),
            Resolve(preset, now).From);
    }

    [Fact]
    public void LastMonth_On_The_31st_Clamps_Its_Own_Month_Start_Nowhere_Because_Month_Starts_Always_Exist()
    {
        // Contrast with the rolling family above: this/last/nextMonth are anchored on the 1st, so no
        // clamping is possible or needed even when "today" is a 31st.
        AssertRange(Resolve("lastMonth", "2026-03-31T12:00:00Z"), "2026-02-01", "2026-03-01");
        AssertRange(Resolve("nextMonth", "2026-01-31T12:00:00Z"), "2026-02-01", "2026-03-01");
    }

    // ---- Leap years and year boundaries ----------------------------------------------------------

    [Fact]
    public void Leap_Day_Is_Handled_As_An_Ordinary_Day()
    {
        AssertRange(Resolve("today", "2028-02-29T12:00:00Z"), "2028-02-29", "2028-03-01");
        AssertRange(Resolve("tomorrow", "2028-02-28T12:00:00Z"), "2028-02-29", "2028-03-01");
        AssertRange(Resolve("yesterday", "2028-03-01T12:00:00Z"), "2028-02-29", "2028-03-01");
        AssertRange(Resolve("thisMonth", "2028-02-29T12:00:00Z"), "2028-02-01", "2028-03-01");
    }

    [Fact]
    public void A_Leap_Year_ThisYear_Range_Still_Ends_On_The_Next_January_First()
    {
        AssertRange(Resolve("thisYear", "2028-02-29T12:00:00Z"), "2028-01-01", "2029-01-01");
        AssertRange(Resolve("yearToDate", "2028-02-29T12:00:00Z"), "2028-01-01", "2028-03-01");
    }

    [Fact]
    public void Day_Presets_Cross_The_Year_Boundary()
    {
        AssertRange(Resolve("today", "2026-12-31T23:59:59Z"), "2026-12-31", "2027-01-01");
        AssertRange(Resolve("tomorrow", "2026-12-31T23:59:59Z"), "2027-01-01", "2027-01-02");
        AssertRange(Resolve("yesterday", "2027-01-01T00:00:00Z"), "2026-12-31", "2027-01-01");
        AssertRange(Resolve("yearToDate", "2027-01-01T00:00:00Z"), "2027-01-01", "2027-01-02");
    }

    // ---- The request's zone decides which calendar day "now" falls on -----------------------------

    [Fact]
    public void The_Calendar_Day_Is_Computed_In_The_Requests_Zone_Not_In_Utc()
    {
        // One instant, three zones, three different answers for "today" — SEM-4's whole point.
        const string lateEveningUtc = "2026-08-12T23:30:00Z";

        AssertRange(Resolve("today", lateEveningUtc, Utc), "2026-08-12", "2026-08-13");
        AssertRange(Resolve("today", lateEveningUtc, Paris), "2026-08-13", "2026-08-14");
        AssertRange(Resolve("today", lateEveningUtc, NewYork), "2026-08-12", "2026-08-13");

        const string earlyMorningUtc = "2026-08-12T02:30:00Z";
        AssertRange(Resolve("today", earlyMorningUtc, Utc), "2026-08-12", "2026-08-13");
        AssertRange(Resolve("today", earlyMorningUtc, NewYork), "2026-08-11", "2026-08-12");
    }

    [Fact]
    public void The_Zone_Can_Shift_A_Week_Month_Quarter_And_Year_Preset_Too()
    {
        // Sunday 23:30 UTC is already Monday in Paris, so the Monday-start week is a completely
        // different, non-overlapping range (spec/fixtures/date-presets/025 pins this same case).
        AssertRange(Resolve("thisWeek", "2026-08-16T23:30:00Z", Utc), "2026-08-10", "2026-08-17");
        AssertRange(Resolve("thisWeek", "2026-08-16T23:30:00Z", Paris), "2026-08-17", "2026-08-24");

        // Last instant of August in UTC is already September in Paris.
        AssertRange(Resolve("thisMonth", "2026-08-31T23:30:00Z", Utc), "2026-08-01", "2026-09-01");
        AssertRange(Resolve("thisMonth", "2026-08-31T23:30:00Z", Paris), "2026-09-01", "2026-10-01");

        // ...which is also a quarter boundary crossing, and at New Year, a year boundary crossing.
        AssertRange(Resolve("thisQuarter", "2026-09-30T23:30:00Z", Paris), "2026-10-01", "2027-01-01");
        AssertRange(Resolve("thisYear", "2026-12-31T23:30:00Z", Paris), "2027-01-01", "2028-01-01");
    }

    [Fact]
    public void A_Non_Utc_Offset_Instant_Is_Converted_Before_Resolution_Not_Read_Literally()
    {
        // The clock hands back a DateTimeOffset that may not be UTC-based; the resolver must convert
        // it into the request's zone rather than reading its date component as-is.
        var range = DatePresetResolver.Resolve(
            "today", DateTimeOffset.Parse("2026-08-13T01:30:00+02:00", System.Globalization.CultureInfo.InvariantCulture),
            Utc, DayOfWeek.Monday);

        AssertRange(range, "2026-08-12", "2026-08-13");
    }

    // ---- StartOfDayInstant: DST correctness ------------------------------------------------------

    [Theory]
    [InlineData("2026-08-13", "Europe/Paris", "2026-08-12T22:00:00Z")]   // CEST, UTC+02:00
    [InlineData("2026-01-15", "Europe/Paris", "2026-01-14T23:00:00Z")]   // CET,  UTC+01:00
    [InlineData("2026-08-13", "UTC", "2026-08-13T00:00:00Z")]
    [InlineData("2026-08-13", "Asia/Kathmandu", "2026-08-12T18:15:00Z")] // +05:45, a non-whole-hour offset
    [InlineData("2026-08-13", "America/New_York", "2026-08-13T04:00:00Z")]
    public void StartOfDayInstant_Is_Local_Midnight_In_The_Given_Zone(string date, string zoneId, string expectedUtc)
    {
        var instant = DatePresetResolver.StartOfDayInstant(
            DateOnly.Parse(date, System.Globalization.CultureInfo.InvariantCulture),
            TimeZoneInfo.FindSystemTimeZoneById(zoneId));

        Assert.Equal(At(expectedUtc), instant);
    }

    [Fact]
    public void The_Two_Bounds_Of_A_Range_Spanning_A_Dst_Transition_Carry_Different_Offsets()
    {
        // The single most common way to get this wrong: read the zone's offset once, apply it to both
        // bounds. Europe's spring-forward is 2026-03-29, inside this Monday-start week.
        var range = Resolve("thisWeek", "2026-03-25T12:00:00Z", Paris);
        AssertRange(range, "2026-03-23", "2026-03-30");

        Assert.Equal(At("2026-03-22T23:00:00Z"), DatePresetResolver.StartOfDayInstant(range.From, Paris));
        Assert.Equal(At("2026-03-29T22:00:00Z"), DatePresetResolver.StartOfDayInstant(range.To, Paris));
        Assert.Equal(TimeSpan.FromHours(1), DatePresetResolver.StartOfDayInstant(range.From, Paris).Offset);
        Assert.Equal(TimeSpan.FromHours(2), DatePresetResolver.StartOfDayInstant(range.To, Paris).Offset);
    }

    [Fact]
    public void Autumn_Dst_Also_Changes_The_Offset_Between_The_Two_Bounds()
    {
        var range = Resolve("thisWeek", "2026-10-21T12:00:00Z", Paris);
        AssertRange(range, "2026-10-19", "2026-10-26");

        Assert.Equal(TimeSpan.FromHours(2), DatePresetResolver.StartOfDayInstant(range.From, Paris).Offset);
        Assert.Equal(TimeSpan.FromHours(1), DatePresetResolver.StartOfDayInstant(range.To, Paris).Offset);
    }

    [Fact]
    public void StartOfDayInstant_Resolves_A_Spring_Forward_Gap_Where_Local_Midnight_Never_Happens()
    {
        // America/Santiago springs forward AT midnight on 2026-09-06: 23:59:59 -04:00 jumps straight
        // to 01:00:00 -03:00, so local 00:00 is not a real instant that day. The day nonetheless
        // starts — at the transition instant itself. TimeZoneInfo.ConvertTimeToUtc would THROW here.
        var santiago = TimeZoneInfo.FindSystemTimeZoneById("America/Santiago");
        var gapDay = new DateOnly(2026, 9, 6);

        Assert.True(santiago.IsInvalidTime(gapDay.ToDateTime(TimeOnly.MinValue, DateTimeKind.Unspecified)));
        Assert.Equal(At("2026-09-06T04:00:00Z"), DatePresetResolver.StartOfDayInstant(gapDay, santiago));

        // Sanity: the neighbouring days behave normally, one either side of the transition.
        Assert.Equal(At("2026-09-05T04:00:00Z"), DatePresetResolver.StartOfDayInstant(new DateOnly(2026, 9, 5), santiago));
        Assert.Equal(At("2026-09-07T03:00:00Z"), DatePresetResolver.StartOfDayInstant(new DateOnly(2026, 9, 7), santiago));
    }

    [Fact]
    public void StartOfDayInstant_Picks_The_First_Occurrence_When_Local_Midnight_Happens_Twice()
    {
        // A zone that falls back at 01:00 -> 00:00 on 2026-11-01, so local 00:00 occurs twice: once
        // at -04:00 (still DST) and again an hour later at -05:00. The DAY starts at the first one —
        // taking the second would silently drop that day's first hour out of every [startOfDay, ...)
        // range. TimeZoneInfo.GetUtcOffset on its own returns the standard-time (second) offset.
        // Built here, not looked up: this is America/Havana's rule as of tzdata 2026c, but the operating
        // system's time zone data moves (2026f dropped the November transition) and a test of the library
        // must not depend on it.
        var havana = TimeZoneInfo.CreateCustomTimeZone(
            "Test/FallBackAtMidnight",
            TimeSpan.FromHours(-5),
            "Test zone",
            "Standard",
            "Daylight",
            [
                TimeZoneInfo.AdjustmentRule.CreateAdjustmentRule(
                    new DateTime(2026, 1, 1),
                    new DateTime(2026, 12, 31),
                    TimeSpan.FromHours(1),
                    TimeZoneInfo.TransitionTime.CreateFixedDateRule(new DateTime(1, 1, 1, 0, 0, 0), 3, 8),
                    TimeZoneInfo.TransitionTime.CreateFixedDateRule(new DateTime(1, 1, 1, 1, 0, 0), 11, 1))
            ]);
        var ambiguousDay = new DateOnly(2026, 11, 1);

        Assert.True(havana.IsAmbiguousTime(ambiguousDay.ToDateTime(TimeOnly.MinValue, DateTimeKind.Unspecified)));

        var start = DatePresetResolver.StartOfDayInstant(ambiguousDay, havana);
        Assert.Equal(At("2026-11-01T04:00:00Z"), start);
        Assert.Equal(TimeSpan.FromHours(-4), start.Offset);
        Assert.True(start < At("2026-11-01T05:00:00Z"), "The day must start at the FIRST occurrence of local midnight.");
    }

    // ---- ToTypedBounds -----------------------------------------------------------------------------

    [Fact]
    public void A_Date_Field_Gets_DateValue_Bounds_With_No_Instant_Manufactured()
    {
        var (from, to) = DatePresetResolver.ToTypedBounds(Resolve("today", FixtureNow), FieldType.Date, Utc);

        Assert.Equal("2026-08-12", Assert.IsType<DateValue>(from).Value);
        Assert.Equal("2026-08-13", Assert.IsType<DateValue>(to).Value);
    }

    [Fact]
    public void A_Date_Fields_Bounds_Are_Zone_Independent_Once_The_Day_Is_Chosen()
    {
        // The zone still decides WHICH day (tested above), but a dateValue carries no zone at all, so
        // formatting the chosen day must not consult the zone a second time.
        var range = new DatePresetRange(new DateOnly(2026, 8, 12), new DateOnly(2026, 8, 13));

        Assert.Equal(
            DatePresetResolver.ToTypedBounds(range, FieldType.Date, Utc),
            DatePresetResolver.ToTypedBounds(range, FieldType.Date, Paris));
    }

    [Fact]
    public void A_Datetime_Field_Gets_DatetimeValue_Bounds_As_Utc_Normalized_Instants_Plus_Zone_Provenance()
    {
        var (from, to) = DatePresetResolver.ToTypedBounds(Resolve("today", FixtureNow, Paris), FieldType.Datetime, Paris);

        var fromValue = Assert.IsType<DatetimeValue>(from);
        var toValue = Assert.IsType<DatetimeValue>(to);

        Assert.Equal("2026-08-11T22:00:00Z", fromValue.Value);
        Assert.Equal("2026-08-12T22:00:00Z", toValue.Value);
        Assert.Equal("Europe/Paris", fromValue.Zone);
        Assert.Equal("Europe/Paris", toValue.Zone);
    }

    [Fact]
    public void A_Datetime_Bound_Satisfies_Ir_Schemas_Instant_Pattern_Even_At_A_Non_Whole_Hour_Offset()
    {
        // Kathmandu is +05:45, so the emitted instant has a non-zero minute component — it must still
        // round-trip through ir.schema.json's ISO-8601 instant pattern (FilterNodeValidator enforces
        // this on the parser's own output, so a format slip here surfaces as a validation failure).
        var kathmandu = TimeZoneInfo.FindSystemTimeZoneById("Asia/Kathmandu");
        var (from, _) = DatePresetResolver.ToTypedBounds(Resolve("today", FixtureNow, kathmandu), FieldType.Datetime, kathmandu);

        Assert.Equal("2026-08-11T18:15:00Z", Assert.IsType<DatetimeValue>(from).Value);

        var node = new ComparisonNode
        {
            Field = "createdAt",
            Op = ComparisonOperator.InRange,
            From = from,
            To = from,
            FromInclusive = true,
            ToInclusive = false
        };
        Assert.Null(Record.Exception(() => FilterNodeValidator.Validate(node)));
    }

    [Theory]
    [InlineData(FieldType.String)]
    [InlineData(FieldType.Int64)]
    [InlineData(FieldType.Decimal)]
    [InlineData(FieldType.Double)]
    [InlineData(FieldType.Boolean)]
    public void A_Non_Date_Field_Type_Cannot_Carry_A_Preset(FieldType fieldType) =>
        Assert.Throws<ArgumentOutOfRangeException>(
            () => DatePresetResolver.ToTypedBounds(Resolve("today", FixtureNow), fieldType, Utc));
}
