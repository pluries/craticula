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

DEFAULT_SCOPE = ["typescript/src/sql"]
TAINTED_PREFIXES = ("escape", "encode", "normalize")
# Functions that return a name or a value the client chose, not text the builder wrote: they are never safe to splice, whatever they are called.
UNQUOTED_NAMES = {"outputName", "columnId"}
# The objects whose methods produce query text or placeholders: the dialect, the parameter sink and the parameter bag.
DIALECT_RECEIVERS = {"dialect", "sink", "bag"}
MESSAGE_CALLS = re.compile(r"(?:precondition|CompileError)\(\s*(?:\x01S\d+\x01\s*,\s*)?$")


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
            if c == "\n":
                line += 1
                out.append(c)
                i += 1
            elif text.startswith("//", i):
                while i < len(text) and text[i] != "\n":
                    i += 1
            elif text.startswith("/*", i):
                end = text.find("*/", i + 2)
                if end < 0:
                    raise ScanError(f"{self.path}: unterminated comment")
                line += text.count("\n", i, end)
                i = end + 2
            elif c in "'\"":
                j = i + 1
                while j < len(text) and text[j] != c:
                    if text[j] == "\\":
                        j += 1
                    if j < len(text) and text[j] == "\n":
                        raise ScanError(f"{self.path}:{line}: a string runs past the end of the line")
                    j += 1
                if j >= len(text):
                    raise ScanError(f"{self.path}:{line}: unterminated string")
                self.strings.append(text[i : j + 1])
                out.append(f"\x01S{len(self.strings) - 1}\x01")
                i = j + 1
            elif c == "`":
                token, i, line = self._template(text, i, line)
                out.append(token)
            else:
                if stop_at_brace:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        if depth == 0:
                            return "".join(out), i, line
                        depth -= 1
                out.append(c)
                i += 1
        return "".join(out), i, line

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
        self.templates.append({"line": start_line, "holes": holes, "at": i})
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


class Scanner:
    def __init__(self, sources: list[Source], allowlist: dict) -> None:
        self.sources = sources
        self.allow = allowlist
        self.used: set = set()
        self.declared = self._declared_names()
        self.assignments = {source.path: self._assignments(source) for source in sources}
        self.params = {source.path: self._parameters(source) for source in sources}
        self.findings: list[tuple[str, int, str, str]] = []

    def _declared_names(self) -> set[str]:
        names: set[str] = set()
        for source in self.sources:
            code = source.code
            names.update(re.findall(r"\bfunction\s+(\w+)\s*\(", code))
            names.update(re.findall(r"\bconst\s+(\w+)\s*(?::[^=]+)?=\s*(?:\([^)]*\)|\w+)\s*(?::[^=>{]+)?=>", code))
            names.update(re.findall(r"(?m)^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*[^{=;]+)?\s*\{", code))
            names.update(re.findall(r"(?m)^\s*(\w+)\s*:\s*(?:\([^)]*\)|\w+)\s*(?::\s*[^=>{]+)?=>", code))
        return {name for name in names if not name.startswith(TAINTED_PREFIXES) and name not in {"if", "for", "while", "switch", "catch"}}

    @staticmethod
    def _parameters(source: Source) -> set[str]:
        """Every name a function or arrow declares as a parameter: a value that comes from a caller, so it is never safe by assignment."""
        code = source.code
        lists = re.findall(r"\bfunction\s+\w+\s*\(([^)]*)\)", code)
        lists += re.findall(r"(?m)^\s*(?:async\s+)?\w+\s*\(([^)]*)\)\s*(?::\s*[^{=;]+)?\s*\{", code)
        lists += re.findall(r"(?m)^\s*\w+\s*:\s*\(([^)]*)\)\s*(?::\s*[^=>{]+)?=>", code)
        lists += re.findall(r"\(([^()]*)\)\s*=>", code)
        names: set[str] = set()
        for group in lists:
            for item in top_level_split(group, ","):
                match = re.match(r"\s*(?:readonly\s+)?(?:\.\.\.)?(\w+)", item)
                if match:
                    names.add(match.group(1))
        return names

    def _assignments(self, source: Source) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        code = source.code
        for match in re.finditer(r"\b(?:const|let|var)\s+(\w+)\s*(?::[^=;]+?)?=(?!=|>)\s*", code):
            end = self._statement_end(code, match.end())
            found.setdefault(match.group(1), []).append(code[match.end() : end])
        for match in re.finditer(r"(?<![\w.])(\w+)\s*\+?=(?!=|>)\s*", code):
            before = code[max(0, match.start() - 8) : match.start()]
            if re.search(r"(?:const|let|var)\s*$", before):
                continue
            end = self._statement_end(code, match.end())
            found.setdefault(match.group(1), []).append(code[match.end() : end])
        for match in re.finditer(r"(?<![\w.])(\w+)\.push\(", code):
            close = matching_paren(code, match.end() - 1)
            if close > 0:
                found.setdefault(match.group(1), []).append(code[match.end() : close])
        for match in re.finditer(r"\bfor\s*\(\s*(?:const|let)\s+(\w+)\s+of\s+([^)]*)\)", code):
            found.setdefault(match.group(1), []).append(match.group(2))
        return found

    @staticmethod
    def _statement_end(code: str, start: int) -> int:
        depth = 0
        for i in range(start, len(code)):
            c = code[i]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    return i
                depth -= 1
            elif c in ";\n" and depth == 0 and c == ";":
                return i
        return len(code)

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
        template = re.fullmatch(r"\x01T(\d+)\x01", e)
        if template:
            return all(self.safe(source, hole, seen) for hole in source.templates[int(template.group(1))]["holes"])
        arms = ternary_arms(e)
        if arms is not None:
            return all(self.safe(source, arm, seen) for arm in arms)
        for token in ("||", "??"):
            parts = top_level_split(e, token)
            if len(parts) > 1:
                return all(self.safe(source, part, seen) for part in parts)
        if re.fullmatch(r"[A-Z][A-Z0-9_]+(?:\[[^\]]*\])?", e):
            return True
        if e.startswith("[") and matching_paren(e, 0) == len(e) - 1:
            items = [item.strip() for item in top_level_split(e[1:-1], ",") if item.strip()]
            return all(self.safe(source, item[3:] if item.startswith("...") else item, seen) for item in items)
        joined = re.fullmatch(r"(.*)\.join\((.*)\)", e)
        if joined and matching_paren(e, e.rindex(".join(") + 5) == len(e) - 1:
            return self._safe_list(source, joined.group(1), seen)
        mapped = re.fullmatch(r"(.*)\.map\((.*)\)", e, re.S)
        if mapped and matching_paren(e, e.rindex(".map(") + 4) == len(e) - 1:
            return self._safe_list(source, e, seen)
        call = re.fullmatch(r"([\w$]+(?:\??\.[\w$]+)*)\s*(?:<[^>]*>)?\((.*)\)", e)
        if call and matching_paren(e, e.index("(", len(call.group(1)))) == len(e) - 1:
            path = re.split(r"\??\.", call.group(1))
            if path[-1] in UNQUOTED_NAMES or path[-1] not in self.declared:
                return False
            return len(path) == 1 or path[-2] in DIALECT_RECEIVERS
        if re.fullmatch(r"[A-Za-z_$][\w$]*", e):
            if e in self.params[source.path]:
                return False
            if e in seen:
                return True
            values = self.assignments[source.path].get(e)
            return bool(values) and all(self.safe(source, value, seen | {e}) for value in values)
        return False

    def _safe_list(self, source: Source, receiver: str, seen: frozenset) -> bool:
        r = receiver.strip()
        mapped = re.fullmatch(r"(.*)\.map\((.*)\)", r)
        if mapped and matching_paren(r, r.rindex(".map(") + 4) == len(r) - 1:
            body = re.fullmatch(r"\s*\(?[\w\s,]*\)?\s*=>\s*(.*)", mapped.group(2), re.S)
            return body is not None and self.safe(source, body.group(1), seen)
        return self.safe(source, r, seen)

    # ---- sinks ------------------------------------------------------------------------------------------------------

    def scan(self) -> None:
        for source in self.sources:
            if (source.path, "*") in self.allow:
                self.used.add((source.path, "*"))
                continue
            self._templates(source)
            self._concatenations(source)
            self._appended_values(source)

    def line_of(self, source: Source, offset: int) -> int:
        return source.code.count("\n", 0, offset) + 1

    def _templates(self, source: Source) -> None:
        for index, template in enumerate(source.templates):
            token = f"\x01T{index}\x01"
            at = source.code.find(token)
            before = source.code[max(0, at - 80) : at]
            if MESSAGE_CALLS.search(before):
                continue
            for hole in template["holes"]:
                if not self.safe(source, hole):
                    self.findings.append((source.path, self.line_of(source, at), self.shown(source, hole), "interpolated into query text and not a placeholder, a quoted identifier or a constant"))

    def _appended_values(self, source: Source) -> None:
        """`x += value` builds text, so its value is a sink of its own, even when no template or literal is next to it."""
        for match in re.finditer(r"(?<![\w.])(\w+)\s*\+=(?!=)\s*", source.code):
            end = self._statement_end(source.code, match.end())
            value = source.code[match.end() : end]
            if not self.safe(source, value):
                self.findings.append((source.path, self.line_of(source, match.start()), self.shown(source, value), "appended to query text and not a placeholder, a quoted identifier or a constant"))

    def _concatenations(self, source: Source) -> None:
        for match in re.finditer(r"(\x01[ST]\d+\x01)\s*\+(?!=)|(?<!\+)\+\s*(\x01[ST]\d+\x01)", source.code):
            begin = max(source.code.rfind(mark, 0, match.start()) for mark in (";", "{", "}")) + 1
            end = source.code.find(";", match.end())
            snippet = self.shown(source, source.code[begin : len(source.code) if end < 0 else end])
            if (source.path, snippet) in self.allow:
                self.used.add((source.path, snippet))
                continue
            at = match.start()
            before = source.code[max(0, at - 80) : at]
            if MESSAGE_CALLS.search(before):
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
            found = [target] if target.is_file() else sorted(target.rglob("*.ts")) if target.is_dir() else []
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
