#!/usr/bin/env python3
"""
Int8 quantization experiment v2 - with correct bitsandbytes weight handling.
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


def quantize_module_to_8bit(module: nn.Module, threshold: float = 6.0):
    """Replace large Linear layers with 8-bit versions (correct bnb way)."""
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
                # Correct way: wrap the weight as Params8bit
                qlinear._parameters["weight"] = bnb.nn.modules.Params8bit(
                    child.weight.data, requires_grad=False
                )
                if child.bias is not None:
                    qlinear.bias = child.bias
                setattr(module, name, qlinear)
        else:
            quantize_module_to_8bit(child, threshold)


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
        "Medium length sentence for int8 test.",
        "Second sentence for averaging.",
        "Third sentence for stats."
    ]

    print("Loading bf16 + best flags...")
    g = load_miso_8b(device="cuda")
    set_best_flags()

    baseline = benchmark("bf16 baseline + best flags", g, texts)

    print("\nQuantizing large Linear layers in backbone to int8 (correct bnb)...")
    m = g._model
    if hasattr(m, "backbone"):
        quantize_module_to_8bit(m.backbone)
        m.backbone.cuda()  # ensure on device
    else:
        quantize_module_to_8bit(m)

    torch.cuda.empty_cache()
    gc.collect()

    print("Warming up quantized model...")
    for _ in range(5):
        _ = g.generate("int8 warmup", speaker=0, context=[], max_audio_length_ms=3000)
    torch.cuda.synchronize()

    int8_rtf = benchmark("int8 (backbone) + best flags", g, texts)

    print("\n=== Result ===")
    print(f"bf16:  {baseline:.3f}")
    print(f"int8:  {int8_rtf:.3f}")
    if int8_rtf < baseline:
        print(f"→ {baseline / int8_rtf:.2f}x faster")
    else:
        print("→ int8 was slower (typical on 5090 with strong bf16)")


if __name__ == "__main__":
    main()
