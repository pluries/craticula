using System.Text.Json;
using System.Text.RegularExpressions;

namespace Craticula.Sql.Tests;

/// <summary>
/// T-1a artifact equality for every non-Postgres dialect (the three #1639 adds, plus #1642's
/// Oracle), the exact counterpart of <see cref="PostgresConformanceFixtureTests"/>: for every
/// fixture carrying an <c>expected/&lt;dialect&gt;.artifact.json</c>, run the same end-to-end path
/// (<c>AgGridRequestParser.Parse</c> -&gt; <c>GridFilterPipeline.Process</c> -&gt;
/// <see cref="SqlQueryBuilder.Build"/>, via <see cref="FixtureCompiler"/>) and compare byte-for-byte
/// against that arm.
///
/// <para><b>The artifact is the oracle, never a literal repeated here.</b> Every non-Postgres arm
/// was produced by mechanical transformation — #1639's 19 pre-existing ones by applying each
/// engine's quote character to their own fixture's <c>schema.json</c> identifiers, its 30 promoted
/// ones by substituting documented per-dialect tokens into that fixture's own <b>Postgres</b> arm,
/// <c>021</c>/<c>022</c>'s six by transforming the arms of the fixture whose schema they reuse
/// verbatim (<c>014</c> and <c>020</c> respectively), and #1642's 39 Oracle arms the same way from
/// the Postgres arm again — and never by running these dialects and recording the output. That is
/// what keeps this comparison between two independently-derived answers instead of a tautology. A
/// disagreement is informative in both directions and must be investigated, never resolved by
/// editing the fixture.</para>
///
/// <para><b>Why the parity showcases are the real assertion.</b> <c>dialect-parity/006</c>-<c>022</c>
/// carry the same request compiled for all five SQL dialects. Because the predicate structure,
/// SQL-2's parenthesisation, the ORDER BY key sequence, SEM-6's tiebreaker and the parameter
/// <em>values</em> are the builder's and cannot vary per dialect, five arms passing at once is a
/// direct check of BM-1's "adding a dialect changes only spellings" — the same claim
/// <see cref="DialectIndependenceTests"/> makes against a synthetic dialect, here against real
/// engines and a hand-authored oracle.</para>
///
/// <para><b>One arm in the suite breaks that reading, and it is the whole point of #1642.</b>
/// <c>dialect-parity/019</c>'s oracle arm is not a token substitution of its Postgres arm: SQL-7's
/// empty-string-is-NULL collapse makes <c>blank</c> a bare <c>IS NULL</c> there, where the other
/// four spell the two-disjunct form. That divergence lives behind
/// <see cref="ISqlDialect.EmptyStringIsNull"/> — an engine fact, not a rendering — so BM-1 still
/// holds; the artifact is what proves the builder consulted it.</para>
/// </summary>
public class DialectConformanceFixtureTests
{
    /// <summary>
    /// The dialects under test, each with the number of arms it is expected to find on disk. Adding
    /// an arm to a fixture without updating this table fails
    /// <see cref="Each_Dialect_Contributes_Exactly_The_Arm_Count_It_Declares"/> rather than being
    /// silently unexercised — the same discovery-based anti-rot shape the Postgres suite uses.
    ///
    /// <para>#1640 added 16 arms per dialect in <c>group-aggregation/</c> and #1641 five more
    /// (<c>016</c>-<c>019</c>, BM-3, plus <c>022</c> from its review pass); the rest live in
    /// <c>dialect-parity/</c>. Discovery below
    /// deliberately scans <em>every</em> category: an arm added elsewhere must show up as a count
    /// mismatch here, not disappear because this suite only looked in one directory.</para>
    ///
    /// <para><b>Oracle's 42 is the full-parity count, and the other three add their own single-engine
    /// showcases on top of it.</b> The shared base is <c>dialect-parity/006</c>-<c>023</c> (18, every
    /// case carrying all six backends) plus <c>024</c> (1, #1886's AGG-6 discriminator — SQL-only, no
    /// Mongo/Search arm, but it DOES carry all five SQL dialects including Oracle's) plus
    /// <c>group-aggregation/</c> in full (23) = <b>42</b>, which is exactly Oracle's count because
    /// Oracle has no single-engine showcase among <c>dialect-parity/001</c>-<c>005</c>. The other
    /// three each add theirs on top of that same 42: SQLite +2 (<c>004</c>, ASCII-CI <c>LIKE</c>, and
    /// <c>025</c>, #2243's fixed-width datetime bound) reaches 44; T-SQL +1 (<c>003</c>, <c>OFFSET/FETCH</c>) reaches 43; MySQL +2 (<c>001</c> AND <c>002</c> are
    /// both <c>ISNULL</c> showcases) reaches 44. The asymmetry in this table is therefore the coverage
    /// policy, not a gap. <em>(This paragraph once summed to 41 while claiming 42 — it had not been
    /// updated for <c>024</c>'s contribution, the same drift class #1644's review pass corrected here
    /// once already for <c>023</c>. Corrected again in #1886's review pass.)</em></para>
    /// </summary>
    private static readonly (string Name, ISqlDialect Dialect, int Expected)[] Dialects =
    [
        ("mssql", MssqlDialect.Instance, 51),
        ("mysql", MySqlDialect.Instance, 47),
        ("oracle", OracleDialect.Instance, 45),
        ("sqlite", SqliteDialect.Instance, 47)
    ];

    /// <summary>
    /// Deliberately empty, and kept rather than deleted so the shape of the guard matches the
    /// Postgres suite's: every non-Postgres arm on disk is currently compiled end to end. The
    /// Postgres suite's own exclusion list is empty too as of #1650 — until then it held
    /// <c>sort-paging/012</c>, blocked on the adapter's missing <c>exportScope</c>, which carried no
    /// non-Postgres arm and so never reached here. An entry added later must state its reason.
    /// </summary>
    private static readonly Dictionary<string, string> ExcludedArms = new(StringComparer.Ordinal);

    public static TheoryData<string, string, string> Arms
    {
        get
        {
            var data = new TheoryData<string, string, string>();
            foreach (var (name, _, _) in Dialects)
            {
                foreach (var (category, fixtureDir) in Discover(name))
                {
                    data.Add(name, category, fixtureDir);
                }
            }

            return data;
        }
    }

    /// <summary>Every fixture on disk, in any category, carrying an arm for
    /// <paramref name="dialect"/> and not excluded by name — in ordinal category/name order.</summary>
    private static IReadOnlyList<(string Category, string Fixture)> Discover(string dialect) =>
    [
        .. Directory.EnumerateDirectories(RepoPaths.Fixture())
            .Select(path => Path.GetFileName(path)!)
            .Where(category => category != "count-mode") // count fixtures are not pages; SqlCountTests compiles them
            .OrderBy(name => name, StringComparer.Ordinal)
            .SelectMany(category => Directory
                .EnumerateDirectories(RepoPaths.Fixture(category))
                .Select(path => Path.GetFileName(path)!)
                .OrderBy(name => name, StringComparer.Ordinal)
                .Select(fixture => (Category: category, Fixture: fixture)))
            .Where(entry => File.Exists(
                RepoPaths.Fixture(entry.Category, entry.Fixture, "expected", $"{dialect}.artifact.json")))
            .Where(entry => !ExcludedArms.ContainsKey($"{entry.Category}/{entry.Fixture}/{dialect}"))
    ];

    private static ISqlDialect DialectNamed(string name) =>
        Dialects.Single(entry => entry.Name == name).Dialect;

    // ---- the conformance assertion ---------------------------------------------------------------

    [Theory]
    [MemberData(nameof(Arms))]
    public void Compiles_To_The_Sql_And_Params_Its_Own_Artifact_Pins(string dialect, string category, string fixtureDir)
    {
        var actual = FixtureCompiler.Compile(category, fixtureDir, DialectNamed(dialect));
        using var expected = JsonDocument.Parse(
            FixtureCompiler.Read(category, fixtureDir, "expected", $"{dialect}.artifact.json"));

        Assert.Equal(expected.RootElement.GetProperty("dialect").GetString(), actual.Dialect);
        Assert.Equal(expected.RootElement.GetProperty("sql").GetString(), actual.Sql);
        Assert.Equal(
            FixtureCompiler.CanonicalJson(expected.RootElement.GetProperty("params")),
            FixtureCompiler.CanonicalJson(actual.Parameters));
    }

    /// <summary>
    /// SEC-2's structural invariant, generalised past Postgres: the statement's placeholders and the
    /// parameter list are the same length.
    ///
    /// <para>Only the two NAMED protocols can keep the Postgres suite's stronger form — SQL Server's
    /// <c>@pN</c> and Oracle's <c>:pN</c>. Such a placeholder carries its ordinal, so <c>p1..pN</c>
    /// can be asserted ascending in first-appearance order; a MySQL/SQLite <c>?</c> carries no
    /// ordinal at all — position in the text <em>is</em> the binding — so there is nothing to compare
    /// and the check is necessarily count-only. That is not a weaker test by accident but the actual
    /// difference between a named and a positional protocol, and it is why <c>params</c> ordering on
    /// those two dialects is guarded by the artifact comparison above rather than by arithmetic
    /// here.</para>
    /// </summary>
    [Theory]
    [MemberData(nameof(Arms))]
    public void Binds_Exactly_As_Many_Parameters_As_The_Statement_Has_Placeholders(string dialect, string category, string fixtureDir)
    {
        var actual = FixtureCompiler.Compile(category, fixtureDir, DialectNamed(dialect));

        if (dialect is "mssql" or "oracle")
        {
            var ordinals = NamedPlaceholder.Matches(actual.Sql)
                .Select(match => int.Parse(match.Groups[1].Value))
                .ToList();

            Assert.Equal(actual.Parameters.Count, ordinals.Count);
            Assert.Equal(Enumerable.Range(1, actual.Parameters.Count), ordinals);
            return;
        }

        Assert.Equal(actual.Parameters.Count, PositionalPlaceholder.Matches(actual.Sql).Count);
    }

    // Both named protocols in one pattern: the sigil differs (`@` on T-SQL, `:` on Oracle) but the
    // `pN` body and its ascending-first-appearance contract do not.
    private static readonly Regex NamedPlaceholder = new(@"[@:]p([0-9]+)", RegexOptions.Compiled);

    /// <summary>
    /// A bare <c>?</c> is also SQLite's GLOB single-character wildcard, so counting every <c>?</c>
    /// could over-count on a case-sensitive substring match — <c>dialect-parity/021</c>'s sqlite arm
    /// reaches that path for real. It stays safe for two independent reasons, and the delimiter
    /// lookarounds encode the second: the class-escaped form (<c>[?]</c>) lives in the bound
    /// <em>parameter</em>, never in the SQL text, and a GLOB anchor is a single-quoted literal
    /// (<c>'*'</c>) which cannot be preceded by a space the way every placeholder is.
    /// </summary>
    private static readonly Regex PositionalPlaceholder = new(@"(?<=[\s(])\?(?=[\s,)]|$)", RegexOptions.Compiled);

    // ---- anti-rot guards -------------------------------------------------------------------------

    [Fact]
    public void Each_Dialect_Contributes_Exactly_The_Arm_Count_It_Declares()
    {
        var actual = Dialects.ToDictionary(entry => entry.Name, entry => Discover(entry.Name).Count);
        var declared = Dialects.ToDictionary(entry => entry.Name, entry => entry.Expected);

        Assert.Equal(declared, actual);
    }

    [Fact]
    public void The_Suite_Is_All_173_Non_Postgres_Arms_In_The_Fixture_Tree()
    {
        // #2522 added the most recent 8: all four arms of group-aggregation/024-025 (GRP-7). Before that #2565 added 4: the SQL Server arms of sort-paging/013-016 (SEM-6's effective sort lists a field once;
        // SQL Server is the arm that refused a column named twice in an ORDER BY list).
        // #2243 added the 1 before that: dialect-parity/025, SQLite's fixed-width datetime bound (SEM-4);
        // its one arm is the sqlite one, authored from the rule rather than transformed from another arm.
        // #1886 added the 4 before that: dialect-parity/024, AGG-6's discriminator — a grouped level
        // ordered by an AVG beside a COALESCE-wrapped SUM. All four arms are that fixture's own
        // Postgres arm with each engine's documented tokens substituted, like every arm below.
        // #1644's review pass added the 4 before that: group-aggregation/023, the one case carrying
        // both a consumed groupKeys and a filterModel, which is what turns GRP-5's drill-down-leads
        // clause order from a normative sentence into something every dialect's `params` is graded on.
        // #1642 added 39: Oracle at full parity coverage (dialect-parity/006-022 and all of
        // group-aggregation/), derived by transformation from each fixture's own Postgres arm like
        // every arm below it. Only ONE of the 39 differs from what the other dialects' arms say
        // structurally — dialect-parity/019, where SQL-7's empty-string-is-NULL collapse makes
        // `blank` a bare `IS NULL`; the rest differ in tokens alone, which is the claim.
        // #1641's review pass added the 3 before that: group-aggregation/022, the one case carrying both a
        // filter model and a searchPrefix, which is what turns GRP-6(c)'s WHERE order from a
        // normative sentence plus a C# unit test into something every port is graded on.
        // #1641 itself added 12: three dialects for each of group-aggregation/016-019, BM-3's
        // set-filter distinct-values query, which had no dialect arms because no compiler built it.
        // Derived by transformation from each fixture's own Postgres arm, like everything below.
        // #1639 left 55 (19 re-authored + 30 from promoting `011`-`020` to full parity coverage +
        // 3 for `021`, the case-sensitive substring case, + 3 for `022`, T-SQL's `[` wildcard).
        // #1640 added 51: three dialects for each of `group-aggregation/001`-`015`, `020` and
        // `021` (the last added in #1640's review pass, pinning AG-6's auto-group-column colId),
        // which is what makes BM-2's "identical grouping protocol across all four dialects"
        // checkable at all. This number going up without the per-dialect table above changing with
        // it means an arm was added and went unexercised.
        Assert.Equal(190, Arms.Count);
    }

    [Fact]
    public void Every_Non_Postgres_Sql_Artifact_On_Disk_Belongs_To_A_Dialect_This_Suite_Runs()
    {
        // The reverse direction of the count guard: catches an arm named for a dialect nobody
        // implements — a typo'd filename, or a future engine's artifacts landing before its dialect
        // does (which is exactly what this guard caught for Oracle up to #1642).
        var known = Dialects.Select(entry => entry.Name).Append("postgres").ToHashSet(StringComparer.Ordinal);

        var unknown = Directory
            .EnumerateFiles(RepoPaths.Fixture(), "*.artifact.json", SearchOption.AllDirectories)
            .Select(path => Path.GetFileName(path)!)
            .Select(name => name[..name.IndexOf('.', StringComparison.Ordinal)])
            .Where(name => name is not ("mongo" or "search"))
            .Where(name => !known.Contains(name))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

        Assert.Empty(unknown);
    }

    [Fact]
    public void Every_Excluded_Arm_Still_Exists_On_Disk()
    {
        // An exclusion that no longer matches a real artifact is dead weight that hides whether the
        // case was renamed (and is now silently in scope) or deleted.
        foreach (var (path, reason) in ExcludedArms)
        {
            var segments = path.Split('/');
            Assert.True(
                File.Exists(RepoPaths.Fixture(segments[0], segments[1], "expected", $"{segments[2]}.artifact.json")),
                $"Excluded arm '{path}' no longer exists. Reason recorded for the exclusion: {reason}");
        }
    }

    /// <summary>
    /// SQL-1 made checkable on every arm this suite discovers: an artifact quotes its table and its
    /// columns, so none can silently regress to the pre-#1639 bare form. Deliberately asserted on
    /// the <em>file</em> rather than on compiler output — that is where the regression would live,
    /// and the compiler is what this suite is trying to grade.
    ///
    /// <para>Oracle falls through to the standard <c>"</c> pair, and there the rule earns its keep
    /// twice over: that engine folds an unquoted identifier to UPPERCASE, so a regression to the
    /// bare form would not merely look different, it would query a different (and on these fixtures,
    /// nonexistent) table.</para>
    /// </summary>
    [Theory]
    [MemberData(nameof(Arms))]
    public void Every_Arm_Quotes_Its_Identifiers_With_Its_Own_Engines_Character(string dialect, string category, string fixtureDir)
    {
        using var artifact = JsonDocument.Parse(
            FixtureCompiler.Read(category, fixtureDir, "expected", $"{dialect}.artifact.json"));
        var sql = artifact.RootElement.GetProperty("sql").GetString()!;

        using var schema = JsonDocument.Parse(FixtureCompiler.Read(category, fixtureDir, "schema.json"));
        var source = schema.RootElement.GetProperty("source").GetString()!;

        var (open, close) = dialect switch
        {
            "mssql" => ("[", "]"),
            "mysql" => ("`", "`"),
            _ => ("\"", "\"")
        };

        Assert.Contains($"FROM {open}{source}{close}", sql, StringComparison.Ordinal);

        foreach (var field in schema.RootElement.GetProperty("fields").EnumerateObject())
        {
            var column = field.Value.GetProperty("physical").GetProperty("sql").GetProperty("column").GetString()!;

            // A column the fixture's request never references simply does not appear; what must
            // never appear is an UNQUOTED occurrence of one that does.
            Assert.DoesNotMatch(
                new Regex($@"(?<!{Regex.Escape(open)})\b{Regex.Escape(column)}\b(?!{Regex.Escape(close)})"),
                sql);
        }
    }
}
