# ASR Code-Switch Bench on RTX 5090

A small, practical research repo for evaluating open-source local ASR models on **English / Polish / Russian** with **single-speaker code-switching** under a **low-latency target**.

## Goal

Find the best local ASR stack on **RTX 5090** for these scenarios:

- `en/pl`
- `en/ru`
- `ru/pl`
- `en/ru/pl`

with a realistic preference order:

1. **usable streaming UX** (partials and commits feel responsive)
2. **good code-switch fidelity** (doesn't flatten everything into one language)
3. **strong final transcript quality**
4. **reasonable VRAM and operational complexity**

The benchmark should answer one simple question:

> Which model gives the best trade-off between code-switch accuracy and latency on a 5090?

---


## Runtime choice

Use **Podman by default** for this repo.

Why:

- better local reproducibility than a hand-built host Python stack
- rootless is nice for a workstation benchmark project
- NVIDIA recommends **CDI** for Podman GPU access
- the same image layout still stays OCI-compatible, so Docker users are not locked out

See [`docs/CONTAINERS.md`](docs/CONTAINERS.md) for the exact GPU setup and run commands.

---

## Recommended Phase-1 model shortlist

### 1) NVIDIA Canary-1B-v2

**Why it's in:** strongest current candidate for multilingual quality + code-switch handling.

- Multilingual ASR across **25 European languages**, including **en / pl / ru**.
- Supports **chunked and streaming inference** in NeMo.
- The technical report says the **unified tokenizer** was chosen partly because it enables **natural code-switching functionality**.
- Commercially usable under **CC BY 4.0**.

**Expectation:** probably the best quality/code-switch baseline, maybe not the absolute lowest latency.

### 2) NVIDIA Parakeet-TDT-0.6B-v3

**Why it's in:** likely the fastest serious multilingual open model in this shortlist.

- Multilingual ASR across the same **25 European languages**.
- Designed for **high-throughput** transcription.
- Supports **streaming** in NeMo.
- NVIDIA explicitly noted it is **not fully tuned for code-switching** yet.

**Expectation:** likely the latency winner or close to it; may lose on switch fidelity.

### 3) Whisper large-v3-turbo via faster-whisper

**Why it's in:** mature tooling, strong multilingual baseline, easy to compare, lots of community use.

- `large-v3-turbo` is a speed-optimized Whisper variant with a much smaller decoder.
- `faster-whisper` adds a `multilingual` option and notes that **Large** models already have **codeswitching capabilities**.
- Great "practical baseline" even if it doesn't end up as the final winner.

**Expectation:** likely very strong final text, weaker true streaming behavior than transducer-style models.

### 4) whisper.cpp (optional native baseline)

**Why it's in:** useful as a native/C++ baseline and for quick streaming experiments.

- Has a simple realtime example that samples audio every **500 ms**.
- Good for checking whether a lightweight local pipeline can feel responsive enough.

**Expectation:** probably not the main winner on this task, but valuable as a reference point.

---

## Models to skip in Phase 1

### WhisperX

Skip initially.

Reasons:

- You have **one speaker**, so diarization is not the bottleneck.
- It adds alignment complexity.
- There were historical **Blackwell / sm_120** compatibility issues reported on RTX 5090.

Bring it back only if you later decide word alignment quality matters more than raw latency.

### Canary Flash / very small ASR models

Skip for now unless you want a dedicated latency-only appendix.

Reason:

- For this repo, the main question is **best overall code-switch ASR under 5090**, not "smallest possible model at any cost".

---

## Benchmark questions

The repo should be able to answer these questions directly:

1. Which model has the best **final transcript quality** on `en/pl`, `en/ru`, `ru/pl`, `en/ru/pl`?
2. Which model preserves **language switches** instead of collapsing into a dominant language?
3. Which model gives the best **streaming UX**: first partials, stable commits, and low jitter?
4. How much **VRAM** and end-to-end compute does each stack need?
5. Does synthetic code-switch data transfer well enough to rank models before real-world testing?

---

## Dataset design

Use **synthetic speech** first, generated from a single consistent voice, because you want:

- perfect source text
- exact switch placement
- controllable speaking rate
- controllable pause structure
- reproducibility

### Language pairs / mixes

Create 4 buckets:

- `en_pl`
- `en_ru`
- `ru_pl`
- `en_ru_pl`

### Switching density

For each bucket, create:

- **low switch density** — one switch every 1-2 clauses
- **medium** — one switch every sentence or subclause
- **high** — multiple switches inside a sentence

### Duration buckets

Generate examples in these lengths:

- **short**: 3-7 s
- **medium**: 10-20 s
- **long**: 30-60 s

### Acoustic variants

Keep phase 1 small but not toy-like:

- clean
- mild room reverb
- light background noise
- faster speaking rate
- slower speaking rate

### Suggested dataset size for Phase 1

A good first pass:

- 4 language buckets
- 3 switch-density buckets
- 3 duration buckets
- 3 acoustic variants (`clean`, `noise_light`, `reverb_light`)
- 10 utterances per cell

That gives:

`4 * 3 * 3 * 3 * 10 = 1080 utterances`

This is enough for ranking without becoming a giant infra project.

---

## Ground truth format

Do **not** store only plain transcript strings.

Store at least:

- normalized transcript
- raw transcript
- token or segment language tags
- switch boundary positions
- expected duration
- scenario metadata

Example manifest row:

```json
{
  "id": "en_ru_medium_short_clean_0001",
  "audio_path": "data/audio/en_ru/clean/en_ru_medium_short_clean_0001.wav",
  "raw_text": "Hello, how are you? Сегодня у меня много работы, but I will finish it tonight.",
  "normalized_text": "hello how are you сегодня у меня много работы but i will finish it tonight",
  "segments": [
    {"lang": "en", "text": "Hello, how are you?"},
    {"lang": "ru", "text": "Сегодня у меня много работы,"},
    {"lang": "en", "text": "but I will finish it tonight."}
  ],
  "switch_count": 2,
  "speaker_id": "synthetic_voice_01",
  "duration_sec": 7.8,
  "condition": "clean"
}
```

---

## What to measure

### Accuracy

Core metrics:

- **WER** on normalized text
- **CER** on normalized text
- **Punctuation-preserving WER** on raw text
- **Hallucination rate** on silence / near-silence clips

### Code-switch fidelity

This is the key differentiator.

Measure at least:

- **Switch Boundary Recall** — how many true switch points are reflected in output
- **Switch Boundary Precision** — how many predicted switches are real
- **Segment Language Accuracy** — for each reference segment, did the output stay in the right language/script
- **Dominant-Language Collapse Rate** — percent of clips where mixed-language audio becomes mostly one language in output

### Latency / streaming UX

For low-latency work, final WER alone is not enough.

Measure:

- **TTFP** — time to first partial
- **TTSC** — time to first stable chunk / commit
- **Finalization lag** — audio end to final transcript end
- **p50 / p95 partial cadence** — how often updates arrive
- **Real-time factor (RTF)**

### Resource usage

- peak VRAM
- average VRAM
- GPU utilization
- wall-clock throughput
- startup/load time

---

## Success criteria

### Primary winner

The default winner should satisfy:

- best or near-best code-switch fidelity
- acceptable final WER
- usable streaming UX
- stable operation on 5090

### Practical threshold for "good enough"

A model is worth keeping if it hits roughly:

- **TTFP <= 500 ms** for streaming partials
- **TTSC <= 1.5 s**
- **Finalization lag <= 2 s** for short/medium clips
- clearly lower collapse rate than weaker baselines

These are not universal ASR standards; they are repo decision thresholds.

---

## Repo layout

```text
asr-codeswitch-bench-5090/
├── README.md
├── Makefile
├── configs/
│   ├── models.yaml
│   └── scenarios.yaml
├── data/
│   └── schema/
│       └── sample.manifest.jsonl
├── docs/
│   ├── DATASET.md
│   ├── METRICS.md
│   ├── MODELS.md
│   └── RUNBOOK.md
├── reports/
│   └── report-template.md
├── results/
│   └── .gitkeep
└── scripts/
    ├── bench.py
    ├── evaluate.py
    └── summarize.py
```

---

## Suggested execution order

### Stage 0 — repo bootstrap

- create envs per backend
- verify GPU, CUDA, torch, NeMo, faster-whisper
- run one known sample through each backend

### Stage 1 — smoke benchmark

Use a tiny subset first:

- 5 clips per language bucket
- only `clean`
- only short + medium durations

Goal:

- make sure metrics pipeline works
- verify transcripts are comparable
- catch tokenizer/script weirdness early

### Stage 2 — main benchmark

Run full synthetic dataset and collect:

- transcript outputs
- timestamps
- latency traces
- VRAM traces
- aggregate metrics tables

### Stage 3 — analysis

Produce:

- global ranking
- per language-pair ranking
- per switch-density ranking
- latency vs quality chart
- failure taxonomy

### Stage 4 — optional real-audio validation

Once the shortlist is narrowed to 1-2 winners:

- record a few real spoken clips
- compare whether synthetic ranking still holds

---

## Recommended initial verdict before running anything

If I had to predict the result now:

- **Best overall / most promising for code-switch:** `Canary-1B-v2`
- **Fastest likely serious candidate:** `Parakeet-TDT-0.6B-v3`
- **Best practical baseline / easiest benchmark anchor:** `faster-whisper + large-v3-turbo`

That gives a very clean Phase-1 story:

- **Canary** = quality-first multilingual candidate
- **Parakeet** = latency-first multilingual candidate
- **Whisper** = robust community baseline

---

## Notes on interpretation

A few traps to avoid:

1. **Synthetic-only overfitting**
   - Great scores on TTS speech do not guarantee real microphone performance.

2. **False streaming optimism**
   - Some stacks look "fast" only because they emit unstable partials that rewrite aggressively.

3. **Language collapse hidden by normalization**
   - A normalized metric can hide the fact that the model silently converted mixed speech into one dominant language.

4. **Timestamp quality != transcript quality**
   - Don't let nice timestamps distract from poor switch fidelity.

---

## Minimal decision at the end of this repo

At the end, the repo should let you write one line like this with confidence:

> For single-speaker `en/pl/ru` code-switch on RTX 5090, use **X** for production streaming and keep **Y** as the quality fallback.

