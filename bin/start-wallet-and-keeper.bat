@echo off
setlocal

set "WALLET_BIN=%USERPROFILE%\.xelis-vault\bin\xelis_wallet.exe"
set "WALLET_DIR=%USERPROFILE%\.xelis-vault\wallets\xvault-user"

echo ========================================================================
echo   XELIS Vault - Wallet + Oracle Keeper (VLT)
echo ========================================================================
echo.

echo [1/3] Nettoyage des instances precedentes...
taskkill /F /FI "WINDOWTITLE eq XELIS Vault - Wallet" 2>nul
taskkill /F /FI "WINDOWTITLE eq XELIS Vault - Oracle Keeper" 2>nul
timeout /t 1 /nobreak >nul

echo [2/3] Lancement du wallet...
start "XELIS Vault - Wallet" cmd /c ""%WALLET_BIN%" --network testnet --wallet-path "%WALLET_DIR%" --daemon-address https://testnet-node.xelis.io"

echo [3/3] Attente du wallet (max 60s)...
set /a waited=0
:wait_wallet
timeout /t 3 /nobreak >nul
set /a waited+=3
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:18083/json_rpc 2>nul | findstr "200" >nul
if errorlevel 1 (
    if %waited% geq 60 (
        echo ERREUR: wallet inaccessible apres 60s. Verifiez la fenetre du wallet.
        pause
        exit /b 1
    )
    goto wait_wallet
)

echo       Wallet pret.

echo.
echo Lancement de l'oracle keeper...
start "XELIS Vault - Oracle Keeper" cmd /c "xvault-miner --run-keeper"

echo.
echo ========================================================================
echo   Termine. Deux fenetres doivent etre ouvertes :
echo     - Wallet
echo     - Oracle Keeper (soumet prix XEL/USD + heartbeats)
echo ========================================================================
echo.
pause

endlocal

