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
    netstat -ano | findstr "LISTENING" | findstr "18082"
) else (
    echo       Wallet: ARRETE
)

echo.
echo [3/5] Adresse du wallet...
set "WALLET_RPC=http://127.0.0.1:18082/json_rpc"
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"get_address\",\"params\":{}}" %WALLET_RPC% 2^>nul') do echo       %%i

echo.
echo [4/5] Soldes...
set "ADDR=YOUR_WALLET_ADDRESS_HERE"
set "VLT=3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f"

echo       XEL:
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"get_balance\",\"params\":{\"address\":\"%ADDR%\"}}" %WALLET_RPC% 2^>nul') do echo         %%i

echo       VLT:
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"get_balance\",\"params\":{\"address\":\"%ADDR%\",\"asset\":\"%VLT%\"}}" %WALLET_RPC% 2^>nul') do echo         %%i

echo.
echo [5/5] Enregistrement mineur...
echo       (necessite 1000 VLT minimum)
echo.

echo ========================================================================
echo   Verification terminee.
echo ========================================================================
pause

endlocal


