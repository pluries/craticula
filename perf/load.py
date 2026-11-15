#!/usr/bin/env python3
"""Load test of a Craticula demo API (story #3324, task #3847, spec FR-18 and FR-19).

Posts request bodies from examples/demo/smoke to <base-url>/api/<engine>/rows from several threads, prints p50, p95, p99 and
requests per second, writes the raw timings and a manifest, one pair of files per engine and dataset. Run it against a local stack without DEMO_PUBLIC: the public
demos refuse more than 60 requests a minute per address. Exit 0 = finished and the oversized request was refused as
resource-limit-exceeded, 1 = finished but it was not, 2 = bad arguments. Tests: scripts/test_perf_load.py.
"""
import argparse
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "examples" / "demo" / "smoke"
ENGINES = ("postgres", "mongo")
DEFAULT_SHAPES = ("number-gt.json", "text-contains-sort.json", "group-by-country.json", "set-filter-status.json")
OVERSIZED_SHAPE = "bad-oversized-page.json"
OVERSIZED_KIND = "resource-limit-exceeded"
REQUEST_TIMEOUT_SECONDS = 30


def percentile(values, p):
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def post(url, body):
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        payload = error.read()
        status = error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, b"", (time.perf_counter() - started) * 1000
    return status, payload, (time.perf_counter() - started) * 1000


def check_oversized(url):
    status, payload, _ = post(url, (SMOKE / OVERSIZED_SHAPE).read_bytes())
    try:
        kind = json.loads(payload)["error"]["kind"]
    except (ValueError, KeyError, TypeError):
        kind = None
    return {"handled": status == 400 and kind == OVERSIZED_KIND, "status": status, "kind": kind}


def worker(url, shapes, deadline, results, lock):
    index = 0
    local = []
    while time.perf_counter() < deadline:
        name, body = shapes[index % len(shapes)]
        index += 1
        status, _, elapsed = post(url, body)
        local.append({"shape": name, "status": status, "ms": round(elapsed, 3)})
    with lock:
        results.extend(local)


def run_load(url, shapes, concurrency, duration):
    results, lock = [], threading.Lock()
    started = time.perf_counter()
    deadline = started + duration
    threads = [threading.Thread(target=worker, args=(url, shapes, deadline, results, lock)) for _ in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results, time.perf_counter() - started


def summarize(results, elapsed):
    good = [r["ms"] for r in results if r["status"] == 200]
    summary = {"count": len(results), "errors": len(results) - len(good), "requests_per_second": round(len(results) / elapsed, 2)}
    for p in (50, 95, 99):
        summary[f"p{p}_ms"] = round(percentile(good, p), 3) if good else None
    return summary


def current_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--engine-version", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shapes", default=",".join(DEFAULT_SHAPES))
    parser.add_argument("--commit")
    parser.add_argument("--repeat-command")
    return parser.parse_args(argv)


def refuse(message):
    print(f"load.py: {message}", file=sys.stderr)
    return 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse(argv)
    except SystemExit as exit_:
        return 2 if exit_.code else 0
    if args.engine not in ENGINES:
        return refuse(f"engine must be one of {', '.join(ENGINES)}")
    if args.concurrency < 1:
        return refuse("concurrency must be at least 1")
    if args.duration <= 0:
        return refuse("duration must be above 0 seconds")
    shapes = []
    for name in (n.strip() for n in args.shapes.split(",") if n.strip()):
        path = SMOKE / name
        if not path.is_file():
            return refuse(f"shape file {name} not found in examples/demo/smoke")
        shapes.append((name, path.read_bytes()))
    if not shapes:
        return refuse("no shape files given")

    url = f"{args.base_url.rstrip('/')}/api/{args.engine}/rows"
    oversized = check_oversized(url)
    results, elapsed = run_load(url, shapes, args.concurrency, args.duration)
    summary = summarize(results, elapsed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / f"load-{args.engine}-{args.dataset}.jsonl"
    raw.write_text("".join(json.dumps(r) + "\n" for r in results), encoding="utf-8")
    command = shlex.join(["python3", "perf/load.py", "--engine", args.engine, "--base-url", args.base_url,
                          "--concurrency", str(args.concurrency), "--duration", f"{args.duration:g}", "--dataset", args.dataset,
                          "--machine", args.machine, "--engine-version", args.engine_version, "--out", args.out,
                          "--shapes", ",".join(name for name, _ in shapes)])
    manifest = {
        "machine": args.machine,
        "platform": f"{platform.system()} {platform.release()}, {os.cpu_count()} logical CPUs, Python {platform.python_version()}",
        "dataset": args.dataset,
        "engine": args.engine,
        "engine_version": args.engine_version,
        "load": {"concurrency": args.concurrency, "duration_seconds": args.duration},
        "shapes": [name for name, _ in shapes],
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "commit": args.commit or current_commit(),
        "command": args.repeat_command or command,
        "summary": summary,
        "oversized": oversized,
    }
    (out / f"manifest-{args.engine}-{args.dataset}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"{args.engine} {args.dataset}: {summary['count']} requests, {summary['errors']} errors, "
          f"p50 {summary['p50_ms']} ms, p95 {summary['p95_ms']} ms, p99 {summary['p99_ms']} ms, {summary['requests_per_second']} requests/s")
    print(f"oversized request: {'handled' if oversized['handled'] else 'NOT handled'} (status {oversized['status']}, kind {oversized['kind']})")
    return 0 if oversized["handled"] else 1


if __name__ == "__main__":
    sys.exit(main())
