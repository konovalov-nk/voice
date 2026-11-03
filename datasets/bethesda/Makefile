.PHONY: all extract convert esm strings-interface manifest clean help
.DEFAULT_GOAL := help

BSA          := "Skyrim - Voices_en0.bsa"
EXTRACTOR    := BSAFileExtractor/BSAFileExtractor.py
VENV_DIR     := BSAFileExtractor/venv
VENV_PY      := $(VENV_DIR)/bin/python
EXTRACTED    := extracted
WAV_DIR      := extracted_wav
CONVERTER    := fuz2wav.py
JOBS         ?= 16
DEPOT        := depot/DepotDownloader
STEAM_USER   ?=
SE_APPID     := 489830
SE_DATA      := 489832
SE_CONTENT   := 489831
GAME_DATA    := game_data
STR_EXTRACTED := iface_extracted/strings
DIALOGUE_JSON := skyrim_dialogue.jsonl
MANIFEST     := voice_manifest.jsonl
SUB_PARSER   := esm2subtitles.py
MANIFEST_BUILDER := build_manifest.py

help:
	@echo "Usage: make <target> [STEAM_USER=yourlogin] [JOBS=16]"
	@echo ""
	@echo "  extract           - extract .fuz from Voices .bsa"
	@echo "  convert           - convert .fuz -> .wav (JOBS=$(JOBS))"
	@echo "  esm               - download Skyrim.esm from Steam"
	@echo "  strings-interface - download Interface.bsa & extract .STRINGS"
	@echo "  dialogue          - parse .esm + string tables -> dialogue.jsonl"
	@echo "  manifest          - build voice_manifest.jsonl (WAV + subtitle)"
	@echo "  all               - extract + convert"
	@echo "  full              - esm + strings-interface + dialogue + manifest"
	@echo "  mp3-sands         - convert wav_sands/ -> mp3_sands/"
	@echo "  clean             - rm extracted artifacts"
	@echo "  reset             - clean + rm venv + game_data"

all: extract convert

full: extract convert esm strings-interface dialogue manifest

extract: $(EXTRACTED) $(VENV_DIR)
	@echo "=== Extracting $(BSA) ... ==="
	cp "$(BSA)" BSAFileExtractor/ 2>/dev/null || true
	cd BSAFileExtractor && $(VENV_PY) $(notdir $(EXTRACTOR)) $(BSA) -o "../$(EXTRACTED)"
	@echo "=== done ==="

convert: $(EXTRACTED) $(VENV_DIR)
	@echo "=== Converting .fuz -> .wav ($(JOBS) workers) ==="
	nice -n 10 ionice -c2 -n7 $(VENV_PY) $(CONVERTER) \
		$(EXTRACTED) $(WAV_DIR) \
		-j $(JOBS) \
		--skip-existing
	@echo "=== done ==="

esm: $(DEPOT)
	@[ -n "$(STEAM_USER)" ] || (echo "ERROR: set STEAM_USER=yourlogin" && exit 1)
	@[ -f $(GAME_DATA)/Data/Skyrim.esm ] && echo "Skyrim.esm already downloaded" || \
		( echo "=== Downloading Skyrim.esm ..." && \
		  echo 'Data/Skyrim.esm' > /tmp/esm_dl.txt && \
		  $(DEPOT) -app $(SE_APPID) -depot $(SE_DATA) \
			-username $(STEAM_USER) -remember-password \
			-dir $(GAME_DATA) -filelist /tmp/esm_dl.txt )

strings-interface: $(DEPOT)
	@[ -n "$(STEAM_USER)" ] || (echo "ERROR: set STEAM_USER=yourlogin" && exit 1)
	@[ -d $(STR_EXTRACTED) ] && echo "Strings already extracted" || \
		( echo "=== Downloading Interface.bsa ..." && \
		  echo 'Data/Skyrim - Interface.bsa' > /tmp/iface_dl.txt && \
		  $(DEPOT) -app $(SE_APPID) -depot $(SE_DATA) \
			-username $(STEAM_USER) -remember-password \
			-dir $(GAME_DATA) -filelist /tmp/iface_dl.txt && \
		  echo "=== Extracting Interface.bsa ..." && \
		  mkdir -p iface_extracted && \
		  cp "$(GAME_DATA)/Data/Skyrim - Interface.bsa" BSAFileExtractor/ && \
		  cd BSAFileExtractor && $(VENV_PY) $(notdir $(EXTRACTOR)) "Skyrim - Interface.bsa" -o "../iface_extracted" )

dialogue: esm strings-interface $(VENV_DIR)
	@echo "=== Parsing .esm + string tables -> $(DIALOGUE_JSON) ..."
	$(VENV_PY) $(SUB_PARSER) $(GAME_DATA)/Data/Skyrim.esm $(STR_EXTRACTED) $(DIALOGUE_JSON)
	@echo "=== done ==="

manifest: $(DIALOGUE_JSON) $(WAV_DIR)
	@echo "=== Building $(MANIFEST) ..."
	$(VENV_PY) $(MANIFEST_BUILDER) $(DIALOGUE_JSON) $(WAV_DIR) $(MANIFEST)
	@echo "=== done ==="

$(EXTRACTED):
	mkdir -p $(EXTRACTED)

$(WAV_DIR):
	mkdir -p $(WAV_DIR)

$(VENV_DIR):
	python -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install -e BSAFileExtractor/bethesda-structs

mp3-sands: wav_sands
	@echo "=== Converting wav_sands -> mp3_sands ==="
	mkdir -p mp3_sands
	for f in wav_sands/*.wav; do \
		ffmpeg -y -v error -i "$$f" "mp3_sands/$$(basename "$$f" .wav).mp3"; \
	done
	@echo "=== done ===" && ls -lh mp3_sands/

clean:
	rm -rf $(EXTRACTED) $(WAV_DIR) wav_sands mp3_sands iface_extracted $(DIALOGUE_JSON) $(MANIFEST)

reset: clean
	rm -rf $(VENV_DIR) $(GAME_DATA)
	rm -rf BSAFileExtractor/venv BSAFileExtractor/"$(BSA)" BSAFileExtractor/"Skyrim - Interface.bsa"
