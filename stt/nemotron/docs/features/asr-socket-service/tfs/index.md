# TFS: ASR Microphone Socket Service

- **Level**: system
- **Status**: draft
- **Concerns**: performance, reliability

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    asr-socket-service                    │
│                                                          │
│  [Pipewire]──audio──> [AudioSource]                      │
│                            │                             │
│                            ▼                             │
│                    [VAD / energy gate]                   │
│                            │                             │
│                     ┌──────┴──────┐                      │
│                     ▼             ▼                      │
│              [silence]      [speech]                      │
│                 │               │                        │
│                 │               ▼                        │
│                 │        [RingBuffer<chunks>]             │
│                 │               │                        │
│                 │               ▼                        │
│                 │        [Nemotron ASR]                   │
│                 │               │                        │
│                 │               ▼                        │
│                 │        [PostProcess]                    │
│                 │        (strip lang tags,               │
│                 │         merge partial hyps)            │
│                 │               │                        │
│                 ▼               ▼                        │
│           [Discard]     ┌──────────────┐                 │
│                         │  Unix Socket  │                 │
│                         │  /tmp/asr.sock│                 │
│                         └──────┬───────┘                 │
│                                │                         │
│               ◄──── connect ───┤                         │
│               ├── Client A     │                         │
│               ├── Client B     │                         │
│               └── ...          │                         │
│                                │                         │
│              send(hyp_text) ───┤                         │
└──────────────────────────────────────────────────────────┘
```

## Components

### AudioSource (`crates/asr-audio`)
- Opens Pipewire stream from default source node
- 16kHz mono, 20ms frames
- Pushes audio chunks into a crossbeam channel

### VAD / Energy Gate
- Simple RMS energy threshold (configurable)
- Drops silence chunks
- Accumulates speech runs into VAD segments
- On silence longer than `max_pause_ms` → finalize segment

### RingBuffer
- `VecDeque<f32>` with max duration (e.g. 30s) — sliding window
- New chunks push to back, old ones pop from front when over limit
- On VAD segment end → send buffer content to ASR

### Nemotron ASR (`infer` module)
- Loads model at startup (from HF, cached in `~/.cache`)
- Runs single-file batch inference on the VAD segment
- Configurable `target_lang`

### PostProcess
- Strip `<lang>` tags from output if `strip_lang_tags=true`
- Remove empty hypotheses
- Join segments into lines

### Unix Socket Server (`crates/asr-socket`)
- `tokio::net::UnixListener` on `/tmp/asr.sock`
- Each connected client gets a `tokio::sync::broadcast` receiver
- New hypotheses are broadcast to all connected clients
- Clients that don't read fast enough are dropped (broadcast lag)

## API / Interfaces

### Unix Socket Protocol
- **Transport**: Unix domain socket (stream)
- **Address**: `/tmp/asr.sock` (configurable via `--socket`)
- **Format**: line-delimited JSON or plain text
- **Connect**: `nc -U /tmp/asr.sock` or any Unix socket client

### Message format (JSONL)
```json
{"text": "hello world this is a test", "lang": "en-US", "ts": 1712345678}
```

Plain text mode (default):
```
hello world this is a test
```

### CLI
```
asr-socket-service [OPTIONS]

Options:
  --lang <LANG>        Target language [default: en-US]
  --socket <PATH>      Unix socket path [default: /tmp/asr.sock]
  --device <DEVICE>    Torch device [default: cuda]
  --energy-threshold <FLOAT>  VAD RMS threshold [default: 0.02]
  --max-pause-ms <MS>  Max silence to finalize segment [default: 800]
  --strip-lang-tags    Strip language tags from output [default: true]
```

## Data model

### In-memory state
| Name | Type | Description |
|------|------|-------------|
| `audio_rx` | `crossbeam::Receiver<Vec<f32>>` | Audio chunks from Pipewire |
| `vad_buffer` | `VecDeque<f32>` | Current speech segment |
| `broadcast_tx` | `tokio::sync::broadcast::Sender<String>` | Fan-out to socket clients |
| `model` | `EncDecRNNTBPEModelWithPrompt` | Loaded ASR model |

### Broadcast channel capacity
- **buffer**: 256 slots
- **lag**: clients that fall behind are dropped silently

## Security and abuse controls

| Threat | Mitigation |
|--------|-----------|
| Любой процесс в системе может читать сокет | Сокет создаётся с umask 077 (только владелец) |
| Мусор в микрофон (шум, музыка) забивает канал | RMS energy gate + max segment duration |
| Клиент не читает данные | `broadcast` drop-on-lag |

## Observability

- **Log**: `INFO` при запуске/остановке, `DEBUG` при гипотезах
- **Metric**: количество распознанных слов в минуту (stderr, human-readable)
- **Signal**: при `SIGINT`/`SIGTERM` — gracefull shutdown (flush + close)

## Test strategy

| Tier | Scope |
|------|-------|
| Unit | Energy gate, ring buffer, post-processing |
| Integration | Socket server: connect, send, receive with timeout |
| Manual | Запуск с реальным микрофоном, `nc -U` как клиент |
