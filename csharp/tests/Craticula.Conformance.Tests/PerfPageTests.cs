namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_perf_page.py</c> (story #3324, task #3849) on every <c>dotnet test</c>: the generator of the performance page and the compile manifest writer, on fake result files in a temporary folder. Standard-library Python, no network.
/// </summary>
// Traceability: FR-19, FR-20, NFR-08, AC-3, AC-4, AC-5, AC-6
public class PerfPageTests
{
    private const string PythonRequirement =
        "The performance page generator needs Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_perf_page.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Performance_Page_Generator_Passes_Its_Tests()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_perf_page.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(120));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_perf_page.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{result.Stderr}");
    }
}
