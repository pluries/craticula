namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_spec_version.py</c> on every <c>dotnet test</c>: <c>spec/VERSION</c> equals the
/// conformance driver's <c>SpecVersion</c> and the claim line in every <c>csharp/src</c> package README. No network.
/// </summary>
public class SpecVersionTests
{
    private const string PythonRequirement =
        "The spec version tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_spec_version.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Spec_Version_Script_Passes()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_spec_version.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_spec_version.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
