SHELL := /bin/bash

PREFIX ?= $(HOME)/.local
BIN_DIR := $(PREFIX)/bin
SYSTEMD_USER_DIR := $(HOME)/.config/systemd/user
RECORDER_CONFIG_DIR := $(HOME)/.config/recorderd
RECORDER_CONFIG := $(RECORDER_CONFIG_DIR)/config.toml
HYPRLAND_CONFIG ?= $(HOME)/.config/hypr/hyprland.conf

.PHONY: setup install configure-target setup-hyprland-binds restart-service transcribe transcribe-both transcribe-select transcribe-all transcribe-all-force

setup:
	$(MAKE) install
	$(MAKE) configure-target
	$(MAKE) setup-hyprland-binds
	$(MAKE) restart-service

install:
	install -Dm755 recorderd "$(BIN_DIR)/recorderd"
	install -Dm755 recorderctl "$(BIN_DIR)/recorderctl"
	install -Dm755 recorder-transcribe "$(BIN_DIR)/recorder-transcribe"
	install -Dm644 recorderd.service "$(SYSTEMD_USER_DIR)/recorderd.service"
	if [ ! -f "$(RECORDER_CONFIG)" ]; then install -Dm644 config.toml.example "$(RECORDER_CONFIG)"; fi
	systemctl --user daemon-reload
	systemctl --user enable --now recorderd.service

configure-target:
	python3 scripts/configure_target.py

setup-hyprland-binds:
	python3 scripts/setup_hyprland_binds.py

restart-service:
	systemctl --user restart recorderd.service

transcribe:
	recorder-transcribe --last

transcribe-both:
	recorder-transcribe --last --both

transcribe-select:
	recorder-transcribe --select

transcribe-all:
	recorder-transcribe --all

transcribe-all-force:
	recorder-transcribe --all --force
