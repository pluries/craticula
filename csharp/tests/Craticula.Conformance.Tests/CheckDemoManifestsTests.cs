namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_check_demo_manifests.py</c> (story #3323, task #3787) on every <c>dotnet test</c>: the manifest check of the demo Kubernetes drafts: names, labels, network policies, container hardening, no literal secret, ingress TLS and HSTS. Standard-library Python (and bash and curl where the script needs them), no network beyond 127.0.0.1.
/// </summary>
public class CheckDemoManifestsTests
{
    private const string PythonRequirement =
        "The demo checks need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_check_demo_manifests.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Demo_Manifest_Check_Passes_Its_Tests()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_check_demo_manifests.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(120));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_check_demo_manifests.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{result.Stderr}");
    }
}
