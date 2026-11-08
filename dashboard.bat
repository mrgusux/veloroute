@echo off
title VeloRoute Web Dashboard
cd /d "%~dp0"
set PYTHONUTF8=1

if not exist .venv\Scripts\python.exe (
    echo Error: .venv virtual environment not found in %~dp0
    echo Please install requirements first.
    pause
    exit /b 1
)

set HOST=127.0.0.1
set PORT=8000

echo ==========================================
echo       Starting VeloRoute Dashboard...
echo ==========================================
echo.
echo Dashboard URL: http://%HOST%:%PORT%
echo Opening browser...
start http://%HOST%:%PORT%

if exist .venv\Scripts\veloroute.exe (
    .\.venv\Scripts\veloroute.exe ui --host %HOST% --port %PORT%
) else (
    .\.venv\Scripts\python.exe -m veloroute.cli ui --host %HOST% --port %PORT%
)
pause
