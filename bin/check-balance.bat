@echo off
setlocal

set "WALLET_RPC=http://127.0.0.1:18083/json_rpc"

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
echo ========================================================================
echo   Verification terminee.
echo ========================================================================
pause

endlocal

