#!/usr/bin/env bash
# One-shot: wait for server, run memory_metrics in background, run fish-smoke-stream, then print memory report.
# Usage: run from repo root; server must already be running.
#   FISH_SERVER_PORT=18081 make fish-smoke-stream-profile
#   make fish-smoke-stream-profile FISH_SERVER_PORT=18081 FISH_SMOKE_REFERENCE_ID=en
# Optional: FISH_MEMORY_DUMP=1 to also call /v1/debug/memory?dump=1 and show snapshot path.

set -e
PORT="${FISH_SERVER_PORT:-18081}"
BASE_URL="http://127.0.0.1:${PORT}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
METRICS_OUT="${FISH_METRICS_OUT:-memory_metrics.jsonl}"
METRICS_INTERVAL="${FISH_METRICS_INTERVAL:-0.2}"
DO_DUMP="${FISH_MEMORY_DUMP:-0}"
MEMORY_PY="${REPO_ROOT}/.cache/fish-speech/tools/memory_metrics.py"

echo "=== fish-smoke-stream with memory profile ==="
echo "PORT=$PORT BASE_URL=$BASE_URL METRICS_OUT=$METRICS_OUT"

echo "Waiting for server $BASE_URL ..."
until curl -sf --connect-timeout 2 "$BASE_URL/v1/health" >/dev/null 2>&1; do
  sleep 1
done
echo "Server ready."

: > "$METRICS_OUT"
python3 "$MEMORY_PY" --url "$BASE_URL/v1/debug/memory" --out "$METRICS_OUT" --interval "$METRICS_INTERVAL" &
METRICS_PID=$!
trap 'kill $METRICS_PID 2>/dev/null; wait $METRICS_PID 2>/dev/null' EXIT

echo "Running fish-smoke-stream ..."
make fish-smoke-stream
echo "Smoke done; waiting 2s then fetching memory ..."
sleep 2

echo ""
echo "--- /v1/debug/memory ---"
MEMORY_JSON=$(curl -sS "$BASE_URL/v1/debug/memory")
echo "$MEMORY_JSON" | jq -r '.memory_summary // "no memory_summary"' 2>/dev/null || echo "$MEMORY_JSON"
echo "$MEMORY_JSON" | jq -c '{allocated_gb, reserved_gb, max_allocated_gb}' 2>/dev/null || true

if [[ "$DO_DUMP" =~ ^(1|true|True|yes|YES)$ ]]; then
  echo ""
  echo "--- /v1/debug/memory?dump=1 ---"
  DUMP_JSON=$(curl -sS "$BASE_URL/v1/debug/memory?dump=1")
  echo "$DUMP_JSON" | jq -c '{snapshot_path, snapshot_error, snapshot_note}' 2>/dev/null || echo "$DUMP_JSON"
fi

echo ""
echo "--- $METRICS_OUT (last 25 lines) ---"
tail -n 25 "$METRICS_OUT" 2>/dev/null || true
echo ""
echo "=== done ==="
