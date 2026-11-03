#!/usr/bin/env python3
"""Editorial rules of the eight authored Guides and Configuration pages of the docs site v2 (story #3554, task #3559), pinned on the
Markdown files in site/pages/ and on a scratch build that registers them together with the four Concepts drafts. The real site.json does
not list them yet (the maker's review dates come first), and nothing here reads that fact. Mirrors scripts/test_build_site_concepts.py.
Offline, standard library only.
Run: python3 scripts/test_build_site_guides.py
"""
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT  # noqa: E402
from test_build_site_concepts import (  # noqa: E402
    FAKE_REVIEW, FORBIDDEN_CLAIMS, LINK, PAGES_DIR, SLUGS as CONCEPT_SLUGS, TITLES as CONCEPT_TITLES, DESCRIPTIONS as CONCEPT_DESCRIPTIONS,
    real_slugs, strip_code, text_of, where_it_comes_from)
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


def title_of(slug: str) -> str:
    return text_of(slug).splitlines()[0].removeprefix("# ").strip()


class EditorialRules(unittest.TestCase):
    def test_each_page_starts_with_a_level_1_title_and_says_what_it_covers_and_who_needs_it_in_the_first_lines(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                lines = [line for line in text_of(slug).splitlines()[:6] if line.strip()]
                self.assertTrue(lines[0].startswith("# ") and not lines[0].startswith("## "), lines[0])
                intro = " ".join(lines[1:])
                self.assertRegex(intro, r"(?i)\bthis page\b")
                self.assertRegex(intro, r"(?i)\bit is for\b|\bis for (?:a|an|the)\b|\bwho\b")

    def test_every_level_2_heading_is_at_most_60_characters(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                headings = [line[3:].strip() for line in text_of(slug).splitlines() if line.startswith("## ")]
                self.assertTrue(headings)
                for heading in headings:
                    self.assertLessEqual(len(heading), 60, heading)

    def test_no_page_holds_a_coded_reference_a_ticket_number_or_the_word_trd(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                text = text_of(slug)
                self.assertNotRegex(text, CODED)
                self.assertNotRegex(text, TICKET)
                self.assertNotIn("TRD", text)

    def test_no_page_claims_a_published_package_a_demo_or_a_live_site(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                lowered = text_of(slug).lower()
                for claim in FORBIDDEN_CLAIMS:
                    self.assertNotIn(claim, lowered)

    def test_each_page_renders_with_no_unresolved_markup(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                rendered = bs.render_markdown(text_of(slug))
                self.assertTrue(rendered.html.strip())
                self.assertEqual(title_of(slug), rendered.title)
                prose = strip_code(rendered.html)
                for leftover in ("](", "**", "{{", "```", "~~~", "&lt;h", "&lt;p&gt;"):
                    self.assertNotIn(leftover, prose)

    def test_every_relative_link_resolves_to_a_repository_file_a_built_page_or_one_of_the_twelve_drafts(self):
        pages = real_slugs() | set(CONCEPT_SLUGS) | set(SLUGS)
        for slug in SLUGS:
            for target in LINK.findall(text_of(slug)):
                with self.subTest(page=slug, link=target):
                    if re.match(r"[a-z][a-z0-9+.-]*:", target):
                        continue
                    path = target.partition("#")[0]
                    if not path:
                        continue
                    if path.endswith(".html") and "/" not in path:
                        self.assertIn(path.removesuffix(".html"), pages)
                    else:
                        resolved = Path(os.path.normpath(PAGES_DIR / path))
                        self.assertTrue(resolved.exists(), f"{target} does not exist")
                        self.assertFalse(bs._is_private(resolved.relative_to(ROOT).as_posix()), f"{target} is private")

    def test_each_page_ends_with_where_this_comes_from_and_names_an_existing_repository_file(self):
        for slug in SLUGS:
            with self.subTest(page=slug):
                section = where_it_comes_from(text_of(slug))
                self.assertTrue(section, "no 'Where this comes from' section")
                self.assertEqual(1, section.count("\n## "), "it is the last level-2 section")
                files = [t for t in LINK.findall(section) if not re.match(r"[a-z][a-z0-9+.-]*:", t) and not t.endswith(".html")]
                existing = [t for t in files if Path(os.path.normpath(PAGES_DIR / t.partition("#")[0])).is_file()]
                self.assertTrue(existing, f"no existing repository file linked in {section[:80]!r}")


class ScratchRegistration(unittest.TestCase):
    """The twelve drafts can be registered: a scratch copy of the site sources with them added builds clean."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.root = cls.tmp / "repo"
        cls.root.mkdir()
        for entry in ROOT.iterdir():
            if entry.name not in ("site", ".git", "github"):
                os.symlink(entry, cls.root / entry.name)
        shutil.copytree(ROOT / "site", cls.root / "site", ignore=shutil.ignore_patterns("_build"))
        config_path = cls.root / "site" / "site.json"
        cls.config = json.loads(config_path.read_text(encoding="utf-8"))
        cls.config["pages"] = cls.registered(cls.config["pages"])
        config_path.write_text(json.dumps(cls.config), encoding="utf-8")
        cls.out = cls.tmp / "out"
        cls.errors = bs.build(cls.root, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}

    @staticmethod
    def entry(slug: str, title: str, group: str, description: str) -> dict:
        return {"slug": slug, "title": title, "source": f"site/pages/{slug}.md", "group": group, "description": description,
                "authored": True, "reviewed": FAKE_REVIEW}

    @classmethod
    def registered(cls, pages: list[dict]) -> list[dict]:
        concepts = [cls.entry(s, CONCEPT_TITLES[s], "Concepts", CONCEPT_DESCRIPTIONS[s]) for s in CONCEPT_SLUGS]
        guides = [cls.entry(s, title_of(s), "Guides", DESCRIPTIONS[s]) for s in GUIDE_SLUGS]
        configuration = [cls.entry(s, title_of(s), "Configuration", DESCRIPTIONS[s]) for s in CONFIGURATION_SLUGS]
        last_guide = max(i for i, p in enumerate(pages) if p.get("group") == "Guides")
        return [pages[0], *concepts, *pages[1:last_guide + 1], *guides, *configuration, *pages[last_guide + 1:]]

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
