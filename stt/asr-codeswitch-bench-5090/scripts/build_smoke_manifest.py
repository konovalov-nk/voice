#!/usr/bin/env python3
"""Build a deterministic Stage-1 smoke manifest from full synthetic manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--condition", default="clean")
    parser.add_argument("--duration-buckets", nargs="+", default=["short", "medium"])
    parser.add_argument("--per-mix", type=int, default=5)
    args = parser.parse_args()

    rows = read_jsonl(args.manifest)
    filtered = [
        row
        for row in rows
        if row.get("condition") == args.condition
        and row.get("duration_bucket") in set(args.duration_buckets)
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in filtered:
        grouped.setdefault(row.get("mix", "unknown"), []).append(row)

    selected: list[dict[str, Any]] = []
    for mix, mix_rows in sorted(grouped.items()):
        mix_rows_sorted = sorted(mix_rows, key=lambda item: item.get("id", ""))
        selected.extend(mix_rows_sorted[: args.per_mix])

    if not selected:
        print("No rows selected. Check filters and input manifest.")
        return 1

    write_jsonl(args.out, selected)
    print(
        f"Wrote {len(selected)} rows to {args.out} "
        f"(condition={args.condition}, per_mix={args.per_mix}, "
        f"duration_buckets={','.join(args.duration_buckets)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
