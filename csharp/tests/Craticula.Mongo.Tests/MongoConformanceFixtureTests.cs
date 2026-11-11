using System.Text.Json.Nodes;
using Craticula.AgGrid;
using Craticula.Core.Schema;

namespace Craticula.Mongo.Tests;

/// <summary>
/// T-1a artifact equality for MongoDB: for every in-scope fixture, run the REAL end-to-end path a
/// host runs — <see cref="AgGridRequestParser.Parse"/> -&gt;
/// <see cref="GridFilterPipeline.Process"/> -&gt; <see cref="MongoPipelineBuilder.Build"/> — and
/// compare the result against that fixture's own <c>expected/mongo.artifact.json</c>.
///
/// <para><b>This suite is the inverse of the SQL ones, and the difference matters.</b> Every
/// <c>postgres.artifact.json</c> had been compiled and re-compiled since #1638; the 157
/// <c>mongo.artifact.json</c> files then on disk were hand-authored across #1630-#1642 as a secondary arm that
/// <em>nothing had ever executed</em>. So a disagreement here was never presumptively the compiler's
/// fault, and it was never presumptively the fixture's either: each was adjudicated against
/// <c>spec/semantics.md</c> and the sibling artifacts, and the losing side corrected. See
/// <c>docs/feat/1643/context.md</c> for the census.</para>
/// </summary>
public class MongoConformanceFixtureTests
{
    /// <summary>
    /// The eight categories this compiler compiles end to end — every category on disk that carries a
    /// compiled artifact at all. Each declares the number of Mongo artifacts it is expected to
    /// contribute, so adding a fixture to one of them fails
    /// <see cref="Each_In_Scope_Category_Contributes_Exactly_The_Fixture_Count_It_Declares"/> rather
    /// than being silently unexercised.
    ///
    /// <para><c>dialect-parity</c> contributes 18 rather than its 25 directories (25 - 001..005 - 024 - 025):
    /// <c>001</c>-<c>004</c> are #1639's single-dialect MySQL/SQL Server/SQLite showcases and
    /// <c>005</c> is Oracle's, none of which carries a Mongo arm at all. Discovery filters on the
    /// artifact's presence, so they need no exclusion entry — there is nothing to compare
    /// against. <c>025</c> (#2243) is SQLite's own: a datetime is text there, so SEM-4's fixed-width bound has no
    /// Mongo counterpart. <c>024</c> is #1886's AGG-6 case and carries the five SQL arms only, for a different
    /// reason worth keeping distinct: this backend is already conformant with that rule and emits the
    /// identical token before and after it, so a Mongo arm would grade nothing.
    /// <c>page-export</c> contributes fewer than its directory count for the same reason:
    /// <c>012</c>-<c>020</c>, <c>022</c>, <c>025</c> and <c>026</c> exercise CSV-writer behavior on a
    /// single representative backend and carry a Postgres arm only. Stated as the rule rather than as
    /// a subtraction on purpose — the arithmetic form went stale in #1653 while
    /// <see cref="InScopeCategories"/>'s own count did not move, so nothing failed.</para>
    ///
    /// <para><c>page-export</c> joined in #1650 (EXP-1/EXP-2), and brought <c>sort-paging</c> from 11
    /// to 12 with it: both blockages were the same one — <c>AgGridRequestParser</c> could not read
    /// <c>exportScope</c>, so no export request could be fed end to end.</para>
    /// </summary>
    private static readonly (string Category, int Expected)[] InScopeCategories =
    [
        ("operators", 62),
        ("date-presets", 26),
        ("community-infinite", 27),
        ("query-time-limit", 6),
        ("default-page-size", 5),
        ("dialect-parity", 19),
        ("group-aggregation", 25),
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
    /// <c>PostgresConformanceFixtureTests</c> gives, and deliberately so: nothing about them is
    /// backend-specific, so a divergence between the two lists would mean one of the suites had
    /// silently changed scope.
    /// </summary>
    private static readonly Dictionary<string, string> ExcludedCategories = new(StringComparer.Ordinal)
    {
        ["schemas"] = "Not a fixture category at all — the suite's own meta-schemas " +
                      "(mongo-artifact.schema.json and friends), validated by ajv-cli, not by this project.",
        ["adversarial"] = "Rejection-only fixtures: they carry expected/rejection.json, not a compiled artifact, " +
                          "and are already exercised by Craticula.Core.Tests' allowlist/limits/coercion suites. " +
                          "(They also carry no mongo.artifact.json, so discovery would skip them anyway — named " +
                          "here so the category list stays exhaustive.)"
    };

    /// <summary>
    /// EMPTY since #1650, exactly as in <c>PostgresConformanceFixtureTests</c>: its last entry was
    /// <c>sort-paging/012</c>, blocked upstream on <c>AgGridRequestParser</c>'s missing
    /// <c>exportScope</c>. Kept as a named, asserted-on collection rather than deleted — an empty
    /// exclusion list is the strongest form of "every fixture is either exercised or excluded for a
    /// stated reason".
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

    /// <summary>Every case directory in <paramref name="category"/> that carries a Mongo artifact and
    /// is not explicitly excluded, in ordinal name order.</summary>
    private static IReadOnlyList<string> DiscoverInScope(string category) =>
    [
        .. Directory.EnumerateDirectories(RepoPaths.Fixture(category))
            .Select(Path.GetFileName)
            .Where(name => name is not null)
            .Select(name => name!)
            .Where(name => File.Exists(RepoPaths.Fixture(category, name, "expected", "mongo.artifact.json")))
            .Where(name => !ExcludedFixtures.ContainsKey($"{category}/{name}"))
            .OrderBy(name => name, StringComparer.Ordinal)
    ];

    // ---- the conformance assertion ---------------------------------------------------------------

    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Compiles_To_The_Pipeline_Its_Own_Mongo_Artifact_Pins(string category, string fixtureDir)
    {
        var actual = MongoFixtureCompiler.Compile(category, fixtureDir);

        Assert.Equal(
            MongoFixtureCompiler.CanonicalJson(Read(category, fixtureDir, "expected", "mongo.artifact.json")),
            MongoFixtureCompiler.CanonicalJson(actual.ToArtifact()));
    }

    /// <summary>
    /// SEM-3's structural invariant, asserted independently of the artifact text: the null-bucket
    /// emulation is a CONTIGUOUS <c>$addFields</c> / <c>$sort</c> / <c>$unset</c> trio, and every
    /// bucket the first stage adds is named by the third.
    ///
    /// <para>Contiguity is the strongest form of SEM-3's "the <c>$unset</c> MUST appear after every
    /// <c>$sort</c> that used a bucket, before the pipeline's <c>$skip</c>/<c>$limit</c>/<c>$group</c>":
    /// nothing can slip between the three, so no stage that consumes documents ever sees the
    /// synthetic field. (It is stated that way rather than as "no <c>$group</c> before the
    /// <c>$unset</c>", because a grouped level's own <c>$group</c> legitimately runs BEFORE the trio —
    /// it is what produces the documents being sorted.)</para>
    ///
    /// <para>Worth its own test because it is the rule the hand-authored suite got wrong most often:
    /// a leaked bucket is a shape divergence from the Postgres/Search results for the identical IR,
    /// and the artifact comparison above would only catch it in the fixtures that happen to pin the
    /// stage. Here it is checked on all 176.</para>
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Emulates_Null_Placement_With_A_Contiguous_AddFields_Sort_Unset_Trio(string category, string fixtureDir)
    {
        var pipeline = MongoFixtureCompiler.Compile(category, fixtureDir).Pipeline;

        var start = pipeline.Select((stage, index) => (stage, index)).First(entry => entry.stage.ContainsKey("$addFields")).index;

        Assert.True(pipeline[start + 1].ContainsKey("$sort"), "SEM-3: the $sort follows the buckets it uses.");
        Assert.True(pipeline[start + 2].ContainsKey("$unset"), "SEM-3: the $unset follows the $sort immediately.");

        var added = pipeline[start]["$addFields"]!.AsObject().Select(entry => entry.Key).ToList();
        var unset = pipeline[start + 2]["$unset"]!;
        var removed = unset is JsonArray array
            ? array.Select(name => name!.GetValue<string>()).ToList()
            : [unset.GetValue<string>()];

        Assert.NotEmpty(added);
        Assert.Equal(added, removed);
        // #2809: SEM-6's exact tiebreaker on a repeated path sorts on a synthetic `<field>ExactKey` field added with the buckets.
        Assert.All(added, name => Assert.True(name.EndsWith("NullBucket", StringComparison.Ordinal) || name.EndsWith("ExactKey", StringComparison.Ordinal), name));

        // ...and there is exactly one trio, so no later $sort can reintroduce a bucket unnoticed.
        Assert.Single(pipeline, stage => stage.ContainsKey("$addFields"));
        Assert.Single(pipeline, stage => stage.ContainsKey("$unset"));
    }

    /// <summary>
    /// The artifact-shape rule <c>mongo-artifact.schema.json</c> states in prose: the
    /// <c>{ pipeline, collation }</c> wrapper appears if and only if a query-level collation is
    /// present, and the bare array otherwise. Asserted against the fixture on disk, so a compiler
    /// that emitted the right stages under the wrong wrapper still fails.
    /// </summary>
    [Theory]
    [MemberData(nameof(InScopeFixtures))]
    public void Uses_The_Wrapper_Object_Shape_Exactly_When_A_Collation_Or_A_Query_Time_Limit_Is_Present(
        string category, string fixtureDir)
    {
        var actual = MongoFixtureCompiler.Compile(category, fixtureDir);
        var expected = JsonNode.Parse(Read(category, fixtureDir, "expected", "mongo.artifact.json"));

        var wrapped = actual.Collation is not null || actual.MaxTimeMs is not null;
        Assert.Equal(wrapped, expected is JsonObject);
        Assert.Equal(wrapped, actual.ToArtifact() is JsonObject);
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
    public void The_End_To_End_Suite_Is_All_161_Mongo_Artifacts_In_The_Suite()
    {
        // #2522 added the most recent 2: group-aggregation/024-025 (GRP-7). Before that #2565 added 4: sort-paging/013-016. 167 with NOTHING subtracted, and it is the same number as the count of mongo.artifact.json
        // files on disk (asserted below): as of #1650 there is no excluded category carrying a Mongo
        // arm and no excluded fixture at all. It last moved when #1650's review pass authored
        // page-export/024; before that #1650 itself released page-export (13, now 14) and
        // sort-paging/012 from exclusion and authored page-export/023.
        Assert.Equal(222, InScopeFixtures.Count);
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
    public void Every_Mongo_Artifact_On_Disk_Is_Compiled_Or_Accounted_For()
    {
        // The count that closes the loop on "211 in scope": every mongo.artifact.json in the repo is
        // either exercised above, or inside a category/fixture this class excludes BY NAME. Since
        // #1650 nothing is excluded, so the two numbers are equal — the arithmetic is kept rather
        // than simplified away, because it is what would catch a future exclusion being added
        // without its artifacts being subtracted.
        var onDisk = Directory
            .EnumerateFiles(RepoPaths.Fixture(), "mongo.artifact.json", SearchOption.AllDirectories)
            .Count();

        var excludedCategoryArtifacts = ExcludedCategories.Keys
            .Where(category => Directory.Exists(RepoPaths.Fixture(category)))
            .Sum(category => Directory
                .EnumerateFiles(RepoPaths.Fixture(category), "mongo.artifact.json", SearchOption.AllDirectories)
                .Count());

        Assert.Equal(222, onDisk);
        Assert.Equal(0, excludedCategoryArtifacts);
        Assert.Equal(onDisk - excludedCategoryArtifacts - ExcludedFixtures.Count, InScopeFixtures.Count);
    }

    /// <summary>
    /// The inverse of the COVERAGE GAP this class recorded until #1650: SC-4's path mapping — the
    /// thing that turns <c>customerName</c> into <c>customer.name</c> and <c>id</c> into <c>_id</c> in
    /// every <c>$match</c> key, <c>$sort</c> key, <c>$group._id</c>, <c>$cond</c> reference and
    /// <c>$project</c> value — used to be exercised by unit tests alone, because the only schemas in
    /// the suite declaring a non-identity path belonged to <c>page-export/</c>, whose whole category
    /// was excluded for an unrelated reason (<c>exportScope</c>). Bringing that category in scope
    /// closed the gap, so the assertion is inverted rather than deleted: it now fails if the last
    /// remapping-fixture ever leaves the suite and the gap silently reopens.
    /// </summary>
    [Fact]
    public void Exercises_SC4_Path_Mapping_On_Fixtures_That_Really_Remap_A_Mongo_Path()
    {
        var remapped = new List<string>();

        foreach (var (category, _) in InScopeCategories)
        {
            foreach (var fixtureDir in DiscoverInScope(category))
            {
                var schema = GridSchema.Parse(Read(category, fixtureDir, "schema.json"));

                remapped.AddRange(schema.Fields
                    .Where(field => field.Value.Physical?.Mongo?.Path is { } path && path != field.Key)
                    .Select(field => $"{category}/{fixtureDir}:{field.Key}"));
            }
        }

        Assert.NotEmpty(remapped);
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

    private static string Read(string category, string fixtureDir, params string[] rest) =>
        MongoFixtureCompiler.Read(category, fixtureDir, rest);
}
