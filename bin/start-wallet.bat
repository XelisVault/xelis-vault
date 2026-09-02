@echo off
setlocal

set "WALLET_BIN=%USERPROFILE%\.xelis-vault\bin\xelis_wallet.exe"
set "WALLET_DIR=%USERPROFILE%\.xelis-vault\wallets\xvault-user"

echo ========================================================================
echo   XELIS Vault - Wallet (testnet)
echo ========================================================================
echo.
echo Lancement du wallet...
echo.

start "XELIS Vault - Wallet" cmd /c ""%WALLET_BIN%" --network testnet --wallet-path "%WALLET_DIR%" --daemon-address https://testnet-node.xelis.io"

timeout /t 3 /nobreak >nul

echo.
echo Wallet lance. Verifiez la fenetre du wallet pour l'adresse et les soldes.
echo.
pause

endlocal

