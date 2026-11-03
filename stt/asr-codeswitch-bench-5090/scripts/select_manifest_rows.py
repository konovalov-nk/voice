#!/usr/bin/env python3
"""Select first N rows from a JSONL manifest.

If --count is 0, copy all rows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--count", type=int, default=0)
    args = parser.parse_args()

    rows: list[str] = []
    with args.manifest.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                # validate JSON line once
                json.loads(line)
                rows.append(line)

    if args.count > 0:
        rows = rows[: args.count]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row + "\n")

    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
