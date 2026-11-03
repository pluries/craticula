#!/usr/bin/env python3
"""Tests of llms.txt, llms-full.txt and the Markdown copy of every page of the docs site v2 (story #3554, task #3560; plan
docs/feat/3560/plan.md; DS-13, DS-14, DSN-6). Offline, standard library only; scratch sites for the format and the configuration,
the real sources for the acceptance checks.

Contract pinned here:
  * site.json optional `baseUrl` (an https address, no query, no fragment, no credentials; one trailing slash is dropped) and optional `summary`
    (one sentence). `build_site.build(root, out_dir, base_url=None)`; `--base-url <url>` of the command line is passed as `base_url` and
    wins over site.json. A baseUrl that is not an https address is a BuildError (exit 2 from main), from either source.
  * `llms.txt`, UTF-8, LF, one trailing newline, exactly:
        # <site title>
        <blank>
        > <summary: site.json `summary`, else the description of the home page>
        <blank>
        ## Home                         (the home page alone, first)
        <blank>
        - [<page title>](<base>/index.md): <description>
        <blank>
        ## <Group>                      (each non-empty group of build_site.GROUPS, in that order)
        <blank>
        - [<Title>](<base>/<slug>.md): <description>     (the pages of the group in sidebar order, subgroup pages in place)
    `<base>/` is dropped when there is no base address, so a preview never points at the production host. Every page appears once.
  * `llms-full.txt`: for the home page, then every other page in sidebar order, `==== <Title> | <slug>.md ====`, a blank line and the
    text of `<slug>.md` without trailing newlines; the blocks are joined by one blank line and the file ends with one newline.
  * `<slug>.md` for every page, next to its html: the text the page was built from (a plain page: its source byte for byte with the
    `{{include}}` lines expanded; a generated page: the Markdown it was generated as).
  * The build removes every `*.md` and the two llms files of an earlier build before it writes, like the `*.html` files.
Run: python3 scripts/test_build_site_llms.py
"""
import contextlib
import html
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site import ROOT  # noqa: E402
from test_build_site_features import fsite  # noqa: E402
from test_build_site_structure import SPLIT_SLUGS, SUMMARIES, meta_description, page, sidebar  # noqa: E402

# repeated literals (SonarQube S1192)
LLMS_TXT = "llms.txt"
SEMANTICS_MD = "semantics.md"
SITE_SUMMARIES_JSON = "site/summaries.json"
LLMS_FULL_TXT = "llms-full.txt"
DOCS_X_MD = "docs/x.md"
SITE_JSON = "site.json"
HTML_GLOB = "*.html"

PAGES = [page("index", None, "Home"), page("a", "Guides", "Alpha"), page("b", "Reference", "Beta", subgroup="Sub"), page("c", "Reference", "Gamma")]
PROD = "https://docs.example.test/craticula"
PREVIEW = "https://preview.example.test/pr-7"
HOME_DESCRIPTION = "The index page."
# Negative cases of the base-address check: the insecure schemes and the login part are assembled, so no literal insecure URL or
# credential-shaped address stands in the source (SonarQube S5332 and S2068); nothing here is ever fetched.
PLAIN_SCHEME = "ht" + "tp"
FILE_TRANSFER_SCHEME = "f" + "tp"
BAD_HOST = "docs.example.test"
LOGIN = ":".join(("user", "pw")) + "@"
SECRET_WORDS = ("-----BEGIN", "ghp_", "github_pat_", "Authorization:")


def llms_site(pages: list[dict] | None = None, files: dict[str, str] | None = None, **extra) -> Path:
    return fsite(pages or PAGES, files, **extra)


def build_out(root: Path, base_url: str | None = None) -> tuple[list[str], Path]:
    out = root / "_out"
    errors = bs.build(root, out) if base_url is None else bs.build(root, out, base_url=base_url)
    return errors, out


def read(out: Path, name: str) -> str:
    path = out / name
    assert path.is_file(), f"{name} is not written"
    return path.read_text(encoding="utf-8")


def sidebar_rows(out: Path, any_docs_page: str) -> list[tuple[str, str, str, str]]:
    """(group, slug, label, description) of the sidebar of a built docs page, in order."""
    text = (out / f"{any_docs_page}.html").read_text(encoding="utf-8")
    rows = []
    for path, href, label, _ in sidebar(text).links:
        slug = href.removesuffix(".html")
        rows.append((path[0], slug, label, html.unescape(meta_description((out / href).read_text(encoding="utf-8")))))
    return rows


def expected_llms(out: Path, title: str, summary: str, base: str, home_title: str = "Home", docs_page: str = "a") -> str:
    prefix = f"{base}/" if base else ""
    home = html.unescape(meta_description((out / "index.html").read_text(encoding="utf-8")))
    lines = [f"# {title}", "", f"> {summary}", "", "## Home", "", f"- [{home_title}]({prefix}index.md): {home}"]
    current = ""
    for group, slug, label, description in sidebar_rows(out, docs_page):
        if group != current:
            lines += ["", f"## {group}", ""]
            current = group
        lines.append(f"- [{label}]({prefix}{slug}.md): {description}")
    return "\n".join(lines) + "\n"


def expected_full(out: Path, home_title: str = "Home", docs_page: str = "a") -> str:
    blocks = [("index", home_title)] + [(slug, label) for _, slug, label, _ in sidebar_rows(out, docs_page)]
    return "\n\n".join(f"==== {label} | {slug}.md ====\n\n{read(out, slug + '.md').rstrip(chr(10))}" for slug, label in blocks) + "\n"


class ScratchLlms(unittest.TestCase):
    """DS-13: llms.txt and llms-full.txt on scratch sites."""

    def test_13_llms_txt_follows_the_llmstxt_shape_with_relative_links_when_no_base_address_is_given(self):
        errors, out = build_out(llms_site())
        self.assertEqual(errors, [])
        self.assertEqual(expected_llms(out, "T", "The index page.", ""), read(out, LLMS_TXT))
        self.assertNotIn("https://", read(out, LLMS_TXT))

    def test_13_the_summary_comes_from_site_json_when_it_names_one(self):
        errors, out = build_out(llms_site(summary="A one-sentence summary of the site."))
        self.assertEqual(errors, [])
        self.assertEqual(expected_llms(out, "T", "A one-sentence summary of the site.", ""), read(out, LLMS_TXT))

    def test_13_site_json_base_url_makes_the_links_absolute_and_a_trailing_slash_is_dropped(self):
        for base in (PROD, PROD + "/"):
            with self.subTest(base=base):
                errors, out = build_out(llms_site(baseUrl=base))
                self.assertEqual(errors, [])
                self.assertEqual(expected_llms(out, "T", HOME_DESCRIPTION, PROD), read(out, LLMS_TXT))
                self.assertNotIn(PROD + "//", read(out, LLMS_TXT))

    def test_13_the_base_url_argument_wins_over_site_json_and_over_nothing(self):
        errors, out = build_out(llms_site(baseUrl=PROD), base_url=PREVIEW + "/")
        self.assertEqual(errors, [])
        text = read(out, LLMS_TXT)
        self.assertEqual(expected_llms(out, "T", HOME_DESCRIPTION, PREVIEW), text)
        self.assertNotIn(PROD, text)
        errors, out = build_out(llms_site(), base_url=PREVIEW)
        self.assertEqual(expected_llms(out, "T", HOME_DESCRIPTION, PREVIEW), read(out, LLMS_TXT))

    def test_13_the_command_line_flag_reaches_the_build(self):
        root = llms_site(baseUrl=PROD)
        code, err = run_cli_with(root, ["--base-url", PREVIEW])
        self.assertEqual((0, ""), (code, err), err)
        self.assertIn(f"]({PREVIEW}/a.md)", read(root / "_out", LLMS_TXT))

    def test_13_a_base_url_that_is_not_an_https_address_is_a_configuration_error(self):
        bad = (f"{PLAIN_SCHEME}://{BAD_HOST}", f"{FILE_TRANSFER_SCHEME}://{BAD_HOST}", BAD_HOST, "https://", "https:///x", f"https://{BAD_HOST}/?a=1",
               f"https://{BAD_HOST}/#top", f"https://{LOGIN}{BAD_HOST}", "https://docs example.test", "")
        for value in bad:
            with self.subTest(base=value):
                with self.assertRaises(bs.BuildError):
                    bs.build(llms_site(baseUrl=value), Path(tempfile.mkdtemp()))
                with self.assertRaises(bs.BuildError):
                    bs.build(llms_site(), Path(tempfile.mkdtemp()), base_url=value)

    def test_13_main_exits_2_on_a_bad_base_url_from_the_flag_or_from_site_json(self):
        code, err = run_cli_with(llms_site(), ["--base-url", f"{PLAIN_SCHEME}://{BAD_HOST}"])
        self.assertEqual(2, code)
        self.assertIn("baseUrl", err)
        code, err = run_cli_with(llms_site(baseUrl=f"{PLAIN_SCHEME}://{BAD_HOST}"), [])
        self.assertEqual(2, code)
        self.assertIn("baseUrl", err)

    def test_13_every_page_is_listed_exactly_once_and_only_non_empty_groups_have_a_section(self):
        errors, out = build_out(llms_site())
        self.assertEqual(errors, [])
        text = read(out, LLMS_TXT)
        slugs = re.findall(r"\]\(([a-z0-9-]+)\.md\)", text)
        self.assertEqual(sorted(slugs), sorted(p.stem for p in out.glob(HTML_GLOB)))
        self.assertEqual(re.findall(r"(?m)^## (.+)$", text), ["Home", "Guides", "Reference"])
        self.assertEqual(1, text.count("](index.md)"))

    def test_13_llms_full_holds_every_title_and_text_home_first_then_in_sidebar_order(self):
        errors, out = build_out(llms_site())
        self.assertEqual(errors, [])
        self.assertEqual(expected_full(out), read(out, LLMS_FULL_TXT))

    def test_13_split_pages_are_listed_in_the_reference_section_in_place(self):
        files = {SEMANTICS_MD: "# Semantics\n\nIntro.\n\n## SEM-1. Case sensitivity\n\nBody one.\n", SITE_SUMMARIES_JSON: json.dumps({"SEM-1": SUMMARIES["SEM-1"]})}
        split = {"slug": "semantics", "title": "Semantics", "source": SEMANTICS_MD, "generator": "semantics-split",
                 "summaries": SITE_SUMMARIES_JSON, "group": "Reference", "description": "The rules behind the output."}
        errors, out = build_out(llms_site([PAGES[0], PAGES[1], split], files))
        self.assertEqual(errors, [])
        text = read(out, LLMS_TXT)
        self.assertEqual(expected_llms(out, "T", HOME_DESCRIPTION, ""), text)
        self.assertIn(f"- [Case rules](case-rules.md): {SUMMARIES['SEM-1']['description']}", text)
        self.assertEqual(1, text.count("](semantics.md)"))


class ScratchMarkdownPages(unittest.TestCase):
    """DS-14: <slug>.md next to every page."""

    def test_14_a_plain_page_has_its_source_byte_for_byte(self):
        source = "# Plain\n\nText with `code` and a [link](other.md).\n\n```sql\nSELECT 1;\n```\n"
        errors, out = build_out(llms_site(files={"a.md": source}))
        self.assertEqual(errors, [])
        self.assertEqual(source, (out / "a.md").read_bytes().decode("utf-8"))
        for slug in ("index", "b", "c"):
            self.assertTrue((out / f"{slug}.md").is_file(), slug)

    def test_14_an_include_is_expanded_as_the_page_shows_it(self):
        files = {"a.md": "# Included\n\n{{include snippet.txt text}}\n\nafter\n", "snippet.txt": "line one\nline two\n"}
        errors, out = build_out(llms_site(files=files))
        self.assertEqual(errors, [])
        text = read(out, "a.md")
        self.assertNotIn("{{include", text)
        self.assertIn("line one\nline two", text)
        self.assertTrue(text.endswith("after\n"))

    def test_14_a_generated_schema_page_has_the_generated_markdown(self):
        schema = {"title": "Demo", "$id": "https://example.test/demo.json", "type": "object", "properties": {"name": {"type": "string"}}}
        pages = [PAGES[0], PAGES[1], {"slug": "demo", "title": "Demo", "generator": "schema-reference", "schema": "demo.schema.json",
                                      "group": "Reference", "description": "The demo schema."}]
        errors, out = build_out(llms_site(pages, {"demo.schema.json": json.dumps(schema)}))
        self.assertEqual(errors, [])
        text = read(out, "demo.md")
        self.assertTrue(text.startswith("# Demo reference"))
        self.assertIn("| `name` |", text)
        self.assertNotIn("{{", text)

    def test_14_split_semantics_pages_have_their_own_markdown_with_title_and_summary(self):
        files = {SEMANTICS_MD: "# Semantics\n\nIntro.\n\n## SEM-1. Case sensitivity\n\nBody one.\n", SITE_SUMMARIES_JSON: json.dumps({"SEM-1": SUMMARIES["SEM-1"]})}
        split = {"slug": "semantics", "title": "Semantics", "source": SEMANTICS_MD, "generator": "semantics-split",
                 "summaries": SITE_SUMMARIES_JSON, "group": "Reference", "description": "The rules behind the output."}
        errors, out = build_out(llms_site([PAGES[0], PAGES[1], split], files))
        self.assertEqual(errors, [])
        part = read(out, f"{SPLIT_SLUGS['SEM-1']}.md")
        for needle in ("# Case rules", SUMMARIES["SEM-1"]["summary"], "Body one."):
            self.assertIn(needle, part)
        index = read(out, SEMANTICS_MD)
        self.assertIn("# Semantics", index)
        self.assertIn(SUMMARIES["SEM-1"]["summary"], index)

    def test_14_every_html_page_has_a_markdown_file_and_the_other_way_round(self):
        errors, out = build_out(llms_site())
        self.assertEqual(errors, [])
        self.assertEqual(sorted(p.stem for p in out.glob(HTML_GLOB)), sorted(p.stem for p in out.glob("*.md")))


class ScratchOutputsAreStableAndClean(unittest.TestCase):
    """DSN-6 and the cleaning of the output folder."""

    def test_6_two_builds_give_identical_bytes_for_the_three_kinds_of_output(self):
        root = llms_site(baseUrl=PROD)
        _, first = build_out(root)
        second = Path(tempfile.mkdtemp()) / "again"
        self.assertEqual(bs.build(root, second), [])
        names = [LLMS_TXT, LLMS_FULL_TXT, *(p.name for p in sorted(first.glob("*.md")))]
        self.assertEqual(["a.md", "b.md", "c.md", "index.md"], sorted(n for n in names if n.endswith(".md")))
        for name in names:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)

    def test_6_a_page_removed_from_site_json_leaves_no_markdown_and_no_listing_behind(self):
        root = llms_site()
        _, out = build_out(root)
        (out / "ghost.md").write_text("# left over\n", encoding="utf-8")
        self.assertTrue((out / "c.md").is_file())
        config = json.loads((root / "site" / SITE_JSON).read_text(encoding="utf-8"))
        config["pages"] = [p for p in config["pages"] if p["slug"] != "c"]
        (root / "site" / SITE_JSON).write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(bs.build(root, out), [])
        self.assertFalse((out / "c.md").exists())
        self.assertFalse((out / "ghost.md").exists())
        self.assertNotIn("](c.md)", read(out, LLMS_TXT))
        self.assertNotIn("c.md", read(out, LLMS_FULL_TXT))

    def test_6_a_source_under_a_private_path_is_still_refused_and_no_output_names_it(self):
        pages = [PAGES[0], page("secret", "Guides", source=DOCS_X_MD)]
        root = llms_site(pages, {DOCS_X_MD: "# Secret\n"})
        with self.assertRaises(bs.BuildError):
            bs.build(root, root / "_out")
        root = llms_site(files={"a.md": "# A\n\n{{include docs/x.md text}}\n", DOCS_X_MD: "private\n"})
        with self.assertRaises(bs.BuildError):
            bs.build(root, root / "_out")
        for name in (LLMS_TXT, LLMS_FULL_TXT, "a.md"):
            self.assertFalse((root / "_out" / name).exists() and "private" in (root / "_out" / name).read_text(encoding="utf-8"), name)


def run_cli_with(root: Path, extra: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = bs.main(["--root", str(root), "--out", str(root / "_out"), *extra])
    return code, err.getvalue()


class RealSite(unittest.TestCase):
    """The acceptance tests on this repository's own sources."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        cls.errors = bs.build(ROOT, cls.out)
        cls.config = json.loads((ROOT / "site" / SITE_JSON).read_text(encoding="utf-8"))
        cls.base = cls.config.get("baseUrl", "")
        cls.pages = sorted(p.stem for p in cls.out.glob(HTML_GLOB))

    def test_the_real_sources_still_build_without_errors(self):
        self.assertEqual(self.errors, [])

    def test_13_site_json_names_the_production_base_address_as_an_https_address_without_a_trailing_slash(self):
        self.assertRegex(self.base, r"^https://[^/?#@\s]+(?:/[^?#\s]*)?$")
        self.assertFalse(self.base.endswith("/"))

    def test_13_llms_txt_is_the_exact_listing_of_every_page_with_absolute_links(self):
        self.assertTrue(self.base, "site.json has no baseUrl")
        title = self.config["title"]
        home = next(p for p in self.config["pages"] if p["slug"] == "index")
        summary = self.config.get("summary", home["description"])
        docs_page = next(slug for slug in self.pages if slug != "index")
        self.assertEqual(expected_llms(self.out, title, summary, self.base, home["title"], docs_page), read(self.out, LLMS_TXT))

    def test_13_every_built_page_is_listed_once_in_llms_txt_and_has_a_markdown_file(self):
        text = read(self.out, LLMS_TXT)
        listed = re.findall(r"\]\(" + re.escape(self.base) + r"/([a-z0-9-]+)\.md\)", text)
        self.assertEqual(sorted(listed), self.pages)
        self.assertEqual(self.pages, sorted(p.stem for p in self.out.glob("*.md")))
        used = {entry["group"] for entry in self.config["pages"] if entry.get("group")}
        self.assertEqual(["Home", *(g for g in bs.GROUPS if g in used)], re.findall(r"(?m)^## (.+)$", text))

    def test_13_llms_full_holds_each_page_in_the_agreed_blocks(self):
        docs_page = next(slug for slug in self.pages if slug != "index")
        home_title = next(p["title"] for p in self.config["pages"] if p["slug"] == "index")
        self.assertEqual(expected_full(self.out, home_title, docs_page), read(self.out, LLMS_FULL_TXT))

    def test_13_a_preview_build_never_points_at_the_production_host(self):
        self.assertTrue(self.base, "site.json has no baseUrl")
        out = Path(tempfile.mkdtemp()) / "preview"
        self.assertEqual(bs.build(ROOT, out, base_url=PREVIEW), [])
        text = read(out, LLMS_TXT)
        self.assertNotIn(self.base, text)
        self.assertEqual(len(self.pages), text.count(f"]({PREVIEW}/"))

    def test_14_the_markdown_files_hold_no_unexpanded_include_and_no_rendered_markup(self):
        for slug in self.pages:
            with self.subTest(page=slug):
                text = read(self.out, f"{slug}.md")
                self.assertTrue(text.strip())
                self.assertNotIn("{{include", text)
                self.assertNotRegex(text, r"</?(?:p|h[1-6]|ul|li|table|pre)[ >]")

    def private_link_targets(self, text: str) -> list[str]:
        """The Markdown link targets and hrefs of an output that point into a private path (relative, or on the repository's GitHub address)."""
        found = []
        for target in re.findall(r"\]\(([^)\s]+)", text) + re.findall(r'href="([^"]+)"', text):
            path = target.partition("#")[0].partition("?")[0]
            match = re.match(r"https://github\.com/[^/]+/[^/]+/(?:blob|tree|raw)/[^/]+/(.*)$", path)
            path = match.group(1) if match else path
            while path.startswith(("./", "../")):
                path = path.split("/", 1)[1]
            if not re.match(r"[a-z][a-z0-9+.-]*:", path) and bs._is_private(path):
                found.append(target)
        return found

    def test_6_no_output_links_into_a_private_path_holds_a_private_host_or_a_credential(self):
        # Public pages may name a private folder in prose (the README layout, "see docs/TRD-..." in a schema description): those sentences
        # already stand in the public README and spec. What DSN-6 forbids is a link into the private part, a private host or a credential.
        outputs = [LLMS_TXT, LLMS_FULL_TXT, *(f"{slug}.md" for slug in self.pages)]
        for name in outputs:
            text = read(self.out, name)
            with self.subTest(output=name):
                self.assertEqual([], self.private_link_targets(text))
                for token in ("dev.azure.com", "visualstudio.com", "ssh.dev.azure", *SECRET_WORDS):
                    self.assertNotIn(token, text)

    def test_6_llms_txt_lists_only_the_built_pages_and_names_no_private_path_at_all(self):
        text = read(self.out, LLMS_TXT)
        for entry in bs.PRIVATE_PATHS:
            self.assertNotIn(entry if "." in Path(entry).name else entry + "/", text)
        targets = re.findall(r"\]\(([^)\s]+)\)", text)
        self.assertEqual(sorted(f"{self.base}/{slug}.md" for slug in self.pages), sorted(targets))

    def test_6_the_link_scan_itself_finds_a_private_target(self):
        sample = "[a](docs/x.md) [b](../../.claude/rules/y.md#z) [c](https://github.com/o/r/blob/main/jenkins/release.Jenkinsfile) [d](README.md)"
        self.assertEqual([DOCS_X_MD, "../../.claude/rules/y.md#z", "https://github.com/o/r/blob/main/jenkins/release.Jenkinsfile"],
                         self.private_link_targets(sample))

    def test_6_two_builds_of_the_real_site_give_identical_bytes(self):
        again = Path(tempfile.mkdtemp()) / "again"
        bs.build(ROOT, again)
        for name in (LLMS_TXT, LLMS_FULL_TXT, "index.md", "overview.md"):
            self.assertEqual(read(self.out, name).encode(), read(again, name).encode(), name)


if __name__ == "__main__":
    unittest.main()
