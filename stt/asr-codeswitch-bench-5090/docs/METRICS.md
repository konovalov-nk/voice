# Metrics

## 1. Transcript quality

### WER

Compute on normalized text.

Use as the main generic ASR accuracy number.

### CER

Useful when script differences or tokenization quirks distort WER.

### Raw-text WER

Compute on raw text with punctuation/case preserved.

Useful for measuring whether a model's formatting behavior is production-friendly.

## 2. Code-switch fidelity

This repo should treat code-switch fidelity as first-class, not a side note.

### 2.1 Switch Boundary Recall

Out of all true reference switch points, how many are reflected in the hypothesis?

High recall means the model notices actual switches.

### 2.2 Switch Boundary Precision

Out of all predicted switch points, how many are real?

High precision means the model isn't inventing switches.

### 2.3 Segment Language Accuracy

For each reference segment, assign the dominant predicted language/script and compare with reference.

This can be implemented heuristically in Phase 1 using:

- Cyrillic presence for Russian
- Latin vocabulary dictionary / langid fallback for English vs Polish

### 2.4 Dominant-Language Collapse Rate

A clip counts as collapsed if a mixed-language reference becomes overwhelmingly one language in output.

Example heuristic:

- if reference has 2+ languages
- and hypothesis content for one language covers >= 85% of non-punctuation tokens
- and at least one reference language is nearly absent

then mark as collapse.

## 3. Streaming / latency

### TTFP — Time to First Partial

`first_partial_timestamp - audio_start_timestamp`

This is the main "does it feel alive" metric.

### TTSC — Time to Stable Commit

Time until the first chunk appears that is no longer rewritten in later updates.

This is more useful than raw first-token speed.

### Finalization Lag

`final_transcript_ready - audio_end`

Important for turn-taking UX.

### Partial Cadence

Track inter-update intervals and report:

- p50
- p95
- max

### RTF — Real-Time Factor

`processing_time / audio_duration`

Interpretation:

- `< 1.0` faster than realtime
- `~ 1.0` roughly realtime
- `> 1.0` slower than realtime

## 4. Resource usage

### Peak VRAM

Main deployment sizing metric.

### Avg GPU utilization

Helps explain whether a stack is compute-bound or pipeline-bound.

### Model load time

Important for cold-start behavior.

## 5. Reporting format

Every experiment row should include:

- model
- backend
- precision / quantization
- scenario
- WER
- CER
- raw_WER
- switch_recall
- switch_precision
- segment_lang_acc
- collapse_rate
- TTFP_p50
- TTSC_p50
- finalization_lag_p50
- RTF_mean
- peak_vram_mb
- notes

