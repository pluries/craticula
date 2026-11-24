#!/usr/bin/env python3
"""Generates the performance page of the docs site from the raw results of a run (story #3324, task #3849, spec FR-20).

Usage: python3 scripts/perf_page.py <results dir> [--repeat <repeat run dir>] [--single <one-client run dir>] [--page site/pages/performance.md] [--site-json site/site.json] [--readme README.md]
Reads <results dir>/compile/results/*-report-full.json (the BenchmarkDotNet output), compile/manifest-compile.json and every
manifest-<engine>-<dataset>.json; writes the page, then registers it once in the site config. Every number in a table is a link to the
raw file it came from, so none is typed by hand. With --repeat it also writes the results block between the one pair of markers of the
README (spec 007), from the same two runs. Exit 0 = written, 2 = no results, an unreadable result file or README, a bad --repeat run, a run
or repeat without a measurement on both schema paths, or a README without exactly one marker pair (neither the page nor the README is written).
Tests: scripts/test_perf_page.py.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
TARGET_NS = 50_000
NOT_MEASURED = "not measured"
ENGINE_LABELS = {"postgres": "PostgreSQL", "ef": "PostgreSQL through EF Core", "mongo": "MongoDB"}
BLOCK_BEGIN = "<!-- performance block: begin, written by scripts/perf_page.py; the site leaves it out -->"
BLOCK_END = "<!-- performance block: end -->"
PERFORMANCE_URL = "https://craticula.pluries.dev/performance.html"
PATH_LABELS = (("prepared-schema", "Schema prepared once, then each request compiled against it"),
               ("full-compile", "Schema parsed from JSON on every call"))
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


def verdict_for(mean):
    return "meets PERF-1" if mean < TARGET_NS else "does not meet PERF-1"


class PathFigures(NamedTuple):
    lowest: tuple[float, str, str]
    highest: tuple[float, str, str]
    over: int
    total: int


def measurements(report):
    """(shape, backend, path) -> (mean ns, bytes allocated per operation) for every benchmark of a BenchmarkDotNet report."""
    measured = {}
    for benchmark in report["Benchmarks"]:
        params = {}
        for pair in benchmark["Parameters"].split("&"):
            key, _, value = pair.partition("=")
            params[key] = value
        path = params.get("SchemaPath", "full-compile")
        measured[(params["Shape"], params["Backend"], path)] = (benchmark["Statistics"]["Mean"], benchmark["Memory"]["BytesAllocatedPerOperation"])
    return measured


def path_figures(measured, path):
    """The lowest and highest per-shape mean of one path, and how many of its shapes are at or above the target; None when the run has none."""
    entries = sorted(((backend, shape), mean) for (shape, backend, key), (mean, _) in measured.items() if key == path)
    if not entries:
        return None
    (low_key, low), (high_key, high) = min(entries, key=lambda item: item[1]), max(entries, key=lambda item: item[1])
    return PathFigures((low, *low_key), (high, *high_key), sum(1 for _, mean in entries if mean >= TARGET_NS), len(entries))


def run_report(results):
    reports = sorted((Path(results) / "compile" / "results").glob("*-report-full.json"))
    if len(reports) != 1:
        raise ResultsError(f"{results}: expected one compile report")
    return reports[0]


def figure_link(mean, report, readme_dir):
    return link(f"{mean / 1000:.1f} µs", report, readme_dir)


def count_text(figures, report, readme_dir):
    return f"{link(str(figures.over), report, readme_dir)} of {link(str(figures.total), report, readme_dir)} at or above the {TARGET_NS // 1000} µs target"


def path_row(label, figures, repeat_figures, reports, readme_dir):
    report, repeat_report = reports
    low, high = figures.lowest, figures.highest
    run_cell = (f"{figure_link(low[0], report, readme_dir)} ({low[1]}, {low[2]}) to {figure_link(high[0], report, readme_dir)} ({high[1]}, {high[2]}); "
                f"{count_text(figures, report, readme_dir)}")
    repeat_cell = f"{figure_link(repeat_figures.lowest[0], repeat_report, readme_dir)} to {figure_link(repeat_figures.highest[0], repeat_report, readme_dir)}"
    if (repeat_figures.over, repeat_figures.total) != (figures.over, figures.total):
        repeat_cell += f"; {count_text(repeat_figures, repeat_report, readme_dir)}"
    return f"| {label} | {run_cell} | {repeat_cell} |"


def check_complete(measured, folders):
    """FR-010: each run measured both paths, and the two runs measured the same set."""
    for run, folder in zip(measured, folders):
        for path, _ in PATH_LABELS:
            if path_figures(run, path) is None:
                raise ResultsError(f"{folder}: no measurement on the {path} path")
    first, second = (set(run) for run in measured)
    if first != second:
        shape, backend, path = min(first ^ second)
        missing = folders[1] if (shape, backend, path) in first else folders[0]
        raise ResultsError(f"{folders[0]} and {folders[1]} do not hold the same measurements: {backend} {shape} on the {path} path is missing from {missing}")


def readme_block(results, repeat, readme_dir):
    """The text of the README's performance region, without markers and without a trailing newline (spec 007, plan Design (a))."""
    results, repeat, readme_dir = Path(results), Path(repeat), Path(readme_dir)
    reports = (run_report(results), run_report(repeat))
    manifest = read_json(results / "compile" / "manifest-compile.json")
    measured = [measurements(read_json(report)) for report in reports]
    check_complete(measured, (results, repeat))
    rows = []
    for path, label in PATH_LABELS:
        figures = [path_figures(run, path) for run in measured]
        rows.append(path_row(label, figures[0], figures[1], reports, readme_dir))
    return "\n".join([
        "## Measured compile time",
        "",
        "The time Craticula takes to compile one grid request into a query, without running it. The figures are taken from the per-shape means "
        "of the report and are measurements on one machine, not promises.",
        "",
        "| What is measured | This run: lowest to highest | Repeat run: lowest to highest |",
        "|---|---|---|",
        *rows,
        "",
        f"Measured on {manifest['machine']} on {manifest['date']}, run folder `{results.name}`. Every figure links to the BenchmarkDotNet report "
        f"it was read from. The full tables, the load results and the method are on the [performance page]({PERFORMANCE_URL}).",
    ])


def replace_region(readme_text, block):
    """The README with the lines between its one begin marker and its one end marker replaced by the lines of `block`."""
    lines = readme_text.splitlines(keepends=True)
    begins = [number for number, line in enumerate(lines, 1) if line.strip() == BLOCK_BEGIN]
    ends = [number for number, line in enumerate(lines, 1) if line.strip() == BLOCK_END]
    problems = []
    if not begins and not ends:
        problems.append(f"README: no begin marker `{BLOCK_BEGIN}`")
    elif not begins:
        problems.append(f"README: line {ends[0]}: the end marker `{BLOCK_END}` has no begin marker `{BLOCK_BEGIN}`")
    elif not ends:
        problems.append(f"README: line {begins[0]}: the begin marker `{BLOCK_BEGIN}` has no end marker `{BLOCK_END}`")
    if len(begins) > 1:
        problems.append(f"README: line {begins[1]}: a second begin marker `{BLOCK_BEGIN}`")
    if len(ends) > 1:
        problems.append(f"README: line {ends[1]}: a second end marker `{BLOCK_END}`")
    if begins and ends and ends[0] < begins[0]:
        problems.append(f"README: line {ends[0]}: the end marker `{BLOCK_END}` comes before the begin marker")
    if problems:
        raise ResultsError("; ".join(problems))
    inner = [f"{line}\n" for line in block.split("\n")] if block else []
    return "".join(lines[:begins[0]] + inner + lines[ends[0] - 1:])


def write_whole(path, text):
    """Replaces the file whole: the text goes to a temporary file beside it, then over it, keeping the old file's mode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def compile_rows(report, report_path, page_dir):
    """One row per backend and shape: the full compile (schema parsed from JSON on every call) and, when the run has it, the prepared-schema path."""
    measured = measurements(report)
    keys = sorted({(shape, backend) for shape, backend, _ in measured})
    lines = ["| Backend | Request shape | Full compile | Allocated | PERF-1 | Prepared schema | Allocated | PERF-1 |", "|---|---|---|---|---|---|---|---|"]
    for shape, backend in keys:
        cells = [backend, shape]
        for path in ("full-compile", "prepared-schema"):
            if (shape, backend, path) in measured:
                mean, allocated = measured[(shape, backend, path)]
                cells += [link(f"{mean / 1000:.1f} µs", report_path, page_dir), link(kib(allocated), report_path, page_dir), verdict_for(mean)]
            else:
                cells += [NOT_MEASURED] * 3
        lines.append("| " + " | ".join(cells) + " |")
    return lines, compile_summary(measured)


def compile_summary(measured):
    """One sentence per path: whether every measured compile time is under the PERF-1 target."""
    parts = []
    for path, label in (("full-compile", "full compile"), ("prepared-schema", "prepared schema")):
        means = [value[0] for key, value in measured.items() if key[2] == path]
        if means:
            over = sum(1 for mean in means if mean >= TARGET_NS)
            parts.append(f"On the {label} path, " + ("every measured compile time is under the target." if over == 0
                         else f"{over} of {len(means)} measured compile times are not under the target."))
    return " ".join(parts)


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


def difference_text(compare, item, page_dir):
    first = link(show(item.name, item.first), item.first_path, page_dir)
    second = link(show(item.name, item.second), item.second_path, page_dir)
    return f"{item.name}: {first} then {second}, {compare.describe(item.change)}"


def repeatability_lines(compare, total, outside, largest, page_dir, limit):
    lines = ["## Repeatability", "",
             "Every measurement was taken twice on the same machine, in two runs one after the other.", ""]
    if outside:
        lines.append(f"{len(outside)} of {total} measurements of the repeat run differ by more than {limit:g}% from this run.")
    else:
        lines.append(f"None of the {total} measurements of the repeat run differs by more than {limit:g}% from this run.")
    lines += ["", "Largest difference: " + difference_text(compare, largest, page_dir) + "."]
    if outside:
        lines += ["", f"Differences above {limit:g}%, largest first:", ""]
        lines += ["- " + difference_text(compare, item, page_dir) for item in outside]
    return lines + [""]


def repeatability(results, repeat, page_dir, limit=10.0):
    compare = load_compare()
    try:
        total, outside, largest = compare.compare(results, repeat, limit)
    except compare.RunError as error:
        raise ResultsError(str(error)) from error
    return repeatability_lines(compare, total, outside, largest, page_dir, limit)


def machine_state(manifest):
    """One line about what the machine itself was doing during the run, when the manifest recorded it."""
    environment = manifest.get("environment")
    if not environment:
        return []
    parts = []
    if environment.get("cpu_steal_percent") is not None:
        parts.append(f"CPU steal {environment['cpu_steal_percent']:g}%")
    if environment.get("load_average_1m") is not None:
        parts.append(f"load average {environment['load_average_1m']:g}")
    parts += [f"{kind} {degrees:g} °C" for kind, degrees in sorted((environment.get("thermal_c") or {}).items())]
    return [f"- Machine during the run: {', '.join(parts)}"] if parts else []


def load_rows(manifests, page_dir):
    rows = []
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
        rows.append(f"| {engine} | {manifest['dataset']} | " + " | ".join(cells) + " |")
    return rows


def single_client(single, page_dir):
    manifests = [(path, read_json(path)) for path in sorted(Path(single).glob("manifest-*.json"))]
    if not manifests:
        raise ResultsError(f"{single}: no load manifest")
    return ["## One client at a time", "",
            "The table above has 8 clients sending requests at once on the same machine, so at 1 million rows it includes waiting. "
            "These runs use one client, so each number is what a single request costs on an otherwise idle server.", "",
            "| Engine | Rows | p50 | p95 | p99 | Throughput | Failed |", "|---|---|---|---|---|---|---|",
            *load_rows(manifests, page_dir), ""]


def render(results, page_dir, repeat=None, single=None):
    results, page_dir = Path(results), Path(page_dir)
    report_files = sorted((results / "compile" / "results").glob("*-report-full.json"))
    manifest_files = sorted(results.glob("manifest-*.json"))
    if len(report_files) != 1 or not manifest_files:
        raise ResultsError(f"{results}: expected one compile report and at least one load manifest")
    repeat_lines = repeatability(results, Path(repeat), page_dir) if repeat is not None else []
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
        "the results below say plainly whether it is met.",
        "",
        "The table has two paths. **Full compile** parses the schema from JSON on every call, as the conformance driver does, because "
        "it receives the schema as text with each request. **Prepared schema** uses a schema built once, which is what a host does: it "
        "builds its schema once and compiles every request against it. The second is what a host pays per request. " + summary,
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
    out += load_rows(manifests, page_dir)
    out += [""]
    if single is not None:
        out += single_client(single, page_dir)
    out += repeat_lines
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
                f"- Load: {load['concurrency']} threads for {load['duration_seconds']:g} seconds"
                + (f", after {load['warmup_seconds']:g} seconds of warm-up that were not measured" if load.get("warmup_seconds") else ""),
                f"- Date: {manifest['date']}, commit {manifest['commit']}",
                *machine_state(manifest),
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
    parser.add_argument("--readme", default=str(ROOT / "README.md"))
    parser.add_argument("--repeat")
    parser.add_argument("--single")
    args = parser.parse_args(argv)
    page, readme = Path(args.page), Path(args.readme)
    try:
        text = render(Path(args.results), page.parent, Path(args.repeat) if args.repeat else None, Path(args.single) if args.single else None)
        new_readme = None
        if args.repeat:
            block = readme_block(Path(args.results), Path(args.repeat), readme.parent)
            new_readme = replace_region(readme.read_text(encoding="utf-8"), block)
        write_whole(page, text)
        if new_readme is not None:
            write_whole(readme, new_readme)
        register(Path(args.site_json))
    except (ResultsError, KeyError, TypeError, OSError, UnicodeDecodeError) as error:
        print(f"perf_page.py: {error}", file=sys.stderr)
        return 2
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
