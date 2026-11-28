namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_spec_freeze.py</c> on every <c>dotnet test</c>: the spec-freeze check
/// (<c>scripts/check-spec-freeze.py</c>, feature 008) on synthetic trees. No network.
/// </summary>
public class SpecFreezeTests
{
    private const string PythonRequirement =
        "The spec freeze tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/check-spec-freeze.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Spec_Freeze_Script_Passes_Its_Synthetic_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_spec_freeze.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_spec_freeze.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
