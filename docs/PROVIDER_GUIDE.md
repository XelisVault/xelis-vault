# Provider Guide — Become a Price Provider

> Earn VLT rewards by providing accurate price data to the XELIS Vault oracle.

---

## What is a Price Provider?

A price provider is anyone who stakes VLT and submits price data to the StakedOracle contract. Providers earn VLT rewards for valid prices (within 5% of the median) and are slashed for outliers (1% of stake per outlier).

**Anyone can become a provider** — you don't need to be a miner or have any special permission. You just need:
- 1,000 VLT (testnet: get from faucet / mainnet: buy on VaultSwap)
- A server with internet access (VPS $5/month is enough)
- The `price_provider.py` script

---

## Economics Summary

| Active Providers | Reward per Provider/Day | ROI on 1,000 VLT Stake |
|------------------|-------------------------|-------------------------|
| 10 | 165 VLT | 6 days |
| 25 | 66 VLT | 15 days |
| 50 | 33 VLT | 30 days |
| 100 | 16 VLT | 61 days |
| 200 | 8 VLT | 122 days |

**Risk**: 1% of stake slashed per outlier. If you use the recommended sources (MEXC + CoinEx + CoinGecko), the risk of being an outlier is very low (<1% of cycles).

---

## Step 1: Get VLT Tokens

### On Testnet
1. Join the XELIS Discord: https://discord.gg/xelis
2. Go to `#testnet-faucet` channel
3. Request testnet XEL to your address
4. Once XELIS Vault is deployed, swap XEL for VLT on VaultSwap, OR
5. Ask the team in `#xelis-vault` for testnet VLT (we distribute free for testing)

### On Mainnet
1. Buy XEL on MEXC or CoinEx
2. Transfer to your XELIS wallet
3. Swap XEL → VLT on VaultSwap

You need at least **1,000 VLT** (1,000,000,000,000 atomic units with 8 decimals).

---

## Step 2: Set Up Your Server

### Requirements
- Linux VPS (Ubuntu 22.04+ recommended)
- 2 GB RAM minimum
- 50 GB disk space (for XELIS daemon)
- Stable internet connection (>99% uptime)
- Python 3.10+

### Install XELIS Daemon

```bash
# Build from source (recommended)
sudo apt install -y build-essential cmake clang rustup
rustup default stable

git clone https://github.com/xelis-project/xelis-blockchain.git
cd xelis-blockchain
cargo build --release --bin xelis_daemon
sudo cp target/release/xelis_daemon /usr/local/bin/

# Or download precompiled binary from https://github.com/xelis-project/xelis-blockchain/releases
```

### Install XELIS Wallet

```bash
cd xelis-blockchain
cargo build --release --bin xelis_wallet
sudo cp target/release/xelis_wallet /usr/local/bin/
```

### Start the Daemon (testnet)

```bash
# Create data directory
mkdir -p ~/.xelis/testnet

# Start daemon (sync with testnet)
xelis_daemon --network testnet &

# Wait for sync (check every 30s)
while true; do
    STATUS=$(curl -s -X POST http://127.0.0.1:8080 \
        -H "Content-Type: application/json" \
        -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}' | jq -r '.result.synced')
    if [ "$STATUS" = "true" ]; then
        echo "Daemon synced!"
        break
    fi
    echo "Waiting for sync..."
    sleep 30
done
```

### Create Wallet

```bash
xelis_wallet --network testnet --rpc-server &
sleep 2

# In a new terminal, attach to wallet
xelis_wallet --network testnet

# Inside wallet prompt:
> create-wallet my-provider-wallet
# Set a strong password (save it!)
# Save the seed phrase (12-24 words) — CRITICAL

> get-address
# Note: xet1abc... (this is your PROVIDER_ADDRESS)

> get-balance
# Should show your testnet XEL balance
```

---

## Step 3: Get VLT and Register as Provider

### Get VLT

On testnet, ask the team for VLT tokens. On mainnet, swap XEL → VLT on VaultSwap.

### Send VLT to Your Provider Address

Send at least 1,000 VLT to your `xet1...` address.

### Register as Provider

```bash
# Call register_provider on the StakedOracle contract
# This will stake exactly 1,000 VLT (MIN_STAKE)
# You must include 1,000 VLT in the transaction as deposit

xelis_wallet --network testnet
> call-contract <STAKED_ORACLE_HASH> register_provider \
    --signer my-provider-wallet \
    --deposit <VLT_ASSET_HASH> 100000000000

# Verify registration
> call-contract <STAKED_ORACLE_HASH> get_provider xet1abc...
# Should return: (100000000000, <topoheight>, 0, 0, true)
#                  ^stake         ^registered   ^rewards ^slashed ^active
```

If you want to stake more (lower slashing risk, same rewards):

```bash
> call-contract <STAKED_ORACLE_HASH> increase_stake 500000000000 \
    --signer my-provider-wallet \
    --deposit <VLT_ASSET_HASH> 500000000000
# Now stake = 1500 VLT
```

---

## Step 4: Install the Price Provider Script

### Install Python Dependencies

```bash
sudo apt install -y python3 python3-pip
pip3 install requests
```

### Download the Script

```bash
mkdir -p /opt/xelis-vault
cd /opt/xelis-vault

# From the XELIS Vault repo
curl -O https://raw.githubusercontent.com/XelisVault/xelis-vault/main/scripts/price_provider.py
chmod +x price_provider.py
```

### Configure Environment

```bash
cat > /opt/xelis-vault/.env << EOF
# Your provider XELIS address (must be registered in StakedOracle)
PROVIDER_ADDRESS=xet1abc...

# StakedOracle contract hash (from deployment)
STAKED_ORACLE_CONTRACT=0x...

# XELIS daemon RPC URL
XELIS_RPC=http://127.0.0.1:8080

# VLT asset hash (from VLTToken.get_asset_hash)
VLT_ASSET_HASH=0x...

# Optional: CoinMarketCap API key (for fallback source)
# Get free key at https://pro.coinmarketcap.com/signup
CMC_API_KEY=

# Submit interval (seconds) — should be < 25s (1 cycle)
SUBMIT_INTERVAL=20

# Prometheus metrics port
PROMETHEUS_PORT=9091

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
EOF
```

### Test the Script

```bash
cd /opt/xelis-vault
source .env

# Test price sources
python3 price_provider.py --test-sources

# Expected output:
# [INFO] Testing all price sources...
# [INFO]   mexc         OK  $0.320000 (150ms)
# [INFO]   coinex       OK  $0.321000 (80ms)
# [INFO]   coingecko    OK  $0.318000 (270ms)
# [WARNING] cmc          FAIL  (no API key)

# List available sources
python3 price_provider.py --list-sources
```

---

## Step 5: Run as a Service

### Create systemd Service

```bash
sudo cat > /etc/systemd/system/xelis-vault-provider.service << EOF
[Unit]
Description=XELIS Vault Price Provider
After=network.target xelis-daemon.service
Requires=xelis-daemon.service

[Service]
Type=simple
User=xelis
WorkingDirectory=/opt/xelis-vault
EnvironmentFile=/opt/xelis-vault/.env
ExecStart=/usr/bin/python3 /opt/xelis-vault/price_provider.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/xelis-vault-provider.log
StandardError=append:/var/log/xelis-vault-provider.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable xelis-vault-provider
sudo systemctl start xelis-vault-provider

# Check status
sudo systemctl status xelis-vault-provider

# View logs
sudo tail -f /var/log/xelis-vault-provider.log
```

---

## Step 6: Monitor Your Provider

### Check Service Status
```bash
sudo systemctl status xelis-vault-provider
```

### View Logs
```bash
sudo tail -f /var/log/xelis-vault-provider.log
```

Expected log output:
```
[INFO] Block 12345 was mined by us! Submitting prices...
[INFO] Feed XEL/USD: median=$0.321000, sources=['mexc', 'coinex', 'coingecko'], ignored=[]
[INFO] Submitting XEL/USD=$0.321000 (atomic=32100000) for block 12345
[INFO]   -> tx=0xabc123...
```

### Prometheus Metrics
```bash
curl http://localhost:9091/metrics
```

Key metrics:
- `provider_prices_submitted_total` — total prices submitted
- `provider_estimated_rewards_vlt` — estimated VLT rewards earned
- `provider_last_price_xel_usd` — last submitted price

### On-Chain Verification

```bash
xelis_wallet --network testnet
> call-contract <STAKED_ORACLE_HASH> get_provider xet1abc...
# Returns: (stake, registered_at, rewards_earned, total_slashed, active)
# rewards_earned should increase over time
# total_slashed should stay low (0 if you're doing well)
```

---

## Step 7: Manage Your Stake

### Check Your Stake
```bash
xelis_wallet --network testnet
> call-contract <STAKED_ORACLE_HASH> get_provider xet1abc...
```

### Add More Stake
```bash
> call-contract <STAKED_ORACLE_HASH> increase_stake 100000000000 \
    --signer my-provider-wallet \
    --deposit <VLT_ASSET_HASH> 100000000000
# Adds 100 VLT to stake
```

### Withdraw Stake
```bash
> call-contract <STAKED_ORACLE_HASH> decrease_stake 50000000000 \
    --signer my-provider-wallet
# Withdraws 50 VLT (must keep >= MIN_STAKE = 1000 VLT)
```

### Deregister Completely
```bash
# Stop the provider script first!
sudo systemctl stop xelis-vault-provider

> call-contract <STAKED_ORACLE_HASH> deregister_provider \
    --signer my-provider-wallet
# Returns your full stake
```

---

## Troubleshooting

### "notprov" Error
You're not registered. Run Step 3 first.

### "lowstake" Error
Your stake is below MIN_STAKE. Add more VLT via `increase_stake`.

### "alreadysub" Error
You're trying to submit twice in the same cycle. The script should not do this — check your `SUBMIT_INTERVAL` (should be ≥ 20s).

### "oorange" Error
Your price is outside the [min, max] range for the feed. Check that your price sources are working correctly:
```bash
python3 price_provider.py --test-sources
```

### No Rewards After Long Time
- Verify oracle is aggregating: `get_cycle 0` should increment
- Verify your prices are within 5% of median: monitor `provider_estimated_rewards_vlt`
- Verify StakedOracle is minter: `call-contract <VLT_TOKEN> get_minter <STAKED_ORACLE_HASH>` (should be `true`)

### High Slashing Rate
- Run `--test-sources` and ensure all 3 main sources work
- Check if your internet is unstable (latency > 5s can cause stale prices)
- Consider increasing your outlier threshold: edit `OUTLIER_THRESHOLD_PCT = 0.10` in the script

---

## FAQ

### Can I run multiple providers?
Yes, but each needs its own:
- XELIS address (with 1,000 VLT stake)
- Server (different IP recommended)
- Running `price_provider.py` instance

### What if my server goes offline?
- No penalties for being offline (only for submitting wrong prices)
- When you come back, you'll resume earning rewards
- If you're offline for a long time, your stake remains safe

### Can I use different price sources?
Yes — edit `PRICE_SOURCES` in `price_provider.py` to add/remove sources. Just make sure they're reliable.

### What happens if VLT supply reaches MAX_SUPPLY?
The `mint_to` function will revert, and rewards won't be distributed for that cycle. The governance should lower `REWARD_PER_CYCLE` before this happens. With 6M VLT allocated to 10 years of rewards, this won't happen before 2036 at the earliest.

### Can I be a provider AND a miner?
Yes! In fact, miners make great providers because they already have the infrastructure. If you also want to help keep the oracle healthy, run `aggregation_keeper.py` alongside (see Miner Guide).

---

## Support

- **Discord**: [XELIS Vault Discord](https://discord.gg/xelisvault) — `#providers` channel
- **Email**: `providers@xelisvault.io`
- **GitHub Issues**: For script bugs only — [XelisVault/xelis-vault/issues](https://github.com/XelisVault/xelis-vault/issues)

---

*Last updated: June 2026 — v4.2*
