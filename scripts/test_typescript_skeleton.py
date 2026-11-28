#!/usr/bin/env python3
"""Pins the TypeScript skeleton's repository-level facts (feature 012): the package, the compiler settings, the lock file,
Dependabot and the README. The ADR and the approved-stack record live under docs/, which the public mirror strips, so those
tests skip when docs/ is absent. Run: python3 scripts/test_typescript_skeleton.py
(also run by Craticula.Conformance.Tests/TypescriptSkeletonTests.cs).
Scenario map (cst-feature coverage reads these ids): US1-AS2 US1-AS3 US1-AS4 US1-AS5 US1-AS6 US3-AS5 (feature 012); US4-AS1 US4-AS3 US4-AS4 (feature 013).
US1-AS1 (npm ci, build, test), US2-* and US3-AS1..AS4 are proven by the node tests in typescript/test and the runner run in CI.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "typescript"
ADR = next(iter(sorted((ROOT / "docs" / "adr").glob("*typescript*.md"))), None) if (ROOT / "docs" / "adr").is_dir() else None
STACK = ROOT / "docs" / "compliance" / "tech-stack.approved.md"
PRIVATE = "docs/ is private and stripped from the public mirror"


def package():
    return json.loads((TS / "package.json").read_text(encoding="utf-8"))


class PackageTests(unittest.TestCase):
    def test_US1_AS2_the_package_is_private_esm_declares_node_22_and_has_no_runtime_dependency(self):
        p = package()
        self.assertIs(p.get("private"), True)
        self.assertEqual("module", p.get("type"))
        self.assertEqual(">=22", p.get("engines", {}).get("node"))
        self.assertNotIn("dependencies", p)
        self.assertNotIn("peerDependencies", p)
        self.assertNotIn("optionalDependencies", p)
        self.assertLessEqual(len(p.get("devDependencies", {})), 3)

    def test_US1_AS2_development_dependencies_are_pinned_exactly(self):
        for name, version in package()["devDependencies"].items():
            with self.subTest(name=name):
                self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_US1_AS3_the_compiler_runs_in_strict_mode(self):
        options = json.loads((TS / "tsconfig.json").read_text(encoding="utf-8"))["compilerOptions"]
        self.assertIs(options.get("strict"), True)
        self.assertIs(options.get("noUncheckedIndexedAccess"), True)
        self.assertEqual("NodeNext", options.get("module"))

    def test_US1_AS3_the_build_script_fails_on_any_error(self):
        self.assertEqual("tsc -p tsconfig.json", package()["scripts"]["build"])
        self.assertNotIn("noEmitOnError", json.dumps(json.loads((TS / "tsconfig.json").read_text(encoding="utf-8"))))

    def test_US1_AS6_the_lock_file_matches_package_json_and_no_script_runs_on_install(self):
        lock = json.loads((TS / "package-lock.json").read_text(encoding="utf-8"))
        root = lock["packages"][""]
        self.assertEqual(package()["devDependencies"], root["devDependencies"])
        self.assertEqual(3, lock["lockfileVersion"])
        self.assertIn("ignore-scripts=true", (TS / ".npmrc").read_text(encoding="utf-8"))

    def test_US3_AS5_the_readme_says_the_driver_is_a_skeleton_covering_one_family(self):
        readme = (TS / "README.md").read_text(encoding="utf-8")
        for needle in ("skeleton", "sort-paging", "PostgreSQL", "not published"):
            self.assertIn(needle, readme)

    def test_US4_AS1_npm_test_prints_line_coverage_of_src_and_fails_below_90_percent(self):
        script = package()["scripts"]["test"]
        for needle in ("--experimental-test-coverage", "--test-coverage-lines=90", 'dist/src/**'):
            self.assertIn(needle, script)

    def test_US4_AS3_there_is_still_no_runtime_dependency_and_at_most_three_development_dependencies(self):
        p = package()
        self.assertNotIn("dependencies", p)
        self.assertLessEqual(len(p["devDependencies"]), 3)

    def test_the_driver_reads_no_file_so_it_cannot_answer_from_the_fixture_tree(self):
        for path in (TS / "src").glob("*.ts"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                for needle in ("node:fs", 'from "fs"', "readFile", "node:path", "spec/fixtures"):
                    self.assertNotIn(needle, text)


class DependabotTests(unittest.TestCase):
    def test_US1_AS5_dependabot_has_an_npm_entry_for_typescript_with_the_14_day_cooldown(self):
        text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        match = re.search(r"(?m)^ {2}- package-ecosystem: npm\n((?: {4}.*\n|\n)+)", text)
        self.assertIsNotNone(match, "no npm ecosystem in dependabot.yml")
        block = match.group(1)
        self.assertRegex(block, r"(?m)^    directory: /typescript$")
        self.assertRegex(block, r"(?m)^    cooldown:\n      default-days: 14$")


@unittest.skipUnless(ADR is not None and STACK.exists(), PRIVATE)
class DecisionRecordTests(unittest.TestCase):
    def test_US1_AS4_the_adr_is_accepted_public_and_records_each_decision_with_its_reason(self):
        text = ADR.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^Status: Accepted\b")
        self.assertRegex(text, r"(?m)^Classification: Public\b")
        for needle in ("typescript/", "ts-v", "Node 22", "ES modules", "node:test", "no runtime dependenc"):
            self.assertIn(needle, text)
        self.assertGreaterEqual(len(re.findall(r"(?i)\bbecause\b|\breason\b", text)), 5)
        self.assertNotIn("docs/", text)

    def test_US1_AS5_the_approved_stack_lists_the_typescript_port_toolchain(self):
        text = STACK.read_text(encoding="utf-8")
        for needle in ("typescript", "@types/node", "node:test"):
            self.assertIn(needle, text.lower() if needle == "typescript" else text)


class ThreatModelTests(unittest.TestCase):
    MODEL = ROOT / "docs" / "architecture" / "threat-model.md"

    @unittest.skipUnless((ROOT / "docs").is_dir(), PRIVATE)
    def test_US4_AS4_the_threat_model_has_the_typescript_request_parser_rows(self):
        text = self.MODEL.read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if "spec 013" in line and line.startswith("|")]
        stride = " ".join(rows).lower()
        for needle in ("tampering", "denial of service", "information disclosure"):
            self.assertIn(needle, stride)
        for needle in ("identifier", "nesting", "error message"):
            self.assertIn(needle, " ".join(rows).lower())


if __name__ == "__main__":
    unittest.main()
