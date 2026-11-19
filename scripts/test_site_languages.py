#!/usr/bin/env python3
"""Tests of the language build of the docs site (spec 004-site-languages, tasks T005 to T007b). Each test names the scenario it proves
(US1-AS1 to AS17) or the requirement it pins (FR-006, FR-016). T005 is a pin and is green from the start; the rest specify behaviour the
generator does not have yet. The language fixture (a copy of this repository's sources with six interface files and a stub translation of each
of the 20 documents, two of them hand-written) is built by `site_test_support.language_build`. Offline, standard library only.
Run: python3 scripts/test_site_languages.py
"""
import atexit
import gzip
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
import site_i18n as si  # noqa: E402
from site_test_support import (  # noqa: E402
    BASE_URL, CHROME_ATTRIBUTE_KEYS, ENCODING, TITLE_KEY, CHROME_TEXT_KEYS, CODE_SNIPPET, DATA_UI_ATTRIBUTE, ENGLISH_UI, FULL, HANDWRITTEN, HANDWRITTEN_OVERVIEW,
    LANG_ATTRIBUTES, LANG_MENU, LANGUAGE_CODES, LANGUAGE_NAMES, LEFTOVER, LINKED_PAGE, MARKS, OUTSIDE_LINK, PARTIAL, PIN_FILE, README_PAGE,
    ROOT, SCHEME, SEMANTICS_TARGET, SIBLING_PAGE, build_english_fixture, html_digests, language_build, make_repo, normalise_versions, site_pages,
    strip_added_fragments, ui_strings)
from site_test_support import (  # noqa: E402
    CODED_SAMPLE, DOCUMENT_COUNT, DRAFTED, HTML_SUFFIX, UI_DOCUMENT, approve_documents, language_tree, stamp_documents, translation_file, write_tree)

ENGLISH = "en"
STYLE_NAME = "style.css"
LLMS_NAME = "llms.txt"
GROUP_NAMES = "group_names"
SPEC_HREF = f"../spec{HTML_SUFFIX}"
JS_DIR = ROOT / "site" / "js"
ALL_CODES = (ENGLISH, *LANGUAGE_CODES)
INDEX_SLUG = "index"
SOME_TRANSLATED_PAGE = "quickstart-csharp"
ENGLISH_ONLY_PAGES = ("spec", "case-sensitivity", "grid-schema", "performance")
SIDEBAR = re.compile(r'<aside[^>]*id="sidebar".*?</aside>', re.S)
PAGER = re.compile(r'<nav class="pager".*?</nav>', re.S)
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S)
HREF = re.compile(r'href="([^"]*)"')
REFERENCE = re.compile(r'<(?:a|link|script|img)\b[^>]*?\b(?:href|src)="([^"]*)"')
ALTERNATE = re.compile(r'<link rel="alternate" hreflang="([^"]*)" href="([^"]*)">')
CANONICAL = re.compile(r'<link rel="canonical" href="([^"]*)">')
LEAF_ITEM = re.compile(r"<li>.*?</li>", re.S)
PRE_BLOCK = re.compile(r"<pre>.*?</pre>", re.S)
HTML_LANG = re.compile(r'<html lang="([^"]*)"')
LLMS_LINK = re.compile(r"\]\(([^)]*)\)")
SITE_JS = JS_DIR / "site.js"
STYLE_CSS = ROOT / "site" / STYLE_NAME
SEMANTICS_ONLY_TERM = "diacritics"
THEME_STORAGE_KEYS = {"THEME_KEY", '"craticula-theme"'}
STORAGE_CALL = re.compile(r"(?:local|session)Storage\.\w+\(\s*([^,)\s]+)")
CHINESE_FONTS = ("PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "Hiragino Sans GB", "WenQuanYi Micro Hei", "SimHei")
CHINESE_FONT_FILE = re.compile(r"(?i)cjk|hans|chinese|[-_]sc[-_.]|han[-_]")
FONT_LIMIT = 100_000
NARROW_PIXELS = 320
SCROLLING_RULES = (".diagram svg",)
CSS_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
FIXED_WIDTH = re.compile(r"(?<![\w-])(?:min-)?width\s*:\s*(\d+(?:\.\d+)?)px")
STRIP_SAMPLE = (f'<head><link rel="alternate" hreflang="fr" href="https://x/fr/a{HTML_SUFFIX}"><link rel="canonical" href="https://x/a{HTML_SUFFIX}">'
                '<link rel="alternate" type="application/rss+xml" href="feed.xml"><link rel="icon" href="favicon.ico"></head>'
                '<body class="home" data-ui="{&quot;a&quot;:1}"><nav class="lang-menu" aria-label="Language"><details><a href="a'
                f'{HTML_SUFFIX}">English</a></details></nav>'
                '<nav class="pager"></nav></body>')
STRIP_EXPECTED = ('<head><link rel="alternate" type="application/rss+xml" href="feed.xml"><link rel="icon" href="favicon.ico"></head>'
                  '<body class="home"><nav class="pager"></nav></body>')
SEARCH_ENGLISH_KEYS = ("search_english", "search_english_url")
FOOTER_OPEN, FOOTER_CLOSE = "<footer", "</footer>"
# T039a: the longest footer text of the real five-language build (2026-11-19) is fr 73, de 73, it 69, es 74, zh 64 characters; each cap is
# that maximum plus a margin of about 7 (English keeps its own cap of 90 in test_build_site_structure.py).
FOOTER_CAPS = {"fr": 80, "de": 80, "it": 76, "es": 82, "zh": 70}
FOOTER_CAP_CHARS = max(FOOTER_CAPS.values())   # the fixture build has no per-language wording: the largest cap applies
LICENCE_NAME = "Apache-2.0"
SCRIPT_OPENING = re.compile(r"<script\b")
BLOB_LINK = re.compile(r"https://github\.com/[^/]+/[^/]+/(?:blob|tree|raw)/[^/]+/(.*)$")
EXPECTED_SCRIPTS = 2


# ---------------------------------------------------------------- helpers

def language_dir(out: Path, code: str) -> Path:
    return out if code == ENGLISH else out / code


def read_page(build, code: str, slug: str) -> str:
    return (language_dir(build.out, code) / f"{slug}{HTML_SUFFIX}").read_text(encoding=ENCODING)


def region(markup: str, pattern: re.Pattern) -> str:
    found = pattern.search(markup)
    assert found, f"no {pattern.pattern[:30]} in the page"
    return found.group(0)


def english_slugs(build) -> list[str]:
    return [page.slug for page in site_pages(build.root) if page.scope == "english"]


def translated_slugs(build) -> list[str]:
    return [page.slug for page in site_pages(build.root) if page.scope == "translated"]


def menu_entries(markup: str) -> list[tuple[str, str, bool]]:
    """(name, href, current) of each link of the language control."""
    entries = []
    for attributes, label in ANCHOR.findall(region(markup, LANG_MENU)):
        entries.append((re.sub(r"<[^>]+>", "", label).strip(), HREF.search(attributes).group(1), "aria-current" in attributes))
    return entries


def control_href(current: str, target: str, slug: str) -> str:
    if current == target:
        return f"{slug}{HTML_SUFFIX}"
    up = "" if current == ENGLISH else "../"
    path = "" if target == ENGLISH else f"{target}/"
    return f"{up}{path}{slug}{HTML_SUFFIX}"


def marked_after(markup: str, href: str, mark: str, window: int = 250) -> bool:
    """Whether every link to `href` is followed by `mark` before the next link."""
    ends = [found.end() for found in re.finditer(re.escape(f'href="{href}"'), markup)]
    return bool(ends) and all(mark in markup[end:end + window].split("<a ")[0] for end in ends)


def page_ui(markup: str) -> dict:
    attribute = region(markup, DATA_UI_ATTRIBUTE)
    return json.loads(html.unescape(attribute.split('="', 1)[1][:-1]))


def english_chrome_left(markup: str) -> list[str]:
    needles = [f">{ENGLISH_UI[key]}<" for key in CHROME_TEXT_KEYS] + [f'"{ENGLISH_UI[key]}"' for key in CHROME_ATTRIBUTE_KEYS]
    needles += [f"<summary>{name}</summary>" for name in (*ENGLISH_UI[GROUP_NAMES].values(), *ENGLISH_UI["subgroups"].values())]
    return [needle for needle in needles if needle in markup]


def dangling_references(page: Path, out: Path) -> list[str]:
    missing = []
    for reference in REFERENCE.findall(page.read_text(encoding=ENCODING)):
        target = reference.partition("#")[0].partition("?")[0]
        if target and not SCHEME.match(reference) and not (page.parent / target).resolve().is_relative_to(out.resolve()):
            missing.append(f"{page.name}: {reference} leaves the build")
        elif target and not SCHEME.match(reference) and not (page.parent / target).resolve().exists():
            missing.append(f"{page.relative_to(out)}: {reference}")
    return missing


def tree_texts(out: Path) -> list[tuple[str, str]]:
    return [(path.relative_to(out).as_posix(), path.read_text(encoding=ENCODING)) for path in sorted(out.rglob("*"))
            if path.suffix in (HTML_SUFFIX, ".js", ".json", ".txt")]


_ENGLISH_BUILD: list = []


def english_build():
    """The real English site, built once, with a base address (no language previewed)."""
    if not _ENGLISH_BUILD:
        tmp = Path(tempfile.mkdtemp())
        errors = bs.build(ROOT, tmp / "out", BASE_URL)
        assert errors == [], errors
        _ENGLISH_BUILD.append(tmp)
    return _ENGLISH_BUILD[0] / "out"


def tearDownModule():
    for tmp in _ENGLISH_BUILD:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- T005: the English pin (green from the start)

class EnglishPin(unittest.TestCase):
    """FR-006, US1-AS10: the English output of the fixture does not change, whatever the language build adds."""

    def test_US1_AS10_the_english_fixture_output_equals_the_recorded_hashes_once_the_added_fragments_are_stripped(self):
        out = build_english_fixture()
        self.addCleanup(shutil.rmtree, out.parent, True)
        self.assertEqual(json.loads(PIN_FILE.read_text(encoding=ENCODING)), html_digests(out))

    def test_US1_AS10_the_pin_holds_the_home_page_and_one_other_page(self):
        self.assertEqual({f"index{HTML_SUFFIX}", f"guide{HTML_SUFFIX}"}, set(json.loads(PIN_FILE.read_text(encoding=ENCODING))))

    def test_US1_AS10_the_fixture_is_deterministic(self):
        first, second = build_english_fixture(), build_english_fixture()
        self.addCleanup(shutil.rmtree, first.parent, True)
        self.addCleanup(shutil.rmtree, second.parent, True)
        self.assertEqual(html_digests(first), html_digests(second))


class StripFunction(unittest.TestCase):
    """The strip function of the pin, on sample markup: it removes the four fragments this feature adds and nothing else."""

    def test_the_control_the_hreflang_and_canonical_links_and_data_ui_are_removed(self):
        self.assertEqual(STRIP_EXPECTED, strip_added_fragments(STRIP_SAMPLE))

    def test_markup_without_added_fragments_is_unchanged(self):
        self.assertEqual(STRIP_EXPECTED, strip_added_fragments(STRIP_EXPECTED))

    def test_the_asset_version_is_normalised_in_style_and_scripts_alike(self):
        markup = '<link rel="stylesheet" href="style.css?v=0123456789"><script src="site.js?v=abcdef0123" defer></script>'
        self.assertEqual('<link rel="stylesheet" href="style.css?v=HASH"><script src="site.js?v=HASH" defer></script>', normalise_versions(markup))


# ---------------------------------------------------------------- T006a: the control, the head and the structure of the build

class LanguageControl(unittest.TestCase):
    def test_US1_AS1_the_control_lists_every_enabled_language_by_its_own_name_with_the_current_one_marked(self):
        full = language_build(FULL)
        for code in ALL_CODES:
            with self.subTest(language=code):
                entries = menu_entries(read_page(full, code, SOME_TRANSLATED_PAGE))
                self.assertEqual([LANGUAGE_NAMES[c] for c in ALL_CODES], [name for name, _, _ in entries])
                self.assertEqual([LANGUAGE_NAMES[code]], [name for name, _, current in entries if current])

    def test_US1_AS1_a_build_that_enables_one_language_lists_english_and_that_language_only(self):
        partial = language_build(PARTIAL)
        names = [name for name, _, _ in menu_entries(read_page(partial, LANGUAGE_CODES[0], SOME_TRANSLATED_PAGE))]
        self.assertEqual([LANGUAGE_NAMES[ENGLISH], LANGUAGE_NAMES[LANGUAGE_CODES[0]]], names)

    def test_US1_AS2_the_control_of_a_translated_page_leads_to_the_same_page_in_each_language(self):
        full = language_build(FULL)
        for code in ALL_CODES:
            with self.subTest(language=code):
                hrefs = [href for _, href, _ in menu_entries(read_page(full, code, SOME_TRANSLATED_PAGE))]
                self.assertEqual([control_href(code, target, SOME_TRANSLATED_PAGE) for target in ALL_CODES], hrefs)

    def test_US1_AS3_the_control_of_an_english_only_page_leads_to_each_home_page_and_says_the_page_is_english_only(self):
        full = language_build(FULL)
        for slug in ENGLISH_ONLY_PAGES:
            with self.subTest(page=slug):
                markup = read_page(full, ENGLISH, slug)
                hrefs = [href for _, href, _ in menu_entries(markup)]
                self.assertEqual([f"{slug}{HTML_SUFFIX}"] + [f"{code}/{INDEX_SLUG}{HTML_SUFFIX}" for code in LANGUAGE_CODES], hrefs)
                menu = region(markup, LANG_MENU)
                self.assertEqual([], [code for code in LANGUAGE_CODES if ui_strings(code)["english_only"] not in menu])

    def test_US1_AS12_the_control_is_made_of_plain_links(self):
        full = language_build(FULL)
        for code in ALL_CODES:
            with self.subTest(language=code):
                menu = region(read_page(full, code, SOME_TRANSLATED_PAGE), LANG_MENU)
                self.assertEqual([], [tag for tag in ("<button", "<script", "onclick", "<form") if tag in menu])
                self.assertEqual(len(ALL_CODES), len(ANCHOR.findall(menu)))


class InterfaceLanguage(unittest.TestCase):
    def test_US1_AS4_a_language_page_declares_its_language(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual(LANG_ATTRIBUTES[code], HTML_LANG.search(read_page(full, code, SOME_TRANSLATED_PAGE)).group(1))
        self.assertEqual("zh-Hans", HTML_LANG.search(read_page(full, "zh", INDEX_SLUG)).group(1))

    def test_US1_AS4_no_english_interface_text_is_left_on_a_language_page(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            for slug in (SOME_TRANSLATED_PAGE, INDEX_SLUG):
                with self.subTest(language=code, page=slug):
                    self.assertEqual([], english_chrome_left(read_page(full, code, slug)))

    def test_US1_AS4_the_interface_strings_are_those_of_the_language(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, SOME_TRANSLATED_PAGE)
                ui = ui_strings(code)
                for expected in (ui["skip"], ui["on_this_page"], ui["menu_button"], ui["nav_docs"], html.escape(ui["search_aria"])):
                    self.assertIn(expected, markup)

    def test_US1_AS4_the_page_hands_the_messages_of_the_script_to_the_script(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual(json.loads(si.script_ui(ui_strings(code))), page_ui(read_page(full, code, SOME_TRANSLATED_PAGE)))

    def test_US1_AS4_the_script_reads_its_messages_from_the_page(self):
        self.assertIn("dataset.ui", SITE_JS.read_text(encoding=ENCODING))


class Alternates(unittest.TestCase):
    def alternates_of(self, markup: str) -> dict[str, str]:
        return dict(ALTERNATE.findall(markup))

    def test_US1_AS5_a_translated_page_names_its_canonical_address_and_every_language_version(self):
        full = language_build(FULL)
        for code in ALL_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, SOME_TRANSLATED_PAGE)
                own = f"{BASE_URL}/" + ("" if code == ENGLISH else f"{code}/") + f"{SOME_TRANSLATED_PAGE}{HTML_SUFFIX}"
                self.assertEqual([own], CANONICAL.findall(markup))
                expected = {LANG_ATTRIBUTES[c]: f"{BASE_URL}/" + ("" if c == ENGLISH else f"{c}/") + f"{SOME_TRANSLATED_PAGE}{HTML_SUFFIX}" for c in ALL_CODES}
                expected["x-default"] = f"{BASE_URL}/{SOME_TRANSLATED_PAGE}{HTML_SUFFIX}"
                self.assertEqual(expected, self.alternates_of(markup))

    def test_US1_AS5_an_english_only_page_carries_its_english_canonical_address_and_x_default_only(self):
        full = language_build(FULL)
        for slug in ENGLISH_ONLY_PAGES:
            with self.subTest(page=slug):
                markup = read_page(full, ENGLISH, slug)
                english = f"{BASE_URL}/{slug}{HTML_SUFFIX}"
                self.assertEqual([english], CANONICAL.findall(markup))
                alternates = self.alternates_of(markup)
                self.assertIn("x-default", alternates)
                self.assertEqual({english}, set(alternates.values()))
                self.assertEqual(set(), set(alternates) & {LANG_ATTRIBUTES[code] for code in LANGUAGE_CODES})

    def test_US1_AS16_a_build_with_no_base_address_omits_canonical_and_hreflang_links(self):  # US1-AS16
        partial = language_build(PARTIAL)
        for code in (ENGLISH, LANGUAGE_CODES[0]):
            with self.subTest(language=code):
                markup = read_page(partial, code, SOME_TRANSLATED_PAGE)
                self.assertEqual([], CANONICAL.findall(markup))
                self.assertEqual({}, self.alternates_of(markup))
                self.assertNotIn('rel="alternate"', markup)


class AssetsAndStructure(unittest.TestCase):
    def test_US1_AS13_a_language_page_loads_the_shared_assets_from_the_root_and_the_stylesheet_stays_versioned(self):
        full = language_build(FULL)
        version = hashlib.sha256((full.out / STYLE_NAME).read_bytes()).hexdigest()[:10]
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, SOME_TRANSLATED_PAGE)
                self.assertIn(f'href="../style.css?v={version}"', markup)
                self.assertRegex(markup, r'src="\.\./theme\.js\?v=[0-9a-f]{10}"')
                self.assertRegex(markup, r'src="\.\./site\.js\?v=[0-9a-f]{10}"')
                self.assertIn('href="../favicon.svg"', markup)
                self.assertNotRegex(markup, r'(?:href|src)="(?:style\.css|theme\.js|site\.js|favicon)')

    def test_US1_AS13_every_internal_reference_of_a_language_page_resolves_from_its_own_address(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                missing = [problem for page in sorted((full.out / code).glob(f"*{HTML_SUFFIX}")) for problem in dangling_references(page, full.out)]
                self.assertEqual([], missing)

    def test_US1_AS13_a_page_whose_slug_is_a_language_prefix_is_refused(self):
        entry = {"slug": LANGUAGE_CODES[0], TITLE_KEY: "French", "source": "index.md", "group": "Guides", "description": "A clash."}
        root = make_repo({"index.md": "# French\n"}, [entry, {**entry, "slug": INDEX_SLUG, TITLE_KEY: "Home"}],
                         languages={"en": {"name": "English", "path": "", "lang": "en"},
                                    LANGUAGE_CODES[0]: {"name": "Français", "path": LANGUAGE_CODES[0], "lang": LANGUAGE_CODES[0], "enabled": False}})
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaisesRegex(bs.BuildError, LANGUAGE_CODES[0]):
            bs.build(root, root / "_out")

    def test_US1_AS11_each_enabled_language_gets_its_folder_with_its_translated_documents_only(self):
        full = language_build(FULL)
        expected = {f"{slug}{HTML_SUFFIX}" for slug in translated_slugs(full)}
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual(expected, {page.name for page in (full.out / code).glob(f"*{HTML_SUFFIX}")})

    def test_FR_023_the_shared_assets_are_written_once_at_the_root(self):
        full = language_build(FULL)
        shared = (STYLE_NAME, "theme.js", "site.js", "favicon.svg", "favicon.ico", "apple-touch-icon.png")
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual([], [name for name in shared if (full.out / code / name).exists()])
                self.assertFalse((full.out / code / "fonts").exists())
        self.assertEqual([], [name for name in shared if not (full.out / name).is_file()])

    def test_FR_024_the_folder_of_a_disabled_language_is_cleared_and_the_enabled_one_is_written(self):
        partial = language_build(PARTIAL)
        self.assertTrue((partial.out / LANGUAGE_CODES[0] / f"{SOME_TRANSLATED_PAGE}{HTML_SUFFIX}").is_file())
        for code in LANGUAGE_CODES[1:]:
            with self.subTest(language=code):
                self.assertFalse((partial.out / code / LEFTOVER).exists())

    def test_FR_026_an_english_only_page_is_built_once_at_its_english_address(self):
        full = language_build(FULL)
        slugs = english_slugs(full)
        self.assertEqual([], [slug for slug in slugs if not (full.out / f"{slug}{HTML_SUFFIX}").is_file()])
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual([], [slug for slug in slugs if (full.out / code / f"{slug}{HTML_SUFFIX}").exists() or (full.out / code / f"{slug}.md").exists()])


# ---------------------------------------------------------------- T006b: sidebar, pager and links

class SidebarAndPager(unittest.TestCase):
    def sidebar(self, build, code: str, slug: str = LINKED_PAGE) -> str:
        return region(read_page(build, code, slug), SIDEBAR)

    def test_US1_AS11_the_group_and_subgroup_names_of_the_sidebar_are_in_the_language(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                sidebar = self.sidebar(full, code)
                ui = ui_strings(code)
                names = (*ui[GROUP_NAMES].values(), *ui["subgroups"].values())
                self.assertEqual([], [name for name in names if f"<summary>{name}</summary>" not in sidebar])

    def test_US1_AS11_the_sidebar_lists_the_translated_pages_under_their_translated_titles(self):
        full = language_build(FULL)
        pages = [page for page in site_pages(full.root) if page.scope == "translated" and page.slug != INDEX_SLUG]
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                sidebar = self.sidebar(full, code)
                missing = [page.slug for page in pages if not re.search(rf'href="{page.slug}{re.escape(HTML_SUFFIX)}"[^>]*>\[{code}\] {re.escape(html.escape(page.title))}</a>', sidebar)]
                self.assertEqual([], missing)

    def test_US1_AS11_the_sidebar_marks_each_english_only_page_and_links_it_at_its_english_address(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                sidebar = self.sidebar(full, code)
                unmarked = [slug for slug in english_slugs(full) if not marked_after(sidebar, f"../{slug}{HTML_SUFFIX}", MARKS[code])]
                self.assertEqual([], unmarked)
                self.assertEqual([], [slug for slug in translated_slugs(full) if f'href="../{slug}{HTML_SUFFIX}"' in sidebar])

    def test_US1_AS11_the_sidebar_of_a_language_page_on_the_real_tree_has_24_english_entries(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                items = LEAF_ITEM.findall(self.sidebar(full, code))
                self.assertEqual(24, len([item for item in items if MARKS[code] in item]))
                self.assertEqual(24, len(english_slugs(full)))

    def test_US1_AS11_the_pager_marks_an_english_only_neighbour_at_the_boundary_and_not_a_translated_one(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                pager = region(read_page(full, code, README_PAGE), PAGER)
                self.assertIn(html.escape(ui_strings(code)["pager_label"]), pager)
                self.assertTrue(marked_after(pager, SPEC_HREF, MARKS[code]))
                self.assertIn(f'href="dialects-and-providers{HTML_SUFFIX}"', pager)
                self.assertNotIn(MARKS[code], pager.split(f'href="{SPEC_HREF}"')[0])

    def test_US1_AS11_the_pager_uses_the_words_of_the_language(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                pager = region(read_page(full, code, README_PAGE), PAGER)
                ui = ui_strings(code)
                self.assertEqual([], [word for word in (ui["previous"], ui["next"]) if word not in pager])


class LinkRewriting(unittest.TestCase):
    ENGLISH_TARGETS = (SEMANTICS_TARGET, f"spec{HTML_SUFFIX}", f"performance{HTML_SUFFIX}", f"semantics{HTML_SUFFIX}", f"grid-schema{HTML_SUFFIX}")

    def page(self, build, code: str, slug: str = LINKED_PAGE) -> str:
        return read_page(build, code, slug)

    def test_US1_AS11_links_into_english_only_pages_go_to_the_english_address_with_their_fragment_and_carry_the_mark(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            for target in self.ENGLISH_TARGETS:
                with self.subTest(language=code, target=target):
                    markup = self.page(full, code)
                    self.assertTrue(marked_after(markup, f"../{target}", MARKS[code]))
                    self.assertNotIn(target, [HREF.search(attrs).group(1) for attrs, _ in ANCHOR.findall(markup) if HREF.search(attrs)])

    def test_US1_AS11_the_same_holds_for_a_translation_of_the_readme_whose_links_start_at_the_repository_root(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = self.page(full, code, README_PAGE)
                self.assertIn(HANDWRITTEN_OVERVIEW, markup)
                self.assertTrue(marked_after(markup, f"../{SEMANTICS_TARGET}", MARKS[code]))
                self.assertTrue(marked_after(markup, SPEC_HREF, MARKS[code]))
                self.assertTrue(marked_after(markup, f"../performance{HTML_SUFFIX}", MARKS[code]))

    def test_US1_AS11_a_link_to_a_translated_page_that_has_a_file_stays_in_the_language_and_is_not_marked(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = self.page(full, code)
                self.assertIn(f'href="{SIBLING_PAGE}{HTML_SUFFIX}"', markup)
                self.assertFalse(marked_after(markup, f"{SIBLING_PAGE}{HTML_SUFFIX}", MARKS[code]))
                self.assertFalse(marked_after(markup, f"{README_PAGE}{HTML_SUFFIX}", MARKS[code]))
                self.assertNotIn(f'href="../{SIBLING_PAGE}{HTML_SUFFIX}"', markup)

    def test_US1_AS11_a_link_to_a_translated_page_with_no_file_in_a_preview_build_goes_to_the_english_page_with_the_mark(self):
        partial = language_build(PARTIAL)
        code = LANGUAGE_CODES[0]
        self.assertFalse((partial.out / code / f"{README_PAGE}{HTML_SUFFIX}").exists())
        markup = self.page(partial, code)
        self.assertTrue(marked_after(markup, f"../{README_PAGE}{HTML_SUFFIX}", MARKS[code]))
        self.assertTrue(marked_after(region(markup, SIDEBAR), f"../{README_PAGE}{HTML_SUFFIX}", MARKS[code]))
        self.assertFalse(marked_after(markup, f"{SIBLING_PAGE}{HTML_SUFFIX}", MARKS[code]))

    def test_US1_AS13_fragment_only_links_external_addresses_and_assets_are_left_alone(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = self.page(full, code)
                self.assertIn('href="#section-one"', markup)
                self.assertIn(f'href="{OUTSIDE_LINK}"', markup)
                self.assertFalse(marked_after(markup, OUTSIDE_LINK, MARKS[code]))
                self.assertNotIn("../https", markup)
                self.assertNotIn("../../", markup)
                self.assertRegex(markup, r'href="\.\./style\.css\?v=[0-9a-f]{10}"')

    def test_US1_AS11_the_rewrite_marks_each_link_once(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = self.page(full, code)
                rewritten = sum(markup.count(f'href="../{slug}{HTML_SUFFIX}') for slug in english_slugs(full))
                self.assertEqual(rewritten, markup.count(MARKS[code]))

    def test_US1_AS11_a_code_block_that_shows_an_english_only_link_is_not_rewritten(self):
        full = language_build(FULL)
        shown = bs.render_markdown(f"```html\n{CODE_SNIPPET}\n```\n").html.strip()
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = self.page(full, code)
                self.assertIn(shown, markup)
                self.assertNotIn(f"../grid-schema{HTML_SUFFIX}", "".join(PRE_BLOCK.findall(markup)))
                self.assertIn(HANDWRITTEN, markup)


# ---------------------------------------------------------------- T006c: the home page

class HomePage(unittest.TestCase):
    def test_US1_AS15_the_group_cards_of_the_home_page_are_in_the_language(self):  # US1-AS15
        full = language_build(FULL)
        english_cards = bs.load_config(ROOT)["groups"].values()
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, INDEX_SLUG)
                ui = ui_strings(code)
                for name in ui[GROUP_NAMES]:
                    self.assertIn(f"<h3>{ui[GROUP_NAMES][name]}</h3><p>{ui['groups'][name]}</p>", markup)
                self.assertEqual([], [text for text in english_cards if html.escape(text) in markup])

    def test_US1_AS15_the_link_list_of_the_home_page_is_translated_and_its_english_only_links_are_rewritten_and_marked(self):  # US1-AS15
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, INDEX_SLUG)
                self.assertIn(f"[{code}] Home", markup)
                self.assertIn(f'href="quickstart-csharp{HTML_SUFFIX}"', markup)
                self.assertTrue(marked_after(markup, SPEC_HREF, MARKS[code]))
                self.assertTrue(marked_after(markup, f"../semantics{HTML_SUFFIX}", MARKS[code]))

    def test_US1_AS15_a_translated_home_template_that_keeps_the_english_href_has_it_rewritten_and_marked(self):  # US1-AS15
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, INDEX_SLUG)
                self.assertIn(f"[{code}] Declare a GridSchema", markup)
                self.assertTrue(marked_after(markup, f"../grid-schema{HTML_SUFFIX}", MARKS[code]))
                self.assertNotIn(f"grid-schema{HTML_SUFFIX}", [HREF.search(attrs).group(1) for attrs, _ in ANCHOR.findall(markup) if HREF.search(attrs)])
                self.assertIn(f"[{code}] Find your way in", markup)


# ---------------------------------------------------------------- T007a: search and llms files

class SearchIndex(unittest.TestCase):
    def index_of(self, out: Path) -> list[dict]:
        return json.loads((out / "search-index.json").read_text(encoding=ENCODING))

    def test_US1_AS9_each_language_has_its_own_index_over_translated_pages_only_with_translated_group_names(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                entries = self.index_of(full.out / code)
                self.assertEqual(sorted(translated_slugs(full)), sorted(entry["slug"] for entry in entries))
                groups = {entry["group"] for entry in entries if entry["slug"] != INDEX_SLUG}
                self.assertEqual(set(), groups - set(ui_strings(code)[GROUP_NAMES].values()))
                self.assertTrue(all(entry[TITLE_KEY].startswith(f"[{code}]") for entry in entries))

    def test_FR_015_the_english_index_covers_every_page(self):
        full = language_build(FULL)
        self.assertEqual(sorted(page.slug for page in site_pages(full.root)), sorted(entry["slug"] for entry in self.index_of(full.out)))

    def test_US1_AS17_the_english_index_finds_a_term_only_a_semantics_page_contains(self):  # US1-AS17
        index = self.index_of(english_build())
        scopes = {page.slug: page.scope for page in site_pages(ROOT)}
        hits = [entry["slug"] for entry in index if SEMANTICS_ONLY_TERM in entry["text"].lower()]
        self.assertTrue(hits)
        self.assertEqual({"english"}, {scopes[slug] for slug in hits})

    def test_US1_AS9_the_search_box_says_in_the_language_where_the_english_site_is_searched(self):
        self.assertEqual([], [key for key in SEARCH_ENGLISH_KEYS if key not in si.SCRIPT_KEYS])
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                handed = json.loads(si.script_ui(ui_strings(code)))
                self.assertEqual({key: ui_strings(code)[key] for key in SEARCH_ENGLISH_KEYS}, {key: handed.get(key) for key in SEARCH_ENGLISH_KEYS})


class LlmsFiles(unittest.TestCase):
    def links(self, path: Path) -> list[str]:
        return LLMS_LINK.findall(path.read_text(encoding=ENCODING))

    def test_FR_016_a_language_llms_txt_links_translated_pages_in_the_language_and_english_only_pages_at_their_english_address(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                links = self.links(full.out / code / LLMS_NAME)
                expected = [f"{BASE_URL}/{code}/{slug}.md" for slug in translated_slugs(full)] + [f"{BASE_URL}/{slug}.md" for slug in english_slugs(full)]
                self.assertEqual(sorted(expected), sorted(links))

    def test_FR_016_a_language_llms_txt_names_the_english_source_and_takes_its_section_titles_from_the_interface_file(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                text = (full.out / code / LLMS_NAME).read_text(encoding=ENCODING)
                ui = ui_strings(code)
                self.assertEqual([], [title for title in (ui["llms_home"], *ui[GROUP_NAMES].values()) if f"## {title}\n" not in text])
                self.assertTrue([line for line in text.splitlines() if ui["llms_english_source"] in line and BASE_URL in line])

    def test_FR_016_a_language_llms_full_txt_holds_the_translated_pages_and_names_the_english_source(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                text = (full.out / code / "llms-full.txt").read_text(encoding=ENCODING)
                self.assertEqual([], [slug for slug in translated_slugs(full) if f"| {slug}.md ====" not in text])
                self.assertEqual([], [slug for slug in english_slugs(full) if f"| {slug}.md ====" in text])
                self.assertIn(ui_strings(code)["llms_english_source"], text)

    def test_FR_016_the_source_of_each_translated_page_is_copied_next_to_it(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertEqual([], [slug for slug in translated_slugs(full) if not (full.out / code / f"{slug}.md").is_file()])
                self.assertIn(HANDWRITTEN, (full.out / code / f"{LINKED_PAGE}.md").read_text(encoding=ENCODING))

    def test_FR_016_the_english_llms_txt_still_lists_every_page_once(self):  # US1-AS17
        full = language_build(FULL)
        links = self.links(full.out / LLMS_NAME)
        self.assertEqual(sorted(f"{BASE_URL}/{page.slug}.md" for page in site_pages(full.root)), sorted(links))


# ---------------------------------------------------------------- T007b: the script and the stylesheet

def fixed_widths(css: str) -> list[tuple[str, float]]:
    return [(selector.strip(), float(value)) for selector, body in CSS_BLOCK.findall(css) for value in FIXED_WIDTH.findall(body)
            if float(value) > NARROW_PIXELS and selector.strip() not in SCROLLING_RULES]


def chinese_font_rules(css: str) -> list[str]:
    return [body for selector, body in CSS_BLOCK.findall(css) if re.search(r'lang\W*"?zh', selector) and "font-family" in body]


class ScriptStorage(unittest.TestCase):
    def test_US1_AS6_the_only_storage_key_of_the_scripts_is_the_themes(self):
        keys = {key for script in sorted(JS_DIR.glob("*.js")) for key in STORAGE_CALL.findall(script.read_text(encoding=ENCODING))}
        self.assertTrue(keys)
        self.assertLessEqual(keys, THEME_STORAGE_KEYS)
        self.assertIn('const THEME_KEY = "craticula-theme"', SITE_JS.read_text(encoding=ENCODING))

    def test_US1_AS6_no_script_of_the_site_writes_a_cookie(self):
        self.assertEqual([], [script.name for script in JS_DIR.glob("*.js") if "cookie" in script.read_text(encoding=ENCODING).lower()])

    def test_US1_AS6_the_build_writes_no_cookie_and_no_language_storage_into_any_page_or_script(self):
        full = language_build(FULL)
        offenders = [name for name, text in tree_texts(full.out) if re.search(r"(?i)set-cookie|document\.cookie|localStorage\.\w+\(\s*[\"'](?!craticula-theme)", text)]
        self.assertEqual([], offenders)


class ChineseSearch(unittest.TestCase):
    """US1-AS8: a characterisation that passes before and after any change to the search; the browser check is the G2 manual one."""

    def terms_pattern(self) -> str:
        found = re.search(r"const terms = .*?\.split\(/(.+?)/\)", SITE_JS.read_text(encoding=ENCODING))
        self.assertIsNotNone(found, "site.js has no `terms` that splits on a pattern")
        return found.group(1)

    def terms(self, query: str) -> list[str]:
        return [word for word in re.split(self.terms_pattern(), query.lower()) if word]

    def test_US1_AS8_a_one_character_term_and_a_run_of_characters_are_one_term_each(self):
        self.assertEqual(["数"], self.terms("数"))
        self.assertEqual(["数据库"], self.terms("数据库"))

    def test_US1_AS8_two_terms_separated_by_a_full_width_space_are_two_terms(self):
        self.assertEqual(["数据", "搜索"], self.terms("数据　搜索"))

    def test_US1_AS8_a_term_matches_inside_a_run_of_characters(self):
        found = re.search(r"const has = .*?\n  \};", SITE_JS.read_text(encoding=ENCODING), re.S)
        self.assertIsNotNone(found, "site.js has no `has`")
        self.assertIn(".includes(", found.group(0))


class Stylesheet(unittest.TestCase):
    def css(self) -> str:
        return STYLE_CSS.read_text(encoding=ENCODING)

    def test_US1_AS7_chinese_text_is_set_in_a_stack_of_chinese_system_fonts(self):
        rules = chinese_font_rules(self.css())
        self.assertTrue(rules, "no rule for lang zh sets a font-family")
        self.assertTrue([body for body in rules if len([font for font in CHINESE_FONTS if font in body]) >= 2])

    def test_US1_AS7_the_stylesheet_holds_no_remote_font_or_address(self):
        css = self.css()
        self.assertNotIn("@import", css)
        self.assertEqual([], [address for address in re.findall(r"url\(\s*[\"']?([^)\"']+)", css) if re.match(r"(?i)(?:https?:)?//", address)])

    def test_US1_AS7_no_font_file_over_100_KB_and_none_for_chinese_was_added(self):
        fonts = [path for path in (ROOT / "site" / "fonts").iterdir() if path.suffix in (".woff", ".woff2", ".ttf", ".otf")]
        self.assertTrue(fonts)
        self.assertEqual([], [path.name for path in fonts if path.stat().st_size > FONT_LIMIT])
        self.assertEqual([], [path.name for path in fonts if CHINESE_FONT_FILE.search(path.name)])

    def test_US1_AS14_no_rule_fixes_a_width_above_320_px_outside_a_scrolling_container(self):  # US1-AS14
        self.assertEqual([], fixed_widths(self.css()))

    def test_US1_AS14_long_words_and_unspaced_lines_wrap_in_the_page_and_in_the_language_control(self):  # US1-AS14
        blocks = CSS_BLOCK.findall(self.css())
        self.assertTrue([body for selector, body in blocks if ".prose" in selector and "overflow-wrap" in body])
        control = [(selector, body) for selector, body in blocks if "lang-menu" in selector or "lang-panel" in selector]
        self.assertTrue(control, "no rule styles the language control")
        self.assertTrue([selector for selector, body in control if "overflow-wrap" in body or "word-break" in body])



# ---------------------------------------------------------------- T014b, T015: the build of a translation (US2-AS4, AS8, AS11, AS15, US4-AS4, AS5)

FRENCH = LANGUAGE_CODES[0]
EDITED_PAGE = "quickstart-csharp"
EDITED_FILE = f"site/i18n/{FRENCH}/{EDITED_PAGE}.md"
SCRIPT_SRC = re.compile(r'src="(?:\.\./)?(?:theme|site)\.js(?:\?v=[0-9a-f]{10})?"')
SCRIPT_TAG = re.compile(r"<script\b[^>]*>")
RESOURCE_TAG = re.compile(r"<(?:img|source|iframe|video|audio|embed|object|link)\b[^>]*>")
REMOTE = re.compile(r'(?:src|href)="(?:https?:)?//')
SELF_REFERENCE = re.compile(r'rel="(?:canonical|alternate)"')  # the language links of FR-004 name the site's own addresses
ANCHOR_HREF = re.compile(r'<a\b[^>]*?\bhref="([^"]+)"')
STATE_FINDING = re.compile(r"not approved|stale|: missing")
SEARCH_NAME = "search-index.json"
LONG_ANCHOR = "{#an-english-anchor-that-is-long-but-is-not-part-of-the-label}"
SEARCH_SAMPLE = ('<script src="https://x.example/a.js"></script><script>inline()</script><img src="https://x.example/p.png">'
                 '<link rel="stylesheet" href="https://x.example/s.css"><a href="../docs/notes.md">n</a>')
SOURCE_FOLDERS = ("site/pages", "spec")
DECLARED_HEADING = re.compile(r"^#{1,6}\s+.*\{#[^}]*\}\s*$", re.M)


def foreign_requests(markup: str) -> list[str]:
    """What a built page must not hold (FR-018, DSN-1, DSN-6): a script that is not the site's own file, a resource or link tag with a remote
    address, an anchor into a private path."""
    found = [tag for tag in SCRIPT_TAG.findall(markup) if not SCRIPT_SRC.search(tag)]
    found += [tag for tag in RESOURCE_TAG.findall(markup) if REMOTE.search(tag) and not SELF_REFERENCE.search(tag)]
    for target in ANCHOR_HREF.findall(markup):
        path = target.partition("#")[0]
        while path.startswith("../"):
            path = path[3:]
        if path and not SCHEME.match(path) and bs._is_private(path):
            found.append(target)
    return found


_REAL = {}


def real_build() -> SimpleNamespace:
    """The repository's own tree built once per run with all five languages previewed (T039a, T039b); `seconds` is the build time."""
    if not _REAL:
        tmp = Path(tempfile.mkdtemp())
        atexit.register(shutil.rmtree, tmp, True)
        out = tmp / "out"
        start = time.perf_counter()
        errors = bs.build(ROOT, out, None, preview=LANGUAGE_CODES)
        _REAL["build"] = SimpleNamespace(out=out, errors=errors, seconds=time.perf_counter() - start)
    return _REAL["build"]


def language_pages(out: Path, code: str) -> list[Path]:
    return sorted((out / code).glob(f"*{HTML_SUFFIX}"))


class Scratch(unittest.TestCase):
    """A copy of the repository's sources with the fixture translations, edited by a test and built once in its own folder."""

    def tree(self, omit: tuple[str, ...] = ()) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.out = tmp / "out"
        return language_tree(tmp, omit)

    def translate(self, root: Path, body: str, title: str = "T", description: str = "D") -> None:
        write_tree(root, {EDITED_FILE: translation_file(EDITED_PAGE, title, description, body)})

    def build(self, root: Path, preview: tuple[str, ...] = (FRENCH,)) -> list[str]:
        return bs.build(root, self.out, None, preview=preview)

    def edited(self, body: str, title: str = "T", description: str = "D") -> list[str]:
        """The errors of a French build whose page `quickstart-csharp` has this text."""
        root = self.tree()
        self.translate(root, body, title, description)
        return self.build(root)

    def page_errors(self, errors: list[str]) -> list[str]:
        return [error for error in errors if EDITED_PAGE in error]

    def configure(self, root: Path, enable: bool) -> None:
        path = root / "site" / "site.json"
        config = json.loads(path.read_text(encoding=ENCODING))
        config["languages"][FRENCH]["enabled"] = enable
        path.write_text(json.dumps(config), encoding=ENCODING)


class BuiltFolderScan(Scratch):
    """T014b, US2-AS8, FR-018: the output scan runs over a built language folder, which the whole-site scans of the English tests do not read."""

    def test_the_scan_finds_a_foreign_script_resource_link_and_private_anchor(self):
        self.assertEqual(5, len(foreign_requests(SEARCH_SAMPLE)))

    def test_US2_AS8_no_page_of_any_built_language_has_a_foreign_request_or_a_private_anchor(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            pages = language_pages(full.out, code)
            self.assertEqual(DOCUMENT_COUNT, len(pages))
            for page in pages:
                with self.subTest(language=code, page=page.name):
                    self.assertEqual([], foreign_requests(page.read_text(encoding=ENCODING)))

    def test_US2_AS8_raw_html_and_a_remote_image_in_a_translation_are_escaped_and_make_no_request(self):
        body = '# T {#t}\n\n<img src="https://evil.example/q.png"> ![x](https://evil.example/p.png)\n'
        errors = self.edited(body)
        self.assertEqual([], self.page_errors(errors))
        markup = (self.out / FRENCH / f"{EDITED_PAGE}{HTML_SUFFIX}").read_text(encoding=ENCODING)
        self.assertIn("&lt;img src=", markup)
        self.assertEqual([], foreign_requests(markup))

    def test_US2_AS8_a_script_or_an_event_handler_in_a_translation_is_refused_naming_the_file(self):
        for name, body in {"script": "# T {#t}\n\n<script>alert(1)</script>\n", "handler": '# T {#t}\n\n<b onclick="x()">b</b>\n'}.items():
            with self.subTest(markup=name):
                errors = self.edited(body)
                self.assertTrue(any(EDITED_FILE in error for error in errors), errors)

    def test_US2_AS8_a_link_into_a_private_path_in_a_translation_is_refused(self):
        errors = self.edited("# T {#t}\n\n[notes](../../docs/notes.md)\n")
        self.assertTrue(any("private" in error and EDITED_PAGE in error for error in errors), errors)


class FooterAndScripts(unittest.TestCase):
    """T020b, FR-028, FR-018: the footer of every built language and the whole-site output rules over a built language folder."""

    def pages(self):
        full = language_build(FULL)
        return full, [(code, page) for code in LANGUAGE_CODES for page in language_pages(full.out, code)]

    def test_FR_028_the_footer_of_every_built_language_holds_the_licence_the_repository_and_the_spec_version_within_the_cap(self):
        full, pages = self.pages()
        version = (ROOT / "spec" / "VERSION").read_text(encoding=ENCODING).strip()
        repository = full.config["repo"].split("//", 1)[1]
        self.assertEqual(len(LANGUAGE_CODES) * DOCUMENT_COUNT, len(pages))
        for code, page in pages:
            with self.subTest(language=code, page=page.name):
                markup = page.read_text(encoding=ENCODING)
                start = markup.find(FOOTER_OPEN)
                self.assertGreaterEqual(start, 0)
                foot = markup[start:markup.find(FOOTER_CLOSE, start) + len(FOOTER_CLOSE)]
                plain = " ".join(re.sub(r"<[^>]+>", " ", foot).split())
                self.assertIn(LICENCE_NAME, plain)
                self.assertIn(f"spec {version}", plain)
                self.assertIn(repository, plain + " ".join(HREF.findall(foot)))
                self.assertLessEqual(len(plain), FOOTER_CAPS[code])

    def test_FR_028_the_footer_of_every_page_of_the_real_tree_in_every_language_holds_the_licence_the_repository_and_the_spec_version_within_its_cap(self):
        real = real_build()
        version = (ROOT / "spec" / "VERSION").read_text(encoding=ENCODING).strip()
        for code in LANGUAGE_CODES:
            pages = language_pages(real.out, code)
            self.assertEqual(DOCUMENT_COUNT, len(pages))
            for page in pages:
                with self.subTest(language=code, page=page.name):
                    markup = page.read_text(encoding=ENCODING)
                    start = markup.find(FOOTER_OPEN)
                    self.assertGreaterEqual(start, 0)
                    foot = markup[start:markup.find(FOOTER_CLOSE, start) + len(FOOTER_CLOSE)]
                    plain = " ".join(re.sub(r"<[^>]+>", " ", foot).split())
                    self.assertIn(LICENCE_NAME, plain)
                    self.assertIn(f"spec {version}", plain)
                    self.assertIn("github.com/pluries/craticula", plain + " ".join(HREF.findall(foot)))
                    self.assertLessEqual(len(plain), FOOTER_CAPS[code])

    def test_FR_018_a_built_language_page_holds_only_the_two_own_scripts_and_no_inline_body(self):
        _, pages = self.pages()
        for code, page in pages:
            with self.subTest(language=code, page=page.name):
                markup = page.read_text(encoding=ENCODING)
                self.assertEqual(EXPECTED_SCRIPTS, len(SCRIPT_OPENING.findall(markup)))
                self.assertEqual(EXPECTED_SCRIPTS, markup.count("></script>"))

    def test_FR_018_no_link_of_a_built_language_page_points_into_a_private_path_even_on_the_repository_address(self):
        _, pages = self.pages()
        for code, page in pages:
            with self.subTest(language=code, page=page.name):
                for target in HREF.findall(page.read_text(encoding=ENCODING)):
                    path = target.partition("#")[0].partition("?")[0]
                    blob = BLOB_LINK.match(path)
                    path = blob.group(1) if blob else path
                    while path.startswith(("./", "../")):
                        path = path.split("/", 1)[1]
                    if not SCHEME.match(path):
                        self.assertFalse(bs._is_private(path), target)

    def test_FR_018_raw_html_of_the_sources_is_never_written_as_a_tag_in_a_built_language_page(self):
        _, pages = self.pages()
        for code, page in pages:
            with self.subTest(language=code, page=page.name):
                markup = PRE_BLOCK.sub("", page.read_text(encoding=ENCODING))
                self.assertEqual([], re.findall(r"<(?:img|iframe|object|embed|form)\b", markup))
                self.assertEqual([], re.findall(r"<[a-z][^>]*\son[a-z]+=", markup))


class DeclaredAnchors(Scratch):
    """T014b, US2-AS11, FR-010: a translated heading declares the English anchor; the build fails when it does not."""

    def test_US2_AS11_the_stub_translations_of_the_fixture_declare_their_anchors_and_the_build_has_no_error(self):
        self.assertEqual([], language_build(FULL).errors)

    def test_US2_AS11_a_heading_without_an_anchor_fails_the_build_naming_the_page_and_the_heading(self):
        errors = self.edited("# T {#t}\n\n## Un titre\n\nTexte.\n")
        self.assertTrue(any(EDITED_PAGE in error and "Un titre" in error for error in errors), errors)

    def test_US2_AS11_a_page_whose_headings_all_declare_an_anchor_builds_without_error(self):
        self.assertEqual([], self.page_errors(self.edited("# T {#t}\n\n## Un titre {#a-title}\n\nTexte.\n")))

    def test_US2_AS11_a_duplicate_declared_anchor_in_one_page_fails_the_build(self):
        errors = self.edited("# T {#same}\n\n## U {#same}\n\nTexte.\n")
        self.assertTrue(any(EDITED_PAGE in error and "same" in error for error in errors), errors)

    def test_US2_AS11_the_declared_anchor_is_the_id_of_the_heading_in_the_toc_and_in_the_search_entry(self):
        errors = self.edited("# T {#t}\n\n## Abschnitt {#english-section}\n\nTexte.\n")
        self.assertEqual([], self.page_errors(errors))
        markup = (self.out / FRENCH / f"{EDITED_PAGE}{HTML_SUFFIX}").read_text(encoding=ENCODING)
        self.assertIn('id="english-section"', markup)
        self.assertIn('href="#english-section"', markup)
        self.assertNotIn("{#english-section}", markup)
        entries = json.loads((self.out / FRENCH / SEARCH_NAME).read_text(encoding=ENCODING))
        entry = next(item for item in entries if item["slug"] == EDITED_PAGE)
        self.assertEqual(["english-section"], [heading["anchor"] for heading in entry["headings"]])
        self.assertEqual(["Abschnitt"], [heading["text"] for heading in entry["headings"]])

    def test_US2_AS11_no_english_source_has_a_heading_that_ends_in_an_anchor_declaration(self):
        sources = [*(ROOT / "site" / "pages").rglob("*.md"), ROOT / "README.md", *(ROOT / "spec").rglob("*.md")]
        self.assertGreater(len(sources), DOCUMENT_COUNT)
        self.assertEqual([], [path.relative_to(ROOT).as_posix() for path in sources if DECLARED_HEADING.search(path.read_text(encoding=ENCODING))])


class TranslatedHeadingsAndReferences(Scratch):
    """T014a, US2-AS15, FR-018: DS-9 (60 characters) and DS-19 (coded references) apply to translations."""

    def test_US2_AS15_a_translated_level_2_heading_over_sixty_characters_fails_the_build(self):
        errors = self.edited("# T {#t}\n\n## " + "x" * 61 + " {#long}\n\nTexte.\n")
        self.assertTrue(any(EDITED_PAGE in error and "61" in error for error in errors), errors)

    def test_US2_AS15_the_declared_anchor_does_not_count_towards_the_sixty_characters(self):
        errors = self.edited("# T {#t}\n\n## " + "x" * 55 + f" {LONG_ANCHOR}\n\nTexte.\n")
        self.assertEqual([], self.page_errors(errors))

    def test_US2_AS15_a_coded_reference_in_a_translated_heading_fails_the_build(self):
        errors = self.edited(f"# T {{#t}}\n\n## Voir {CODED_SAMPLE} {{#see}}\n\nTexte.\n")
        self.assertTrue(any(EDITED_PAGE in error and "coded reference" in error for error in errors), errors)

    def test_US2_AS15_a_coded_reference_in_a_translated_title_or_description_fails_the_build(self):
        for name, title, description in (("title", f"Titre {CODED_SAMPLE}", "D"), ("description", "T", f"Voir {CODED_SAMPLE}")):
            with self.subTest(field=name):
                errors = self.edited("# T {#t}\n\nTexte.\n", title, description)
                self.assertTrue(any(EDITED_PAGE in error and "coded reference" in error for error in errors), errors)

    def test_US2_AS15_no_search_entry_of_a_built_language_holds_a_coded_reference(self):
        full = language_build(FULL)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                self.assertIsNone(bs.CODED_REFERENCE.search((full.out / code / SEARCH_NAME).read_text(encoding=ENCODING)))
        errors = self.edited(f"# T {{#t}}\n\nTexte {CODED_SAMPLE}.\n")
        text = (self.out / FRENCH / SEARCH_NAME).read_text(encoding=ENCODING)
        self.assertEqual([], self.page_errors(errors))
        self.assertIsNone(bs.CODED_REFERENCE.search(text))


class DraftsHaveNoBanner(unittest.TestCase):
    """T015, US2-AS4, FR-011: a machine-drafted page carries no banner; the status is the file's and the command's."""

    def test_US2_AS4_the_pages_built_from_machine_drafted_files_show_no_draft_notice(self):
        full = language_build(FULL)
        header = (full.root / "site" / "i18n" / FRENCH / f"{EDITED_PAGE}.md").read_text(encoding=ENCODING)
        self.assertIn(f"status: {DRAFTED}", header)
        for code in LANGUAGE_CODES:
            with self.subTest(language=code):
                markup = read_page(full, code, EDITED_PAGE)
                self.assertIsNone(re.search(r"(?i)draft|brouillon|banner|machine", markup))


class EnableGateInTheBuild(Scratch):
    """T015, US4-AS4, AS5, FR-024: the build refuses an enabled language that fails the gate, naming the document; a disabled one builds nothing."""

    def enabled(self, approved: bool) -> Path:
        root = self.tree()
        self.configure(root, True)
        stamp_documents(root, FRENCH)
        if approved:
            approve_documents(root, FRENCH, ui=True)
        return root

    def gate_errors(self, root: Path) -> list[str]:
        return [error for error in self.build(root, ()) if STATE_FINDING.search(error)]

    def test_US4_AS4_an_enabled_language_with_every_document_and_the_interface_approved_has_no_gate_error(self):
        self.assertEqual([], self.gate_errors(self.enabled(True)))
        self.assertTrue((self.out / FRENCH / f"index{HTML_SUFFIX}").is_file())

    def test_US4_AS4_an_enabled_language_with_documents_not_approved_is_refused_naming_each_document_and_the_interface_file(self):
        errors = self.gate_errors(self.enabled(False))
        for name in (f"fr/{EDITED_PAGE}", "fr/limits", f"fr/{UI_DOCUMENT}"):
            self.assertTrue(any(name in error for error in errors), (name, errors[:3]))

    def test_US4_AS4_a_document_missing_from_an_enabled_language_is_refused_by_name(self):
        root = self.enabled(True)
        (root / EDITED_FILE).unlink()
        self.assertTrue(any(f"fr/{EDITED_PAGE}" in error and "missing" in error for error in self.gate_errors(root)))

    def test_US4_AS5_an_english_change_makes_an_enabled_language_stale_and_it_is_refused_until_it_is_current_and_approved(self):  # US4-AS5
        root = self.enabled(True)
        page = root / "site" / "pages" / "limits.md"
        page.write_text(page.read_text(encoding=ENCODING) + "\nA sentence the translation lacks.\n", encoding=ENCODING)
        self.assertTrue(any("fr/limits" in error and "stale" in error for error in self.gate_errors(root)))

    def test_US4_AS5_the_same_stale_language_disabled_builds_nothing_and_is_not_offered(self):  # US4-AS5
        root = self.enabled(True)
        self.configure(root, False)
        page = root / "site" / "pages" / "limits.md"
        page.write_text(page.read_text(encoding=ENCODING) + "\nA sentence the translation lacks.\n", encoding=ENCODING)
        write_tree(self.out, {f"{FRENCH}/{LEFTOVER}": "old"})
        self.assertEqual([], self.build(root, ()))
        self.assertFalse((self.out / FRENCH).exists())
        self.assertNotIn(f'hreflang="{FRENCH}"', (self.out / f"index{HTML_SUFFIX}").read_text(encoding=ENCODING))


# ---------------------------------------------------------------- review round: the mechanism of spec 004 (findings 1 to 3 and 7)

FRENCH_HOME_FILE = f"site/i18n/{FRENCH}/{si.HOME_FILE}"
OUTPUT_ESCAPE_HOME = {"a script element": "<script>steal()</script>", "an event-handler attribute": '<img src="x" onerror="steal()">'}
BAD_HOME_FILES = {"a file with no header block": b"<main><h1>Accueil</h1></main>\n", "a file that is not UTF-8": b"<!--\n\xff\xfe\n-->\n<main></main>\n"}
SEARCH_ENGLISH_URL = "search_english_url"
SEARCH_ENGLISH = "search_english"
KEEP_NAME = "keep.txt"
OLD_PAGE = "old.html"
FUNCTION_BODY = re.compile(r"\n  const (\w+) = \([^)]*\) => \{(.*?)\n  \};", re.S)
ENGLISH_DEFAULTS = re.compile(r"const ENGLISH = \{.*?\n  \};", re.S)
SEARCH_GUARD = re.compile(r"if\s*\(\s*T\.search_english\b|\bT\.search_english\s*(?:&&|\?)")


class HomeTemplateInTheBuild(Scratch):
    """Finding 1, US2-AS8, FR-018: the translated `home.html` is raw HTML, so the build runs the DS-21 markup check on it (`build_site.unsafe_markup`)
    and reports `[<code>] site/i18n/<code>/home.html: ...` naming the problem, like any English page source."""

    def test_US2_AS8_a_translated_home_page_with_a_script_or_an_event_handler_is_a_build_error_naming_the_file(self):  # US2-AS8
        for problem, payload in OUTPUT_ESCAPE_HOME.items():
            with self.subTest(problem=problem):
                root = self.tree()
                path = root / FRENCH_HOME_FILE
                path.write_text(path.read_text(encoding=ENCODING) + payload + "\n", encoding=ENCODING)
                errors = [error for error in self.build(root) if FRENCH_HOME_FILE in error]
                self.assertTrue(any(f"[{FRENCH}]" in error and problem in error for error in errors), errors)

    def test_US2_AS8_the_unchanged_fixture_home_page_has_no_error(self):  # US2-AS8 (control)
        self.assertEqual([], [error for error in self.build(self.tree()) if FRENCH_HOME_FILE in error])


class HomeTemplateIsPartOfTheDocument(Scratch):
    """Finding 2, US3-AS3, US3-AS4, FR-024: the build reports a language's `index` whose `home.html` is missing or unreadable as an error
    `[<code>] site/i18n/<code>/home.html: ...`, never a traceback and never the English template used silently."""

    def build_or_fail(self, root: Path, preview: tuple[str, ...] = (FRENCH,)) -> list[str]:
        try:
            return self.build(root, preview)
        except si.I18nError as error:
            self.fail(f"the build raised instead of reporting: {error}")

    def home_errors(self, errors: list[str]) -> list[str]:
        return [error for error in errors if error.startswith(f"[{FRENCH}]") and FRENCH_HOME_FILE in error]

    def test_US3_AS4_an_enabled_language_whose_index_has_no_home_page_is_an_error_naming_the_file(self):  # US3-AS4
        root = self.tree()
        self.configure(root, True)
        (root / FRENCH_HOME_FILE).unlink()
        self.assertTrue(self.home_errors(self.build_or_fail(root, ())))

    def test_US3_AS4_a_previewed_language_whose_index_has_no_home_page_is_an_error_naming_the_file(self):  # US3-AS4
        root = self.tree()
        (root / FRENCH_HOME_FILE).unlink()
        self.assertTrue(self.home_errors(self.build_or_fail(root)))

    def test_US2_AS17_a_home_page_with_a_bad_header_or_bad_bytes_is_an_error_naming_the_file_and_not_a_traceback(self):  # US2-AS17
        for case, content in BAD_HOME_FILES.items():
            with self.subTest(case=case):
                root = self.tree()
                (root / FRENCH_HOME_FILE).write_bytes(content)
                self.assertTrue(self.home_errors(self.build_or_fail(root)))


class SearchEnglishLink(Scratch):
    """Finding 3, US1-AS9, FR-003, FR-015: the search box says, in the visitor's language, where the English pages can be searched; the build
    hands a language page `search_english_url` = `../index.html` whatever the interface file says, and English pages keep their own."""

    def test_US1_AS9_a_language_page_hands_the_search_box_the_english_home_one_folder_up(self):  # US1-AS9
        root = self.tree()
        for code in LANGUAGE_CODES:
            path = root / "site" / "i18n" / code / si.UI_FILE
            ui = json.loads(path.read_text(encoding=ENCODING))
            ui[SEARCH_ENGLISH_URL] = f"index{HTML_SUFFIX}"
            path.write_text(json.dumps(ui, ensure_ascii=False), encoding=ENCODING)
        self.build(root, LANGUAGE_CODES)
        for code in LANGUAGE_CODES:
            for slug in (INDEX_SLUG, SOME_TRANSLATED_PAGE):
                with self.subTest(language=code, page=slug):
                    handed = page_ui(read_page(self, code, slug))
                    self.assertEqual(f"../index{HTML_SUFFIX}", handed.get(SEARCH_ENGLISH_URL))
                    self.assertEqual(ui_strings(code)[SEARCH_ENGLISH], handed.get(SEARCH_ENGLISH))

    def test_US1_AS9_an_english_page_keeps_its_own_address_or_none(self):  # US1-AS9 (control)
        markup = read_page(language_build(FULL), ENGLISH, INDEX_SLUG)
        if DATA_UI_ATTRIBUTE.search(markup):
            self.assertEqual(f"index{HTML_SUFFIX}", page_ui(markup).get(SEARCH_ENGLISH_URL, f"index{HTML_SUFFIX}"))


class SiteScriptSearchEnglish(unittest.TestCase):
    """Finding 3, US1-AS9, FR-015: `site.js` shows `T.search_english` as a link to `T.search_english_url` where the language's index is searched
    (in `render`, or in a helper `render` calls), only when the page carries the string (English defaults do not), and as text, never as markup."""

    @classmethod
    def setUpClass(cls):
        cls.source = SITE_JS.read_text(encoding=ENCODING)
        cls.bodies = {name: body for name, body in FUNCTION_BODY.findall(cls.source)}

    def uses(self) -> list[str]:
        return [name for name, body in self.bodies.items() if "T.search_english" in body]

    def test_US1_AS9_the_script_reads_the_string_and_its_address(self):  # US1-AS9
        self.assertIn(f"T.{SEARCH_ENGLISH_URL}", self.source)
        self.assertRegex(self.source, rf"T\.{SEARCH_ENGLISH}\b(?!_)")

    def test_US1_AS9_the_english_defaults_do_not_carry_it_and_the_use_is_guarded(self):  # US1-AS9
        defaults = ENGLISH_DEFAULTS.search(self.source)
        self.assertIsNotNone(defaults)
        self.assertNotIn(SEARCH_ENGLISH, defaults.group(0))
        self.assertRegex(self.source, SEARCH_GUARD)

    def test_US1_AS9_it_is_shown_where_the_loaded_index_is_rendered(self):  # US1-AS9
        render = self.bodies.get("render", "")
        self.assertTrue(render)
        reached = "T.search_english" in render or any(f"{name}(" in render for name in self.uses())
        self.assertTrue(reached, f"render() does not show it; functions that mention it: {self.uses()}")

    def test_US1_AS9_it_is_shown_as_text_and_never_as_markup(self):  # US1-AS9
        lines = [line for line in self.source.splitlines() if "T.search_english" in line]
        self.assertTrue(lines)
        self.assertEqual([], [line for line in lines if "innerHTML" in line or "insertAdjacentHTML" in line])
        self.assertNotRegex(self.source, r"(?:innerHTML|insertAdjacentHTML)\s*[=(]")


MEGABYTE, KILOBYTE = 1_000_000, 1024
SC007_TOTAL_BYTES = 15 * MEGABYTE
SC007_SECONDS = 30
SC007_INDEX_GZIP_BYTES = 500 * KILOBYTE
SC007_SCRIPT_GZIP_BYTES = 30 * KILOBYTE


class SiteBudget(unittest.TestCase):
    """SC-007: the real six-language build, made once, stays within the size and time budget (budget tests: green when written)."""

    @classmethod
    def setUpClass(cls):
        cls.real = real_build()

    def test_SC_007_the_real_build_has_no_error(self):  # SC-007
        self.assertEqual([], self.real.errors)

    def test_SC_007_the_six_language_site_is_at_most_15_MB(self):  # SC-007
        total = sum(path.stat().st_size for path in self.real.out.rglob("*") if path.is_file())
        self.assertLessEqual(total, SC007_TOTAL_BYTES)

    def test_SC_007_the_six_language_build_takes_at_most_30_seconds(self):  # SC-007
        self.assertLessEqual(self.real.seconds, SC007_SECONDS)

    def test_SC_007_each_search_index_is_at_most_500_KB_gzipped(self):  # SC-007
        for code in ALL_CODES:
            with self.subTest(language=code):
                index = language_dir(self.real.out, code) / "search-index.json"
                self.assertTrue(index.is_file())
                self.assertLessEqual(len(gzip.compress(index.read_bytes())), SC007_INDEX_GZIP_BYTES)

    def test_SC_007_the_script_with_its_interface_messages_is_at_most_30_KB_gzipped(self):  # SC-007
        script = self.real.out / "site.js"
        self.assertTrue(script.is_file())
        self.assertLessEqual(len(gzip.compress(script.read_bytes())), SC007_SCRIPT_GZIP_BYTES)
        for code in LANGUAGE_CODES:
            page = read_page(self.real, code, INDEX_SLUG)
            self.assertRegex(page, DATA_UI_ATTRIBUTE)   # the messages ride on the page, so the script serves every language unchanged


class OutputFolderGuards(Scratch):
    """Finding 7, FR-024: the build clears only the folders of the declared languages and refuses a language folder that is a symbolic link
    (BuildError), writing nothing through it."""

    def test_FR_024_a_folder_named_like_an_undeclared_language_is_left_alone(self):  # FR-024
        root = self.tree()
        path = root / "site" / "site.json"
        config = json.loads(path.read_text(encoding=ENCODING))
        del config["languages"]["es"]
        path.write_text(json.dumps(config), encoding=ENCODING)
        write_tree(self.out, {f"es/{OLD_PAGE}": "old", f"{FRENCH}/{OLD_PAGE}": "old"})
        self.assertEqual([], [error for error in self.build(root, ()) if "es/" in error])
        self.assertTrue((self.out / "es" / OLD_PAGE).is_file())
        self.assertFalse((self.out / FRENCH / OLD_PAGE).exists())

    def test_FR_024_a_language_folder_that_is_a_symbolic_link_is_a_build_error_and_nothing_is_written_through_it(self):  # FR-024
        root = self.tree()
        elsewhere = self.out.parent / "elsewhere"
        write_tree(elsewhere, {KEEP_NAME: "keep"})
        self.out.mkdir()
        os.symlink(elsewhere, self.out / FRENCH)
        with self.assertRaises(bs.BuildError) as raised:
            self.build(root)
        self.assertIn(FRENCH, str(raised.exception))
        self.assertEqual([KEEP_NAME], [path.name for path in elsewhere.iterdir()])


if __name__ == "__main__":
    unittest.main()
