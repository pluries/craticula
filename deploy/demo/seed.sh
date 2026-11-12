#!/usr/bin/env bash
# The init step of a public demo pod (story #3323, task #3785; spec FR-12, FR-15): loads the synthetic seed into the pod's one
# database, creates the read-only account the API will use, and prints the dataset checksum. Runs inside the demo image
# (`bash /app/seed.sh`) as the init container, which is the only container that holds the administrator's connection string.
# Environment (all from the init container; the API container never gets the admin values):
#   DEMO_PROVIDERS           exactly one engine: postgres or mongo
#   DEMO_PG | DEMO_MONGO     the ADMIN connection string of that engine (the seed reads the one that matches DEMO_PROVIDERS)
#   DEMO_READONLY_PASSWORD   the password of the read-only account the seed creates
#   SEED_ATTEMPTS, SEED_DELAY_SECONDS   how long to wait for a database that is still starting (30 tries, 2 s apart)
#   DEMO_API_DLL             the seed program (default /app/Demo.Api.dll)
# Exit 0: seeded and the checksum line printed; 1: a count differs or no checksum was printed; 2: bad environment or the database
# never answered.
set -euo pipefail

provider="${DEMO_PROVIDERS:-}"
case "$provider" in
  postgres | mongo) ;;
  *) echo "seed: DEMO_PROVIDERS must name exactly one engine: postgres or mongo" >&2; exit 2 ;;
esac
[ -n "${DEMO_READONLY_PASSWORD:-}" ] || { echo "seed: DEMO_READONLY_PASSWORD is not set" >&2; exit 2; }

attempts="${SEED_ATTEMPTS:-30}"
delay="${SEED_DELAY_SECONDS:-2}"
dll="${DEMO_API_DLL:-/app/Demo.Api.dll}"
out="$(mktemp)"
trap 'rm -f "$out"' EXIT

for ((try = 1; try <= attempts; try++)); do
  status=0
  dotnet "$dll" seed "$provider" >"$out" 2>&1 || status=$?
  cat "$out"
  case "$status" in
    0) break ;;
    2) echo "seed: $provider is not ready (try $try of $attempts)" >&2; sleep "$delay" ;;
    *) echo "seed: the seed command ended with exit code $status" >&2; exit 1 ;;
  esac
done
[ "$status" -eq 0 ] || { echo "seed: $provider never accepted the seed" >&2; exit 2; }

# the seed's own output, printed above, carries the line; here it is only required
grep -qE '^Checksum: [0-9a-f]{64}$' "$out" || { echo "seed: the seed printed no checksum line" >&2; exit 1; }
