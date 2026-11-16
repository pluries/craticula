#!/usr/bin/env python3
"""Generates the performance page of the docs site from the raw results of a run (story #3324, task #3849, spec FR-20).

Usage: python3 scripts/perf_page.py <results dir> [--repeat <repeat run dir>] [--page site/pages/performance.md] [--site-json site/site.json]
Reads <results dir>/compile/results/*-report-full.json (the BenchmarkDotNet output), compile/manifest-compile.json and every
manifest-<engine>-<dataset>.json; writes the page, then registers it once in the site config. Every number in a table is a link to the
raw file it came from, so none is typed by hand. Exit 0 = written, 2 = no results or an unreadable result file (nothing is written).
Tests: scripts/test_perf_page.py.
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_NS = 50_000
ENGINE_LABELS = {"postgres": "PostgreSQL", "ef": "PostgreSQL through EF Core", "mongo": "MongoDB"}
SITE_ENTRY = {
    "slug": "performance",
    "title": "Performance",
    "source": "site/pages/performance.md",
    "group": "Reference",
    "description": "Measured compile time and load results, each number linked to its raw file.",
}


class ResultsError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ResultsError(f"{path}: cannot read ({error})") from error


def link(text, target, page_dir):
    return f"[{text}]({Path(os.path.relpath(target, page_dir)).as_posix()})"


def kib(value):
    return f"{value / 1024:.1f} KiB" if value >= 1024 else f"{value:.0f} B"


def compile_rows(report, report_path, page_dir):
    rows = []
    for benchmark in report["Benchmarks"]:
        params = {}
        for pair in benchmark["Parameters"].split("&"):
            key, _, value = pair.partition("=")
            params[key] = value
        mean = benchmark["Statistics"]["Mean"]
        allocated = benchmark["Memory"]["BytesAllocatedPerOperation"]
        rows.append((params["Backend"], params["Shape"], mean, allocated))
    rows.sort(key=lambda r: (r[1], r[0]))
    lines = ["| Backend | Request shape | Mean time | Allocated per request | PERF-1 |", "|---|---|---|---|---|"]
    for backend, shape, mean, allocated in rows:
        verdict = "meets PERF-1" if mean < TARGET_NS else "does not meet PERF-1"
        mean_cell = link(f"{mean / 1000:.1f} µs", report_path, page_dir)
        allocated_cell = link(kib(allocated), report_path, page_dir)
        lines.append(f"| {backend} | {shape} | {mean_cell} | {allocated_cell} | {verdict} |")
    over = sum(1 for r in rows if r[2] >= TARGET_NS)
    summary = ("Every measured compile time is under the target." if over == 0
               else f"{over} of {len(rows)} measured compile times are not under the target.")
    return lines, summary


def load_compare():
    spec = importlib.util.spec_from_file_location("perf_compare", ROOT / "perf" / "compare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def show(name, value):
    if name.endswith("mean"):
        return f"{value / 1000:.1f} µs"
    if name.endswith("requests per second"):
        return f"{value:.1f} /s"
    return f"{value:.1f} ms"


def repeatability(results, repeat, page_dir, limit=10.0):
    compare = load_compare()
    total, outside = compare.compare(results, repeat, limit)
    lines = ["## Repeatability", "",
             f"Every measurement was taken twice on the same machine, in two runs one after the other. The target is that the second "
             f"run lands within {limit:g}% of the first."]
    if not outside:
        lines += ["", f"All {total} measurements of the repeat run are within {limit:g}% of this run."]
        return lines + [""]
    lines += ["", f"{total - len(outside)} of {total} measurements of the repeat run are within {limit:g}% of this run. "
              f"These {len(outside)} are not, so read them with that spread in mind:", ""]
    for item in outside:
        first = link(show(item["name"], item["first"]), item["first_path"], page_dir)
        second = link(show(item["name"], item["second"]), item["second_path"], page_dir)
        lines.append(f"- {item['name']}: {first} then {second}, {item['change']:.1f}% apart")
    return lines + [""]


def render(results, page_dir, repeat=None):
    results, page_dir = Path(results), Path(page_dir)
    report_files = sorted((results / "compile" / "results").glob("*-report-full.json"))
    manifest_files = sorted(results.glob("manifest-*.json"))
    if len(report_files) != 1 or not manifest_files:
        raise ResultsError(f"{results}: expected one compile report and at least one load manifest")
    compile_manifest = read_json(results / "compile" / "manifest-compile.json")
    report = read_json(report_files[0])
    manifests = [(path, read_json(path)) for path in manifest_files]
    machines = sorted({m["machine"] for _, m in manifests} | {compile_manifest["machine"]})

    table, summary = compile_rows(report, report_files[0], page_dir)
    out = [
        "# Performance",
        "",
        "These are measurements of Craticula on one machine, not promises. Nothing here changes how Craticula behaves: the only hard "
        "limit on the demos is the two second query cut-off. Every number links to the raw result it came from, and each run lists "
        "the command that repeats it.",
        "",
        f"Measured on {', '.join(machines)}.",
        "",
        "## Compile time",
        "",
        "Compiling a request means parsing it, checking it against the schema and building the query. Nothing is executed. The "
        "specification sets a target of under 50 µs per typical request (PERF-1). The target is benchmarked, not enforced, and "
        "the results below say plainly whether it is met. " + summary,
        "",
        *table,
        "",
        "## Load on the demo API",
        "",
        "A load test posts a mix of grid requests to the demo API on a local stack, without the public rate limit. The table shows "
        "latency percentiles and requests per second for each engine and data size.",
        "",
        "| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |",
        "|---|---|---|---|---|---|---|",
    ]
    for path, manifest in sorted(manifests, key=lambda item: (item[1]["dataset"], item[1]["engine"])):
        s = manifest["summary"]
        engine = ENGINE_LABELS.get(manifest["engine"], manifest["engine"])
        cells = [
            link(f"{s['p50_ms']:.1f} ms", path, page_dir),
            link(f"{s['p95_ms']:.1f} ms", path, page_dir),
            link(f"{s['p99_ms']:.1f} ms", path, page_dir),
            link(f"{s['requests_per_second']:.1f} /s", path, page_dir),
            link(str(s["errors"]), path, page_dir),
        ]
        out.append(f"| {engine} | {manifest['dataset']} | " + " | ".join(cells) + " |")
    out += [""]
    if repeat is not None:
        out += repeatability(results, Path(repeat), page_dir)
    out += ["## How each result was produced", "", "### Compile benchmark", "",
            f"- Machine: {compile_manifest['machine']}",
            f"- Tool: {compile_manifest['benchmark']} on .NET {compile_manifest['dotnet']}",
            f"- Date: {compile_manifest['date']}, commit {compile_manifest['commit']}",
            f"- Raw result: {link('BenchmarkDotNet report', report_files[0], page_dir)}",
            "", "To repeat it:", "", "```", compile_manifest["command"], "```", ""]
    for path, manifest in sorted(manifests, key=lambda item: (item[1]["dataset"], item[1]["engine"])):
        engine = ENGINE_LABELS.get(manifest["engine"], manifest["engine"])
        raw = path.with_name(path.name.replace("manifest-", "load-").replace(".json", ".jsonl"))
        load, oversized = manifest["load"], manifest["oversized"]
        out += [f"### {engine}, {manifest['dataset']} rows", "",
                f"- Machine: {manifest['machine']} ({manifest.get('platform', 'platform not recorded')})",
                f"- Engine: {manifest['engine_version']}",
                f"- Load: {load['concurrency']} threads for {load['duration_seconds']:g} seconds",
                f"- Date: {manifest['date']}, commit {manifest['commit']}",
                f"- Oversized request: answered {oversized['status']} with {oversized['kind']}"
                f"{'' if oversized['handled'] else ' (not the expected refusal)'}",
                f"- Raw results: {link('manifest', path, page_dir)}, {link('every request', raw, page_dir)}",
                "", "To repeat it:", "", "```", manifest["command"], "```", ""]
    return "\n".join(out).rstrip() + "\n"


def register(site_json):
    data = json.loads(site_json.read_text(encoding="utf-8"))
    if any(page.get("slug") == SITE_ENTRY["slug"] for page in data["pages"]):
        return
    data["pages"].append(dict(SITE_ENTRY))
    site_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results")
    parser.add_argument("--page", default=str(ROOT / "site" / "pages" / "performance.md"))
    parser.add_argument("--site-json", default=str(ROOT / "site" / "site.json"))
    parser.add_argument("--repeat")
    args = parser.parse_args(argv)
    page = Path(args.page)
    try:
        text = render(Path(args.results), page.parent, Path(args.repeat) if args.repeat else None)
    except (ResultsError, KeyError, TypeError) as error:
        print(f"perf_page.py: {error}", file=sys.stderr)
        return 2
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")
    register(Path(args.site_json))
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
