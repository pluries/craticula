#!/usr/bin/env python3
"""Pins scripts/check-staged-packages.py (story #3706, task #3709; spec FR-36, NFR-04, ADR 0010): the check the publish job of the
workflow nuget-publish runs on the staged packages before it asks nuget.org for a key. It is release-verify.py without the unsigned
folder: the same signature, timestamp and certificate rules (not tested again here, see test_release_verify.py), plus the folder and
the hash list. The packages are tiny zips built here; `dotnet` is the synthetic scripts/release-verify-fixtures/dotnet-stub.py.
Run: python3 scripts/test_check_staged_packages.py

Contract pinned here:
  check-staged-packages.py --version V --dir DIR --sums FILE --certificate FILE [--dotnet CMD]
  Exit 0 all checks pass, 1 a check failed (nothing may be pushed), 2 a usage or environment error (a line on stderr that starts with
  `check-staged-packages.py: `). All problems are reported in one run. Output lines:
    `<id> <version>: signature OK, timestamp OK, sha256 OK, identity OK` per package that passes, and `PASS: 10 packages verified`;
    a failing package has a line that starts with `<id> <version>:` and holds `signature FAIL`, `timestamp FAIL`, `sha256 FAIL` or
    `identity FAIL (<short reason>)` (`package missing` for a missing file); a package with several failures is still one problem; `unexpected entry in the directory: <name>` for every extra entry; a line holding `sums`
    for every problem of the list itself (and naming the file name it is about); the last line `FAIL: <n> problem(s); nothing may be
    pushed`, n counting failing packages, extra entries and list problems.
  Identity: the zip holds exactly one `*.nuspec` at its root, parsed with xml.etree and read without regard to the XML namespace; its
  metadata id equals the expected id (case-insensitive) and its metadata version equals the expected version exactly. A missing, second or
  unparsable nuspec, a missing id or version, another id or version and an unreadable zip are `identity FAIL`.
  DIR holds exactly the ten <id>.<version>.nupkg of pack_smoke.PACKAGES. SUMS is in sha256sum format: ten lines `<64 lower-case hex>`,
  two spaces, the file name; exactly the ten names, none twice, each hash equal to the SHA-256 of DIR/<name>.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pack_smoke  # noqa: E402

SCRIPT = ROOT / "scripts" / "check-staged-packages.py"
FIXTURES = ROOT / "scripts" / "release-verify-fixtures"
STUB = FIXTURES / "dotnet-stub.py"
VALID = FIXTURES / "release-certificate.valid.json"
FINGERPRINT = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
OTHER_FINGERPRINT = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
VERSION = "1.0.0"
SECRET_MARKER = "SYNTHETIC-SECRET-MARKER-5512"
PACKAGES = list(pack_smoke.PACKAGES)
PASS_LINE = "signature OK, timestamp OK, sha256 OK, identity OK"
PASS_SUMMARY = "PASS: 10 packages verified"
ENV_ERROR = re.compile(r"(?m)^check-staged-packages\.py: ")


def final_line(count: int) -> str:
    return f"FAIL: {count} problem(s); nothing may be pushed"


def out(result) -> str:
    return result.stdout + result.stderr


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Staged:
    """Ten signed packages, their sums file, a stub config and a runner for the command line."""

    def __init__(self, tmp, version=VERSION):
        self.base = Path(tmp)
        self.version = version
        self.dir = self.base / "staged"
        self.dir.mkdir()
        self.sums = self.base / "SHA256SUMS.signed"
        self.config_path = self.base / "stub.json"
        self.log = self.base / "dotnet.log"
        self.modes = {}
        for package_id in PACKAGES:
            self.write_package(self.name(package_id), package_id)
        self.write_sums()

    def name(self, package_id, version=None):
        return f"{package_id}.{version or self.version}.nupkg"

    @staticmethod
    def nuspec(package_id, version, namespace=True, id_element=True, version_element=True):
        ns = ' xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"' if namespace else ""
        parts = (f"<id>{package_id}</id>" if id_element else "") + (f"<version>{version}</version>" if version_element else "")
        return f'<?xml version="1.0"?><package{ns}><metadata>{parts}</metadata></package>'.encode()

    def write_package(self, file_name, package_id, marker=b"", nuspecs=None):
        """A tiny zip: by default one root nuspec with the right id and version and a signature entry; `nuspecs` replaces the nuspec entries
        (a dict of entry name to bytes)."""
        entries = nuspecs if nuspecs is not None else {f"{package_id}.nuspec": self.nuspec(package_id, self.version)}
        with zipfile.ZipFile(self.dir / file_name, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
            archive.writestr(".signature.p7s", b"synthetic signature " + package_id.encode() + marker)

    def replace_package(self, package_id, **kwargs):
        """Rewrites a package and the list, so that only the identity (or the other thing the test changes) can fail."""
        self.write_package(self.name(package_id), package_id, **kwargs)
        self.write_sums()

    def sums_lines(self, names=None):
        return [f"{sha256((self.dir / name).read_bytes())}  {name}" for name in (names or [self.name(i) for i in PACKAGES])]

    def write_sums(self, lines=None, text=None):
        if text is not None:
            content = text
        else:
            chosen = self.sums_lines() if lines is None else lines
            content = "\n".join(chosen) + "\n"
        self.sums.write_text(content, encoding="utf-8")

    def alter(self, package_id):
        """Changes the package after the list was made."""
        self.write_package(self.name(package_id), package_id, marker=b" altered after the list")

    def run(self, certificate=VALID, extra_env=None, dotnet=None, version=None, directory=None, sums=None, drop=()):
        self.config_path.write_text(json.dumps({"expectedFingerprint": FINGERPRINT, "modes": self.modes, "default": "ok", "log": str(self.log)}), encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "RELEASE_VERIFY_STUB_CONFIG": str(self.config_path)}
        env.update(extra_env or {})
        args = [sys.executable, str(SCRIPT), "--version", self.version if version is None else version, "--dir", str(directory or self.dir), "--sums", str(sums or self.sums),
                "--certificate", str(certificate), "--dotnet", str(dotnet or STUB)]
        for flag in drop:
            index = args.index(flag)
            del args[index:index + 2]
        return subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)


def lines_of(result, package_id, version=VERSION):
    return [line for line in result.stdout.splitlines() if line.startswith(f"{package_id} {version}:")]


class AllPass(unittest.TestCase):
    def test_ten_matching_packages_exit_0_with_one_exact_line_each_and_the_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Staged(tmp).run()
            self.assertEqual(0, result.returncode, out(result))
            for package_id in PACKAGES:
                self.assertEqual([f"{package_id} {VERSION}: {PASS_LINE}"], lines_of(result, package_id))
            self.assertEqual(PASS_SUMMARY, result.stdout.splitlines()[-1])
            self.assertEqual(11, len(result.stdout.splitlines()))

    def test_a_pre_release_version_works_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Staged(tmp, version="1.1.0-rc.1").run()
            self.assertEqual(0, result.returncode, out(result))
            self.assertEqual(PASS_SUMMARY, result.stdout.splitlines()[-1])

    def test_dotnet_is_asked_once_per_package_with_all_and_the_fingerprint_of_the_certificate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            self.assertEqual(0, staged.run().returncode)
            calls = [json.loads(line) for line in staged.log.read_text().splitlines()]
            self.assertEqual(10, len(calls))
            for call in calls:
                self.assertEqual(["nuget", "verify"], call["argv"][:2])
                self.assertIn("--all", call["argv"])
                self.assertEqual(FINGERPRINT, call["argv"][call["argv"].index("--certificate-fingerprint") + 1])
            self.assertEqual(sorted(staged.name(i) for i in PACKAGES), sorted(Path(c["argv"][-1]).name for c in calls))

    def test_the_script_loads_release_verify_by_path_and_does_not_copy_its_checks(self):
        text = SCRIPT.read_text(encoding="utf-8") if SCRIPT.is_file() else ""
        self.assertIn("importlib", text)
        self.assertIn("release-verify.py", text)
        self.assertIn("release_verify", text)
        self.assertNotIn("def load_certificate", text)
        self.assertNotIn("def verify_signature", text)


class FolderChecks(unittest.TestCase):
    def test_an_extra_file_or_folder_fails_the_run_and_is_named(self):
        for entry in ("stray.txt", f"Craticula.Core.{VERSION}.snupkg", "subfolder"):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                staged = Staged(tmp)
                path = staged.dir / entry
                path.mkdir() if entry == "subfolder" else path.write_bytes(b"x")
                result = staged.run()
                self.assertEqual(1, result.returncode, out(result))
                self.assertIn(f"unexpected entry in the directory: {entry}", result.stdout)
                self.assertEqual(final_line(1), result.stdout.splitlines()[-1])
                self.assertEqual(10, len([line for line in result.stdout.splitlines() if PASS_LINE in line]))

    def test_a_missing_package_fails_the_run_and_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            (staged.dir / staged.name("Craticula.Mongo")).unlink()
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            self.assertRegex(out(result), r"(?i)Craticula\.Mongo.*missing|missing.*Craticula\.Mongo")
            self.assertRegex(result.stdout.splitlines()[-1], r"^FAIL: \d+ problem\(s\); nothing may be pushed$")

    def test_a_package_of_another_version_counts_as_missing_and_as_an_unexpected_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            (staged.dir / staged.name("Craticula.Sql")).rename(staged.dir / staged.name("Craticula.Sql", "9.9.9"))
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            self.assertIn("Craticula.Sql", out(result))
            self.assertIn(staged.name("Craticula.Sql", "9.9.9"), result.stdout)

    def test_a_missing_directory_is_an_environment_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            result = staged.run(directory=Path(tmp) / "absent")
            self.assertEqual(2, result.returncode, out(result))
            self.assertRegex(result.stderr, ENV_ERROR)
            self.assertRegex(result.stderr, r"(?i)director")


class SumsChecks(unittest.TestCase):
    def test_a_package_altered_after_the_list_was_made_fails_naming_it_and_the_other_nine_still_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.alter("Craticula.Export.Csv")
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            line = lines_of(result, "Craticula.Export.Csv")[0]
            self.assertIn("sha256 FAIL", line)
            self.assertNotIn(PASS_LINE, line)
            self.assertEqual(9, len([row for row in result.stdout.splitlines() if PASS_LINE in row]))
            self.assertEqual(final_line(1), result.stdout.splitlines()[-1])

    def test_a_list_that_is_not_exactly_the_ten_names_with_their_hashes_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            good = staged.sums_lines()
            first_hash, first_name = good[0].split("  ")
            cases = {
                "a malformed line": good[:9] + ["this is not a sums line"],
                "nine lines": good[:9],
                "eleven lines": good + [f"{sha256(b'x')}  Craticula.Extra.{VERSION}.nupkg"],
                "a name outside the ten": good[:9] + [f"{sha256(b'x')}  Craticula.Other.{VERSION}.nupkg"],
                "a name twice": good[:9] + [good[0]],
                "an upper-case hash": [good[0].replace(first_hash, first_hash.upper())] + good[1:],
                "a short hash": [f"{first_hash[:40]}  {first_name}"] + good[1:],
                "a single space": [f"{first_hash} {first_name}"] + good[1:],
                "a wrong hash": [f"{sha256(b'wrong')}  {first_name}"] + good[1:],
                "a path in the name": [f"{first_hash}  ./{first_name}"] + good[1:],
                "an empty list": [],
            }
            for name, lines in cases.items():
                with self.subTest(case=name):
                    staged.write_sums(lines=lines)
                    result = staged.run()
                    self.assertEqual(1, result.returncode, out(result))
                    self.assertRegex(result.stdout, r"(?i)sums|sha256 FAIL", "a list problem names the list, a wrong hash fails the package")
                    self.assertRegex(result.stdout.splitlines()[-1], r"^FAIL: \d+ problem\(s\); nothing may be pushed$")

    def test_the_problem_of_the_list_names_the_file_it_is_about(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            good = staged.sums_lines()
            cases = {"a name outside the ten": (good[:9] + [f"{sha256(b'x')}  Craticula.Other.{VERSION}.nupkg"], f"Craticula.Other.{VERSION}.nupkg"),
                     "a name missing": (good[1:], staged.name(PACKAGES[0])),
                     "a name twice": (good[:9] + [good[0]], good[0].split("  ")[1])}
            for name, (lines, named) in cases.items():
                with self.subTest(case=name):
                    staged.write_sums(lines=lines)
                    result = staged.run()
                    self.assertEqual(1, result.returncode, out(result))
                    self.assertTrue(any("sums" in row.lower() and named in row for row in result.stdout.splitlines()), result.stdout)

    def test_a_missing_or_unreadable_list_is_an_environment_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            missing = staged.run(sums=Path(tmp) / "absent")
            self.assertEqual(2, missing.returncode, out(missing))
            self.assertRegex(missing.stderr, ENV_ERROR)
            unreadable = staged.run(sums=staged.dir.parent / "staged")      # a folder where a file is expected
            self.assertEqual(2, unreadable.returncode, out(unreadable))
            self.assertRegex(unreadable.stderr, ENV_ERROR)


class SignatureChecks(unittest.TestCase):
    def test_each_signature_outcome_fails_the_run_names_the_package_and_ends_with_the_fail_line(self):
        cases = {"unsigned": "signature FAIL", "wrong-fingerprint": "signature FAIL", "untrusted-root": "signature FAIL", "no-timestamp": "timestamp FAIL",
                 "silent-no-timestamp": "timestamp FAIL"}
        for mode, words in cases.items():
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                staged = Staged(tmp)
                staged.modes["Craticula.Search"] = mode
                result = staged.run()
                self.assertEqual(1, result.returncode, out(result))
                line = lines_of(result, "Craticula.Search")[0]
                self.assertIn(words, line)
                self.assertNotIn(PASS_LINE, line)
                self.assertEqual(final_line(1), result.stdout.splitlines()[-1])
                self.assertEqual(9, len([row for row in result.stdout.splitlines() if PASS_LINE in row]))

    def test_a_fingerprint_that_is_not_the_signers_fails_every_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            certificate = Path(tmp) / "certificate.json"
            certificate.write_text(json.dumps({"sha256": OTHER_FINGERPRINT, "validUntil": "2099-12-31", "subject": "CN=Synthetic Test"}), encoding="utf-8")
            result = Staged(tmp).run(certificate=certificate)
            self.assertEqual(1, result.returncode, out(result))
            self.assertEqual(final_line(10), result.stdout.splitlines()[-1])

    def test_all_ten_problems_are_reported_in_one_run(self):
        modes = ["unsigned", "wrong-fingerprint", "untrusted-root", "no-timestamp", "silent-no-timestamp"] * 2
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.modes = dict(zip(PACKAGES, modes))
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            for package_id in PACKAGES:
                self.assertEqual(1, len(lines_of(result, package_id)), package_id)
                self.assertIn("FAIL", lines_of(result, package_id)[0])
            self.assertEqual(final_line(10), result.stdout.splitlines()[-1])

    def test_a_failing_package_never_hides_another_kind_of_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.modes["Craticula.Core"] = "unsigned"
            staged.alter("Craticula.Dapper")
            (staged.dir / "stray.txt").write_bytes(b"x")
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            self.assertIn("signature FAIL", lines_of(result, "Craticula.Core")[0])
            self.assertIn("sha256 FAIL", lines_of(result, "Craticula.Dapper")[0])
            self.assertIn("unexpected entry in the directory: stray.txt", result.stdout)
            self.assertEqual(final_line(3), result.stdout.splitlines()[-1])


class IdentityChecks(unittest.TestCase):
    """The package says what it is: the nuspec inside the zip names the expected id and version."""
    ID = "Craticula.Mongo"

    def failing(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.replace_package(self.ID, **kwargs)
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            line = lines_of(result, self.ID)[0]
            self.assertRegex(line, r"identity FAIL \(.+\)")
            self.assertNotIn("identity OK", line)
            self.assertEqual(9, len([row for row in result.stdout.splitlines() if PASS_LINE in row]))
            self.assertEqual(final_line(1), result.stdout.splitlines()[-1])
            return line

    def test_a_signed_package_whose_nuspec_says_another_version_fails_although_the_file_name_and_the_list_match(self):
        line = self.failing(nuspecs={f"{self.ID}.nuspec": Staged.nuspec(self.ID, "0.9.0")})
        self.assertIn("signature OK", line)
        self.assertIn("sha256 OK", line)

    def test_another_id_fails(self):
        self.failing(nuspecs={f"{self.ID}.nuspec": Staged.nuspec("Craticula.Other", VERSION)})

    def test_the_version_is_compared_exactly_but_the_id_is_not_case_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp, version="1.1.0-rc.1")
            staged.replace_package(self.ID, nuspecs={f"{self.ID}.nuspec": Staged.nuspec(self.ID.lower(), "1.1.0-rc.1")})
            result = staged.run()
            self.assertEqual(0, result.returncode, out(result))
            staged.replace_package(self.ID, nuspecs={f"{self.ID}.nuspec": Staged.nuspec(self.ID, "1.1.0-RC.1")})
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            self.assertIn("identity FAIL", lines_of(result, self.ID, "1.1.0-rc.1")[0])

    def test_no_nuspec_two_nuspecs_or_a_nuspec_that_is_not_at_the_root_fail(self):
        cases = {
            "no nuspec": {"readme.txt": b"x"},
            "two nuspecs": {f"{self.ID}.nuspec": Staged.nuspec(self.ID, VERSION), "second.nuspec": Staged.nuspec(self.ID, VERSION)},
            "only a nested nuspec": {f"sub/{self.ID}.nuspec": Staged.nuspec(self.ID, VERSION)},
        }
        for name, entries in cases.items():
            with self.subTest(case=name):
                self.failing(nuspecs=entries)

    def test_an_unparsable_nuspec_or_one_without_an_id_or_a_version_fails(self):
        cases = {
            "unparsable": b"<package><metadata><id>",
            "not xml": b"this is not xml at all",
            "no id": Staged.nuspec(self.ID, VERSION, id_element=False),
            "no version": Staged.nuspec(self.ID, VERSION, version_element=False),
            "an empty id": Staged.nuspec("", VERSION),
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.failing(nuspecs={f"{self.ID}.nuspec": data})

    def test_a_nuspec_without_a_namespace_is_read_like_one_with_a_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.replace_package(self.ID, nuspecs={f"{self.ID}.nuspec": Staged.nuspec(self.ID, VERSION, namespace=False)})
            result = staged.run()
            self.assertEqual(0, result.returncode, out(result))
            self.assertEqual(PASS_SUMMARY, result.stdout.splitlines()[-1])

    def test_a_zip_that_cannot_be_read_fails_the_identity_with_the_list_rewritten_to_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            (staged.dir / staged.name(self.ID)).write_bytes(b"this is not a zip file")
            staged.write_sums()
            result = staged.run()
            self.assertEqual(1, result.returncode, out(result))
            line = lines_of(result, self.ID)[0]
            self.assertRegex(line, r"identity FAIL \(.+\)")
            self.assertEqual(9, len([row for row in result.stdout.splitlines() if PASS_LINE in row]))
            self.assertEqual(final_line(1), result.stdout.splitlines()[-1])

    def test_a_package_with_a_signature_failure_and_a_wrong_identity_is_one_failing_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            staged.modes[self.ID] = "unsigned"
            staged.replace_package(self.ID, nuspecs={f"{self.ID}.nuspec": Staged.nuspec(self.ID, "0.9.0")})
            result = staged.run()
            line = lines_of(result, self.ID)[0]
            self.assertEqual(1, result.returncode, out(result))
            self.assertIn("signature FAIL", line)
            self.assertIn("identity FAIL", line)
            self.assertEqual(final_line(1), result.stdout.splitlines()[-1])


class InputsAndEnvironment(unittest.TestCase):
    def test_a_certificate_file_that_cannot_be_trusted_is_an_environment_error_with_release_verifys_message(self):
        cases = {"empty": r"(?i)empty", "expired": r"(?i)expired", "malformed": r"(?i)malformed|invalid|parse|JSON", "short-fingerprint": r"(?i)fingerprint"}
        for name, pattern in cases.items():
            with self.subTest(certificate=name), tempfile.TemporaryDirectory() as tmp:
                result = Staged(tmp).run(certificate=FIXTURES / f"release-certificate.{name}.json")
                self.assertEqual(2, result.returncode, out(result))
                self.assertRegex(result.stderr, ENV_ERROR)
                self.assertRegex(result.stderr, pattern)
                self.assertNotIn(SECRET_MARKER, out(result))

    def test_a_missing_certificate_file_is_an_environment_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Staged(tmp).run(certificate=Path(tmp) / "absent.json")
            self.assertEqual(2, result.returncode, out(result))
            self.assertRegex(result.stderr, ENV_ERROR)
            self.assertRegex(result.stderr, r"(?i)certificate")

    def test_a_version_that_is_not_semver_is_an_environment_error(self):
        for bad in ("1.2", "v1.0.0", "1.0.0+build", "01.0.0", "1.0.0-01", ""):
            with self.subTest(version=bad), tempfile.TemporaryDirectory() as tmp:
                result = Staged(tmp).run(version=bad)
                self.assertEqual(2, result.returncode, out(result))
                self.assertRegex(result.stderr, ENV_ERROR)
                self.assertRegex(result.stderr, r"(?i)version")

    def test_dotnet_that_cannot_be_found_is_an_environment_error_naming_dotnet(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Staged(tmp).run(dotnet=Path(tmp) / "no-such-dotnet")
            self.assertEqual(2, result.returncode, out(result))
            self.assertRegex(result.stderr, ENV_ERROR)
            self.assertRegex(result.stderr, r"(?i)dotnet")

    def test_a_missing_required_option_is_a_usage_error(self):
        for flag in ("--version", "--dir", "--sums", "--certificate"):
            with self.subTest(option=flag), tempfile.TemporaryDirectory() as tmp:
                result = Staged(tmp).run(drop=(flag,))
                self.assertEqual(2, result.returncode, out(result))
                self.assertIn(flag, result.stderr)
                self.assertIn("check-staged-packages.py", result.stderr)
                self.assertEqual("", result.stdout)

    def test_no_secret_looking_environment_variable_reaches_dotnet_or_the_output(self):
        secrets = {"NUGET_API_KEY": SECRET_MARKER + "-KEY", "CERT_PASSWORD": SECRET_MARKER + "-PWD", "NUGET_TOKEN": SECRET_MARKER + "-TOK", "GH_OTP": SECRET_MARKER + "-OTP"}
        with tempfile.TemporaryDirectory() as tmp:
            staged = Staged(tmp)
            dump = Path(tmp) / "dotnet-env.txt"
            wrapper = Path(tmp) / "dotnet-wrapper.sh"
            wrapper.write_text(f"#!/bin/sh\nenv >> '{dump}'\nexec '{sys.executable}' '{STUB}' \"$@\"\n")
            wrapper.chmod(0o755)
            success = staged.run(dotnet=wrapper, extra_env=secrets)
            staged.modes["Craticula.Sql"] = "unsigned"
            failure = staged.run(dotnet=wrapper, extra_env=secrets)
            self.assertEqual((0, 1), (success.returncode, failure.returncode), out(success) + out(failure))
            environment = dump.read_text(encoding="utf-8")
            self.assertIn("RELEASE_VERIFY_STUB_CONFIG=", environment, "the wrapper saw the environment dotnet gets")
            for name in secrets:
                self.assertNotIn(f"{name}=", environment)
            self.assertNotIn(SECRET_MARKER, environment)
            for result in (success, failure):
                self.assertNotIn(SECRET_MARKER, out(result))

    def test_the_script_and_the_fixtures_it_uses_hold_no_secret_material(self):
        text = SCRIPT.read_text(encoding="utf-8") if SCRIPT.is_file() else ""
        self.assertTrue(text, "scripts/check-staged-packages.py does not exist")
        for pattern in (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"(?i)\b(token|otp|password)\s*=\s*['\"][^'\"\s$]{6,}['\"]", r"[A-Za-z0-9+/=]{200,}"):
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
