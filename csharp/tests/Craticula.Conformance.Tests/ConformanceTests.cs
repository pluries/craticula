using System.Text.Json;

namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the language-neutral conformance runner (<c>conformance/run.py</c>, spec/conformance-runner.md)
/// against the C# driver on every <c>dotnet test</c>, so a compiler change that moves any expected
/// artifact fails here (story #1654 AC-5), and pins the driver's two failure paths that the
/// graded cases never reach (§2.1, §2.2, §2.3, §8; the exit 1 for an unanswerable line is the driver's
/// own design, whose spec consequence is §2.4 item 5).
/// </summary>
public class ConformanceTests
{
    private const string PythonRequirement =
        "The conformance suite needs Python 3.10+ on PATH as 'python3' or 'python' (spec/conformance-runner.md §9). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    /// <summary>
    /// T-1(a), spec §7: the runner starts the C# driver once, streams every fixture case and exits 0
    /// only when every graded artifact is equal. On failure the runner's whole report is the message.
    ///
    /// <para>Exit 0 alone is not the claim: a driver that stops declaring a backend leaves its cases
    /// "not graded" and still exits 0 (§6). Conformance is the run over the whole tree (§9), so the
    /// JSON report must show all seven backends declared, none left not graded, each with passes.</para>
    /// </summary>
    [Fact]
    public void Runner_Grades_Every_Fixture_Artifact_Equal_For_The_CSharp_Driver()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var reportPath = Path.Combine(Path.GetTempPath(), $"craticula-conformance-{Guid.NewGuid():N}.json");
        try
        {
            var result = RunnerHost.RunSuite(python, "--json", reportPath);
            var output =
                $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
                $"--- stderr ---{Environment.NewLine}{result.Stderr}";

            Assert.True(
                result.ExitCode == 0,
                $"conformance/run.py exited {result.ExitCode} (0 = every graded artifact equal, 1 = a FAIL, 2 = protocol failure).{Environment.NewLine}{output}");

            using var report = JsonDocument.Parse(File.ReadAllText(reportPath));
            var declared = report.RootElement.GetProperty("hello").GetProperty("backends")
                .EnumerateArray().Select(b => b.GetString()).Order(StringComparer.Ordinal).ToArray();
            Assert.True(
                declared.SequenceEqual(AllBackends.Order(StringComparer.Ordinal)),
                $"the driver must declare all seven backends, it declared: {string.Join(", ", declared)}.{Environment.NewLine}{output}");

            foreach (var backend in AllBackends)
            {
                var totals = report.RootElement.GetProperty("totals").GetProperty(backend);
                Assert.True(
                    totals.GetProperty("notGraded").GetInt32() == 0 && totals.GetProperty("passed").GetInt32() > 0,
                    $"backend '{backend}' must be fully graded (passed > 0, notGraded = 0): {totals.GetRawText()}{Environment.NewLine}{output}");
            }
        }
        finally
        {
            File.Delete(reportPath);
        }
    }

    /// <summary>
    /// Feature 009 (US1-AS5, US2-AS5, FR-007): the driver declares the <c>rejection</c> and <c>writer</c>
    /// capabilities, and the runner grades every rejection fixture and every writer fixture of the tree
    /// as passed, none left not graded. Feature 009 US3-AS4 and US3-AS5: nothing failed, and every graded case of every
    /// kind passed (the whole tree is graded, execution equality aside).
    /// </summary>
    [Fact]
    public void Runner_Grades_Every_Rejection_And_Writer_Fixture_For_The_CSharp_Driver()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var fixtures = Path.Combine(RepoPaths.Root, "spec", "fixtures");
        var rejections = Directory.EnumerateFiles(fixtures, "rejection.json", SearchOption.AllDirectories).Count();
        var writers = Directory.EnumerateFiles(fixtures, "rowStream.json", SearchOption.AllDirectories).Count();
        Assert.True(rejections > 30 && writers >= 12, $"the tree should carry rejection and writer fixtures ({rejections}, {writers})");

        var reportPath = Path.Combine(Path.GetTempPath(), $"craticula-conformance-{Guid.NewGuid():N}.json");
        try
        {
            var result = RunnerHost.RunSuite(python, "--json", reportPath);
            var output = $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}--- stderr ---{Environment.NewLine}{result.Stderr}";
            Assert.True(result.ExitCode == 0, $"conformance/run.py exited {result.ExitCode}.{Environment.NewLine}{output}");

            using var report = JsonDocument.Parse(File.ReadAllText(reportPath));
            var capabilities = report.RootElement.GetProperty("hello").GetProperty("capabilities")
                .EnumerateArray().Select(c => c.GetString()!).Order(StringComparer.Ordinal).ToArray();
            Assert.Equal(["rejection", "writer"], capabilities);

            foreach (var (kind, count) in new[] { ("rejection", rejections), ("writer", writers) })
            {
                var totals = report.RootElement.GetProperty("totals").GetProperty(kind);
                Assert.True(
                    totals.GetProperty("passed").GetInt32() == count
                    && totals.GetProperty("failed").GetInt32() == 0
                    && totals.GetProperty("notGraded").GetInt32() == 0,
                    $"'{kind}' must pass all {count} fixtures: {totals.GetRawText()}{Environment.NewLine}{output}");
            }

            var passed = report.RootElement.GetProperty("totals").EnumerateObject().Sum(t => t.Value.GetProperty("passed").GetInt32());
            var artifacts = Directory.EnumerateFiles(fixtures, "*.artifact.json", SearchOption.AllDirectories).Count();
            Assert.Equal(artifacts + rejections + writers, passed);
            Assert.Empty(report.RootElement.GetProperty("failures").EnumerateArray());

            Assert.DoesNotContain(
                report.RootElement.GetProperty("outOfTier").EnumerateArray(),
                o => !o.GetProperty("reason").GetString()!.StartsWith("execution equality", StringComparison.Ordinal));
        }
        finally
        {
            File.Delete(reportPath);
        }
    }

    private static readonly string[] AllBackends = ["postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search"];

    /// <summary>
    /// Spec §2.1, §2.2, §2.3, §8: the hello comes first; a request naming a backend outside the closed
    /// set still gets exactly one answer, an <c>error</c> object with the id echoed and a <c>kind</c>
    /// and <c>message</c>; the driver then exits 0 on EOF.
    /// </summary>
    [Fact]
    public void Driver_Answers_An_Unknown_Backend_With_An_Error_Object()
    {
        var result = RunnerHost.RunDriver(
            ["""{"id":"x#db2","backend":"db2","schema":{},"agGridRequest":{}}"""]);

        Assert.Equal(0, result.ExitCode);
        var lines = result.Stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        Assert.Equal(2, lines.Length);

        using var hello = JsonDocument.Parse(lines[0]);
        Assert.True(hello.RootElement.TryGetProperty("hello", out _), "first stdout line must be the hello");

        using var answer = JsonDocument.Parse(lines[1]);
        var root = answer.RootElement;
        Assert.Equal("x#db2", root.GetProperty("id").GetString());
        Assert.False(root.TryGetProperty("artifact", out _), "an error answer carries no artifact");
        var error = root.GetProperty("error");
        Assert.False(string.IsNullOrWhiteSpace(error.GetProperty("kind").GetString()));
        Assert.False(string.IsNullOrWhiteSpace(error.GetProperty("message").GetString()));
    }

    /// <summary>
    /// A line whose <c>id</c> cannot be read cannot be answered in order, so the driver stops with
    /// exit 1 and the reason on stderr; stdout holds only the hello. The exit 1 is the driver's own
    /// design; the spec's consequence for a runner is §2.4 item 5 (a non-zero exit is a protocol
    /// failure), and §2 sends logs to stderr.
    /// </summary>
    [Fact]
    public void Driver_Exits_1_With_A_Reason_On_Stderr_For_A_Line_Without_A_Readable_Id()
    {
        var result = RunnerHost.RunDriver(["[1,2]"]);

        Assert.Equal(1, result.ExitCode);
        Assert.False(string.IsNullOrWhiteSpace(result.Stderr), "the reason must be on stderr");
        var lines = result.Stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var only = Assert.Single(lines);
        using var hello = JsonDocument.Parse(only);
        Assert.True(hello.RootElement.TryGetProperty("hello", out _));
    }
}
