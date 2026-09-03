@echo off
setlocal enabledelayedexpansion

:: ============================================================================
::   XELIS Vault - Wallet + Oracle Keeper Launcher
:: ============================================================================
::   This script starts the wallet and the oracle keeper in separate windows.
::   It waits for the wallet to be ready before launching the keeper.
:: ============================================================================

set "VAULT_DIR=%USERPROFILE%\.xelis-vault"
set "WALLET_BIN=%VAULT_DIR%\bin\xelis_wallet.exe"
set "WALLET_DIR=%VAULT_DIR%\wallets\xvault-user"
set "LOG_DIR=%VAULT_DIR%\logs"
set "RPC_PORT=18082"
set "RPC_URL=http://127.0.0.1:%RPC_PORT%/json_rpc"
set "DAEMON_RPC=https://testnet-node.xelis.io"

:: Seed can be provided via environment variable
if not defined XELIS_WALLET_SEED (
    echo.
    echo   [!] No seed provided. Set XELIS_WALLET_SEED environment variable
    echo       or create wallet manually with: xelis_wallet.exe --generate
    echo.
    echo       Example: set XELIS_WALLET_SEED=your seed words here
    pause
    exit /b 1
)
set "SEED=%XELIS_WALLET_SEED%"

:: Try to find xvault-miner.exe in common locations
set "KEEPER_EXE="
if exist "%VAULT_DIR%\bin\xvault-miner.exe" (
    set "KEEPER_EXE=%VAULT_DIR%\bin\xvault-miner.exe"
) else if exist "%VAULT_DIR%\build\dist\xvault-miner.exe" (
    set "KEEPER_EXE=%VAULT_DIR%\build\dist\xvault-miner.exe"
) else if exist "%~dp0xvault-miner.exe" (
    set "KEEPER_EXE=%~dp0xvault-miner.exe"
)

:: Alternative: use Python script directly
set "KEEPER_PY=%VAULT_DIR%\src\scripts\xvault-miner.py"

echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║         XELIS Vault - Wallet + Oracle Keeper Launcher          ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.

:: ── Step 1: Check prerequisites ──────────────────────────────────────────
echo  [1/4] Checking prerequisites...

if not exist "%WALLET_BIN%" (
    echo.
    echo    [!] ERROR: Wallet binary not found:
    echo        %WALLET_BIN%
    echo.
    echo    Please ensure xelis_wallet.exe is in the bin directory.
    pause
    exit /b 1
)
echo        [OK] Wallet binary found

:: Check for keeper (exe or python)
set "KEEPER_AVAILABLE=0"
if defined KEEPER_EXE (
    set "KEEPER_AVAILABLE=1"
    echo        [OK] Keeper binary found: %KEEPER_EXE%
) else if exist "%KEEPER_PY%" (
    set "KEEPER_AVAILABLE=1"
    echo        [OK] Keeper Python script found
) else (
    echo        [!] Keeper not found - will start wallet only
    echo            Place xvault-miner.exe in %VAULT_DIR%\bin\ or run:
    echo            python %VAULT_DIR%\src\scripts\xvault-miner.py
)

:: ── Step 2: Kill existing instances ──────────────────────────────────────
echo.
echo  [2/4] Cleaning up existing instances...
taskkill /F /FI "WINDOWTITLE eq XELIS Vault - Wallet" 2>nul | findstr "terminated" >nul && echo        Killed existing Wallet
taskkill /F /FI "WINDOWTITLE eq XELIS Vault - Oracle Keeper" 2>nul | findstr "terminated" >nul && echo        Killed existing Keeper
taskkill /F /FI "IMAGENAME eq xelis_wallet.exe" 2>nul | findstr "terminated" >nul && echo        Killed orphan wallet process
timeout /t 1 /nobreak >nul
echo        [OK] Cleanup done

:: ── Step 3: Start wallet ─────────────────────────────────────────────────
echo.
echo  [3/4] Starting wallet...
echo        RPC: %RPC_URL%
echo        Address: (will be displayed after wallet starts)

start "XELIS Vault - Wallet" cmd /k "title XELIS Vault - Wallet && "%WALLET_BIN%" --seed "%SEED%" --network testnet --wallet-path "%WALLET_DIR%" --password testpass --rpc-bind-address 127.0.0.1:%RPC_PORT% --rpc-username wallet --rpc-password testpass --daemon-address %DAEMON_RPC%"

:: ── Step 4: Wait for wallet and start keeper ─────────────────────────────
echo.
echo  [4/4] Waiting for wallet to be ready...

set /a waited=0
:wait_wallet
timeout /t 1 /nobreak >nul
set /a waited+=1

:: Check if wallet process is still running
tasklist /FI "IMAGENAME eq xelis_wallet.exe" 2>nul | findstr "xelis_wallet.exe" >nul
if errorlevel 1 (
    echo.
    echo    [!] ERROR: Wallet process exited unexpectedly.
    echo        Check the wallet window for errors.
    pause
    exit /b 1
)

:: Try to reach the RPC
curl -s -o nul -w "%%{http_code}" %RPC_URL% 2>nul | findstr "200 401" >nul
if errorlevel 1 (
    if %waited% lss 90 (
        <nul set /p "=        Waiting... (%waited%s)`r"
        goto wait_wallet
    ) else (
        echo.
        echo    [!] WARNING: Wallet not responding after %waited%s.
        echo        The wallet window is open but RPC is not accessible.
        echo        You can still use the wallet manually.
    )
) else (
    echo        [OK] Wallet ready (%waited%s)
)

:: Start keeper if available
if "%KEEPER_AVAILABLE%"=="1" (
    echo.
    echo        Starting Oracle Keeper...
    
    if defined KEEPER_EXE (
        start "XELIS Vault - Oracle Keeper" cmd /k "title XELIS Vault - Oracle Keeper && "%KEEPER_EXE%" --run-keeper --rpc %DAEMON_RPC% --wallet-url %RPC_URL%"
    ) else (
        start "XELIS Vault - Oracle Keeper" cmd /k "title XELIS Vault - Oracle Keeper && python "%KEEPER_PY%" --run-keeper --rpc %DAEMON_RPC% --wallet-url %RPC_URL%"
    )
    
    echo        [OK] Keeper started in new window
)

:: ── Summary ──────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║                        LAUNCH COMPLETE                         ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║  Two windows should be open:                                   ║
echo  ║    - XELIS Vault - Wallet       (RPC on port %RPC_PORT%)            ║
if "%KEEPER_AVAILABLE%"=="1" (
echo  ║    - XELIS Vault - Oracle Keeper (submits prices + heartbeats)   ║
) else (
echo  ║                                                                  ║
echo  ║  To start keeper manually:                                       ║
echo  ║    python %VAULT_DIR:\=\\%\\src\\scripts\\xvault-miner.py                ║
)
echo  ║                                                                  ║
echo  ║  Logs: %VAULT_DIR%\logs\                                         ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo  Press any key to close this launcher window...
pause >nul

endlocal
