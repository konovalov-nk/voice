PYTHON ?= python3
CONTAINER_RUNTIME ?= podman
IMAGE ?= asr-codeswitch-bench:dev
CONTAINERFILE ?= Containerfile
PROMPTS ?= data/manifests/prompts_v1.jsonl
MANIFEST ?= data/manifests/synthetic_v1.jsonl
SMOKE_MANIFEST ?= data/manifests/synthetic_stage1_smoke.jsonl
SMOKE_MODEL_ID ?= whisper_large_v3_turbo_fw
SMOKE_PREDICTIONS ?= results/stage1_smoke.predictions.json
SMOKE_REPORT ?= results/stage1_smoke.report.json
SMOKE_SUMMARY ?= results/STAGE1_SMOKE_SUMMARY.md
COQUI_MODEL ?= tts_models/multilingual/multi-dataset/xtts_v2
SPEAKER_WAV ?= speaker.wav
SPEAKER_WAV_EN ?= en.wav
SPEAKER_WAV_PL ?= pl.wav
SPEAKER_WAV_RU ?= ru.wav
RENDER_MODE ?= full_text
SOURCE_SPLIT ?= synthetic_v1
DATASET_VERSION ?= synthetic_v1.0.0
GENERATOR_VERSION ?= tts-pipeline-0.2
GIT_SHA ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
PAUSE_MS ?= 60
XFADE_MS ?= 40
AUDIO_ROOT ?= data/audio
INTERMEDIATE_ROOT ?= data/intermediate
V2_AUDIO_ROOT ?= data/audio_v2
V2_INTERMEDIATE_ROOT ?= data/intermediate_v2
V2_MANIFEST ?= data/manifests/synthetic_v2.jsonl
AB_OUT ?= results/ab.csv
AB_COUNT ?= 40
AB_MIX ?=
AB_CONDITION ?= clean
FISH_IMAGE ?= fishaudio/fish-speech:latest
FISH_DOCKER ?= docker
FISH_REPO_DIR ?= .cache/fish-speech
FISH_IMAGE_5090 ?= fish-speech-webui:cu129
FISH_CUDA_VER ?= 12.9.0
FISH_UV_EXTRA ?= cu129
FISH_CHECKPOINTS_DIR ?= checkpoints/s2-pro
FISH_DEVICE ?= cpu
FISH_MODE ?= server
FISH_SERVER_PORT ?= 18080
FISH_SERVER_NAME ?= fish-s2-api
FISH_REQUEST_TIMEOUT ?= 300
FISH_AUDIO_ROOT ?= data/audio_fish
FISH_INTERMEDIATE_ROOT ?= data/intermediate_fish
FISH_MANIFEST ?= data/manifests/synthetic_fish_s2.jsonl
FISH_COUNT ?= 0
FISH_PROMPTS_SELECTED ?= .cache/fish/prompts_selected.jsonl
FISH_LATENCY_OUT ?= results/fish_latency.json
FISH_COMPILE ?= 1
FISH_SMOKE_TEXT ?= hello, this is a fish smoke test
FISH_SMOKE_TIMEOUT ?= 30
FISH_SMOKE_OUT ?= results/fish_smoke.wav
FISH_SMOKE_REF_AUDIO ?=
FISH_SMOKE_REF_TEXT ?=
FISH_SMOKE_REFERENCE_ID ?=
FISH_SMOKE_CHUNK_LENGTH ?= 200
FISH_SMOKE_STREAM_TEXT ?= hello, this is a bit longer test [pause] and [laugh] I think it is working! A bit longer example here to see stability. I wonder if I am making right things [pause] or not. Lets test tags! [whisper] see if I can whisper [echo] or maybe do echo? [clearing throat] well... the right man in the wrong place can make [stuttering] all ... the.. difference ... [emphasis] in the world!
# FISH_SMOKE_STREAM_TEXT ?= hello, this is a short test
FISH_SMOKE_STREAM_TIMEOUT ?= 240
FISH_SMOKE_STREAM_OUT ?= results/fish_smoke_stream.wav
FISH_SMOKE_STREAM_MIN_GAP ?= 0.2
FISH_SMOKE_STREAM_MIN_CHUNKS ?= 2
# chunk_length: API allows 100-300. Smaller => more batches => more stream chunks.
FISH_SMOKE_STREAM_CHUNK_LENGTH ?= 120
FISH_SMOKE_CONTAINER ?= fish-s2-api-compile
FISH_SMOKE_PROFILE ?= 1
FISH_PROFILE_INFERENCE ?= 0
# KV cache length (pre-allocated; drives peak VRAM). 512 = default. If 512 still OOM on 32GB, try 384.
# Optional: FISH_MAX_NEW_TOKENS_CAP=80 further limits generation length (use with cache=384 for 32GB).
# Optional: FISH_RECORD_MEMORY_HISTORY=1 enables CUDA alloc history; then GET /v1/debug/memory?dump=1 writes .pickle snapshot.
FISH_CACHE_MAX_SEQ_LEN ?= 512
FISH_MAX_NEW_TOKENS_CAP ?=
FISH_RECORD_MEMORY_HISTORY ?=
FISH_REFERENCE_ID ?= demo-en
FISH_REFERENCE_AUDIO ?= en.wav
FISH_REFERENCE_TEXT ?= optional transcript
SGLANG_OMNI_DIR ?= .cache/sglang-omni
SGLANG_CONFIG ?= configs/s2pro_tts_5090.yaml
SGLANG_MODEL_PATH ?= checkpoints/s2-pro
SGLANG_PORT ?= 8000
SGLANG_PYTHON ?= python3
SGLANG_SPEECH_TIMEOUT ?= 10
SGLANG_PREFILL_ATTN_BACKEND ?= triton
SGLANG_DECODE_ATTN_BACKEND ?= flashinfer
S2_FORCE_SDPA_KVCACHE ?= 1
SGLANG_SMOKE_TEXT ?= hello, this is a bit longer test [pause] and [laugh] I think it is working!
SGLANG_SMOKE_TIMEOUT ?= 10
SGLANG_SMOKE_OUT ?= results/sglang_smoke.wav
SGLANG_CONTAINER_NAME ?= sglang-flashinfer-test
SGLANG_SMOKE_REF_AUDIO ?=
SGLANG_SMOKE_REF_TEXT ?=

ifeq ($(CONTAINER_RUNTIME),podman)
GPU_ARGS ?= --device nvidia.com/gpu=all --security-opt=label=disable
else
GPU_ARGS ?= --gpus all
endif

image:
	$(CONTAINER_RUNTIME) build -f $(CONTAINERFILE) -t $(IMAGE) .

shell:
	$(CONTAINER_RUNTIME) run --rm -it \
		$(GPU_ARGS) \
		-v "$$PWD":/workspace:Z \
		-w /workspace \
		$(IMAGE)

smoke-container:
	$(CONTAINER_RUNTIME) run --rm \
		$(GPU_ARGS) \
		-v "$$PWD":/workspace:Z \
		-w /workspace \
		$(IMAGE) \
		python scripts/bench.py --model-id whisper_large_v3_turbo_fw --manifest data/schema/sample.manifest.jsonl --output results/smoke.json

smoke:
	@echo "Run a tiny benchmark slice first"
	@echo "Example: $(PYTHON) scripts/bench.py --model-id whisper_large_v3_turbo_fw --manifest data/schema/sample.manifest.jsonl --output results/smoke.json"

eval:
	@echo "Example: $(PYTHON) scripts/evaluate.py --predictions results/smoke.json --report results/smoke.report.json"

summary:
	@echo "Example: $(PYTHON) scripts/summarize.py --report results/smoke.report.json --out results/SUMMARY.md"

validate-manifest:
	$(PYTHON) scripts/validate_manifest.py --manifest $(MANIFEST)

build-smoke-manifest:
	$(PYTHON) scripts/build_smoke_manifest.py --manifest $(MANIFEST) --out $(SMOKE_MANIFEST)

stage1-smoke: validate-manifest build-smoke-manifest
	$(PYTHON) scripts/bench.py --model-id $(SMOKE_MODEL_ID) --manifest $(SMOKE_MANIFEST) --output $(SMOKE_PREDICTIONS)
	$(PYTHON) scripts/evaluate.py --predictions $(SMOKE_PREDICTIONS) --report $(SMOKE_REPORT)
	$(PYTHON) scripts/summarize.py --report $(SMOKE_REPORT) --out $(SMOKE_SUMMARY)

dataset-prompts:
	$(PYTHON) scripts/generate_prompts.py --out $(PROMPTS)

dataset-clean-audio:
	$(PYTHON) scripts/synthesize_tts.py --manifest-in $(PROMPTS) --audio-root $(AUDIO_ROOT) --backend mock --render-mode $(RENDER_MODE)

dataset-clean-audio-coqui:
	COQUI_TOS_AGREED=1 TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 TTS_HOME=.cache/tts $(PYTHON) scripts/synthesize_tts.py --manifest-in $(PROMPTS) --audio-root $(AUDIO_ROOT) --segment-root $(INTERMEDIATE_ROOT) --backend coqui --coqui-model $(COQUI_MODEL) --speaker-wav "$(SPEAKER_WAV)" --render-mode $(RENDER_MODE)

dataset-clean-audio-coqui-segment:
	COQUI_TOS_AGREED=1 TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 TTS_HOME=.cache/tts $(PYTHON) scripts/synthesize_tts.py --manifest-in $(PROMPTS) --audio-root $(AUDIO_ROOT) --segment-root $(INTERMEDIATE_ROOT) --backend coqui --render-mode segment_stitch --coqui-model $(COQUI_MODEL) --speaker-wav-en "$(SPEAKER_WAV_EN)" --speaker-wav-pl "$(SPEAKER_WAV_PL)" --speaker-wav-ru "$(SPEAKER_WAV_RU)" --pause-ms $(PAUSE_MS) --xfade-ms $(XFADE_MS)

dataset-augment:
	$(PYTHON) scripts/augment_audio.py --manifest-in $(PROMPTS) --audio-root $(AUDIO_ROOT)

dataset-manifest:
	$(PYTHON) scripts/build_manifest.py --prompts $(PROMPTS) --audio-root $(AUDIO_ROOT) --out $(MANIFEST) --strict --source-split $(SOURCE_SPLIT) --dataset-version $(DATASET_VERSION) --generator-version $(GENERATOR_VERSION) --git-sha $(GIT_SHA) --engine-model-id $(COQUI_MODEL) --render-mode $(RENDER_MODE)

dataset-all: dataset-prompts dataset-clean-audio dataset-augment dataset-manifest

dataset-all-coqui: dataset-prompts dataset-clean-audio-coqui dataset-augment dataset-manifest

dataset-all-coqui-segment: dataset-prompts
	$(MAKE) dataset-clean-audio-coqui-segment AUDIO_ROOT=$(V2_AUDIO_ROOT) INTERMEDIATE_ROOT=$(V2_INTERMEDIATE_ROOT)
	$(MAKE) dataset-augment AUDIO_ROOT=$(V2_AUDIO_ROOT)
	$(MAKE) dataset-manifest AUDIO_ROOT=$(V2_AUDIO_ROOT) MANIFEST=$(V2_MANIFEST) RENDER_MODE=segment_stitch SOURCE_SPLIT=synthetic_v2 DATASET_VERSION=synthetic_v2.0.0

dataset-all-coqui-container:
	$(CONTAINER_RUNTIME) run --rm \
		$(GPU_ARGS) \
		-e COQUI_TOS_AGREED=1 \
		-e TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
		-e TTS_HOME=/workspace/.cache/tts \
		-v "$$PWD":/workspace:Z \
		-w /workspace \
		$(IMAGE) \
		make dataset-all-coqui SPEAKER_WAV=$(SPEAKER_WAV) COQUI_MODEL=$(COQUI_MODEL)

dataset-all-coqui-segment-container:
	$(CONTAINER_RUNTIME) run --rm \
		$(GPU_ARGS) \
		-e COQUI_TOS_AGREED=1 \
		-e TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
		-e TTS_HOME=/workspace/.cache/tts \
		-v "$$PWD":/workspace:Z \
		-w /workspace \
		$(IMAGE) \
		make dataset-all-coqui-segment COQUI_MODEL=$(COQUI_MODEL) SPEAKER_WAV_EN=$(SPEAKER_WAV_EN) SPEAKER_WAV_PL=$(SPEAKER_WAV_PL) SPEAKER_WAV_RU=$(SPEAKER_WAV_RU) PAUSE_MS=$(PAUSE_MS) XFADE_MS=$(XFADE_MS) V2_AUDIO_ROOT=$(V2_AUDIO_ROOT) V2_INTERMEDIATE_ROOT=$(V2_INTERMEDIATE_ROOT) V2_MANIFEST=$(V2_MANIFEST)

qa-ab:
	$(PYTHON) scripts/qa_ab.py --manifest-a data/manifests/synthetic_v1.jsonl --manifest-b $(V2_MANIFEST) --label-a v1 --label-b v2 --count $(AB_COUNT) --condition $(AB_CONDITION) --out $(AB_OUT) $(if $(AB_MIX),--mix $(AB_MIX),)

fish-checkpoints:
	$(FISH_DOCKER) run --rm --entrypoint bash -v "$$PWD":/workspace:Z $(FISH_IMAGE) -lc "/app/.venv/bin/hf download fishaudio/s2-pro --local-dir /workspace/$(FISH_CHECKPOINTS_DIR)"

fish-build-5090:
	@if [ ! -d "$(FISH_REPO_DIR)" ]; then \
		mkdir -p "$(dir $(FISH_REPO_DIR))"; \
		git clone https://github.com/fishaudio/fish-speech.git "$(FISH_REPO_DIR)"; \
	else \
		git -C "$(FISH_REPO_DIR)" pull --ff-only; \
	fi
	$(FISH_DOCKER) build --platform linux/amd64 -f "$(FISH_REPO_DIR)/docker/Dockerfile" --build-arg BACKEND=cuda --build-arg CUDA_VER=$(FISH_CUDA_VER) --build-arg UV_EXTRA=$(FISH_UV_EXTRA) --target webui -t $(FISH_IMAGE_5090) "$(FISH_REPO_DIR)"

fish-all-5090: fish-build-5090
	$(MAKE) fish-checkpoints FISH_IMAGE=$(FISH_IMAGE_5090)
	$(MAKE) fish-all FISH_IMAGE=$(FISH_IMAGE_5090) FISH_DEVICE=cuda

FISH_WARMUP_REFERENCE_ID ?=
FISH_CACHE_MAX_SEQ_LEN ?=
fish-serve-compile:
	$(FISH_DOCKER) rm -f $(FISH_SERVER_NAME) >/dev/null 2>&1 || true
	$(FISH_DOCKER) run -d --rm --name $(FISH_SERVER_NAME) -p $(FISH_SERVER_PORT):8080 $(if $(filter cuda,$(FISH_DEVICE)),--gpus all,) \
		-e FISH_PROFILE_INFERENCE=$(FISH_PROFILE_INFERENCE) \
		$(if $(filter cuda,$(FISH_DEVICE)),-e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,) \
		$(if $(FISH_WARMUP_REFERENCE_ID),-e FISH_WARMUP_REFERENCE_ID=$(FISH_WARMUP_REFERENCE_ID),) \
		$(if $(FISH_CACHE_MAX_SEQ_LEN),-e FISH_CACHE_MAX_SEQ_LEN=$(FISH_CACHE_MAX_SEQ_LEN),) \
		$(if $(FISH_MAX_NEW_TOKENS_CAP),-e FISH_MAX_NEW_TOKENS_CAP=$(FISH_MAX_NEW_TOKENS_CAP),) \
		$(if $(FISH_RECORD_MEMORY_HISTORY),-e FISH_RECORD_MEMORY_HISTORY=$(FISH_RECORD_MEMORY_HISTORY),) \
		-e PYTHONPATH=/workspace/$(FISH_REPO_DIR) \
		-v "$$PWD":/workspace:Z -w /workspace --entrypoint /app/.venv/bin/python $(FISH_IMAGE) /workspace/$(FISH_REPO_DIR)/tools/api_server.py --listen 0.0.0.0:8080 --device $(FISH_DEVICE) --llama-checkpoint-path /workspace/$(FISH_CHECKPOINTS_DIR) --decoder-checkpoint-path /workspace/$(FISH_CHECKPOINTS_DIR)/codec.pth $(if $(filter 1 true TRUE yes YES,$(FISH_COMPILE)),--compile,)

# Same as fish-serve-compile but without torch.compile (lower VRAM, no JIT spike, slower tokens/s)
fish-serve:
	$(MAKE) fish-serve-compile FISH_COMPILE=0

fish-smoke:
	$(PYTHON) scripts/fish_smoke.py --base-url http://127.0.0.1:$(FISH_SERVER_PORT) --timeout $(FISH_SMOKE_TIMEOUT) --text "$(FISH_SMOKE_TEXT)" --ref-audio "$(FISH_SMOKE_REF_AUDIO)" --ref-text "$(FISH_SMOKE_REF_TEXT)" --reference-id "$(FISH_SMOKE_REFERENCE_ID)" --chunk-length $(FISH_SMOKE_CHUNK_LENGTH) --out $(FISH_SMOKE_OUT) --container-name $(FISH_SMOKE_CONTAINER) $(if $(filter 1 true TRUE yes YES,$(FISH_SMOKE_PROFILE)),--profile,)

fish-smoke-stream:
	$(PYTHON) scripts/fish_smoke.py --base-url http://127.0.0.1:$(FISH_SERVER_PORT) --timeout $(FISH_SMOKE_STREAM_TIMEOUT) --streaming --min-stream-gap $(FISH_SMOKE_STREAM_MIN_GAP) --min-chunks $(FISH_SMOKE_STREAM_MIN_CHUNKS) --text "$(FISH_SMOKE_STREAM_TEXT)" --ref-audio "$(FISH_SMOKE_REF_AUDIO)" --ref-text "$(FISH_SMOKE_REF_TEXT)" --reference-id "$(FISH_SMOKE_REFERENCE_ID)" --chunk-length $(FISH_SMOKE_STREAM_CHUNK_LENGTH) --out $(FISH_SMOKE_STREAM_OUT) --container-name $(FISH_SMOKE_CONTAINER) $(if $(filter 1 true TRUE yes YES,$(FISH_SMOKE_PROFILE)),--profile,)

# One-shot: wait for server, run memory_metrics in background, run fish-smoke-stream, print memory report. Server must be running.
# FISH_MEMORY_DUMP=1 to also dump snapshot (requires FISH_RECORD_MEMORY_HISTORY=1 at serve start).
fish-smoke-stream-profile:
	bash scripts/fish_smoke_stream_with_memory.sh

# Full E2E for agent: (optionally build), start server, run 2x smoke-stream + memory report; output in results/fish_e2e_report.txt.
# Uses short text so request 1 fits in 32GB; request 2 checks OOM when memory does not drop after request 1.
# Skip build: FISH_E2E_SKIP_BUILD=1. With torch.compile: FISH_COMPILE=1 (first request slower + compiles, may need more VRAM).
fish-e2e-memory-test:
	$(if $(filter-out 1 true TRUE yes YES,$(FISH_E2E_SKIP_BUILD)),$(MAKE) fish-build-5090,)
	$(MAKE) fish-serve-compile FISH_COMPILE=$(or $(FISH_COMPILE),0) \
		FISH_CACHE_MAX_SEQ_LEN=384 FISH_MAX_NEW_TOKENS_CAP=80 \
		FISH_SERVER_PORT=18081 FISH_SERVER_NAME=fish-s2-api FISH_DEVICE=cuda \
		FISH_IMAGE=fish-speech-webui:cu129 FISH_PROFILE_INFERENCE=1
	FISH_SERVER_PORT=18081 FISH_SERVER_NAME=fish-s2-api \
	$(if $(filter 1 true TRUE yes YES,$(FISH_COMPILE)),FISH_E2E_HEALTH_TIMEOUT=900,) \
	FISH_SMOKE_REFERENCE_ID=en FISH_SMOKE_CHUNK_LENGTH=100 FISH_SMOKE_STREAM_CHUNK_LENGTH=100 \
	FISH_SMOKE_STREAM_TEXT="hello, this is a short test" \
	bash scripts/fish_e2e_memory_test.sh

fish-reference-add:
	curl -sS -X POST "http://127.0.0.1:$(FISH_SERVER_PORT)/v1/references/add?format=json" -H "Accept: application/json" -F "id=$(FISH_REFERENCE_ID)" -F "text=$(FISH_REFERENCE_TEXT)" -F "audio=@$(FISH_REFERENCE_AUDIO)"

fish-reference-list:
	curl -sS "http://127.0.0.1:$(FISH_SERVER_PORT)/v1/references/list?format=json" -H "Accept: application/json"

fish-reference-delete:
	curl -sS -X DELETE "http://127.0.0.1:$(FISH_SERVER_PORT)/v1/references/delete?format=json" -H "Accept: application/json" -H "Content-Type: application/json" -d '{"reference_id":"$(FISH_REFERENCE_ID)"}'

# Pre-encode reference wav+txt to .codes.pt. Without FISH_PREENCODE_REF_ID: ID=stem per file (ru.wav -> references/ru/). With: all under references/<REF_ID>/
FISH_PREENCODE_REF_DIR ?= my_voices
FISH_PREENCODE_REF_ID ?=
# Use venv in fish-speech repo (path relative after cd); else fall back to $(PYTHON)
FISH_PREENCODE_PYTHON := $(if $(wildcard $(FISH_REPO_DIR)/.venv/bin/python),.venv/bin/python,$(PYTHON))
fish-preencode:
	cd $(FISH_REPO_DIR) && PYTHONPATH=. $(FISH_PREENCODE_PYTHON) tools/preencode_references.py \
		--input-dir "$(CURDIR)/$(FISH_PREENCODE_REF_DIR)" \
		$(if $(FISH_PREENCODE_REF_ID),--ref-id $(FISH_PREENCODE_REF_ID),) \
		--output-dir "$(CURDIR)/references" \
		--checkpoint-path "$(CURDIR)/$(FISH_CHECKPOINTS_DIR)/codec.pth" \
		--device cpu

fish-clean-audio:
	$(PYTHON) scripts/synthesize_fish_s2.py --manifest-in $(PROMPTS) --audio-root $(FISH_AUDIO_ROOT) --segment-root $(FISH_INTERMEDIATE_ROOT) --checkpoints-dir $(FISH_CHECKPOINTS_DIR) --fish-image $(FISH_IMAGE) --device $(FISH_DEVICE) --mode $(FISH_MODE) --server-port $(FISH_SERVER_PORT) --server-name $(FISH_SERVER_NAME) --request-timeout $(FISH_REQUEST_TIMEOUT) --count $(FISH_COUNT)

fish-augment:
	$(PYTHON) scripts/augment_audio.py --manifest-in $(PROMPTS) --audio-root $(FISH_AUDIO_ROOT)

fish-manifest:
	$(PYTHON) scripts/build_manifest.py --prompts $(PROMPTS) --audio-root $(FISH_AUDIO_ROOT) --out $(FISH_MANIFEST) --strict --source-split synthetic_fish_s2 --dataset-version synthetic_fish_s2.0.1 --generator-version fish-s2-pipeline-0.1 --git-sha $(GIT_SHA) --engine-model-id fishaudio/s2-pro --render-mode segment_stitch

fish-prompts-selected:
	$(PYTHON) scripts/select_manifest_rows.py --manifest $(PROMPTS) --out $(FISH_PROMPTS_SELECTED) --count $(FISH_COUNT)

fish-all: fish-prompts-selected
	$(MAKE) fish-clean-audio PROMPTS=$(FISH_PROMPTS_SELECTED) FISH_COUNT=0
	$(MAKE) fish-augment PROMPTS=$(FISH_PROMPTS_SELECTED)
	$(MAKE) fish-manifest PROMPTS=$(FISH_PROMPTS_SELECTED)

fish-latency: fish-prompts-selected
	$(PYTHON) scripts/synthesize_fish_s2.py --manifest-in $(FISH_PROMPTS_SELECTED) --audio-root $(FISH_AUDIO_ROOT) --segment-root $(FISH_INTERMEDIATE_ROOT) --checkpoints-dir $(FISH_CHECKPOINTS_DIR) --fish-image $(FISH_IMAGE) --device $(FISH_DEVICE) --mode $(FISH_MODE) --server-port $(FISH_SERVER_PORT) --server-name $(FISH_SERVER_NAME) --request-timeout $(FISH_REQUEST_TIMEOUT) --count 0 --no-skip-existing --latency-out $(FISH_LATENCY_OUT) --latency-label "fish_s2"

sglang-serve-flashinfer:
	PYTHONPATH="$$PWD:$$PWD/$(SGLANG_OMNI_DIR)" $(SGLANG_PYTHON) -m sglang_omni.cli.cli serve --model-path "$$PWD/$(SGLANG_MODEL_PATH)" --config "$$PWD/$(SGLANG_CONFIG)" --port $(SGLANG_PORT)

sglang-install-deps:
	$(SGLANG_PYTHON) -m pip install -U pip setuptools wheel
	$(SGLANG_PYTHON) -m pip install msgpack
	$(SGLANG_PYTHON) -m pip install -e "$(SGLANG_OMNI_DIR)[s2pro]"

sglang-serve-flashinfer-container:
	$(CONTAINER_RUNTIME) run --rm -it \
		$(GPU_ARGS) \
		-e CUDA_HOME=/usr/local/cuda \
		-e SGLANG_ENABLE_JIT_DEEPGEMM=0 \
		-e SGLOMNI_SPEECH_TIMEOUT_S=$(SGLANG_SPEECH_TIMEOUT) \
		-e SGLANG_PREFILL_ATTN_BACKEND=$(SGLANG_PREFILL_ATTN_BACKEND) \
		-e SGLANG_DECODE_ATTN_BACKEND=$(SGLANG_DECODE_ATTN_BACKEND) \
		-e S2_FORCE_SDPA_KVCACHE=$(S2_FORCE_SDPA_KVCACHE) \
		-p $(SGLANG_PORT):$(SGLANG_PORT) \
		-v "$$PWD":/workspace:Z \
		-w /workspace \
		$(IMAGE) \
		bash -lc "CUDA_HOME=/usr/local/cuda SGLANG_ENABLE_JIT_DEEPGEMM=0 PYTHONPATH=/workspace:/workspace/$(SGLANG_OMNI_DIR) python /workspace/scripts/sglang_serve_direct.py --model-path /workspace/$(SGLANG_MODEL_PATH) --config /workspace/$(SGLANG_CONFIG) --port $(SGLANG_PORT)"

sglang-serve-sm120-safe:
	$(MAKE) sglang-serve-flashinfer-container \
		SGLANG_PREFILL_ATTN_BACKEND=triton \
		SGLANG_DECODE_ATTN_BACKEND=flashinfer \
		S2_FORCE_SDPA_KVCACHE=1

sglang-smoke-10s:
	$(PYTHON) scripts/sglang_smoke.py --base-url http://127.0.0.1:$(SGLANG_PORT) --timeout $(SGLANG_SMOKE_TIMEOUT) --text "$(SGLANG_SMOKE_TEXT)" --ref-audio "$(SGLANG_SMOKE_REF_AUDIO)" --ref-text "$(SGLANG_SMOKE_REF_TEXT)" --out $(SGLANG_SMOKE_OUT) --container-name $(SGLANG_CONTAINER_NAME)
