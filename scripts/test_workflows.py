#!/usr/bin/env python3
"""Pins the supply-chain rules of every GitHub workflow offline (story #2467, NFR-02): each `uses:` of a third-party
or local-looking action is pinned to a 40-character commit SHA, every workflow declares a top-level `permissions:`
block, and the public CI (`ci.yml`) references no secret. Line checks only, stdlib only, no network. A reusable-workflow
call to this repository (`./.github/workflows/...`) needs no pin. A mapping line with no space after its colon (`run:bash x`,
story #1662 FR-02) is invalid YAML that no job could survive; `key_without_space` catches that class without a YAML library,
and every workflow is also parsed with PyYAML when it is installed. Run: python3 scripts/test_workflows.py
(also run by Craticula.Conformance.Tests/WorkflowLintTests.cs on every `dotnet test`).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)")
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
PERMISSIONS = re.compile(r"^permissions:", re.MULTILINE)
SECRET = re.compile(r"\bsecrets\b", re.IGNORECASE)
READ_ONLY_PERMISSIONS = re.compile(r"^permissions:\n  contents: read\n(?!  )", re.MULTILINE)
JOB_PERMISSIONS = re.compile(r"^    permissions:", re.MULTILINE)
PIPED_RUN = re.compile(r"^\s*run:\s.*\|", re.MULTILINE)
EXPLICIT_BASH = re.compile(r"^\s*shell:\s*bash\s*$", re.MULTILINE)
KEY_WITHOUT_SPACE = re.compile(r"^(?P<key>[A-Za-z_][\w.-]*):(?P<rest>(?!//)[^ ].*)$")
RUN_KEY = re.compile(r"^(?P<indent>\s*)(?:-\s+)*run:\s*(?P<value>.*)$")
UNTRUSTED_EXPRESSION = re.compile(r"\$\{\{.*?\b(?:github\.event\b|github\[|github\.head_ref|github\.ref_name)")
HEAD_CHECKOUT = re.compile(r"^\s*(?:ref|repository):\s*.*(?:pull_request\.head|head_ref|head\.repo|refs/pull|github\[)", re.MULTILINE)
BLOCK_SCALAR = re.compile(r":\s+[|>](?:[+-]?\d*|\d*[+-]?)\s*(?:#.*)?$")


def unpinned_uses(text: str) -> list[str]:
    """The `uses:` values that are neither a local path nor `owner/action@<40 hex>`."""
    bad = []
    for line in text.splitlines():
        match = USES.match(line)
        if not match:
            continue
        ref = match.group("ref").strip("'\"")
        if ref.startswith("./"):
            continue
        if not SHA_PIN.match(ref):
            bad.append(ref)
    return bad


def has_top_level_permissions(text: str) -> bool:
    return PERMISSIONS.search(text) is not None


def is_read_only(text: str) -> bool:
    """Top-level permissions are exactly `contents: read` and no job raises them."""
    return READ_ONLY_PERMISSIONS.search(text) is not None and JOB_PERMISSIONS.search(text) is None


def pipe_hides_failure(text: str) -> bool:
    """A single-line `run:` with a pipe and no explicit `shell: bash` (default `bash -e` has no pipefail)."""
    return PIPED_RUN.search(text) is not None and EXPLICIT_BASH.search(text) is None


def key_without_space(text: str) -> list[str]:
    """Mapping lines written `key:value` with no space after the colon (FR-02: `run:bash x` is not a mapping entry, so the
    whole file fails to load; `- run:bash x` loads but the step is a string, which GitHub rejects). Comments, blank lines, the
    bodies of block scalars (`run: |`), URLs (`key://`) and `- vol:/path` list strings are skipped. Stdlib only, a line scan: it does not replace a parser,
    it catches the one class a regex lint missed. A multi-line plain scalar whose continuation line looks like `a:b` is a known
    false positive (none exists; the failure is loud)."""
    bad = []
    block_column = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if block_column is not None:
            if indent > block_column:
                continue
            block_column = None
        content = line.lstrip(" ").rstrip()
        key_column = indent
        while content.startswith("- "):
            content = content[2:].lstrip(" ")
            key_column = len(line) - len(content)
        if BLOCK_SCALAR.search(line):
            block_column = key_column
        else:
            match = KEY_WITHOUT_SPACE.match(content)
            # `- vol:/path` (a volume or port mapping) is a legitimate list string: a leading slash only counts on a mapping key.
            if match and not (stripped.startswith("- ") and match.group("rest").startswith("/")):
                bad.append(stripped)
    return bad


def event_expression_in_run(text: str) -> list[str]:
    """Lines of a `run:` value (one line, or the body of a `run: |` block) that splice an event expression such as
    `${{ github.event.pull_request.title }}`, `github.head_ref` or `github.ref_name` into the shell text: a contributor chooses
    those strings (script injection). They belong in `env:`, where the shell reads them as data. Line scan, stdlib only."""
    bad = []
    block_column = None
    for line in text.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if block_column is not None:
            if indent > block_column:
                if UNTRUSTED_EXPRESSION.search(line):
                    bad.append(line.strip())
                continue
            block_column = None
        match = RUN_KEY.match(line)
        if not match:
            continue
        value = match.group("value")
        key_column = len(match.group("indent")) + (2 if line.lstrip().startswith("- ") else 0)
        if re.match(r"^[|>][+-]?\d*[+-]?\s*(?:#.*)?$", value):
            block_column = key_column
        elif UNTRUSTED_EXPRESSION.search(value):
            bad.append(line.strip())
    return bad


def target_checks_out_head(text: str) -> list[str]:
    """In a `pull_request_target` workflow (it runs with the base branch's code and token), the `ref:` or `repository:` lines
    of a checkout that point at the pull request's head: that would run a contributor's code with that token. The pull
    request's commits may be fetched as data in a `run:` step (`git fetch refs/pull/<n>/head`); they may not be checked out."""
    code = re.sub(r"(?m)^\s*#.*$", "", text)
    if "pull_request_target" not in code:
        return []
    return [line.strip() for line in code.splitlines() if HEAD_CHECKOUT.match(line)]


def secret_references(text: str) -> list[str]:
    """Lines that mention `secrets` outside a comment."""
    return [line.strip() for line in text.splitlines() if SECRET.search(line) and not line.lstrip().startswith("#")]


class RuleFunctionTests(unittest.TestCase):
    """Each rule has a case that must fail, so a rule that stops checking is noticed."""

    def test_sha_pin_is_accepted(self):
        self.assertEqual([], unpinned_uses("      - uses: actions/checkout@" + "a" * 40 + " # v7.0.1\n"))

    def test_tag_pin_fails(self):
        self.assertEqual(["actions/checkout@v4"], unpinned_uses("      - uses: actions/checkout@v4\n"))

    def test_branch_pin_fails(self):
        self.assertEqual(["owner/action@main"], unpinned_uses("    uses: owner/action@main\n"))

    def test_short_sha_fails(self):
        self.assertEqual(["owner/action@" + "a" * 39], unpinned_uses("      - uses: owner/action@" + "a" * 39 + "\n"))

    def test_local_reusable_workflow_needs_no_pin(self):
        self.assertEqual([], unpinned_uses("    uses: ./.github/workflows/release.yml\n"))

    def test_missing_permissions_fails(self):
        self.assertFalse(has_top_level_permissions("name: x\non: push\njobs: {}\n"))

    def test_nested_permissions_do_not_count(self):
        self.assertFalse(has_top_level_permissions("name: x\njobs:\n  a:\n    permissions:\n      contents: read\n"))

    def test_top_level_permissions_pass(self):
        self.assertTrue(has_top_level_permissions("name: x\npermissions:\n  contents: read\n"))

    def test_secret_reference_fails(self):
        self.assertEqual(["token: ${{ secrets.TOKEN }}"], secret_references("        token: ${{ secrets.TOKEN }}\n"))

    def test_bracket_and_json_secret_forms_fail(self):
        self.assertEqual(2, len(secret_references("a: ${{ secrets['X'] }}\nb: ${{ toJSON(secrets) }}\n")))

    def test_read_only_permissions_pass(self):
        self.assertTrue(is_read_only("name: x\npermissions:\n  contents: read\n\njobs: {}\n"))

    def test_write_permissions_fail(self):
        self.assertFalse(is_read_only("name: x\npermissions: write-all\n"))
        self.assertFalse(is_read_only("name: x\npermissions:\n  contents: write\n"))

    def test_job_level_permissions_fail(self):
        self.assertFalse(is_read_only("permissions:\n  contents: read\njobs:\n  a:\n    permissions:\n      contents: write\n"))

    def test_pipe_without_shell_fails(self):
        self.assertTrue(pipe_hides_failure("        run: bash x.sh 2>&1 | tee log\n"))

    def test_pipe_with_explicit_bash_passes(self):
        self.assertFalse(pipe_hides_failure("        shell: bash\n        run: bash x.sh | tee log\n"))

    def test_key_without_space_fails_on_the_broken_ci_line(self):
        """FR-02: the exact line commit 78a7c9c wrote into ci.yml."""
        line = '        run:bash scripts/coverage.sh 2>&1 | tee "$RUNNER_TEMP/coverage.log"\n'
        self.assertEqual(['run:bash scripts/coverage.sh 2>&1 | tee "$RUNNER_TEMP/coverage.log"'], key_without_space(line))

    def test_key_without_space_fails_on_other_keys(self):
        self.assertEqual(["name:Build", "uses:actions/checkout@v4"], key_without_space("name:Build\n    uses:actions/checkout@v4\n"))

    def test_list_item_keys_are_checked(self):
        """The first key of a step sits after `- `: the same mistake there loads as a string and GitHub rejects the step."""
        text = "    steps:\n      - run:bash x\n      - uses:actions/checkout@v4\n"
        self.assertEqual(["- run:bash x", "- uses:actions/checkout@v4"], key_without_space(text))

    def test_value_starting_with_a_slash_is_flagged_but_a_url_is_not(self):
        self.assertEqual(["working-directory:/tmp"], key_without_space("  working-directory:/tmp\n"))
        self.assertEqual([], key_without_space("  url://host/x\n"))

    def test_tab_after_the_colon_is_flagged(self):
        self.assertEqual(["a:\tb"], key_without_space("a:\tb\n"))

    def test_list_items_that_are_plain_strings_pass(self):
        self.assertEqual([], key_without_space("    ports:\n      - 5432:5432\n      - 'a:b'\n      - vol:/path\n"))

    def test_block_scalar_header_variants(self):
        for header in ("|", "|-", "|+", ">", ">-", "|2", "|2-", "|-2"):
            with self.subTest(header=header):
                text = f"        run: {header}\n          echo url:x\n        shell:bash\n"
                self.assertEqual(["shell:bash"], key_without_space(text))

    def test_key_with_space_passes(self):
        self.assertEqual([], key_without_space("      - name: Test\n        run: bash x.sh\n    needs:\n      - build\n"))

    def test_block_scalar_bodies_are_not_scanned(self):
        text = "      - run: |\n          echo a:b\n          url:x\n      - name: next\n"
        self.assertEqual([], key_without_space(text))

    def test_key_without_space_resumes_after_a_block_scalar(self):
        text = "        run: |\n          echo a:b\n        shell:bash\n"
        self.assertEqual(["shell:bash"], key_without_space(text))

    def test_urls_comments_and_expressions_are_not_flagged(self):
        text = "# note a:b\n  https://example.org/x\n  if: ${{ github.event_name == 'push' }}\n  cron: '0 3 * * 1'\n"
        self.assertEqual([], key_without_space(text))

    def test_event_expression_in_a_run_line_fails(self):
        self.assertEqual(['- run: echo "${{ github.event.pull_request.title }}"'],
                         event_expression_in_run('      - run: echo "${{ github.event.pull_request.title }}"\n'))

    def test_event_expression_in_a_run_block_fails(self):
        text = "      - name: x\n        run: |\n          echo start\n          git checkout ${{ github.head_ref }}\n          echo ${{ github.ref_name }}\n"
        self.assertEqual(["git checkout ${{ github.head_ref }}", "echo ${{ github.ref_name }}"], event_expression_in_run(text))

    def test_other_event_expression_forms_in_a_run_line_fail(self):
        for expr in ("${{ toJSON(github.event) }}", "${{ format('{0}', github.event.pull_request.title) }}",
                     "${{ github['event']['pull_request']['title'] }}", "${{ github.head_ref }}", "${{ github.ref_name }}"):
            with self.subTest(expr=expr):
                self.assertEqual(1, len(event_expression_in_run(f"        run: echo {expr}\n")), expr)

    def test_head_checkout_in_a_pull_request_target_workflow_fails(self):
        for ref in ("ref: ${{ github.event.pull_request.head.sha }}", "ref: ${{ github.head_ref }}", "ref: refs/pull/1/merge",
                    "repository: ${{ github.event.pull_request.head.repo.full_name }}", "ref: ${{ github['event'] }}"):
            with self.subTest(ref=ref):
                text = f"on:\n  pull_request_target:\njobs:\n  a:\n    steps:\n      - uses: a/b@{'a' * 40}\n        with:\n          {ref}\n"
                self.assertEqual([ref], target_checks_out_head(text), ref)

    def test_head_checkout_in_a_pull_request_workflow_is_not_this_rules_concern(self):
        text = "on:\n  pull_request:\njobs:\n  a:\n    steps:\n      - uses: a/b@" + "a" * 40 + "\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n"
        self.assertEqual([], target_checks_out_head(text))

    def test_a_base_checkout_and_a_data_fetch_in_a_pull_request_target_workflow_pass(self):
        text = ("on:\n  pull_request_target:\n# ref: ${{ github.head_ref }} is only a comment\njobs:\n  a:\n    steps:\n      - uses: a/b@" + "a" * 40 +
                "\n        with:\n          fetch-depth: 0\n      - run: |\n          git fetch origin \"+refs/pull/${PR}/head:refs/x\"\n")
        self.assertEqual([], target_checks_out_head(text))

    def test_event_expression_in_env_with_a_clean_run_passes(self):
        text = ("      - name: x\n        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
                "        run: |\n          echo \"$TITLE\"\n")
        self.assertEqual([], event_expression_in_run(text))

    def test_event_expression_outside_a_run_passes(self):
        text = "concurrency:\n  group: ci-${{ github.ref }}\n      - uses: a/b@" + "a" * 40 + "\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n"
        self.assertEqual([], event_expression_in_run(text))

    def test_run_block_ends_at_the_next_key(self):
        text = "        run: |\n          echo ok\n        env:\n          X: ${{ github.event.number }}\n"
        self.assertEqual([], event_expression_in_run(text))

    def test_secret_in_comment_is_ignored(self):
        self.assertEqual([], secret_references("# No secret: nothing reads secrets.X here\n"))


class RealWorkflowTests(unittest.TestCase):
    def workflows(self):
        files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(files, "no workflow found under .github/workflows")
        return files

    def test_every_action_is_pinned_to_a_sha(self):
        for path in self.workflows():
            with self.subTest(workflow=path.name):
                self.assertEqual([], unpinned_uses(path.read_text(encoding="utf-8")))

    def test_every_workflow_has_a_space_after_each_key_colon(self):
        """FR-02: stdlib check, always runs."""
        for path in self.workflows():
            with self.subTest(workflow=path.name):
                self.assertEqual([], key_without_space(path.read_text(encoding="utf-8")))

    def test_every_workflow_parses_as_yaml(self):
        """FR-02: a full parse when PyYAML is installed (it is not a dependency of the repository)."""
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed; test_every_workflow_has_a_space_after_each_key_colon still runs")
        for path in self.workflows():
            with self.subTest(workflow=path.name):
                self.assertIsInstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)

    def test_no_workflow_splices_an_event_expression_into_a_run_block(self):
        for path in self.workflows():
            with self.subTest(workflow=path.name):
                self.assertEqual([], event_expression_in_run(path.read_text(encoding="utf-8")))

    def test_a_pull_request_target_workflow_is_read_only_secretless_and_never_checks_out_the_head(self):
        found = 0
        for path in self.workflows():
            text = path.read_text(encoding="utf-8")
            if "pull_request_target" not in re.sub(r"(?m)^\s*#.*$", "", text):
                continue
            found += 1
            with self.subTest(workflow=path.name):
                self.assertTrue(is_read_only(text), "a pull_request_target workflow must be read-only (contents: read)")
                self.assertEqual([], secret_references(text), "a pull_request_target workflow must use no secret")
                self.assertEqual([], target_checks_out_head(text), "it must not check out the pull request's head")
                self.assertIn("persist-credentials: false", text)
        self.assertGreaterEqual(found, 1, "dco.yml is expected to be a pull_request_target workflow")

    def test_dco_workflow_runs_the_base_checker_under_the_job_name_dco(self):
        text = (WORKFLOWS / "dco.yml").read_text(encoding="utf-8")
        code = re.sub(r"(?m)^\s*#.*$", "", text)
        self.assertRegex(code, r"(?m)^  dco:$")
        self.assertRegex(code, r"(?m)^  pull_request_target:$")
        self.assertNotRegex(code, r"(?m)^  pull_request:$")
        self.assertIn("scripts/check-dco.sh", code)
        self.assertIn("refs/pull/${PR_NUMBER}/head", code)
        self.assertEqual(1, len(re.findall(r"(?m)^\s*- uses: actions/checkout@", code)), "one checkout, of the base")

    def test_every_workflow_declares_permissions(self):
        for path in self.workflows():
            with self.subTest(workflow=path.name):
                self.assertTrue(has_top_level_permissions(path.read_text(encoding="utf-8")))

    def test_public_ci_uses_no_secret(self):
        ci = WORKFLOWS / "ci.yml"
        self.assertTrue(ci.exists(), "ci.yml is missing")
        self.assertEqual([], secret_references(ci.read_text(encoding="utf-8")))

    def test_public_ci_is_read_only(self):
        self.assertTrue(is_read_only((WORKFLOWS / "ci.yml").read_text(encoding="utf-8")))

    def test_public_ci_pipes_run_under_explicit_bash(self):
        self.assertFalse(pipe_hides_failure((WORKFLOWS / "ci.yml").read_text(encoding="utf-8")))

    def test_public_ci_has_the_two_required_checks(self):
        text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        for job in ("build", "test"):
            with self.subTest(job=job):
                self.assertRegex(text, rf"(?m)^  {job}:$")

    # --- docs.yml (task #2836): the docs site build and the Pages deploy ---

    @staticmethod
    def docs_text() -> str:
        """docs.yml without its comment lines, so a mutation hidden in a comment cannot satisfy an assertion."""
        lines = (WORKFLOWS / "docs.yml").read_text(encoding="utf-8").splitlines()
        return "\n".join(line for line in lines if not line.strip().startswith("#")) + "\n"

    def test_docs_workflow_has_a_site_and_a_deploy_job_and_none_named_like_a_required_check(self):
        text = self.docs_text()
        for job in ("site", "deploy"):
            with self.subTest(job=job):
                self.assertRegex(text, rf"(?m)^  {job}:$")
        for job in ("build", "test"):
            with self.subTest(forbidden=job):
                self.assertNotRegex(text, rf"(?m)^  {job}:$")    # ci.yml's required checks keep their names

    def test_docs_workflow_runs_on_pull_requests_and_on_pushes_to_main(self):
        text = self.docs_text()
        self.assertRegex(text, r"(?m)^  pull_request:\n    branches: \[main\]$")
        self.assertRegex(text, r"(?m)^  push:\n    branches: \[main\]$")

    def test_docs_workflow_is_read_only_except_in_the_deploy_job(self):
        text = self.docs_text()
        self.assertRegex(text, r"(?m)^permissions:\n  contents: read\n(?!  )")
        site, deploy = text.split("\n  deploy:\n")
        self.assertNotRegex(site, r"(?m)^    permissions:")
        self.assertRegex(deploy, r"(?m)^    permissions:\n      pages: write\n      id-token: write\n(?!      )")
        self.assertNotRegex(text, r"(?m)^\s+(?:contents|actions|pull-requests|packages|statuses|checks): write")

    def test_docs_workflow_uses_no_secret(self):
        self.assertEqual([], secret_references(self.docs_text()))

    def test_docs_deploy_runs_only_on_a_push_to_main_with_pages_switched_on_after_the_site_job(self):
        text = self.docs_text()
        gate = "if: github.event_name == 'push' && github.ref == 'refs/heads/main' && vars.DOCS_PAGES == 'true'"
        deploy = text.split("\n  deploy:\n")[1]
        self.assertIn(f"\n    {gate}\n", "\n" + deploy)
        self.assertRegex(deploy, r"(?m)^    needs: site$")
        self.assertRegex(deploy, r"(?m)^    environment:\n      name: github-pages$")
        # the artifact is uploaded under the same gate, and no step needs the Pages API (configure-pages would need pages: read)
        self.assertIn(f"\n        {gate}\n        with:\n          path: site/_build\n", text)
        self.assertNotIn("configure-pages", text)

    def test_docs_site_job_runs_the_generator_tests_and_builds_into_the_folder_the_artifact_reads(self):
        text = self.docs_text()
        self.assertRegex(text, r"(?m)^        run: python3 scripts/test_build_site\.py$")
        self.assertRegex(text, r"(?m)^        run: python3 scripts/build_site\.py --out site/_build$")
        self.assertNotIn("|| true", text)
        self.assertNotIn("continue-on-error", text)


class ScorecardWorkflowTests(unittest.TestCase):
    """scorecard.yml (spec FR-07): weekly and by hand, never on a pull request, the one job that may ask for an OIDC token."""

    @staticmethod
    def text() -> str:
        lines = (WORKFLOWS / "scorecard.yml").read_text(encoding="utf-8").splitlines()
        return "\n".join(line for line in lines if not line.strip().startswith("#")) + "\n"

    def test_it_runs_weekly_and_by_hand_and_on_nothing_else(self):
        text = self.text()
        self.assertRegex(text, r'(?m)^on:\n  schedule:\n    - cron: "[^"]+"\n  workflow_dispatch:\n(?!  )')
        for event in ("pull_request", "pull_request_target", "push"):
            with self.subTest(event=event):
                self.assertNotRegex(text, rf"(?m)^\s+{event}:")

    def test_every_action_is_pinned_to_a_sha(self):
        text = self.text()
        self.assertEqual([], unpinned_uses(text))
        self.assertRegex(text, r"(?m)^      - uses: ossf/scorecard-action@[0-9a-f]{40} # v2\.5\.0$")

    def test_top_level_permissions_are_contents_read_only(self):
        self.assertRegex(self.text(), r"(?m)^permissions:\n  contents: read\n(?!  )")

    def test_the_analysis_job_has_exactly_the_two_permissions(self):
        text = self.text()
        self.assertRegex(text, r"(?m)^  analysis:$")
        self.assertRegex(text, r"(?m)^    timeout-minutes: 15$")
        self.assertRegex(text, r"(?m)^    permissions:\n      id-token: write\n      contents: read\n(?!      )")
        self.assertEqual(1, len(re.findall(r"(?m)^\s+permissions:", text.split("\njobs:\n")[1])))
        self.assertNotRegex(text, r"(?m)^\s+(?:actions|security-events|pull-requests|packages|statuses|checks|issues): ")

    def test_it_publishes_json_and_uploads_no_sarif_or_artifact(self):
        text = self.text()
        self.assertRegex(text, r"(?m)^          results_format: json$")
        self.assertRegex(text, r"(?m)^          publish_results: true$")
        self.assertNotIn("sarif", text.lower())
        self.assertNotIn("upload-artifact", text)
        self.assertNotIn("codeql", text.lower())

    def test_it_uses_no_secret_and_no_credential_is_kept_by_checkout(self):
        text = self.text()
        self.assertEqual([], secret_references(text))
        self.assertRegex(text, r"(?m)^        with:\n          persist-credentials: false$")


class NugetPublishWorkflowTests(unittest.TestCase):
    """nuget-publish.yml (story #3706, task #3709; spec FR-36, NFR-04, ADR 0010): run by the maker for a staged tag. Job `fetch`
    reads the draft release (the only job with a write permission, no environment, no OIDC token); job `publish` holds the OIDC
    token inside the environment `nuget`, checks the packages and only then asks for a key. Line checks only, stdlib only."""

    FILE = WORKFLOWS / "nuget-publish.yml"
    ACTIONS = ("actions/checkout", "actions/upload-artifact", "actions/download-artifact", "actions/setup-dotnet", "NuGet/login")
    STEP = re.compile(r"(?m)^      - ")

    def text(self) -> str:
        self.assertTrue(self.FILE.is_file(), ".github/workflows/nuget-publish.yml does not exist")
        lines = self.FILE.read_text(encoding="utf-8").splitlines()
        return "\n".join(line for line in lines if not line.strip().startswith("#")) + "\n"

    def jobs(self) -> tuple[str, str]:
        text = self.text()
        self.assertIn("\njobs:\n", text)
        body = "\n" + text.split("\njobs:\n", 1)[1]
        self.assertRegex(body, r"(?m)^  fetch:$")
        self.assertRegex(body, r"(?m)^  publish:$")
        fetch, publish = body.split("\n  publish:\n", 1)
        return fetch.split("\n  fetch:\n", 1)[1], publish

    def steps(self, job: str) -> list[str]:
        self.assertIn("\n    steps:\n", job)
        return [chunk for chunk in self.STEP.split(job.split("\n    steps:\n", 1)[1]) if chunk.strip()]

    def pinned_in_release(self) -> dict[str, str]:
        found = {}
        for line in (WORKFLOWS / "release.yml").read_text(encoding="utf-8").splitlines():
            match = USES.match(line)
            if match and "@" in match.group("ref"):
                repo, sha = match.group("ref").split("@")
                found[repo] = sha
        return found

    @staticmethod
    def run_lines(text: str) -> list[str]:
        """The lines of every `run:` value (one line, or the body of a block)."""
        found, block_column = [], None
        for line in text.splitlines():
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            if block_column is not None:
                if indent > block_column:
                    found.append(line.strip())
                    continue
                block_column = None
            match = RUN_KEY.match(line)
            if match:
                value = match.group("value")
                if re.match(r"^[|>][+-]?\d*[+-]?\s*(?:#.*)?$", value):
                    block_column = len(match.group("indent")) + (2 if line.lstrip().startswith("- ") else 0)
                else:
                    found.append(value)
        return found

    # ---- shape of the workflow
    def test_the_only_trigger_is_a_manual_run_with_one_required_string_input_called_tag(self):
        text = self.text()
        self.assertRegex(text, r"(?m)^on:\n  workflow_dispatch:\n    inputs:\n      tag:\n(?:        .+\n)+(?!      )")
        block = text.split("    inputs:\n", 1)[1].split("\n\n", 1)[0].split("\npermissions:", 1)[0]
        self.assertEqual(["tag"], re.findall(r"(?m)^      ([A-Za-z_][\w-]*):$", block), "exactly one input")
        self.assertRegex(block, r"(?m)^        required: true$")
        self.assertRegex(block, r"(?m)^        type: string$")
        for event in ("push", "pull_request", "pull_request_target", "schedule", "workflow_call", "release", "workflow_run"):
            with self.subTest(event=event):
                self.assertNotRegex(text, rf"(?m)^\s+{event}:")

    def test_top_level_permissions_are_contents_read_and_runs_never_cancel_each_other(self):
        text = self.text()
        self.assertRegex(text, r"(?m)^permissions:\n  contents: read\n(?!  )")
        self.assertRegex(text, r"(?m)^concurrency:\n  group: \S.*\n  cancel-in-progress: false\n(?!  )")

    def test_there_are_exactly_two_jobs_fetch_and_publish_with_publish_after_fetch_and_a_timeout_each(self):
        fetch, publish = self.jobs()
        body = self.text().split("\njobs:\n", 1)[1]
        self.assertEqual(["fetch", "publish"], re.findall(r"(?m)^  ([a-z][\w-]*):$", body))
        self.assertRegex(publish, r"(?m)^    needs: fetch$")
        for name, job in (("fetch", fetch), ("publish", publish)):
            with self.subTest(job=name):
                self.assertRegex(job, r"(?m)^    timeout-minutes: \d+$")
                self.assertRegex(job, r"(?m)^    runs-on: ubuntu-latest$")

    # ---- fetch
    def test_fetch_has_exactly_contents_write_and_neither_an_environment_nor_an_oidc_token(self):
        fetch, _ = self.jobs()
        self.assertRegex(fetch, r"(?m)^    permissions:\n      contents: write\n(?!      )")
        self.assertNotRegex(fetch, r"(?m)^    environment:")
        self.assertNotIn("id-token", fetch)
        self.assertNotIn("actions/checkout", fetch, "the job that may write executes no code of the repository")

    def test_fetch_validates_the_tag_in_its_first_step_before_anything_is_downloaded(self):
        fetch, _ = self.jobs()
        first = self.steps(fetch)[0]
        self.assertIn("run:", first)
        self.assertNotIn("uses:", first)
        self.assertIn("^dotnet-v", first)
        self.assertRegex(first, r"(?m)^          TAG: \$\{\{ inputs\.tag \}\}$")
        self.assertIn("exit 1", first)
        self.assertLess(fetch.index("^dotnet-v"), fetch.index("gh api"))
        self.assertLess(fetch.index("^dotnet-v"), fetch.index("download"))

    def test_the_tag_reaches_the_shell_only_through_env_never_inside_a_run_block(self):
        text = self.text()
        self.assertTrue(self.run_lines(text), "the workflow has run steps")
        self.assertEqual([], [line for line in self.run_lines(text) if "${{" in line])
        self.assertEqual([], event_expression_in_run(text))

    def test_fetch_exposes_the_tag_and_the_version_as_job_outputs(self):
        fetch, _ = self.jobs()
        self.assertRegex(fetch, r"(?m)^    outputs:\n(?:      \w+: .+\n)*      tag: .+\n")
        self.assertRegex(fetch, r"(?m)^      version: .+$")

    def test_fetch_finds_the_draft_with_the_api_because_a_draft_is_not_found_by_the_release_download_command(self):
        fetch, _ = self.jobs()
        self.assertNotRegex(fetch, r"gh release download")
        self.assertIn("gh api", fetch)
        for needle in ("draft", "tag_name", "per_page=100", ".nupkg", "SHA256SUMS.signed"):
            self.assertIn(needle, fetch)

    def test_fetch_uploads_the_download_as_the_artifact_staged_and_fails_when_there_is_nothing(self):
        fetch, _ = self.jobs()
        uploads = [step for step in self.steps(fetch) if "actions/upload-artifact@" in step]
        self.assertEqual(1, len(uploads))
        self.assertRegex(uploads[0], r"(?m)^          name: staged$")
        self.assertRegex(uploads[0], r"(?m)^          if-no-files-found: error$")

    # ---- publish
    def test_publish_runs_in_the_environment_nuget_with_exactly_the_oidc_token_and_read_access(self):
        _, publish = self.jobs()
        self.assertRegex(publish, r"(?m)^    environment: nuget$")
        block = re.search(r"(?m)^    permissions:\n((?:      .+\n)+)", publish)
        self.assertIsNotNone(block, "publish declares its permissions")
        self.assertEqual({"id-token: write", "contents: read"}, {line.strip() for line in block.group(1).splitlines()})
        self.assertEqual(2, len(block.group(1).splitlines()))

    def test_publish_steps_run_in_the_agreed_order_the_check_before_the_login_and_the_login_before_the_push(self):
        _, publish = self.jobs()
        order = ["actions/download-artifact@", "actions/checkout@", "actions/setup-dotnet@", "python3 scripts/check-staged-packages.py", "NuGet/login@",
                 "dotnet nuget push"]
        positions = [publish.index(item) for item in order]
        self.assertEqual(sorted(positions), positions, "the steps are not in the agreed order")
        steps = self.steps(publish)
        self.assertEqual(6, len(steps))
        self.assertEqual(1, publish.count("dotnet nuget push"), "one push command")

    def test_publish_downloads_the_artifact_staged_and_checks_out_only_the_scripts_at_the_tag_without_credentials(self):
        _, publish = self.jobs()
        download = next(step for step in self.steps(publish) if "actions/download-artifact@" in step)
        self.assertRegex(download, r"(?m)^          name: staged$")
        checkout = next(step for step in self.steps(publish) if "actions/checkout@" in step)
        self.assertRegex(checkout, r"(?m)^          ref: \$\{\{ needs\.fetch\.outputs\.tag \}\}$")
        self.assertRegex(checkout, r"(?m)^          sparse-checkout:\s*(?:\|\s*\n\s*)?scripts\s*$")
        self.assertRegex(checkout, r"(?m)^          persist-credentials: false$")

    def test_the_check_step_gets_the_version_through_env_and_reads_the_certificate_file_of_the_tag(self):
        _, publish = self.jobs()
        check = next(step for step in self.steps(publish) if "check-staged-packages.py" in step)
        self.assertRegex(check, r"(?m)^          VERSION: \$\{\{ needs\.fetch\.outputs\.version \}\}$")
        for option in ("--version", "--dir", "--sums", "--certificate scripts/release-certificate.json"):
            self.assertIn(option, check)
        self.assertNotIn("continue-on-error", check)
        self.assertNotIn("|| true", check)

    def test_nuget_login_exists_only_in_publish_takes_the_user_from_a_variable_and_runs_after_the_check(self):
        fetch, publish = self.jobs()
        self.assertNotIn("NuGet/login", fetch)
        self.assertEqual(1, self.text().count("NuGet/login@"))
        login = next(step for step in self.steps(publish) if "NuGet/login@" in step)
        self.assertRegex(login, r"(?m)^          user: \$\{\{ vars\.NUGET_USER \}\}$")
        self.assertRegex(login, r"(?m)^        id: \w+$")

    def test_the_push_skips_duplicates_and_is_the_only_place_that_names_the_api_key(self):
        _, publish = self.jobs()
        push = next(step for step in self.steps(publish) if "dotnet nuget push" in step)
        self.assertIn("--skip-duplicate", push)
        self.assertRegex(push, r"(?m)^          NUGET_API_KEY: \$\{\{ steps\.\w+\.outputs\.NUGET_API_KEY \}\}$")
        other = "".join(step for step in self.steps(publish) if "dotnet nuget push" not in step)
        self.assertNotIn("NUGET_API_KEY", other)
        self.assertNotIn("NUGET_API_KEY", self.jobs()[0])
        self.assertNotRegex(self.text(), r"(?m)^\s*(?:run:\s*)?echo .*NUGET_API_KEY")
        self.assertNotRegex(self.text(), r"set -x|set -o xtrace")

    # ---- supply chain
    def test_no_secret_is_referenced_anywhere(self):
        self.assertEqual([], secret_references(self.text()))

    def test_every_action_is_pinned_to_the_sha_release_yml_uses_and_no_other_action_appears(self):
        text = self.text()
        self.assertEqual([], unpinned_uses(text))
        used = {}
        for line in text.splitlines():
            match = USES.match(line)
            if match:
                repo, sha = match.group("ref").split("@")
                used[repo] = sha
        self.assertEqual(set(self.ACTIONS), set(used))
        known = self.pinned_in_release()
        for repo in self.ACTIONS:
            self.assertEqual(known[repo], used[repo], repo)

    def test_no_step_hides_a_failure(self):
        text = self.text()
        self.assertNotIn("continue-on-error", text)
        self.assertNotIn("|| true", text)


if __name__ == "__main__":
    unittest.main()
