#!/usr/bin/env bash
# The whole measurement of story #3324 (task #3848, NFR-08): the compile benchmark and the load test of all three engines at both sizes,
# run twice on this machine, then the two runs compared. Run it on the measurement machine with nothing else running on it.
# Usage: PERF_MACHINE=<label> bash scripts/perf-run.sh [date]        default date: today (UTC)
# Output: perf/results/<date>/ (the run to publish) and perf/results/<date>-repeat/ (the repeat). It ends with
# `python3 perf/compare.py`, which lists how far the repeat differs from the run (NFR-08: the spread is shown, there is no target; it exits 0 for
# any spread). A run it cannot read, or a repeat that is not a separate run (same folder, a copy, another machine or commit), is an exit 2.
# `python3 scripts/perf_page.py perf/results/<date> --repeat perf/results/<date>-repeat`
# writes the site page with that spread. Takes about an hour.
# Needs docker compose, the .NET SDK and Python 3.10+. Environment: PERF_MACHINE (required), PERF_CONCURRENCY, PERF_DURATION.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -n "${PERF_MACHINE:-}" ] || { echo "perf-run: set PERF_MACHINE to the machine's label (it is published in the results)" >&2; exit 2; }
DATE="${1:-$(date -u +%F)}"

for run in "$DATE" "$DATE-repeat"; do
  OUT="perf/results/$run"
  echo "=== run $run ==="
  bash scripts/perf-compile.sh "$OUT/compile"
  for engine in postgres ef mongo; do
    for size in 10k 1m; do
      PERF_OUT="$OUT" bash scripts/perf-load.sh "$engine" "$size"
    done
  done
done

python3 perf/compare.py "perf/results/$DATE" "perf/results/$DATE-repeat" || status=$?
echo
if [ "${status:-0}" -eq 0 ]; then
  echo "next: python3 scripts/perf_page.py perf/results/$DATE --repeat perf/results/$DATE-repeat   (then review the page, commit perf/results and site/)"
fi
exit "${status:-0}"
