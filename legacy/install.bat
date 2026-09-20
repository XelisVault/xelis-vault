@echo off
REM ============================================================================
REM  XELIS Vault — Windows Quick Installer (wrapper for PowerShell)
REM ============================================================================
REM  Download and run, or double-click this file.
REM  Or from cmd:  install.bat
REM ============================================================================

REM Try PowerShell Core first, then Windows PowerShell
where pwsh >nul 2>nul
if %errorlevel% == 0 (
    pwsh -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
) else (
    powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
)
