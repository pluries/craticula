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
reference tables, `"generator": "rules-index"` lists every rule id of the rule source (`spec/semantics.md`) with a link to its
anchor. A paragraph that opens with a bold rule id (`**GRP-7. ...**`) and a heading that opens with one (`## SEM-1. ...`) get an
anchor of that id (`#grp-7`, `#sem-1`), and the build fails when a page mentions a rule id (of the prefixes in `ruleIdPrefixes`)
that the rule source does not define.

    python3 scripts/build_site.py [--out DIR] [--root DIR]

Exit codes: 0 built and every link resolves, 1 a link is dead or private, 2 bad usage or an unreadable configuration.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The private paths of scripts/publish-github.sh (its PRIVATE array): what the public mirror does not carry, so a link to one is
# dead there. test_build_site.py pins this tuple to the real array where that script exists (the private repository).
PRIVATE_PATHS = ("docs", ".claude", "CLAUDE.md", ".mcp.json", ".githooks", ".azuredevops", ".sonarlint", ".vscode",
                 "scripts/publish-github.sh", "scripts/sync-release-commit.sh", "scripts/apply-public-change.sh",
                 "scripts/test_apply_public_change.py", "scripts/test_publish_mirror_real.py", "scripts/test_jenkinsfile.py",
                 "scripts/test_release_steps.py", "scripts/release-steps-fixtures",
                 "csharp/tests/Craticula.Conformance.Tests/JenkinsfileTests.cs", "Jenkinsfile", "jenkins")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)")
ALLOWED_SCHEMES = ("http:", "https:", "mailto:")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


def render_markdown(source: str, resolve=lambda href, image=False: href) -> Rendered:
    """Markdown to HTML for the subset the repository's documents use (headings, paragraphs, lists, tables, fenced code,
    block quotes, rules, inline code, links, emphasis). Raw HTML in the source is escaped, never passed through."""
    source = source.replace("\x00", "\ufffd")  # NUL marks this converter's placeholders
    out = Rendered(html="")
    slugs = Slugger()
    body: list[str] = []
    lines = source.replace("\r\n", "\n").split("\n")
    i = 0

    def inline(text: str, number: int) -> str:
        return _inline(text, number, out, resolve)

    while i < len(lines):
        line = lines[i]
        number = i + 1

        if not line.strip():
            i += 1
            continue

        fence = _FENCE.match(line)
        if fence:
            marker, language = fence.group(2), fence.group(3)
            indent = len(fence.group(1))
            i += 1
            code: list[str] = []
            while i < len(lines) and not re.match(rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$", lines[i]):
                code.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(language)}"' if language else ""
            body.append(f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
            continue

        heading = _HEADING.match(line)
        if heading:
            level, text = len(heading.group(1)), heading.group(2)
            plain = re.sub(r"[`*]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text))
            anchor = slugs(plain)
            out.anchors.add(anchor)
            out.headings.append((level, plain, anchor))
            alias = ""
            rule = _RULE_HEADING.match(text)
            if rule:  # `## SEM-1. Case sensitivity` is also reachable as `#sem-1`
                anchor_id = rule_anchor(rule.group(1))
                out.anchors.add(anchor_id)
                alias = f'<a id="{anchor_id}"></a>'
            if level == 1 and not out.title:
                out.title = re.sub(r"[`*]", "", text)
            body.append(f'<h{level} id="{anchor}">{alias}{inline(text, number)}</h{level}>')
            i += 1
            continue

        if _RULE.match(line):
            body.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            quote: list[str] = []
            start = i
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = render_markdown("\n".join(quote), resolve)
            out.links.extend((start + n, href) for n, href in inner.links)
            out.anchors.update(inner.anchors)
            body.append(f"<blockquote>{inner.html}</blockquote>")
            continue

        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
            head = _cells(line)
            i += 2
            rows: list[tuple[int, list[str]]] = []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                rows.append((i + 1, _cells(lines[i])))
                i += 1
            parts = ["<table><thead><tr>" + "".join(f"<th>{inline(c, number)}</th>" for c in head) + "</tr></thead><tbody>"]
            for row_number, cells in rows:
                parts.append("<tr>" + "".join(f"<td>{inline(c, row_number)}</td>" for c in cells) + "</tr>")
            parts.append("</tbody></table>")
            body.append("".join(parts))
            continue

        if _LIST.match(line):
            # (line, indent, ordered, parts): a part is a list of text lines or an HTML string for a fenced block, in source order
            items: list[tuple[int, int, bool, list]] = []
            while i < len(lines):
                m = _LIST.match(lines[i])
                if m:
                    items.append((i + 1, len(m.group(1).expandtabs(4)), m.group(2)[0].isdigit(), [[m.group(3)]]))
                    i += 1
                elif not lines[i].strip():
                    # A blank line stays inside the list only when an indented list item or fenced block follows it.
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if items and j < len(lines) and lines[j].startswith(("  ", "\t")) and (_FENCE.match(lines[j]) or _LIST.match(lines[j])):
                        i = j
                    else:
                        break
                elif items and lines[i].startswith((" ", "\t")) and _FENCE.match(lines[i]):
                    opener = _FENCE.match(lines[i])
                    marker, language, indent = opener.group(2), opener.group(3), len(opener.group(1))
                    i += 1
                    code = []
                    while i < len(lines) and not re.match(rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$", lines[i]):
                        code.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                        i += 1
                    i += 1
                    cls = f' class="language-{html.escape(language)}"' if language else ""
                    items[-1][3].append(f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
                elif lines[i].strip() and lines[i].startswith((" ", "\t")) and items:
                    if isinstance(items[-1][3][-1], str):  # text after a fenced block is a new paragraph of the item
                        items[-1][3].append([])
                    items[-1][3][-1].append(lines[i].strip())
                    i += 1
                else:
                    break
            body.append(_render_list(items, inline))
            continue

        paragraph = [line.strip()]
        start = number
        i += 1
        while i < len(lines) and lines[i].strip() and not (
            _HEADING.match(lines[i]) or _FENCE.match(lines[i]) or _LIST.match(lines[i])
            or lines[i].lstrip().startswith(">") or _RULE.match(lines[i])
            or ("|" in lines[i] and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]))
        ):
            paragraph.append(lines[i].strip())
            i += 1
        joined = " ".join(paragraph)
        opener = _RULE_OPENER.match(joined)
        attribute = ""
        if opener:  # `**GRP-7. A ...**` opens a rule: give the paragraph the anchor `#grp-7`
            anchor_id = rule_anchor(opener.group(1))
            if anchor_id not in out.anchors:
                out.anchors.add(anchor_id)
                attribute = f' id="{anchor_id}"'
        body.append(f"<p{attribute}>{inline(joined, start)}</p>")

    out.html = "\n".join(body)
    return out


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


def render_sidebar(pages: list["Page"], current_slug: str) -> str:
    """FR-32, task #3474: one block per group in first-appearance order, the current page marked aria-current."""
    groups: dict[str, list[Page]] = {}
    for page in pages:
        groups.setdefault(page.group or "", []).append(page)
    current = ' aria-current="page"'  # not inline in the f-string: a backslash there needs Python 3.12 (the floor is 3.10)
    blocks = []
    for name, members in groups.items():
        items = "".join(
            f'<li><a href="{html.escape(p.slug)}.html"{current if p.slug == current_slug else ""}>{html.escape(p.title)}</a></li>'
            for p in members)
        blocks.append(f'<div class="side-group"><p class="side-title">{html.escape(name)}</p><ul>{items}</ul></div>')
    return "".join(blocks)


def render_toc(rendered: Rendered) -> str:
    """FR-32, task #3474: the 'On this page' block of the level-2 headings, or '' when there are none."""
    links = "".join(f'<li><a href="#{html.escape(anchor)}">{html.escape(text)}</a></li>' for level, text, anchor in rendered.headings if level == 2)
    return f'<p class="side-title">On this page</p><ul>{links}</ul>' if links else ""


GENERATORS = ("schema-reference", "rules-index")


def load_config(root: Path) -> dict:
    path = root / "site" / "site.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BuildError(f"cannot read {path}: {error}") from error
    for key in ("title", "repo", "branch", "pages"):
        if key not in config:
            raise BuildError(f"{path}: missing '{key}'")
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
        elif generator == "rules-index":
            entry["source"] = config["ruleSource"]
        if not isinstance(entry.get("source"), str):
            raise BuildError(f"{path}: page '{entry['slug']}' needs a string 'source' (or the 'schema' / 'ruleSource' its generator reads)")
        if not SLUG.match(entry["slug"]):
            raise BuildError(f"{path}: page slug '{entry['slug']}' must match [a-z0-9][a-z0-9-]*")
        if not isinstance(entry.get("group"), str) or not entry["group"].strip():
            raise BuildError(f"{path}: page '{entry['slug']}' needs a non-empty string 'group' (the sidebar block it belongs to)")
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


def rules_index(text: str, rules_page: str) -> str:
    rows = [f"| [{rule}]({rules_page}.html#{rule_anchor(rule)}) | {_cell(title)} |" for rule, title in rule_definitions(text).items()]
    return "\n".join([
        "# Rule index", "",
        "Every numbered rule of the semantics specification, in document order. Each id links to the rule itself.", "",
        "| Rule | Starts with |", "|---|---|", *rows, ""])


_INCLUDE = re.compile(r"^\{\{include\s+(\S+)\s+([\w-]*)\}\}\s*$")
_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})")


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
                 pages_by_slug: dict[str, Page] | None = None, page_anchors=None, label: str | None = None) -> str:
    """The href to emit for `href` found in `source`, or the original one after recording an error."""
    where = f"{label or source}:{line}"
    if EXTERNAL.match(href):
        if not href.lower().startswith(ALLOWED_SCHEMES):
            errors.append(f"{where}: link '{href[:40]}' uses a scheme other than http, https or mailto")
        return href
    path_part, _, fragment = href.partition("#")
    if not path_part:
        if fragment and fragment not in own_anchors:
            errors.append(f"{where}: dead anchor '#{fragment}'")
        return href
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


def fill_template(template: str, values: dict[str, str]) -> str:
    """One pass: a value that itself contains {{...}} (page content may) is never substituted again."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def build(root: Path, out_dir: Path) -> list[str]:
    """Build the site; returns the list of errors (empty when every link resolves and every rule id exists)."""
    config = load_config(root)
    pages = [Page(p["slug"], p["title"], p["source"], p.get("generator"), group=p["group"], template=p.get("template")) for p in config["pages"]]
    pages_by_slug = {p.slug: p for p in pages}
    pages_by_source = {p.source: p for p in pages if p.generator is None}
    page_of_file = {os.path.basename(p.source): p.slug for p in pages if p.generator == "schema-reference"}
    errors: list[str] = []

    text_cache: dict[str, str] = {}

    def read(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8")

    def page_text(page: Page) -> str:
        """The Markdown of a page: the file itself, or what its generator makes of the file."""
        if page.slug not in text_cache:
            if page.generator == "schema-reference":
                try:
                    schema = json.loads(read(page.source))
                except ValueError as error:
                    raise BuildError(f"{page.source}: not valid JSON: {error}") from error
                text_cache[page.slug] = schema_reference(schema, os.path.basename(page.source), page_of_file)
            elif page.generator == "rules-index":
                semantics = next((p for p in pages if p.source == config["ruleSource"] and p.generator is None), None)
                text_cache[page.slug] = rules_index(read(page.source), semantics.slug if semantics else "semantics")
            else:
                text_cache[page.slug] = expand_includes(read(page.source), root, page.source)
        return text_cache[page.slug]

    anchor_cache: dict[str, set[str]] = {}

    def page_anchors(slug: str) -> set[str]:
        if slug not in anchor_cache:
            try:
                anchor_cache[slug] = render_markdown(page_text(pages_by_slug[slug])).anchors
            except (OSError, UnicodeDecodeError):
                anchor_cache[slug] = set()
        return anchor_cache[slug]

    file_anchor_cache: dict[str, set[str]] = {}

    def anchors_of(rel: str) -> set[str]:
        """Anchors of a Markdown file of the repository (a page's own are computed from its text)."""
        if rel in pages_by_source:
            return page_anchors(pages_by_source[rel].slug)
        if rel not in file_anchor_cache:
            try:
                file_anchor_cache[rel] = render_markdown(read(rel)).anchors
            except (OSError, UnicodeDecodeError):
                file_anchor_cache[rel] = set()
        return file_anchor_cache[rel]

    templates = {rel: read(rel) for rel in {"site/template.html", *(p.template for p in pages if p.template)}}
    style = read("site/style.css")
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.html"):  # a page removed from site.json must not linger in the output
        stale.unlink()
    (out_dir / "style.css").write_text(style, encoding="utf-8")
    fonts_in, fonts_out = root / "site" / "fonts", out_dir / "fonts"
    if fonts_out.is_dir():  # a font removed from site/fonts must not linger in the output
        for stale_font in fonts_out.iterdir():
            if stale_font.is_file():
                stale_font.unlink()
    if fonts_in.is_dir():
        fonts_out.mkdir(exist_ok=True)
        for font in sorted(fonts_in.iterdir()):
            if font.is_file():
                (fonts_out / font.name).write_bytes(font.read_bytes())

    nav = "".join(f'<li><a href="{html.escape(p.slug)}.html">{html.escape(p.title)}</a></li>' for p in pages)
    texts: dict[str, str] = {}

    for page in pages:
        try:
            text = page_text(page)
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"site/site.json: page '{page.slug}': cannot read {page.source}: {error}")
            continue
        texts[page.source if page.generator is None else f"{page.source} (page '{page.slug}')"] = text
        own = page_anchors(page.slug)
        link_errors: list[str] = []
        rendered = render_markdown(text, resolve=lambda href, image=False: href)
        # Second pass with the real resolver, now that the page's own anchors are known; the line of each link is taken
        # from the first pass's record, in order.
        lines = iter(line for line, _ in rendered.links)
        source_for_links = page.source if page.generator is None else f"site/site.json#{page.slug}"

        def resolver(href: str, image: bool = False, source=page.source if page.generator is None else "site/_generated", own=own,
                     sink=link_errors, lines=lines, label=source_for_links if page.generator else None) -> str:
            return resolve_link(href, source, pages_by_source, root, config, anchors_of, sink, next(lines, 0), own, raw=image,
                                pages_by_slug=pages_by_slug, page_anchors=page_anchors, label=label)

        rendered = render_markdown(text, resolve=resolver)
        errors.extend(link_errors)
        page.rendered = rendered

        values = {
            "site_title": html.escape(config["title"]),
            "page_title": html.escape(page.title),
            "nav": nav,
            "sidebar": render_sidebar(pages, page.slug),
            "toc": render_toc(rendered),
            "content": rendered.html,
            "source": html.escape(page.source),
            "source_url": html.escape(f"{config['repo'].rstrip('/')}/blob/{config['branch']}/{page.source}"),
        }
        page_html = fill_template(templates[page.template or "site/template.html"], values)
        (out_dir / f"{page.slug}.html").write_text(page_html, encoding="utf-8")

    if config["ruleSource"]:
        try:
            errors.extend(check_rule_ids(texts, read(config["ruleSource"]), config["ruleIdPrefixes"]))
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"site/site.json: cannot read the rule source {config['ruleSource']}: {error}")

    return errors


def main(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Build the Craticula docs site (see the module docstring).")
    parser.add_argument("--root", type=Path, default=default_root, help="repository root (default: this checkout)")
    parser.add_argument("--out", type=Path, default=None, help="output folder (default: <root>/site/_build)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    out_dir = (args.out or root / "site" / "_build").resolve()
    try:
        errors = build(root, out_dir)
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
