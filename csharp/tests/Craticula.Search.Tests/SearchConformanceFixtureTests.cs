using System.Text.Json.Nodes;
using Craticula.AgGrid;
using Craticula.Core.Schema;

namespace Craticula.Search.Tests;

/// <summary>
/// T-1a artifact equality for OpenSearch/Elasticsearch: for every in-scope fixture, run the REAL
/// end-to-end path a host runs — <see cref="AgGridRequestParser.Parse"/> -&gt;
/// <see cref="GridFilterPipeline.Process"/> -&gt; <see cref="SearchQueryBuilder.Build"/> — and
/// compare the result against that fixture's own <c>expected/search.artifact.json</c>.
///
/// <para><b>This suite is the third and last of the inverted ones.</b> Every
/// <c>postgres.artifact.json</c> had been compiled and re-compiled since #1638 and the
/// <c>mongo.artifact.json</c> arm since #1643; the 158 <c>search.artifact.json</c> files then on disk
/// were hand-authored across #1630-#1643 as a TERTIARY arm that <em>nothing had ever executed</em>. So a
/// disagreement here was never presumptively the compiler's fault, and it was never presumptively the
/// fixture's either: each was adjudicated against <c>spec/semantics.md</c> and the sibling artifacts,
/// and the losing side corrected. See <c>docs/feat/1644/context.md</c> for the census.</para>
/// </summary>
public class SearchConformanceFixtureTests
{
    /// <summary>
    /// The eight categories this compiler compiles end to end — every category on disk that carries a
    /// compiled artifact at all. Each declares the number of Search artifacts it is expected to
    /// contribute, so adding a fixture to one of them fails
    /// <see cref="Each_In_Scope_Category_Contributes_Exactly_The_Fixture_Count_It_Declares"/> rather
    /// than being silently unexercised.
    ///
    /// <para><c>dialect-parity</c> contributes 18 rather than its 25 directories (25 - 001..005 - 024 - 025):
    /// <c>001</c>-<c>004</c> are #1639's single-dialect MySQL/SQL Server/SQLite showcases and
    /// <c>005</c> is #1642's Oracle one, none of which carries a Search arm at all. Discovery filters
    /// on the artifact's presence, so they need no exclusion entry — there is nothing to compare
    /// against. <c>025</c> (#2243) is SQLite's own: a datetime is text there, so SEM-4's fixed-width bound has no
    /// Search counterpart. <c>024</c> is #1886's AGG-6 case and carries the five SQL arms only, for a different
    /// reason worth keeping distinct: this backend is already conformant with that rule and emits the
    /// identical token before and after it, so a Search arm would grade nothing.
    /// <c>ag-grid-majors</c> contributes 6 of its 8 for the same reason (<c>007</c> and
    /// <c>008</c> are rejection fixtures), and <c>page-export</c> fewer than its directory count
    /// (<c>012</c>-<c>020</c>, <c>022</c>, <c>025</c> and <c>026</c> exercise CSV-writer behavior on a
    /// single representative backend). That one is stated as the rule rather than as a subtraction on
    /// purpose — its arithmetic form went stale in #1653 while <see cref="InScopeCategories"/>'s own
    /// count did not move, so nothing failed.
    /// <c>group-aggregation</c> contributes 22 of its 23 because <c>020</c> has no Search arm at all:
    /// ordering a grouped level by an aggregate is refused on this backend (OSE-11(c)).</para>
    ///
    /// <para><c>page-export</c> joined in #1650 (EXP-1/EXP-2), and brought <c>sort-paging</c> from 11
    /// to 12 with it: both blockages were the same one — <c>AgGridRequestParser</c> could not read
    /// <c>exportScope</c>. This backend renders no projection either way (OSE-13), so nothing about
    /// EXP-1(b) changed here; only the requests could finally be fed.</para>
    /// </summary>
    private static readonly (string Category, int Expected)[] InScopeCategories =
    [
        ("operators", 62),
        ("date-presets", 26),
        ("community-infinite", 27),
        ("query-time-limit", 6),
        ("default-page-size", 5),
        ("dialect-parity", 19),
        ("group-aggregation", 24),
        ("filter-tree", 15),
        ("sort-paging", 17),
        ("ag-grid-majors", 6),
        ("page-export", 14)
    ];

    /// <summary>
    /// The categories deliberately NOT compiled, each with the reason — stated here rather than left
    /// as a silent absence, so a reader can tell "out of scope" from "forgotten".
    /// <see cref="Every_Fixture_Category_On_Disk_Is_Either_In_Scope_Or_Excluded_By_Name"/> fails if a
    /// NEW category appears and is named in neither list. The two reasons are the same two
    /// <c>PostgresConformanceFixtureTests</c> and <c>MongoConformanceFixtureTests</c> give, and
    /// deliberately so: nothing about them is backend-specific, so a divergence between the three
    /// lists would mean one of the suites had silently changed scope.
    /// </summary>
    private static readonly Dictionary<string, string> ExcludedCategories = new(StringComparer.Ordinal)
    {
        ["schemas"] = "Not a fixture category at all — the suite's own meta-schemas " +
                      "(search-artifact.schema.json and friends), validated by ajv-cli, not by this project.",
        ["adversarial"] = "Rejection-only fixtures: they carry expected/rejection.json, not a compiled artifact, " +
                          "and are already exercised by Craticula.Core.Tests' allowlist/limits/coercion suites. " +
                          "(They also carry no search.artifact.json, so discovery would skip them anyway — named " +
                          "here so the category list stays exhaustive.)"
    };

    /// <summary>
    /// EMPTY since #1650, exactly as in the SQL and Mongo suites: its last entry was
    /// <c>sort-paging/012</c>, blocked upstream on <c>AgGridRequestParser</c>'s missing
    /// <c>exportScope</c> — the same blockage that kept the whole <c>page-export</c> category out.
    /// Kept as a named, asserted-on collection rather than deleted.
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

    /// <summary>Every case directory in <paramref name="category"/> that carries a Search artifact and
    /// is not explicitly excluded, in ordinal name order.</summary>
    private static IReadOnlyList<string> DiscoverInScope(string category) =>
    [
        .. Directory.EnumerateDirectories(RepoPaths.Fixture(category))
            .Select(Path.GetFileName)
            .Where(name => name is not null)
            .Select(name => name!)
            .Where(name => File.Exists(RepoPaths.Fixture(category, name, "expected", "search.artifact.json")))
            .Where(name => !ExcludedFixtures.ContainsKey($"{category}/{name}"))
            .OrderBy(name => name, StringComparer.Ordinal)
    ];

    // ---- the conformance assertion ---------------------------------------------------------------

    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Compiles_To_The_Search_Body_Its_Own_Artifact_Pins(string category, string fixtureDir)
    {
        var actual = SearchFixtureCompiler.Compile(category, fixtureDir);

        Assert.Equal(
            SearchFixtureCompiler.CanonicalJson(Read(category, fixtureDir, "expected", "search.artifact.json")),
            SearchFixtureCompiler.CanonicalJson(actual.ToArtifact()));
    }

    /// <summary>
    /// SEM-3, asserted independently of the artifact text: <b>every</b> sort key carries an explicit
    /// <c>missing</c>, on all 175 fixtures.
    ///
    /// <para>SEM-3's first Must-NOT forbids relying on the engine's own default even when it happens
    /// to match, and SEM-6's fourth forbids "the stable key is probably never null" as a licence to
    /// omit the marker on the appended tiebreaker specifically. Both are the kind of omission the
    /// artifact comparison would only catch in the fixtures that happen to pin a null-ordering case,
    /// so it is checked here on every one — the Search counterpart of the contiguous-trio invariant
    /// <c>MongoConformanceFixtureTests</c> asserts for the same rule's emulated form.</para>
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Spells_An_Explicit_Missing_On_Every_Sort_Key(string category, string fixtureDir)
    {
        var sort = SearchFixtureCompiler.Compile(category, fixtureDir).Sort;

        if (sort is null)
        {
            // A grouped level or a distinct-values request returns buckets, not hits, so it has no
            // `sort` member at all — the composite's own bucket ordering is AGG-5/GRP-4's business.
            Assert.True(IsBucketRequest(category, fixtureDir));
            return;
        }

        Assert.NotEmpty(sort);

        foreach (var key in sort)
        {
            var body = Assert.Single(key!.AsObject()).Value!.AsObject();

            Assert.True(body.ContainsKey("order"), "SEM-3/AR-9: every sort key spells its direction.");
            Assert.True(body.ContainsKey("missing"), "SEM-3: every sort key spells its null placement.");
            Assert.Contains(body["missing"]!.GetValue<string>(), new[] { "_last", "_first" });
        }
    }

    /// <summary>
    /// OSE-9/OSE-10, asserted structurally: a request that returns hits carries a <c>query</c>, a
    /// <c>sort</c> and no <c>aggs</c>; one that returns buckets carries <c>size: 0</c>, an
    /// <c>aggs</c>, and neither <c>sort</c> nor <c>from</c>. The two forms are structurally different
    /// requests rather than one form with optional members, and a compiler that mixed them would
    /// produce a body both engines accept and neither answers usefully — <c>size: 0</c> beside a
    /// <c>sort</c> orders nothing.
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Emits_Either_A_Hit_Request_Or_A_Bucket_Request_And_Never_A_Mixture(
        string category, string fixtureDir)
    {
        var query = SearchFixtureCompiler.Compile(category, fixtureDir);

        if (IsBucketRequest(category, fixtureDir))
        {
            Assert.NotNull(query.Aggs);
            Assert.Null(query.Sort);
            Assert.Null(query.From);
            Assert.Equal(0, query.Size);
            return;
        }

        Assert.Null(query.Aggs);
        Assert.NotNull(query.Query);
        Assert.NotNull(query.Sort);
    }

    /// <summary>
    /// GRP-2's per-clause granularity, asserted as the property that makes MongoDB's accepted
    /// divergence #3 have no counterpart here: <c>case_insensitive</c> sits on the individual
    /// <c>term</c>/<c>wildcard</c> that asked for it, while a drill-down <c>term</c> and a composite
    /// source simply do not carry the parameter, so a single request satisfies SEM-1 and GRP-2 at
    /// once.
    ///
    /// <para><b>ONE fact, not 145 theories.</b> This was a <c>[Theory]</c> over every in-scope fixture
    /// until #1644's review pass observed that
    /// <see cref="SearchQuery.CaseInsensitivitySuppressedByBucketIdentity"/> is a <em>constant of the
    /// type</em> — unlike <c>MongoQuery.CollationSuppressedByBucketIdentity</c>, which is computed
    /// from what its pipeline actually did — so all 145 cases then in scope were asserting
    /// <c>Assert.False(false)</c> and inflating the suite's count with no information. What is worth
    /// asserting is the structural claim the constant STANDS FOR, which needs exactly one request:
    /// <c>group-aggregation/005</c>, the drill-down leaf that is MongoDB's own second divergence
    /// shape. In one body it spells an exact drill-down <c>term</c> (GRP-2) and orders on a
    /// case-insensitive string's normalizer sub-field (SEM-1) — the pair MongoDB has to choose
    /// between.</para>
    /// </summary>
    [Fact]
    public void Satisfies_SEM1_And_GRP2_In_The_One_Request_MongoDB_Must_Choose_Between()
    {
        var query = SearchFixtureCompiler.Compile("group-aggregation", "005-leaf-query-two-group-cols-fully-consumed");

        Assert.False(query.CaseInsensitivitySuppressedByBucketIdentity);

        // GRP-2: the drill-down term is exact — no `case_insensitive` anywhere in the query...
        Assert.DoesNotContain("case_insensitive", SearchFixtureCompiler.CanonicalJson(query.Query));

        // ...and SEM-1 is satisfied in the same body, on the leaf's own ordering key.
        Assert.Contains("product.normalized", SearchFixtureCompiler.CanonicalJson(query.Sort));
    }

    private static bool IsBucketRequest(string category, string fixtureDir)
    {
        if (SearchFixtureCompiler.IsSetValuesFixture(category, fixtureDir))
        {
            return true;
        }

        var parsed = SearchFixtureCompiler.PrepareRowFetch(category, fixtureDir).Parsed;

        return parsed.Group is { } group && group.GroupKeys.Count < group.GroupCols.Count;
    }

    // ---- anti-rot guards -------------------------------------------------------------------------

    [Fact]
    public void Each_In_Scope_Category_Contributes_Exactly_The_Fixture_Count_It_Declares()
    {
        var actual = InScopeCategories.ToDictionary(entry => entry.Category, entry => DiscoverInScope(entry.Category).Count);
        var declared = InScopeCategories.ToDictionary(entry => entry.Category, entry => entry.Expected);

        Assert.Equal(declared, actual);
    }

    [Fact]
    public void The_End_To_End_Suite_Is_All_160_Search_Artifacts_In_The_Suite()
    {
        // 166 with NOTHING subtracted, and it is the same number as the count of search.artifact.json
        // files on disk (asserted below): as of #1650 there is no excluded category carrying a Search
        // arm and no excluded fixture at all. It last moved when #1650's review pass authored
        // page-export/024; before that #1650 itself released page-export (13, now 14) and
        // sort-paging/012 from exclusion and authored page-export/023.
        Assert.Equal(221, InScopeFixtures.Count);
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
    public void Every_Search_Artifact_On_Disk_Is_Compiled_Or_Accounted_For()
    {
        // The count that closes the loop on "203 in scope": every search.artifact.json in the repo is
        // either exercised above, or inside a category/fixture this class excludes BY NAME. Since
        // #1650 nothing is excluded, so the two numbers are equal — the arithmetic is kept rather
        // than simplified away, because it is what would catch a future exclusion being added
        // without its artifacts being subtracted.
        var onDisk = Directory
            .EnumerateFiles(RepoPaths.Fixture(), "search.artifact.json", SearchOption.AllDirectories)
            .Count();

        var excludedCategoryArtifacts = ExcludedCategories.Keys
            .Where(category => Directory.Exists(RepoPaths.Fixture(category)))
            .Sum(category => Directory
                .EnumerateFiles(RepoPaths.Fixture(category), "search.artifact.json", SearchOption.AllDirectories)
                .Count());

        Assert.Equal(221, onDisk);
        Assert.Equal(0, excludedCategoryArtifacts);
        Assert.Equal(onDisk - excludedCategoryArtifacts - ExcludedFixtures.Count, InScopeFixtures.Count);
    }

    /// <summary>
    /// A recorded COVERAGE GAP, asserted so it self-heals rather than being a comment nobody
    /// re-reads: <b>no in-scope fixture declares a <c>physical.search.field</c> that differs from its
    /// colId</b>, so SC-4's field mapping — the thing that would turn <c>customerName</c> into
    /// <c>customer_name</c> in every <c>term</c> key, <c>exists</c> clause, <c>sort</c> key,
    /// composite source and aggregation metric — is exercised by unit tests alone. The <em>sub-field</em>
    /// halves of the same mapping (<c>keywordSubField</c>, <c>normalizedSubField</c>) ARE covered by
    /// fixtures, and richly; it is the base field that is always the identity here.
    ///
    /// <para>This test FAILS the day a fixture closes the gap, which is the point: at that moment
    /// this note is obsolete and should be deleted along with it, rather than left claiming a
    /// weakness that no longer exists.</para>
    /// </summary>
    [Fact]
    public void Records_That_No_In_Scope_Fixture_Maps_A_Search_Field_Away_From_Its_ColId()
    {
        var remapped = new List<string>();

        foreach (var (category, _) in InScopeCategories)
        {
            foreach (var fixtureDir in DiscoverInScope(category))
            {
                var schema = GridSchema.Parse(Read(category, fixtureDir, "schema.json"));

                remapped.AddRange(schema.Fields
                    .Where(field => field.Value.Physical?.Search?.Field is { } path && path != field.Key)
                    .Select(field => $"{category}/{fixtureDir}:{field.Key}"));
            }
        }

        Assert.Empty(remapped);
    }

    [Fact]
    public void Every_Excluded_Fixture_Still_Exists_On_Disk()
    {
        foreach (var (path, reason) in ExcludedFixtures)
        {
            var segments = path.Split('/');
            Assert.True(
                Directory.Exists(RepoPaths.Fixture(segments)),
                $"Excluded fixture '{path}' no longer exists. Reason recorded for the exclusion: {reason}");
        }
    }

    /// <summary>
    /// Every compiled artifact validates against the suite's own meta-schema, whose
    /// <c>additionalProperties: false</c> is what pins the member set — and therefore what makes
    /// OSE-13's "there is no projection member on this backend" a contract rather than an omission.
    /// Checked here as well as by <c>ajv-cli</c> because ajv only ever sees the files on disk, never
    /// the compiler's own output.
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Emits_Only_Members_The_Artifact_Meta_Schema_Admits(string category, string fixtureDir)
    {
        var permitted = JsonNode
            .Parse(File.ReadAllText(RepoPaths.Fixture("schemas", "search-artifact.schema.json")))!
            .AsObject()["properties"]!
            .AsObject()
            .Select(property => property.Key)
            .ToHashSet(StringComparer.Ordinal);

        var artifact = SearchFixtureCompiler.Compile(category, fixtureDir).ToArtifact();

        Assert.All(artifact.Select(member => member.Key), member => Assert.Contains(member, permitted));
    }

    private static string Read(string category, string fixtureDir, params string[] rest) =>
        SearchFixtureCompiler.Read(category, fixtureDir, rest);
}
