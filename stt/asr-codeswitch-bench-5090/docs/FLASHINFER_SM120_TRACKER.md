# FlashInfer SM120 Tracker (SGLang Omni + Fish S2 Pro)

## Goal

Get `POST /v1/audio/speech` stable on RTX 5090 (SM120) with SGLang Omni + Fish S2 Pro, targeting:

- first response path is functional
- hot request returns in <=10s (current smoke gate)
- no process crash / no kernel-image runtime error

## Current diagnosis

What works:

- container starts
- SGLang Omni pipeline starts (`preprocessing`, `tts_engine`, `vocoder`)
- request is enqueued and transitions to `SchedulerStatus.RUNNING`

What fails:

- request hangs in running state, then process crashes around 40s with:
  - `CUDA error ... flash_fwd_launch_template.h:166: no kernel image is available for execution on the device`

Interpretation:

- this is a narrow attention prefill runtime path issue on SM120
- not a general boot/install problem anymore

## Baseline environment (known reproducible)

- GPU: RTX 5090 (SM120)
- PyTorch: `2.9.1+cu128`
- Triton: `3.5.1`
- SGLang: `0.5.8` / `0.5.8.post1` tested
- FlashInfer: `0.6.1` and `0.6.6` tested

## Experiment board

Status keys: `pass`, `fail`, `partial`, `todo`

| ID | Change | Result | Status | Notes |
|---|---|---|---|---|
| E01 | Fix container toolchain (devel image, compiler present) | JIT compile failure removed | pass | moved blocker from build-time to runtime |
| E02 | `flashinfer 0.6.1` baseline | request crashes with kernel-image error | fail | request reaches RUNNING first |
| E03 | `flashinfer 0.6.6 + flashinfer-cubin 0.6.6` | same crash | fail | no improvement |
| E04 | lower pressure (`mem_fraction_static=0.6`, `max_running_requests=1`, `chunked_prefill_size=2048`) | same crash | fail | more free VRAM but same runtime error |
| E05 | source-build FlashInfer with `FLASHINFER_CUDA_ARCH_LIST=12.0f` | same crash | fail | not just wheel packaging |
| E06 | force prefill backend `trtllm` | explicit assert (`backend must be fa2 or fa3`) | fail | this path is invalid for current call site |
| E07 | force prefill backend `fa3` | no success on SM120 | fail | expected for current HW/path |
| E08 | server-side fail-fast timeout/abort guard | quick feedback loop for debugging | pass | keeps iterations fast |
| E09 | hybrid backend (`prefill=triton`, `decode=flashinfer`) with short timeout | no immediate kernel crash, but request still hangs | partial | request reaches RUNNING, then timeout |
| E10 | hybrid backend (`prefill=triton`, `decode=flashinfer`) with no timeout | still crashes with same kernel-image error (~33-34s) | fail | split backend does not avoid failing kernel path in this S2 route |
| E11 | full Triton attention (`prefill=triton`, `decode=triton`) with timeout | hangs until timeout, no fast success | partial | no immediate stack trace |
| E12 | full Triton attention (`prefill=triton`, `decode=triton`) no timeout | still crashes with same kernel-image error (~33s) | fail | indicates failing kernel path is still exercised despite backend overrides |
| E13 | instrument fish runtime path and locate exact failing stack | failure traced to `text2semantic/modeling.py::flash_attn_kvcache_op` under `_codebook_loop_impl` | pass | root cause narrowed to fish fast-AR KV-cache attention path |
| E14 | monkeypatch `flash_attn_kvcache_op` -> SDPA fallback + disable `use_torch_compile` for codebook loop | request succeeds | pass | first request ~7.6-8.0s, hot request ~0.27s |
| E15 | hybrid backend with workaround (`prefill=triton`, `decode=flashinfer`, SDPA fallback) | request succeeds | pass | keeps flashinfer decode path while avoiding failing fish flash-attn kernel |
| E16 | add reusable safe-start + smoke tooling in repo | targets/scripts created | pass | `sglang-serve-sm120-safe`, `sglang-smoke-10s`, `scripts/sglang_smoke.py` |

## Working hypothesis

Most likely root cause is in SM120 FlashInfer prefill (`fa2`) routing/generation path, not in container/dependency setup.

## Roadmap

### Phase A - Fast isolation

1. Keep one frozen reproducible baseline (no random version churn).
2. Verify exact prefill signature selected for S2 request (shape/dtype/backend) right before kernel dispatch.
3. Capture minimal reproducer with `max_new_tokens=1`.

Exit criteria:

- one short reproducer command
- one exact failing signature tuple logged

### Phase B - Bypass broken prefill path (preferred)

1. Try hybrid attention split if S2 integration allows:
   - `prefill_attention_backend=triton`
   - `decode_attention_backend=flashinfer`
2. If direct config path is unavailable, patch the S2 executor/runtime glue to force this split for prefill only.

Exit criteria:

- no kernel-image crash
- successful audio response for smoke input

### Phase C - If hybrid fails, patch path-level runtime

1. Patch FlashInfer/SGLang prefill backend selection for SM120 in local branch.
2. Re-run smoke and warm/hot checks.
3. If local patch works, prepare upstream-friendly diff and references.

Exit criteria:

- stable smoke response path
- clear patch boundary (local vs upstream)

## Tracking template (append each run)

Use this block for every new attempt:

```text
Date:
Experiment ID:
Change:
Command:
Result:
Logs key lines:
Conclusion:
Next:
```

## Immediate next experiments

1. Keep validating quality/latency on realistic texts with current safe profile.
2. Optionally gate fallback behavior behind a dedicated config flag per deployment.
3. Submit upstream issue using `docs/FLASHINFER_SM120_UPSTREAM_ISSUE.md`.
