namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_typescript_skeleton.py</c> on every <c>dotnet test</c>: the TypeScript skeleton's package, compiler
/// settings, lock file, Dependabot entry and README (feature 012). The decision-record checks skip on the public mirror. No network.
/// </summary>
public class TypescriptSkeletonTests
{
    private const string PythonRequirement =
        "The TypeScript skeleton tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_typescript_skeleton.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Typescript_Skeleton_Repository_Facts_Pass_Their_Checks()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_typescript_skeleton.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_typescript_skeleton.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
