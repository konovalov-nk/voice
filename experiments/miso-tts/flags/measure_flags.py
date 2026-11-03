#!/usr/bin/env python3
"""
Highest-ROI cheap flags sweep for MisoTTS on RTX 5090.
Focus on things that cost almost zero code change.
"""
import time
import torch
from generator import load_miso_8b

def set_flags(tf32=True, coord_tuning=True, cudagraphs=True, max_autotune=False):
    torch.backends.cuda.matmul.allow_tf32 = tf32
    torch.backends.cudnn.allow_tf32 = tf32
    torch._inductor.config.coordinate_descent_tuning = coord_tuning
    torch._inductor.config.triton.cudagraphs = cudagraphs
    if max_autotune:
        torch._inductor.config.max_autotune = True

def benchmark(name, g, texts, warmup=3, runs=4):
    for _ in range(warmup):
        _ = g.generate("warmup warmup", speaker=0, context=[], max_audio_length_ms=3000)
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
    print(f"{name:40s} | RTF {avg:.3f}   (min {min(rtfs):.3f} / max {max(rtfs):.3f})")
    return avg

def main():
    texts = [
        "This is a medium length sentence for consistent benchmarking across runs.",
        "Here comes another sentence of roughly similar duration to average noise.",
        "Third sentence to make the statistics more reliable.",
        "Fourth sentence for better averaging."
    ]

    print("Loading model fresh for this flag set...\n")
    g = load_miso_8b(device="cuda")

    results = {}

    # 1. Everything off (as close to "pure" as possible)
    set_flags(tf32=False, coord_tuning=False, cudagraphs=False, max_autotune=False)
    results["baseline (all flags off)"] = benchmark("baseline (all flags off)", g, texts)

    # 2. Only TF32 (usually the biggest free win on 40/50 series)
    set_flags(tf32=True, coord_tuning=False, cudagraphs=False, max_autotune=False)
    results["+ TF32 only"] = benchmark("+ TF32 only", g, texts)

    # 3. TF32 + coordinate_descent_tuning
    set_flags(tf32=True, coord_tuning=True, cudagraphs=False, max_autotune=False)
    results["+ TF32 + coord_tuning"] = benchmark("+ TF32 + coord_tuning", g, texts)

    # 4. TF32 + cudagraphs
    set_flags(tf32=True, coord_tuning=False, cudagraphs=True, max_autotune=False)
    results["+ TF32 + cudagraphs"] = benchmark("+ TF32 + cudagraphs", g, texts)

    # 5. TF32 + tuning + cudagraphs
    set_flags(tf32=True, coord_tuning=True, cudagraphs=True, max_autotune=False)
    results["+ TF32 + tuning + cudagraphs"] = benchmark("+ TF32 + tuning + cudagraphs", g, texts)

    # 6. All of the above + max_autotune (a bit heavier)
    set_flags(tf32=True, coord_tuning=True, cudagraphs=True, max_autotune=True)
    results["+ TF32 + tuning + cudagraphs + max_autotune"] = benchmark("+ TF32 + tuning + cudagraphs + max_autotune", g, texts)

    print("\n=== Summary (sorted) ===")
    for name, rtf in sorted(results.items(), key=lambda x: x[1]):
        print(f"{name:40s} : {rtf:.3f}")

if __name__ == "__main__":
    main()
