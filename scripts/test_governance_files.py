#!/usr/bin/env python3
"""Pins the governance files of the public repository (story #1662): CODEOWNERS (FR-03, AC-3), SECURITY.md (FR-04, AC-5, SC-02),
the DCO workflow's presence (FR-02), the rule that these public files name no private path (NFR-01), and, where the private
documents exist, that the gate list of the repository's flow rule and its two copies agree and name the governance files.
Line checks only, stdlib only, no network. The private documents (`.claude/`, `docs/`) are absent from the public mirror: the
gate-list tests then skip. Run: python3 scripts/test_governance_files.py
(also run by Craticula.Conformance.Tests/GovernanceFilesTests.cs on every `dotnet test`).
"""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
SECURITY = ROOT / "SECURITY.md"
# The private paths of scripts/publish-github.sh (its PRIVATE array), spelled so that a prose mention is not a false positive
# (`docs/`, not `docs`). A test pins this tuple to the real array where the publish script exists (the private repository).
PRIVATE_PREFIXES = ("docs/", ".claude", "CLAUDE.md", ".mcp.json", ".githooks", ".azuredevops", ".sonarlint", ".vscode",
                    "scripts/publish-github.sh", "scripts/sync-release-commit.sh", "scripts/apply-public-change.sh",
                    "scripts/test_apply_public_change.py", "scripts/test_publish_mirror_real.py", "scripts/test_jenkinsfile.py",
                    "scripts/test_release_steps.py", "scripts/test_release_steps_publish.py", "scripts/test_release_steps_notes.py", "scripts/release-steps-fixtures/",
                    "csharp/tests/Craticula.Conformance.Tests/JenkinsfileTests.cs", "csharp/tests/Craticula.Conformance.Tests/ReleaseStepsTests.cs", "Jenkinsfile", "jenkins/")
# `docs/adr` is the one public folder under a private path (the PUBLIC_EXCEPT array of scripts/publish-github.sh, #1665, ADR 0004).
PUBLIC_EXCEPTIONS = ("docs/adr",)
PRIVATE_HOSTS = re.compile(r"dev\.azure\.com|visualstudio\.com", re.IGNORECASE)
PUBLISH_SCRIPT = ROOT / "scripts" / "publish-github.sh"
OWNER = re.compile(r"^(?:@[A-Za-z0-9][A-Za-z0-9-]*(?:/[A-Za-z0-9._-]+)?|[^@\s]+@[^@\s]+\.[A-Za-z]+)$")
GATE_COPIES = (".claude/rules/git-branch-naming.md", "docs/compliance/isms-change-pr-pipeline.md", "docs/compliance/pipelines-craticula.md")
# What the governance stories add to the gate: a pull request touching these validates its own copy of the checks or changes
# what the publish accepts, so the agent never completes it (the maker does).
GATE_GOVERNANCE = (".github/CODEOWNERS", "Jenkinsfile", "jenkins/", "scripts/check-dco*", "scripts/test_check_dco*", "scripts/apply-public-change*",
                   "scripts/test_apply_public_change*", "scripts/test_governance_files*", "scripts/test_jenkinsfile*", ".githooks/", "docs/adr/", ".github/workflows/",
                   # an ADR is what lets an MPL-2.0 package pass the license gate (FR-09), so editing one changes the gate
                   # what makes the lints run: the workflow and security-script tests, and the wrappers that run them in `dotnet test`
                   "scripts/test_workflows*", "scripts/test_lint_sec2*", "scripts/test_coverage*", "csharp/tests/Craticula.Conformance.Tests/",
                   # the license gate (ADR-0003, #1664): its script, policy, reviewed exceptions, fixtures and the tool pin
                   "scripts/check-licenses*", "scripts/test_check_licenses*", "scripts/license-overrides.json",
                   "scripts/license-allowlist.json", "scripts/license-fixtures/", "csharp/.config/dotnet-tools.json")


def codeowners_rules(text: str) -> list[tuple[str, list[str]]]:
    """(pattern, owners) per rule line; comments and blank lines are skipped."""
    rules = []
    for line in text.splitlines():
        line = re.split(r"\s#", line.strip(), maxsplit=1)[0].strip()   # an inline comment ends the rule
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        rules.append((parts[0], parts[1:]))
    return rules


def codeowners_problems(text: str, root: Path) -> list[str]:
    """What is wrong with a CODEOWNERS file: a rule without an owner, an owner that is not `@user`, `@org/team` or an e-mail,
    a pattern that matches nothing in the tree, a catch-all that is not the first rule (the last matching pattern wins, so a
    catch-all placed later would override every specific rule), a missing `csharp/src/` rule."""
    problems = []
    rules = codeowners_rules(text)
    if not rules:
        return ["no rule"]
    if rules[0][0] != "*":
        problems.append("the catch-all `*` must be the first rule (the last matching pattern wins)")
    for index, (pattern, _) in enumerate(rules):
        if index > 0 and pattern in ("*", "**", "/**"):
            problems.append(f"{pattern}: a catch-all after the first rule overrides every specific rule above it (the last matching pattern wins)")
    if not any(pattern.strip("/") == "csharp/src" for pattern, _ in rules):
        problems.append("no rule for /csharp/src/")
    for pattern, owners in rules:
        if not owners:
            problems.append(f"{pattern}: no owner")
        for owner in owners:
            if not OWNER.match(owner):
                problems.append(f"{pattern}: '{owner}' is not an @user, @org/team or e-mail owner")
        if pattern != "*":
            target = pattern.lstrip("/").rstrip("/")
            if ".." in Path(target).parts:
                problems.append(f"{pattern}: leaves the repository")
                continue
            globbed = any(c in target for c in "*?[")
            if "/" not in pattern.strip("/") and not pattern.startswith("/"):
                exists = any(root.rglob(target))      # an unanchored pattern matches at any depth
            elif globbed:
                exists = any(root.glob(target))
            else:
                exists = (root / target).exists()
            if not exists:
                problems.append(f"{pattern}: matches nothing in the tree")
    return problems


LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.MULTILINE)


def security_problems(text: str, root: Path) -> list[str]:
    """What is wrong with SECURITY.md: no private-report path (the **Security** tab and **Report a vulnerability**, both in bold as
    the steps), fewer than two response times in days, no supported-versions table with a supported row, an e-mail address, a
    private host anywhere, a link (inline, with a title, or a reference definition) that does not resolve inside the repository
    or points at a private path."""
    problems = []
    if "**Security** tab" not in text or "**Report a vulnerability**" not in text:
        problems.append("no private-report path (the **Security** tab, **Report a vulnerability**)")
    if len(re.findall(r"within \*\*\d+ (?:calendar )?days\*\*", text)) < 2:
        problems.append("fewer than two response times in days (acknowledgement and first assessment)")
    if not supported_row(text):
        problems.append("no supported-versions table with a supported row")
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        problems.append("an e-mail address (the policy names the Security tab only)")
    if PRIVATE_HOSTS.search(text):
        problems.append("a private host (dev.azure.com, visualstudio.com)")
    for match in LINK.finditer(text):
        target = match.group(1) or match.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):
            continue
        path = target.split("#")[0].lstrip("/")      # a root-relative link is read against the repository root
        if path.startswith(PRIVATE_PREFIXES):
            problems.append(f"link into a private path: {target}")
        elif path and not (root / path).exists():
            problems.append(f"link that does not resolve: {target}")
    return problems


def supported_row(text: str) -> bool:
    """True when a `| Version | Supported |` table has a row whose second cell starts with Yes."""
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if re.match(r"^\|\s*Version\s*\|\s*Supported\s*\|", line):
            for row in lines[number + 1:]:
                if not row.startswith("|"):
                    break
                cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[1].lower().startswith("yes"):
                    return True
    return False


def _private_match_at(line: str, start: int) -> bool:
    """True when the private prefix found at `start` is a reference to the private root path (not a public exception such as `docs/adr`,
    not a nested directory that merely shares the name)."""
    if any(re.match(re.escape(exception) + r"(?:/(?!\.\.)|(?![\w/-]|\.\w))", line[start:]) for exception in PUBLIC_EXCEPTIONS):
        return False
    before = line[:start]
    if not before or before[-1] not in "/.-_" and not before[-1].isalnum():
        return True
    return bool(re.search(r"(?:^|[^\w./-])(?:\.{1,2}/|/)+$", before))


def private_references(text: str) -> list[str]:
    """Lines of a public file that name a private path (`docs/`, `.claude`, `CLAUDE.md`, `.mcp.json`, `.githooks`, the private
    scripts, ...), also when written root-anchored (`/docs/`, `./.githooks/x`, `../docs/x`) as CODEOWNERS and shell lines do, or
    that name a private host: the mirror strips them, so an outsider could not follow the reference (NFR-01). A nested directory
    that merely shares the name (`csharp/docs/x`) is not the private root path."""
    found = []
    for line in text.splitlines():
        hit = bool(PRIVATE_HOSTS.search(line)) or any(
            _private_match_at(line, match.start()) for prefix in PRIVATE_PREFIXES for match in re.finditer(re.escape(prefix), line))
        if hit:
            found.append(line.strip())
    return found


def gate_paths(text: str) -> set[str]:
    """The backticked paths of the gate list in `text`: from the `.azuredevops/` entry nearest before `csharp/**/Directory.*.props`
    up to that entry (the list ends there in the flow rule and in both copies; an earlier mention of `.azuredevops/` in
    the surrounding prose is not part of it)."""
    for end in re.finditer(r"Directory\.\*\.props", text):
        start = text.rfind("`.azuredevops/`", 0, end.start())
        if start != -1 and end.start() - start < 2500:
            return set(re.findall(r"`([^`]+)`", text[start:end.end() + 1]))
    return set()


class CodeownersRuleTests(unittest.TestCase):
    """Each rule has a case that must fail, so a rule that stops checking is noticed."""

    def setUp(self):
        self.root = ROOT

    def test_fr03_a_good_file_has_no_problem(self):
        self.assertEqual([], codeowners_problems("*  @pluries\n/csharp/src/  @pluries\n/spec/  @pluries\n", self.root))

    def test_fr03_no_owner_fails(self):
        self.assertIn("/spec/: no owner", codeowners_problems("*  @pluries\n/csharp/src/  @pluries\n/spec/\n", self.root))

    def test_fr03_a_bare_word_owner_fails(self):
        self.assertTrue(any("not an @user" in p for p in codeowners_problems("*  pluries\n/csharp/src/  @pluries\n", self.root)))

    def test_fr03_an_org_team_and_an_email_are_valid_owners(self):
        self.assertEqual([], codeowners_problems("*  @org/team a@example.org\n/csharp/src/  @org/team\n", self.root))

    def test_fr03_a_pattern_that_matches_nothing_fails(self):
        self.assertIn("/nosuchdir/: matches nothing in the tree",
                      codeowners_problems("*  @pluries\n/csharp/src/  @pluries\n/nosuchdir/  @pluries\n", self.root))

    def test_fr03_a_glob_pattern_is_resolved(self):
        self.assertEqual([], codeowners_problems("*  @pluries\n/csharp/src/  @pluries\n/scripts/test_*.py  @pluries\n", self.root))
        self.assertIn("/scripts/zzz_*.py: matches nothing in the tree",
                      codeowners_problems("*  @pluries\n/csharp/src/  @pluries\n/scripts/zzz_*.py  @pluries\n", self.root))

    def test_fr03_a_catch_all_after_a_specific_rule_fails(self):
        self.assertTrue(any("catch-all" in p for p in codeowners_problems("/csharp/src/  @pluries\n*  @pluries\n", self.root)))

    def test_fr03_a_missing_csharp_src_rule_fails(self):
        self.assertIn("no rule for /csharp/src/", codeowners_problems("*  @pluries\n/spec/  @pluries\n", self.root))

    def test_fr03_an_empty_file_fails(self):
        self.assertEqual(["no rule"], codeowners_problems("# only a comment\n\n", self.root))


class SecurityRuleTests(unittest.TestCase):
    GOOD = ("# Security policy\n\n1. Open the **Security** tab of this repository.\n2. Choose **Report a vulnerability**.\n\n"
            "We acknowledge within **7 calendar days** and assess within **30 days**.\n\n"
            "| Version | Supported |\n|---|---|\n| The latest release | Yes |\n\nSee [VERSIONING.md](VERSIONING.md).\n")

    def test_fr04_a_good_file_has_no_problem(self):
        self.assertEqual([], security_problems(self.GOOD, ROOT))

    def test_fr04_no_private_report_path_fails(self):
        self.assertTrue(security_problems(self.GOOD.replace("**Report a vulnerability**", "write to us"), ROOT))

    def test_fr04_a_single_response_time_fails(self):
        self.assertTrue(security_problems(self.GOOD.replace(" and assess within **30 days**", ""), ROOT))

    def test_fr04_no_supported_versions_row_fails(self):
        self.assertTrue(security_problems(self.GOOD.replace("| The latest release | Yes |", "| The latest release | No |"), ROOT))
        self.assertTrue(security_problems(self.GOOD.replace("| Version | Supported |", "| Release | Status |"), ROOT))

    def test_fr04_a_mailbox_fails(self):
        self.assertIn("an e-mail address (the policy names the Security tab only)",
                      security_problems(self.GOOD + "\nOr write to security@example.org.\n", ROOT))

    def test_nfr01_a_link_into_a_private_path_fails(self):
        for target in ("docs/adr/0001-x.md", ".claude/rules/x.md", "CLAUDE.md"):
            with self.subTest(target=target):
                self.assertTrue(any("private path" in p for p in security_problems(self.GOOD + f"\n[x]({target})\n", ROOT)))

    def test_nfr01_a_private_host_link_fails(self):
        self.assertTrue(any("private host" in p for p in security_problems(self.GOOD + "\n[x](https://dev.azure.com/o/p)\n", ROOT)))

    def test_fr04_a_dead_relative_link_fails(self):
        self.assertTrue(any("does not resolve" in p for p in security_problems(self.GOOD + "\n[x](NOSUCHFILE.md)\n", ROOT)))

    def test_fr04_an_external_https_link_is_not_resolved_against_the_tree(self):
        self.assertEqual([], security_problems(self.GOOD + "\n[x](https://developercertificate.org)\n", ROOT))


class MoreRuleTests(unittest.TestCase):
    """Cases added after the review: the catch-all anywhere, inline comments, globs, links, the host, the supported row."""

    def test_fr03_a_catch_all_added_later_fails(self):
        for extra in ("*  @other", "**  @other", "/**  @other"):
            with self.subTest(extra=extra):
                self.assertTrue(any("catch-all after" in p for p in
                                codeowners_problems(f"*  @pluries\n/csharp/src/  @pluries\n{extra}\n", ROOT)), extra)

    def test_fr03_an_inline_comment_is_not_an_owner(self):
        self.assertEqual([], codeowners_problems("*  @pluries  # everything\n/csharp/src/  @pluries # the code\n", ROOT))

    def test_fr03_a_pattern_that_leaves_the_repository_fails(self):
        self.assertTrue(any("leaves the repository" in p for p in codeowners_problems("*  @p\n/csharp/src/  @p\n/../*  @p\n", ROOT)))

    def test_fr03_an_unanchored_pattern_matches_at_any_depth(self):
        self.assertEqual([], codeowners_problems("*  @p\n/csharp/src/  @p\n*.cs  @p\n", ROOT))
        self.assertTrue(codeowners_problems("*  @p\n/csharp/src/  @p\n*.nosuchext  @p\n", ROOT))

    def test_fr04_the_report_path_needs_both_steps_in_bold(self):
        text = SecurityRuleTests.GOOD
        self.assertTrue(security_problems(text.replace("**Security** tab", "Security tab"), ROOT))
        self.assertTrue(security_problems(text.replace("**Report a vulnerability**", "Report a vulnerability"), ROOT))

    def test_fr04_a_yes_outside_the_versions_table_does_not_count(self):
        text = SecurityRuleTests.GOOD.replace("| The latest release | Yes |", "| The latest release | No |") + "\nYes, we read every report.\n| a | Yes |\n"
        self.assertTrue(security_problems(text, ROOT))

    def test_fr04_links_with_a_title_or_by_reference_are_checked(self):
        good = SecurityRuleTests.GOOD
        self.assertTrue(any("does not resolve" in p for p in security_problems(good + '\n[x](NOSUCH.md "a title")\n', ROOT)))
        self.assertTrue(any("does not resolve" in p for p in security_problems(good + "\n[x][1]\n\n[1]: NOSUCH.md\n", ROOT)))
        self.assertTrue(any("private path" in p for p in security_problems(good + "\n[1]: docs/x.md\n", ROOT)))
        self.assertEqual([], security_problems(good + '\n[v](VERSIONING.md "versions")\n[w](/VERSIONING.md)\n', ROOT))
        self.assertTrue(any("does not resolve" in p for p in security_problems(good + "\n[x](/etc/passwd)\n", ROOT)))

    def test_nfr01_a_private_host_anywhere_in_security_md_fails(self):
        for form in ("https://dev.azure.com/o/p", "<https://dev.azure.com/o/p>", "[1]: https://org.visualstudio.com/x", "dev.azure.com/o"):
            with self.subTest(form=form):
                self.assertTrue(any("private host" in p for p in security_problems(SecurityRuleTests.GOOD + f"\n{form}\n", ROOT)), form)

    def test_the_public_exceptions_match_the_publish_script_where_it_exists(self):
        if not PUBLISH_SCRIPT.exists():
            self.skipTest("the publish script is private (absent from the public mirror)")
        match = re.search(r"(?m)^PUBLIC_EXCEPT=\((.*)\)\s*$", PUBLISH_SCRIPT.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "no PUBLIC_EXCEPT array in the publish script")
        self.assertEqual(set(match.group(1).split()), set(PUBLIC_EXCEPTIONS), "PUBLIC_EXCEPTIONS differs from the PUBLIC_EXCEPT array of scripts/publish-github.sh")

    def test_the_release_certificate_file_is_public_unlike_the_release_files_of_jenkins(self):
        # #3488, FR-33: a fingerprint is public, so the mirror carries scripts/release-certificate.json
        self.assertFalse("scripts/release-certificate.json".startswith(PRIVATE_PREFIXES))
        for path in ("jenkins/release.Jenkinsfile", "jenkins/jobs/craticula-release.xml"):
            self.assertTrue(path.startswith(PRIVATE_PREFIXES), path)

    def test_nfr01_the_prefix_tuple_matches_the_publish_script_where_it_exists(self):
        if not PUBLISH_SCRIPT.exists():
            self.skipTest("the publish script is private (absent from the public mirror)")
        match = re.search(r"(?m)^PRIVATE=\((.*)\)\s*$", PUBLISH_SCRIPT.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "no PRIVATE array in the publish script")
        real = {entry.rstrip("/") for entry in match.group(1).split()}
        ours = {prefix.rstrip("/") for prefix in PRIVATE_PREFIXES}
        self.assertEqual(real, ours, "PRIVATE_PREFIXES differs from the PRIVATE array of scripts/publish-github.sh")


class PrivateReferenceRuleTests(unittest.TestCase):
    def test_nfr01_private_names_are_found(self):
        for line in ("see docs/adr/../feat/x.md", "see docs/adrx/0001.md", "see docs/architecture.md", "run .claude/hooks/x.js", "read CLAUDE.md", "the .mcp.json file", "in .githooks/commit-msg",
                     "the .azuredevops/pipeline-pr.yml pipeline", "the .sonarlint/x file", "the .vscode/settings.json",
                     "/docs/  @pluries", "/.claude/  @p", "/.githooks/ @p", "/.azuredevops/ @p", "run: bash ./.githooks/x", "see ../docs/x.md",
                     "[1]: ./docs/x.md", "(scripts/apply-public-change.sh)", "/scripts/sync-release-commit.sh @p",
                     "scripts/test_publish_mirror_real.py", "see https://dev.azure.com/org/project", "https://org.visualstudio.com/x"):
            with self.subTest(line=line):
                self.assertEqual([line], private_references(line))

    def test_nfr01_public_names_are_not_flagged(self):
        for line in ("see docs/adr/0001.md and docs/adr", "the folder `docs/adr/`", "kept in docs/adr.", "see README.md and spec/semantics.md", "scripts/check-dco.sh", "csharp/src/Core", "the .github/workflows folder",
                     "mydocs/readme", "subdocs/x", "csharp/docs/x", "src/docs/x", "scripts/check-dco.sh and scripts/test_check_dco.py"):
            with self.subTest(line=line):
                self.assertEqual([], private_references(line))


class DependabotTests(unittest.TestCase):
    """The Dependabot configuration: both ecosystems weekly and grouped, every deliberately held package held by a scoped ignore
    (a bare ignore also suppresses security updates), and a two-week cooldown on NuGet. A text check always runs; the full parse
    runs when PyYAML is installed (it is not a dependency of the repository)."""
    PATH = ROOT / ".github" / "dependabot.yml"
    HELD = ("System.Security.Cryptography.Pkcs", "Microsoft.Data.SqlClient", "Microsoft.EntityFrameworkCore.Relational",
            "Microsoft.EntityFrameworkCore.Sqlite", "Microsoft.Data.Sqlite")

    def text(self):
        return self.PATH.read_text(encoding="utf-8")

    def test_both_ecosystems_are_configured_weekly(self):
        text = self.text()
        self.assertIn("version: 2", text)
        self.assertRegex(text, r"package-ecosystem: nuget\n\s+directory: /csharp\n\s+schedule:\n\s+interval: weekly")
        self.assertRegex(text, r"package-ecosystem: github-actions\n\s+directory: /\n\s+schedule:\n\s+interval: weekly")
        self.assertEqual(2, text.count("groups:"))

    def test_the_cooldown_keeps_the_two_week_rule(self):
        self.assertRegex(self.text(), r"cooldown:\n\s+default-days: 14")

    def test_every_held_package_is_ignored_with_a_scope(self):
        text = self.text()
        for name in self.HELD:
            with self.subTest(package=name):
                self.assertRegex(text, rf"- dependency-name: {re.escape(name)}\n\s+(update-types|versions): \[")

    def test_the_release_please_action_major_is_held_with_a_scope(self):
        # #3263: a bare ignore would also block its security updates; only the major is held.
        self.assertRegex(self.text(), r"- dependency-name: googleapis/release-please-action\n\s+update-types: \[\"version-update:semver-major\"\]")
        self.assertTrue((ROOT / ".github" / "workflows" / "release-please.yml").exists())

    def test_the_held_packages_are_still_named_in_the_props_file(self):
        props = (ROOT / "csharp" / "Directory.Packages.props").read_text(encoding="utf-8")
        for name in self.HELD:
            with self.subTest(package=name):
                self.assertIn(f'<PackageVersion Include="{name}"', props)

    def test_the_file_parses_as_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed; the text checks above still run")
        data = yaml.safe_load(self.text())
        ecosystems = {u["package-ecosystem"]: u for u in data["updates"]}
        self.assertEqual({"nuget", "github-actions"}, set(ecosystems))
        self.assertEqual("/csharp", ecosystems["nuget"]["directory"])
        for update in ecosystems.values():
            self.assertEqual("weekly", update["schedule"]["interval"])
            self.assertLessEqual(update["open-pull-requests-limit"], 10)
        action_ignores = ecosystems["github-actions"]["ignore"]
        self.assertEqual({"googleapis/release-please-action"}, {i["dependency-name"] for i in action_ignores})
        self.assertTrue(all(i.get("update-types") == ["version-update:semver-major"] for i in action_ignores))
        ignores = ecosystems["nuget"]["ignore"]
        self.assertEqual(set(self.HELD), {i["dependency-name"] for i in ignores})
        for entry in ignores:
            self.assertTrue(entry.get("versions") or entry.get("update-types"),
                            f"{entry['dependency-name']}: a bare ignore also blocks security updates")
        self.assertEqual(14, ecosystems["nuget"]["cooldown"]["default-days"])


class GatePathRuleTests(unittest.TestCase):
    ROW = ("**A PR that touches the gate** (`.azuredevops/`, `scripts/pack*`, `scripts/check-dco*`, `.github/workflows/`, "
           "`csharp/src/.editorconfig`, any `csharp/**/Directory.*.props`) validates its own copy `not/this`.")

    def test_the_list_is_read_up_to_the_props_entry(self):
        self.assertEqual({".azuredevops/", "scripts/pack*", "scripts/check-dco*", ".github/workflows/", "csharp/src/.editorconfig",
                          "csharp/**/Directory.*.props"}, gate_paths(self.ROW))

    def test_a_text_without_the_list_gives_nothing(self):
        self.assertEqual(set(), gate_paths("no gate list here, only `scripts/pack*`"))

    def test_an_earlier_mention_of_azuredevops_in_the_prose_is_not_part_of_the_list(self):
        text = "`.azuredevops/` is private; `scripts/` is published.\n\n" + self.ROW
        self.assertNotIn("scripts/", gate_paths(text))
        self.assertIn("scripts/check-dco*", gate_paths(text))

    def test_a_wrapped_list_is_read(self):
        wrapped = self.ROW.replace(", `scripts/pack*`", ",\n  `scripts/pack*`")
        self.assertIn("scripts/pack*", gate_paths(wrapped))


README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
CONDUCT = ROOT / "CODE_OF_CONDUCT.md"
ISSUE_TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
BADGE = re.compile(r"\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)")
BADGE_HOSTS = ("github.com", "img.shields.io", "api.scorecard.dev")
# FR-10: a Sonar or a package-version badge appears once its source exists, never before (SC-05); drop the entry then.
BADGE_NOT_YET = re.compile(r"sonar|nuget", re.IGNORECASE)
REQUIRED_BADGES = {"CI": r"github\.com/pluries/craticula/actions/workflows/ci\.yml/badge\.svg",
                   "coverage gate": r"img\.shields\.io/badge/coverage",
                   "license": r"img\.shields\.io/github/license/pluries/craticula",
                   "spec version": r"img\.shields\.io/badge/spec-",
                   "OpenSSF Scorecard": r"api\.scorecard\.dev/projects/github\.com/pluries/craticula/badge"}


def readme_top(text: str) -> str:
    return re.split(r"(?m)^## ", text, maxsplit=1)[0]


def readme_badges(text: str) -> list[tuple[str, str, str]]:
    """The badges above the first `##` heading of the README: (label, image url, link)."""
    return BADGE.findall(readme_top(text))


def unreadable_badge_problems(text: str) -> list[str]:
    """An image above the first heading that the badge pattern does not read (an `<img>`, a reference-style or an unlinked badge)
    would escape the host and early-badge checks: refuse it."""
    top = readme_top(text)
    problems = ["an <img> tag: use the `[![label](image)](link)` form" for _ in re.findall(r"(?i)<img\b", top)]
    if top.count("![") != len(BADGE.findall(top)):
        problems.append("an image that is not in the `[![label](image)](link)` form")
    return problems


def _workflow_badge_problems(label: str, image: str, root: Path) -> list[str]:
    workflow = re.search(r"github\.com/([\w.-]+/[\w.-]+)/actions/workflows/([\w.-]+)/badge\.svg", image)
    if not workflow:
        return []
    if workflow.group(1) != "pluries/craticula":
        return [f"{label}: a workflow badge of another repository ({workflow.group(1)})"]
    if not (root / ".github" / "workflows" / workflow.group(2)).exists():
        return [f"{label}: workflow {workflow.group(2)} does not exist"]
    return []


def _spec_badge_problems(label: str, image: str, root: Path) -> list[str]:
    spec = re.search(r"img\.shields\.io/badge/spec-(\d[^-/]*)-", image)
    if not spec:
        return []
    actual = (root / "spec" / "VERSION").read_text(encoding="utf-8").strip()
    return [] if spec.group(1) == actual else [f"{label}: shows spec {spec.group(1)}, spec/VERSION says {actual}"]


def badge_problems(badges: list[tuple[str, str, str]], root: Path) -> list[str]:
    """What is wrong with README badges: an image from an unexpected host, a Sonar or package badge before its source exists, a CI badge
    for a workflow that is not in the repository, a spec-version badge that differs from `spec/VERSION`, a link to a missing file."""
    problems = []
    for label, image, link in badges:
        host = image.split("/")[2] if "://" in image else ""
        if host not in BADGE_HOSTS:
            problems.append(f"{label}: image host '{host}' is not one of {', '.join(BADGE_HOSTS)}")
        if BADGE_NOT_YET.search(image):
            problems.append(f"{label}: a Sonar or package-version badge before its source exists (FR-10)")
        problems += _workflow_badge_problems(label, image, root) + _spec_badge_problems(label, image, root)
        if "://" not in link and not (root / link.split("#")[0]).exists():
            problems.append(f"{label}: link {link} does not exist")
    return problems


class ContributorFileRuleTests(unittest.TestCase):
    """The rules of the badge check, on synthetic input (the real files are in RealFileTests)."""

    def make_root(self, version="0.1.0"):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
        (root / "spec").mkdir()
        (root / "spec" / "VERSION").write_text(version + "\n", encoding="utf-8")
        (root / "LICENSE").write_text("Apache\n", encoding="utf-8")
        return root

    GOOD = [("CI", "https://github.com/pluries/craticula/actions/workflows/ci.yml/badge.svg?branch=main", "https://github.com/x"),
            ("spec version", "https://img.shields.io/badge/spec-0.1.0-blue", "spec/VERSION"),
            ("license", "https://img.shields.io/github/license/pluries/craticula", "LICENSE")]

    def test_a_good_set_of_badges_has_no_problem(self):
        self.assertEqual([], badge_problems(self.GOOD, self.make_root()))

    def test_a_workflow_badge_of_another_repository_is_a_problem(self):
        bad = [("CI", "https://github.com/someone/else/actions/workflows/ci.yml/badge.svg", "LICENSE")]
        self.assertTrue(any("another repository" in p for p in badge_problems(bad, self.make_root())))

    def test_an_image_the_badge_pattern_cannot_read_is_a_problem(self):
        for text in ('# T\n\n<img src="https://img.shields.io/nuget/v/x">\n\n## H\n',
                     "# T\n\n![sonar][s]\n\n[s]: https://sonarcloud.io/x\n\n## H\n",
                     "# T\n\n![unlinked](https://img.shields.io/badge/a-b-blue)\n\n## H\n"):
            with self.subTest(text=text):
                self.assertTrue(unreadable_badge_problems(text))
        self.assertEqual([], unreadable_badge_problems("# T\n\n[![a](https://img.shields.io/b)](LICENSE)\n\n## H\n![later](x)\n"))

    def test_a_badge_for_a_workflow_that_does_not_exist_is_a_problem(self):
        bad = [("CI", "https://github.com/pluries/craticula/actions/workflows/nope.yml/badge.svg", "LICENSE")]
        self.assertTrue(any("nope.yml does not exist" in p for p in badge_problems(bad, self.make_root())))

    def test_a_sonar_or_package_badge_before_its_source_exists_is_a_problem(self):
        for image in ("https://sonarcloud.io/api/project_badges/measure?project=x", "https://img.shields.io/nuget/v/Craticula.Core"):
            with self.subTest(image=image):
                self.assertTrue(badge_problems([("x", image, "LICENSE")], self.make_root()))

    def test_a_spec_version_badge_that_differs_from_the_file_is_a_problem(self):
        bad = [("spec version", "https://img.shields.io/badge/spec-0.2.0-blue", "LICENSE")]
        self.assertTrue(any("spec/VERSION says 0.1.0" in p for p in badge_problems(bad, self.make_root("0.1.0"))))

    def test_an_image_from_an_unexpected_host_is_a_problem(self):
        self.assertTrue(any("image host" in p for p in badge_problems([("x", "https://tracker.example/pixel.svg", "LICENSE")], self.make_root())))

    def test_a_link_to_a_missing_file_is_a_problem(self):
        self.assertTrue(any("does not exist" in p for p in badge_problems([("x", self.GOOD[2][1], "NOPE.md")], self.make_root())))

    def test_only_the_badges_above_the_first_heading_count(self):
        text = "# T\n\n[![a](https://img.shields.io/b)](LICENSE)\n\n## H\n\n[![b](https://img.shields.io/c)](LICENSE)\n"
        self.assertEqual([("a", "https://img.shields.io/b", "LICENSE")], readme_badges(text))


class RealFileTests(unittest.TestCase):
    def test_fr10_the_readme_badges_exist_resolve_to_real_things_and_none_is_early(self):
        text = README.read_text(encoding="utf-8")
        badges = readme_badges(text)
        for label, pattern in REQUIRED_BADGES.items():
            with self.subTest(badge=label):
                self.assertTrue(any(name == label and re.search(pattern, image) for name, image, _ in badges),
                                f"the README has no '{label}' badge pointing at {pattern}")
        self.assertEqual([], unreadable_badge_problems(text))
        self.assertEqual([], badge_problems(badges, ROOT))

    def test_fr11_contributing_explains_the_dco_the_subject_format_and_the_commands(self):
        text = CONTRIBUTING.read_text(encoding="utf-8")
        for needle in ("git commit -s", "Signed-off-by", "feat:", "fix:", "dotnet build", "dotnet test", "SECURITY.md", "CODE_OF_CONDUCT.md"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for link in ("SECURITY.md", "CODE_OF_CONDUCT.md"):
            self.assertTrue((ROOT / link).exists(), f"{link} is linked from CONTRIBUTING.md but missing")

    def test_fr11_the_code_of_conduct_says_where_to_report(self):
        text = CONDUCT.read_text(encoding="utf-8")
        self.assertIn("Report a vulnerability", text)
        self.assertIn("Conduct:", text)
        self.assertIn("Contributor Covenant", text)

    def test_fr11_the_issue_templates_and_the_pull_request_template_exist_and_have_their_parts(self):
        config = (ISSUE_TEMPLATES / "config.yml").read_text(encoding="utf-8")
        self.assertIn("blank_issues_enabled: false", config)
        self.assertIn("security/advisories/new", config)
        for name in ("bug_report.yml", "feature_request.yml"):
            with self.subTest(template=name):
                text = "\n".join(l for l in (ISSUE_TEMPLATES / name).read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
                for key in ("name:", "description:", "body:", "- type: textarea", "required: true"):
                    self.assertIn(key, text)
        pull_request = PR_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("git commit -s", pull_request)
        self.assertIn("dco", pull_request)

    def test_fr11_the_adr_folder_has_public_records_and_each_one_names_no_private_path(self):
        # #1665 AC5, ADR 0004: a record marked `Classification: Public` is written for outsiders. A record without the mark (a draft) is not read here.
        adr = ROOT / "docs" / "adr"
        if not adr.is_dir():
            self.skipTest("no docs/adr folder here")
        public = [path for path in sorted(adr.glob("*.md")) if re.search(r"Classification: Public\b", path.read_text(encoding="utf-8"))]
        self.assertGreaterEqual(len(public), 3, "ADR 0001, 0002 and 0004 are public records")
        for path in public:
            with self.subTest(record=path.name):
                self.assertEqual([], private_references(path.read_text(encoding="utf-8")))

    def test_fr03_codeowners_exists_and_is_valid(self):
        self.assertTrue(CODEOWNERS.exists(), ".github/CODEOWNERS is missing")
        self.assertEqual([], codeowners_problems(CODEOWNERS.read_text(encoding="utf-8"), ROOT))

    def test_fr04_security_md_exists_and_is_valid(self):
        self.assertTrue(SECURITY.exists(), "SECURITY.md is missing")
        self.assertEqual([], security_problems(SECURITY.read_text(encoding="utf-8"), ROOT))

    def test_fr02_the_dco_workflow_and_its_checker_exist(self):
        self.assertTrue((ROOT / ".github" / "workflows" / "dco.yml").exists(), "dco.yml is missing")
        checker = ROOT / "scripts" / "check-dco.sh"
        self.assertTrue(checker.exists(), "scripts/check-dco.sh is missing")
        self.assertTrue(os.access(checker, os.X_OK) or os.name == "nt", "scripts/check-dco.sh is not executable")

    def test_nfr01_the_public_governance_files_name_no_private_path(self):
        public = (SECURITY, CODEOWNERS, ROOT / ".github" / "workflows" / "dco.yml", CONTRIBUTING, CONDUCT, PR_TEMPLATE, README,
                  *sorted(ISSUE_TEMPLATES.glob("*.yml")))
        for path in public:
            with self.subTest(file=path.name):
                self.assertEqual([], private_references(path.read_text(encoding="utf-8")))

    def test_the_gate_lists_name_the_governance_files_and_agree(self):
        if not PUBLISH_SCRIPT.exists():
            self.skipTest("the private documents are absent (the public mirror)")
        reference = None
        for name in GATE_COPIES:
            with self.subTest(file=name):
                path = ROOT / name
                self.assertTrue(path.exists(), f"{name} is missing: the gate list is copied there (renamed or moved?)")
                paths = gate_paths(path.read_text(encoding="utf-8"))
                self.assertTrue(paths, "no gate list found")
                self.assertEqual([], sorted(set(GATE_GOVERNANCE) - paths), "governance entries missing from the gate list")
                if reference is None:
                    reference = paths
                self.assertEqual(reference, paths, "the gate lists of the copies differ")


if __name__ == "__main__":
    unittest.main()
