#!/usr/bin/env python3
"""
Robust selective torch.compile benchmark for MisoTTS.

This script is designed to minimize the need to kill GPU processes between runs.

Usage examples:
    uv run python bench_selective_compile.py                    # baseline only
    uv run python bench_selective_compile.py --target backbone
    uv run python bench_selective_compile.py --target generate_frame
    uv run python bench_selective_compile.py --target all       # progressive on one load

Recommended before running:
    export HF_HUB_OFFLINE=1
    export PYTORCH_ALLOC_CONF=expandable_segments:True
"""

import os
import gc
import time
import argparse
import torch

# Set these as early as possible
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

from generator import load_miso_8b


def set_best_flags():
    """Best cheap flags we found so far."""
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch._inductor.config.coordinate_descent_tuning = True
    torch._inductor.config.triton.cudagraphs = True
    torch._inductor.config.max_autotune = True


def benchmark(name, g, texts, warmup=3, runs=4):
    """Run several generations and report RTF stats."""
    # Warmup
    for _ in range(warmup):
        _ = g.generate("warmup warmup warmup", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()

    rtfs = []
    for txt in texts:
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        audio = g.generate(txt, speaker=0, context=[], max_audio_length_ms=8000)
        torch.cuda.synchronize()
        dur = len(audio) / g.sample_rate
        rtf = (time.perf_counter() - t0) / dur
        rtfs.append(rtf)

    avg = sum(rtfs) / len(rtfs)
    print(f"{name:50s} | RTF {avg:.3f}  (min {min(rtfs):.3f} / max {max(rtfs):.3f})")
    return avg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["backbone", "decoder", "generate_frame", "all"],
        default=None,
        help="Which part to torch.compile. 'all' = progressive (backbone -> decoder -> generate_frame) on one model load."
    )
    args = parser.parse_args()

    texts = [
        "This is a medium length sentence for consistent benchmarking.",
        "Here comes another sentence of roughly similar duration to average noise.",
        "Third sentence to make the statistics more reliable.",
    ]

    print("Loading model (this may take a while on first run in the worktree)...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    # Always measure baseline first
    baseline_rtf = benchmark("best_flags_no_compile", g, texts)

    if args.target is None:
        print("\nDone (baseline only). Use --target to compile something.")
        return

    m = g._model

    if args.target in ("backbone", "all"):
        print("\n--- Compiling backbone ---")
        if hasattr(m, "backbone"):
            m.backbone = torch.compile(m.backbone, mode="max-autotune", fullgraph=False)
        else:
            print("No .backbone found, skipping")

        # Extra warmups for autotune + compile
        for _ in range(4):
            _ = g.generate("warmup after backbone compile", speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()

        benchmark("best_flags + compile(backbone)", g, texts)

    if args.target in ("decoder", "all"):
        print("\n--- Compiling decoder ---")
        if hasattr(m, "decoder"):
            m.decoder = torch.compile(m.decoder, mode="max-autotune", fullgraph=False)
        else:
            print("No .decoder found, skipping")

        for _ in range(3):
            _ = g.generate("warmup after decoder compile", speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()

        benchmark("best_flags + compile(backbone+decoder)", g, texts)

    if args.target in ("generate_frame", "all"):
        print("\n--- Compiling generate_frame ---")
        # These help reduce graph breaks in generate_frame
        torch._dynamo.config.capture_scalar_outputs = True

        if hasattr(m, "generate_frame"):
            m.generate_frame = torch.compile(m.generate_frame, mode="max-autotune", fullgraph=False)
        else:
            print("No generate_frame found, skipping")

        for _ in range(3):
            _ = g.generate("warmup after generate_frame compile", speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()

        benchmark("best_flags + compile(backbone+decoder+generate_frame)", g, texts)

    # Aggressive cleanup at the end (helps if you run the script multiple times in the same shell)
    print("\nCleaning up...")
    del g
    gc.collect()
    torch.cuda.empty_cache()
    print("Done.")


if __name__ == "__main__":
    main()
