#!/usr/bin/env python3
"""Tests of the page features of the docs site v2 (story #3554, task #3556; plan docs/feat/3556/plan.md): the two scripts, the
search index, heading anchors, the top bar, the theme tokens, the mobile menu and the contrast of both themes. Offline,
standard library only; JavaScript behaviour (ranking, clipboard, theme flash) is checked in a browser, so the scripts get static
checks only. The scratch repositories come from test_build_site and test_build_site_structure.

Contract pinned here (the placeholder names are the build's template values):
  * `{{scripts}}` (in the head): `<script src="theme.js"></script>` (blocking) then `<script src="site.js" defer></script>`; the
    build copies `site/js/theme.js` and `site/js/site.js` to the output root when they exist.
  * `{{topbar}}`: one `<header class="top">` holding the logo link (`a.brand`, href index.html, inline svg), the links "Docs" (the
    first page in sidebar order) and "Reference" (the first page of the group Reference), an icon link to the repository
    (inline svg, aria-label containing "GitHub"), one icon link per registry listed in site.json `packages`
    (`{"nuget": "<url>"}`; aria-label containing the registry name), `button.search-button` and `button.theme-button`, each icon
    with an accessible name and no `<img>`.
  * `{{menu_button}}`: on a docs page `<button type="button" class="menu-toggle" aria-controls="sidebar" aria-expanded="false">`
    with an accessible name, empty on the page `index`; the template owns `<aside id="sidebar">`.
  * Heading anchors are added by the build around the converter's output (render_markdown is unchanged): a heading of level 2
    to 4 reads `<hN id="x">text <a class="anchor" href="#x" aria-label="Link to this section">#</a></hN>`.
  * `search-index.json` at the output root: a JSON array, one entry per page in site.json order, with the keys slug, title,
    description, group ("" for the home page), headings (h2 to h4 as {text, anchor}) and text (plain, no coded reference).
Run: python3 scripts/test_build_site_features.py
"""
import gzip
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT, contrast, luminance  # noqa: E402
from test_build_site_structure import (  # noqa: E402
    CODED, HOME, TICKET, Anchors, Tags, built, head_links, outcome, page, sidebar_order, site, strip_tags, toc_labels)

TEMPLATE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{page_title}}</title>'
            '<meta name="description" content="{{description}}">{{head_links}}{{scripts}}<link rel="stylesheet" href="style.css"></head>'
            '<body>{{topbar}}<div class="layout">{{menu_button}}<aside id="sidebar"><nav aria-label="Pages">{{sidebar}}</nav></aside>'
            '<main id="main">{{content}}{{prev_next}}</main><nav class="toc" aria-label="On this page">{{toc}}</nav></div>'
            '<footer>spec {{spec_version}}</footer></body></html>')
THEME_JS = "/* theme */\ndocument.documentElement.classList.add('js');\n"
SITE_JS = "/* site */\n"
FEATURE_SOURCE = ("# Feature page\n\nIntro with **bold**, `code` and [a link](other.md).\n\n## Alpha\n\nAlpha body. The rule SEM-6 and ticket #1638 are named.\n\n"
                  "### Beta\n\nBeta body.\n\n#### Gamma\n\nGamma body.\n\n##### Five\n\nFive body.\n\n## Same\n\nx\n\n## Same\n\ny\n")
TOKENS = ("--bg", "--surface", "--text", "--muted", "--link", "--accent", "--accent-ink")
REGISTRY_HOSTS = ("nuget.org", "npmjs.com", "pypi.org", "pkg.go.dev")
DENIED_JS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "document.cookie")


def fsite(pages: list[dict], files: dict[str, str] | None = None, **extra) -> Path:
    """A scratch site with the features template, both scripts and a source for the feature page."""
    base = {"site/template.html": TEMPLATE, "site/js/theme.js": THEME_JS, "site/js/site.js": SITE_JS, "other.md": "# Other\n",
            "feature.md": FEATURE_SOURCE}
    return site(pages, {**base, **(files or {})}, **extra)


FEATURE_PAGES = [HOME, page("feature", "Guides", "Feature page"), page("ref", "Reference", "Reference page")]


def block(text: str, start: str, end: str) -> str:
    """From the first `start` up to and including `end`; '' when absent."""
    at = text.find(start)
    return "" if at < 0 else text[at:text.find(end, at) + len(end)]


class Controls(HTMLParser):
    """The links and buttons of a fragment with their attributes, accessible name text and whether an inline svg is inside."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict] = []
        self.images = 0
        self._open: dict | None = None

    def handle_starttag(self, tag, attrs):
        found = {k: (v or "") for k, v in attrs}
        if tag == "img":
            self.images += 1
        if tag in ("a", "button"):
            self._open = {"tag": tag, "attrs": found, "svg": False, "text": ""}
        elif tag == "svg" and self._open is not None:
            self._open["svg"] = True

    def handle_data(self, data):
        if self._open is not None:
            self._open["text"] += data

    def handle_endtag(self, tag):
        if tag in ("a", "button") and self._open is not None:
            self.items.append(self._open)
            self._open = None

    @staticmethod
    def name(item: dict) -> str:
        return (item["attrs"].get("aria-label") or item["text"]).strip()


def topbar(page_html: str) -> Controls:
    parser = Controls()
    parser.feed(block(page_html, '<header class="top"', "</header>"))
    return parser


def scripts_in_head(page_html: str) -> list[dict]:
    head = page_html[:page_html.find("</head>")]
    parser = Tags()
    parser.feed(head)
    return [{"src": attrs.get("src"), "defer": "defer" in attrs, "async": "async" in attrs} for tag, attrs in parser.tags if tag == "script"]


def headings_of(page_html: str, levels: str = "234") -> list[tuple[str, str, str]]:
    main = block(page_html, "<main", "</main>")
    return [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(rf'<h([{levels}]) id="([^"]+)">(.*?)</h\1>', main, re.S)]


def css_blocks(css: str) -> list[tuple[str, str, str]]:
    """(media prelude or '', selector list, declarations) of every style rule, comments dropped, at-rules other than media skipped."""
    text = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: list[tuple[str, str, str]] = []

    def walk(chunk: str, context: str) -> None:
        position = 0
        while position < len(chunk):
            opener = chunk.find("{", position)
            if opener < 0:
                return
            prelude, depth, end = chunk[position:opener].strip(), 1, opener + 1
            while end < len(chunk) and depth:
                depth += (chunk[end] == "{") - (chunk[end] == "}")
                end += 1
            body = chunk[opener + 1:end - 1]
            if prelude.startswith("@media"):
                walk(body, prelude)
            elif not prelude.startswith("@"):
                found.append((context, prelude, body))
            position = end

    walk(text, "")
    return found


def tokens_of(body: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", body))


def theme_tokens(css: str) -> dict[str, dict[str, str]]:
    """The token sets: light (plain :root), dark_media (:root under prefers-color-scheme: dark), dark_attr, light_attr."""
    sets: dict[str, dict[str, str]] = {"light": {}, "dark_media": {}, "dark_attr": {}, "light_attr": {}}
    for context, selector, body in css_blocks(css):
        selectors = [s.strip() for s in selector.split(",")]
        if context == "" and ":root" in selectors:
            sets["light"].update(tokens_of(body))
        elif "prefers-color-scheme: dark" in context.replace("(", "").replace(")", "") and any(s.startswith(":root") for s in selectors):
            sets["dark_media"].update(tokens_of(body))
        elif context == "" and any('[data-theme="dark"]' in s for s in selectors):
            sets["dark_attr"].update(tokens_of(body))
        elif context == "" and any('[data-theme="light"]' in s for s in selectors):
            sets["light_attr"].update(tokens_of(body))
    return sets


def inside_try(text: str, index: int) -> bool:
    """True when the character at `index` lies in a `try { ... }` block (braces counted; the scripts hold no brace in a string)."""
    stack: list[bool] = []
    for position in range(index):
        char = text[position]
        if char == "{":
            stack.append(text[:position].rstrip().endswith("try"))
        elif char == "}" and stack:
            stack.pop()
    return any(stack)


class ScratchScripts(unittest.TestCase):
    """Contract 1 on a scratch site: both scripts are copied and linked from every page, the theme script blocks."""

    @classmethod
    def setUpClass(cls):
        errors, cls.out = outcome(fsite(FEATURE_PAGES))
        assert errors == [], errors
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}

    def test_1_both_scripts_are_copied_to_the_output_root_unchanged(self):
        self.assertEqual((self.out / "theme.js").read_text(encoding="utf-8") if (self.out / "theme.js").is_file() else None, THEME_JS)
        self.assertEqual((self.out / "site.js").read_text(encoding="utf-8") if (self.out / "site.js").is_file() else None, SITE_JS)

    def test_1_every_page_links_the_blocking_theme_script_then_the_deferred_site_script_in_the_head(self):
        self.assertEqual(sorted(self.pages), ["feature", "index", "ref"])
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                self.assertEqual(scripts_in_head(text), [{"src": "theme.js", "defer": False, "async": False},
                                                         {"src": "site.js", "defer": True, "async": False}])

    def test_1_no_page_holds_an_inline_script(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                self.assertEqual([body for body in re.findall(r"<script\b[^>]*>(.*?)</script>", text, re.S) if body.strip()], [])
                self.assertEqual(len(re.findall(r"<script\b", text)), 2)


class ScratchSearchIndex(unittest.TestCase):
    """Contract 2."""

    @classmethod
    def setUpClass(cls):
        cls.root = fsite(FEATURE_PAGES)
        errors, cls.out = outcome(cls.root)
        assert errors == [], errors
        path = cls.out / "search-index.json"
        cls.entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def setUp(self):
        self.assertIsNotNone(self.entries, "search-index.json is not written")

    def test_2_the_index_is_one_entry_per_page_in_site_order_with_the_pinned_keys(self):
        self.assertEqual([e["slug"] for e in self.entries], ["index", "feature", "ref"])
        for entry in self.entries:
            self.assertEqual(sorted(entry), ["description", "group", "headings", "slug", "text", "title"])
        feature = self.entries[1]
        self.assertEqual((feature["title"], feature["description"], feature["group"]), ("Feature page", "The feature page.", "Guides"))
        self.assertEqual(self.entries[0]["group"], "")

    def test_2_headings_are_the_plain_h2_to_h4_texts_with_their_anchors(self):
        self.assertEqual(self.entries[1]["headings"], [
            {"text": "Alpha", "anchor": "alpha"}, {"text": "Beta", "anchor": "beta"}, {"text": "Gamma", "anchor": "gamma"},
            {"text": "Same", "anchor": "same"}, {"text": "Same", "anchor": "same-1"}])

    def test_2_the_text_is_plain_and_holds_no_coded_reference(self):
        text = self.entries[1]["text"]
        for word in ("Intro with bold", "code", "a link", "Alpha body.", "Gamma body."):
            self.assertIn(word, text)
        for markup in ("<", "**", "](", "`"):
            self.assertNotIn(markup, text)
        self.assertNotRegex(text, CODED)
        self.assertNotRegex(text, TICKET)

    def test_2_no_entry_field_holds_a_coded_reference(self):
        self.assertTrue(self.entries)
        for entry in self.entries:
            for value in (entry["title"], entry["description"], *(h["text"] for h in entry["headings"])):
                self.assertNotRegex(value, CODED)
                self.assertNotRegex(value, TICKET)

    def test_2_two_builds_give_the_same_bytes(self):
        first = (self.out / "search-index.json").read_bytes() if (self.out / "search-index.json").is_file() else b""
        second_out = Path(tempfile.mkdtemp()) / "again"
        self.assertEqual(bs.build(self.root, second_out), [])
        self.assertTrue(first)
        self.assertEqual(first, (second_out / "search-index.json").read_bytes())


class ScratchAnchors(unittest.TestCase):
    """Contract 3 (DS-6)."""

    @classmethod
    def setUpClass(cls):
        cls.pages = built(fsite(FEATURE_PAGES))

    def test_3_each_h2_to_h4_holds_one_anchor_link_to_its_own_id(self):
        found = headings_of(self.pages["feature"])
        self.assertEqual([(level, identifier) for level, identifier, _ in found], [("2", "alpha"), ("3", "beta"), ("4", "gamma"), ("2", "same"), ("2", "same-1")])
        for level, identifier, inner in found:
            with self.subTest(heading=identifier):
                self.assertEqual(inner.count('<a class="anchor"'), 1)
                self.assertIn(f'<a class="anchor" href="#{identifier}" aria-label="Link to this section">', inner)

    def test_3_h1_and_h5_have_no_anchor_and_the_toc_keeps_the_plain_text(self):
        self.assertNotIn("anchor", "".join(inner for _, _, inner in headings_of(self.pages["feature"], "156")))
        self.assertEqual(toc_labels(self.pages["feature"]), ["Alpha", "Same", "Same"])

    def test_3_a_heading_keeps_its_own_text_before_the_anchor(self):
        inner = next(inner for _, identifier, inner in headings_of(self.pages["feature"]) if identifier == "alpha")
        self.assertTrue(inner.startswith("Alpha"))
        self.assertIn('class="anchor"', inner)


class ScratchTopBar(unittest.TestCase):
    """Contract 4 (DS-1) on a scratch site, then with a registry listed."""

    @classmethod
    def setUpClass(cls):
        cls.pages = built(fsite(FEATURE_PAGES))
        cls.repo = "https://example.test/r"

    def test_4_every_page_home_included_has_the_logo_the_docs_and_reference_links(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                bar = topbar(text)
                brand = [i for i in bar.items if "brand" in i["attrs"].get("class", "").split()]
                self.assertEqual([(i["attrs"].get("href"), i["svg"]) for i in brand], [("index.html", True)])
                links = {i["text"].strip(): i["attrs"].get("href") for i in bar.items if i["tag"] == "a"}
                self.assertEqual(links.get("Docs"), sidebar_order(self.pages["feature"])[0])
                self.assertEqual(links.get("Reference"), "ref.html")
                self.assertNotIn("aria-current", block(text, '<header class="top"', "</header>"))

    def test_4_the_github_link_the_search_button_and_the_theme_button_have_accessible_names_and_inline_icons(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                bar = topbar(text)
                self.assertEqual(bar.images, 0)
                github = [i for i in bar.items if i["tag"] == "a" and i["attrs"].get("href") == self.repo]
                self.assertEqual(len(github), 1)
                self.assertIn("GitHub", Controls.name(github[0]))
                self.assertTrue(github[0]["svg"])
                search = [i for i in bar.items if i["tag"] == "button" and "search-button" in i["attrs"].get("class", "").split()]
                theme = [i for i in bar.items if i["tag"] == "button" and "theme-button" in i["attrs"].get("class", "").split()]
                self.assertEqual((len(search), len(theme)), (1, 1))
                for control, word in ((search[0], "search"), (theme[0], "theme")):
                    self.assertEqual(control["attrs"].get("type"), "button")
                    self.assertIn(word, Controls.name(control).lower())
                    self.assertTrue(control["svg"])

    def test_4_no_registry_icon_appears_while_site_json_lists_no_package(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                hrefs = [i["attrs"].get("href", "") for i in topbar(text).items if i["tag"] == "a"]
                self.assertEqual([h for h in hrefs if any(host in h for host in REGISTRY_HOSTS)], [])

    def test_4_a_registry_listed_under_packages_gets_one_named_inline_icon_link_on_every_page(self):
        url = "https://www.nuget.org/packages/Craticula"
        pages = built(fsite(FEATURE_PAGES, packages={"nuget": url}))
        for slug, text in pages.items():
            with self.subTest(page=slug):
                found = [i for i in topbar(text).items if i["tag"] == "a" and i["attrs"].get("href") == url]
                self.assertEqual(len(found), 1)
                self.assertIn("NuGet", Controls.name(found[0]))
                self.assertTrue(found[0]["svg"])


class ScratchMenu(unittest.TestCase):
    """Contract 6, markup side."""

    @classmethod
    def setUpClass(cls):
        cls.pages = built(fsite(FEATURE_PAGES))

    def test_6_a_docs_page_has_one_menu_button_that_controls_the_sidebar(self):
        for slug in ("feature", "ref"):
            with self.subTest(page=slug):
                bar = Controls()
                bar.feed(self.pages[slug])
                buttons = [i for i in bar.items if i["tag"] == "button" and "menu-toggle" in i["attrs"].get("class", "").split()]
                self.assertEqual(len(buttons), 1)
                self.assertEqual((buttons[0]["attrs"].get("type"), buttons[0]["attrs"].get("aria-controls"), buttons[0]["attrs"].get("aria-expanded")),
                                 ("button", "sidebar", "false"))
                self.assertTrue(Controls.name(buttons[0]))
                self.assertEqual(self.pages[slug].count('id="sidebar"'), 1)

    def test_6_the_home_page_has_no_menu_button(self):
        self.assertNotIn("menu-toggle", self.pages["index"])
        self.assertNotIn('aria-controls="sidebar"', self.pages["index"])


class RealSite(unittest.TestCase):
    """The acceptance tests on this repository's own sources and stylesheet."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        cls.errors = bs.build(ROOT, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}
        cls.config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))
        cls.css = (ROOT / "site" / "style.css").read_text(encoding="utf-8")

    def js(self, name: str) -> str:
        path = ROOT / "site" / "js" / name
        self.assertTrue(path.is_file(), f"site/js/{name} does not exist")
        return path.read_text(encoding="utf-8")

    def test_the_real_sources_still_build_without_errors(self):
        self.assertEqual(self.errors, [])

    def test_1_both_scripts_exist_are_copied_and_linked_from_every_page(self):
        for name in ("theme.js", "site.js"):
            self.assertEqual((self.out / name).read_text(encoding="utf-8") if (self.out / name).is_file() else None, self.js(name))
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                self.assertEqual(scripts_in_head(text), [{"src": "theme.js", "defer": False, "async": False},
                                                         {"src": "site.js", "defer": True, "async": False}])

    def test_1_each_script_is_at_most_30_kb_gzipped(self):
        for name in ("theme.js", "site.js"):
            with self.subTest(script=name):
                self.assertLessEqual(len(gzip.compress(self.js(name).encode("utf-8"), 9)), 30 * 1024)

    def test_1_the_scripts_use_no_markup_sink_no_eval_no_cookie_and_no_other_host(self):
        for name in ("theme.js", "site.js"):
            text = self.js(name)
            for denied in DENIED_JS:
                with self.subTest(script=name, token=denied):
                    self.assertNotIn(denied, text)
            with self.subTest(script=name, token="host"):
                self.assertNotRegex(text, r"(?i)https?:|[\"'`]//")

    def test_1_the_site_script_loads_the_index_from_its_own_host_by_a_relative_path(self):
        self.assertIn("search-index.json", self.js("site.js"))

    def test_5_the_theme_script_marks_the_page_and_reads_the_choice_before_paint(self):
        text = self.js("theme.js")
        self.assertIn("documentElement", text)
        self.assertRegex(text, r"""["']js["']""")
        self.assertIn("data-theme", text)

    def test_5_every_storage_access_is_in_a_try_block_and_one_key_is_used(self):
        keys: set[str] = set()
        for name in ("theme.js", "site.js"):
            text = self.js(name)
            for found in re.finditer("localStorage", text):
                with self.subTest(script=name, at=found.start()):
                    self.assertTrue(inside_try(text, found.start()), "localStorage outside a try block")
            keys.update(re.findall(r"""(?:getItem|setItem|removeItem)\(\s*["']([^"']+)["']""", text))
        self.assertLessEqual(len(keys), 1)
        self.assertGreater(len("".join(self.js(n) for n in ("theme.js", "site.js")).split("localStorage")), 1, "the choice is never stored")

    def test_2_the_search_index_lists_every_page_with_plain_fields_and_is_at_most_500_kb_gzipped(self):
        path = self.out / "search-index.json"
        self.assertTrue(path.is_file(), "search-index.json is not written")
        raw = path.read_bytes()
        self.assertLessEqual(len(gzip.compress(raw, 9)), 500 * 1024)
        entries = json.loads(raw)
        self.assertEqual(sorted(e["slug"] for e in entries), sorted(self.pages))
        self.assertEqual([e["slug"] for e in entries][:1], ["index"])
        for entry in entries:
            with self.subTest(page=entry["slug"]):
                self.assertEqual(sorted(entry), ["description", "group", "headings", "slug", "text", "title"])
                self.assertTrue(entry["title"] and entry["description"] and entry["text"])
                for value in (entry["title"], entry["description"], entry["text"], *(h["text"] for h in entry["headings"])):
                    self.assertNotRegex(value, CODED)
                    self.assertNotRegex(value, TICKET)
                self.assertNotRegex(entry["text"], r"</?[a-z][^>]*>")
        self.assertIn("Deterministic paging", [e["title"] for e in entries])

    def test_2_two_builds_of_the_real_site_give_the_same_index_bytes(self):
        again = Path(tempfile.mkdtemp()) / "again"
        bs.build(ROOT, again)
        self.assertTrue((self.out / "search-index.json").is_file(), "search-index.json is not written")
        self.assertEqual((self.out / "search-index.json").read_bytes(), (again / "search-index.json").read_bytes())

    def test_3_every_h2_to_h4_of_every_page_has_its_anchor_and_the_toc_keeps_plain_text(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                for level, identifier, inner in headings_of(text):
                    self.assertIn(f'<a class="anchor" href="#{identifier}" aria-label="Link to this section">', inner)
                for label in toc_labels(text):
                    self.assertNotIn("Link to this section", label)
                    self.assertFalse(label.endswith("#"), label)

    def test_4_every_page_home_included_has_the_top_bar(self):
        repo = self.config["repo"]
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                self.assertEqual(text.count('<header class="top"'), 1)
                bar = topbar(text)
                self.assertEqual(bar.images, 0)
                texts = {i["text"].strip() for i in bar.items if i["tag"] == "a"}
                self.assertLessEqual({"Docs", "Reference"}, texts)
                github = [i for i in bar.items if i["tag"] == "a" and i["attrs"].get("href") == repo]
                self.assertEqual(len(github), 1)
                self.assertIn("GitHub", Controls.name(github[0]))
                self.assertTrue(github[0]["svg"])
                for word, cls in (("search", "search-button"), ("theme", "theme-button")):
                    found = [i for i in bar.items if i["tag"] == "button" and cls in i["attrs"].get("class", "").split()]
                    self.assertEqual(len(found), 1)
                    self.assertIn(word, Controls.name(found[0]).lower())
                    self.assertTrue(found[0]["svg"])

    def test_4_no_registry_icon_is_shown_while_no_package_is_published(self):
        self.assertNotIn("packages", self.config)
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                hrefs = [i["attrs"].get("href", "") for i in topbar(text).items if i["tag"] == "a"]
                self.assertEqual([h for h in hrefs if any(host in h for host in REGISTRY_HOSTS)], [])

    def test_6_docs_pages_have_the_menu_button_and_the_sidebar_id_and_the_home_page_neither(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                if slug == "index":
                    self.assertNotIn("menu-toggle", text)
                    continue
                parser = Controls()
                parser.feed(text)
                buttons = [i for i in parser.items if i["tag"] == "button" and "menu-toggle" in i["attrs"].get("class", "").split()]
                self.assertEqual([(b["attrs"].get("aria-controls"), b["attrs"].get("aria-expanded")) for b in buttons], [("sidebar", "false")])
                self.assertEqual(text.count('id="sidebar"'), 1)

    def test_6_the_stylesheet_hides_the_sidebar_behind_the_button_only_with_javascript_at_800px(self):
        rules = css_blocks(self.css)
        base = [body for context, selector, body in rules if context == "" and selector.strip() == ".menu-toggle"]
        self.assertTrue(base and any(re.search(r"display\s*:\s*none", body) for body in base), ".menu-toggle must be hidden without JavaScript")
        narrow = [(selector, body) for context, selector, body in rules if re.search(r"max-width\s*:\s*800px", context)]
        self.assertTrue(any("html.js" in selector and ("#sidebar" in selector or ".side" in selector) and re.search(r"display\s*:\s*none", body)
                            for selector, body in narrow), "html.js must hide the sidebar at 800px and narrower")
        self.assertTrue(any("html.js" in selector and ".menu-toggle" in selector and re.search(r"display\s*:\s*(?!none)", body)
                            for selector, body in narrow), "html.js must show the menu button at 800px and narrower")

    def test_6_tables_scroll_inside_their_own_box(self):
        self.assertTrue(any("table" in selector and re.search(r"overflow-x\s*:\s*auto", body) for _, selector, body in css_blocks(self.css)))

    def test_5_light_is_the_root_and_dark_follows_the_system_and_the_attribute_with_the_same_tokens(self):
        sets = theme_tokens(self.css)
        for name in TOKENS:
            for which in ("light", "dark_media", "dark_attr", "light_attr"):
                self.assertIn(name, sets[which], f"{name} missing from {which}")
        for name in TOKENS:
            self.assertEqual(sets["dark_media"][name], sets["dark_attr"][name], name)
            self.assertEqual(sets["light_attr"][name], sets["light"][name], name)
        self.assertGreater(luminance(sets["light"]["--bg"]), luminance(sets["dark_attr"]["--bg"]))
        self.assertGreater(luminance(sets["dark_attr"]["--text"]), luminance(sets["dark_attr"]["--bg"]))

    def test_7_text_muted_link_and_accent_button_reach_4_5_in_both_themes(self):
        sets = theme_tokens(self.css)
        for which in ("light", "dark_attr", "dark_media"):
            colours = sets[which]
            self.assertLessEqual(set(TOKENS), set(colours), f"{which} lacks tokens")
            pairs = [("--text", "--bg"), ("--text", "--surface"), ("--muted", "--bg"), ("--muted", "--surface"), ("--link", "--bg"),
                     ("--link", "--surface"), ("--accent-ink", "--accent")]
            for foreground, ground in pairs:
                with self.subTest(theme=which, pair=f"{foreground}/{ground}"):
                    self.assertGreaterEqual(contrast(colours[foreground], colours[ground]), 4.5)

    def test_5_the_theme_button_markup_names_its_state_for_assistive_technology(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                found = [i for i in topbar(text).items if i["tag"] == "button" and "theme-button" in i["attrs"].get("class", "").split()]
                self.assertEqual(len(found), 1)
                self.assertTrue(Controls.name(found[0]))


class StripTagsGuard(unittest.TestCase):
    """The helper the tests above lean on must itself separate words."""

    def test_strip_tags_keeps_words_apart(self):
        self.assertEqual(strip_tags("<b>a</b><i>b</i>"), "a b")
        self.assertEqual(Anchors().links, [])
        self.assertEqual(head_links("<head></head>"), [])


if __name__ == "__main__":
    unittest.main()
