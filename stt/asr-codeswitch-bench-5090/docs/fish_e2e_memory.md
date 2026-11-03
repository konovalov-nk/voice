# Fish-speech E2E memory test (for agent)

Автономный прогон для отладки OOM: один вызов без ручных шагов.

## Команда

Из корня репозитория (`asr-codeswitch-bench-5090`):

```bash
make fish-e2e-memory-test
```

С опциями (сервер уже собран, референс en, дамп снапшота):

```bash
make fish-e2e-memory-test FISH_E2E_SKIP_BUILD=1 FISH_SMOKE_REFERENCE_ID=en \
  FISH_SMOKE_CHUNK_LENGTH=100 FISH_SMOKE_STREAM_CHUNK_LENGTH=100 FISH_MEMORY_DUMP=1
```

## Что делает

1. При необходимости собирает образ (`fish-build-5090`), если не задано `FISH_E2E_SKIP_BUILD=1`.
2. Останавливает старый контейнер, поднимает сервер с `FISH_CACHE_MAX_SEQ_LEN=384`, `FISH_MAX_NEW_TOKENS_CAP=80`, порт 18081.
3. Ждёт готовности сервера (до 180 с).
4. В фоне пишет метрики памяти в `memory_metrics.jsonl`.
5. Первый запрос: `make fish-smoke-stream`.
6. Снимает память после первого запроса.
7. Второй запрос: снова `make fish-smoke-stream` (проверка OOM на втором запросе).
8. Снимает память после второго запроса, хвост логов контейнера, хвост `memory_metrics.jsonl`.
9. При `FISH_MEMORY_DUMP=1` дергает `/v1/debug/memory?dump=1` (нужен `FISH_RECORD_MEMORY_HISTORY=1` при старте сервера).

## Результат

Текстовый отчёт пишется в **`results/fish_e2e_report.txt`**. В нём:

- Request 1: OK / FAIL  
- Request 2: OK / OOM_OR_FAIL  
- Память после 1-го и 2-го запроса (`allocated_gb`, `max_allocated_gb`)  
- Хвост логов контейнера (ошибки CUDA OOM и т.п.)  
- Последние строки `memory_metrics.jsonl`  
- При дампе — `snapshot_path` или `snapshot_error`

Агент может запустить `make fish-e2e-memory-test`, дождаться завершения и прочитать `results/fish_e2e_report.txt` для анализа OOM без копипаста контекста.
