#!/usr/bin/env python3
"""Tests of the real translation tree `site/i18n/` (spec 004-site-languages, task T020a): the checks of `site_i18n.check_site` run over the
files that are committed, not over a fixture. The default mode finds nothing wrong in what exists; the complete mode (every document of every
declared language exists) runs only when `i18n.complete` is true or a language is enabled, so `main` is not red before the maker approves.
A missing `approvals.json` means no approvals. The counts per language are printed. Offline, standard library only.
Run: python3 scripts/test_site_i18n_content.py
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_i18n as si  # noqa: E402
from site_test_support import DOCUMENT_COUNT, ENCODING, ROOT, STATE_WORDS  # noqa: E402

SITE = "site"
SITE_FILE = ROOT / SITE / "site.json"
ENGLISH = "en"
SCOPE = "scope"
SLUG = "slug"
PAGES = "pages"
ENGLISH_SCOPE = ("semantics", "spec", "grid-schema", "ir-schema", "performance")
SITE_ENTRIES = 26
SCOPE_VALUES = ("translated", "english")


def config() -> dict:
    return json.loads(SITE_FILE.read_text(encoding=ENCODING))


def declared_languages() -> list[str]:
    return [code for code in config()["languages"] if code != ENGLISH]


def complete_mode_applies() -> bool:
    options = config().get("i18n")
    return bool(isinstance(options, dict) and options.get("complete") is True) or bool(si.enabled_languages(config()))


def link_all(source: Path, target: Path, skip: tuple[str, ...]) -> None:
    for entry in source.iterdir():
        if entry.name not in skip:
            (target / entry.name).symlink_to(entry)


class RealTree(unittest.TestCase):
    def test_US3_the_default_checks_find_nothing_wrong_in_the_files_that_exist(self):
        plain = copy.deepcopy(config())
        plain["i18n"] = {"complete": False}
        for entry in plain["languages"].values():
            if "enabled" in entry:
                entry["enabled"] = False
        with tempfile.TemporaryDirectory() as tmp:
            link_all(ROOT, Path(tmp), skip=(SITE, ".git", "github"))
            site = Path(tmp) / SITE
            site.mkdir()
            link_all(ROOT / SITE, site, skip=("site.json", "_build"))
            (site / "site.json").write_text(json.dumps(plain), encoding=ENCODING)
            self.assertEqual([], si.check_site(Path(tmp)))

    def test_US3_the_complete_checks_find_nothing_once_the_maker_turns_them_on(self):
        if not complete_mode_applies():
            self.skipTest("i18n.complete is false and no language is enabled: the complete mode is off")
        findings = si.check_site(ROOT)
        self.assertEqual([], findings, "\n".join(findings))

    def test_US3_the_status_has_the_four_words_summing_to_the_document_count_in_each_language(self):
        counts = si.status(ROOT)
        print()
        print(si.render_status(counts), end="")
        self.assertEqual(declared_languages(), list(counts))
        for code, row in counts.items():
            with self.subTest(language=code):
                self.assertEqual(list(STATE_WORDS), list(row))
                self.assertEqual(DOCUMENT_COUNT, sum(row.values()))


class Scope(unittest.TestCase):
    def test_the_site_file_has_the_entries_and_only_the_two_scopes(self):
        entries = config()[PAGES]
        self.assertEqual(SITE_ENTRIES, len(entries))
        self.assertEqual(set(SCOPE_VALUES), {entry[SCOPE] for entry in entries})

    def test_the_english_only_documents_are_the_planned_ones(self):
        english = [entry[SLUG] for entry in config()[PAGES] if entry[SCOPE] == SCOPE_VALUES[1]]
        self.assertEqual(sorted(ENGLISH_SCOPE), sorted(english))

    def test_the_documents_to_translate_are_the_rest(self):
        self.assertEqual(DOCUMENT_COUNT, len(si.documents(ROOT)))
        self.assertTrue(set(ENGLISH_SCOPE).isdisjoint(si.documents(ROOT)))


if __name__ == "__main__":
    unittest.main()
