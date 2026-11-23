#!/usr/bin/env bash
# The alert of the public site (spec NFR-09; story #3322): the shape of scripts/demo-watch.sh. It runs the live site check up to THRESHOLD
# times in ONE run, one attempt starting every INTERVAL seconds, and exits 1 (the Jenkins job turns red) only when every attempt failed.
# Each attempt is cut after ATTEMPT seconds and counts as a failed one. The first success ends the run with exit 0. No state is kept
# between runs: the Jenkins agents are one-shot containers.
# The check is check-site.sh with CHECK_SITE_EDGE_HTTPS=on (Cloudflare answers http itself) and CHECK_SITE_MIN_DAYS=14, so a certificate
# with 14 days or less left fails (NFR-09). Both can be overridden by the environment (a drill: CHECK_SITE_MIN_DAYS=400).
# On an alert, when SITE_WATCH_NOTIFY_URL is set, it POSTs a short text with the first failing check lines of the last attempt: plain text
# as the body (ntfy and similar), JSON {"content": "..."} for a Discord webhook (a path with /api/webhooks/). The URL is a secret: it comes
# from the environment (a Jenkins credential binding) and is never printed or written down.
# Exit 0 = no alert, 1 = alert (also when the message could not be sent), 2 = bad setting or no `timeout` command (GNU coreutils).
# Environment:
#   SITE_WATCH_CHECK             the command line to run (default `bash scripts/check-site.sh`)
#   SITE_WATCH_THRESHOLD         attempts, all failing, that raise the alert (default 3)
#   SITE_WATCH_INTERVAL_SECONDS  from the start of one attempt to the start of the next (default 300; 0 for none)
#   SITE_WATCH_ATTEMPT_SECONDS   the longest one attempt may run (default 120)
#   SITE_WATCH_NOTIFY_URL        where an alert is posted (optional, secret)
set -uo pipefail

CHECK="${SITE_WATCH_CHECK:-bash scripts/check-site.sh}"
THRESHOLD="${SITE_WATCH_THRESHOLD:-3}"
INTERVAL="${SITE_WATCH_INTERVAL_SECONDS:-300}"
ATTEMPT="${SITE_WATCH_ATTEMPT_SECONDS:-120}"
[[ "$THRESHOLD" =~ ^[1-9][0-9]*$ ]] || { echo "site-watch: SITE_WATCH_THRESHOLD must be a whole number above 0" >&2; exit 2; }
[[ "$INTERVAL" =~ ^[0-9]+$ ]] || { echo "site-watch: SITE_WATCH_INTERVAL_SECONDS must be a whole number (0 or more)" >&2; exit 2; }
[[ "$ATTEMPT" =~ ^[1-9][0-9]*$ ]] || { echo "site-watch: SITE_WATCH_ATTEMPT_SECONDS must be a whole number above 0" >&2; exit 2; }
command -v timeout >/dev/null || { echo "site-watch: the timeout command (GNU coreutils) is required" >&2; exit 2; }

export CHECK_SITE_EDGE_HTTPS="${CHECK_SITE_EDGE_HTTPS:-on}"
export CHECK_SITE_MIN_DAYS="${CHECK_SITE_MIN_DAYS:-14}"

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

for ((attempt = 1; attempt <= THRESHOLD; attempt++)); do
  started=$SECONDS
  if timeout --kill-after=5 "$ATTEMPT" bash -c "$CHECK" >"$out" 2>&1; then
    echo "site-watch: the site checks pass (attempt $attempt of $THRESHOLD)"
    exit 0
  fi
  cat "$out"
  if [ "$attempt" -lt "$THRESHOLD" ]; then
    pause=$((INTERVAL - (SECONDS - started)))
    [ "$pause" -lt 0 ] && pause=0
    echo "site-watch: the check failed (attempt $attempt of $THRESHOLD); the next one starts in ${pause}s"
    sleep "$pause"
  fi
done

echo "site-watch: ALERT: the check failed $THRESHOLD times in a row, one attempt every ${INTERVAL}s"
if [ -n "${SITE_WATCH_NOTIFY_URL:-}" ]; then
  failing="$(grep '^FAIL' "$out" | head -n 3)"
  [ -n "$failing" ] || failing="$(tail -n 3 "$out")"
  detail="$(printf '%s' "$failing" | tr -c '[:print:]' ' ' | cut -c1-500)"
  message="The Craticula site check failed $THRESHOLD times in a row (certificate under ${CHECK_SITE_MIN_DAYS} days left, or a redirect or header check). First failing lines: $detail See the Jenkins job craticula-site-watch."
  if [[ "$SITE_WATCH_NOTIFY_URL" == */api/webhooks/* ]]; then
    escaped="$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    send=(curl -fsS -m 15 -o /dev/null -H "Content-Type: application/json" -d "{\"content\":\"$escaped\"}" "$SITE_WATCH_NOTIFY_URL")
  else
    send=(curl -fsS -m 15 -o /dev/null -H "Title: Craticula site check failed" -d "$message" "$SITE_WATCH_NOTIFY_URL")
  fi
  if "${send[@]}" >/dev/null 2>&1; then
    echo "site-watch: the notification was sent"
  else
    echo "site-watch: the notification could not be sent" >&2
  fi
fi
exit 1
