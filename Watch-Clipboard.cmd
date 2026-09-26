@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Tube.Perverzija Clipboard Watcher (Turbo aria2c Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python "%REPO_DIR%tools\perverzija_downloader.py" --watch %*

if errorlevel 1 pause
