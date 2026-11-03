"""Shared support of the editorial tests of the docs site v2 pages (test_build_site_concepts.py, test_build_site_guides.py): the editorial
rules as a mixin that a test class combines with unittest.TestCase and the scratch build that registers draft pages. Public, like the
other site tests. Standard library only; this module defines no test case of its own, so unittest runs nothing here.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT  # noqa: E402
from test_build_site_structure import CODED, TICKET  # noqa: E402

# repeated literals (SonarQube S1192)
HTML_SUFFIX = ".html"

PAGES_DIR = ROOT / "site" / "pages"
FAKE_REVIEW = "2026-11-03"   # a date for the scratch builds only: the maker's real review date is not invented here
# "There is no live demo site" is an honest denial that the pages may keep, so the claims are the affirmative phrases.
FORBIDDEN_CLAIMS = ("available on nuget", "install from nuget", "published on nuget", "on nuget.org", "try the demo", "online demo", "hosted demo",
                    "see it live", "cannot drift", "dotnet add package", "nuget install", "npm install", "pip install", "go get ", "try it online")
LINK = re.compile(r"\]\(([^)\s]+)\)")
SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:")


def text_of(slug: str) -> str:
    path = PAGES_DIR / f"{slug}.md"
    assert path.is_file(), f"site/pages/{slug}.md does not exist"
    return path.read_text(encoding="utf-8")


def title_of(slug: str) -> str:
    return text_of(slug).splitlines()[0].removeprefix("# ").strip()


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


def registered_entry(slug: str, title: str, group: str, description: str) -> dict:
    return {"slug": slug, "title": title, "source": f"site/pages/{slug}.md", "group": group, "description": description,
            "authored": True, "reviewed": FAKE_REVIEW}


def build_registered(transform) -> SimpleNamespace:
    """Builds a scratch copy of the site sources whose page list is `transform(pages)`: symlinks to the repository's top-level entries, a
    copy of site/. Returns tmp, root, config, out, errors and pages (slug -> html); the caller removes `tmp`."""
    tmp = Path(tempfile.mkdtemp())
    root = tmp / "repo"
    root.mkdir()
    for entry in ROOT.iterdir():
        if entry.name not in ("site", ".git", "github"):
            os.symlink(entry, root / entry.name)
    shutil.copytree(ROOT / "site", root / "site", ignore=shutil.ignore_patterns("_build"))
    config_path = root / "site" / "site.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["pages"] = transform(config["pages"])
    config_path.write_text(json.dumps(config), encoding="utf-8")
    out = tmp / "out"
    errors = bs.build(root, out)
    pages = {f.stem: f.read_text(encoding="utf-8") for f in out.glob("*.html")}
    return SimpleNamespace(tmp=tmp, root=root, config=config, out=out, errors=errors, pages=pages)


class EditorialMixin:
    """The editorial rules of a set of authored draft pages: a test class sets `SLUGS` (the pages under test) and `OTHER_SLUGS` (draft slugs
    of other sets that a link may name) and combines this mixin with unittest.TestCase."""
    SLUGS: tuple = ()
    OTHER_SLUGS: tuple = ()

    def test_each_page_starts_with_a_level_1_title_and_says_what_it_covers_and_who_needs_it_in_the_first_lines(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                lines = [line for line in text_of(slug).splitlines()[:6] if line.strip()]
                self.assertTrue(lines[0].startswith("# ") and not lines[0].startswith("## "), lines[0])
                intro = " ".join(lines[1:])
                self.assertRegex(intro, r"(?i)\bthis page\b")
                self.assertRegex(intro, r"(?i)\bit is for\b|\bis for (?:a|an|the)\b|\bwho\b")

    def test_every_level_2_heading_is_at_most_60_characters(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                headings = [line[3:].strip() for line in text_of(slug).splitlines() if line.startswith("## ")]
                self.assertTrue(headings)
                for heading in headings:
                    self.assertLessEqual(len(heading), 60, heading)

    def test_no_page_holds_a_coded_reference_a_ticket_number_or_the_word_trd(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                text = text_of(slug)
                self.assertNotRegex(text, CODED)
                self.assertNotRegex(text, TICKET)
                self.assertNotIn("TRD", text)

    def test_no_page_claims_a_published_package_a_demo_or_a_live_site(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                lowered = text_of(slug).lower()
                for claim in FORBIDDEN_CLAIMS:
                    self.assertNotIn(claim, lowered)

    def test_each_page_renders_with_no_unresolved_markup(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                rendered = bs.render_markdown(text_of(slug))
                self.assertTrue(rendered.html.strip())
                self.assertEqual(title_of(slug), rendered.title)
                prose = strip_code(rendered.html)
                for leftover in ("](", "**", "{{", "```", "~~~", "&lt;h", "&lt;p&gt;"):
                    self.assertNotIn(leftover, prose)

    def test_every_relative_link_resolves_to_a_repository_file_a_built_page_or_one_of_the_drafts(self):
        pages = real_slugs() | set(self.SLUGS) | set(self.OTHER_SLUGS)
        for slug in self.SLUGS:
            for target in LINK.findall(text_of(slug)):
                with self.subTest(page=slug, link=target):
                    path = target.partition("#")[0]
                    if SCHEME.match(target) or not path:
                        continue
                    if path.endswith(HTML_SUFFIX) and "/" not in path:
                        self.assertIn(path.removesuffix(HTML_SUFFIX), pages)
                    else:
                        resolved = Path(os.path.normpath(PAGES_DIR / path))
                        self.assertTrue(resolved.exists(), f"{target} does not exist")
                        self.assertFalse(bs._is_private(resolved.relative_to(ROOT).as_posix()), f"{target} is private")

    def test_each_page_ends_with_where_this_comes_from_and_names_an_existing_repository_file(self):
        for slug in self.SLUGS:
            with self.subTest(page=slug):
                section = where_it_comes_from(text_of(slug))
                self.assertTrue(section, "no 'Where this comes from' section")
                self.assertEqual(1, section.count("\n## "), "it is the last level-2 section")
                files = [t for t in LINK.findall(section) if not SCHEME.match(t) and not t.endswith(HTML_SUFFIX)]
                existing = [t for t in files if Path(os.path.normpath(PAGES_DIR / t.partition("#")[0])).is_file()]
                self.assertTrue(existing, f"no existing repository file linked in {section[:80]!r}")
