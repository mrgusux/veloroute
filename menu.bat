@echo off
title LLMCycle Manager
cd /d "%~dp0"
set PYTHONUTF8=1

:MENU
cls
echo ======================================================
echo                LLMCycle Easy Launcher
echo ======================================================
echo.
echo  [1] Start Web Dashboard (Opens Browser Automatically)
echo  [2] Add Provider / API Keys (Saves to .env)
echo  [3] Edit Provider (Update Base URL / Replace Keys)
echo  [4] Delete Provider (Remove from .env)
echo  [5] View Configured Providers and Keys
echo  [6] Fetch Dynamic Live Models
echo  [7] Test Connection (Ping Providers)
echo  [8] Manage Egress Proxy (View / Set / Clear)
echo  [9] Run Python Example Script
echo  [C] Open Command Prompt (Environment Ready)
echo  [0] Exit
echo.
echo ======================================================
choice /c 123456789C0 /m "Select an option"

if errorlevel 11 exit
if errorlevel 10 goto OPENCMD
if errorlevel 9 goto RUNEXAMPLE
if errorlevel 8 goto PROXYMENU
if errorlevel 7 goto PING
if errorlevel 6 goto MODELS
if errorlevel 5 goto LISTKEYS
if errorlevel 4 goto DELPROV
if errorlevel 3 goto EDITPROV
if errorlevel 2 goto ADDKEY
if errorlevel 1 goto DASHBOARD
goto MENU

:DASHBOARD
cls
echo Starting LLMCycle Dashboard...
start http://127.0.0.1:8000
.\.venv\Scripts\llmcycle.exe ui --host 127.0.0.1 --port 8000
pause
goto MENU

:ADDKEY
cls
echo ======================================================
echo           Add API Key / Custom Provider
echo ======================================================
echo Standard providers: openai, groq, gemini, deepseek, anthropic...
echo Custom providers: apinex, openrouter, or any custom endpoint
echo.
set /p prov="Enter Provider Name: "
if "%prov%"=="" goto MENU
set /p akey="Enter API Key(s) (comma-separated for multi-key): "
if "%akey%"=="" goto MENU
set /p burl="Enter Base URL (Press Enter to skip if standard): "

if not "%burl%"=="" (
    .\.venv\Scripts\llmcycle.exe providers add %prov% %akey% --base-url "%burl%"
) else (
    .\.venv\Scripts\llmcycle.exe keys add %prov% %akey%
)
echo.
echo Provider details saved to .env!
pause
goto MENU

:EDITPROV
cls
echo ======================================================
echo           Edit Existing Provider
echo ======================================================
echo.
set /p prov="Enter Provider Name to Edit: "
if "%prov%"=="" goto MENU
echo.
echo Leave blank and press Enter to keep current value.
set /p nburl="Enter New Base URL (or Enter to keep): "
set /p nkeys="Enter New API Keys (or Enter to keep): "

if not "%nburl%"=="" (
    if not "%nkeys%"=="" (
        .\.venv\Scripts\llmcycle.exe providers edit %prov% --base-url "%nburl%" --keys "%nkeys%"
    ) else (
        .\.venv\Scripts\llmcycle.exe providers edit %prov% --base-url "%nburl%"
    )
) else (
    if not "%nkeys%"=="" (
        .\.venv\Scripts\llmcycle.exe keys edit %prov% "%nkeys%"
    ) else (
        echo No changes requested.
    )
)
echo.
pause
goto MENU

:DELPROV
cls
echo ======================================================
echo           Delete Provider / Remove Key
echo ======================================================
echo.
echo [1] Delete entire provider (removes keys and base URL)
echo [2] Remove a specific key from a provider
echo [0] Cancel
echo.
choice /c 120 /m "Select delete action"
if errorlevel 3 goto MENU
if errorlevel 2 goto DELKEY
if errorlevel 1 goto DELFULLPROV
goto MENU

:DELFULLPROV
echo.
set /p prov="Enter Provider Name to Delete: "
if "%prov%"=="" goto MENU
set /p confirm="Are you sure you want to delete '%prov%'? [Y/N]: "
if /i "%confirm%"=="Y" (
    .\.venv\Scripts\llmcycle.exe providers remove %prov%
) else (
    echo Deletion cancelled.
)
echo.
pause
goto MENU

:DELKEY
echo.
set /p prov="Enter Provider Name: "
if "%prov%"=="" goto MENU
set /p dkey="Enter specific API Key (or hint) to remove: "
if "%dkey%"=="" goto MENU
.\.venv\Scripts\llmcycle.exe keys remove %prov% "%dkey%"
echo.
pause
goto MENU

:LISTKEYS
cls
echo ======================================================
echo               Configured Providers & Keys
echo ======================================================
echo.
.\.venv\Scripts\llmcycle.exe list
echo.
.\.venv\Scripts\llmcycle.exe keys list
echo.
pause
goto MENU

:MODELS
cls
echo ======================================================
echo               Dynamic Live Models
echo ======================================================
echo.
set /p mprov="Enter Provider (Press Enter to list for all): "
if not "%mprov%"=="" (
    .\.venv\Scripts\llmcycle.exe models %mprov%
) else (
    .\.venv\Scripts\llmcycle.exe models
)
echo.
pause
goto MENU

:PING
cls
echo ======================================================
echo                 Testing Connections...
echo ======================================================
echo.
.\.venv\Scripts\llmcycle.exe ping
echo.
pause
goto MENU

:PROXYMENU
cls
echo ======================================================
echo               Egress Proxy Settings
echo ======================================================
echo.
.\.venv\Scripts\llmcycle.exe proxy show
echo.
echo [1] Set new proxy URL
echo [2] Clear proxy
echo [0] Back
echo.
choice /c 120 /m "Select option"
if errorlevel 3 goto MENU
if errorlevel 2 (
    .\.venv\Scripts\llmcycle.exe proxy clear
    pause
    goto MENU
)
if errorlevel 1 (
    set /p purl="Enter proxy URL (e.g. http://127.0.0.1:8080): "
    if not "%purl%"=="" .\.venv\Scripts\llmcycle.exe proxy set "%purl%"
    pause
    goto MENU
)
goto MENU

:RUNEXAMPLE
cls
echo ======================================================
echo               Running example.py...
echo ======================================================
echo.
.\.venv\Scripts\python.exe example.py
echo.
pause
goto MENU

:OPENCMD
cls
echo Starting Command Prompt with virtual environment...
cmd /k "cd /d %~dp0 && .\.venv\Scripts\activate.bat"
goto MENU
