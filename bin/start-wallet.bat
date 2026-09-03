@echo off
REM Xelis Vault - Start Wallet (Windows)
REM Usage: start-wallet.bat [password]

setlocal enabledelayedexpansion

REM Find Python
set "PYTHON="
if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON=python"
    ) else (
        echo ERROR: Python not found. Please install Python or create venv.
        pause
        exit /b 1
    )
)

REM Default password
set "PASS=%~1"
if "!PASS!"=="" set "PASS=testpass"

REM Wallet port
set "PORT=18082"

echo.
echo ========================================
echo   XELIS WALLET
echo ========================================
echo.
echo   RPC: http://127.0.0.1:%PORT%/json_rpc
echo   User: wallet
echo   Pass: !PASS!
echo.
echo   Starting wallet...
echo   Press Ctrl+C to stop
echo.

REM Start wallet
"%PYTHON%" src\scripts\onboarding.py wallet --password "!PASS!" --port %PORT%

pause
