# XELIS Vault — CLI Guide

## For Miners: `xvault-miner`

### First-time setup — fully automatic (v12R)

```bash
xvault-miner --setup
```

The onboarding wizard configures everything for you:

1. **Wallet** — three options, presented automatically:
   - *Already running*: enter RPC URL + credentials once, validated live.
   - *Not installed*: the official `xelis_wallet` release binary is downloaded
     automatically (Linux/Windows; on macOS, build-from-source instructions are shown).
   - *New wallet*: a seed phrase is generated **locally** with the exact Xelis
     mnemonic scheme (24 words + checksum), displayed **once** for backup, then
     the wallet is launched in the background and synced to the network.
   - *Import*: paste your existing 24/25-word seed (validated before use).
2. **Daemon** — auto-detects `http://127.0.0.1:18081`, or enter a custom node,
   or continue offline (degraded dashboard).
3. **Contracts** — loaded automatically from the bundled `network/testnet.json`.
   You NEVER type contract addresses manually.
4. **Services** — oracle / chat / both (default: both).

Your miner address is read from the wallet itself. Everything is stored in
`~/.xelis-vault/config/config.json`; subsequent launches go straight to the
dashboard.

> Security: seeds are generated and stay on your machine; they are displayed
> exactly once.

### Legacy manual setup

The old per-field prompts (`interactive_setup`) remain available as a fallback
when the bundled network file is missing.

---

## Historical notes (contracts not deployed era)

> ⚠️ The section below predates the v12.x testnet deployments and the v12R
> auto-configuration. Kept for reference only.

## For Miners: `xvault-miner` (legacy)

### First-time setup
```bash
xvault-miner --setup
```
Interactive setup will ask for:
- XELIS daemon RPC URL
- Wallet RPC URL
- Your miner address
- Public endpoint URL
- Services (oracle, chat, or both)
- Contract addresses

### Start mining
```bash
xvault-miner --miner
```

### Start with specific services
```bash
xvault-miner --services oracle    # Oracle only
xvault-miner --services chat      # Chat only
xvault-miner --services both      # Both (default)
```

### Dry run (no transactions)
```bash
xvault-miner --dry-run
```

### Dashboard features
The dashboard shows in real-time:
- Miner status (active/inactive)
- Stake amount (VLT)
- Reputation score (0-10000) and tier (Excellent/Good/Warning/Critical/Banned)
- Total rewards earned
- Total slashed
- Valid/total submissions
- Services enabled (oracle/chat)
- Protocol stats (budget, distribution, budget factor, active miners)
- Price feeds (XEL/USD, deviation, sources, staleness)

### Enable compound (auto re-stake rewards)
From the dashboard, press `C` to toggle compound mode.

### Quit
Press `Q` or `Ctrl+C`

---

## For Community: `xvault`

### First-time setup (wallet creation)
```bash
xvault --setup
```
This will:
1. Download the official XELIS wallet binary
2. Ask: create new wallet or import from seed
3. If create: generate wallet, display seed phrase (SAVE IT!)
4. Save configuration to ~/.xelis-vault/config/config.json

### Main menu
```bash
xvault
```
Interactive menu with:
1. Dashboard — overview & balance
2. Vault — deposit XEL, borrow xUSD, repay, withdraw
3. Swap — trade XEL, xUSD, VLT (PSM + AMM)
4. Governance — stake VLT, vote, propose
5. Mixer — private transfers
6. Chat — encrypted messaging
7. Stats — protocol statistics
8. Settings — configure RPC, wallet, contracts
9. Start Miner — launch miner dashboard
0. Exit

### Quick commands
```bash
xvault --balance     # Quick balance check
xvault --swap        # Quick swap menu
xvault --vault       # Vault management
xvault --governance  # Governance menu
```

---

## Installation

### One-liner
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

### Windows (PowerShell)
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

### Windows (Command Prompt)
Download `install.bat` and double-click it.

### Manual
```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv ~/.xelis-vault/venv
~/.xelis-vault/venv/bin/pip install requests python-dotenv
# Create launchers:
echo '#!/bin/bash' > ~/.local/bin/xvault-miner
echo 'exec ~/.xelis-vault/venv/bin/python ~/.xelis-vault/src/scripts/xvault-miner.py "$@"' >> ~/.local/bin/xvault-miner
chmod +x ~/.local/bin/xvault-miner
echo '#!/bin/bash' > ~/.local/bin/xvault
echo 'exec ~/.xelis-vault/venv/bin/python ~/.xelis-vault/src/scripts/xvault.py "$@"' >> ~/.local/bin/xvault
chmod +x ~/.local/bin/xvault
```

### Uninstall
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

---

## Troubleshooting

### "Python 3 required"
Install Python 3.10+:
- Ubuntu/Debian: `sudo apt install python3 python3-venv`
- macOS: `brew install python`
- Windows: Download from https://www.python.org/downloads/ (check "Add Python to PATH")

### "git required"
- Ubuntu/Debian: `sudo apt install git`
- macOS: `brew install git`
- Windows: Download from https://git-scm.com/download/win

### "requests not installed"
The installer creates a venv and installs requests. If it fails:
```bash
~/.xelis-vault/venv/bin/pip install requests python-dotenv
```

### "xvault: command not found"
Add ~/.local/bin to PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### "Wallet not connected"
Ensure xelis_daemon and xelis_wallet are running:
```bash
xelis_daemon --testnet
xelis_wallet --testnet
```

### "Contract addresses not set"
Run `xvault --setup` or edit `~/.xelis-vault/config/config.json` with the correct contract addresses after deployment.

### Reset configuration
```bash
rm ~/.xelis-vault/config/config.json
xvault --setup
```

### View logs
```bash
cat ~/.xelis-vault/logs/miner.log
```

---

## Configuration

Config file: `~/.xelis-vault/config/config.json`

```json
{
  "rpc_url": "http://127.0.0.1:18081",
  "wallet_url": "http://127.0.0.1:18082",
  "wallet_user": "wallet",
  "wallet_pass": "testpass",
  "miner_address": "xelis1...",
  "miner_endpoint": "https://my-miner.example:8080",
  "services": "both",
  "contracts": {
    "staked_oracle": "...",
    "miner": "...",
    "vlt_token": "...",
    "vlt_asset": "...",
    "xusd": "...",
    "vault_engine": "...",
    "psm": "...",
    "vault_swap": "...",
    "governance_vault": "...",
    "governor": "...",
    "timelock": "...",
    "guardian_multisig": "...",
    "treasury": "...",
    "contract_registry": "..."
  }
}
```
