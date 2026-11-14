@echo off
title VeloRoute AI Gateway
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

:: Locate Python executable
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.\.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo.
        echo ==============================================================
        echo   [ERROR] Python was not found on your system!
        echo   Please install Python 3.11+ from https://www.python.org/
        echo ==============================================================
        echo.
        pause
        exit /b 1
    )
)

:: Ensure .env exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Initializing .env configuration from .env.example...
        copy /y ".env.example" ".env" >nul
    )
)

:: Server configuration
set HOST=127.0.0.1
set PORT=8000

cls
echo ==============================================================
echo                 ⚡ VeloRoute AI Gateway ⚡
echo ==============================================================
echo.
echo   * Web Dashboard  : http://%HOST%:%PORT%
echo   * Web Console    : http://%HOST%:%PORT%/console
echo   * OpenAI API     : http://%HOST%:%PORT%/v1/chat/completions
echo   * Anthropic API  : http://%HOST%:%PORT%/v1/messages
echo   * Gemini API     : http://%HOST%:%PORT%/v1beta/models
echo   * Health Check   : http://%HOST%:%PORT%/health
echo.
echo ==============================================================
echo [INFO] Opening Web Dashboard in your browser...
start "" "http://%HOST%:%PORT%"

echo [INFO] Starting VeloRoute Gateway server (Press Ctrl+C to stop)...
echo.

%PYTHON_EXE% -m veloroute.cli ui --host %HOST% --port %PORT%

if %errorlevel% neq 0 (
    echo.
    echo ==============================================================
    echo   [ERROR] Server exited unexpectedly with code %errorlevel%.
    echo ==============================================================
)
pause
