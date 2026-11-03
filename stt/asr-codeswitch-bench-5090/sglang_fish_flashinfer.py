from __future__ import annotations

import asyncio
import logging
import os
import time
import torch

from sglang_omni.executors import EngineExecutor
from sglang_omni.models.fishaudio_s2_pro.pipeline.engine_io import (
    apply_tts_result,
    build_sglang_tts_request,
)
from sglang_omni.models.fishaudio_s2_pro.pipeline.state_io import (
    load_state,
    store_state,
)
from sglang_omni.proto import StagePayload


logger = logging.getLogger(__name__)


def _patch_fish_kvcache_attention_fallback() -> None:
    if os.getenv("S2_FORCE_SDPA_KVCACHE", "1") not in {"1", "true", "True"}:
        return

    import sglang_omni.models.fishaudio_s2_pro.fish_speech.models.text2semantic.modeling as t2s

    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)

    def _sdpa_kvcache_op(
        q: torch.Tensor,
        k_cache: torch.Tensor,
        v_cache: torch.Tensor,
        k: torch.Tensor | None = None,
        v: torch.Tensor | None = None,
        cache_seqlens: torch.Tensor | None = None,
        causal: bool = False,
        num_splits: int = 0,
    ) -> torch.Tensor:
        del num_splits
        assert k is not None and v is not None and cache_seqlens is not None

        bsz, new_len, n_q, head_dim = q.shape
        n_kv = k.shape[2]

        for b in range(bsz):
            start = int(cache_seqlens[b].item())
            end = start + new_len
            k_cache[b, start:end, :n_kv, :head_dim] = k[b]
            v_cache[b, start:end, :n_kv, :head_dim] = v[b]

        outputs = []
        for b in range(bsz):
            total_len = int(cache_seqlens[b].item()) + new_len
            qh = q[b : b + 1].transpose(1, 2)
            kh = k_cache[b : b + 1, :total_len].transpose(1, 2)
            vh = v_cache[b : b + 1, :total_len].transpose(1, 2)

            if kh.shape[1] != qh.shape[1]:
                repeat = qh.shape[1] // kh.shape[1]
                kh = kh.repeat_interleave(repeat, dim=1)
                vh = vh.repeat_interleave(repeat, dim=1)

            yh = torch.nn.functional.scaled_dot_product_attention(
                qh, kh, vh, attn_mask=None, dropout_p=0.0, is_causal=causal
            )
            outputs.append(yh.transpose(1, 2).contiguous())

        return torch.cat(outputs, dim=0)

    t2s.flash_attn_kvcache_op = torch._dynamo.disable(_sdpa_kvcache_op)
    logger.info("patched fish s2 kvcache attention to SDPA fallback")


def _patch_flashinfer_prefill_backend() -> None:
    target_backend = os.getenv("SGLANG_FLASHINFER_PREFILL_BACKEND")
    if not target_backend:
        return

    import sglang.srt.layers.attention.flashinfer_backend as fib

    original_ctor = fib.BatchPrefillWithPagedKVCacheWrapper

    def _patched_ctor(*args, **kwargs):
        if kwargs.get("backend") == "fa2":
            kwargs["backend"] = target_backend
        return original_ctor(*args, **kwargs)

    fib.BatchPrefillWithPagedKVCacheWrapper = _patched_ctor
    logger.info("patched flashinfer paged prefill backend=%s", target_backend)


def create_sglang_tts_engine_executor(
    model_path: str,
    *,
    device: str = "cuda",
    attention_backend: str | None = "flashinfer",
    max_new_tokens: int = 2048,
    top_k: int = 30,
) -> EngineExecutor:
    _patch_fish_kvcache_attention_fallback()
    _patch_flashinfer_prefill_backend()

    from sglang.srt.server_args import ServerArgs

    from sglang_omni.models.fishaudio_s2_pro.factory import (
        _patch_fish_config_for_sglang,
        create_s2pro_sglang_engine,
    )
    from sglang_omni.models.fishaudio_s2_pro.pipeline.stages import _load_audio_decoder

    audio_decoder, num_codebooks, codebook_size, tokenizer, checkpoint_dir = (
        _load_audio_decoder(model_path, device)
    )
    audio_decoder.setup_caches(max_batch_size=1, dtype=torch.bfloat16)

    _patch_fish_config_for_sglang(checkpoint_dir)
    prefill_attention_backend = os.getenv("SGLANG_PREFILL_ATTN_BACKEND", "triton")
    decode_attention_backend = os.getenv("SGLANG_DECODE_ATTN_BACKEND", "flashinfer")

    server_args = ServerArgs(
        model_path=checkpoint_dir,
        tp_size=1,
        dtype="bfloat16",
        attention_backend=attention_backend,
        prefill_attention_backend=prefill_attention_backend,
        decode_attention_backend=decode_attention_backend,
        moe_runner_backend="triton",
        fp8_gemm_runner_backend="triton",
        mem_fraction_static=0.6,
        chunked_prefill_size=2048,
        max_running_requests=1,
        disable_cuda_graph=True,
    )

    logger.info(
        "server backends attention=%s prefill=%s decode=%s",
        attention_backend,
        prefill_attention_backend,
        decode_attention_backend,
    )

    engine = create_s2pro_sglang_engine(
        server_args=server_args,
        audio_decoder=audio_decoder,
        tokenizer=tokenizer,
        gpu_id=int(device.split(":")[-1]) if ":" in device else 0,
        num_codebooks=num_codebooks,
        codebook_size=codebook_size,
        max_new_tokens=max_new_tokens,
        top_k=top_k,
        use_torch_compile=False,
    )

    planner = engine.scheduler.batch_planner
    scheduler = engine.scheduler
    original_schedule = scheduler.schedule
    original_select_requests = planner.select_requests

    def _logged_schedule():
        if scheduler.waiting or scheduler.running:
            logger.info(
                "scheduler schedule enter waiting=%s running=%s",
                len(scheduler.waiting),
                len(scheduler.running),
            )
        out = original_schedule()
        if scheduler.waiting or scheduler.running or out is not None:
            out_n = len(out.requests) if out is not None else 0
            logger.info(
                "scheduler schedule exit out=%s waiting=%s running=%s",
                out_n,
                len(scheduler.waiting),
                len(scheduler.running),
            )
        return out

    def _logged_select_requests(waiting, running, resource_manager):
        selected = original_select_requests(waiting, running, resource_manager)
        prefill_waiting = len(
            getattr(planner.prefill_manager, "waiting_queue", []) or []
        )
        decode_runnable = bool(getattr(planner.decode_manager, "runnable", False))
        logger.info(
            "planner select waiting=%s running=%s selected=%s prefill_waiting=%s decode_runnable=%s",
            len(waiting),
            len(running),
            len(selected),
            prefill_waiting,
            decode_runnable,
        )
        return selected

    planner.select_requests = _logged_select_requests
    scheduler.schedule = _logged_schedule

    original_add_request = engine.add_request
    original_get_result = engine.get_result
    original_step = engine._step

    async def _logged_add_request(request_id: str, data: object) -> None:
        sched = engine.scheduler
        logger.info(
            "engine add_request req=%s waiting=%s running=%s",
            request_id,
            len(sched.waiting),
            len(sched.running),
        )
        await original_add_request(request_id, data)

    async def _logged_get_result(request_id: str):
        start = time.monotonic()
        while True:
            try:
                result = await asyncio.wait_for(
                    original_get_result(request_id), timeout=1.0
                )
                logger.info(
                    "engine get_result req=%s done_after=%.3fs",
                    request_id,
                    time.monotonic() - start,
                )
                return result
            except asyncio.TimeoutError:
                sched = engine.scheduler
                req = sched.requests.get(request_id)
                req_status = getattr(req, "status", None)
                logger.info(
                    "engine wait req=%s elapsed=%.3fs status=%s waiting=%s running=%s",
                    request_id,
                    time.monotonic() - start,
                    req_status,
                    len(sched.waiting),
                    len(sched.running),
                )

    step_counter = {"n": 0}

    async def _logged_step() -> bool:
        step_counter["n"] += 1
        step_id = step_counter["n"]
        sched = engine.scheduler
        if sched.waiting or sched.running:
            logger.info(
                "engine step_begin id=%s waiting=%s running=%s",
                step_id,
                len(sched.waiting),
                len(sched.running),
            )

        try:
            did_work = await original_step()
        except Exception:
            logger.exception("engine step exception id=%s", step_id)
            raise

        if sched.waiting or sched.running:
            logger.info(
                "engine step_end id=%s did_work=%s waiting=%s running=%s",
                step_id,
                did_work,
                len(sched.waiting),
                len(sched.running),
            )
        return did_work

    engine.add_request = _logged_add_request
    engine.get_result = _logged_get_result
    engine._step = _logged_step

    def _request_builder(payload: StagePayload):
        state = load_state(payload)
        logger.info(
            "tts_engine enqueue req=%s max_new_tokens=%s input_tokens=%s",
            payload.request_id,
            state.max_new_tokens,
            len(state.input_ids),
        )
        return build_sglang_tts_request(state, tokenizer)

    def _result_builder(payload: StagePayload, result: object) -> StagePayload:
        state = load_state(payload)
        apply_tts_result(state, result)
        output_codes = getattr(state, "output_codes", None)
        output_len = int(output_codes.shape[1]) if output_codes is not None else 0
        logger.info(
            "tts_engine done req=%s output_codes=%s", payload.request_id, output_len
        )
        return store_state(payload, state)

    return EngineExecutor(
        engine=engine,
        request_builder=_request_builder,
        result_builder=_result_builder,
    )
