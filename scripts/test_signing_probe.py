#!/usr/bin/env python3
"""Pins the signing probe (story #3320, spec FR-03 to FR-05, task #3478): the throwaway package and scripts/signing-probe.sh.
Fixtures are real `dotnet nuget verify` outputs (SDK 10.0.114, throwaway self-signed certificate) except
verify-signed-synthetic-timestamp-block.txt, which is SYNTHETIC: a later certificate block with another SHA256 follows the author block.
Run: python3 scripts/test_signing_probe.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pack_smoke  # noqa: E402

PROBE_DIR = ROOT / "csharp" / "tools" / "Craticula.SigningProbe"
CSPROJ = PROBE_DIR / "Craticula.SigningProbe.csproj"
SCRIPT = ROOT / "scripts" / "signing-probe.sh"
FIXTURES = ROOT / "scripts" / "signing-probe-fixtures"
SIGNED = FIXTURES / "verify-signed.txt"
UNSIGNED = FIXTURES / "verify-unsigned.txt"
UNREADABLE = FIXTURES / "verify-unreadable.txt"
SYNTHETIC = FIXTURES / "verify-signed-synthetic-timestamp-block.txt"
AUTHOR_SHA256 = "19FF9BE9E142B83BB41148D10D2DF62247AD0B772E9C44BF121ED09F7D12E538"
PACKAGE_ID = "Craticula.SigningProbe"


def run(args, env=None, timeout=300):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=timeout)


def fingerprint(fixture):
    with tempfile.TemporaryDirectory() as tmp:
        nupkg = Path(tmp) / "x.nupkg"
        nupkg.write_bytes(b"not a real package")
        env = dict(os.environ, SIGNING_PROBE_VERIFY_OUTPUT=str(fixture))
        return run(["fingerprint", str(nupkg)], env=env)


class ProjectFactsT1(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CSPROJ.is_file(), f"missing {CSPROJ}")
        self.root = ET.parse(CSPROJ).getroot()

    def prop(self, name):
        found = [e.text for e in self.root.iter(name)]
        return found[0] if found else None

    def test_T1_package_properties(self):
        self.assertEqual(self.prop("PackageId"), PACKAGE_ID)
        self.assertEqual(self.prop("IsPackable"), "true")
        self.assertRegex(self.prop("Version") or "", r"^\d+\.\d+\.\d+")
        self.assertEqual(self.prop("PackageLicenseExpression"), "Apache-2.0")
        self.assertEqual(self.prop("Description"), "Signing probe, not for use")

    def test_T1_has_no_package_reference(self):
        self.assertEqual(list(self.root.iter("PackageReference")), [])

    def test_T1_is_outside_src_and_the_solution_and_the_pack_smoke(self):
        self.assertTrue(CSPROJ.is_file(), f"missing {CSPROJ}")
        self.assertFalse((ROOT / "csharp" / "src" / PACKAGE_ID).exists())
        sln = (ROOT / "csharp" / "Craticula.sln").read_text(encoding="utf-8")
        self.assertNotIn("Craticula.SigningProbe", sln)
        self.assertNotIn(PACKAGE_ID, pack_smoke.PACKAGES)

    def test_T1_folder_holds_no_build_output_and_no_key_material(self):
        self.assertTrue(PROBE_DIR.is_dir(), f"missing {PROBE_DIR}")
        for d in ("bin", "obj"):
            self.assertFalse((PROBE_DIR / d).exists(), d)
        banned = {".pfx", ".p12", ".pem", ".key", ".snk", ".cer"}
        bad = [p for p in PROBE_DIR.rglob("*") if p.suffix.lower() in banned]
        self.assertEqual(bad, [])


@unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK not on PATH")
class PackT2(unittest.TestCase):
    def test_T2_pack_writes_one_unsigned_nupkg_and_leaves_no_bin_obj(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = run(["pack", str(out)])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            nupkgs = sorted(p.name for p in out.glob("*.nupkg"))
            self.assertEqual(len(nupkgs), 1, nupkgs)
            self.assertRegex(nupkgs[0], r"^Craticula\.SigningProbe\.\d+\.\d+\.\d+.*\.nupkg$")
            self.assertEqual([p.name for p in out.iterdir()], nupkgs, "temporary subfolder must be removed")
            self.assertIn(nupkgs[0], result.stdout)
            names = zipfile.ZipFile(out / nupkgs[0]).namelist()
            self.assertFalse([n for n in names if n.endswith(".signature.p7s")])
            self.assertTrue([n for n in names if n.endswith(".nuspec")])
            self.assertTrue([n for n in names if re.match(r"lib/net10\.0/.+\.dll$", n)])
            self.assertTrue([n for n in names if n.lower() == "readme.md"])
            allowed = re.compile(r"(\.nuspec$|^lib/net10\.0/.+\.dll$|^readme\.md$|^\[Content_Types\]\.xml$|^_rels/|^package/)", re.I)
            self.assertEqual([n for n in names if not allowed.search(n)], [])
        for d in ("bin", "obj"):
            self.assertFalse((PROBE_DIR / d).exists(), f"{d} left in the project folder")


class PackErrorsT3(unittest.TestCase):
    def test_T3_pack_without_argument_exits_2_with_usage(self):
        result = run(["pack"])
        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stdout + result.stderr, r"(?i)usage")

    def test_T3_pack_without_dotnet_exits_2_naming_the_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            for tool in ("bash", "dirname", "basename", "mkdir", "mv", "rm", "ls", "cat", "grep", "sed", "awk", "head", "tr",
                         "mktemp", "readlink", "find", "env", "printf", "echo", "date", "wc", "sort", "cut"):
                found = shutil.which(tool)
                if found:
                    (bin_dir / tool).symlink_to(found)
            env = {"PATH": str(bin_dir), "HOME": tmp}
            result = subprocess.run([str(bin_dir / "bash"), str(SCRIPT), "pack", str(Path(tmp) / "out")],
                                    capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertRegex(result.stdout + result.stderr, r"(?i)\.net sdk")


class FingerprintT4(unittest.TestCase):
    def test_T4_signed_fixture_prints_signer_hash_and_dates(self):
        result = fingerprint(SIGNED)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("signer: O=throwaway test, CN=Scratch Open Source Developer", lines)
        self.assertIn(f"sha256: {AUTHOR_SHA256}", lines)
        self.assertRegex(result.stdout, r"(?m)^valid from \(as printed\): 11/1/2026 3:18:01\s?PM$")
        self.assertRegex(result.stdout, r"(?m)^valid until \(as printed\): 12/6/2027 3:18:01\s?PM$")
        self.assertIn("valid until: 2027-12-06", lines)

    def test_T4_unsigned_fixture_prints_unsigned_and_exits_1(self):
        result = fingerprint(UNSIGNED)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unsigned", result.stdout.splitlines())

    def test_T4_unreadable_fixture_exits_2_with_raw_lines(self):
        result = fingerprint(UNREADABLE)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("this is not the output of dotnet nuget verify", result.stdout + result.stderr)

    def test_T4_the_author_block_wins_over_a_later_certificate_block(self):
        self.assertTrue(SYNTHETIC.is_file(), f"missing {SYNTHETIC}")
        result = fingerprint(SYNTHETIC)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"sha256: {AUTHOR_SHA256}", result.stdout.splitlines())
        self.assertNotIn("A" * 64, result.stdout)
        self.assertIn("valid until: 2027-12-06", result.stdout.splitlines())

    def test_T4_verify_with_a_missing_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["verify", str(Path(tmp) / "absent.nupkg")])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


class NoSecretsT5(unittest.TestCase):
    PATTERNS = {
        "PEM private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "literal certificate password": re.compile(r"--certificate-password[ =]+(?![\"']?\$)[^\s\"'$]+"),
        "long base64 blob": re.compile(r"[A-Za-z0-9+/=]{200,}"),
        "token or one-time code assignment": re.compile(r"(?i)\b(token|otp|one[-_ ]?time[-_ ]?code)\s*[=:]\s*[^\s$]"),
    }

    def test_T5_no_secret_material_in_the_probe_files(self):
        files = [SCRIPT] + [p for p in FIXTURES.rglob("*") if p.is_file()]
        if PROBE_DIR.is_dir():
            files += [p for p in PROBE_DIR.rglob("*") if p.is_file()]
        self.assertTrue(SCRIPT.is_file() and SIGNED.is_file())
        hits = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in self.PATTERNS.items():
                if pattern.search(text):
                    hits.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
