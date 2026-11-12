namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the offline unit tests of the coverage gate (<c>scripts/test_coverage.py</c>: synthetic cobertura
/// files through <c>scripts/coverage.py</c>, story #1657) on every <c>dotnet test</c>, so the gate's
/// per-file merge, its exact threshold comparison and its exit codes cannot change unnoticed.
/// </summary>
public class CoverageGateTests
{
    private const string PythonRequirement =
        "The coverage gate tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/coverage.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Coverage_Gate_Script_Passes_Its_Synthetic_Cobertura_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_coverage.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_coverage.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
