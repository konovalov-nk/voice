#!/usr/bin/env python3
"""
Test selective torch.compile placement + best flags.
Goal: compile only the expensive parts instead of the whole model.
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
        _ = g.generate("warmup", speaker=0, context=[], max_audio_length_ms=3000)
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
    print(f"{name:50s} | RTF {avg:.3f}")
    return avg

def main():
    texts = ["Test sentence for placement experiment one.", "Second sentence for placement stats.", "Third for noise reduction."]

    print("Loading model + best flags...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    # Baseline in this tree
    benchmark("best_flags_no_compile (placement tree)", g, texts)

    # Try compiling only the backbone (most compute heavy)
    print("\nCompiling only backbone (g._model.backbone)...")
    try:
        g2 = load_miso_8b(device="cuda")
        set_best_flags()
        if hasattr(g2._model, 'backbone'):
            g2._model.backbone = torch.compile(g2._model.backbone, mode="max-autotune", fullgraph=False)
        else:
            print("No .backbone attribute, falling back to whole model")
            g2._model = torch.compile(g2._model, mode="max-autotune", fullgraph=False)
        for _ in range(3):
            _ = g2.generate("backbone compile warmup", speaker=0, context=[], max_audio_length_ms=3000)
        torch.cuda.synchronize()
        benchmark("best_flags + compile(backbone only)", g2, texts)
    except Exception as e:
        print("Backbone compile failed:", e)

if __name__ == "__main__":
    main()
