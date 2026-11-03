#!/usr/bin/env python3
"""Turn aggregate JSON into a short markdown summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    lines = [
        "# Summary",
        "",
        f"- Samples: {report.get('count', 0)}",
        "",
        "## Notes",
    ]
    for note in report.get("notes", []):
        lines.append(f"- {note}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
