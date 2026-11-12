namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs <c>scripts/test_workflows.py</c> (story #2467, NFR-02) on every <c>dotnet test</c>: every GitHub workflow pins each
/// <c>uses:</c> to a full commit SHA and declares top-level <c>permissions</c>, and the public CI (<c>ci.yml</c>) names the
/// jobs <c>build</c> and <c>test</c> and references no secret. Line checks only, no network and no GitHub.
/// </summary>
public class WorkflowLintTests
{
    private const string PythonRequirement =
        "The workflow lint tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_workflows.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Workflow_Lint_Script_Passes()
    {
        var python = RunnerHost.Python;
        if (python is null)
        {
            Assert.Fail(PythonRequirement);
        }

        var result = RunnerHost.Run(
            python,
            ["scripts/test_workflows.py"],
            RepoPaths.Root,
            stdinLines: null,
            TimeSpan.FromSeconds(180));

        Assert.True(
            result.ExitCode == 0,
            $"scripts/test_workflows.py exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
