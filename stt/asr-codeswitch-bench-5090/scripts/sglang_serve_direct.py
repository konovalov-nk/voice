#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import logging
import os
import signal
import sys
from pathlib import Path

import yaml

from sglang_omni.client import Client, ClientError
from sglang_omni.models.fishaudio_s2_pro.config import S2ProPipelineConfig
from sglang_omni.pipeline.coordinator import Coordinator
from sglang_omni.serve.launcher import launch_server


def _patch_speech_timeout() -> None:
    timeout_s = float(os.getenv("SGLOMNI_SPEECH_TIMEOUT_S", "0") or "0")
    if timeout_s <= 0:
        return

    original = Client.speech

    async def _speech_with_timeout(
        self: Client,
        request,
        *,
        request_id: str,
        response_format: str = "wav",
        speed: float = 1.0,
    ):
        task = asyncio.create_task(
            original(
                self,
                request,
                request_id=request_id,
                response_format=response_format,
                speed=speed,
            )
        )
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            try:
                await self.abort(request_id)
            except Exception:
                pass
            try:
                await task
            except BaseException:
                pass
            raise ClientError(
                f"speech generation timed out after {timeout_s:.1f}s"
            ) from exc

    Client.speech = _speech_with_timeout


def _patch_coordinator_submit_cleanup() -> None:
    original = Coordinator.submit

    async def _submit_with_cleanup(self: Coordinator, request_id, request):
        try:
            return await original(self, request_id, request)
        finally:
            self._completion_futures.pop(request_id, None)

    Coordinator.submit = _submit_with_cleanup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error", "critical"),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    faulthandler.enable(file=sys.stderr, all_threads=True)
    faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)

    _patch_speech_timeout()
    _patch_coordinator_submit_cleanup()

    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid config file: {args.config}")

    raw.pop("config_cls", None)
    cfg = S2ProPipelineConfig(**raw)
    cfg = cfg.model_copy(update={"model_path": args.model_path})

    launch_server(
        cfg,
        host=args.host,
        port=args.port,
        model_name=None,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
