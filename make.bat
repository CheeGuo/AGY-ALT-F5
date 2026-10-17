@echo off
set PYTHON=py

if "%1"=="install" goto install
if "%1"=="playground" goto playground
if "%1"=="run-cli" goto runcli
if "%1"=="paham-lite" goto pahamlite
if "%1"=="paham-demo" goto pahamdemo
if "%1"=="paham-test" goto pahamtest
goto help

:install
%PYTHON% -m pip install -e .
goto end

:playground
%PYTHON% -m google.adk.cli web .
goto end

:runcli
%PYTHON% -m google.adk.cli run expense_agent
goto end

:pahamlite
%PYTHON% -m uvicorn paham.lite.server:app --host 0.0.0.0 --port 8080
goto end

:pahamdemo
%PYTHON% -m paham.demo
goto end

:pahamtest
%PYTHON% -m unittest discover -s paham/tests -t .
goto end

:help
echo Available commands:
echo   make install     - Install project dependencies
echo   make playground  - Launch the ADK Web UI / playground
echo   make run-cli     - Run agent in interactive CLI
echo   make paham-lite - Run Paham low-bandwidth web app + SMS webhook on :8080
echo   make paham-demo - Run Paham multilingual demo scenarios
echo   make paham-test - Run Paham offline tests

:end
