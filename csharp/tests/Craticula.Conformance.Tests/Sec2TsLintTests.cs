namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the SEC-2 lint of the TypeScript port (<c>scripts/lint-sec2-ts.py</c>, feature 014 US4) on every <c>dotnet test</c>:
/// its offline unit tests (<c>scripts/test_lint_sec2_ts.py</c>, synthetic TypeScript files that pin which values may reach
/// query text, the allowlist and the exit codes), and the lint itself over the TypeScript query builders, so a value
/// interpolated or concatenated into SQL text fails the build's tests, not a review.
/// </summary>
public class Sec2TsLintTests
{
    private const string PythonRequirement =
        "The SEC-2 lint tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/lint-sec2-ts.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Sec2_Ts_Lint_Script_Passes_Its_Synthetic_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_lint_sec2_ts.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_lint_sec2_ts.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }

    /// <summary>
    /// TRD SEC-2: no value other than a placeholder, a quoted identifier or a constant reaches query text in
    /// <c>typescript/src/sql</c>; the reviewed exceptions are <c>scripts/sec2-ts-allowlist.txt</c>, and an entry that no
    /// longer matches fails too.
    /// </summary>
    [Fact]
    public void Sec2_Ts_Lint_Passes_On_The_Query_Text_Builders()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/lint-sec2-ts.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/lint-sec2-ts.py exited {result.ExitCode} (0 = clean, 1 = a finding or a stale allowlist entry, " +
            $"2 = a scope, allowlist or parse error).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
