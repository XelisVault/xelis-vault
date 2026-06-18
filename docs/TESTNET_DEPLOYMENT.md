# Testnet Deployment Guide — XELIS Vault v4.2

> Complete step-by-step guide to deploy XELIS Vault v4.2 on the XELIS testnet.

---

## Prerequisites

### Software Requirements
- XELIS daemon (`xelis_daemon`) — sync on testnet
- XELIS wallet (`xelis_wallet`) — for transaction signing
- XELIS Silex compiler — to compile `.slx` files
- Python 3.10+ — for off-chain scripts
- `curl` or `jq` — for RPC interaction

### Testnet Information
- **Network**: testnet
- **Address prefix**: `xet` (instead of `xel` for mainnet)
- **Block time**: 5 seconds
- **RPC port**: 8080 (daemon), 8081 (wallet)
- **Explorer**: https://testnet-explorer.xelis.io/
- **Faucet**: see XELIS Discord `#testnet-faucet` channel

### Accounts Needed
You need 3 XELIS testnet addresses:
1. **Deployer** — deploys all contracts, becomes initial admin
2. **Guardian** — emergency pause multisig (can be a separate address)
3. **Treasury** — receives 50% of fees and slashes

Get testnet XEL from the faucet for each.

---

## Step 1: Start the Daemon

```bash
# Start daemon on testnet
xelis_daemon --network testnet

# Wait for sync (check status)
curl -X POST http://127.0.0.1:8080 \
  -H "Content-Type: application/json" \
  -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}'

# Verify "topoheight" is increasing (synced)
```

---

## Step 2: Start the Wallet

```bash
# Start wallet RPC server
xelis_wallet --network testnet --rpc-server

# In another terminal, create/open the deployer wallet
xelis_wallet --network testnet
> create-wallet deployer
# (set a password, save the seed phrase securely)
> get-address
xet1...  # Note this address — it's the DEPLOYER

# Get testnet XEL from the faucet (Discord #testnet-faucet)
# Send some XEL to your deployer address

# Check balance
> get-balance
```

---

## Step 3: Compile Contracts

```bash
# Clone the repo (or use your local copy)
git clone https://github.com/XelisVault/xelis-vault.git
cd xelis-vault/contracts

# Compile each .slx file (using the XELIS Silex compiler)
# Note: replace `silex-compiler` with the actual binary name
for contract in \
    token/VLTToken.slx \
    oracle/StakedOracle.slx \
    governance/OracleGovernance.slx \
    vault/VaultEngineV3.slx \
    amm/VaultSwapV2.slx \
    proxy/ContractRegistry.slx; do
    echo "Compiling $contract..."
    silex-compiler compile "$contract"
done
```

If any contract fails to compile, check the [Silex documentation](https://docs.xelis.io/features/smart-contracts/silex) for syntax requirements.

---

## Step 4: Deploy Contracts

Deploy in this exact order — each contract depends on the previous ones.

### 4.1 ContractRegistry

```bash
xelis_wallet call-contract deploy proxy/ContractRegistry.compiled \
  --signer deployer

# Note the returned contract hash, e.g.: 0xabc123...
REGISTRY=0xabc123...
```

### 4.2 VLTToken

```bash
xelis_wallet call-contract deploy token/VLTToken.compiled \
  --signer deployer

VLT_TOKEN=0xdef456...

# Create the VLT asset
xelis_wallet call-contract call $VLT_TOKEN create_asset \
  --signer deployer

# Get the VLT asset hash
xelis_wallet call-contract read $VLT_TOKEN get_asset_hash
VLT_ASSET=0xa1b2c3...
```

### 4.3 StakedOracle

```bash
xelis_wallet call-contract deploy oracle/StakedOracle.compiled \
  --signer deployer

STAKED_ORACLE=0x789abc...

# Configure StakedOracle
xelis_wallet call-contract call $STAKED_ORACLE set_vlt_contract $VLT_TOKEN --signer deployer
xelis_wallet call-contract call $STAKED_ORACLE set_vlt_asset $VLT_ASSET --signer deployer
xelis_wallet call-contract call $STAKED_ORACLE set_treasury <TREASURY_ADDR> --signer deployer
xelis_wallet call-contract call $STAKED_ORACLE set_registry $REGISTRY --signer deployer
xelis_wallet call-contract call $STAKED_ORACLE set_timelock <TIMELOCK_HASH> --signer deployer
```

### 4.4 Register Contracts in Registry

```bash
xelis_wallet call-contract call $REGISTRY register "ContractRegistry" $REGISTRY --signer deployer
xelis_wallet call-contract call $REGISTRY register "VLTToken" $VLT_TOKEN --signer deployer
xelis_wallet call-contract call $REGISTRY register "StakedOracle" $STAKED_ORACLE --signer deployer
```

### 4.5 Authorize StakedOracle as Minter

```bash
# Allow StakedOracle to mint VLT for rewards
xelis_wallet call-contract call $VLT_TOKEN set_minter $STAKED_ORACLE true --signer deployer
```

### 4.6 Add First Feed (XEL/USD)

```bash
# Add XEL/USD feed: price range $0.001 - $10,000 (in atomic = 1e8 decimals)
# min_price = 100000 (0.001 USD in atomic)
# max_price = 10000000000000 (10000 USD in atomic)
xelis_wallet call-contract call $STAKED_ORACLE add_feed \
  "XEL/USD" 0x0000000000000000000000000000000000000000000000000000000000000000 8 100000 10000000000000 \
  --signer deployer
```

### 4.7 Deploy Other Contracts

```bash
# VaultEngineV3
xelis_wallet call-contract deploy vault/VaultEngineV3.compiled --signer deployer
VAULT_ENGINE=0x...
xelis_wallet call-contract call $VAULT_ENGINE set_registry $REGISTRY --signer deployer
xelis_wallet call-contract call $VAULT_ENGINE set_xusd_contract <XUSD_HASH> --signer deployer
xelis_wallet call-contract call $REGISTRY register "VaultEngine" $VAULT_ENGINE --signer deployer

# VaultSwapV2
xelis_wallet call-contract deploy amm/VaultSwapV2.compiled --signer deployer
VAULT_SWAP=0x...
xelis_wallet call-contract call $VAULT_SWAP set_registry $REGISTRY --signer deployer
xelis_wallet call-contract call $REGISTRY register "VaultSwap" $VAULT_SWAP --signer deployer
```

---

## Step 5: Initial VLT Distribution

Distribute the 10M VLT according to the whitepaper allocation:

```bash
# Example: distribute 6M VLT to the oracle rewards reserve (held by StakedOracle contract)
xelis_wallet call-contract call $VLT_TOKEN mint_to $STAKED_ORACLE 600000000000000 --signer deployer

# 1.5M VLT to team wallet (with vesting contract — not shown here)
xelis_wallet call-contract call $VLT_TOKEN mint_to <TEAM_ADDR> 150000000000000 --signer deployer

# 1.2M VLT to treasury
xelis_wallet call-contract call $VLT_TOKEN mint_to <TREASURY_ADDR> 120000000000000 --signer deployer

# 1.0M VLT to DEX liquidity (VaultSwap)
xelis_wallet call-contract call $VLT_TOKEN mint_to $VAULT_SWAP 100000000000000 --signer deployer

# 200k VLT to airdrop reserve
xelis_wallet call-contract call $VLT_TOKEN mint_to <AIRDROP_ADDR> 20000000000000 --signer deployer

# 100k VLT to bug bounty reserve
xelis_wallet call-contract call $VLT_TOKEN mint_to <BUG_BOUNTY_ADDR> 10000000000000 --signer deployer

# Verify total supply = 10M
xelis_wallet call-contract read $VLT_TOKEN get_circulating_supply
# Should return 1000000000000000
```

---

## Step 6: Bootstrap Price Providers

You need at least 5-10 providers for healthy oracle operation.

### 6.1 Each Provider Does:

```bash
# Get VLT tokens (send them 1000+ VLT from treasury)
# Then they register:
xelis_wallet call-contract call $STAKED_ORACLE register_provider --signer provider1
```

### 6.2 Run the Provider Script

See [`PROVIDER_GUIDE.md`](PROVIDER_GUIDE.md) for full setup.

```bash
# On each provider's server
export PROVIDER_ADDRESS=xet1...
export STAKED_ORACLE_CONTRACT=$STAKED_ORACLE
export XELIS_RPC=http://127.0.0.1:8080
python3 scripts/price_provider.py
```

---

## Step 7: Launch Aggregation Keepers

Run 2-3 keepers on different servers for redundancy:

```bash
export STAKED_ORACLE_CONTRACT=$STAKED_ORACLE
export XELIS_RPC=http://127.0.0.1:8080
python3 scripts/aggregation_keeper.py
```

---

## Step 8: Verify Oracle Operation

### 8.1 Check Cycles Are Advancing

```bash
# Check current cycle for XEL/USD feed (feed_id = 0)
xelis_wallet call-contract read $STAKED_ORACLE get_cycle 0
# Should increment every 5 blocks (~25s)
```

### 8.2 Check Aggregated Price

```bash
xelis_wallet call-contract read $STAKED_ORACLE get_price "XEL/USD"
# Should return a u64 atomic price (e.g., 32000000 = $0.32)
```

### 8.3 Check Provider Stats

```bash
# Get total providers
xelis_wallet call-contract read $STAKED_ORACLE get_providers_count

# Get specific provider info
xelis_wallet call-contract read $STAKED_ORACLE get_provider xet1...
# Returns (stake, registered_at, rewards_earned, total_slashed, active)
```

### 8.4 Check VLT Supply

```bash
xelis_wallet call-contract read $VLT_TOKEN get_circulating_supply
xelis_wallet call-contract read $VLT_TOKEN get_total_burned
```

---

## Step 9: Test VaultEngine

```bash
# Deposit XEL as collateral (1 XEL = 100000000 atomic)
xelis_wallet call-contract call $VAULT_ENGINE deposit \
  0x0000000000000000000000000000000000000000000000000000000000000000 100000000 \
  --signer user1

# Borrow xUSD (50% LTV max = borrow 0.5 XEL worth of xUSD)
# First get current XEL price
PRICE=$(xelis_wallet call-contract read $STAKED_ORACLE get_price "XEL/USD")
# Borrow up to 50% of collateral value
xelis_wallet call-contract call $VAULT_ENGINE borrow 1 25000000 --signer user1

# Check health factor
xelis_wallet call-contract read $VAULT_ENGINE get_health_factor 1
# Should be >= 20000 (2.0x)
```

---

## Step 10: Test VaultSwap

```bash
# Create XEL/xUSD pool (admin only initially)
xelis_wallet call-contract call $VAULT_SWAP create_pool \
  0x0000000000000000000000000000000000000000000000000000000000000000 <XUSD_ASSET> false \
  --signer deployer

# Add liquidity (1 XEL + 0.32 xUSD = 32000000 atomic)
xelis_wallet call-contract call $VAULT_SWAP add_liquidity \
  0x0000000000000000000000000000000000000000000000000000000000000000 <XUSD_ASSET> 100000000 32000000 \
  --signer deployer

# Swap 0.1 XEL for xUSD (with min 0.03 xUSD output)
xelis_wallet call-contract call $VAULT_SWAP swap \
  0x0000000000000000000000000000000000000000000000000000000000000000 <XUSD_ASSET> 10000000 3000000 \
  --signer user1
```

---

## Troubleshooting

### Contract Won't Compile
- Check Silex syntax: semicolons optional, but types are strict
- Verify `Asset::create()` signature matches XELIS-Forge examples
- See [Silex docs](https://docs.xelis.io/features/smart-contracts/silex)

### Transaction Reverts with "notauth"
- Make sure you're calling from the right signer
- For admin functions, signer must be the contract's admin address
- For Timelock functions, must be called via Timelock contract

### Oracle Price Stays at 0
- Check that providers are registered: `get_providers_count`
- Check that providers are submitting: `get_submissions_count 0 <current_cycle>`
- Check that keeper is running: `get_cycle 0` should increment
- Check feed is active and not in circuit breaker: `get_price_meta 0`

### Rewards Not Distributed
- Verify StakedOracle is registered as minter in VLTToken
- Check VLT supply: `get_max_supply` vs `get_circulating_supply` (must be < max)
- Check that aggregation is happening (cycle increments)

### Slashing Too Aggressive
- Check `MAX_DEVIATION_BPS` (default 500 = 5%)
- Check that providers are using correct price sources
- Run `price_provider.py --test-sources` to verify sources

---

## Monitoring

### Prometheus Metrics

Both scripts expose Prometheus metrics:

```bash
# Provider metrics (port 9091)
curl http://provider-server:9091/metrics

# Keeper metrics (port 9092)
curl http://keeper-server:9092/metrics
```

### Grafana Dashboard

Sample Grafana dashboard JSON: `scripts/grafana-dashboard.json` (to be created)

Key metrics to monitor:
- `provider_prices_submitted_total` — rate of submissions
- `provider_estimated_rewards_vlt` — rewards earned
- `miner_blocks_found_total` — blocks found by miner
- `staked_oracle_providers_count` — on-chain provider count
- `staked_oracle_aggregated_price` — current oracle price
- `vlt_circulating_supply` — VLT supply (should decrease over time)
- `vlt_total_burned` — total VLT burned

---

## Next Steps

After successful testnet deployment:

1. **Recruit more providers** — aim for 20+ on testnet
2. **Run for 4+ weeks** — verify stability
3. **Test edge cases**:
   - Provider going offline
   - Sudden price drop
   - Slashing scenarios
   - Governance proposal lifecycle
4. **Document issues** — anything weird should be reported and fixed
5. **Prepare for mainnet audit** — submit contracts to Trail of Bits or OpenZeppelin

---

## Support

- **Discord**: [XELIS Vault Discord](https://discord.gg/xelisvault) (to be created)
- **Email**: `support@xelisvault.io`
- **GitHub Issues**: [XelisVault/xelis-vault/issues](https://github.com/XelisVault/xelis-vault/issues)

---

*Last updated: June 2026 — v4.2*
