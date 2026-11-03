#!/usr/bin/env python3
"""
Parse vram_steps logs and show table + optional HTML chart.

Usage:
  python scripts/plot_vram_steps.py results/e2e_vram_20260315_091328/vram_steps_full.txt
  python scripts/plot_vram_steps.py results/e2e_vram_20260315_091328/
  cat vram_steps_*.txt | python scripts/plot_vram_steps.py -
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Log line: "... vram_step req=2cd310 step=inference_start  alloc_gb=14.42 max_gb=14.42"
# or "... vram_step req=3e9a40 step=segment_decode_start seg_idx=1 alloc_gb=14.15 max_gb=19.52"
VRAM_RE = re.compile(
    r"vram_step\s+req=(\S+)\s+step=(\S+)(?:\s+seg_idx=(\d+))?\s+alloc_gb=([\d.]+)\s+max_gb=([\d.]+)"
)


def parse_line(line: str) -> dict | None:
    m = VRAM_RE.search(line)
    if not m:
        return None
    req, step, seg_idx, alloc_gb, max_gb = m.groups()
    return {
        "req": req,
        "step": step,
        "seg_idx": int(seg_idx) if seg_idx else None,
        "alloc_gb": float(alloc_gb),
        "max_gb": float(max_gb),
        "label": f"{step}" + (f"[{seg_idx}]" if seg_idx else ""),
    }


def load_files(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.glob("vram_steps*.txt")):
                rows.extend(load_file(f))
        elif p.name == "-" or str(p) == "-":
            for line in sys.stdin:
                r = parse_line(line)
                if r:
                    rows.append(r)
        else:
            rows.extend(load_file(p))
    return rows


def load_file(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            r = parse_line(line)
            if r:
                rows.append(r)
    return rows


def table_text(rows: list[dict]) -> str:
    """Plain text table."""
    if not rows:
        return "(no vram_step lines found)"
    lines = []
    col_req = max(len(r["req"]) for r in rows)
    col_label = max(len(r["label"]) for r in rows)
    col_alloc = 8
    col_max = 8
    sep = "  "
    header = (
        "req".ljust(col_req)
        + sep
        + "step".ljust(col_label)
        + sep
        + "alloc_gb".rjust(col_alloc)
        + sep
        + "max_gb".rjust(col_max)
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in rows:
        lines.append(
            r["req"].ljust(col_req)
            + sep
            + r["label"].ljust(col_label)
            + sep
            + f"{r['alloc_gb']:.2f}".rjust(col_alloc)
            + sep
            + f"{r['max_gb']:.2f}".rjust(col_max)
        )
    return "\n".join(lines)


def table_rich(rows: list[dict]) -> None:
    """Rich table (if available)."""
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="VRAM steps", show_header=True)
        table.add_column("req", style="dim")
        table.add_column("step", style="cyan")
        table.add_column("alloc_gb", justify="right", style="green")
        table.add_column("max_gb", justify="right", style="yellow")
        for r in rows:
            table.add_row(
                r["req"],
                r["label"],
                f"{r['alloc_gb']:.2f}",
                f"{r['max_gb']:.2f}",
            )
        Console().print(table)
    except ImportError:
        print(table_text(rows))


def html_chart(rows: list[dict], out_path: Path, title: str = "VRAM steps") -> None:
    """Write HTML with SVG bar chart (no matplotlib)."""
    if not rows:
        return
    max_gb = max(r["max_gb"] for r in rows)
    max_gb = max(max_gb, 1)
    width = 800
    height = 24 * len(rows) + 80
    bar_height = 18
    bar_max_width = width - 200
    margin_left = 180

    bars_svg = []
    for i, r in enumerate(rows):
        y = 40 + i * (bar_height + 4)
        w = (r["alloc_gb"] / max_gb) * bar_max_width
        w_max = (r["max_gb"] / max_gb) * bar_max_width
        label = r["label"][:30]
        bars_svg.append(
            f'  <g>'
            f'<text x="5" y="{y + bar_height/2 + 4}" class="label">{label}</text>'
            f'<rect x="{margin_left}" y="{y}" width="{w_max}" height="{bar_height}" '
            f'fill="#444" rx="2"/>'
            f'<rect x="{margin_left}" y="{y}" width="{w}" height="{bar_height}" '
            f'fill="#3b82f6" rx="2"/>'
            f'<text x="{margin_left + bar_max_width + 8}" y="{y + bar_height/2 + 4}" '
            f'class="value">{r["alloc_gb"]:.1f} / {r["max_gb"]:.1f} GB</text>'
            f'</g>'
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 20px; background: #1a1a1a; color: #e5e5e5; }}
    h1 {{ font-size: 1.2rem; }}
    .label {{ font-size: 12px; fill: #94a3b8; }}
    .value {{ font-size: 11px; fill: #94a3b8; }}
    svg {{ margin: 10px 0; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>Blue = alloc_gb, dark = max_gb so far. Total steps: {len(rows)}</p>
  <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
{chr(10).join(bars_svg)}
  </svg>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse vram_steps logs, print table and/or HTML chart")
    ap.add_argument(
        "paths",
        nargs="*",
        default=["-"],
        help="Paths to vram_steps*.txt or dir (e.g. results/e2e_vram_*); '-' = stdin",
    )
    ap.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Write HTML chart to this file",
    )
    ap.add_argument(
        "--no-rich",
        action="store_true",
        help="Use plain text table instead of rich",
    )
    args = ap.parse_args()

    paths = [Path(p) for p in args.paths]
    if not paths or (len(paths) == 1 and paths[0].name == "-" and not sys.stdin.isatty()):
        paths = [Path("-")]

    rows = load_files(paths)
    if not rows:
        print("No vram_step lines found.", file=sys.stderr)
        sys.exit(1)

    if args.no_rich:
        print(table_text(rows))
    else:
        table_rich(rows)

    out = args.output
    if out is None and paths and paths[0] != Path("-"):
        first = paths[0]
        if first.is_dir():
            out = first / "vram_steps_chart.html"
        else:
            out = first.parent / "vram_steps_chart.html"
    if out:
        html_chart(rows, Path(out), title="VRAM by step")
        print(f"Chart written to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
