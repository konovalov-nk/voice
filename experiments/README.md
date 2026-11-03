# Local experiment overlays

Upstream projects used in this repo are **not vendored**. They are cloned into
the working tree for experiments and excluded via the "third-party" section of
the root `.gitignore`. Everything that is ours lives in this folder, either as
a new file or as a patch against a pinned upstream commit.

| Folder | Upstream | Contents |
| --- | --- | --- |
| `miso-tts/` | [MisoLabsAI/MisoTTS](https://github.com/MisoLabsAI/MisoTTS) `5e70d7a` | `EXPERIMENTS_PROTOCOL.md`, benchmark/measurement scripts for the `compile-modes`, `compile-placement` and `flags` experiments |
| `vibevoice/` | [microsoft/VibeVoice](https://github.com/microsoft/VibeVoice) `1807b85`, [vibevoice-community/VibeVoice](https://github.com/vibevoice-community/VibeVoice) `493b186` | launch scripts |
| `fish-speech/` | [fishaudio/fish-speech](https://github.com/fishaudio/fish-speech) `45a9bda` (fork: [konovalov-nk/fish-speech](https://github.com/konovalov-nk/fish-speech)) | `changes.patch` plus new files: VRAM logging/plotting scripts and Prometheus/Grafana monitoring setup |
| `bsa-file-extractor/` | [Sw4T/BSAFileExtractor](https://github.com/Sw4T/BSAFileExtractor) `cce03df` | `changes.patch` with the local fixes needed to extract Skyrim voice archives |

## Applying a patch

```bash
git clone https://github.com/fishaudio/fish-speech
git -C fish-speech checkout 45a9bda
git -C fish-speech apply /path/to/voice/experiments/fish-speech/changes.patch

# new files that are not part of the patch
cp -r experiments/fish-speech/scripts experiments/fish-speech/tools \
      experiments/fish-speech/examples fish-speech/
```

Same for `bsa-file-extractor/changes.patch` and
`miso-tts/flags/generator.patch` (applied to a MisoTTS checkout).

## Notes

- `miso-tts/flags/generator.patch` **disables the audio watermark** to measure
  raw generation quality. It is a benchmark-only change — never ship it.
- `generator.py.bak`, `.cursor/` plans and other editor/backup files from the
  original working copies were intentionally not carried over.
- These overlays are snapshots, not submodules. If an upstream clone is
  updated, re-apply the patches and adjust them as needed.
