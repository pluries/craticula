#!/usr/bin/env python3
"""Pins the .NET 11 decision records (feature 010): the ADR, the SDK 11 run record and the consequences table.

They live under docs/, which the public mirror strips, so every test skips when the files are absent.
Run: python3 scripts/test_dotnet11_decision.py (also run by Craticula.Conformance.Tests/Dotnet11DecisionTests.cs).
Scenario map (cst-feature coverage reads these ids): US1-AS1 US1-AS2 US1-AS3 US1-AS5 US2-AS1 US2-AS2 US2-AS3 US2-AS4
US2-AS5 US3-AS1 US3-AS2 US3-AS3 US3-AS4. US1-AS4 (no tracked file outside docs/ changed by the run) is checked by git diff in evidence.md.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR = next(iter(sorted((ROOT / "docs" / "adr").glob("*dotnet-11*.md"))), None) if (ROOT / "docs" / "adr").is_dir() else None
RECORD = ROOT / "docs" / "specs" / "010-dotnet-11-decision" / "sdk11-run.md"
PRIVATE = "docs/ is private and stripped from the public mirror"
STANCES = ("multi-target", "move to net11.0", "stay on net10.0")


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end():]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def csharp_projects():
    found = []
    for base in ("csharp", "examples"):
        for p in (ROOT / base).rglob("*.csproj"):
            if not {"bin", "obj", "node_modules"} & set(p.parts):
                found.append(p.stem)
    return sorted(found)


@unittest.skipUnless(ADR and RECORD.exists(), PRIVATE)
class DotnetDecisionRecords(unittest.TestCase):
    def setUp(self):
        self.adr = read(ADR)
        self.record = read(RECORD)

    def test_US1_AS1_the_record_names_the_sdk_and_the_build_result(self):
        self.assertIn("11.0.100", self.record)
        self.assertRegex(self.record, r"0 Warning\(s\)")
        self.assertRegex(self.record, r"0 Error\(s\)")
        self.assertIn("-warnaserror", self.record)

    def test_US1_AS2_the_record_has_test_counts_per_project_for_both_sdks(self):
        table = section(self.record, "Offline tests")
        rows = [l for l in table.splitlines() if re.match(r"\|\s*Craticula\.", l)]
        self.assertGreaterEqual(len(rows), 13)
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            self.assertGreaterEqual(len(cells), 3, row)
            self.assertTrue(all(re.search(r"\d", c) for c in cells[1:3]), row)
        self.assertIn("SDK 10", table)
        self.assertIn("SDK 11", table)

    def test_US1_AS3_a_difference_is_recorded_with_project_cause_and_origin(self):
        failures = section(self.record, "Differences")
        self.assertIn("FilterNodeValidatorIsoInstantTests", failures)
        self.assertIn("Craticula.Core.Tests", failures)
        self.assertRegex(failures, r"(?i)runtime")
        self.assertIn("24:00", failures)

    def test_US1_AS5_the_record_says_how_the_sdk_was_obtained_and_selected(self):
        how = section(self.record, "Method")
        self.assertIn("dotnet-install", how)
        self.assertIn("global.json", how)
        self.assertRegex(how, r"(?i)scratch")

    def test_US2_AS1_the_adr_is_accepted_public_and_names_exactly_one_stance(self):
        self.assertRegex(self.adr, r"(?m)^Status: Accepted\b")
        self.assertRegex(self.adr, r"(?m)^Classification: Public\b")
        decision = section(self.adr, "Decision").lower()
        named = [s for s in STANCES if s in decision]
        self.assertEqual(1, len(named), named)

    def test_US2_AS2_the_adr_names_a_review_date_with_a_reason(self):
        decision = section(self.adr, "Decision")
        match = re.search(r"[Rr]eview(?:ed)? (?:on|by) (\d{4}-\d{2}-\d{2})", decision)
        self.assertIsNotNone(match, decision)
        self.assertRegex(decision, r"(?i)because|since|after")

    def test_US2_AS3_the_adr_cites_the_record_and_the_support_end_dates(self):
        for needle in ("sdk11-run.md", "2028-11-14", "11.0.100"):
            self.assertIn(needle, self.adr)

    def test_US2_AS4_each_rejected_stance_has_a_reason(self):
        alternatives = section(self.adr, "Alternatives").lower()
        for rejected in ("multi-target", "move to net11.0"):
            self.assertIn(rejected, alternatives)
        self.assertGreaterEqual(len(re.findall(r"(?i)why not", alternatives)), 2)

    def test_US2_AS5_the_adr_holds_nothing_private(self):
        for needle in ("pluries.dev/admin", "password", "token", "BEGIN PRIVATE"):
            self.assertNotIn(needle, self.adr)
        self.assertNotRegex(self.adr, r"\b(192\.168|172\.(1[6-9]|2\d|3[01])|10\.(?!0\.))\d+\.\d+")

    def test_US3_AS1_every_project_has_a_row_in_the_consequences_table(self):
        table = section(self.adr, "Consequences by project")
        missing = [p for p in csharp_projects() if p not in table]
        self.assertEqual([], missing)
        self.assertGreaterEqual(len(csharp_projects()), 30)

    def test_US3_AS2_the_adapters_and_the_dependabot_hold_are_addressed(self):
        table = section(self.adr, "Consequences by project")
        for needle in ("Dependabot", "Microsoft.EntityFrameworkCore", "Craticula.Dapper", "Craticula.EntityFrameworkCore"):
            self.assertIn(needle, table)

    def test_US3_AS3_the_files_naming_dotnet_10_are_listed_as_follow_ups(self):
        follow = section(self.adr, "Follow-ups")
        for needle in ("global.json", "Directory.Build.props", "ci.yml", "Dockerfile", "tech-stack.approved.md"):
            self.assertIn(needle, follow)

    def test_US3_AS4_an_approved_stack_entry_is_listed_or_declared_not_needed(self):
        follow = section(self.adr, "Follow-ups")
        self.assertRegex(follow, r"(?i)approved.stack")


if __name__ == "__main__":
    unittest.main()
