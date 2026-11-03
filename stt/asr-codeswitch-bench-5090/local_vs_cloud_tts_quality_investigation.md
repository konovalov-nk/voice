# Investigating Quality Gap: Local S2-Pro vs Fish Audio Paid/Playground

## Context (starting point: `maya.wav/mp3`)

We compared two outputs for the same prompt/reference:

- Local: `local-s2-pro-maya.wav`
- Cloud/Paid: `fish-audio-s2-pro-maya.mp3`

Initial finding: these files are not directly comparable frame-by-frame (different container/codec and even different duration).
So before conclusions, we need a controlled comparison pipeline.

## What we are trying to answer

We are **not** trying to get bit-identical waveforms.

We are trying to answer:

1. Can we reproduce **comparable perceived quality** (naturalness, expressiveness, voice consistency)?
2. If not, is the gap mostly from:
   - serving/runtime pipeline differences, or
   - model weights/checkpoint differences?

## Important reality check

Even with public weights + public OSS inference repos, exact cloud reproduction is unlikely because the paid service may include private components:

- text-stream commit logic (`text`/`flush`/`stop` behavior),
- prompt rewriting/instruction enrichment,
- production decoding/stitching/post-processing,
- internal serving/cache policies.

So target should be **quality parity**, not "same waveform".

## High-level architecture (current local)

```python
# Current local flow (simplified)
request(text, reference, params) ->
  build_prompt(system + user + voice marker) ->
  SlowAR generates semantic token q_t[0] each timestep ->
  FastAR generates residual acoustic codebooks q_t[1..N-1] ->
  collect code frames ->
  DAC/vocoder decodes frames -> waveform ->
  stream/return audio
```

## Who generates what (critical for debugging "flatness")

```python
# Per timestep t in decode_one_token_ar(...)
semantic = SlowAR.sample(...)             # q_t[0], high-level speech plan/prosody scaffold
residuals = []
for k in range(1, N):                     # Fast AR
    residuals.append(FastAR.sample(...))  # q_t[k], fine acoustic detail
frame_codes = [semantic] + residuals
```

- SlowAR mostly controls semantic/prosodic trajectory.
- FastAR adds timbre/detail texture.
- "Flat" can come from either (or both), but often from conservative semantic trajectory + conservative sampling/prompting.

## Why WER is insufficient here

WER checks **what words** were spoken, not **how** they were spoken.
For "sounds flat", we need acoustic/prosodic diagnostics.

## Can we compare acoustic tokens from cloud vs local?

Yes, with caveat.

We can do:

```python
# Not true generation tokens, but re-encoded tokens from final audio
codes_local = codec.encode(local_audio)
codes_cloud = codec.encode(cloud_audio)
compare(codes_local, codes_cloud)
```

This does **not** recover cloud's original sampled tokens exactly, but still gives useful signal for style/variability differences if same codec is used.

## Controlled experiment plan

### Phase 0 - Make inputs comparable

- Request cloud output in WAV/PCM if possible (avoid MP3 for token stats).
- Use same prompt text, same reference audio, same language tags, same params.
- Run each condition multiple times (for example, 5-10) to estimate stochastic variance.

### Phase 1 - Audio-level diagnostics

- Duration, pause distribution, energy contour, F0 contour variability.
- Subjective A/B blind tests ("flatness", "emotional continuity", "voice consistency").

### Phase 2 - Token-level diagnostics (re-encoded)

For each codebook (especially `k=0` semantic):

- entropy,
- repetition/run-length,
- transition diversity.

Interpretation:

- lower diversity / higher repetition can indicate over-constrained decoding and perceived flatness.

### Phase 3 - Local pipeline ablations

Test one factor at a time:

1. sampling policy (`temperature`/`top_p`/`top_k`/`repetition`/`RAS`),
2. prompt construction / optional instruction rewrite,
3. text chunking/commit behavior,
4. reference preprocessing,
5. decode/stitching behavior.

## The 5 major gap sources (with e2e impact)

### 1) Split/commit strategy

When do we synthesize buffered text?

```python
buffer += text_delta
if flush or (has_punctuation(buffer_tail) and len_ok) or timeout:
    synthesize(buffer_tail)
```

E2E impact: too-early commits give incomplete prosodic context, causing abrupt or flat phrasing.

### 2) Prompt construction / instruction rewrite

How raw text is transformed before TTS.

```python
rewritten = rewrite(raw_text, add_style_tags=True, preserve_meaning=True)
prompt = system + user(rewritten) + assistant("<|voice|>")
```

E2E impact: large effect on expressiveness and style persistence (for example, joy/sad/urgent tone continuity).

### 3) Sampling policy

How next tokens are sampled.

```python
logits = model(context)
logits = apply_repetition_penalty(logits, recent_tokens)
token = sample(top_p_filter(top_k_filter(softmax(logits / temp))))
# optional RAS fallback for anti-repeat behavior
```

E2E impact: too conservative gives safe but flat speech; too random gives instability/noise.

### 4) Reference preprocessing

How reference voice is cleaned and encoded.

```python
ref = load_audio()
ref = mono_resample_trim_normalize(ref)
ref_codes = codec.encode(ref)
```

E2E impact: directly affects speaker similarity and timbre richness. Poor reference preprocessing can flatten output.

### 5) Decode/stitching path

How token chunks become waveform and how boundaries are merged.

```python
for chunk in token_chunks:
    wav = decoder.decode(chunk)
    wav = crossfade_with_previous(wav, prev_wav)
```

E2E impact: boundary artifacts or loudness jumps can make output feel synthetic/flat even with good tokens.

## Success criteria

Define parity as:

- statistically similar subjective scores in blind A/B,
- no major gap in prosody/voice consistency metrics across test set.

Do not use waveform equality as the target.

## Bottom line

- The quality gap is likely real.
- The gap is likely multi-factor (runtime + prompting + sampling + decode path), not one single knob.
- With controlled experiments, we can identify how much of the gap is recoverable with public weights + open code.
