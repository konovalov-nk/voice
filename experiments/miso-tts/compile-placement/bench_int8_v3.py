#!/usr/bin/env python3
"""
Int8 (8-bit) quantization v3 - using the correct Int8Params for bitsandbytes 0.45.
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


def quantize_to_int8(module: nn.Module, threshold: float = 6.0):
    """Replace large nn.Linear with bnb 8-bit version using Int8Params."""
    for name, child in list(module.named_children()):
        if isinstance(child, nn.Linear):
            if child.in_features >= 1024 and child.out_features >= 1024:
                qlinear = bnb.nn.Linear8bitLt(
                    child.in_features,
                    child.out_features,
                    bias=child.bias is not None,
                    has_fp16_weights=False,
                    threshold=threshold,
                )
                # Correct for int8
                qlinear._parameters["weight"] = bnb.nn.modules.Int8Params(
                    child.weight.data, requires_grad=False
                )
                if child.bias is not None:
                    qlinear.bias = child.bias
                setattr(module, name, qlinear)
        else:
            quantize_to_int8(child, threshold)


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
    print(f"{name:45s} | RTF {avg:.3f}  (min {min(rtfs):.3f})")
    return avg


def main():
    texts = [
        "Medium length sentence for int8 quantization benchmark.",
        "Second sentence for better statistics.",
        "Third sentence to average results."
    ]

    print("Loading model in bf16 + best flags...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    baseline = benchmark("bf16 + best flags", g, texts)

    print("\nQuantizing large layers in backbone to int8 (using Int8Params)...")
    m = g._model
    if hasattr(m, "backbone"):
        quantize_to_int8(m.backbone)
        m.backbone = m.backbone.cuda()
    else:
        quantize_to_int8(m)

    torch.cuda.empty_cache()
    gc.collect()

    print("Warming up int8 model (may take a bit for first quantization)...")
    for _ in range(5):
        _ = g.generate("int8 warmup", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()

    int8_result = benchmark("int8 backbone + best flags", g, texts)

    print("\n=== Final ===")
    print(f"bf16: {baseline:.3f}")
    print(f"int8: {int8_result:.3f}")
    if int8_result < baseline:
        print(f"Improvement: {baseline / int8_result:.2f}x")
    else:
        print("int8 was not faster (common on 5090)")


if __name__ == "__main__":
    main()
