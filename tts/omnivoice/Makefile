PY ?= .venv/bin/python
HOST ?= 127.0.0.1
PORT ?= 8765
SERVER_URL ?= http://$(HOST):$(PORT)
PROMPTS_DIR ?= prompts
PROMPT_GLOB ?= *.txt
NUM_STEP ?= 16
REPEATS ?= 3
WARMUP ?= 1
OUT ?= benchmarks/results/bench_$(shell date +%Y%m%d_%H%M%S).json

.PHONY: help serve bench bench-quick bench-with-server

help:
	@printf "Targets:\n"
	@printf "  make serve            - run OmniVoice API server\n"
	@printf "  make bench            - run benchmark against running server\n"
	@printf "  make bench-quick      - quick benchmark (1 repeat, 1 warmup)\n"
	@printf "  make bench-with-server- start server, run benchmark, stop server\n"

serve:
	$(PY) scripts/server.py --host $(HOST) --port $(PORT) --device cuda:0 --dtype float16

bench:
	$(PY) scripts/benchmark.py \
		--server-url $(SERVER_URL) \
		--prompts-dir $(PROMPTS_DIR) \
		--prompt-glob "$(PROMPT_GLOB)" \
		--num-step $(NUM_STEP) \
		--repeats $(REPEATS) \
		--warmup-runs $(WARMUP) \
		--output $(OUT)

bench-quick:
	$(MAKE) bench REPEATS=1 WARMUP=1 OUT=benchmarks/results/bench_quick_$(shell date +%Y%m%d_%H%M%S).json

bench-with-server:
	bash -lc '$(PY) scripts/server.py --host $(HOST) --port $(PORT) --device cuda:0 --dtype float16 > /tmp/omnivoice_server.log 2>&1 & srv=$$!; trap "kill $$srv" EXIT; sleep 2; $(PY) scripts/benchmark.py --server-url $(SERVER_URL) --prompts-dir $(PROMPTS_DIR) --prompt-glob "$(PROMPT_GLOB)" --num-step $(NUM_STEP) --repeats $(REPEATS) --warmup-runs $(WARMUP) --output $(OUT)'
