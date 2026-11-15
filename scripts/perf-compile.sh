#!/usr/bin/env bash
# Compile benchmark (story #3324, task #3846, spec FR-17): mean time and allocation per request for the named request shapes on the
# SQL (PostgreSQL), MongoDB and Search compilers, saved raw, then one line per shape and backend against PERF-1 (under 50 µs).
# Usage: bash scripts/perf-compile.sh [output folder]      default: perf/results/<date>/compile (relative to the repository)
# Needs the .NET SDK. Run it on a quiet machine: the numbers are only comparable with the same machine's other runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${1:-perf/results/$(date -u +%F)/compile}"
dotnet run --project csharp/tools/Craticula.Benchmarks -c Release -- run --out "$OUT"
