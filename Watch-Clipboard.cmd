@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Universal Clipboard Watcher (16-Stream Turbo Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python -m mpv_config.cli.main download --watch %*

if errorlevel 1 pause
