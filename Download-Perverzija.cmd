@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Tube.Perverzija Fast Downloader (Turbo aria2c Speed)
set "REPO_DIR=c:\Users\Abdallah_Ahmed\Desktop\mpv-config"

if exist "%REPO_DIR%\tools\perverzija_downloader.py" (
    cd /d "%REPO_DIR%"
    python "%REPO_DIR%\tools\perverzija_downloader.py" %*
) else (
    python "%~dp0tools\perverzija_downloader.py" %*
)

if errorlevel 1 pause
