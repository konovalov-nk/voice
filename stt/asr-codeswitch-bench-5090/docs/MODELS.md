# Model Notes

## Inclusion criteria

A model goes into the benchmark if it satisfies all of these:

- local / open-source
- runnable on RTX 5090
- supports English, Polish, and Russian
- has a plausible path to streaming or chunked low-latency inference
- doesn't require multi-speaker diarization for basic value

## Phase-1 candidates

### Canary-1B-v2

Role: **quality-first multilingual contender**

What we expect:

- strongest multilingual fidelity
- best handling of mixed-language text spans
- somewhat heavier runtime than Parakeet

Questions to answer:

- does it really beat Whisper on `en/ru/pl` mix quality?
- what is the latency cost of that gain?
- how stable are partials under frequent switches?

### Parakeet-TDT-0.6B-v3

Role: **latency-first multilingual contender**

What we expect:

- very strong throughput
- likely best TTFP / RTF
- possible weakness when switches are dense inside a sentence

Questions to answer:

- how bad is the code-switch gap in practice?
- is the gap small enough that speed wins anyway?
- does it collapse mixed segments more often than Canary/Whisper?

### Whisper large-v3-turbo via faster-whisper

Role: **community baseline**

What we expect:

- strong final transcript quality
- easiest operational setup after NeMo
- decent but not ideal streaming semantics

Questions to answer:

- how much does `multilingual=True` help?
- is it competitive on dense code-switch or only on clean mixed clauses?
- how large is finalization lag compared with Parakeet?

### whisper.cpp (optional)

Role: **native baseline / low-friction realtime reference**

Use it if:

- you want a C++/native comparison
- you care about a very simple local stack
- you want to compare perceived responsiveness against Python backends

## Excluded in Phase 1

### WhisperX

Reason to defer:

- adds alignment complexity
- less relevant for one-speaker benchmark
- can return in Phase 2 if word timestamps become important

### API-only or closed models

Reason to exclude:

- repo goal is local/open deployment on 5090

