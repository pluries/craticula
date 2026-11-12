#!/usr/bin/env bash
# The alert of the public demos (spec NFR-09, AC 9; task #3788): runs the live check up to THRESHOLD times in ONE run, one attempt starting
# every INTERVAL seconds, and exits 1 (the Jenkins job turns red and notifies the maker) only when every attempt failed: 3 attempts 5 minutes
# apart = 15 minutes down. Each attempt is cut after ATTEMPT seconds and counts as a failed one, so a demo that accepts connections and never
# answers cannot stretch the alert past its time. The first success ends the run with exit 0. It keeps no state between runs: the Jenkins
# agents are one-shot containers, so a count kept in a workspace would be gone after every build.
# Exit 0 = no alert, 1 = alert, 2 = bad setting or no `timeout` command (GNU coreutils).
# Environment:
#   DEMO_WATCH_CHECK             the command line to run (default `bash scripts/check-demos.sh`)
#   DEMO_WATCH_THRESHOLD         attempts, all failing, that raise the alert (default 3)
#   DEMO_WATCH_INTERVAL_SECONDS  from the start of one attempt to the start of the next (default 300; 0 for none)
#   DEMO_WATCH_ATTEMPT_SECONDS   the longest one attempt may run (default 120)
set -uo pipefail

CHECK="${DEMO_WATCH_CHECK:-bash scripts/check-demos.sh}"
THRESHOLD="${DEMO_WATCH_THRESHOLD:-3}"
INTERVAL="${DEMO_WATCH_INTERVAL_SECONDS:-300}"
ATTEMPT="${DEMO_WATCH_ATTEMPT_SECONDS:-120}"
[[ "$THRESHOLD" =~ ^[1-9][0-9]*$ ]] || { echo "demo-watch: DEMO_WATCH_THRESHOLD must be a whole number above 0" >&2; exit 2; }
[[ "$INTERVAL" =~ ^[0-9]+$ ]] || { echo "demo-watch: DEMO_WATCH_INTERVAL_SECONDS must be a whole number (0 or more)" >&2; exit 2; }
[[ "$ATTEMPT" =~ ^[1-9][0-9]*$ ]] || { echo "demo-watch: DEMO_WATCH_ATTEMPT_SECONDS must be a whole number above 0" >&2; exit 2; }
command -v timeout >/dev/null || { echo "demo-watch: the timeout command (GNU coreutils) is required" >&2; exit 2; }

for ((attempt = 1; attempt <= THRESHOLD; attempt++)); do
  started=$SECONDS
  if timeout --kill-after=5 "$ATTEMPT" bash -c "$CHECK"; then
    echo "demo-watch: the demos answer (attempt $attempt of $THRESHOLD)"
    exit 0
  fi
  if [ "$attempt" -lt "$THRESHOLD" ]; then
    pause=$((INTERVAL - (SECONDS - started)))
    [ "$pause" -lt 0 ] && pause=0
    echo "demo-watch: the check failed (attempt $attempt of $THRESHOLD); the next one starts in ${pause}s"
    sleep "$pause"
  fi
done

echo "demo-watch: ALERT: the check failed $THRESHOLD times in a row, one attempt every ${INTERVAL}s"
exit 1
