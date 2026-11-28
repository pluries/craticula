#!/usr/bin/env python3
"""Pins the SEC-2 lint for the TypeScript query builders (scripts/lint-sec2-ts.py), feature 014 US4, with synthetic TypeScript trees.

Each folder under scripts/lint-sec2-ts-fixtures/ is one tiny tree linted with --root. Run: python3 scripts/test_lint_sec2_ts.py
(also run by Craticula.Conformance.Tests/Sec2TsLintTests.cs on every `dotnet test`).
Scenario map (cst-feature coverage reads these ids): US4-AS1 US4-AS2 US4-AS3 US4-AS4.
"""
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = HERE / "lint-sec2-ts.py"
FIXTURES = HERE / "lint-sec2-ts-fixtures"
NO_ALLOWLIST = FIXTURES / "no-allowlist.txt"


def lint(case: str | None = None, *paths: str, allowlist: Path | None = NO_ALLOWLIST) -> subprocess.CompletedProcess:
    command = [sys.executable, str(SCRIPT)]
    if case is not None:
        # fixtures end in .ts.fixture, so the SonarQube analysis of the repository does not read their deliberate defects as code
        command += ["--root", str(FIXTURES / case)]
        paths = paths or tuple(sorted(file.relative_to(FIXTURES / case).as_posix() for file in (FIXTURES / case).rglob("*.ts.fixture")))
    if allowlist is not None:
        command += ["--allowlist", str(allowlist)]
    return subprocess.run([*command, *paths], capture_output=True, text=True, encoding="utf-8", timeout=60)


def findings(result: subprocess.CompletedProcess) -> list[str]:
    return [line for line in result.stdout.splitlines() if ": SEC-2: " in line]


class RealCode(unittest.TestCase):
    def test_US4_AS1_the_typescript_query_builders_are_clean_and_the_pass_line_counts_files(self):
        result = lint(allowlist=None)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"PASS: SEC-2 lint \(TypeScript\), \d+ files")


class NegativeFixtures(unittest.TestCase):
    def test_US4_AS1_a_builder_that_quotes_binds_and_uses_constants_is_clean(self):
        self.assertEqual(0, lint("clean").returncode)

    def test_US4_AS2_a_request_value_interpolated_into_the_text_is_a_finding_with_file_line_and_expression(self):
        result = lint("value-interpolated")
        self.assertEqual(1, result.returncode)
        self.assertEqual(["typescript/src/sql/builder.ts.fixture:4: SEC-2: value - interpolated into query text and not a placeholder, a quoted identifier or a constant"], findings(result))

    def test_US4_AS2_a_name_concatenated_from_a_variable_is_a_finding(self):
        result = lint("name-concatenated")
        self.assertEqual(1, result.returncode)
        self.assertTrue(all(finding.startswith("typescript/src/sql/builder.ts.fixture:5: SEC-2: ") and "concatenated" in finding for finding in findings(result)), result.stdout)

    def test_US4_AS2_an_unquoted_identifier_in_a_template_is_a_finding(self):
        result = lint("unquoted-identifier")
        self.assertEqual(1, result.returncode)
        self.assertIn("field.sql.text", result.stdout)

    def test_US4_AS2_an_escaped_value_in_the_text_is_a_finding_because_escaping_is_not_binding(self):
        result = lint("escaped-value")
        self.assertEqual(1, result.returncode)
        self.assertIn("escapePattern(pattern)", result.stdout)

    def test_US4_AS2_a_string_method_that_only_shares_a_name_with_a_dialect_method_is_a_finding(self):
        result = lint("member-call")
        self.assertEqual(1, result.returncode)
        self.assertIn("request.filter.field.substring(0)", result.stdout)

    def test_US4_AS2_a_value_appended_with_no_literal_next_to_it_is_a_finding(self):
        result = lint("bare-append")
        self.assertEqual(1, result.returncode)
        self.assertIn("appended to query text", result.stdout)

    def test_US4_AS2_a_value_pushed_into_a_list_that_is_joined_into_the_text_is_a_finding(self):
        result = lint("push-argument")
        self.assertEqual(1, result.returncode)
        self.assertIn("items.join", result.stdout)

    def test_US4_AS2_an_output_name_spliced_without_quoting_is_a_finding(self):
        result = lint("unquoted-output-name")
        self.assertEqual(1, result.returncode)
        self.assertIn("outputName(aggregation)", result.stdout)

    def test_US4_AS2_a_request_value_used_as_a_document_key_is_a_finding(self):
        result = lint("doc-key-from-value")
        self.assertEqual(1, result.returncode)
        self.assertIn("used as a document key", result.stdout)

    def test_US4_AS2_a_request_object_spread_into_a_document_is_a_finding(self):
        result = lint("spread-request")
        self.assertEqual(1, result.returncode)
        self.assertIn("...request", result.stdout)

    def test_US4_AS2_a_server_side_script_operator_is_a_finding(self):
        result = lint("script-operator")
        self.assertEqual(1, result.returncode)
        self.assertIn("$where", result.stdout)

    def test_US4_AS2_a_key_given_to_a_map_constructor_is_checked_like_a_doc_key(self):
        result = lint("new-map-key")
        self.assertEqual(1, result.returncode)
        self.assertIn("request.key", result.stdout)

    def test_US4_AS2_an_escaped_value_is_still_a_finding_in_key_position(self):
        result = lint("escaper-key")
        self.assertEqual(1, result.returncode)
        self.assertIn("escapeRegex(request.key)", result.stdout)

    def test_US4_AS2_a_script_operator_written_as_a_template_literal_is_a_finding(self):
        result = lint("template-script")
        self.assertEqual(1, result.returncode)
        self.assertIn("$function", result.stdout)

    def test_an_error_message_may_carry_the_request_value(self):
        self.assertEqual(0, lint("message-exempt").returncode)


class Allowlist(unittest.TestCase):
    def test_US4_AS3_an_entry_that_matches_nothing_fails_the_run(self):
        result = lint("stale-entry", allowlist=FIXTURES / "stale-entry.allowlist.txt")
        self.assertEqual(1, result.returncode)
        self.assertIn("stale entry", result.stderr)

    def test_a_trust_entry_accepts_exactly_its_expression(self):
        allow = FIXTURES / "value-interpolated.allowlist.txt"
        allow.write_text("trust typescript/src/sql/builder.ts.fixture | value | a reason\n", encoding="utf-8")
        try:
            self.assertEqual(0, lint("value-interpolated", allowlist=allow).returncode)
        finally:
            allow.unlink()

    def test_a_malformed_entry_is_an_environment_error(self):
        result = lint("clean", allowlist=FIXTURES / "malformed-allowlist.txt")
        self.assertEqual(2, result.returncode)

    def test_a_missing_scope_path_is_an_environment_error(self):
        self.assertEqual(2, lint("clean", "typescript/src/nowhere").returncode)


class Wiring(unittest.TestCase):
    def test_US4_AS4_the_public_ci_runs_the_lint_and_the_runner_for_every_declared_dialect(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/lint-sec2-ts.py", ci)
        for dialect in ("postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search"):
            self.assertIn(f'--only "*#{dialect}"', ci)

    def test_US4_AS4_the_jenkinsfile_runs_the_lint_next_to_the_csharp_one(self):
        jenkinsfile = ROOT / "Jenkinsfile"
        if not jenkinsfile.exists():
            self.skipTest("the Jenkinsfile is private and absent from the public mirror")
        self.assertIn("lint-sec2-ts.py", jenkinsfile.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
