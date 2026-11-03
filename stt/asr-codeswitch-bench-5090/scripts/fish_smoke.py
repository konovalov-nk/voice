#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import re
import subprocess
import time
import wave
from pathlib import Path
from urllib import error, request

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fish API smoke check")
    p.add_argument("--base-url", default="http://127.0.0.1:18080")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--text", default="hello, this is a fish smoke test")
    p.add_argument("--ref-audio", default="")
    p.add_argument("--ref-text", default="")
    p.add_argument("--reference-id", default="")
    p.add_argument("--out", default="results/fish_smoke.wav")
    p.add_argument("--streaming", action="store_true")
    p.add_argument(
        "--chunk-length",
        type=int,
        default=200,
        help="Max bytes per batch (API allows 100-300). Smaller => more chunks for streaming.",
    )
    p.add_argument("--chunk-size", type=int, default=8192)
    p.add_argument("--min-stream-gap", type=float, default=0.2)
    p.add_argument("--min-chunks", type=int, default=2)
    p.add_argument("--stream-sample-rate", type=int, default=44100)
    p.add_argument("--stream-channels", type=int, default=1)
    p.add_argument("--container-name", default="fish-s2-api-compile")
    p.add_argument("--log-tail", type=int, default=4000)
    p.add_argument("--profile", action="store_true")
    return p.parse_args()


def _parse_log_ts(line: str) -> dt.datetime | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})", line)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        return None


def _profile_from_logs(
    container_name: str, tail: int, text: str
) -> dict[str, float | int]:
    proc = subprocess.run(
        ["docker", "logs", "--tail", str(tail), container_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {}

    lines = (proc.stdout + "\n" + proc.stderr).splitlines()
    anchor_idx = -1
    anchor_ts = None
    target = f"Batch text: {text}"
    for i, line in enumerate(lines):
        if target in line:
            ts = _parse_log_ts(line)
            if ts is not None:
                anchor_idx = i
                anchor_ts = ts

    if anchor_idx < 0 or anchor_ts is None:
        return {}

    encoded_ts = None
    generated_ts = None
    decode_ts = None
    ref_load_ts = None
    ref_encoded_ts = None

    for i in range(max(0, anchor_idx - 80), anchor_idx):
        line = lines[i]
        ts = _parse_log_ts(line)
        if ts is None:
            continue
        if "Loaded audio with" in line:
            ref_load_ts = ts
        elif "Encoded prompt:" in line and "vq_manager" in line:
            ref_encoded_ts = ts

    for i in range(anchor_idx, min(len(lines), anchor_idx + 160)):
        line = lines[i]
        ts = _parse_log_ts(line)
        if ts is None:
            continue
        if encoded_ts is None and "Encoded prompt shape:" in line:
            encoded_ts = ts
        elif generated_ts is None and "Generated" in line and "tokens in" in line:
            generated_ts = ts
        elif decode_ts is None and "decode_vq_tokens" in line and "VQ features" in line:
            decode_ts = ts

    out: dict[str, float | int] = {}
    if ref_load_ts and ref_encoded_ts:
        out["profile_ref_encode_ms"] = round(
            (ref_encoded_ts - ref_load_ts).total_seconds() * 1000.0, 1
        )
    if encoded_ts:
        out["profile_prompt_prepare_ms"] = round(
            (encoded_ts - anchor_ts).total_seconds() * 1000.0, 1
        )
    if encoded_ts and generated_ts:
        out["profile_generate_ms"] = round(
            (generated_ts - encoded_ts).total_seconds() * 1000.0, 1
        )
    if generated_ts and decode_ts:
        out["profile_decode_ms"] = round(
            (decode_ts - generated_ts).total_seconds() * 1000.0, 1
        )
    return out


def _wait_health(base_url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    url = f"{base_url.rstrip('/')}/v1/health"
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=2) as resp:
                if resp.getcode() == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"health check failed: {url}")


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    _wait_health(args.base_url, timeout_s=args.timeout)

    # API schema requires chunk_length in [100, 300]
    chunk_length = max(100, min(300, args.chunk_length))
    if chunk_length != args.chunk_length:
        print(
            f"fish smoke: chunk_length {args.chunk_length} clamped to {chunk_length} (API allows 100-300)"
        )

    payload = {
        "text": args.text,
        "reference_id": args.reference_id or None,
        "format": "wav",
        "streaming": bool(args.streaming),
        "normalize": True,
        "max_new_tokens": 1024,
        "chunk_length": chunk_length,
        "top_p": 0.8,
        "repetition_penalty": 1.1,
        "temperature": 0.8,
        "use_memory_cache": "on",
    }

    if args.ref_audio:
        ref_path = Path(args.ref_audio)
        payload["references"] = [
            {
                "audio": base64.b64encode(ref_path.read_bytes()).decode("ascii"),
                "text": args.ref_text,
            }
        ]

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{args.base_url.rstrip('/')}/v1/tts",
        data=body,
        headers={"content-type": "application/json", "accept": "audio/wav"},
        method="POST",
    )

    # WAV header is 44 bytes; first byte after that is first audio sample (TTFA to first sound).
    WAV_HEADER_SIZE = 44

    t0 = time.perf_counter()
    t1_audio = None  # time when first audio byte received (after header)
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            first = resp.read(1)
            t1 = time.perf_counter()
            chunks = [first]
            chunk_count = 1 if first else 0
            total_read = len(first)
            while True:
                chunk = resp.read(args.chunk_size)
                if not chunk:
                    break
                if t1_audio is None and total_read + len(chunk) > WAV_HEADER_SIZE:
                    t1_audio = time.perf_counter()
                chunks.append(chunk)
                total_read += len(chunk)
                chunk_count += 1
            t2 = time.perf_counter()
            audio_bytes = b"".join(chunks)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"fish smoke failed: http {exc.code}: {detail[:300]}")
        return 1
    except Exception as exc:
        print(f"fish smoke failed: {type(exc).__name__}: {exc}")
        return 1

    out_path.write_bytes(audio_bytes)

    duration_s = 0.0
    peak_dbfs = float("nan")
    rms_dbfs = float("nan")
    wav_ok = audio_bytes.startswith(b"RIFF")

    if wav_ok:
        with wave.open(str(out_path), "rb") as w:
            ch = w.getnchannels()
            sr = w.getframerate()
            sw = w.getsampwidth()
            n = w.getnframes()
            raw = w.readframes(n)

        if sw == 2:
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            print(f"fish smoke failed: unsupported wav sample width {sw}")
            return 1

        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)

        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        peak_dbfs = 20.0 * math.log10(max(peak, 1e-12))
        rms_dbfs = 20.0 * math.log10(max(rms, 1e-12))
        duration_s = n / float(sr) if sr else 0.0

    else:
        # Streaming endpoint may return raw PCM bytes (no RIFF header).
        # Wrap as a proper WAV so the file is playable in common players.
        pcm = np.frombuffer(audio_bytes, dtype=np.int16)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(args.stream_channels)
            w.setsampwidth(2)
            w.setframerate(args.stream_sample_rate)
            w.writeframes(pcm.tobytes())

        x = pcm.astype(np.float32) / 32768.0
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        peak_dbfs = 20.0 * math.log10(max(peak, 1e-12))
        rms_dbfs = 20.0 * math.log10(max(rms, 1e-12))
        duration_s = (len(pcm) / float(args.stream_channels)) / float(
            args.stream_sample_rate
        )

        raw_out = out_path.with_suffix(out_path.suffix + ".pcm")
        raw_out.write_bytes(audio_bytes)

    ttfa_s = t1 - t0  # time to first byte (WAV header start)
    ttfa_audio_s = (t1_audio - t0) if t1_audio is not None else ttfa_s  # time to first audio byte (after 44-byte header)
    total_s = t2 - t0

    rtf = total_s / duration_s if duration_s > 0 else 0.0

    stream_gap = total_s - ttfa_s
    if args.streaming and (
        stream_gap < args.min_stream_gap or chunk_count < args.min_chunks
    ):
        print(
            f"fish smoke failed: streaming check failed ttfa_s={ttfa_s:.3f} total_s={total_s:.3f} gap_s={stream_gap:.3f} chunks={chunk_count} (need gap>={args.min_stream_gap} and chunks>={args.min_chunks})"
        )
        return 1

    mode = "stream" if args.streaming else "oneshot"
    profile = (
        _profile_from_logs(args.container_name, args.log_tail, args.text)
        if args.profile
        else {}
    )
    profile_s = " ".join(f"{k}={v}" for k, v in sorted(profile.items()))
    profile_suffix = f" {profile_s}" if profile_s else ""
    if wav_ok:
        print(
            f"fish smoke ok: mode={mode} wav=1 ttfa_s={ttfa_s:.3f} ttfa_audio_s={ttfa_audio_s:.3f} total_s={total_s:.3f} gap_s={stream_gap:.3f} chunks={chunk_count} rtf={rtf:.3f} duration_s={duration_s:.3f} peak_dbfs={peak_dbfs:.2f} rms_dbfs={rms_dbfs:.2f} out={out_path}{profile_suffix}"
        )
    else:
        print(
            f"fish smoke ok: mode={mode} wav=0(wrapped) ttfa_s={ttfa_s:.3f} ttfa_audio_s={ttfa_audio_s:.3f} total_s={total_s:.3f} gap_s={stream_gap:.3f} chunks={chunk_count} rtf={rtf:.3f} duration_s={duration_s:.3f} peak_dbfs={peak_dbfs:.2f} rms_dbfs={rms_dbfs:.2f} out={out_path} raw={out_path.with_suffix(out_path.suffix + '.pcm')}{profile_suffix}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
