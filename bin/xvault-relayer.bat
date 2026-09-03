@echo off
REM XELIS Vault Relayer CLI launcher (Windows)
REM Uses the venv created by the installer, or system python as fallback.
setlocal

set "VAULT_DIR=%USERPROFILE%\.xelis-vault"

if exist "%VAULT_DIR%\venv\Scripts\python.exe" (
    "%VAULT_DIR%\venv\Scripts\python.exe" "%VAULT_DIR%\src\scripts\relayer_daemon.py" %*
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        python "%VAULT_DIR%\src\scripts\relayer_daemon.py" %*
    ) else (
        echo Error: Python not found. Install Python 3 or run the installer first. >&2
        exit /b 1
    )
)
