#!/usr/bin/env python3
"""Language-neutral conformance runner (spec/conformance-runner.md, TRD T-1 tier a).

Starts a driver command, streams every fixture case to it as JSON Lines, compares each answer with the expected
artifact under the backend's equality rule (spec §4) and reports. Python 3.10+, standard library only.

Exit status: 0 every graded case passed, 1 at least one failed, 2 protocol failure, usage error or an empty graded set
(spec §7).
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKENDS = ("postgres", "mssql", "mysql", "oracle", "sqlite", "mongo", "search")
SQL_BACKENDS = ("postgres", "mssql", "mysql", "oracle", "sqlite")
KINDS = ("rejection", "writer")  # the two other kinds of case (spec §2.2), graded under a hello capability (§2.1)
ARTIFACT_SUFFIX = ".artifact.json"
EXPORT_FILES = ("export.csv", "export.tsv")
DEFAULT_TIMEOUT = 30.0  # spec §2.4 item 4
MAX_LISTED = 20
POSIX = os.name != "nt"


class UsageError(Exception):
    pass


class ProtocolFailure(Exception):
    pass


# ---------------------------------------------------------------- literal-preserving JSON (spec §4)

class Num:
    """A JSON number kept as written: `1`, `1.0` and `1E0` are three different values."""
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class Obj:
    """A JSON object kept in document order."""
    __slots__ = ("pairs", "map")

    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        self.pairs = pairs
        self.map = dict(pairs)

    def keys(self) -> list[str]:
        return [k for k, _ in self.pairs]


def _reject_constant(name: str) -> object:
    raise ValueError(f"{name} is not valid JSON")


def parse_json(text: str) -> object:
    return json.loads(text, object_pairs_hook=Obj, parse_float=Num, parse_int=Num, parse_constant=_reject_constant)


def dumps(value: object) -> str:
    """Serialise a parsed value on one line, numbers exactly as written. ASCII only, so any string survives a pipe."""
    if isinstance(value, Obj):
        return "{" + ",".join(f"{json.dumps(k)}:{dumps(v)}" for k, v in value.pairs) + "}"
    if isinstance(value, list):
        return "[" + ",".join(dumps(v) for v in value) + "]"
    if isinstance(value, Num):
        return value.text
    return json.dumps(value)


def show(value: object, limit: int = 300) -> str:
    text = "<missing>" if value is MISSING else dumps(value)
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars)"


MISSING = object()


# ---------------------------------------------------------------- equality (spec §4)

def _kind(v: object) -> str:
    if isinstance(v, Obj):
        return "object"
    if isinstance(v, list):
        return "array"
    if isinstance(v, Num):
        return "number"
    if isinstance(v, bool):
        return "boolean"
    if v is None:
        return "null"
    return "string"


def first_diff(exp: object, act: object, path: str, ordered_keys: bool):
    """First place where the two values differ, as (path, expected, actual), or None. Numbers compare by text."""
    ke, ka = _kind(exp), _kind(act)
    if ke != ka:
        return path, show(exp), show(act)
    if ke == "object":
        if ordered_keys:
            ek, ak = exp.keys(), act.keys()
            if ek != ak:
                return path, "keys " + show(ek), "keys " + show(ak)
            for (k, ev), (_, av) in zip(exp.pairs, act.pairs):
                d = first_diff(ev, av, f"{path}.{k}", ordered_keys)
                if d:
                    return d
            return None
        for k, ev in exp.pairs:
            d = first_diff(ev, act.map.get(k, MISSING), f"{path}.{k}", ordered_keys) if k in act.map \
                else (f"{path}.{k}", show(ev), show(MISSING))
            if d:
                return d
        for k, av in act.pairs:
            if k not in exp.map:
                return f"{path}.{k}", show(MISSING), show(av)
        return None
    if ke == "array":
        for i, (ev, av) in enumerate(zip(exp, act)):
            d = first_diff(ev, av, f"{path}[{i}]", ordered_keys)
            if d:
                return d
        if len(exp) != len(act):
            i = min(len(exp), len(act))
            return (f"{path}[{i}]", show(exp[i] if i < len(exp) else MISSING),
                    show(act[i] if i < len(act) else MISSING))
        return None
    if ke == "number":
        return None if exp.text == act.text else (path, show(exp), show(act))
    return None if exp == act and (ke != "boolean" or exp is act) else (path, show(exp), show(act))


def compare(backend: str, exp: object, act: object):
    if backend in SQL_BACKENDS:  # dialect, sql, params by value; member order in the wrapper is not significant
        if not isinstance(exp, Obj) or not isinstance(act, Obj):
            return first_diff(exp, act, "$", True)
        for member in ("dialect", "sql", "params"):
            e, a = exp.map.get(member, MISSING), act.map.get(member, MISSING)
            d = (f"$.{member}", show(e), show(a)) if (e is MISSING or a is MISSING) and e is not a \
                else first_diff(e, a, f"$.{member}", True) if e is not MISSING else None
            if d:
                return d
        return None
    return first_diff(exp, act, "$", ordered_keys=(backend == "mongo"))  # search: OSE-0, unordered maps


# ---------------------------------------------------------------- fixtures (spec §1)

def _out_of_tier(d: Path, graded: bool) -> list[str]:
    """What this directory carries that the tier does not grade — by content, even beside a graded artifact."""
    reasons = []
    if (d / "dataset.json").exists() or (d / "expectedRows.json").exists():
        reasons.append("execution equality (T-1b)")
    return reasons or ([] if graded else ["no graded file"])


def case_kinds(d: Path) -> list[str]:
    """The backends with an expected artifact, then `rejection` and `writer` when the folder carries them (§1)."""
    exp = d / "expected"
    stems = sorted(p.name[: -len(ARTIFACT_SUFFIX)] for p in exp.glob("*" + ARTIFACT_SUFFIX)) if exp.is_dir() else []
    kinds = sorted(stems, key=lambda s: BACKENDS.index(s) if s in BACKENDS else len(BACKENDS))
    if (exp / "rejection.json").is_file():
        kinds.append("rejection")
    if (d / "rowStream.json").is_file() and any((exp / f).is_file() for f in EXPORT_FILES):
        kinds.append("writer")
    return kinds


def enumerate_fixtures(root: Path, only: list[str]):
    """Return (cases, out_of_tier): cases = [(fixture_id, backend, dir)], out_of_tier = [(fixture_id, reason)]."""
    if not root.is_dir():
        raise UsageError(f"fixture tree not found: {root}")
    cases, out = [], []
    for cat in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "schemas"):
        for d in sorted(p for p in cat.iterdir() if p.is_dir()):
            fid = f"{cat.name}/{d.name}"
            kinds = case_kinds(d)
            for s in kinds:
                if s not in BACKENDS and s not in KINDS:
                    raise UsageError(f"{fid}: expected/{s}{ARTIFACT_SUFFIX} names a backend outside {', '.join(BACKENDS)}")
            if only and not any(fnmatch.fnmatchcase(fid, g) or any(fnmatch.fnmatchcase(f"{fid}#{s}", g) for s in kinds)
                                for g in only):
                continue
            out += [(fid, r) for r in _out_of_tier(d, bool(kinds))]
            for s in kinds:
                if not only or any(fnmatch.fnmatchcase(fid, g) or fnmatch.fnmatchcase(f"{fid}#{s}", g) for g in only):
                    cases.append((fid, s, d))
    if not cases:  # spec §6: an empty graded set never passes
        raise UsageError(f"no expected artifact matches --only {' '.join(only)}" if only
                         else f"no expected artifact under {root}")
    return cases, out


def _read_json(path: Path) -> object:
    try:
        return parse_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise UsageError(f"cannot read {path}: {e}") from e


# ---------------------------------------------------------------- driver session (spec §2)

def driver_argv(command: str, posix: bool = POSIX) -> list[str] | str:
    """Spec §9: no shell. POSIX splits like a shell line; Windows parses the string itself (shlex eats backslashes)."""
    return shlex.split(command) if posix else command


class Driver:
    def __init__(self, command: str, timeout: float) -> None:
        try:
            argv = driver_argv(command)
            if not argv:
                raise ValueError("empty command")
            # its own process group, so kill() reaches whatever a launcher driver (dotnet run, npx …) started
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,  # stderr passes through
                                         start_new_session=POSIX,
                                         creationflags=0 if POSIX else subprocess.CREATE_NEW_PROCESS_GROUP)
        except (OSError, ValueError) as e:
            raise UsageError(f"cannot start driver {command!r}: {e}") from e
        self.timeout = timeout
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        self._out: queue.Queue[bytes | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._writer = threading.Thread(target=self._write, daemon=True)
        self._reader.start()
        self._writer.start()

    def _read(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            self._lines.put(raw)
        self._lines.put(None)

    def _write(self) -> None:
        try:
            while (data := self._out.get()) is not None:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            self.proc.stdin.close()
        except OSError:
            pass  # the reader reports the driver's exit

    def send(self, line: str) -> None:
        self._out.put(line.encode("ascii") + b"\n")

    def read(self, deadline: float, what: str) -> object:
        try:
            raw = self._lines.get(timeout=max(deadline - time.monotonic(), 0))
        except queue.Empty:
            raise ProtocolFailure(f"no {what} within {self.timeout:g} s") from None
        if raw is None:
            try:
                status = self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                status = "?"
            raise ProtocolFailure(f"driver stopped before the {what} (exit status {status})")
        try:
            value = parse_json(raw.decode("utf-8"))
        except ValueError as e:
            raise ProtocolFailure(f"stdout line is not JSON ({e}): {raw[:80]!r}") from None
        if not isinstance(value, Obj):
            raise ProtocolFailure(f"stdout line is not a JSON object: {raw[:80]!r}")
        return value

    def hello(self) -> dict:
        v = self.read(time.monotonic() + self.timeout, "hello")
        h = v.map.get("hello")
        if not isinstance(h, Obj):
            raise ProtocolFailure("first line is not a hello")
        impl, spec, backends = h.map.get("impl"), h.map.get("specVersion"), h.map.get("backends")
        if not (isinstance(impl, str) and isinstance(spec, str) and isinstance(backends, list) and backends
                and all(isinstance(b, str) and b in BACKENDS for b in backends)):
            raise ProtocolFailure("hello needs impl, specVersion and a non-empty backends list from "
                                  + ", ".join(BACKENDS))
        caps = h.map.get("capabilities", [])
        if not (isinstance(caps, list) and all(isinstance(c, str) and c in KINDS for c in caps)):
            raise ProtocolFailure("hello capabilities must be a list drawn from " + ", ".join(KINDS))
        return {"impl": impl, "specVersion": spec, "backends": list(dict.fromkeys(backends)),
                "capabilities": list(dict.fromkeys(caps))}

    def ask(self, request: str, rid: str, kind: str = "compile") -> Obj:
        self.send(request)
        v = self.read(time.monotonic() + self.timeout, "response")
        if v.map.get("id") != rid:
            raise ProtocolFailure(f"response id {show(v.map.get('id', MISSING))} where {rid!r} was awaited")
        answer = "bytes" if kind == "writer" else "artifact"
        has_a, has_e = answer in v.map, "error" in v.map
        err = v.map.get("error")
        valid_error = has_e and isinstance(err, Obj) and isinstance(err.map.get("kind"), str) \
            and isinstance(err.map.get("message"), str) \
            and all(isinstance(err.map.get(m, ""), str) for m in ("rejectedAt", "reason"))
        valid_bytes = answer != "bytes" or not has_a or isinstance(v.map["bytes"], str)
        if has_a == has_e or (has_e and not valid_error) or not valid_bytes:
            raise ProtocolFailure(f"response to {rid!r} has neither a lone {answer} nor a valid error")
        return v

    def finish(self) -> None:
        """Close stdin; the driver must exit 0 and say nothing more (spec §2.3, §2.4)."""
        self._out.put(None)
        deadline = time.monotonic() + self.timeout
        try:
            extra = self._lines.get(timeout=max(deadline - time.monotonic(), 0))
            if extra is not None:
                raise ProtocolFailure(f"unexpected line after the last response: {extra[:80]!r}")
            status = self.proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
        except (queue.Empty, subprocess.TimeoutExpired):
            raise ProtocolFailure(f"driver did not exit within {self.timeout:g} s of the end of the session") from None
        if status != 0:
            raise ProtocolFailure(f"driver exited with status {status}")

    def kill(self) -> None:
        """End the driver and every process it started (spec §2.4), then release the pipes nobody is blocked on."""
        if self.proc.returncode is None:  # not reaped yet, so its pid still names the driver's group / tree
            try:
                if POSIX:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                else:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except OSError:
                pass
            if self.proc.poll() is None:
                self.proc.kill()
        self.proc.wait()
        self._out.put(None)  # the writer closes stdin and ends
        for thread, pipe in ((self._writer, self.proc.stdin), (self._reader, self.proc.stdout)):
            thread.join(timeout=1)
            if not thread.is_alive():  # closing a pipe under a thread blocked on it would block us too
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass


# ---------------------------------------------------------------- grading by kind (spec §4)

def byte_text(data: bytes, i: int, side: str) -> str:
    return f"0x{data[i]:02x}" if i < len(data) else f"the end of the {side} bytes"


def grade_rejection(rid: str, expected: object, resp: Obj):
    """spec §4.1: the error's rejectedAt and reason equal the fixture's; an artifact answer means the request was accepted."""
    if "error" not in resp.map:
        return {"id": rid, "note": "accepted a request that must be rejected (the driver answered with an artifact)"}
    e = resp.map["error"].map
    actual = (e.get("rejectedAt", MISSING), e.get("reason", MISSING))
    if MISSING in actual:
        return {"id": rid, "note": f"the error carries no rejectedAt and reason (kind {e['kind']})"}
    want = (expected.map.get("rejectedAt"), expected.map.get("reason"))
    if actual != want:
        return {"id": rid, "path": "rejectedAt/reason", "expected": f"{want[0]}/{want[1]}",
                "actual": f"{actual[0]}/{actual[1]}"}
    return None


def grade_writer(rid: str, expected: bytes, resp: Obj):
    """spec §4.2: the decoded bytes equal the expected file byte for byte."""
    try:
        actual = base64.b64decode(resp.map["bytes"], validate=True)
    except ValueError:  # binascii.Error is a ValueError
        raise ProtocolFailure(f"response to {rid!r}: bytes is not valid base64") from None
    if actual == expected:
        return None
    i = next((n for n, (x, y) in enumerate(zip(expected, actual)) if x != y), min(len(expected), len(actual)))
    return {"id": rid, "note": f"first differing byte at offset {i}: expected {byte_text(expected, i, 'expected')}, "
                               f"actual {byte_text(actual, i, 'actual')}"}


def grade(rid: str, kind: str, expected: object, resp: Obj):
    """None when the case passes, else the failure record the report prints (spec §4, §4.1, §4.2, §6)."""
    if kind == "rejection":
        return grade_rejection(rid, expected, resp)
    if "error" in resp.map:
        e = resp.map["error"].map
        return {"id": rid, "error": f"{e['kind']}: {e['message']}"}
    if kind == "writer":
        return grade_writer(rid, expected, resp)
    diff = compare(kind, expected, resp.map["artifact"])
    return diff and {"id": rid, "path": diff[0], "expected": diff[1], "actual": diff[2]}


# ---------------------------------------------------------------- run and report

def run(args: argparse.Namespace) -> tuple[int, dict]:
    root = Path(args.fixtures)
    cases, out = enumerate_fixtures(root, args.only or [])
    report: dict = {"driver": args.driver, "status": "pass", "failures": [], "unanswered": [], "protocolFailure": None,
                    "outOfTier": [{"id": i, "reason": r} for i, r in out], "totals": {}, "hello": None}
    jobs = []  # read every file first: an unreadable fixture is a usage error, never a half-run session
    for fid, kind, d in cases:
        rid = f"{fid}#{kind}"
        members = [("id", rid)]
        if kind == "rejection":
            members += [("kind", kind)]
        elif kind == "writer":
            members += [("kind", kind)]
        else:
            members += [("backend", kind)]
        members += [("schema", _read_json(d / "schema.json")), ("agGridRequest", _read_json(d / "agGridRequest.json"))]
        if kind == "writer":
            members.append(("rowStream", _read_json(d / "rowStream.json")))
            if (d / "writerConfig.json").is_file():
                members.append(("writerConfig", _read_json(d / "writerConfig.json")))
            files = [d / "expected" / f for f in EXPORT_FILES if (d / "expected" / f).is_file()]
            if len(files) != 1:
                raise UsageError(f"{fid}: expected/ must hold exactly one of {' and '.join(EXPORT_FILES)}")
            expected = files[0].read_bytes()
        elif kind == "rejection":
            expected = _read_json(d / "expected" / "rejection.json")
        else:
            expected = _read_json(d / "expected" / f"{kind}{ARTIFACT_SUFFIX}")
        jobs.append((rid, kind, dumps(Obj(members)), expected))
    driver = Driver(args.driver, args.timeout)
    graded: list = []
    answered = 0
    try:
        hello = report["hello"] = driver.hello()
        declared = set(hello["backends"]) | set(hello["capabilities"])
        totals = {b: {"passed": 0, "failed": 0, "notGraded": 0} for b in BACKENDS + KINDS}
        report["totals"] = totals
        graded = [j for j in jobs if j[1] in declared]
        for _, b, _r, _e in jobs:
            if b not in declared:
                totals[b]["notGraded"] += 1
        for rid, kind, request, expected in graded:
            resp = driver.ask(request, rid, kind)
            answered += 1
            failure = grade(rid, kind, expected, resp)
            if failure:
                totals[kind]["failed"] += 1
                report["failures"].append(failure)
            else:
                totals[kind]["passed"] += 1
        driver.finish()
    except ProtocolFailure as e:
        report["status"] = "protocol-failure"
        report["protocolFailure"] = str(e)
        report["unanswered"] = [j[0] for j in graded[answered:]]
        return 2, report
    finally:
        driver.kill()
    if not graded:  # spec §6: no selected case is in a backend the driver declared
        report["status"] = "nothing-graded"
        return 2, report
    if report["failures"]:
        report["status"] = "fail"
        return 1, report
    return 0, report


def render(report: dict) -> str:
    lines: list[str] = []
    h = report["hello"]
    if h:
        caps = f" capabilities={','.join(h['capabilities'])}" if h["capabilities"] else ""
        lines.append(f"driver: impl={h['impl']} specVersion={h['specVersion']} backends={','.join(h['backends'])}{caps}")
    for f in report["failures"]:
        lines.append(f"FAIL {f['id']}")
        if "note" in f:
            lines.append(f"  {f['note']}")
        elif "error" in f:
            lines.append(f"  driver answered error {f['error']}")
        else:
            lines += [f"  at       {f['path']}", f"  expected {f['expected']}", f"  actual   {f['actual']}"]
    if report["protocolFailure"]:
        lines.append(f"PROTOCOL FAILURE: {report['protocolFailure']}")
        un = report["unanswered"]
        if un:
            lines.append(f"unanswered requests ({len(un)}):")
            lines += [f"  {i}" for i in un[:MAX_LISTED]]
            if len(un) > MAX_LISTED:
                lines.append(f"  ... and {len(un) - MAX_LISTED} more")
    if report["totals"]:
        lines.append(f"{'backend':<10}{'passed':>8}{'failed':>8}{'not graded':>12}")
        for b, t in report["totals"].items():
            if t["passed"] or t["failed"] or t["notGraded"]:
                lines.append(f"{b:<10}{t['passed']:>8}{t['failed']:>8}{t['notGraded']:>12}")
    if report["outOfTier"]:
        lines.append(f"out of tier ({len(report['outOfTier'])}):")
        lines += [f"  {o['id']}  {o['reason']}" for o in report["outOfTier"]]
    lines.append({"pass": "RESULT: PASS", "fail": "RESULT: FAIL", "protocol-failure": "RESULT: PROTOCOL FAILURE",
                  "nothing-graded": "RESULT: NOTHING GRADED (no selected case is in a declared backend)"}
                 [report["status"]])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Grade an implementation's driver against the conformance fixtures.")
    ap.add_argument("--driver", required=True,
                    help='command that starts the driver, e.g. "dotnet driver.dll" (spec §9)')
    ap.add_argument("--fixtures", default=str(Path(__file__).resolve().parent.parent / "spec" / "fixtures"))
    ap.add_argument("--json", metavar="FILE", help="also write the report as JSON")
    ap.add_argument("--only", action="append", metavar="GLOB",
                    help="grade only fixtures matching <category>/<slug> or <category>/<slug>#<backend> (repeatable)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per hello/response (default 30)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        code, report = run(args)
    except UsageError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2
    print(render(report))
    if args.json:
        try:
            Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as e:
            print(f"usage error: cannot write {args.json}: {e}", file=sys.stderr)
            return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
