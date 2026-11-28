namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_dotnet11_decision.py</c> on every <c>dotnet test</c>: the ADR, the SDK 11 run record and the
/// consequences table of feature 010 (they skip on the public mirror, where <c>docs/</c> is stripped). No network.
/// </summary>
public class Dotnet11DecisionTests
{
    private const string PythonRequirement =
        "The .NET 11 decision tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_dotnet11_decision.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Dotnet11_Decision_Records_Pass_Their_Checks()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_dotnet11_decision.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_dotnet11_decision.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
