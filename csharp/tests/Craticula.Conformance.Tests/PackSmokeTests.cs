namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the offline unit tests of the pack smoke (<c>scripts/test_pack_smoke.py</c>, story #1658 AC-2) on every
/// <c>dotnet test</c>: synthetic nupkgs (a missing README, a missing or wrong adapter range, a third-party dependency
/// on a compile-only package, a wrong license or version, a DLL without an embedded PDB or SourceLink) that must fail,
/// and a good set that must pass. The real smoke (<c>scripts/pack-smoke.sh</c>) packs the ten projects and restores
/// clean consumers, which takes minutes and needs nuget.org, so it runs in the release workflow (the Azure PR gate that also ran it was retired in #2982), not here.
/// </summary>
public class PackSmokeTests
{
    private const string PythonRequirement =
        "The pack smoke tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_pack_smoke.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Pack_Smoke_Script_Passes_Its_Synthetic_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_pack_smoke.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_pack_smoke.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
