#!/usr/bin/env python3
"""Create `noise_light` and `reverb_light` variants from clean wav files."""

from __future__ import annotations

import argparse
import json
import math
import random
import struct
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


def read_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"Only 16-bit PCM wav is supported: {path}")
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())

    samples_i16 = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    if channels == 1:
        mono = [s / 32768.0 for s in samples_i16]
    else:
        mono = []
        for i in range(0, len(samples_i16), channels):
            chunk = samples_i16[i : i + channels]
            mono.append((sum(chunk) / len(chunk)) / 32768.0)
    return mono, sample_rate


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    pcm = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, sample))
        pcm.extend(struct.pack("<h", int(value * 32767.0)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))


def add_light_noise(
    samples: list[float], rng: random.Random, snr_db: float = 26.0
) -> list[float]:
    signal_power = sum(s * s for s in samples) / max(1, len(samples))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    noise_std = math.sqrt(max(noise_power, 1e-12))

    out: list[float] = []
    for sample in samples:
        noisy = sample + rng.gauss(0.0, noise_std)
        out.append(max(-1.0, min(1.0, noisy)))
    return out


def add_light_reverb(samples: list[float], sample_rate: int) -> list[float]:
    delay_a = max(1, int(0.018 * sample_rate))
    delay_b = max(1, int(0.041 * sample_rate))

    out: list[float] = [0.0] * len(samples)
    for i, dry in enumerate(samples):
        a = out[i - delay_a] if i >= delay_a else 0.0
        b = out[i - delay_b] if i >= delay_b else 0.0
        wet = dry + 0.45 * a + 0.25 * b
        mixed = 0.78 * dry + 0.22 * wet
        out[i] = max(-1.0, min(1.0, mixed))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-in", required=True, type=Path)
    parser.add_argument("--audio-root", type=Path, default=Path("data/audio"))
    parser.add_argument("--seed", type=int, default=5090)
    args = parser.parse_args()

    rows = read_jsonl(args.manifest_in)
    rng = random.Random(args.seed)

    created = 0
    for row in rows:
        mix = row["mix"]
        base_id = row["id"]

        clean_path = args.audio_root / mix / "clean" / f"{base_id}.wav"
        if not clean_path.exists():
            raise FileNotFoundError(f"Missing clean file: {clean_path}")

        samples, sample_rate = read_wav(clean_path)

        noise_path = args.audio_root / mix / "noise_light" / f"{base_id}.wav"
        reverb_path = args.audio_root / mix / "reverb_light" / f"{base_id}.wav"

        write_wav(noise_path, add_light_noise(samples, rng), sample_rate)
        write_wav(reverb_path, add_light_reverb(samples, sample_rate), sample_rate)
        created += 2

    print(f"Created {created} augmented files under {args.audio_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
