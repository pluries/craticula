namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_check_community_oracle.py</c> (story #2454, AC-1/AC-4) on every <c>dotnet test</c>: every case of
/// <c>spec/fixtures/community-infinite</c> equals the existing fixture it maps to in <c>oracle.json</c>, is labelled
/// <c>derived</c> or <c>captured</c>, and the check itself fails on a changed or missing artifact or a different request.
/// </summary>
public class CommunityOracleTests
{
    private const string PythonRequirement =
        "The Community oracle tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_check_community_oracle.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Community_Oracle_Script_Passes_Its_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_check_community_oracle.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_check_community_oracle.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
