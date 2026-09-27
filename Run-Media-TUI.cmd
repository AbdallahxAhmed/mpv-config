@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title "MovieBox-Style Media TUI (Ratatui + Sixel)"
set "REPO_DIR=%~dp0"
cd /d "%REPO_DIR%"

"%REPO_DIR%tools\media-tui\target\release\media-tui.exe" %*

if errorlevel 1 pause
