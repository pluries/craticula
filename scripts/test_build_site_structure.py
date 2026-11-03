#!/usr/bin/env python3
"""Tests of the structure and generator of the docs site v2 (story #3554, task #3555): the four-group nested sidebar, previous and
next links, the semantics split with plain titles and summaries, the link remap, the footer and the favicon, and the build
refusals of DS-9, DS-19, DS-21, DS-22 and DS-24. Offline, standard library only; the scratch repositories come from test_build_site.
Run: python3 scripts/test_build_site_structure.py
"""
import json
import re
import struct
import sys
import tempfile
import unittest
import zlib
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT, make_repo  # noqa: E402

# repeated literals (SonarQube S1192)
AGGREGATION_SEMANTICS = "aggregation semantics"
SEMANTICS_MD = "semantics.md"
SITE_SUMMARIES_JSON = "site/summaries.json"
THE_RULES_BEHIND_THE_OUTPUT = "The rules behind the output."
INDEX_MD = "index.md"
FAVICON_SVG = "favicon.svg"
FAVICON_ICO = "favicon.ico"
APPLE_TOUCH_ICON_PNG = "apple-touch-icon.png"
XMLNS_ATTRIBUTE = 'xmlns(?::\\w+)?="[^"]*"'
HTML_GLOB = "*.html"
BETA_HTML = "beta.html"
BAD_MD = "bad.md"

TEMPLATE = ('<!doctype html><html><head>{{head_links}}<meta name="description" content="{{description}}"><title>{{page_title}}</title></head>'
            '<body><aside>{{sidebar}}</aside><nav class="toc">{{toc}}</nav><main>{{content}}</main>{{prev_next}}'
            '<footer>spec {{spec_version}}</footer></body></html>')
CODED = re.compile(r"\b[A-Z]{2,5}-\d+")
TICKET = re.compile(r"#\d{3,}")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PREV_NEXT = 'aria-label="Previous and next"'

SEM_SOURCE = ("# Semantics\n\nIntro.\n\n"
              "## SEM-1. Case sensitivity\n\nBody one. **SEM-1a. A rule.** x\n\n"
              "## SEM-2. Null handling\n\nBody two.\n\n"
              "## Addendum — aggregation semantics (not numbered SEM-*, for the same reason)\n\n**AGG-1. Sum.** Body three.\n")
SUMMARIES = {
    "SEM-1": {"title": "Case rules", "description": "How text compares.", "summary": "Text compares without case by default. Opt in to case sensitive. That is all."},
    "SEM-2": {"title": "Null rules", "description": "How nulls behave.", "summary": "A null matches nothing. Sorting puts it last."},
    AGGREGATION_SEMANTICS: {"title": "Aggregation rules", "description": "How sums work.", "summary": "Sums skip nulls."},
}
SPLIT_SLUGS = {"SEM-1": "case-rules", "SEM-2": "null-rules", AGGREGATION_SEMANTICS: "aggregation-rules"}


def page(slug: str, group: str | None, title: str | None = None, **extra) -> dict:
    entry = {"slug": slug, "title": title or slug.title(), "source": f"{slug}.md", "description": f"The {slug} page.", **extra}
    if group is not None:
        entry["group"] = group
    return entry


HOME = page("index", "Guides", "Home")  # accepted by the current build; the page without a group is pinned by one test (Sidebar)


def split_page() -> dict:
    return {"slug": "semantics", "title": "Semantics", "source": SEMANTICS_MD, "generator": "semantics-split",
            "summaries": SITE_SUMMARIES_JSON, "group": "Reference", "description": THE_RULES_BEHIND_THE_OUTPUT}


def site(pages: list[dict], files: dict[str, str] | None = None, **extra) -> Path:
    sources = {p["source"]: f"# {p['title']}\n\nText of {p['slug']}.\n" for p in pages if "generator" not in p}
    return make_repo({"site/template.html": TEMPLATE, "spec/VERSION": "7.8.9\n", **sources, **(files or {})}, pages,
                     default_group=False, default_description=False, **extra)


def split_site(summaries: dict | None = None, index_source: str | None = None, files: dict[str, str] | None = None) -> Path:
    extra_files = {SEMANTICS_MD: SEM_SOURCE, SITE_SUMMARIES_JSON: json.dumps(SUMMARIES if summaries is None else summaries), **(files or {})}
    if index_source is not None:
        extra_files[INDEX_MD] = index_source
    return site([HOME, split_page()], extra_files)


def outcome(root: Path) -> tuple[list[str], Path]:
    """The build's messages (its error list, or a configuration error as one message) and the output folder."""
    out = root / "_out"
    try:
        return bs.build(root, out), out
    except bs.BuildError as error:
        return [str(error)], out


def built(root: Path) -> dict[str, str]:
    errors, out = outcome(root)
    assert errors == [], errors
    return {f.stem: f.read_text(encoding="utf-8") for f in out.glob(HTML_GLOB)}


class Tags(HTMLParser):
    """Every start tag of a document with its attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {k: (v or "") for k, v in attrs}))


class Anchors(HTMLParser):
    """The links of a fragment: (attributes, text)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[dict, str]] = []
        self._attrs: dict | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._attrs, self._text = {k: (v or "") for k, v in attrs}, []

    def handle_data(self, data):
        if self._attrs is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._attrs is not None:
            self.links.append((self._attrs, "".join(self._text).strip()))
            self._attrs = None


class SideParser(HTMLParser):
    """The sidebar: each link with the labels of the `<details>` around it, and which `<details>` are open."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[list] = []  # [label, is_open]
        self.links: list[tuple[tuple[str, ...], str, str, bool]] = []  # path, href, label, current
        self.open: dict[tuple[str, ...], bool] = {}
        self._in_summary = False
        self._href: str | None = None
        self._current = False
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        found = dict(attrs)
        if tag == "details":
            self.stack.append(["", "open" in found])
        elif tag == "summary":
            self._in_summary = True
        elif tag == "a":
            self._href, self._current, self._text = found.get("href") or "", found.get("aria-current") == "page", []

    def handle_data(self, data):
        if self._in_summary and self.stack:
            self.stack[-1][0] += data.strip()
        elif self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "summary":
            self._in_summary = False
        elif tag == "details" and self.stack:
            path = tuple(item[0] for item in self.stack)
            self.open[path] = self.stack[-1][1]
            self.stack.pop()
        elif tag == "a" and self._href is not None:
            self.links.append((tuple(item[0] for item in self.stack), self._href, "".join(self._text).strip(), self._current))
            self._href = None


def element_inner(text: str, tag: str) -> str:
    """The inner markup of the first `<tag ...>` element of `text`; '' when absent."""
    opened = text.find(f"<{tag}")
    if opened < 0:
        return ""
    begin = text.find(">", opened) + 1
    return text[begin:text.find(f"</{tag}>", begin)]


def fragment(text: str, start: str, end: str) -> str:
    """The part of `text` from the tag that holds `start` (an attribute text) up to `end`; '' when absent."""
    at = text.find(start)
    if at < 0:
        return ""
    begin = max(text.rfind("<", 0, at), 0)
    return text[begin:text.find(end, at) + len(end)]


def group_of(path: tuple[str, ...]) -> str:
    return path[0] if path else ""


def sidebar(page_html: str) -> SideParser:
    parser = SideParser()
    parser.feed(fragment(page_html, "<aside", "</aside>"))
    return parser


def sidebar_order(page_html: str) -> list[str]:
    """The hrefs of the sidebar in order."""
    return [href for _, href, _, _ in sidebar(page_html).links]


def prev_next(page_html: str) -> dict[str, str]:
    parser = Anchors()
    parser.feed(fragment(page_html, PREV_NEXT, "</nav>"))
    return {attrs.get("rel", ""): attrs.get("href", "") for attrs, _ in parser.links}


def toc_labels(page_html: str) -> list[str]:
    parser = Anchors()
    parser.feed(fragment(page_html, 'class="toc"', "</nav>"))
    return [text for _, text in parser.links]


def head_links(page_html: str) -> list[dict]:
    parser = Tags()
    parser.feed(page_html[:page_html.find("</head>")])
    return [attrs for tag, attrs in parser.tags if tag == "link"]


def meta_description(page_html: str) -> str:
    parser = Tags()
    parser.feed(page_html)
    return next((attrs.get("content", "") for tag, attrs in parser.tags if tag == "meta" and attrs.get("name") == "description"), "")


def decode_png(data: bytes) -> tuple[int, int, bool, bool]:
    """(width, height, every chunk CRC valid, the inflated pixel data has the size the header promises)."""
    assert data[:8] == PNG_SIGNATURE, "not a PNG"
    position, idat, crc_ok = 8, b"", True
    width = height = depth = kind = 0
    while position < len(data):
        length, name = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        (crc,) = struct.unpack(">I", data[position + 8 + length:position + 12 + length])
        crc_ok = crc_ok and (zlib.crc32(name + body) & 0xFFFFFFFF) == crc
        if name == b"IHDR":
            width, height, depth, kind = struct.unpack(">IIBB", body[:10])
        elif name == b"IDAT":
            idat += body
        elif name == b"IEND":
            break
        position += 12 + length
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[kind]
    row = (width * channels * depth + 7) // 8
    return width, height, crc_ok, len(zlib.decompress(idat)) == height * (row + 1)


def read_ico(data: bytes) -> list[tuple[int, int, bytes]]:
    """(width, height, image data) of each entry of an ICO file; a size byte of 0 means 256."""
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1), "not an ICO header"
    entries = []
    for number in range(count):
        width, height, _, _, _, _, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * number:22 + 16 * number])
        assert offset + size <= len(data), "an entry points past the end of the file"
        entries.append((width or 256, height or 256, data[offset:offset + size]))
    return entries


def sentences(text: str) -> int:
    flat = text.strip()
    for mark in ("! ", "? "):
        flat = flat.replace(mark, ". ")
    return flat.count(". ") + 1


def strip_tags(markup: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", markup).split())


class Sidebar(unittest.TestCase):
    """T1: DS-2, the four groups, nested, each page once, the current page marked and its group open."""

    PAGES = [HOME, page("gamma", "Reference", "Gamma"), page("alpha", "Guides", "Alpha"),
             page("beta", "Guides", "Beta", subgroup="Setup"), page("delta", "Reference", "Delta", subgroup="Semantics"),
             page("epsilon", "Reference", "Epsilon", subgroup="Semantics")]

    def test_T1_groups_follow_the_fixed_order_and_empty_groups_are_left_out(self):
        pages = built(site(self.PAGES))
        labels = [group_of(path) for path, _, _, _ in sidebar(pages["alpha"]).links]
        self.assertEqual(list(dict.fromkeys(labels)), ["Guides", "Reference"])
        for absent in ("Concepts", "Configuration"):
            self.assertNotIn(absent, pages["alpha"])

    def test_T1_all_four_groups_appear_in_the_fixed_order_whatever_the_config_order(self):
        every = [HOME, page("d", "Reference"), page("c", "Configuration"), page("b", "Guides"), page("a", "Concepts")]
        labels = [group_of(path) for path, _, _, _ in sidebar(built(site(every))["a"]).links]
        self.assertEqual(labels, ["Concepts", "Guides", "Configuration", "Reference"])

    def test_T1_each_page_is_listed_once_and_the_home_page_is_not_listed(self):
        order = sidebar_order(built(site(self.PAGES))["alpha"])
        self.assertEqual(sorted(order), ["alpha.html", BETA_HTML, "delta.html", "epsilon.html", "gamma.html"])
        self.assertNotIn("index.html", order)

    def test_T1_a_subgroup_nests_its_pages_one_level_under_the_group(self):
        paths = {href: path for path, href, _, _ in sidebar(built(site(self.PAGES))["alpha"]).links}
        self.assertEqual(paths["alpha.html"], ("Guides",))
        self.assertEqual(paths[BETA_HTML], ("Guides", "Setup"))
        self.assertEqual(paths["delta.html"], ("Reference", "Semantics"))
        self.assertEqual(paths["epsilon.html"], ("Reference", "Semantics"))
        self.assertEqual(paths["gamma.html"], ("Reference",))

    def test_T1_the_current_page_is_marked_and_its_group_and_subgroup_are_open(self):
        pages = built(site(self.PAGES))
        side = sidebar(pages["beta"])
        current = [href for _, href, _, is_current in side.links if is_current]
        self.assertEqual(current, [BETA_HTML])
        self.assertTrue(side.open.get(("Guides",)))
        self.assertTrue(side.open.get(("Guides", "Setup")))
        self.assertFalse(side.open.get(("Reference",), False))
        self.assertIn(("Reference",), side.open)
        self.assertFalse(side.open.get(("Reference", "Semantics"), False))
        self.assertIn(("Reference", "Semantics"), side.open)

    def test_T1_the_home_page_may_have_no_group(self):
        pages = built(site([page("index", None, "Home"), page("a", "Guides")]))
        self.assertEqual(sidebar_order(pages["a"]), ["a.html"])

    def test_T1_the_home_page_marks_nothing_current(self):
        side = sidebar(built(site(self.PAGES))["index"])
        self.assertEqual([href for _, href, _, is_current in side.links if is_current], [])

    def test_T1_a_subgroup_that_is_not_a_string_is_refused_naming_the_page(self):
        pages = [HOME, page("alpha", "Guides", "Alpha", subgroup=5)]
        errors, _ = outcome(site(pages))
        self.assertTrue(any("alpha" in message for message in errors), errors)

    def test_T1_every_page_needs_a_description_naming_the_page_when_it_is_missing(self):
        for bad in ("missing", "", "   ", 7):
            with self.subTest(description=bad):
                broken = page("alpha", "Guides", "Alpha")
                if bad == "missing":
                    del broken["description"]
                else:
                    broken["description"] = bad
                errors, _ = outcome(site([HOME, broken]))
                self.assertTrue(any("alpha" in message and "description" in message for message in errors), errors)


class PreviousNext(unittest.TestCase):
    """T2: DS-8."""

    PAGES = [HOME, page("a", "Guides"), page("b", "Guides", subgroup="Setup"), page("c", "Reference")]

    def test_T2_the_first_page_has_no_previous_the_last_no_next_the_others_both_in_sidebar_order(self):
        pages = built(site(self.PAGES))
        order = [href[:-5] for href in sidebar_order(pages["a"])]
        self.assertEqual(order, ["a", "b", "c"])
        for position, slug in enumerate(order):
            with self.subTest(page=slug):
                self.assertEqual(pages[slug].count(PREV_NEXT), 1)
                found = prev_next(pages[slug])
                self.assertEqual(found.get("prev"), f"{order[position - 1]}.html" if position else None)
                self.assertEqual(found.get("next"), f"{order[position + 1]}.html" if position + 1 < len(order) else None)

    def test_T2_the_home_page_has_no_previous_and_next_block(self):
        self.assertNotIn(PREV_NEXT, built(site(self.PAGES))["index"])

    def test_T2_the_block_ends_the_page_content(self):
        page_html = built(site(self.PAGES))["b"]
        self.assertGreater(page_html.find(PREV_NEXT), page_html.find("Text of b."))

    def test_T2_split_pages_follow_the_index_page_in_the_flat_order(self):
        pages = built(split_site())
        order = [href[:-5] for href in sidebar_order(pages["semantics"])]
        self.assertEqual(order, ["semantics", "case-rules", "null-rules", "aggregation-rules"])
        self.assertEqual(prev_next(pages["case-rules"]), {"prev": "semantics.html", "next": "null-rules.html"})
        self.assertIsNone(prev_next(pages["semantics"]).get("prev"))
        self.assertIsNone(prev_next(pages["aggregation-rules"]).get("next"))


class SemanticsSplit(unittest.TestCase):
    """T3 and T4: DS-10."""

    def test_T3_each_section_becomes_a_page_slugged_from_its_plain_title(self):
        pages = built(split_site())
        for key, slug in SPLIT_SLUGS.items():
            with self.subTest(section=key):
                self.assertIn(slug, pages)
                self.assertEqual(slug, bs.slugify(SUMMARIES[key]["title"]))
        self.assertIn("semantics", pages)

    def test_T3_the_heading_line_is_replaced_by_the_plain_title_as_the_h1(self):
        pages = built(split_site())
        for key, slug in SPLIT_SLUGS.items():
            with self.subTest(section=key):
                title = SUMMARIES[key]["title"]
                h1 = element_inner(pages[slug], "h1")
                self.assertEqual(strip_tags(h1), title)
                self.assertNotIn("Case sensitivity", pages[slug].replace("Case rules", ""))
                self.assertNotRegex(strip_tags(h1), CODED)

    def test_T3_the_summary_is_the_lead_paragraph_and_the_description_is_the_meta_description(self):
        pages = built(split_site())
        for key, slug in SPLIT_SLUGS.items():
            with self.subTest(section=key):
                body_marker = {"SEM-1": "Body one.", "SEM-2": "Body two.", AGGREGATION_SEMANTICS: "Body three."}[key]
                self.assertLess(pages[slug].index(SUMMARIES[key]["summary"]), pages[slug].index(body_marker))
                self.assertEqual(meta_description(pages[slug]), SUMMARIES[key]["description"])

    def test_T3_the_rules_of_a_section_keep_their_anchors(self):
        pages = built(split_site())
        self.assertIn('id="sem-1"', pages["case-rules"])
        self.assertIn('id="agg-1"', pages["aggregation-rules"])

    def test_T3_the_index_page_lists_every_split_page_with_its_summary(self):
        pages = built(split_site())
        for key, slug in SPLIT_SLUGS.items():
            with self.subTest(section=key):
                self.assertIn(f'href="{slug}.html"', pages["semantics"])
                self.assertIn(SUMMARIES[key]["summary"], pages["semantics"])
        self.assertEqual(meta_description(pages["semantics"]), THE_RULES_BEHIND_THE_OUTPUT)

    def test_T3_the_sidebar_lists_the_split_pages_in_the_semantics_subgroup_of_reference(self):
        side = sidebar(built(split_site())["semantics"])
        paths = {href: path for path, href, _, _ in side.links}
        self.assertEqual(paths["semantics.html"], ("Reference",))
        for slug in SPLIT_SLUGS.values():
            self.assertEqual(paths[f"{slug}.html"], ("Reference", "Semantics"))
        labels = [label for _, _, label, _ in side.links]
        self.assertEqual([label for label in labels if CODED.search(label)], [])

    def test_T4_a_section_without_an_entry_fails_the_build_naming_its_heading(self):
        for missing in SUMMARIES:
            with self.subTest(missing=missing):
                entries = {key: value for key, value in SUMMARIES.items() if key != missing}
                errors, _ = outcome(split_site(entries))
                self.assertTrue(any(missing in message for message in errors), errors)

    def test_T4_an_entry_without_a_summary_fails_the_build_naming_the_page(self):
        for field_name in ("summary", "description", "title"):
            for blank in ("", "  ", None):
                with self.subTest(field=field_name, value=blank):
                    entries = json.loads(json.dumps(SUMMARIES))
                    if blank is None:
                        del entries["SEM-2"][field_name]
                    else:
                        entries["SEM-2"][field_name] = blank
                    errors, _ = outcome(split_site(entries))
                    self.assertTrue(any("SEM-2" in message or "Null" in message for message in errors), errors)


class LinkRemap(unittest.TestCase):
    """T5: a link to the former single semantics page resolves to the split page that holds the anchor."""

    def test_T5_links_with_a_rule_anchor_go_to_the_split_page_that_holds_it(self):
        index = ("# Home\n\n[a](semantics.html#sem-1) [b](semantics.html#agg-1) [c](semantics.md#agg-1) [d](semantics.html#sem-2)\n"
                 "\n[plain](semantics.html)\n")
        pages = built(split_site(index_source=index))
        for href in ("case-rules.html#sem-1", "aggregation-rules.html#agg-1", "null-rules.html#sem-2"):
            self.assertIn(f'href="{href}"', pages["index"])
        self.assertEqual(pages["index"].count('href="aggregation-rules.html#agg-1"'), 2)
        self.assertIn('href="semantics.html"', pages["index"])
        self.assertNotIn('href="semantics.html#', pages["index"])

    def test_T5_a_dead_anchor_still_fails_naming_the_page_and_the_anchor(self):
        for link in ("semantics.html#nope", "semantics.md#nope"):
            with self.subTest(link=link):
                errors, _ = outcome(split_site(index_source=f"# Home\n\n[x]({link})\n"))
                self.assertTrue(any(INDEX_MD in message and "nope" in message for message in errors), errors)


class Footer(unittest.TestCase):
    """T6: DS-16."""

    def test_T6_the_template_receives_the_text_of_spec_version(self):
        pages = built(site([HOME, page("a", "Guides")]))
        for slug in ("index", "a"):
            self.assertIn("<footer>spec 7.8.9</footer>", pages[slug])


class Favicon(unittest.TestCase):
    """T6: DS-18."""

    @classmethod
    def setUpClass(cls):
        cls.root = site([HOME, page("a", "Guides")])
        cls.errors, cls.out = outcome(cls.root)

    def test_T6_the_build_writes_a_svg_a_32_pixel_ico_and_a_180_pixel_touch_icon(self):
        self.assertEqual(self.errors, [])
        for name in (FAVICON_SVG, FAVICON_ICO, APPLE_TOUCH_ICON_PNG):
            self.assertTrue((self.out / name).is_file(), f"{name} is not written")
        svg = (self.out / FAVICON_SVG).read_text(encoding="utf-8")
        self.assertTrue(svg.lstrip().startswith("<svg"))
        icon = (self.out / APPLE_TOUCH_ICON_PNG).read_bytes()
        self.assertEqual(decode_png(icon), (180, 180, True, True))
        entries = read_ico((self.out / FAVICON_ICO).read_bytes())
        self.assertEqual([(w, h) for w, h, _ in entries], [(32, 32)])
        data = entries[0][2]
        if data[:8] == PNG_SIGNATURE:
            self.assertEqual(decode_png(data), (32, 32, True, True))
        else:
            width, double_height = struct.unpack("<ii", data[4:12])
            self.assertEqual((width, double_height), (32, 64))

    def test_T6_every_page_links_the_svg_and_the_touch_icon_in_its_head(self):
        pages = {f.stem: f.read_text(encoding="utf-8") for f in self.out.glob(HTML_GLOB)}
        self.assertEqual(sorted(pages), ["a", "index"])
        for slug, text in pages.items():
            with self.subTest(page=slug):
                links = head_links(text)
                svg = [tag for tag in links if tag.get("rel") == "icon" and tag.get("href") == FAVICON_SVG]
                touch = [tag for tag in links if tag.get("rel") == "apple-touch-icon" and tag.get("href") == APPLE_TOUCH_ICON_PNG]
                self.assertEqual(len(svg), 1)
                self.assertEqual(svg[0].get("type"), "image/svg+xml")
                self.assertEqual(len(touch), 1)

    def assert_file_names_no_other_host(self, file: Path, text: str):
        if file.suffix == ".svg":
            self.assertNotIn("http", re.sub(XMLNS_ATTRIBUTE, "", text), file.name)
        if file.suffix == ".css":
            self.assertNotIn("@import", text)
            self.assertNotIn("url(http", text)

    def assert_tags_name_no_other_host(self, file: Path, text: str):
        tags = Tags()
        tags.feed(re.sub(XMLNS_ATTRIBUTE, "", text) if file.suffix == ".svg" else text)
        for tag, attrs in tags.tags:
            if tag == "a":
                continue
            for name in ("src", "srcset", "poster", "data", "href"):
                self.assertNotRegex(attrs.get(name, ""), r"(?i)^\s*(?:[a-z][a-z0-9+.-]*:|//)", f"{file.name}: <{tag} {name}>")

    def test_T10_nothing_built_loads_from_another_host(self):
        self.assertTrue((self.out / FAVICON_SVG).is_file(), "favicon.svg is not written")
        files = [f for f in sorted(self.out.rglob("*")) if f.is_file() and f.suffix in (".html", ".css", ".svg")]
        for file in files:
            text = file.read_text(encoding="utf-8")
            self.assert_file_names_no_other_host(file, text)
            self.assert_tags_name_no_other_host(file, text)


class Refusals(unittest.TestCase):
    """T7 to T9: DS-9, DS-19, DS-21, DS-22 and DS-24, each planted in a scratch copy of the site sources."""

    def with_index(self, entry: dict, files: dict[str, str]) -> list[str]:
        return outcome(site([HOME, entry], files))[0]

    def test_T7_a_level_2_heading_over_60_characters_fails_naming_the_page(self):
        errors = self.with_index(page("longhead", "Guides"), {"longhead.md": f"# Long\n\n## {'w' * 61}\n"})
        self.assertTrue(any("longhead" in message for message in errors), errors)

    def test_T7_a_level_2_heading_of_60_characters_builds_and_is_shown_in_full(self):
        label = "w" * 60
        pages = built(site([HOME, page("longhead", "Guides")], {"longhead.md": f"# Long\n\n## {label}\n"}))
        self.assertEqual(toc_labels(pages["longhead"]), [label])

    def test_T7_a_deeper_heading_over_60_characters_is_not_a_toc_label(self):
        self.assertEqual(self.with_index(page("deep", "Guides"), {"deep.md": f"# Deep\n\n### {'w' * 80}\n"}), [])

    def test_T7_an_authored_page_without_a_review_date_fails_naming_the_page(self):
        for extra in ({"authored": True}, {"authored": True, "reviewed": ""}, {"authored": True, "reviewed": "yesterday"}):
            with self.subTest(extra=extra):
                errors = self.with_index(page("written", "Guides", **extra), {})
                self.assertTrue(any("written" in message for message in errors), errors)

    def test_T7_an_authored_page_with_a_review_date_and_a_plain_page_build(self):
        self.assertEqual(self.with_index(page("written", "Guides", authored=True, reviewed="2026-11-03"), {}), [])
        self.assertEqual(self.with_index(page("plain", "Guides"), {}), [])

    def test_T8_a_script_an_event_handler_or_a_javascript_link_fails_naming_the_file(self):
        bad_sources = ("<script>alert(1)</script>", "<SCRIPT src=x></SCRIPT>", "<img src=x onerror=alert(1)>", '<a href="x" onclick = "y">z</a>',
                       "[x](javascript:alert(1))", "[x](JaVaScRiPt:alert(1))")
        for source in bad_sources:
            with self.subTest(source=source):
                errors = self.with_index(page("bad", "Guides"), {BAD_MD: f"# Bad\n\n{source}\n"})
                self.assertTrue(any(BAD_MD in message for message in errors), errors)

    def test_T8_prose_that_names_a_handler_without_using_one_builds(self):
        self.assertEqual(self.with_index(page("prose", "Guides"), {"prose.md": "# Prose\n\nThe error handler runs when a request fails.\n"}), [])

    def test_T8_a_page_source_under_a_private_path_fails_naming_the_file(self):
        for private in ("docs/x.md", ".claude/rules/x.md", "jenkins/y.md", "Jenkinsfile"):
            with self.subTest(source=private):
                entry = page("secret", "Guides", source=private)
                errors = outcome(site([HOME, entry], {private: "# Secret\n"}))[0]
                self.assertTrue(any(private in message for message in errors), errors)

    def test_T9_a_coded_reference_fails_in_a_title_a_description_and_a_toc_label(self):
        cases = {
            "title rule id": (page("coded", "Guides", "Rules SEM-6"), {}),
            "title ticket": (page("coded", "Guides", "Ticket #1638"), {}),
            "title schema code": (page("coded", "Guides", "Check SC-1"), {}),
            "description rule id": (page("coded", "Guides", description="Explains the SEM-6 paging."), {}),
            "description ticket": (page("coded", "Guides", description="Tracked in #1638."), {}),
            "toc label": (page("coded", "Guides"), {"coded.md": "# Coded\n\n## About SEM-6\n"}),
        }
        for name, (entry, files) in cases.items():
            with self.subTest(case=name):
                errors = self.with_index(entry, files)
                self.assertTrue(any("coded" in message for message in errors), errors)

    def test_T9_a_coded_reference_fails_in_a_split_title_and_a_split_summary(self):
        for field_name, value in (("title", "SEM-6 paging"), ("summary", "Follows AR-12. Second."), ("description", "See #1638 for more.")):
            with self.subTest(field=field_name):
                entries = json.loads(json.dumps(SUMMARIES))
                entries["SEM-2"][field_name] = value
                errors, _ = outcome(split_site(entries))
                self.assertTrue(any(value.split()[0] in message or "SEM-2" in message or "Null" in message for message in errors), errors)

    def test_T9_ids_stay_allowed_in_the_rendered_body_and_two_digit_numbers_are_not_tickets(self):
        body = "# Body\n\nThe rule SEM-6 and ticket #1638 are named in the body; issue #12 too.\n"
        errors = self.with_index(page("body", "Guides", description="Issue #12 is fine."), {"body.md": body})
        self.assertEqual(errors, [])


REVIEW_SOURCE = ("# Semantics\n\nPreface paragraph here.\n\n"
                 "## SEM-6. Deterministic paging\n\nBody six.\n\n### Examples\n\nex one.\n\n"
                 "## SEM-1. Case sensitivity\n\nBody one.\n\n### Examples\n\nex two.\n\n"
                 "## SEM-2. Null handling\n\n### Case sensitivity\n\nnested.\n")
REVIEW_SUMMARIES = {
    "SEM-6": {"title": "Deterministic paging", "description": "How paging stays stable.", "summary": "Pages never overlap."},
    "SEM-1": {"title": "Case sensitivity", "description": "How text compares.", "summary": "Text compares without case."},
    "SEM-2": {"title": "Null handling", "description": "How nulls behave.", "summary": "A null matches nothing."},
}


def review_site(source: str = REVIEW_SOURCE, summaries: dict | None = None, index_source: str = "# Home\n", extra_pages: list[dict] | None = None,
                files: dict[str, str] | None = None) -> Path:
    """A split site whose semantics source sits at spec/semantics.md, like the real one."""
    generated = {**split_page(), "source": "spec/semantics.md"}
    return site([HOME, generated, *(extra_pages or [])],
                {"spec/semantics.md": source, SITE_SUMMARIES_JSON: json.dumps(REVIEW_SUMMARIES if summaries is None else summaries),
                 INDEX_MD: index_source, **(files or {})})


def link_targets(page_html: str) -> dict[str, str]:
    parser = Anchors()
    parser.feed(page_html)
    return {text: attrs.get("href", "") for attrs, text in parser.links}


class SplitLinkAnchors(unittest.TestCase):
    """Review finding A: a link by an anchor of the ORIGINAL file goes to the split page that holds that heading."""

    FORMS = {"root": "spec/semantics.md#{}", "html": "semantics.html#{}"}

    def lands(self, anchor: str) -> tuple[list[str], dict[str, str], dict[str, str]]:
        """Build a site whose pages link `anchor` in each form; (errors, link text -> href, built pages)."""
        rows = [f"[{form}:{anchor}]({pattern.format(anchor)})" for form, pattern in self.FORMS.items()]
        guide = page("guide", "Guides", source="a/b/guide.md")
        root = review_site(index_source="# Home\n\n" + "\n\n".join(rows) + "\n", extra_pages=[guide],
                           files={"a/b/guide.md": f"# Guide\n\n[nested:{anchor}](../../spec/semantics.md#{anchor})\n"})
        errors, out = outcome(root)
        pages = {f.stem: f.read_text(encoding="utf-8") for f in out.glob(HTML_GLOB)}
        return errors, {**link_targets(pages.get("index", "")), **link_targets(pages.get("guide", ""))}, pages

    def assert_lands_on(self, anchor: str, slug: str, exact: str | None = None):
        errors, targets, pages = self.lands(anchor)
        self.assertEqual(errors, [])
        for form in (*self.FORMS, "nested"):
            with self.subTest(link=f"{form}:{anchor}"):
                href = targets.get(f"{form}:{anchor}", "")
                page_part, _, fragment = href.partition("#")
                self.assertEqual(page_part, f"{slug}.html")
                if exact is not None:
                    self.assertEqual(href, exact)
                if fragment:  # never a dead fragment
                    self.assertIn(f'id="{fragment}"', pages[slug])

    def test_A_a_heading_that_became_the_h1_links_to_its_page_without_a_fragment(self):
        self.assert_lands_on("sem-6-deterministic-paging", "deterministic-paging", exact="deterministic-paging.html")

    def test_A_a_heading_that_keeps_its_id_links_with_the_fragment(self):
        self.assert_lands_on("examples", "deterministic-paging", exact="deterministic-paging.html#examples")

    def test_A_a_suffixed_duplicate_anchor_goes_to_its_own_section_and_never_fails_the_build(self):
        self.assert_lands_on("examples-1", "case-sensitivity")

    def test_A_an_anchor_that_the_h1_of_another_page_would_shadow_goes_to_the_section_that_holds_it(self):
        self.assert_lands_on("case-sensitivity", "null-handling")

    def test_A_rule_anchors_keep_their_fragment_on_their_page(self):
        self.assert_lands_on("sem-1", "case-sensitivity", exact="case-sensitivity.html#sem-1")
        self.assert_lands_on("sem-2", "null-handling", exact="null-handling.html#sem-2")


class SplitFences(unittest.TestCase):
    """Review finding B: a section is not cut inside a fence, with the converter's close rule (same character, length >= opener)."""

    def test_B_a_four_backtick_fence_holding_three_backticks_and_a_heading_line_does_not_cut_a_section(self):
        source = ("# Semantics\n\n## SEM-1. Case sensitivity\n\n````md\n```\n## Not a heading\n````\n\nBody after the fence.\n\n"
                  "## SEM-2. Null handling\n\nBody two.\n")
        pages = built(review_site(source, {key: REVIEW_SUMMARIES[key] for key in ("SEM-1", "SEM-2")}))
        self.assertIn("Body after the fence.", pages["case-sensitivity"])
        self.assertIn("## Not a heading", pages["case-sensitivity"])
        self.assertEqual(sorted(slug for slug in pages if slug not in ("index", "semantics")), ["case-sensitivity", "null-handling"])

    def test_B_a_tilde_fence_is_not_closed_by_a_backtick_line(self):
        source = ("# Semantics\n\n## SEM-1. Case sensitivity\n\n~~~\n```\n## Not a heading\n~~~\n\nBody after the fence.\n")
        pages = built(review_site(source, {"SEM-1": REVIEW_SUMMARIES["SEM-1"]}))
        self.assertIn("Body after the fence.", pages["case-sensitivity"])


class SplitPreface(unittest.TestCase):
    """Review finding C: the text before the first `## ` shows on the index page."""

    def test_C_the_preface_follows_the_description_and_comes_before_the_part_list(self):
        main = fragment(built(review_site())["semantics"], "<main", "</main>")
        description, preface, first_part = main.find(THE_RULES_BEHIND_THE_OUTPUT), main.find("Preface paragraph here."), main.find('href="deterministic-paging.html"')
        self.assertGreaterEqual(description, 0)
        self.assertGreater(preface, description)
        self.assertGreater(first_part, preface)


class UnsafeMarkupEverywhere(unittest.TestCase):
    """Review finding D: DS-21 also catches a handler glued to a slash or a quote, in every source the build reads."""

    BAD = ("<svg/onload=alert(1)>", '<a href="x"onclick=1>y</a>')

    def test_D_a_page_source_with_a_glued_handler_fails_naming_the_file(self):
        for markup in self.BAD:
            with self.subTest(markup=markup):
                errors = outcome(site([HOME, page("bad", "Guides")], {BAD_MD: f"# Bad\n\n{markup}\n"}))[0]
                self.assertTrue(any(BAD_MD in message for message in errors), errors)

    def test_D_the_semantics_source_with_a_glued_handler_fails_naming_the_file(self):
        for markup in self.BAD:
            with self.subTest(markup=markup):
                errors = outcome(review_site(REVIEW_SOURCE + f"\n{markup}\n"))[0]
                self.assertTrue(any(SEMANTICS_MD in message for message in errors), errors)

    def test_D_a_summaries_value_with_markup_fails_naming_the_file(self):
        for markup in self.BAD:
            with self.subTest(markup=markup):
                entries = json.loads(json.dumps(REVIEW_SUMMARIES))
                entries["SEM-2"]["summary"] = f"Safe words. {markup}"
                errors = outcome(review_site(summaries=entries))[0]
                self.assertTrue(any("summaries.json" in message for message in errors), errors)


class ConfigRefusals(unittest.TestCase):
    """Review finding E: a bad site.json is a configuration error (BuildError, exit 2)."""

    def refused(self, pages: list[dict]):
        with self.assertRaises(bs.BuildError):
            bs.build(site(pages), Path(tempfile.mkdtemp()))

    def test_E_authored_must_be_a_boolean(self):
        for bad in ("yes", "true", 1):
            with self.subTest(authored=bad):
                self.refused([HOME, page("alpha", "Guides", authored=bad, reviewed="2026-11-03")])

    def test_E_reviewed_must_be_a_real_calendar_date(self):
        for bad in ("2026-99-99", "2026-02-30", "2026-13-01"):
            with self.subTest(reviewed=bad):
                self.refused([HOME, page("alpha", "Guides", authored=True, reviewed=bad)])

    def test_E_a_subgroup_holding_a_coded_reference_is_refused(self):
        self.refused([HOME, page("alpha", "Guides", subgroup="SEM-1 rules")])

    def test_E_site_json_must_be_an_object(self):
        for text in ("[]", "5", "null", '"text"'):
            with self.subTest(site_json=text):
                root = site([HOME])
                (root / "site" / "site.json").write_text(text, encoding="utf-8")
                with self.assertRaises(bs.BuildError):
                    bs.build(root, root / "_out")


class RealSite(unittest.TestCase):
    """The acceptance tests on this repository's own sources (T1 to T10 of the real build)."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        cls.errors = bs.build(ROOT, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob(HTML_GLOB)}
        cls.config = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))

    def split_links(self) -> list[tuple[tuple[str, ...], str, str, bool]]:
        return [link for link in sidebar(self.pages["semantics"]).links if link[0] == ("Reference", "Semantics")]

    def test_the_real_sources_build_without_errors(self):
        self.assertEqual(self.errors, [])

    def test_T3_semantics_is_split_into_16_pages_with_plain_titles(self):
        sections = [line for line in (ROOT / "spec" / SEMANTICS_MD).read_text(encoding="utf-8").splitlines() if line.startswith("## ")]
        self.assertEqual(len(sections), 16)
        links = self.split_links()
        self.assertEqual(len(links), 16)
        for _, href, label, _ in links:
            with self.subTest(page=href):
                self.assertRegex(href, bs.SLUG.pattern[:-1] + r"\.html$")
                self.assertNotRegex(label, CODED)
                self.assertNotIn(label, sections)
                h1 = element_inner(self.pages[href[:-5]], "h1")
                self.assertEqual(strip_tags(h1), label)
                self.assertIn(f'href="{href}"', self.pages["semantics"])

    def test_T3_each_split_page_leads_with_a_summary_of_at_most_three_sentences(self):
        links = self.split_links()
        self.assertEqual(len(links), 16)
        for _, href, _, _ in links:
            with self.subTest(page=href):
                text = self.pages[href[:-5]]
                lead = element_inner(text[text.index("</h1>"):], "p")
                plain = strip_tags(lead)
                self.assertTrue(plain)
                self.assertLessEqual(sentences(plain), 3)
                self.assertEqual(sentences(meta_description(text)), 1)

    def test_T3_the_rule_index_page_is_gone_and_every_rule_anchor_is_reachable(self):
        self.assertNotIn("rules", self.pages)
        definitions = bs.rule_definitions((ROOT / "spec" / SEMANTICS_MD).read_text(encoding="utf-8"))
        everything = "".join(self.pages.values())
        self.assertEqual([rule for rule in definitions if f'id="{bs.rule_anchor(rule)}"' not in everything], [])

    def test_T1_site_json_has_a_description_for_every_page_and_only_the_four_groups(self):
        for entry in self.config["pages"]:
            with self.subTest(page=entry["slug"]):
                self.assertTrue(isinstance(entry.get("description"), str) and entry["description"].strip())
                if entry["slug"] == "index":
                    self.assertIn(entry.get("group"), (None, *bs.GROUPS))
                else:
                    self.assertIn(entry.get("group"), bs.GROUPS)

    def test_T1_the_sidebar_has_the_groups_in_order_lists_each_page_once_and_not_the_home_page(self):
        for slug, text in self.pages.items():
            if slug == "index":
                continue  # the home page is the landing layout with no side column (DS-2); its design is task #3557
            with self.subTest(page=slug):
                links = sidebar(text).links
                groups = list(dict.fromkeys(group_of(path) for path, _, _, _ in links))
                self.assertEqual(groups, [name for name in bs.GROUPS if name in groups])
                hrefs = [href for _, href, _, _ in links]
                self.assertEqual(len(hrefs), len(set(hrefs)))
                self.assertEqual(sorted(hrefs), sorted(f"{other}.html" for other in self.pages if other != "index"))
                self.assertEqual([is_current for _, href, _, is_current in links if href == f"{slug}.html"], [True])

    def test_T2_every_docs_page_ends_with_previous_and_next_in_sidebar_order(self):
        order = [href[:-5] for href in sidebar_order(self.pages["overview"])]
        self.assertNotIn(PREV_NEXT, self.pages["index"])
        self.assertEqual(len(order), len(self.pages) - 1)
        for position, slug in enumerate(order):
            with self.subTest(page=slug):
                found = prev_next(self.pages[slug])
                self.assertEqual(found.get("prev"), f"{order[position - 1]}.html" if position else None)
                self.assertEqual(found.get("next"), f"{order[position + 1]}.html" if position + 1 < len(order) else None)

    def test_T9_no_label_is_over_60_characters_and_none_holds_a_coded_reference(self):
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                labels = [label for _, _, label, _ in sidebar(text).links] + toc_labels(text)
                for label in labels:
                    self.assertLessEqual(len(label), 60, label)
                    self.assertNotRegex(label, CODED)
                    self.assertNotRegex(label, TICKET)
                description = meta_description(text)
                self.assertTrue(description)
                self.assertNotRegex(description, CODED)
                self.assertNotRegex(description, TICKET)

    def test_T6_the_footer_holds_the_licence_the_repository_and_the_spec_version_only(self):
        version = (ROOT / "spec" / "VERSION").read_text(encoding="utf-8").strip()
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                foot = fragment(text, "<footer", "</footer>")
                self.assertTrue(foot)
                plain = strip_tags(foot)
                self.assertIn("Apache-2.0", plain)
                self.assertIn(f"spec {version}", plain)
                self.assertIn(self.config["repo"].split("//", 1)[1], plain + " ".join(attrs.get("href", "") for attrs, _ in _links(foot)))
                self.assertLessEqual(len(plain), 90)
                self.assertNotIn("drift", plain)

    def test_T6_the_favicon_files_decode_and_every_page_links_them(self):
        for name in (FAVICON_SVG, FAVICON_ICO, APPLE_TOUCH_ICON_PNG):
            self.assertTrue((self.out / name).is_file(), f"{name} is not written")
        self.assertEqual(decode_png((self.out / APPLE_TOUCH_ICON_PNG).read_bytes()), (180, 180, True, True))
        self.assertEqual([(w, h) for w, h, _ in read_ico((self.out / FAVICON_ICO).read_bytes())], [(32, 32)])
        self.assertTrue((self.out / FAVICON_SVG).read_text(encoding="utf-8").lstrip().startswith("<svg"))
        for slug, text in self.pages.items():
            with self.subTest(page=slug):
                hrefs = [(tag.get("rel"), tag.get("href")) for tag in head_links(text)]
                self.assertIn(("icon", FAVICON_SVG), hrefs)
                self.assertIn(("apple-touch-icon", APPLE_TOUCH_ICON_PNG), hrefs)

    def test_T10_the_favicon_svg_loads_nothing_from_another_host(self):
        self.assertTrue((self.out / FAVICON_SVG).is_file(), "favicon.svg is not written")
        text = re.sub(XMLNS_ATTRIBUTE, "", (self.out / FAVICON_SVG).read_text(encoding="utf-8"))
        self.assertNotIn("http", text)


def _links(markup: str) -> list[tuple[dict, str]]:
    parser = Anchors()
    parser.feed(markup)
    return parser.links


if __name__ == "__main__":
    unittest.main()
