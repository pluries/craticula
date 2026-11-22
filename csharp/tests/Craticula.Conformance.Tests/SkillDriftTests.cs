namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_skill_drift.py</c> on every <c>dotnet test</c>: the public skill, its page and the plugin
/// text agree with their sources (FR-016, FR-040). No network.
/// </summary>
public class SkillDriftTests
{
    private const string PythonRequirement =
        "The skill drift tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_skill_drift.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Skill_Drift_Script_Passes()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_skill_drift.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_skill_drift.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
