# Runbook

## Environment strategy

Use separate environments per backend.

Suggested split:

- `env/nemo` for Canary + Parakeet
- `env/faster-whisper` for Whisper baseline
- `env/whisper-cpp` only if you want the native baseline

This avoids turning the repo into dependency soup.

## Phase-1 execution plan

### Step 1 — install and smoke test

For each candidate:

- verify model download
- verify one sample transcription
- verify timestamps if available
- verify streaming script path

### Step 2 — dataset freeze

Freeze the synthetic benchmark manifest before tuning.

### Step 3 — baseline configs

Use one conservative default config per model first.

Do not immediately hyper-optimize every knob.

The benchmark should compare models, not your tuning stamina.

### Step 4 — run smoke subset

Start with:

- 20-40 clips total
- mixed language buckets
- mostly short/medium duration

Use this run to validate:

- transcript parser
- metrics
- latency instrumentation
- VRAM capture

Convenient one-command smoke flow (after `synthetic_v1` is ready):

```bash
make stage1-smoke
```

This command does:

1. strict manifest validation (`scripts/validate_manifest.py`)
2. deterministic smoke subset build (`clean` + `short/medium`, `5` clips per mix)
3. bench -> evaluate -> summary chain

Useful overrides:

```bash
make stage1-smoke MANIFEST=data/manifests/synthetic_v1.jsonl SMOKE_MODEL_ID=whisper_large_v3_turbo_fw
```

### Step 5 — run main suite

Run full synthetic test set with fixed configs.

### Step 6 — optional tuned rerun

After the first honest comparison, allow one tuned rerun per model.

That keeps the project fair.

## Failure taxonomy

Tag failures like this:

- `collapse_to_en`
- `collapse_to_ru`
- `collapse_to_pl`
- `missed_switch`
- `hallucinated_switch`
- `timestamp_bad`
- `late_commit`
- `startup_heavy`
- `backend_instability`
