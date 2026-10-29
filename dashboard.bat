@echo off
title LLMCycle Web Dashboard
cd /d "%~dp0"
set PYTHONUTF8=1

if not exist .venv\Scripts\llmcycle.exe (
    echo Error: .venv virtual environment not found in %~dp0
    echo Please install requirements first.
    pause
    exit /b 1
)

set HOST=127.0.0.1
set PORT=8000

echo ==========================================
echo       Starting LLMCycle Dashboard...
echo ==========================================
echo.
echo Dashboard URL: http://%HOST%:%PORT%
echo Opening browser...
start http://%HOST%:%PORT%

.\.venv\Scripts\llmcycle.exe ui --host %HOST% --port %PORT%
pause
