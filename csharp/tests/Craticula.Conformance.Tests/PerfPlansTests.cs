namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_perf_plans.py</c> (story #3856, task #3859) on every <c>dotnet test</c>: the helpers of the query-plan script (statements, literals, plan summaries). Standard-library Python, no docker and no network.
/// </summary>
// Traceability: AC-3 of story #3856
public class PerfPlansTests
{
    private const string PythonRequirement =
        "The query plan script needs Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_perf_plans.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Query_Plan_Script_Helpers_Pass_Their_Tests()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_perf_plans.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(120));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_perf_plans.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{result.Stderr}");
    }
}
