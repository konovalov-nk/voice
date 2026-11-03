# Upstream Issue Draft - Fish S2 Pro on SM120

## Title

`Fish S2 Pro fails on SM120 in flash_attn_kvcache path (no kernel image), while SGLang server and scheduler are healthy`

## Summary

On RTX 5090 (SM120), SGLang Omni server starts and request scheduling works, but `POST /v1/audio/speech` crashes in Fish S2 Pro fast-AR KV-cache attention path.

Failing call chain:

- `s2pro_sglang_ar.py::_codebook_loop_impl`
- `text2semantic/modeling.py::Attention.forward_kvcached`
- `text2semantic/modeling.py::flash_attn_kvcache_op`
- kernel launch fails with:
  - `CUDA error ... flash_fwd_launch_template.h:166: no kernel image is available for execution on the device`

## Environment

- GPU: RTX 5090 (SM120)
- PyTorch: `2.9.1+cu128`
- Triton: `3.5.1`
- CUDA runtime/toolchain: 12.8
- SGLang: `0.5.8` and `0.5.8.post1` tested
- FlashInfer: `0.6.1` and `0.6.6` tested
- flashinfer source build with `FLASHINFER_CUDA_ARCH_LIST=12.0f` also tested

## Repro (minimal)

1. Start SGLang Omni + Fish S2 Pro server on SM120.
2. Send:

```bash
curl -X POST http://127.0.0.1:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"hi","max_new_tokens":1}' \
  --output out.wav
```

Observed behavior:

- request enters running state
- after ~33-40s process crashes with kernel-image error

## What was ruled out

- container/toolchain issue (compiler and devel image present)
- simple dependency mismatch (`flashinfer 0.6.1` vs `0.6.6`) alone
- pure backend routing toggles in SGLang (`prefill/decode triton/flashinfer`) alone

## Temporary workaround that works

1. Monkeypatch Fish `flash_attn_kvcache_op` to SDPA fallback.
2. Disable codebook-loop torch.compile (`use_torch_compile=False`).

With this workaround:

- first request succeeds in ~7.6-8.0s
- hot request succeeds in ~0.27s

So the failure appears to be specifically in the Fish fast-AR kvcache flash-attn kernel path on SM120.

## Ask

- Confirm whether this path should be supported on SM120.
- Suggest proper backend/routing for `flash_attn_kvcache` in Fish S2 Pro on Blackwell.
- If known unsupported, recommend official fallback path for this model/runtime combo.
