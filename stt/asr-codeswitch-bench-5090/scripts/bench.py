#!/usr/bin/env python3
"""Benchmark runner skeleton for local ASR code-switch experiments.

This file is intentionally small and opinionated. It is a scaffold, not a full implementation.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class BenchConfig:
    model_id: str
    manifest_path: Path
    output_path: Path
    streaming: bool = True


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_one_sample(sample: dict[str, Any], model_id: str) -> dict[str, Any]:
    # TODO:
    # - dispatch to backend adapter: nemo / faster-whisper / whisper.cpp
    # - capture partial traces for streaming models
    # - capture timestamps and resource stats
    start = time.perf_counter()
    # placeholder result
    elapsed = time.perf_counter() - start
    return {
        "id": sample["id"],
        "model_id": model_id,
        "hypothesis_text": "",
        "segments": [],
        "latency": {
            "ttfp_ms": None,
            "ttsc_ms": None,
            "finalization_lag_ms": None,
            "wall_ms": round(elapsed * 1000, 2),
        },
        "resources": {
            "peak_vram_mb": None,
            "avg_gpu_util": None,
        },
        "notes": ["TODO: connect backend adapter"],
    }


def run_benchmark(cfg: BenchConfig) -> list[dict[str, Any]]:
    manifest = load_manifest(cfg.manifest_path)
    return [run_one_sample(sample, cfg.model_id) for sample in manifest]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cfg = BenchConfig(
        model_id=args.model_id,
        manifest_path=args.manifest,
        output_path=args.output,
    )
    results = run_benchmark(cfg)
    payload = {
        "config": {
            **asdict(cfg),
            "manifest_path": str(cfg.manifest_path),
            "output_path": str(cfg.output_path),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
