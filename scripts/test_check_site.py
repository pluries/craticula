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
LANGUAGE_ENV = "CHECK_SITE_LANGUAGES"
LANG_VALUES = {"fr": "fr", "de": "de", "zh": "zh-Hans"}   # the url prefix and the `lang` value of each language (spec FR-001)
ACCEPT_GERMAN = "de"
UNKNOWN_PREFIX = "xx"
SEARCH_INDEX, LLMS, LLMS_FULL = "search-index.json", "llms.txt", "llms-full.txt"
NOSNIFF = ("X-Content-Type-Options", "nosniff")
REFERRER = ("Referrer-Policy", "strict-origin-when-cross-origin")
URL = r"https://craticula\.pluries\.dev:\d+"   # a live address as the script prints it against the stub


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
        host, target = self.headers.get("Host", ""), self._target()
        if host.split(":")[0] == PRIMARY and not self.server.plain and self.server.mode == "good":
            self._serve_site(target.split("?")[0])
            return
        status, location = self._decide(host, target)
        self._send(status, location)

    def _home(self, code, lang_value):
        """A home page: its lang, and the hreflang alternates of every language served (none while only English is served)."""
        base = f"https://{PRIMARY}:{self.server.https_port}"
        entries = [("en", "")] + [(LANG_VALUES[c], c + "/") for c in self.server.languages]
        links = "" if len(entries) < 2 or "no_hreflang" in self.server.defects else "".join(
            f'<link rel="alternate" hreflang="{lang}" href="{base}/{folder}index.html">' for lang, folder in entries)
        links += f'<link rel="alternate" hreflang="x-default" href="{base}/index.html">' if links else ""
        return f'<!doctype html><html lang="{lang_value}"><head>{links}</head><body></body></html>'

    def _lang_file(self, code, name):
        base = f"https://{PRIMARY}:{self.server.https_port}"
        if code == "en" or f"no_source_{name}" in self.server.defects:
            return "# Craticula\n"
        return f"# Craticula\n\nSource: {base}/{name}\n"

    def _site_routes(self, path, accept):
        """Returns (status, content type, body) for a path of the good site, or None when the stub has no such page."""
        defects, served = self.server.defects, self.server.languages
        if path in ("/", "/index.html"):
            if accept == ACCEPT_GERMAN and "negotiate_content" in defects:
                return 200, "text/html", self._home("de", "de")
            return 200, "text/html", self._home("en", "en")
        parts = path.strip("/").split("/", 1)
        code, rest = (parts[0], parts[1] if len(parts) > 1 else "") if parts[0] in (*served, UNKNOWN_PREFIX) else ("en", path.lstrip("/"))
        if code == UNKNOWN_PREFIX:
            return (200, "text/html", self._home("en", "en")) if "unknown_language_200" in defects else None
        if code != "en" and rest == "":
            return 200, "text/html", self._home(code, "en" if "wrong_lang" in defects else LANG_VALUES[code])
        missing = {SEARCH_INDEX: "no_search_index", LLMS: "no_llms", LLMS_FULL: "no_llms_full"}
        if rest in missing and not (code != "en" and missing[rest] in defects):
            return 200, "text/plain", "[]" if rest == SEARCH_INDEX else self._lang_file(code, rest)
        return None

    def _serve_site(self, path):
        """A site that behaves as the spec says; server.defects switches single faults on (read per test)."""
        accept = self.headers.get("Accept-Language", "")
        self.server.requests.append((path, accept))
        defects = self.server.defects
        found = self._site_routes(path, accept)
        if accept == ACCEPT_GERMAN and "redirect_negotiation" in defects and path == "/":
            self.send_response(302)
            self.send_header("Location", f"/{ACCEPT_GERMAN}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = (found[2] if found else "Not found\n").encode()
        self.send_response(found[0] if found else 404)
        self.send_header("Content-Type", found[1] if found else "text/plain")
        for header in (NOSNIFF, REFERRER):
            if not (header is NOSNIFF and "no_nosniff" in defects) and not (header is REFERRER and "no_referrer" in defects):
                self.send_header(*header)
        if "vary" in defects and path == "/":
            self.send_header("Vary", "Accept-Language")
        if accept and "language_cookie" in defects:
            self.send_header("Set-Cookie", f"lang={COOKIE_VALUE}; Path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

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

    def start(self, mode="good", cookie=False, days=90, languages=(), defects=()):
        cert, key = self.certs[days]
        plain = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        secure = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(cert), str(key))
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
        for server, is_plain in ((plain, True), (secure, False)):
            server.mode, server.cookie, server.plain = mode, cookie, is_plain
            server.languages, server.defects, server.requests = tuple(languages), set(defects), []
            server.https_port = secure.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.ports = (plain.server_address[1], secure.server_address[1])
        self.secure = secure
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

    # --- per-language live checks (spec 004, US4-AS1, US4-AS3, FR-016, FR-022) ---
    # Contract: CHECK_SITE_LANGUAGES = the enabled language codes, space separated, default empty (English only). English is always
    # checked; the Accept-Language, unknown-prefix and header checks run whatever the value.

    def _requested(self):
        return {path for path, _ in self.secure.requests}

    def test_US4_AS1_every_enabled_language_is_probed_and_a_good_site_exits_0(self):  # US4-AS1
        self.start(languages=("fr", "de", "zh"))
        result = self.run_script(**{LANGUAGE_ENV: "fr de zh"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)
        wanted = {f"/{c}/{name}" for c in LANG_VALUES for name in (SEARCH_INDEX, LLMS, LLMS_FULL)}
        wanted |= {f"/{c}/" for c in LANG_VALUES} | {"/", f"/{UNKNOWN_PREFIX}/", f"/{LLMS}", f"/{LLMS_FULL}", f"/{SEARCH_INDEX}"}
        self.assertEqual(wanted - self._requested(), set())

    def test_US4_AS1_without_languages_only_english_and_the_unknown_prefix_are_probed(self):  # US4-AS1
        self.start()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        requested = self._requested()
        self.assertTrue({"/", f"/{UNKNOWN_PREFIX}/", f"/{LLMS}"} <= requested, requested)
        self.assertFalse([p for p in requested if p.startswith(("/fr/", "/de/", "/zh/"))], requested)

    def test_US4_AS1_a_request_with_accept_language_de_is_sent_to_the_english_address(self):  # US4-AS1
        self.start(languages=("de",))
        self.run_script(**{LANGUAGE_ENV: "de"})
        self.assertIn(("/", ACCEPT_GERMAN), self.secure.requests)

    def test_US4_AS1_each_per_language_fault_exits_1_and_names_the_url(self):  # US4-AS1
        cases = (
            ("no_search_index", rf"FAIL {URL}/fr/search-index\.json: expected status 200, got 404"),
            ("no_llms", rf"FAIL {URL}/fr/llms\.txt: expected status 200, got 404"),
            ("no_llms_full", rf"FAIL {URL}/fr/llms-full\.txt: expected status 200, got 404"),
            ("wrong_lang", rf'FAIL {URL}/fr/: expected <html lang="fr">'),
            ("no_hreflang", rf"FAIL {URL}/fr/: missing hreflang link for fr"),
            ("unknown_language_200", rf"FAIL {URL}/xx/: expected status 404, got 200"),
            ("no_nosniff", rf"FAIL {URL}/: missing header X-Content-Type-Options: nosniff"),
            ("no_referrer", rf"FAIL {URL}/: missing header Referrer-Policy: strict-origin-when-cross-origin"),
        )
        for defect, pattern in cases:
            with self.subTest(defect=defect):
                self.start(languages=("fr",), defects=(defect,))
                result = self.run_script(**{LANGUAGE_ENV: "fr"})
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertRegex(result.stdout, pattern)

    def test_US4_AS1_a_chinese_home_must_carry_lang_zh_hans(self):  # US4-AS1
        self.start(languages=("zh",), defects=("wrong_lang",))
        result = self.run_script(**{LANGUAGE_ENV: "zh"})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, rf'FAIL {URL}/zh/: expected <html lang="zh-Hans">')

    def test_US4_AS1_accept_language_must_not_redirect_negotiate_vary_or_set_a_cookie(self):  # US4-AS1
        cases = (
            ("redirect_negotiation", r"\(Accept-Language: de\): expected status 200, got 302"),
            ("negotiate_content", r'\(Accept-Language: de\): expected <html lang="en">'),
            ("vary", r"\(Accept-Language: de\): the Vary header names Accept-Language"),
            ("language_cookie", r"sets a cookie"),
        )
        for defect, pattern in cases:
            with self.subTest(defect=defect):
                self.start(languages=("de",), defects=(defect,))
                result = self.run_script(**{LANGUAGE_ENV: "de"})
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertRegex(result.stdout, rf"FAIL {URL}/.*{pattern}")
                self.assertNotIn(COOKIE_VALUE, result.stdout + result.stderr)

    def test_US4_AS3_a_language_llms_file_must_name_the_english_source(self):  # US4-AS3
        for name in (LLMS, LLMS_FULL):
            with self.subTest(file=name):
                self.start(languages=("fr",), defects=(f"no_source_{name}",))
                result = self.run_script(**{LANGUAGE_ENV: "fr"})
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertRegex(result.stdout, rf"FAIL {URL}/fr/{name.replace('.', chr(92) + '.')}: does not name the English source {URL}/{name.replace('.', chr(92) + '.')}")

    def test_US4_AS1_a_bad_language_list_exits_2_and_names_the_variable(self):  # US4-AS1
        self.start()
        for value in ("en", "fr ../x", "FR", "fr;ls"):
            with self.subTest(value=value):
                result = self.run_script(**{LANGUAGE_ENV: value})
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(LANGUAGE_ENV, result.stderr)
                self.assertNotIn("passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
