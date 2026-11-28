#!/usr/bin/env python3
"""Pins the spec version: spec/VERSION is the one place it is written, and the conformance driver's
SpecVersion constant and every csharp/src package README must claim the same value. Reads public files only.
The check functions take a repository root, so the negative tests below run them on scratch directories.
Run: python3 scripts/test_spec_version.py (also run by Craticula.Conformance.Tests/SpecVersionTests.cs on `dotnet test`).
"""
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
DRIVER = "csharp/tools/Craticula.Conformance.Driver/Program.cs"
CLAIM_PREFIX = "Implements Craticula spec version "
CLAIM = re.compile(r"^Implements Craticula spec version (\d+\.\d+\.\d+)(?!\d)")
DRIVER_LITERAL = re.compile(r'SpecVersion\s*=\s*"([^"]*)"')


def read_version(root: Path) -> str:
    text = (root / "spec/VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.match(text):
        raise AssertionError(f"spec/VERSION: found {text!r}, expected a MAJOR.MINOR.PATCH version")
    return text


def check_driver(root: Path, expected: str) -> None:
    matches = DRIVER_LITERAL.findall((root / DRIVER).read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise AssertionError(f"{DRIVER}: found {len(matches)} SpecVersion literals, expected exactly 1")
    if matches[0] != expected:
        raise AssertionError(f"{DRIVER}: found SpecVersion {matches[0]!r}, expected {expected!r} (spec/VERSION)")


def package_dirs(root: Path) -> list:
    return sorted(p.name for p in (root / "csharp/src").glob("Craticula.*") if p.is_dir())


def readme_dirs(root: Path) -> list:
    return sorted(p.parent.name for p in (root / "csharp/src").glob("Craticula.*/README.md"))


def check_readme_set(root: Path) -> None:
    packages, readmes = package_dirs(root), readme_dirs(root)
    if packages != readmes:
        missing = sorted(set(packages) - set(readmes))
        extra = sorted(set(readmes) - set(packages))
        raise AssertionError(
            f"csharp/src: package folders and README.md files differ (no README: {missing}, README without folder: {extra})")


def check_readme(root: Path, name: str, expected: str) -> None:
    rel = f"csharp/src/{name}/README.md"
    lines = [ln for ln in (root / rel).read_text(encoding="utf-8").splitlines() if ln.startswith(CLAIM_PREFIX)]
    if len(lines) != 1:
        raise AssertionError(f"{rel}: found {len(lines)} lines starting {CLAIM_PREFIX!r}, expected exactly 1")
    m = CLAIM.match(lines[0])
    found = m.group(1) if m else lines[0][len(CLAIM_PREFIX):].split()[0:1]
    if not m or found != expected:
        raise AssertionError(f"{rel}: found spec version {found!r}, expected {expected!r} (spec/VERSION)")


def check_all_readmes(root: Path, expected: str) -> None:
    check_readme_set(root)
    for name in package_dirs(root):
        check_readme(root, name, expected)


def check_matrix(root: Path, expected: str) -> None:
    """The root README's `## Compatibility` table: header `| Spec version | ... |`, then exactly one data row whose
    first cell is the spec version."""
    rel = "README.md"
    readme = root / rel
    if not readme.is_file():
        raise AssertionError(f"{rel}: file not found")
    lines = readme.read_text(encoding="utf-8").splitlines()
    if "## Compatibility" not in [ln.strip() for ln in lines]:
        raise AssertionError(f"{rel}: no '## Compatibility' section")
    start = lines.index("## Compatibility")
    rows = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        if ln.lstrip().startswith("|"):
            rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    if len(rows) < 3 or not rows[0] or rows[0][0] != "Spec version":
        raise AssertionError(f"{rel}: the Compatibility table must start with a 'Spec version' header, a separator and one row")
    if len(rows) != 3:
        raise AssertionError(f"{rel}: the Compatibility table must hold exactly one data row, found {len(rows) - 2}")
    if rows[2][0] != expected:
        raise AssertionError(f"{rel}: Compatibility row has spec version {rows[2][0]!r}, expected {expected!r} (spec/VERSION)")


class SpecVersionTests(unittest.TestCase):
    def test_version_file_is_semver(self):
        read_version(ROOT)

    def test_driver_constant_matches(self):
        check_driver(ROOT, read_version(ROOT))

    def test_every_package_readme_claims_the_version(self):
        check_all_readmes(ROOT, read_version(ROOT))

    def test_readme_matrix(self):
        check_matrix(ROOT, read_version(ROOT))


class RuntimeSupportTests(unittest.TestCase):
    """Feature 011, US3-AS1 (ADR-0015): the README says which .NET runs the packages, with the check it rests on."""

    def test_readme_states_the_runtime_support_with_its_check(self):
        lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        start = lines.index("## Compatibility")
        section = []
        for ln in lines[start + 1:]:
            if ln.startswith("## "):
                break
            section.append(ln)
        text = " ".join(section)
        for needle in ("net10.0", ".NET 11 runtime", "11.0.100", "2026-11-27"):
            self.assertIn(needle, text)


class CheckerNegativeTests(unittest.TestCase):
    def make_repo(self, version="0.1.0"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name in ("Craticula.A", "Craticula.B"):
            d = root / "csharp/src" / name
            d.mkdir(parents=True)
            (d / "README.md").write_text(f"# {name}\n\nImplements Craticula spec version {version} (the rest).\n", encoding="utf-8")
        drv = root / DRIVER
        drv.parent.mkdir(parents=True)
        drv.write_text(f'class P {{ private const string SpecVersion = "{version}"; }}\n', encoding="utf-8")
        (root / "spec").mkdir()
        (root / "spec/VERSION").write_text(version + "\n", encoding="utf-8")
        return root

    def test_good_repo_passes(self):
        root = self.make_repo()
        check_driver(root, "0.1.0")
        check_all_readmes(root, "0.1.0")

    def test_wrong_readme_version_names_file(self):
        root = self.make_repo()
        (root / "csharp/src/Craticula.B/README.md").write_text("Implements Craticula spec version 0.2.0 (x)\n", encoding="utf-8")
        with self.assertRaises(AssertionError) as cm:
            check_all_readmes(root, "0.1.0")
        self.assertIn("csharp/src/Craticula.B/README.md", str(cm.exception))
        self.assertIn("0.2.0", str(cm.exception))

    def test_missing_line_names_file(self):
        root = self.make_repo()
        (root / "csharp/src/Craticula.A/README.md").write_text("# no claim\n", encoding="utf-8")
        with self.assertRaises(AssertionError) as cm:
            check_all_readmes(root, "0.1.0")
        self.assertIn("csharp/src/Craticula.A/README.md", str(cm.exception))

    def test_new_package_without_readme_fails(self):
        root = self.make_repo()
        (root / "csharp/src/Craticula.C").mkdir()
        with self.assertRaises(AssertionError) as cm:
            check_all_readmes(root, "0.1.0")
        self.assertIn("Craticula.C", str(cm.exception))

    def test_driver_drift_names_file(self):
        root = self.make_repo()
        with self.assertRaises(AssertionError) as cm:
            check_driver(root, "0.2.0")
        self.assertIn(DRIVER, str(cm.exception))

    def test_matrix_good_wrong_and_missing(self):
        root = self.make_repo()
        table = "| Spec version | .NET target |\n|---|---|\n| {} | net10.0 |\n"
        (root / "README.md").write_text("# x\n\n## Compatibility\n\n" + table.format("0.1.0") + "\n## License\n", encoding="utf-8")
        check_matrix(root, "0.1.0")
        (root / "README.md").write_text("# x\n\n## Compatibility\n\n" + table.format("0.2.0"), encoding="utf-8")
        with self.assertRaises(AssertionError) as cm:
            check_matrix(root, "0.1.0")
        self.assertIn("README.md", str(cm.exception))
        self.assertIn("0.2.0", str(cm.exception))
        (root / "README.md").write_text("# x\n\n## License\n", encoding="utf-8")
        with self.assertRaises(AssertionError) as cm:
            check_matrix(root, "0.1.0")
        self.assertIn("README.md", str(cm.exception))
        self.assertIn("Compatibility", str(cm.exception))

    def test_bad_version_file_fails(self):
        root = self.make_repo("0.1.0")
        (root / "spec/VERSION").write_text("v1\n", encoding="utf-8")
        with self.assertRaises(AssertionError) as cm:
            read_version(root)
        self.assertIn("spec/VERSION", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
