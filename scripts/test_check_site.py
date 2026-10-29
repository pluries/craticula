#!/usr/bin/env python3
"""Pins scripts/check-site.sh (task #3330, spec FR-06 to FR-08 and NFR-05): the live check of the public site.

Offline: a local stub on 127.0.0.1 (one plain HTTP port, one HTTPS port with a throw-away self-signed certificate made by
openssl) is scripted per test, and the script reaches it through CHECK_SITE_CONNECT_TO and CHECK_SITE_CURL_OPTS=--cacert.
Needs bash, curl, openssl, GNU date and Python 3.10; skips where one is missing.
Run: python3 scripts/test_check_site.py
"""
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check-site.sh"
PRIMARY = "craticula.pluries.dev"
REDIRECTORS = ("pluries.dev", "www.pluries.dev")
COOKIE_VALUE = "s3cr3t-cookie-value"


def _has_gnu_date():
    date = shutil.which("date")
    return bool(date) and subprocess.run([date, "-d", "@0", "+%s"], capture_output=True).returncode == 0


NEED_TOOLS = unittest.skipUnless(
    sys.version_info >= (3, 10) and all(shutil.which(t) for t in ("bash", "curl", "openssl")) and _has_gnu_date() and SCRIPT.exists(),
    "needs Python 3.10, bash, curl, openssl, GNU date and the script")


class Stub(BaseHTTPRequestHandler):
    """Behaviour is read from the server: server.mode, server.cookie, server.https_port."""

    def log_message(self, *args):
        """Silences the stub's request log."""

    def _target(self):
        return self.requestline.split()[1]   # self.path may collapse a leading //

    def _decide(self, host_header, path):
        mode = self.server.mode
        host = host_header.split(":")[0]
        base = f"https://{PRIMARY}:{self.server.https_port}"
        if host == PRIMARY and self.server.plain:
            return (301 if mode == "wrong301" else 308), self._open_path(path, base + ("/" if mode == "path_lost" else path))
        if host in REDIRECTORS:
            return (301 if mode == "wrong301" else 302), self._open_path(path, base + path)
        if host == PRIMARY:
            return 200, None
        if mode == "open_host":
            return 302, f"https://{host_header}{path}"
        return 404, None

    def _open_path(self, path, location):
        if self.server.mode == "open_path" and path[:2] in ("//", "/\\", "/h"):
            return path[1:] if path.startswith("/h") else path
        return location

    def _send(self, status, location):
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        if self.server.cookie:
            self.send_header("Set-Cookie", f"session={COOKIE_VALUE}; HttpOnly")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _answer(self):
        status, location = self._decide(self.headers.get("Host", ""), self._target())
        self._send(status, location)

    do_GET = do_HEAD = do_POST = _answer


def make_certificate(directory, days):
    cert, key = directory / f"cert{days}.pem", directory / f"key{days}.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", str(days), "-subj", f"/CN={PRIMARY}",
                    "-addext", f"subjectAltName=DNS:{PRIMARY},DNS:pluries.dev,DNS:www.pluries.dev",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    return cert, key


@NEED_TOOLS
class CheckSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.certs = {days: make_certificate(cls.tmp, days) for days in (90, 10)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def start(self, mode="good", cookie=False, days=90):
        cert, key = self.certs[days]
        plain = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        secure = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(cert), str(key))
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
        for server, is_plain in ((plain, True), (secure, False)):
            server.mode, server.cookie, server.plain = mode, cookie, is_plain
            server.https_port = secure.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.ports = (plain.server_address[1], secure.server_address[1])
        self.cert = cert
        return self.ports

    def run_script(self, path=None, **extra):
        http_port, https_port = self.ports
        mappings = [f"{h}:{p}:127.0.0.1:{p}" for h in (PRIMARY, *REDIRECTORS) for p in (http_port, https_port)]
        env = {k: v for k, v in os.environ.items() if not k.startswith("CHECK_SITE_")}
        env.update({"CHECK_SITE_HTTP_PORT": str(http_port), "CHECK_SITE_HTTPS_PORT": str(https_port),
                    "CHECK_SITE_CONNECT_TO": " ".join(mappings), "CHECK_SITE_CURL_OPTS": f"--cacert {self.cert}"})
        env.update(extra)
        if path is not None:
            env["PATH"] = path
        return subprocess.run([shutil.which("bash"), str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)

    def test_t1_everything_as_specified_exits_0(self):
        self.start()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)
        self.assertIn("all", result.stdout.splitlines()[-1])

    def test_t2_301_instead_of_302_exits_1_and_names_the_url(self):
        self.start(mode="wrong301")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"FAIL http://pluries\.dev:\d+/some/page.*expected status 302, got 301")
        self.assertRegex(result.stdout, r"FAIL http://craticula\.pluries\.dev:\d+/some/page.*expected status 308, got 301")

    def test_primary_http_redirect_keeps_the_path(self):
        self.start(mode="path_lost")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"FAIL http://craticula\.pluries\.dev:\d+/some/page\?a=1: expected Location")

    def test_t3_redirect_copying_the_host_header_is_an_open_redirect(self):
        self.start(mode="open_host")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("forged Host: evil.example", result.stdout)
        self.assertIn("open redirect, Location is https://evil.example", result.stdout)

    def test_t3_redirect_built_from_the_path_is_an_open_redirect(self):
        self.start(mode="open_path")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("(crafted path)", result.stdout)
        self.assertIn("open redirect", result.stdout)

    def test_t4_a_cookie_exits_1_and_its_value_is_never_printed(self):
        self.start(cookie=True)
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("sets a cookie", result.stdout)
        self.assertNotIn(COOKIE_VALUE, result.stdout + result.stderr)

    def test_t5_a_certificate_with_10_days_left_exits_1_and_names_the_days(self):
        self.start(days=10)
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"the certificate has (9|10) days left, more than 30 are required")
        self.assertEqual(self.run_script(CHECK_SITE_MIN_DAYS="5").returncode, 0)

    def _tools_without(self, missing):
        bin_dir = Path(tempfile.mkdtemp(dir=self.tmp))
        for name in ("openssl", "curl", "date", "grep", "sed", "tr", "mktemp", "rm", "cat", "head"):
            if name != missing and shutil.which(name):
                (bin_dir / name).symlink_to(shutil.which(name))
        return str(bin_dir)

    def test_t6_a_missing_curl_or_openssl_exits_2_with_a_message(self):
        self.start()
        for tool in ("curl", "openssl"):
            with self.subTest(tool=tool):
                result = self.run_script(path=self._tools_without(tool))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(f"{tool} is not installed", result.stderr)
                self.assertNotIn("passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
