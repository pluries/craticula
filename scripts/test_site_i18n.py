"""Tests of scripts/site_i18n.py (spec 004-site-languages, tasks T001 and T002). Each test names the scenario it proves
(US1-AS13, US2-AS1, AS10, AS13, AS14, AS17) or the requirement it pins (FR-027, D-015). Standard library only."""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
import site_i18n as si  # noqa: E402
from site_test_support import (  # noqa: E402
    APPROVALS_PATH, APPROVED, APPROVER, APPROVERS_PATH, DOCUMENT_COUNT, DRAFTED, GLOSSARY_PATH, HEADER_KEYS, LANGUAGE_CODES, ROOT, SCOPES,
    STATE_WORDS, TODAY, UI_DOCUMENT, ZERO_FINGERPRINT, approval_record, approve_documents, english_fingerprints, language_tree, make_repo, mark_approved,
    stamp_documents, translation_file, ui_strings, write_records, write_tree)

FRENCH, GERMAN = LANGUAGE_CODES[0], LANGUAGE_CODES[1]
LANGUAGES = "languages"
ENABLED = "enabled"
PAGES = "pages"
SLUG = "slug"
SCOPE = "scope"
COMPLETE = "complete"
ZH_HANS = "zh-Hans"
ENGLISH_CODE = "en"
I18N_KEY = "i18n"


def page_entry(slug: str, scope: str | None = SCOPES[0]) -> dict:
    entry = {SLUG: slug, "title": slug.title(), "source": f"site/pages/{slug}.md"}
    if scope is not None:
        entry[SCOPE] = scope
    return entry


def good_config() -> dict:
    return {
        LANGUAGES: {"en": {"name": "English", "path": "", "lang": "en"},
                    FRENCH: {"name": "Français", "path": FRENCH, "lang": FRENCH, ENABLED: False},
                    "zh": {"name": "中文", "path": "zh", "lang": ZH_HANS, ENABLED: True}},
        I18N_KEY: {COMPLETE: False},
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
        config[LANGUAGES][ZH_HANS] = {"name": "中文", "path": ZH_HANS, "lang": ZH_HANS}
        self.assertIsNone(problem(config))

    def test_i18n_must_be_an_object_with_a_boolean_complete(self):
        for value in ("yes", [COMPLETE], {COMPLETE: "true"}, {COMPLETE: 1}):
            with self.subTest(value=value):
                config = good_config()
                config[I18N_KEY] = value
                self.assertIn(I18N_KEY, problem(config) or "")

    def test_i18n_complete_true_is_accepted(self):
        config = good_config()
        config[I18N_KEY] = {COMPLETE: True}
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

    def test_US2_AS13_a_prose_edit_changes_it(self):  # US2-AS13
        self.assertNotEqual(finger(), finger(ENGLISH.replace("compiles", "translates")))

    def test_US2_AS13_a_code_edit_changes_it(self):
        self.assertNotEqual(finger(), finger(ENGLISH.replace("SELECT 1", "SELECT 2")))

    def test_US2_AS13_a_badge_line_is_ignored(self):  # US2-AS13
        with_badge = f"{BADGE}\n\n{ENGLISH}"
        other_badge = with_badge.replace("badge.svg", "other.svg")
        self.assertEqual(finger(), finger(with_badge))
        self.assertEqual(finger(with_badge), finger(other_badge))

    def test_US2_AS13_an_html_comment_is_ignored(self):  # US2-AS13
        commented = ENGLISH.replace("\n\nThe library", "\n<!-- maintainers: keep this short -->\n\nThe library")
        self.assertEqual(finger(), finger(commented))
        self.assertEqual(finger(commented), finger(commented.replace("keep this short", "reworded")))

    def test_US2_AS14_the_text_after_include_expansion_is_what_is_covered(self):  # US2-AS14
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



# shared literals of the tests below (a literal repeated three times is a Sonar finding)
GUIDE, INDEX, OVERVIEW, CSHARP, GO = "guide", "index", "overview", "quickstart-csharp", "quickstart-go"
MISSING, STALE, ENCODING = "missing", "stale", "utf-8"
VERBATIM, FORBIDDEN, LANGUAGE_KEY, DOCUMENT_KEY = "verbatim", "forbidden", "language", "document"
VOYEZ, REGARDEZ, NOBODY, TERM, GUIDES, SOURCE = "voyez la", "regardez la", "Nobody", "GridSchema", "Guides", "source"
BLOCK_ONE, APPROVED_BY, HASH_KEY, APPROVALS_NAME, GUIDE_SOURCE = "code block 1", "approved_by", "translation_hash", "approvals.json", "site/pages/guide.md"
ENGLISH_NAME, HEX_64, TITLE_KEY, DESCRIPTION_KEY = "English", r"^[0-9a-f]{64}$", "title", "description"

# ---------------------------------------------------------------- T014a: identity (US2-AS2, AS3, AS12, AS15)

LABEL = "fr/guide"
EN_PAGE = ("# A guide\n\n## First step\n\nRun `dotnet build` on 3 projects, see the [home page](index.md) and ![chart](chart.png).\n\n"
           "```bash\ndotnet build\n```\n\n```json\n{\"limit\": 10}\n```\n")
FR_PAGE = ("# Un guide {#a-guide}\n\n## Première étape {#first-step}\n\nLancez `dotnet build` sur 3 projets, voyez la [page d'accueil](index.md) "
           "et ![graphique](chart.png).\n\n```bash\ndotnet build\n```\n\n```json\n{\"limit\": 10}\n```\n")
EN_ANCHORS = ["a-guide", "first-step"]
FIRST_BLOCK, SECOND_BLOCK = "```bash\ndotnet build\n```", '```json\n{"limit": 10}\n```'
INLINE, IMAGE, LINK, STEP = "`dotnet build` sur", "![graphique](chart.png)", "(index.md)", "## Première étape {#first-step}"


def identity(translated: str, resolve=None) -> list[str]:
    return si.check_identity(LABEL, EN_PAGE, translated, EN_ANCHORS, resolve)


def mentions(findings: list[str], word: str) -> bool:
    return bool(findings) and all(item.startswith(LABEL) for item in findings) and any(word in item for item in findings)


class ScanOfBlocks(unittest.TestCase):
    """T014a, T017: `_scan` splits a page into fenced blocks and the lines outside them."""

    def test_the_blocks_keep_their_tag_and_the_prose_is_what_is_left(self):
        scan = si._scan("Intro\n\n```bash\nrun it\n```\n\nOutro\n")
        self.assertEqual(["bash\nrun it"], scan.blocks)
        self.assertNotIn("run it", scan.prose)
        self.assertIn("Outro", scan.prose)

    def test_a_tilde_fence_is_a_block_too_and_a_longer_fence_holds_a_shorter_one(self):
        scan = si._scan("~~~\nA\n~~~\n\n````md\n```\ninner\n```\n````\n")
        self.assertEqual(["\nA", "md\n```\ninner\n```"], scan.blocks)

    def test_the_anchors_of_an_english_text_are_those_of_its_headings_in_order(self):
        self.assertEqual(EN_ANCHORS, si._english_anchors(EN_PAGE))


class IdentityCode(unittest.TestCase):
    """T014a, US2-AS2: code blocks, commands and JSON samples are the English ones in content, number and order."""

    def test_US2_AS2_a_faithful_translation_has_no_finding(self):
        self.assertEqual([], identity(FR_PAGE))

    def test_US2_AS2_one_character_in_a_block_a_command_or_a_json_sample_is_named(self):
        cases = {"a command in a block": ("dotnet build\n```\n\n```json", "dotnet bulid\n```\n\n```json", BLOCK_ONE),
                 "a json sample": ('"limit": 10', '"limit": 11', "code block 2"),
                 "an inline command": (INLINE, "`dotnet builds` sur", "inline code")}
        for name, (old, new, word) in cases.items():
            with self.subTest(case=name):
                self.assertTrue(mentions(identity(FR_PAGE.replace(old, new)), word))

    def test_US2_AS2_a_missing_or_an_extra_block_is_named(self):
        self.assertTrue(mentions(identity(FR_PAGE.replace(SECOND_BLOCK, "")), "code block 2"))
        self.assertTrue(mentions(identity(FR_PAGE + "\n```sh\nrm -rf x\n```\n"), "code block 3"))

    def test_US2_AS2_blocks_in_another_order_are_named(self):
        swapped = FR_PAGE.replace(FIRST_BLOCK, "@@").replace(SECOND_BLOCK, FIRST_BLOCK).replace("@@", SECOND_BLOCK)
        self.assertTrue(mentions(identity(swapped), BLOCK_ONE))


class IdentityWrappedInlineCode(unittest.TestCase):
    """US2-AS2: an inline code span wrapped across a line break is one span, as the renderer reads it (build_site._INLINE_CODE, re.S)."""

    EN = "# A guide\n\n## First step\n\nFor a tree such as `not startswith(a,'x') and (b eq 1\nor c gt 2)`, use `customFilters` here and `and` there.\n"
    FR = ("# Un guide {#a-guide}\n\n## Première étape {#first-step}\n\nPour un arbre tel que `not startswith(a,'x') and\n(b eq 1 or c gt 2)`, "
          "utilisez `customFilters` ici et `and` là.\n")

    def check(self, translated: str) -> list[str]:
        return si.check_identity(LABEL, self.EN, translated, EN_ANCHORS)

    def test_US2_AS2_a_span_wrapped_at_different_places_is_not_a_finding(self):
        self.assertEqual([], [item for item in self.check(self.FR) if "inline code" in item])

    def test_US2_AS2_a_changed_character_inside_a_wrapped_span_is_a_finding(self):
        found = [item for item in self.check(self.FR.replace("c gt 2", "c gt 3")) if "inline code" in item]
        self.assertTrue(any("c gt 3" in item for item in found), found)

    def test_US2_AS2_control_spans_on_one_line_are_unchanged(self):
        one_line = "`dotnet build`"
        self.assertEqual([], si.check_identity(LABEL, "# A guide\n\n## First step\n\nRun " + one_line + ".\n",
                                               "# Un guide {#a-guide}\n\n## Première étape {#first-step}\n\nLancez " + one_line + ".\n", EN_ANCHORS))
        self.assertTrue(mentions(identity(FR_PAGE.replace(INLINE, "`dotnet builds` sur")), "inline code"))

    def test_US2_AS2_the_real_french_odata_page_has_no_inline_code_finding(self):
        root = Path(__file__).resolve().parent.parent
        if not (root / "site" / "i18n" / "fr" / "odata-migration.md").is_file():
            self.skipTest("site/i18n/fr/odata-migration.md does not exist")
        self.assertEqual([], [item for item in si.check_page(root, "fr", "odata-migration") if "inline code" in item])


class IdentityTargets(unittest.TestCase):
    """T014a, US2-AS3: images, headings, anchors and link targets."""

    def test_US2_AS3_a_changed_or_missing_image_is_named(self):
        for name, new in {"another file": "![graphique](chart2.png)", "none": ""}.items():
            with self.subTest(image=name):
                self.assertTrue(mentions(identity(FR_PAGE.replace(IMAGE, new)), "image"))

    def test_US2_AS3_a_link_to_another_page_is_named_and_the_text_of_a_link_is_free(self):
        self.assertTrue(mentions(identity(FR_PAGE.replace(LINK, "(other.md)")), "link"))
        self.assertEqual([], identity(FR_PAGE.replace("[page d'accueil]", "[retour]")))

    def test_US2_AS3_two_spellings_of_one_page_and_anchor_are_equal_through_the_resolver(self):
        def resolve(target: str) -> str:
            return target.replace(".html", ".md")
        english, translated = "See [a](guide.md#step).\n", "Voir [a](guide.html#step).\n"
        self.assertEqual([], si.check_identity(LABEL, english, translated, [], resolve))
        self.assertTrue(mentions(si.check_identity(LABEL, english, translated, []), "link"))
        other = "Voir [a](guide.html#other).\n"
        self.assertTrue(mentions(si.check_identity(LABEL, english, other, [], resolve), "link"))

    def test_US2_AS3_a_missing_heading_is_counted(self):
        self.assertTrue(mentions(identity(FR_PAGE.replace(STEP + "\n\n", "")), "heading"))

    def test_US2_AS3_a_heading_without_its_english_anchor_is_named(self):
        findings = identity(FR_PAGE.replace(STEP, "## Première étape"))
        self.assertTrue(mentions(findings, "anchor"))
        self.assertTrue(any("Première étape" in item for item in findings))

    def test_US2_AS3_an_anchor_that_is_not_the_english_one_is_named(self):
        self.assertTrue(mentions(identity(FR_PAGE.replace("{#first-step}", "{#premiere-etape}")), "anchor"))

    def test_US2_AS8_an_address_or_a_private_path_the_english_page_lacks_is_named(self):
        for added in ("Voir https://evil.example/x.", "Voir [notes](../../docs/notes.md)."):
            with self.subTest(added=added):
                self.assertTrue(mentions(identity(FR_PAGE + "\n" + added + "\n"), "URL" if "https" in added else "link"))


EN_STRUCTURE = "Versions 1.5 and 2.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| x | y |\n\n> note\n"
FR_STRUCTURE = "Versions 2 et 1.5.\n\n- un\n- deux\n\n| a | b |\n|---|---|\n| x | y |\n\n> remarque\n"


class IdentityNumbers(unittest.TestCase):
    """T014a, US2-AS12: numbers as a set of digit strings, and the counts of tables, list items and block quotes."""

    def check(self, translated: str) -> list[str]:
        return si.check_numbers(LABEL, EN_STRUCTURE, translated)

    def test_US2_AS12_the_same_numbers_in_another_order_and_the_same_counts_have_no_finding(self):
        self.assertEqual([], self.check(FR_STRUCTURE))

    def test_US2_AS12_a_changed_missing_or_extra_number_is_named(self):
        cases = {"changed": FR_STRUCTURE.replace("1.5", "1.6"), MISSING: FR_STRUCTURE.replace(" et 1.5", ""), "extra": FR_STRUCTURE + "\nSoit 7.\n"}
        for name, translated in cases.items():
            with self.subTest(number=name):
                self.assertTrue(mentions(self.check(translated), "number"))

    def test_US2_AS12_a_different_count_of_list_items_or_tables_is_named(self):
        cases = {"list item": FR_STRUCTURE.replace("- deux\n", ""), "table": FR_STRUCTURE.replace("| a | b |\n|---|---|\n| x | y |\n\n", "")}
        for word, translated in cases.items():
            with self.subTest(count=word):
                self.assertTrue(mentions(self.check(translated), word))

    def test_US2_AS12_the_digits_of_an_anchor_declaration_are_not_numbers(self):
        self.assertEqual([], si.check_numbers(LABEL, "# Step\n", "# Étape {#step-2}\n"))


# ---------------------------------------------------------------- T014b: glossary (US2-AS6)

ENGLISH_TERMS = "Declare a GridSchema for AG Grid."
GLOSSARY = {VERBATIM: [TERM, "AG Grid"], FORBIDDEN: {"fr": {TERM: ["schéma de grille"]}, "zh": {}}}


def glossary(translated: str, lang: str = FRENCH, english: str = ENGLISH_TERMS, table: dict | None = None) -> list[str]:
    return si.check_glossary(LABEL, lang, english, translated, GLOSSARY if table is None else table)


class GlossaryTerms(unittest.TestCase):
    """T014b, US2-AS6, FR-013: verbatim terms, forbidden renderings and the entry of the language."""

    def test_US2_AS6_a_translation_that_keeps_its_terms_has_no_finding(self):
        self.assertEqual([], glossary("Déclarez un GridSchema pour AG Grid."))

    def test_US2_AS6_a_verbatim_term_that_is_gone_is_named(self):
        findings = glossary("Déclarez un schéma pour AG Grid.")
        self.assertEqual(1, len(findings))
        self.assertTrue(findings[0].startswith(LABEL) and TERM in findings[0])

    def test_US2_AS6_a_verbatim_term_is_matched_without_regard_to_case(self):
        self.assertEqual([], glossary("Déclarez un gridschema pour ag grid."))

    def test_US2_AS6_a_term_inside_a_longer_word_is_not_the_term(self):
        self.assertTrue(any(TERM in item for item in glossary("Déclarez des GridSchemas pour AG Grid.")))

    def test_US2_AS6_a_term_next_to_chinese_characters_is_a_token(self):
        self.assertEqual([], glossary("使用GridSchema声明AG Grid。", "zh"))

    def test_US2_AS6_a_term_the_english_page_does_not_use_is_not_required(self):
        self.assertEqual([], glossary("Bonjour.", english="Hello."))

    def test_US2_AS6_a_forbidden_rendering_is_named(self):
        findings = glossary("Déclarez un GridSchema (schéma de grille) pour AG Grid.")
        self.assertEqual(1, len(findings))
        self.assertIn("schéma de grille", findings[0])

    def test_US2_AS6_a_forbidden_word_is_matched_as_a_whole_token(self):
        table = {VERBATIM: [], FORBIDDEN: {FRENCH: {"set": ["jeu"]}}}
        self.assertEqual([], glossary("Des jeux.", table=table))
        self.assertTrue(glossary("Un jeu.", table=table))

    def test_US2_AS6_a_language_without_an_entry_fails_and_an_empty_entry_is_an_entry(self):
        findings = glossary("Déclarez un GridSchema pour AG Grid.", GERMAN)
        self.assertEqual(1, len(findings))
        self.assertIn(GERMAN, findings[0])
        self.assertEqual([], glossary("使用GridSchema声明AG Grid。", "zh"))


ANCHOR_TABLE = {VERBATIM: [TERM, "AG Grid"], FORBIDDEN: {GERMAN: {"AG Grid": ["AG-Grid"]}}}


def anchored(translated: str, english: str, table: dict | None = None) -> list[str]:
    return glossary(translated, GERMAN, english, ANCHOR_TABLE if table is None else table)


class GlossaryAnchors(unittest.TestCase):
    """US2-AS6: a declared anchor `{#...}` on a heading is an identifier, not prose; the glossary check ignores it in both halves."""

    def test_US2_AS6_a_forbidden_rendering_inside_a_declared_anchor_is_not_a_finding(self):
        english = "## Supported backends and AG Grid versions {#supported-backends-and-ag-grid-versions}\n"
        translated = "## Unterstützte Backends und AG Grid Versionen {#supported-backends-and-ag-grid-versions}\n"
        self.assertEqual([], anchored(translated, english))

    def test_US2_AS6_a_forbidden_rendering_in_prose_is_still_a_finding(self):
        english = "## Supported {#supported-backends-and-ag-grid-versions}\n\nRequests from AG Grid.\n"
        translated = "## Unterstützt {#supported-backends-and-ag-grid-versions}\n\nAnfragen von AG-Grid.\n"
        findings = anchored(translated, english, {VERBATIM: [], FORBIDDEN: {GERMAN: {"AG Grid": ["AG-Grid"]}}})
        self.assertEqual(1, len(findings))
        self.assertIn("AG-Grid", findings[0])

    def test_US2_AS6_a_verbatim_term_that_only_occurs_in_an_anchor_is_missing(self):
        english = "## Overview {#gridschema-overview}\n\nDeclare a GridSchema.\n"
        translated = "## Überblick {#gridschema-overview}\n\nDeklarieren Sie ein Schema.\n"
        findings = anchored(translated, english, {VERBATIM: [TERM], FORBIDDEN: {GERMAN: {}}})
        self.assertEqual(1, len(findings))
        self.assertIn(TERM, findings[0])

    def test_US2_AS6_without_anchors_the_check_is_unchanged(self):
        table = {VERBATIM: [TERM], FORBIDDEN: {GERMAN: {"AG Grid": ["AG-Grid"]}}}
        self.assertEqual([], anchored("## Überblick\n\nEin GridSchema für AG Grid.\n", "## Overview\n\nA GridSchema.\n", table))
        self.assertTrue(anchored("## Überblick\n\nEin GridSchema für AG-Grid.\n", "## Overview\n\nA GridSchema.\n", table))
        self.assertTrue(anchored("## Überblick\n\nEin Schema.\n", "## Overview\n\nA GridSchema.\n", table))


# ---------------------------------------------------------------- T014c: home template, quickstarts, scope (US3-AS1, AS2, AS5)

HOME_EN = '<main><h1>Home</h1><p>3 steps in 2 minutes</p><pre>dotnet build</pre><code>run</code><a href="guide.html">Go</a><img src="logo.svg" alt=""></main>'
HOME_FR = '<main><h1>Accueil</h1><p>3 étapes en 2 minutes</p><pre>dotnet build</pre><code>run</code><a href="guide.html">Aller</a><img src="logo.svg" alt="logo"></main>'


def template(translated: str) -> list[str]:
    return si.check_template(LABEL, HOME_EN, translated)


class HomeTemplate(unittest.TestCase):
    """T014c, US3-AS1, FR-020: the home template of a language has the English structure, figures and targets."""

    def test_US3_AS1_a_faithful_template_has_no_finding(self):
        self.assertEqual([], template(HOME_FR))

    def test_US3_AS1_a_changed_structure_figure_target_or_code_is_named(self):
        cases = {"structure": HOME_FR.replace("<p>", "<div><p>").replace("</p>", "</p></div>"), "number": HOME_FR.replace("2 minutes", "3 minutes"),
                 "href and src": HOME_FR.replace('href="guide.html"', 'href="other.html"'), "<pre>": HOME_FR.replace("<pre>dotnet build", "<pre>dotnet bulid"),
                 "<code>": HOME_FR.replace("<code>run", "<code>exec")}
        for word, translated in cases.items():
            with self.subTest(difference=word):
                findings = template(translated)
                self.assertTrue(any(word in item and "home.html" in item and item.startswith(LABEL) for item in findings), findings)

    def test_US3_AS1_a_script_or_an_address_the_english_template_lacks_is_named(self):
        self.assertTrue(template(HOME_FR + "<script>x()</script>"))
        self.assertTrue(any("https://evil.example" in item for item in template(HOME_FR.replace("Aller", "Aller https://evil.example/a"))))


QUICKSTARTS = (CSHARP, "quickstart-typescript", "quickstart-python", GO)
HEADING_LINE = re.compile(r"^(#{1,6}\s+.*?)\s*$", re.M)
BLOCK_LINE = re.compile(r"^\s*(```|~~~)")


def declare_anchors(text: str) -> str:
    """The text with each heading ending in the anchor the renderer gives it (a translation that changed nothing else)."""
    anchors = iter(si._english_anchors(text))
    return HEADING_LINE.sub(lambda match: f"{match.group(1)} {{#{next(anchors)}}}" if not BLOCK_LINE.match(match.group(0)) else match.group(0), text)


def quickstart_text(slug: str) -> str:
    """The page after `{{include}}` expansion: the commands and code of a quickstart may live in an included file."""
    source = f"site/pages/{slug}.md"
    return bs.expand_includes((ROOT / source).read_text(encoding=ENCODING), ROOT, source)


def first_code(text: str) -> tuple[int, str]:
    """Where the first character of the first code of a page is, and what the check calls it: a fenced block, else an inline span."""
    fence = re.search(r"^`{3,}[^\n]*\n", text, re.M)
    if fence:
        return fence.end(), BLOCK_ONE
    return text.index("`") + 1, "inline code"


class QuickstartCode(unittest.TestCase):
    """T014c, US3-AS2: the commands and code of a quickstart are the English ones, byte for byte."""

    def test_US3_AS2_a_translation_with_the_english_code_has_no_finding(self):
        for slug in QUICKSTARTS:
            with self.subTest(quickstart=slug):
                english = quickstart_text(slug)
                self.assertEqual([], si.check_identity(slug, english, declare_anchors(english), si._english_anchors(english)))

    def test_US3_AS2_one_changed_character_in_the_first_code_is_named(self):
        for slug in QUICKSTARTS:
            with self.subTest(quickstart=slug):
                english = quickstart_text(slug)
                at, word = first_code(english)
                changed = english[:at] + ("x" if english[at] != "x" else "y") + english[at + 1:]
                findings = si.check_identity(slug, english, declare_anchors(changed), si._english_anchors(english))
                self.assertTrue(any(item.startswith(slug) and word in item for item in findings), findings)


# ---------------------------------------------------------------- a small repository for the checks of one language (T014c, T015)

HOME_PAGE_EN, GUIDE_EN, REF_EN = "# Home\n\nStart with the [guide](guide.md).\n", EN_PAGE, "# A reference\n"
INDEX_FR = "# Accueil {#home}\n\nCommencez par le [guide](guide.md).\n"
MINI_PAGES = [
    {"slug": INDEX, TITLE_KEY: "Home", SOURCE: "site/pages/index.md", "template": "site/home.html", DESCRIPTION_KEY: "The home page.", SCOPE: SCOPES[0]},
    {"slug": GUIDE, TITLE_KEY: "A guide", SOURCE: GUIDE_SOURCE, DESCRIPTION_KEY: "The guide.", SCOPE: SCOPES[0]},
    {"slug": "ref", TITLE_KEY: "A reference", SOURCE: "site/pages/ref.md", DESCRIPTION_KEY: "English only.", SCOPE: SCOPES[1]},
]
MINI_LANGUAGES = {"en": {"name": ENGLISH_NAME, "path": "", "lang": "en"}, FRENCH: {"name": "Français", "path": FRENCH, "lang": FRENCH, ENABLED: False}}
MINI_GLOSSARY = {VERBATIM: ["dotnet"], FORBIDDEN: {FRENCH: {}}}
FR_DIR = f"site/i18n/{FRENCH}"
GUIDE_FILE, INDEX_FILE, HOME_FILE = f"{FR_DIR}/guide.md", f"{FR_DIR}/index.md", f"{FR_DIR}/home.html"
UI_FILE = f"{FR_DIR}/{UI_DOCUMENT}"


class MiniRepository(unittest.TestCase):
    """A repository of two documents and one English-only page, with French drafts of the two documents (stamped), a glossary and an
    approver list. The approvals record does not exist until a test writes it."""

    complete = False

    def setUp(self):
        files = {"site/pages/index.md": HOME_PAGE_EN, GUIDE_SOURCE: GUIDE_EN, "site/pages/ref.md": REF_EN, "site/home.html": HOME_EN,
                 "site/i18n/en/ui.json": '{"a": "b"}', GLOSSARY_PATH: json.dumps(MINI_GLOSSARY), APPROVERS_PATH: APPROVER + "\n"}
        self.root = make_repo(files, MINI_PAGES, languages=MINI_LANGUAGES, **{I18N_KEY: {COMPLETE: self.complete}})
        self.addCleanup(shutil.rmtree, self.root, True)
        write_tree(self.root, {GUIDE_FILE: translation_file(GUIDE, "Un guide", "Le guide.", FR_PAGE),
                               INDEX_FILE: translation_file(INDEX, "Accueil", "La page d'accueil.", INDEX_FR),
                               HOME_FILE: translation_file(INDEX, "Accueil", "La page d'accueil.", HOME_FR, as_comment=True),
                               UI_FILE: '{"a": "c", "groups": {}}'})
        stamp_documents(self.root, FRENCH)

    def edit(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding=ENCODING)
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding=ENCODING)


class ScopeCheck(MiniRepository):
    """T014c, US3-AS5: a translation file for a page of `scope: english` fails."""

    def test_US3_AS5_the_documents_are_the_translated_scope_pages_only(self):
        self.assertEqual([INDEX, GUIDE], si.documents(self.root))

    def test_US3_AS5_the_documents_of_this_repository_are_twenty_and_leave_out_the_english_pages_and_the_split_parts(self):
        slugs = si.documents(ROOT)
        self.assertEqual(DOCUMENT_COUNT, len(slugs))
        for english in ("spec", "semantics", "grid-schema", "ir-schema", "performance", "case-sensitivity"):
            self.assertNotIn(english, slugs)

    def test_US3_AS5_a_file_for_an_english_only_page_is_named(self):
        write_tree(self.root, {f"{FR_DIR}/ref.md": translation_file("ref", "Une référence", "Anglais.", "# Une référence {#a-reference}\n")})
        findings = si.check_scope(self.root, FRENCH)
        self.assertEqual(1, len(findings))
        self.assertIn("fr/ref", findings[0])
        self.assertIn("fr/ref", " ".join(si.check_site(self.root)))

    def test_US3_AS5_translations_of_the_documents_alone_have_no_finding(self):
        self.assertEqual([], si.check_scope(self.root, FRENCH))

    def test_US2_AS7_a_document_without_a_file_is_missing_and_an_english_only_page_is_not(self):
        (self.root / GUIDE_FILE).unlink()
        self.assertEqual([GUIDE], si.missing_pages(self.root, FRENCH))
        self.assertEqual([INDEX, GUIDE], si.missing_pages(self.root, GERMAN))


class PageChecks(MiniRepository):
    """T014c, US3-AS1: `check_page` runs the checks on one file, `index` with its template."""

    def test_a_faithful_translation_of_a_page_and_of_the_home_page_has_no_finding(self):
        self.assertEqual([], si.check_page(self.root, FRENCH, GUIDE))
        self.assertEqual([], si.check_page(self.root, FRENCH, INDEX))

    def test_a_changed_code_block_is_named_with_the_language_and_the_document(self):
        self.edit(GUIDE_FILE, "dotnet build\n```\n\n```json", "dotnet bulid\n```\n\n```json")
        findings = si.check_page(self.root, FRENCH, GUIDE)
        self.assertTrue(findings and all(item.startswith(LABEL) for item in findings))
        self.assertTrue(any(BLOCK_ONE in item for item in findings))

    def test_US3_AS1_a_home_template_with_another_target_is_named(self):
        self.edit(HOME_FILE, 'href="guide.html"', 'href="other.html"')
        findings = si.check_page(self.root, FRENCH, INDEX)
        self.assertTrue(any("home.html" in item and "href and src" in item for item in findings), findings)

    def test_a_missing_file_or_page_is_an_error(self):
        (self.root / GUIDE_FILE).unlink()
        for slug in (GUIDE, "nowhere"):
            with self.subTest(slug=slug), self.assertRaises(si.I18nError):
                si.check_page(self.root, FRENCH, slug)

    def test_US2_AS6_the_glossary_of_the_repository_applies_to_the_page(self):
        write_tree(self.root, {GLOSSARY_PATH: json.dumps({VERBATIM: ["dotnet"], FORBIDDEN: {FRENCH: {"projects": ["projets"]}}})})
        findings = si.check_page(self.root, FRENCH, GUIDE)
        self.assertTrue(any("projets" in item and item.startswith(LABEL) for item in findings), findings)


class DefaultMode(MiniRepository):
    """T015, US2-AS7: the default mode counts missing documents and passes."""

    def test_US2_AS7_default_mode_passes_with_a_missing_document_and_counts_it(self):
        (self.root / GUIDE_FILE).unlink()
        self.assertEqual([], si.check_site(self.root))
        self.assertEqual(1, si.status(self.root)[FRENCH][MISSING])


class CompleteMode(MiniRepository):
    """T015, US2-AS7: the complete mode fails naming each missing document."""

    complete = True

    def test_US2_AS7_complete_mode_fails_naming_each_missing_document(self):
        (self.root / GUIDE_FILE).unlink()
        findings = si.check_site(self.root)
        self.assertEqual(1, len([item for item in findings if item.endswith(MISSING)]))
        self.assertTrue(any(item.startswith(LABEL) and MISSING in item for item in findings), findings)

    def test_US2_AS7_complete_mode_names_every_document_of_a_language_with_no_file(self):
        for slug in (GUIDE, INDEX):
            (self.root / FR_DIR / f"{slug}.md").unlink()
        (self.root / HOME_FILE).unlink()
        findings = [item for item in si.check_site(self.root) if item.endswith(MISSING)]
        self.assertEqual(["fr/index: missing", "fr/guide: missing"], findings)

    def test_US2_AS7_a_complete_set_has_no_missing_finding(self):
        self.assertEqual([], si.check_site(self.root))


# ---------------------------------------------------------------- T015: approvals (US2-AS4, AS5, AS9)

class Tty(io.StringIO):
    """A standard input that says whether it is a terminal."""

    def __init__(self, typed: str = "", terminal: bool = True) -> None:
        super().__init__(typed)
        self.terminal = terminal

    def isatty(self) -> bool:
        return self.terminal


def stdin(typed: str = "", terminal: bool = True):
    return mock.patch.object(sys, "stdin", Tty(typed, terminal))


def read_records(root: Path) -> list[dict]:
    path = root / APPROVALS_PATH
    return json.loads(path.read_text(encoding=ENCODING)) if path.is_file() else []


def status_of(root: Path, slug: str) -> str:
    return si.parse_translation((root / FR_DIR / f"{slug}.md").read_text(encoding=ENCODING)).header[si.STATUS]


class ApprovalRecord(MiniRepository):
    """T015, US2-AS5: `approved` needs a matching record, an approver on the list, a current fingerprint and the translation as approved."""

    def approved(self) -> None:
        approve_documents(self.root, FRENCH, (GUIDE,))

    def findings(self) -> list[str]:
        return si.check_page(self.root, FRENCH, GUIDE)

    def test_US2_AS5_an_approved_file_with_its_record_has_no_finding(self):
        self.approved()
        self.assertEqual([], self.findings())

    def test_US2_AS5_an_approved_file_without_any_record_fails_and_says_so(self):
        mark_approved(self.root, FRENCH, GUIDE)
        findings = self.findings()
        self.assertTrue(any(item.startswith(LABEL) and APPROVALS_NAME in item for item in findings), findings)

    def test_US2_AS5_an_approver_who_is_not_on_the_list_fails_and_is_named(self):
        self.approved()
        (self.root / APPROVERS_PATH).write_text("Someone Else\n", encoding=ENCODING)
        findings = self.findings()
        self.assertTrue(any(APPROVER in item and item.startswith(LABEL) for item in findings), findings)

    def test_US2_AS5_an_english_change_after_the_approval_makes_it_stale(self):
        self.approved()
        self.edit(GUIDE_SOURCE, "Run `dotnet build`", "Run `dotnet build --force`")
        findings = self.findings()
        self.assertTrue(any(STALE in item and item.startswith(LABEL) for item in findings), findings)

    def test_US2_AS5_a_translation_body_changed_after_the_approval_has_no_matching_record(self):
        self.approved()
        self.edit(GUIDE_FILE, VOYEZ, REGARDEZ)
        findings = self.findings()
        self.assertTrue(any(APPROVALS_NAME in item and item.startswith(LABEL) for item in findings), findings)

    def test_US2_AS5_a_header_change_after_the_approval_does_not_void_it(self):
        self.approved()
        self.edit(GUIDE_FILE, "title: Un guide", "title: Le guide")
        self.assertEqual([], self.findings())

    def test_US2_AS5_the_record_of_another_language_or_document_is_not_a_match(self):
        current = english_fingerprints(self.root)[GUIDE]
        mark_approved(self.root, FRENCH, GUIDE)
        for other in ({LANGUAGE_KEY: GERMAN}, {DOCUMENT_KEY: INDEX}):
            with self.subTest(record=other):
                write_records(self.root, [{**approval_record(self.root, FRENCH, GUIDE, current), **other}])
                self.assertTrue(any(APPROVALS_NAME in item for item in self.findings()))

    def test_US2_AS5_the_two_record_checks_name_the_label_and_need_nothing_of_a_draft(self):
        header = {si.STATUS: APPROVED}
        records = [{LANGUAGE_KEY: FRENCH, DOCUMENT_KEY: GUIDE, si.FINGERPRINT: "f", HASH_KEY: "h", APPROVED_BY: APPROVER}]
        self.assertEqual([], si.check_approval_record(LABEL, header, records, "h", "f"))
        self.assertTrue(si.check_approval_record(LABEL, header, records, "other", "f")[0].startswith(LABEL))
        self.assertTrue(si.check_approval_record(LABEL, header, records, "h", "other"))
        self.assertEqual([], si.check_approval_record(LABEL, {si.STATUS: DRAFTED}, [], "h", "f"))
        self.assertEqual([], si.check_approval(LABEL, header, records, [APPROVER]))
        self.assertTrue(si.check_approval(LABEL, header, records, [NOBODY])[0].startswith(LABEL))
        self.assertIn(APPROVER, si.check_approval(LABEL, header, records, [NOBODY])[0])
        self.assertEqual([], si.check_approval(LABEL, {si.STATUS: DRAFTED}, [], []))

    def test_a_missing_approvals_file_reads_as_no_approvals_and_a_missing_approvers_file_as_nobody(self):
        self.assertFalse((self.root / APPROVALS_PATH).exists())
        self.assertEqual([], si.check_site(self.root))
        self.assertEqual(0, si.status(self.root)[FRENCH][APPROVED])
        (self.root / APPROVERS_PATH).unlink()
        self.assertEqual([], si._approvers(self.root))

    def test_the_approver_list_is_one_name_per_line_without_blank_lines(self):
        (self.root / APPROVERS_PATH).write_text("\ufeffAda Tester\n\n  Grace Hopper  \n", encoding=ENCODING)
        self.assertEqual(["Ada Tester", "Grace Hopper"], si._approvers(self.root))


class TranslationHash(MiniRepository):
    """T015: the hash of the translation as approved covers the body of every file of the document and nothing of the header."""

    def hashed(self, document: str = GUIDE) -> str:
        return si.translation_fingerprint(self.root, FRENCH, document)

    def test_it_is_sixty_four_hex_characters_and_follows_the_body(self):
        before = self.hashed()
        self.assertRegex(before, HEX_64)
        self.edit(GUIDE_FILE, VOYEZ, REGARDEZ)
        self.assertNotEqual(before, self.hashed())

    def test_the_header_does_not_change_it(self):
        before = self.hashed()
        self.edit(GUIDE_FILE, "drafted_on: 2026-11-19", "drafted_on: 2026-12-01")
        self.assertEqual(before, self.hashed())

    def test_the_home_document_covers_its_template_too(self):
        before = self.hashed(INDEX)
        self.edit(HOME_FILE, "Aller", "Allons")
        self.assertNotEqual(before, self.hashed(INDEX))

    def test_a_missing_file_gives_an_empty_string(self):
        self.assertEqual("", si.translation_fingerprint(self.root, GERMAN, GUIDE))

    def test_the_interface_file_is_hashed_as_text(self):
        before = self.hashed(UI_DOCUMENT)
        self.assertRegex(before, HEX_64)
        self.edit(UI_FILE, '"a": "c"', '"a": "d"')
        self.assertNotEqual(before, self.hashed(UI_DOCUMENT))


class ApproveCommand(MiniRepository):
    """T015, US2-AS9, FR-012: `approve` is the only writer of an approval, and it needs a terminal and a typed confirmation."""

    def approve(self, typed: str = f"{FRENCH}/guide\n", terminal: bool = True, by: str = APPROVER, document: str = GUIDE) -> str:
        with stdin(typed, terminal), contextlib.redirect_stdout(io.StringIO()):
            return si.approve(self.root, FRENCH, document, by, TODAY)

    def assert_nothing_written(self) -> None:
        self.assertEqual([], read_records(self.root))
        self.assertEqual(DRAFTED, status_of(self.root, GUIDE))

    def test_US2_AS9_with_a_terminal_and_the_typed_confirmation_it_writes_the_record_and_the_status(self):
        value = self.approve()
        self.assertEqual(english_fingerprints(self.root)[GUIDE], value)
        keys = (LANGUAGE_KEY, DOCUMENT_KEY, si.FINGERPRINT, HASH_KEY, APPROVED_BY, "approved_on")
        self.assertEqual([{LANGUAGE_KEY: FRENCH, DOCUMENT_KEY: GUIDE, si.FINGERPRINT: value,
                           HASH_KEY: si.translation_fingerprint(self.root, FRENCH, GUIDE), APPROVED_BY: APPROVER, "approved_on": TODAY}],
                         [{key: record[key] for key in keys} for record in read_records(self.root)])
        self.assertEqual(APPROVED, status_of(self.root, GUIDE))
        self.assertEqual([], si.check_page(self.root, FRENCH, GUIDE))

    def test_US2_AS9_without_a_terminal_it_refuses_and_writes_nothing(self):
        with self.assertRaises(si.I18nError):
            self.approve(terminal=False)
        self.assert_nothing_written()

    def test_US2_AS9_without_the_typed_confirmation_it_refuses_and_writes_nothing(self):
        for typed in ("", "\n", "yes\n", "fr/index\n"):
            with self.subTest(typed=typed), self.assertRaises(si.I18nError):
                self.approve(typed)
            self.assert_nothing_written()

    def test_US2_AS9_a_name_that_is_not_on_the_list_is_refused_and_nothing_is_written(self):
        with self.assertRaises(si.I18nError) as raised:
            self.approve(by=NOBODY)
        self.assertIn(NOBODY, str(raised.exception))
        self.assert_nothing_written()

    def test_US2_AS9_the_command_line_refuses_without_a_terminal_and_writes_nothing(self):
        with stdin(f"{FRENCH}/guide\n", False), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = si.main(["approve", FRENCH, GUIDE, "--by", APPROVER], root=self.root)
        self.assertEqual(2, code)
        self.assert_nothing_written()

    def test_US2_AS9_the_interface_file_is_approved_as_a_document_of_its_own(self):
        self.approve(f"{FRENCH}/{UI_DOCUMENT}\n", document=UI_DOCUMENT)
        self.assertEqual([UI_DOCUMENT], [record[DOCUMENT_KEY] for record in read_records(self.root)])
        self.assertEqual(si.ui_source_fingerprint(self.root), read_records(self.root)[0][si.FINGERPRINT])

    def test_US2_AS9_an_approval_replaces_the_record_of_the_same_document(self):
        self.approve()
        self.edit(GUIDE_FILE, VOYEZ, REGARDEZ)
        self.approve()
        self.assertEqual(1, len(read_records(self.root)))


class RedraftAfterApproval(MiniRepository):
    """T015, US2-AS9: an English change and a re-draft fall back to `machine-drafted`; only `approve` writes an approval."""

    def test_US2_AS9_a_redraft_after_an_english_change_makes_the_file_machine_drafted_again(self):
        approve_documents(self.root, FRENCH, (GUIDE,))
        self.assertEqual(APPROVED, status_of(self.root, GUIDE))
        self.edit(GUIDE_SOURCE, "Run `dotnet build`", "Run `dotnet build --force`")
        si.stamp(self.root, FRENCH, GUIDE, TODAY)
        self.assertEqual(DRAFTED, status_of(self.root, GUIDE))
        self.assertEqual({MISSING: 0, STALE: 0, DRAFTED: 2, APPROVED: 0}, si.status(self.root)[FRENCH])

    def test_US2_AS9_the_drafting_step_writes_no_record(self):
        si.stamp(self.root, FRENCH, GUIDE, TODAY)
        self.assertFalse((self.root / APPROVALS_PATH).exists())
        approve_documents(self.root, FRENCH, (GUIDE,))
        before = (self.root / APPROVALS_PATH).read_bytes()
        si.stamp(self.root, FRENCH, GUIDE, TODAY)
        self.assertEqual(before, (self.root / APPROVALS_PATH).read_bytes())


# ---------------------------------------------------------------- T015: status and gate (US3-AS6, US4-AS4, AS5)

STATUS_OMITTED = (OVERVIEW, "limits")
STATUS_STALE = ("what-is-craticula", GO)
STATUS_APPROVED = (CSHARP, "request-to-query")
UNRECORDED, EDITED_AFTER = "safety-model", INDEX


class TwentyDocuments(unittest.TestCase):
    """A copy of this repository's sources with a stub translation of the 20 documents in each language, two of them missing."""

    omitted: tuple[str, ...] = ()

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = language_tree(tmp, self.omitted)

    def page_file(self, lang: str, slug: str) -> Path:
        return self.root / "site" / "i18n" / lang / f"{slug}.md"


class StatusCounts(TwentyDocuments):
    """T015, US3-AS6, FR-019: the counts are exclusive, in the order missing, stale, machine-drafted, approved, and sum to 20."""

    omitted = STATUS_OMITTED

    def setUp(self):
        super().setUp()
        stamp_documents(self.root, FRENCH)
        approve_documents(self.root, FRENCH, (*STATUS_APPROVED, *STATUS_STALE, EDITED_AFTER))
        for slug in STATUS_STALE:
            si._update_header(self.page_file(FRENCH, slug), {si.FINGERPRINT: ZERO_FINGERPRINT})
        mark_approved(self.root, FRENCH, UNRECORDED)
        path = self.page_file(FRENCH, EDITED_AFTER)
        path.write_text(path.read_text(encoding=ENCODING) + "\nUne ligne de plus.\n", encoding=ENCODING)

    def test_US3_AS6_each_document_is_counted_once_in_the_first_category_that_applies(self):
        row = si.status(self.root)[FRENCH]
        self.assertEqual({MISSING: len(STATUS_OMITTED), STALE: len(STATUS_STALE), APPROVED: len(STATUS_APPROVED),
                          DRAFTED: DOCUMENT_COUNT - len(STATUS_OMITTED) - len(STATUS_STALE) - len(STATUS_APPROVED)}, row)

    def test_US3_AS6_an_approved_file_without_a_record_or_changed_after_approval_counts_as_machine_drafted(self):
        self.assertIn(UNRECORDED, si.documents(self.root))
        before = si.status(self.root)[FRENCH]
        approve_documents(self.root, FRENCH, (UNRECORDED,))
        after = si.status(self.root)[FRENCH]
        self.assertEqual(before[APPROVED] + 1, after[APPROVED])
        self.assertEqual(before[DRAFTED] - 1, after[DRAFTED])

    def test_US3_AS6_the_four_counts_sum_to_twenty_in_every_language(self):
        counts = si.status(self.root)
        self.assertEqual(set(LANGUAGE_CODES), set(counts))
        for lang, row in counts.items():
            with self.subTest(language=lang):
                self.assertEqual(set(STATE_WORDS), set(row))
                self.assertEqual(DOCUMENT_COUNT, sum(row.values()))

    def test_US3_AS6_a_language_with_only_stub_fingerprints_is_stale_except_the_missing_ones(self):
        self.assertEqual({MISSING: 2, STALE: DOCUMENT_COUNT - 2, DRAFTED: 0, APPROVED: 0}, si.status(self.root)[GERMAN])

    def test_US3_AS6_the_report_has_a_line_per_language_with_the_four_words_in_order(self):
        lines = si.render_status(si.status(self.root)).splitlines()
        self.assertEqual(len(LANGUAGE_CODES), len(lines))
        row = si.status(self.root)[FRENCH]
        expected = r"\s+".join(f"{word} {row[word]}" for word in STATE_WORDS)
        self.assertRegex(lines[0], rf"^{FRENCH}\s+{expected}$")

    def test_US3_AS6_the_status_command_prints_the_report_and_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = si.main([si.STATUS], root=self.root)
        self.assertEqual(0, code)
        self.assertEqual(si.render_status(si.status(self.root)), out.getvalue())


class EnableGate(TwentyDocuments):
    """T015, US4-AS4, AS5, FR-024: a language may be enabled only when every document and its interface file are current and approved."""

    def setUp(self):
        super().setUp()
        stamp_documents(self.root, FRENCH)
        approve_documents(self.root, FRENCH, ui=True)

    def test_US4_AS4_a_language_with_everything_current_and_approved_has_no_finding(self):
        self.assertEqual([], si.check_enable_gate(self.root, FRENCH))

    def test_US4_AS4_a_document_that_is_machine_drafted_is_named(self):
        stamp_documents(self.root, FRENCH, (GO,))
        write_records(self.root, [record for record in read_records(self.root) if record[DOCUMENT_KEY] != GO])
        findings = si.check_enable_gate(self.root, FRENCH)
        self.assertEqual(1, len(findings))
        self.assertTrue(findings[0].startswith("fr/quickstart-go") and "not approved" in findings[0])

    def test_US4_AS5_a_document_the_english_text_has_left_behind_is_named_as_stale(self):
        path = self.root / "site" / "pages" / "limits.md"
        path.write_text(path.read_text(encoding=ENCODING) + "\nOne more sentence.\n", encoding=ENCODING)
        findings = si.check_enable_gate(self.root, FRENCH)
        self.assertEqual(1, len(findings))
        self.assertTrue(findings[0].startswith("fr/limits") and STALE in findings[0])

    def test_US4_AS4_a_document_without_a_file_is_named_as_missing(self):
        self.page_file(FRENCH, OVERVIEW).unlink()
        findings = si.check_enable_gate(self.root, FRENCH)
        self.assertTrue(any(item.startswith("fr/overview") and MISSING in item for item in findings), findings)

    def test_US4_AS4_an_interface_file_without_an_approval_is_named(self):
        write_records(self.root, [record for record in read_records(self.root) if record[DOCUMENT_KEY] != UI_DOCUMENT])
        findings = si.check_enable_gate(self.root, FRENCH)
        self.assertEqual(1, len(findings))
        self.assertTrue(findings[0].startswith(f"fr/{UI_DOCUMENT}") and "not approved" in findings[0])

    def test_US4_AS4_an_interface_file_changed_after_its_approval_is_named(self):
        path = self.root / "site" / "i18n" / FRENCH / UI_DOCUMENT
        path.write_text(path.read_text(encoding=ENCODING).replace("[fr] Skip", "[fr] Jump"), encoding=ENCODING)
        self.assertEqual([f"fr/{UI_DOCUMENT}"], [item.split(":")[0] for item in si.check_enable_gate(self.root, FRENCH)])

    def test_US4_AS4_a_language_with_nothing_approved_is_named_document_by_document(self):
        findings = si.check_enable_gate(self.root, GERMAN)
        self.assertEqual(DOCUMENT_COUNT + 1, len(findings))
        self.assertTrue(any(item.startswith("de/quickstart-csharp") for item in findings))

    def test_US4_AS4_the_gate_command_exits_zero_when_it_passes_and_names_the_documents_when_it_fails(self):
        with contextlib.redirect_stderr(io.StringIO()) as quiet:
            self.assertEqual(0, si.main(["gate", FRENCH], root=self.root))
        self.assertEqual("", quiet.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as complaint:
            self.assertEqual(1, si.main(["gate", GERMAN], root=self.root))
        self.assertIn("de/quickstart-csharp", complaint.getvalue())


# ---------------------------------------------------------------- review round: the mechanism of spec 004 (findings 1 to 7)

HOME_NAME = si.HOME_FILE
ATTRIBUTE_WORD = "attribute"
NOT_APPROVED = "not approved"
NOT_DECLARED = "declared"
OUTSIDE_LANG = "../x"
UNDECLARED_LANG = "es"
OUTSIDE_DIR = "site/x"
OUTSIDE_FILE = f"{OUTSIDE_DIR}/guide.md"
UNDECLARED_FILE = f"site/i18n/{UNDECLARED_LANG}/guide.md"
KEEP_NAME = "keep.txt"
OLD_PAGE = "old.html"
ELEMENT_EN = '<main><p class="lead"><a href="guide.html" title="Go to the guide">Go</a></p></main>'


class TemplateAttributes(unittest.TestCase):
    """Finding 1, US2-AS8, FR-018: `check_template` compares the full set of attribute names of each element, so a translator cannot add an
    event handler, a style or any attribute the English element lacks (nor drop one). A finding starts with the label, names `home.html` and the
    word `attribute`, and names each attribute that differs (compared without regard to case)."""

    def named(self, english: str, translated: str, name: str) -> bool:
        findings = si.check_template(LABEL, english, translated)
        return any(item.startswith(LABEL) and HOME_NAME in item and ATTRIBUTE_WORD in item and name in item.lower() for item in findings)

    def test_US2_AS8_attributes_added_to_an_element_are_named(self):  # US2-AS8
        added = '<main id="main" onmouseover="steal()" style="background:url(//e.example/a)">'
        findings = template(HOME_FR.replace("<main>", added))
        for name in ("id", "onmouseover", "style"):
            with self.subTest(attribute=name):
                self.assertTrue(any(item.startswith(LABEL) and HOME_NAME in item and ATTRIBUTE_WORD in item and name in item for item in findings), findings)

    def test_US2_AS8_every_way_of_writing_an_attribute_is_found(self):  # US2-AS8
        spellings = {"onclick": ("onclick='x()'", "onclick=x()", 'ONCLICK="x()"', 'onclick = "x()"'), "hidden": ("hidden",)}
        for name, forms in spellings.items():
            for form in forms:
                with self.subTest(form=form):
                    self.assertTrue(self.named(HOME_EN, HOME_FR.replace("<main>", f"<main {form}>"), name), form)

    def test_US2_AS8_an_attribute_the_translation_dropped_is_named(self):  # US2-AS8
        self.assertTrue(self.named(ELEMENT_EN, ELEMENT_EN.replace(' class="lead"', ""), "class"))
        self.assertTrue(self.named(ELEMENT_EN, ELEMENT_EN.replace(' title="Go to the guide"', ""), "title"))

    def test_US2_AS8_an_attribute_moved_to_another_element_is_named(self):  # US2-AS8
        moved = '<main><p><a class="lead" href="guide.html" title="Go to the guide">Go</a></p></main>'
        self.assertTrue(self.named(ELEMENT_EN, moved, "class"))

    def test_US2_AS8_the_same_names_in_another_order_with_another_text_have_no_finding(self):  # US2-AS8
        translated = '<main><p class="envol"><a title="Aller au guide" href="guide.html">Aller</a></p></main>'
        self.assertEqual([], si.check_template(LABEL, ELEMENT_EN, translated))


class HomeFileIsPartOfIndex(MiniRepository):
    """Finding 2, US3-AS3, US3-AS4, FR-024: the document `index` is `index.md` and `home.html`; without the second it is missing."""

    def test_US3_AS4_a_home_page_without_its_template_is_listed_as_missing(self):  # US3-AS4
        (self.root / HOME_FILE).unlink()
        self.assertEqual([INDEX], si.missing_pages(self.root, FRENCH))
        self.assertEqual([INDEX, GUIDE], si.missing_pages(self.root, GERMAN))

    def test_US3_AS6_the_status_counts_it_as_missing_and_not_as_drafted(self):  # US3-AS6
        (self.root / HOME_FILE).unlink()
        self.assertEqual({MISSING: 1, STALE: 0, DRAFTED: 1, APPROVED: 0}, si.status(self.root)[FRENCH])

    def test_US4_AS4_the_enable_gate_names_the_missing_file(self):  # US4-AS4
        (self.root / HOME_FILE).unlink()
        found = [item for item in si.check_enable_gate(self.root, FRENCH) if item.startswith(f"{FRENCH}/{INDEX}")]
        self.assertEqual(1, len(found), found)
        self.assertIn(MISSING, found[0])
        self.assertIn(HOME_NAME, found[0])
        self.assertNotIn(NOT_APPROVED, found[0])

    def test_US3_AS3_an_index_approved_with_a_home_page_still_machine_drafted_is_machine_drafted(self):  # US3-AS3
        approve_documents(self.root, FRENCH, (INDEX,))
        self.assertEqual({MISSING: 0, STALE: 0, DRAFTED: 1, APPROVED: 1}, si.status(self.root)[FRENCH])
        si._update_header(self.root / HOME_FILE, {si.STATUS: DRAFTED})
        self.assertEqual({MISSING: 0, STALE: 0, DRAFTED: 2, APPROVED: 0}, si.status(self.root)[FRENCH])
        found = [item for item in si.check_enable_gate(self.root, FRENCH) if item.startswith(f"{FRENCH}/{INDEX}")]
        self.assertEqual(1, len(found), found)
        self.assertIn(NOT_APPROVED, found[0])

    def test_US3_AS3_approve_refuses_an_index_that_has_no_home_page_and_writes_nothing(self):  # US3-AS3
        (self.root / HOME_FILE).unlink()
        before = (self.root / INDEX_FILE).read_bytes()
        with stdin(f"{FRENCH}/{INDEX}\n"), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(si.I18nError) as raised:
            si.approve(self.root, FRENCH, INDEX, APPROVER, TODAY)
        self.assertIn(HOME_NAME, str(raised.exception))
        self.assertEqual([], read_records(self.root))
        self.assertEqual(before, (self.root / INDEX_FILE).read_bytes())
        self.assertEqual(DRAFTED, status_of(self.root, INDEX))


class HomeFileInCompleteMode(MiniRepository):
    """Finding 2, US3-AS4: the complete mode names a home page whose template is missing."""

    complete = True

    def test_US3_AS4_complete_mode_reports_the_index_whose_template_is_missing(self):  # US3-AS4
        (self.root / HOME_FILE).unlink()
        self.assertIn(f"{FRENCH}/{INDEX}: {MISSING}", si.check_site(self.root))


class TwoLanguagesOnePath(unittest.TestCase):
    """Finding 4, FR-001: two languages may not write into the same folder; the message names the path and both codes."""

    def test_FR_001_a_path_taken_by_two_languages_is_refused_and_both_are_named(self):  # FR-001
        config = good_config()
        config[LANGUAGES][GERMAN] = {"name": "Deutsch", "path": FRENCH, "lang": GERMAN, ENABLED: False}
        message = problem(config) or ""
        for word in (FRENCH, GERMAN, "path"):
            self.assertIn(word, message)

    def test_FR_001_a_path_that_is_the_default_of_another_language_is_refused(self):  # FR-001
        config = good_config()
        config[LANGUAGES][GERMAN] = {"name": "Deutsch", "lang": GERMAN, ENABLED: False}
        config[LANGUAGES]["it"] = {"name": "Italiano", "path": GERMAN, "lang": "it", ENABLED: False}
        message = problem(config) or ""
        for word in (GERMAN, "it", "path"):
            self.assertIn(word, message)

    def test_FR_001_languages_with_their_own_paths_are_accepted(self):  # FR-001
        config = good_config()
        config[LANGUAGES][GERMAN] = {"name": "Deutsch", "lang": GERMAN, ENABLED: False}
        config[LANGUAGES]["it"] = {"name": "Italiano", "path": "ita", "lang": "it", ENABLED: False}
        self.assertIsNone(problem(config))


class LanguageArgument(MiniRepository):
    """Finding 5, FR-012: `stamp` and `approve` accept only a language declared in site.json; anything else (a path out of the folder, an
    undeclared folder) is an I18nError that says the language is not declared, and nothing is written."""

    BAD = (OUTSIDE_LANG, UNDECLARED_LANG, "fr/../fr", "")

    def setUp(self):
        super().setUp()
        for rel in (OUTSIDE_FILE, UNDECLARED_FILE):
            write_tree(self.root, {rel: translation_file(GUIDE, "Un guide", "Le guide.", FR_PAGE)})
        stamp_documents(self.root, FRENCH)
        self.before = self.snapshot()

    def snapshot(self) -> dict[str, bytes]:
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in sorted(self.root.rglob("*")) if path.is_file()}

    def test_FR_012_stamp_refuses_a_language_that_is_not_declared_and_writes_nothing(self):  # FR-012
        for lang in self.BAD:
            with self.subTest(language=lang):
                with self.assertRaises(si.I18nError) as raised:
                    si.stamp(self.root, lang, GUIDE, TODAY)
                self.assertIn(NOT_DECLARED, str(raised.exception))
                self.assertEqual(self.before, self.snapshot())

    def test_FR_012_the_stamp_command_exits_2_for_such_a_language(self):  # FR-012
        with contextlib.redirect_stderr(io.StringIO()) as complaint:
            self.assertEqual(2, si.main(["stamp", OUTSIDE_LANG, GUIDE], root=self.root))
        self.assertIn(NOT_DECLARED, complaint.getvalue())
        self.assertEqual(self.before, self.snapshot())

    def test_FR_012_approve_refuses_a_language_that_is_not_declared_and_writes_nothing(self):  # FR-012
        for lang in self.BAD:
            with self.subTest(language=lang):
                with stdin(f"{lang}/{GUIDE}\n"), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(si.I18nError) as raised:
                    si.approve(self.root, lang, GUIDE, APPROVER, TODAY)
                self.assertIn(NOT_DECLARED, str(raised.exception))
                self.assertEqual(self.before, self.snapshot())

    def test_FR_012_a_declared_language_is_still_stamped(self):  # FR-012 (control)
        self.assertRegex(si.stamp(self.root, FRENCH, GUIDE, TODAY), r"^[0-9a-f]{64}$")


THEMES = ("auto", "light", "dark")
NESTED_MAPS = {"theme_names": THEMES, "group_names": ("Concepts", "Guides", "Configuration", "Reference"), "subgroups": ("Semantics", "Quickstarts")}


class NestedInterfaceMaps(unittest.TestCase):
    """Finding 6, US1-AS4, FR-003: `load_ui` checks the keys inside `theme_names`, `group_names` and `subgroups` against the English maps,
    so a translation cannot leave one out and fall back to an English label or a traceback. The error names the file, the map and the key."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.reference = ui_strings(ENGLISH_CODE)

    def load(self, ui: dict) -> dict:
        write_tree(self.tmp, {f"site/i18n/{FRENCH}/{UI_DOCUMENT}": json.dumps(ui, ensure_ascii=False)})
        return si.load_ui(self.tmp, FRENCH, self.reference)

    def test_US1_AS4_a_complete_interface_file_is_accepted(self):  # US1-AS4 (control)
        ui = ui_strings(FRENCH)
        self.assertEqual(ui, self.load(ui))

    def test_US1_AS4_a_key_missing_from_a_nested_map_is_an_error_naming_the_map_and_the_key(self):  # US1-AS4
        for name, keys in NESTED_MAPS.items():
            for key in keys:
                with self.subTest(map=name, key=key):
                    ui = ui_strings(FRENCH)
                    del ui[name][key]
                    with self.assertRaises(si.I18nError) as raised:
                        self.load(ui)
                    message = str(raised.exception)
                    for word in (UI_DOCUMENT, name, key):
                        self.assertIn(word, message)

    def test_US1_AS4_a_nested_map_that_is_empty_is_refused_too(self):  # US1-AS4
        ui = ui_strings(FRENCH)
        ui["theme_names"] = {}
        with self.assertRaises(si.I18nError):
            self.load(ui)


class ClearLanguageFolders(unittest.TestCase):
    """Finding 7, FR-024: the build clears the folder of each language the configuration declares and nothing else, and does not write through
    a symbolic link."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = self.tmp / "out"
        self.elsewhere = self.tmp / "elsewhere"
        write_tree(self.tmp, {f"elsewhere/{KEEP_NAME}": "keep"})
        self.config = good_config()
        self.config[LANGUAGES][GERMAN] = {"name": "Deutsch", "path": GERMAN, "lang": GERMAN, ENABLED: False}
        self.config[LANGUAGES]["pt"] = {"name": "Português", "path": "br", "lang": "pt", ENABLED: False}

    def test_FR_024_the_folders_of_the_declared_languages_go_and_every_other_folder_stays(self):  # FR-024
        folders = (FRENCH, GERMAN, "zh", "br", UNDECLARED_LANG, "images", "pt")
        write_tree(self.out, {f"{name}/{OLD_PAGE}": "old" for name in folders})
        si.clear_language_folders(self.out, self.config)
        self.assertEqual({UNDECLARED_LANG, "images", "pt"}, {path.name for path in self.out.iterdir()})

    def test_FR_024_a_language_folder_that_is_a_symbolic_link_is_refused_and_its_target_is_untouched(self):  # FR-024
        self.out.mkdir()
        os.symlink(self.elsewhere, self.out / FRENCH)
        with self.assertRaises(si.I18nError) as raised:
            si.clear_language_folders(self.out, self.config)
        for word in (FRENCH, "symbolic link"):
            self.assertIn(word, str(raised.exception))
        self.assertEqual([KEEP_NAME], [path.name for path in self.elsewhere.iterdir()])

    def test_FR_024_a_link_with_the_name_of_an_undeclared_language_is_not_this_builds_business(self):  # FR-024 (control)
        self.out.mkdir()
        os.symlink(self.elsewhere, self.out / UNDECLARED_LANG)
        si.clear_language_folders(self.out, self.config)
        self.assertTrue((self.out / UNDECLARED_LANG).is_symlink())
        self.assertEqual([KEEP_NAME], [path.name for path in self.elsewhere.iterdir()])


if __name__ == "__main__":
    unittest.main()
