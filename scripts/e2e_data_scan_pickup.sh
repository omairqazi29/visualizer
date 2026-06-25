#!/usr/bin/env bash
# Live e2e: mock-data-publisher (Docker) + data-scan pickup verification.
#
# Usage:
#   ./scripts/e2e_data_scan_pickup.sh
#   MOCK_PUBLISHER_URL=http://127.0.0.1:8765 ./scripts/e2e_data_scan_pickup.sh
#   SKIP_DOCKER=1 ./scripts/e2e_data_scan_pickup.sh   # assume publisher already up
#
# Exit 0 only if assertions pass.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.data-scan-e2e.yml)
PROFILE=(--profile data-scan-e2e)
MOCK_URL="${MOCK_PUBLISHER_URL:-http://127.0.0.1:8765}"
STARTED_DOCKER=0

cleanup() {
  if [[ "$STARTED_DOCKER" == "1" && "${KEEP_COMPOSE:-0}" != "1" ]]; then
    echo "[e2e] tearing down mock-data-publisher..."
    docker compose "${COMPOSE_FILES[@]}" "${PROFILE[@]}" stop mock-data-publisher 2>/dev/null || true
    docker compose "${COMPOSE_FILES[@]}" "${PROFILE[@]}" rm -f mock-data-publisher 2>/dev/null || true
  fi
}
trap cleanup EXIT

wait_healthy() {
  local url="$1" tries="${2:-30}"
  for i in $(seq 1 "$tries"); do
    if curl -sf "$url/health" >/dev/null 2>&1; then
      echo "[e2e] mock healthy at $url (attempt $i)"
      return 0
    fi
    sleep 1
  done
  echo "[e2e] ERROR: mock not healthy at $url/health after ${tries}s" >&2
  return 1
}

# --- Start mock publisher unless skipped or already up ---
if [[ "${SKIP_DOCKER:-0}" != "1" ]]; then
  if curl -sf "$MOCK_URL/health" >/dev/null 2>&1; then
    echo "[e2e] mock already up at $MOCK_URL"
  else
    if ! command -v docker >/dev/null 2>&1; then
      echo "[e2e] docker not found; start mock locally:" >&2
      echo "  python tests/e2e/mock_data_server/server.py" >&2
      echo "  then: SKIP_DOCKER=1 $0" >&2
      exit 1
    fi
    echo "[e2e] building + starting mock-data-publisher (profile data-scan-e2e)..."
    docker compose "${COMPOSE_FILES[@]}" "${PROFILE[@]}" up --build -d mock-data-publisher
    STARTED_DOCKER=1
    wait_healthy "$MOCK_URL" 45
  fi
else
  wait_healthy "$MOCK_URL" 5 || {
    echo "[e2e] SKIP_DOCKER=1 but mock not reachable at $MOCK_URL" >&2
    exit 1
  }
fi

# Optional parallel API smoke (nice-to-have; non-blocking)
if [[ "${WITH_API:-0}" == "1" ]]; then
  echo "[e2e] starting api in parallel..."
  docker compose "${COMPOSE_FILES[@]}" up -d api 2>/dev/null || true
  sleep 2
  curl -sf "http://127.0.0.1:8000/api/health" && echo "[e2e] api /api/health ok" || echo "[e2e] api health skipped/failed (non-fatal)"
fi

# Reset mock to seed
curl -sf -X POST "$MOCK_URL/reset" >/dev/null || true
echo "[e2e] mock status:"
curl -sf "$MOCK_URL/status" | python3 -m json.tool 2>/dev/null || curl -sf "$MOCK_URL/status"
echo

# Export env for pytest / direct python
export MOCK_PUBLISHER_URL="$MOCK_URL"
export INGESTION_REQUEST_DELAY_SEC=0
export INGESTION_EXTRA_ALLOWED_HOSTS=mock-data-publisher,localhost,127.0.0.1
export INGESTION_SOURCE_URL_dos_iv_fsc="${MOCK_URL}/dos/monthly"
export INGESTION_SOURCE_URL_uscis_inventory="${MOCK_URL}/uscis/data"
export INGESTION_SOURCE_URL_uscis_i485_perf="${MOCK_URL}/uscis/data"
export INGESTION_SOURCE_URL_uscis_i140="${MOCK_URL}/uscis/data"

echo "[e2e] running pytest -m e2e (data scan pickup)..."
python3 -m pytest tests/e2e/test_data_scan_pickup.py -m e2e -v --tb=short -s
RC=$?

if [[ $RC -eq 0 ]]; then
  echo
  echo "[e2e] SUCCESS — mock publish + scan pickup verified"
else
  echo
  echo "[e2e] FAILED (exit $RC)" >&2
fi
exit $RC
