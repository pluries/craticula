#!/usr/bin/env bash
# Compile benchmark (story #3324, task #3846, spec FR-17): mean time and allocation per request for the named request shapes on the
# SQL (PostgreSQL), MongoDB and Search compilers, saved raw, then one line per shape and backend against PERF-1 (under 50 µs).
# Usage: bash scripts/perf-compile.sh [output folder]      default: perf/results/<date>/compile (relative to the repository)
# PERF_MACHINE labels the machine in the manifest (default: the host name). Needs the .NET SDK and Python 3.10+. Run it on a quiet machine: the numbers are only comparable with the same machine's other runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${1:-perf/results/$(date -u +%F)/compile}"
dotnet run --project csharp/tools/Craticula.Benchmarks -c Release -- run --out "$OUT"
python3 perf/compile_manifest.py --out "$OUT" --machine "${PERF_MACHINE:-$(hostname)}" --benchmark-version "BenchmarkDotNet $(sed -n 's/.*BenchmarkDotNet" Version="\([^"]*\)".*/\1/p' csharp/Directory.Packages.props)"
