#!/usr/bin/env python3
"""Pins scripts/perf_page.py, perf/compare.py and perf/compile_manifest.py (tasks #3849, #3848, spec FR-17, FR-19, FR-20, NFR-08,
acceptance criteria AC-4, AC-5 and AC-6 of story #3324): the performance page of the docs site and the comparison of two runs.

The page is generated from the raw results of a run (perf/results/<date>/): the compile benchmark's BenchmarkDotNet JSON and the
manifest-<engine>-<dataset>.json of each load run. So no number is typed by hand, and every number in a table is a link to the raw
file it came from (FR-20). Contract:
  python3 scripts/perf_page.py <results dir> [--page <file>] [--site-json <file>]
  writes the page (default site/pages/performance.md) and registers it in the site config once (slug "performance");
  exit 0 = written, 2 = no results or a malformed result file (nothing is written).
Run: python3 scripts/test_perf_page.py
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PAGE_SCRIPT = HERE / "perf_page.py"
COMPILE_JSON = "compile/results/Craticula.Benchmarks.CompileBenchmarks-report-full.json"


def load_module():
    spec = importlib.util.spec_from_file_location("perf_page", PAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_results(root, compile_mean=12345.6, slow=False):
    """Fake run: two compile benchmarks and two load manifests, laid out as perf/results/<date>/."""
    results = root / "perf" / "results" / "2026-11-20"
    (results / "compile" / "results").mkdir(parents=True)
    benchmarks = [
        {"Parameters": "Backend=postgres&Shape=plain-page", "Statistics": {"Mean": compile_mean}, "Memory": {"BytesAllocatedPerOperation": 7000}},
        {"Parameters": "Backend=mongo&Shape=deep-filter", "Statistics": {"Mean": 90000.0 if slow else 26600.0}, "Memory": {"BytesAllocatedPerOperation": 18000}},
    ]
    (results / COMPILE_JSON).write_text(json.dumps({"Benchmarks": benchmarks}), encoding="utf-8")
    (results / "compile" / "manifest-compile.json").write_text(json.dumps({
        "machine": "test-box", "date": "2026-11-20", "commit": "abc1234", "dotnet": "10.0.100", "benchmark": "BenchmarkDotNet 0.15.8",
        "command": "bash scripts/perf-compile.sh perf/results/2026-11-20/compile"}), encoding="utf-8")
    for engine, version in (("postgres", "PostgreSQL 16.4"), ("mongo", "MongoDB 7.0.14")):
        manifest = {
            "machine": "test-box", "platform": "Linux 6.8, 4 logical CPUs, Python 3.12", "dataset": "10k", "engine": engine,
            "engine_version": version, "load": {"concurrency": 8, "duration_seconds": 60}, "shapes": ["number-gt.json"],
            "date": "2026-11-20", "commit": "abc1234",
            "command": f"python3 perf/load.py --engine {engine} --dataset 10k --out perf/results/2026-11-20",
            "summary": {"count": 5000, "errors": 0, "requests_per_second": 83.33, "p50_ms": 8.5, "p95_ms": 15.6, "p99_ms": 21.2},
            "oversized": {"handled": True, "status": 400, "kind": "resource-limit-exceeded"},
        }
        (results / f"manifest-{engine}-10k.json").write_text(json.dumps(manifest), encoding="utf-8")
        (results / f"load-{engine}-10k.jsonl").write_text('{"shape": "number-gt.json", "status": 200, "ms": 8.5}\n', encoding="utf-8")
    return results


def table_rows(page):
    return [line for line in page.splitlines() if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line)]


class RenderTests(unittest.TestCase):
    def render(self, **kwargs):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root, **kwargs)
            page_path = root / "site" / "pages" / "performance.md"
            page = module.render(results, page_path.parent, root)
            return page, root, page_path.parent

    def test_every_number_in_a_table_is_a_link_to_a_raw_file_that_exists(self):  # T1
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = write_results(root)
            page_dir = root / "site" / "pages"
            page_dir.mkdir(parents=True)
            page = module.render(results, page_dir, root)
            measurement = re.compile(r"\d+(\.\d+)? (µs|ms|KiB|B|/s)")
            checked = 0
            for row in table_rows(page):
                for cell in [c.strip() for c in row.strip("|").split("|")]:
                    if not measurement.search(cell):
                        continue
                    match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", cell)
                    self.assertIsNotNone(match, f"a number without a link: {cell!r} in {row!r}")
                    self.assertTrue((page_dir / match.group(2)).resolve().is_file(), f"dead link {match.group(2)}")
                    checked += 1
            self.assertGreaterEqual(checked, 12)

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
        for expected in ("test-box", "10k", "PostgreSQL 16.4", "MongoDB 7.0.14", "8 threads", "60 seconds", "2026-11-20", "abc1234",
                         "python3 perf/load.py --engine postgres --dataset 10k"):
            self.assertIn(expected, page)

    def test_the_compile_run_states_machine_date_commit_and_the_repeat_command(self):  # T3
        page, _, _ = self.render()
        for expected in ("BenchmarkDotNet 0.15.8", ".NET 10.0.100", "bash scripts/perf-compile.sh perf/results/2026-11-20/compile"):
            self.assertIn(expected, page)

    def test_the_oversized_request_is_reported(self):  # T3
        page, _, _ = self.render()
        self.assertIn("resource-limit-exceeded", page)

    def test_the_page_follows_the_site_rules(self):  # T4
        page, _, _ = self.render()
        self.assertTrue(page.startswith("# Performance\n"))
        self.assertNotIn("—", page)  # no em dash chains
        self.assertLess(max(len(line) for line in page.splitlines() if line.startswith("## ")), 60)


class CompareTests(unittest.TestCase):
    """T6: perf/compare.py <first run> <second run> [--limit 10]: exit 0 = every metric of the second run is within the limit
    (percent, default 10, NFR-08) of the first, 1 = at least one is not (each is listed), 2 = a run is missing or unreadable."""
    SCRIPT = ROOT / "perf" / "compare.py"

    def run_compare(self, first, second, *extra):
        return subprocess.run([sys.executable, "-I", str(self.SCRIPT), str(first), str(second), *extra], capture_output=True, text=True, timeout=30)

    def scale(self, results, factor):
        """Multiplies the p50 and the compile means of a fake run by `factor`."""
        for path in results.glob("manifest-*-*.json"):
            if path.name == "manifest-compile.json":
                continue
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["summary"]["p50_ms"] *= factor
            path.write_text(json.dumps(manifest), encoding="utf-8")
        report = results / COMPILE_JSON
        data = json.loads(report.read_text(encoding="utf-8"))
        for benchmark in data["Benchmarks"]:
            benchmark["Statistics"]["Mean"] *= factor
        report.write_text(json.dumps(data), encoding="utf-8")

    def test_two_identical_runs_are_within_the_limit(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_results(Path(two))
            result = self.run_compare(a, b)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("within 10%", result.stdout)

    def test_a_change_below_the_limit_passes(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_results(Path(two))
            self.scale(b, 1.09)
            self.assertEqual(0, self.run_compare(a, b).returncode)

    def test_a_change_above_the_limit_fails_and_names_the_metric(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_results(Path(two))
            self.scale(b, 1.25)
            result = self.run_compare(a, b)
            self.assertEqual(1, result.returncode)
            self.assertIn("p50", result.stdout)
            self.assertIn("compile", result.stdout)
            self.assertIn("25.0%", result.stdout)

    def test_the_limit_can_be_changed(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_results(Path(two))
            self.scale(b, 1.25)
            self.assertEqual(0, self.run_compare(a, b, "--limit", "30").returncode)

    def test_a_run_whose_requests_all_failed_is_exit_2_not_exit_1(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a, b = write_results(Path(one)), write_results(Path(two))
            path = b / "manifest-postgres-10k.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["summary"]["p50_ms"] = None
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_compare(a, b)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("p50", result.stderr)

    def test_a_run_with_a_missing_folder_is_exit_2(self):
        with tempfile.TemporaryDirectory() as one:
            a = write_results(Path(one))
            self.assertEqual(2, self.run_compare(a, Path(one) / "nowhere").returncode)


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
    def run_cli(self, root, results, *extra):
        page = root / "site" / "pages" / "performance.md"
        site_json = root / "site" / "site.json"
        site_json.parent.mkdir(parents=True, exist_ok=True)
        if not site_json.exists():
            site_json.write_text(json.dumps({"pages": [{"slug": "index"}]}), encoding="utf-8")
        args = [sys.executable, "-I", str(PAGE_SCRIPT), str(results), "--page", str(page), "--site-json", str(site_json),
                "--repo-root", str(root), *extra]
        return subprocess.run(args, capture_output=True, text=True, timeout=60), page, site_json

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
            (results / "manifest-postgres-10k.json").write_text("{ not json", encoding="utf-8")
            result, page, _ = self.run_cli(root, results)
            self.assertEqual(2, result.returncode)
            self.assertFalse(page.exists())


if __name__ == "__main__":
    unittest.main()
