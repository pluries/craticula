#!/usr/bin/env python3
"""Checks the staged Craticula packages before the workflow nuget-publish asks nuget.org for a key (story #3706, spec FR-36, NFR-04, ADR 0010).
Usage: check-staged-packages.py --version X.Y.Z --dir DIR --sums FILE --certificate FILE [--dotnet CMD]
DIR holds exactly the ten packages of the version. SUMS is the list `SHA256SUMS.signed` in sha256sum format: ten lines, a lower-case SHA-256, two
spaces, the file name, exactly the ten names, each hash equal to the real hash of the file. Every package must carry a signature of the certificate
whose fingerprint is in the certificate file, with a timestamp (the same rules as release-verify.py, whose functions this script loads), and
the id and the version in its nuspec must be those of its file name.
One report line per package on stdout, then one line per extra entry and per problem of the list, then PASS or FAIL. All problems are reported in one run.
Exit 0: all ten packages pass. 1: a check failed, nothing may be pushed. 2: usage or environment error (a line on stderr).
Nothing here reads or prints a key, a one-time code or a token."""
import argparse
import datetime
import importlib.util
import re
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

PROGRAM = "check-staged-packages.py"
SUMS_LINE = re.compile(r"([0-9a-f]{64}) {2}(.+)")
TIMESTAMP_FAILURE = "the SDK output does not confirm a timestamp"
MAX_NUSPEC_BYTES = 1024 * 1024


def load_release_verify():
    """The functions of release-verify.py (the filename has a hyphen, so it is loaded by path)."""
    path = Path(__file__).resolve().with_name("release-verify.py")
    spec = importlib.util.spec_from_file_location("release_verify", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_verify"] = module
    spec.loader.exec_module(module)
    return module


release_verify = load_release_verify()
EnvironmentProblem = release_verify.EnvironmentProblem


def read_sums_lines(path):
    """The lines of the list; trailing empty lines are dropped, an empty line inside stays (and is malformed)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise EnvironmentProblem("sums file not found")
    except (OSError, UnicodeDecodeError):
        raise EnvironmentProblem("sums file cannot be read")
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_sums(lines, version):
    """Returns (name -> hash of the first valid line, the problems of the list). The ten names are the ten packages of the version."""
    expected = [f"{package_id}.{version}.nupkg" for package_id in release_verify.PACKAGES]
    listed = {}
    problems = []
    for number, line in enumerate(lines, start=1):
        match = SUMS_LINE.fullmatch(line)
        if match is None:
            problems.append(f"sums: line {number} is malformed")
            continue
        name = match.group(2)
        if name not in expected:
            problems.append(f"sums: {release_verify.printable(name)} is not one of the ten packages")
        elif name in listed:
            problems.append(f"sums: {name} is listed twice")
        else:
            listed[name] = match.group(1)
    for name in expected:
        if name not in listed:
            problems.append(f"sums: {name} is missing from the list")
    return listed, problems


def signature_parts(args, path, fingerprint):
    """Returns (report parts, ok) for the signature and the timestamp of one package."""
    signature_ok, timestamp_ok, detail = release_verify.verify_signature(args.dotnet, path, fingerprint)
    if not signature_ok:
        return [f"signature FAIL ({detail or 'verification failed'})", "timestamp not checked"], False
    if not timestamp_ok:
        return ["signature OK", f"timestamp FAIL ({detail or TIMESTAMP_FAILURE})"], False
    return ["signature OK", "timestamp OK"], True


def hash_part(path, expected):
    """Returns (report part, ok). A package that is not in the list is a problem of the list, reported there."""
    if expected is None:
        return "sha256 not listed", True
    if release_verify.sha256_of(path) == expected:
        return "sha256 OK", True
    return "sha256 FAIL (the file is not the one that was staged)", False


def check_package(args, package_id, fingerprint, listed):
    """Returns (report line, passed as a package)."""
    prefix = f"{package_id} {args.version}:"
    path = release_verify.package_path(args.dir, package_id, args.version)
    if path is None:
        return f"{prefix} package missing", False
    parts, signed_ok = signature_parts(args, path, fingerprint)
    hash_report, hash_ok = hash_part(path, listed.get(f"{package_id}.{args.version}.nupkg"))
    identity_report, identity_ok = identity_part(path, package_id, args.version)
    return f"{prefix} {', '.join(parts + [hash_report, identity_report])}", signed_ok and hash_ok and identity_ok


def read_nuspec(path):
    """The bytes of the one nuspec at the root of the package, or a short reason why there is none."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist() if info.filename.endswith(".nuspec") and "/" not in info.filename]
            if len(names) != 1:
                return None, "no nuspec" if not names else "more than one nuspec"
            if archive.getinfo(names[0]).file_size > MAX_NUSPEC_BYTES:
                return None, "nuspec is too large"
            return archive.read(names[0]), None
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError):
        return None, "the package is not a readable zip"


def nuspec_value(root, name):
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name and element.text and element.text.strip():
            return element.text.strip()
    return None


def identity_part(path, package_id, version):
    """Returns (report part, ok): the id and the version inside the package must be those of its file name."""
    data, reason = read_nuspec(path)
    if data is None:
        return f"identity FAIL ({reason})", False
    if b"<!DOCTYPE" in data.upper():
        return "identity FAIL (nuspec holds a DOCTYPE)", False
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return "identity FAIL (nuspec cannot be parsed)", False
    found_id, found_version = nuspec_value(root, "id"), nuspec_value(root, "version")
    if found_id is None or found_version is None:
        return "identity FAIL (nuspec has no id or no version)", False
    if found_id.lower() != package_id.lower():
        return f"identity FAIL (the package is {release_verify.printable(found_id)[:80]}, not {package_id})", False
    if found_version != version:
        return f"identity FAIL (the package is version {release_verify.printable(found_version)[:80]}, not {version})", False
    return "identity OK", True


def parse_args(argv):
    parser = argparse.ArgumentParser(prog=PROGRAM)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--sums", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--dotnet", default="dotnet")
    return parser.parse_args(argv)


def run(args):
    if not release_verify.is_semver(args.version):
        raise EnvironmentProblem("--version is not a SemVer version")
    try:
        fingerprint, _ = release_verify.load_certificate(args.certificate, datetime.date.today())
    except ValueError as error:
        raise EnvironmentProblem(str(error))
    release_verify.check_directory(args.dir, "staged")
    lines = read_sums_lines(args.sums)
    release_verify.check_dotnet(args.dotnet)
    listed, list_problems = parse_sums(lines, args.version)
    failures = 0
    for package_id in release_verify.PACKAGES:
        line, passed = check_package(args, package_id, fingerprint, listed)
        print(line)
        failures += 0 if passed else 1
    for name in release_verify.unexpected_entries(args.dir, args.version):
        print(f"unexpected entry in the directory: {release_verify.printable(name)}")
        failures += 1
    for problem in list_problems:
        print(problem)
        failures += 1
    if failures:
        print(f"FAIL: {failures} problem(s); nothing may be pushed")
        return 1
    print(f"PASS: {len(release_verify.PACKAGES)} packages verified")
    return 0


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except EnvironmentProblem as error:
        print(f"{PROGRAM}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
