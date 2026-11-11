#!/usr/bin/env python3
"""Pins scripts/check-demos.sh and scripts/demo-watch.sh (task #3788, spec FR-11, FR-13, NFR-09, AC 1 to 5 and 9, amendment M2)
and the Jenkins job that runs the watch (jenkins/jobs/craticula-demo-watch.xml).

Offline: a fake demo on 127.0.0.1 (plain http, one port, a thread) is scripted per test.
Contract of check-demos.sh (exit 0 all checks passed, 1 at least one `FAIL <url>: <what>` line on stdout, 2 usage/environment):
  CHECK_DEMOS_TARGETS     space separated `<provider>=<base url>` (default: postgres=https://craticula-pg.pluries.dev
                          mongo=https://craticula-mongo.pluries.dev)
  CHECK_DEMOS_FLOOD       number of quick requests of the rate-limit check (default 70)
  CHECK_DEMOS_CURL_OPTS   extra curl options, space separated
  Per target: POST <base>/api/<provider>/rows with a small page answers 200 and a JSON body with "rows"; PUT and DELETE on that
  route answer 405; a page larger than the limit (endRow 100000) is rejected with a 4xx other than 429; FLOOD quick POSTs
  include at least one 429 (the second address is NOT checked live, M2); for an https base the certificate accepts TLS 1.2+ and
  the response carries Strict-Transport-Security (a FAIL line naming "Strict-Transport-Security" otherwise; skipped for http).
Contract of demo-watch.sh (exit 0 = no alert, 1 = alert): runs DEMO_WATCH_CHECK (a command line, default
  `bash scripts/check-demos.sh`); the consecutive failures are kept in the file $DEMO_WATCH_STATE_DIR/failures (a whole number);
  a failure adds one and exits 1 only when the count reaches DEMO_WATCH_THRESHOLD (default 3); a success resets the count to 0.
Run: python3 scripts/test_check_demos.py
"""
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECK = HERE / "check-demos.sh"
WATCH = HERE / "demo-watch.sh"
WATCH_JOB = ROOT / "jenkins" / "jobs" / "craticula-demo-watch.xml"
PUBLISH_SCRIPT = HERE / "publish-github.sh"
LIMIT = 60
NEED_TOOLS = unittest.skipUnless(shutil.which("bash") and shutil.which("curl"), "needs bash and curl")


class FakeDemo(BaseHTTPRequestHandler):
    """Behaviour is read from the server: server.delete_status, server.oversized_status, server.limit (None = never 429), server.counts."""

    def log_message(self, *args):
        """Silences the request log."""

    def _reply(self, status, body=b"{}", headers=()):
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        if getattr(self.server, "hsts", False):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        server = self.server
        server.counts[self.path] = server.counts.get(self.path, 0) + 1
        if server.limit is not None and server.counts[self.path] > server.limit:
            return self._reply(429, b'{"error":"rate limit"}', [("Retry-After", "30")])
        if request.get("endRow", 0) - request.get("startRow", 0) > 1000:
            return self._reply(server.oversized_status, b'{"error":"page too large"}')
        self._reply(200, json.dumps({"rows": [{"id": 1}], "lastRow": 1}).encode())

    def do_PUT(self):
        self._reply(405, b"{}", [("Allow", "POST")])

    def do_DELETE(self):
        self._reply(self.server.delete_status, b"{}")


@NEED_TOOLS
class CheckDemosTests(unittest.TestCase):
    def start(self, delete_status=405, oversized_status=400, limit=LIMIT):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDemo)
        server.delete_status, server.oversized_status, server.limit, server.counts = delete_status, oversized_status, limit, {}
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.server = server
        return f"http://127.0.0.1:{server.server_address[1]}"

    def run_script(self, base, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CHECK_DEMOS_")}
        env["CHECK_DEMOS_TARGETS"] = f"postgres={base} mongo={base}"
        env.update(extra)
        return subprocess.run(["bash", str(CHECK)], env=env, capture_output=True, text=True, timeout=120)

    def assert_exit(self, result, code):
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("not implemented", result.stderr)

    def test_t1_a_demo_that_behaves_exits_0(self):
        result = self.run_script(self.start())
        self.assert_exit(result, 0)
        self.assertNotIn("FAIL", result.stdout)
        self.assertIn("passed", result.stdout.splitlines()[-1])

    def test_t1_a_demo_answering_200_to_delete_exits_1_and_names_the_route(self):
        base = self.start(delete_status=200)
        result = self.run_script(base)
        self.assert_exit(result, 1)
        self.assertRegex(result.stdout, r"FAIL \S*/api/postgres/rows.*DELETE.*200")

    def test_t1_an_oversized_page_accepted_exits_1(self):
        result = self.run_script(self.start(oversized_status=200))
        self.assert_exit(result, 1)
        self.assertRegex(result.stdout, r"FAIL .*(page|oversized)")

    def test_t1_a_first_request_that_is_not_200_exits_1(self):
        result = self.run_script(self.start(limit=0))
        self.assert_exit(result, 1)
        self.assertRegex(result.stdout, r"FAIL \S*/api/postgres/rows.*expected 200")

    def test_t1_the_checks_target_both_providers(self):
        base = self.start()
        self.assert_exit(self.run_script(base), 0)
        self.assertIn("/api/postgres/rows", self.server.counts)
        self.assertIn("/api/mongo/rows", self.server.counts)

    def test_t2_a_demo_that_never_answers_429_after_the_flood_exits_1(self):
        result = self.run_script(self.start(limit=None))
        self.assert_exit(result, 1)
        self.assertRegex(result.stdout, r"FAIL .*429")

    def test_t2_a_demo_that_limits_after_the_flood_exits_0_and_the_flood_size_is_set_by_the_variable(self):
        base = self.start()
        self.assert_exit(self.run_script(base, CHECK_DEMOS_FLOOD="70"), 0)
        self.assertGreaterEqual(self.server.counts["/api/postgres/rows"], 70)

    def test_t2_a_flood_smaller_than_the_limit_finds_no_429_and_exits_1(self):
        result = self.run_script(self.start(), CHECK_DEMOS_FLOOD="5")
        self.assert_exit(result, 1)
        self.assertRegex(result.stdout, r"FAIL .*429")

    def test_an_unreachable_demo_exits_1_not_0(self):
        result = self.run_script("http://127.0.0.1:9")
        self.assert_exit(result, 1)
        self.assertIn("FAIL", result.stdout)

    def test_a_malformed_target_exits_2(self):
        result = self.run_script("", CHECK_DEMOS_TARGETS="no-equals-sign")
        self.assert_exit(result, 2)


@unittest.skipUnless(shutil.which("bash") and shutil.which("curl") and shutil.which("openssl"), "needs bash, curl and openssl")
class CheckDemosHstsTests(unittest.TestCase):
    """The https part (NFR-01, M4): a throw-away self-signed certificate for localhost, trusted through CHECK_DEMOS_CURL_OPTS."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.cert, cls.key = cls.tmp / "cert.pem", cls.tmp / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1", "-keyout", str(cls.key), "-out", str(cls.cert)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_https(self, hsts):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDemo)
        server.delete_status, server.oversized_status, server.limit, server.counts, server.hsts = 405, 400, LIMIT, {}, hsts
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(str(self.cert), str(self.key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"https://localhost:{server.server_address[1]}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("CHECK_DEMOS_")}
        env.update({"CHECK_DEMOS_TARGETS": f"postgres={base} mongo={base}", "CHECK_DEMOS_CURL_OPTS": f"--cacert {self.cert}"})
        result = subprocess.run(["bash", str(CHECK)], env=env, capture_output=True, text=True, timeout=120)
        self.assertNotIn("not implemented", result.stderr)
        return result

    def test_an_https_demo_with_hsts_exits_0(self):
        result = self.run_https(hsts=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_an_https_demo_without_a_strict_transport_security_header_exits_1(self):
        result = self.run_https(hsts=False)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"FAIL .*Strict-Transport-Security")


@NEED_TOOLS
class DemoWatchTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)

    def watch(self, check, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DEMO_WATCH_")}
        env.update({"DEMO_WATCH_STATE_DIR": str(self.state), "DEMO_WATCH_CHECK": check})
        env.update(extra)
        result = subprocess.run(["bash", str(WATCH)], env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn("not implemented", result.stderr)
        return result

    def count(self):
        return int((self.state / "failures").read_text().strip())

    def test_t3_one_failure_does_not_alert_and_is_counted(self):
        self.assertEqual(0, self.watch("false").returncode)
        self.assertEqual(1, self.count())

    def test_t3_two_failures_in_a_row_do_not_alert(self):
        self.assertEqual(0, self.watch("false").returncode)
        self.assertEqual(0, self.watch("false").returncode)
        self.assertEqual(2, self.count())

    def test_t3_three_failures_in_a_row_alert_with_exit_1(self):
        self.watch("false")
        self.watch("false")
        third = self.watch("false")
        self.assertEqual(1, third.returncode, third.stdout + third.stderr)
        self.assertEqual(3, self.count())

    def test_t3_a_success_resets_the_count(self):
        self.watch("false")
        self.watch("false")
        self.assertEqual(0, self.watch("true").returncode)
        self.assertEqual(0, self.count())
        self.assertEqual(0, self.watch("false").returncode)
        self.assertEqual(0, self.watch("false").returncode)
        self.assertEqual(2, self.count())

    def test_t3_the_threshold_is_a_setting(self):
        self.assertEqual(1, self.watch("false", DEMO_WATCH_THRESHOLD="1").returncode)

    def test_t3_a_missing_state_file_counts_as_zero(self):
        self.assertFalse((self.state / "failures").exists())
        self.assertEqual(0, self.watch("true").returncode)


@unittest.skipUnless(PUBLISH_SCRIPT.is_file(), "private repository only: scripts/publish-github.sh is absent (public mirror)")
class DemoWatchJobTests(unittest.TestCase):
    """RED until jenkins/jobs/craticula-demo-watch.xml exists (task #3788, gate file: the maker pushes it)."""

    def setUp(self):
        self.assertTrue(WATCH_JOB.is_file(), "jenkins/jobs/craticula-demo-watch.xml is missing from the private repository")
        self.text = WATCH_JOB.read_text(encoding="utf-8")
        self.root = ET.fromstring(self.text.split("?>", 1)[1] if self.text.startswith("<?xml") else self.text)

    def test_is_a_freestyle_or_pipeline_job_that_is_enabled(self):
        self.assertIn(self.root.tag, ("project", "flow-definition"))
        self.assertEqual(["false"], [e.text for e in self.root.iter("disabled")])

    def test_is_pinned_to_one_node_so_the_failure_count_is_not_split_across_agents(self):
        self.assertEqual(["false"], [e.text for e in self.root.iter("canRoam")], "canRoam must be false")
        nodes = [e.text for e in self.root.iter("assignedNode")]
        self.assertEqual(1, len(nodes), "one assignedNode (a node label the maker fills in)")
        self.assertTrue(nodes[0] and nodes[0].strip())

    def test_names_no_mail_address(self):
        self.assertNotRegex(self.text, r"(?<![\w.+-])(?!git@)[\w.+-]+@[\w-]+\.[\w.-]+")

    def test_runs_every_5_minutes_with_no_other_trigger(self):
        timers = list(self.root.iter("hudson.triggers.TimerTrigger"))
        self.assertEqual(["H/5 * * * *"], [t.findtext("spec") for t in timers])
        others = [t.tag for t in self.root.iter() if t.tag.endswith("Trigger") and t.tag != "hudson.triggers.TimerTrigger"]
        self.assertEqual([], others)

    def test_calls_the_watch_script_and_holds_no_credential_value(self):
        self.assertIn("scripts/demo-watch.sh", self.text)
        for literal in ("password", "token=", "BEGIN PRIVATE KEY"):
            self.assertNotIn(literal, self.text.lower().replace("passwordparameter", ""))


if __name__ == "__main__":
    unittest.main()
