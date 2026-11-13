#!/usr/bin/env bash
# Live check of the two public demos, from outside (spec FR-11, FR-13, NFR-09, AC 1 to 5, amendment M2; task #3788).
#   scripts/check-demos.sh
# Per target, on POST <base>/api/<provider>/rows (each failure is one line `FAIL <url>: <what>`):
#   1. a small page answers 200 with a JSON body that has "rows";
#   2. PUT and DELETE on the route answer 405 (the demo accepts only the grid's POST);
#   3. a page larger than the limit (endRow 100000) is rejected with a 4xx other than 429;
#   4. a quick flood of POSTs includes at least one 429 (the rate limit; that a second address still answers is the unit test's
#      proof, M2);
#   5. for an https base: the connection works with TLS 1.2 as the floor and the response carries Strict-Transport-Security.
# Exit 0: every check passed (the last line says "passed"); 1: at least one failed; 2: usage or environment.
# Needs curl. The flood uses up this address's budget of the rate limit for a minute: the watch runs every 5 minutes.
# Environment:
#   CHECK_DEMOS_TARGETS    space separated <provider>=<base url> (default postgres=https://craticula-pg.pluries.dev
#                          mongo=https://craticula-mongo.pluries.dev)
#   CHECK_DEMOS_FLOOD      number of quick requests of check 4 (default 70, above the 60 a minute of the limit; 0 skips check 4)
#   CHECK_DEMOS_CURL_OPTS  extra curl options, space separated
set -euo pipefail

die() { echo "check-demos: $*" >&2; exit 2; }

command -v curl >/dev/null 2>&1 || die "curl is not installed or not on PATH"
FLOOD="${CHECK_DEMOS_FLOOD:-70}"
[[ "$FLOOD" =~ ^[0-9]+$ ]] || die "CHECK_DEMOS_FLOOD must be a whole number"
read -r -a TARGETS <<<"${CHECK_DEMOS_TARGETS:-postgres=https://craticula-pg.pluries.dev mongo=https://craticula-mongo.pluries.dev}"
read -r -a CURL_EXTRA <<<"${CHECK_DEMOS_CURL_OPTS:-}"
[ ${#TARGETS[@]} -gt 0 ] || die "CHECK_DEMOS_TARGETS is empty"
for target in "${TARGETS[@]}"; do
  [[ "$target" =~ ^[a-z]+=https?://[^[:space:]]+$ ]] || die "malformed target '$target': expected <provider>=<base url>"
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SMALL='{"startRow":0,"endRow":10,"rowGroupCols":[],"valueCols":[],"pivotCols":[],"pivotMode":false,"groupKeys":[],"filterModel":null,"sortModel":[]}'
LARGE='{"startRow":0,"endRow":100000,"rowGroupCols":[],"valueCols":[],"pivotCols":[],"pivotMode":false,"groupKeys":[],"filterModel":null,"sortModel":[]}'
TOTAL=0
FAILED=0

ok() { TOTAL=$((TOTAL + 1)); }
fail() { TOTAL=$((TOTAL + 1)); FAILED=$((FAILED + 1)); echo "FAIL $*"; }

# request <method> <url> [body]: STATUS is the HTTP code (000 when nothing answered); the body and headers land in $WORK.
request() {
  local method="$1" url="$2" body="${3:-}" args=()
  [ -z "$body" ] || args=(-H 'Content-Type: application/json' --data "$body")
  [[ "$url" != https://* ]] || args+=(--tlsv1.2)
  STATUS="$(curl -sS -o "$WORK/body" -D "$WORK/headers" -w '%{http_code}' --max-time 15 -X "$method" \
    ${CURL_EXTRA[@]+"${CURL_EXTRA[@]}"} "${args[@]}" "$url" 2>/dev/null)" || STATUS="000"
}

check_target() {
  local provider="${1%%=*}" base="${1#*=}" url
  base="${base%/}"
  url="$base/api/$provider/rows"

  request POST "$url" "$SMALL"
  if [ "$STATUS" != "200" ]; then
    fail "$url: POST of a small page: expected 200, got $STATUS"
  elif ! grep -q '"rows"' "$WORK/body"; then
    fail "$url: POST of a small page: the body has no \"rows\""
  else
    ok
  fi
  if [[ "$base" == https://* ]]; then
    if grep -qi '^strict-transport-security:' "$WORK/headers" 2>/dev/null; then ok
    else fail "$url: the response has no Strict-Transport-Security header (or TLS 1.2 was refused)"; fi
  fi

  for method in PUT DELETE; do
    request "$method" "$url"
    if [ "$STATUS" = "405" ]; then ok; else fail "$url: $method: expected 405, got $STATUS"; fi
  done

  request POST "$url" "$LARGE"
  if [[ "$STATUS" =~ ^4[0-9][0-9]$ && "$STATUS" != "429" ]]; then ok
  else fail "$url: an oversized page (endRow 100000) was not rejected: got $STATUS (expected a 4xx other than 429)"; fi

  if [ "$FLOOD" -eq 0 ]; then return; fi  # the watch's retries: no flood, so the next run still has its budget
  local urls=() i
  for ((i = 0; i < FLOOD; i++)); do urls+=(-o /dev/null "$url"); done
  local codes
  codes="$(curl -sS -w '%{http_code}\n' --max-time 60 -X POST -H 'Content-Type: application/json' --data "$SMALL" \
    $([[ "$base" == https://* ]] && echo --tlsv1.2) ${CURL_EXTRA[@]+"${CURL_EXTRA[@]}"} "${urls[@]}" 2>/dev/null || true)"
  if grep -qx '429' <<<"$codes"; then ok; else fail "$url: no 429 after $FLOOD quick requests (the rate limit does not answer)"; fi
}

for target in "${TARGETS[@]}"; do check_target "$target"; done

if [ "$FAILED" -gt 0 ]; then
  echo "check-demos: $FAILED of $TOTAL checks failed"
  exit 1
fi
echo "check-demos: $TOTAL checks passed"
