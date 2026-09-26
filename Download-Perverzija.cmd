@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Tube.Perverzija Fast Downloader (Turbo aria2c Speed)
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python "%REPO_DIR%tools\mpvdl.py" %*

if errorlevel 1 pause
