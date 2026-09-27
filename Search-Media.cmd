@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Anime & Hentai Multi-Site Quality Search
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

python "%REPO_DIR%tools\hsearch.py" %*

if errorlevel 1 pause
