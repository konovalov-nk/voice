#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


def _wav_data_offset(buf: bytes) -> int | None:
    if len(buf) < 12:
        return None
    if buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        return None

    i = 12
    n = len(buf)
    while i + 8 <= n:
        chunk_id = buf[i : i + 4]
        chunk_size = int.from_bytes(buf[i + 4 : i + 8], "little")
        data_start = i + 8
        data_end = data_start + chunk_size
        if chunk_id == b"data":
            return data_start
        i = data_end + (chunk_size % 2)
    return None


def _pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    xs = sorted(values)
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


@dataclass
class RunResult:
    prompt_file: str
    run_index: int
    text_chars: int
    num_step: int
    ttfb_ms: float
    ttfa_ms: float
    total_ms: float
    server_gen_ms: float
    audio_duration_s: float
    audio_bytes: int
    rtf: float


def read_prompts(prompts_dir: Path, glob_expr: str) -> list[tuple[Path, str]]:
    files = sorted(prompts_dir.glob(glob_expr))
    prompts: list[tuple[Path, str]] = []
    for fp in files:
        if fp.is_file():
            text = fp.read_text(encoding="utf-8").strip()
            if text:
                prompts.append((fp, text))
    return prompts


def one_request(
    client: httpx.Client,
    url: str,
    text: str,
    language: str | None,
    num_step: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": text,
        "language": language,
        "num_step": num_step,
    }

    t0 = time.perf_counter()
    ttfb_s: float | None = None
    ttfa_s: float | None = None
    total_bytes = 0
    recv_buf = bytearray()

    with client.stream("POST", url, json=payload) as resp:
        resp.raise_for_status()
        headers = resp.headers
        for chunk in resp.iter_bytes():
            now = time.perf_counter()
            if ttfb_s is None and chunk:
                ttfb_s = now - t0

            recv_buf.extend(chunk)
            total_bytes += len(chunk)

            if ttfa_s is None:
                off = _wav_data_offset(recv_buf)
                if off is not None and len(recv_buf) > off:
                    ttfa_s = now - t0

        total_s = time.perf_counter() - t0

    ttfb_s = ttfb_s if ttfb_s is not None else total_s
    ttfa_s = ttfa_s if ttfa_s is not None else total_s
    gen_ms = float(headers.get("X-Gen-Time-Ms", "nan"))
    audio_s = float(headers.get("X-Audio-Duration-S", "nan"))

    return {
        "ttfb_ms": ttfb_s * 1000.0,
        "ttfa_ms": ttfa_s * 1000.0,
        "total_ms": total_s * 1000.0,
        "server_gen_ms": gen_ms,
        "audio_duration_s": audio_s,
        "audio_bytes": int(headers.get("X-Audio-Bytes", total_bytes)),
    }


def wait_for_health(client: httpx.Client, health_url: str, timeout_s: float) -> None:
    start = time.perf_counter()
    while time.perf_counter() - start <= timeout_s:
        try:
            resp = client.get(health_url)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Server did not become healthy: {health_url}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Benchmark OmniVoice API latency and throughput."
    )
    p.add_argument("--server-url", default="http://127.0.0.1:8765")
    p.add_argument("--prompts-dir", default="prompts")
    p.add_argument("--prompt-glob", default="*.txt")
    p.add_argument("--language", default=None)
    p.add_argument("--num-step", type=int, default=16)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmup-runs", type=int, default=1)
    p.add_argument("--timeout-s", type=float, default=1800.0)
    p.add_argument("--wait-health-s", type=float, default=30.0)
    p.add_argument("--output", default=None, help="Path to JSON result file.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    prompts = read_prompts(Path(args.prompts_dir), args.prompt_glob)
    if not prompts:
        raise RuntimeError(
            f"No prompt files found in {args.prompts_dir}/{args.prompt_glob}"
        )

    tts_url = args.server_url.rstrip("/") + "/tts"
    health_url = args.server_url.rstrip("/") + "/health"

    run_rows: list[RunResult] = []
    with httpx.Client(timeout=args.timeout_s) as client:
        wait_for_health(client, health_url, args.wait_health_s)

        warmup_text = prompts[0][1]
        for _ in range(args.warmup_runs):
            _ = one_request(client, tts_url, warmup_text, args.language, args.num_step)

        for prompt_file, text in prompts:
            for i in range(1, args.repeats + 1):
                r = one_request(client, tts_url, text, args.language, args.num_step)
                audio_s = r["audio_duration_s"]
                gen_s = r["server_gen_ms"] / 1000.0
                rtf = gen_s / audio_s if audio_s > 0 else float("nan")
                run_rows.append(
                    RunResult(
                        prompt_file=str(prompt_file),
                        run_index=i,
                        text_chars=len(text),
                        num_step=args.num_step,
                        ttfb_ms=r["ttfb_ms"],
                        ttfa_ms=r["ttfa_ms"],
                        total_ms=r["total_ms"],
                        server_gen_ms=r["server_gen_ms"],
                        audio_duration_s=audio_s,
                        audio_bytes=r["audio_bytes"],
                        rtf=rtf,
                    )
                )

    ttfb = [x.ttfb_ms for x in run_rows]
    ttfa = [x.ttfa_ms for x in run_rows]
    total = [x.total_ms for x in run_rows]
    gen = [x.server_gen_ms for x in run_rows]
    audio_s = [x.audio_duration_s for x in run_rows]
    rtf = [x.rtf for x in run_rows]

    summary = {
        "count": len(run_rows),
        "prompts": len(prompts),
        "repeats": args.repeats,
        "warmup_runs": args.warmup_runs,
        "num_step": args.num_step,
        "language": args.language,
        "ttfb_ms": {
            "avg": statistics.mean(ttfb),
            "p50": _pct(ttfb, 50),
            "p95": _pct(ttfb, 95),
            "min": min(ttfb),
            "max": max(ttfb),
        },
        "ttfa_ms": {
            "avg": statistics.mean(ttfa),
            "p50": _pct(ttfa, 50),
            "p95": _pct(ttfa, 95),
            "min": min(ttfa),
            "max": max(ttfa),
        },
        "total_ms": {
            "avg": statistics.mean(total),
            "p50": _pct(total, 50),
            "p95": _pct(total, 95),
        },
        "server_gen_ms": {
            "avg": statistics.mean(gen),
            "p50": _pct(gen, 50),
            "p95": _pct(gen, 95),
        },
        "audio_duration_s": {
            "avg": statistics.mean(audio_s),
            "p50": _pct(audio_s, 50),
            "p95": _pct(audio_s, 95),
        },
        "rtf": {
            "avg": statistics.mean(rtf),
            "p50": _pct(rtf, 50),
            "p95": _pct(rtf, 95),
            "min": min(rtf),
            "max": max(rtf),
        },
    }

    print("=== Benchmark Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out = {
        "summary": summary,
        "runs": [asdict(x) for x in run_rows],
    }
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
