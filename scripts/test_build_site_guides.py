#!/usr/bin/env python3
"""Editorial rules of the eight authored Guides and Configuration pages of the docs site v2 (story #3554, task #3559), pinned on the
Markdown files in site/pages/ and on a scratch build that registers them together with the four Concepts drafts. The real site.json does
not list them yet (the maker's review dates come first), and nothing here reads that fact. Mirrors scripts/test_build_site_concepts.py.
Offline, standard library only.
Run: python3 scripts/test_build_site_guides.py
"""
import gzip
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from site_test_support import EditorialMixin, build_registered, registered_entry, text_of, title_of  # noqa: E402
from test_build_site_concepts import DESCRIPTIONS as CONCEPT_DESCRIPTIONS, SLUGS as CONCEPT_SLUGS, TITLES as CONCEPT_TITLES  # noqa: E402
from test_build_site_home import cards_of  # noqa: E402
from test_build_site_structure import CODED, TICKET, meta_description, sidebar  # noqa: E402

GUIDE_SLUGS = ("paging-and-sorting", "grouping-and-aggregation", "csv-export", "relational-adapters", "search-adapters")
CONFIGURATION_SLUGS = ("the-gridschema", "limits", "dialects-and-providers")
SLUGS = GUIDE_SLUGS + CONFIGURATION_SLUGS
DESCRIPTIONS = {
    "paging-and-sorting": "How the row range and the sort order of a request become paging and ordering.",
    "grouping-and-aggregation": "How row grouping and aggregation answer one level at a time.",
    "csv-export": "What Craticula does for a CSV export and what stays with you.",
    "relational-adapters": "The optional Dapper and Entity Framework Core packages.",
    "search-adapters": "The optional MongoDB and OpenSearch packages.",
    "the-gridschema": "What the schema holds and which of its settings are enforced.",
    "limits": "The resource limits on every request and how to change them.",
    "dialects-and-providers": "The databases Craticula writes queries for and how they differ.",
}


class EditorialRules(EditorialMixin, unittest.TestCase):
    SLUGS = SLUGS
    OTHER_SLUGS = CONCEPT_SLUGS


class ScratchRegistration(unittest.TestCase):
    """The twelve drafts can be registered: a scratch copy of the site sources with them added builds clean."""

    @classmethod
    def registered(cls, pages: list[dict]) -> list[dict]:
        concepts = [registered_entry(s, CONCEPT_TITLES[s], "Concepts", CONCEPT_DESCRIPTIONS[s]) for s in CONCEPT_SLUGS]
        guides = [registered_entry(s, title_of(s), "Guides", DESCRIPTIONS[s]) for s in GUIDE_SLUGS]
        configuration = [registered_entry(s, title_of(s), "Configuration", DESCRIPTIONS[s]) for s in CONFIGURATION_SLUGS]
        last_guide = max(i for i, p in enumerate(pages) if p.get("group") == "Guides")
        return [pages[0], *concepts, *pages[1:last_guide + 1], *guides, *configuration, *pages[last_guide + 1:]]

    @classmethod
    def setUpClass(cls):
        site = build_registered(cls.registered)
        cls.addClassCleanup(shutil.rmtree, site.tmp, ignore_errors=True)
        cls.config, cls.out, cls.errors, cls.pages = site.config, site.out, site.errors, site.pages

    def docs_links(self) -> list[tuple[tuple[str, ...], str, str, bool]]:
        return sidebar(self.pages["quickstart-csharp"]).links

    def test_the_site_builds_without_errors_with_the_twelve_pages_registered(self):
        self.assertEqual(self.errors, [])
        for slug in (*CONCEPT_SLUGS, *SLUGS):
            self.assertIn(slug, self.pages)

    def test_the_sidebar_shows_the_four_groups_in_order_with_the_new_pages_in_theirs(self):
        links = self.docs_links()
        groups = list(dict.fromkeys(path[0] for path, _, _, _ in links))
        self.assertEqual(["Concepts", "Guides", "Configuration", "Reference"], groups)
        self.assertEqual([f"{s}.html" for s in CONFIGURATION_SLUGS], [h for path, h, _, _ in links if path[0] == "Configuration"])
        guides = [h for path, h, _, _ in links if path[0] == "Guides"]
        self.assertEqual([f"{s}.html" for s in GUIDE_SLUGS], guides[-len(GUIDE_SLUGS):])
        self.assertGreater(len(guides), len(GUIDE_SLUGS), "the existing Guides pages come first")

    def test_the_home_page_shows_a_card_for_each_of_the_four_groups_in_order(self):
        cards = cards_of(self.pages["index"]).cards
        first: dict[str, str] = {}
        for path, href, _, _ in self.docs_links():
            first.setdefault(path[0], href)
        expected = [(first[name], name, self.config["groups"][name]) for name in bs.GROUPS]
        self.assertEqual(expected, cards)

    def llms_sections(self) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current = ""
        for line in (self.out / "llms.txt").read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                current = line[3:]
                sections[current] = []
            elif line.startswith("- [") and current:
                sections[current].append(line.split("](", 1)[1].split(")", 1)[0].rsplit("/", 1)[-1].removesuffix(".md"))
        return sections

    def test_llms_txt_lists_every_new_page_under_its_group(self):
        sections = self.llms_sections()
        self.assertEqual(["Home", *bs.GROUPS], list(sections))
        self.assertEqual(list(CONCEPT_SLUGS), sections["Concepts"])
        self.assertEqual(list(GUIDE_SLUGS), [s for s in sections["Guides"] if s in GUIDE_SLUGS])
        self.assertEqual(list(CONFIGURATION_SLUGS), sections["Configuration"])
        self.assertTrue(all(s not in sections["Reference"] for s in (*CONCEPT_SLUGS, *SLUGS)))

    def test_the_search_index_has_one_entry_per_page_and_no_coded_reference(self):
        raw = (self.out / "search-index.json").read_bytes()
        self.assertLessEqual(len(gzip.compress(raw, 9)), 500 * 1024)
        entries = json.loads(raw)
        self.assertEqual(sorted(self.pages), sorted(e["slug"] for e in entries))
        by_slug = {e["slug"]: e for e in entries}
        for slug in SLUGS:
            self.assertEqual(DESCRIPTIONS[slug], by_slug[slug]["description"])
            self.assertEqual(title_of(slug), by_slug[slug]["title"])
        for entry in entries:
            with self.subTest(page=entry["slug"]):
                for value in (entry["title"], entry["description"], entry["text"], *(h["text"] for h in entry["headings"])):
                    self.assertNotRegex(value, CODED)
                    self.assertNotRegex(value, TICKET)

    def test_each_new_page_has_its_description_and_labels_within_sixty_characters(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                self.assertEqual(DESCRIPTIONS[slug], meta_description(self.pages[slug]))
                self.assertTrue(all(len(label) <= 60 for _, _, label, _ in sidebar(self.pages[slug]).links))

    def test_the_markdown_copies_equal_the_sources(self):
        for slug in SLUGS:
            self.assertEqual(text_of(slug), (self.out / f"{slug}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
