#!/usr/bin/env python3
"""Writes <out>/manifest-compile.json for a compile benchmark run (story #3324, FR-19): machine, date, commit, versions and the
command that repeats it. Called by scripts/perf-compile.sh. Exit 0 = written, 2 = bad arguments. Tests: scripts/test_perf_page.py."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(command):
    try:
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--commit")
    parser.add_argument("--dotnet-version")
    parser.add_argument("--benchmark-version", default="BenchmarkDotNet")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return 2 if exit_.code else 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "machine": args.machine,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "commit": args.commit or run(["git", "rev-parse", "--short", "HEAD"]),
        "dotnet": args.dotnet_version or run(["dotnet", "--version"]),
        "benchmark": args.benchmark_version,
        "command": f"bash scripts/perf-compile.sh {args.out}",
    }
    (out / "manifest-compile.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
