#!/usr/bin/env python3
"""Verifies the ten signed Craticula packages before release (story #3321, spec FR-01 to FR-04, FR-33).
Usage: release-verify.py --version X.Y.Z --unsigned DIR --signed DIR --certificate FILE [--dotnet CMD] [--today YYYY-MM-DD]
Exit 0: all ten packages pass. 1: a check failed. 2: usage or environment error.
SKELETON (task #3484 red step): every behaviour raises NotImplementedError."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_smoke  # noqa: E402

PACKAGES = pack_smoke.PACKAGES


def load_certificate(path, today):
    """Reads the certificate file (FR-33: `sha256`, `validUntil`, `subject`); returns (sha256, valid_until) or raises ValueError naming the problem (empty, unparsable, bad sha256 fingerprint, expired)."""
    raise NotImplementedError


def package_path(directory, package_id, version):
    """Returns the .nupkg path of a package in `directory`, or None when it is missing."""
    raise NotImplementedError


def compare_content(unsigned_path, signed_path):
    """Returns a list of differences between the unsigned zip and the signed one minus `.signature.p7s`; empty when equal."""
    raise NotImplementedError


def verify_signature(dotnet, signed_path, fingerprint):
    """Returns (signature_ok, timestamp_ok, detail) from `dotnet nuget verify --all --certificate-fingerprint`."""
    raise NotImplementedError


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="release-verify.py")
    parser.add_argument("--version", required=True)
    parser.add_argument("--unsigned", required=True)
    parser.add_argument("--signed", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--today")
    return parser.parse_args(argv)


def main(argv=None):
    parse_args(sys.argv[1:] if argv is None else argv)
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
