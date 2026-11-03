#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-asr-codeswitch-bench:dev}"
WORKDIR="${WORKDIR:-/workspace}"

exec podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  -v "$PWD":"$WORKDIR":Z \
  -w "$WORKDIR" \
  "$IMAGE" "$@"
