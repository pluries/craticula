namespace Craticula.Conformance.Tests;

/// <summary>
/// Runs the three Python test files of the site languages (spec 004-site-languages, task T021) on every <c>dotnet test</c>: the checks and
/// approvals (<c>scripts/test_site_i18n.py</c>), the committed translation tree (<c>scripts/test_site_i18n_content.py</c>) and the language
/// build (<c>scripts/test_site_languages.py</c>). One call per file: the 120 s limit of <see cref="RunnerHost.SuiteTimeout"/> applies to each.
/// Standard-library Python only, no network.
/// </summary>
public class SiteLanguageTests
{
    private const string PythonRequirement =
        "The site language tests need Python 3.10+ on PATH as 'python3' or 'python' (scripts/test_site_*.py). " +
        "It is a hard requirement, not a skip: install Python 3.10+ and re-run.";

    [Fact]
    public void Site_Language_Checks_And_Approvals_Pass_Their_Tests() => AssertPasses("scripts/test_site_i18n.py");

    [Fact]
    public void Site_Translation_Tree_Passes_Its_Tests() => AssertPasses("scripts/test_site_i18n_content.py");

    [Fact]
    public void Site_Language_Build_Passes_Its_Tests() => AssertPasses("scripts/test_site_languages.py");

    private static void AssertPasses(string script)
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
            RunnerHost.SuiteTimeout);

        Assert.True(
            result.ExitCode == 0,
            $"{script} exited {result.ExitCode} (0 = every case passed).{Environment.NewLine}" +
            $"--- stdout ---{Environment.NewLine}{result.Stdout}{Environment.NewLine}" +
            $"--- stderr ---{Environment.NewLine}{result.Stderr}");
    }
}
