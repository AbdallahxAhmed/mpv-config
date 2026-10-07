@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Universal Video Turbo Downloader (16-Stream Turbo Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python -m mpv_config.cli.main download %*

if errorlevel 1 pause
