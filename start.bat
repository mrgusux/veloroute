@echo off
setlocal
title VeloRoute AI Gateway
cd /d "%~dp0"
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "HOST=127.0.0.1"
set "PORT=8000"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

cls
echo ==============================================================
echo                 VeloRoute AI Gateway
echo ==============================================================
echo.
echo   * Web Dashboard  : http://%HOST%:%PORT%
echo   * Web Console    : http://%HOST%:%PORT%/console
echo   * OpenAI Proxy   : http://%HOST%:%PORT%/v1/chat/completions
echo   * Anthropic Proxy: http://%HOST%:%PORT%/v1/messages
echo   * Gemini Proxy   : http://%HOST%:%PORT%/v1beta/models
echo   * Health Check   : http://%HOST%:%PORT%/health
echo.
echo ==============================================================

REM Check if .env exists; if not, initialize from .env.example
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        echo [INFO] Initializing .env configuration from .env.example...
        copy /y "%~dp0.env.example" "%~dp0.env" >nul
    )
)

REM Verify Virtual Environment with all installed dependencies
if not exist "%VENV_PY%" (
    echo.
    echo ==============================================================
    echo   [ERROR] Virtual environment not found at:
    echo   %VENV_PY%
    echo.
    echo   Please verify that the .venv folder exists.
    echo ==============================================================
    echo.
    pause
    exit /b 1
)

echo [INFO] Opening Web Dashboard in your default browser...
start "" "http://%HOST%:%PORT%"

echo [INFO] Starting VeloRoute Gateway server (Press Ctrl+C to stop)...
echo.

"%VENV_PY%" -m veloroute.cli ui --host %HOST% --port %PORT%

if %errorlevel% neq 0 (
    echo.
    echo ==============================================================
    echo   [ERROR] VeloRoute server stopped with exit code %errorlevel%.
    echo ==============================================================
    echo.
)
pause