# XELIS Vault - Clean Distribution

This is a clean distribution of XELIS Vault for new users.

## Prerequisites

- **Python 3.10+** installed
- **Windows**: PowerShell or Command Prompt
- **Linux/macOS**: Bash shell

## Quick Start

### 1. Installation

**Windows:**
```powershell
# Open PowerShell in this directory
.\install.ps1
```

**Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

### 2. Configuration

Edit `config/config.json` with your settings:
```json
{
  "rpc_url": "https://testnet-node.xelis.io",
  "wallet_url": "http://127.0.0.1:18082",
  "wallet_user": "wallet",
  "wallet_pass": "your_secure_password",
  "miner_address": "",
  "miner_endpoint": "",
  "services": "oracle",
  "miner_threads": "4"
}
```

### 3. Start the Wallet

**Windows:**
```powershell
.\bin\start-wallet.bat your_password
```

**Linux/macOS:**
```bash
./bin/start-wallet.sh your_password
```

### 4. Start the Miner Console

**Windows:**
```powershell
.\bin\xvault-miner.bat
```

**Linux/macOS:**
```bash
./bin/xvault-miner.sh
```

## Directory Structure

```
xelis-vault-clean/
├── bin/                    # Executables and launch scripts
│   ├── xelis_wallet.exe    # XELIS wallet binary (Windows)
│   ├── xelis_miner.exe     # XELIS miner binary (Windows)
│   ├── start-wallet.bat    # Windows wallet launcher
│   ├── start-wallet.sh     # Unix wallet launcher
│   ├── xvault-miner.bat    # Windows miner console
│   └── xvault-miner.sh     # Unix miner console
├── config/
│   └── config.json         # Your configuration (edit this)
├── src/
│   ├── contracts/          # Smart contracts (.slx)
│   ├── scripts/            # Python scripts
│   └── docs/               # Documentation
├── logs/                   # Log files (created on first run)
├── wallets/                # Wallet data (created on first run)
└── README.md               # This file
```

## First Time Setup

1. **Run the installer** - This creates the Python virtual environment
2. **Edit config.json** - Set your wallet password and preferences
3. **Start the wallet** - This creates your wallet file
4. **Get testnet coins** - Use the faucet to get XEL and VLT
5. **Register as miner** - Use the miner console to register

## Getting Testnet Coins

1. Start your wallet
2. Copy your wallet address
3. Visit the XELIS testnet faucet
4. Request XEL and VLT tokens

## Registering as a Miner

1. Start the miner console: `xvault-miner.bat` (or `.sh`)
2. Select "Actions" → "Register as miner"
3. Follow the prompts
4. You need 1000 VLT for stake + XEL for fees

## Running the Oracle Keeper

The oracle keeper submits price feeds to earn rewards.

**Windows:**
```powershell
.\bin\start-wallet-and-keeper.bat your_password
```

**Linux/macOS:**
```bash
./bin/start-wallet-and-keeper.sh your_password
```

## Troubleshooting

### Wallet won't start
- Check if port 18082 is available
- Ensure Python is installed
- Check `logs/wallet.log` for errors

### Miner registration fails
- Ensure you have 1000 VLT + XEL for fees
- Check wallet is synced
- Verify endpoint is accessible

### Keeper says "no provider wallets"
- Ensure wallet is running on port 18082
- Check `config/config.json` wallet_url

## Support

- Documentation: `src/docs/`
- Whitepaper: `src/docs/WHITEPAPER.md`
- User Guide: `src/docs/USER_GUIDE.md`

## Important Notes

- **This is TESTNET software** - Do not use mainnet funds
- **Backup your wallet** - Save your seed phrase securely
- **Keep passwords safe** - Cannot be recovered
- **Endpoint changes** - If using trycloudflare.com, update endpoint when tunnel restarts
