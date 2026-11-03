#!/usr/bin/env python3
"""Render clean audio with Fish Audio S2.

Two execution modes:
- server: start one persistent Fish API container and send /v1/tts requests
- cli: invoke Fish text2semantic CLI per segment (legacy, much slower)
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import statistics
import struct
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"Only 16-bit PCM wav is supported: {path}")

    raw = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    if channels == 1:
        mono = [x / 32768.0 for x in raw]
    else:
        mono = []
        for i in range(0, len(raw), channels):
            chunk = raw[i : i + channels]
            mono.append((sum(chunk) / len(chunk)) / 32768.0)
    return mono, sample_rate


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    pcm = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        pcm.extend(struct.pack("<h", int(value * 32767.0)))

    ensure_parent(path)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))


def rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples))


def gain_match(samples: list[float], target_rms: float) -> tuple[list[float], float]:
    source_rms = rms(samples)
    if source_rms <= 1e-7 or target_rms <= 1e-7:
        return samples, 0.0
    ratio = target_rms / source_rms
    ratio = max(10 ** (-6 / 20), min(10 ** (6 / 20), ratio))
    gain_db = 20.0 * math.log10(ratio)
    adjusted = [max(-1.0, min(1.0, x * ratio)) for x in samples]
    return adjusted, gain_db


def stitch_segments(
    segments: list[list[float]], sample_rate: int, pause_ms: int, xfade_ms: int
) -> tuple[list[float], list[dict[str, int]], list[int], list[int]]:
    if not segments:
        return [], [], [], []

    pause_samples = int(sample_rate * (pause_ms / 1000.0))
    xfade_samples = int(sample_rate * (xfade_ms / 1000.0))

    out = segments[0][:]
    bounds = [{"start": 0, "end": len(out)}]
    pause_before_ms = [0]
    pause_after_ms = [pause_ms if len(segments) > 1 else 0]

    for idx in range(1, len(segments)):
        prev_pause = pause_after_ms[idx - 1]
        if prev_pause > 0 and pause_samples > 0:
            out.extend([0.0] * pause_samples)

        current = segments[idx]
        overlap = 0
        if prev_pause == 0 and xfade_samples > 0:
            overlap = min(xfade_samples, len(out), len(current))

        if overlap > 0:
            start = len(out) - overlap
            for i in range(overlap):
                fade_out = (overlap - 1 - i) / max(1, overlap - 1)
                fade_in = i / max(1, overlap - 1)
                out[start + i] = out[start + i] * fade_out + current[i] * fade_in
            out.extend(current[overlap:])
            seg_start = start
        else:
            seg_start = len(out)
            out.extend(current)

        seg_end = len(out)
        bounds.append({"start": seg_start, "end": seg_end})
        pause_before_ms.append(0)
        pause_after_ms.append(pause_ms if idx < len(segments) - 1 else 0)

    return out, bounds, pause_before_ms, pause_after_ms


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def docker_python_cmd(
    image: str, workspace: Path, args: list[str], use_gpu: bool
) -> list[str]:
    cmd = ["docker", "run", "--rm"]
    if use_gpu:
        cmd.extend(["--gpus", "all"])
    cmd.extend(
        [
            "--entrypoint",
            "/app/.venv/bin/python",
            "-v",
            f"{workspace}:/workspace:Z",
            image,
        ]
    )
    cmd.extend(args)
    return cmd


def ensure_prompt_tokens(
    image: str,
    workspace: Path,
    checkpoints_dir: Path,
    prompt_root: Path,
    refs: dict[str, Path],
    use_gpu: bool,
    device: str,
) -> dict[str, Path]:
    prompt_root.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    for lang, ref_wav in refs.items():
        prompt_npy = prompt_root / f"{lang}_prompt.npy"
        prompt_wav = prompt_root / f"{lang}_prompt.wav"
        out[lang] = prompt_npy
        if prompt_npy.exists():
            continue

        cmd = docker_python_cmd(
            image=image,
            workspace=workspace,
            args=[
                "/app/fish_speech/models/dac/inference.py",
                "-i",
                f"/workspace/{ref_wav.as_posix()}",
                "-o",
                f"/workspace/{prompt_wav.as_posix()}",
                "--checkpoint-path",
                f"/workspace/{(checkpoints_dir / 'codec.pth').as_posix()}",
                "--device",
                device,
            ],
            use_gpu=use_gpu,
        )
        subprocess.run(cmd, check=True)

    return out


def write_segment_metadata(
    meta_path: Path,
    row: dict[str, Any],
    segment_rows: list[dict[str, Any]],
    rendered_bounds_ms: list[dict[str, Any]],
    speaker_ref_by_lang: dict[str, str],
    xfade_ms: int,
) -> None:
    payload = {
        "sample_id": row.get("id"),
        "text_uid": row.get("text_uid"),
        "render_mode": "segment_stitch",
        "speaker_ref_by_lang": speaker_ref_by_lang,
        "segments_rendered": segment_rows,
        "rendered_segment_bounds_ms": rendered_bounds_ms,
        "xfade_ms": xfade_ms,
        "engine_model_id": "fishaudio/s2-pro",
    }
    ensure_parent(meta_path)
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def check_container_running(name: str) -> bool:
    cmd = ["docker", "ps", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"]
    result = run(cmd)
    return name in result.stdout.strip().splitlines()


def wait_for_health(base_url: str, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    health_url = f"{base_url}/v1/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(1.0)
    raise TimeoutError(
        f"Fish API did not become healthy in {timeout_sec}s: {health_url}"
    )


def start_fish_server(args: argparse.Namespace, workspace: Path) -> tuple[str, bool]:
    if args.server_url:
        base_url = args.server_url.rstrip("/")
        wait_for_health(base_url, args.server_health_timeout)
        return base_url, False

    name = args.server_name
    base_url = f"http://127.0.0.1:{args.server_port}"

    running = check_container_running(name)
    if running and not args.server_reuse:
        subprocess.run(["docker", "stop", name], check=False)
        running = False

    if not running:
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-p",
            f"{args.server_port}:8080",
        ]
        if args.device == "cuda":
            cmd.extend(["--gpus", "all"])
        cmd.extend(
            [
                "-v",
                f"{workspace}:/workspace:Z",
                "-w",
                "/workspace",
                "--entrypoint",
                "/app/.venv/bin/python",
                args.fish_image,
                "/app/tools/api_server.py",
                "--listen",
                "0.0.0.0:8080",
                "--device",
                args.device,
                "--llama-checkpoint-path",
                f"/workspace/{args.checkpoints_dir.as_posix()}",
                "--decoder-checkpoint-path",
                f"/workspace/{(args.checkpoints_dir / 'codec.pth').as_posix()}",
            ]
        )
        subprocess.run(cmd, check=True)
        started_here = True
    else:
        started_here = False

    wait_for_health(base_url, args.server_health_timeout)
    return base_url, started_here


def stop_fish_server(name: str) -> None:
    subprocess.run(["docker", "stop", name], check=False)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (p / 100.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def write_latency_report(
    out_path: Path,
    segment_rows: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    request_ms = [float(x["request_ms"]) for x in segment_rows]
    connect_ms = [float(x["connect_ms"]) for x in segment_rows]
    read_ms = [float(x["read_ms"]) for x in segment_rows]
    rtf = [float(x["rtf"]) for x in segment_rows if x.get("rtf") is not None]

    payload = {
        "metadata": metadata,
        "aggregate": {
            "segments": len(segment_rows),
            "samples": len(sample_rows),
            "request_ms": {
                "mean": round(statistics.fmean(request_ms), 2) if request_ms else 0.0,
                "p50": round(percentile(request_ms, 50), 2),
                "p95": round(percentile(request_ms, 95), 2),
            },
            "connect_ms": {
                "mean": round(statistics.fmean(connect_ms), 2) if connect_ms else 0.0,
                "p50": round(percentile(connect_ms, 50), 2),
                "p95": round(percentile(connect_ms, 95), 2),
            },
            "read_ms": {
                "mean": round(statistics.fmean(read_ms), 2) if read_ms else 0.0,
                "p50": round(percentile(read_ms, 50), 2),
                "p95": round(percentile(read_ms, 95), 2),
            },
            "rtf": {
                "mean": round(statistics.fmean(rtf), 4) if rtf else None,
                "p50": round(percentile(rtf, 50), 4) if rtf else None,
                "p95": round(percentile(rtf, 95), 4) if rtf else None,
            },
        },
        "by_segment": segment_rows,
        "by_sample": sample_rows,
    }
    ensure_parent(out_path)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def tts_server_render(
    base_url: str,
    text: str,
    ref_wav: Path,
    ref_text: str,
    out_path: Path,
    timeout_sec: int,
) -> dict[str, float]:
    audio_b64 = base64.b64encode(ref_wav.read_bytes()).decode("ascii")
    payload = {
        "text": text,
        "references": [{"audio": audio_b64, "text": ref_text}],
        "reference_id": None,
        "format": "wav",
        "streaming": False,
        "normalize": True,
        "max_new_tokens": 1024,
        "chunk_length": 200,
        "top_p": 0.8,
        "repetition_penalty": 1.1,
        "temperature": 0.8,
        "use_memory_cache": "on",
        "seed": None,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=f"{base_url}/v1/tts",
        data=body,
        headers={"content-type": "application/json", "accept": "audio/wav"},
        method="POST",
    )
    try:
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            headers_ready = time.perf_counter()
            audio_bytes = resp.read()
            finished = time.perf_counter()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Fish API HTTP {exc.code}: {detail}") from exc

    ensure_parent(out_path)
    out_path.write_bytes(audio_bytes)
    return {
        "request_ms": (finished - started) * 1000.0,
        "connect_ms": (headers_ready - started) * 1000.0,
        "read_ms": (finished - headers_ready) * 1000.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-in", required=True, type=Path)
    parser.add_argument("--audio-root", type=Path, default=Path("data/audio_fish"))
    parser.add_argument(
        "--segment-root", type=Path, default=Path("data/intermediate_fish")
    )
    parser.add_argument("--fish-cache-root", type=Path, default=Path(".fish"))
    parser.add_argument(
        "--checkpoints-dir", type=Path, default=Path("checkpoints/s2-pro")
    )
    parser.add_argument("--fish-image", default="fishaudio/fish-speech:latest")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--mode", choices=("server", "cli"), default="server")
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--pause-ms", type=int, default=60)
    parser.add_argument("--xfade-ms", type=int, default=40)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument(
        "--no-skip-existing", dest="skip_existing", action="store_false"
    )
    parser.add_argument("--server-url", default="")
    parser.add_argument("--server-port", type=int, default=18080)
    parser.add_argument("--server-name", default="fish-s2-api")
    parser.add_argument("--server-health-timeout", type=int, default=180)
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--latency-out", type=Path, default=None)
    parser.add_argument("--latency-label", default="")
    parser.add_argument("--server-reuse", action="store_true", default=True)
    parser.add_argument("--no-server-reuse", dest="server_reuse", action="store_false")
    parser.add_argument("--keep-server", action="store_true", default=False)
    args = parser.parse_args()

    workspace = Path.cwd().resolve()
    refs = {"en": Path("en.wav"), "pl": Path("pl.wav"), "ru": Path("ru.wav")}
    ref_text = {
        "en": Path("en.txt").read_text(encoding="utf-8").strip().replace("\n", " "),
        "pl": Path("pl.txt").read_text(encoding="utf-8").strip().replace("\n", " "),
        "ru": Path("ru.txt").read_text(encoding="utf-8").strip().replace("\n", " "),
    }

    for lang, p in refs.items():
        if not p.exists():
            raise FileNotFoundError(f"Missing reference wav for {lang}: {p}")
    if not args.checkpoints_dir.exists():
        raise FileNotFoundError(
            f"Missing checkpoints dir: {args.checkpoints_dir}. Download with `hf download fishaudio/s2-pro --local-dir checkpoints/s2-pro`"
        )

    use_gpu = args.device == "cuda"
    prompt_tokens: dict[str, Path] = {}
    base_url = ""
    started_server = False

    if args.mode == "cli":
        prompt_tokens = ensure_prompt_tokens(
            image=args.fish_image,
            workspace=workspace,
            checkpoints_dir=args.checkpoints_dir,
            prompt_root=args.fish_cache_root / "prompts",
            refs=refs,
            use_gpu=use_gpu,
            device=args.device,
        )
    else:
        base_url, started_server = start_fish_server(args, workspace)
        print(f"Fish API ready: {base_url}")

    rows = read_jsonl(args.manifest_in)
    if args.count > 0:
        rows = rows[: args.count]

    rendered = 0
    skipped = 0
    latency_segments: list[dict[str, Any]] = []
    latency_samples: list[dict[str, Any]] = []
    try:
        for row in rows:
            mix = row["mix"]
            base_id = row["id"]
            out_path = args.audio_root / mix / "clean" / f"{base_id}.wav"
            ensure_parent(out_path)
            if args.skip_existing and out_path.exists():
                skipped += 1
                continue

            seg_root = args.segment_root / mix / "clean" / base_id
            seg_root.mkdir(parents=True, exist_ok=True)

            segments = row.get("segments") or []
            if not segments:
                raise ValueError(f"Missing segments for row {base_id}")

            segment_audio_arrays: list[list[float]] = []
            segment_rows: list[dict[str, Any]] = []
            sample_rate: int | None = None
            sample_request_ms = 0.0
            sample_audio_ms = 0.0

            for idx, segment in enumerate(segments, start=1):
                lang = str(segment["lang"])
                text = str(segment["text"])
                seg_id = f"seg_{idx:02d}"
                seg_path = seg_root / f"{seg_id}_{lang}.wav"

                if args.mode == "server":
                    latency = tts_server_render(
                        base_url=base_url,
                        text=text,
                        ref_wav=refs[lang],
                        ref_text=ref_text[lang],
                        out_path=seg_path,
                        timeout_sec=args.request_timeout,
                    )
                else:
                    cmd = docker_python_cmd(
                        image=args.fish_image,
                        workspace=workspace,
                        args=[
                            "/app/fish_speech/models/text2semantic/inference.py",
                            "--text",
                            text,
                            "--prompt-text",
                            ref_text[lang],
                            "--prompt-tokens",
                            f"/workspace/{prompt_tokens[lang].as_posix()}",
                            "--checkpoint-path",
                            f"/workspace/{args.checkpoints_dir.as_posix()}",
                            "--device",
                            args.device,
                            "--output",
                            f"/workspace/{seg_path.as_posix()}",
                            "--output-dir",
                            f"/workspace/{seg_root.as_posix()}",
                        ],
                        use_gpu=use_gpu,
                    )
                    subprocess.run(cmd, check=True)
                    latency = {
                        "request_ms": None,
                        "connect_ms": None,
                        "read_ms": None,
                    }

                seg_samples, seg_sr = read_wav(seg_path)
                if sample_rate is None:
                    sample_rate = seg_sr
                elif sample_rate != seg_sr:
                    raise ValueError(
                        f"Segment sample rate mismatch: {sample_rate} vs {seg_sr}"
                    )

                segment_audio_arrays.append(seg_samples)
                duration_ms = (len(seg_samples) * 1000.0) / seg_sr
                request_ms = (
                    float(latency["request_ms"])
                    if latency["request_ms"] is not None
                    else None
                )
                rtf = None
                if request_ms is not None and duration_ms > 1e-6:
                    rtf = (request_ms / 1000.0) / (duration_ms / 1000.0)

                if request_ms is not None:
                    connect_ms = (
                        float(latency["connect_ms"])
                        if latency["connect_ms"] is not None
                        else 0.0
                    )
                    read_ms = (
                        float(latency["read_ms"])
                        if latency["read_ms"] is not None
                        else 0.0
                    )
                    sample_request_ms += request_ms
                    sample_audio_ms += duration_ms
                    latency_segments.append(
                        {
                            "sample_id": base_id,
                            "segment_id": seg_id,
                            "lang": lang,
                            "chars": len(text),
                            "duration_ms": round(duration_ms, 2),
                            "request_ms": round(request_ms, 2),
                            "connect_ms": round(connect_ms, 2),
                            "read_ms": round(read_ms, 2),
                            "rtf": round(rtf, 4) if rtf is not None else None,
                        }
                    )

                segment_rows.append(
                    {
                        "segment_id": seg_id,
                        "lang": lang,
                        "text": text,
                        "segment_audio_path": seg_path.as_posix(),
                        "gain_db": 0.0,
                        "pause_before_ms": 0,
                        "pause_after_ms": 0,
                    }
                )

            assert sample_rate is not None
            target_rms = rms(segment_audio_arrays[0])
            for i in range(len(segment_audio_arrays)):
                adjusted, gain_db = gain_match(segment_audio_arrays[i], target_rms)
                segment_audio_arrays[i] = adjusted
                segment_rows[i]["gain_db"] = round(gain_db, 3)

            stitched, bounds, pause_before_ms, pause_after_ms = stitch_segments(
                segments=segment_audio_arrays,
                sample_rate=sample_rate,
                pause_ms=args.pause_ms,
                xfade_ms=args.xfade_ms,
            )
            for i in range(len(segment_rows)):
                segment_rows[i]["pause_before_ms"] = pause_before_ms[i]
                segment_rows[i]["pause_after_ms"] = pause_after_ms[i]

            rendered_bounds_ms = []
            for i, bound in enumerate(bounds):
                rendered_bounds_ms.append(
                    {
                        "segment_id": segment_rows[i]["segment_id"],
                        "start_ms": int(round(bound["start"] * 1000.0 / sample_rate)),
                        "end_ms": int(round(bound["end"] * 1000.0 / sample_rate)),
                    }
                )

            write_wav(out_path, stitched, sample_rate)
            write_segment_metadata(
                meta_path=out_path.with_suffix(".segments.json"),
                row=row,
                segment_rows=segment_rows,
                rendered_bounds_ms=rendered_bounds_ms,
                speaker_ref_by_lang={k: v.as_posix() for k, v in refs.items()},
                xfade_ms=args.xfade_ms,
            )
            rendered += 1
            if args.mode == "server" and sample_request_ms > 0:
                sample_rtf = None
                if sample_audio_ms > 1e-6:
                    sample_rtf = (sample_request_ms / 1000.0) / (
                        sample_audio_ms / 1000.0
                    )
                latency_samples.append(
                    {
                        "sample_id": base_id,
                        "segments": len(segment_rows),
                        "request_ms_total": round(sample_request_ms, 2),
                        "audio_ms_total": round(sample_audio_ms, 2),
                        "rtf": round(sample_rtf, 4) if sample_rtf is not None else None,
                    }
                )
    finally:
        if args.mode == "server" and started_server and not args.keep_server:
            stop_fish_server(args.server_name)

    print(f"Rendered {rendered} clean files under {args.audio_root}")
    if skipped:
        print(f"Skipped {skipped} existing files")
    if args.latency_out and args.mode == "server" and latency_segments:
        write_latency_report(
            out_path=args.latency_out,
            segment_rows=latency_segments,
            sample_rows=latency_samples,
            metadata={
                "model": "fishaudio/s2-pro",
                "label": args.latency_label,
                "server": base_url,
                "mode": args.mode,
                "device": args.device,
                "samples_rendered": rendered,
                "samples_skipped": skipped,
                "source_manifest": args.manifest_in.as_posix(),
                "generated_at_epoch": int(time.time()),
            },
        )
        print(f"Wrote latency report: {args.latency_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
