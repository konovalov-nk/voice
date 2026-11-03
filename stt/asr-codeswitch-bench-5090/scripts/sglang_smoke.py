#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path
from urllib import error, request


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SGLang speech smoke check")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--text", default="hello, this is a test")
    p.add_argument("--ref-audio", default="")
    p.add_argument("--ref-text", default="")
    p.add_argument("--out", default="results/sglang_smoke.wav")
    p.add_argument("--container-name", default="sglang-flashinfer-test")
    p.add_argument("--log-tail", type=int, default=2000)
    p.add_argument("--request-id", default="")
    return p.parse_args()


def _to_container_audio_path(path_value: str) -> str:
    if not path_value:
        return ""

    p = Path(path_value)
    if str(p).startswith("/workspace/"):
        return str(p)

    try:
        resolved = p.resolve()
        cwd = Path.cwd().resolve()
        rel = resolved.relative_to(cwd)
        return f"/workspace/{rel.as_posix()}"
    except Exception:
        return str(p)


def _parse_log_time(line: str) -> dt.datetime | None:
    if len(line) < 23:
        return None
    stamp = line[:23]
    try:
        return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None


def _extract_stage_times(
    *,
    container_name: str,
    request_id: str,
    tail: int,
) -> tuple[float | None, float | None]:
    try:
        proc = subprocess.run(
            ["podman", "logs", "--tail", str(tail), container_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None, None

    if proc.returncode != 0:
        return None, None

    t_enqueue = None
    t_tts_done = None
    t_vocoder_done = None
    tts_done_after_ms = None

    re_enqueue = re.compile(rf"tts_engine enqueue req={re.escape(request_id)}\b")
    re_tts_done = re.compile(rf"tts_engine done req={re.escape(request_id)}\b")
    re_vocoder_done = re.compile(rf"vocoder done req={re.escape(request_id)}\b")
    re_done_after = re.compile(r"engine get_result req=.* done_after=([0-9.]+)s")

    for line in proc.stdout.splitlines():
        ts = _parse_log_time(line)
        if ts is None:
            continue

        if re_enqueue.search(line):
            t_enqueue = ts
        elif "tts_engine enqueue req=" in line:
            t_enqueue = ts
        elif re_tts_done.search(line):
            t_tts_done = ts
        elif "tts_engine done req=" in line:
            t_tts_done = ts
        m = re_done_after.search(line)
        if m:
            try:
                tts_done_after_ms = float(m.group(1)) * 1000.0
            except Exception:
                pass
        elif re_vocoder_done.search(line):
            t_vocoder_done = ts
        elif "vocoder done req=" in line:
            t_vocoder_done = ts

    if t_enqueue is None and tts_done_after_ms is None:
        return None, None

    if t_enqueue is not None and t_tts_done is not None:
        tts_ms = (t_tts_done - t_enqueue).total_seconds() * 1000.0
    else:
        tts_ms = tts_done_after_ms
    voc_ms = (
        (t_vocoder_done - t_tts_done).total_seconds() * 1000.0
        if (t_vocoder_done and t_tts_done)
        else None
    )
    return tts_ms, voc_ms


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    request_id = args.request_id or f"smoke-{uuid.uuid4()}"

    payload_obj = {"input": args.text, "request_id": request_id}
    if args.ref_audio:
        payload_obj["ref_audio"] = _to_container_audio_path(args.ref_audio)
    if args.ref_text:
        payload_obj["ref_text"] = args.ref_text

    payload = json.dumps(payload_obj).encode("utf-8")
    req = request.Request(
        url=f"{args.base_url.rstrip('/')}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    ttfa = None
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            code = resp.getcode()
            first = resp.read(1)
            ttfa = time.perf_counter() - start
            body = first + resp.read()
    except error.HTTPError as exc:
        body = exc.read()
        print(f"smoke failed: http {exc.code}, body={body[:200]!r}")
        return 1
    except Exception as exc:
        print(f"smoke failed: {type(exc).__name__}: {exc}")
        return 1

    elapsed = time.perf_counter() - start
    if code != 200:
        print(f"smoke failed: unexpected status {code}")
        return 1

    out_path.write_bytes(body)

    try:
        with wave.open(str(out_path), "rb") as f:
            channels = f.getnchannels()
            rate = f.getframerate()
            frames = f.getnframes()
    except Exception as exc:
        print(f"smoke failed: invalid wav: {type(exc).__name__}: {exc}")
        return 1

    duration_s = frames / float(rate) if rate else 0.0
    rtf = (elapsed / duration_s) if duration_s > 0 else 0.0

    tts_ms, voc_ms = _extract_stage_times(
        container_name=args.container_name,
        request_id=request_id,
        tail=args.log_tail,
    )

    tts_field = f"{tts_ms:.1f}" if tts_ms is not None else "na"
    voc_field = f"{voc_ms:.1f}" if voc_ms is not None else "na"

    print(
        f"smoke ok: req={request_id} status=200 ttfa_s={ttfa:.3f} total_s={elapsed:.3f} rtf={rtf:.3f} tts_ms={tts_field} vocoder_ms={voc_field} channels={channels} rate={rate} frames={frames} duration_s={duration_s:.3f} out={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
