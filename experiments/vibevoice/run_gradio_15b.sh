#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv Python at $VENV_PYTHON"
  echo "Create it first: python -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

exec "$VENV_PYTHON" "$ROOT_DIR/demo/gradio_demo.py" \
  --model_path microsoft/VibeVoice-1.5B \
  --device cuda \
  --port 8898
