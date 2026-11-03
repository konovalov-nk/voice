# MisoTTS Compile Experiments - Protocol & Isolation

## Worktree Layout (for isolation)

- `MisoTTS/` (main branch)               → **Baseline** (reference measurements, no experimental changes)
- `experiments/compile-modes/`           → Testing different `torch.compile(..., mode=...)`
- `experiments/compile-placement/`       → Testing *where* we apply compile (model._model, specific submodules, generate loop, etc.)
- `experiments/flags/`                   → Inductor config, cudagraphs, TF32, fp32 matmul precision, etc.

Each worktree has its own checkout. You can have different versions of `test_misotts.py`, different patches, etc. without them affecting each other.

**Rule:** Never run experiments that modify code in the baseline tree. Only use it for clean reference runs.

## Measurement Protocol (must follow for comparable results)

### 1. Environment
- Use the same Python/uv env inside the worktree (or explicitly document if you use a different one).
- Always start from a clean `uv run` (no leftover CUDA context if possible).
- Disable any background GPU stuff if possible.

### 2. Warmup
- Minimum **2 full warmup generations** before any timed measurement.
- For compile experiments: do **at least 3** warmup generations after setting `torch.compile` (compilation + autotuning happens lazily).

### 3. Measurement
- Use `time.perf_counter()` + `torch.cuda.synchronize()` before and after each `generate()`.
- Run **at least 3** (better 5) timed generations per condition.
- Report: mean RTF, min, max, std if possible.
- Always report **audio duration** of the generated sample (because RTF is sensitive to it).

### 4. Texts used
Use a fixed set of test sentences of different lengths:
- Short (~2-3s target)
- Medium (~5-7s)
- Longer (~10s+)

Example set (or similar):
1. "This is a short test sentence."
2. "Here we have a medium length sentence that should produce roughly five to seven seconds of speech."
3. "This is a longer test prompt designed to exercise the model for approximately ten seconds or more of generated audio while keeping the text natural."

For prompted experiments, use the same reference audio + transcript across runs.

### 5. Other controls
- Keep `max_audio_length_ms` consistent for a given test (e.g. 8000 or 10000).
- Do not change speaker id mid-benchmark unless testing that variable.
- After heavy compile experiments, it is recommended to restart the Python process before baseline runs (to avoid lingering compiled graphs / memory).

### 6. What to record for every experiment
- Worktree / branch name
- torch version + CUDA version
- Exact `torch.compile(...)` call (mode, fullgraph, dynamic, etc.)
- Any `torch._inductor.config.*` or env vars changed
- Warmup count
- Number of timed runs + mean / min / max RTF
- Whether it was unprompted or prompted
- Any errors / graph breaks observed (`TORCH_LOGS="graph_breaks"` can be useful)

## Current Baseline (as of 2026-06-08 on main)

See results from previous runs in this chat:
- Cold (no warmup): ~1.35-1.40 RTF
- After warmup, no compile: ~1.32-1.35 RTF
- With `torch.compile(..., mode="max-autotune")`: ~1.31 RTF (modest ~3-5% gain)

All future experiments should be compared against fresh baseline runs in the `main` tree following this protocol.

## How to run a measurement

Example (adapt `test_misotts.py` or write a small snippet):

```python
import time, torch
from generator import load_miso_8b

g = load_miso_8b(device="cuda")

# warmup
for _ in range(3):
    _ = g.generate("warmup text", speaker=0, context=[], max_audio_length_ms=4000)
torch.cuda.synchronize()

# timed
t0 = time.perf_counter()
audio = g.generate("measurement text here", speaker=0, context=[], max_audio_length_ms=8000)
torch.cuda.synchronize()
rtf = (time.perf_counter() - t0) / (len(audio) / g.sample_rate)
print("RTF:", rtf)
```

When doing compile experiments, apply the compile **after** loading and **before** the warmup loop.

Good luck, and keep results comparable.
