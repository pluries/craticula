#!/usr/bin/env python3
"""SEC-2 lint for the TypeScript query builders: only a placeholder, a quoted identifier or a constant may be spliced into query
text (TRD SEC-2; feature 014, US4). The TypeScript counterpart of scripts/lint-sec2.py, in the same spirit and with a smaller reach.

Usage: lint-sec2-ts.py [--root <repo>] [--allowlist <file>] [--explain] [paths...]   (stdlib, Python 3.10+)

Default scope: typescript/src/sql/**/*.ts. Paths are files or folders relative to --root. Exit codes: 0 clean; 1 at least one finding
or one stale allowlist entry, each finding printed as `file:line: SEC-2: <expression> - <why>`; 2 usage or environment error (a scope
path missing or holding no .ts file, a malformed allowlist, source the scanner cannot read: it fails closed).

WHAT COUNTS AS QUERY TEXT. Every template literal in a scoped file is presumed query text, and so is every operand of a `+` next to a
string or template literal. Exempt: a template that is an argument of `precondition(...)` or `new CompileError(...)`: an error message.

WHEN A SPLICE IS SAFE. Checked by provenance, recursively, under this closed list:
  - a string, number, boolean or null literal;
  - a template literal whose own holes are all safe;
  - a CONSTANT_CASE name, or an index of one (`COMPARISON_SYMBOL[op]`): compile-time text;
  - a call to a function that is declared in the scanned files, by name: its body is scanned as well. A call on an object counts only
    when the object is the dialect, the sink or the bag (`dialect.quoteIdentifier(...)`, `sink.bind(...)`): `field.substring(0)` is a
    string method that only shares a name. `outputName` and `columnId` return what the client named, so they are never safe. Names that start with `escape`, `encode`
    or `normalize` are NOT safe: escaping a value does not make it query text, binding it does;
  - `a ? b : c`, `a || b`, `a ?? b` whose branches are safe;
  - `list.map(x => safe).join(sep)`, and a list literal whose items are safe;
  - a name whose every assignment (`const`, `let`, `=`, `+=`) is safe, unless the name is also a parameter of some function in the
    file: a parameter comes from a caller, so it is a finding unless an allowlist entry vouches for it.
Anything else is a finding: a parameter, a member of a runtime object (`request.value`, `field.sql.text`), a call the scanner cannot see.

ALLOWLIST (scripts/sec2-ts-allowlist.txt), one entry per line, '#' comments:
  `trust <file> | <expression> | <reason>`: a reviewed trust boundary, accepted as it stands. The key is the file and the exact
    expression (whitespace collapsed). Only for a value that is not a user value: a quoting or placeholder primitive's own input, a
    parameter that arrives quoted from the one caller that quotes it. A user value in query text is a defect to fix, never an entry.
  `skip-file <file> | <reason>`: the file builds no query text (bound values, escaping of bound values).
An entry that matches nothing in the run fails it (exit 1), so the file cannot rot.
"""
import argparse
import re
import sys
from pathlib import Path

DEFAULT_SCOPE = ["typescript/src/sql", "typescript/src/mongo", "typescript/src/search", "typescript/src/doc"]
# Server-side script and write operators: a compile-only library has no use for them, and a value reaching one would run as code.
FORBIDDEN_OPERATORS = {"$where", "$function", "$accumulator", "$out", "$merge", "script", "script_score", "scripted_metric", "script_fields"}
TAINTED_PREFIXES = ("escape", "encode", "normalize")
# Functions that return a name or a value the client chose, not text the builder wrote: they are never safe to splice, whatever they are called.
UNQUOTED_NAMES = {"outputName", "columnId"}
# Pattern escapers: in a document builder their result is a pattern VALUE embedded as a JSON value (a regular expression, a wildcard), never a key
# or query text. In SQL text an escaped value is still a finding: escaping does not make it text, binding does.
DOCUMENT_ESCAPERS = {"escapeRegex", "escapeSearchRegex", "escapeWildcard"}
# The objects whose methods produce query text or placeholders: the dialect, the parameter sink and the parameter bag.
DIALECT_RECEIVERS = {"dialect", "sink", "bag"}
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "await", "typeof", "new"}
MESSAGE_CALLS = re.compile(r"(?:precondition|failure|CompileError)\(\s*(?:\x01S\d+\x01\s*,\s*)?$")


class ScanError(Exception):
    pass


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Source:
    """A file with comments removed and every string and template literal replaced by a token (`\x01S3\x01`, `\x01T4\x01`)."""

    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.templates: list[dict] = []
        self.strings: list[str] = []
        self.code = self._mask(text, 0)[0]

    def _mask(self, text: str, base_line: int, start: int = 0, stop_at_brace: bool = False):
        out: list[str] = []
        i = start
        line = base_line
        depth = 0
        while i < len(text):
            c = text[i]
            skipped = self._skip_comment(text, i, line)
            if c == "\n":
                line += 1
                out.append(c)
                i += 1
            elif skipped is not None:
                i, line = skipped
            elif c in "'\"":
                token, i = self._string(text, i, line)
                out.append(token)
            elif c == "`":
                token, i, line = self._template(text, i, line)
                out.append(token)
            elif stop_at_brace and c == "}" and depth == 0:
                return "".join(out), i, line
            else:
                depth += {"{": 1, "}": -1}.get(c, 0) if stop_at_brace else 0
                out.append(c)
                i += 1
        return "".join(out), i, line

    def _skip_comment(self, text: str, i: int, line: int):
        """The position and line after a comment that starts at `i`, or None when none does."""
        if text.startswith("//", i):
            end = text.find("\n", i)
            return (len(text) if end < 0 else end), line
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ScanError(f"{self.path}: unterminated comment")
            return end + 2, line + text.count("\n", i, end)
        return None

    def _string(self, text: str, i: int, line: int):
        quote = text[i]
        j = i + 1
        while j < len(text) and text[j] != quote:
            j += 2 if text[j] == "\\" else 1
            if j < len(text) and text[j] == "\n":
                raise ScanError(f"{self.path}:{line}: a string runs past the end of the line")
        if j >= len(text):
            raise ScanError(f"{self.path}:{line}: unterminated string")
        self.strings.append(text[i : j + 1])
        return f"\x01S{len(self.strings) - 1}\x01", j + 1

    def _template(self, text: str, i: int, line: int):
        start_line = line
        holes: list[str] = []
        j = i + 1
        while j < len(text) and text[j] != "`":
            if text[j] == "\\":
                j += 2
                continue
            if text.startswith("${", j):
                # the hole is source of its own: find the matching brace, honouring nested strings and templates
                scratch = Source(self.path, "")
                scratch.templates = self.templates
                scratch.strings = self.strings
                masked, end, line = scratch._mask(text, line, j + 2, stop_at_brace=True)
                holes.append(masked)
                j = end + 1
                continue
            if text[j] == "\n":
                line += 1
            j += 1
        if j >= len(text):
            raise ScanError(f"{self.path}:{start_line}: unterminated template literal")
        self.templates.append({"line": start_line, "holes": holes, "at": i, "raw": text[i + 1 : j]})
        return f"\x01T{len(self.templates) - 1}\x01", j + 1, line


def top_level_split(expr: str, token: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    last = 0
    i = 0
    while i < len(expr):
        c = expr[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and expr.startswith(token, i) and not (token == "?" and expr.startswith("?.", i)) and not (token == "?" and expr.startswith("??", i)):
            parts.append(expr[last:i])
            last = i + len(token)
            i += len(token)
            continue
        i += 1
    parts.append(expr[last:])
    return parts


def ternary_arms(expr: str):
    """The two arms of a top-level `c ? a : b` (the condition is not provenance), or None. The `:` that closes the first `?` skips nested ones."""
    depth = 0
    question = -1
    nested = 0
    for i, c in enumerate(expr):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == "?" and not expr.startswith(("?.", "??"), i) and not expr.startswith("??", i - 1):
            if question < 0:
                question = i
            else:
                nested += 1
        elif depth == 0 and c == ":" and question >= 0:
            if nested == 0:
                return [expr[question + 1 : i], expr[i + 1 :]]
            nested -= 1
    return None


def matching_paren(expr: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(expr)):
        if expr[i] in "([{":
            depth += 1
        elif expr[i] in ")]}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def skip_space(code: str, index: int) -> int:
    while index < len(code) and code[index].isspace():
        index += 1
    return index


def identifier_before(code: str, end: int) -> str:
    """The identifier that ends just before `end` (spaces skipped), or an empty string."""
    stop = end
    while stop > 0 and code[stop - 1].isspace():
        stop -= 1
    start = stop
    while start > 0 and (code[start - 1].isalnum() or code[start - 1] in "_$"):
        start -= 1
    return code[start:stop]


def binding_before(code: str, index: int) -> str:
    """The name an arrow is bound to (`name = (`, `name: (`), or an empty string for an anonymous one."""
    stop = index
    while stop > 0 and code[stop - 1].isspace():
        stop -= 1
    if stop == 0 or code[stop - 1] not in "=:":
        return ""
    return identifier_before(code, stop - 1)


def return_type_end(code: str, colon: int) -> int:
    """The index of the `{` or `=>` that ends a return type annotation starting at `colon`, or -1 when this is not one."""
    for j in range(colon + 1, len(code)):
        if code.startswith("=>", j) or code[j] == "{":
            return j
        if code[j] in ";),?" or (code[j] == "=" and not code.startswith("=>", j)):
            return -1
    return -1


def definitions(code: str) -> list[tuple[str, str]]:
    """(name, parameter text) of every function, method and arrow in the code; the name is empty for an anonymous arrow."""
    found: list[tuple[str, str]] = []
    for i, c in enumerate(code):
        close = matching_paren(code, i) if c == "(" else -1
        if close < 0:
            continue
        after = skip_space(code, close + 1)
        if code.startswith(":", after):
            after = return_type_end(code, after)
        if after < 0 or not (code.startswith("{", after) or code.startswith("=>", after)):
            continue
        name = identifier_before(code, i)
        if name in KEYWORDS:
            continue
        found.append((name or binding_before(code, i), code[i + 1 : close]))
    return found


def parameter_names(text: str) -> set[str]:
    names: set[str] = set()
    for item in top_level_split(text, ","):
        word = item.strip().removeprefix("readonly ").removeprefix("...").strip()
        end = 0
        while end < len(word) and (word[end].isalnum() or word[end] in "_$"):
            end += 1
        if end:
            names.add(word[:end])
    return names


def statement_end(code: str, start: int) -> int:
    depth = 0
    for i in range(start, len(code)):
        c = code[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == ";" and depth == 0:
            return i
    return len(code)


def assignment_target(code: str, equals: int) -> tuple[str, bool]:
    """The name an `=` or `+=` at `equals` assigns to, and whether it appends; an empty name for anything else (a member, a comparison)."""
    if code.startswith(("==", "=>"), equals) or (equals > 0 and code[equals - 1] in "=!<>"):
        return "", False
    last = equals - 1
    appends = last >= 0 and code[last] == "+"
    if appends:
        last -= 1
    elif last >= 0 and code[last] in "-*/%|&^":
        return "", False
    begin = max(code.rfind(mark, 0, last + 1) for mark in (";", "{", "}", "\n")) + 1
    head = code[begin : last + 1].strip()
    keyword, _, rest = head.partition(" ")
    if keyword in ("const", "let", "var"):
        head = rest.strip().split(":", 1)[0].strip()
    return (head if head.isidentifier() else ""), appends


def pushed_values(code: str) -> list[tuple[str, str]]:
    """(list name, pushed arguments) of every `list.push(...)`: the pushed value flows into the list."""
    found: list[tuple[str, str]] = []
    cursor = code.find(".push(")
    while cursor >= 0:
        receiver = identifier_before(code, cursor)
        close = matching_paren(code, cursor + 5)
        if receiver and close > 0:
            found.append((receiver, code[cursor + 6 : close]))
        cursor = code.find(".push(", cursor + 1)
    return found


def loop_sources(code: str) -> list[tuple[str, str]]:
    """(loop variable, source list) of every `for (const x of list)`."""
    found: list[tuple[str, str]] = []
    cursor = code.find("for (")
    while cursor >= 0:
        close = matching_paren(code, cursor + 4)
        keyword, _, rest = (code[cursor + 5 : close] if close > 0 else "").strip().partition(" ")
        name, _, source_list = rest.partition(" of ")
        if keyword in ("const", "let") and source_list and name.strip().isidentifier():
            found.append((name.strip(), source_list))
        cursor = code.find("for (", cursor + 1)
    return found


def collect_assignments(code: str) -> tuple[dict[str, list[str]], list[tuple[int, str]]]:
    """Every value assigned to each name (`=`, `+=`, a pushed argument, a for-of source) and the values appended with `+=`."""
    found: dict[str, list[str]] = {}
    appended: list[tuple[int, str]] = []
    for i, c in enumerate(code):
        target, appends = assignment_target(code, i) if c == "=" else ("", False)
        if not target:
            continue
        value = code[i + 1 : statement_end(code, i + 1)]
        found.setdefault(target, []).append(value)
        if appends:
            appended.append((i, value))
    for name, value in pushed_values(code) + loop_sources(code):
        found.setdefault(name, []).append(value)
    return found, appended


def call_on(expr: str, method: str):
    """`(receiver, arguments)` when the whole expression is `receiver.method(arguments)`, else None."""
    marker = f".{method}("
    index = expr.rfind(marker)
    open_index = index + len(marker) - 1
    if index < 0 or matching_paren(expr, open_index) != len(expr) - 1:
        return None
    return expr[:index], expr[open_index + 1 : -1]


def arrow_body(arguments: str):
    """The body of a single arrow function passed as the argument, or None."""
    head, arrow, body = arguments.partition("=>")
    if not arrow or not all(ch.isalnum() or ch in "_$, ()" for ch in head):
        return None
    return body.strip()


class Scanner:
    def __init__(self, sources: list[Source], allowlist: dict) -> None:
        self.sources = sources
        self.allow = allowlist
        self.used: set = set()
        defs = {source.path: definitions(source.code) for source in sources}
        self.declared = {name for found in defs.values() for name, _ in found if name and name not in KEYWORDS and not name.startswith(TAINTED_PREFIXES)}
        self.params = {path: {name for _, text in found for name in parameter_names(text)} for path, found in defs.items()}
        collected = {source.path: collect_assignments(source.code) for source in sources}
        self.assignments = {path: values for path, (values, _) in collected.items()}
        self.appended = {path: values for path, (_, values) in collected.items()}
        self.findings: list[tuple[str, int, str, str]] = []

    # ---- provenance -------------------------------------------------------------------------------------------------

    @staticmethod
    def shown(source: Source, text: str) -> str:
        """The expression as written: string literals put back (a template stays a token), whitespace collapsed."""
        return collapse(re.sub(r"\x01S(\d+)\x01", lambda m: source.strings[int(m.group(1))], text))

    def safe(self, source: Source, expr: str, seen: frozenset = frozenset()) -> bool:
        e = collapse(expr)
        while e.startswith("(") and matching_paren(e, 0) == len(e) - 1:
            e = e[1:-1].strip()
        if e == "" or re.fullmatch(r"\x01S\d+\x01|\d+(?:\.\d+)?|true|false|null|undefined", e):
            return True
        key = (source.path, self.shown(source, e))
        if key in self.allow:
            self.used.add(key)
            return True
        for rule in (self._safe_template, self._safe_branches, self._safe_constant, self._safe_array, self._safe_chain, self._safe_call, self._safe_name):
            verdict = rule(source, e, seen)
            if verdict is not None:
                return verdict
        return False

    def _safe_template(self, source: Source, e: str, seen: frozenset):
        template = re.fullmatch(r"\x01T(\d+)\x01", e)
        if template is None:
            return None
        return all(self.safe(source, hole, seen) for hole in source.templates[int(template.group(1))]["holes"])

    def _safe_branches(self, source: Source, e: str, seen: frozenset):
        arms = ternary_arms(e)
        if arms is not None:
            return all(self.safe(source, arm, seen) for arm in arms)
        for token in ("||", "??"):
            parts = top_level_split(e, token)
            if len(parts) > 1:
                return all(self.safe(source, part, seen) for part in parts)
        return None

    @staticmethod
    def _safe_constant(source: Source, e: str, seen: frozenset):
        return True if re.fullmatch(r"[A-Z][A-Z0-9_]+(?:\[[^\]]*\])?!?", e) else None

    def _safe_array(self, source: Source, e: str, seen: frozenset):
        if not (e.startswith("[") and matching_paren(e, 0) == len(e) - 1):
            return None
        items = [item.strip() for item in top_level_split(e[1:-1], ",") if item.strip()]
        return all(self.safe(source, item.removeprefix("..."), seen) for item in items)

    def _safe_chain(self, source: Source, e: str, seen: frozenset):
        joined = call_on(e, "join")
        if joined is not None:
            return self._safe_items(source, joined[0], seen)
        if call_on(e, "map") is not None:
            return self._safe_items(source, e, seen)
        return None

    def _safe_items(self, source: Source, receiver: str, seen: frozenset) -> bool:
        r = receiver.strip()
        mapped = call_on(r, "map")
        if mapped is None:
            return self.safe(source, r, seen)
        body = arrow_body(mapped[1])
        return body is not None and self.safe(source, body, seen)

    def _safe_call(self, source: Source, e: str, seen: frozenset):
        open_index = e.find("(")
        if open_index <= 0 or matching_paren(e, open_index) != len(e) - 1:
            return None
        path = e[:open_index].strip().replace("?.", ".").split(".")
        if not all(part.isidentifier() for part in path):
            return None
        if path[-1] in DOCUMENT_ESCAPERS and ("/mongo/" in source.path or "/search/" in source.path):
            return True
        if path[-1] in UNQUOTED_NAMES or path[-1] not in self.declared:
            return False
        return len(path) == 1 or path[-2] in DIALECT_RECEIVERS

    def _safe_name(self, source: Source, e: str, seen: frozenset):
        if not e.isidentifier():
            return None
        if e in self.params[source.path]:
            return False
        if e in seen:
            return True
        values = self.assignments[source.path].get(e)
        return bool(values) and all(self.safe(source, value, seen | {e}) for value in values)

    # ---- sinks ------------------------------------------------------------------------------------------------------

    def scan(self) -> None:
        for source in self.sources:
            if (source.path, "*") in self.allow:
                self.used.add((source.path, "*"))
                continue
            self._templates(source)
            self._concatenations(source)
            self._appended_values(source)
            self._document_keys(source)
            self._spreads(source)
            self._script_operators(source)

    @staticmethod
    def line_of(source: Source, offset: int) -> int:
        return source.code.count("\n", 0, offset) + 1

    def _templates(self, source: Source) -> None:
        for index, template in enumerate(source.templates):
            token = f"\x01T{index}\x01"
            at = source.code.find(token)
            if MESSAGE_CALLS.search(source.code[max(0, at - 80) : at]):
                continue
            for hole in template["holes"]:
                if not self.safe(source, hole):
                    self.findings.append((source.path, self.line_of(source, at), self.shown(source, hole), "interpolated into query text and not a placeholder, a quoted identifier or a constant"))

    def _appended_values(self, source: Source) -> None:
        """`x += value` builds text, so its value is a sink of its own, even when no template or literal is next to it."""
        for offset, value in self.appended[source.path]:
            if not self.safe(source, value):
                self.findings.append((source.path, self.line_of(source, offset), self.shown(source, value), "appended to query text and not a placeholder, a quoted identifier or a constant"))

    def _document_keys(self, source: Source) -> None:
        """A key of a document (`doc(["key", value])`, `new Map([[key, value]])`, `.set(key, value)`) must be a literal, a constant or a schema name the builder resolved."""
        for offset, key in self._keys_of(source.code):
            escaped = any(name in key for name in DOCUMENT_ESCAPERS)
            if escaped or not self.safe(source, key):
                self.findings.append((source.path, self.line_of(source, offset), self.shown(source, key), "used as a document key and not a literal, a constant or a name the builder resolved from the schema"))

    @staticmethod
    def _call_arguments(code: str, marker: str) -> list[tuple[int, str]]:
        """(offset, argument text) of every call that starts with `marker`."""
        found: list[tuple[int, str]] = []
        cursor = code.find(marker)
        while cursor >= 0:
            close = matching_paren(code, cursor + len(marker) - 1)
            if close > 0:
                found.append((cursor, code[cursor + len(marker) : close]))
            cursor = code.find(marker, cursor + 1)
        return found

    @staticmethod
    def _entry_keys(offset: int, arguments: list[str]) -> list[tuple[int, str]]:
        """The key of each `[key, value]` entry among the arguments; an argument that is not an entry list is itself the unknown source of keys."""
        keys: list[tuple[int, str]] = []
        for argument in arguments:
            text = argument.strip().removeprefix("...")
            if not text:
                continue
            keys.append((offset, top_level_split(text[1:], ",")[0] if text.startswith("[") else text))
        return keys

    def _keys_of(self, code: str) -> list[tuple[int, str]]:
        found: list[tuple[int, str]] = []
        for offset, inner in self._call_arguments(code, "doc("):
            found += self._entry_keys(offset, top_level_split(inner, ","))
        for offset, inner in self._call_arguments(code, "new Map("):
            outer = inner.strip()
            entries = top_level_split(outer[1:-1], ",") if outer.startswith("[") and outer.endswith("]") else [outer]
            found += self._entry_keys(offset, entries)
        for offset, inner in self._call_arguments(code, ".set("):
            if inner.strip():
                found.append((offset, top_level_split(inner, ",")[0]))
        return found

    def _spreads(self, source: Source) -> None:
        """`{ ...x }` copies every member of x into a document: x must be something the builder made, never a request object."""
        cursor = source.code.find("...")
        while cursor >= 0:
            end = cursor + 3
            while end < len(source.code) and (source.code[end].isalnum() or source.code[end] in "_$"):
                end += 1
            operand = source.code[cursor + 3 : end]
            enclosing = source.code.rfind("{", 0, cursor)
            key = (source.path, f"...{operand}")
            if key in self.allow:
                self.used.add(key)
            elif operand and enclosing > source.code.rfind("[", 0, cursor) and not self.safe(source, operand):
                self.findings.append((source.path, self.line_of(source, cursor), f"...{operand}", "spread into an object; spread only what the builder made"))
            cursor = source.code.find("...", end)

    def _script_operators(self, source: Source) -> None:
        literals = [(f"\x01S{index}\x01", literal[1:-1]) for index, literal in enumerate(source.strings)]
        literals += [(f"\x01T{index}\x01", template["raw"]) for index, template in enumerate(source.templates) if not template["holes"]]
        for token, text in literals:
            if text in FORBIDDEN_OPERATORS:
                at = source.code.find(token)
                self.findings.append((source.path, self.line_of(source, at), text, "a server-side script or write operator, which a compile-only library never emits"))

    def _concatenations(self, source: Source) -> None:
        for match in re.finditer(r"(\x01[ST]\d+\x01)\s*\+(?!=)|(?<!\+)\+\s*(\x01[ST]\d+\x01)", source.code):
            begin = max(source.code.rfind(mark, 0, match.start()) for mark in (";", "{", "}")) + 1
            end = source.code.find(";", match.end())
            snippet = self.shown(source, source.code[begin : len(source.code) if end < 0 else end])
            if (source.path, snippet) in self.allow:
                self.used.add((source.path, snippet))
                continue
            at = match.start()
            if MESSAGE_CALLS.search(source.code[max(0, at - 80) : at]):
                continue
            self.findings.append((source.path, self.line_of(source, at), snippet, "concatenated into query text; build it as a template whose holes are safe"))


def load_allowlist(path: Path) -> dict:
    allow: dict = {}
    if not path.exists():
        return allow
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        kind = parts[0].split(" ", 1)[0]
        if kind == "trust" and len(parts) >= 3 and parts[0] != "trust":
            file = parts[0].split(" ", 1)[1].strip()
            expression = collapse("|".join(parts[1:-1]))
            allow[(file, expression)] = parts[-1]
        elif kind == "skip-file" and len(parts) == 2 and parts[0] != "skip-file":
            allow[(parts[0].split(" ", 1)[1].strip(), "*")] = parts[1]
        else:
            raise ScanError(f"{path.name}:{number}: not a `trust <file> | <expression> | <reason>` or `skip-file <file> | <reason>` entry")
        if not parts[-1]:
            raise ScanError(f"{path.name}:{number}: an entry needs a reason")
    return allow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--allowlist", default=None)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    allowlist_path = Path(args.allowlist) if args.allowlist else Path(__file__).resolve().parent / "sec2-ts-allowlist.txt"
    try:
        files: list[Path] = []
        for scope in args.paths or DEFAULT_SCOPE:
            target = root / scope
            found = []
            if target.is_file():
                found = [target]
            elif target.is_dir():
                found = sorted(target.rglob("*.ts"))
            if not found:
                raise ScanError(f"scope path '{scope}' is missing or holds no .ts file")
            files.extend(found)
        allow = load_allowlist(allowlist_path)
        sources = [Source(file.relative_to(root).as_posix(), file.read_text(encoding="utf-8")) for file in files]
        scanner = Scanner(sources, allow)
        scanner.scan()
    except ScanError as error:
        print(f"lint-sec2-ts: {error}", file=sys.stderr)
        return 2
    stale = [key for key in allow if key not in scanner.used]
    for path, line, expression, why in scanner.findings:
        print(f"{path}:{line}: SEC-2: {expression} - {why}")
    for file, expression in stale:
        print(f"{allowlist_path.name}: stale entry: {file} | {expression} matches nothing in this run", file=sys.stderr)
    if scanner.findings or stale:
        return 1
    print(f"PASS: SEC-2 lint (TypeScript), {len(sources)} files, {len(allow)} reviewed allowlist entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
