from __future__ import annotations

import logging
import time

import torch

from sglang_omni.executors import PreprocessingExecutor
from sglang_omni.models.fishaudio_s2_pro.pipeline.state_io import (
    load_state,
    store_state,
)
from sglang_omni.proto import StagePayload


logger = logging.getLogger(__name__)


def create_vocoder_executor(
    model_path: str,
    *,
    device: str = "cuda",
) -> PreprocessingExecutor:
    from sglang_omni.models.fishaudio_s2_pro.pipeline.stages import (
        _load_codec,
        _resolve_checkpoint,
    )

    checkpoint_dir = _resolve_checkpoint(model_path)
    codec = _load_codec(checkpoint_dir, device)

    def _vocode(payload: StagePayload) -> StagePayload:
        start = time.perf_counter()
        request_id = payload.request_id

        state = load_state(payload)
        output_codes = state.output_codes
        codebook_codes = output_codes[1:].to(device)

        with torch.no_grad():
            audio = codec.from_indices(codebook_codes[None])

        audio_np = audio[0, 0].float().cpu()
        state.audio_samples = audio_np
        state.sample_rate = codec.sample_rate
        payload = store_state(payload, state)

        payload.data["audio_data"] = audio_np.tolist()
        payload.data["sample_rate"] = codec.sample_rate
        payload.data["modality"] = "audio"

        elapsed = time.perf_counter() - start
        logger.info(
            "vocoder done req=%s elapsed_s=%.3f samples=%s sr=%s",
            request_id,
            elapsed,
            int(audio_np.numel()),
            codec.sample_rate,
        )
        return payload

    return PreprocessingExecutor(_vocode)
