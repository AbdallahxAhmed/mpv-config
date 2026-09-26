@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Hanime.tv Fast Downloader (16-Stream Turbo Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python "%REPO_DIR%tools\hanime_downloader.py" %*

if errorlevel 1 pause
