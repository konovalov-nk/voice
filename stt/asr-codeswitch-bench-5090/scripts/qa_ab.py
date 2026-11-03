#!/usr/bin/env python3
"""Simple interactive A/B listening test for two manifests.

Usage example:
python3 scripts/qa_ab.py \
  --manifest-a data/manifests/synthetic_v1.jsonl \
  --manifest-b data/manifests/synthetic_v2.jsonl \
  --label-a v1 --label-b v2 \
  --count 40 --condition clean --mix en_ru \
  --out results/ab_en_ru_clean.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Pair:
    sample_id: str
    a_path: Path
    b_path: Path
    condition: str
    mix: str
    density: str
    duration_bucket: str
    display_text: str
    canonical_text: str
    segments: list[dict[str, Any]]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_pairs(
    manifest_a: Path,
    manifest_b: Path,
    mix: str | None,
    condition: str | None,
    density: str | None,
    duration_bucket: str | None,
) -> list[Pair]:
    rows_a = {r["id"]: r for r in read_jsonl(manifest_a)}
    rows_b = {r["id"]: r for r in read_jsonl(manifest_b)}
    common = sorted(set(rows_a) & set(rows_b))

    pairs: list[Pair] = []
    for sample_id in common:
        ra = rows_a[sample_id]
        rb = rows_b[sample_id]

        if mix and ra.get("mix") != mix:
            continue
        if condition and ra.get("condition") != condition:
            continue
        if density and ra.get("density") != density:
            continue
        if duration_bucket and ra.get("duration_bucket") != duration_bucket:
            continue

        pairs.append(
            Pair(
                sample_id=sample_id,
                a_path=Path(ra["audio_path"]),
                b_path=Path(rb["audio_path"]),
                condition=str(ra.get("condition", "")),
                mix=str(ra.get("mix", "")),
                density=str(ra.get("density", "")),
                duration_bucket=str(ra.get("duration_bucket", "")),
                display_text=str(ra.get("display_text", ra.get("raw_text", ""))),
                canonical_text=str(
                    ra.get("canonical_text", ra.get("normalized_text", ""))
                ),
                segments=list(ra.get("segments", [])),
            )
        )
    return pairs


def play_audio(path: Path) -> None:
    subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)],
        check=False,
    )


def ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-a", required=True, type=Path)
    parser.add_argument("--manifest-b", required=True, type=Path)
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=5090)
    parser.add_argument("--mix", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--density", default=None)
    parser.add_argument("--duration-bucket", default=None)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--show-canonical", action="store_true")
    parser.add_argument("--hide-segments", action="store_true")
    args = parser.parse_args()

    pairs = load_pairs(
        manifest_a=args.manifest_a,
        manifest_b=args.manifest_b,
        mix=args.mix,
        condition=args.condition,
        density=args.density,
        duration_bucket=args.duration_bucket,
    )
    if not pairs:
        raise SystemExit("No overlapping samples found for selected filters.")

    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    pairs = pairs[: min(args.count, len(pairs))]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "mix",
                "condition",
                "density",
                "duration_bucket",
                "first_label",
                "second_label",
                "winner",
                "accent_leakage_score",
                "word_corruption_score",
                "boundary_artifact_score",
                "note",
            ],
        )
        writer.writeheader()

        print(f"Starting A/B listening for {len(pairs)} samples")
        print("Controls: [1]=play first, [2]=play second, [w]=submit result, [q]=quit")
        print("Winner values: 1, 2, tie")

        for i, pair in enumerate(pairs, start=1):
            order = [
                ("first", args.label_a, pair.a_path),
                ("second", args.label_b, pair.b_path),
            ]
            if rng.random() < 0.5:
                order = [
                    ("first", args.label_b, pair.b_path),
                    ("second", args.label_a, pair.a_path),
                ]

            print("-" * 72)
            print(
                f"[{i}/{len(pairs)}] {pair.sample_id} | {pair.mix} {pair.condition} {pair.density} {pair.duration_bucket}"
            )
            print("Text:")
            print(
                textwrap.fill(
                    pair.display_text,
                    width=100,
                    initial_indent="  ",
                    subsequent_indent="  ",
                )
            )
            if args.show_canonical:
                print("Canonical:")
                print(
                    textwrap.fill(
                        pair.canonical_text,
                        width=100,
                        initial_indent="  ",
                        subsequent_indent="  ",
                    )
                )
            if not args.hide_segments and pair.segments:
                print("Segments:")
                for seg in pair.segments:
                    lang = str(seg.get("lang", "?"))
                    text = str(seg.get("text", ""))
                    print(
                        textwrap.fill(
                            text,
                            width=100,
                            initial_indent=f"  [{lang}] ",
                            subsequent_indent="       ",
                        )
                    )

            while True:
                cmd = ask("Command (1/2/w/q): ")
                if cmd == "1":
                    play_audio(order[0][2])
                elif cmd == "2":
                    play_audio(order[1][2])
                elif cmd == "q":
                    print(f"Stopped early. Partial results saved to {args.out}")
                    return 0
                elif cmd == "w":
                    winner = ask("Winner (1/2/tie): ")
                    if winner not in {"1", "2", "tie"}:
                        print("Invalid winner value")
                        continue
                    accent = ask("accent_leakage_score (0-3): ")
                    corruption = ask("word_corruption_score (0-3): ")
                    boundary = ask("boundary_artifact_score (0-3): ")
                    note = input("note (optional): ").strip()

                    writer.writerow(
                        {
                            "sample_id": pair.sample_id,
                            "mix": pair.mix,
                            "condition": pair.condition,
                            "density": pair.density,
                            "duration_bucket": pair.duration_bucket,
                            "first_label": order[0][1],
                            "second_label": order[1][1],
                            "winner": winner,
                            "accent_leakage_score": accent,
                            "word_corruption_score": corruption,
                            "boundary_artifact_score": boundary,
                            "note": note,
                        }
                    )
                    f.flush()
                    break
                else:
                    print("Unknown command")

    print(f"Done. Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
