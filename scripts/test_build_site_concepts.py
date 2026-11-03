#!/usr/bin/env python3
"""Editorial rules of the four Concepts pages of the docs site v2 (story #3554, task #3558), pinned on the Markdown files themselves
(site/pages/what-is-craticula.md, request-to-query.md, strict-and-lenient.md, safety-model.md) and on a scratch build that registers
them. The real site.json does not list them yet (the maker's review date comes first), so nothing here reads that fact. Offline,
standard library only.
Run: python3 scripts/test_build_site_concepts.py
"""
import datetime
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from site_test_support import EditorialMixin, build_registered, registered_entry  # noqa: E402
from test_build_site import ROOT  # noqa: E402
from test_build_site_home import cards_of  # noqa: E402
from test_build_site_structure import CODED, meta_description, sidebar  # noqa: E402

SLUGS = ("what-is-craticula", "request-to-query", "strict-and-lenient", "safety-model")
TITLES = {"what-is-craticula": "What Craticula is", "request-to-query": "How a request becomes a query",
          "strict-and-lenient": "Strict and Lenient", "safety-model": "The safety model"}
DESCRIPTIONS = {"what-is-craticula": "What Craticula does, what it leaves to you and where the project stands.",
                "request-to-query": "How one grid request becomes a query with parameters.",
                "strict-and-lenient": "The two schema modes and what each does with an unknown column.",
                "safety-model": "What Craticula does against a hostile request and what it does not."}


class EditorialRules(EditorialMixin, unittest.TestCase):
    SLUGS = SLUGS


class ScratchRegistration(unittest.TestCase):
    """The four pages can be registered: a scratch copy of the site sources with them added builds clean."""

    @classmethod
    def setUpClass(cls):
        def register(pages):   # idempotent: a page the real site.json already lists is replaced by the scratch entry
            rest = [p for p in pages if p["slug"] not in SLUGS]
            return [rest[0]] + [registered_entry(slug, TITLES[slug], "Concepts", DESCRIPTIONS[slug]) for slug in SLUGS] + rest[1:]

        site = build_registered(register)
        cls.addClassCleanup(shutil.rmtree, site.tmp, ignore_errors=True)
        cls.config, cls.out, cls.errors, cls.pages = site.config, site.out, site.errors, site.pages

    def test_the_site_builds_without_errors_with_the_four_pages_registered(self):
        self.assertEqual(self.errors, [])
        for slug in SLUGS:
            self.assertIn(slug, self.pages)

    def test_the_concepts_group_leads_the_sidebar_with_the_four_pages_in_order(self):
        links = sidebar(self.pages["quickstart-csharp"]).links
        self.assertEqual("Concepts", links[0][0][0])
        self.assertEqual([f"{slug}.html" for slug in SLUGS], [href for path, href, _, _ in links if path[0] == "Concepts"])
        self.assertEqual([TITLES[slug] for slug in SLUGS], [label for path, _, label, _ in links if path[0] == "Concepts"])

    def test_the_home_page_shows_a_concepts_card_with_the_groups_description(self):
        home = self.pages["index"]
        cards = cards_of(home).cards
        self.assertEqual(("what-is-craticula.html", "Concepts", self.config["groups"]["Concepts"]), cards[0])
        self.assertEqual([name for name in bs.GROUPS if name in {c[1] for c in cards}], [c[1] for c in cards])

    def test_the_home_page_still_holds_to_its_own_rules(self):
        home = self.pages["index"]
        self.assertEqual(1, home.count("<h1"))
        self.assertNotIn("{{", home)
        self.assertEqual(1, home.count('name="description"'))
        for leftover in ('id="sidebar"', "menu-toggle", "<aside"):
            self.assertNotIn(leftover, home)
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", home[home.find("<main"):home.find("</main>")]), CODED)

    def test_each_registered_page_has_its_description_title_and_no_coded_label(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                self.assertEqual(DESCRIPTIONS[slug], meta_description(self.pages[slug]))
                self.assertIn("<h1", self.pages[slug])
                labels = [label for _, _, label, _ in sidebar(self.pages[slug]).links]
                self.assertTrue(all(len(label) <= 60 for label in labels))

    def test_the_markdown_copies_and_the_llms_listing_cover_the_four_pages(self):
        text = (self.out / "llms.txt").read_text(encoding="utf-8")
        for slug in SLUGS:
            self.assertIn(f"{slug}.md", text)
            self.assertEqual((ROOT / "site" / "pages" / f"{slug}.md").read_text(encoding="utf-8"), (self.out / f"{slug}.md").read_text(encoding="utf-8"))
        self.assertIn("## Concepts", text)


class RealRegistration(unittest.TestCase):
    """The maker approved the four pages: the real site.json lists them as authored Concepts pages with a review date, and the site builds them."""

    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))
        cls.entries = {entry["slug"]: entry for entry in cls.config["pages"]}
        cls.out = Path(tempfile.mkdtemp()) / "out"
        cls.addClassCleanup(shutil.rmtree, cls.out.parent, ignore_errors=True)
        cls.errors = bs.build(ROOT, cls.out)

    def test_the_real_site_json_lists_each_page_as_an_authored_concepts_page_with_a_valid_review_date(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                entry = self.entries[slug]
                self.assertEqual("Concepts", entry["group"])
                self.assertEqual(f"site/pages/{slug}.md", entry["source"])
                self.assertIs(entry["authored"], True)
                self.assertRegex(entry["reviewed"], r"^\d{4}-\d{2}-\d{2}$")
                datetime.date.fromisoformat(entry["reviewed"])
                self.assertTrue(entry["description"].strip())

    def test_the_real_site_builds_the_four_pages_without_errors(self):
        self.assertEqual(self.errors, [])
        for slug in SLUGS:
            self.assertTrue((self.out / f"{slug}.html").is_file(), slug)
            self.assertTrue((self.out / f"{slug}.md").is_file(), slug)


if __name__ == "__main__":
    unittest.main()
