#!/usr/bin/env python3
"""Tests of scripts/build_site.py (story #1666, task #2832): the Markdown converter, the link and anchor check, the exit
codes, the build of this repository's own site, and the rule that no public Markdown file links into the private part of the
repository. Offline, standard library only.
Run: python3 scripts/test_build_site.py
"""
import contextlib
import html
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = "<html><title>{{page_title}}</title><nav>{{nav}}</nav>{{content}}<a href=\"{{source_url}}\">{{source}}</a></html>"


def make_repo(files: dict[str, str], pages: list[dict], default_group: bool = True, default_description: bool = True, **extra) -> Path:
    """A scratch repository: the site files, the given pages' sources and any other file. Docs site v2 (#3555): `group` is one of
    the four group names and `description` is required, so a page without the key gets "Guides" and a one-sentence description
    unless the caller opts out with `default_group=False` or `default_description=False` (the refusal tests)."""
    if default_group:
        pages = [p if not isinstance(p, dict) or "group" in p else {**p, "group": "Guides"} for p in pages]
    if default_description:
        pages = [p if not isinstance(p, dict) or "description" in p else {**p, "description": "A page of the test site."} for p in pages]
    root = Path(tempfile.mkdtemp())
    config = {"title": "T", "repo": "https://example.test/r", "branch": "main", "pages": pages, **extra}
    everything = {"site/site.json": json.dumps(config), "site/template.html": TEMPLATE, "site/style.css": "body{}", **files}
    for rel, text in everything.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


INDEX = {"slug": "index", "title": "Home", "source": "index.md", "group": "Guides", "description": "The home page."}


def run_build(files: dict[str, str], pages: list[dict], **extra):
    root = make_repo(files, pages, **extra)
    out = root / "_out"
    return bs.build(root, out), out


class Anchors(unittest.TestCase):
    def test_slugs_follow_github(self):
        self.assertEqual(bs.slugify("Why"), "why")
        self.assertEqual(bs.slugify("How it works"), "how-it-works")
        self.assertEqual(bs.slugify("`spec/` — the source of truth"), "spec--the-source-of-truth")
        self.assertEqual(bs.slugify("GRP-7. A `nullValue` group key"), "grp-7-a-nullvalue-group-key")

    def test_duplicate_headings_get_a_suffix(self):
        rendered = bs.render_markdown("# A\n\n## Same\n\n## Same\n\n## Same\n")
        self.assertEqual(rendered.anchors, {"a", "same", "same-1", "same-2"})

    def test_a_suffix_that_is_itself_taken_is_skipped_like_github(self):
        rendered = bs.render_markdown("# S\n\n# S 1\n\n# S\n\n# S\n")
        self.assertEqual(rendered.anchors, {"s", "s-1", "s-2", "s-3"})

    def test_underscores_and_a_trailing_hash_survive(self):
        rendered = bs.render_markdown("## pg_trgm index\n\n### C#\n\n## Closed ##\n")
        self.assertEqual(rendered.anchors, {"pg_trgm-index", "c", "closed"})
        self.assertIn(">C#</h3>", rendered.html)
        self.assertIn(">Closed</h2>", rendered.html)

    def test_an_angle_bracket_in_a_heading_is_not_a_tag(self):
        self.assertEqual(bs.slugify("a < b and <c>"), "a--b-and")
        self.assertEqual(bs.slugify("x <b>bold</b>"), "x-bold")


RULES = ("# Rules\n\n## SEM-1. Case sensitivity\n\ntext\n\n**GRP-7. A nullValue key drills in.** More text.\n\n"
         "**GRP-7b. Not a duplicate.**\n\nplain\n")
RULES_PAGE = ("# Rules\n\n## Case sensitivity\n\n**SEM-1. Case sensitivity.** text\n\n**GRP-7. A nullValue key drills in.** More text.\n\n"
              "**GRP-7b. Not a duplicate.**\n\nplain\n")  # DS-19: a heading (a TOC label) holds no rule id, so the rule opens in bold
SEMANTICS = {"slug": "semantics", "title": "Semantics", "source": "rules.md"}
RULE_CONFIG = {"ruleSource": "rules.md", "ruleIdPrefixes": ["SEM", "GRP"]}


class RuleAnchors(unittest.TestCase):
    def test_a_bold_opener_and_a_numbered_heading_get_the_rule_id_as_anchor(self):
        rendered = bs.render_markdown(RULES)
        self.assertIn('<p id="grp-7">', rendered.html)
        self.assertIn('<a id="sem-1"></a>', rendered.html)
        self.assertLessEqual({"sem-1", "sem-1-case-sensitivity", "grp-7", "grp-7b"}, rendered.anchors)

    def test_a_bold_phrase_that_is_not_a_rule_id_gets_no_anchor(self):
        rendered = bs.render_markdown("**Note. This is bold.** text\n\n**lower-1. x**\n")
        self.assertNotIn(" id=", rendered.html)

    def test_definitions_are_found_with_their_titles_in_document_order(self):
        self.assertEqual(list(bs.rule_definitions(RULES)), ["SEM-1", "GRP-7", "GRP-7b"])
        self.assertEqual(bs.rule_definitions(RULES)["SEM-1"], "Case sensitivity")


class Includes(unittest.TestCase):
    def test_a_file_is_included_as_a_code_block_even_when_it_holds_a_fence(self):
        files = {"index.md": "# Home\n\n{{include src/a.cs csharp}}\n\nafter\n", "src/a.cs": "var x = 1 < 2;\n```\nnot a fence end\n```\n"}
        errors, out = run_build(files, [INDEX])
        self.assertEqual(errors, [])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('<pre><code class="language-csharp">var x = 1 &lt; 2;\n```\nnot a fence end\n```</code></pre>', page)
        self.assertIn("<p>after</p>", page)

    def test_the_fence_is_longer_than_any_backtick_run_in_the_file(self):
        files = {"index.md": "# Home\n\n{{include a.txt text}}\n", "a.txt": "x\n````\ny\n"}
        errors, out = run_build(files, [INDEX])
        self.assertEqual(errors, [])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("x\n````\ny</code></pre>", page)

    def test_a_malformed_include_is_an_error_not_literal_text(self):
        for bad in ("{{include a.txt}}", "{{include}}", "{{include a.txt a b}}", "{{include a.txt c#}}"):
            with self.subTest(bad=bad):
                root = make_repo({"index.md": f"# Home\n\n{bad}\n", "a.txt": "x"}, [INDEX])
                with self.assertRaises(bs.BuildError):
                    bs.build(root, root / "_out")

    def test_a_hyphenated_language_works_and_an_example_inside_a_fence_is_left_alone(self):
        files = {"index.md": "# Home\n\n{{include a.txt shell-session}}\n\n```\n{{include nothing.txt text}}\n```\n", "a.txt": "x"}
        errors, out = run_build(files, [INDEX])
        self.assertEqual(errors, [])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="language-shell-session"', page)
        self.assertIn("{{include nothing.txt text}}", page)

    def test_a_missing_private_or_outside_include_is_a_configuration_error(self):
        for bad in ("src/missing.cs", "docs/x.md", "../outside.md", "/etc/hostname"):
            with self.subTest(bad=bad):
                root = make_repo({"index.md": f"# Home\n\n{{{{include {bad} text}}}}\n", "docs/x.md": "x"}, [INDEX])
                with self.assertRaises(bs.BuildError):
                    bs.build(root, root / "_out")


class RuleSuffixes(unittest.TestCase):
    TEXT = "**SQL-7. Base.** x\n\n**SQL-7(b). Part b.** y\n\n**EXP-1(a). Compile half.** z\n"

    def test_a_parenthesised_suffix_is_part_of_the_rule_id_and_its_anchor(self):
        self.assertEqual(list(bs.rule_definitions(self.TEXT)), ["SQL-7", "SQL-7(b)", "EXP-1(a)"])
        self.assertEqual(bs.rule_anchor("SQL-7(b)"), "sql-7b")
        self.assertLessEqual({"sql-7", "sql-7b", "exp-1a"}, bs.render_markdown(self.TEXT).anchors)

    def test_a_mention_with_a_suffix_is_checked_against_the_base_id(self):
        self.assertEqual(bs.check_rule_ids({"a.md": "SQL-7(b) and SQL-7b and GRP-1(f)\n"}, self.TEXT, ["SQL", "GRP"]),
                         ["a.md:1: rule id 'GRP-1' is not defined in the rule source"])


class RuleIdCheck(unittest.TestCase):
    def test_a_defined_id_passes_and_an_unknown_one_fails_with_its_line(self):
        ok = bs.check_rule_ids({"a.md": "see SEM-1 and GRP-7 (and GRP-7b)\n"}, RULES, ["SEM", "GRP"])
        self.assertEqual(ok, [])
        bad = bs.check_rule_ids({"a.md": "fine\nbut GRP-99 is not a rule\n"}, RULES, ["SEM", "GRP"])
        self.assertEqual(bad, ["a.md:2: rule id 'GRP-99' is not defined in the rule source"])

    def test_a_prefix_outside_the_list_is_not_checked(self):
        self.assertEqual(bs.check_rule_ids({"a.md": "AR-1 and EXP-9 and XYZ-3\n"}, RULES, ["SEM", "GRP"]), [])

    def test_a_longer_number_is_not_mistaken_for_a_defined_one(self):
        self.assertEqual(len(bs.check_rule_ids({"a.md": "GRP-70\n"}, RULES, ["SEM", "GRP"])), 1)

    def test_the_build_fails_on_an_unknown_id_on_any_page(self):
        pages = [INDEX, SEMANTICS]
        errors, _ = run_build({"index.md": "# Home\n\nSee GRP-8.\n", "rules.md": RULES_PAGE}, pages, **RULE_CONFIG)
        self.assertEqual(len(errors), 1)
        self.assertIn("index.md:3: rule id 'GRP-8'", errors[0])

    def test_the_build_passes_when_every_id_is_defined(self):
        errors, out = run_build({"index.md": "# Home\n\nSee GRP-7 and [it](rules.md#grp-7).\n", "rules.md": RULES_PAGE}, [INDEX, SEMANTICS], **RULE_CONFIG)
        self.assertEqual(errors, [])
        self.assertIn('href="semantics.html#grp-7"', (out / "index.html").read_text(encoding="utf-8"))

    def test_a_link_to_an_undefined_rule_anchor_fails_as_a_dead_anchor(self):
        errors, _ = run_build({"index.md": "# Home\n\n[x](rules.md#grp-99)\n", "rules.md": RULES_PAGE}, [INDEX, SEMANTICS])
        self.assertEqual(len(errors), 1)
        self.assertIn("dead anchor '#grp-99' in rules.md", errors[0])


class SchemaReference(unittest.TestCase):
    SCHEMA = {
        "title": "Demo", "$id": "https://example.test/demo.json", "description": "A demo | with a pipe.\nTwo lines.",
        "type": "object", "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "description": "The name."},
            "mode": {"enum": ["a", "b"], "default": "a"},
            "tags": {"type": "array", "items": {"$ref": "#/$defs/tag"}},
            "map": {"type": "object", "additionalProperties": {"type": "object", "properties": {"inner": {"type": "boolean"}}}},
            "either": {"oneOf": [{"type": "object", "properties": {"left": {"type": "string"}}},
                                 {"type": "object", "properties": {"right": {"type": "string"}}}]},
            "ext": {"$ref": "./other.schema.json#/$defs/thing"},
        },
        "$defs": {"tag": {"description": "A tag.", "type": "object", "properties": {"label": {"type": "string"}}},
                  "kind": {"enum": ["x", "y"]}},
    }

    def test_every_member_of_every_depth_is_listed(self):
        markdown = bs.schema_reference(self.SCHEMA, "demo.schema.json", {"demo.schema.json": "demo", "other.schema.json": "other"})
        members = set(re.findall(r"(?m)^\| `([^`]+)` \|", markdown))
        self.assertEqual(members, {"name", "mode", "tags", "map", "map.*.inner", "either", "either.left", "either.right", "ext", "label"})

    def test_types_defaults_required_and_cross_links_are_shown(self):
        markdown = bs.schema_reference(self.SCHEMA, "demo.schema.json", {"demo.schema.json": "demo", "other.schema.json": "other"})
        self.assertIn("| `name` | string (minLength `1`) | yes |  | The name. |", markdown)
        self.assertIn('one of `"a"`, `"b"` |  | `"a"`', markdown)
        self.assertIn("array of [tag](#tag)", markdown)
        self.assertIn("[thing](other.html#thing)", markdown)
        self.assertIn("### kind", markdown)
        self.assertIn("A demo | with a pipe.\nTwo lines.", markdown)  # the description paragraph is plain text

    def test_required_flags_follow_the_object_they_belong_to(self):
        schema = {"title": "T", "required": ["a"], "properties": {
            "a": {"type": "string"}, "b": {"type": "string"},
            "o": {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}, "y": {"type": "string"}}},
            "v": {"oneOf": [{"type": "object", "required": ["p"], "properties": {"p": {"type": "string"}}},
                            {"type": "object", "required": ["q"], "properties": {"q": {"type": "string"}}}]}}}
        rows = {m.group(1): m.group(3) for m in re.finditer(r"(?m)^\| `([^`]+)` \| ([^|]*) \| ([^|]*) \|", bs.schema_reference(schema, "t.schema.json", {"t.schema.json": "t"}))}
        self.assertEqual(rows["a"].strip(), "yes")
        self.assertEqual(rows["b"].strip(), "")
        self.assertEqual(rows["o.x"].strip(), "yes")
        self.assertEqual(rows["o.y"].strip(), "")
        # a variant's own required member is only required in that variant: the variants exclude each other
        self.assertEqual(rows["v.p"].strip(), "in this variant")
        self.assertEqual(rows["v.q"].strip(), "in this variant")

    def test_definitions_show_their_description_and_their_type_line(self):
        schema = {"title": "T", "$defs": {"name": {"description": "A name.", "type": "string", "minLength": 1},
                                           "kind": {"enum": ["x", "y"]}, "anything": True}}
        markdown = bs.schema_reference(schema, "t.schema.json", {"t.schema.json": "t"})
        self.assertIn("### name\n\nA name.\n\nType: string (minLength `1`)", markdown)
        self.assertIn('### kind\n\nType: one of `"x"`, `"y"`', markdown)
        self.assertIn("### anything", markdown)

    def test_constraints_are_written_as_json(self):
        markdown = bs.schema_reference({"title": "T", "properties": {"x": {"type": "array", "uniqueItems": True}}}, "t.schema.json", {"t.schema.json": "t"})
        self.assertIn("uniqueItems `true`", markdown)

    def test_a_schema_that_is_not_an_object_is_a_configuration_error(self):
        pages = [INDEX, {"slug": "demo", "title": "Demo", "generator": "schema-reference", "schema": "demo.schema.json"}]
        root = make_repo({"index.md": "# Home\n", "demo.schema.json": "[]"}, pages)
        with self.assertRaises(bs.BuildError):
            bs.build(root, root / "_out")

    def test_an_unknown_id_in_a_schema_description_fails_the_build(self):
        schema = json.dumps({"title": "T", "properties": {"x": {"type": "string", "description": "see GRP-99"}}})
        pages = [INDEX, SEMANTICS, {"slug": "demo", "title": "Demo", "generator": "schema-reference", "schema": "demo.schema.json"}]
        errors, _ = run_build({"index.md": "# Home\n", "rules.md": RULES_PAGE, "demo.schema.json": schema}, pages, **RULE_CONFIG)
        self.assertEqual(len(errors), 1)
        self.assertIn("GRP-99", errors[0])
        self.assertIn("demo.schema.json (page 'demo')", errors[0])

    def test_a_dead_link_on_a_generated_page_names_the_page_not_a_phantom_file(self):
        schema = json.dumps({"title": "T", "properties": {"x": {"type": "string", "description": "see [it](missing.md)"}}})
        pages = [INDEX, {"slug": "demo", "title": "Demo", "generator": "schema-reference", "schema": "demo.schema.json"}]
        errors, _ = run_build({"index.md": "# Home\n", "demo.schema.json": schema}, pages)
        self.assertEqual(len(errors), 1)
        self.assertIn("site/site.json#demo:", errors[0])

    def test_a_pipe_in_a_description_does_not_break_the_table(self):
        schema = {"title": "T", "properties": {"x": {"type": "string", "description": "a | b"}}}
        markdown = bs.schema_reference(schema, "t.schema.json", {"t.schema.json": "t"})
        self.assertIn("a \\| b", markdown)
        self.assertIn("<td>a | b</td>", bs.render_markdown(markdown).html)

    def test_the_real_schemas_list_every_property_name(self):
        pages = {"grid-schema.schema.json": "grid-schema", "ir.schema.json": "ir-schema"}
        for name in pages:
            schema = json.loads((ROOT / "spec" / name).read_text(encoding="utf-8"))
            expected: set[str] = set()

            def walk(node):
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key == "properties" and isinstance(value, dict):
                            for member, sub in value.items():
                                expected.add(member)
                                walk(sub)
                        else:
                            walk(value)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)

            walk(schema)
            markdown = bs.schema_reference(schema, name, pages)
            listed = {re.sub(r"\[\]|\*", "", path).split(".")[-1] for path in re.findall(r"(?m)^\| `([^`]+)` \|", markdown)}
            self.assertEqual(sorted(expected - listed), [], f"{name}: members missing from the reference")
            for definition in schema.get("$defs", {}):
                self.assertIn(f"### {definition}", markdown)

    def test_a_generated_page_builds_through_the_site(self):
        schema = json.dumps(self.SCHEMA)
        pages = [INDEX, {"slug": "demo", "title": "Demo", "generator": "schema-reference", "schema": "demo.schema.json"}]
        errors, out = run_build({"index.md": "# Home\n\n[ref](demo.schema.json)\n", "demo.schema.json": schema.replace("./other.schema.json#/$defs/thing", "#/$defs/kind")}, pages)
        self.assertEqual(errors, [])
        self.assertIn('id="members"', (out / "demo.html").read_text(encoding="utf-8"))

    def test_an_unknown_generator_is_a_configuration_error(self):
        root = make_repo({"index.md": "# Home\n"}, [INDEX, {"slug": "x", "title": "X", "generator": "nope"}])
        with self.assertRaises(bs.BuildError):
            bs.build(root, root / "_out")

    def test_the_removed_rules_index_generator_is_an_unknown_generator(self):
        """#3555: the Rule index page and its generator are removed (DS-19 and the spec's scope)."""
        root = make_repo({"index.md": "# Home\n", "rules.md": RULES_PAGE}, [INDEX, {"slug": "rules", "title": "Rule index", "generator": "rules-index"}],
                         ruleSource="rules.md", ruleIdPrefixes=["SEM"])
        with self.assertRaises(bs.BuildError):
            bs.build(root, root / "_out")


class Converter(unittest.TestCase):
    def test_headings_get_ids_and_the_first_h1_is_the_title(self):
        rendered = bs.render_markdown("# Hello `x`\n\ntext\n\n## Sub\n")
        self.assertIn('<h1 id="hello-x">Hello <code>x</code></h1>', rendered.html)
        self.assertIn('<h2 id="sub">Sub</h2>', rendered.html)
        self.assertEqual(rendered.title, "Hello x")

    def test_fenced_code_is_escaped_and_keeps_its_language(self):
        rendered = bs.render_markdown("```sql\nSELECT * FROM t WHERE a < 1 AND b > 2;\n```\n")
        self.assertIn('<pre><code class="language-sql">SELECT * FROM t WHERE a &lt; 1 AND b &gt; 2;</code></pre>', rendered.html)

    def test_a_heading_inside_a_fence_is_not_a_heading(self):
        rendered = bs.render_markdown("```\n# not a heading\n```\n")
        self.assertEqual(rendered.anchors, set())

    def test_raw_html_is_escaped_never_passed_through(self):
        rendered = bs.render_markdown("a <script>alert(1)</script> b\n")
        self.assertNotIn("<script>", rendered.html)
        self.assertIn("&lt;script&gt;", rendered.html)

    def test_tables(self):
        rendered = bs.render_markdown("| a | b |\n|---|---|\n| `x` | y \\| z |\n")
        self.assertIn("<th>a</th><th>b</th>", rendered.html)
        self.assertIn("<td><code>x</code></td><td>y | z</td>", rendered.html)

    def test_nested_and_ordered_lists(self):
        rendered = bs.render_markdown("- one\n  - inner\n- two\n\n1. first\n2. second\n")
        self.assertIn("<ul><li>one<ul><li>inner</li></ul></li><li>two</li></ul>", rendered.html)
        self.assertIn("<ol><li>first</li><li>second</li></ol>", rendered.html)

    def test_a_fenced_block_indented_under_a_list_item_stays_in_the_item(self):
        rendered = bs.render_markdown("- first\n\n  ```sql\n  SELECT 1;\n  ```\n- second\n")
        self.assertEqual(rendered.html.count("<ul>"), 1)
        self.assertIn("<li>first<pre><code class=\"language-sql\">SELECT 1;</code></pre></li><li>second</li>", rendered.html)

    def test_text_after_a_fenced_block_in_a_list_item_stays_after_it(self):
        rendered = bs.render_markdown("- first\n  ```\n  code\n  ```\n  after the code\n- second\n")
        self.assertLess(rendered.html.index("<pre>"), rendered.html.index("after the code"))
        self.assertIn("<li>first<pre><code>code</code></pre><p>after the code</p></li>", rendered.html)

    def test_emphasis_and_code_do_not_interfere(self):
        rendered = bs.render_markdown("**bold** and *it* and `a*b*c` and snake_case_name\n")
        self.assertIn("<strong>bold</strong>", rendered.html)
        self.assertIn("<em>it</em>", rendered.html)
        self.assertIn("<code>a*b*c</code>", rendered.html)
        self.assertIn("snake_case_name", rendered.html)

    def test_links_are_recorded_with_their_line_and_can_be_rewritten(self):
        rendered = bs.render_markdown("one\n\n[x](a.md#b) and [`y`](c.md)\n", resolve=lambda href: "R:" + href)
        self.assertEqual(rendered.links, [(3, "a.md#b"), (3, "c.md")])
        self.assertIn('<a href="R:a.md#b">x</a>', rendered.html)
        self.assertIn('<a href="R:c.md"><code>y</code></a>', rendered.html)

    def test_every_value_that_reaches_the_page_is_escaped(self):
        rendered = bs.render_markdown(
            '[a"b](x"y.md) ![al"t](im"g.png) `<i>` <https://e.test/?a=1&b=<2> **<b>**\n', resolve=lambda href, image=False: href)
        self.assertNotIn('"b](', rendered.html)
        self.assertIn('href="x&quot;y.md"', rendered.html)
        self.assertIn('alt="al&quot;t"', rendered.html)
        self.assertIn('src="im&quot;g.png"', rendered.html)
        self.assertIn("<code>&lt;i&gt;</code>", rendered.html)
        self.assertNotIn("<b>", rendered.html)

    def test_a_nul_in_the_source_cannot_forge_a_placeholder(self):
        rendered = bs.render_markdown("a \x00 b \x000\x00 `c`\n")
        self.assertIn("<code>c</code>", rendered.html)
        self.assertNotIn("\x00", rendered.html)

    def test_images_are_recorded_like_links(self):
        rendered = bs.render_markdown("![alt](pic.png)\n", resolve=lambda href, image=False: "I:" + href if image else href)
        self.assertEqual(rendered.links, [(1, "pic.png")])
        self.assertIn('src="I:pic.png"', rendered.html)

    def test_block_quotes(self):
        rendered = bs.render_markdown("> quoted [l](x.md)\n> more\n")
        self.assertIn("<blockquote><p>quoted", rendered.html)
        self.assertEqual([href for _, href in rendered.links], ["x.md"])


class LinkCheck(unittest.TestCase):
    def test_a_clean_site_builds_and_a_repo_file_link_goes_to_github(self):
        errors, out = run_build({"index.md": "# Home\n\n[code](src/a.cs) [dir](src/)\n", "src/a.cs": "x"}, [INDEX])
        self.assertEqual(errors, [])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://example.test/r/blob/main/src/a.cs"', page)
        self.assertIn('href="https://example.test/r/tree/main/src"', page)
        self.assertTrue((out / "style.css").exists())

    def test_a_link_to_another_page_becomes_a_site_link_with_its_anchor_checked(self):
        pages = [INDEX, {"slug": "two", "title": "Two", "source": "d/two.md"}]
        files = {"index.md": "# Home\n\n[go](d/two.md#part)\n", "d/two.md": "# Two\n\n## Part\n"}
        errors, out = run_build(files, pages)
        self.assertEqual(errors, [])
        self.assertIn('href="two.html#part"', (out / "index.html").read_text(encoding="utf-8"))

    def test_a_dead_file_link_fails_with_the_source_line(self):
        errors, _ = run_build({"index.md": "# Home\n\nok\n\n[x](missing.md)\n"}, [INDEX])
        self.assertEqual(len(errors), 1)
        self.assertIn("index.md:5: dead link 'missing.md'", errors[0])

    def test_a_dead_anchor_in_the_same_page_fails(self):
        errors, _ = run_build({"index.md": "# Home\n\n[x](#nowhere) [y](#home)\n"}, [INDEX])
        self.assertEqual(len(errors), 1)
        self.assertIn("dead anchor '#nowhere'", errors[0])

    def test_a_dead_anchor_in_another_page_fails(self):
        pages = [INDEX, {"slug": "two", "title": "Two", "source": "two.md"}]
        errors, _ = run_build({"index.md": "# Home\n\n[x](two.md#nowhere)\n", "two.md": "# Two\n"}, pages)
        self.assertEqual(len(errors), 1)
        self.assertIn("dead anchor '#nowhere' in two.md", errors[0])

    def test_a_dead_anchor_in_a_markdown_file_without_a_page_fails(self):
        files = {"index.md": "# Home\n\n[ok](other.md#there) [bad](other.md#gone)\n", "other.md": "# Other\n\n## There\n"}
        errors, _ = run_build(files, [INDEX])
        self.assertEqual(len(errors), 1)
        self.assertIn("dead anchor '#gone' in other.md", errors[0])

    def test_a_link_into_the_private_part_fails_even_when_the_file_exists(self):
        files = {"index.md": "# Home\n\n[trd](docs/TRD.md) [m](CLAUDE.md) [c](.claude/rules/x.md)\n",
                 "docs/TRD.md": "# TRD\n", "CLAUDE.md": "x", ".claude/rules/x.md": "x"}
        errors, _ = run_build(files, [INDEX])
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("private part of the repository" in e for e in errors))

    def test_a_link_that_leaves_the_repository_fails(self):
        errors, _ = run_build({"index.md": "# Home\n\n[x](../outside.md)\n"}, [INDEX])
        self.assertEqual(len(errors), 1)
        self.assertIn("leaves the repository", errors[0])

    def test_a_script_scheme_is_refused_for_a_link_and_an_image(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", "vbscript:x", "JaVaScRiPt:alert(1)"):
            with self.subTest(bad=bad):
                errors, _ = run_build({"index.md": f"# Home\n\n[x]({bad}) ![y]({bad})\n"}, [INDEX])
                self.assertEqual(len(errors), 2)
                self.assertTrue(all("scheme other than http" in e for e in errors))

    def test_bare_directory_links_into_the_private_part_fail(self):
        files = {"index.md": "# Home\n\n[a](docs) [b](docs/) [c](.claude/) [d](.githooks) [e](scripts/publish-github.sh)\n",
                 "docs/x.md": "x", ".claude/x": "x", ".githooks/x": "x", "scripts/publish-github.sh": "x"}
        errors, _ = run_build(files, [INDEX])
        self.assertEqual(len(errors), 5)
        self.assertTrue(all("private part" in e for e in errors))

    def test_a_private_looking_name_that_is_public_passes(self):
        errors, _ = run_build({"index.md": "# Home\n\n[x](docs-site.md) [y](scripts/build_site.py)\n", "docs-site.md": "x", "scripts/build_site.py": "x"}, [INDEX])
        self.assertEqual(errors, [])

    def test_images_are_checked_and_rewritten(self):
        files = {"index.md": "# Home\n\n![ok](img/a.png) ![gone](img/b.png) ![secret](docs/s.png)\n", "img/a.png": "x", "docs/s.png": "x"}
        errors, out = run_build(files, [INDEX])
        self.assertEqual(len(errors), 2)
        self.assertIn("dead link 'img/b.png'", errors[0])
        self.assertIn("private part", errors[1])
        # NFR-13: the resolved raw address is another host, so the image is its alt text, not an <img>.
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('<span class="img-alt">ok</span>', page)
        self.assertNotIn("raw/main/img/a.png", page)

    def test_page_content_cannot_inject_into_the_template(self):
        _, out = run_build({"index.md": "# Home\n\n`{{source}}` and {{nav}} and {{content}}\n"}, [INDEX])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page.count("<nav>"), 1)
        self.assertIn("<code>{{source}}</code>", page)

    def test_a_page_removed_from_the_site_leaves_no_stale_output(self):
        root = make_repo({"index.md": "# Home\n", "two.md": "# Two\n"}, [INDEX, {"slug": "two", "title": "Two", "source": "two.md"}])
        out = root / "_out"
        bs.build(root, out)
        self.assertTrue((out / "two.html").exists())
        config = json.loads((root / "site" / "site.json").read_text(encoding="utf-8"))
        config["pages"] = [INDEX]
        (root / "site" / "site.json").write_text(json.dumps(config), encoding="utf-8")
        bs.build(root, out)
        self.assertFalse((out / "two.html").exists())

    def test_the_title_in_the_navigation_is_escaped(self):
        _, out = run_build({"index.md": "# Home\n"}, [{"slug": "index", "title": "<b>x</b>", "source": "index.md"}])
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", (out / "index.html").read_text(encoding="utf-8"))

    def test_external_links_are_not_fetched(self):
        errors, _ = run_build({"index.md": "# Home\n\n[x](https://example.invalid/never) [m](mailto:a@b.c)\n"}, [INDEX])
        self.assertEqual(errors, [])

    def test_a_page_whose_source_is_missing_is_reported(self):
        errors, _ = run_build({}, [INDEX])
        self.assertEqual(len(errors), 1)
        self.assertIn("cannot read index.md", errors[0])

SIDE_TEMPLATE = "<html><aside>{{sidebar}}</aside><div class=\"toc\">{{toc}}</div>{{content}}</html>"


def grouped(slug: str, group: str | None, title: str | None = None, **extra) -> dict:
    page = {"slug": slug, "title": title or slug.title(), "source": f"{slug}.md", **extra}
    if group is not None:
        page["group"] = group
    return page


def build_side(files: dict[str, str], pages: list[dict]) -> dict[str, str]:
    root = make_repo({"site/template.html": SIDE_TEMPLATE, **files}, pages)
    errors = bs.build(root, root / "_out")
    assert errors == [], errors
    return {f.stem: f.read_text(encoding="utf-8") for f in (root / "_out").glob("*.html")}


def run_cli(root: Path):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = bs.main(["--root", str(root), "--out", str(root / "_out")])
    return code, err.getvalue()


class Sidebar(unittest.TestCase):
    """FR-32, task #3474: T1 and T2; reshaped by #3555 (four fixed groups, the home page outside the sidebar)."""

    PAGES = [grouped("spec", "Reference", "The spec"), grouped("intro", "Guides", "Intro"), grouped("index", None, "Home")]  # Reference first in the file, Guides first in the sidebar
    FILES = {"index.md": "# Home\n", "spec.md": "# Spec\n", "intro.md": "# Intro\n"}

    def test_T1_one_list_per_group_in_the_fixed_order_pages_in_config_order(self):
        side = re.search(r"<aside>(.*)</aside>", build_side(self.FILES, self.PAGES)["intro"], re.S).group(1)
        self.assertLess(side.index("Guides"), side.index("Reference"))
        self.assertEqual(side.count("Guides"), 1)
        guides = side[:side.index("Reference")]
        self.assertIn('href="intro.html"', guides)
        self.assertNotIn("spec.html", guides)
        self.assertIn(">The spec</a>", side[side.index("Reference"):])

    def test_T1_the_home_page_is_not_in_the_sidebar(self):
        side = re.search(r"<aside>(.*)</aside>", build_side(self.FILES, self.PAGES)["intro"], re.S).group(1)
        self.assertNotIn('href="index.html"', side)

    def test_T1_the_current_page_alone_is_marked_aria_current(self):
        built = build_side(self.FILES, self.PAGES)
        marked = re.findall(r'<a [^>]*aria-current="page"[^>]*>', built["spec"])
        self.assertEqual(len(marked), 1)
        self.assertIn('href="spec.html"', marked[0])
        self.assertNotIn("aria-current", built["intro"].split("spec.html")[1].split("</a>")[0])

    def test_T1_a_single_group_renders_no_other_group(self):
        built = build_side({"index.md": "# Home\n", "intro.md": "# Intro\n"}, [grouped("index", None, "Home"), grouped("intro", "Guides", "Intro")])
        self.assertEqual(built["intro"].count("Guides"), 1)
        self.assertNotIn("Reference", built["intro"])
        self.assertIn('aria-current="page"', built["intro"])

    def test_T1_title_is_escaped(self):
        built = build_side({"index.md": "# Home\n", "intro.md": "# Intro\n"}, [grouped("index", None, "Home"), grouped("intro", "Guides", "T <i>")])
        self.assertIn("T &lt;i&gt;", built["intro"])

    def test_T1_render_sidebar_marks_the_current_page(self):
        pages = [bs.Page("a", "A", "a.md", group="Guides"), bs.Page("b", "B", "b.md", group="Guides")]
        side = bs.render_sidebar(pages, "b")
        self.assertEqual(side.count('aria-current="page"'), 1)

    def test_T2_a_page_without_a_group_is_refused_with_exit_2_naming_the_slug(self):
        root = make_repo({"index.md": "# Home\n", "spec.md": "# S\n"}, [grouped("index", "Guides"), grouped("spec", None)], default_group=False)
        code, err = run_cli(root)
        self.assertEqual(code, 2)
        self.assertIn("spec", err)

    def test_T2_an_empty_non_string_or_unknown_group_is_refused(self):
        for bad in ("", 3, None, "Start here", "G"):
            with self.subTest(bad=bad):
                page = grouped("spec", "Guides")
                page["group"] = bad
                code, err = run_cli(make_repo({"index.md": "# Home\n", "spec.md": "# S\n"}, [grouped("index", "Guides"), page]))
                self.assertEqual(code, 2)
                self.assertIn("spec", err)


class Toc(unittest.TestCase):
    """FR-32, task #3474: T3 and T4."""

    def toc_of(self, markdown: str) -> str:
        built = build_side({"index.md": markdown}, [grouped("index", None, "Home")])
        return re.search(r'<div class="toc">(.*?)</div>', built["index"], re.S).group(1)

    def test_T3_three_level_2_headings_give_three_links_in_order(self):
        toc = self.toc_of("# Home\n\n## Alpha\n\n### Deep\n\n## Beta\n\n## Gamma\n")
        self.assertIn("On this page", toc)
        self.assertEqual(re.findall(r'<a href="#([^"]+)">([^<]*)</a>', toc), [("alpha", "Alpha"), ("beta", "Beta"), ("gamma", "Gamma")])

    def test_T3_a_page_without_level_2_headings_has_no_toc_at_all(self):
        self.assertEqual(self.toc_of("# Home\n\n### Only deep\n\ntext\n").strip(), "")

    def test_T3_duplicate_headings_link_to_their_own_suffixed_anchors(self):
        toc = self.toc_of("# Home\n\n## Same\n\n## Same\n")
        self.assertEqual(re.findall(r'href="#([^"]+)"', toc), ["same", "same-1"])

    def test_T3_render_toc_of_a_rendered_page(self):
        self.assertEqual(bs.render_toc(bs.render_markdown("# T\n")), "")

    def test_T4_markup_in_a_heading_is_escaped_and_the_anchor_is_the_headings_own(self):
        built = build_side({"index.md": "# Home\n\n## a <b> & c\n"}, [grouped("index", None, "Home")])["index"]
        toc = re.search(r'<div class="toc">(.*?)</div>', built, re.S).group(1)
        href, text = re.search(r'<a href="#([^"]+)">([^<]*)</a>', toc).groups()
        self.assertIn("a &lt;b&gt; &amp; c", text)
        self.assertNotIn("<b>", toc)
        self.assertIn(f'<h2 id="{href}">', built)

    def test_T4_a_heading_links_to_its_own_anchor(self):
        # #3555: the former test used a `## SEM-1. Title` heading; DS-19 now refuses a coded reference in a TOC label
        # (the refusal is pinned in test_build_site_structure.py), so the rule id is gone from the heading.
        built = build_side({"index.md": "# Home\n\n## Title\n"}, [grouped("index", None, "Home")])["index"]
        href = re.search(r'<div class="toc">.*?href="#([^"]+)"', built, re.S).group(1)
        self.assertEqual(href, "title")
        self.assertIn(f'<h2 id="{href}">', built)


class PerPageTemplate(unittest.TestCase):
    """FR-32, task #3474: T5."""

    def test_T5_a_page_with_a_template_key_uses_that_file(self):
        files = {"index.md": "# Home\n", "two.md": "# Two\n", "site/home.html": "<html>HOME-TEMPLATE {{content}}</html>"}
        built = build_side(files, [grouped("index", None, "Home", template="site/home.html"), grouped("two", "Guides", "Two")])
        self.assertIn("HOME-TEMPLATE", built["index"])
        self.assertIn("<h1", built["index"])
        self.assertNotIn("HOME-TEMPLATE", built["two"])
        self.assertIn("<aside>", built["two"])

    def test_T5_a_missing_template_file_is_exit_2_naming_the_path(self):
        root = make_repo({"index.md": "# Home\n"}, [grouped("index", None, "Home", template="site/nope.html")])
        code, err = run_cli(root)
        self.assertEqual(code, 2)
        self.assertIn("site/nope.html", err)

    def test_T5_a_template_that_is_not_a_string_is_exit_2(self):
        code, _ = run_cli(make_repo({"index.md": "# Home\n"}, [grouped("index", None, "Home", template=7)]))
        self.assertEqual(code, 2)


class NoInjection(unittest.TestCase):
    """FR-32, task #3474: T6."""

    def test_T6_sidebar_and_toc_placeholders_in_content_are_printed_as_text(self):
        built = build_side({"index.md": "# Home\n\n## Part\n\n`{{sidebar}}` and {{toc}} here\n"}, [grouped("index", None, "Home")])["index"]
        self.assertIn("<code>{{sidebar}}</code>", built)
        self.assertIn("{{toc}} here", built)
        self.assertEqual(built.count("<aside>"), 1)
        self.assertEqual(built.count("On this page"), 1)

    def test_T6_a_heading_that_holds_a_placeholder_does_not_expand_in_the_toc(self):
        # #3555: the home page is outside the sidebar, so a second page in a group carries the sidebar link.
        built = build_side({"index.md": "# Home\n\n## About {{sidebar}}\n", "two.md": "# Two\n"},
                           [grouped("index", None, "Home"), grouped("two", "Guides", "Two")])["index"]
        self.assertEqual(built.count('href="two.html"'), 1)
        self.assertEqual(built.count("<aside>"), 1)
        self.assertIn("{{sidebar}}", built)

FONT_FILES = ["bricolage-grotesque-latin-700-normal.woff2", "bricolage-grotesque-latin-800-normal.woff2",
              "instrument-sans-latin-400-normal.woff2", "instrument-sans-latin-500-normal.woff2",
              "instrument-sans-latin-600-normal.woff2", "jetbrains-mono-latin-400-normal.woff2",
              "jetbrains-mono-latin-500-normal.woff2"]
FAMILIES = ["Bricolage Grotesque", "Instrument Sans", "JetBrains Mono"]
GENERIC = ("sans-serif", "serif", "monospace", "system-ui")


def luminance(hex_colour: str) -> float:
    digits = hex_colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    channels = [int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class SiteDesign(unittest.TestCase):
    """The approved redesign of this repository's own site (FR-32, NFR-13, task #3475): T1..T6 of that task."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        bs.build(ROOT, cls.out)
        cls.pages = {f.stem: f.read_text(encoding="utf-8") for f in cls.out.glob("*.html")}
        cls.css_path = ROOT / "site" / "style.css"
        cls.css = cls.css_path.read_text(encoding="utf-8")

    def root_vars(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for block in re.findall(r":root\s*{([^}]*)}", self.css):
            found.update(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", block))
        return found

    def test_T1_no_source_line_no_script_no_foreign_resource_in_any_built_page(self):
        self.assertIn("index", self.pages)
        for slug, page in self.pages.items():
            with self.subTest(page=slug):
                self.assertNotIn("Source:", page)
                self.assertNotIn("fonts.googleapis.com", page)
                self.assertNotIn("fonts.gstatic.com", page)
                # #3556: the only scripts are the site's own files (theme.js, site.js), relative, with no inline body (DSN-1, DSN-7).
                self.assertEqual(re.findall(r"<script\b[^>]*\bsrc=\"([^\"]*)\"", page), re.findall(r"<script\b[^>]*\bsrc=\"((?:theme|site)\.js)\"", page))
                self.assertEqual(page.count("></script>"), page.count("<script"))  # no inline body
                self.assertEqual(len(re.findall(r"<script\b", page)), len(re.findall(r"<script\b[^>]*\bsrc=", page)))
                for tag in re.findall(r"<link\b[^>]*>", page):
                    self.assertNotRegex(tag, r"href=\"https?://")
                for tag in re.findall(r"<(?:img|source|iframe|video|audio|embed|object)\b[^>]*>", page):
                    self.assertNotRegex(tag, r"\bsrc=\"(?:https?:)?//")
                self.assertNotRegex(page, r"\bsrc=\"(?:https?:)?//")

    def test_T1_the_stylesheet_loads_nothing_from_another_host(self):
        built = (self.out / "style.css").read_text(encoding="utf-8")
        for text in (self.css, built):
            self.assertNotIn("@import", text)
            self.assertNotIn("url(http", text)
            self.assertNotIn("googleapis", text)

    def test_T2_home_page_shows_the_request_the_statement_and_the_links(self):
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", self.pages["index"])).split())
        # #3557: the "Refused" line with its rule code is gone from the hero (DS-19), so its text is no longer a needle.
        for needle in ('SELECT * FROM "orders"', '"filter": "acme"', "Safe queries out."):
            self.assertIn(needle, text)
        for slug in ("quickstart-csharp", "index-guidance", "overview", "spec", "semantics", "grid-schema",
                     "ir-schema", "odata-migration"):
            self.assertIn(f'href="{slug}.html"', self.pages["index"], slug)

    def test_T2_only_the_index_page_names_a_template(self):
        pages = json.loads((ROOT / "site" / "site.json").read_text(encoding="utf-8"))["pages"]
        self.assertEqual({p["slug"]: p.get("template") for p in pages if p.get("template")}, {"index": "site/home.html"})

    def test_T3_the_font_files_are_in_the_repository_with_their_licences(self):
        fonts = ROOT / "site" / "fonts"
        for name in FONT_FILES:
            with self.subTest(font=name):
                data = (fonts / name).read_bytes()
                self.assertEqual(data[:4], b"wOF2")
                self.assertLess(len(data), 60 * 1024)
        licences = (fonts / "LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("SIL Open Font License", licences)
        for family in FAMILIES:
            self.assertIn(family, licences)

    def test_T3_the_build_copies_the_fonts_folder(self):
        built = sorted(f.name for f in (self.out / "fonts").glob("*"))
        self.assertEqual(built, sorted(FONT_FILES + ["LICENSES.md"]))

    def test_T3_each_font_file_has_a_relative_font_face_and_exists_in_the_output(self):
        urls = re.findall(r"@font-face\s*{[^}]*?url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", self.css)
        self.assertEqual(sorted(urls), sorted(f"fonts/{name}" for name in FONT_FILES))
        for url in urls:
            self.assertTrue((self.out / url).is_file(), url)

    def test_T3_every_font_family_is_ours_followed_by_a_generic_fallback(self):
        css = re.sub(r"@font-face\s*{[^}]*}", "", self.css)
        declared = re.findall(r"font-family\s*:\s*([^;}]+)", css)
        self.assertTrue(declared, "the stylesheet names no font-family")
        for value in declared:
            parts = [x.strip().strip("'\"") for x in value.split(",")]
            self.assertIn(parts[0], FAMILIES, value)
            self.assertIn(parts[-1], GENERIC, value)
        self.assertEqual({v.split(",")[0].strip().strip("'\"") for v in declared}, set(FAMILIES))

    def test_T5_the_colour_contract_is_declared_in_root(self):
        colours = self.root_vars()
        for name in ("--bg", "--surface", "--text", "--muted", "--faint", "--accent", "--accent-ink"):
            self.assertIn(name, colours)

    def test_T5_text_colours_reach_4_5_on_both_backgrounds_and_accent_ink_on_accent(self):
        colours = self.root_vars()
        for name in ("--text", "--muted", "--faint", "--accent"):
            for ground in ("--bg", "--surface"):
                with self.subTest(colour=name, ground=ground):
                    self.assertGreaterEqual(contrast(colours[name], colours[ground]), 4.5)
        self.assertGreaterEqual(contrast(colours["--accent-ink"], colours["--accent"]), 4.5)

    def test_T5_dark_is_a_media_query_and_an_attribute_over_a_light_root(self):
        # #3556 (DS-5): the former "dark only" test; the site now offers Dark, Light and Auto.
        self.assertRegex(self.css, r"prefers-color-scheme:\s*dark")
        self.assertIn('[data-theme="dark"]', self.css)
        self.assertIn('[data-theme="light"]', self.css)

    def test_T5_the_contrast_helper_matches_known_ratios(self):
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(contrast("#777777", "#ffffff"), 4.48, places=2)

    def test_T1_the_stylesheet_has_no_import_no_foreign_url_and_only_relative_font_urls(self):
        built = (self.out / "style.css").read_text(encoding="utf-8")
        for text in (self.css, built):
            self.assertNotRegex(text, r"(?i)@import")
            self.assertNotRegex(text, r"(?i)url\(\s*['\"]?\s*(?:(?!data:)[a-z][a-z0-9+.-]*:|[/\\]{2})")
            self.assertNotRegex(text, r"(?i)gstatic|googleapis")
            urls = re.findall(r"url\(\s*['\"]?([^)'\"]*)['\"]?\s*\)", text)
            self.assertTrue(urls)
            for url in urls:
                self.assertRegex(url, r"^fonts/[\w.-]+$")

    def test_T1_no_tag_but_a_loads_or_points_to_another_host(self):
        for slug, page in self.pages.items():
            for tag in re.findall(r"<(?!a(?![a-z0-9]))[a-z][^>]*>", page, re.I):
                for name, value in re.findall(r"""\b(src|srcset|poster|data|href)\s*=\s*["']([^"']*)["']""", tag, re.I):
                    with self.subTest(page=slug, tag=tag[:60]):
                        self.assertNotRegex(value, r"(?i)^\s*(?:[a-z][a-z0-9+.-]*:|[/\\]{2})", f"{name} in {tag[:80]}")

    def test_FR32_a_docs_page_has_both_group_names_and_one_toc_link_per_level_2_heading(self):
        page = self.pages["quickstart-csharp"]
        side = re.search(r"<aside\b.*?</aside>", page, re.S).group(0)
        self.assertIn("Guides", side)
        self.assertIn("Reference", side)
        main = re.search(r"<main\b.*?</main>", page, re.S).group(0)
        toc = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', page, re.S).group(1)
        self.assertGreater(main.count("<h2"), 0)
        self.assertEqual(len(re.findall(r'<a href="#', toc)), main.count("<h2"))

    def test_T5_the_literal_text_colours_of_the_prose_rules_reach_4_5_on_their_ground(self):
        colours = self.root_vars()
        grounds = {".prose p": ["--bg", "--surface"], ".lead": ["--bg", "--surface"], ".muted": ["--bg", "--surface"],
                   "code": ["--code"], "blockquote": ["--bg"], ".card p": ["--surface"], ".panel pre": ["--surface"],
                   ".p": ["--surface"], ".c": ["--surface"]}
        found: dict[str, str] = {}
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)):
            declared = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{3,6}|var\(\s*(--[\w-]+)\s*\))", body)
            if not declared:
                continue
            value = declared.group(1) if declared.group(2) is None else colours[declared.group(2)]
            for selector in (x.strip() for x in selectors.split(",")):
                if selector in grounds:
                    found[selector] = value
        for needed in (".prose p", ".lead", ".muted", "code", "blockquote", ".card p", ".p", ".c"):
            self.assertIn(needed, found)
        for selector, value in found.items():
            for ground in grounds[selector]:
                with self.subTest(selector=selector, ground=ground):
                    self.assertGreaterEqual(contrast(value, colours[ground]), 4.5)

    def test_T6_the_stylesheet_stacks_at_phone_width_and_scrolls_code_sideways(self):
        self.assertRegex(self.css, r"@media\s*\(max-width:")
        self.assertRegex(self.css, r"overflow-x:\s*auto")
        self.assertRegex(self.css, r"pre\b[^{]*{[^}]*overflow-x:\s*auto")
        self.assertIn('<meta name="viewport"', self.pages["quickstart-csharp"])

    def test_T6_a_docs_page_has_the_sidebar_the_toc_and_one_current_link(self):
        page = self.pages["quickstart-csharp"]
        self.assertIn("<aside", page)
        self.assertIn('class="toc"', page)
        self.assertIn("On this page", page)
        self.assertEqual(page.count('aria-current="page"'), 1)
        self.assertIn("<details", page)  # the sidebar groups are native collapsible blocks (DS-2)

    def css_rules(self) -> list[tuple[list[str], dict[str, str]]]:
        """Flat list of (selectors, declarations) in source order; comments dropped, at-rule wrappers ignored."""
        text = self.css
        start = text.find("/*")
        while start != -1:
            end = text.find("*/", start + 2)
            text = text[:start] if end == -1 else text[:start] + text[end + 2:]
            start = text.find("/*")
        rules = []
        for chunk in text.split("}"):
            head, brace, body = chunk.rpartition("{")
            if not brace:
                continue
            selectors = head.rpartition("{")[2]
            declarations = {}
            for declaration in body.split(";"):
                name, colon, value = declaration.partition(":")
                if colon:
                    declarations[name.strip()] = value.strip()
            rules.append(([s.strip() for s in selectors.split(",")], declarations))
        return rules

    def declared(self, selector: str, prop: str) -> str | None:
        """Last value that a rule naming exactly this selector gives the property."""
        value = None
        for selectors, declarations in self.css_rules():
            if selector in selectors and prop in declarations:
                value = declarations[prop]
        return value

    def effective_in_prose(self, tag: str, prop: str, initial: str) -> str:
        """What a cell inside .prose computes: its own rule (source order wins), else inherited from .prose."""
        own = None
        for selectors, declarations in self.css_rules():
            for selector in selectors:
                parts = selector.split()
                if parts and parts[-1] == tag and parts[0] in (tag, ".prose", "table") and prop in declarations:
                    own = declarations[prop]
        if own is not None:
            return own
        return self.declared(".prose", prop) or initial

    def test_T1_cells_inside_prose_break_only_when_a_word_cannot_fit(self):
        for tag in ("td", "th"):
            with self.subTest(cell=tag):
                effective = self.effective_in_prose(tag, "overflow-wrap", "normal")
                self.assertEqual(effective, "break-word")
                self.assertNotEqual(effective, "anywhere")

    def test_T2_header_cells_never_wrap(self):
        self.assertEqual(self.effective_in_prose("th", "white-space", "normal"), "nowrap")

    def test_T3_characterization_prose_and_the_link_lists_keep_overflow_wrap_anywhere(self):
        for selector in (".prose", ".side li a", ".toc a"):
            with self.subTest(selector=selector):
                self.assertEqual(self.declared(selector, "overflow-wrap"), "anywhere")

    def test_T3_the_built_stylesheet_is_the_source_stylesheet(self):
        built = (self.out / "style.css").read_text(encoding="utf-8")
        self.assertEqual(built, self.css)

class RemoteImages(unittest.TestCase):
    """NFR-13, task #3475: an image on another host is never emitted as <img>; its alt text stands in for it."""

    BADGE = "https://img.shields.io/badge/coverage-90-green.svg"

    def render(self, markdown: str) -> str:
        return bs.render_markdown(markdown).html

    def test_a_remote_image_becomes_its_alt_text_in_a_span(self):
        out = self.render(f"![build status]({self.BADGE})\n")
        self.assertIn('<span class="img-alt">build status</span>', out)
        self.assertNotIn("<img", out)
        self.assertNotIn('src="http', out)

    def test_a_wrapped_badge_keeps_its_link_around_the_span(self):
        url = "https://github.com/pluries/craticula/actions/workflows/ci.yml"
        out = self.render(f"[![coverage gate]({self.BADGE})]({url})\n")
        self.assertIn(f'<a href="{url}"><span class="img-alt">coverage gate</span></a>', out)
        self.assertNotIn("<img", out)

    def test_a_remote_image_with_an_empty_alt_renders_nothing(self):
        out = self.render(f"before ![]({self.BADGE}) after\n")
        self.assertNotIn("<img", out)
        self.assertNotIn("img-alt", out)
        self.assertNotIn("shields.io", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_the_alt_text_is_escaped(self):
        out = self.render(f"![a <b> & c]({self.BADGE})\n")
        self.assertIn('<span class="img-alt">a &lt;b&gt; &amp; c</span>', out)
        self.assertNotIn("<b>", out)

    def test_an_http_image_is_remote_too(self):
        out = self.render("![plain](http://example.test/a.png)\n")
        self.assertIn('<span class="img-alt">plain</span>', out)
        self.assertNotIn("<img", out)

    def test_a_remote_image_in_a_table_cell_behaves_the_same(self):
        out = self.render(f"| a | b |\n|---|---|\n| x | ![in cell]({self.BADGE}) |\n")
        self.assertIn('<td><span class="img-alt">in cell</span></td>', out)
        self.assertNotIn("<img", out)

    def test_a_remote_image_in_a_list_item_behaves_the_same(self):
        out = self.render(f"- item ![in list]({self.BADGE})\n")
        self.assertIn('<span class="img-alt">in list</span>', out)
        self.assertNotIn("<img", out)

    def test_a_local_image_is_still_an_img(self):
        out = self.render("![local](img/a.png)\n")
        self.assertIn('<img alt="local" src="img/a.png">', out)
        self.assertNotIn("img-alt", out)

    def test_a_local_image_that_resolves_to_a_repository_url_is_remote(self):
        out = bs.render_markdown("![shot](img/a.png)\n", resolve=lambda href, image=False: "https://example.test/r/raw/main/" + href).html
        self.assertIn('<span class="img-alt">shot</span>', out)
        self.assertNotIn("<img", out)

    FOREIGN_SOURCES = [
        "HTTP://evil.example/a.png", "Https://evil.example/b.png", "https:/evil.example/c.png", "http:evil.example/d.png",
        "https:\\\\evil.example\\e.png"]
    ERRORING_SOURCES = ["//evil.example/f.png", "\\\\evil.example\\g.png"]

    def test_an_image_with_any_scheme_or_a_double_slash_is_remote_however_it_is_spelled(self):
        for source in self.FOREIGN_SOURCES:
            with self.subTest(source=source):
                errors, out = run_build({"index.md": f"# Home\n\n![a]({source})\n"}, [INDEX])
                self.assertEqual(errors, [])
                written = "".join(f.read_text(encoding="utf-8") for f in out.glob("*.html"))
                self.assertIn('<span class="img-alt">a</span>', written)
                self.assertNotIn("<img", written)
                self.assertNotIn("src=", written)
                self.assertNotIn("evil.example", written)

    def test_a_double_slash_image_the_build_already_reports_still_writes_no_img_and_no_src(self):
        for source in self.ERRORING_SOURCES:
            with self.subTest(source=source):
                _, out = run_build({"index.md": f"# Home\n\n![a]({source})\n"}, [INDEX])
                written = "".join(f.read_text(encoding="utf-8") for f in out.glob("*.html"))
                self.assertNotIn("<img", written)
                self.assertNotIn("src=", written)

    def test_a_built_page_holds_no_remote_img_and_keeps_the_badge_link(self):
        files = {"index.md": f"# Home\n\n[![coverage gate]({self.BADGE})](https://github.com/pluries/craticula/actions)\n"}
        errors, out = run_build(files, [INDEX])
        self.assertEqual(errors, [])
        page = (out / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<img", page)
        self.assertIn('<a href="https://github.com/pluries/craticula/actions"><span class="img-alt">coverage gate</span></a>', page)


class Cli(unittest.TestCase):
    def run_main(self, root: Path):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = bs.main(["--root", str(root), "--out", str(root / "_out")])
        return code, err.getvalue()

    def test_exit_0_when_every_link_resolves(self):
        code, _ = self.run_main(make_repo({"index.md": "# Home\n"}, [INDEX]))
        self.assertEqual(code, 0)

    def test_exit_1_on_a_dead_link(self):
        code, err = self.run_main(make_repo({"index.md": "# Home\n\n[x](nope.md)\n"}, [INDEX]))
        self.assertEqual(code, 1)
        self.assertIn("dead link", err)

    def test_exit_2_on_a_missing_or_invalid_configuration(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual(self.run_main(root)[0], 2)
        broken = make_repo({"index.md": "# Home\n"}, [INDEX])
        (broken / "site" / "site.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_main(broken)[0], 2)

    def test_exit_2_on_an_unsafe_slug_or_source(self):
        for bad in ({"slug": "../x", "title": "X", "source": "index.md"},
                    {"slug": 'a"b', "title": "X", "source": "index.md"},
                    {"slug": "x", "title": "X", "source": "/etc/hostname"},
                    {"slug": "x", "title": "X", "source": "../outside.md"},
                    {"slug": "x", "title": "X", "source": "docs/TRD.md"},
                    {"slug": "x", "title": "X"}):
            with self.subTest(bad=bad):
                code, err = self.run_main(make_repo({"index.md": "# Home\n", "docs/TRD.md": "x"}, [INDEX, bad]))
                self.assertEqual(code, 2, err)

    def test_exit_2_on_a_page_that_is_not_utf8(self):
        root = make_repo({"index.md": "# Home\n"}, [INDEX])
        (root / "index.md").write_bytes(b"# Home\n\xff\xfe\n")
        code, _ = self.run_main(root)
        self.assertEqual(code, 1)  # reported as an unreadable page, not a traceback

    def test_exit_2_when_the_rule_prefixes_are_not_a_list(self):
        root = make_repo({"index.md": "# Home\n", "rules.md": RULES_PAGE}, [INDEX], ruleSource="rules.md", ruleIdPrefixes="SEM")
        self.assertEqual(self.run_main(root)[0], 2)

    def test_exit_2_when_there_is_no_index_page(self):
        code, err = self.run_main(make_repo({"a.md": "# A\n"}, [{"slug": "a", "title": "A", "source": "a.md"}]))
        self.assertEqual(code, 2)
        self.assertIn("include 'index'", err)


class ThisRepository(unittest.TestCase):
    def test_the_real_site_builds_with_every_link_resolving(self):
        with tempfile.TemporaryDirectory() as out:
            errors = bs.build(ROOT, Path(out))
            self.assertEqual(errors, [])
            self.assertTrue((Path(out) / "index.html").exists())

    def test_the_private_list_matches_the_publish_script_where_it_exists(self):
        publish = ROOT / "scripts" / "publish-github.sh"
        if not publish.exists():
            self.skipTest("the publish script is private (absent from the public mirror)")
        match = re.search(r"(?m)^PRIVATE=\((.*)\)\s*$", publish.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "no PRIVATE array in the publish script")
        self.assertEqual({e.rstrip("/") for e in match.group(1).split()}, set(bs.PRIVATE_PATHS),
                         "PRIVATE_PATHS differs from the PRIVATE array of scripts/publish-github.sh")

    def test_site_is_public_and_docs_is_private(self):
        self.assertTrue(bs._is_private("docs/TRD.md"))
        self.assertTrue(bs._is_private("docs"))
        self.assertFalse(bs._is_private("site/pages/index.md"))
        self.assertFalse(bs._is_private("docs-site.md"))
        self.assertFalse(bs._is_private(".github/workflows/ci.yml"))

    def test_the_semantics_page_reaches_every_rule_by_anchor(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(bs.build(ROOT, Path(out)), [])
            semantics = "".join(f.read_text(encoding="utf-8") for f in sorted(Path(out).glob("*.html")))  # the rules live on the split pages (#3555)
            definitions = bs.rule_definitions((ROOT / "spec" / "semantics.md").read_text(encoding="utf-8"))
            self.assertIn("GRP-7", definitions)
            self.assertLessEqual({"SQL-7(b)", "EXP-1(a)", "EXP-1(b)"}, set(definitions))  # a parenthesised suffix is part of the id
            self.assertIn('id="sql-7b"', semantics)
            missing = [rule for rule in definitions if f'id="{bs.rule_anchor(rule)}"' not in semantics]
            self.assertEqual(missing, [], "rules without an anchor on a semantics page")
            self.assertIn('id="grp-7"', semantics)
            self.assertIn('id="sem-1"', semantics)
            self.assertFalse((Path(out) / "rules.html").exists(), "the Rule index page is removed")

    def test_the_quickstart_shows_the_program_and_its_output_verbatim(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(bs.build(ROOT, Path(out)), [])
            page = (Path(out) / "quickstart-csharp.html").read_text(encoding="utf-8")
            sample = ROOT / "csharp" / "samples" / "Craticula.Quickstart"
            for name in ("Program.cs", "expected-output.txt"):
                body = (sample / name).read_text(encoding="utf-8").rstrip("\n")
                self.assertIn(html.escape(body, quote=False), page, f"{name} is not on the quickstart page as it is")

    def test_the_odata_guide_shows_every_example_request_and_its_statement(self):
        """DoD of #2835: each construct has its request and its compiled statement on the page, as the files the C# test compiles."""
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(bs.build(ROOT, Path(out)), [])
            page = (Path(out) / "odata-migration.html").read_text(encoding="utf-8")
            folder = ROOT / "site" / "examples" / "odata"
            names = sorted(p.stem for p in folder.glob("*.json") if p.name != "schema.json")
            self.assertGreaterEqual(len(names), 8)
            for name in names:
                for suffix in (".json", ".sql.txt"):
                    body = (folder / (name + suffix)).read_text(encoding="utf-8").rstrip("\n")
                    self.assertTrue(body, f"{name}{suffix} is empty")
                    self.assertIn(html.escape(body, quote=False), page, f"{name}{suffix} is not on the OData guide")
            self.assertIn(html.escape((folder / "schema.json").read_text(encoding="utf-8").rstrip("\n"), quote=False), page)

    def test_no_page_claims_a_package_is_published(self):
        """DoD of #2834: the stubs and the quickstart say nothing is published and give no install command."""
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(bs.build(ROOT, Path(out)), [])
            for slug in ("quickstart-csharp", "quickstart-typescript", "quickstart-python", "quickstart-go"):
                page = (Path(out) / f"{slug}.html").read_text(encoding="utf-8")
                self.assertRegex(page, r"(?i)nothing is published|no .* implementation yet", slug)
                for command in ("dotnet add package", "npm install", "pip install", "go get ", "nuget.org/packages"):
                    self.assertNotIn(command, page, f"{slug} shows an install command: {command}")

    def test_the_schema_pages_exist_and_link_to_each_other(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(bs.build(ROOT, Path(out)), [])
            grid = (Path(out) / "grid-schema.html").read_text(encoding="utf-8")
            self.assertIn('href="ir-schema.html#filternode"', grid)
            self.assertIn('id="fieldconfig"', grid)

    def test_no_public_markdown_file_links_into_the_private_part(self):
        """AC-7 of #1666: the public mirror does not carry docs/, so a link into it is dead there. Inline links and images
        are read by the converter; reference definitions and raw <a href> are read here."""
        skip_dirs = {"node_modules", "bin", "obj", "_build", ".git", "github"}
        reference = re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
        raw = re.compile(r"""(?:href|src)=["']([^"']+)["']""")
        offenders = []
        for folder, dirs, names in os.walk(ROOT):
            rel_folder = Path(folder).relative_to(ROOT).as_posix()
            dirs[:] = [d for d in dirs if d not in skip_dirs and not bs._is_private(f"{rel_folder}/{d}" if rel_folder != "." else d)]
            for name in names:
                if not name.endswith(".md"):
                    continue
                path = Path(folder) / name
                rel = path.relative_to(ROOT).as_posix()
                if bs._is_private(rel):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                found = list(bs.render_markdown(text).links)
                for number, line in enumerate(text.splitlines(), 1):
                    m = reference.match(line)
                    if m:
                        found.append((number, m.group(1)))
                    found.extend((number, href) for href in raw.findall(line))
                for line, href in found:
                    if bs.EXTERNAL.match(href) or href.startswith("#"):
                        continue
                    target = os.path.normpath(os.path.join(os.path.dirname(rel), href.partition("#")[0])).replace(os.sep, "/")
                    if bs._is_private(target):
                        offenders.append(f"{rel}:{line}: {href}")
        self.assertEqual(offenders, [], "public Markdown files link into the private part of the repository")


if __name__ == "__main__":
    unittest.main()
