#!/usr/bin/env python3
import argparse
import io
import time

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from omnivoice import OmniVoice


def _best_device() -> str:
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class TTSRequest(BaseModel):
    text: str
    language: str | None = None
    num_step: int = 16
    guidance_scale: float = 2.0
    speed: float | None = None
    duration: float | None = None


def build_app(
    model_id: str, device: str, dtype: torch.dtype, load_asr: bool
) -> FastAPI:
    app = FastAPI(title="OmniVoice API", version="1.0")

    model = OmniVoice.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        load_asr=load_asr,
    )

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "model": model_id,
            "device": device,
            "dtype": str(dtype),
            "sampling_rate": model.sampling_rate,
        }

    @app.post("/tts")
    def tts(req: TTSRequest) -> Response:
        text = (req.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is empty")

        t0 = time.perf_counter()
        audio = model.generate(
            text=text,
            language=req.language,
            num_step=req.num_step,
            guidance_scale=req.guidance_scale,
            speed=req.speed,
            duration=req.duration,
        )[0]
        gen_s = time.perf_counter() - t0

        wav = audio.squeeze(0).detach().cpu().numpy().astype(np.float32)
        audio_s = float(wav.shape[-1]) / float(model.sampling_rate)

        buf = io.BytesIO()
        sf.write(buf, wav, model.sampling_rate, format="WAV", subtype="PCM_16")
        payload = buf.getvalue()

        return Response(
            content=payload,
            media_type="audio/wav",
            headers={
                "X-Gen-Time-Ms": f"{gen_s * 1000.0:.2f}",
                "X-Audio-Duration-S": f"{audio_s:.6f}",
                "X-Audio-Bytes": str(len(payload)),
                "X-Sampling-Rate": str(model.sampling_rate),
            },
        )

    return app


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run local OmniVoice API server.")
    p.add_argument("--model", default="k2-fsa/OmniVoice")
    p.add_argument("--device", default=None, help="cuda:0, mps, cpu. Auto if omitted.")
    p.add_argument(
        "--dtype",
        default="float16",
        choices=["float16", "bfloat16", "float32"],
        help="Model dtype.",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--load-asr", action="store_true", default=False)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    device = args.device or _best_device()
    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    dtype = dtype_map[args.dtype]

    app = build_app(args.model, device, dtype, args.load_asr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
