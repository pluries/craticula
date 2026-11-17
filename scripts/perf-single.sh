#!/usr/bin/env bash
# One client at a time (story #3856, task #3858): the load test of every engine at both sizes with a single client, so each number is
# what one request costs on an idle server, not what it costs with 8 clients waiting for each other. Run it on the measurement machine
# with nothing else running on it. Usage: PERF_MACHINE=<label> bash scripts/perf-single.sh [date]        default date: today (UTC)
# Output: perf/results/<date>-single/ (same files as perf-load.sh). Then:
#   python3 scripts/perf_page.py perf/results/<date> --repeat perf/results/<date>-repeat --single perf/results/<date>-single
# Needs docker compose, the .NET SDK and Python 3.10+. Environment: PERF_MACHINE (required), PERF_DURATION, PERF_WARMUP.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -n "${PERF_MACHINE:-}" ] || { echo "perf-single: set PERF_MACHINE to the machine's label (it is published in the results)" >&2; exit 2; }
DATE="${1:-$(date -u +%F)}"
case "$DATE" in /*|*..*) echo "perf-single: the date must be a plain name such as 2026-11-16, not a path" >&2; exit 2 ;; esac

for engine in postgres ef mongo; do
  for size in 10k 1m; do
    PERF_CONCURRENCY=1 PERF_OUT="perf/results/$DATE-single" bash scripts/perf-load.sh "$engine" "$size"
  done
done
