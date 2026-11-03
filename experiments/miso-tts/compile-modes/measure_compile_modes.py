#!/usr/bin/env python3
"""
Test torch.compile modes on top of the best cheap flags we found.
"""
import time
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
        _ = g.generate("warmup text here", speaker=0, context=[], max_audio_length_ms=3000)
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
    texts = [
        "Medium length sentence for benchmarking compile impact.",
        "Another sentence of similar length for averaging.",
        "Third sentence to reduce measurement noise.",
    ]

    print("Loading model...\n")
    g = load_miso_8b(device="cuda")

    set_best_flags()

    # No compile (just the best flags)
    results = {}
    results["best_flags_no_compile"] = benchmark("best_flags_no_compile", g, texts)

    # Now try different compile modes
    for mode in ["reduce-overhead", "max-autotune", "max-autotune-no-cudagraphs"]:
        print(f"\n=== Compiling with mode={mode} ===")
        g2 = load_miso_8b(device="cuda")   # fresh load for clean compile
        set_best_flags()
        g2._model = torch.compile(g2._model, mode=mode, fullgraph=False, dynamic=False)

        # Extra warmup because compile + autotune is lazy
        for _ in range(4):
            _ = g2.generate("compile warmup " + mode, speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()

        results[f"compile_{mode}"] = benchmark(f"compile + best_flags + {mode}", g2, texts)

    print("\n=== Final ranking ===")
    for name, rtf in sorted(results.items(), key=lambda x: x[1]):
        print(f"{name:45s} : {rtf:.3f}")

if __name__ == "__main__":
    main()
