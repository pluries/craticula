#!/usr/bin/env python3
"""Pins scripts/perf_page.py, perf/compare.py and perf/compile_manifest.py (tasks #3849, #3848, spec FR-17, FR-19, FR-20, NFR-08,
acceptance criteria AC-4, AC-5 and AC-6 of story #3324): the performance page of the docs site and the comparison of two runs.

The page is generated from the raw results of a run (perf/results/<date>/): the compile benchmark's BenchmarkDotNet JSON and the
manifest-<engine>-<dataset>.json of each load run. So no number is typed by hand, and every number in a table is a link to the raw
file it came from (FR-20). Contract:
  python3 scripts/perf_page.py <results dir> [--page <file>] [--site-json <file>]
  writes the page (default site/pages/performance.md) and registers it in the site config once (slug "performance");
  exit 0 = written, 2 = no results, a malformed result file or a bad --repeat run (nothing is written).
perf/compare.py reports the spread of two runs: exit 0 = any spread (the differences are listed), 2 = a bad input.
Run: python3 scripts/test_perf_page.py
"""
import contextlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PAGE_SCRIPT = HERE / "perf_page.py"
COMPILE_JSON = "compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json"
FIRST_LOAD_MANIFEST = "manifest-postgres-10k.json"
SECTION = "## Repeatability"
FORBIDDEN_WORDS = ("target", "goal", "meets", "fails")
LIMIT = 10.0
REPEAT_FLAG = "--repeat"
LIMIT_FLAG = "--limit"
TRACEBACK = "Traceback"
PAGE_LARGEST = "Largest difference:"
COMMAND_LARGEST = "largest difference:"
STATISTICS = "Statistics"
MEAN = "Mean"
BENCHMARKS = "Benchmarks"
PARAMETERS = "Parameters"
SUMMARY_KEY = "summary"
P99 = "p99_ms"
POSTGRES = "postgres"
MONGO = "mongo"
POSTGRES_P99 = "load postgres 10k p99"
POSTGRES_P95 = "load postgres 10k p95"
MONGO_P99 = "load mongo 10k p99"
MONGO_MEAN = "compile mongo/deep-filter mean"
POSTGRES_MEAN = "compile postgres/plain-page mean"
FROM_ZERO = "from 0"
TOTAL = 10   # 2 compile benchmarks + 2 engines x (p50, p95, p99, requests per second)
CUSTOM_LIMIT = 25
WIDE_LIMIT = 30
HUGE_INTEGER = 10**400   # a JSON integer no float can hold
COMMITTED_RESULTS = "2026-11-16-p"
COMMITTED_REPEAT = "2026-11-16-p-repeat"
COMMITTED_SINGLE = "2026-11-16-p-single"
FIRST_RUN_FOLDER = "2026-11-20"
REPEAT_RUN = "2026-11-20-repeat"
MACHINE_KEY = "machine"
COMMIT_KEY = "commit"
COMMAND_KEY = "command"
MACHINE_LABEL = "test-box"
COMMIT_VALUE = "abc1234"
COMPILE_MANIFEST_FILE = "manifest-compile.json"
P95 = "p95_ms"
NUDGE = 1.01   # the repeat's postgres p95 differs from the first run's by 1%
SAME_FOLDER = "same folder"
MISSING_FIELD = "missing field"
MACHINE = "machine"
COMMIT = "commit"
SAME_COMMANDS = "same commands"
IDENTICAL = "identical measurements"
DATE_KEY = "date"
OTHER_MACHINE = "other-box"
OTHER_COMMIT = "def5678"
LONG_COMMIT = COMMIT_VALUE + "5"   # COMMIT_VALUE is a prefix of it, 7 and 8 characters
SHORT_COMMIT = "abc12"   # shorter than 7 characters: only equality counts
UNKNOWN_COMMIT = "unknown"
OTHER_DATE = "2026-11-21"
COMPILE_MANIFEST_PATH = f"compile/{COMPILE_MANIFEST_FILE}"
MONGO_LOAD_MANIFEST = "manifest-mongo-10k.json"
UNPAIRED_MANIFEST = "manifest-postgres-10k-x.json"
RUN_MANIFESTS = (COMPILE_MANIFEST_PATH, FIRST_LOAD_MANIFEST, MONGO_LOAD_MANIFEST)
RERUN_COMMAND = "bash scripts/perf-compile.sh perf/results/rerun/compile"
TINY_LIMIT = 0.5
MANIFEST_PREFIX = "manifest-"
NOT_SEPARATE = "not a separate run"
EXIT_2 = "exit 2"
OLD_PAGE = "# an earlier page\n"
OLD_SITE = json.dumps({"pages": [{"slug": "index"}]})
UNMATCHED = "the two runs do not hold the same measurements"


def load_module():
    spec = importlib.util.spec_from_file_location("perf_page", PAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_results(root, compile_mean=12345.6, slow=False, both_paths=False, run=FIRST_RUN_FOLDER):
    """Fake run: two compile benchmarks and two load manifests, laid out as perf/results/<date>/; `run` is only the folder name the recorded commands name."""
    results = root / "perf" / "results" / FIRST_RUN_FOLDER
    (results / "compile" / "results").mkdir(parents=True)
    benchmarks = [
        {PARAMETERS: "Backend=postgres&Shape=plain-page", STATISTICS: {"Mean": compile_mean}, "Memory": {"BytesAllocatedPerOperation": 7000}},
        {PARAMETERS: "Backend=mongo&Shape=deep-filter", STATISTICS: {"Mean": 90000.0 if slow else 26600.0}, "Memory": {"BytesAllocatedPerOperation": 18000}},
    ]
    if both_paths:   # the same shapes on the two paths: SchemaPath=full-compile, and prepared-schema at a third of the time
        benchmarks = [{**b, PARAMETERS: b[PARAMETERS] + "&SchemaPath=full-compile"} for b in benchmarks] + [
            {**b, PARAMETERS: b[PARAMETERS] + "&SchemaPath=prepared-schema", STATISTICS: {"Mean": b[STATISTICS]["Mean"] / 3},
             "Memory": {"BytesAllocatedPerOperation": b["Memory"]["BytesAllocatedPerOperation"] / 2}} for b in benchmarks]
    (results / COMPILE_JSON).write_text(json.dumps({BENCHMARKS: benchmarks}), encoding="utf-8")
    (results / "compile" / COMPILE_MANIFEST_FILE).write_text(json.dumps({
        MACHINE_KEY: MACHINE_LABEL, "date": FIRST_RUN_FOLDER, COMMIT_KEY: COMMIT_VALUE, "dotnet": "10.0.100", "benchmark": "BenchmarkDotNet 0.15.8",
        COMMAND_KEY: f"bash scripts/perf-compile.sh perf/results/{run}/compile"}), encoding="utf-8")
    for engine, version in (("postgres", "PostgreSQL 16.4"), ("mongo", "MongoDB 7.0.14")):
        manifest = {
            MACHINE_KEY: MACHINE_LABEL, "platform": "Linux 6.8, 4 logical CPUs, Python 3.12", "dataset": "10k", "engine": engine,
            "engine_version": version, "load": {"concurrency": 8, "duration_seconds": 60, "warmup_seconds": 5}, "shapes": ["number-gt.json"],
            "date": FIRST_RUN_FOLDER, COMMIT_KEY: COMMIT_VALUE,
            COMMAND_KEY: f"python3 perf/load.py --engine {engine} --dataset 10k --out perf/results/{run}",
            SUMMARY_KEY: {"count": 5000, "errors": 0, "requests_per_second": 83.33, "p50_ms": 8.5, P95: 15.6, P99: 21.2},
            "oversized": {"handled": True, "status": 400, "kind": "resource-limit-exceeded"},
        }
        (results / f"manifest-{engine}-10k.json").write_text(json.dumps(manifest), encoding="utf-8")
        (results / f"load-{engine}-10k.jsonl").write_text('{"shape": "number-gt.json", "status": 200, "ms": 8.5}\n', encoding="utf-8")
    return results


def write_repeat(root, **kwargs):
    """A legitimate repeat of write_results: its commands name their own folder and its postgres p95 differs by 1%; same machine and commit."""
    results = write_results(root, run=REPEAT_RUN, **kwargs)
    manifest = json.loads((results / FIRST_LOAD_MANIFEST).read_text(encoding="utf-8"))
    set_load_figure(results, POSTGRES, P95, manifest[SUMMARY_KEY][P95] * NUDGE)
    return results


def set_load_figure(results, engine, figure, value):
    path = results / f"manifest-{engine}-10k.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[SUMMARY_KEY][figure] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")


def edit_report(results, edit):
    path = results / COMPILE_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def set_compile_mean(results, parameters_contains, value):
    def edit(data):
        for benchmark in data[BENCHMARKS]:
            if parameters_contains in benchmark[PARAMETERS]:
                benchmark[STATISTICS][MEAN] = value
    edit_report(results, edit)


def split_first_benchmark(data):
    """Two benchmarks that map to the same measurement name: the first one and a copy, told apart only by a third parameter."""
    first = data[BENCHMARKS][0]
    copy = json.loads(json.dumps(first))
    first[PARAMETERS] += "&Rows=1"
    copy[PARAMETERS] += "&Rows=2"
    data[BENCHMARKS].append(copy)


def use_an_unknown_schema_path(data):
    data[BENCHMARKS][0][PARAMETERS] += "&SchemaPath=warm-schema"


def duplicate_load_manifest(results):
    """A second manifest file for the same engine and dataset."""
    source = results / FIRST_LOAD_MANIFEST
    (results / "manifest-postgres-10k-again.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def repeatability_section(page):
    return page[page.index(SECTION):].split("\n## ")[0]


def compare_module():
    return load_module().load_compare()


def double_run(results):
    """Doubles the compile means and the four load figures of a fake run, so every change is exactly 100%."""
    edit_report(results, lambda data: [benchmark[STATISTICS].update({MEAN: benchmark[STATISTICS][MEAN] * 2}) for benchmark in data[BENCHMARKS]])
    for engine in (POSTGRES, MONGO):
        manifest = json.loads((results / f"manifest-{engine}-10k.json").read_text(encoding="utf-8"))
        for figure in ("p50_ms", P95, P99, "requests_per_second"):
            set_load_figure(results, engine, figure, manifest[SUMMARY_KEY][figure] * 2)


def fake_pair(tmp):
    """Two fake runs under separate roots, for the first run and its repeat."""
    return write_results(Path(tmp) / "one"), write_repeat(Path(tmp) / "two")


@contextlib.contextmanager
def in_directory(path):
    """Runs the block with `path` as the working directory; None leaves it alone."""
    if path is None:
        yield
        return
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def read_manifest(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")


def read_figure(run, engine, figure):
    return read_manifest(run / f"manifest-{engine}-10k.json")[SUMMARY_KEY][figure]


def setting(relative, key, value):
    """change(run): sets `key` of the manifest `relative` to `value`."""
    def change(run):
        manifest = read_manifest(run / relative)
        manifest[key] = value
        write_manifest(run / relative, manifest)
    return change


def removing(relative, key):
    """change(run): removes `key` from the manifest `relative`."""
    def change(run):
        manifest = read_manifest(run / relative)
        del manifest[key]
        write_manifest(run / relative, manifest)
    return change


def removing_file(relative):
    def change(run):
        (run / relative).unlink()
    return change


def replacing_with_a_list(relative):
    def change(run):
        write_manifest(run / relative, [])
    return change


def every_manifest(key, value):
    """change(run): sets `key` in the compile manifest and in every load manifest."""
    def change(run):
        for relative in RUN_MANIFESTS:
            setting(relative, key, value)(run)
    return change


def applied_to(index, change):
    """A breaker that applies change(run) to the first run (0) or to the repeat (1)."""
    def breaker(first, second, tmp):
        change((first, second)[index])
        return first, second, None
    return breaker


def same_path(first, second, tmp):
    return first, first, None


def with_a_trailing_slash(first, second, tmp):
    return first, f"{first}/", None


def as_a_relative_path(first, second, tmp):
    cwd = first.parent
    return first, Path("..") / cwd.name / first.name, cwd


def through_a_symbolic_link(first, second, tmp):
    link = Path(tmp) / "link"
    link.symlink_to(first, target_is_directory=True)
    return first, link, None


def a_copy_of_the_first_run(first, second, tmp):
    shutil.rmtree(second)
    shutil.copytree(first, second)
    return first, second, None


def a_partial_copy(first, second, tmp):
    """A copy in which only the compile manifest records a new command: the engines were not run again."""
    a_copy_of_the_first_run(first, second, tmp)
    setting(COMPILE_MANIFEST_PATH, COMMAND_KEY, RERUN_COMMAND)(second)
    return first, second, None


def with_the_nudge_undone(first, second, tmp):
    set_load_figure(second, POSTGRES, P95, read_figure(first, POSTGRES, P95))
    return first, second, None


def a_copy_on_another_machine(first, second, tmp):
    a_copy_of_the_first_run(first, second, tmp)
    every_manifest(MACHINE_KEY, OTHER_MACHINE)(second)
    return first, second, None


def a_copy_without_a_machine(first, second, tmp):
    a_copy_of_the_first_run(first, second, tmp)
    removing(FIRST_LOAD_MANIFEST, MACHINE_KEY)(second)
    return first, second, None


def the_same_folder_with_an_unreadable_manifest(first, second, tmp):
    (first / FIRST_LOAD_MANIFEST).write_text("{ not json", encoding="utf-8")
    return first, first, None


def with_an_unpaired_manifest(first, second, tmp):
    (second / FIRST_LOAD_MANIFEST).rename(second / UNPAIRED_MANIFEST)
    return first, second, None


# (label, the file and field the message names, change(run)); each is applied to the first run and to the repeat
MISSING_CASES = [
    ("load manifest without machine", (FIRST_LOAD_MANIFEST, MACHINE_KEY), removing(FIRST_LOAD_MANIFEST, MACHINE_KEY)),
    ("load manifest without commit", (FIRST_LOAD_MANIFEST, COMMIT_KEY), removing(FIRST_LOAD_MANIFEST, COMMIT_KEY)),
    ("load manifest without command", (FIRST_LOAD_MANIFEST, COMMAND_KEY), removing(FIRST_LOAD_MANIFEST, COMMAND_KEY)),
    ("compile manifest without machine", (COMPILE_MANIFEST_FILE, MACHINE_KEY), removing(COMPILE_MANIFEST_PATH, MACHINE_KEY)),
    ("unknown commit", (FIRST_LOAD_MANIFEST, COMMIT_KEY), setting(FIRST_LOAD_MANIFEST, COMMIT_KEY, UNKNOWN_COMMIT)),
    ("empty commit", (COMPILE_MANIFEST_FILE, COMMIT_KEY), setting(COMPILE_MANIFEST_PATH, COMMIT_KEY, "")),
    ("whitespace-only machine", (FIRST_LOAD_MANIFEST, MACHINE_KEY), setting(FIRST_LOAD_MANIFEST, MACHINE_KEY, " ")),
    ("no compile manifest", ("compile manifest",), removing_file(COMPILE_MANIFEST_PATH)),
    ("compile manifest that is a list", (COMPILE_MANIFEST_FILE,), replacing_with_a_list(COMPILE_MANIFEST_PATH)),
]
MISSING_ROWS = [(f"{label}, {where}", texts, applied_to(index, change))
                for label, texts, change in MISSING_CASES for where, index in (("first run", 0), ("repeat", 1))]

# (check name, label, breaker(first, second, tmp) -> (first, second, cwd)): every way to build a pair the checks must refuse
BREAKERS = [
    (SAME_FOLDER, "the same path", same_path),
    (SAME_FOLDER, "a trailing slash", with_a_trailing_slash),
    (SAME_FOLDER, "a relative path", as_a_relative_path),
    (SAME_FOLDER, "a symbolic link", through_a_symbolic_link),
    *[(MISSING_FIELD, label, breaker) for label, _, breaker in MISSING_ROWS],
    (MACHINE, "another label in every manifest of the repeat", applied_to(1, every_manifest(MACHINE_KEY, OTHER_MACHINE))),
    (MACHINE, "two labels in the repeat", applied_to(1, setting(FIRST_LOAD_MANIFEST, MACHINE_KEY, OTHER_MACHINE))),
    (MACHINE, "two labels in the first run", applied_to(0, setting(FIRST_LOAD_MANIFEST, MACHINE_KEY, OTHER_MACHINE))),
    # US1-AS8: two different commits are refused and both are named
    (COMMIT, "another commit in every manifest of the repeat", applied_to(1, every_manifest(COMMIT_KEY, OTHER_COMMIT))),
    (COMMIT, "two commits in the repeat", applied_to(1, setting(FIRST_LOAD_MANIFEST, COMMIT_KEY, OTHER_COMMIT))),
    (COMMIT, "two commits in the first run", applied_to(0, setting(FIRST_LOAD_MANIFEST, COMMIT_KEY, OTHER_COMMIT))),
    (SAME_COMMANDS, "a copy of the first run", a_copy_of_the_first_run),
    (SAME_COMMANDS, "a partial copy", a_partial_copy),
    (IDENTICAL, "every figure equal, the commands differ", with_the_nudge_undone),
]
# what a refusal message must contain besides its name; C2 is pinned per file and field through MISSING_ROWS
CHECK_VALUES = {
    SAME_FOLDER: (), MISSING_FIELD: (), MACHINE: (MACHINE_LABEL, OTHER_MACHINE), COMMIT: (COMMIT_VALUE, OTHER_COMMIT),
    SAME_COMMANDS: (MANIFEST_PREFIX,), IDENTICAL: (f"{TOTAL} measurements",),
}
# (what the message starts with, label, breaker): which check speaks first when several fail
ORDER_CASES = [
    (f"{MACHINE}:", "machine before same commands (US2-AS3)", a_copy_on_another_machine),
    (f"{MISSING_FIELD}:", "missing field before machine", a_copy_without_a_machine),
    (f"{SAME_FOLDER}:", "same folder before anything is read", the_same_folder_with_an_unreadable_manifest),
    (UNMATCHED, "a manifest without a counterpart is the existing refusal", with_an_unpaired_manifest),
]


def one_figure_differs(first, second):
    """US1-AS5: only the repeat's mongo p99 differs from the first run's."""
    with_the_nudge_undone(first, second, None)
    set_load_figure(second, MONGO, P99, read_figure(first, MONGO, P99) * NUDGE)


def prefix_commits(first, second):
    every_manifest(COMMIT_KEY, LONG_COMMIT)(second)


def equal_short_commits(first, second):
    every_manifest(COMMIT_KEY, SHORT_COMMIT)(first)
    every_manifest(COMMIT_KEY, SHORT_COMMIT)(second)


def another_date(first, second):
    every_manifest(DATE_KEY, OTHER_DATE)(second)


# (label, prepare(first, second)): pairs a real repeat can be and the checks must accept
ACCEPTANCES = [
    ("US1-AS5 one figure differs", one_figure_differs),
    ("US1-AS9 commits of 7 and 8 characters, one a prefix of the other", prefix_commits),
    ("US1-AS9 equal commits shorter than 7 characters", equal_short_commits),
    ("US1-AS11 another date, same machine and commit", another_date),
]
COMMITTED_PAIRS = [
    (COMMITTED_RESULTS, COMMITTED_REPEAT), ("2026-11-16-ltp01", "2026-11-16-ltp01-repeat"),
    ("2026-11-16-w", "2026-11-16-w-repeat"), ("2026-11-16", "2026-11-16-repeat"),
]


def header_comment(path):
    """The leading comment block of a script, without the comment marks and with whitespace normalised."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line.lstrip("#"))
    return " ".join(" ".join(lines).split())


def clear_benchmarks(data):
    data[BENCHMARKS].clear()


def null_parameters(data):
    data[BENCHMARKS][0][PARAMETERS] = None


def drop_a_benchmark(data):
    data[BENCHMARKS].pop()


def is_measurement(cell):
    """A table cell that shows a measured number with its unit, as a link ([12.3 µs](path)) or as plain text."""
    text = cell[1:cell.index("]")] if cell.startswith("[") and "]" in cell else cell
    parts = text.split(" ")
    return len(parts) == 2 and parts[1] in ("µs", "ms", "KiB", "B", "/s") and parts[0].replace(".", "", 1).isdigit()


def table_rows(page):
    return [line for line in page.splitlines() if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line)]


class RenderTests(unittest.TestCase):
    def render(self, **kwargs):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root, **kwargs)
            page_path = root / "site" / "pages" / "performance.md"
            page = module.render(results, page_path.parent)
            return page, root, page_path.parent

    def test_every_number_in_a_table_is_a_link_to_a_raw_file_that_exists(self):  # T1
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            page_dir = root / "site" / "pages"
            page_dir.mkdir(parents=True)
            page = module.render(results, page_dir)
            checked = 0
            for row in table_rows(page):
                for cell in [c.strip() for c in row.strip("|").split("|")]:
                    if not is_measurement(cell):
                        continue
                    match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", cell)
                    self.assertIsNotNone(match, f"a number without a link: {cell!r} in {row!r}")
                    self.assertTrue((page_dir / match.group(2)).resolve().is_file(), f"dead link {match.group(2)}")
                    checked += 1
            self.assertGreaterEqual(checked, 12)

    def test_the_ef_engine_has_its_own_row_and_label(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            manifest = json.loads((results / FIRST_LOAD_MANIFEST).read_text(encoding="utf-8"))
            manifest["engine"] = "ef"
            manifest["engine_version"] = "PostgreSQL 16.4 through Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3"
            manifest[SUMMARY_KEY]["p50_ms"] = 9.9
            (results / "manifest-ef-10k.json").write_text(json.dumps(manifest), encoding="utf-8")
            (results / "load-ef-10k.jsonl").write_text("{}\n", encoding="utf-8")
            page_dir = root / "site" / "pages"
            page_dir.mkdir(parents=True)
            page = module.render(results, page_dir)
            self.assertIn("PostgreSQL through EF Core", page)
            self.assertIn("9.9 ms", page)
            self.assertIn("Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3", page)

    def test_the_numbers_come_from_the_results_not_from_the_text(self):  # T1
        page, _, _ = self.render()
        for expected in ("12.3 µs", "6.8 KiB", "8.5 ms", "15.6 ms", "21.2 ms", "83.3 /s"):
            self.assertIn(expected, page)

    def test_a_mean_below_the_target_says_it_meets_perf_1(self):  # T2
        page, _, _ = self.render()
        self.assertIn("meets PERF-1", page)

    def test_a_slow_result_says_it_does_not_meet_perf_1_and_still_shows_the_number(self):  # T2
        page, _, _ = self.render(slow=True)
        self.assertIn("does not meet PERF-1", page)
        self.assertIn("90.0 µs", page)

    def test_each_run_states_machine_dataset_versions_load_date_commit_and_the_repeat_command(self):  # T3
        page, _, _ = self.render()
        for expected in ("test-box", "10k", "PostgreSQL 16.4", "MongoDB 7.0.14", "8 threads", "60 seconds", "5 seconds of warm-up", "2026-11-20", "abc1234",
                         "python3 perf/load.py --engine postgres --dataset 10k"):
            self.assertIn(expected, page)

    def test_the_compile_run_states_machine_date_commit_and_the_repeat_command(self):  # T3
        page, _, _ = self.render()
        for expected in ("BenchmarkDotNet 0.15.8", ".NET 10.0.100", "bash scripts/perf-compile.sh perf/results/2026-11-20/compile"):
            self.assertIn(expected, page)

    def test_the_machine_state_of_each_load_run_is_stated(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            results = write_results(Path(tmp))
            for path in results.glob("manifest-*-*.json"):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["environment"] = {"cpu_steal_percent": 1.5, "load_average_1m": 7.25, "thermal_c": {"acpitz": 95.0}}
                path.write_text(json.dumps(manifest), encoding="utf-8")
            page_dir = Path(tmp) / "site" / "pages"
            page_dir.mkdir(parents=True)
            page = module.render(results, page_dir)
            self.assertIn("CPU steal 1.5%", page)
            self.assertIn("load average 7.25", page)
            self.assertIn("acpitz 95 °C", page)

    def test_a_manifest_without_an_environment_still_renders(self):
        page, _, _ = self.render()
        self.assertNotIn("CPU steal", page)

    def test_the_oversized_request_is_reported(self):  # T3
        page, _, _ = self.render()
        self.assertIn("resource-limit-exceeded", page)

    def test_the_page_follows_the_site_rules(self):  # T4
        page, _, _ = self.render()
        self.assertTrue(page.startswith("# Performance\n"))
        self.assertNotIn("—", page)  # no em dash chains
        self.assertLess(max(len(line) for line in page.splitlines() if line.startswith("## ")), 60)


class SingleClientTests(unittest.TestCase):
    """AC-2 of story #3856: the page shows a run with one client next to the concurrent one, every number linked."""

    def single_run(self, root):
        results = write_results(root)
        for path in results.glob("manifest-*-*.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["load"]["concurrency"] = 1
            manifest[SUMMARY_KEY]["p50_ms"] = 3.3
            path.write_text(json.dumps(manifest), encoding="utf-8")
        return results

    def render(self, with_single=True):
        module = load_module()
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first = write_results(Path(one))
            single = self.single_run(Path(two)) if with_single else None
            page_dir = Path(one) / "site" / "pages"
            page_dir.mkdir(parents=True)
            return module.render(first, page_dir, single=single)

    def test_the_page_has_a_section_with_the_one_client_numbers(self):
        page = self.render()
        self.assertIn("## One client at a time", page)
        self.assertIn("3.3 ms", page)

    def test_every_number_of_that_section_is_a_link(self):
        page = self.render()
        section = page.split("## One client at a time")[1].split("\n## ")[0]
        rows = [line for line in section.splitlines() if line.startswith("|") and is_measurement(line.strip("|").split("|")[2].strip())]
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            for cell in [c.strip() for c in row.strip("|").split("|")][2:6]:
                self.assertTrue(cell.startswith("[") and "](" in cell, f"a number without a link: {cell!r}")

    def test_without_a_single_client_run_there_is_no_such_section(self):
        self.assertNotIn("One client at a time", self.render(with_single=False))

    def test_the_cli_takes_the_single_client_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            import shutil
            single = root / "perf" / "results" / "2026-11-20-single"
            shutil.copytree(results, single)
            page = root / "site" / "pages" / "performance.md"
            site_json = root / "site" / "site.json"
            site_json.parent.mkdir(parents=True, exist_ok=True)
            site_json.write_text(json.dumps({"pages": []}), encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(PAGE_SCRIPT), str(results), "--single", str(single), "--page", str(page),
                                     "--site-json", str(site_json)], capture_output=True, text=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("## One client at a time", page.read_text(encoding="utf-8"))


class SchemaPathTests(unittest.TestCase):
    """The compile table shows the full compile (schema parsed from JSON on every call) and the prepared-schema path side by side."""

    def render(self, both_paths, slow=False):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            results = write_results(Path(tmp), both_paths=both_paths, slow=slow)
            page_dir = Path(tmp) / "site" / "pages"
            page_dir.mkdir(parents=True)
            return module.render(results, page_dir)

    def compile_section(self, page):
        return page.split("## Compile time")[1].split("\n## ")[0]

    def test_both_paths_are_columns_of_one_table(self):
        section = self.compile_section(self.render(True))
        self.assertIn("Full compile", section)
        self.assertIn("Prepared schema", section)
        rows = [line for line in section.splitlines() if line.startswith("| postgres | plain-page") or line.startswith("| mongo | deep-filter")]
        self.assertEqual(2, len(rows), "one row per backend and shape, with both paths in it")

    def test_every_number_of_both_paths_is_a_link(self):
        section = self.compile_section(self.render(True))
        row = next(line for line in section.splitlines() if line.startswith("| postgres | plain-page"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        measured = [c for c in cells if is_measurement(c[1:c.index("]")] if c.startswith("[") else c)]
        self.assertGreaterEqual(len(measured), 4)   # full mean and allocation, prepared mean and allocation
        for cell in measured:
            self.assertTrue(cell.startswith("[") and "](" in cell, f"a number without a link: {cell!r}")

    def test_each_path_has_its_own_verdict(self):
        page = self.render(True, slow=True)   # mongo/deep-filter: 90 us full, 30 us prepared
        row = next(line for line in self.compile_section(page).splitlines() if line.startswith("| mongo | deep-filter"))
        self.assertIn("does not meet PERF-1", row)
        self.assertIn("meets PERF-1", row.replace("does not meet PERF-1", ""))

    def test_the_prepared_numbers_are_the_prepared_run_not_the_full_one(self):
        section = self.compile_section(self.render(True))
        self.assertIn("12.3 µs", section)   # full postgres/plain-page
        self.assertIn("4.1 µs", section)    # prepared: a third of it

    def test_results_without_a_schema_path_still_render_and_say_the_prepared_path_was_not_measured(self):
        section = self.compile_section(self.render(False))
        self.assertIn("not measured", section)
        self.assertIn("12.3 µs", section)

    def test_the_section_explains_the_two_paths(self):
        section = self.compile_section(self.render(True))
        self.assertIn("builds its schema once", section)


class RepeatabilityTests(unittest.TestCase):
    """NFR-08, AC-4: the page states how a repeat run compared, and every number it quotes links to its raw file."""

    def scaled(self, results, factor):
        for path in results.glob("manifest-*-*.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest[SUMMARY_KEY]["p99_ms"] *= factor
            path.write_text(json.dumps(manifest), encoding="utf-8")

    def render(self, factor):
        module = load_module()
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first, second = write_results(Path(one)), write_repeat(Path(two))
            self.scaled(second, factor)
            page_dir = Path(one) / "site" / "pages"
            page_dir.mkdir(parents=True)
            page = module.render(first, page_dir, repeat=second)
            return page

    def render_with(self, prepare):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            prepare(first, second)
            page_dir = Path(tmp) / "one" / "site" / "pages"
            page_dir.mkdir(parents=True)
            return module.render(first, page_dir, repeat=second)

    def spread(self, **figures):
        """prepare() for render_with: both runs start at p99 100 on both engines, the repeat takes `figures` (engine=value)."""
        def prepare(first, second):
            for engine in (POSTGRES, MONGO):
                set_load_figure(first, engine, P99, 100.0)
                set_load_figure(second, engine, P99, figures.get(engine, 100.0))
        return prepare

    def bullets(self, section):
        return [line for line in section.splitlines() if line.startswith("- ")]

    def test_the_section_says_twice_on_the_same_machine_and_has_no_target_wording(self):  # US1-AS1
        for factor in (1.0, 1.25):
            with self.subTest(factor=factor):
                section = repeatability_section(self.render(factor))
                self.assertIn("Every measurement was taken twice on the same machine, in two runs one after the other.", section)
                for word in FORBIDDEN_WORDS:
                    self.assertNotIn(word, section.lower())

    def test_differences_are_counted_the_largest_is_named_and_the_list_has_two_links_per_line(self):  # US1-AS2
        section = repeatability_section(self.render(1.25))
        self.assertIn(f"2 of {TOTAL} measurements of the repeat run differ by more than {LIMIT:g}% from this run.", section)
        largest = next(line for line in section.splitlines() if line.startswith(PAGE_LARGEST))
        self.assertTrue(largest.startswith(f"{PAGE_LARGEST} {MONGO_P99}: ["), largest)   # a tie keeps name order
        self.assertEqual(2, largest.count("]("), largest)
        self.assertTrue(largest.endswith("."), largest)
        self.assertIn(f"Differences above {LIMIT:g}%, largest first:", section)
        bullets = self.bullets(section)
        self.assertEqual(2, len(bullets))
        for line in bullets:
            self.assertEqual(2, line.count("]("), line)
            self.assertIn("25.0% apart", line)

    def test_the_list_is_largest_first(self):  # US1-AS2
        section = repeatability_section(self.render_with(self.spread(mongo=120.0, postgres=130.0)))
        bullets = self.bullets(section)
        self.assertEqual([POSTGRES_P99, MONGO_P99], [line[2:].split(":")[0] for line in bullets])
        largest = next(line for line in section.splitlines() if line.startswith(PAGE_LARGEST))
        self.assertIn(f" {POSTGRES_P99}: [", largest)
        self.assertIn("30.0% apart", largest)

    def test_when_none_differs_the_section_says_so_and_still_names_the_largest(self):  # US1-AS3
        section = repeatability_section(self.render(1.0))
        self.assertIn(f"None of the {TOTAL} measurements of the repeat run differs by more than {LIMIT:g}% from this run.", section)
        largest = next(line for line in section.splitlines() if line.startswith(PAGE_LARGEST))
        self.assertEqual(2, largest.count("]("), largest)
        self.assertEqual([], self.bullets(section))
        self.assertNotIn("Differences above", section)
        self.assertNotIn("target", section.lower())

    def test_exactly_the_limit_is_not_listed_and_a_hair_above_is_listed_with_one_decimal(self):  # US1-AS5
        section = repeatability_section(self.render_with(self.spread(mongo=110.0, postgres=110.04)))
        bullets = self.bullets(section)
        self.assertEqual(1, len(bullets), bullets)
        self.assertTrue(bullets[0].startswith(f"- {POSTGRES_P99}: ["), bullets[0])
        self.assertIn("10.0% apart", bullets[0])
        self.assertIn(f"1 of {TOTAL} measurements of the repeat run differ by more than {LIMIT:g}%", section)

    def test_a_zero_baseline_with_a_non_zero_repeat_is_listed_as_from_zero(self):  # US1-AS6
        def prepare(first, second):
            set_load_figure(first, POSTGRES, P99, 0)
            set_load_figure(second, POSTGRES, P99, 5.0)
        section = repeatability_section(self.render_with(prepare))
        bullets = self.bullets(section)
        self.assertEqual(1, len(bullets), bullets)
        self.assertTrue(bullets[0].startswith(f"- {POSTGRES_P99}: ["), bullets[0])
        self.assertTrue(bullets[0].endswith(FROM_ZERO), bullets[0])
        largest = next(line for line in section.splitlines() if line.startswith(PAGE_LARGEST))
        self.assertIn(FROM_ZERO, largest)

    def test_the_published_page_is_what_the_generator_writes_for_the_committed_runs(self):  # US1-AS4 (spec 001) and US1-AS12 (spec 002: the published page does not change)
        runs = ROOT / "perf" / "results"
        page_dir = ROOT / "site" / "pages"
        page = load_module().render(
            runs / COMMITTED_RESULTS, page_dir, repeat=runs / COMMITTED_REPEAT, single=runs / COMMITTED_SINGLE)
        self.assertEqual((page_dir / "performance.md").read_text(encoding="utf-8"), page)
        section = repeatability_section(page)
        self.assertEqual(21, len(self.bullets(section)))
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, section.lower())

    def test_without_a_repeat_there_is_no_repeatability_section(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            results = write_results(Path(tmp))
            page_dir = Path(tmp) / "site" / "pages"
            page_dir.mkdir(parents=True)
            self.assertNotIn("Repeatability", module.render(results, page_dir))


class RefusalCoreTests(unittest.TestCase):
    """compare() refuses a repeat that is not a separate run (spec 002, C1 to C6), reporting the first failing check."""

    def refusal(self, breaker):
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            first, second, cwd = breaker(first, second, Path(tmp))
            with in_directory(cwd), self.assertRaises(module.RunError) as caught:
                module.compare(first, second)
            return str(caught.exception)

    def accepted_total(self, prepare):
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            prepare(first, second)
            return module.compare(first, second)[0]

    def test_every_broken_pair_is_refused_with_the_name_of_its_check_and_the_values_compared(self):  # US1-AS1 to AS4, AS6 to AS8, AS10
        for check, label, breaker in BREAKERS:
            with self.subTest(check=check, label=label):
                message = self.refusal(breaker)
                self.assertTrue(message.startswith(f"{check}:"), message)
                for value in CHECK_VALUES[check]:
                    self.assertIn(value, message)

    def test_a_missing_field_names_the_file_and_the_field_in_either_run(self):  # US1-AS10
        for label, texts, breaker in MISSING_ROWS:
            with self.subTest(label=label):
                message = self.refusal(breaker)
                self.assertTrue(message.startswith(f"{MISSING_FIELD}:"), message)
                for text in texts:
                    self.assertIn(text, message)

    def test_a_partial_copy_names_a_manifest_that_is_unchanged(self):  # US1-AS3
        message = self.refusal(a_partial_copy)
        self.assertTrue(message.startswith(f"{SAME_COMMANDS}:"), message)
        self.assertNotIn(COMPILE_MANIFEST_FILE, message)
        self.assertTrue(any(name in message for name in (FIRST_LOAD_MANIFEST, MONGO_LOAD_MANIFEST)), message)

    def test_the_first_failing_check_is_the_one_reported(self):  # US2-AS3
        for expected, label, breaker in ORDER_CASES:
            with self.subTest(label=label):
                self.assertTrue(self.refusal(breaker).startswith(expected))

    def test_the_legitimate_pair_of_the_fixture_is_accepted(self):  # control
        self.assertEqual(TOTAL, self.accepted_total(lambda first, second: None))

    def test_a_real_repeat_is_accepted(self):  # US1-AS5, AS9, AS11
        for label, prepare in ACCEPTANCES:
            with self.subTest(label=label):
                self.assertEqual(TOTAL, self.accepted_total(prepare))

    def test_the_single_figure_pair_differs_in_that_figure_only(self):  # US1-AS5
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            one_figure_differs(first, second)
            _, outside, _ = module.compare(first, second, TINY_LIMIT)
            self.assertEqual([MONGO_P99], [item.name for item in outside])


class CompareTests(unittest.TestCase):
    """T6: perf/compare.py <first run> <second run> [--limit 10]: exit 0 = the two runs were read and any spread is listed (the
    differences above the limit, percent, default 10), 2 = a run is missing, unreadable, malformed or does not match the other."""
    SCRIPT = ROOT / "perf" / "compare.py"

    def run_compare(self, first, second, *extra, cwd=None):
        return subprocess.run([sys.executable, "-I", str(self.SCRIPT), str(first), str(second), *extra], capture_output=True, text=True,
                              timeout=30, cwd=cwd)

    def scale(self, results, factor):
        """Multiplies the p50 and the compile means of a fake run by `factor`."""
        for path in results.glob("manifest-*-*.json"):
            if path.name == "manifest-compile.json":
                continue
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest[SUMMARY_KEY]["p50_ms"] *= factor
            path.write_text(json.dumps(manifest), encoding="utf-8")
        report = results / COMPILE_JSON
        data = json.loads(report.read_text(encoding="utf-8"))
        for benchmark in data[BENCHMARKS]:
            benchmark[STATISTICS]["Mean"] *= factor
        report.write_text(json.dumps(data), encoding="utf-8")

    def test_the_two_paths_are_compared_as_separate_measurements(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one), both_paths=True), write_repeat(Path(two), both_paths=True)
            report = b / COMPILE_JSON
            data = json.loads(report.read_text(encoding="utf-8"))
            for benchmark in data[BENCHMARKS]:
                if "SchemaPath=prepared-schema" in benchmark[PARAMETERS]:
                    benchmark[STATISTICS]["Mean"] *= 1.5     # only the prepared path moves
            report.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("prepared", result.stdout)
            self.assertNotIn("compile postgres/plain-page mean:", result.stdout)

    def test_two_runs_within_the_limit_say_none_differs(self):  # US2-AS2
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"none of the {TOTAL} measurements differs by more than {LIMIT:g}%", result.stdout)
            self.assertIn(COMMAND_LARGEST, result.stdout)
            self.assertIn(f"{POSTGRES_P95}", result.stdout)   # the 1% nudge is the largest difference the pair carries

    def test_a_change_below_the_limit_passes(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_repeat(Path(two))
            self.scale(b, 1.09)
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"none of the {TOTAL} measurements differs by more than {LIMIT:g}%", result.stdout)

    def test_a_change_above_the_limit_is_listed_and_still_exits_0(self):  # US2-AS1
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_repeat(Path(two))
            self.scale(b, 1.25)
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"4 of {TOTAL} measurements differ by more than {LIMIT:g}%:", result.stdout)
            self.assertIn(COMMAND_LARGEST, result.stdout)
            self.assertIn("p50", result.stdout)
            self.assertIn("compile", result.stdout)
            self.assertIn("25.0%", result.stdout)

    def test_a_zero_baseline_is_printed_as_from_zero(self):  # US2-AS1
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            set_load_figure(a, POSTGRES, P99, 0)
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(FROM_ZERO, result.stdout)

    def test_a_custom_limit_lists_only_the_measurements_above_it(self):  # US2-AS4
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            set_compile_mean(b, "Backend=postgres", 12345.6 * 1.2)
            set_compile_mean(b, "Backend=mongo", 26600.0 * 1.3)
            result = self.run_compare(a, b, LIMIT_FLAG, str(CUSTOM_LIMIT))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"1 of {TOTAL} measurements differ by more than {CUSTOM_LIMIT:g}%:", result.stdout)
            self.assertIn(MONGO_MEAN, result.stdout)
            self.assertNotIn(POSTGRES_MEAN, result.stdout)

    def test_a_limit_that_is_not_a_finite_number_above_zero_is_exit_2_and_prints_no_comparison(self):  # US2-AS5
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            for bad in ("nan", "inf", "abc", "0", "-1"):   # abc already exits 2 today: a pin
                with self.subTest(limit=bad):
                    result = self.run_compare(a, b, LIMIT_FLAG, bad)
                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertEqual("", result.stdout)
                    self.assertIn(LIMIT_FLAG, result.stderr)
                    self.assertNotIn(TRACEBACK, result.stderr)

    def assert_bad_input(self, first, second):
        result = self.run_compare(first, second)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertNotIn(TRACEBACK, result.stderr)
        self.assertNotIn("none of", result.stdout)
        self.assertNotEqual("", result.stderr)

    def test_a_value_that_is_not_a_finite_number_is_exit_2(self):  # US2-AS6
        for bad in (float("nan"), "12", True):
            with self.subTest(value=bad), tempfile.TemporaryDirectory() as tmp:
                a, b = fake_pair(tmp)
                set_load_figure(b, POSTGRES, P99, bad)
                self.assert_bad_input(a, b)

    def test_a_report_with_a_null_parameters_is_exit_2_without_a_traceback(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            edit_report(b, null_parameters)
            self.assert_bad_input(a, b)

    def test_runs_that_hold_no_benchmark_are_exit_2(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            edit_report(a, clear_benchmarks)
            edit_report(b, clear_benchmarks)
            self.assert_bad_input(a, b)

    def test_runs_that_do_not_hold_the_same_measurements_are_exit_2(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            edit_report(b, drop_a_benchmark)
            self.assert_bad_input(a, b)

    def test_two_benchmarks_with_the_same_measurement_name_are_exit_2(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            edit_report(a, split_first_benchmark)
            edit_report(b, split_first_benchmark)
            self.assert_bad_input(a, b)

    def test_a_schema_path_that_is_not_known_is_exit_2(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            edit_report(a, use_an_unknown_schema_path)
            edit_report(b, use_an_unknown_schema_path)
            self.assert_bad_input(a, b)

    def test_two_load_manifests_for_the_same_engine_and_dataset_are_exit_2(self):  # US2-AS3
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            duplicate_load_manifest(a)
            duplicate_load_manifest(b)
            self.assert_bad_input(a, b)

    def test_a_figure_too_big_for_a_float_is_exit_2_without_a_traceback(self):  # US2-AS6
        with tempfile.TemporaryDirectory() as tmp:
            a, b = fake_pair(tmp)
            set_load_figure(b, POSTGRES, P99, HUGE_INTEGER)
            self.assert_bad_input(a, b)

    def test_the_limit_can_be_changed(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_repeat(Path(two))
            self.scale(b, 1.25)
            result = self.run_compare(a, b, LIMIT_FLAG, str(WIDE_LIMIT))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"none of the {TOTAL} measurements differs by more than {WIDE_LIMIT:g}%", result.stdout)

    def test_a_run_whose_requests_all_failed_is_exit_2_not_exit_1(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_repeat(Path(two))
            path = b / FIRST_LOAD_MANIFEST
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest[SUMMARY_KEY]["p50_ms"] = None
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_compare(a, b)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("p50", result.stderr)

    def test_a_run_with_a_missing_folder_is_exit_2(self):
        with tempfile.TemporaryDirectory() as one:
            a = write_results(Path(one))
            self.assertEqual(2, self.run_compare(a, Path(one) / "nowhere").returncode)

    def test_every_broken_pair_is_refused_by_the_command_with_nothing_on_stdout(self):  # US2-AS1
        for check, label, breaker in BREAKERS:
            with self.subTest(check=check, label=label), tempfile.TemporaryDirectory() as tmp:
                first, second = fake_pair(tmp)
                first, second, cwd = breaker(first, second, Path(tmp))
                result = self.run_compare(first, second, cwd=cwd)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("", result.stdout)
                self.assertTrue(result.stderr.startswith(f"compare.py: {check}:"), result.stderr)

    def test_the_four_committed_pairs_are_compared_as_before(self):  # US2-AS2
        for first, second in COMMITTED_PAIRS:
            with self.subTest(first=first):
                result = self.run_compare(ROOT / "perf" / "results" / first, ROOT / "perf" / "results" / second)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn(COMMAND_LARGEST, result.stdout)

    def test_the_docstring_and_the_script_header_say_a_repeat_that_is_not_a_separate_run_is_refused_with_exit_2(self):  # SC-004
        docstring = " ".join(compare_module().__doc__.split())
        header = header_comment(ROOT / "scripts" / "perf-run.sh")
        for name, text in (("perf/compare.py", docstring), ("scripts/perf-run.sh", header)):
            for phrase in (NOT_SEPARATE, EXIT_2):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)


class CompareCoreTests(unittest.TestCase):
    """perf/compare.py compare(): (total, outside, largest), the spread of every measurement."""

    def pair(self, tmp, first_p99=100.0, **repeat_p99):
        """Two fake runs: every p99 of the first is `first_p99`, the repeat's per engine (engine=value, default unchanged)."""
        first, second = fake_pair(tmp)
        for engine in (POSTGRES, MONGO):
            set_load_figure(first, engine, P99, first_p99)
            set_load_figure(second, engine, P99, repeat_p99.get(engine, first_p99))
        return first, second

    def test_it_returns_the_total_the_outside_list_and_the_largest(self):  # US1-AS2
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = self.pair(tmp, mongo=120.0, postgres=130.0)
            total, outside, largest = module.compare(first, second)
            self.assertEqual(TOTAL, total)
            self.assertEqual([POSTGRES_P99, MONGO_P99], [item.name for item in outside])
            self.assertEqual(POSTGRES_P99, largest.name)
            self.assertAlmostEqual(30.0, largest.change)
            self.assertEqual((100.0, 130.0), (largest.first, largest.second))
            self.assertTrue(largest.first_path.is_relative_to(first))
            self.assertTrue(largest.second_path.is_relative_to(second))

    def test_ties_keep_name_order(self):  # US1-AS2
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            _, outside, largest = module.compare(*self.pair(tmp, mongo=125.0, postgres=125.0))
            self.assertEqual([MONGO_P99, POSTGRES_P99], [item.name for item in outside])
            self.assertEqual(MONGO_P99, largest.name)

    def test_the_largest_is_named_when_none_exceeds_the_limit(self):  # US1-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            _, outside, largest = module.compare(*self.pair(tmp, postgres=105.0))
            self.assertEqual([], outside)
            self.assertEqual(POSTGRES_P99, largest.name)
            self.assertAlmostEqual(5.0, largest.change)

    def test_the_largest_is_the_first_by_name_when_every_change_is_equal(self):  # US1-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first, second = write_results(Path(one)), write_results(Path(two), run=REPEAT_RUN)
            double_run(second)
            _, outside, largest = module.compare(first, second, 100.0)
            self.assertEqual([], outside)
            self.assertEqual(MONGO_MEAN, largest.name)
            self.assertEqual(100.0, largest.change)

    def test_exactly_the_limit_is_not_listed_and_a_hair_above_is(self):  # US1-AS5
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            _, outside, _ = module.compare(*self.pair(tmp, mongo=110.0, postgres=110.04))
            self.assertEqual([POSTGRES_P99], [item.name for item in outside])

    def test_a_zero_baseline_with_a_non_zero_repeat_is_listed_as_infinite_and_described_from_zero(self):  # US1-AS6, FR-004
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = self.pair(tmp, first_p99=0.0, postgres=5.0)
            _, outside, largest = module.compare(first, second)
            self.assertEqual([POSTGRES_P99], [item.name for item in outside])
            self.assertEqual(math.inf, largest.change)
            self.assertEqual(FROM_ZERO, module.describe(largest.change))

    def test_zero_to_zero_is_no_difference(self):  # US1-AS6
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            _, outside, _ = module.compare(*self.pair(tmp, first_p99=0.0))
            self.assertEqual(0.0, module.percent_change(0, 0))
            self.assertEqual([], outside)

    def test_describe_gives_one_decimal(self):  # US1-AS5
        self.assertEqual("25.0% apart", compare_module().describe(25.0))
        self.assertEqual("10.0% apart", compare_module().describe(10.04))

    def test_a_negative_baseline_uses_its_absolute_value(self):  # US2-AS6
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            set_load_figure(first, POSTGRES, P99, -100.0)
            set_load_figure(second, POSTGRES, P99, -110.0)
            _, outside, largest = module.compare(first, second)
            self.assertEqual([], outside)
            self.assertEqual(POSTGRES_P99, largest.name)
            self.assertAlmostEqual(10.0, largest.change)

    def test_a_value_that_is_not_a_finite_number_raises_run_error(self):  # US2-AS6
        module = compare_module()
        for bad in (float("nan"), "12", True):
            with self.subTest(value=bad), tempfile.TemporaryDirectory() as tmp:
                first, second = fake_pair(tmp)
                set_load_figure(second, POSTGRES, P99, bad)
                with self.assertRaises(module.RunError):
                    module.compare(first, second)

    def test_two_benchmarks_with_the_same_measurement_name_raise_run_error(self):  # US2-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            edit_report(first, split_first_benchmark)
            edit_report(second, split_first_benchmark)
            with self.assertRaises(module.RunError):
                module.compare(first, second)

    def test_a_schema_path_that_is_not_known_raises_run_error(self):  # US2-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            edit_report(first, use_an_unknown_schema_path)
            edit_report(second, use_an_unknown_schema_path)
            with self.assertRaises(module.RunError):
                module.compare(first, second)

    def test_two_load_manifests_for_the_same_engine_and_dataset_raise_run_error(self):  # US2-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            duplicate_load_manifest(first)
            duplicate_load_manifest(second)
            with self.assertRaises(module.RunError):
                module.compare(first, second)

    def test_a_figure_too_big_for_a_float_raises_run_error(self):  # US2-AS6
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            set_load_figure(second, POSTGRES, P99, HUGE_INTEGER)
            with self.assertRaises(module.RunError):
                module.compare(first, second)

    def test_a_null_parameters_raises_run_error(self):  # US2-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            edit_report(second, null_parameters)
            with self.assertRaises(module.RunError):
                module.compare(first, second)

    def test_an_empty_benchmarks_list_raises_run_error(self):  # US2-AS3
        module = compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = fake_pair(tmp)
            edit_report(first, clear_benchmarks)
            edit_report(second, clear_benchmarks)
            with self.assertRaises(module.RunError):
                module.compare(first, second)


class CompileManifestTests(unittest.TestCase):
    SCRIPT = ROOT / "perf" / "compile_manifest.py"

    def test_it_writes_machine_date_commit_versions_and_the_repeat_command(self):  # T5
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-I", str(self.SCRIPT), "--out", tmp, "--machine", "test-box", "--commit", "abc1234",
                                     "--dotnet-version", "10.0.100", "--benchmark-version", "BenchmarkDotNet 0.15.8"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = json.loads(Path(tmp, "manifest-compile.json").read_text(encoding="utf-8"))
            self.assertEqual({"machine", "date", "commit", "dotnet", "benchmark", "command"}, set(manifest))
            self.assertEqual("abc1234", manifest["commit"])
            self.assertEqual(f"bash scripts/perf-compile.sh {tmp}", manifest["command"])

    def test_a_missing_machine_label_is_exit_2(self):  # T5
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-I", str(self.SCRIPT), "--out", tmp], capture_output=True, text=True, timeout=30)
            self.assertEqual(2, result.returncode)
            self.assertIn("machine", result.stderr)


class CliTests(unittest.TestCase):
    def run_cli(self, root, results, *extra, cwd=None):
        page = root / "site" / "pages" / "performance.md"
        site_json = root / "site" / "site.json"
        site_json.parent.mkdir(parents=True, exist_ok=True)
        if not site_json.exists():
            site_json.write_text(json.dumps({"pages": [{"slug": "index"}]}), encoding="utf-8")
        args = [sys.executable, "-I", str(PAGE_SCRIPT), str(results), "--page", str(page), "--site-json", str(site_json),
                *extra]
        return subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=cwd), page, site_json

    def seed_site(self, root):
        """An earlier page and site config, which a refusal must leave as they are."""
        page = root / "site" / "pages" / "performance.md"
        site_json = root / "site" / "site.json"
        page.parent.mkdir(parents=True)
        page.write_text(OLD_PAGE, encoding="utf-8")
        site_json.write_text(OLD_SITE, encoding="utf-8")
        return page, site_json

    def test_every_broken_pair_is_refused_by_the_page_generator_and_the_existing_page_is_left_alone(self):  # US1-AS1 US1-AS2 US1-AS3 US1-AS4 US1-AS6 US1-AS7 US1-AS8 US1-AS10 US1-AS13
        for check, label, breaker in BREAKERS:
            with self.subTest(check=check, label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                first, second = fake_pair(tmp)
                first, second, cwd = breaker(first, second, root)
                page, site_json = self.seed_site(root)
                result, _, _ = self.run_cli(root, first, REPEAT_FLAG, str(second), cwd=cwd)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("", result.stdout)
                self.assertTrue(result.stderr.startswith(f"perf_page.py: {check}:"), result.stderr)
                self.assertEqual(OLD_PAGE, page.read_text(encoding="utf-8"))
                self.assertEqual(OLD_SITE, site_json.read_text(encoding="utf-8"))

    def test_a_real_repeat_writes_the_page(self):  # US1-AS5, AS9, AS11
        for label, prepare in ACCEPTANCES:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                first, second = fake_pair(tmp)
                prepare(first, second)
                result, page, _ = self.run_cli(root, first, REPEAT_FLAG, str(second))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn(SECTION, page.read_text(encoding="utf-8"))

    def test_the_cli_takes_the_repeat_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            repeat = write_repeat(root / "repeat")
            result, page, _ = self.run_cli(root, results, "--repeat", str(repeat))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("## Repeatability", page.read_text(encoding="utf-8"))

    def test_a_missing_repeat_folder_is_exit_2_with_the_reason_and_writes_nothing(self):  # US1-AS7
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            result, page, _ = self.run_cli(root, results, REPEAT_FLAG, str(root / "nowhere"))
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("nowhere", result.stderr)
            self.assertNotIn(TRACEBACK, result.stderr)
            self.assertFalse(page.exists())

    def test_a_repeat_folder_with_other_measurements_is_exit_2_with_the_reason_and_writes_nothing(self):  # US1-AS7
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            repeat = root / "perf" / "results" / "2026-11-20-repeat"
            import shutil
            shutil.copytree(results, repeat)
            edit_report(repeat, drop_a_benchmark)
            result, page, _ = self.run_cli(root, results, REPEAT_FLAG, str(repeat))
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("same measurements", result.stderr)
            self.assertNotIn(TRACEBACK, result.stderr)
            self.assertFalse(page.exists())

    def test_a_repeat_run_with_a_figure_too_big_for_a_float_is_exit_2_and_writes_nothing(self):  # US1-AS7
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            repeat = root / "perf" / "results" / "2026-11-20-repeat"
            shutil.copytree(results, repeat)
            set_load_figure(repeat, POSTGRES, P99, HUGE_INTEGER)
            result, page, _ = self.run_cli(root, results, REPEAT_FLAG, str(repeat))
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertNotIn(TRACEBACK, result.stderr)
            self.assertFalse(page.exists())

    def test_it_writes_the_page_and_registers_it_once(self):  # T4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            first, page, site_json = self.run_cli(root, results)
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertTrue(page.is_file())
            second, _, _ = self.run_cli(root, results)
            self.assertEqual(0, second.returncode, second.stderr)
            pages = json.loads(site_json.read_text(encoding="utf-8"))["pages"]
            self.assertEqual(1, [p["slug"] for p in pages].count("performance"))
            entry = next(p for p in pages if p["slug"] == "performance")
            self.assertEqual("site/pages/performance.md", entry["source"])
            self.assertTrue(entry["description"])

    def test_no_results_is_exit_2_and_writes_nothing(self):  # T4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "perf" / "results" / "2026-11-21"
            empty.mkdir(parents=True)
            result, page, _ = self.run_cli(root, empty)
            self.assertEqual(2, result.returncode)
            self.assertFalse(page.exists())

    def test_a_malformed_result_file_is_exit_2(self):  # T4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            (results / FIRST_LOAD_MANIFEST).write_text("{ not json", encoding="utf-8")
            result, page, _ = self.run_cli(root, results)
            self.assertEqual(2, result.returncode)
            self.assertFalse(page.exists())


if __name__ == "__main__":
    unittest.main()
