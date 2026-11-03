# Worklog

## 2026-03-09

- [done] Reviewed `README.md` and dataset requirements.
- [done] Agreed on synthetic-first pipeline (prompt -> clean audio -> augments -> final manifest).
- [done] Implemented dataset tooling scripts and Makefile targets.
- [done] Added dataset generation notes to `docs/DATASET.md`.
- [done] Ran smoke pipeline (`per-cell=1`): prompts -> clean audio -> augments -> final manifest.
- [done] Added `dataset-clean-audio-coqui` target for real TTS rendering.
- [blocked] Local env currently misses `TTS` and `torch`; real voice synthesis pending env + speaker reference.
- [done] Switched to container-first path and added container dataset target.
- [in_progress] Building image with Coqui TTS and running full coqui dataset generation.
- [done] Added resume-friendly behavior for TTS rendering (`--skip-existing` default).
- [done] Diagnosed Docker GPU failure: stale `/etc/cdi/nvidia.yaml` still references `590.48.01` while host driver is `595.45.04`.
- [in_progress] Upgrading container PyTorch base to CUDA 12.8 to support RTX 5090 (`sm_120`).
- [done] Added `Dataset architecture (v2)` spec to `docs/DATASET.md`.
- [done] Added `data/schema/sample.manifest.v2.jsonl` with char-span + bool QA fields.
- [blocked] Docker GPU runtime currently fails (`libEGL_nvidia.so.590.48.01` missing in container init).
- [done] Added strict manifest validation script (`scripts/validate_manifest.py`).
- [done] Added deterministic Stage-1 smoke subset builder (`scripts/build_smoke_manifest.py`).
- [done] Added one-command smoke pipeline target (`make stage1-smoke`).
- [done] Extended prompt/manifest scripts with v2 identity + char-span fields.
- [done] Added canonicalization policy file: `docs/CANONICALIZATION.md`.
- [todo] Implement segment-level TTS render mode with per-language references.
- [todo] Implement stitch metadata persistence (`pause_before_ms`, `pause_after_ms`, `xfade_ms`, gains).
- [todo] Add `real_human_seed` manifest template and paired `text_uid` coverage checks.
- [next] Wire real TTS voice profile and freeze `synthetic_v1` artifact.
- [done] Detected per-language references: `en.wav`, `pl.wav`, `ru.wav` + transcripts.
- [done] Implemented `segment_stitch` mode in `scripts/synthesize_tts.py`.
- [done] Added sidecar stitch metadata (`*.segments.json`) and manifest ingestion.
- [done] Added `dataset-all-coqui-segment(-container)` targets to `Makefile`.
- [done] Updated dataset docs for per-language reference flow.
- [done] Ran segment-stitch smoke pipeline (`mock` backend), produced `synthetic_segment_smoke.jsonl`.
- [done] Ran one-sample real Coqui segment-stitch render with `en.wav/pl.wav/ru.wav` references.
- [done] Ran full Coqui segment-stitch generation (`synthetic_v2`): 360 clean + 720 augments + 1080-row manifest.
- [done] Added interactive A/B listening helper: `scripts/qa_ab.py` + `make qa-ab`.
- [done] Added Fish S2 pilot renderer (`scripts/synthesize_fish_s2.py`) and Fish dataset targets.
- [done] Researched Fish 5090 support path: use CUDA 12.9 + `cu129` custom build instead of upstream `latest` image.
- [done] Added `make fish-build-5090` and `make fish-all-5090` helper targets.
- [done] Fixed Fish partial-run pipeline: `FISH_COUNT` now selects prompts for clean+augment+manifest consistently.
- [done] Added Fish persistent server mode (`FISH_MODE=server`) to avoid per-segment model reloads.
- [done] Verified persistent mode on 5090 via API logs: one startup model load, then multiple `/v1/tts` requests.

## 2026-03-12

- [done] Added Fish latency instrumentation in `scripts/synthesize_fish_s2.py` for server mode:
  - per-segment request/connect/read timing
  - per-segment and per-sample RTF
  - aggregate p50/p95/mean report output
- [done] Added `make fish-latency` target and `FISH_LATENCY_OUT` output path.
- [next] Run `make fish-latency ... FISH_COUNT=20` on 5090 and compare with previous ~6.5-6.8s API response baseline.
- [done] Added FlashInfer override path for SGLang Omni S2 Pro:
  - new local factory `sglang_fish_flashinfer.create_sglang_tts_engine_executor`
  - `configs/s2pro_tts_5090.yaml` now uses `attention_backend: flashinfer` for `tts_engine`.

## 2026-03-13

- [done] Confirmed runtime failure narrowed to SM120 prefill attention path:
  - request reaches `SchedulerStatus.RUNNING`
  - then crashes with `no kernel image is available for execution on the device`
- [done] Tested matrix without success: `sglang 0.5.8/0.5.8.post1`, `flashinfer 0.6.1/0.6.6`, source-build flashinfer, reduced KV pressure.
- [done] Added fast-fail server timeout guard to avoid long hanging curls during debugging.
- [done] Added temporary instrumentation in `sglang_fish_flashinfer.py` for scheduler/engine request lifecycle tracing.
- [done] Added prefill backend override hook for focused experiments (`SGLANG_FLASHINFER_PREFILL_BACKEND`).
- [done] Created tracker and roadmap doc: `docs/FLASHINFER_SM120_TRACKER.md`.
- [done] Tried hybrid attention split (`prefill=triton`, `decode=flashinfer`): still crashes with `no kernel image` after ~33-34s when timeout guard is disabled.
- [done] Ran full Triton attention control (`prefill=triton`, `decode=triton`): still crashes with same kernel-image error after ~33s.
- [done] Identified exact failing path: fish fast-AR codebook loop calls `flash_attn_kvcache_op` in `text2semantic/modeling.py`, which still hits unsupported kernel path on SM120.
- [done] Implemented temporary runtime workaround in `sglang_fish_flashinfer.py`:
  - monkeypatch fish `flash_attn_kvcache_op` to SDPA fallback
  - disable codebook-loop torch.compile (`use_torch_compile=False`)
- [done] Verified stable responses with workaround:
  - cold request: ~7.6-8.0s
  - hot request: ~0.27s (200 OK)
  - works in hybrid mode: `prefill=triton`, `decode=flashinfer`
- [done] Added explicit SM120-safe startup target: `make sglang-serve-sm120-safe`.
- [done] Added 10s smoke checker: `make sglang-smoke-10s` (`scripts/sglang_smoke.py`).
- [done] Added upstream issue draft packet: `docs/FLASHINFER_SM120_UPSTREAM_ISSUE.md`.
- [next] Run broader quality/latency checks on real prompts with current safe profile.
