#!/usr/bin/env python3
"""Pins scripts/site-watch.sh and the Jenkins job that runs it (story #3322, spec NFR-09: the maker is told when the certificate
the visitor sees has 14 days or less left).

Contract of site-watch.sh (exit 0 = no alert, 1 = alert, 2 = bad setting), the shape of demo-watch.sh: up to SITE_WATCH_THRESHOLD
attempts in one run, the first success ends it, only all failing attempts alert; on an alert the message names the failing check lines
and goes to SITE_WATCH_NOTIFY_URL (a secret: never printed). Each attempt runs check-site.sh with CHECK_SITE_EDGE_HTTPS=on and
CHECK_SITE_MIN_DAYS=14 unless the environment overrides them.
Run: python3 scripts/test_site_watch.py
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import test_check_demos as demos

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WATCH = HERE / "site-watch.sh"
WATCH_JOB = ROOT / "jenkins" / "jobs" / "craticula-site-watch.xml"
PUBLISH_SCRIPT = HERE / "publish-github.sh"
NEED_TOOLS = unittest.skipUnless(shutil.which("bash") and shutil.which("curl") and shutil.which("timeout"), "needs bash, curl and timeout")

CERT_FAIL = "FAIL https://site.example/: the certificate has 10 days left, more than 14 are required"


@NEED_TOOLS
class SiteWatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.counter = self.dir / "attempts"

    def watch(self, check, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SITE_WATCH_", "CHECK_SITE_"))}
        env.update({"SITE_WATCH_CHECK": check, "SITE_WATCH_INTERVAL_SECONDS": "0"})
        env.update(extra)
        result = subprocess.run(["bash", str(WATCH)], env=env, capture_output=True, text=True, timeout=60, cwd=self.dir)
        self.assertNotIn("not implemented", result.stderr)
        return result

    def counting(self, outcome):
        return f"echo x >> {self.counter}; {outcome}"

    def attempts(self):
        return len(self.counter.read_text().split()) if self.counter.exists() else 0

    notify_server = demos.DemoWatchTests.notify_server

    def test_all_pass_exits_0_and_posts_nothing(self):
        url, bodies = self.notify_server()
        result = self.watch(self.counting("true"), SITE_WATCH_NOTIFY_URL=url)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(1, self.attempts())
        self.assertEqual([], bodies)

    def test_one_failure_then_a_pass_exits_0_and_posts_nothing(self):
        url, bodies = self.notify_server()
        check = f"echo x >> {self.counter}; [ $(wc -l < {self.counter}) -ge 2 ]"
        self.assertEqual(0, self.watch(check, SITE_WATCH_NOTIFY_URL=url).returncode)
        self.assertEqual(2, self.attempts())
        self.assertEqual([], bodies)

    def test_three_failures_exit_1_and_post_one_discord_message(self):
        url, bodies = self.notify_server(path="/api/webhooks/1234567890/discord-secret-token")
        result = self.watch(self.counting(f"echo '{CERT_FAIL}'; false"), SITE_WATCH_NOTIFY_URL=url)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual(3, self.attempts())
        self.assertIn("ALERT", result.stdout)
        self.assertEqual(1, len(bodies))
        self.assertIn("application/json", self.notify_types[0])
        self.assertIn("craticula", json.loads(bodies[0])["content"].lower())

    def test_the_notify_url_never_appears_in_the_output(self):
        url, _ = self.notify_server(path="/api/webhooks/1234567890/discord-secret-token")
        result = self.watch("false", SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL=url)
        self.assertNotIn("discord-secret-token", result.stdout + result.stderr)
        self.assertNotIn(url, result.stdout + result.stderr)

    def test_a_plain_url_gets_plain_text(self):
        url, bodies = self.notify_server()
        self.watch("false", SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL=url)
        self.assertNotIn("application/json", self.notify_types[0])
        self.assertEqual(1, len(bodies))

    def test_the_certificate_days_failure_is_in_the_message_and_the_log(self):
        url, bodies = self.notify_server()
        check = f"echo 'FAIL https://other.example/: a redirect'; echo '{CERT_FAIL}'; echo 'PASS something'; false"
        result = self.watch(check, SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL=url)
        self.assertEqual(1, result.returncode)
        self.assertIn("10 days left", bodies[0])
        self.assertIn("a redirect", bodies[0])
        self.assertNotIn("PASS something", bodies[0])
        self.assertIn("10 days left", result.stdout)

    def test_the_message_is_capped_in_the_number_of_failing_lines(self):
        url, bodies = self.notify_server()
        check = "for i in 1 2 3 4 5 6 7 8; do echo \"FAIL line$i\"; done; false"
        self.watch(check, SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL=url)
        self.assertIn("line1", bodies[0])
        self.assertNotIn("line8", bodies[0])

    def test_a_failure_without_fail_lines_still_says_something(self):
        url, bodies = self.notify_server()
        self.watch("echo 'curl is missing'; false", SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL=url)
        self.assertIn("curl is missing", bodies[0])

    def test_the_check_runs_with_edge_https_on_and_14_days_by_default(self):
        check = f'echo "$CHECK_SITE_EDGE_HTTPS $CHECK_SITE_MIN_DAYS" >> {self.counter}; false'
        self.assertEqual(1, self.watch(check, SITE_WATCH_THRESHOLD="1").returncode)
        self.assertEqual(["on", "14"], self.counter.read_text().split())

    def test_both_check_settings_can_be_overridden_for_a_drill(self):
        check = f'echo "$CHECK_SITE_EDGE_HTTPS $CHECK_SITE_MIN_DAYS" >> {self.counter}; false'
        self.watch(check, SITE_WATCH_THRESHOLD="1", CHECK_SITE_MIN_DAYS="400", CHECK_SITE_EDGE_HTTPS="off")
        self.assertEqual(["off", "400"], self.counter.read_text().split())

    def test_the_default_check_is_check_site(self):
        text = WATCH.read_text(encoding="utf-8")
        self.assertIn("scripts/check-site.sh", text)

    def test_a_hanging_check_is_cut_and_counts_as_a_failure(self):
        result = self.watch("sleep 30", SITE_WATCH_THRESHOLD="1", SITE_WATCH_ATTEMPT_SECONDS="1")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)

    def test_an_unreachable_notify_url_keeps_exit_1_and_is_reported(self):
        result = self.watch("false", SITE_WATCH_THRESHOLD="1", SITE_WATCH_NOTIFY_URL="http://127.0.0.1:9/secret-topic")
        self.assertEqual(1, result.returncode)
        self.assertIn("notification", result.stdout + result.stderr)
        self.assertNotIn("secret-topic", result.stdout + result.stderr)

    def test_without_a_notify_url_an_alert_only_exits_1(self):
        result = self.watch("false", SITE_WATCH_THRESHOLD="1")
        self.assertEqual(1, result.returncode)
        self.assertNotIn("notification", result.stdout + result.stderr)

    def test_a_bad_setting_is_refused_with_exit_2(self):
        self.assertEqual(2, self.watch("true", SITE_WATCH_THRESHOLD="0").returncode)
        self.assertEqual(2, self.watch("true", SITE_WATCH_INTERVAL_SECONDS="soon").returncode)
        self.assertEqual(2, self.watch("true", SITE_WATCH_ATTEMPT_SECONDS="0").returncode)

    def test_it_keeps_no_state_between_runs(self):
        self.watch(self.counting("false"))
        self.assertEqual(1, self.watch(self.counting("false")).returncode)
        self.assertEqual(6, self.attempts())
        self.assertEqual([self.counter.name], sorted(p.name for p in self.dir.iterdir()))


@unittest.skipUnless(PUBLISH_SCRIPT.is_file(), "private repository only: scripts/publish-github.sh is absent (public mirror)")
class SiteWatchJobTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WATCH_JOB.is_file(), "jenkins/jobs/craticula-site-watch.xml is missing")
        self.text = WATCH_JOB.read_text(encoding="utf-8")
        self.root = ET.fromstring(self.text.split("?>", 1)[1] if self.text.startswith("<?xml") else self.text)

    def test_is_an_enabled_go_agent_job_that_never_runs_in_parallel(self):
        self.assertEqual("project", self.root.tag)
        self.assertEqual(["false"], [e.text for e in self.root.iter("disabled")])
        self.assertEqual(["false"], [e.text for e in self.root.iter("canRoam")])
        self.assertEqual(["go"], [e.text for e in self.root.iter("assignedNode")])
        self.assertEqual(["false"], [e.text for e in self.root.iter("concurrentBuild")])

    def test_runs_every_5_minutes_with_no_other_trigger(self):
        self.assertEqual(["H/5 * * * *"], [t.findtext("spec") for t in self.root.iter("hudson.triggers.TimerTrigger")])

    def test_calls_the_watch_script_and_binds_no_credential(self):
        self.assertIn("scripts/site-watch.sh", self.text)
        self.assertNotIn("SITE_WATCH_NOTIFY_URL", self.root.findtext("builders/hudson.tasks.Shell/command") or "")
        self.assertEqual(0, len(list(self.root.iter("org.jenkinsci.plugins.credentialsbinding.impl.SecretBuildWrapper"))))
        for literal in ("password", "token=", "BEGIN PRIVATE KEY"):
            self.assertNotIn(literal, self.text.lower())


if __name__ == "__main__":
    unittest.main()
