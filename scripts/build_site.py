#!/usr/bin/env python3
"""Build the Craticula docs site from the repository's own Markdown (story #1666, task #2832).

Standard library only, so the build needs no new dependency. The pages are listed in `site/site.json`; each page is a
Markdown file of the repository (a page written for the site under `site/pages/`, or a public document such as `README.md`
or `spec/README.md` that the site renders as it is). The output is a folder of static HTML files.

The build also checks every link of every page, and fails (exit 1) on:
  * a link to a file that does not exist in the repository;
  * a link to a heading anchor that does not exist (in a page of the site, or in another Markdown file of the repository);
  * a link into the private part of the repository (the PRIVATE list of `scripts/publish-github.sh`, which the public mirror
    does not carry, written out below), as a file or as a bare directory;
  * a link that leaves the repository, or uses a scheme other than http, https or mailto;
  * the same for an image (`![alt](path)`), whose relative path is also rewritten to its public address.
A link to an existing repository file that has no page on the site is rewritten to its public GitHub address.
External `http(s)` links are not fetched (the build must work offline).

A page may include a repository file as a code block with a line `{{include <path> <language>}}`: the file is the single source of
the code the page shows (a quickstart program that the solution builds cannot drift from its page). The path must be a public
file inside the repository.

Pages are Markdown files, or generated from a repository file: `"generator": "schema-reference"` renders a JSON Schema as
reference tables, `"generator": "semantics-split"` cuts the rule source (`spec/semantics.md`) into one page per section. A paragraph that opens with a bold rule id (`**GRP-7. ...**`) and a heading that opens with one (`## SEM-1. ...`) get an
anchor of that id (`#grp-7`, `#sem-1`), and the build fails when a page mentions a rule id (of the prefixes in `ruleIdPrefixes`)
that the rule source does not define.

Docs site v2 contract (story #3554, task #3555; spec `docs/spec/docs-site-v2.md`; the behaviour is built by the green step):
  * `site/site.json` page keys: `slug`, `title`, `source`, `group` (one of GROUPS, or absent/null only for the page `index`),
    optional `subgroup` (one nesting level under the group), required `description` (one sentence), optional `authored: true`
    with `reviewed` (an ISO date; an authored page without it fails the build), optional `generator`, `template`.
  * `"generator": "semantics-split"` (keys `source` = spec/semantics.md, `summaries` = site/summaries.json): one index page (the
    page's own slug, group Reference) that lists the split pages with their summaries, then one page per `## ` section of the
    source (SEM-1..SEM-8 and each addendum) in subgroup `Semantics`. A section's key in the summaries file is its rule id
    (`SEM-1`) or, for an addendum, the text after `Addendum — ` up to ` (`; the entry holds `title` (plain name), `description`
    (one sentence) and `summary` (at most three sentences, the lead paragraph). The split page's slug is `slugify(title)`, its h1
    is the plain title (the heading line is replaced) and the anchors of the rules it holds (`#sem-1`, `#grp-7`) stay. A
    section with no entry fails the build and names the heading. The `rules-index` generator is removed.
  * Sidebar: GROUPS in that fixed order, empty ones omitted, subgroups as nested native `<details>` with a `<summary>`, the
    group open when it holds the current page, the current page `aria-current="page"`, the page `index` absent.
  * Template values added: `{{prev_next}}` (a `<nav aria-label="Previous and next">` linking the neighbours in sidebar order,
    empty for `index`; its links carry `rel="prev"` and `rel="next"`), `{{head_links}}` (the favicon SVG and apple-touch-icon `<link>` tags), `{{description}}`, `{{spec_version}}`
    (the text of `spec/VERSION`). The build writes `favicon.svg`, `favicon.ico` (32 x 32) and `apple-touch-icon.png` (180 x 180).
  * The build fails and names the file or page on: a source with `<script`, an event-handler attribute or a `javascript:` link
    (DS-21); a level-2 heading over 60 characters; a missing description, summary or `reviewed`; a coded reference
    (a word boundary, 2 to 5 capitals, a hyphen and digits, or `#` and three digits) in a title, sidebar label, TOC label, description or summary (DS-19).
  * A link to `semantics.html#<anchor>` or to the source file `semantics.md#<anchor>` resolves to the split page that holds the anchor.

    python3 scripts/build_site.py [--out DIR] [--root DIR] [--base-url URL] [--preview-languages fr,de]

Exit codes: 0 built and every link resolves, 1 a link is dead or private, 2 bad usage or an unreadable configuration.
"""
from __future__ import annotations

import argparse
import datetime
import functools
import hashlib
import html
import json
import os
import re
import struct
import urllib.parse
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import site_i18n

# The private paths of scripts/publish-github.sh (its PRIVATE array): what the public mirror does not carry, so a link to one is
# dead there. test_build_site.py pins this tuple to the real array where that script exists (the private repository).
PRIVATE_PATHS = ("docs", ".claude", "CLAUDE.md", ".mcp.json", ".githooks", ".azuredevops", ".sonarlint", ".vscode",
                 "scripts/publish-github.sh", "scripts/sync-release-commit.sh", "scripts/apply-public-change.sh",
                 "scripts/test_apply_public_change.py", "scripts/test_publish_mirror_real.py", "scripts/test_jenkinsfile.py",
                 "scripts/test_release_steps.py", "scripts/test_release_steps_publish.py", "scripts/test_release_steps_notes.py", "scripts/release-steps-fixtures",
                 "csharp/tests/Craticula.Conformance.Tests/JenkinsfileTests.cs", "csharp/tests/Craticula.Conformance.Tests/ReleaseStepsTests.cs", "Jenkinsfile", "jenkins")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)")
ALLOWED_SCHEMES = ("http:", "https:", "mailto:")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CODED_REFERENCE = re.compile(r"\b[A-Z]{2,5}-\d+|#\d{3,}")  # DS-19: a rule id, a requirement id, a schema code or a ticket number
EVENT_HANDLER = re.compile(r"[\s/\"']on[a-z]+\s*=")  # DS-21, inside one tag
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MAX_TOC_LABEL = 60  # DS-9
ADDENDUM = "Addendum — "
SPLIT_SUBGROUP = "Semantics"
LLMS_NAME, LLMS_FULL_NAME = "llms.txt", "llms-full.txt"
I18N_DIR = "site/i18n"
README_SOURCE = "README.md"
LEFT_OUT_BEGIN = "<!-- performance block: begin, written by scripts/perf_page.py; the site leaves it out -->"
LEFT_OUT_END = "<!-- performance block: end -->"
HOME_BLOCK_ID = "measured-performance"


def language_file(code: str, name: str) -> str:
    """The repository path of a file of a language's translation folder."""
    return f"{I18N_DIR}/{code}/{name}"


def left_out_region(text: str, label: str) -> tuple[str, str, list[str]]:
    """The text without the lines from the begin marker to the end marker, the lines between them, and the problems of the pair.
    A marker is a whole line compared after `strip()`; with a problem the text comes back unchanged and the inner text is empty."""
    lines = text.splitlines(keepends=True)
    begins = [number for number, line in enumerate(lines, 1) if line.strip() == LEFT_OUT_BEGIN]
    ends = [number for number, line in enumerate(lines, 1) if line.strip() == LEFT_OUT_END]
    problems = []
    if not begins and not ends:
        problems.append(f"{label}: no begin marker `{LEFT_OUT_BEGIN}`; the performance block needs one pair of markers")
    elif not begins:
        problems.append(f"{label}: line {ends[0]}: the end marker `{LEFT_OUT_END}` has no begin marker `{LEFT_OUT_BEGIN}`")
    if len(begins) > 1:
        problems.append(f"{label}: line {begins[1]}: a second begin marker `{LEFT_OUT_BEGIN}`; the performance block has one pair")
    if len(ends) > 1:
        problems.append(f"{label}: line {ends[1]}: a second end marker `{LEFT_OUT_END}`; the performance block has one pair")
    if begins and ends and ends[0] < begins[0]:
        problems.append(f"{label}: line {ends[0]}: the end marker `{LEFT_OUT_END}` comes before the begin marker")
    elif begins and not ends:
        problems.append(f"{label}: line {begins[0]}: the begin marker `{LEFT_OUT_BEGIN}` has no end marker")
    if problems:
        return text, "", problems
    begin, end = begins[0], ends[0]
    inner = "\n".join(line.rstrip("\r\n") for line in lines[begin:end - 1])
    return "".join(lines[:begin - 1] + lines[end:]), inner, []


GROUP_NAMES, SUBGROUPS = "group_names", "subgroups"  # the tables of the interface text that name the groups and the subgroups


class BuildError(Exception):
    """A configuration problem (exit 2)."""


# ---------------------------------------------------------------- anchors

def slugify(text: str) -> str:
    """GitHub's heading slug: lower case, drop punctuation, spaces to hyphens (so existing `#...` links keep working)."""
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


class Slugger:
    """GitHub's de-duplication: the first `same` is `same`, then `same-1`, `same-2`; a suffix that is already taken (by a
    heading literally called `same 1`) is skipped, so every id on the page is unique."""

    def __init__(self) -> None:
        self.used: set[str] = set()
        self.counts: dict[str, int] = {}

    def declare(self, anchor: str) -> str:
        """A heading's own anchor (`{#anchor}`): it takes the place of the generated one, and no later heading can generate it."""
        if anchor in self.used:
            raise BuildError(f"the anchor '{anchor}' is declared or generated twice on the page")
        self.used.add(anchor)
        return anchor

    def __call__(self, text: str) -> str:
        base = slugify(text)
        candidate = base
        while candidate in self.used:
            n = self.counts.get(base, 0) + 1
            self.counts[base] = n
            candidate = f"{base}-{n}"
        self.used.add(candidate)
        return candidate


# ---------------------------------------------------------------- Markdown

@dataclass
class Rendered:
    html: str
    anchors: set[str] = field(default_factory=set)
    links: list[tuple[int, str]] = field(default_factory=list)  # (source line, href)
    title: str = ""
    headings: list[tuple[int, str, str]] = field(default_factory=list)  # level, text and anchor of each heading, in order; FR-32, task #3474
    undeclared: list[str] = field(default_factory=list)  # with `require_anchors`: the text of each heading that declares no `{#english-anchor}` (spec 004, US2-AS11)


_INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.S)
_LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")


def _inline(text: str, line: int, out: Rendered, resolve, holes: list[str] | None = None) -> str:
    """Inline Markdown to HTML. `resolve(href)` returns the href to emit; links are recorded for the checker.
    A nested call (a link's label) shares the caller's `holes` and returns its text still holding placeholders."""
    nested = holes is not None
    if holes is None:
        holes = []

    def restore(value: str) -> str:
        while "\x00" in value:  # a held link may itself hold a code span
            value = re.sub(r"\x00(\d+)\x00", lambda m: holes[int(m.group(1))], value)
        return value

    def hold(fragment: str) -> str:
        holes.append(fragment)
        return f"\x00{len(holes) - 1}\x00"

    def code(match: re.Match) -> str:
        return hold(f"<code>{html.escape(match.group(2).strip(), quote=False)}</code>")

    text = _INLINE_CODE.sub(code, text)

    def autolink(match: re.Match) -> str:
        url = match.group(1)
        return hold(f'<a href="{html.escape(url)}">{html.escape(url, quote=False)}</a>')

    text = _AUTOLINK.sub(autolink, text)

    def link(match: re.Match) -> str:
        bang, label, href = match.group(1), match.group(2), match.group(3)
        label_html = _inline(label, line, out, resolve, holes)
        if bang:
            out.links.append((line, href))
            href = resolve(href, True)
            if re.match(r"[A-Za-z][A-Za-z0-9+.-]+:|[/\\]{2}", href):  # NFR-13: a browser loads nothing from another host, so a remote image (any scheme or spelling: HTTP:, https:/h, \\h) is its alt text; a one-letter "scheme" is a drive letter, not a fetch
                alt = re.sub(r"<[^>]+>", "", restore(label_html)).strip()
                return hold(f'<span class="img-alt">{alt}</span>' if alt else "")
            return hold(f'<img alt="{html.escape(re.sub(r"<[^>]+>", "", restore(label_html)))}" src="{html.escape(href)}">')
        out.links.append((line, href))
        return hold(f'<a href="{html.escape(resolve(href))}">{label_html}</a>')

    text = _LINK.sub(link, text)
    text = html.escape(text, quote=False)
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    text = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    return text if nested else restore(text)


RULE_ID = r"[A-Z]{2,5}-\d+(?:\([a-z]\)|[a-z])?"


def rule_anchor(rule: str) -> str:
    """`GRP-7` -> `grp-7`, `SQL-7(b)` -> `sql-7b`."""
    return re.sub(r"[()]", "", rule.lower())
_RULE_OPENER = re.compile(rf"^\*\*({RULE_ID})\.\s")
_RULE_HEADING = re.compile(rf"^({RULE_ID})\.\s")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^(\s*)(```+|~~~+)\s*([\w+-]*)")
_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


_DECLARED_ANCHOR = re.compile(r"^(.*?)\s*\{#([\w-]+)\}$")


def _split_declaration(text: str) -> tuple[str, str]:
    """A heading's text without its `{#anchor}` declaration, and the anchor ('' when it declares none)."""
    match = _DECLARED_ANCHOR.match(text)
    return (match.group(1), match.group(2)) if match else (text, "")


_INDENTED = (" ", "\t")


class _BlockParser:
    """One pass over the lines of a document: each block kind has its own method, tried in a fixed order; a line none of them
    takes starts a paragraph. Reads and advances `self.i` (the index of the next line)."""

    def __init__(self, source: str, resolve, require_anchors: bool) -> None:
        self.resolve = resolve
        self.require_anchors = require_anchors
        self.out = Rendered(html="")
        self.slugs = Slugger()
        self.body: list[str] = []
        self.lines = source.replace("\r\n", "\n").split("\n")
        self.i = 0

    def inline(self, text: str, number: int) -> str:
        return _inline(text, number, self.out, self.resolve)

    def parse(self) -> Rendered:
        blocks = (self._fence, self._heading, self._hrule, self._quote, self._table, self._list)
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                self.i += 1
            elif not any(block(line, self.i + 1) for block in blocks):
                self._paragraph(line, self.i + 1)
        self.out.html = "\n".join(self.body)
        return self.out

    def _read_fence(self, opener: re.Match) -> str:
        """The `<pre>` of the fenced block whose opening line is `self.lines[self.i]`; leaves `self.i` after the closing line."""
        marker, language, indent = opener.group(2), opener.group(3), len(opener.group(1))
        closing = re.compile(rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$")
        self.i += 1
        code: list[str] = []
        while self.i < len(self.lines) and not closing.match(self.lines[self.i]):
            text = self.lines[self.i]
            code.append(text[indent:] if text[:indent].strip() == "" else text)
            self.i += 1
        self.i += 1
        cls = f' class="language-{html.escape(language)}"' if language else ""
        return f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>"

    def _fence(self, line: str, number: int) -> bool:
        fence = _FENCE.match(line)
        if fence:
            self.body.append(self._read_fence(fence))
        return bool(fence)

    def _heading(self, line: str, number: int) -> bool:
        heading = _HEADING.match(line)
        if not heading:
            return False
        out = self.out
        level, (text, declared) = len(heading.group(1)), _split_declaration(heading.group(2))
        plain = re.sub(r"[`*]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text))
        anchor = self.slugs.declare(declared) if declared else self.slugs(plain)
        if self.require_anchors and not declared:
            out.undeclared.append(plain)
        out.anchors.add(anchor)
        out.headings.append((level, plain, anchor))
        alias = self._rule_alias(text)
        if level == 1 and not out.title:
            out.title = re.sub(r"[`*]", "", text)
        self.body.append(f'<h{level} id="{anchor}">{alias}{self.inline(text, number)}</h{level}>')
        self.i += 1
        return True

    def _rule_alias(self, text: str) -> str:
        """`## SEM-1. Case sensitivity` is also reachable as `#sem-1`: the empty anchor element that carries it, or ''."""
        rule = _RULE_HEADING.match(text)
        if not rule:
            return ""
        anchor_id = rule_anchor(rule.group(1))
        self.out.anchors.add(anchor_id)
        return f'<a id="{anchor_id}"></a>'

    def _hrule(self, line: str, number: int) -> bool:
        if _RULE.match(line):
            self.body.append("<hr>")
            self.i += 1
            return True
        return False

    def _quote(self, line: str, number: int) -> bool:
        if not line.lstrip().startswith(">"):
            return False
        quote: list[str] = []
        start = self.i
        while self.i < len(self.lines) and self.lines[self.i].lstrip().startswith(">"):
            quote.append(re.sub(r"^\s*>\s?", "", self.lines[self.i]))
            self.i += 1
        inner = render_markdown("\n".join(quote), self.resolve)
        self.out.links.extend((start + n, href) for n, href in inner.links)
        self.out.anchors.update(inner.anchors)
        self.body.append(f"<blockquote>{inner.html}</blockquote>")
        return True

    def _table(self, line: str, number: int) -> bool:
        lines, i = self.lines, self.i
        if not ("|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]):
            return False
        head = _cells(line)
        self.i += 2
        rows: list[tuple[int, list[str]]] = []
        while self.i < len(lines) and lines[self.i].strip() and "|" in lines[self.i]:
            rows.append((self.i + 1, _cells(lines[self.i])))
            self.i += 1
        parts = ["<table><thead><tr>" + "".join(f"<th>{self.inline(c, number)}</th>" for c in head) + "</tr></thead><tbody>"]
        for row_number, cells in rows:
            parts.append("<tr>" + "".join(f"<td>{self.inline(c, row_number)}</td>" for c in cells) + "</tr>")
        parts.append("</tbody></table>")
        self.body.append("".join(parts))
        return True

    def _list(self, line: str, number: int) -> bool:
        if not _LIST.match(line):
            return False
        # (line, indent, ordered, parts): a part is a list of text lines or an HTML string for a fenced block, in source order
        items: list[tuple[int, int, bool, list]] = []
        while self.i < len(self.lines):
            if not self._list_step(items):
                break
        self.body.append(_render_list(items, self.inline))
        return True

    def _list_step(self, items: list) -> bool:
        """Consume the list's next line (an item, a continuation, a nested fenced block, a blank inside it); False when the list ends."""
        text = self.lines[self.i]
        match = _LIST.match(text)
        if match:
            items.append((self.i + 1, len(match.group(1).expandtabs(4)), match.group(2)[0].isdigit(), [[match.group(3)]]))
            self.i += 1
            return True
        if not text.strip():
            return self._list_blank(items)
        if not (items and text.startswith(_INDENTED)):
            return False
        opener = _FENCE.match(text)
        if opener:
            items[-1][3].append(self._read_fence(opener))
            return True
        if isinstance(items[-1][3][-1], str):  # text after a fenced block is a new paragraph of the item
            items[-1][3].append([])
        items[-1][3][-1].append(text.strip())
        self.i += 1
        return True

    def _list_blank(self, items: list) -> bool:
        """A blank line stays inside the list only when an indented list item or fenced block follows it."""
        j = self.i
        while j < len(self.lines) and not self.lines[j].strip():
            j += 1
        if items and j < len(self.lines) and self.lines[j].startswith(("  ", "\t")) and (_FENCE.match(self.lines[j]) or _LIST.match(self.lines[j])):
            self.i = j
            return True
        return False

    def _ends_paragraph(self, index: int) -> bool:
        lines = self.lines
        text = lines[index]
        return bool(
            not text.strip()
            or _HEADING.match(text) or _FENCE.match(text) or _LIST.match(text)
            or text.lstrip().startswith(">") or _RULE.match(text)
            or ("|" in text and index + 1 < len(lines) and _TABLE_SEP.match(lines[index + 1]))
        )

    def _paragraph(self, line: str, number: int) -> None:
        paragraph = [line.strip()]
        self.i += 1
        while self.i < len(self.lines) and not self._ends_paragraph(self.i):
            paragraph.append(self.lines[self.i].strip())
            self.i += 1
        joined = " ".join(paragraph)
        opener = _RULE_OPENER.match(joined)
        attribute = ""
        if opener:  # `**GRP-7. A ...**` opens a rule: give the paragraph the anchor `#grp-7`
            anchor_id = rule_anchor(opener.group(1))
            if anchor_id not in self.out.anchors:
                self.out.anchors.add(anchor_id)
                attribute = f' id="{anchor_id}"'
        self.body.append(f"<p{attribute}>{self.inline(joined, number)}</p>")


def render_markdown(source: str, resolve=lambda href, image=False: href, *, require_anchors: bool = False) -> Rendered:
    """Markdown to HTML for the subset the repository's documents use (headings, paragraphs, lists, tables, fenced code,
    block quotes, rules, inline code, links, emphasis). Raw HTML in the source is escaped, never passed through.
    `## Heading {#anchor}` declares the anchor (US2-AS11); with `require_anchors`, a heading without one goes to `Rendered.undeclared`."""
    source = source.replace("\x00", "\ufffd")  # NUL marks this converter's placeholders
    return _BlockParser(source, resolve, require_anchors).parse()


def _render_list(items, inline) -> str:
    """Nested lists by indentation: an item indented deeper than the previous one opens a child list; a fenced block indented
    under an item stays inside that item."""
    html_parts: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for number, indent, ordered, parts in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            html_parts.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            html_parts.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            html_parts.append("</li>")
        content = []
        for position, part in enumerate(parts):
            if isinstance(part, str):
                content.append(part)
            else:
                text = inline(" ".join(part), number)
                content.append(text if position == 0 else f"<p>{text}</p>")
        html_parts.append(f"<li>{''.join(content)}")
    while stack:
        html_parts.append(f"</li></{stack.pop()[1]}>")
    return "".join(html_parts)


# ---------------------------------------------------------------- site

@dataclass
class Page:
    slug: str
    title: str
    source: str  # repository-relative file the page reads (for a generated page: the file it is generated from)
    generator: str | None = None
    rendered: Rendered | None = None
    group: str | None = None  # FR-32, task #3474
    template: str | None = None  # FR-32, task #3474
    description: str = ""  # #3555, DS-12
    subgroup: str | None = None  # #3555, DS-2: one nesting level under the group
    authored: bool = False  # #3555, DS-24
    reviewed: str | None = None  # #3555, DS-24: ISO date of the review of an authored page
    summary: str = ""  # #3555, DS-10: the lead paragraph of a split semantics page
    alias: str = ""  # #3555: the rule anchor (`sem-1`) a split page keeps next to its title
    scope: str = "translated"  # spec 004-site-languages FR-027: "translated" or "english", read from the page entry of site.json


def _layout(pages: list["Page"]) -> dict[str, list]:
    """DS-2: group -> its entries in order, where an entry is a page or a (subgroup name, pages) pair placed where the
    subgroup's first page appears. A page without a group (the home page) is not part of the sidebar."""
    layout: dict[str, list] = {name: [] for name in GROUPS}
    subgroups: dict[tuple[str, str], list[Page]] = {}
    for page in pages:
        if not page.group or page.slug == "index":
            continue
        if page.subgroup:
            key = (page.group, page.subgroup)
            if key not in subgroups:
                subgroups[key] = []
                layout[page.group].append((page.subgroup, subgroups[key]))
            subgroups[key].append(page)
        else:
            layout[page.group].append(page)
    return layout


def ordered_pages(pages: list["Page"]) -> list["Page"]:
    """The pages in sidebar order: the order of previous and next."""
    flat: list[Page] = []
    for name in GROUPS:
        for entry in _layout(pages)[name]:
            flat.extend(entry[1] if isinstance(entry, tuple) else [entry])
    return flat


def _ui(ui: dict | None) -> dict:
    """The interface text a render function uses: the one it is given, else the English one (spec 004-site-languages, FR-003)."""
    return ui if ui is not None else site_i18n.default_ui()


def _label(ui: dict | None, table: str, name: str) -> str:
    """The shown name of a group or subgroup; the key itself when the interface text has no entry for it."""
    return _ui(ui)[table].get(name, name)


def _side_link(page: "Page", current_slug: str) -> str:
    current = ' aria-current="page"' if page.slug == current_slug else ""
    return f'<li><a href="{html.escape(page.slug)}.html"{current}>{html.escape(page.title)}</a></li>'


def _sidebar_item(entry, current_slug: str, ui: dict | None) -> tuple[str, bool]:
    """The list item of one entry of a group (a page, or a subgroup and its pages) and whether it holds the current page."""
    if not isinstance(entry, tuple):
        return _side_link(entry, current_slug), entry.slug == current_slug
    sub_name, members = entry
    sub_open = any(member.slug == current_slug for member in members)
    open_attribute = " open" if sub_open else ""
    links = "".join(_side_link(member, current_slug) for member in members)
    return (f'<li class="side-sub"><details{open_attribute}><summary>{html.escape(_label(ui, SUBGROUPS, sub_name))}</summary>'
            f'<ul>{links}</ul></details></li>'), sub_open


def render_sidebar(pages: list["Page"], current_slug: str, ui: dict | None = None) -> str:
    """DS-2: the groups in their fixed order (empty ones left out) as native collapsible blocks; a subgroup nests one level
    deeper; the group and subgroup that hold the current page are open, and the current page is marked aria-current."""
    layout = _layout(pages)
    blocks = []
    for name in GROUPS:
        if not layout[name]:
            continue
        rendered = [_sidebar_item(entry, current_slug, ui) for entry in layout[name]]
        open_attribute = " open" if any(holds for _, holds in rendered) else ""
        items = "".join(item for item, _ in rendered)
        blocks.append(f'<div class="side-group"><details{open_attribute}><summary>{html.escape(_label(ui, GROUP_NAMES, name))}</summary><ul>{items}</ul></details></div>')
    return "".join(blocks)


def render_pager(pages: list["Page"], current_slug: str, ui: dict | None = None) -> str:
    """DS-8: links to the previous and the next page in sidebar order; empty for a page that is not in the sidebar (the home page)."""
    order = ordered_pages(pages)
    slugs = [page.slug for page in order]
    if current_slug not in slugs:
        return ""
    words = _ui(ui)
    position = slugs.index(current_slug)
    links = []
    if position > 0:
        before = order[position - 1]
        links.append(f'<a class="pager-prev" rel="prev" href="{html.escape(before.slug)}.html"><span>{html.escape(words["previous"])}</span><strong>{html.escape(before.title)}</strong></a>')
    if position + 1 < len(order):
        after = order[position + 1]
        links.append(f'<a class="pager-next" rel="next" href="{html.escape(after.slug)}.html"><span>{html.escape(words["next"])}</span><strong>{html.escape(after.title)}</strong></a>')
    return f'<nav class="pager" aria-label="{html.escape(words["pager_label"])}">{"".join(links)}</nav>'


def render_toc(rendered: Rendered, ui: dict | None = None) -> str:
    """FR-32, task #3474: the 'On this page' block of the level-2 headings, or '' when there are none."""
    links = "".join(f'<li><a href="#{html.escape(anchor)}">{html.escape(text)}</a></li>' for level, text, anchor in rendered.headings if level == 2)
    return f'<p class="side-title">{html.escape(_ui(ui)["on_this_page"])}</p><ul>{links}</ul>' if links else ""


GROUPS = tuple(site_i18n.default_ui()[GROUP_NAMES])  # #3555, DS-2: the sidebar's fixed order, the order of `group_names` in site/i18n/en/ui.json
GENERATORS = ("schema-reference", "semantics-split")


@dataclass
class SplitPage:
    """One page cut from spec/semantics.md (#3555, DS-10)."""
    slug: str
    title: str
    description: str
    summary: str
    markdown: str  # the section with its heading line replaced by `# <title>` and the summary as the lead paragraph
    alias: str = ""  # the rule anchor the section's heading had (`sem-1`), kept on the page
    original: str = ""  # the section as the source has it, heading line included: the anchors old links point at


def _section_key(heading: str) -> str:
    """The key of a `## ` heading in the summaries file: its rule id (`SEM-1`), or for an addendum the text between
    `Addendum — ` and ` (`."""
    rule = _RULE_HEADING.match(heading)
    if rule:
        return rule.group(1)
    if heading.startswith(ADDENDUM):
        return heading[len(ADDENDUM):].split(" (", 1)[0].strip()
    return heading.strip()


def _cut(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The lines before the first `## ` heading, and the `## ` sections after them; a fenced block never starts a section (the
    fence closes on the same character with at least as many of them, as render_markdown reads it)."""
    preface: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    fence = ""
    for line in text.split("\n"):
        opener = _FENCE_LINE.match(line)
        if fence:
            closer = opener.group(1) if opener else ""
            if closer and closer[0] == fence[0] and len(closer) >= len(fence) and not line.strip().strip(fence[0]):
                fence = ""
        elif opener:
            fence = opener.group(1)
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
            continue
        (sections[-1][1] if sections else preface).append(line)
    return preface, sections


def semantics_preface(text: str) -> str:
    """The text before the first section of the semantics source, without its level-1 title line."""
    lines = _cut(text)[0]
    while lines and (not lines[0].strip() or lines[0].startswith("# ")):
        lines = lines[1:]
    return "\n".join(lines).strip()


def semantics_split(text: str, summaries: dict) -> list[SplitPage]:
    """Cut the semantics source into one SplitPage per `## ` section, in document order, with its plain title, description and
    summary taken from `summaries` (keys: see the module docstring). A section without an entry raises BuildError naming it."""
    sections = _cut(text)[1]
    pages: list[SplitPage] = []
    seen: set[str] = set()
    for heading, lines in sections:
        key = _section_key(heading)
        entry = summaries.get(key)
        if not isinstance(entry, dict):
            raise BuildError(f"the summaries file has no entry '{key}' for the section '{heading[:60]}'")
        for name in ("title", "description", "summary"):
            value = entry.get(name)
            if not isinstance(value, str) or not value.strip():
                raise BuildError(f"the summaries file: entry '{key}' needs a non-empty string '{name}'")
        title = entry["title"].strip()
        slug = slugify(title)
        if not SLUG.match(slug) or slug in seen:
            raise BuildError(f"the summaries file: entry '{key}': the title '{title}' gives the page name '{slug}', which is invalid or used twice")
        seen.add(slug)
        rule = _RULE_HEADING.match(heading)
        body = "\n".join(lines).strip("\n")
        pages.append(SplitPage(slug, title, entry["description"].strip(), entry["summary"].strip(),
                               f"# {title}\n\n{entry['summary'].strip()}\n\n{body}\n", rule_anchor(rule.group(1)) if rule else "",
                               f"## {heading}\n{body}\n"))
    return pages


def split_index(page: "Page", parts: list[SplitPage], preface: str = "") -> str:
    """The Markdown of the index page of a split source: its description, the preface of the source, then each part with its summary."""
    lines = [f"# {page.title}", "", page.description, ""]
    if preface:
        lines.extend([preface, ""])
    lines.extend(f"- [{part.title}]({part.slug}.html): {part.summary}" for part in parts)
    return "\n".join([*lines, ""])


def unsafe_markup(text: str) -> str | None:
    """DS-21: what a page source holds that the site never publishes (a script element or an event-handler attribute), or None."""
    lowered = text.lower()
    position = lowered.find("<")
    while position >= 0:
        end = lowered.find(">", position)
        tag = lowered[position:end if end >= 0 else len(lowered)]
        if tag.startswith("<script"):
            return "a script element"
        if EVENT_HANDLER.search(tag):
            return "an event-handler attribute"
        position = lowered.find("<", position + 1)
    return None


# ---------------------------------------------------------------- inline diagrams (#3830)

DIAGRAM_LINE = re.compile(r"^!\[([^\]\n]*)\]\((site/diagrams/[A-Za-z0-9._-]+\.svg)\)[ \t]*$", re.M)
SVG_EXTERNAL = (
    (re.compile(r"<\s*(?:image|use|iframe|object|embed|style\b[^>]*\bsrc)\b", re.I), "an element that loads another file"),
    (re.compile(r"\bhref\s*=\s*[\"'](?!#)", re.I), "a reference that leaves the file"),
    (re.compile(r"url\(\s*[\"']?(?!#)", re.I), "a url() that leaves the file"),
    (re.compile(r"@import", re.I), "an @import"),
    (re.compile(r"<\s*foreignObject", re.I), "a foreign object"),
)


def unsafe_svg(svg: str) -> str | None:
    """What a diagram file holds that the site never draws into a page (a script, an event handler, anything loaded from outside the file), or None."""
    if "<svg" not in svg:
        return "no svg element"
    problem = unsafe_markup(svg)
    if problem:
        return problem
    for pattern, what in SVG_EXTERNAL:
        if pattern.search(svg):
            return what
    return None


def diagram_figure(svg: str, alt: str) -> str:
    """The file as an inline figure: the page's own CSS variables colour it, and the alt text names it for a screen reader."""
    labelled = re.sub(r"<svg\b", f'<svg role="img" focusable="false" aria-label="{html.escape(alt)}"', svg.strip(), count=1)
    return f'<figure class="diagram">{labelled}</figure>'


# ---------------------------------------------------------------- asset versions (#3841)

VERSIONED_ASSET = re.compile(r'\b(href|src)="((?:\.\./)?)(style\.css|theme\.js|site\.js)"')  # `../` in a language folder


def asset_versions(out_dir: Path) -> dict[str, str]:
    """A short hash of each shared asset's content: the stylesheet and the scripts are served for hours under names that never change, so the
    pages link them with this hash and a changed file gets a new address."""
    return {name: hashlib.sha256((out_dir / name).read_bytes()).hexdigest()[:10]
            for name in ("style.css", *SCRIPTS) if (out_dir / name).is_file()}


def version_assets(page_html: str, versions: dict[str, str]) -> str:
    def swap(match: re.Match) -> str:
        version = versions.get(match.group(3))
        return f'{match.group(1)}="{match.group(2)}{match.group(3)}?v={version}"' if version else match.group(0)
    return VERSIONED_ASSET.sub(swap, page_html)


# ---------------------------------------------------------------- favicon (DS-18)

FAVICON_ORANGE = (255, 122, 61)
FAVICON_DARK = (18, 16, 14)
FAVICON_BARS = (10, 16, 22)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">'
               '<rect x="1" y="1" width="30" height="30" rx="8" fill="#FF7A3D"/>'
               '<path d="M10 7v18M16 7v18M22 7v18" stroke="#12100E" stroke-width="3" stroke-linecap="round" fill="none"/></svg>\n')


def _in_mark(x: float, y: float) -> tuple[int, int, int] | None:
    """The colour of the brand mark at a point of its 32 x 32 grid, or None outside it (the rounded square and three bars)."""
    centre_x, centre_y = min(max(x, 9), 23), min(max(y, 9), 23)
    if not (1 <= x <= 31 and 1 <= y <= 31) or (x - centre_x) ** 2 + (y - centre_y) ** 2 > 64:
        return None
    bar_y = min(max(y, 7), 25)
    if any((x - bar) ** 2 + (y - bar_y) ** 2 <= 2.25 for bar in FAVICON_BARS):
        return FAVICON_DARK
    return FAVICON_ORANGE


def _png_chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)


def _pixel(column: int, row: int, size: int) -> tuple[int, int, int, int]:
    """One RGBA pixel of the brand mark: the mean of 4 x 4 samples, transparent where none falls inside it."""
    samples, scale = 4, size / 32
    inside = [colour for sample_y in range(samples) for sample_x in range(samples)
              if (colour := _in_mark((column + (sample_x + 0.5) / samples) / scale, (row + (sample_y + 0.5) / samples) / scale)) is not None]
    if not inside:
        return 0, 0, 0, 0
    count = len(inside)
    return (sum(c[0] for c in inside) // count, sum(c[1] for c in inside) // count, sum(c[2] for c in inside) // count,
            255 * count // (samples * samples))


@functools.lru_cache(maxsize=None)
def favicon_png(size: int) -> bytes:
    """The brand mark as an RGBA PNG of `size` x `size` pixels, drawn with 4 x 4 samples per pixel (no image library)."""
    rows = []
    for row in range(size):
        line = bytearray([0])
        for column in range(size):
            line.extend(_pixel(column, row, size))
        rows.append(bytes(line))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return PNG_SIGNATURE + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _png_chunk(b"IEND", b"")


def favicon_ico() -> bytes:
    """A 32 x 32 `favicon.ico` holding the PNG (the format every current browser reads)."""
    image = favicon_png(32)
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(image), 22) + image


def head_links(assets: str = "") -> str:
    """The icon links of the page head; `assets` is the prefix that reaches the shared files from the page (empty, or `../` in a language folder)."""
    return (f'<link rel="icon" type="image/svg+xml" href="{assets}favicon.svg"><link rel="icon" href="{assets}favicon.ico" sizes="32x32">'
            f'<link rel="apple-touch-icon" href="{assets}apple-touch-icon.png">')


# ---------------------------------------------------------------- page features (#3556)

SCRIPTS = ("theme.js", "site.js")
TEMPLATE_UI_KEYS = ("skip", "on_this_page")  # the `{{ui_<key>}}` values of the page templates


def script_tags(assets: str = "") -> str:
    return f'<script src="{assets}theme.js"></script><script src="{assets}site.js" defer></script>'


REGISTRY_NAMES = {"nuget": "NuGet", "npm": "npm", "pypi": "PyPI", "go": "Go"}
_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICON_GITHUB = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7'
               'c-2.78.6-3.37-1.34-3.37-1.34-.45-1.15-1.11-1.46-1.11-1.46-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.9.83.09-.65.35-1.08.63-1.33'
               '-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.5 9.5 0 0 1 12 6.8c.85 0 1.7.11 2.5.34 1.9-1.29 2.74-1.02 2.74-1.02'
               '.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2Z"/></svg>')
ICON_SEARCH = _ICON.format('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>')
ICON_NUGET = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M1.998.342a1.997 1.997 0 1 0 0 3.995 1.997 1.997 0 0 0 0-3.995z'
              'm9.18 4.34a6.156 6.156 0 0 0-6.153 6.155v6.667c0 3.4 2.756 6.154 6.154 6.154h6.667c3.4 0 6.154-2.755 6.154-6.154v-6.667a6.154 6.154 0 0 0-6.154-6.155z'
              'm-1.477 2.8a2.496 2.496 0 1 1 0 4.993 2.496 2.496 0 0 1 0-4.993zm7.968 6.16a3.996 3.996 0 1 1-.002 7.992 3.996 3.996 0 0 1 .002-7.992z"/></svg>')
REGISTRY_ICONS = {"nuget": ICON_NUGET}  # the NuGet mark (Simple Icons, CC0); the other registries get the generic package icon
ICON_PACKAGE = _ICON.format('<path d="M21 8 12 3 3 8v8l9 5 9-5V8Z"/><path d="m3 8 9 5 9-5M12 13v8"/>')
ICON_MENU = _ICON.format('<path d="M4 6h16M4 12h16M4 18h16"/>')
ICON_THEME = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<g class="i-auto"><circle cx="12" cy="12" r="8"/><path d="M12 4v16" /></g><g class="i-light"><circle cx="12" cy="12" r="4"/>'
              '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></g>'
              '<g class="i-dark"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"/></g></svg>')
LOGO = ('<svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true"><rect x="1.5" y="1.5" width="25" height="25" rx="7" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M9 6v16M14 6v16M19 6v16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>')
_HEADING_OPEN = re.compile(r'<h([234]) id="([^"]+)">(.*?)</h\1>', re.S)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def render_topbar(config: dict, pages: list["Page"], ui: dict | None = None, language_menu: str = "") -> str:
    """DS-1: the top bar of every page: logo, Docs and Reference, the language control (empty while one language is built), the repository and the published registries, search and theme."""
    words = _ui(ui)
    order = ordered_pages(pages)
    docs = order[0].slug if order else "index"
    reference = next((p.slug for p in order if p.group == "Reference"), docs)
    registries = "".join(
        f'<a class="icon-btn" href="{html.escape(url, quote=True)}" aria-label="{html.escape(REGISTRY_NAMES.get(key, key))} package">{REGISTRY_ICONS.get(key, ICON_PACKAGE)}</a>'
        for key, url in config.get("packages", {}).items())
    return (f'<header class="top"><div class="wrap-wide"><a class="brand" href="index.html">{LOGO}{html.escape(config["title"])}</a>'
            f'<nav class="top-nav" aria-label="Main"><a href="{html.escape(docs)}.html">{html.escape(words["nav_docs"])}</a><a href="{html.escape(reference)}.html">{html.escape(words["nav_reference"])}</a></nav>'
            f'<div class="top-actions">{language_menu}<a class="icon-btn" href="{html.escape(config["repo"], quote=True)}" aria-label="{html.escape(words["github_aria"])}">{ICON_GITHUB}</a>{registries}'
            f'<button type="button" class="icon-btn search-button" aria-label="{html.escape(words["search_aria"])}">{ICON_SEARCH}</button>'
            f'<button type="button" class="icon-btn theme-button" aria-label="{html.escape(words["theme_aria"].format(name=words["theme_names"]["auto"]))}">{ICON_THEME}</button></div></div></header>')


def render_group_cards(config: dict, pages: list["Page"], ui: dict | None = None) -> str:
    """DS-3: one card per group that has pages, linking its first page; empty without a `groups` key in site.json. A group that has pages
    and no description fails the build."""
    groups = config.get("groups") if ui is None else ui.get("groups")
    if groups is None:
        return ""
    order = ordered_pages(pages)
    cards = []
    for name in GROUPS:
        first = next((p for p in order if p.group == name), None)
        if first is None:
            continue
        description = groups.get(name)
        if not isinstance(description, str) or not description.strip():
            raise BuildError(f"site/site.json: the group '{name}' has pages and needs a one-sentence description under 'groups'")
        cards.append(f'<a class="card" href="{html.escape(first.slug)}.html"><h3>{html.escape(_label(ui, GROUP_NAMES, name))}</h3><p>{html.escape(description)}</p></a>')
    return f'<div class="cards group-cards">{"".join(cards)}</div>'


def render_menu_button(slug: str, ui: dict | None = None) -> str:
    """DS-15: the button that opens the sidebar on a phone; the home page has no sidebar."""
    if slug == "index":
        return ""
    words = _ui(ui)
    return (f'<button type="button" class="menu-toggle" aria-controls="sidebar" aria-expanded="false" aria-label="{html.escape(words["menu_aria"])}">'
            f'{ICON_MENU}<span>{html.escape(words["menu_button"])}</span></button>')


def add_anchors(page_html: str) -> str:
    """DS-6: a link anchor in each heading of level 2 to 4, shown on hover and on keyboard focus."""
    return _HEADING_OPEN.sub(lambda m: (f'<h{m.group(1)} id="{m.group(2)}">{m.group(3)} '
                                        f'<a class="anchor" href="#{m.group(2)}" aria-label="Link to this section">#</a></h{m.group(1)}>'), page_html)


def plain_text(page_html: str) -> str:
    """The text of a rendered page without markup and without coded references, for the search index."""
    text = html.unescape(_TAG.sub(" ", page_html))
    return " ".join(CODED_REFERENCE.sub("", text).split())


def search_entry(page: "Page", ui: dict | None = None) -> dict:
    """DS-4, DS-12: the search index entry of a page (the headings keep their text; coded references never reach the index)."""
    rendered = page.rendered
    headings = [{"text": " ".join(CODED_REFERENCE.sub("", text).split()), "anchor": anchor} for level, text, anchor in rendered.headings if 2 <= level <= 4]
    return {"slug": page.slug, "title": page.title, "description": page.description, "group": "" if page.slug == "index" or not page.group else _label(ui, GROUP_NAMES, page.group), "headings": headings,
            "text": plain_text(rendered.html)}


def normalise_base_url(value: object, where: str) -> str:
    """DS-13: the address the llms files link to: https, a host, no credentials, no query, no fragment; one trailing slash is dropped."""
    if not isinstance(value, str):
        raise BuildError(f"{where}: baseUrl must be an https address")
    address = value[:-1] if value.endswith("/") else value
    try:
        parts = urllib.parse.urlsplit(address)
    except ValueError as error:
        raise BuildError(f"{where}: baseUrl '{value}' is not an address") from error
    if parts.scheme != "https" or not parts.hostname or "@" in parts.netloc or parts.query or parts.fragment or address.endswith("/") or re.search(r"\s", address):
        raise BuildError(f"{where}: baseUrl '{value}' must be an https address without credentials, query or fragment")
    return address


def render_llms_txt(config: dict, pages: list["Page"], base: str, ui: dict | None = None, locate: Callable[["Page"], str] | None = None,
                    note: str = "", summary: str = "") -> str:
    """DS-13: `llms.txt` in the llmstxt.org shape: title, summary, then the home page and one section per sidebar group. A language's file
    passes its interface text, `locate` (the address prefix of a page's source file) and `note` (the line that names the English source)."""
    home = next((p for p in pages if p.slug == "index"), None)
    summary = summary or config.get("summary") or (home.description if home else "")
    prefix = f"{base}/" if base else ""

    def line(page: "Page") -> str:
        return f"- [{page.title}]({locate(page) if locate else prefix}{page.slug}.md): {page.description}"

    head = f"# {config['title']}\n\n> {summary}" + (f"\n\n{note}" if note else "")
    sections = [head]
    if home:
        sections.append(f"## {_ui(ui)['llms_home']}\n\n" + line(home))
    layout = _layout(pages)
    for name in GROUPS:
        members = [p for p in ordered_pages(pages) if p.group == name]
        if layout[name]:
            sections.append(f"## {_label(ui, GROUP_NAMES, name)}\n\n" + "\n".join(line(p) for p in members))
    return "\n\n".join(sections) + "\n"


def render_llms_full(pages: list["Page"], texts: dict[str, str], note: str = "") -> str:
    """DS-13: `llms-full.txt`: the home page, then every other page in sidebar order, each as a titled block; a language's file opens with
    `note`, the line that names the English source."""
    home = [p for p in pages if p.slug == "index"]
    blocks = [f"==== {p.title} | {p.slug}.md ====\n\n{texts[p.slug].rstrip(chr(10))}" for p in [*home, *ordered_pages(pages)] if p.slug in texts]
    return "\n\n".join(([note] if note else []) + blocks) + "\n"


def load_config(root: Path) -> dict:
    path = root / "site" / "site.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BuildError(f"cannot read {path}: {error}") from error
    if not isinstance(config, dict):
        raise BuildError(f"{path}: the file must hold one JSON object")
    for key in ("title", "repo", "branch", "pages"):
        if key not in config:
            raise BuildError(f"{path}: missing '{key}'")
    packages = config.setdefault("packages", {})
    if not isinstance(packages, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.startswith("https://") for k, v in packages.items()):
        raise BuildError(f"{path}: 'packages' must map a registry name to an https address")
    if "groups" in config:
        groups = config["groups"]
        if not isinstance(groups, dict):
            raise BuildError(f"{path}: 'groups' must map a group name to a one-sentence description")
        for name, text in groups.items():
            if name not in GROUPS:
                raise BuildError(f"{path}: 'groups': '{name}' is not one of {', '.join(GROUPS)}")
            if not isinstance(text, str):
                raise BuildError(f"{path}: 'groups': the description of '{name}' must be a string")
            if CODED_REFERENCE.search(text):
                raise BuildError(f"{path}: 'groups': the description of '{name}' holds a coded reference")
    if "baseUrl" in config:
        config["baseUrl"] = normalise_base_url(config["baseUrl"], str(path))
    if "summary" in config and (not isinstance(config["summary"], str) or not config["summary"].strip()):
        raise BuildError(f"{path}: 'summary' must be one non-empty sentence")
    config.setdefault("ruleSource", None)
    config.setdefault("ruleIdPrefixes", [])
    for entry in config["pages"]:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("slug", "title")):
            raise BuildError(f"{path}: every page needs a string 'slug' and 'title'")
        generator = entry.get("generator")
        if generator is not None and generator not in GENERATORS:
            raise BuildError(f"{path}: page '{entry['slug']}': unknown generator '{generator}'")
        if generator == "schema-reference":
            entry["source"] = entry.get("schema")
        if not isinstance(entry.get("source"), str):
            raise BuildError(f"{path}: page '{entry['slug']}' needs a string 'source' (or the 'schema' its generator reads)")
        if generator == "semantics-split":
            summaries = entry.get("summaries")
            norm = os.path.normpath(summaries).replace(os.sep, "/") if isinstance(summaries, str) else ""
            if not norm or os.path.isabs(summaries) or norm.startswith("../") or norm == ".." or _is_private(norm):
                raise BuildError(f"{path}: page '{entry['slug']}': 'summaries' must name a public file inside the repository")
        if not SLUG.match(entry["slug"]):
            raise BuildError(f"{path}: page slug '{entry['slug']}' must match [a-z0-9][a-z0-9-]*")
        group = entry.get("group")
        if group not in GROUPS and not (entry["slug"] == "index" and group is None):
            raise BuildError(f"{path}: page '{entry['slug']}' needs a 'group' that is one of {', '.join(GROUPS)}")
        subgroup = entry.get("subgroup")
        if subgroup is not None and (not isinstance(subgroup, str) or not subgroup.strip()):
            raise BuildError(f"{path}: page '{entry['slug']}': 'subgroup' must be a non-empty string")
        if subgroup and CODED_REFERENCE.search(subgroup):
            raise BuildError(f"{path}: page '{entry['slug']}': the subgroup holds a coded reference")
        description = entry.get("description")
        if not isinstance(description, str) or not description.strip():
            raise BuildError(f"{path}: page '{entry['slug']}' needs a one-sentence 'description'")
        if "authored" in entry and not isinstance(entry["authored"], bool):
            raise BuildError(f"{path}: page '{entry['slug']}': 'authored' must be true or false")
        if entry.get("authored") is True:
            reviewed = entry.get("reviewed")
            try:
                if not isinstance(reviewed, str) or not ISO_DATE.fullmatch(reviewed):
                    raise ValueError(reviewed)
                datetime.date.fromisoformat(reviewed)
            except ValueError as error:
                raise BuildError(f"{path}: authored page '{entry['slug']}' needs a 'reviewed' date (YYYY-MM-DD, a real day)") from error
        for label, value in (("title", entry["title"]), ("description", description)):
            if CODED_REFERENCE.search(value):
                raise BuildError(f"{path}: page '{entry['slug']}': the {label} holds a coded reference")
        template = entry.get("template")
        if template is not None:
            norm = os.path.normpath(template).replace(os.sep, "/") if isinstance(template, str) else ""
            if not norm or os.path.isabs(template) or norm.startswith("../") or norm == ".." or _is_private(norm):
                raise BuildError(f"{path}: page '{entry['slug']}': template {template!r} must be a public file inside the repository")
            if not (root / norm).is_file():
                raise BuildError(f"{path}: page '{entry['slug']}': template '{template}' does not exist")
        source = entry["source"]
        normal = os.path.normpath(source).replace(os.sep, "/")
        if os.path.isabs(source) or normal.startswith("../") or normal == ".." or _is_private(normal):
            raise BuildError(f"{path}: page '{entry['slug']}': source '{source}' must be a public file inside the repository")
    slugs = [p["slug"] for p in config["pages"]]
    if len(set(slugs)) != len(slugs) or "index" not in slugs:
        raise BuildError(f"{path}: page slugs must be unique and include 'index'")
    problem = site_i18n.config_problem(config, slugs)
    if problem:
        raise BuildError(f"{path}: {problem}")
    if not isinstance(config["ruleIdPrefixes"], list) or not all(isinstance(x, str) and re.fullmatch(r"[A-Z]{2,5}", x) for x in config["ruleIdPrefixes"]):
        raise BuildError(f"{path}: 'ruleIdPrefixes' must be a list of upper-case prefixes such as \"SEM\"")
    if config["ruleIdPrefixes"] and not config["ruleSource"]:
        raise BuildError(f"{path}: 'ruleIdPrefixes' needs a 'ruleSource'")
    return config


# ---------------------------------------------------------------- generated pages

def _cell(text: str) -> str:
    """One Markdown table cell: no pipe, no line break."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _ref_link(ref: str, own_file: str, page_of_file: dict[str, str]) -> str:
    """`#/$defs/x` or `./other.schema.json#/$defs/x` as a Markdown link to the definition's heading."""
    file_part, _, pointer = ref.partition("#")
    name = pointer.rsplit("/", 1)[-1]
    target_file = os.path.basename(file_part) if file_part else own_file
    page = page_of_file.get(target_file)
    if page is None:
        return f"`{name}`"
    anchor = slugify(name)
    return f"[{name}]({'' if target_file == own_file else page + '.html'}#{anchor})"


def _type_cell(schema: dict, own_file: str, page_of_file: dict[str, str]) -> str:
    parts: list[str] = []
    if "$ref" in schema:
        parts.append(_ref_link(schema["$ref"], own_file, page_of_file))
    if "const" in schema:
        parts.append(f"const `{json.dumps(schema['const'])}`")
    if "enum" in schema:
        parts.append("one of " + ", ".join(f"`{json.dumps(v)}`" for v in schema["enum"]))
    kind = schema.get("type")
    if kind and "enum" not in schema and "const" not in schema:
        parts.append(" or ".join(kind) if isinstance(kind, list) else str(kind))
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        parts.append("of " + _type_cell(schema["items"], own_file, page_of_file))
    for key in ("oneOf", "anyOf", "allOf"):
        if key in schema:
            word = {"oneOf": "one of", "anyOf": "any of", "allOf": "all of"}[key]
            parts.append(word + " " + ", ".join(_type_cell(v, own_file, page_of_file) for v in schema[key]))
    if schema.get("type") == "object" and "properties" not in schema and "$ref" not in schema:
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            parts.append("map to " + _type_cell(extra, own_file, page_of_file))
    constraints = []
    for key in ("minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "minProperties", "format", "pattern", "uniqueItems"):
        if key in schema:
            constraints.append(f"{key} `{json.dumps(schema[key])}`")
    if constraints:
        parts.append("(" + ", ".join(constraints) + ")")
    return " ".join(parts) if parts else "any"


def _member_rows(schema: dict, prefix: str, own_file: str, page_of_file: dict[str, str], required_here: set[str] | None = None,
                 variant: bool = False) -> list[str]:
    """Rows `| member | type | required | default | description |` for every property of an object schema, nested inline
    objects flattened to a dotted path (`*` stands for a map's key, `[]` for an array's element)."""
    rows: list[str] = []
    required = set(schema.get("required", [])) if required_here is None else required_here
    for name, sub in (schema.get("properties") or {}).items():
        if not isinstance(sub, dict):
            sub = {}
        path = f"{prefix}{name}"
        default = f"`{json.dumps(sub['default'])}`" if "default" in sub else ""
        rows.append("| " + " | ".join([
            f"`{path}`", _cell(_type_cell(sub, own_file, page_of_file)),
            ("in this variant" if variant else "yes") if name in required else "",
            _cell(default), _cell(sub.get("description", ""))]) + " |")
        rows.extend(_nested_rows(sub, path, own_file, page_of_file, variant))
    return rows


def _nested_rows(sub: dict, path: str, own_file: str, page_of_file: dict[str, str], variant: bool = False) -> list[str]:
    rows: list[str] = []
    if not isinstance(sub, dict):
        return rows
    if sub.get("properties"):
        rows.extend(_member_rows(sub, path + ".", own_file, page_of_file, variant=variant))
    extra = sub.get("additionalProperties")
    if isinstance(extra, dict) and "$ref" not in extra:
        rows.extend(_nested_rows(extra, path + ".*", own_file, page_of_file, variant))
    items = sub.get("items")
    if isinstance(items, dict) and "$ref" not in items and items.get("properties"):
        rows.extend(_member_rows(items, path + "[].", own_file, page_of_file, variant=variant))
    for key in ("oneOf", "anyOf", "allOf"):  # inline variants contribute their members under the same path
        for alternative in sub.get(key, []):
            if isinstance(alternative, dict) and "$ref" not in alternative:
                rows.extend(_nested_rows(alternative, path, own_file, page_of_file, variant=True))
    return rows


_TABLE_HEAD = ["| Member | Type | Required | Default | Description |", "|---|---|---|---|---|"]


def schema_reference(schema: dict, own_file: str, page_of_file: dict[str, str]) -> str:
    """Markdown reference of a JSON Schema: its root members, then each definition with its members and variants."""
    if not isinstance(schema, dict):
        raise BuildError(f"{own_file}: a JSON Schema document must be an object")
    lines = [f"# {schema.get('title', own_file)} reference", "",
             f"Generated from `spec/{own_file}` (`$id` `{schema.get('$id', '')}`). Every member of the schema is listed with its type and description.", ""]
    if schema.get("description"):
        lines += [str(schema["description"]), ""]
    rows = _member_rows(schema, "", own_file, page_of_file)
    if rows:
        lines += ["## Members", "", *_TABLE_HEAD, *rows, ""]
    defs = schema.get("$defs") or {}
    if defs:
        lines += ["## Definitions", ""]
    for name, definition in defs.items():
        if not isinstance(definition, dict):  # `true` / `false` are valid subschemas
            definition = {}
        lines += [f"### {name}", ""]
        if definition.get("description"):
            lines += [str(definition["description"]), ""]
        type_line = _type_cell({k: v for k, v in definition.items() if k not in ("properties", "description")}, own_file, page_of_file)
        if type_line != "any":
            lines += [f"Type: {type_line}", ""]
        rows = _member_rows(definition, "", own_file, page_of_file)
        rows.extend(_nested_rows({k: v for k, v in definition.items() if k != "properties"}, "", own_file, page_of_file))
        if rows:
            lines += [*_TABLE_HEAD, *rows, ""]
    return "\n".join(lines)


_RULE_DEFINITION = re.compile(rf"(?m)^(?:#+\s+|\*\*)({RULE_ID})\.\s*(.*)$")


def rule_definitions(text: str) -> dict[str, str]:
    """Rule id -> its title (the first words of the heading or bold opener), in document order."""
    found: dict[str, str] = {}
    for match in _RULE_DEFINITION.finditer(text):
        title = re.sub(r"\*\*.*$", "", match.group(2)).strip()
        found.setdefault(match.group(1), title[:110])
    return found


_INCLUDE = re.compile(r"^\{\{include\s+(\S+)\s+([\w-]*)\}\}\s*$")


def expand_includes(text: str, root: Path, source: str) -> str:
    """Replace each `{{include path language}}` line by the file as a fenced code block, the fence one backtick longer than the
    longest backtick run in the file (at least four), so a file that holds a fence of its own survives. A line that starts with
    `{{include` but is not well formed, and an unreadable, private or outside path, are configuration errors (exit 2). A line
    inside a code fence of the page itself is left alone (it is an example of the directive)."""
    out: list[str] = []
    fence: str | None = None
    for number, line in enumerate(text.split("\n"), 1):
        opener = _FENCE_LINE.match(line)
        if opener:
            marker = opener.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        if fence is not None or not line.startswith("{{include"):
            out.append(line)
            continue
        match = _INCLUDE.match(line)
        if not match:
            raise BuildError(f"{source}:{number}: malformed include (expected `{{{{include <path> <language>}}}}`): {line[:60]}")
        rel = os.path.normpath(match.group(1)).replace(os.sep, "/")
        if os.path.isabs(match.group(1)) or rel.startswith("../") or rel == ".." or _is_private(rel):
            raise BuildError(f"{source}:{number}: include '{match.group(1)}' must be a public file inside the repository")
        try:
            body = (root / rel).read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
        except (OSError, UnicodeDecodeError) as error:
            raise BuildError(f"{source}:{number}: cannot include '{rel}': {error}") from error
        longest = max((len(run) for run in re.findall(r"`+", body)), default=0)
        ticks = "`" * max(4, longest + 1)
        out.append(f"{ticks}{match.group(2)}\n{body}\n{ticks}")
    return "\n".join(out)


def check_rule_ids(texts: dict[str, str], rule_text: str, prefixes: list[str]) -> list[str]:
    """Every `PREFIX-n` mentioned on a page must be defined by the rule source (heading or bold opener)."""
    if not prefixes:
        return []
    defined = {re.sub(r"(?:\([a-z]\)|[a-z])$", "", rule) for rule in rule_definitions(rule_text)}
    mention = re.compile(rf"\b((?:{'|'.join(map(re.escape, prefixes))})-\d+)(?![\d])")
    errors: list[str] = []
    for source, text in texts.items():
        for number, line in enumerate(text.splitlines(), 1):
            for match in mention.finditer(line):
                if match.group(1) not in defined:
                    errors.append(f"{source}:{number}: rule id '{match.group(1)}' is not defined in the rule source")
    return errors


def _is_private(rel: str) -> bool:
    """True for a path the public mirror does not carry: a PRIVATE entry itself (file or bare directory) or anything under it."""
    rel = rel.strip("/")
    return any(rel == entry or rel.startswith(entry + "/") for entry in PRIVATE_PATHS)


def resolve_link(href: str, source: str, pages_by_source: dict[str, Page], root: Path, config: dict,
                 anchors_of, errors: list[str], line: int, own_anchors: set[str], raw: bool = False,
                 label: str | None = None, context: "LinkContext | None" = None) -> str:
    """The href to emit for `href` found in `source`, or the original one after recording an error."""
    where = f"{label or source}:{line}"
    context = context or LinkContext()
    pages_by_slug, page_anchors, splits, own_split = context.pages_by_slug, context.page_anchors, context.splits, context.own_split

    def split_href(links: "SplitLinks", fragment: str, name: str) -> str:
        if not fragment:
            return f"{links.index_slug}.html"
        found = links.owner(fragment)
        if found is None:
            errors.append(f"{where}: dead anchor '#{fragment}' in {name}")
            return href
        return f"{found[0]}.html" + (f"#{fragment}" if found[1] else "")

    if EXTERNAL.match(href):
        if not href.lower().startswith(ALLOWED_SCHEMES):
            errors.append(f"{where}: link '{href[:40]}' uses a scheme other than http, https or mailto")
        return href
    path_part, _, fragment = href.partition("#")
    if not path_part:
        if fragment and fragment not in own_anchors:
            found = own_split.owner(fragment) if own_split else None
            if found:
                return f"{found[0]}.html" + (f"#{fragment}" if found[1] else "")
            errors.append(f"{where}: dead anchor '#{fragment}'")
        return href
    index_links = {links.index_slug: links for links in splits.values()}
    if path_part.endswith(".html") and "/" not in path_part and path_part[:-5] in index_links:
        return split_href(index_links[path_part[:-5]], fragment, path_part)
    if pages_by_slug and path_part.endswith(".html") and "/" not in path_part and path_part[:-5] in pages_by_slug:
        # A link to a built page (`ir-schema.html#filternode`), as the generated pages write them.
        if fragment and page_anchors is not None and fragment not in page_anchors(path_part[:-5]):
            errors.append(f"{where}: dead anchor '#{fragment}' in page {path_part}")
        return href
    target = os.path.normpath(os.path.join(os.path.dirname(source), path_part)).replace(os.sep, "/")
    if target.startswith("../") or target == "..":
        errors.append(f"{where}: link '{href}' leaves the repository")
        return href
    if _is_private(target):
        errors.append(f"{where}: link '{href}' points into the private part of the repository ({target})")
        return href
    if target in splits:
        return split_href(splits[target], fragment, target)
    page = pages_by_source.get(target)
    if page is not None:
        if fragment and fragment not in anchors_of(page.source):
            errors.append(f"{where}: dead anchor '#{fragment}' in {target}")
        return f"{page.slug}.html" + (f"#{fragment}" if fragment else "")
    full = root / target
    if not full.exists():
        errors.append(f"{where}: dead link '{href}' (no such file: {target})")
        return href
    if fragment and target.endswith(".md") and fragment not in anchors_of(target):
        errors.append(f"{where}: dead anchor '#{fragment}' in {target}")
    kind = "tree" if full.is_dir() else ("raw" if raw else "blob")
    return f"{config['repo'].rstrip('/')}/{kind}/{config['branch']}/{target.rstrip('/')}" + (f"#{fragment}" if fragment else "")


@dataclass
class LinkContext:
    """What a link needs to know about the built pages: by name, their anchors, the split sources and the split the current page is part of."""
    pages_by_slug: dict[str, Page] | None = None
    page_anchors: "Callable[[str], set[str]] | None" = None
    splits: dict[str, "SplitLinks"] = field(default_factory=dict)
    own_split: "SplitLinks | None" = None


@dataclass
class SplitLinks:
    """Where the anchors of a split source went: the index page's slug and, for an anchor, the page that holds its heading and
    whether the anchor still exists on that page (None when the source has no such anchor)."""
    index_slug: str
    owner: Callable[[str], "tuple[str, bool] | None"]


# A link to a page the language folder does not hold: an anchor whose href is `<slug>.html` or `<slug>.html#fragment` (spec 004-site-languages, FR-026).
ENGLISH_LINK = re.compile(r'<a\b([^>]*?)(?<![\w-])href="([a-z0-9][a-z0-9-]*)\.html(#[^"]*)?"([^>]*)>(.*?)</a>', re.S)
ENGLISH_MARK_CLASS = "en-mark"


def english_links(page_html: str, pages_by_slug: dict[str, "Page"], built: set[str], mark: str) -> str:
    """The one pass over a language page's final HTML: each link to a known page that is English only, or that this build has no file for,
    goes to the English address (`../<slug>.html`, the fragment kept) and is followed by the localized mark. Only an anchor's `href` of the
    form `<slug>.html` matches, so a rewritten link, a fragment-only link, an asset, an external address and an escaped code sample are left alone."""
    shown = html.escape(mark)

    def swap(match: re.Match) -> str:
        slug = match.group(2)
        page = pages_by_slug.get(slug)
        if page is None or (page.scope != "english" and slug in built):
            return match.group(0)
        return (f'<a{match.group(1)}href="../{slug}.html{match.group(3) or ""}"{match.group(4)}>{match.group(5)}</a> '
                f'<span class="{ENGLISH_MARK_CLASS}">{shown}</span>')
    return ENGLISH_LINK.sub(swap, page_html)


@dataclass
class LanguageContext:
    """What the build of one translated language has beyond the English build it follows: its interface text, the translated copy of each
    translated-scope page that has a file, the text of each (its `{{include}}` lines expanded) and the errors found reading the files."""
    code: str
    english: "SiteBuild"
    ui: dict
    translations: site_i18n.Translations
    pages: dict[str, "Page"] = field(default_factory=dict)
    bodies: dict[str, str] = field(default_factory=dict)
    templates: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def fill_template(template: str, values: dict[str, str]) -> str:
    """One pass: a value that itself contains {{...}} (page content may) is never substituted again."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


class SiteBuild:
    """One build of the site: the pages (with the split ones), what each links to, and the files written. Kept as methods so that no single
    function carries the whole build."""

    def __init__(self, root: Path, config: dict, base: str, language: LanguageContext | None = None) -> None:
        self.root, self.config, self.base = root, config, base
        self.language = language
        self.code = language.code if language else site_i18n.ENGLISH
        self.ui = language.ui if language else None
        self.langset = language.english.langset if language else site_i18n.LanguageSet(base=base)
        self.path = site_i18n.language_path(config, self.code)
        self.scripts_ready = False
        self.versions: dict[str, str] = {}
        self.translated: set[str] = set()
        self.pages: list[Page] = []
        self.errors: list[str] = []
        self.region_cache: tuple[str, list[str]] | None = None
        self.text_cache: dict[str, str] = {}
        self.split_sources: dict[str, list[Page]] = {}
        self.split_slugs: dict[str, str] = {}
        self.split_summaries: dict[str, str] = {}
        self.member_original: dict[str, str] = {}
        self.anchor_cache: dict[str, set[str]] = {}
        self.file_anchor_cache: dict[str, set[str]] = {}
        self.splits: dict[str, SplitLinks] = {}
        self.own_split_of: dict[str, SplitLinks] = {}
        self.load_pages()
        if language:
            self.use_translations(language)
        self.pages_by_slug = {p.slug: p for p in self.pages}
        if len(self.pages_by_slug) != len(self.pages):
            raise BuildError("page names are not unique once the split pages are added")
        self.pages_by_source = {p.source: p for p in self.pages if p.generator is None}
        self.page_of_file = {os.path.basename(p.source): p.slug for p in self.pages if p.generator == "schema-reference"}
        self.splits = {source: SplitLinks(self.split_slugs[source], self.make_owner(source)) for source in self.split_sources}
        self.own_split_of = {member.slug: self.splits[source] for source, members in self.split_sources.items() for member in members}

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def use_translations(self, language: LanguageContext) -> None:
        """A language build keeps the English page list (the sidebar shows every page) with the translated copy and text of each page it has a file for."""
        self.errors = list(language.errors)
        self.pages = [language.pages.get(page.slug, page) for page in self.pages]
        self.text_cache.update(language.bodies)
        self.translated = set(language.pages)

    def built(self) -> list[Page]:
        """The pages this build writes: all of them in English, the translated ones in a language."""
        return [page for page in self.pages if self.language is None or page.slug in self.translated]

    def source_label(self, page: Page) -> str:
        return language_file(self.code, f"{page.slug}.md") if page.slug in self.translated else page.source

    def load_pages(self) -> None:
        for entry in self.config["pages"]:
            page = Page(entry["slug"], entry["title"], entry["source"], entry.get("generator"), group=entry.get("group"), template=entry.get("template"),
                        description=entry["description"], subgroup=entry.get("subgroup"), authored=entry.get("authored") is True, reviewed=entry.get("reviewed"),
                        scope=entry["scope"])
            self.pages.append(page)
            if page.generator == "semantics-split":
                self.expand_split(page, entry["summaries"])

    def expand_split(self, page: Page, summaries_path: str) -> None:
        """DS-10: the index text of a split page and one page for each section of its source."""
        try:
            parts = semantics_split(self.read(page.source), json.loads(self.read(summaries_path)))
        except (OSError, ValueError) as error:
            raise BuildError(f"page '{page.slug}': cannot read {page.source} or {summaries_path}: {error}") from error
        self.text_cache[page.slug] = split_index(page, parts, semantics_preface(self.read(page.source)))
        self.split_slugs[page.source] = page.slug
        self.split_summaries[page.slug] = summaries_path
        self.split_sources[page.source] = []
        for part in parts:
            for label, value in (("title", part.title), ("description", part.description), ("summary", part.summary)):
                if CODED_REFERENCE.search(value):
                    self.errors.append(f"site/site.json: page '{part.slug}' ('{part.title}'): the {label} holds a coded reference")
            member = Page(part.slug, part.title, page.source, "semantics-part", group="Reference", subgroup=SPLIT_SUBGROUP,
                          description=part.description, summary=part.summary, alias=part.alias, scope=page.scope)
            self.text_cache[member.slug] = part.markdown
            self.member_original[member.slug] = part.original
            self.pages.append(member)
            self.split_sources[page.source].append(member)

    def page_text(self, page: Page) -> str:
        """The Markdown of a page: the file itself, or what its generator makes of the file."""
        if page.slug not in self.text_cache:
            if page.generator == "schema-reference":
                try:
                    schema = json.loads(self.read(page.source))
                except ValueError as error:
                    raise BuildError(f"{page.source}: not valid JSON: {error}") from error
                self.text_cache[page.slug] = schema_reference(schema, os.path.basename(page.source), self.page_of_file)
            else:
                text = expand_includes(self.read(page.source), self.root, page.source)
                self.text_cache[page.slug] = left_out_region(text, page.source)[0] if page.source == README_SOURCE else text
        return self.text_cache[page.slug]

    def readme_region(self) -> tuple[str, list[str]]:
        """The inner text of the README's left-out region and the problems of its marker pair; empty when no page is sourced from the README."""
        if self.region_cache is None:
            self.region_cache = ("", [])
            if README_SOURCE in self.pages_by_source:
                try:
                    _, inner, problems = left_out_region(self.read(README_SOURCE), README_SOURCE)
                    self.region_cache = (inner, problems)
                except (OSError, UnicodeDecodeError):
                    pass
        return self.region_cache

    def home_block(self) -> str:
        """The README's performance region rendered for the English home page; empty in a language build or when the region is empty."""
        inner = self.readme_region()[0] if self.language is None else ""
        if not inner:
            return ""
        page = self.pages_by_source[README_SOURCE]
        base = self.config.get("baseUrl")
        link_errors: list[str] = []
        first = render_markdown(inner)
        resolver = self.resolver_for(page, self.page_anchors(page.slug), link_errors, iter(line for line, _ in first.links), f"{README_SOURCE} (performance block)")

        def resolve(href: str, image: bool = False) -> str:
            name = href[len(base) + 1:] if base and href.startswith(f"{base}/") else ""
            return resolver(name if name.endswith(".html") and name[:-5] in self.pages_by_slug else href, image)

        rendered = render_markdown(inner, resolve=resolve)
        self.errors.extend(link_errors)
        return f'<div id="{HOME_BLOCK_ID}">{add_anchors(rendered.html)}</div>'

    def page_anchors(self, slug: str) -> set[str]:
        if slug not in self.anchor_cache:
            try:
                found = set(render_markdown(self.page_text(self.pages_by_slug[slug])).anchors)
            except (OSError, UnicodeDecodeError):
                found = set()
            if self.pages_by_slug[slug].alias:
                found.add(self.pages_by_slug[slug].alias)
            self.anchor_cache[slug] = found
        return self.anchor_cache[slug]

    def make_owner(self, source: str):
        members = self.split_sources[source]
        index_slug = self.split_slugs[source]
        heading_page: dict[str, str] = {}
        current = index_slug
        section = -1
        for level, _, anchor in render_markdown(self.read(source)).headings:
            if level == 2:
                section += 1
                current = members[section].slug if section < len(members) else current
            heading_page.setdefault(anchor, current)

        def owner(anchor: str) -> tuple[str, bool] | None:
            if anchor in heading_page:
                return heading_page[anchor], anchor in self.page_anchors(heading_page[anchor])
            for member in members:
                if anchor in self.page_anchors(member.slug):
                    return member.slug, True
            return (index_slug, True) if anchor in self.page_anchors(index_slug) else None
        return owner

    def anchors_of(self, rel: str) -> set[str]:
        """Anchors of a Markdown file of the repository (a page's own are computed from its text)."""
        if rel in self.pages_by_source:
            return self.page_anchors(self.pages_by_source[rel].slug)
        if rel not in self.file_anchor_cache:
            try:
                self.file_anchor_cache[rel] = render_markdown(self.read(rel)).anchors
            except (OSError, UnicodeDecodeError):
                self.file_anchor_cache[rel] = set()
        return self.file_anchor_cache[rel]

    def write_assets(self, out_dir: Path) -> bool:
        """The files every page shares: stylesheet, scripts, favicons, fonts. A file removed from the sources must not linger in the output.
        Returns whether both scripts exist."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.html", "*.md", LLMS_NAME, LLMS_FULL_NAME):
            for stale in out_dir.glob(pattern):
                stale.unlink()
        (out_dir / "style.css").write_text(self.read("site/style.css"), encoding="utf-8")
        scripts_ready = all((self.root / "site" / "js" / name).is_file() for name in SCRIPTS)
        for name in SCRIPTS:
            source = self.root / "site" / "js" / name
            if source.is_file():
                (out_dir / name).write_bytes(source.read_bytes())
            elif (out_dir / name).exists():
                (out_dir / name).unlink()
        (out_dir / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
        (out_dir / "favicon.ico").write_bytes(favicon_ico())
        (out_dir / "apple-touch-icon.png").write_bytes(favicon_png(180))
        self.copy_fonts(out_dir)
        return scripts_ready

    def copy_fonts(self, out_dir: Path) -> None:
        fonts_in, fonts_out = self.root / "site" / "fonts", out_dir / "fonts"
        if fonts_out.is_dir():
            for stale_font in fonts_out.iterdir():
                if stale_font.is_file():
                    stale_font.unlink()
        if fonts_in.is_dir():
            fonts_out.mkdir(exist_ok=True)
            for font in sorted(fonts_in.iterdir()):
                if font.is_file():
                    (fonts_out / font.name).write_bytes(font.read_bytes())

    def check_markup(self, page: Page, text: str) -> None:
        """DS-21: a source that holds a script element or an event-handler attribute is refused, and so are the files a split reads."""
        sources: list[tuple[str, str]] = []
        if page.generator == "semantics-split":
            summaries = self.split_summaries[page.slug]
            sources = [(page.source, self.read(page.source)), (summaries, self.read(summaries))]
        elif page.generator is None:
            sources = [(self.source_label(page), text)]
        for name, value in sources:
            problem = unsafe_markup(value)
            if problem:
                self.errors.append(f"{name}: page '{page.slug}' holds {problem}, which the site never publishes")

    def resolver_for(self, page: Page, own: set[str], link_errors: list[str], lines, label_override: str | None = None) -> Callable:
        generated = page.generator is not None
        label = f"site/site.json#{page.slug}" if generated else None
        if page.generator == "semantics-part":
            label = f"{page.source} (page '{page.slug}')"
        label = label_override or label
        source = page.source if page.generator in (None, "semantics-part", "semantics-split") else "site/_generated"
        context = LinkContext(self.pages_by_slug, self.page_anchors, self.splits, self.own_split_of.get(page.slug))

        def resolve(href: str, image: bool = False) -> str:
            return resolve_link(href, source, self.pages_by_source, self.root, self.config, self.anchors_of, link_errors, next(lines, 0), own,
                                raw=image, label=label, context=context)
        return resolve

    def draw_diagrams(self, page: Page, text: str) -> tuple[str, dict[str, str]]:
        """A whole-line image of an SVG file under site/diagrams is drawn into the page as a figure (GitHub shows the same line as an image).
        The text gets a placeholder paragraph per diagram, which `render` swaps for the figure once the Markdown is converted."""
        figures: dict[str, str] = {}

        def draw(match: re.Match) -> str:
            alt, rel = match.group(1), match.group(2)
            try:
                svg = self.read(rel)
            except OSError:
                self.errors.append(f"{page.source}: the diagram {rel} does not exist")
                return match.group(0)
            problem = unsafe_svg(svg)
            if problem:
                self.errors.append(f"{rel}: the diagram holds {problem}, which the site never draws into a page")
                return match.group(0)
            key = f"DIAGRAMHOLD{len(figures)}X"
            figures[key] = diagram_figure(svg, alt)
            return key

        return DIAGRAM_LINE.sub(draw, text), figures

    def render(self, page: Page, text: str) -> Rendered:
        """The page's HTML body: links resolved against what the site builds, an alias anchor and the heading anchors added."""
        link_errors: list[str] = []
        text, figures = self.draw_diagrams(page, text)
        required = self.language is not None and page.slug in self.translated
        first = render_markdown(text, resolve=lambda href, image=False: href, require_anchors=required)
        # Second pass with the real resolver, now that the page's own anchors are known; the line of each link comes from the first pass.
        rendered = render_markdown(text, resolve=self.resolver_for(page, self.page_anchors(page.slug), link_errors, iter(line for line, _ in first.links)),
                                   require_anchors=required)
        self.errors.extend(link_errors)
        for key, figure in figures.items():
            rendered.html = rendered.html.replace(f"<p>{key}</p>", figure)
        if page.alias:
            rendered.html = f'<a id="{html.escape(page.alias)}"></a>' + rendered.html
            rendered.anchors.add(page.alias)
        page.rendered = rendered
        return rendered

    def check_headings(self, page: Page, rendered: Rendered) -> None:
        for heading in rendered.undeclared:
            self.errors.append(f"page '{page.slug}': the heading '{heading[:60]}' declares no English anchor; end it with {{#english-anchor}}")
        for level, heading, _ in rendered.headings:
            if level != 2:
                continue
            if len(heading) > MAX_TOC_LABEL:
                self.errors.append(f"page '{page.slug}': the heading '{heading[:40]}…' is {len(heading)} characters; a level-2 heading is at most {MAX_TOC_LABEL}")
            if CODED_REFERENCE.search(heading):
                self.errors.append(f"page '{page.slug}': the heading '{heading[:60]}' holds a coded reference, and it is a label of the page's contents")

    def prepare_output(self, out_dir: Path) -> Path:
        """The folder this build writes its pages into. English writes the shared files at the root and clears the folder of every language;
        a language takes the root's versions of the shared files and writes nothing else of them (FR-023)."""
        if self.language is not None:
            english = self.language.english
            self.scripts_ready, self.versions = english.scripts_ready, english.versions
            folder = out_dir / self.path
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        self.scripts_ready = self.write_assets(out_dir)
        try:
            site_i18n.clear_language_folders(out_dir, self.config)
        except site_i18n.I18nError as error:
            raise BuildError(str(error)) from error
        self.versions = asset_versions(out_dir)
        return out_dir

    def spec_version(self) -> str:
        try:
            return self.read("spec/VERSION").strip()
        except (OSError, UnicodeDecodeError):
            return ""

    def shared_values(self) -> dict[str, str]:
        """What every page of this build has alike; the interface text is a value too, `ui_<key>` for each key the templates use."""
        assets = self.langset.prefix(self.code)
        return {
            "site_title": html.escape(self.config["title"]),
            "head_links": head_links(assets),
            "lang": html.escape(site_i18n.language_attribute(self.config, self.code)),
            "assets": assets,
            "data_ui": self.data_ui(),
            "spec_version": html.escape(self.spec_version()),
            "nav": "".join(f'<li><a href="{html.escape(p.slug)}.html">{html.escape(p.title)}</a></li>' for p in self.pages if p.generator != "semantics-part"),
            "group_cards": render_group_cards(self.config, self.pages, self.ui),
            "scripts": script_tags(assets) if self.scripts_ready else "",
            **{f"ui_{key}": html.escape(_ui(self.ui)[key]) for key in TEMPLATE_UI_KEYS},
        }

    def template_of(self, page: Page, templates: dict[str, str]) -> str:
        """The template of a page; a translated home page uses its language's `home.html` when the language has one."""
        rel = page.template or "site/template.html"
        if self.language is not None:
            return self.language.templates.get(rel, templates[rel])
        return templates[rel]

    def finish(self, page_html: str) -> str:
        """Versions the shared assets and, in a language, sends the links to pages it does not hold to the English ones."""
        page_html = version_assets(page_html, self.versions)
        if self.language is None:
            return page_html
        return english_links(page_html, self.pages_by_slug, self.translated, _ui(self.ui)["english_mark"])

    def build_page(self, page: Page, target: Path, shared: dict[str, str], templates: dict[str, str]) -> tuple[str, dict] | None:
        """Writes one page and its source copy; returns its text and search entry, or None when the source cannot be read."""
        try:
            text = self.page_text(page)
        except (OSError, UnicodeDecodeError) as error:
            self.errors.append(f"site/site.json: page '{page.slug}': cannot read {page.source}: {error}")
            return None
        self.check_markup(page, text)
        try:
            rendered = self.render(page, text)
        except BuildError as error:
            self.errors.append(f"page '{page.slug}': {error}")
            return None
        entry = search_entry(page, self.ui)
        rendered.html = add_anchors(rendered.html)
        self.check_headings(page, rendered)
        values = {**shared, **self.page_values(page, rendered)}
        (target / f"{page.slug}.html").write_text(self.finish(fill_template(self.template_of(page, templates), values)), encoding="utf-8")
        (target / f"{page.slug}.md").write_text(text, encoding="utf-8")
        return text, entry

    def run(self, out_dir: Path) -> list[str]:
        templates = {rel: self.read(rel) for rel in {"site/template.html", *(p.template for p in self.pages if p.template)}}
        target = self.prepare_output(out_dir)
        shared = self.shared_values()
        texts: dict[str, str] = {}
        page_texts: dict[str, str] = {}
        index_entries: list[dict] = []
        if self.language is None:
            inner, region_problems = self.readme_region()
            self.errors.extend(region_problems)
            region_markup = unsafe_markup(inner)
            if region_markup:
                self.errors.append(f"README.md (performance block): holds {region_markup}, which the site never publishes")
        for page in self.built():
            made = self.build_page(page, target, shared, templates)
            if made is None:
                continue
            page_texts[page.slug] = made[0]
            texts[f"{page.source} (page '{page.slug}')" if page.generator is not None else self.source_label(page)] = made[0]
            index_entries.append(made[1])
        self.write_listings(target, page_texts, index_entries)
        self.check_rule_source(texts)
        return self.errors

    def data_ui(self) -> str:
        """The `data-ui` attribute of `<body>` with the messages of `site.js`; empty for English, where the script's own strings stand."""
        if self.ui is None:
            return ""
        handed = {**self.ui, "search_english_url": self.langset.prefix(self.code) + "index.html"}
        return f' data-ui="{html.escape(site_i18n.script_ui(handed), quote=True)}"'

    def page_values(self, page: Page, rendered: Rendered) -> dict[str, str]:
        menu = self.langset.menu(self.code, page.slug, _ui(self.ui)["language_label"])
        return {
            "page_title": html.escape(page.title),
            "description": html.escape(page.description, quote=True),
            "alternates": self.langset.alternates(self.code, page.slug),
            "topbar": render_topbar(self.config, self.pages, self.ui, menu),
            "sidebar": render_sidebar(self.pages, page.slug, self.ui),
            "toc": render_toc(rendered, self.ui),
            "prev_next": render_pager(self.pages, page.slug, self.ui),
            "menu_button": render_menu_button(page.slug, self.ui),
            "content": (self.home_block() if self.language is None and page.slug == "index" else "") + rendered.html,
            "source": html.escape(page.source),
            "source_url": html.escape(f"{self.config['repo'].rstrip('/')}/blob/{self.config['branch']}/{page.source}"),
        }

    def english_address(self, name: str) -> str:
        """Where the English file `name` is, as a language's `llms` files name it: the public address, or `../<name>` without a base address."""
        return f"{self.base}/{name}" if self.base else f"../{name}"

    def llms_prefix(self, page: Page) -> str:
        """The address prefix of a page's source file in a language's `llms.txt`: its own folder for a translated page, the English root otherwise."""
        own_folder = page.slug in self.translated
        if self.base:
            return f"{self.base}/{self.path}/" if own_folder else f"{self.base}/"
        return "" if own_folder else "../"

    def write_listings(self, out_dir: Path, page_texts: dict[str, str], index_entries: list[dict]) -> None:
        if self.language is None:
            llms, full = render_llms_txt(self.config, self.pages, self.base), render_llms_full(self.pages, page_texts)
        else:
            words = _ui(self.ui)
            note = f"{words['llms_english_source']}: {self.english_address(LLMS_NAME)}"
            summary = next((p.description for p in self.pages if p.slug == "index"), "")
            llms = render_llms_txt(self.config, self.pages, self.base, self.ui, self.llms_prefix, note, summary)
            full = render_llms_full(self.pages, page_texts, f"{words['llms_english_source']}: {self.english_address(LLMS_FULL_NAME)}")
        (out_dir / LLMS_NAME).write_text(llms, encoding="utf-8")
        (out_dir / LLMS_FULL_NAME).write_text(full, encoding="utf-8")
        (out_dir / "search-index.json").write_text(json.dumps(index_entries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def check_rule_source(self, texts: dict[str, str]) -> None:
        if not self.config["ruleSource"]:
            return
        try:
            self.errors.extend(check_rule_ids(texts, self.read(self.config["ruleSource"]), self.config["ruleIdPrefixes"]))
        except (OSError, UnicodeDecodeError) as error:
            self.errors.append(f"site/site.json: cannot read the rule source {self.config['ruleSource']}: {error}")


def coded_reference_errors(code: str, page: "Page") -> list[str]:
    """DS-19 on the title and the description of a translated page."""
    return [f"{language_file(code, f'{page.slug}.md')}: page '{page.slug}': the {label} holds a coded reference"
            for label, value in (("title", page.title), ("description", page.description)) if CODED_REFERENCE.search(value)]


def add_translation(context: LanguageContext, page: Page) -> None:
    """Adds the translated copy and text of `page` to the context, and its template (`home.html`): raw HTML that gets the DS-21 check
    English sources get. Raises I18nError for a file that is missing or cannot be read."""
    code, translations = context.code, context.translations
    mine = translations.page(code, page.slug)
    if mine is None:
        return
    body = expand_includes(translations.body(code, page.slug), context.english.root, language_file(code, f"{page.slug}.md"))
    if page.template:
        name = Path(page.template).name
        own = translations.template(code, page.template)
        if own is None:
            raise site_i18n.I18nError(f"{language_file(code, name)} does not exist; the document '{page.slug}' needs it")
        problem = unsafe_markup(own)
        if problem:
            context.errors.append(f"{language_file(code, name)}: page '{page.slug}' holds {problem}, which the site never publishes")
        context.templates[page.template] = own
    context.bodies[page.slug] = body
    context.pages[page.slug] = mine
    context.errors.extend(coded_reference_errors(code, mine))


def language_context(english: SiteBuild, code: str, translations: site_i18n.Translations, ui: dict) -> LanguageContext:
    """The translated copy and text of each translated-scope page the language has a file for; a file that cannot be read is an error and
    the page counts as not translated."""
    context = LanguageContext(code, english, ui, translations)
    for page in english.pages:
        if page.scope != "translated":
            continue
        try:
            add_translation(context, page)
        except site_i18n.I18nError as error:
            context.errors.append(str(error))
            context.pages.pop(page.slug, None)
            context.bodies.pop(page.slug, None)
    return context


def language_contexts(root: Path, english: SiteBuild, codes: list[str]) -> list[LanguageContext]:
    """The context of each language of `codes`; an interface file that is missing or lacks a key of the English one is a configuration error."""
    if not codes:
        return []
    translations = site_i18n.Translations(root, english.pages_by_slug)
    try:
        reference = site_i18n.load_ui(root, site_i18n.ENGLISH)
        return [language_context(english, code, translations, site_i18n.load_ui(root, code, reference)) for code in codes]
    except site_i18n.I18nError as error:
        raise BuildError(str(error)) from error


def build(root: Path, out_dir: Path, base_url: str | None = None, preview: tuple[str, ...] = ()) -> list[str]:
    """Build the English site, then each enabled language (and each of `preview`, which may be disabled) into `<out_dir>/<path>/`; returns the
    list of errors (empty when every link resolves and every rule id exists), those of a language prefixed with its code (spec
    004-site-languages, FR-024). A language that is not built is cleared from the output."""
    config = load_config(root)
    base = normalise_base_url(base_url, "--base-url") if base_url is not None else config.get("baseUrl", "")
    english = SiteBuild(root, config, base)
    try:
        codes = site_i18n.languages_to_build(config, tuple(preview))
    except site_i18n.I18nError as error:
        raise BuildError(str(error)) from error
    contexts = language_contexts(root, english, codes)
    if contexts:
        notes = {context.code: context.ui["english_only"] for context in contexts}
        english.langset = site_i18n.language_set(config, base, codes, site_i18n.Translations(root, english.pages_by_slug), notes)
        english.langset.translated = {context.code: set(context.pages) for context in contexts}
    errors = english.run(out_dir)
    for code in site_i18n.enabled_languages(config):
        errors += site_i18n.check_enable_gate(root, code)
    for context in contexts:
        errors += [f"[{context.code}] {error}" for error in SiteBuild(root, config, base, context).run(out_dir)]
    return errors


def main(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Build the Craticula docs site (see the module docstring).")
    parser.add_argument("--root", type=Path, default=default_root, help="repository root (default: this checkout)")
    parser.add_argument("--out", type=Path, default=None, help="output folder (default: <root>/site/_build)")
    parser.add_argument("--base-url", default=None, help="the https address the llms files link to (default: baseUrl of site/site.json; none = relative links)")
    parser.add_argument("--preview-languages", default="", help="comma-separated codes of disabled languages to build as well, to read their drafts (never for the published site)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    out_dir = (args.out or root / "site" / "_build").resolve()
    try:
        errors = build(root, out_dir, args.base_url, tuple(code for code in args.preview_languages.split(",") if code))
    except BuildError as error:
        print(f"build_site: {error}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as error:
        print(f"build_site: {error}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"build_site: {error}", file=sys.stderr)
        print(f"build_site: {len(errors)} problem(s); the site was written to {out_dir} but must not be published.", file=sys.stderr)
        return 1

    print(f"build_site: built {len(list(out_dir.glob('*.html')))} page(s) into {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
