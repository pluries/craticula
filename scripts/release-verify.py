#!/usr/bin/env python3
"""Verifies the ten signed Craticula packages before release (story #3321, spec FR-01 to FR-04, FR-33).
Usage: release-verify.py --version X.Y.Z --unsigned DIR --signed DIR --certificate FILE [--dotnet CMD] [--today YYYY-MM-DD]
Per package: signed by the certificate whose SHA-256 fingerprint is in the certificate file, timestamped, and equal to the
unsigned build apart from the signature entry. One report line per package on stdout.
Exit 0: all ten packages pass. 1: a check failed. 2: usage or environment error (messages on stderr).
Nothing here reads or prints a key, a one-time code or a token. The certificate file holds a public fingerprint, and the
environment that dotnet receives has every variable that looks like a secret removed."""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_smoke  # noqa: E402

PACKAGES = pack_smoke.PACKAGES
SIGNATURE_ENTRY = ".signature.p7s"
SECRET_NAME = re.compile(r"(?i)key|token|password|secret|otp|credential")
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
BREAK = re.compile(r"[\r\n]")
VERIFY_TIMEOUT_SECONDS = 120


class EnvironmentProblem(Exception):
    """A usage or environment error: exit 2."""


def printable(text):
    """A name from a file or a zip entry, safe for a one-line report."""
    return "".join(char if char.isprintable() else "?" for char in text)


def load_certificate(path, today):
    """Returns (sha256 fingerprint in lower case, valid-until date) or raises ValueError naming the problem (never echoing other fields)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError("certificate file not found")
    except (OSError, UnicodeDecodeError):
        raise ValueError("certificate file cannot be read")
    if not text.strip():
        raise ValueError("certificate file is empty: the maker fills in scripts/release-certificate.json after the signing probe")
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("certificate file is malformed JSON")
    if not isinstance(data, dict):
        raise ValueError("certificate file is malformed: a JSON object is expected")
    fingerprint = data.get("sha256")
    if not isinstance(fingerprint, str) or not SHA256_HEX.match(fingerprint):
        raise ValueError("certificate sha256 fingerprint is missing or not 64 hex characters")
    subject = data.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("certificate subject is missing")
    try:
        valid_until = datetime.date.fromisoformat(str(data.get("validUntil")))
    except ValueError:
        raise ValueError("certificate validUntil is missing or not an ISO date (YYYY-MM-DD)")
    if valid_until < today:
        raise ValueError(f"certificate expired on {valid_until.isoformat()}")
    return fingerprint.lower(), valid_until


def package_path(directory, package_id, version):
    """Returns the .nupkg path of a package in `directory`, or None when it is missing."""
    path = Path(directory) / f"{package_id}.{version}.nupkg"
    return path if path.is_file() else None


def read_entries(path):
    """name -> bytes of a zip; raises ValueError on a damaged zip or a duplicated entry name."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate entry names")
            return {name: archive.read(name) for name in names}
    except zipfile.BadZipFile:
        raise ValueError("not a readable zip")


def compare_content(unsigned_path, signed_path):
    """Returns a list of differences between the unsigned zip and the signed one minus `.signature.p7s`; empty when equal."""
    try:
        unsigned = read_entries(unsigned_path)
        signed = read_entries(signed_path)
    except ValueError as error:
        return [str(error)]
    differences = []
    if SIGNATURE_ENTRY not in signed:
        differences.append(f"no {SIGNATURE_ENTRY} entry")
    signed.pop(SIGNATURE_ENTRY, None)
    if SIGNATURE_ENTRY in unsigned:
        differences.append(f"the unsigned build holds a {SIGNATURE_ENTRY} entry")
    for name in sorted(unsigned.keys() - signed.keys()):
        differences.append(f"removed {printable(name)}")
    for name in sorted(signed.keys() - unsigned.keys()):
        differences.append(f"extra {printable(name)}")
    for name in sorted(unsigned.keys() & signed.keys()):
        if unsigned[name] != signed[name]:
            differences.append(f"changed {printable(name)}")
    return differences


def dotnet_environment():
    return {name: value for name, value in os.environ.items() if not SECRET_NAME.search(name)}


def verify_signature(dotnet, signed_path, fingerprint):
    """Returns (signature_ok, timestamp_ok, detail) from `dotnet nuget verify --all --certificate-fingerprint`."""
    target = str(signed_path)
    if target.startswith("-"):
        target = "./" + target
    command = [dotnet, "nuget", "verify", "--all", "--certificate-fingerprint", fingerprint, target]
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=dotnet_environment(), timeout=VERIFY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, False, "verify timed out"
    except OSError:
        raise EnvironmentProblem("dotnet could not be run")
    output = result.stdout + result.stderr
    codes = sorted(set(re.findall(r"NU\d{4}", output)))
    signature_ok = result.returncode == 0 and "NU3004" not in codes and "NU3034" not in codes
    timestamp_ok = "NU3027" not in codes
    return signature_ok, timestamp_ok, " ".join(codes)


def check_directory(path, label):
    if not Path(path).is_dir():
        raise EnvironmentProblem(f"{label} directory not found")
    for entry in Path(path).iterdir():
        if BREAK.search(entry.name):
            raise EnvironmentProblem(f"{label} directory holds a file name with a line break: {printable(entry.name)}")


def check_dotnet(dotnet):
    if shutil.which(dotnet) is None:
        raise EnvironmentProblem("dotnet not found: the .NET SDK is required to verify signatures")


def verify_package(package_id, args, fingerprint):
    """Returns (report line, passed)."""
    prefix = f"{package_id} {args.version}:"
    unsigned = package_path(args.unsigned, package_id, args.version)
    signed = package_path(args.signed, package_id, args.version)
    missing = [label for label, path in (("unsigned", unsigned), ("signed", signed)) if path is None]
    if missing:
        return f"{prefix} {' and '.join(missing)} package missing", False
    signature_ok, timestamp_ok, detail = verify_signature(args.dotnet, signed, fingerprint)
    differences = compare_content(unsigned, signed)
    parts = []
    if signature_ok:
        parts.append("signature OK")
        parts.append("timestamp OK" if timestamp_ok else f"timestamp FAIL ({detail})")
    else:
        parts.append(f"signature FAIL ({detail or 'verification failed'})")
        parts.append("timestamp not checked")
    if differences:
        parts.append("content FAIL (" + "; ".join(differences[:3]) + (f"; {len(differences) - 3} more" if len(differences) > 3 else "") + ")")
    else:
        parts.append("content OK")
    return f"{prefix} {', '.join(parts)}", signature_ok and timestamp_ok and not differences


def unexpected_packages(directory, version):
    expected = {f"{package_id}.{version}.nupkg" for package_id in PACKAGES}
    return sorted(entry.name for entry in Path(directory).glob("*.nupkg") if entry.name not in expected)


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="release-verify.py")
    parser.add_argument("--version", required=True)
    parser.add_argument("--unsigned", required=True)
    parser.add_argument("--signed", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--today")
    return parser.parse_args(argv)


def run(args):
    try:
        today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    except ValueError:
        raise EnvironmentProblem("--today must be an ISO date (YYYY-MM-DD)")
    try:
        fingerprint, _ = load_certificate(args.certificate, today)
    except ValueError as error:
        raise EnvironmentProblem(str(error))
    check_directory(args.unsigned, "unsigned")
    check_directory(args.signed, "signed")
    check_dotnet(args.dotnet)
    failures = 0
    for package_id in PACKAGES:
        line, passed = verify_package(package_id, args, fingerprint)
        print(line)
        failures += 0 if passed else 1
    for name in unexpected_packages(args.signed, args.version):
        print(f"unexpected package in the signed directory: {printable(name)}")
        failures += 1
    if failures:
        print(f"FAIL: {failures} problem(s); nothing may be pushed")
        return 1
    print(f"PASS: {len(PACKAGES)} packages verified")
    return 0


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except EnvironmentProblem as error:
        print(f"release-verify.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
