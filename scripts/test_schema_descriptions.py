#!/usr/bin/env python3
"""Plain descriptions in the two schema files (docs site v2, story #3554, task #3561; DS-20, risk R5): every `description` of
spec/grid-schema.schema.json and spec/ir.schema.json is plain English of at most three sentences with no coded reference, and the
original text moved unchanged to `$comment` on the same member, which the schema reference pages do not show. Standard library only.

Contract pinned here:
  * The baseline `scripts/schema-descriptions-baseline.json` is the snapshot taken before the rewrite: per schema file the string-valued
    `description` (72 members: 22 in grid-schema, 50 in ir) and `$comment` (1: ir `/$defs/setValuesSpec/properties/searchPrefix`) keywords
    by the RFC 6901 JSON Pointer of the schema node that holds them ("" is the root, `~` is `~0`, `/` is `~1`, array items by index),
    byte for byte, and `skeletonSha256`: the SHA-256 of the schema without any string-valued description or $comment key, as canonical
    JSON (sorted keys, separators "," and ":", ensure_ascii off, UTF-8). The baseline is public (spec text only).
  * A member whose description changed: its `$comment` is the original description; when the member already had a `$comment`, it is the
    original description, a blank line (two line feeds), then the original `$comment`.
  * A member whose description is unchanged must already be plain (no coded reference, at most three sentences) and keeps its `$comment`.
  * Descriptions exist at exactly the baseline pointers (none added, none removed); a description is a non-empty string.
  * "Validates the same documents": the skeleton hash is unchanged, so no keyword other than description and $comment moved.
  * The generated schema reference pages never show a `$comment`.
A sentence is counted as a `.`, `!` or `?` followed by a space or the end of the text, after `e.g.` and `i.e.` are removed.
Run: python3 scripts/test_schema_descriptions.py
"""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402
from test_build_site_structure import CODED, TICKET  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "schema-descriptions-baseline.json"
FILES = ("grid-schema.schema.json", "ir.schema.json")
COUNTS = {"grid-schema.schema.json": 22, "ir.schema.json": 50}
TERMINATOR = re.compile(r"[.!?](?:\s|$)")


def escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def collect(node, pointer: str, keyword: str, found: dict) -> dict:
    """pointer -> text of every string-valued `keyword` of the schema nodes under `node`."""
    if isinstance(node, dict):
        if isinstance(node.get(keyword), str):
            found[pointer] = node[keyword]
        for key, child in node.items():
            collect(child, f"{pointer}/{escape(key)}", keyword, found)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            collect(child, f"{pointer}/{index}", keyword, found)
    return found


def skeleton(node):
    if isinstance(node, dict):
        return {k: skeleton(v) for k, v in node.items() if not (k in ("description", "$comment") and isinstance(v, str))}
    if isinstance(node, list):
        return [skeleton(v) for v in node]
    return node


def skeleton_hash(schema) -> str:
    canonical = json.dumps(skeleton(schema), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sentences(text: str) -> int:
    return len(TERMINATOR.findall(text.replace("e.g.", "eg").replace("i.e.", "ie")))


def load(name: str) -> dict:
    return json.loads((ROOT / "spec" / name).read_text(encoding="utf-8"))


def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def expected_comment(original: str, existing: str | None) -> str:
    return original if existing is None else f"{original}\n\n{existing}"


class Baseline(unittest.TestCase):
    """The snapshot itself."""

    def test_the_baseline_holds_the_72_member_descriptions_and_the_one_comment(self):
        data = baseline()
        for name in FILES:
            self.assertEqual(COUNTS[name], len(data[name]["descriptions"]), name)
        self.assertEqual(["/$defs/setValuesSpec/properties/searchPrefix"], list(data["ir.schema.json"]["comments"]))
        self.assertEqual({}, data["grid-schema.schema.json"]["comments"])
        for name in FILES:
            self.assertRegex(data[name]["skeletonSha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(all(text.strip() for text in data[name]["descriptions"].values()))

    def test_the_baseline_is_public_spec_text_in_a_public_path(self):
        self.assertFalse(bs._is_private("scripts/schema-descriptions-baseline.json"))
        self.assertFalse(bs._is_private("scripts/test_schema_descriptions.py"))


class SchemaFiles(unittest.TestCase):
    def test_no_keyword_other_than_description_and_comment_changed_so_the_schemas_validate_the_same_documents(self):
        for name in FILES:
            with self.subTest(schema=name):
                self.assertEqual(baseline()[name]["skeletonSha256"], skeleton_hash(load(name)))

    def test_descriptions_stay_at_exactly_the_baseline_members_as_non_empty_strings(self):
        for name in FILES:
            with self.subTest(schema=name):
                current = collect(load(name), "", "description", {})
                self.assertEqual(sorted(baseline()[name]["descriptions"]), sorted(current))
                self.assertTrue(all(text.strip() for text in current.values()))

    def test_every_description_is_plain_with_no_coded_reference_and_at_most_three_sentences(self):
        for name in FILES:
            for pointer, text in collect(load(name), "", "description", {}).items():
                with self.subTest(schema=name, member=pointer):
                    self.assertNotRegex(text, CODED)
                    self.assertNotRegex(text, TICKET)
                    self.assertGreaterEqual(sentences(text), 1)
                    self.assertLessEqual(sentences(text), 3, text)

    def test_the_original_text_moved_unchanged_to_comment_on_every_rewritten_member(self):
        for name in FILES:
            original = baseline()[name]
            descriptions = collect(load(name), "", "description", {})
            comments = collect(load(name), "", "$comment", {})
            for pointer, before in original["descriptions"].items():
                with self.subTest(schema=name, member=pointer):
                    if CODED.search(before) or TICKET.search(before):
                        self.assertNotEqual(before, descriptions.get(pointer), "a coded description is rewritten")
                    if descriptions.get(pointer) == before:
                        self.assertEqual(original["comments"].get(pointer), comments.get(pointer), "an unchanged description keeps its comment")
                    else:
                        self.assertEqual(expected_comment(before, original["comments"].get(pointer)), comments.get(pointer))

    def test_a_description_that_stayed_the_same_was_already_plain(self):
        for name in FILES:
            current = collect(load(name), "", "description", {})
            for pointer, before in baseline()[name]["descriptions"].items():
                if current.get(pointer) == before:
                    with self.subTest(schema=name, member=pointer):
                        self.assertNotRegex(before, CODED)
                        self.assertNotRegex(before, TICKET)
                        self.assertLessEqual(sentences(before), 3)

    def test_the_comment_of_the_baseline_survives_inside_the_merged_comment(self):
        pointer = "/$defs/setValuesSpec/properties/searchPrefix"
        kept = baseline()["ir.schema.json"]["comments"][pointer]
        merged = collect(load("ir.schema.json"), "", "$comment", {}).get(pointer, "")
        self.assertTrue(merged.endswith("\n\n" + kept), "the earlier comment is kept after the original description")


class ReferencePages(unittest.TestCase):
    def test_the_reference_pages_never_show_a_comment_and_no_coded_reference_reaches_them(self):
        pages = {"grid-schema.schema.json": "grid-schema", "ir.schema.json": "ir-schema"}
        for name in FILES:
            schema = load(name)
            markdown = bs.schema_reference(schema, name, pages)
            with self.subTest(schema=name):
                for pointer, comment in collect(schema, "", "$comment", {}).items():
                    self.assertNotIn(comment, markdown, pointer)
                self.assertNotRegex(markdown, CODED)
                self.assertNotRegex(markdown, TICKET)

    def test_the_generator_hides_a_comment_and_shows_the_description(self):
        schema = {"title": "T", "properties": {"x": {"type": "string", "description": "A plain sentence.", "$comment": "SC-9 the original wording"}},
                  "$defs": {"d": {"description": "Plain too.", "$comment": "GRP-1 the original", "type": "object"}}}
        markdown = bs.schema_reference(schema, "t.schema.json", {"t.schema.json": "t"})
        self.assertIn("A plain sentence.", markdown)
        self.assertIn("Plain too.", markdown)
        self.assertNotIn("SC-9", markdown)
        self.assertNotIn("GRP-1", markdown)


class HelperGuards(unittest.TestCase):
    """The helpers the tests above lean on."""

    def test_pointers_escape_tilde_and_slash_and_index_arrays(self):
        found = collect({"a/b": {"description": "x"}, "c~d": [{"description": "y"}], "description": "root"}, "", "description", {})
        self.assertEqual({"": "root", "/a~1b": "x", "/c~0d/0": "y"}, found)

    def test_the_sentence_counter_ignores_abbreviations(self):
        self.assertEqual(2, sentences("Matches e.g. a prefix. Another one."))
        self.assertEqual(3, sentences("One. Two! Three?"))
        self.assertEqual(1, sentences("A single sentence."))
        self.assertEqual(0, sentences("No full stop at the end"))

    def test_the_skeleton_hash_ignores_only_string_annotations(self):
        base = {"type": "object", "description": "a", "properties": {"description": {"type": "string"}}}
        changed = {"type": "object", "description": "b", "$comment": "c", "properties": {"description": {"type": "string"}}}
        self.assertEqual(skeleton_hash(base), skeleton_hash(changed))
        self.assertNotEqual(skeleton_hash(base), skeleton_hash({**base, "type": "array"}))


if __name__ == "__main__":
    unittest.main()
