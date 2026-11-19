"""Tests of scripts/site_i18n.py (spec 004-site-languages, tasks T001 and T002). Each test names the scenario it proves
(US1-AS13, US2-AS1, AS10, AS13, AS14, AS17) or the requirement it pins (FR-027, D-015). Standard library only."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_i18n as si  # noqa: E402
from site_test_support import HEADER_KEYS, LANGUAGE_CODES, SCOPES  # noqa: E402

FRENCH, GERMAN = LANGUAGE_CODES[0], LANGUAGE_CODES[1]
LANGUAGES = "languages"
ENABLED = "enabled"
PAGES = "pages"
SLUG = "slug"
SCOPE = "scope"


def page_entry(slug: str, scope: str | None = SCOPES[0]) -> dict:
    entry = {SLUG: slug, "title": slug.title(), "source": f"site/pages/{slug}.md"}
    if scope is not None:
        entry[SCOPE] = scope
    return entry


def good_config() -> dict:
    return {
        LANGUAGES: {"en": {"name": "English", "path": "", "lang": "en"},
                    FRENCH: {"name": "Français", "path": FRENCH, "lang": FRENCH, ENABLED: False},
                    "zh": {"name": "中文", "path": "zh", "lang": "zh-Hans", ENABLED: True}},
        "i18n": {"complete": False},
        PAGES: [page_entry("index"), page_entry("overview"), page_entry("semantics", SCOPES[1])],
    }


def problem(config: dict) -> str | None:
    return si.config_problem(config, [entry[SLUG] for entry in config.get(PAGES, [])])


class ConfigShape(unittest.TestCase):
    """T001: `languages` and `i18n` of site/site.json."""

    def test_a_well_formed_configuration_has_no_problem(self):
        self.assertIsNone(problem(good_config()))

    def test_a_configuration_without_languages_and_i18n_has_no_problem(self):
        config = {PAGES: [page_entry("index")]}
        self.assertIsNone(problem(config))

    def test_languages_that_is_not_a_map_is_refused(self):
        for value in (["fr"], "fr", 3):
            with self.subTest(value=value):
                config = good_config()
                config[LANGUAGES] = value
                self.assertIn(LANGUAGES, problem(config) or "")

    def test_a_language_entry_that_is_not_an_object_is_refused_and_named(self):
        config = good_config()
        config[LANGUAGES][GERMAN] = "Deutsch"
        self.assertIn(GERMAN, problem(config) or "")

    def test_name_path_and_lang_must_be_strings(self):
        for key in ("name", "path", "lang"):
            with self.subTest(key=key):
                config = good_config()
                config[LANGUAGES][FRENCH][key] = 7
                self.assertIn(key, problem(config) or "")

    def test_enabled_must_be_a_boolean(self):
        for value in ("yes", 1, None, "false"):
            with self.subTest(value=value):
                config = good_config()
                config[LANGUAGES][FRENCH][ENABLED] = value
                message = problem(config) or ""
                self.assertIn(ENABLED, message)
                self.assertIn(FRENCH, message)

    def test_a_code_that_is_not_one_short_safe_folder_name_is_refused(self):
        for code in ("../x", "fr/x", "f", "FR", "fr.x", "images", "fonts", ".."):
            with self.subTest(code=code):
                config = good_config()
                config[LANGUAGES][code] = {"name": "X", "path": "xx", "lang": "xx"}
                self.assertIn(code, problem(config) or "")

    def test_a_path_that_is_not_one_short_safe_folder_name_is_refused(self):
        for path in ("../x", "a/b", "", "img", "fonts", "x" * 20):
            with self.subTest(path=path):
                config = good_config()
                config[LANGUAGES][FRENCH]["path"] = path
                self.assertIn(FRENCH, problem(config) or "")

    def test_a_script_subtag_code_and_path_are_accepted(self):
        config = good_config()
        config[LANGUAGES]["zh-Hans"] = {"name": "中文", "path": "zh-Hans", "lang": "zh-Hans"}
        self.assertIsNone(problem(config))

    def test_i18n_must_be_an_object_with_a_boolean_complete(self):
        for value in ("yes", ["complete"], {"complete": "true"}, {"complete": 1}):
            with self.subTest(value=value):
                config = good_config()
                config["i18n"] = value
                self.assertIn("i18n", problem(config) or "")

    def test_i18n_complete_true_is_accepted(self):
        config = good_config()
        config["i18n"] = {"complete": True}
        self.assertIsNone(problem(config))


class SlugClash(unittest.TestCase):
    """T001, US1-AS13: a page slug equal to a language prefix is refused."""

    def test_US1_AS13_a_slug_equal_to_a_declared_language_path_is_refused(self):
        config = good_config()
        config[PAGES].append(page_entry(FRENCH))
        message = problem(config) or ""
        self.assertIn(FRENCH, message)
        self.assertIn("prefix", message)

    def test_US1_AS13_a_slug_equal_to_a_custom_declared_path_is_refused(self):
        config = good_config()
        config[LANGUAGES]["pt"] = {"name": "Português", "path": "br", "lang": "pt", ENABLED: False}
        config[PAGES].append(page_entry("br"))
        self.assertIn("br", problem(config) or "")

    def test_US1_AS13_a_slug_equal_to_a_known_folder_is_refused_even_when_that_language_is_not_declared(self):
        config = good_config()
        config[PAGES].append(page_entry(GERMAN))
        self.assertIn(GERMAN, problem(config) or "")

    def test_US1_AS13_a_slug_that_is_no_prefix_is_accepted(self):
        config = good_config()
        config[PAGES].append(page_entry("french-notes"))
        self.assertIsNone(problem(config))


class ScopeKey(unittest.TestCase):
    """T001, FR-027: every page entry has a `scope` of `translated` or `english`."""

    def test_both_scopes_are_accepted(self):
        for scope in SCOPES:
            with self.subTest(scope=scope):
                config = good_config()
                config[PAGES].append(page_entry("extra", scope))
                self.assertIsNone(problem(config))

    def test_a_missing_scope_is_refused_and_the_page_is_named(self):
        config = good_config()
        config[PAGES].append(page_entry("guide", None))
        message = problem(config) or ""
        self.assertIn("guide", message)
        self.assertIn(SCOPE, message)

    def test_an_invalid_scope_is_refused_and_the_page_is_named(self):
        for value in ("both", "", "English", None, 5, ["english"]):
            with self.subTest(value=value):
                config = good_config()
                entry = page_entry("guide")
                entry[SCOPE] = value
                config[PAGES].append(entry)
                message = problem(config) or ""
                self.assertIn("guide", message)
                self.assertIn(SCOPE, message)

    def test_the_problem_is_found_without_mutating_the_configuration(self):
        config = good_config()
        config[PAGES].append(page_entry("guide", None))
        before = copy.deepcopy(config)
        problem(config)
        self.assertEqual(before, config)


TRANSLATION_HEAD = {
    "translates": "overview", "title": "Vue d'ensemble", "description": "Ce que fait la bibliothèque.",
    "source_fingerprint": "a" * 64, "drafter": "claude", "drafted_on": "2026-11-19", "status": "machine-drafted",
}
BODY = "# Vue d'ensemble\n\nTexte.\n"


def translation_text(head: dict, form: str = "---") -> str:
    lines = "".join(f"{key}: {value}\n" for key, value in head.items())
    opening, closing = ("---", "---") if form == "---" else ("<!--", "-->")
    return f"{opening}\n{lines}{closing}\n{BODY}"


class TranslationHeader(unittest.TestCase):
    """T002, US2-AS17: the header keys of a translation file."""

    def test_a_complete_header_is_parsed_with_its_body(self):
        parsed = si.parse_translation(translation_text(TRANSLATION_HEAD))
        self.assertEqual(TRANSLATION_HEAD, parsed.header)
        self.assertEqual(BODY, parsed.body)

    def test_the_header_of_a_home_template_may_be_an_html_comment(self):
        parsed = si.parse_translation(translation_text(TRANSLATION_HEAD, "<!--"))
        self.assertEqual(TRANSLATION_HEAD["source_fingerprint"], parsed.header["source_fingerprint"])

    def test_US2_AS17_a_missing_key_fails_and_names_it(self):
        for key in HEADER_KEYS:
            with self.subTest(key=key):
                head = {k: v for k, v in TRANSLATION_HEAD.items() if k != key}
                with self.assertRaises(si.I18nError) as raised:
                    si.parse_translation(translation_text(head))
                self.assertIn(key, str(raised.exception))

    def test_US2_AS17_an_empty_value_counts_as_missing(self):
        for key in ("drafter", "source_fingerprint", "title"):
            with self.subTest(key=key):
                with self.assertRaises(si.I18nError) as raised:
                    si.parse_translation(translation_text({**TRANSLATION_HEAD, key: ""}))
                self.assertIn(key, str(raised.exception))

    def test_both_statuses_are_accepted(self):
        for status in ("machine-drafted", "approved"):
            with self.subTest(status=status):
                parsed = si.parse_translation(translation_text({**TRANSLATION_HEAD, "status": status}))
                self.assertEqual(status, parsed.header["status"])

    def test_any_other_status_is_refused(self):
        for status in ("reviewed", "draft", "Approved"):
            with self.subTest(status=status):
                with self.assertRaises(si.I18nError) as raised:
                    si.parse_translation(translation_text({**TRANSLATION_HEAD, "status": status}))
                self.assertIn("status", str(raised.exception))


ENGLISH = "# Overview\n\nThe library compiles requests.\n\n```sql\nSELECT 1;\n```\n"
TITLE = "Overview"
DESCRIPTION = "What the library does."
HOME_TEMPLATE = "<main><h1>Craticula</h1></main>\n"
BADGE = "[![build](https://example.test/badge.svg)](https://example.test/ci)"


def finger(text: str = ENGLISH, home: str | None = None) -> str:
    return si.fingerprint(text, TITLE, DESCRIPTION, home)


class Fingerprint(unittest.TestCase):
    """T002: what the fingerprint of an English document covers and ignores."""

    def test_it_is_sixty_four_hex_characters(self):
        self.assertRegex(finger(), r"^[0-9a-f]{64}$")

    def test_US2_AS10_crlf_and_lf_give_the_same_fingerprint(self):
        self.assertEqual(finger(ENGLISH), finger(ENGLISH.replace("\n", "\r\n")))

    def test_US2_AS10_trailing_spaces_do_not_change_it(self):
        self.assertEqual(finger(ENGLISH), finger(ENGLISH.replace("compiles requests.", "compiles requests.   ")))

    def test_US2_AS10_the_title_and_the_description_are_covered(self):
        base = finger()
        self.assertNotEqual(base, si.fingerprint(ENGLISH, TITLE + " 2", DESCRIPTION))
        self.assertNotEqual(base, si.fingerprint(ENGLISH, TITLE, DESCRIPTION + " More."))

    def test_US2_AS13_a_prose_edit_changes_it(self):
        self.assertNotEqual(finger(), finger(ENGLISH.replace("compiles", "translates")))

    def test_US2_AS13_a_code_edit_changes_it(self):
        self.assertNotEqual(finger(), finger(ENGLISH.replace("SELECT 1", "SELECT 2")))

    def test_US2_AS13_a_badge_line_is_ignored(self):
        with_badge = f"{BADGE}\n\n{ENGLISH}"
        other_badge = with_badge.replace("badge.svg", "other.svg")
        self.assertEqual(finger(), finger(with_badge))
        self.assertEqual(finger(with_badge), finger(other_badge))

    def test_US2_AS13_an_html_comment_is_ignored(self):
        commented = ENGLISH.replace("\n\nThe library", "\n<!-- maintainers: keep this short -->\n\nThe library")
        self.assertEqual(finger(), finger(commented))
        self.assertEqual(finger(commented), finger(commented.replace("keep this short", "reworded")))

    def test_US2_AS14_the_text_after_include_expansion_is_what_is_covered(self):
        included = ENGLISH + "\n## Included\n\nText from a repository file.\n"
        self.assertNotEqual(finger(), finger(included))
        self.assertNotEqual(finger(included), finger(included.replace("repository file", "other file")))

    def test_the_home_template_is_covered_for_the_home_document(self):
        with_home = finger(home=HOME_TEMPLATE)
        self.assertNotEqual(finger(), with_home)
        self.assertNotEqual(with_home, finger(home=HOME_TEMPLATE.replace("Craticula", "Other")))
        self.assertEqual(with_home, finger(home=HOME_TEMPLATE.replace("\n", "\r\n")))

    def test_the_home_index_markdown_is_covered_too(self):
        self.assertNotEqual(finger(ENGLISH, HOME_TEMPLATE), finger(ENGLISH.replace("compiles", "translates"), HOME_TEMPLATE))


ENGLISH_UI = {"docs": "Docs", "previous": "Previous", "next": "Next", "group_names": {"Guides": "Guides"}}
GROUPS = {"Guides": "How to do the common jobs.", "Reference": "The exact rules."}


class UiFingerprint(unittest.TestCase):
    """T002, US2-AS10 and D-015: `ui.json` has its own fingerprint, group card descriptions included."""

    def test_it_is_sixty_four_hex_characters_and_stable(self):
        value = si.ui_fingerprint(ENGLISH_UI, GROUPS)
        self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertEqual(value, si.ui_fingerprint(copy.deepcopy(ENGLISH_UI), copy.deepcopy(GROUPS)))

    def test_an_english_interface_string_changes_it(self):
        changed = {**ENGLISH_UI, "next": "Continue"}
        self.assertNotEqual(si.ui_fingerprint(ENGLISH_UI, GROUPS), si.ui_fingerprint(changed, GROUPS))

    def test_a_group_card_description_changes_it(self):
        changed = {**GROUPS, "Guides": "Other words."}
        self.assertNotEqual(si.ui_fingerprint(ENGLISH_UI, GROUPS), si.ui_fingerprint(ENGLISH_UI, changed))

    def test_the_order_of_the_keys_does_not_change_it(self):
        reordered = dict(reversed(list(ENGLISH_UI.items())))
        self.assertEqual(si.ui_fingerprint(ENGLISH_UI, GROUPS), si.ui_fingerprint(reordered, dict(reversed(list(GROUPS.items())))))

    def test_it_differs_from_the_fingerprint_of_a_document(self):
        self.assertNotEqual(si.ui_fingerprint(ENGLISH_UI, GROUPS), finger())


class StaleFingerprint(unittest.TestCase):
    """T002, US2-AS1: a translation recorded against another English fingerprint fails and says which."""

    RECORDED = "b" * 64
    CURRENT = "c" * 64

    def test_US2_AS1_a_matching_fingerprint_has_no_finding(self):
        self.assertEqual([], si.check_fingerprint(GERMAN, "overview", self.CURRENT, self.CURRENT))

    def test_US2_AS1_a_stale_fingerprint_names_the_language_the_document_and_both_values(self):
        findings = si.check_fingerprint("zh", "quickstart-csharp", self.RECORDED, self.CURRENT)
        self.assertEqual(1, len(findings))
        for part in ("zh", "quickstart-csharp", self.RECORDED, self.CURRENT):
            self.assertIn(part, findings[0])

    def test_US2_AS1_a_file_that_records_no_fingerprint_is_a_finding(self):
        findings = si.check_fingerprint(FRENCH, "overview", None, self.CURRENT)
        self.assertEqual(1, len(findings))
        self.assertIn(self.CURRENT, findings[0])


if __name__ == "__main__":
    unittest.main()
