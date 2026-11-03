# OmniVoice Local Server + Benchmark

## Start server

```bash
make serve
```

## Run benchmark (server already running)

```bash
make bench
```

## One-shot benchmark (starts and stops server automatically)

```bash
make bench-with-server
```

## Prompts folder

- `prompts/factorio_mix_long.txt`
- `prompts/short_ru.txt`
- `prompts/short_en.txt`

## Output metrics

Benchmark JSON contains:

- `ttfb_ms`
- `ttfa_ms`
- `total_ms`
- `server_gen_ms`
- `audio_duration_s`
- `audio_bytes`
- `rtf`
