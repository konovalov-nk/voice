# Containers: Podman-first setup for RTX 5090

This repo is **Podman-first**.

Why:

- rootless workflow is nice for local research
- no daemon required
- NVIDIA explicitly recommends **CDI** for Podman GPU access
- the same `Containerfile` still works with Docker if needed

## Host prerequisites

Install on the host:

- recent NVIDIA driver
- Podman
- NVIDIA Container Toolkit

For Podman, use **CDI** instead of the Docker-style runtime hook.

### 1. Generate a CDI spec

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

Verify:

```bash
nvidia-ctk cdi list
```

You should see devices like `nvidia.com/gpu=all` or indexed GPUs.

### 2. Smoke test GPU access in Podman

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  docker.io/pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime \
  python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## Build the benchmark image

```bash
podman build -t asr-codeswitch-bench:dev .
```

## Run an interactive shell

```bash
podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  -v "$PWD":/workspace:Z \
  -w /workspace \
  asr-codeswitch-bench:dev
```

Notes:

- `--security-opt=label=disable` often avoids SELinux labeling friction on local GPU experiments.
- `:Z` is useful on SELinux-based systems; on Arch you may not need it.

## Run a smoke benchmark

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  -v "$PWD":/workspace:Z \
  -w /workspace \
  asr-codeswitch-bench:dev \
  python scripts/bench.py \
    --model-id whisper_large_v3_turbo_fw \
    --manifest data/schema/sample.manifest.jsonl \
    --output results/smoke.json
```

## Why not make Podman the only path?

Because some ASR examples and community snippets still assume Docker.

Practical rule for this repo:

- **default docs:** Podman
- **compatibility promise:** OCI image + plain CLI, so Docker users can mirror commands easily

## Backend notes

### faster-whisper

The current stack expects **CUDA 12 + cuDNN 9** in modern configurations. Keeping it inside a container avoids the usual host mismatch mess.

### NeMo / Canary / Parakeet

NeMo is heavier than faster-whisper. The container path is worth it here, because the environment is harder to keep reproducible on a bare host.

## Recommended repo convention

Use these targets in docs and scripts:

- `make image`
- `make shell`
- `make smoke`
- `make eval`

where each target shells out to `podman` by default, but can be overridden.
