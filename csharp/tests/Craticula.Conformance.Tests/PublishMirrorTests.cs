namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the offline unit tests of the public mirror (<c>scripts/test_publish_mirror.py</c>, story #1659 AC-1 and AC-4) on
/// every <c>dotnet test</c>: the commit-subject mapping table and,
/// on scratch repositories and a scratch bare remote, the published-boundary check, the sync-back round trip that
/// ends in a fast-forward push, and the refusal of an unrecorded public change. The script tests skip themselves where the
/// private scripts, git-filter-repo or node are absent (the public mirror), the pure tests never do. The real
/// <c>github</c> remote is never contacted. A second test runs the private-only check of the real history
/// (<c>scripts/test_publish_mirror_real.py</c>) when that file is present, and does nothing where it is not.
/// </summary>
public class PublishMirrorTests
{
    private const string PythonRequirement =
        "The mirror tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_publish_mirror.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Publish_Mirror_Script_Passes_Its_Scratch_Repository_Cases()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_publish_mirror.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_publish_mirror.py exited {result.ExitCode} (0 = every case passed or skipped).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }

    [Fact]
    public void Publish_Mirror_Real_History_Check_Passes_Where_The_Private_File_Exists()
    {
        var script = Path.Combine(RepoPaths.Root, "scripts", "test_publish_mirror_real.py");
        if (!File.Exists(script))
        {
            return; // the public mirror does not carry it
        }

        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_publish_mirror_real.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_publish_mirror_real.py exited {result.ExitCode} (0 = passed or skipped).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
