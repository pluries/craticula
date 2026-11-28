#!/usr/bin/env python3
"""Read-only check of the spec-freeze criteria (feature 008). Python standard library only.

Prints one line per criterion, `F-n <name> met|UNMET <evidence>`, and exits 0 when every criterion is met, 1 when any is
unmet. It writes nothing. The criteria are written in VERSIONING.md, section "Freezing the specification"; criterion F-7
checks that every id below is listed there, so the document and this script cannot drift apart.

Usage: python3 scripts/check-spec-freeze.py [--root <repository root>]
"""
import argparse
import json
import re
import sys
from pathlib import Path

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
REQUIRED_FIXTURE_FILES = ("description.md", "agGridRequest.json", "schema.json")
# Content the runner cannot grade as an artifact: the runner document lists it as "not graded here".
UNGRADED_ROWS = ("rejection.json", "rowStream.json")
MARKER = re.compile(r"\b(TODO|TBD|FIXME)\b")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CRITERIA = ("F-1", "F-2", "F-3", "F-4", "F-5", "F-6", "F-7")


def fixture_folders(root: Path):
    fixtures = root / "spec" / "fixtures"
    if not fixtures.is_dir():
        return []
    return sorted(
        d for category in fixtures.iterdir() if category.is_dir() and category.name != "schemas"
        for d in category.iterdir() if d.is_dir()
    )


def label(root: Path, folder: Path) -> str:
    return folder.relative_to(root / "spec" / "fixtures").as_posix()


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def names(items, limit=5) -> str:
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def f1_version(root: Path):
    version = read(root / "spec" / "VERSION").strip()
    if SEMVER.match(version):
        return True, f"spec/VERSION reads {version}"
    return False, f"spec/VERSION is not MAJOR.MINOR.PATCH: {version!r}"


def f2_schemas(root: Path):
    bad = []
    for name in ("ir.schema.json", "grid-schema.schema.json"):
        try:
            document = json.loads(read(root / "spec" / name))
        except ValueError:
            bad.append(f"{name} is not valid JSON")
            continue
        if not isinstance(document, dict) or document.get("$schema") != DRAFT_2020_12:
            bad.append(f"{name} does not declare JSON Schema draft 2020-12")
    return (not bad), ("; ".join(bad) if bad else "both schemas parse and declare draft 2020-12")


def f3_semantics(root: Path):
    text = read(root / "spec" / "semantics.md")
    if not text:
        return False, "spec/semantics.md is missing or empty"
    marked = [str(n) for n, l in enumerate(text.splitlines(), 1) if MARKER.search(l)]
    if marked:
        return False, "open marker on line " + names(marked)
    return True, "no TODO, TBD or FIXME marker"


def f4_shape(root: Path):
    broken = []
    folders = fixture_folders(root)
    for folder in folders:
        missing = [n for n in REQUIRED_FIXTURE_FILES if not (folder / n).is_file()]
        if not (folder / "expected").is_dir():
            missing.append("expected/")
        if missing:
            broken.append(f"{label(root, folder)} lacks {'/'.join(missing)}")
    if broken:
        return False, names(broken)
    return True, f"{len(folders)} fixture folders carry the required files"


def f5_no_orphan(root: Path):
    orphans = []
    folders = fixture_folders(root)
    for folder in folders:
        expected = folder / "expected"
        present = expected.is_dir()
        has_graded = present and any(expected.glob("*.artifact.json"))
        has_rejection = present and (expected / "rejection.json").is_file()
        has_bytes = present and (folder / "rowStream.json").is_file() and any(expected.glob("export.*"))
        if not (has_graded or has_rejection or has_bytes):
            orphans.append(label(root, folder))
    if orphans:
        return False, "no expected artifact, rejection or export bytes: " + names(orphans)
    return True, f"each of {len(folders)} fixture folders has something to be graded against"


def f6_runner_grades_all(root: Path):
    text = read(root / "spec" / "conformance-runner.md")
    start = text.find("**Not graded here**")
    if start < 0:
        return False, "spec/conformance-runner.md has no 'Not graded here' list"
    section = text[start:]
    end = re.search(r"^## ", section, re.M)
    section = section[: end.start()] if end else section
    ungraded = [needle for needle in UNGRADED_ROWS if needle in section]
    if ungraded:
        return False, "the runner does not grade " + ", ".join(ungraded)
    return True, "the runner grades rejections and writer bytes; only execution equality is left to other tiers"


def f7_documented(root: Path):
    text = read(root / "VERSIONING.md")
    match = re.search(r"^## Freezing the specification\s*$", text, re.M)
    if not match:
        return False, "VERSIONING.md has no 'Freezing the specification' section"
    section = text[match.end():]
    end = re.search(r"^## ", section, re.M)
    section = section[: end.start()] if end else section
    missing = [c for c in CRITERIA if c not in section]
    if missing:
        return False, "not listed in VERSIONING.md: " + ", ".join(missing)
    return True, "VERSIONING.md lists every criterion"


CHECKS = (
    ("F-1", "version-file", f1_version),
    ("F-2", "schemas-valid", f2_schemas),
    ("F-3", "semantics-closed", f3_semantics),
    ("F-4", "fixture-shape", f4_shape),
    ("F-5", "no-orphan-fixture", f5_no_orphan),
    ("F-6", "runner-grades-all-tiers", f6_runner_grades_all),
    ("F-7", "criteria-documented", f7_documented),
)


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Read-only check of the spec-freeze criteria.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    root = parser.parse_args(argv).root.resolve()
    failed = 0
    for criterion, name, check in CHECKS:
        try:
            ok, evidence = check(root)
        except Exception as error:  # a broken input is a failed criterion, never a crash
            ok, evidence = False, f"check failed: {error}"
        failed += 0 if ok else 1
        print(f"{criterion} {name} {'met' if ok else 'UNMET'} {evidence}")
    print(f"{len(CHECKS) - failed} of {len(CHECKS)} criteria met")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
