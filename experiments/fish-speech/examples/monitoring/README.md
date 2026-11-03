# Fish Speech — Prometheus + Grafana (optional)

Стек мониторинга для метрик API-сервера Fish Speech. **Не обязателен**: приложение отдаёт `/metrics` в формате Prometheus; при необходимости вы сами поднимаете Prometheus и Grafana.

## Требования

- Запущенный API-сервер Fish Speech с эндпоинтом `http://127.0.0.1:8080/metrics` (например `make run-server` из корня репо).
- Docker и Docker Compose.

## Запуск

Из **корня репозитория**:

```bash
docker compose -f examples/monitoring/docker-compose.yaml -p fish-monitoring up -d
```

Или из этой папки:

```bash
cd examples/monitoring
docker compose up -d
```

- **Grafana:** http://localhost:3000 (логин `admin`, пароль `admin`; при первом входе можно сменить).
- **Prometheus:** http://localhost:9090 (targets: Status → Targets — должен быть `fish-speech` в Up).

Дашборд **Fish Speech TTS** подхватывается автоматически (папка Fish Speech в Dashboards).

## Порты

Используется `network_mode: host`, поэтому:

- Prometheus слушает **9090** на хосте.
- Grafana слушает **3000** на хосте.

Если порты заняты, измените их в `docker-compose.yaml` или остановите конфликтующие сервисы.

## Конфигурация Prometheus

`prometheus.yml` настроен на scrape `127.0.0.1:8080`. Если API слушает другой хост/порт (например, в другой сети или в Docker без host), измените `targets` в `prometheus.yml` (например `host.docker.internal:8080` для доступа с контейнера к серверу на хосте при отключённом host network).

## Метрики на дашборде

- **VRAM (GB)** — выделенная и пиковая память GPU.
- **TTS request rate** — число запросов в секунду по типу (streaming / non-streaming).
- **TTS request duration** — латентность запроса (P50, P99).
- **Time to first audio** — время до первого аудио-сегмента (TTFA).
- **Model params (GB)** — статические веса по компонентам (llm_slow, llm_fast, dac).
- **Per-function VRAM peak** — пик VRAM по шагам пайплайна.
- **Pipeline step latency** — P99 по шагам (prefill, decode_n_tokens, decode_one_token, forward_fast).

Подробнее про метрики — в `docs/docker-32gb-rtx5090.md` и `tools/server/metrics.py`.
