using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Craticula.Core.Schema;

namespace Craticula.Core.Tests.Schema;

/// <summary>
/// T-1b's structural guard (<c>spec/semantics.md</c> XEQ-1..XEQ-4): every fixture that carries
/// <c>dataset.json</c> / <c>expectedRows.json</c> must carry both, and each file must agree with the
/// fixture's OWN <c>schema.json</c> (and <c>agGridRequest.json</c>) in the ways its JSON Schema cannot
/// express because the field types live in other files -- every seed row names every declared field and
/// nothing else, the stableKey is unique and non-null (SEM-6's total order, XEQ-2), every column is a
/// schema field or an aggregate output name, and every cell is encoded the way XEQ-2 says its type is.
///
/// <para>Deliberately NOT an execution test: nothing here runs a query or compares a result. That is
/// the integration tier's job (#2206/#2207). This only keeps the oracle files honest about their own
/// shape, so a malformed seed fails here in milliseconds instead of as an unexplained mismatch on a
/// container.</para>
/// </summary>
public class ExecutionTierFixtureShapeTests
{
    private const long MaxSafeInteger = 9_007_199_254_740_992L; // 2^53, XEQ-2's int64 bound

    // [0-9] and \z, not \d and $: .NET's \d matches any Unicode digit and $ matches before a final newline.
    private static readonly Regex DecimalPattern = new(@"^[+-]?[0-9]+(\.[0-9]+)?\z", RegexOptions.CultureInvariant);

    private static readonly Regex DatePattern = new(@"^[0-9]{4}-[0-9]{2}-[0-9]{2}\z", RegexOptions.CultureInvariant);

    // XEQ-2: at most millisecond precision, the coarsest any backend keeps.
    private static readonly Regex DatetimePattern =
        new(@"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,3})?Z\z", RegexOptions.CultureInvariant);

    private static readonly HashSet<string> Backends =
        new(StringComparer.Ordinal) { "postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search" };

    /// <summary>Every fixture directory carrying at least one of the two T-1b files.</summary>
    public static IEnumerable<object[]> TierFixtures() =>
        Directory.EnumerateFiles(RepoPaths.Fixture(), "schema.json", SearchOption.AllDirectories)
            .Select(Path.GetDirectoryName)
            .OfType<string>()
            .Where(d => File.Exists(Path.Combine(d, "dataset.json")) || File.Exists(Path.Combine(d, "expectedRows.json")))
            .OrderBy(d => d, StringComparer.Ordinal)
            .Select(d => new object[] { Path.GetRelativePath(RepoPaths.Fixture(), d).Replace('\\', '/') });

    [Fact]
    public void At_Least_One_Fixture_Carries_The_Tier()
    {
        // A floor, not an exact count (#2204 authors the rest): guards against this theory silently
        // exercising nothing if the file names or the fixture root ever move.
        Assert.NotEmpty(TierFixtures());
    }

    /// <summary>Every fixture directory with at least one <c>expected/*.artifact.json</c>: its query returns rows (XEQ-1).
    /// Not <c>count-mode/</c> (CNT-1..CNT-8): those artifacts return one number, and their execution-tier proof is
    /// <c>SqlCountParityTests</c>, which runs the count against the unpaged rows of the source fixtures' own datasets.</summary>
    public static IEnumerable<object[]> ExecutableFixtures() =>
        Directory.EnumerateFiles(RepoPaths.Fixture(), "schema.json", SearchOption.AllDirectories)
            .Select(Path.GetDirectoryName)
            .OfType<string>()
            .Where(d => !Path.GetRelativePath(RepoPaths.Fixture(), d).Replace('\\', '/').StartsWith("count-mode/", StringComparison.Ordinal))
            .Where(d => Directory.Exists(Path.Combine(d, "expected"))
                && Directory.EnumerateFiles(Path.Combine(d, "expected"), "*.artifact.json").Any())
            .OrderBy(d => d, StringComparer.Ordinal)
            .Select(d => new object[] { Path.GetRelativePath(RepoPaths.Fixture(), d).Replace('\\', '/') });

    [Theory]
    [MemberData(nameof(ExecutableFixtures))]
    public void An_Executable_Fixture_Carries_The_Pair(string fixture)
    {
        // #2204's DoD: a fixture with a compiled artifact returns rows, so it must say which (XEQ-1).
        var dir = RepoPaths.Fixture(fixture.Split('/'));

        Assert.True(
            File.Exists(Path.Combine(dir, "dataset.json")) && File.Exists(Path.Combine(dir, "expectedRows.json")),
            $"{fixture} has an expected/*.artifact.json but lacks dataset.json or expectedRows.json (XEQ-1).");
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void A_Fixture_Carries_Both_Files_Or_Neither(string fixture)
    {
        var dir = RepoPaths.Fixture(fixture.Split('/'));

        Assert.True(File.Exists(Path.Combine(dir, "dataset.json")), $"{fixture} has expectedRows.json but no dataset.json (XEQ-1).");
        Assert.True(File.Exists(Path.Combine(dir, "expectedRows.json")), $"{fixture} has dataset.json but no expectedRows.json (XEQ-1).");
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void Every_Seed_Row_Names_Every_Schema_Field_And_Nothing_Else(string fixture)
    {
        var (schema, dataset, _) = Load(fixture);
        var declared = schema.Fields.Keys.ToHashSet(StringComparer.Ordinal);

        var rows = dataset.RootElement.GetProperty("rows");
        Assert.True(rows.GetArrayLength() > 0, $"{fixture}: a seed with no rows cannot discriminate (XEQ-1).");

        var index = 0;
        foreach (var entry in rows.EnumerateArray())
        {
            var present = entry.GetProperty("row").EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal);
            Assert.True(
                declared.SetEquals(present),
                $"{fixture} row {index}: keys [{string.Join(", ", present.Order())}] != schema fields [{string.Join(", ", declared.Order())}] (XEQ-2: every field, explicit null, nothing else).");
            index++;
        }
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void The_Seeds_StableKey_Is_Unique_And_Non_Null(string fixture)
    {
        // SEM-6's tiebreaker makes a result order total only over such a key; XEQ-3's "order is part of the
        // contract" depends on it.
        var (schema, dataset, _) = Load(fixture);

        var seen = new HashSet<string>(StringComparer.Ordinal);
        var index = 0;
        foreach (var entry in dataset.RootElement.GetProperty("rows").EnumerateArray())
        {
            var key = entry.GetProperty("row").GetProperty(schema.StableKey);
            Assert.True(key.ValueKind != JsonValueKind.Null, $"{fixture} row {index}: stableKey '{schema.StableKey}' is null (XEQ-2).");
            Assert.True(seen.Add(key.GetRawText()), $"{fixture} row {index}: stableKey '{schema.StableKey}' repeats {key.GetRawText()} (XEQ-2).");
            index++;
        }
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void Every_Seed_Cell_Is_Encoded_By_Its_Fields_Declared_Type(string fixture)
    {
        var (schema, dataset, _) = Load(fixture);

        var index = 0;
        foreach (var entry in dataset.RootElement.GetProperty("rows").EnumerateArray())
        {
            foreach (var cell in entry.GetProperty("row").EnumerateObject())
            {
                var problem = EncodingProblem(schema.Fields[cell.Name].Type, cell.Value);
                Assert.True(problem is null, $"{fixture} row {index}, field '{cell.Name}': {problem} (XEQ-2).");
            }

            index++;
        }
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void Expected_Rows_Are_Aligned_To_Their_Columns_And_Encoded_By_Type(string fixture)
    {
        var (schema, _, expected) = Load(fixture);
        var request = LoadRequest(fixture);

        AssertResultShape(fixture, "main result", schema, request, expected.RootElement);
    }

    [Theory]
    [MemberData(nameof(TierFixtures))]
    public void Allowed_Divergences_Are_Named_Justified_And_Unique(string fixture)
    {
        var (schema, _, expected) = Load(fixture);
        var request = LoadRequest(fixture);

        if (!expected.RootElement.TryGetProperty("allowedDivergence", out var divergences))
        {
            return;
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var entry in divergences.EnumerateArray())
        {
            var backend = entry.GetProperty("backend").GetString()!;
            Assert.Contains(backend, Backends);

            // XEQ-4: `engine` only qualifies the shared `search` artifact, and the engine-less form is not mixed
            // with the engine-qualified one.
            var engine = entry.TryGetProperty("engine", out var e) ? e.GetString() : null;
            if (engine is not null)
            {
                Assert.Equal("search", backend);
                Assert.Contains(engine, new[] { "opensearch", "elasticsearch" });
            }

            Assert.True(seen.Add($"{backend}/{engine}"), $"{fixture}: two allowedDivergence entries for '{backend}' engine '{engine}' (XEQ-4: one per backend, or per backend and engine).");
            if (backend == "search")
            {
                Assert.False(
                    seen.Contains("search/") && seen.Any(k => k.StartsWith("search/", StringComparison.Ordinal) && k != "search/"),
                    $"{fixture}: a 'search' divergence without an engine is mixed with an engine-qualified one (XEQ-4).");
            }

            Assert.False(
                string.IsNullOrWhiteSpace(entry.GetProperty("reason").GetString()),
                $"{fixture}: the '{backend}' divergence has no reason (XEQ-4).");

            var outcome = entry.GetProperty("outcome").GetString();
            var hasExpected = entry.TryGetProperty("expected", out var result);
            switch (outcome)
            {
                case "rows":
                    Assert.True(hasExpected, $"{fixture}: the '{backend}' divergence has outcome 'rows' but no expected result (XEQ-4).");
                    AssertResultShape(fixture, $"'{backend}' divergence", schema, request, result);
                    break;
                case "error":
                    Assert.False(hasExpected, $"{fixture}: the '{backend}' divergence has outcome 'error' and must not carry an expected result (XEQ-4).");
                    break;
                default:
                    Assert.Fail($"{fixture}: the '{backend}' divergence has outcome '{outcome}', not 'rows' or 'error' (XEQ-4).");
                    break;
            }
        }
    }

    private static void AssertResultShape(string fixture, string what, GridSchema schema, JsonElement request, JsonElement result)
    {
        var columns = result.GetProperty("columns").EnumerateArray().Select(c => c.GetString()!).ToList();
        Assert.NotEmpty(columns);
        Assert.Equal(columns.Count, columns.Distinct(StringComparer.Ordinal).Count());

        // XEQ-3: every column is a schema field or, on a grouped level, an aggregate output name -- never an
        // unchecked mystery. A misspelled column must fail here, not pass because it has no type to check.
        var types = columns.Select(c => ColumnType(fixture, what, schema, request, c)).ToList();

        var index = 0;
        foreach (var row in result.GetProperty("rows").EnumerateArray())
        {
            Assert.True(
                row.GetArrayLength() == columns.Count,
                $"{fixture} {what}, row {index}: {row.GetArrayLength()} cells for {columns.Count} columns (XEQ-3 alignment).");

            var position = 0;
            foreach (var cell in row.EnumerateArray())
            {
                var problem = EncodingProblem(types[position], cell);
                Assert.True(problem is null, $"{fixture} {what}, row {index}, column '{columns[position]}': {problem} (XEQ-2).");
                position++;
            }

            index++;
        }
    }

    /// <summary>
    /// The type XEQ-3 compares a result column by. On a grouped level (<c>rowGroupCols</c> outnumber
    /// <c>groupKeys</c>) a column named by a <c>valueCols</c> entry is typed by its aggregation: <c>count</c>
    /// is int64, <c>avg</c> is a double, anything else takes the aggregated field's type. Every other column
    /// must be a schema field.
    /// </summary>
    private static FieldType ColumnType(string fixture, string what, GridSchema schema, JsonElement request, string column)
    {
        // A BM-3 values query (setValuesRequest) has no rowGroupCols: its one column is the schema field named by colId.
        // An export discards group state (EXP-1(a)), so it is never a grouped level. Own copy of the rule in
        // Craticula.Integration.Tests' ColumnTypes.IsGrouped: a different assembly (XEQ-3).
        var exportFormat = request.TryGetProperty("exportFormat", out var format) && format.ValueKind != JsonValueKind.Null;
        var grouped = !exportFormat
            && request.TryGetProperty("rowGroupCols", out var groupCols)
            && groupCols.GetArrayLength() > request.GetProperty("groupKeys").GetArrayLength();
        if (grouped)
        {
            foreach (var value in request.GetProperty("valueCols").EnumerateArray())
            {
                if (value.GetProperty("id").GetString() != column)
                {
                    continue;
                }

                var function = value.GetProperty("aggFunc").GetString();
                if (function == "count")
                {
                    return FieldType.Int64;
                }

                if (function == "avg")
                {
                    return FieldType.Double;
                }

                var aggregated = value.GetProperty("field").GetString()!;
                Assert.True(schema.Fields.ContainsKey(aggregated), $"{fixture} {what}: aggregate '{column}' names unknown field '{aggregated}'.");
                return schema.Fields[aggregated].Type;
            }
        }

        Assert.True(
            schema.Fields.ContainsKey(column),
            $"{fixture} {what}: column '{column}' is neither a schema field nor an aggregate output name (XEQ-3).");
        return schema.Fields[column].Type;
    }

    /// <summary>Why <paramref name="cell"/> is not a legal XEQ-2 encoding of <paramref name="type"/>, or null when it is.</summary>
    private static string? EncodingProblem(FieldType type, JsonElement cell)
    {
        if (cell.ValueKind == JsonValueKind.Null)
        {
            return null; // an explicit null is legal for every type
        }

        return type switch
        {
            FieldType.Int64 when cell.ValueKind == JsonValueKind.Number =>
                cell.TryGetInt64(out var n) && Math.Abs(n) <= MaxSafeInteger ? null : $"{cell.GetRawText()} is not an integer within +/-2^53",
            FieldType.Double when cell.ValueKind == JsonValueKind.Number => null,
            FieldType.Decimal when cell.ValueKind == JsonValueKind.String =>
                DecimalPattern.IsMatch(cell.GetString()!) ? null : $"{cell.GetRawText()} is not a plain decimal string (no grouping, no trailing sign)",
            FieldType.Boolean when cell.ValueKind is JsonValueKind.True or JsonValueKind.False => null,
            FieldType.String when cell.ValueKind == JsonValueKind.String => null,
            FieldType.Date when cell.ValueKind == JsonValueKind.String =>
                DatePattern.IsMatch(cell.GetString()!) && DateOnly.TryParseExact(cell.GetString(), "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _)
                    ? null : $"{cell.GetRawText()} is not a real calendar date YYYY-MM-DD",
            FieldType.Datetime when cell.ValueKind == JsonValueKind.String =>
                DatetimePattern.IsMatch(cell.GetString()!) && DateTime.TryParse(cell.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out _)
                    ? null : $"{cell.GetRawText()} is not a real UTC instant with at most millisecond precision ending in Z",
            _ => $"a {cell.ValueKind} is not a legal {type} cell",
        };
    }

    private static JsonElement LoadRequest(string fixture) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(RepoPaths.Fixture(fixture.Split('/')), "agGridRequest.json"))).RootElement;

    private static (GridSchema Schema, JsonDocument Dataset, JsonDocument Expected) Load(string fixture)
    {
        var dir = RepoPaths.Fixture(fixture.Split('/'));
        var schema = GridSchema.Parse(File.ReadAllText(Path.Combine(dir, "schema.json")));
        var dataset = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "dataset.json")));
        var expected = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "expectedRows.json")));
        return (schema, dataset, expected);
    }
}
