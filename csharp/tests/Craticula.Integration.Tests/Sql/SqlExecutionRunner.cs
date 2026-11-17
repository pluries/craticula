using System.Data.Common;
using System.Text;
using Craticula.Core.Schema;
using Craticula.Integration.Tests.Oracle;
using Craticula.Sql;
using Xunit;

namespace Craticula.Integration.Tests.Containers.Sql;

/// <summary>
/// XEQ-1..XEQ-4 for one fixture on one SQL engine: compile with the engine's dialect, create and seed the table, run
/// the compiled query through the engine's own driver, map the physical result onto the LOGICAL column list (XEQ-3)
/// and hand it to <see cref="RowComparer"/>. A difference fails with the fixture, the backend, the SQL sent and the
/// mismatch list; nothing here edits an expectation or loosens the comparer.
/// </summary>
internal static class SqlExecutionRunner
{
    /// <summary>The fixtures that carry an <c>expected/&lt;backend&gt;.artifact.json</c> (XEQ-1), as theory data.</summary>
    public static IEnumerable<object[]> FixturesFor(string backend) =>
        ExecutionFixture.All()
            .Where(name => File.Exists(RepoPaths.Fixture([.. name.Split('/'), "expected", $"{backend}.artifact.json"])))
            .Select(name => new object[] { name });

    /// <summary>The same fixtures as <see cref="FixturesFor"/>, typed so a theory's name parameter is checked at compile time.</summary>
    public static TheoryData<string> TypedFixturesFor(string backend)
    {
        var data = new TheoryData<string>();
        foreach (var name in FixturesFor(backend))
        {
            data.Add((string)name[0]);
        }

        return data;
    }

    /// <summary>
    /// SC-2 of story #3863 for one fixture on one engine: the count equals the number of rows the same request returns when
    /// nothing bounds the window (a grouped level counts its groups). A fixture the engine is expected to refuse (XEQ-4)
    /// or a distinct-values request has no count to compare.
    /// </summary>
    public static async Task AssertCountEqualsUnpagedRowsAsync(SqlEngine engine, string name)
    {
        var fixture = ExecutionFixture.Load(name);
        if (!SqlFixtureCompiler.IsRowFetch(fixture) || fixture.ExpectationFor(engine.Backend) is ExpectError)
        {
            return;
        }

        var unpaged = await engine.RunAsync(fixture, SqlFixtureCompiler.CompileUnpaged(fixture, engine.Dialect));
        var counted = await engine.RunAsync(fixture, SqlFixtureCompiler.CompileCount(fixture, engine.Dialect));

        var total = Convert.ToInt64(Assert.Single(counted.Rows)[0], System.Globalization.CultureInfo.InvariantCulture);
        Assert.True(
            total == unpaged.Rows.Count,
            $"{name} on {engine.Backend}: the count says {total} but the unpaged request returns {unpaged.Rows.Count} row(s).\n  count SQL: {counted.SentSql}\n  rows SQL: {unpaged.SentSql}");
    }

    public static async Task AssertMatchesOracleAsync(SqlEngine engine, string name)
    {
        var fixture = ExecutionFixture.Load(name);
        Assert.Contains(engine.Backend, fixture.Backends);

        var expectation = fixture.ExpectationFor(engine.Backend);
        var query = SqlFixtureCompiler.Compile(fixture, engine.Dialect);

        EngineResult result;
        try
        {
            result = await engine.RunAsync(fixture, query);
        }
        catch (DbException exception) when (expectation is ExpectError)
        {
            _ = exception; // XEQ-4 "error": the backend refuses the query, and it did.
            return;
        }
        catch (DbException exception)
        {
            Assert.Fail($"{name} on {engine.Backend}: the engine refused the compiled query: {exception.Message}\n{Describe(query)}");
            return;
        }

        if (expectation is ExpectError error)
        {
            Assert.Fail($"{name} on {engine.Backend}: XEQ-4 says the engine refuses this query ({error.Reason}) but it returned {result.Rows.Count} row(s). " +
                "Delete the allowedDivergence entry if the refusal is gone on purpose.");
            return;
        }

        var expected = ((ExpectRows)expectation).Result;
        var logical = ToLogical(fixture, result.Columns);
        var types = ColumnTypes.Resolve(fixture.Schema, fixture.Request, expected.Columns);

        IReadOnlyList<string> problems;
        try
        {
            problems = RowComparer.Compare(expected, types, logical, result.Rows, ColumnTypes.AverageColumns(fixture.Request, expected.Columns));
        }
        catch (Exception exception) when (exception is InvalidCastException or FormatException or InvalidOperationException)
        {
            problems = [$"the comparer could not read an engine value: {exception.Message}"];
        }

        if (problems.Count > 0)
        {
            var message = new StringBuilder()
                .Append(name).Append(" on ").Append(engine.Backend).Append(": ").Append(problems.Count).AppendLine(" mismatch(es) against expectedRows.json (XEQ-3)");
            foreach (var problem in problems.Take(12))
            {
                message.Append("  - ").AppendLine(problem);
            }

            message.AppendLine($"  engine columns: [{string.Join(", ", result.Columns)}] -> logical [{string.Join(", ", logical)}]")
                .AppendLine($"  engine rows: {result.Rows.Count}, expected rows: {expected.Rows.Count}")
                .AppendLine($"  SQL sent: {result.SentSql}")
                .Append("  parameters: ").Append(string.Join(", ", query.Parameters.Select(Show)));
            Assert.Fail(message.ToString());
        }
    }

    /// <summary>
    /// XEQ-3's physical-to-logical step. On a grouped level an aggregate's compiled output name (AGG-2: the alias when the
    /// column id differs from its field, else the default <c>&lt;field&gt;_&lt;func&gt;</c>) maps to the <c>valueCols</c>
    /// entry's own <c>id</c>, which is the name <c>expectedRows.json</c> and <see cref="ColumnTypes"/> use. Otherwise a
    /// result column named after a schema field is that field (an alias, GRP-3's group column, a leaf's projection), one
    /// named after a physical SQL column (<c>SELECT *</c>) is the field that owns it, and anything else stays as it is.
    /// </summary>
    private static IReadOnlyList<string> ToLogical(ExecutionFixture fixture, IReadOnlyList<string> physical)
    {
        var schema = fixture.Schema;
        var aggregates = AggregateOutputNames(fixture.Request);
        return physical.Select(name =>
            aggregates.TryGetValue(name, out var id)
                ? id
                : schema.Fields.ContainsKey(name)
                    ? name
                    : schema.FieldOrder.FirstOrDefault(field => string.Equals(SqlEngine.PhysicalColumn(schema, field), name, StringComparison.OrdinalIgnoreCase)) ?? name)
            .ToList();
    }

    private static Dictionary<string, string> AggregateOutputNames(System.Text.Json.JsonElement request)
    {
        var names = new Dictionary<string, string>(StringComparer.Ordinal);
        if (!Oracle.ColumnTypes.IsGrouped(request))
        {
            return names;
        }

        foreach (var value in request.GetProperty("valueCols").EnumerateArray())
        {
            var id = value.GetProperty("id").GetString()!;
            var field = value.GetProperty("field").GetString()!;
            names[id != field ? id : $"{field}_{value.GetProperty("aggFunc").GetString()}"] = id;
        }

        return names;
    }

    private static string Describe(SqlQuery query) =>
        $"SQL: {SqlMutation.Apply(query.Sql)}\nparameters: {string.Join(", ", query.Parameters.Select(Show))}";

    private static string Show(object? value) => value switch
    {
        null => "null",
        string text => $"'{text}'",
        IReadOnlyList<object?> list => $"[{string.Join(", ", list.Select(Show))}]",
        _ => Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture) ?? "?"
    };
}
