namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_perf_load.py</c> (story #3324, task #3847) on every <c>dotnet test</c>: the load test of a demo API against a fake demo on 127.0.0.1. Standard-library Python, no network beyond 127.0.0.1.
/// </summary>
// Traceability: FR-18, FR-19, AC-2, AC-3
public class PerfLoadTests
{
    private const string PythonRequirement =
        "The load test needs Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_perf_load.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Load_Test_Script_Passes_Its_Tests()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_perf_load.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(120));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_perf_load.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{result.Stderr}");
    }
}
