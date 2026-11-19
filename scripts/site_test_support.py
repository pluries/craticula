"""Shared support of the editorial tests of the docs site v2 pages (test_build_site_concepts.py, test_build_site_guides.py): the editorial
rules as a mixin that a test class combines with unittest.TestCase and the scratch build that registers draft pages. Public, like the
other site tests. Standard library only; this module defines no test case of its own, so unittest runs nothing here.
"""
import atexit
import hashlib
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
from test_build_site import ROOT, make_repo  # noqa: E402
from test_build_site_structure import CODED, TICKET  # noqa: E402

# repeated literals (SonarQube S1192)
HTML_SUFFIX = ".html"

PAGES_DIR = ROOT / "site" / "pages"

# Spec 004-site-languages: shared literals of the language tests (a literal repeated three times is a Sonar finding)
I18N_DIR = "site/i18n"
LANGUAGE_CODES = ("fr", "de", "it", "es", "zh")
HEADER_KEYS = ("translates", "title", "description", "source_fingerprint", "drafter", "drafted_on", "status")
SCOPES = ("translated", "english")
FAKE_REVIEW = "2026-11-03"   # a date for the scratch builds only: the maker's real review date is not invented here
# "There is no live demo site" is an honest denial that the pages may keep, so the claims are the affirmative phrases.
FORBIDDEN_CLAIMS = ("available on nuget", "install from nuget", "published on nuget", "on nuget.org", "try the demo", "online demo", "hosted demo",
                    "see it live", "cannot drift", "dotnet add package", "nuget install", "npm install", "pip install", "go get ", "try it online")
# 1.0.0 is on nuget.org (2026-11-10): the pages that tell a reader how to install an adapter may say so. Every other claim stays forbidden.
PACKAGE_CLAIMS = ("available on nuget", "install from nuget", "published on nuget", "on nuget.org", "dotnet add package", "nuget install")
PUBLISHED_PAGES = ("relational-adapters", "search-adapters")
LINK = re.compile(r"\]\(([^)\s]+)\)")
SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:")


def text_of(slug: str) -> str:
    path = PAGES_DIR / f"{slug}.md"
    assert path.is_file(), f"site/pages/{slug}.md does not exist"
    return path.read_text(encoding="utf-8")


def title_of(slug: str) -> str:
    return text_of(slug).splitlines()[0].removeprefix("# ").strip()


def real_slugs() -> set[str]:
    """The slugs of the built site: the registered pages and the pages the semantics split generates (one per rule summary)."""
    config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))
    slugs = {entry["slug"] for entry in config["pages"]}
    for entry in config["pages"]:
        if entry.get("generator") == "semantics-split":
            summaries = json.loads((ROOT / entry["summaries"]).read_text(encoding="utf-8"))
            slugs |= {bs.slugify(summary["title"]) for summary in summaries.values()}
    return slugs


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
            "authored": True, "reviewed": FAKE_REVIEW, "scope": SCOPES[0]}


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
                    if slug in PUBLISHED_PAGES and claim in PACKAGE_CLAIMS:
                        continue
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


# ---------------------------------------------------------------- spec 004-site-languages: the English pin (T005)

ENCODING = "utf-8"
REFERENCE_GROUP = "Reference"
MARK_KEY, SEARCH_URL_KEY = "english_mark", "search_english_url"
TITLE_KEY, DESCRIPTION_KEY, INDEX_KEY = "title", "description", "index"
LANG_MENU = re.compile(r'<nav class="lang-menu".*?</nav>', re.S)
HREFLANG_LINK = re.compile(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">')
CANONICAL_LINK = re.compile(r'<link rel="canonical" href="[^"]*">')
DATA_UI_ATTRIBUTE = re.compile(r' data-ui="[^"]*"')
ADDED_FRAGMENTS = (LANG_MENU, HREFLANG_LINK, CANONICAL_LINK, DATA_UI_ATTRIBUTE)
ASSET_VERSION = re.compile(r"\?v=[0-9a-f]{10}")
VERSION_PLACEHOLDER = "?v=HASH"
PIN_FILE = Path(__file__).resolve().parent / "testdata" / "english-fixture.sha256.json"
FIXTURE_SPEC_VERSION = "9.9.9-fixture"
FIXTURE_FILES = ("site/template.html", "site/home.html", "site/style.css", "site/js/theme.js", "site/js/site.js")
ENGLISH_FIXTURE_PAGES = [
    {"slug": INDEX_KEY, TITLE_KEY: "Home", "source": "site/pages/index.md", "template": "site/home.html", DESCRIPTION_KEY: "The home page of the fixture."},
    {"slug": "guide", TITLE_KEY: "A guide", "source": "site/pages/guide.md", DESCRIPTION_KEY: "The one guide of the fixture."},
]
ENGLISH_FIXTURE_TEXTS = {"site/pages/index.md": "# Home\n\nStart with the [guide](guide.md).\n",
                         "site/pages/guide.md": "# A guide\n\n## First step\n\nRun it, then go [home](index.md).\n",
                         "spec/VERSION": FIXTURE_SPEC_VERSION + "\n"}


def strip_added_fragments(markup: str) -> str:
    """The page without what spec 004 adds to the English markup: the language control, the `hreflang` and canonical links, `data-ui`."""
    for pattern in ADDED_FRAGMENTS:
        markup = pattern.sub("", markup)
    return markup


def normalise_versions(markup: str) -> str:
    return ASSET_VERSION.sub(VERSION_PLACEHOLDER, markup)


def html_digests(out: Path) -> dict[str, str]:
    """The sha256 of each output HTML file with `?v=<hash>` normalised and the added fragments stripped (the assets are not hashed)."""
    return {page.name: hashlib.sha256(strip_added_fragments(normalise_versions(page.read_text(encoding=ENCODING))).encode(ENCODING)).hexdigest()
            for page in sorted(out.glob("*.html"))}


def build_english_fixture() -> Path:
    """The output folder of the English fixture: the repository's own template, home page, stylesheet and scripts, two pages, no groups,
    split page, base address or language. The caller removes `out.parent`."""
    files = {rel: (ROOT / rel).read_text(encoding=ENCODING) for rel in FIXTURE_FILES}
    root = make_repo({**files, **ENGLISH_FIXTURE_TEXTS}, ENGLISH_FIXTURE_PAGES)
    errors = bs.build(root, root / "_out")
    assert errors == [], errors
    return root / "_out"


def record_english_pin() -> None:
    """Rewrites the pin from the generator as it stands. Run it only from the unchanged English generator (T005), never to make a test pass."""
    out = build_english_fixture()
    PIN_FILE.parent.mkdir(exist_ok=True)
    PIN_FILE.write_text(json.dumps(html_digests(out), indent=2, sort_keys=True) + "\n", encoding=ENCODING)
    shutil.rmtree(out.parent)


# ---------------------------------------------------------------- spec 004-site-languages: the language fixture (T006a to T007b)

BASE_URL = "https://docs.example.test"
LANGUAGE_NAMES = {"en": "English", "fr": "Français", "de": "Deutsch", "it": "Italiano", "es": "Español", "zh": "中文"}
LANG_ATTRIBUTES = {"en": "en", "fr": "fr", "de": "de", "it": "it", "es": "es", "zh": "zh-Hans"}
MARKS = {"fr": "(anglais)", "de": "(Englisch)", "it": "(inglese)", "es": "(inglés)", "zh": "（英文）"}
STUB_FINGERPRINT = "0" * 64
DRAFT_DATE = "2026-11-19"
HANDWRITTEN = "HANDWRITTEN-PAGE"
HANDWRITTEN_OVERVIEW = "HANDWRITTEN-OVERVIEW"
LINKED_PAGE, README_PAGE, SIBLING_PAGE = "what-is-craticula", "overview", "request-to-query"
SEMANTICS_LINK = "../../spec/semantics.md#sem-1"
SEMANTICS_TARGET = "case-sensitivity.html#sem-1"
CODE_SNIPPET = '<a href="grid-schema.html">grid</a>'
OUTSIDE_LINK = "https://example.org/x"
FULL, PARTIAL = "full", "partial"
LEFTOVER = "leftover.html"
ENGLISH_UI = {
    "skip": "Skip to content", "nav_docs": "Docs", "nav_reference": REFERENCE_GROUP, "menu_button": "Menu", "menu_aria": "Open the page menu",
    "pager_label": "Previous and next", "previous": "Previous", "next": "Next", "on_this_page": "On this page", "github_aria": "GitHub repository",
    "language_label": "Language", MARK_KEY: "(English)", "english_only": "This page is English only",
    "llms_home": "Home", "llms_english_source": "English source",
    "search_english": "Search the English site", SEARCH_URL_KEY: "index.html",
    "copy": "Copy", "copied": "Copied", "copy_failed": "Copy failed", "copy_aria": "Copy this code",
    "search_aria": "Search the documentation (Ctrl+K)", "search_label": "Search the documentation", "search_placeholder": "Search",
    "search_empty": "Type to search the documentation.", "search_none": "Nothing matches that search.", "search_loading": "Loading the search index...",
    "search_unavailable": "Search is not available right now.", "result_one": "result", "result_other": "results",
    "theme_aria": "Theme: {name}. Change theme", "theme_title": "Theme: {name}",
    "theme_names": {"auto": "Auto", "light": "Light", "dark": "Dark"},
    "group_names": {"Concepts": "Concepts", "Guides": "Guides", "Configuration": "Configuration", REFERENCE_GROUP: REFERENCE_GROUP},
    "subgroups": {"Semantics": "Semantics", "Quickstarts": "Quickstarts"},
}
CHROME_TEXT_KEYS = ("skip", "nav_docs", "nav_reference", "menu_button", "previous", "next", "on_this_page")
CHROME_ATTRIBUTE_KEYS = ("menu_aria", "pager_label", "github_aria", "search_aria")


def _tagged(code: str, value):
    if isinstance(value, dict):
        return {key: _tagged(code, item) for key, item in value.items()}
    return f"[{code}] {value}"


def ui_strings(code: str) -> dict:
    """The interface file of a language of the fixture: every English string behind a `[code]` tag, so no string is English by accident, the
    group card descriptions under `groups` (a translated file only, D-015) and the localized "(English)" mark."""
    if code == "en":
        return dict(ENGLISH_UI)
    ui = {key: _tagged(code, value) for key, value in ENGLISH_UI.items()}
    ui.update({MARK_KEY: MARKS[code], "result_one": f"[{code}] result", "result_other": f"[{code}] results", SEARCH_URL_KEY: "../index.html"})
    ui["groups"] = {name: f"[{code}] card of {name}" for name in ENGLISH_UI["group_names"]}
    return ui


def site_pages(root: Path) -> list:
    """The pages of the English site of `root` (the split semantics parts included), as `build_site.Page`."""
    return bs.SiteBuild(root, bs.load_config(root), "").pages


def stub_title(code: str, english_title: str) -> str:
    return f"[{code}] {english_title}"


def translation_file(slug: str, title: str, description: str, body: str, as_comment: bool = False) -> str:
    header = (f"translates: {slug}\ntitle: {title}\ndescription: {description}\nsource_fingerprint: {STUB_FINGERPRINT}\n"
              f"drafter: claude\ndrafted_on: {DRAFT_DATE}\nstatus: machine-drafted\n")
    opening, closing = ("<!--", "-->") if as_comment else ("---", "---")
    return f"{opening}\n{header}{closing}\n{body}"


def linked_body(code: str, title: str) -> str:
    """The first hand-written page: every kind of link the language build must leave alone or send to an English address."""
    links = (f"[rule]({SEMANTICS_LINK}) [spec](../../spec/README.md) [performance](performance.html) [index](../../spec/semantics.md) "
             f"[grid](grid-schema.html) [readme](../../README.md) [sibling](request-to-query.md) [own](#section-one) [outside]({OUTSIDE_LINK})")
    return f"# {title}\n\n{HANDWRITTEN} {code}.\n\n## Section one\n\n{links}\n\n```html\n{CODE_SNIPPET}\n```\n"


def overview_body(code: str, title: str) -> str:
    """The second hand-written page: a translation of the README, whose links are written from the repository root."""
    return f"# {title}\n\n{HANDWRITTEN_OVERVIEW} {code}.\n\n[rule](spec/semantics.md#sem-1) [spec](spec/README.md) [performance](performance.html)\n"


def index_body(title: str) -> str:
    return f"# {title}\n\n- [quickstart](quickstart-csharp.md)\n- [spec](../../spec/README.md)\n- [semantics](../../spec/semantics.md)\n"


def home_template(code: str, english_home: str) -> str:
    """A translated home page: the English file with two headings tagged, the `grid-schema.html` link kept as written in English."""
    tagged = english_home.replace("<h2>Find your way in</h2>", f"<h2>[{code}] Find your way in</h2>")
    return tagged.replace('<a href="grid-schema.html">Declare a GridSchema</a>', f'<a href="grid-schema.html">[{code}] Declare a GridSchema</a>')


def _body_of(code: str, slug: str, title: str) -> str:
    if slug == LINKED_PAGE:
        return linked_body(code, title)
    if slug == README_PAGE:
        return overview_body(code, title)
    return index_body(title) if slug == INDEX_KEY else f"# {title}\n\n[{code}] a stub of {slug}.\n"


def language_files(code: str, config: dict, english_home: str, omit: tuple[str, ...] = ()) -> dict[str, str]:
    """The files of one language: its interface file and a translation of every translated document not in `omit`."""
    files = {f"site/i18n/{code}/ui.json": json.dumps(ui_strings(code), ensure_ascii=False)}
    for entry in config["pages"]:
        slug = entry["slug"]
        if entry["scope"] != "translated" or slug in omit:
            continue
        title = stub_title(code, entry[TITLE_KEY])
        description = f"[{code}] {entry[DESCRIPTION_KEY]}"
        files[f"site/i18n/{code}/{slug}.md"] = translation_file(slug, title, description, _body_of(code, slug, title))
        if slug == INDEX_KEY:
            files[f"site/i18n/{code}/home.html"] = translation_file(slug, title, description, home_template(code, english_home), as_comment=True)
    return files


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=ENCODING)


def language_tree(tmp: Path, omit: tuple[str, ...] = (), keep_base: bool = True) -> Path:
    """A copy of this repository's sources whose `site/i18n` is the fixture's alone: the six interface files and the stub translations."""
    root = tmp / "repo"
    root.mkdir()
    for entry in ROOT.iterdir():
        if entry.name not in ("site", ".git", "github"):
            os.symlink(entry, root / entry.name)
    shutil.copytree(ROOT / "site", root / "site", ignore=shutil.ignore_patterns("_build", "i18n"))
    config_path = root / "site" / "site.json"
    config = json.loads(config_path.read_text(encoding=ENCODING))
    if not keep_base:
        config.pop("baseUrl")
        config_path.write_text(json.dumps(config), encoding=ENCODING)
    english_home = (root / "site" / "home.html").read_text(encoding=ENCODING)
    write_tree(root, {"site/i18n/en/ui.json": json.dumps(ENGLISH_UI, ensure_ascii=False)})
    for code in LANGUAGE_CODES:
        write_tree(root, language_files(code, config, english_home, omit))
    return root


_BUILDS: dict[str, SimpleNamespace] = {}
_SCRATCH = Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, _SCRATCH, True)


def language_build(name: str) -> SimpleNamespace:
    """One of the two builds the language tests read, made once per run. FULL: every language previewed, all 20 documents translated, a base
    address. PARTIAL: only French previewed, `overview` not translated, no base address, and the folders of two disabled languages left from an
    earlier build. A build that raises (the language build is not written yet) is not kept, so each test that needs it fails by itself."""
    if name not in _BUILDS:
        full = name == FULL
        tmp = Path(tempfile.mkdtemp(dir=_SCRATCH))
        root = language_tree(tmp, () if full else (README_PAGE,), keep_base=full)
        out = tmp / "out"
        if not full:
            write_tree(out, {f"{code}/{LEFTOVER}": "old" for code in LANGUAGE_CODES[1:]})
        errors = bs.build(root, out, BASE_URL if full else None, preview=LANGUAGE_CODES if full else LANGUAGE_CODES[:1])
        _BUILDS[name] = SimpleNamespace(root=root, out=out, errors=errors, config=json.loads((root / "site" / "site.json").read_text(encoding=ENCODING)))
    return _BUILDS[name]
