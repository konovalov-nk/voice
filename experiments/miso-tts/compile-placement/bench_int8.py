#!/usr/bin/env python3
"""
Quick int8 (8-bit) quantization experiment for MisoTTS on RTX 5090.

Focus: quantize only the heavy backbone to save VRAM and see RTF impact.
Uses best flags we found earlier.
"""

import os
import gc
import time
import torch
import torch.nn as nn

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

from generator import load_miso_8b
import bitsandbytes as bnb


def set_best_flags():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch._inductor.config.coordinate_descent_tuning = True
    torch._inductor.config.triton.cudagraphs = True
    torch._inductor.config.max_autotune = True


def replace_linear_with_8bit(module: nn.Module, threshold: float = 6.0):
    """Recursively replace nn.Linear with bnb.nn.Linear8bitLt (only for large layers)."""
    for name, child in list(module.named_children()):
        if isinstance(child, nn.Linear):
            # Skip very small layers (embeddings/heads) to keep quality
            if child.in_features >= 1024 and child.out_features >= 1024:
                new_layer = bnb.nn.Linear8bitLt(
                    child.in_features,
                    child.out_features,
                    bias=child.bias is not None,
                    has_fp16_weights=False,
                    threshold=threshold,
                )
                # Copy weights
                new_layer.weight = child.weight
                if child.bias is not None:
                    new_layer.bias = child.bias
                setattr(module, name, new_layer)
        else:
            replace_linear_with_8bit(child, threshold)


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
    print(f"{name:45s} | RTF {avg:.3f}  (min {min(rtfs):.3f})")
    return avg


def main():
    texts = [
        "Medium length sentence for int8 quantization test.",
        "Another sentence of similar length for stats.",
        "Third sentence to reduce variance."
    ]

    print("Loading model in bf16 + best flags...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    baseline = benchmark("bf16 + best_flags (no quant)", g, texts)

    # Try to quantize only the backbone (biggest part)
    print("\nReplacing backbone Linear layers with 8-bit (bitsandbytes)...")
    m = g._model
    if hasattr(m, "backbone"):
        replace_linear_with_8bit(m.backbone, threshold=6.0)
        # Move to cuda if needed (8bit layers sometimes need explicit .cuda())
        m.backbone = m.backbone.cuda()
    else:
        print("No backbone found, quantizing whole model instead")
        replace_linear_with_8bit(m)

    torch.cuda.empty_cache()
    gc.collect()

    print("Warming up after quantization...")
    for _ in range(4):
        _ = g.generate("int8 warmup", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()

    quantized = benchmark("int8 backbone + best_flags", g, texts)

    print("\n=== Summary ===")
    print(f"bf16 baseline: {baseline:.3f}")
    print(f"int8 (backbone): {quantized:.3f}")
    if quantized < baseline:
        print(f"Speedup: {baseline / quantized:.2f}x")
    else:
        print("Slower after int8 (common on high-end cards with good bf16)")


if __name__ == "__main__":
    main()
