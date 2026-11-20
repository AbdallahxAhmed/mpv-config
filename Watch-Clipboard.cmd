@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Universal Clipboard Watcher (16-Stream Turbo Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

rem The CLI lives in the venv install.ps1 creates; fall back to a "python"
rem on PATH for checkouts installed some other way.
set "MPV_CONFIG_PY=%LOCALAPPDATA%\mpv-config\venv\Scripts\python.exe"
if not exist "%MPV_CONFIG_PY%" set "MPV_CONFIG_PY=python"
"%MPV_CONFIG_PY%" -m mpv_config.cli.main download --watch %*

if errorlevel 1 pause
