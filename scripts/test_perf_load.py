#!/usr/bin/env python3
"""Pins perf/load.py (task #3847, spec FR-18, FR-19, acceptance criteria AC-2 and AC-3 of story #3324): the load test of a demo API.

Offline: a fake demo on 127.0.0.1 (plain http, a thread) answers the rows route; nothing leaves the machine.
Contract of perf/load.py (exit 0 = the run finished and the oversized request was refused the way the demo refuses it,
1 = it finished but the oversized request was not handled, 2 = bad arguments):
  --engine <postgres|ef|mongo>   --base-url <url>   --concurrency <n>   --duration <seconds>   --dataset <label, e.g. 10k>
  --machine <label>   --engine-version <text>   --out <dir>   [--shapes a.json,b.json]   [--commit <sha>]   [--repeat-command <text>]
  [--warmup <seconds, default 5>]: requests sent before the measured period are discarded (the first requests are slower: connections, JIT)
  Posts the request bodies of examples/demo/smoke to <base-url>/api/<engine>/rows from <concurrency> threads for <duration>
  seconds; prints p50, p95, p99 (milliseconds) and requests per second; writes load-<engine>-<dataset>.jsonl (one line per request)
  and manifest-<engine>-<dataset>.json (machine, dataset, engine version, load, date, commit, the command that repeats the run) into <out>: one
  pair of files per run, so the runs of both engines and both sizes can share one folder.
  The oversized case posts bad-oversized-page.json once and expects 400 with error.kind "resource-limit-exceeded".
Run: python3 scripts/test_perf_load.py
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOAD = ROOT / "perf" / "load.py"
ABSOLUTE_PATH = "/an/absolute/path/the/scripts/must/refuse"


def load_module():
    spec = importlib.util.spec_from_file_location("perf_load", LOAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDemo(BaseHTTPRequestHandler):
    """server.oversized_status / server.oversized_kind script the answer to a page of 100000 rows; everything else is 200. server.rows_requests counts the others."""

    def log_message(self, *args):
        """Silences the request log."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if body.get("endRow", 0) >= 100000:
            status = self.server.oversized_status
            payload = {"error": {"kind": self.server.oversized_kind, "message": "too large"}} if status != 200 else {"rows": []}
        else:
            self.server.rows_requests += 1
            status, payload = 200, {"rows": [], "lastRow": 0}
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Demo:
    def __init__(self, oversized_status=400, oversized_kind="resource-limit-exceeded"):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDemo)
        self.server.oversized_status = oversized_status
        self.server.oversized_kind = oversized_kind
        self.server.rows_requests = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def run_load(base_url, out, extra=(), engine="postgres", concurrency="2", duration="0.5", warmup="0"):
    args = [sys.executable, "-I", str(LOAD), "--engine", engine, "--base-url", base_url, "--concurrency", concurrency,
            "--duration", duration, "--warmup", warmup, "--dataset", "10k", "--machine", "test-box", "--engine-version", "postgres 16.4",
            "--commit", "abc1234", "--out", str(out), *extra]
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


class PercentileTests(unittest.TestCase):
    """T1."""

    def test_nearest_rank_percentiles_of_one_to_one_hundred(self):
        load = load_module()
        values = list(range(100, 0, -1))  # unsorted on purpose
        self.assertEqual(50, load.percentile(values, 50))
        self.assertEqual(95, load.percentile(values, 95))
        self.assertEqual(99, load.percentile(values, 99))

    def test_one_value_is_every_percentile(self):
        load = load_module()
        self.assertEqual(7.5, load.percentile([7.5], 99))

    def test_no_values_is_an_error(self):
        load = load_module()
        with self.assertRaises(ValueError):
            load.percentile([], 50)


class RunTests(unittest.TestCase):
    def test_a_run_writes_the_raw_timings_and_a_manifest_with_every_field(self):  # T2
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            result = run_load(url, out)
            self.assertEqual(0, result.returncode, result.stderr)
            raw = Path(out, "load-postgres-10k.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertGreater(len(raw), 0)
            first = json.loads(raw[0])
            self.assertEqual({"shape", "status", "ms"}, set(first))
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            for key in ("machine", "dataset", "engine", "engine_version", "load", "date", "commit", "command", "summary", "oversized"):
                self.assertIn(key, manifest)
            self.assertEqual("abc1234", manifest["commit"])
            self.assertEqual("10k", manifest["dataset"])
            self.assertEqual({"concurrency": 2, "duration_seconds": 0.5, "warmup_seconds": 0.0}, manifest["load"])
            self.assertIn("perf/load.py", manifest["command"])
            self.assertIn("--dataset 10k", manifest["command"])
            for key in ("count", "errors", "p50_ms", "p95_ms", "p99_ms", "requests_per_second"):
                self.assertIn(key, manifest["summary"])
            self.assertIn("p99", result.stdout)

    def test_two_runs_in_one_folder_keep_their_own_manifests(self):  # T2
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            self.assertEqual(0, run_load(url, out, engine="postgres").returncode)
            self.assertEqual(0, run_load(url, out, engine="mongo").returncode)
            names = sorted(p.name for p in Path(out).iterdir())
            self.assertEqual(["load-mongo-10k.jsonl", "load-postgres-10k.jsonl", "manifest-mongo-10k.json", "manifest-postgres-10k.json"], names)

    def test_the_oversized_request_refused_with_the_expected_kind_is_handled(self):  # T3
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            result = run_load(url, out)
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            self.assertEqual({"handled": True, "status": 400, "kind": "resource-limit-exceeded"}, manifest["oversized"])
            self.assertEqual(0, result.returncode)

    def test_an_oversized_request_that_is_answered_200_is_a_failure(self):  # T3
        with Demo(oversized_status=200) as url, tempfile.TemporaryDirectory() as out:
            result = run_load(url, out)
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["oversized"]["handled"])
            self.assertEqual(1, result.returncode)
            self.assertIn("oversized", result.stdout.lower())

    def test_an_oversized_request_refused_with_another_kind_is_a_failure(self):  # T3
        with Demo(oversized_kind="invalid-page") as url, tempfile.TemporaryDirectory() as out:
            self.assertEqual(1, run_load(url, out).returncode)


class WarmupTests(unittest.TestCase):
    """Requests sent during the warm-up are not measured: not in the raw file, not in the summary."""

    def raw_count(self, out):
        return len(Path(out, "load-postgres-10k.jsonl").read_text(encoding="utf-8").splitlines())

    def test_warmup_requests_are_sent_but_not_recorded(self):
        with tempfile.TemporaryDirectory() as out:
            demo = Demo()
            with demo as url:
                result = run_load(url, out, warmup="0.6", duration="0.4")
                self.assertEqual(0, result.returncode, result.stderr)
                sent = demo.server.rows_requests
            recorded = self.raw_count(out)
            self.assertGreater(recorded, 0)
            self.assertGreater(sent, recorded * 1.5, f"{sent} requests were sent but {recorded} were recorded: the warm-up should be the larger part")
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            self.assertEqual(recorded, manifest["summary"]["count"])

    def test_without_a_warmup_every_request_is_recorded(self):
        with tempfile.TemporaryDirectory() as out:
            demo = Demo()
            with demo as url:
                run_load(url, out, warmup="0")
                sent = demo.server.rows_requests
            self.assertEqual(sent, self.raw_count(out))

    def test_the_manifest_records_the_warmup_length(self):
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            run_load(url, out, warmup="0.3")
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            self.assertEqual(0.3, manifest["load"]["warmup_seconds"])

    def test_the_default_warmup_is_five_seconds(self):
        load = load_module()
        args = load.parse(["--engine", "postgres", "--base-url", "http://x", "--concurrency", "1", "--duration", "1", "--dataset", "10k",
                           "--machine", "m", "--engine-version", "v", "--out", "o"])
        self.assertEqual(5.0, args.warmup)

    def test_a_negative_warmup_is_refused(self):
        with tempfile.TemporaryDirectory() as out:
            result = run_load("http://127.0.0.1:9", out, warmup="-1")
            self.assertEqual(2, result.returncode)
            self.assertIn("warmup", result.stderr)


class EfEngineTests(unittest.TestCase):
    """The demo serves PostgreSQL twice: through Dapper (route postgres) and through the EF Core adapter (route ef)."""

    def test_the_ef_route_is_loaded_and_keeps_its_own_files(self):
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            result = run_load(url, out, engine="ef")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(Path(out, "load-ef-10k.jsonl").is_file())
            manifest = json.loads(Path(out, "manifest-ef-10k.json").read_text(encoding="utf-8"))
            self.assertEqual("ef", manifest["engine"])


class RepeatCommandTests(unittest.TestCase):
    """FR-19: a reviewer repeats a run from the page alone, so the manifest records the command that does everything."""

    def test_the_given_repeat_command_is_what_the_manifest_records(self):
        with Demo() as url, tempfile.TemporaryDirectory() as out:
            run_load(url, out, extra=("--repeat-command", "PERF_MACHINE=vm bash scripts/perf-load.sh postgres 10k"))
            manifest = json.loads(Path(out, "manifest-postgres-10k.json").read_text(encoding="utf-8"))
            self.assertEqual("PERF_MACHINE=vm bash scripts/perf-load.sh postgres 10k", manifest["command"])


class ScriptGuardTests(unittest.TestCase):
    """The scripts refuse, before any docker or dotnet call, what would publish a private detail: a missing machine label (the
    host name would be written into public files) and an absolute output path (it carries a home directory)."""

    def run_script(self, script, args, env_extra):
        env = {"PATH": "/usr/bin:/bin"}
        env.update(env_extra)
        return subprocess.run(["bash", str(ROOT / "scripts" / script), *args], capture_output=True, text=True, timeout=30, env=env)

    def test_perf_load_requires_the_machine_label(self):
        result = self.run_script("perf-load.sh", ["postgres", "10k"], {})
        self.assertEqual(2, result.returncode)
        self.assertIn("PERF_MACHINE", result.stderr)

    def test_perf_load_accepts_the_ef_engine_name(self):
        result = self.run_script("perf-load.sh", ["ef", "10k"], {})
        self.assertEqual(2, result.returncode)
        self.assertIn("PERF_MACHINE", result.stderr)  # past the engine check, stopped by the next guard
        self.assertNotIn("usage:", result.stderr)

    def test_perf_load_refuses_an_absolute_output_path(self):
        result = self.run_script("perf-load.sh", ["postgres", "10k"], {"PERF_MACHINE": "box", "PERF_OUT": ABSOLUTE_PATH})
        self.assertEqual(2, result.returncode)
        self.assertIn("relative", result.stderr)

    def test_perf_compile_requires_the_machine_label(self):
        result = self.run_script("perf-compile.sh", [], {})
        self.assertEqual(2, result.returncode)
        self.assertIn("PERF_MACHINE", result.stderr)

    def test_perf_compile_refuses_an_absolute_output_path(self):
        result = self.run_script("perf-compile.sh", [ABSOLUTE_PATH], {"PERF_MACHINE": "box"})
        self.assertEqual(2, result.returncode)
        self.assertIn("relative", result.stderr)


class ArgumentTests(unittest.TestCase):
    """T4: exit 2 with a message on stderr, before any request."""

    def check(self, expected_word, **overrides):
        with tempfile.TemporaryDirectory() as out:
            result = run_load("http://127.0.0.1:9", out, **overrides)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn(expected_word, result.stderr)

    def test_zero_concurrency(self):
        self.check("concurrency", concurrency="0")

    def test_a_negative_duration(self):
        self.check("duration", duration="-1")

    def test_an_unknown_engine(self):
        self.check("engine", engine="oracle")

    def test_a_missing_engine_version(self):
        with tempfile.TemporaryDirectory() as out:
            args = [sys.executable, "-I", str(LOAD), "--engine", "postgres", "--base-url", "http://127.0.0.1:9", "--concurrency", "1",
                    "--duration", "1", "--dataset", "10k", "--machine", "m", "--out", out]
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            self.assertEqual(2, result.returncode)
            self.assertIn("engine-version", result.stderr)

    def test_an_unknown_shape_file(self):
        with tempfile.TemporaryDirectory() as out:
            result = run_load("http://127.0.0.1:9", out, extra=("--shapes", "no-such-shape.json"))
            self.assertEqual(2, result.returncode)
            self.assertIn("no-such-shape.json", result.stderr)


if __name__ == "__main__":
    unittest.main()
