#!/usr/bin/env python3
"""Tests of the home page of the docs site v2 (story #3554, task #3557; plan docs/feat/3557/plan.md): the hero, the group cards
made from `site/site.json` `groups`, the numbered path, the page content below it and the leftovers that must be gone. Offline,
standard library only; scratch sites for the configuration refusals and the card generation, the real sources for the page.

Contract pinned here:
  * Template value `{{group_cards}}` expands to `<div class="cards group-cards">` holding one
    `<a class="card" href="<first page of the group>.html"><h3>Group</h3><p>description</p></a>` per non-empty group, in the order
    of build_site.GROUPS; it is empty when site.json has no `groups` key.
  * `groups` in site.json, when present, is an object of group name to one-sentence description. A non-empty group without a
    non-empty string description, a description with a coded reference, or a `groups` value that is not an object of strings
    fails the build and names the group (or `groups`).
  * The home page: one h1, two hero buttons (`a.btn` primary, `a.btn-ghost` secondary), `ol.path` with four `li` ("Step N", a
    linked title, one sentence), `index.md` shown below the path under "All pages", no `{{`, one meta description, no sidebar and
    no menu button, no colour literal in `site/home.html`, no coded reference in the text.
Run: python3 scripts/test_build_site_home.py
"""
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT  # noqa: E402
from test_build_site_features import TEMPLATE, block  # noqa: E402
from test_build_site_structure import CODED, TICKET, Anchors, built, meta_description, outcome, page, sidebar, site, strip_tags  # noqa: E402

# repeated literals (SonarQube S1192)
STEP_BY_STEP_TASKS = "Step by step tasks."
EVERY_RULE_AND_MEMBER = "Every rule and member."

HOME_TEMPLATE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{page_title}}</title>'
                 '<meta name="description" content="{{description}}">{{head_links}}</head>'
                 '<body class="home">{{topbar}}<main id="main">{{group_cards}}{{content}}</main><footer>spec {{spec_version}}</footer></body></html>')
GROUP_TEXT = {"Concepts": "How the pieces fit together.", "Guides": STEP_BY_STEP_TASKS, "Configuration": "Settings and options.",
              "Reference": EVERY_RULE_AND_MEMBER}
HEX_COLOUR = re.compile(r"(?<!&)#[0-9a-fA-F]{3,8}\b")
COLOUR_FUNCTION = re.compile(r"\b(?:rgb|rgba|hsl|hsla)\(")


def home_page() -> dict:
    return page("index", None, "Home", template="site/home.html")


def hsite(pages: list[dict], **extra) -> Path:
    """A scratch site whose home page uses a template with {{group_cards}}."""
    return site([home_page(), *pages], {"site/template.html": TEMPLATE, "site/home.html": HOME_TEMPLATE}, **extra)


class Cards(HTMLParser):
    """The cards of the group-cards block: (href, heading, paragraph) in order."""

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[tuple[str, str, str]] = []
        self.blocks = 0
        self._depth = 0
        self._card: dict | None = None
        self._field = ""

    def handle_starttag(self, tag, attrs):
        found = {k: (v or "") for k, v in attrs}
        if tag == "div" and "group-cards" in found.get("class", "").split():
            self.blocks += 1
            self._depth = 1
        elif tag == "div" and self._depth:
            self._depth += 1
        elif tag == "a" and self._depth and "card" in found.get("class", "").split():
            self._card = {"href": found.get("href", ""), "h3": "", "p": ""}
        elif tag in ("h3", "p") and self._card is not None:
            self._field = tag

    def handle_data(self, data):
        if self._card is not None and self._field:
            self._card[self._field] += data

    def handle_endtag(self, tag):
        if tag in ("h3", "p"):
            self._field = ""
        elif tag == "a" and self._card is not None:
            self.cards.append((self._card["href"], self._card["h3"].strip(), self._card["p"].strip()))
            self._card = None
        elif tag == "div" and self._depth:
            self._depth -= 1


class PathParser(HTMLParser):
    """The items of `ol.path`: for each `li` its text and its links."""

    def __init__(self) -> None:
        super().__init__()
        self.lists = 0
        self.items: list[dict] = []
        self._in_path = False
        self._item: dict | None = None
        self._link: dict | None = None

    def handle_starttag(self, tag, attrs):
        found = {k: (v or "") for k, v in attrs}
        if tag == "ol" and "path" in found.get("class", "").split():
            self.lists += 1
            self._in_path = True
        elif tag == "li" and self._in_path:
            self._item = {"text": "", "links": []}
        elif tag == "a" and self._item is not None:
            self._link = {"href": found.get("href", ""), "text": ""}

    def handle_data(self, data):
        if self._item is not None:
            self._item["text"] += data
        if self._link is not None:
            self._link["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None and self._item is not None:
            self._item["links"].append(self._link)
            self._link = None
        elif tag == "li" and self._item is not None:
            self.items.append(self._item)
            self._item = None
        elif tag == "ol":
            self._in_path = False


def cards_of(page_html: str) -> Cards:
    parser = Cards()
    parser.feed(page_html)
    return parser


def squash(text: str) -> str:
    return " ".join(text.split())


class ScratchGroupCards(unittest.TestCase):
    """Contract 2 on scratch sites."""

    PAGES = [page("r", "Reference", "Rules"), page("a", "Guides", "First guide"), page("b", "Guides", "Second guide")]

    def test_2_one_card_per_non_empty_group_in_the_fixed_order_linking_the_first_page(self):
        parser = cards_of(built(hsite(self.PAGES, groups=GROUP_TEXT))["index"])
        self.assertEqual(parser.blocks, 1)
        self.assertEqual(parser.cards, [("a.html", "Guides", GROUP_TEXT["Guides"]), ("r.html", "Reference", GROUP_TEXT["Reference"])])

    def test_2_the_order_follows_the_fixed_group_order_not_the_json_order(self):
        reverse = dict(reversed(list(GROUP_TEXT.items())))
        parser = cards_of(built(hsite(self.PAGES, groups=reverse))["index"])
        self.assertEqual([heading for _, heading, _ in parser.cards], ["Guides", "Reference"])

    def test_2_empty_groups_get_no_card_and_a_card_holds_no_digit_or_coded_reference(self):
        home = built(hsite(self.PAGES, groups=GROUP_TEXT))["index"]
        group_block = block(home, '<div class="cards group-cards"', "</div>")
        self.assertTrue(group_block, "the home page has no group-cards block")
        for empty in ("Concepts", "Configuration"):
            self.assertNotIn(empty, group_block)
        self.assertNotRegex(strip_tags(group_block), r"\d")
        self.assertNotRegex(strip_tags(group_block), CODED)

    def test_2_without_a_groups_key_the_value_is_empty_and_the_build_still_works(self):
        home = built(hsite(self.PAGES))["index"]
        self.assertNotIn("group-cards", home)
        self.assertNotIn("{{group_cards}}", home)


class ScratchGroupConfig(unittest.TestCase):
    """Contract 2, the configuration refusals."""

    PAGES = [page("r", "Reference", "Rules"), page("a", "Guides", "First guide")]

    def test_2_a_non_empty_group_without_a_description_fails_the_build_naming_the_group(self):
        for name, groups in (("missing", {"Guides": STEP_BY_STEP_TASKS}), ("blank", {"Guides": STEP_BY_STEP_TASKS, "Reference": "  "}),
                             ("empty", {"Guides": STEP_BY_STEP_TASKS, "Reference": ""}), ("not a string", {"Guides": STEP_BY_STEP_TASKS, "Reference": 5})):
            with self.subTest(case=name):
                errors, _ = outcome(hsite(self.PAGES, groups=groups))
                self.assertTrue(any("Reference" in message for message in errors), errors)

    def test_2_an_empty_group_may_go_without_a_description(self):
        errors, _ = outcome(hsite(self.PAGES, groups={"Guides": STEP_BY_STEP_TASKS, "Reference": EVERY_RULE_AND_MEMBER}))
        self.assertEqual(errors, [])

    def test_2_a_key_that_is_not_one_of_the_four_groups_fails_the_build_naming_the_key(self):
        for key in ("Concept", "Guidez", "guides", "Misc"):
            with self.subTest(key=key):
                errors, _ = outcome(hsite(self.PAGES, groups={"Guides": STEP_BY_STEP_TASKS, "Reference": EVERY_RULE_AND_MEMBER, key: "A group."}))
                self.assertTrue(any(key in message for message in errors), errors)

    def test_2_a_value_that_is_not_a_string_fails_naming_the_group_even_when_the_group_is_empty(self):
        for bad in (5, None, ["text"], {"a": "b"}, True):
            with self.subTest(value=bad):
                errors, _ = outcome(hsite(self.PAGES, groups={"Guides": STEP_BY_STEP_TASKS, "Reference": EVERY_RULE_AND_MEMBER, "Concepts": bad}))
                self.assertTrue(any("Concepts" in message for message in errors), errors)

    def test_2_groups_must_be_an_object_of_strings(self):
        for bad in (["Guides"], "Guides", 5, None):
            with self.subTest(groups=bad):
                errors, _ = outcome(hsite(self.PAGES, groups=bad))
                self.assertTrue(any("groups" in message for message in errors), errors)

    def test_2_a_description_with_a_coded_reference_fails_naming_the_group(self):
        for text in ("See SEM-6 for details.", "Tracked in #1638."):
            with self.subTest(text=text):
                errors, _ = outcome(hsite(self.PAGES, groups={"Guides": text, "Reference": EVERY_RULE_AND_MEMBER}))
                self.assertTrue(any("Guides" in message for message in errors), errors)


class RealHome(unittest.TestCase):
    """Contracts 1 to 5 on this repository's home page."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        cls.errors = bs.build(ROOT, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}
        cls.home = cls.pages["index"]
        cls.config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))
        cls.template = (ROOT / "site" / "home.html").read_text(encoding="utf-8")
        cls.main = block(cls.home, "<main", "</main>")
        cls.hero = block(cls.home, '<section class="hero"', "</section>")

    def test_the_real_sources_still_build_without_errors(self):
        self.assertEqual(self.errors, [])

    def test_1_the_hero_has_one_h1_and_a_lead_and_two_buttons_one_primary_one_secondary(self):
        self.assertEqual(self.home.count("<h1"), 1)
        self.assertIn("<h1", self.hero)
        self.assertIn('<p class="lead">', self.hero)
        buttons = [attrs.get("class", "").split() for attrs, _ in self.links_of(self.hero) if {"btn", "btn-ghost"} & set(attrs.get("class", "").split())]
        self.assertEqual(sorted(buttons), [["btn"], ["btn-ghost"]])

    def links_of(self, markup: str) -> list[tuple[dict, str]]:
        parser = Anchors()
        parser.feed(markup)
        return parser.links

    def test_1_the_hero_shows_the_request_and_the_compiled_statement_as_two_panels(self):
        self.assertEqual(self.hero.count('class="panel"'), 2)
        self.assertIn('"startRow"', self.hero)
        self.assertIn("SELECT", self.hero)

    def test_1_the_pre_release_note_stays_short(self):
        self.assertIn("no package published yet", squash(strip_tags(self.hero)).lower())

    def test_1_the_refused_line_with_its_rule_code_and_the_arrow_are_gone(self):
        for leftover in ("Refused", 'class="refused', "UnknownFieldException", "allowlist check failed", 'class="arrow"'):
            with self.subTest(leftover=leftover):
                self.assertNotIn(leftover, self.home)
                self.assertNotIn(leftover, self.template)

    def test_1_the_home_template_holds_no_colour_literal(self):
        self.assertEqual(HEX_COLOUR.findall(self.template), [])
        self.assertEqual(COLOUR_FUNCTION.findall(self.template), [])

    def test_2_site_json_describes_every_non_empty_group_in_plain_words(self):
        groups = self.config.get("groups")
        self.assertIsInstance(groups, dict)
        used = {page_entry["group"] for page_entry in self.config["pages"] if page_entry.get("group")}
        for name in used:
            with self.subTest(group=name):
                self.assertIsInstance(groups.get(name), str)
                self.assertTrue(groups[name].strip())
                self.assertNotRegex(groups[name], CODED)
                self.assertNotRegex(groups[name], TICKET)

    def test_2_the_home_page_has_one_card_per_non_empty_group_linking_its_first_page(self):
        parser = cards_of(self.home)
        self.assertEqual(parser.blocks, 1)
        docs_page = next(slug for slug in self.pages if slug != "index")
        first: dict[str, str] = {}
        for path, href, _, _ in sidebar(self.pages[docs_page]).links:
            first.setdefault(path[0], href)
        groups = self.config.get("groups", {})
        self.assertEqual(parser.cards, [(first[name], name, groups.get(name)) for name in bs.GROUPS if name in first])

    def test_2_no_card_holds_a_digit_or_a_coded_reference(self):
        group_block = block(self.home, '<div class="cards group-cards"', "</div>")
        self.assertTrue(group_block, "the home page has no group-cards block")
        text = strip_tags(group_block)
        self.assertNotRegex(text, r"\d")
        self.assertNotRegex(text, CODED)

    def test_3_the_numbered_path_has_four_steps_that_link_to_existing_pages(self):
        parser = PathParser()
        parser.feed(self.home)
        self.assertEqual(parser.lists, 1)
        self.assertEqual(len(parser.items), 4)
        for number, item in enumerate(parser.items, 1):
            with self.subTest(step=number):
                text = squash(item["text"])
                self.assertTrue(text.startswith(f"Step {number}"), text)
                self.assertEqual(len(item["links"]), 1)
                link = item["links"][0]
                self.assertIn(link["href"].partition("#")[0].removesuffix(".html"), self.pages)
                rest = squash(text.removeprefix(f"Step {number}").replace(link["text"], "", 1))
                self.assertTrue(link["text"].strip())
                self.assertTrue(rest.endswith("."), f"one sentence follows the title: {rest!r}")

    def test_4_index_md_is_shown_below_the_path_as_the_all_pages_list(self):
        after_path = self.main[self.main.find("</ol>"):]
        self.assertGreater(self.main.find("</ol>"), 0, "no numbered path")
        self.assertIn("all pages", strip_tags(after_path).lower())
        source = (ROOT / "site" / "pages" / "index.md").read_text(encoding="utf-8")
        first_label = re.search(r"\[([^\]]+)\]\(", source).group(1)
        self.assertIn(first_label.replace("`", ""), strip_tags(after_path))

    def test_4_index_md_holds_no_coded_reference(self):
        source = (ROOT / "site" / "pages" / "index.md").read_text(encoding="utf-8")
        self.assertNotRegex(source, CODED)
        self.assertNotRegex(source, TICKET)

    def test_5_nothing_is_left_unexpanded_and_the_page_has_one_meta_description(self):
        self.assertNotIn("{{", self.home)
        self.assertEqual(self.home.count('name="description"'), 1)
        description = next(p["description"] for p in self.config["pages"] if p["slug"] == "index")
        self.assertEqual(meta_description(self.home), description)

    def test_5_the_home_page_has_no_sidebar_and_no_menu_button(self):
        for leftover in ('id="sidebar"', "menu-toggle", "<aside"):
            with self.subTest(leftover=leftover):
                self.assertNotIn(leftover, self.home)

    def test_5_the_text_of_the_home_page_holds_no_coded_reference(self):
        text = strip_tags(self.main)
        self.assertNotRegex(text, CODED)
        self.assertNotRegex(text, TICKET)


if __name__ == "__main__":
    unittest.main()
