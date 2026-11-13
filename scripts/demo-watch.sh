#!/usr/bin/env bash
# The alert of the public demos (spec NFR-09, AC 9; task #3788): runs the live check up to THRESHOLD times in ONE run, one attempt starting
# every INTERVAL seconds, and exits 1 (the Jenkins job turns red and notifies the maker) only when every attempt failed: 3 attempts 5 minutes
# apart = 15 minutes down. Each attempt is cut after ATTEMPT seconds and counts as a failed one, so a demo that accepts connections and never
# answers cannot stretch the alert past its time. The first success ends the run with exit 0. It keeps no state between runs: the Jenkins
# agents are one-shot containers, so a count kept in a workspace would be gone after every build.
# On an alert it also sends a text message to DEMO_WATCH_NOTIFY_URL when that is set (the Jenkins controller has no mail or chat plugin): a
# POST of the message as the body, which ntfy topics and similar services accept; a Discord webhook URL (a path with /api/webhooks/) gets it as
# JSON, {"content": "..."}, which is what Discord takes. The URL is a secret (an ntfy topic is only as private as
# its name): it comes from the environment (a Jenkins credential binding), is never printed and is never written in the repository.
# Exit 0 = no alert, 1 = alert (also when the message could not be sent), 2 = bad setting or no `timeout` command (GNU coreutils).
# Environment:
#   DEMO_WATCH_CHECK             the command line to run (default `bash scripts/check-demos.sh`)
#   DEMO_WATCH_THRESHOLD         attempts, all failing, that raise the alert (default 3)
#   DEMO_WATCH_INTERVAL_SECONDS  from the start of one attempt to the start of the next (default 300; 0 for none)
#   DEMO_WATCH_ATTEMPT_SECONDS   the longest one attempt may run (default 120)
#   DEMO_WATCH_NOTIFY_URL        where an alert is posted (optional, secret)
# The retries run the check with CHECK_DEMOS_FLOOD=0 (no rate-limit flood): the flood proves the limit answers, not that the demos are up.
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
  # Only the first attempt floods: a retry that ends in a flood leaves this address throttled for a minute, and the next run (it starts
  # as soon as this one ends) would fail its first attempt on 429 again, round after round.
  if [ "$attempt" -gt 1 ]; then export CHECK_DEMOS_FLOOD=0; fi
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
if [ -n "${DEMO_WATCH_NOTIFY_URL:-}" ]; then
  message="The Craticula demos look down: the live check failed $THRESHOLD times in a row, about $(( (THRESHOLD - 1) * INTERVAL / 60 )) minutes. See the Jenkins job craticula-demo-watch."
  if [[ "$DEMO_WATCH_NOTIFY_URL" == */api/webhooks/* ]]; then
    # a Discord webhook takes JSON with a content member
    escaped="$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    send=(curl -fsS -m 15 -o /dev/null -H "Content-Type: application/json" -d "{\"content\":\"$escaped\"}" "$DEMO_WATCH_NOTIFY_URL")
  else
    send=(curl -fsS -m 15 -o /dev/null -H "Title: Craticula demos down" -d "$message" "$DEMO_WATCH_NOTIFY_URL")
  fi
  if "${send[@]}" >/dev/null 2>&1; then
    echo "demo-watch: the notification was sent"
  else
    echo "demo-watch: the notification could not be sent" >&2
  fi
fi
exit 1
