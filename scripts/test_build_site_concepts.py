#!/usr/bin/env python3
"""Editorial rules of the four Concepts pages of the docs site v2 (story #3554, task #3558), pinned on the Markdown files themselves
(site/pages/what-is-craticula.md, request-to-query.md, strict-and-lenient.md, safety-model.md) and on a scratch build that registers
them. The real site.json does not list them yet (the maker's review date comes first), so nothing here reads that fact. Offline,
standard library only.
Run: python3 scripts/test_build_site_concepts.py
"""
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
from test_build_site_home import cards_of  # noqa: E402
from test_build_site_structure import CODED, TICKET, meta_description, sidebar  # noqa: E402

PAGES_DIR = ROOT / "site" / "pages"
SLUGS = ("what-is-craticula", "request-to-query", "strict-and-lenient", "safety-model")
TITLES = {"what-is-craticula": "What Craticula is", "request-to-query": "How a request becomes a query",
          "strict-and-lenient": "Strict and Lenient", "safety-model": "The safety model"}
DESCRIPTIONS = {"what-is-craticula": "What Craticula does, what it leaves to you and where the project stands.",
                "request-to-query": "How one grid request becomes a query with parameters.",
                "strict-and-lenient": "The two schema modes and what each does with an unknown column.",
                "safety-model": "What Craticula does against a hostile request and what it does not."}
FAKE_REVIEW = "2026-11-03"   # a date for the scratch build only: the maker's real review date is not invented here
# "There is no live demo site" is an honest denial that the pages may keep, so the claims are the affirmative phrases.
FORBIDDEN_CLAIMS = ("available on nuget", "install from nuget", "published on nuget", "on nuget.org", "try the demo", "online demo", "hosted demo", "see it live", "cannot drift",
                    "dotnet add package", "nuget install", "npm install", "pip install", "go get ", "try it online")
LINK = re.compile(r"\]\(([^)\s]+)\)")


def text_of(slug: str) -> str:
    path = PAGES_DIR / f"{slug}.md"
    assert path.is_file(), f"site/pages/{slug}.md does not exist"
    return path.read_text(encoding="utf-8")


def real_slugs() -> set[str]:
    config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))
    return {entry["slug"] for entry in config["pages"]}


def strip_code(markup: str) -> str:
    """The HTML without its <pre> blocks and inline <code> spans, where punctuation is legitimate."""
    for tag in ("pre", "code"):
        while f"<{tag}" in markup:
            start = markup.index(f"<{tag}")
            end = markup.find(f"</{tag}>", start)
            markup = markup[:start] + markup[end + len(tag) + 3:]
    return markup


def where_it_comes_from(text: str) -> str:
    marker = "\n## Where this comes from"
    return text[text.index(marker):] if marker in text else ""


class EditorialRules(unittest.TestCase):
    def test_each_page_starts_with_a_level_1_title_and_says_what_it_covers_and_who_needs_it_in_five_lines(self):
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
                self.assertEqual(TITLES[slug], rendered.title)
                prose = strip_code(rendered.html)
                for leftover in ("](", "**", "{{", "```", "~~~", "&lt;h", "&lt;p&gt;"):
                    self.assertNotIn(leftover, prose)

    def test_every_relative_link_resolves_to_a_repository_file_a_built_page_or_one_of_the_four_pages(self):
        pages = real_slugs() | set(SLUGS)
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
                text = text_of(slug)
                section = where_it_comes_from(text)
                self.assertTrue(section, "no 'Where this comes from' section")
                self.assertEqual(1, section.count("\n## "), "it is the last level-2 section")
                files = [t for t in LINK.findall(section) if not re.match(r"[a-z][a-z0-9+.-]*:", t) and not t.endswith(".html")]
                existing = [t for t in files if Path(os.path.normpath(PAGES_DIR / t.partition("#")[0])).is_file()]
                self.assertTrue(existing, f"no existing repository file linked in {section[:80]!r}")


class ScratchRegistration(unittest.TestCase):
    """The four pages can be registered: a scratch copy of the site sources with them added builds clean."""

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
        cls.config["pages"] = [cls.config["pages"][0]] + [
            {"slug": slug, "title": TITLES[slug], "source": f"site/pages/{slug}.md", "group": "Concepts", "description": DESCRIPTIONS[slug],
             "authored": True, "reviewed": FAKE_REVIEW} for slug in SLUGS] + cls.config["pages"][1:]
        config_path.write_text(json.dumps(cls.config), encoding="utf-8")
        cls.out = cls.tmp / "out"
        cls.errors = bs.build(cls.root, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}

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


if __name__ == "__main__":
    unittest.main()
