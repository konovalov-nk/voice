# Dataset Plan

## Why synthetic first

Synthetic speech is not the end goal. It is the fastest way to get:

- exact transcripts
- exact switch placement
- reproducibility
- controllable style/speed/noise

That makes it good for ranking models early.

## Corpus matrix

### Language composition

- `en_pl`
- `en_ru`
- `ru_pl`
- `en_ru_pl`

### Switch density

- `low`
- `medium`
- `high`

### Duration

- `short` = 3-7 s
- `medium` = 10-20 s
- `long` = 30-60 s

### Conditions

- `clean`
- `noise_light`
- `reverb_light`

## Text generation guidelines

Text should not be random word salad.

Generate utterances that sound like realistic user speech:

- task switching
- everyday narration
- technical discussion
- scheduling / reminders
- casual thoughts

Examples of good switch styles:

- clause-level switch
- sentence-level switch
- parenthetical insertion in another language
- fast alternation of short phrases

Examples to avoid in Phase 1:

- poetry
- slang-heavy outliers
- named-entity spam
- tongue twisters
- extremely unnatural punctuation

## Annotation format

Each sample should preserve both raw and normalized text.

Recommended manifest fields:

- `id`
- `audio_path`
- `raw_text`
- `normalized_text`
- `segments[]`
- `switch_count`
- `speaker_id`
- `duration_sec`
- `condition`
- `mix`
- `density`

## Holdout split

Recommended split:

- train/dev prompts for TTS text authoring experiments: optional
- `dev` synthetic set: 15%
- `test` synthetic set: 85%

Since we're not training ASR in Phase 1, the important part is simply:

- keep a fixed held-out benchmark set
- do not hand-tune model settings on the full test corpus

## Optional Phase-2 real set

Later add a tiny real-speech set:

- same speaker
- same language mixes
- phone mic + desktop mic
- mild room noise

This checks whether synthetic ranking transfers.

## Dataset architecture (v2)

### Source splits

- `real_human` - primary benchmark truth
- `synthetic_v1` - XTTS full-text stress baseline
- `synthetic_v2` - cleaner synthetic control (segment render + stitch)
- `synthetic_v3` - accent-stress synthetic control

### Intended vs observed fields

Store both intent and realized render behavior.

- intended: `target_lang_spans`, `switch_pattern`, `switch_points`
- observed: `rendered_segment_bounds_ms`, QA issue scores, stitch metadata

`target_lang_spans` use character offsets, not token indices.

Example:

```json
{"lang":"en","start_char":0,"end_char":33}
```

### Identity and reproducibility

Required fields per sample:

- `sample_id`
- `text_uid`
- `prompt_id`
- `speaker_id`
- `audio_path`
- `duration_ms`
- `sample_rate_hz`
- `source_split`
- `language_combo`
- `dataset_version`
- `generator_version`
- `git_sha`
- `seed`
- `engine_model_id`
- `engine_params`
- `render_mode`

### Switch taxonomy

- `switch_density`: `low|medium|high`
- `switch_pattern`: e.g. `A_B`, `A_B_A`, `A_B_C`
- `boundary_type`: `clause|named_entity|quote|filler|technical_term`
- `utterance_length`: `short|medium|long`

### Segment stitch policy for synthetic_v2

- split only by clause or short phrase (not single words)
- render each segment with the segment language
- optional per-language references via `speaker_ref_by_lang`
- apply light segment gain matching, then stitch, then final utterance loudness normalization
- keep segment artifacts and timing metadata for debugging

### QA scoring and gate

Per sample:

- `accent_leakage_score` (0-3)
- `word_corruption_score` (0-3)
- `boundary_artifact_score` (0-3)
- `overall_accept` (boolean)
- optional `render_notes`

Suggested gate before full generation:

- `word_corruption_score <= 1`
- `boundary_artifact_score <= 1`
- mean `accent_leakage_score <= 1.5`
- `overall_accept_rate >= 0.85`

### Canonicalization policy

Keep both:

- `display_text` - human-readable intended text
- `canonical_text` - normalized text used for WER/CER

Canonicalization rules must be versioned and explicit for punctuation, numbers,
case, `yo/e` mapping in Russian, and named entities.

Reference policy file: `docs/CANONICALIZATION.md`.

### Minimal phases

- Phase 0: `real_human_seed` (30-50) + existing `synthetic_v1`
- Phase 1: `synthetic_v2` with XTTS segment-stitch
- Phase 2: second engine A/B (for example MOSS-TTS) on same `text_uid`
- Phase 3: `synthetic_v3` accent-stress split

### Manifest v2 example

```json
{
  "sample_id": "s2_en_ru_high_long_0002_clean",
  "text_uid": "txt_en_ru_high_long_0002",
  "prompt_id": "pr_en_ru_high_long_017",
  "source_split": "synthetic_v2",
  "dataset_version": "synthetic_v2.0.0",
  "generator_version": "tts-pipeline-0.4.1",
  "git_sha": "abc123def456",
  "seed": 5090,
  "language_combo": "en_ru",
  "switch_density": "high",
  "switch_pattern": "A_B_A",
  "boundary_type": "clause",
  "utterance_length": "long",
  "display_text": "I need to send the report today, а потом проверю логи и вернусь к ревью.",
  "canonical_text": "i need to send the report today а потом проверю логи и вернусь к ревью",
  "target_lang_spans": [
    {"lang": "en", "start_char": 0, "end_char": 31},
    {"lang": "ru", "start_char": 33, "end_char": 73}
  ],
  "switch_points": [33],
  "audio_path": "data/audio/en_ru/clean/s2_en_ru_high_long_0002_clean.wav",
  "duration_ms": 18420,
  "sample_rate_hz": 24000,
  "render_mode": "segment_stitch",
  "engine_model_id": "coqui/XTTS-v2",
  "engine_params": {"temperature": 0.65, "top_p": 0.9, "speed": 1.0},
  "speaker_id": "spk_01",
  "speaker_ref_by_lang": {
    "en": "assets/refs/spk_01_en.wav",
    "ru": "assets/refs/spk_01_ru.wav"
  },
  "segments_rendered": [
    {
      "segment_id": "seg_01",
      "lang": "en",
      "text": "I need to send the report today,",
      "segment_audio_path": "data/intermediate/s2_en_ru_high_long_0002/seg_01_en.wav",
      "gain_db": -1.2,
      "pause_before_ms": 0,
      "pause_after_ms": 60
    },
    {
      "segment_id": "seg_02",
      "lang": "ru",
      "text": "а потом проверю логи и вернусь к ревью.",
      "segment_audio_path": "data/intermediate/s2_en_ru_high_long_0002/seg_02_ru.wav",
      "gain_db": -0.4,
      "pause_before_ms": 80,
      "pause_after_ms": 0
    }
  ],
  "rendered_segment_bounds_ms": [
    {"segment_id": "seg_01", "start_ms": 0, "end_ms": 8420},
    {"segment_id": "seg_02", "start_ms": 8340, "end_ms": 18420}
  ],
  "xfade_ms": 40,
  "qa_observed_issues": ["mild_accent_leakage_on_seg_02_start"],
  "accent_leakage_score": 1,
  "word_corruption_score": 0,
  "boundary_artifact_score": 1,
  "overall_accept": true,
  "render_notes": "Boundary is audible but acceptable for benchmark."
}
```

## Local generation pipeline

Current scripts in `scripts/` support a deterministic synthetic pipeline:

1. Generate prompt manifest (text only)
2. Render `clean` audio from prompts
3. Build `noise_light` and `reverb_light` variants
4. Build final benchmark manifest (`1080` rows for defaults)

Run end-to-end:

```bash
make dataset-all
```

Step-by-step:

```bash
make dataset-prompts
make dataset-clean-audio
make dataset-augment
make dataset-manifest
```

By default `dataset-clean-audio` uses `mock` backend for reproducible plumbing tests.
To use a real TTS model, call `scripts/synthesize_tts.py` directly with `--backend coqui`
after installing Coqui TTS in your active environment.

Example with Makefile target:

```bash
make dataset-prompts
make dataset-clean-audio-coqui SPEAKER_WAV=assets/voice_ref.wav
make dataset-augment
make dataset-manifest
```

Container-first flow:

```bash
make image
make dataset-all-coqui-container SPEAKER_WAV=speaker.wav
```

Segment-stitch flow with per-language references:

```bash
make dataset-all-coqui-segment-container \
  SPEAKER_WAV_EN=en.wav \
  SPEAKER_WAV_PL=pl.wav \
  SPEAKER_WAV_RU=ru.wav
```

Default outputs for this target:

- clean/augmented audio: `data/audio_v2/`
- intermediate segment renders: `data/intermediate_v2/`
- final manifest: `data/manifests/synthetic_v2.jsonl`

This mode renders each language segment independently and writes stitch metadata
to sidecar files near clean audio:

- `data/audio/<mix>/clean/<id>.segments.json`

## Fish Audio S2 pilot

Experimental local pipeline is available via Fish Audio Docker images.

Quick CPU pilot:

```bash
make fish-checkpoints
make fish-all FISH_DEVICE=cpu FISH_COUNT=10
```

RTX 5090 path (recommended):

```bash
make fish-all-5090 FISH_COUNT=10
```

`FISH_COUNT` now applies consistently to clean render, augment, and manifest build
by creating a selected prompts file at `.cache/fish/prompts_selected.jsonl`.

By default Fish renderer uses `FISH_MODE=server`, which starts one persistent API
container and sends per-segment `/v1/tts` requests. This avoids reloading model
weights for each segment.

Latency capture (request/connect/read + RTF) for the selected subset:

```bash
make fish-latency FISH_IMAGE=fish-speech-webui:cu129 FISH_DEVICE=cuda FISH_COUNT=20
```

This writes `results/fish_latency.json` with aggregate p50/p95 and per-segment
rows.

Notes:

- `fish-all-5090` builds local image from `fishaudio/fish-speech` with `CUDA_VER=12.9.0` and
  `UV_EXTRA=cu129`, which is the recommended setup for 5090 from upstream issue discussion.
- If needed, override image/build args:
  - `FISH_IMAGE_5090` (default `fish-speech-webui:cu129`)
  - `FISH_CUDA_VER` (default `12.9.0`)
  - `FISH_UV_EXTRA` (default `cu129`)
- Outputs are written to:
  - audio: `data/audio_fish/`
  - intermediate segments: `data/intermediate_fish/`
  - manifest: `data/manifests/synthetic_fish_s2.jsonl`

Minimal dependency check:

```bash
python3 -c "import TTS; import torch; print(torch.cuda.is_available())"
```
