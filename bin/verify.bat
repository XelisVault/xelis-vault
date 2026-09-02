@echo off
setlocal

echo ========================================================================
echo   XELIS Vault - Verification complete (Windows)
echo ========================================================================
echo.

echo [1/5] Config...
if exist "%USERPROFILE%\.xelis-vault\config\config.json" (
    echo       config.json present
    type "%USERPROFILE%\.xelis-vault\config\config.json"
) else (
    echo       ERREUR: config.json introuvable
)

echo.
echo [2/5] Wallet en cours...
tasklist /FI "IMAGENAME eq xelis_wallet.exe" 2>nul | findstr /I "xelis_wallet.exe" >nul
if %errorlevel% == 0 (
    echo       Wallet: DEMARRE
    netstat -ano | findstr "LISTENING" | findstr "18083"
) else (
    echo       Wallet: ARRETE
)

echo.
echo [3/5] Adresse du wallet...
set "WALLET_RPC=http://127.0.0.1:18083/json_rpc"
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"get_address\",\"params\":{}}" %WALLET_RPC% 2^>nul') do echo       %%i

echo.
echo [4/5] Soldes...
echo       XEL:
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"get_balance\",\"params\":{\"address\":\"%ADDR%\"}}" %WALLET_RPC% 2^>nul') do echo         %%i

echo.
echo [5/5] Enregistrement mineur...
echo       (necessite 1000 VLT minimum)
echo.

echo ========================================================================
echo   Verification terminee.
echo ========================================================================
pause

endlocal

