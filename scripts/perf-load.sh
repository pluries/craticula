#!/usr/bin/env bash
# Load test of one demo engine on a throwaway local stack (story #3324, task #3847, spec FR-18).
# Usage: bash scripts/perf-load.sh <postgres|mongo> <10k|1m> [extra perf/load.py arguments]
# Starts the database in its own compose project (craticula-perf, its own ports and volumes: your dev demo data is untouched),
# seeds it with that many rows, starts the API WITHOUT public mode (the public demos refuse more than 60 requests a minute per
# address), runs perf/load.py, then stops everything and removes the throwaway volumes.
# Environment: PERF_MACHINE (required: the label written into the published results, never the host name), PERF_CONCURRENCY (default 8), PERF_DURATION seconds (default 60),
# PERF_OUT (default perf/results/<date>, relative to the repository: the manifest repeats it as given), PERF_API_PORT (default 5081). Needs docker compose, the .NET SDK and Python 3.10+.
set -euo pipefail

usage() { echo "usage: bash scripts/perf-load.sh <postgres|mongo> <10k|1m> [extra perf/load.py arguments]" >&2; exit 2; }
[ $# -ge 2 ] || usage
ENGINE="$1"; SIZE="$2"; shift 2
case "$ENGINE" in postgres|mongo) ;; *) usage ;; esac
case "$SIZE" in 10k) ROWS=10000 ;; 1m) ROWS=1000000 ;; *) usage ;; esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO="$ROOT/examples/demo"
cd "$ROOT"
PROJECT=craticula-perf
export DEMO_PG_PORT=55533 DEMO_MONGO_PORT=57117
API_PORT="${PERF_API_PORT:-5081}"
OUT="${PERF_OUT:-perf/results/$(date -u +%F)}"
MACHINE="${PERF_MACHINE:-}"
[ -n "$MACHINE" ] || { echo "perf-load: set PERF_MACHINE to the machine's label (it is published in the results)" >&2; exit 2; }
case "$OUT" in /*) echo "perf-load: PERF_OUT must be a path relative to the repository (an absolute one would publish a home directory)" >&2; exit 2 ;; esac
REPEAT="PERF_MACHINE=$MACHINE PERF_CONCURRENCY=${PERF_CONCURRENCY:-8} PERF_DURATION=${PERF_DURATION:-60} PERF_OUT=$OUT bash scripts/perf-load.sh $ENGINE $SIZE"
export DEMO_PG="Host=127.0.0.1;Port=$DEMO_PG_PORT;Username=demo;Password=demo;Database=demo"
export DEMO_MONGO="mongodb://127.0.0.1:$DEMO_MONGO_PORT"
compose() { docker compose -p "$PROJECT" -f "$DEMO/docker-compose.yml" "$@"; }

API_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

compose up -d --wait "$ENGINE"
CONTAINER="$(compose ps -q "$ENGINE")"
IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")"
VERSION="$IMAGE"
case "$ENGINE" in
  postgres) VERSION="$(docker exec "$CONTAINER" postgres --version | tr -d '\r')" ;;
  mongo) VERSION="MongoDB $(docker exec "$CONTAINER" mongod --version | sed -n 's/^db version v//p' | head -1)" ;;
esac

dotnet run --project "$DEMO/Api" -c Release -- seed "$ENGINE" --rows "$ROWS"
Logging__LogLevel__Default=Warning dotnet run --project "$DEMO/Api" -c Release --no-build --no-launch-profile --urls "http://127.0.0.1:$API_PORT" &
API_PID=$!
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null || { echo "perf-load: the API did not answer /api/health" >&2; exit 1; }

python3 "$ROOT/perf/load.py" --engine "$ENGINE" --base-url "http://127.0.0.1:$API_PORT" --dataset "$SIZE" \
  --concurrency "${PERF_CONCURRENCY:-8}" --duration "${PERF_DURATION:-60}" --machine "$MACHINE" --engine-version "$VERSION" \
  --out "$OUT" --repeat-command "$REPEAT" "$@"
