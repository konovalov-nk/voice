#!/usr/bin/env python3
"""Synthesize clean audio for prompt rows.

Supports:
- full-text rendering (legacy mode)
- segment-stitch rendering with per-language speaker references
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def mock_tts(
    text: str, target_duration_sec: float, sample_rate: int = 16000
) -> list[float]:
    duration = max(1.0, float(target_duration_sec))
    total = int(sample_rate * duration)
    words = max(1, len(text.split()))
    base_freq = 120.0 + (words % 8) * 15.0
    audio: list[float] = []

    for i in range(total):
        t = i / sample_rate
        base = 0.08 * math.sin(2.0 * math.pi * base_freq * t)
        gate = 1.0 if math.sin(2.0 * math.pi * 2.2 * t) > -0.1 else 0.0
        audio.append(base * gate)

    fade_len = min(sample_rate // 40, total // 10)
    if fade_len > 0:
        for i in range(fade_len):
            fade = i / max(1, fade_len - 1)
            audio[i] *= fade
            audio[total - 1 - i] *= fade
    return audio


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    pcm = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        pcm.extend(struct.pack("<h", int(value * 32767.0)))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))


def read_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"Only 16-bit PCM wav is supported: {path}")

    raw = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    if channels == 1:
        mono = [x / 32768.0 for x in raw]
    else:
        mono = []
        for i in range(0, len(raw), channels):
            chunk = raw[i : i + channels]
            mono.append((sum(chunk) / len(chunk)) / 32768.0)
    return mono, sample_rate


def rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples))


def infer_language(row: dict[str, Any]) -> str:
    segments = row.get("segments") or []
    if segments and isinstance(segments[0], dict):
        lang = str(segments[0].get("lang", "en"))
        if lang in {"en", "pl", "ru"}:
            return lang
    first = str(row.get("mix", "en")).split("_")[0]
    return first if first in {"en", "pl", "ru"} else "en"


def resolve_speaker_by_lang(args: argparse.Namespace) -> dict[str, str | None]:
    mapping = {
        "en": args.speaker_wav_en,
        "pl": args.speaker_wav_pl,
        "ru": args.speaker_wav_ru,
    }
    if args.speaker_wav:
        for lang in mapping:
            if not mapping[lang]:
                mapping[lang] = args.speaker_wav

    for lang in ("en", "pl", "ru"):
        default_ref = Path(f"{lang}.wav")
        if not mapping[lang] and default_ref.exists():
            mapping[lang] = str(default_ref)

    return mapping


def coqui_tts(
    model: Any,
    text: str,
    out_path: Path,
    speaker_wav: str | None,
    language: str | None,
) -> None:
    kwargs: dict[str, Any] = {"text": text, "file_path": str(out_path)}
    if speaker_wav:
        kwargs["speaker_wav"] = speaker_wav
    if language:
        kwargs["language"] = language
    model.tts_to_file(**kwargs)


def gain_match(samples: list[float], target_rms: float) -> tuple[list[float], float]:
    source_rms = rms(samples)
    if source_rms <= 1e-7 or target_rms <= 1e-7:
        return samples, 0.0
    ratio = target_rms / source_rms
    ratio = max(10 ** (-6 / 20), min(10 ** (6 / 20), ratio))
    gain_db = 20.0 * math.log10(ratio)
    adjusted = [max(-1.0, min(1.0, x * ratio)) for x in samples]
    return adjusted, gain_db


def stitch_segments(
    segments: list[list[float]],
    sample_rate: int,
    pause_ms: int,
    xfade_ms: int,
) -> tuple[list[float], list[dict[str, int]], list[int], list[int]]:
    if not segments:
        return [], [], [], []

    pause_samples = int(sample_rate * (pause_ms / 1000.0))
    xfade_samples = int(sample_rate * (xfade_ms / 1000.0))

    out = segments[0][:]
    bounds = [{"start": 0, "end": len(out)}]
    pause_before_ms = [0]
    pause_after_ms = [pause_ms if len(segments) > 1 else 0]

    for idx in range(1, len(segments)):
        prev_pause = pause_after_ms[idx - 1]
        if prev_pause > 0 and pause_samples > 0:
            out.extend([0.0] * pause_samples)

        current = segments[idx]
        overlap = 0
        if prev_pause == 0 and xfade_samples > 0:
            overlap = min(xfade_samples, len(out), len(current))

        if overlap > 0:
            start = len(out) - overlap
            for i in range(overlap):
                fade_out = (overlap - 1 - i) / max(1, overlap - 1)
                fade_in = i / max(1, overlap - 1)
                out[start + i] = out[start + i] * fade_out + current[i] * fade_in
            out.extend(current[overlap:])
            seg_start = start
        else:
            seg_start = len(out)
            out.extend(current)

        seg_end = len(out)
        bounds.append({"start": seg_start, "end": seg_end})
        pause_before_ms.append(0)
        pause_after_ms.append(pause_ms if idx < len(segments) - 1 else 0)

    return out, bounds, pause_before_ms, pause_after_ms


def write_segment_metadata(
    meta_path: Path,
    row: dict[str, Any],
    segment_rows: list[dict[str, Any]],
    rendered_bounds_ms: list[dict[str, Any]],
    speaker_ref_by_lang: dict[str, str | None],
    xfade_ms: int,
) -> None:
    payload = {
        "sample_id": row.get("id"),
        "text_uid": row.get("text_uid"),
        "render_mode": "segment_stitch",
        "speaker_ref_by_lang": {k: v for k, v in speaker_ref_by_lang.items() if v},
        "segments_rendered": segment_rows,
        "rendered_segment_bounds_ms": rendered_bounds_ms,
        "xfade_ms": xfade_ms,
    }
    ensure_parent(meta_path)
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def synthesize_segment_stitch(
    row: dict[str, Any],
    out_path: Path,
    coqui_model: Any,
    backend: str,
    args: argparse.Namespace,
    speaker_ref_by_lang: dict[str, str | None],
) -> None:
    segments = row.get("segments") or []
    if not segments:
        raise ValueError(f"Missing `segments` for row {row.get('id')}")

    segment_audio_arrays: list[list[float]] = []
    segment_rows: list[dict[str, Any]] = []
    sample_rate: int | None = None

    seg_root = args.segment_root / row["mix"] / "clean" / row["id"]
    seg_root.mkdir(parents=True, exist_ok=True)

    for index, segment in enumerate(segments, start=1):
        lang = str(segment["lang"])
        text = str(segment["text"])
        seg_id = f"seg_{index:02d}"
        seg_path = seg_root / f"{seg_id}_{lang}.wav"

        if backend == "mock":
            seg_samples = mock_tts(
                text,
                target_duration_sec=max(1.0, len(text) / 18.0),
                sample_rate=args.sample_rate,
            )
            seg_sr = args.sample_rate
            write_wav(seg_path, seg_samples, seg_sr)
        else:
            assert coqui_model is not None
            coqui_tts(
                coqui_model,
                text,
                seg_path,
                speaker_ref_by_lang.get(lang),
                lang,
            )
            seg_samples, seg_sr = read_wav(seg_path)

        if sample_rate is None:
            sample_rate = seg_sr
        elif sample_rate != seg_sr:
            raise ValueError(f"Segment sample rate mismatch: {sample_rate} vs {seg_sr}")

        segment_audio_arrays.append(seg_samples)
        segment_rows.append(
            {
                "segment_id": seg_id,
                "lang": lang,
                "text": text,
                "segment_audio_path": seg_path.as_posix(),
                "gain_db": 0.0,
                "pause_before_ms": 0,
                "pause_after_ms": 0,
            }
        )

    assert sample_rate is not None
    target_rms = rms(segment_audio_arrays[0])
    for i in range(len(segment_audio_arrays)):
        adjusted, gain_db = gain_match(segment_audio_arrays[i], target_rms)
        segment_audio_arrays[i] = adjusted
        segment_rows[i]["gain_db"] = round(gain_db, 3)

    stitched, bounds, pause_before_ms, pause_after_ms = stitch_segments(
        segments=segment_audio_arrays,
        sample_rate=sample_rate,
        pause_ms=args.pause_ms,
        xfade_ms=args.xfade_ms,
    )

    for i in range(len(segment_rows)):
        segment_rows[i]["pause_before_ms"] = pause_before_ms[i]
        segment_rows[i]["pause_after_ms"] = pause_after_ms[i]

    rendered_bounds_ms = []
    for i, bound in enumerate(bounds):
        rendered_bounds_ms.append(
            {
                "segment_id": segment_rows[i]["segment_id"],
                "start_ms": int(round(bound["start"] * 1000.0 / sample_rate)),
                "end_ms": int(round(bound["end"] * 1000.0 / sample_rate)),
            }
        )

    write_wav(out_path, stitched, sample_rate)
    write_segment_metadata(
        meta_path=out_path.with_suffix(".segments.json"),
        row=row,
        segment_rows=segment_rows,
        rendered_bounds_ms=rendered_bounds_ms,
        speaker_ref_by_lang=speaker_ref_by_lang,
        xfade_ms=args.xfade_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-in", required=True, type=Path)
    parser.add_argument("--audio-root", type=Path, default=Path("data/audio"))
    parser.add_argument("--segment-root", type=Path, default=Path("data/intermediate"))
    parser.add_argument("--backend", choices=("mock", "coqui"), default="mock")
    parser.add_argument(
        "--render-mode", choices=("full_text", "segment_stitch"), default="full_text"
    )
    parser.add_argument(
        "--coqui-model", default="tts_models/multilingual/multi-dataset/xtts_v2"
    )
    parser.add_argument("--speaker-wav", default=None)
    parser.add_argument("--speaker-wav-en", default=None)
    parser.add_argument("--speaker-wav-pl", default=None)
    parser.add_argument("--speaker-wav-ru", default=None)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--pause-ms", type=int, default=60)
    parser.add_argument("--xfade-ms", type=int, default=40)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument(
        "--no-skip-existing", dest="skip_existing", action="store_false"
    )
    args = parser.parse_args()

    rows = read_jsonl(args.manifest_in)
    coqui_model = None

    if args.backend == "coqui":
        try:
            from TTS.api import TTS  # type: ignore[import-not-found]
            import torch  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Coqui backend requested but `TTS` is not installed"
            ) from exc
        use_gpu = bool(torch.cuda.is_available())
        print(f"Coqui backend: gpu={'on' if use_gpu else 'off'}")
        coqui_model = TTS(args.coqui_model, gpu=use_gpu)

    speaker_ref_by_lang = resolve_speaker_by_lang(args)

    rendered = 0
    skipped = 0

    for row in rows:
        mix = row["mix"]
        base_id = row["id"]
        out_path = args.audio_root / mix / "clean" / f"{base_id}.wav"
        ensure_parent(out_path)

        if args.skip_existing and out_path.exists():
            skipped += 1
            continue

        if args.render_mode == "segment_stitch":
            synthesize_segment_stitch(
                row=row,
                out_path=out_path,
                coqui_model=coqui_model,
                backend=args.backend,
                args=args,
                speaker_ref_by_lang=speaker_ref_by_lang,
            )
        elif args.backend == "mock":
            audio = mock_tts(
                row["raw_text"],
                row.get("target_duration_sec", 5.0),
                sample_rate=args.sample_rate,
            )
            write_wav(out_path, audio, args.sample_rate)
        else:
            assert coqui_model is not None
            coqui_tts(
                coqui_model,
                row["raw_text"],
                out_path,
                args.speaker_wav,
                infer_language(row),
            )

        rendered += 1

    print(f"Rendered {rendered} clean files under {args.audio_root}")
    if skipped:
        print(f"Skipped {skipped} existing files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
