#!/usr/bin/env python3
"""
Test torch.compile on top of best cheap flags.
Run separate times for different modes to avoid OOM.
Usage:
  uv run python measure_compile.py              # baseline (best flags, no compile)
  uv run python measure_compile.py max-autotune # with compile mode
"""
import sys
import time
import gc
import torch
from generator import load_miso_8b

def set_best_flags():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch._inductor.config.coordinate_descent_tuning = True
    torch._inductor.config.triton.cudagraphs = True
    torch._inductor.config.max_autotune = True

def benchmark(name, g, texts, warmup=3):
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
    print(f"{name:45s} | RTF {avg:.3f}  (min {min(rtfs):.3f})")
    return avg

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    texts = [
        "Medium length sentence for benchmarking compile impact.",
        "Another sentence of similar length for averaging.",
        "Third sentence to reduce measurement noise.",
    ]

    print("Loading model...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    if mode:
        print(f"Applying torch.compile(mode={mode}) ...")
        g._model = torch.compile(g._model, mode=mode, fullgraph=False, dynamic=False)
        # Extra warmup for compilation + autotuning
        extra_warm = 4 if "max" in mode else 2
        for _ in range(extra_warm):
            _ = g.generate("compile warmup " + mode, speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()
        name = f"best_flags + compile({mode})"
    else:
        name = "best_flags_no_compile"

    benchmark(name, g, texts)

    # Cleanup
    del g
    gc.collect()
    torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
