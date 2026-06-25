CONFIG_DIR  := $(HOME)/.config/throne
CONFIG_FILE := $(CONFIG_DIR)/rules.toml
SERVICE_DIR := $(HOME)/.config/systemd/user
SERVICE     := throne.service

.PHONY: run install uninstall enable disable deps help

help:
	@echo "targets: deps, run, install, uninstall, enable, disable"

deps:
	uv add python-xlib tomli
	sudo apt-get install -y wmctrl xdotool x11-utils

run:
	python throne.py

install:
	@mkdir -p $(CONFIG_DIR)
	@if [ ! -f $(CONFIG_FILE) ]; then \
		cp rules.example.toml $(CONFIG_FILE); \
		echo "Created $(CONFIG_FILE)"; \
	else \
		echo "$(CONFIG_FILE) already exists, skipping"; \
	fi
	@mkdir -p $(HOME)/.local/bin
	@cp throne.py $(HOME)/.local/bin/throne
	@chmod +x $(HOME)/.local/bin/throne
	@echo "Installed to ~/.local/bin/throne"

enable: install
	@mkdir -p $(SERVICE_DIR)
	@cp $(SERVICE) $(SERVICE_DIR)/$(SERVICE)
	systemctl --user daemon-reload
	systemctl --user enable --now $(SERVICE)
	@echo "throne enabled and started"

disable:
	systemctl --user disable --now $(SERVICE)
	@rm -f $(SERVICE_DIR)/$(SERVICE)
	systemctl --user daemon-reload
	@echo "throne disabled"

uninstall: disable
	rm -f $(HOME)/.local/bin/throne
	@echo "Removed ~/.local/bin/throne"
	@echo "Config left intact at $(CONFIG_DIR)"
