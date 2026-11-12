using System.Text.Json;
using System.Text.RegularExpressions;
using Craticula.AgGrid;
using Craticula.Core.Schema;

namespace Craticula.Sql.Tests;

/// <summary>
/// T-1a artifact equality: for every leaf fixture this story scopes in, run the REAL end-to-end path
/// a host runs — <see cref="AgGridRequestParser.Parse"/> -&gt;
/// <see cref="GridFilterPipeline.Process"/> -&gt; <see cref="SqlQueryBuilder.Build"/> — and compare
/// the result byte-for-byte against that fixture's own <c>expected/postgres.artifact.json</c>.
///
/// <para><b>The artifact is the oracle, never a literal repeated here.</b> The fixtures were
/// hand-authored (#1630) and repaired by mechanical transformation of that hand-authored SQL
/// (#1638 Phase A) specifically so this comparison is between two independently-derived answers. A
/// disagreement is therefore informative in both directions and must be investigated, never
/// resolved by editing the fixture.</para>
/// </summary>
public class PostgresConformanceFixtureTests
{
    /// <summary>
    /// The eight categories this compiler compiles end to end — every category on disk that carries a
    /// compiled artifact at all. Each declares the number of Postgres artifacts it is expected to
    /// contribute, so adding a fixture to one of them fails
    /// <see cref="Each_In_Scope_Category_Contributes_Exactly_The_Fixture_Count_It_Declares"/> rather
    /// than being silently unexercised.
    ///
    /// <para><c>group-aggregation</c> joined in #1640 (BM-2), which is also why
    /// <c>ag-grid-majors</c> went from 5 to 6: its <c>004</c> is a grouped request and was excluded
    /// by name until a grouping compiler existed. It reached all 21 of its cases in #1641, when
    /// <c>016</c>-<c>019</c>'s BM-3 distinct-values path gained a compiler
    /// (<see cref="SqlQueryBuilder.BuildSetValues"/>); <see cref="FixtureCompiler"/> dispatches on the
    /// request document, so both kinds run through this same theory. #1641's review pass added
    /// <c>022</c> — the one case carrying a filter model AND a <c>searchPrefix</c>, which is what
    /// makes GRP-6(c)'s <c>WHERE</c> order artifact-pinned rather than unit-test-pinned — taking it
    /// to 22.</para>
    ///
    /// <para><c>page-export</c> joined in #1650 (EXP-1/EXP-2), and brought <c>sort-paging</c> from 11
    /// to 12 with it: both blockages were the same one — <c>AgGridRequestParser</c> could not read
    /// <c>exportScope</c>, so no export request could be fed end to end. All <b>26</b> of its cases are
    /// in scope, not just the fourteen carrying a Mongo/Search arm: <c>012</c>-<c>020</c>,
    /// <c>022</c>, <c>025</c> and <c>026</c> document CSV-<em>writer</em> behavior, but their
    /// <c>postgres.artifact.json</c> is an ordinary compiled query and is compared like any other.
    /// <b>Two of them are here to be byte-identical to another case's arm</b>, which is the sharpest
    /// thing this runner contributes to the writer stories: <c>025</c> (#1651) is <c>012</c>'s request
    /// with only <c>exportFormat</c> changed, and <c>026</c> (#1653) is <c>013</c>'s inputs with only
    /// EXP-5's per-field <c>format</c> members added to its schema — so neither the requested format nor
    /// a declared date pattern or decimal separator moves a single byte a compiler emits. Neither
    /// relation is left as prose:
    /// <c>Craticula.Export.Csv.Tests.CsvWriterConformanceFixtureTests</c>
    /// .<c>The_Tsv_Fixture_Is_The_Comma_Fixtures_Request_With_Only_Its_ExportFormat_Changed</c> and
    /// .<c>The_Per_Field_Format_Fixture_Is_The_Semicolon_Fixtures_Inputs_With_Only_Its_Schema_Changed</c>
    /// assert them, together with the input difference that makes each meaningful.</para>
    /// </summary>
    private static readonly (string Category, int Expected)[] InScopeCategories =
    [
        ("operators", 62),
        ("date-presets", 26),
        ("community-infinite", 27),
        ("query-time-limit", 6),
        ("default-page-size", 5),
        ("dialect-parity", 21),
        ("group-aggregation", 25),
        ("filter-tree", 15),
        ("sort-paging", 17),
        ("ag-grid-majors", 6),
        ("page-export", 26)
    ];

    /// <summary>
    /// The categories deliberately NOT compiled, each with the reason — stated here rather than left
    /// as a silent absence, so a reader can tell "out of scope" from "forgotten".
    /// <see cref="Every_Fixture_Category_On_Disk_Is_Either_In_Scope_Or_Excluded_By_Name"/> fails if a
    /// NEW category appears and is named in neither list. Neither of the two remaining entries is a
    /// compiler gap: one is not a fixture category and the other carries no artifact to compare.
    /// </summary>
    private static readonly Dictionary<string, string> ExcludedCategories = new(StringComparer.Ordinal)
    {
        ["schemas"] = "Not a fixture category at all — the suite's own meta-schemas " +
                      "(sql-artifact.schema.json and friends), validated by ajv-cli, not by this project.",
        ["adversarial"] = "Rejection-only fixtures: they carry expected/rejection.json, not a compiled artifact, " +
                          "and are already exercised by Craticula.Core.Tests' allowlist/limits/coercion suites."
    };

    /// <summary>
    /// EMPTY since #1650, and kept as a named, asserted-on collection rather than deleted: the point
    /// of this suite is that a fixture is either exercised or excluded FOR A STATED REASON, and an
    /// empty exclusion list is the strongest form of that claim. Everything that carries no
    /// <c>expected/postgres.artifact.json</c> (the rejection-shaped cases, and
    /// <c>dialect-parity/001</c>-<c>005</c>'s single-dialect MySQL/SQL Server/SQLite/Oracle artifacts)
    /// is filtered out by the discovery below without needing to be listed, since there is nothing to
    /// compare against.
    ///
    /// <para>Its last entry was <c>sort-paging/012</c>, blocked upstream on
    /// <c>AgGridRequestParser</c>'s missing <c>exportScope</c> — the same blockage that kept the whole
    /// <c>page-export</c> category out — and #1650 removed both.</para>
    /// </summary>
    private static readonly Dictionary<string, string> ExcludedFixtures = new(StringComparer.Ordinal);

    public static TheoryData<string, string> InScopeFixtures
    {
        get
        {
            var data = new TheoryData<string, string>();
            foreach (var (category, _) in InScopeCategories)
            {
                foreach (var fixtureDir in DiscoverInScope(category))
                {
                    data.Add(category, fixtureDir);
                }
            }

            return data;
        }
    }

    /// <summary>Every case directory in <paramref name="category"/> that carries a Postgres artifact
    /// and is not explicitly excluded, in ordinal name order.</summary>
    private static IReadOnlyList<string> DiscoverInScope(string category) =>
    [
        .. Directory.EnumerateDirectories(RepoPaths.Fixture(category))
            .Select(Path.GetFileName)
            .Where(name => name is not null)
            .Select(name => name!)
            .Where(name => File.Exists(RepoPaths.Fixture(category, name, "expected", "postgres.artifact.json")))
            .Where(name => !ExcludedFixtures.ContainsKey($"{category}/{name}"))
            .OrderBy(name => name, StringComparer.Ordinal)
    ];

    // ---- the conformance assertion ---------------------------------------------------------------

    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Compiles_To_The_Sql_And_Params_Its_Own_Postgres_Artifact_Pins(string category, string fixtureDir)
    {
        var actual = Compile(category, fixtureDir);
        using var expected = JsonDocument.Parse(Read(category, fixtureDir, "expected", "postgres.artifact.json"));

        Assert.Equal(expected.RootElement.GetProperty("dialect").GetString(), actual.Dialect);
        Assert.Equal(expected.RootElement.GetProperty("sql").GetString(), actual.Sql);
        Assert.Equal(
            CanonicalJson(expected.RootElement.GetProperty("params")),
            CanonicalJson(actual.Parameters));
    }

    /// <summary>
    /// SEC-2's structural invariant: the statement's placeholders and the parameter list are the
    /// same length. A dialect that formatted a placeholder without binding (or bound without
    /// formatting) would desynchronize the two, and the artifact comparison above would only catch
    /// it if the drift happened to change the SQL text as well.
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Binds_Exactly_As_Many_Parameters_As_The_Statement_Has_Placeholders(string category, string fixtureDir)
    {
        var actual = Compile(category, fixtureDir);

        var ordinals = PostgresPlaceholder.Matches(actual.Sql)
            .Select(match => int.Parse(match.Groups[1].Value))
            .ToList();

        Assert.Equal(actual.Parameters.Count, ordinals.Count);

        // ...and they are $1..$N in first-appearance order, which is what makes "params[] is
        // positional" true rather than merely plausible.
        Assert.Equal(Enumerable.Range(1, actual.Parameters.Count), ordinals);
    }

    private static readonly Regex PostgresPlaceholder = new(@"\$([0-9]+)", RegexOptions.Compiled);

    // ---- anti-rot guards -------------------------------------------------------------------------

    [Fact]
    public void Each_In_Scope_Category_Contributes_Exactly_The_Fixture_Count_It_Declares()
    {
        // Guards the usual fixture-test rot in the direction that matters: a case ADDED to one of
        // these categories later must either pass this suite or be given an explicit exclusion
        // reason — it can never just quietly go unexercised.
        var actual = InScopeCategories.ToDictionary(entry => entry.Category, entry => DiscoverInScope(entry.Category).Count);
        var declared = InScopeCategories.ToDictionary(entry => entry.Category, entry => entry.Expected);

        Assert.Equal(declared, actual);
    }

    [Fact]
    public void The_End_To_End_Suite_Is_All_175_Fixtures_In_The_Scoped_Categories()
    {
        // #2522 added the most recent 2: group-aggregation/024-025 (GRP-7, the null group's drill-down). Before that #2565 added 5: sort-paging/013-017. 184 with NOTHING subtracted: ExcludedFixtures is empty as of #1650, so every Postgres
        // artifact in a scoped category is compiled and compared. The number last moved when #1886
        // authored dialect-parity/024 (AGG-6's discriminator: a grouped level ordered by an AVG,
        // beside a COALESCE-wrapped SUM in the same projection — the only case whose ORDER BY fails
        // both when the wrap is missing and when it is over-applied; over-applying it to a projected
        // AVG/MIN/MAX is separately caught by group-aggregation/008-010,012,013). Before that #1653
        // authored page-export/026 (EXP-5's per-field format overrides — a schema member no compiler
        // reads, which is why that arm is byte-identical to 013's); before that #1651
        // authored page-export/025 (TSV writer output), #1650's review pass authored
        // page-export/024, #1650 itself released page-export (23) and sort-paging/012 from exclusion
        // and authored page-export/023, and #1644's review pass added group-aggregation/023 — the one
        // case carrying both a consumed groupKeys and a filterModel, which pins GRP-5's
        // drill-down-leads clause order in `params`.
        Assert.Equal(236, InScopeFixtures.Count);
        Assert.Empty(ExcludedFixtures);
    }

    [Fact]
    public void Every_Fixture_Category_On_Disk_Is_Either_In_Scope_Or_Excluded_By_Name()
    {
        var onDisk = Directory
            .EnumerateDirectories(RepoPaths.Fixture())
            .Select(path => Path.GetFileName(path)!)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

        var accounted = InScopeCategories
            .Select(entry => entry.Category)
            .Concat(ExcludedCategories.Keys)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

        Assert.Equal(accounted, onDisk);
    }

    [Fact]
    public void Every_Postgres_Artifact_On_Disk_Is_Compiled_Or_Accounted_For()
    {
        // The count that closes the loop on "225 in scope": every postgres.artifact.json in the repo
        // is either exercised above, or inside a category/fixture this class excludes BY NAME. The
        // category table plus Every_Fixture_Category_On_Disk_… does not close it — an artifact added
        // under an EXCLUDED category (adversarial/) would leave every count untouched and go silently
        // uncompiled. The Mongo and Search runners have asserted this since #1650; this one had not,
        // in the story whose headline property is that every fixture is executed by something.
        var onDisk = Directory
            .EnumerateFiles(RepoPaths.Fixture(), "postgres.artifact.json", SearchOption.AllDirectories)
            .Count();

        var excludedCategoryArtifacts = ExcludedCategories.Keys
            .Where(category => Directory.Exists(RepoPaths.Fixture(category)))
            .Sum(category => Directory
                .EnumerateFiles(RepoPaths.Fixture(category), "postgres.artifact.json", SearchOption.AllDirectories)
                .Count());

        Assert.Equal(236, onDisk);
        Assert.Equal(0, excludedCategoryArtifacts);
        Assert.Equal(onDisk - excludedCategoryArtifacts - ExcludedFixtures.Count, InScopeFixtures.Count);
    }

    [Fact]
    public void Every_Excluded_Fixture_Still_Exists_On_Disk()
    {
        // An exclusion that no longer matches a real directory is dead weight that hides whether the
        // case was renamed (and is now silently in scope) or deleted.
        foreach (var (path, reason) in ExcludedFixtures)
        {
            var segments = path.Split('/');
            Assert.True(
                Directory.Exists(RepoPaths.Fixture(segments)),
                $"Excluded fixture '{path}' no longer exists. Reason recorded for the exclusion: {reason}");
        }
    }

    // ---- the harness ------------------------------------------------------------------------------

    private static SqlQuery Compile(string category, string fixtureDir) =>
        FixtureCompiler.Compile(category, fixtureDir, PostgresDialect.Instance);

    private static string Read(string category, string fixtureDir, params string[] rest) =>
        FixtureCompiler.Read(category, fixtureDir, rest);

    private static string CanonicalJson<T>(T value) => FixtureCompiler.CanonicalJson(value);
}
