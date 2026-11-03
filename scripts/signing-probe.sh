#!/usr/bin/env bash
# Signing probe helper (story #3320, spec FR-03 to FR-05, task #3478). Packs the unsigned probe package, runs dotnet's own
# signature check and reads the signer's fingerprint and expiry from its output. It never signs and holds no key: signing is
# the maker's step (docs/compliance/release-craticula.md, "Author signing certificate and the probe").
#   signing-probe.sh pack <out dir>          writes Craticula.SigningProbe.<version>.nupkg (unsigned) into <out dir>
#   signing-probe.sh verify <nupkg>          dotnet nuget verify --all <nupkg>; its exit code is the result
#   signing-probe.sh fingerprint <nupkg>     signer, SHA-256, expiry and timestamp state of the author certificate
#                                            (exit 1: unsigned; 2: unreadable)
# SIGNING_PROBE_VERIFY_OUTPUT=<file> makes `fingerprint` read that file instead of running dotnet (the tests use it).
set -euo pipefail

usage() {
  echo "usage: signing-probe.sh pack <out dir> | verify <nupkg> | fingerprint <nupkg>" >&2
  exit 2
}

fail() {
  echo "signing-probe.sh: $1" >&2
  exit 2
}

need_dotnet() {
  command -v dotnet >/dev/null 2>&1 || fail "the .NET SDK is required (dotnet not found on PATH)"
}

# The SDK echoes the package path before the signature block: a path with a line break could forge the readout.
need_file() {
  case "$1" in
    *$'\n'* | *$'\r'*) fail "the file name contains a line break" ;;
  esac
  [ -f "$1" ] || fail "no such file: $1"
}

# A path that starts with a dash would be read as an option by dotnet.
safe_path() {
  case "$1" in
    -*) printf './%s\n' "$1" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$root/tools/signing-probe/Craticula.SigningProbe.csproj"

# Script-level so the exit trap still sees it after cmd_pack has returned; the path is never put into the trap text.
build_dir=""
cleanup() {
  [ -z "$build_dir" ] || rm -r -- "$build_dir"
}
trap cleanup EXIT

cmd_pack() {
  [ $# -eq 1 ] || usage
  case "$1" in
    -*) usage ;;
  esac
  need_dotnet
  local out found
  mkdir -p -- "$1"
  out="$(CDPATH= cd -- "$1" && pwd)"
  build_dir="$(mktemp -d "$out/.build.XXXXXX")"
  # --artifacts-path keeps bin and obj out of the project folder: nothing is written outside <out dir>.
  dotnet pack "$project" -c Release --artifacts-path "$build_dir" -v q -nologo >&2
  found="$(find "$build_dir/package" -name '*.nupkg' ! -name '*.symbols.nupkg' | head -n 2)"
  [ -n "$found" ] && [ "$(printf '%s\n' "$found" | wc -l)" -eq 1 ] || fail "dotnet pack did not produce exactly one .nupkg"
  mv -- "$found" "$out/"
  printf '%s\n' "$out/$(basename "$found")"
}

cmd_verify() {
  [ $# -eq 1 ] || usage
  need_file "$1"
  need_dotnet
  exec dotnet nuget verify --all "$(safe_path "$1")"
}

# The first "Verifying the author primary signature" block is the author's certificate; a timestamping service's certificate
# comes in a later block and must not win. Dates: the SDK prints them in the current culture, so the script runs dotnet with the
# invariant culture (month first) and trusts M/D/YYYY then (mdy=1); for a file it trusts only the en-US 12-hour form (AM or PM),
# otherwise it prints the as-printed lines and no ISO date.
read_author_block() {
  awk -v mdy="$1" '
    /^Verifying the author primary signature with certificate:/ { if (seen) exit; seen = 1; inblock = 1; next }
    inblock && /^  [^ ]/ {
      if ($0 ~ /^  Subject Name: /)      { sub(/^  Subject Name: /, ""); signer = $0 }
      else if ($0 ~ /^  SHA256 hash: /)  { sub(/^  SHA256 hash: /, ""); sha = $0 }
      else if ($0 ~ /^  Valid from: /) {
        line = $0; sub(/^  Valid from: /, "", line)
        cut = index(line, " to ")
        if (cut > 0) { from = substr(line, 1, cut - 1); until = substr(line, cut + 4) }
      }
      next
    }
    inblock { exit }
    END {
      if (signer == "" || sha == "") exit 3
      print "signer: " signer
      print "sha256: " sha
      if (from != "") print "valid from (as printed): " from
      if (until != "") print "valid until (as printed): " until
      split(until, parts, " ")
      if ((mdy == 1 || until ~ /[AP]M$/) && split(parts[1], d, "/") == 3 && d[1] ~ /^[0-9]+$/ && d[2] ~ /^[0-9]+$/ && d[3] ~ /^[0-9][0-9][0-9][0-9]$/)
        printf "valid until: %04d-%02d-%02d\n", d[3], d[1], d[2]
    }'
}

cmd_fingerprint() {
  [ $# -eq 1 ] || usage
  need_file "$1"
  local output block mdy=0
  if [ -n "${SIGNING_PROBE_VERIFY_OUTPUT:-}" ]; then
    need_file "$SIGNING_PROBE_VERIFY_OUTPUT"
    echo "signing-probe.sh: reading $SIGNING_PROBE_VERIFY_OUTPUT (SIGNING_PROBE_VERIFY_OUTPUT is set), dotnet is not run" >&2
    output="$(cat "$SIGNING_PROBE_VERIFY_OUTPUT")"
  else
    need_dotnet
    mdy=1
    output="$(DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 dotnet nuget verify --all -v detailed "$(safe_path "$1")" 2>&1 || true)"
  fi
  # Here-strings, not pipes: a reader that stops early (grep -q, head) would end a pipe with SIGPIPE and pipefail would report 141.
  if grep -q 'NU3004' <<<"$output"; then
    echo "unsigned"
    exit 1
  fi
  if block="$(read_author_block "$mdy" <<<"$output")"; then
    printf '%s\n' "$block"
    # NU3027 is the SDK's "should be timestamped" warning. A heuristic: the real output of a timestamped signature is untested
    # until the maker's real signature, so a "yes" is only "no NU3027".
    if grep -q 'NU3027' <<<"$output"; then
      echo "timestamped: no"
    else
      echo "timestamped: yes"
    fi
    return 0
  fi
  echo "signing-probe.sh: cannot read the author certificate from the verify output; first lines:" >&2
  head -n 10 <<<"$output" >&2 || true
  exit 2
}

[ $# -ge 1 ] || usage
command="$1"
shift
case "$command" in
  pack) cmd_pack "$@" ;;
  verify) cmd_verify "$@" ;;
  fingerprint) cmd_fingerprint "$@" ;;
  *) usage ;;
esac
