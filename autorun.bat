:: autorun.bat
@echo off
title BITU
cd /d "%~dp0"
set "PYTHONPATH=src"
set "PYTHONUNBUFFERED=1"
set "BITU_EXPLORER_DEBUG=1"
"%~dp0.venv\Scripts\python.exe" -m cli.start
if errorlevel 1 pause