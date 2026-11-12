namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the SEC-2 lint (<c>scripts/lint-sec2.py</c>, story #1660 AC-4) on every <c>dotnet test</c>: its offline
/// unit tests (<c>scripts/test_lint_sec2.py</c>, synthetic C# files that pin which values may reach query text, the
/// allowlist and the exit codes), and the lint itself over the five query-text builders, so a user value
/// interpolated or concatenated into SQL, a Mongo pipeline or a search body fails the build's tests, not a review.
/// </summary>
public class Sec2LintTests
{
    private const string PythonRequirement =
        "The SEC-2 lint tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/lint-sec2.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Sec2_Lint_Script_Passes_Its_Synthetic_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_lint_sec2.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_lint_sec2.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }

    /// <summary>
    /// TRD SEC-2: no value other than a placeholder, a quoted identifier, a constant or an enum reaches query text in
    /// <c>Craticula.Sql</c>, <c>.Mongo</c>, <c>.Search</c>, <c>.Dapper</c> or <c>.EntityFrameworkCore</c>; the
    /// reviewed exceptions are <c>scripts/sec2-allowlist.txt</c>, and an entry that no longer matches fails too.
    /// </summary>
    [Fact]
    public void Sec2_Lint_Passes_On_The_Query_Text_Builders()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/lint-sec2.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/lint-sec2.py exited {result.ExitCode} (0 = clean, 1 = a finding or a stale allowlist entry, " +
            $"2 = a scope, allowlist or parse error).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
