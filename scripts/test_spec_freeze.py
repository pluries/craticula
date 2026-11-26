#!/usr/bin/env python3
"""Pins the spec-freeze check (scripts/check-spec-freeze.py, feature 008) on synthetic trees.

Each test builds a small repository layout in a temporary folder, runs the check against it with --root and reads the
report. Run: python3 scripts/test_spec_freeze.py (also run by Craticula.Conformance.Tests/SpecFreezeTests.cs).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = HERE / "check-spec-freeze.py"
GAPS = REPO / "docs" / "specs" / "008-spec-freeze-criteria" / "gaps.md"

# Scenario map (cst-feature coverage reads these ids): US1-AS1 US1-AS2 US1-AS3 US1-AS4 US2-AS1 US2-AS2 US2-AS3 US2-AS4
# US2-AS5 US3-AS1 US3-AS2 US3-AS3, one test method each, named after the scenario.
IDS = ["F-1", "F-2", "F-3", "F-4", "F-5", "F-6", "F-7"]

RUNNER_DOC = """# Conformance runner

## 1. What this tier grades, and what it does not

**Graded:** every artifact.

**Not graded here**:

| Fixture content | Why not | Graded by |
|---|---|---|
| `dataset.json` / `expectedRows.json` (T-1b) | needs a database | integration tier |

## 2. The protocol
"""

VERSIONING = "# Versioning\n\n## Freezing the specification\n\n" + "\n".join(f"- **{i}** a criterion" for i in IDS) + "\n"


def build(root: Path, *, version="0.3.0", runner_doc=RUNNER_DOC, versioning=VERSIONING, semantics="# Semantics\n") -> None:
    spec = root / "spec"
    (spec / "fixtures" / "cat" / "001-ok" / "expected").mkdir(parents=True)
    (spec / "VERSION").write_text(version + "\n")
    for name in ("ir.schema.json", "grid-schema.schema.json"):
        (spec / name).write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}))
    (spec / "semantics.md").write_text(semantics)
    (spec / "conformance-runner.md").write_text(runner_doc)
    (root / "VERSIONING.md").write_text(versioning)
    fx = spec / "fixtures" / "cat" / "001-ok"
    for name in ("description.md", "agGridRequest.json", "schema.json"):
        (fx / name).write_text("{}")
    (fx / "expected" / "postgres.artifact.json").write_text("{}")


def check(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True, text=True, timeout=60,
    )


def line(output: str, criterion: str) -> str:
    return next(l for l in output.splitlines() if l.startswith(criterion + " "))


class SpecFreezeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def snapshot(self):
        return sorted((str(p.relative_to(self.root)), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file())

    def test_US2_AS1_report_has_one_line_per_criterion_and_exit_1_while_one_is_unmet(self):
        build(self.root, runner_doc=RUNNER_DOC.replace(
            "| `dataset.json`", "| `expected/rejection.json` (SEC-6) | not a compiled artifact | own tests |\n| `dataset.json`"))
        result = check(self.root)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        for criterion in IDS:
            self.assertRegex(line(result.stdout, criterion), r" (met|UNMET) ")
        self.assertIn("UNMET", line(result.stdout, "F-6"))

    def test_US2_AS2_a_tree_where_every_criterion_holds_exits_0(self):
        build(self.root)
        result = check(self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for criterion in IDS:
            self.assertIn(" met ", line(result.stdout, criterion))

    def test_US2_AS3_a_fixture_folder_without_any_expected_file_breaks_only_F5_and_names_it(self):
        build(self.root)
        orphan = self.root / "spec" / "fixtures" / "cat" / "002-orphan"
        (orphan / "expected").mkdir(parents=True)
        for name in ("description.md", "agGridRequest.json", "schema.json"):
            (orphan / name).write_text("{}")
        result = check(self.root)
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("UNMET", line(result.stdout, "F-5"))
        self.assertIn("cat/002-orphan", line(result.stdout, "F-5"))
        for criterion in ("F-1", "F-2", "F-3", "F-4", "F-6", "F-7"):
            self.assertIn(" met ", line(result.stdout, criterion))

    def test_US2_AS3_a_fixture_folder_missing_a_required_file_breaks_F4(self):
        build(self.root)
        (self.root / "spec" / "fixtures" / "cat" / "001-ok" / "description.md").unlink()
        result = check(self.root)
        self.assertIn("UNMET", line(result.stdout, "F-4"))
        self.assertIn("cat/001-ok", line(result.stdout, "F-4"))

    def test_US2_AS3_a_rejection_only_folder_is_not_an_orphan(self):
        build(self.root)
        folder = self.root / "spec" / "fixtures" / "cat" / "002-reject"
        (folder / "expected").mkdir(parents=True)
        for name in ("description.md", "agGridRequest.json", "schema.json"):
            (folder / name).write_text("{}")
        (folder / "expected" / "rejection.json").write_text("{}")
        self.assertIn(" met ", line(check(self.root).stdout, "F-5"))

    def test_US2_AS3_an_unparseable_version_is_a_failed_criterion_not_a_crash(self):
        build(self.root, version="one.two")
        result = check(self.root)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("UNMET", line(result.stdout, "F-1"))
        self.assertNotIn("Traceback", result.stderr)

    def test_US2_AS3_a_schema_that_is_not_json_breaks_F2(self):
        build(self.root)
        (self.root / "spec" / "ir.schema.json").write_text("{ not json")
        self.assertIn("UNMET", line(check(self.root).stdout, "F-2"))

    def test_US2_AS3_a_todo_marker_in_semantics_breaks_F3(self):
        build(self.root, semantics="# Semantics\n\nTODO decide this rule\n")
        self.assertIn("UNMET", line(check(self.root).stdout, "F-3"))

    def test_US2_AS3_a_criterion_missing_from_the_versioning_section_breaks_F7(self):
        build(self.root, versioning=VERSIONING.replace("- **F-4** a criterion\n", ""))
        result = check(self.root)
        self.assertIn("UNMET", line(result.stdout, "F-7"))
        self.assertIn("F-4", line(result.stdout, "F-7"))

    def test_US2_AS4_the_check_writes_nothing(self):
        build(self.root)
        before = self.snapshot()
        check(self.root)
        self.assertEqual(before, self.snapshot())

    def test_US2_AS4_the_script_imports_only_the_standard_library(self):
        imports = {
            l.split()[1].split(".")[0]
            for l in SCRIPT.read_text().splitlines()
            if l.startswith(("import ", "from "))
        }
        self.assertTrue(imports <= set(sys.stdlib_module_names), imports - set(sys.stdlib_module_names))

    @unittest.skipUnless(GAPS.exists(), "docs/ is private and stripped from the public mirror")
    def test_US3_AS1_the_real_tree_reports_only_criteria_that_gaps_md_resolves(self):
        result = check(REPO)
        gaps = GAPS.read_text()
        unmet = [l.split()[0] for l in result.stdout.splitlines() if " UNMET " in l]
        for criterion in unmet:
            self.assertIn(f"| {criterion} |", gaps, f"{criterion} is unmet and has no row in gaps.md")

    def freeze_section(self):
        text = (REPO / "VERSIONING.md").read_text(encoding="utf-8")
        start = text.index("## Freezing the specification")
        return text[start:]

    def test_US1_AS1_the_real_versioning_section_lists_a_criterion_for_each_part_of_the_spec(self):
        section = self.freeze_section()
        for part in ("IR schema", "GridSchema schema", "semantics.md", "fixtures"):
            self.assertIn(part, section)
        self.assertIn(" met ", line(check(REPO).stdout, "F-7"))

    def test_US1_AS2_the_real_versioning_section_states_what_each_kind_of_spec_version_promises(self):
        section = self.freeze_section()
        for kind in ("**Patch**", "**Minor**", "**Major**", "does not promise"):
            self.assertIn(kind, section)

    def test_US1_AS3_the_spec_readme_links_to_the_criteria_and_does_not_restate_them(self):
        readme = (REPO / "spec" / "README.md").read_text(encoding="utf-8")
        self.assertIn("VERSIONING.md#freezing-the-specification", readme)
        self.assertNotIn("F-6", readme)

    def test_US1_AS4_the_real_criteria_name_what_the_runner_grades_and_what_stays_out(self):
        section = self.freeze_section()
        for term in ("rejection.json", "rowStream.json", "execution equality"):
            self.assertIn(term, section)

    def test_US2_AS5_dotnet_test_runs_this_file(self):
        wrapper = REPO / "csharp" / "tests" / "Craticula.Conformance.Tests" / "SpecFreezeTests.cs"
        self.assertIn("scripts/test_spec_freeze.py", wrapper.read_text(encoding="utf-8"))

    @unittest.skipUnless(GAPS.exists(), "docs/ is private and stripped from the public mirror")
    def test_US3_AS2_gaps_md_gives_each_known_candidate_an_outcome(self):
        gaps = GAPS.read_text(encoding="utf-8")
        for candidate in ("rejection.json", "rowStream.json", "Execution equality"):
            row = next(l for l in gaps.splitlines() if l.startswith("|") and candidate in l)
            self.assertRegex(row, r"closed before the freeze|covered by a named test tier|accepted")

    @unittest.skipUnless(GAPS.exists(), "docs/ is private and stripped from the public mirror")
    def test_US3_AS3_every_accepted_gap_carries_its_reason(self):
        for l in GAPS.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in l.strip("|").split("|")]
            if l.startswith("|") and len(cells) == 4 and cells[2].startswith("accepted"):
                self.assertGreater(len(cells[3]), 20, l)


if __name__ == "__main__":
    unittest.main()
