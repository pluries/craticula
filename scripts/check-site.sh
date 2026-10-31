#!/usr/bin/env bash
# Live check of the public site's address, redirects and certificate (spec FR-06, FR-07, FR-08, NFR-05; task #3330).
#   scripts/check-site.sh
# Checks (each failure is one line naming the URL and what was seen):
#   1. http://<primary>/<path> answers 308 and Location https://<primary>/<path> (the path is kept).
#   2. http:// and https:// of each redirect host answer 302 and Location exactly https://<primary> plus the same path.
#   3. https://<primary>/ answers 200 and its certificate has more than CHECK_SITE_MIN_DAYS days left.
#   4. No response of any request carries a Set-Cookie header (the value is never printed).
#   5. No open redirect: crafted paths (//evil.example/, /\evil.example, /https://evil.example/) and a forged Host header sent
#      to the redirecting hosts never produce a Location outside https://<primary>. A response without Location is accepted
#      only when it is a 4xx refusal; a 3xx without a safe Location, a 2xx, a 5xx or no answer fails.
# Exit 0: every check passed; 1: at least one failed; 2: usage or environment (curl, openssl or GNU date missing, bad value).
# Needs curl, openssl and GNU date (`date -d`) only. Environment (the defaults are the live values):
#   CHECK_SITE_PRIMARY         the site host (craticula.pluries.dev)
#   CHECK_SITE_REDIRECT_HOSTS  hosts that redirect to the site, space separated (pluries.dev www.pluries.dev)
#   CHECK_SITE_MIN_DAYS        the certificate must have MORE days than this left (30)
#   CHECK_SITE_HTTP_PORT, CHECK_SITE_HTTPS_PORT   ports of the URLs and of the certificate probe (80, 443); a non-default
#                              port appears in the URLs and in the expected Location
#   CHECK_SITE_CONNECT_TO      curl --connect-to mappings, space separated (HOST1:PORT1:HOST2:PORT2), to send the requests
#                              elsewhere (a test stub); the certificate probe follows the mapping of <primary>:<https port>
#   CHECK_SITE_CURL_OPTS       extra curl options, space separated (e.g. --cacert file)
set -euo pipefail

die() { echo "check-site: $*" >&2; exit 2; }

PRIMARY="${CHECK_SITE_PRIMARY:-craticula.pluries.dev}"
REDIRECT_HOSTS="${CHECK_SITE_REDIRECT_HOSTS:-pluries.dev www.pluries.dev}"
MIN_DAYS="${CHECK_SITE_MIN_DAYS:-30}"
HTTP_PORT="${CHECK_SITE_HTTP_PORT:-80}"
HTTPS_PORT="${CHECK_SITE_HTTPS_PORT:-443}"
MAX_TIME=10
PAGE_PATH="/some/page?a=1"
PROBES=('//evil.example/' '/\evil.example' '/https://evil.example/')

read -r -a CONNECT_TO <<<"${CHECK_SITE_CONNECT_TO:-}"
read -r -a CURL_EXTRA <<<"${CHECK_SITE_CURL_OPTS:-}"
read -r -a REDIRECTORS <<<"$REDIRECT_HOSTS"
CONNECT_ARGS=()
for mapping in ${CONNECT_TO[@]+"${CONNECT_TO[@]}"}; do CONNECT_ARGS+=(--connect-to "$mapping"); done

TOTAL=0
FAILED=0
STATUS=""
LOCATION=""

require_environment() {
  command -v curl >/dev/null 2>&1 || die "curl is not installed or not on PATH"
  command -v openssl >/dev/null 2>&1 || die "openssl is not installed or not on PATH"
  command -v date >/dev/null 2>&1 || die "date is not on PATH"
  date -d '@0' +%s >/dev/null 2>&1 || die "this date is not GNU date (date -d is needed for the certificate expiry)"
  [[ "$MIN_DAYS" =~ ^[0-9]+$ ]] || die "CHECK_SITE_MIN_DAYS must be a whole number"
  [[ "$HTTP_PORT" =~ ^[0-9]+$ && "$HTTPS_PORT" =~ ^[0-9]+$ ]] || die "the ports must be whole numbers"
  [ ${#REDIRECTORS[@]} -gt 0 ] || die "CHECK_SITE_REDIRECT_HOSTS is empty"
}

ok() { TOTAL=$((TOTAL + 1)); }
fail() { TOTAL=$((TOTAL + 1)); FAILED=$((FAILED + 1)); echo "FAIL $*"; }

# url <scheme> <host> <path>: the default port of the scheme is left out.
url() {
  local scheme="$1" host="$2" path="$3" port=""
  if [ "$scheme" = http ] && [ "$HTTP_PORT" != 80 ]; then port=":$HTTP_PORT"; fi
  if [ "$scheme" = https ] && [ "$HTTPS_PORT" != 443 ]; then port=":$HTTPS_PORT"; fi
  printf '%s://%s%s%s' "$scheme" "$host" "$port" "$path"
}

expected_base() { url https "$PRIMARY" ""; }

# fetch <url> [curl options]: one request, redirects not followed. Sets STATUS and LOCATION, and fails the cookie check when
# the response carries Set-Cookie (only its presence is reported, never a value).
fetch() {
  local target="$1" headers; shift
  headers="$WORK/headers"
  : >"$headers"
  STATUS="$(curl --silent --max-time "$MAX_TIME" --path-as-is ${CONNECT_ARGS[@]+"${CONNECT_ARGS[@]}"} \
    ${CURL_EXTRA[@]+"${CURL_EXTRA[@]}"} "$@" --output /dev/null --dump-header "$headers" \
    --write-out '%{http_code}' "$target" 2>/dev/null)" || STATUS="000"
  LOCATION="$(sed -n -E 's/^[Ll][Oo][Cc][Aa][Tt][Ii][Oo][Nn]:[[:space:]]*//p' "$headers" | tr -d '\r')"
  LOCATION="${LOCATION%%$'\n'*}"
  if grep -qi '^set-cookie:' "$headers"; then
    fail "$target: the response sets a cookie (Set-Cookie header present)"
  else
    ok
  fi
}

# expect_redirect <url> <status> <location>
expect_redirect() {
  local target="$1" want_status="$2" want_location="$3"
  fetch "$target"
  if [ "$STATUS" != "$want_status" ]; then
    fail "$target: expected status $want_status, got $STATUS"
  elif [ "$LOCATION" != "$want_location" ]; then
    fail "$target: expected Location $want_location, got '${LOCATION:-<none>}'"
  else
    ok
  fi
}

check_primary_http_redirect() {
  local base; base="$(expected_base)"
  expect_redirect "$(url http "$PRIMARY" "$PAGE_PATH")" 308 "$base$PAGE_PATH"
  expect_redirect "$(url http "$PRIMARY" "/")" 308 "$base/"
}

check_redirect_hosts() {
  local base host scheme; base="$(expected_base)"
  for host in "${REDIRECTORS[@]}"; do
    for scheme in http https; do
      expect_redirect "$(url "$scheme" "$host" "$PAGE_PATH")" 302 "$base$PAGE_PATH"
    done
  done
}

# The certificate probe goes where curl is sent for <primary>:<https port>.
certificate_target() {
  local mapping from to
  for mapping in ${CONNECT_TO[@]+"${CONNECT_TO[@]}"}; do
    from="${mapping%:*:*}"
    to="${mapping#*:*:}"
    if [ "$from" = "$PRIMARY:$HTTPS_PORT" ]; then printf '%s' "$to"; return; fi
  done
  printf '%s:%s' "$PRIMARY" "$HTTPS_PORT"
}

days_left() {
  local end_line end_epoch
  end_line="$(openssl s_client -connect "$(certificate_target)" -servername "$PRIMARY" </dev/null 2>/dev/null \
    | openssl x509 -enddate -noout 2>/dev/null)" || return 1
  end_epoch="$(date -d "${end_line#notAfter=}" +%s 2>/dev/null)" || return 1
  echo $(((end_epoch - $(date +%s)) / 86400))
}

check_primary_https() {
  local target days; target="$(url https "$PRIMARY" "/")"
  fetch "$target"
  if [ "$STATUS" = 200 ]; then ok; else fail "$target: expected status 200, got $STATUS"; fi
  if days="$(days_left)"; then
    if [ "$days" -gt "$MIN_DAYS" ]; then ok; else fail "$target: the certificate has $days days left, more than $MIN_DAYS are required"; fi
  else
    fail "$target: the certificate could not be read from $(certificate_target)"
  fi
}

# A Location is safe when it is the site itself or a path under it.
location_is_safe() {
  local base; base="$(expected_base)"
  [[ "$LOCATION" == "$base" || "$LOCATION" == "$base/"* ]]
}

assess_open_redirect() {
  local what="$1"
  if [ -n "$LOCATION" ]; then
    if location_is_safe; then ok; else fail "$what: open redirect, Location is $LOCATION"; fi
  elif [[ "$STATUS" == 4* ]]; then
    ok
  else
    fail "$what: expected a redirect to the site or a refusal, got status $STATUS without a Location"
  fi
}

check_open_redirects() {
  local targets=("http $PRIMARY") host scheme pair probe target
  for host in "${REDIRECTORS[@]}"; do targets+=("http $host" "https $host"); done
  for pair in "${targets[@]}"; do
    scheme="${pair%% *}"; host="${pair#* }"
    for probe in "${PROBES[@]}"; do
      target="$(url "$scheme" "$host" "$probe")"
      fetch "$target"
      assess_open_redirect "$target (crafted path)"
    done
    target="$(url "$scheme" "$host" "/")"
    fetch "$target" -H "Host: evil.example"
    assess_open_redirect "$target (forged Host: evil.example)"
  done
}

main() {
  require_environment
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  check_primary_http_redirect
  check_redirect_hosts
  check_primary_https
  check_open_redirects
  if [ "$FAILED" -gt 0 ]; then
    echo "check-site: $FAILED of $TOTAL checks failed"
    exit 1
  fi
  echo "check-site: all $TOTAL checks passed"
}

main "$@"
