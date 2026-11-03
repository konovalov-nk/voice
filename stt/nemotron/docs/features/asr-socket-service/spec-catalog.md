# ASR Socket Service — Spec Catalog (coherence taxonomy)

- **Status**: draft
- **Source**: `docs/features/asr-socket-service/pfs.md`, `docs/features/asr-socket-service/tfs/index.md`
- **Format**: coherence-compatible — каждая секция `## spec/...` → одна запись в Dolt-каталоге coherence

---

## Уровни (SpecLevel)

| Уровень | Назначение | Specs |
|---------|-----------|-------|
| `product` | Пользовательские поверхности | 2 — сервис + клиент |
| `system` | Сквозные процессы | 4 — аудио, VAD, ASR, сокет |
| `module` | Бounded capabilities | 0 |
| `component` | Конкретные адаптеры | 4 — pipewire, energy, nemotron, socket server |
| `foundation` | Доменные модели + инфра | 4 — транскрипция, сегмент, pipewire, vad |

**Total: 14 specs, ~42 ACs**

---

## PRODUCT

### spec: `product/asr-socket-service`

- **title**: ASR Socket Service
- **level**: product
- **status**: draft
- **description**: Непрерывно слушает дефолтный микрофон через Pipewire, распознаёт речь Nemotron 3.5, отдаёт текст через Unix socket.

#### AC: `запускается-и-слушает-микрофон`

| поле | значение |
|------|----------|
| title | service starts and listens on default microphone |
| intent | При запуске без аргументов сервис открывает Pipewire stream на дефолтном источнике и начинает слушать |
| review_mode | manual |
| risk_level | medium |
| concerns | [reliability] |

#### AC: `принимает---lang`

| поле | значение |
|------|----------|
| title | accepts --lang flag |
| intent | При `--lang ru-RU` сервис использует указанный язык для распознавания; при `--lang auto` — автоматическое детектирование |
| review_mode | manual |
| risk_level | low |
| concerns | [] |

#### AC: `принимает---socket`

| поле | значение |
|------|----------|
| title | accepts --socket flag |
| intent | При `--socket /tmp/custom.sock` сервис создаёт Unix socket по указанному пути |
| review_mode | manual |
| risk_level | low |
| concerns | [] |

#### AC: `принимает---device`

| поле | значение |
|------|----------|
| title | accepts --device flag |
| intent | При `--device cpu` сервис использует CPU для инференса вместо CUDA |
| review_mode | manual |
| risk_level | low |
| concerns | [] |

#### AC: `graceful-shutdown`

| поле | значение |
|------|----------|
| title | shuts down gracefully on SIGINT/SIGTERM |
| intent | При Ctrl+C сервис закрывает Pipewire стрим, удаляет socket файл, завершается с exit code 0 |
| review_mode | manual |
| risk_level | medium |
| concerns | [reliability] |

#### AC: `не-пишет-мусор`

| поле | значение |
|------|----------|
| title | does not emit garbage for silence/noise |
| intent | Когда микрофон молчит или присутствует только фоновый шум, сервис не отправляет пустые гипотезы клиентам |
| review_mode | automated |
| risk_level | medium |
| concerns | [correctness] |

---

### spec: `product/asr-client`

- **title**: ASR Socket Client
- **level**: product
- **status**: draft
- **description**: Утилита для подключения к Unix socket сервиса и чтения распознанного текста.

#### AC: `подключается-к-сокету`

| поле | значение |
|------|----------|
| title | connects to Unix socket |
| intent | Клиент может подключиться к `/tmp/asr.sock` и начать получать данные |
| review_mode | manual |
| risk_level | low |
| concerns | [] |

#### AC: `получает-строки`

| поле | значение |
|------|----------|
| title | receives text lines |
| intent | После подключения клиент построчно получает распознанный текст |
| review_mode | manual |
| risk_level | low |
| concerns | [] |

#### AC: `переподключается`

| поле | значение |
|------|----------|
| title | reconnects on disconnect |
| intent | При обрыве соединения клиент автоматически переподключается с exponential backoff |
| review_mode | manual |
| risk_level | low |
| concerns | [reliability] |

---

## SYSTEM

### spec: `system/process/audio-capture`

- **title**: Audio Capture from Pipewire
- **level**: system
- **status**: draft
- **description**: Непрерывный захват аудио с дефолтного микрофона через Pipewire.

#### AC: `захватывает-16kHz-mono`

| поле | значение |
|------|----------|
| title | captures 16kHz mono from default source |
| intent | Pipewire stream открывается на дефолтном источнике, аудио ресемплируется в 16kHz mono float32 |
| review_mode | manual |
| risk_level | high |
| concerns | [correctness, reliability] |

#### AC: `пушит-фреймы`

| поле | значение |
|------|----------|
| title | pushes 20ms frames into channel |
| intent | Каждые 20ms аудио фрейм (320 сэмплов) отправляется в crossbeam::Receiver |
| review_mode | manual |
| risk_level | medium |
| concerns | [performance] |

#### AC: `обрабатывает-ошибки-стрима`

| поле | значение |
|------|----------|
| title | handles stream errors |
| intent | При ошибке Pipewire стрима (отключение микрофона, XRUN) сервис логирует и пытается восстановить соединение |
| review_mode | manual |
| risk_level | high |
| concerns | [reliability] |

---

### spec: `system/process/voice-activity-detection`

- **title**: Voice Activity Detection
- **level**: system
- **status**: draft
- **description**: Energy-based VAD для отделения речи от тишины.

#### AC: `отбрасывает-тишину`

| поле | значение |
|------|----------|
| title | drops silent frames below energy threshold |
| intent | Фреймы с RMS ниже `--energy-threshold` (default 0.02) отбрасываются |
| review_mode | automated |
| risk_level | medium |
| concerns: [correctness] |

#### AC: `аккумулирует-сегменты`

| поле | значение |
|------|----------|
| title | accumulates speech into segments |
| intent | Следующие подряд speech-фреймы аккумулируются в VAD сегмент |
| review_mode | manual |
| risk_level | medium |
| concerns: [correctness] |

#### AC: `финализирует-по-паузе`

| поле | значение |
|------|----------|
| title | finalizes segment after max pause |
| intent | Когда тишина превышает `--max-pause-ms` (default 800ms), текущий речевой сегмент финализируется и отправляется в ASR |
| review_mode | automated |
| risk_level | medium |
| concerns: [correctness, performance] |

---

### spec: `system/process/asr-inference`

- **title**: Nemotron ASR Inference
- **level**: system
- **status**: draft
- **description**: Запуск инференса Nemotron 3.5 на VAD сегментах.

#### AC: `запускает-инференс`

| поле | значение |
|------|----------|
| title | runs inference on VAD segments |
| intent | Каждый финализированный VAD сегмент подаётся в модель; результат — распознанный текст |
| review_mode | automated |
| risk_level | high |
| concerns: [correctness, performance] |

#### AC: `конфигурируемый-язык`

| поле | значение |
|------|----------|
| title | supports configurable target language |
| intent | Параметр `--lang` пробрасывается в `model.set_inference_prompt(target_lang)` |
| review_mode | manual |
| risk_level | low |
| concerns: [correctness] |

#### AC: `стрипает-языковые-теги`

| поле | значение |
|------|----------|
| title | strips language tags from output |
| intent | Если `--strip-lang-tags` (default true), теги `<en-US>` удаляются из финального текста |
| review_mode | manual |
| risk_level | low |
| concerns: [correctness] |

#### AC: `слабая-задержка`

| поле | значение |
|------|----------|
| title | low-latency inference |
| intent | Инференс занимает не более 2х кратной длины аудио (RTF < 2) |
| review_mode | automated |
| risk_level | high |
| concerns: [performance] |

---

### spec: `system/process/socket-broadcast`

- **title**: Unix Socket Broadcast
- **level**: system
- **status**: draft
- **description**: Рассылка распознанного текста всем подключенным клиентам через Unix socket.

#### AC: `слушает-сокет`

| поле | значение |
|------|----------|
| title | listens on configurable socket path |
| intent | Сервер создаёт `tokio::net::UnixListener` на пути `--socket` (default `/tmp/asr.sock`) |
| review_mode | manual |
| risk_level | medium |
| concerns: [security] |

#### AC: `принимает-клиентов`

| поле | значение |
|------|----------|
| title | accepts multiple concurrent connections |
| intent | Несколько клиентов могут подключиться одновременно; каждый получает свой broadcast receiver |
| review_mode | manual |
| risk_level | medium |
| concerns: [performance] |

#### AC: `рассылает-гипотезы`

| поле | значение |
|------|----------|
| title | broadcasts hypotheses to all clients |
| intent | Каждая новая гипотеза отправляется всем подключённым клиентам через `tokio::sync::broadcast` |
| review_mode | manual |
| risk_level | high |
| concerns: [correctness] |

#### AC: `отключает-лаггирующих`

| поле | значение |
|------|----------|
| title | drops lagging clients |
| intent | Клиенты, не успевающие читать (backpressure), отключаются с логом; broadcast buffer — 256 слотов |
| review_mode | automated |
| risk_level | low |
| concerns: [reliability] |

#### AC: `очищает-сокет-при-выходе`

| поле | значение |
|------|----------|
| title | removes socket file on shutdown |
| intent | При graceful shutdown `.sock` файл удаляется |
| review_mode | manual |
| risk_level | low |
| concerns: [reliability] |

---

## COMPONENT

### spec: `component/audio/pipewire-source`

- **title**: Pipewire Audio Source
- **level**: component
- **status**: draft
- **description**: Адаптер для открытия Pipewire стрима и преобразования в 16kHz mono.

#### AC: `открывает-default-source`

| поле | значение |
|------|----------|
| title | opens stream from default source node |
| intent | Использует `libspa` / `pipewire-rs` для открытия стрима с дефолтного PW_NODE |
| review_mode | manual |
| risk_level | high |
| concerns: [reliability] |

#### AC: `конвертирует-в-16kHz`

| поле | значение |
|------|----------|
| title | converts to 16kHz mono float32 |
| intent | Аудио ресемплируется до 16000 Hz, микшируется в mono, нормализуется в float32 \[-1.0, 1.0\] |
| review_mode | automated |
| risk_level | medium |
| concerns: [correctness] |

---

### spec: `component/audio/rms-energy-gate`

- **title**: RMS Energy Gate
- **level**: component
- **status**: draft
- **description**: Вычисляет RMS фрейма, сравнивает с порогом, возвращает speech/silence.

#### AC: `вычисляет-rms`

| поле | значение |
|------|----------|
| title | computes RMS on audio frames |
| intent | RMS = sqrt(mean(x²)) для каждого 20ms фрейма (320 сэмплов) |
| review_mode | automated |
| risk_level | low |
| concerns: [correctness] |

#### AC: `конфигурируемый-порог`

| поле | значение |
|------|----------|
| title | configurable energy threshold |
| intent | Порог задаётся через `--energy-threshold`, default 0.02 |
| review_mode | automated |
| risk_level | low |
| concerns: [correctness] |

---

### spec: `component/asr/nemotron-engine`

- **title**: Nemotron Engine
- **level**: component
- **status**: draft
- **description**: Обёртка над `EncDecRNNTBPEModelWithPrompt` для инференса.

#### AC: `загружает-модель`

| поле | значение |
|------|----------|
| title | loads model at startup |
| intent | При старте сервис загружает `nvidia/nemotron-3.5-asr-streaming-0.6b` через `from_pretrained`, кеширует в `~/.cache/huggingface` |
| review_mode | manual |
| risk_level | high |
| concerns: [reliability] |

#### AC: `выполняет-инференс`

| поле | значение |
|------|----------|
| title | runs inference on float32 audio |
| intent | Принимает `&[f32]`, возвращает `Result<String>`. Препроцессинг → encoder → prompt → decoder |
| review_mode | automated |
| risk_level | high |
| concerns: [correctness, performance] |

#### AC: `поддерживает-языки`

| поле | значение |
|------|----------|
| title | supports 40 language locales |
| intent | Все языки из prompt_dictionary модели доступны через параметр target_lang |
| review_mode | manual |
| risk_level | low |
| concerns: [correctness] |

---

### spec: `component/networking/unix-socket-server`

- **title**: Unix Socket Server
- **level**: component
- **status**: draft
- **description**: Асинхронный Unix socket server на tokio с broadcast-рассылкой.

#### AC: `создаёт-socket`

| поле | значение |
|------|----------|
| title | creates socket with umask 077 |
| intent | Сокет создаётся с правами только для владельца (umask 077) |
| review_mode | manual |
| risk_level | medium |
| concerns: [security] |

#### AC: `много-клиентов`

| поле | значение |
|------|----------|
| title | handles N concurrent clients |
| intent | Сервер обслуживает до 64 одновременных клиентов, каждый в отдельной tokio task |
| review_mode | automated |
| risk_level | medium |
| concerns: [performance] |

---

## FOUNDATION

### spec: `foundation/domain/model/asr-transcription`

- **title**: ASR Transcription Model
- **level**: foundation
- **status**: draft
- **description**: Модель данных для распознанного текста.

#### AC: `имеет-текст-и-язык`

| поле | значение |
|------|----------|
| title | has text and language fields |
| intent | Transcription { text: String, lang: String, timestamp: u64 } |
| review_mode | manual |
| risk_level | low |
| concerns: [] |

#### AC: `имеет-timestamp`

| поле | значение |
|------|----------|
| title | has Unix timestamp |
| intent | Поле `ts` содержит Unix timestamp в секундах |
| review_mode | manual |
| risk_level | low |
| concerns: [] |

---

### spec: `foundation/domain/model/audio-segment`

- **title**: Audio Segment Model
- **level**: foundation
- **status**: draft
- **description**: Модель данных для сегмента аудио (VAD сегмент).

#### AC: `держит-float32-сэмплы`

| поле | значение |
|------|----------|
| title | holds float32 samples |
| intent | AudioSegment { samples: Vec<f32>, sample_rate: u32 } |
| review_mode | manual |
| risk_level | low |
| concerns: [] |

---

### spec: `foundation/infra/pipewire-connectivity`

- **title**: Pipewire Connectivity
- **level**: foundation
- **status**: draft
- **description**: Базовая связность с Pipewire: инициализация контекста, подключение к default source.

#### AC: `инициализирует-pipewire`

| поле | значение |
|------|----------|
| title | initializes Pipewire context |
| intent | `pw_init()` + создание `pw_thread_loop` + подключение к `core` |
| review_mode | manual |
| risk_level | high |
| concerns: [reliability] |

#### AC: `обрабатывает-xrun`

| поле | значение |
|------|----------|
| title | handles XRUN underruns |
| intent | При XRUN (underflow/overflow) логирует и продолжает стрим |
| review_mode | manual |
| risk_level | medium |
| concerns: [reliability] |

---

### spec: `foundation/infra/vad-energy-gate`

- **title**: VAD Energy Gate Algorithm
- **level**: foundation
- **status**: draft
- **description**: Алгоритм вычисления RMS и пороговой детекции речи.

#### AC: `rms-независим-от-длины`

| поле | значение |
|------|----------|
| title | RMS computation is length-independent |
| intent | RMS = sqrt(sum(x²) / N), нормализован по длине фрейма |
| review_mode | automated |
| risk_level | low |
| concerns: [correctness] |

#### AC: `hysteresis`

| поле | значение |
|------|----------|
| title | has hysteresis to prevent chatter |
| intent | speech→silence переход требует RMS < порог × 0.7 (hysteresis 30%) |
| review_mode | automated |
| risk_level | low |
| concerns: [correctness] |

---

## Relation Graph

```text
product/asr-socket-service
├── depends_on → system/process/audio-capture
├── depends_on → system/process/asr-inference
├── depends_on → system/process/socket-broadcast
├── constrained_by → system/process/voice-activity-detection
└── has → product/asr-client   [optional companion]

system/process/audio-capture
└── implemented_by → component/audio/pipewire-source

system/process/voice-activity-detection
└── implemented_by → component/audio/rms-energy-gate

system/process/asr-inference
└── implemented_by → component/asr/nemotron-engine

system/process/socket-broadcast
└── implemented_by → component/networking/unix-socket-server

component/audio/pipewire-source
└── implemented_by → foundation/infra/pipewire-connectivity

component/audio/rms-energy-gate
└── uses → foundation/infra/vad-energy-gate
```

---

## Summary

| Категория | Count |
|-----------|-------|
| **Specs** | 14 |
| **ACs** | 42 |
| — product | 10 |
| — system | 17 |
| — component | 8 |
| — foundation | 7 |

| Risk Distribution | | |
|--|---|---|
| critical | 0 | |
| high | 6 | |
| medium | 22 | |
| low | 14 | |

| Concern Distribution | |
|---------------------|---|
| correctness | 14 |
| performance | 4 |
| reliability | 8 |
| security | 2 |
| maintainability | 0 |
