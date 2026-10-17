.PHONY: install playground run-cli clean help paham-lite paham-demo paham-test

PYTHON ?= py

help:
	@echo Available commands:
	@echo   make install     - Install project dependencies
	@echo   make playground  - Launch the ADK Web UI / playground
	@echo   make run-cli     - Run agent in interactive CLI
	@echo   make paham-lite - Run Paham low-bandwidth web app + SMS webhook on :8080
	@echo   make paham-demo - Run Paham multilingual demo scenarios
	@echo   make paham-test - Run Paham offline tests

install:
	$(PYTHON) -m pip install -e .

playground:
	$(PYTHON) -m google.adk.cli web .

run-cli:
	$(PYTHON) -m google.adk.cli run expense_agent

paham-lite:
	$(PYTHON) -m uvicorn paham.lite.server:app --host 0.0.0.0 --port 8080

paham-demo:
	$(PYTHON) -m paham.demo

paham-test:
	$(PYTHON) -m unittest discover -s paham/tests -t .
