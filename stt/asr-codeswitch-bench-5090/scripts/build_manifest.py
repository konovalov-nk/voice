#!/usr/bin/env python3
"""Build final benchmark manifest from prompts + rendered audio tree."""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path
from typing import Any

CONDITIONS = ("clean", "noise_light", "reverb_light")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        sample_rate = wf.getframerate()
    return round(float(frames) / float(sample_rate), 3)


def wav_meta(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        sample_rate = wf.getframerate()
    duration_ms = int(round((frames / sample_rate) * 1000.0))
    return duration_ms, sample_rate


def load_segment_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--audio-root", type=Path, default=Path("data/audio"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/manifests/synthetic_v1.jsonl")
    )
    parser.add_argument("--source-split", default="synthetic_v1")
    parser.add_argument("--dataset-version", default="synthetic_v1.0.0")
    parser.add_argument("--generator-version", default="tts-pipeline-0.1")
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument("--engine-model-id", default="unknown")
    parser.add_argument("--render-mode", default="full_text")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    prompts = read_jsonl(args.prompts)
    output_rows: list[dict[str, Any]] = []

    missing = 0
    for row in prompts:
        mix = row["mix"]
        base_id = row["id"]
        clean_meta_path = args.audio_root / mix / "clean" / f"{base_id}.segments.json"
        segment_meta = load_segment_meta(clean_meta_path)
        for condition in CONDITIONS:
            wav_path = args.audio_root / mix / condition / f"{base_id}.wav"
            if not wav_path.exists():
                missing += 1
                if args.strict:
                    raise FileNotFoundError(f"Missing audio file: {wav_path}")
                continue

            rel_path = wav_path.as_posix()
            duration_ms, sample_rate_hz = wav_meta(wav_path)
            sample_id = f"{base_id}_{condition}"
            output_rows.append(
                {
                    "sample_id": sample_id,
                    "id": f"{base_id}_{condition}",
                    "text_uid": row.get("text_uid", f"txt_{base_id}"),
                    "prompt_id": row.get("prompt_id", f"pr_{base_id}"),
                    "source_split": args.source_split,
                    "dataset_version": args.dataset_version,
                    "generator_version": args.generator_version,
                    "git_sha": args.git_sha,
                    "language_combo": row.get("language_combo", mix),
                    "audio_path": rel_path,
                    "duration_ms": duration_ms,
                    "sample_rate_hz": sample_rate_hz,
                    "raw_text": row["raw_text"],
                    "display_text": row.get("display_text", row["raw_text"]),
                    "canonical_text": row.get("canonical_text", row["normalized_text"]),
                    "normalized_text": row["normalized_text"],
                    "segments": row["segments"],
                    "target_lang_spans": row.get("target_lang_spans", []),
                    "switch_points": row.get("switch_points", []),
                    "switch_pattern": row.get("switch_pattern"),
                    "switch_count": row["switch_count"],
                    "speaker_id": row["speaker_id"],
                    "duration_sec": duration_sec(wav_path),
                    "condition": condition,
                    "mix": mix,
                    "density": row["density"],
                    "duration_bucket": row["duration_bucket"],
                    "engine_model_id": args.engine_model_id,
                    "render_mode": args.render_mode,
                    "speaker_ref_by_lang": segment_meta.get("speaker_ref_by_lang", {}),
                    "segments_rendered": segment_meta.get("segments_rendered", []),
                    "rendered_segment_bounds_ms": segment_meta.get(
                        "rendered_segment_bounds_ms", []
                    ),
                    "xfade_ms": segment_meta.get("xfade_ms"),
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in output_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(output_rows)} rows to {args.out}")
    if missing:
        print(f"Skipped {missing} missing files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
