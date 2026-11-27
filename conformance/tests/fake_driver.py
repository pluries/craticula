#!/usr/bin/env python3
"""A conformance driver for the runner's own tests. It speaks the protocol of spec/conformance-runner.md but compiles
nothing: it answers from the expected artifacts (--fixtures) or from a table of canned answers (--answers), and --mode
makes it misbehave in one specific way. Independent of run.py on purpose: it is the proof that a driver in another
program needs nothing from the runner (AC-4)."""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

ALL = "postgres,mssql,mysql,oracle,sqlite,mongo,search"


def minify(text):
    """Drop JSON whitespace outside strings so a pretty-printed file fits on one line, literals untouched."""
    out, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch not in " \t\r\n":
            out.append(ch)
    return "".join(out)


def emit(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


ERROR_MEMBER = '"error":'
BYTES_MEMBER = '"bytes":'


def fixture_dir(args, rid):
    category, rest = rid.split("/", 1)
    return Path(args.fixtures) / category / rest.split("#", 1)[0]


def rejection_payload(args, rid, canned):
    """The rejection the fixture expects, as an error answer; --mode bends it in one specific way."""
    if rid in canned:
        return ERROR_MEMBER + json.dumps(canned[rid]["error"])
    expected = json.loads((fixture_dir(args, rid) / "expected" / "rejection.json").read_text(encoding="utf-8-sig"))
    error = {"kind": "FakeRejection", "message": "fake", "rejectedAt": expected["rejectedAt"], "reason": expected["reason"]}
    if args.mode == "wrong-reason":
        error["reason"] = "unknown-field" if error["reason"] != "unknown-field" else "malformed-request"
    if args.mode == "wrong-stage":
        error["rejectedAt"] = "allowlist" if error["rejectedAt"] != "allowlist" else "resourceLimits"
    if args.mode == "no-pair":
        del error["rejectedAt"], error["reason"]
    if args.mode == "accepts":
        return '"artifact":{}'
    return ERROR_MEMBER + json.dumps(error)


def writer_payload(args, rid, canned, req):
    """The bytes the fixture expects, base64; --mode bends them (a flipped byte, a dropped BOM, LF for CRLF)."""
    if rid in canned:
        return BYTES_MEMBER + json.dumps(canned[rid]["bytes"])
    if args.mode == "echo-config":  # the config the runner sent, so a test can see it arrive unchanged
        data = json.dumps(req.get("writerConfig"), separators=(",", ":")).encode()
        return BYTES_MEMBER + json.dumps(base64.b64encode(data).decode("ascii"))
    folder = fixture_dir(args, rid) / "expected"
    path = next(p for p in (folder / "export.csv", folder / "export.tsv") if p.exists())
    data = path.read_bytes()
    if args.mode == "flip-byte":
        data = data[:-3] + bytes([data[-3] ^ 1]) + data[-2:]
    if args.mode == "drop-bom" and data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if args.mode == "lf-endings":
        data = data.replace(b"\r\n", b"\n")
    if args.mode == "writer-error":
        return '"error":{"kind":"CsvWriterException","message":"refused"}'
    return BYTES_MEMBER + json.dumps(base64.b64encode(data).decode("ascii"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures")
    ap.add_argument("--answers", help='JSON file: {id: {"artifact": "<raw JSON text>"} | {"error": {kind, message}}}')
    ap.add_argument("--backends", default=ALL)
    ap.add_argument("--caps", default="", help="capabilities declared in the hello: rejection, writer (comma separated)")
    ap.add_argument("--mode", default="ok")
    ap.add_argument("--after", type=int, default=2, help="requests answered before a crash / hang / early exit")
    ap.add_argument("--pid-file", help="write this process's pid here, so a test can check nothing outlives the run")
    args = ap.parse_args()
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    canned = json.loads(Path(args.answers).read_text()) if args.answers else {}
    backends = json.dumps(args.backends.split(","))
    caps = json.dumps([c for c in args.caps.split(",") if c])

    if args.mode == "hang-hello":
        time.sleep(600)
    if args.mode == "exit-silently":
        sys.exit(0)
    if args.mode == "bad-hello":
        emit('{"notHello":1}')
    elif args.mode == "no-hello":
        pass
    elif args.mode == "hello-garbage":
        emit("this is not json")
    else:
        emit('{"hello":{"impl":"fake","specVersion":"0.0.0","backends":%s,"capabilities":%s}}' % (backends, caps))

    n, previous = 0, None
    for line in sys.stdin:
        req = json.loads(line)
        rid, backend, kind = req["id"], req.get("backend"), req.get("kind", "compile")
        n += 1
        if args.mode == "crash" and n > args.after:
            sys.stderr.write("fake driver: simulated crash\n")
            sys.exit(1)
        if args.mode == "early-exit" and n > args.after:
            sys.exit(0)
        if args.mode == "hang" and n > args.after:
            time.sleep(600)
        if args.mode == "unsolicited" and n == 2:
            emit('{"id":"nobody#postgres","artifact":{}}')
        if args.mode == "non-json" and n == 2:
            emit("not json at all")
        if args.mode == "not-object" and n == 2:
            emit("[1,2]")

        if kind == "writer":
            payload = writer_payload(args, rid, canned, req)
        elif kind == "rejection":
            payload = rejection_payload(args, rid, canned)
        elif rid in canned:
            body = canned[rid]
            payload = '"artifact":' + body["artifact"] if "artifact" in body else ERROR_MEMBER + json.dumps(body["error"])
        else:
            category, rest = rid.split("/", 1)
            slug = rest.split("#", 1)[0]
            path = Path(args.fixtures) / category / slug / "expected" / (backend + ".artifact.json")
            payload = '"artifact":' + minify(path.read_text(encoding="utf-8-sig"))

        answer_id = rid
        if args.mode == "repeat-id" and n == 2:
            answer_id = previous  # the id already answered: repeated, and out of order
        if args.mode == "unknown-id" and n == 2:
            answer_id = "nope"
        if args.mode == "neither" and n == 2:
            payload = '"note":1'
        if args.mode == "both" and n == 2:
            payload = payload + ',"error":{"kind":"x","message":"y"}'
        emit('{"id":%s,%s}' % (json.dumps(answer_id), payload))
        previous = rid

    if args.mode == "trailing":
        emit('{"id":"late#postgres","artifact":{}}')
    if args.mode == "exit-nonzero":
        sys.exit(3)
    if args.mode == "no-exit":
        time.sleep(600)


if __name__ == "__main__":
    main()
