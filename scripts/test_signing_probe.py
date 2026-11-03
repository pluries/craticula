#!/usr/bin/env python3
"""Pins the signing probe (story #3320, spec FR-03 to FR-05, task #3478): the throwaway package and scripts/signing-probe.sh.
Fixtures: verify-signed.txt, verify-unsigned.txt are real `dotnet nuget verify` output (SDK 10.0.114, throwaway self-signed
certificate) EDITED (certificate PEM lines removed, the package path shortened); verify-unreadable.txt is hand-written;
verify-signed-synthetic-timestamp-block.txt and verify-signed-dmy-synthetic.txt are SYNTHETIC (invented): a later timestamping-service
block with another SHA256, and a validity line in d/M/yyyy form.
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

PROBE_DIR = ROOT / "tools" / "signing-probe"
CSPROJ = PROBE_DIR / "Craticula.SigningProbe.csproj"
SCRIPT = ROOT / "scripts" / "signing-probe.sh"
FIXTURES = ROOT / "scripts" / "signing-probe-fixtures"
SIGNED = FIXTURES / "verify-signed.txt"
UNSIGNED = FIXTURES / "verify-unsigned.txt"
UNREADABLE = FIXTURES / "verify-unreadable.txt"
SYNTHETIC = FIXTURES / "verify-signed-synthetic-timestamp-block.txt"
DMY = FIXTURES / "verify-signed-dmy-synthetic.txt"
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


def make_stub(directory, body):
    """A stub `dotnet` (bash) in `directory`; returns an environment with it first on PATH and no verify-output override."""
    stub = Path(directory) / "dotnet"
    stub.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "SIGNING_PROBE_VERIFY_OUTPUT"}
    env["PATH"] = f"{directory}{os.pathsep}{env['PATH']}"
    return env


def assert_probe_folder_untouched(case):
    # an SDK quoting bug turns a quote in --artifacts-path into a junk folder inside the project
    case.assertEqual(sorted(p.name for p in PROBE_DIR.iterdir()), ["Craticula.SigningProbe.csproj", "ProbeMarker.cs", "README.md"])


PACKING_STUB = """
while [ $# -gt 0 ]; do
  if [ "$1" = "--artifacts-path" ]; then dir="$2"; shift; fi
  shift
done
mkdir -p "$dir/package/release"
: > "$dir/package/release/Craticula.SigningProbe.0.0.1.nupkg"
"""


class ProjectLocationT1(unittest.TestCase):
    def test_T1_no_probe_project_anywhere_under_csharp(self):
        found = [str(p.relative_to(ROOT)) for p in (ROOT / "csharp").rglob(f"{PACKAGE_ID}.csproj")]
        self.assertEqual(found, [], "the license gate scans csharp/tools and needs a restored project there")

    def test_T1_probe_folder_is_at_the_repository_root(self):
        self.assertTrue(PROBE_DIR.is_dir(), f"missing {PROBE_DIR}")
        for name in ("Craticula.SigningProbe.csproj", "ProbeMarker.cs", "README.md"):
            self.assertTrue((PROBE_DIR / name).is_file(), f"missing {name}")


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
        # outside csharp/ no Directory.Build.props applies: the project sets these itself
        self.assertEqual(self.prop("TargetFramework"), "net10.0")
        # no build-machine PDB path in the dll, no private commit hash in the nuspec
        self.assertEqual(self.prop("DebugType"), "none")
        self.assertEqual(self.prop("EnableSourceControlManagerQueries"), "false")

    def test_T1_has_no_package_reference(self):
        self.assertEqual(list(self.root.iter("PackageReference")), [])

    def test_T1_is_not_in_the_solution_nor_the_pack_smoke(self):
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
        assert_probe_folder_untouched(self)


@unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK not on PATH")
class PackContentT2(unittest.TestCase):
    def test_T2_dll_carries_no_pdb_path_and_nuspec_no_repository_element(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["pack", str(Path(tmp) / "out")])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archive = zipfile.ZipFile(next((Path(tmp) / "out").glob("*.nupkg")))
            dll = archive.read(next(n for n in archive.namelist() if n.endswith(".dll")))
            self.assertNotIn(b".pdb", dll)
            self.assertNotIn(".pdb".encode("utf-16-le"), dll)
            nuspec = archive.read(next(n for n in archive.namelist() if n.endswith(".nuspec"))).decode("utf-8")
            self.assertNotIn("<repository", nuspec)
        assert_probe_folder_untouched(self)


class PackScriptDefectsT3(unittest.TestCase):
    def test_T3_failing_dotnet_with_a_quote_in_the_out_dir_deletes_nothing_and_leaves_no_build_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a").mkdir()
            (base / "a" / "important.txt").write_text("keep", encoding="utf-8")
            out = base / "a' 'x"
            (base / "stubs").mkdir()
            env = make_stub(base / "stubs", "exit 1")
            result = run(["pack", str(out)], env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((base / "a" / "important.txt").is_file(), "a sibling folder was deleted by the cleanup trap")
            self.assertEqual(list(base.rglob(".build.*")), [])

    @unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK not on PATH")
    def test_T3_real_pack_into_a_folder_with_an_apostrophe(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Chris's out"
            result = run(["pack", str(out)])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(list(out.glob("*.nupkg"))), 1)
            self.assertEqual(list(out.glob(".build.*")), [])
        assert_probe_folder_untouched(self)

    def test_T3_option_like_first_argument_exits_2_with_usage_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            stubs = Path(tmp) / "stubs"
            stubs.mkdir()
            work = Path(tmp) / "work"
            work.mkdir()
            env = make_stub(stubs, PACKING_STUB)
            result = subprocess.run(["bash", str(SCRIPT), "pack", "-x"], capture_output=True, text=True, env=env, cwd=work)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertRegex(result.stdout + result.stderr, r"(?i)usage")
            self.assertEqual(list(work.iterdir()), [])

    def test_T3_cdpath_does_not_redirect_the_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stubs, work, decoy = base / "stubs", base / "work", base / "decoy"
            for d in (stubs, work, decoy / "out"):
                d.mkdir(parents=True)
            env = make_stub(stubs, PACKING_STUB)
            env["CDPATH"] = str(decoy)
            result = subprocess.run(["bash", str(SCRIPT), "pack", "out"], capture_output=True, text=True, env=env, cwd=work)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([p.name for p in (work / "out").glob("*.nupkg")], ["Craticula.SigningProbe.0.0.1.nupkg"])
            self.assertEqual(list((decoy / "out").iterdir()), [])
            self.assertEqual(result.stdout.strip().splitlines()[-1], str((work / "out").resolve() / "Craticula.SigningProbe.0.0.1.nupkg"))

    def test_T3_verify_and_fingerprint_refuse_a_path_with_a_newline_or_carriage_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stubs = base / "stubs"
            stubs.mkdir()
            env = make_stub(stubs, f'cat "{SIGNED}"')
            for ch in ("\n", "\r"):
                nupkg = base / f"a{ch}b.nupkg"
                nupkg.write_bytes(b"x")
                for command in ("verify", "fingerprint"):
                    result = run([command, str(nupkg)], env=env)
                    self.assertEqual(result.returncode, 2, f"{command} {ch!r}: {result.stdout}{result.stderr}")
                    self.assertTrue(result.stderr.strip(), f"{command} {ch!r}: no message")


class FingerprintScriptDefectsT4(unittest.TestCase):
    def test_T4_dotnet_runs_with_the_invariant_culture(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stubs = base / "stubs"
            stubs.mkdir()
            env = make_stub(stubs, f'printf %s "${{DOTNET_SYSTEM_GLOBALIZATION_INVARIANT-unset}}" > "$(dirname "$0")/invariant.txt"\ncat "{SIGNED}"')
            env.pop("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", None)
            nupkg = base / "x.nupkg"
            nupkg.write_bytes(b"x")
            result = run(["fingerprint", str(nupkg)], env=env)
            self.assertEqual((stubs / "invariant.txt").read_text(encoding="utf-8"), "1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lines = result.stdout.splitlines()
            self.assertIn(f"sha256: {AUTHOR_SHA256}", lines)
            self.assertIn("valid until: 2027-12-06", lines)

    def test_T4_a_large_unsigned_output_prints_unsigned_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.txt"
            # the marker comes first: with it last, grep -q reads everything and no SIGPIPE reaches the writer
            big.write_text("error: NU3004: The package is not signed.\n" + ("x" * 79 + "\n") * 3800, encoding="utf-8")
            self.assertGreater(big.stat().st_size, 300_000)
            result = fingerprint(big)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("unsigned", result.stdout.splitlines())

    def test_T4_reading_the_override_file_is_announced_on_stderr(self):
        result = fingerprint(SIGNED)
        self.assertRegex(result.stderr, r"(?i)SIGNING_PROBE_VERIFY_OUTPUT")

    def test_T4_timestamped_follows_the_nu3027_warning(self):
        # heuristic: NU3027 is the SDK's "should be timestamped" warning; the real timestamped output is untested
        # until the maker's real signature
        self.assertIn("NU3027", SIGNED.read_text(encoding="utf-8"))
        self.assertNotIn("NU3027", SYNTHETIC.read_text(encoding="utf-8"))
        self.assertIn("timestamped: no", fingerprint(SIGNED).stdout.splitlines())
        self.assertIn("timestamped: yes", fingerprint(SYNTHETIC).stdout.splitlines())

    def test_T4_a_day_first_date_never_yields_a_wrong_iso_date(self):
        self.assertTrue(DMY.is_file(), f"missing {DMY}")
        result = fingerprint(DMY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"(?m)^valid from \(as printed\): 01/11/2026 15:18:01$")
        self.assertRegex(result.stdout, r"(?m)^valid until \(as printed\): 06/12/2027 15:18:01$")
        iso = [line for line in result.stdout.splitlines() if line.startswith("valid until: ")]
        self.assertIn(iso, ([], ["valid until: 2027-12-06"]))


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
