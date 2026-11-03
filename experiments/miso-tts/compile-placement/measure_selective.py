#!/usr/bin/env python3
"""
Selective torch.compile experiments.
Loads model *once*, measures baseline with best flags,
then applies compile to specific parts and re-measures.

Run:
  uv run python measure_selective.py
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
    print(f"{name:55s} | RTF {avg:.3f}  (min {min(rtfs):.3f})")
    return avg

def main():
    texts = [
        "Medium length sentence for selective compile test.",
        "Another sentence of similar length.",
        "Third for averaging."
    ]

    print("Loading model once...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    # Baseline
    baseline = benchmark("best_flags_no_compile", g, texts)

    # === Selective compiles on the *same* loaded model ===
    m = g._model

    print("\n--- Compiling backbone only ---")
    if hasattr(m, "backbone"):
        m.backbone = torch.compile(m.backbone, mode="max-autotune", fullgraph=False)
    for _ in range(4):
        _ = g.generate("warmup after backbone compile", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()
    benchmark("best_flags + compile(backbone)", g, texts)

    print("\n--- Compiling decoder only (on top of previous) ---")
    if hasattr(m, "decoder"):
        m.decoder = torch.compile(m.decoder, mode="max-autotune", fullgraph=False)
    for _ in range(3):
        _ = g.generate("warmup after decoder compile", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()
    benchmark("best_flags + compile(backbone+decoder)", g, texts)

    print("\n--- Compiling generate_frame (on top) ---")
    if hasattr(m, "generate_frame"):
        m.generate_frame = torch.compile(m.generate_frame, mode="max-autotune", fullgraph=False)
    for _ in range(3):
        _ = g.generate("warmup after generate_frame compile", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()
    benchmark("best_flags + compile(backbone+decoder+generate_frame)", g, texts)

if __name__ == "__main__":
    main()
