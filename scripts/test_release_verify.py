#!/usr/bin/env python3
"""Pins scripts/release-verify.py (story #3321, spec FR-01 to FR-04 and FR-33, task #3484, cases T1 to T7 of docs/feat/3484/plan.md).
The packages are tiny zips built here; `dotnet` is the synthetic scripts/release-verify-fixtures/dotnet-stub.py, behaviour per package
from a JSON sidecar. The certificate file has the FR-33 fields sha256, validUntil and subject. Fingerprints, certificates and markers are invented.
The script takes no date option: the fixtures expire in 2000 or in 2099.
Run: python3 scripts/test_release_verify.py
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pack_smoke  # noqa: E402

SCRIPT = ROOT / "scripts" / "release-verify.py"
FIXTURES = ROOT / "scripts" / "release-verify-fixtures"
STUB = FIXTURES / "dotnet-stub.py"
VALID = FIXTURES / "release-certificate.valid.json"
FINGERPRINT = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
VERSION = "1.0.0"
SECRET_MARKER = "SYNTHETIC-SECRET-MARKER-7731"
SIGNATURE = ".signature.p7s"


def entries(package_id):
    return {
        f"{package_id}.nuspec": f"<package><id>{package_id}</id><version>{VERSION}</version></package>".encode(),
        f"lib/net10.0/{package_id}.dll": b"MZ synthetic " + package_id.encode(),
        "[Content_Types].xml": b"<Types/>",
    }


def write_zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


class Workspace:
    """Ten unsigned and ten signed packages in a temp dir, a stub config, and a runner for the CLI."""

    def __init__(self, tmp, version=VERSION):
        self.base = Path(tmp)
        self.unsigned = self.base / "unsigned"
        self.signed = self.base / "signed"
        self.unsigned.mkdir()
        self.signed.mkdir()
        self.config_path = self.base / "stub.json"
        self.log = self.base / "dotnet.log"
        self.modes = {}
        for package_id in pack_smoke.PACKAGES:
            files = entries(package_id)
            write_zip(self.unsigned / f"{package_id}.{version}.nupkg", files)
            write_zip(self.signed / f"{package_id}.{version}.nupkg", {**files, SIGNATURE: b"synthetic signature " + package_id.encode()})

    def run(self, certificate=VALID, extra_env=None, dotnet=None, version=VERSION, signed=None, unsigned=None, extra_args=()):
        self.config_path.write_text(json.dumps({"expectedFingerprint": FINGERPRINT, "modes": self.modes, "default": "ok", "log": str(self.log)}), encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "RELEASE_VERIFY_STUB_CONFIG": str(self.config_path)}
        env.update(extra_env or {})
        args = [sys.executable, str(SCRIPT), "--version", version, "--unsigned", str(unsigned or self.unsigned), "--signed", str(signed or self.signed),
                "--certificate", str(certificate), "--dotnet", str(dotnet or STUB), *extra_args]
        return subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)

    def rewrite_signed(self, package_id, mutate):
        path = self.signed / f"{package_id}.{VERSION}.nupkg"
        with zipfile.ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        path.unlink()
        write_zip(path, mutate(files))


def make_certificate(directory, **overrides):
    fields = {"sha256": FINGERPRINT, "validUntil": "2099-12-31", "subject": "CN=Synthetic Test, O=Open Source Developer"}
    fields.update(overrides)
    path = Path(directory) / "certificate.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def patch_zip(path, flag_bits=0, method=None):
    """Rewrites the general-purpose flag and/or the compression method in every local and central header of a zip."""
    data = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = data.find(signature)
        while position != -1:
            flags = int.from_bytes(data[position + flag_offset:position + flag_offset + 2], "little") | flag_bits
            data[position + flag_offset:position + flag_offset + 2] = flags.to_bytes(2, "little")
            if method is not None:
                data[position + flag_offset + 2:position + flag_offset + 4] = method.to_bytes(2, "little")
            position = data.find(signature, position + 4)
    path.write_bytes(bytes(data))


def out(result):
    return result.stdout + result.stderr


class AllPassT1(unittest.TestCase):
    def test_T1_ten_matching_signed_packages_exit_0_with_one_line_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            result = ws.run()
            self.assertEqual(result.returncode, 0, out(result))
            lines = result.stdout.splitlines()
            for package_id in pack_smoke.PACKAGES:
                matching = [line for line in lines if line.startswith(f"{package_id} {VERSION}:")]
                self.assertEqual(len(matching), 1, f"{package_id}: {lines}")
                self.assertRegex(matching[0], r"signature OK")
                self.assertRegex(matching[0], r"timestamp OK")
                self.assertRegex(matching[0], r"content OK")

    def test_T1_the_ten_ids_are_the_pack_smoke_ones(self):
        self.assertEqual(len(pack_smoke.PACKAGES), 10)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            result = ws.run()
            self.assertEqual(result.returncode, 0, out(result))
            self.assertEqual(len([line for line in result.stdout.splitlines() if re.match(r"^Craticula\.\S+ ", line)]), 10)

    def test_T1_dotnet_is_called_per_signed_package_with_all_and_the_fingerprint_from_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            result = ws.run()
            self.assertEqual(result.returncode, 0, out(result))
            records = [json.loads(line) for line in ws.log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 10)
            for record in records:
                call = record["argv"]
                self.assertEqual(call[:3], ["nuget", "verify", "--all"])
                self.assertEqual(call[3:5], ["-v", "detailed"], call)
                self.assertEqual(record["invariant"], "1")
                self.assertEqual(call[call.index("--certificate-fingerprint") + 1], FINGERPRINT)
                self.assertTrue(Path(call[-1]).is_relative_to(ws.signed), call)


class SignatureT2T3T5(unittest.TestCase):
    def failing(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ws.modes["Craticula.Sql"] = mode
            return ws.run()

    def test_T2_an_unsigned_package_exits_1_naming_it_and_the_signature_check(self):
        result = self.failing("unsigned")
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Sql ")), "")
        self.assertRegex(line, r"(?i)signature FAIL|not signed|NU3004")

    def test_T2_the_other_nine_packages_are_still_reported(self):
        result = self.failing("unsigned")
        self.assertEqual(result.returncode, 1, out(result))
        reported = {l.split(" ")[0] for l in result.stdout.splitlines() if l.startswith("Craticula.")}
        self.assertEqual(reported, set(pack_smoke.PACKAGES))

    def test_T3_a_package_signed_by_another_certificate_exits_1(self):
        result = self.failing("wrong-fingerprint")
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Sql ")), "")
        self.assertRegex(line, r"(?i)signature FAIL|fingerprint|NU3034")

    def test_T5_a_package_without_a_timestamp_exits_1_naming_the_timestamp_check(self):
        result = self.failing("no-timestamp")
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Sql ")), "")
        self.assertIn("timestamp FAIL", line)

    def test_T5_a_package_whose_output_names_no_timestamp_at_all_fails_the_timestamp_check(self):
        result = self.failing("silent-no-timestamp")
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Sql ")), "")
        self.assertIn("timestamp FAIL", line)

    def test_T8_an_untrusted_root_exits_1_with_a_signature_failure(self):
        # characterization: already satisfied by the exit code of dotnet
        result = self.failing("untrusted-root")
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Sql ")), "")
        self.assertIn("signature FAIL", line)


class ContentT4(unittest.TestCase):
    def mutated(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ws.rewrite_signed("Craticula.Core", mutate)
            return ws.run()

    def assert_content_failure(self, result):
        self.assertEqual(result.returncode, 1, out(result))
        line = next((l for l in out(result).splitlines() if l.startswith("Craticula.Core ")), "")
        self.assertRegex(line, r"(?i)content (FAIL|mismatch)")

    def test_T4_a_changed_byte_is_a_content_mismatch(self):
        def flip(files):
            name = "lib/net10.0/Craticula.Core.dll"
            files[name] = files[name][:-1] + b"X"
            return files
        self.assert_content_failure(self.mutated(flip))

    def test_T4_an_extra_file_is_a_content_mismatch(self):
        self.assert_content_failure(self.mutated(lambda files: {**files, "lib/net10.0/extra.dll": b"extra"}))

    def test_T4_a_removed_file_is_a_content_mismatch(self):
        def drop(files):
            del files["[Content_Types].xml"]
            return files
        self.assert_content_failure(self.mutated(drop))

    def test_T4_a_signed_package_without_the_signature_entry_is_a_content_mismatch(self):
        def unsign(files):
            del files[SIGNATURE]
            return files
        self.assert_content_failure(self.mutated(unsign))


class InputsT6(unittest.TestCase):
    def test_T6_a_missing_package_exits_1_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.signed / f"Craticula.Mongo.{VERSION}.nupkg").unlink()
            result = ws.run()
            self.assertEqual(result.returncode, 1, out(result))
            self.assertRegex(out(result), r"(?i)Craticula\.Mongo.*missing|missing.*Craticula\.Mongo")

    def test_T6_a_missing_unsigned_package_exits_1_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.unsigned / f"Craticula.Search.{VERSION}.nupkg").unlink()
            result = ws.run()
            self.assertEqual(result.returncode, 1, out(result))
            self.assertRegex(out(result), r"(?i)Craticula\.Search.*missing|missing.*Craticula\.Search")

    def test_T6_a_package_of_another_version_counts_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, version="1.0.1")
            result = ws.run(version=VERSION)
            self.assertEqual(result.returncode, 1, out(result))
            self.assertRegex(out(result), r"(?i)missing")
            self.assertIn("Craticula.Sql", out(result))

    def test_T6_an_expired_certificate_file_exits_2_with_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=FIXTURES / "release-certificate.expired.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)expired")

    def test_T6_an_empty_certificate_file_exits_2_with_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=FIXTURES / "release-certificate.empty.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)empty")

    def test_T6_a_malformed_certificate_file_exits_2_with_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=FIXTURES / "release-certificate.malformed.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)malformed|invalid|parse|JSON")

    def test_T6_a_fingerprint_that_is_not_64_hex_characters_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=FIXTURES / "release-certificate.short-fingerprint.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)fingerprint")

    def test_T6_a_missing_certificate_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=Path(tmp) / "absent.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)certificate")

    def test_T6_a_missing_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(signed=Path(tmp) / "absent")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)signed|director")

    def test_T6_dotnet_not_found_exits_2_naming_dotnet(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(dotnet=Path(tmp) / "no-such-dotnet")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)dotnet")

    def test_T6_a_package_file_name_with_a_line_break_is_refused(self):
        for char in ("\n", "\r"):
            with self.subTest(char=repr(char)):
                with tempfile.TemporaryDirectory() as tmp:
                    ws = Workspace(tmp)
                    write_zip(ws.signed / f"Craticula.Sql.{VERSION}{char}x.nupkg", entries("Craticula.Sql"))
                    result = ws.run()
                    self.assertIn(result.returncode, (1, 2), out(result))
                    self.assertRegex(out(result), r"(?i)line break|newline|control character")


class SignedFolderS1(unittest.TestCase):
    def assert_unexpected(self, prepare):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            prepare(ws.signed)
            result = ws.run()
            self.assertEqual(result.returncode, 1, out(result))
            self.assertIn("unexpected", out(result).lower())

    def test_S1_a_snupkg_next_to_the_packages(self):
        self.assert_unexpected(lambda d: (d / f"Craticula.Sql.{VERSION}.snupkg").write_bytes(b"x"))

    def test_S1_an_upper_case_extension(self):
        self.assert_unexpected(lambda d: (d / f"Craticula.Sql.{VERSION}.NUPKG").write_bytes(b"x"))

    def test_S1_a_package_in_a_subdirectory(self):
        def prepare(d):
            (d / "sub").mkdir()
            (d / "sub" / f"Craticula.Sql.{VERSION}.nupkg").write_bytes(b"x")
        self.assert_unexpected(prepare)

    def test_S1_an_empty_subdirectory(self):
        self.assert_unexpected(lambda d: (d / "sub").mkdir())

    def test_S1_a_stray_text_file(self):
        self.assert_unexpected(lambda d: (d / "notes.txt").write_text("x", encoding="utf-8"))

    def test_S1_an_eleventh_well_formed_package(self):
        self.assert_unexpected(lambda d: write_zip(d / f"Craticula.Other.{VERSION}.nupkg", entries("Craticula.Other")))


class RobustnessT10T11N2(unittest.TestCase):
    def assert_core_fails_cleanly(self, result):
        self.assertEqual(result.returncode, 1, out(result))
        self.assertNotIn("Traceback", out(result))
        reported = {l.split(" ")[0] for l in result.stdout.splitlines() if l.startswith("Craticula.")}
        self.assertEqual(reported, set(pack_smoke.PACKAGES))
        line = next((l for l in result.stdout.splitlines() if l.startswith("Craticula.Core ")), "")
        self.assertIn("content FAIL", line)
        self.assertRegex(result.stdout, r"(?m)^FAIL")

    def test_T10_a_signed_zip_with_a_duplicated_entry_name_fails_the_content_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            path = ws.signed / f"Craticula.Core.{VERSION}.nupkg"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with zipfile.ZipFile(path, "a") as archive:
                    archive.writestr("lib/net10.0/Craticula.Core.dll", b"MZ synthetic Craticula.Core")
            result = ws.run()
            self.assert_core_fails_cleanly(result)
            self.assertRegex(result.stdout, r"(?i)duplicate")

    def test_T11_an_unsigned_package_that_holds_a_signature_entry_fails_the_content_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            path = ws.unsigned / f"Craticula.Core.{VERSION}.nupkg"
            write_zip(path, {**entries("Craticula.Core"), SIGNATURE: b"synthetic signature Craticula.Core"})
            self.assert_core_fails_cleanly(ws.run())

    def test_N2_a_signed_file_of_garbage_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.signed / f"Craticula.Core.{VERSION}.nupkg").write_bytes(b"this is not a zip " * 20)
            self.assert_core_fails_cleanly(ws.run())

    def test_N2_a_zip_entry_with_an_unsupported_compression_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            patch_zip(ws.signed / f"Craticula.Core.{VERSION}.nupkg", method=99)
            self.assert_core_fails_cleanly(ws.run())

    def test_N2_a_zip_entry_with_the_encrypted_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            patch_zip(ws.signed / f"Craticula.Core.{VERSION}.nupkg", flag_bits=0x1)
            self.assert_core_fails_cleanly(ws.run())


class CertificateAndVersionN1N3N4(unittest.TestCase):
    def test_N1_a_sha256_with_a_trailing_newline_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=make_certificate(tmp, sha256=FINGERPRINT + "\n"))
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)fingerprint")

    def test_N4_a_valid_until_without_dashes_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=make_certificate(tmp, validUntil="20991231"))
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)validUntil")

    def test_N3_a_version_that_is_not_semver_exits_2(self):
        for version in ("*", "1.0", "1.0.0/../x", "1.0.0 ", ""):
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as tmp:
                    result = Workspace(tmp).run(version=version)
                    self.assertEqual(result.returncode, 2, out(result))
                    self.assertRegex(out(result), r"(?i)version")

    def test_N3_a_version_with_build_metadata_or_a_leading_zero_prerelease_exits_2(self):
        # Spec change (#3485): the package file name drops build metadata, so the signed file would not be found; a
        # numeric prerelease identifier with a leading zero is not SemVer. Replaces the former "build metadata stays valid".
        for version in ("1.0.0-rc.1+build5", "1.0.0+build5", "1.0.0-rc.01"):
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as tmp:
                    result = Workspace(tmp).run(version=version)
                    self.assertEqual(result.returncode, 2, out(result))
                    self.assertRegex(out(result), r"(?i)version")

    def test_N3_a_prerelease_version_stays_valid(self):
        version = "1.0.0-rc.1"
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, version=version)
            result = ws.run(version=version)
            self.assertEqual(result.returncode, 0, out(result))

    def test_S3_the_today_option_no_longer_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(extra_args=("--today", "2026-01-01"))
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)unrecognized|unknown")


class ReportN5(unittest.TestCase):
    def test_N5_each_passing_line_carries_the_sha256_of_the_signed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            result = ws.run()
            self.assertEqual(result.returncode, 0, out(result))
            for package_id in pack_smoke.PACKAGES:
                digest = hashlib.sha256((ws.signed / f"{package_id}.{VERSION}.nupkg").read_bytes()).hexdigest()
                line = next(l for l in result.stdout.splitlines() if l.startswith(f"{package_id} {VERSION}:"))
                self.assertIn(f"sha256 {digest}", line)


class NoSecretsT7(unittest.TestCase):
    PATTERNS = {
        "PEM private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "literal certificate password": re.compile(r"--certificate-password[ =]+(?![\"']?\$)[^\s\"'$]+"),
        "long base64 blob": re.compile(r"[A-Za-z0-9+/=]{200,}"),
        "token or one-time code assignment": re.compile(r"(?i)\b(token|otp|one[-_ ]?time[-_ ]?code)\s*[=:]\s*[^\s$]"),
    }

    def test_T7_the_script_and_the_fixtures_hold_no_secret_material(self):
        files = [SCRIPT] + [p for p in FIXTURES.rglob("*") if p.is_file()]
        self.assertTrue(SCRIPT.is_file() and VALID.is_file())
        hits = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in self.PATTERNS.items():
                if pattern.search(text):
                    hits.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(hits, [])

    def test_T7_environment_secrets_never_reach_the_output(self):
        env = {"NUGET_API_KEY": SECRET_MARKER + "-KEY", "CERT_PASSWORD": SECRET_MARKER + "-PWD", "NUGET_TOKEN": SECRET_MARKER + "-TOK"}
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            success = ws.run(extra_env=env)
            self.assertEqual(success.returncode, 0, out(success))
            self.assertTrue(success.stdout.strip(), "a successful run prints its report lines")
            ws.modes["Craticula.Sql"] = "unsigned"
            failure = ws.run(extra_env=env)
            self.assertEqual(failure.returncode, 1, out(failure))
        for result in (success, failure):
            self.assertNotIn(SECRET_MARKER, out(result))

    def test_T7_extra_fields_of_the_certificate_file_are_never_echoed_in_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Workspace(tmp).run(certificate=FIXTURES / "release-certificate.expired.json")
            self.assertEqual(result.returncode, 2, out(result))
            self.assertRegex(out(result), r"(?i)expired")
            self.assertNotIn(SECRET_MARKER, out(result))


if __name__ == "__main__":
    unittest.main()
