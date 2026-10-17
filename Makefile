.PHONY: install playground run-cli clean help pelita-lite pelita-demo pelita-test

PYTHON ?= py

help:
	@echo Available commands:
	@echo   make install     - Install project dependencies
	@echo   make playground  - Launch the ADK Web UI / playground
	@echo   make run-cli     - Run agent in interactive CLI
	@echo   make pelita-lite - Run Pelita low-bandwidth web app + SMS webhook on :8080
	@echo   make pelita-demo - Run Pelita multilingual demo scenarios
	@echo   make pelita-test - Run Pelita offline tests

install:
	$(PYTHON) -m pip install -e .

playground:
	$(PYTHON) -m google.adk.cli web .

run-cli:
	$(PYTHON) -m google.adk.cli run expense_agent

pelita-lite:
	$(PYTHON) -m uvicorn pelita.lite.server:app --host 0.0.0.0 --port 8080

pelita-demo:
	$(PYTHON) -m pelita.demo

pelita-test:
	$(PYTHON) -m unittest discover -s pelita/tests -t .
