#!/usr/bin/env python3
"""Validate benchmark manifest structure and metadata consistency."""

from __future__ import annotations

import argparse
import json
import re
import wave
from pathlib import Path
from typing import Any

ALLOWED_MIXES = {"en_pl", "en_ru", "ru_pl", "en_ru_pl"}
ALLOWED_DENSITIES = {"low", "medium", "high"}
ALLOWED_CONDITIONS = {"clean", "noise_light", "reverb_light"}
ALLOWED_DURATION_BUCKETS = {"short", "medium", "long"}
ALLOWED_LANGS = {"en", "pl", "ru"}

NORM_RE = re.compile(r"[^0-9a-zа-яёąćęłńóśźż\s]", flags=re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = NORM_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc
    return rows


def read_wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        sample_rate = wf.getframerate()
    if sample_rate <= 0:
        raise ValueError(f"Invalid WAV sample rate for {path}")
    return float(frames) / float(sample_rate)


def validate_row(
    row: dict[str, Any],
    base_dir: Path,
    duration_tolerance_sec: float,
    check_audio: bool,
) -> list[str]:
    issues: list[str] = []

    required = [
        "id",
        "audio_path",
        "raw_text",
        "normalized_text",
        "segments",
        "switch_count",
        "speaker_id",
        "duration_sec",
        "condition",
        "mix",
        "density",
    ]
    for key in required:
        if key not in row:
            issues.append(f"missing field: {key}")

    if issues:
        return issues

    if not isinstance(row["id"], str) or not row["id"].strip():
        issues.append("field 'id' must be a non-empty string")

    if row["mix"] not in ALLOWED_MIXES:
        issues.append(f"invalid mix: {row['mix']}")

    if row["density"] not in ALLOWED_DENSITIES:
        issues.append(f"invalid density: {row['density']}")

    if row["condition"] not in ALLOWED_CONDITIONS:
        issues.append(f"invalid condition: {row['condition']}")

    duration_bucket = row.get("duration_bucket")
    if duration_bucket is not None and duration_bucket not in ALLOWED_DURATION_BUCKETS:
        issues.append(f"invalid duration_bucket: {duration_bucket}")

    segments = row["segments"]
    if not isinstance(segments, list) or not segments:
        issues.append("field 'segments' must be a non-empty list")
    else:
        for idx, segment in enumerate(segments):
            if not isinstance(segment, dict):
                issues.append(f"segments[{idx}] must be an object")
                continue
            lang = segment.get("lang")
            text = segment.get("text")
            if lang not in ALLOWED_LANGS:
                issues.append(f"segments[{idx}].lang invalid: {lang}")
            if not isinstance(text, str) or not text.strip():
                issues.append(f"segments[{idx}].text must be non-empty string")

    expected_switch_count = (
        max(0, len(segments) - 1) if isinstance(segments, list) else None
    )
    if row["switch_count"] != expected_switch_count:
        issues.append(
            "switch_count mismatch: "
            f"got {row['switch_count']}, expected {expected_switch_count}"
        )

    raw_text = row["raw_text"]
    normalized_text = row["normalized_text"]
    if not isinstance(raw_text, str) or not raw_text.strip():
        issues.append("field 'raw_text' must be a non-empty string")
    if not isinstance(normalized_text, str) or not normalized_text.strip():
        issues.append("field 'normalized_text' must be a non-empty string")
    elif isinstance(raw_text, str):
        expected_norm = normalize_text(raw_text)
        if normalized_text != expected_norm:
            issues.append(
                "normalized_text mismatch against normalization rule: "
                f"expected '{expected_norm}'"
            )

    try:
        duration_sec = float(row["duration_sec"])
        if duration_sec <= 0:
            issues.append("duration_sec must be > 0")
    except (TypeError, ValueError):
        issues.append("duration_sec must be numeric")
        duration_sec = None

    audio_path = row["audio_path"]
    if not isinstance(audio_path, str) or not audio_path.strip():
        issues.append("field 'audio_path' must be a non-empty string")
    elif check_audio:
        audio_fs_path = (base_dir / audio_path).resolve()
        if not audio_fs_path.exists():
            issues.append(f"audio file missing: {audio_fs_path}")
        elif duration_sec is not None:
            try:
                observed = read_wav_duration_sec(audio_fs_path)
                if abs(observed - duration_sec) > duration_tolerance_sec:
                    issues.append(
                        "duration mismatch with WAV: "
                        f"manifest={duration_sec:.3f}s wav={observed:.3f}s "
                        f"tolerance={duration_tolerance_sec:.3f}s"
                    )
            except Exception as exc:  # pragma: no cover
                issues.append(f"failed to read WAV '{audio_fs_path}': {exc}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--duration-tolerance-sec", type=float, default=0.2)
    parser.add_argument("--no-audio-check", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.manifest)
    if not rows:
        print(f"ERROR: manifest is empty: {args.manifest}")
        return 1

    failures = 0
    for idx, row in enumerate(rows, start=1):
        row_issues = validate_row(
            row=row,
            base_dir=args.base_dir,
            duration_tolerance_sec=args.duration_tolerance_sec,
            check_audio=not args.no_audio_check,
        )
        if row_issues:
            failures += 1
            print(f"Row {idx} ({row.get('id', '<unknown>')}):")
            for issue in row_issues:
                print(f"  - {issue}")

    if failures:
        print(
            f"Validation failed: {failures}/{len(rows)} rows have issues "
            f"in {args.manifest}"
        )
        return 1

    print(f"Validation OK: {len(rows)} rows in {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
