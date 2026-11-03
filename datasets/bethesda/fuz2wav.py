#!/usr/bin/env python3
"""Convert FUZ files from Bethesda BSA archives to WAV via ffmpeg — parallel."""

import argparse
import os
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def fuz_to_xwma(fuz_path: Path, xwma_path: Path) -> bool:
    with open(fuz_path, "rb") as f:
        data = f.read()

    if data[:4] != b"FUZE":
        return False

    lip_size = struct.unpack_from("<I", data, 8)[0]
    audio = data[16 + lip_size :]

    pkt_size = struct.unpack_from("<I", audio, 0)[0]
    chunks = audio[8 : 8 + pkt_size - 4]

    riff_size = 4 + len(chunks)
    riff = b"RIFF" + struct.pack("<I", riff_size) + b"XWMA" + chunks

    with open(xwma_path, "wb") as f:
        f.write(riff)

    return True


def xwma_to_wav(xwma_path: Path, wav_path: Path) -> bool:
    tmp_wav = wav_path.with_suffix(".part.wav")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v", "error",
                "-i", str(xwma_path),
                str(tmp_wav),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        tmp_wav.replace(wav_path)
        return True

    except subprocess.CalledProcessError:
        tmp_wav.unlink(missing_ok=True)
        return False


def convert_one(src: Path, dst: Path, fuz: Path, skip_existing: bool) -> tuple[bool, Path, str | None]:
    rel = fuz.relative_to(src).with_suffix(".wav")
    wav = dst / rel

    if skip_existing and wav.exists() and wav.stat().st_size > 0:
        return True, rel, "skipped"

    wav.parent.mkdir(parents=True, exist_ok=True)

    xwma_tmp = wav.with_suffix(f".{os.getpid()}.xwma")

    try:
        ok = fuz_to_xwma(fuz, xwma_tmp) and xwma_to_wav(xwma_tmp, wav)
        return ok, rel, None
    finally:
        xwma_tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert .fuz voice files to .wav in parallel"
    )
    parser.add_argument("src", type=Path, help="Source directory with .fuz files")
    parser.add_argument("dst", type=Path, nargs="?", help="Output directory (default: src parent)")
    parser.add_argument(
        "-j", "--workers", type=int,
        default=max(2, (os.cpu_count() or 4) // 2),
        help="Number of parallel workers"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip .wav files that already exist"
    )
    parser.add_argument(
        "--progress-every", type=int, default=500,
        help="Report progress every N files"
    )

    args = parser.parse_args()

    src = args.src
    dst = args.dst if args.dst else src.parent
    dst.mkdir(parents=True, exist_ok=True)

    fuz_files = list(src.rglob("*.fuz"))
    total = len(fuz_files)

    ok = fail = skipped = done = 0

    print(f"Found {total} .fuz files")
    print(f"Workers: {args.workers}")
    print(f"Output:  {dst}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(convert_one, src, dst, fuz, args.skip_existing)
            for fuz in fuz_files
        ]

        for future in as_completed(futures):
            success, rel, status = future.result()
            done += 1

            if status == "skipped":
                skipped += 1
            elif success:
                ok += 1
            else:
                fail += 1
                print(f"FAIL: {rel}")

            if done % args.progress_every == 0 or done == total:
                pct = done / total * 100 if total else 100
                print(
                    f"[{done}/{total}] {pct:.1f}% "
                    f"OK={ok} SKIP={skipped} FAIL={fail}"
                )

    print(f"\nDone: {ok} converted, {skipped} skipped, {fail} failed (of {total})")


if __name__ == "__main__":
    main()
