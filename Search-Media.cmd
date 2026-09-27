@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title "Anime & Hentai Multi-Site Next-Gen Streaming TUI"
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

if exist "%REPO_DIR%tools\media-tui\target\release\media-tui.exe" (
    "%REPO_DIR%tools\media-tui\target\release\media-tui.exe" %*
) else (
    python "%REPO_DIR%tools\hsearch.py" %*
)

if errorlevel 1 pause
