@echo off
setlocal

set "WALLET_RPC=http://127.0.0.1:18082/json_rpc"
set "ADDR=YOUR_WALLET_ADDRESS_HERE"
set "VLT=3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f"

echo ========================================================================
echo   XELIS Vault - Verification du wallet
echo ========================================================================
echo.

echo [1/4] Test de connectivit?? RPC...
curl -s -o nul -w "HTTP %%{http_code}" %WALLET_RPC% 2>nul
echo.

echo.
echo [2/4] Adresse du wallet...
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"get_address\",\"params\":{}}" %WALLET_RPC% 2^>nul') do echo %%i

echo.
echo [3/4] Solde XEL...
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"get_balance\",\"params\":{\"address\":\"%ADDR%\"}}" %WALLET_RPC% 2^>nul') do echo %%i

echo.
echo [4/4] Solde VLT...
for /f "delims=" %%i in ('curl -s -X POST -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"get_balance\",\"params\":{\"address\":\"%ADDR%\",\"asset\":\"%VLT%\"}}" %WALLET_RPC% 2^>nul') do echo %%i

echo.
echo ========================================================================
echo   Verification terminee.
echo ========================================================================
pause

endlocal


