#!/usr/bin/env bash
# 1) Stop server, start with COMPILE=1 and VRAM_STEPS=1
# 2) Wait for warmup (~5-6 min)
# 3) Run e2e (first run may trigger compile again — allow long timeout)
# 4) Run e2e again (second run, no compile)
# 5) Save full docker logs + vram_step lines to results/e2e_vram_YYYYMMDD_HHMMSS/
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PORT="${PORT:-8080}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT}}"
CONTAINER="${CONTAINER:-fish-speech}"
WAIT_WARMUP="${WAIT_WARMUP:-360}"
E2E_REQUEST_TIMEOUT="${E2E_REQUEST_TIMEOUT:-300}"

LOG_DIR="results/e2e_vram_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
echo "=== E2E VRAM log run ==="
echo "  LOG_DIR=$LOG_DIR  PORT=$PORT  WAIT_WARMUP=${WAIT_WARMUP}s"
echo ""

# 1) Stop and start with COMPILE=1 VRAM_STEPS=1
echo "--- Stopping server ---"
docker rm -f "$CONTAINER" 2>/dev/null || true
sleep 2
echo "--- Starting server COMPILE=1 VRAM_STEPS=1 ---"
COMPILE=1 VRAM_STEPS=1 PORT="$PORT" ./scripts/run_server_32gb.sh
echo ""

# 2) Wait for warmup (health returns 200)
echo "--- Waiting for warmup (health 200), timeout ${WAIT_WARMUP}s ---"
WAIT=0
until curl -sf --connect-timeout 2 "$BASE_URL/v1/health" >/dev/null 2>&1; do
  sleep 10
  WAIT=$((WAIT + 10))
  echo "  ... ${WAIT}s"
  if [[ $WAIT -ge $WAIT_WARMUP ]]; then
    echo "ERROR: health not ready in ${WAIT_WARMUP}s. Saving logs and exiting."
    docker logs "$CONTAINER" 2>&1 | tee "$LOG_DIR/docker_logs_warmup_timeout.txt"
    grep -E "vram_step|Warmup|torch.compile|GPU Memory" "$LOG_DIR/docker_logs_warmup_timeout.txt" > "$LOG_DIR/vram_steps_warmup_timeout.txt" || true
    exit 1
  fi
done
echo "  Server ready after ${WAIT}s."
echo ""

# Snapshot logs after warmup (before any e2e)
docker logs "$CONTAINER" 2>&1 | tee "$LOG_DIR/docker_logs_after_warmup.txt"
grep "vram_step" "$LOG_DIR/docker_logs_after_warmup.txt" > "$LOG_DIR/vram_steps_after_warmup.txt" || true
echo "  Saved: $LOG_DIR/docker_logs_after_warmup.txt, vram_steps_after_warmup.txt"
echo ""

# 3) First e2e (may trigger compile; use long request timeout via env if your e2e supports it)
echo "--- First e2e run (may trigger compile, allow up to ${E2E_REQUEST_TIMEOUT}s) ---"
export E2E_HEALTH_TIMEOUT=60
if PORT="$PORT" BASE_URL="$BASE_URL" ./scripts/e2e_smoke.sh; then
  echo "  First e2e passed."
else
  echo "  First e2e failed or timed out (compile may still be running). Continuing."
fi
docker logs "$CONTAINER" 2>&1 | tee "$LOG_DIR/docker_logs_after_first_e2e.txt"
grep "vram_step" "$LOG_DIR/docker_logs_after_first_e2e.txt" > "$LOG_DIR/vram_steps_after_first_e2e.txt" || true
echo ""

# 4) Second e2e
echo "--- Second e2e run ---"
if PORT="$PORT" BASE_URL="$BASE_URL" ./scripts/e2e_smoke.sh; then
  echo "  Second e2e passed."
else
  echo "  Second e2e failed."
fi
docker logs "$CONTAINER" 2>&1 | tee "$LOG_DIR/docker_logs_after_second_e2e.txt"
grep "vram_step" "$LOG_DIR/docker_logs_after_second_e2e.txt" > "$LOG_DIR/vram_steps_after_second_e2e.txt" || true
echo ""

# 5) Full log and summary
docker logs "$CONTAINER" 2>&1 | tee "$LOG_DIR/docker_logs_full.txt"
grep "vram_step" "$LOG_DIR/docker_logs_full.txt" > "$LOG_DIR/vram_steps_full.txt" || true

# 6) Build table + HTML chart from vram_steps
if [[ -f "$LOG_DIR/vram_steps_full.txt" ]] && [[ -s "$LOG_DIR/vram_steps_full.txt" ]]; then
  if python3 "$REPO_ROOT/scripts/plot_vram_steps.py" "$LOG_DIR/vram_steps_full.txt" -o "$LOG_DIR/vram_steps_chart.html" 2>/dev/null; then
    echo "  vram_steps_chart.html — open in browser to view chart"
  fi
fi

echo "=== Done. Logs in $LOG_DIR ==="
echo "  docker_logs_after_warmup.txt   — after warmup, before e2e"
echo "  docker_logs_after_first_e2e.txt"
echo "  docker_logs_after_second_e2e.txt"
echo "  docker_logs_full.txt"
echo "  vram_steps_*.txt — grep vram_step for each phase"
ls -la "$LOG_DIR"
