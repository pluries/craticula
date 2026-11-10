namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the offline Python tests of the release chain on every <c>dotnet test</c> (task #3482, stories #3320 and #3706): the signing
/// probe, the verification of the signed packages, the check of the staged packages before the workflow pushes them and the
/// maintainer identity of the public pages. The tests of the private release steps script are in ReleaseStepsTests, which the public
/// mirror does not carry. Each file fails the build when one of its cases fails. Standard-library Python only, no network; the tests
/// that need <c>dotnet</c> run on the build agents, which have it.
/// </summary>
public class ReleaseScriptsTests
{
    private const string PythonRequirement =
        "The release script tests need Python 3.10+ on PATH as 'python3' or 'python'. " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    public static TheoryData<string> Scripts => new()
    {
        "scripts/test_signing_probe.py",
        "scripts/test_release_verify.py",
        "scripts/test_check_staged_packages.py",
        "scripts/test_maintainer_identity.py",
    };

    [Theory]
    [MemberData(nameof(Scripts))]
    public void Release_Script_Passes_Its_Tests(string script)
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            [script],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(300));

        Assert.True(
            result.ExitCode == 0,
            $"{script} exited {result.ExitCode} (0 = every case passed or skipped).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
