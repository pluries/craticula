#!/usr/bin/env bash
# Signing probe helper (story #3320, spec FR-03 to FR-05, task #3478). Packs the unsigned probe package, runs dotnet's own
# signature check and reads the signer's fingerprint and expiry from its output. It never signs and holds no key: signing is
# the maker's step (docs/compliance/release-craticula.md, "Author signing certificate and the probe").
#   signing-probe.sh pack <out dir>          writes Craticula.SigningProbe.<version>.nupkg (unsigned) into <out dir>
#   signing-probe.sh verify <nupkg>          dotnet nuget verify --all <nupkg>; its exit code is the result
#   signing-probe.sh fingerprint <nupkg>     signer, SHA-256 and expiry of the author certificate (exit 1: unsigned; 2: unreadable)
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

need_file() {
  [ -f "$1" ] || fail "no such file: $1"
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$root/csharp/tools/Craticula.SigningProbe/Craticula.SigningProbe.csproj"

cmd_pack() {
  [ $# -eq 1 ] || usage
  need_dotnet
  local out build found
  mkdir -p "$1"
  out="$(cd "$1" && pwd)"
  build="$(mktemp -d "$out/.build.XXXXXX")"
  # --artifacts-path keeps bin and obj out of the project folder: nothing is written outside <out dir>.
  # The path is expanded now: the trap runs after this function has returned and its locals are gone.
  trap "rm -r -- '$build'" EXIT
  dotnet pack "$project" -c Release --artifacts-path "$build" -v q -nologo >&2
  found="$(find "$build/package" -name '*.nupkg' ! -name '*.symbols.nupkg' | head -n 2)"
  [ -n "$found" ] && [ "$(printf '%s\n' "$found" | wc -l)" -eq 1 ] || fail "dotnet pack did not produce exactly one .nupkg"
  mv -- "$found" "$out/"
  printf '%s\n' "$out/$(basename "$found")"
}

cmd_verify() {
  [ $# -eq 1 ] || usage
  need_file "$1"
  need_dotnet
  exec dotnet nuget verify --all "$1"
}

# The first "Verifying the author primary signature" block is the author's certificate; a timestamping service's certificate
# comes in a later block and must not win.
read_author_block() {
  awk '
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
      # The SDK prints M/D/YYYY h:mm:ss AM/PM (en-US); another format prints only the as-printed line.
      split(until, parts, " ")
      if (split(parts[1], d, "/") == 3 && d[1] ~ /^[0-9]+$/ && d[2] ~ /^[0-9]+$/ && d[3] ~ /^[0-9][0-9][0-9][0-9]$/)
        printf "valid until: %04d-%02d-%02d\n", d[3], d[1], d[2]
    }'
}

cmd_fingerprint() {
  [ $# -eq 1 ] || usage
  need_file "$1"
  local output block
  if [ -n "${SIGNING_PROBE_VERIFY_OUTPUT:-}" ]; then
    need_file "$SIGNING_PROBE_VERIFY_OUTPUT"
    output="$(cat "$SIGNING_PROBE_VERIFY_OUTPUT")"
  else
    need_dotnet
    output="$(dotnet nuget verify --all -v detailed "$1" 2>&1 || true)"
  fi
  if printf '%s\n' "$output" | grep -q 'NU3004'; then
    echo "unsigned"
    exit 1
  fi
  if block="$(printf '%s\n' "$output" | read_author_block)"; then
    printf '%s\n' "$block"
    return 0
  fi
  echo "signing-probe.sh: cannot read the author certificate from the verify output; first lines:" >&2
  printf '%s\n' "$output" | head -n 10 >&2
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
