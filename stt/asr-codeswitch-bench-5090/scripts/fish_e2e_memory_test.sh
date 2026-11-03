#!/usr/bin/env bash
# E2E memory test for agent: run with server already up.
# All logs go to a timestamped folder (e.g. results/fish_e2e_20260315_120000) for sharing.
# 1) Wait for health, 2) memory_metrics in background, 3) 1st fish-smoke-stream,
# 4) memory after 1st, 5) 2nd fish-smoke-stream (OOM check), 6) memory after 2nd,
# 7) docker logs, 8) optional dump, 9) write report.
# Usage: FISH_SERVER_PORT=18081 FISH_SERVER_NAME=fish-s2-api bash scripts/fish_e2e_memory_test.sh

set -e
PORT="${FISH_SERVER_PORT:-18081}"
BASE_URL="http://127.0.0.1:${PORT}"
CONTAINER="${FISH_SERVER_NAME:-fish-s2-api}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
REPORT_DIR="${REPORT_DIR:-results}"
# Timestamped log dir for this run (share this folder with others)
E2E_LOG_DIR="${FISH_E2E_LOG_DIR:-$REPORT_DIR/fish_e2e_$(date +%Y%m%d_%H%M%S)}"
REPORT_FILE="${REPORT_FILE:-$E2E_LOG_DIR/report.txt}"
METRICS_OUT="${FISH_METRICS_OUT:-$E2E_LOG_DIR/memory_metrics.jsonl}"
METRICS_INTERVAL="${FISH_METRICS_INTERVAL:-0.2}"
DO_DUMP="${FISH_MEMORY_DUMP:-0}"
HEALTH_TIMEOUT="${FISH_E2E_HEALTH_TIMEOUT:-180}"
MEMORY_PY="${REPO_ROOT}/.cache/fish-speech/tools/memory_metrics.py"

mkdir -p "$E2E_LOG_DIR"
exec 1> >(tee -a "$REPORT_FILE") 2>&1

echo "=== Fish E2E memory test (agent) ==="
echo "PORT=$PORT CONTAINER=$CONTAINER"
echo "Log dir: $E2E_LOG_DIR"
echo ""

echo "Waiting for server (timeout ${HEALTH_TIMEOUT}s) ..."
WAIT=0
until curl -sf --connect-timeout 2 "$BASE_URL/v1/health" >/dev/null 2>&1; do
  sleep 2
  WAIT=$((WAIT + 2))
  if [[ $WAIT -ge $HEALTH_TIMEOUT ]]; then
    echo "ERROR: server did not become ready in ${HEALTH_TIMEOUT}s"
    exit 1
  fi
done
echo "Server ready after ${WAIT}s."
echo ""

: > "$METRICS_OUT"
python3 "$MEMORY_PY" --url "$BASE_URL/v1/debug/memory" --out "$METRICS_OUT" --interval "$METRICS_INTERVAL" &
METRICS_PID=$!
trap 'kill $METRICS_PID 2>/dev/null; wait $METRICS_PID 2>/dev/null' EXIT

echo "--- Request 1: fish-smoke-stream ---"
if make fish-smoke-stream; then
  REQ1="OK"
else
  REQ1="FAIL"
fi
echo "Request 1: $REQ1"
sleep 2
MEMORY_1=$(curl -sS "$BASE_URL/v1/debug/memory")
echo "Memory after request 1:"
echo "$MEMORY_1" | jq -c '{allocated_gb, reserved_gb, max_allocated_gb}' 2>/dev/null || echo "$MEMORY_1"
echo ""

echo "--- Request 2: fish-smoke-stream (OOM check) ---"
if make fish-smoke-stream; then
  REQ2="OK"
else
  REQ2="OOM_OR_FAIL"
fi
echo "Request 2: $REQ2"
sleep 2
MEMORY_2=$(curl -sS "$BASE_URL/v1/debug/memory")
echo "Memory after request 2:"
echo "$MEMORY_2" | jq -c '{allocated_gb, reserved_gb, max_allocated_gb}' 2>/dev/null || echo "$MEMORY_2"
echo ""

if [[ "$DO_DUMP" =~ ^(1|true|True|yes|YES)$ ]]; then
  echo "--- Memory snapshot dump ---"
  curl -sS "$BASE_URL/v1/debug/memory?dump=1" | jq -c '{snapshot_path, snapshot_error}' 2>/dev/null || true
  echo ""
fi

echo "--- Docker logs (last 200 lines) ---"
docker logs "$CONTAINER" 2>&1 | tail -n 200 || true
echo ""

# Full docker logs into log dir for sharing
docker logs "$CONTAINER" 2>&1 > "$E2E_LOG_DIR/docker_logs.txt" || true

echo "--- memory_metrics.jsonl (last 30 lines) ---"
tail -n 30 "$METRICS_OUT" 2>/dev/null || true
echo ""

echo "=== Summary ==="
echo "Request 1: $REQ1"
echo "Request 2: $REQ2"
TTFA_LINE=$(grep 'fish smoke ok' "$REPORT_FILE" 2>/dev/null | grep -oE 'ttfa_s=[0-9.]+' | tail -1)
TTFA_AUDIO_LINE=$(grep 'fish smoke ok' "$REPORT_FILE" 2>/dev/null | grep -oE 'ttfa_audio_s=[0-9.]+' | tail -1)
echo "TTFA (first byte / WAV header): ${TTFA_LINE:-N/A}"
echo "TTFA (first audio byte): ${TTFA_AUDIO_LINE:-N/A}"
echo "Memory after 1st: $(echo "$MEMORY_1" | jq -c '{allocated_gb, max_allocated_gb}' 2>/dev/null)"
echo "Memory after 2nd: $(echo "$MEMORY_2" | jq -c '{allocated_gb, max_allocated_gb}' 2>/dev/null)"
echo ""
echo "Logs saved to: $E2E_LOG_DIR"
echo "  report.txt          - full run log"
echo "  memory_metrics.jsonl - VRAM samples"
echo "  docker_logs.txt     - full container log (share this folder)"
