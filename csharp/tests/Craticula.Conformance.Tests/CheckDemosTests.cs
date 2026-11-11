namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_check_demos.py</c> (story #3323, task #3788) on every <c>dotnet test</c>: the live check of the two demos and the 15-minute watch, against a fake demo on 127.0.0.1, and the watch job's XML. Standard-library Python (and bash and curl where the script needs them), no network beyond 127.0.0.1.
/// </summary>
public class CheckDemosTests
{
    private const string PythonRequirement =
        "The demo checks need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_check_demos.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Demo_Live_Check_And_Watch_Pass_Their_Tests()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_check_demos.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_check_demos.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{result.Stderr}");
    }
}
