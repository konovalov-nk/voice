#!/usr/bin/env python3
"""Generate synthetic code-switch text prompts for dataset creation."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

MIXES = ("en_pl", "en_ru", "ru_pl", "en_ru_pl")
DENSITIES = ("low", "medium", "high")
DURATIONS = ("short", "medium", "long")

DURATION_SEC_RANGE: dict[str, tuple[float, float]] = {
    "short": (3.0, 7.0),
    "medium": (10.0, 20.0),
    "long": (30.0, 60.0),
}

LANG_SEGMENTS: dict[str, list[str]] = {
    "en": [
        "I need to send the report before lunch",
        "let us sync after the deploy finishes",
        "the meeting starts in twenty minutes",
        "please set a reminder for tomorrow morning",
        "I will push the changes after one more test",
        "can you check the logs from last night",
        "we should keep this version as a stable baseline",
        "I am running late but still joining the call",
    ],
    "pl": [
        "muszę jeszcze sprawdzić logi z serwera",
        "spotkanie przenieśmy na późniejsze popołudnie",
        "dodaj proszę to zadanie do backlogu",
        "mam dzisiaj dużo rzeczy do zrobienia",
        "potrzebuję chwili na poprawki w konfiguracji",
        "to rozwiązanie wygląda dużo stabilniej",
        "ustawmy przypomnienie na jutro rano",
        "najpierw zróbmy szybki test integracyjny",
    ],
    "ru": [
        "мне нужно проверить последние изменения",
        "давай перенесем встречу на вечер",
        "добавь пожалуйста эту задачу в план",
        "сегодня у меня плотный график",
        "сначала я прогоню быстрый smoke test",
        "эта версия выглядит более стабильно",
        "поставь напоминание на завтра утром",
        "я подключусь к звонку через пять минут",
    ],
}


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^0-9a-zа-яёąćęłńóśźż\s]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def choose_language_sequence(mix: str, density: str, rng: random.Random) -> list[str]:
    langs = mix.split("_")
    if density == "low":
        length = 2
    elif density == "medium":
        length = 3
    else:
        length = 5 if len(langs) == 2 else 6

    sequence = [rng.choice(langs)]
    for _ in range(length - 1):
        candidates = [lang for lang in langs if lang != sequence[-1]]
        sequence.append(rng.choice(candidates))
    return sequence


def build_sample_text(
    sequence: list[str], rng: random.Random
) -> tuple[str, list[dict[str, str]]]:
    segments: list[dict[str, str]] = []
    for lang in sequence:
        segment = rng.choice(LANG_SEGMENTS[lang]).strip()
        segment = segment[0].upper() + segment[1:] + "."
        segments.append({"lang": lang, "text": segment})

    raw_text = " ".join(item["text"] for item in segments)
    return raw_text, segments


def target_duration(duration_bucket: str, rng: random.Random) -> float:
    low, high = DURATION_SEC_RANGE[duration_bucket]
    return round(rng.uniform(low, high), 2)


def lang_spans_from_segments(
    segments: list[dict[str, str]],
) -> list[dict[str, int | str]]:
    spans: list[dict[str, int | str]] = []
    cursor = 0
    for segment in segments:
        text = segment["text"]
        start_char = cursor
        end_char = start_char + len(text)
        spans.append(
            {"lang": segment["lang"], "start_char": start_char, "end_char": end_char}
        )
        cursor = end_char + 1
    return spans


def switch_points_from_spans(spans: list[dict[str, int | str]]) -> list[int]:
    return [int(span["start_char"]) for span in spans[1:]]


def switch_pattern_for_sequence(sequence: list[str]) -> str:
    mapping: dict[str, str] = {}
    next_letter = ord("A")
    pattern: list[str] = []
    for lang in sequence:
        if lang not in mapping:
            mapping[lang] = chr(next_letter)
            next_letter += 1
        pattern.append(mapping[lang])
    return "_".join(pattern)


def generate_rows(seed: int, per_cell: int, speaker_id: str) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []

    for mix in MIXES:
        for density in DENSITIES:
            for duration_bucket in DURATIONS:
                for index in range(1, per_cell + 1):
                    seq = choose_language_sequence(mix=mix, density=density, rng=rng)
                    raw_text, segments = build_sample_text(seq, rng)
                    base_id = f"{mix}_{density}_{duration_bucket}_{index:04d}"
                    text_uid = f"txt_{base_id}"
                    prompt_id = f"pr_{base_id}"
                    canonical_text = normalize_text(raw_text)
                    target_lang_spans = lang_spans_from_segments(segments)
                    rows.append(
                        {
                            "id": base_id,
                            "text_uid": text_uid,
                            "prompt_id": prompt_id,
                            "raw_text": raw_text,
                            "display_text": raw_text,
                            "normalized_text": canonical_text,
                            "canonical_text": canonical_text,
                            "segments": segments,
                            "target_lang_spans": target_lang_spans,
                            "switch_points": switch_points_from_spans(
                                target_lang_spans
                            ),
                            "switch_pattern": switch_pattern_for_sequence(seq),
                            "switch_count": max(0, len(segments) - 1),
                            "speaker_id": speaker_id,
                            "target_duration_sec": target_duration(
                                duration_bucket, rng
                            ),
                            "mix": mix,
                            "language_combo": mix,
                            "density": density,
                            "duration_bucket": duration_bucket,
                            "seed": seed,
                        }
                    )
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("data/manifests/prompts_v1.jsonl")
    )
    parser.add_argument("--seed", type=int, default=5090)
    parser.add_argument("--per-cell", type=int, default=10)
    parser.add_argument("--speaker-id", default="synthetic_voice_01")
    args = parser.parse_args()

    rows = generate_rows(
        seed=args.seed, per_cell=args.per_cell, speaker_id=args.speaker_id
    )
    write_jsonl(args.out, rows)
    print(f"Wrote {len(rows)} prompt rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
