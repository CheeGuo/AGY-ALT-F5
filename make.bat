@echo off
set PYTHON=py

if "%1"=="install" goto install
if "%1"=="playground" goto playground
if "%1"=="run-cli" goto runcli
if "%1"=="pelita-lite" goto pelitalite
if "%1"=="pelita-demo" goto pelitademo
if "%1"=="pelita-test" goto pelitatest
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

:pelitalite
%PYTHON% -m uvicorn pelita.lite.server:app --host 0.0.0.0 --port 8080
goto end

:pelitademo
%PYTHON% -m pelita.demo
goto end

:pelitatest
%PYTHON% -m unittest discover -s pelita/tests -t .
goto end

:help
echo Available commands:
echo   make install     - Install project dependencies
echo   make playground  - Launch the ADK Web UI / playground
echo   make run-cli     - Run agent in interactive CLI
echo   make pelita-lite - Run Pelita low-bandwidth web app + SMS webhook on :8080
echo   make pelita-demo - Run Pelita multilingual demo scenarios
echo   make pelita-test - Run Pelita offline tests

:end
