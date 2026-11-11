#!/usr/bin/env bash
# The alert of the public demos (spec NFR-09, AC 9; task #3788): runs the live check, counts the failures in a row and exits 1 (the
# Jenkins job turns red and notifies the maker) only when the count reaches the threshold: 3 runs 5 minutes apart = 15 minutes down.
# A success resets the count. Exit 0 = no alert, 1 = alert.
# Environment:
#   DEMO_WATCH_CHECK      the command line to run (default `bash scripts/check-demos.sh`)
#   DEMO_WATCH_STATE_DIR  where the count lives, in the file `failures` (default .demo-watch next to the workspace; the job sets it
#                         to a folder that outlives a build)
#   DEMO_WATCH_THRESHOLD  failures in a row that raise the alert (default 3)
set -uo pipefail

CHECK="${DEMO_WATCH_CHECK:-bash scripts/check-demos.sh}"
STATE_DIR="${DEMO_WATCH_STATE_DIR:-.demo-watch}"
THRESHOLD="${DEMO_WATCH_THRESHOLD:-3}"
[[ "$THRESHOLD" =~ ^[1-9][0-9]*$ ]] || { echo "demo-watch: DEMO_WATCH_THRESHOLD must be a whole number above 0" >&2; exit 2; }
mkdir -p "$STATE_DIR"
STATE="$STATE_DIR/failures"

count=0
if [ -f "$STATE" ]; then
  count="$(tr -dc '0-9' <"$STATE")"
  count="${count:-0}"
fi

if bash -c "$CHECK"; then
  echo 0 >"$STATE"
  echo "demo-watch: the demos answer; failures in a row reset to 0"
  exit 0
fi

count=$((count + 1))
echo "$count" >"$STATE"
if [ "$count" -ge "$THRESHOLD" ]; then
  echo "demo-watch: ALERT: the check failed $count times in a row (threshold $THRESHOLD)"
  exit 1
fi
echo "demo-watch: the check failed ($count of $THRESHOLD before the alert)"
exit 0
