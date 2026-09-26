@echo off
py -3 "%~dp0cookie_sync_host.py" %* 2>nul
if %errorlevel% neq 0 (
    python "%~dp0cookie_sync_host.py" %*
)
