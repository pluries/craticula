#!/usr/bin/env python3
"""Pins the redirect of pluries.dev and www.pluries.dev to the Craticula site (story #3322, spec FR-08, task #3328).

The ingress-nginx admission webhook of the cluster refuses a redirect annotation that carries $request_uri and every snippet
annotation, so the redirect lives in the site's own nginx (a second server block in deploy/site/nginx.conf) and the redirect
Ingress is a plain one that routes the two hosts to the same Service.
Static checks read deploy/site/nginx.conf and the GitOps manifest kept under docs/feat/3328/gitops (private: skipped where it is absent,
as in the public mirror). The live check runs the pinned nginx image of deploy/site/Dockerfile with that configuration and skips where
Docker or the image is unavailable.
Run: python3 scripts/test_site_redirect.py
"""
import re
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NGINX_CONF = ROOT / "deploy" / "site" / "nginx.conf"
DOCKERFILE = ROOT / "deploy" / "site" / "Dockerfile"
INGRESS = ROOT / "docs" / "feat" / "3328" / "gitops" / "cst" / "craticula-site" / "base" / "ingress-redirect.yaml"
PRIMARY = "craticula.pluries.dev"
REDIRECTORS = ("pluries.dev", "www.pluries.dev")


def _server_blocks(conf):
    """Top-level server { ... } blocks of the configuration, as text (brace counting; no braces in strings here)."""
    blocks, depth, start = [], 0, None
    for i, ch in enumerate(conf):
        if ch == "{":
            depth += 1
            if depth == 2 and re.search(r"server\s*$", conf[:i]):
                start = i
        elif ch == "}":
            if depth == 2 and start is not None:
                blocks.append(conf[start:i + 1])
                start = None
            depth -= 1
    return blocks


class NginxConfTests(unittest.TestCase):
    def setUp(self):
        self.conf = NGINX_CONF.read_text()
        self.blocks = _server_blocks(self.conf)

    def test_a_server_block_names_both_redirect_hosts_and_returns_302_with_the_request_uri(self):
        redirect = [b for b in self.blocks if all(h in b for h in REDIRECTORS)]
        self.assertEqual(len(redirect), 1, "exactly one server block for pluries.dev and www.pluries.dev")
        self.assertRegex(redirect[0], r"server_name\s+pluries\.dev\s+www\.pluries\.dev\s*;")
        self.assertRegex(redirect[0], r"return\s+302\s+https://" + re.escape(PRIMARY) + r"\$request_uri\s*;")

    def test_the_redirect_block_serves_no_content(self):
        redirect = [b for b in self.blocks if "return 302" in b][0]
        self.assertNotIn("root ", redirect)
        self.assertNotIn("try_files", redirect)

    def test_the_site_block_stays_the_default_server_and_does_not_redirect(self):
        site = [b for b in self.blocks if "return 302" not in b]
        self.assertEqual(len(site), 1)
        self.assertRegex(site[0], r"listen\s+8080\s+default_server\s*;")
        self.assertIn("try_files", site[0])


@unittest.skipUnless(INGRESS.exists(), "the GitOps manifest is private (docs/ is stripped from the mirror)")
class RedirectIngressTests(unittest.TestCase):
    def setUp(self):
        self.text = INGRESS.read_text()
        self.code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))

    def test_no_redirect_or_snippet_annotation(self):
        for forbidden in ("permanent-redirect", "temporal-redirect", "snippet", "request_uri"):
            self.assertNotIn(forbidden, self.code)

    def test_http_is_not_sent_to_https_first(self):
        self.assertIn('nginx.ingress.kubernetes.io/ssl-redirect: "false"', self.code)

    def test_both_hosts_route_to_the_site_service(self):
        for host in REDIRECTORS:
            self.assertRegex(self.code, r"host:\s+" + re.escape(host) + r"\s")
        self.assertRegex(self.code, r"name:\s+craticula-site\s")
        self.assertRegex(self.code, r"number:\s+80\b")
        self.assertIn("secretName: pluries-ingress-tls", self.code)


def _pinned_nginx_image():
    m = re.search(r"^FROM\s+(nginxinc/nginx-unprivileged@sha256:[0-9a-f]{64})", DOCKERFILE.read_text(), re.M)
    return m.group(1) if m else None


@unittest.skipUnless(shutil.which("docker"), "docker not installed")
class LiveRedirectTests(unittest.TestCase):
    port = 18083

    @classmethod
    def setUpClass(cls):
        image = _pinned_nginx_image()
        if not image:
            raise unittest.SkipTest("no pinned nginx image in the Dockerfile")
        cls.site = tempfile.mkdtemp(prefix="site-redirect-")
        Path(cls.site, "index.html").write_text("<h1>site</h1>\n")
        Path(cls.site).chmod(0o755)
        Path(cls.site, "index.html").chmod(0o644)
        run = subprocess.run(
            ["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{cls.port}:8080",
             "-v", f"{NGINX_CONF}:/etc/nginx/nginx.conf:ro", "-v", f"{cls.site}:/usr/share/nginx/html:ro", image],
            capture_output=True, text=True, timeout=300)
        if run.returncode != 0:
            shutil.rmtree(cls.site, ignore_errors=True)
            raise unittest.SkipTest("cannot start the pinned nginx image: " + run.stderr.strip()[:200])
        cls.cid = run.stdout.strip()
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "stop", "-t", "1", cls.cid], capture_output=True)
        shutil.rmtree(cls.site, ignore_errors=True)

    def _get(self, host, path):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers={"Host": host})
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, r.headers.get("Location"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location"), e.read()

    def test_redirect_hosts_answer_302_keeping_path_and_query(self):
        for host in REDIRECTORS:
            for path in ("/", "/docs/getting-started/?a=1&b=2"):
                status, location, _ = self._get(host, path)
                self.assertEqual((status, location), (302, f"https://{PRIMARY}{path}"), f"{host}{path}")

    def test_primary_host_still_serves_the_site(self):
        status, location, body = self._get(PRIMARY, "/")
        self.assertEqual((status, location), (200, None))
        self.assertIn(b"site", body)

    def test_unknown_path_on_the_primary_is_404(self):
        self.assertEqual(self._get(PRIMARY, "/nope")[0], 404)

    def test_an_unknown_host_gets_the_site_not_a_redirect(self):
        status, location, _ = self._get("unknown.example", "/")
        self.assertEqual((status, location), (200, None))


if __name__ == "__main__":
    unittest.main()
