# Miner Guide — Unified XELIS Vault Miner

> Complete guide for becoming a XELIS Vault miner: stake 100 VLT, choose your services (oracle, chat, or both), and earn rewards through the unified `XelisVaultMiner` contract.

---

## What Is a XELIS Vault Miner?

A XELIS Vault miner is **not** the same as a XELIS BlockDAG miner. BlockDAG miners produce blocks and earn XEL; Vault miners run **protocol services** and earn **VLT** rewards. The two roles are independent — you can be one, the other, or both.

Vault miners serve one or more of these services:

| Service ID | Service | What you do | How you earn |
|------------|---------|-------------|--------------|
| 1 | **Oracle** | Fetch XEL prices from MEXC/CoinEx/your own sources, submit them on-chain every ~25s | `BASE_REWARD_ORACLE` × reputation × budget factor (≈0.48 VLT per valid cycle) |
| 2 | **Chat** | Run a VaultChat relayer: receive signed encrypted messages, store them, anchor a Merkle root on-chain every hour | `BASE_REWARD_CHAT` × reputation × budget factor (≈0.5 VLT per anchor) |
| 3–8 | Reserved | Future services: storage, indexer, etc. | — |

All rewards are paid in **VLT** and sourced from a fixed 6,000,000 VLT pool that the contract self-adjusts to last exactly **10 years** (see §Dynamic Rewards below).

---

## Why Become a Miner?

- **Low barrier**: only 100 VLT required to stake (≈ a few dollars at launch prices)
- **Passive income**: rewards scale with your reputation — reliable miners earn up to 1.5× more
- **Multiple revenue streams**: run oracle + chat simultaneously from a single process
- **Composable**: join or create a `MinerPool` to mutualize stake and reputation with other miners
- **Public good**: your oracle submissions protect every swap, loan, and liquidation on XELIS Vault

---

## 1. Prerequisites

### 1.1 Hardware

| Setup | CPU | RAM | Disk | Network | Cost |
|-------|-----|-----|------|---------|------|
| **Minimal** (oracle only) | 2 cores | 4 GB | 100 GB SSD | 100 Mbps | ~$10–15/mo VPS |
| **Recommended** (oracle + chat) | 4 cores | 8 GB | 200 GB SSD | 100 Mbps | ~$20–30/mo VPS |
| **Pool operator** | 4+ cores | 8+ GB | 500 GB NVMe | 1 Gbps | ~$40–80/mo VPS |

### 1.2 Software

- **Python 3.8+** (`python3 --version`)
- **`requests` module** (auto-installed by the script if missing)
- **XELIS daemon** synced on testnet or mainnet (the script can install it for you)
- **A XELIS wallet** with at least 100 VLT (claimable from the testnet faucet)

### 1.3 Get 100 VLT

On testnet, claim from the Faucet contract:

```bash
xelis_wallet call-contract <FaucetContract> claim_both --signer mywallet
# → 100 XEL (for gas) + 200 VLT (more than enough to stake)
```

On mainnet, buy VLT on VaultSwap or receive it from another holder.

---

## 2. Quick Start — One-Command Setup

The easiest path: run the unified miner script interactively. It will guide you through every step.

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/XelisVault/xelis-vault/main/scripts/xelis_vault_miner.py -o xelis_vault_miner.py
python3 xelis_vault_miner.py --setup
```

### Windows (PowerShell)

```powershell
iwr -useb https://raw.githubusercontent.com/XelisVault/xelis-vault/main/scripts/xelis_vault_miner.py -OutFile xelis_vault_miner.py
python xelis_vault_miner.py --setup
```

The script will:

1. ✅ Detect your OS and architecture (Linux / macOS / Windows)
2. ✅ Verify Python 3.8+ is installed
3. ✅ Detect (or offer to install) the XELIS daemon
4. ✅ Help you create or import a wallet
5. ✅ Ask for the `XelisVaultMiner`, `StakedOracle`, and `VaultChat` contract addresses
6. ✅ Ask which services to enable (oracle, chat, or both)
7. ✅ Optionally add a custom price source (HTTP API or external command)
8. ✅ Save the config to `~/.xelis-vault/miner_config.json`
9. ✅ Offer to install a systemd / launchd / Windows service for auto-start
10. ✅ Offer to start mining immediately

**No technical knowledge required** — the installer is 100% interactive.

---

## 3. Manual Setup (advanced)

If you prefer to control every step, here is the manual path.

### 3.1 Install the script

```bash
mkdir -p ~/.xelis-vault
curl -fsSL https://raw.githubusercontent.com/XelisVault/xelis-vault/main/scripts/xelis_vault_miner.py \
    -o ~/.xelis-vault/xelis_vault_miner.py
chmod +x ~/.xelis-vault/xelis_vault_miner.py
```

### 3.2 Register as a miner on-chain

```bash
# 1. Deposit 100 VLT and register with services_mask = 3 (oracle + chat)
#    services_mask is a bitmask:
#      bit 0 (value 1) = Oracle
#      bit 1 (value 2) = Chat
#      bit 2 (value 4) = Reserved (storage)
#      ...
#    So:
#      1 = oracle only
#      2 = chat only
#      3 = oracle + chat
xelis_wallet call-contract <XelisVaultMiner> register_miner \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 10000000000 \
    "https://my-miner.example.com"  \
    0x<your_chat_pubkey>            \
    3                               # services_mask
```

The `endpoint_url` is the public URL where users can reach your chat relayer (can be empty if you only run oracle). The `miner_pubkey` is the X25519 public key users will use to verify your signed chat anchors — leave it as `0x00` if you are not running chat.

### 3.3 Configure the script

```bash
cat > ~/.xelis-vault/miner_config.json << EOF
{
  "miner_address": "xet1...",
  "miner_contract": "0x<XelisVaultMiner hash>",
  "oracle_contract": "0x<StakedOracle hash>",
  "chat_contract": "0x<VaultChat hash or empty>",
  "vlt_asset": "0x<VLT asset hash>",
  "rpc_url": "http://127.0.0.1:8080",
  "network": "testnet",
  "services": {
    "oracle": true,
    "chat": true
  },
  "oracle_config": {
    "submit_interval": 20,
    "feeds": ["XEL/USD"],
    "sources": ["mexc", "coinex"]
  },
  "chat_config": {
    "storage_dir": "~/.xelis-vault/chat_messages",
    "anchor_interval": 3600,
    "max_messages_per_hour": 10000
  },
  "heartbeat_interval": 480,
  "prometheus_port": 9091,
  "log_level": "INFO"
}
EOF
```

### 3.4 Run

```bash
python3 ~/.xelis-vault/xelis_vault_miner.py --run
```

### 3.5 Install as a systemd service (Linux)

```bash
python3 ~/.xelis-vault/xelis_vault_miner.py --install-service
sudo systemctl daemon-reload
sudo systemctl enable --now xelis-vault-miner
```

---

## 4. Service Selection

You can enable or disable services at any time, both on-chain and in your local config.

### 4.1 On-chain (affects what you can be slashed/rewarded for)

```bash
# Add the chat service to an oracle-only miner
xelis_wallet call-contract <XelisVaultMiner> enable_service 2 --signer mywallet

# Remove the oracle service (you stop earning oracle rewards)
xelis_wallet call-contract <XelisVaultMiner> disable_service 1 --signer mywallet
```

### 4.2 In your local config

Edit `~/.xelis-vault/miner_config.json` and toggle the `services.oracle` / `services.chat` flags. The script will only run threads for enabled services.

### 4.3 Choosing what to run

| Profile | Oracle | Chat | VPS size | Notes |
|---------|--------|------|----------|-------|
| **Lightweight** | ✓ | — | 2 vCPU / 4 GB | Lowest cost, ~25s submit cadence |
| **Chat relayer** | — | ✓ | 2 vCPU / 4 GB + 200 GB disk | Stores ciphertexts, anchors hourly |
| **Full miner** | ✓ | ✓ | 4 vCPU / 8 GB + 200 GB disk | Maximum rewards, both revenue streams |
| **Pool member** | ✓ | ✓ | 2 vCPU / 4 GB | Joins an existing pool, lower SLA expectations |

---

## 5. Reputation System Explained

Every miner has a **reputation score** between 0 and 10,000. New miners start at the maximum (10,000). The score affects two things:

1. **Your reward multiplier** (see §6)
2. **Your active status** — if your reputation drops below `REP_CRITICAL` (1,000), you are automatically deactivated and stop earning rewards until you climb back up

### 5.1 How to gain reputation

| Action | Reputation gain |
|--------|-----------------|
| Submit a valid oracle price | +1 |
| Successfully anchor a batch of chat messages | +5 |
| Send a heartbeat (proof of life, every ~8 min) | +1 (if no infraction in the last 1,000 blocks) |
| Bonus per day without any infraction | +10 |

### 5.2 How to lose reputation

| Infraction | Reputation loss | Stake slash | Severity code |
|------------|-----------------|-------------|---------------|
| Oracle outlier price (>5% from median) | -50 | 1% | 0 |
| Node offline detected | -200 | 2% | 1 |
| Chat data loss (lost stored messages) | -500 | 5% | 2 |
| Chat censorship (refused valid messages) | -1,000 | 10% | 3 |
| Malicious behavior (proven) | -5,000 | 50% | 4 |

Stake slash split: **50% burned** (deflationary), **10% to the reporter** (incentive for watchdogs), **40% to the treasury**.

### 5.3 Reputation tiers

| Tier | Score range | Multiplier | Effect |
|------|-------------|------------|--------|
| Excellent | 10,000 – 8,000 | **1.5×** | Bonus rewards for top miners |
| Good | 8,000 – 5,000 | 1.0× | Normal |
| Warning | 5,000 – 2,000 | 0.5× | Half rewards — improve or you'll keep falling |
| Critical | 2,000 – 1,000 | 0.25× | Quarter rewards — last chance |
| Banned | < 1,000 | 0× | Auto-deactivated, no rewards until you regenerate |

### 5.4 Regenerating reputation

Reputation regenerates naturally: each heartbeat (every ~8 minutes) gives +1 point **if** you have had no infraction in the last 1,000 blocks (~83 minutes). This means:

- A miner who had a single outlier (-50) recovers in ~50 heartbeats = ~7 hours of clean operation
- A miner who lost 1,000 reputation (censorship) needs ~1,000 heartbeats = ~5.5 days of clean operation
- A miner in Banned tier must wait until they cross back above 1,000 — they will be inactive during that time

### 5.5 Checking your reputation

```bash
xelis_wallet call-contract <XelisVaultMiner> read get_miner_reputation <your_addr>
# → returns a u64 in [0, 10000]

xelis_wallet call-contract <XelisVaultMiner> read get_reputation_tier <your_addr>
# → 0=banned, 1=critical, 2=warning, 3=good, 4=excellent

xelis_wallet call-contract <XelisVaultMiner> read get_miner <your_addr>
# → (endpoint_url, pubkey, stake, services_mask, reputation, valid_submissions,
#    successful_anchors, total_submissions, total_rewards_earned, total_slashed, active)
```

---

## 6. Dynamic Rewards Explained

Your per-action reward is computed by `XelisVaultMiner.distribute_reward()` as:

```
dynamic_reward = base_reward × reputation_mult × budget_factor
```

### 6.1 Base reward

| Service | Base reward |
|---------|-------------|
| Oracle (valid price submission) | 0.48 VLT (`BASE_REWARD_ORACLE = 47,564,687` atomic) |
| Chat (successful anchor) | 0.5 VLT (`BASE_REWARD_CHAT = 50,000,000` atomic) |

### 6.2 Reputation multiplier

From §5.3 above: 0× / 0.25× / 0.5× / 1.0× / 1.5× depending on your tier.

### 6.3 Budget factor (auto-adjustment)

The contract maintains a global `budget_factor` (in basis points, 10,000 = 1.0×). Every 2,016 blocks (~1 week), `maybe_adjust_budget()` runs:

1. Compute the **actual distribution rate** = `total_distributed / elapsed_blocks`
2. Compute the **target rate** = `remaining_budget / remaining_blocks` (so the 6M VLT pool lasts exactly 10 years)
3. If we're distributing too fast → reduce `budget_factor` (down to 5,000 = 0.5× minimum)
4. If we're distributing too slow → increase `budget_factor` (up to 20,000 = 2.0× maximum)
5. Apply a 50/50 blend with the previous factor to avoid shocks

This means:

- **If the network is very active** (many miners, many submissions) → rewards per action decrease, but the pool lasts the full 10 years
- **If the network is quiet** (few miners) → rewards per action increase (up to 2×), encouraging new miners to join
- **The 6M VLT pool will always last 10 years**, regardless of network conditions

### 6.4 Example calculation

A miner with reputation 9,200 (Excellent tier) submitting a valid oracle price when `budget_factor = 12,000` (1.2×):

```
dynamic_reward = 0.48 VLT × 1.5 × 1.2 = 0.864 VLT
```

A miner with reputation 3,500 (Warning tier) submitting the same price:

```
dynamic_reward = 0.48 VLT × 0.5 × 1.2 = 0.288 VLT
```

A miner with reputation 800 (Banned tier):

```
dynamic_reward = 0   ← no reward minted, regardless of validity
```

### 6.5 Checking the current budget factor

```bash
xelis_wallet call-contract <XelisVaultMiner> read get_budget_info
# → (total_budget, distributed, budget_factor, launch_topo, target_duration)
# total_budget = 600,000,000,000,000 (6M VLT in atomic units)
# distributed  = how much has been paid out so far
# budget_factor = current multiplier in bps (10000 = 1.0×)
```

---

## 7. Miner Pools

### 7.1 Why join a pool?

- **Mutualized availability**: if your node goes down, other pool members keep serving
- **Combined reputation**: pool reputation is the mean of members' — useful for chat users choosing where to store messages
- **Lower operational burden**: you can run a smaller node, the pool absorbs the slack
- **Same rewards**: your share = `pool_pending × (your_stake / pool_total_stake)` minus the creator commission

### 7.2 Creating a pool

Any registered miner can create a pool:

```bash
xelis_wallet call-contract <MinerPool> create_pool \
    --signer mywallet \
    "My Awesome Pool"           `# name` \
    "Reliable oracle + chat, EU-hosted"   `# description` \
    500                          `# creator_commission_bps (5%)`
# → returns the new pool_id
```

The creator automatically becomes member #1. The creator commission (in basis points, max 2,000 = 20%) is taken from each member's reward and sent to the creator.

### 7.3 Joining a pool

```bash
# List existing pools
xelis_wallet call-contract <MinerPool> read get_pools_count
# → e.g. 7

# Inspect a pool
xelis_wallet call-contract <MinerPool> read get_pool 3
# → (creator, name, description, commission_bps, total_stake, created_at, active)

# Join
xelis_wallet call-contract <MinerPool> join_pool 3 --signer mywallet
```

Constraints:
- You must already be a registered miner
- You can only be in one pool at a time
- A pool can have at most 50 members

### 7.4 Earning and claiming

When `XelisVaultMiner.distribute_reward()` pays you, it checks if you are in a pool. If so, the reward is sent to `MinerPool.distribute_pool_rewards()` instead of to you directly. The pool accumulates these rewards.

To claim your share:

```bash
xelis_wallet call-contract <MinerPool> claim_pool_rewards --signer mywallet
```

Your share = `pool_pending × (your_stake / pool_total_stake)` minus commission.

### 7.5 Leaving a pool

```bash
xelis_wallet call-contract <MinerPool> leave_pool --signer mywallet
```

On leave, your pending share is paid out. The pool creator cannot leave — they must dissolve the pool (transfer admin) instead.

### 7.6 Pool operators: kicking a member

```bash
xelis_wallet call-contract <MinerPool> kick_member <member_addr> --signer creator_wallet
```

Use this for members who have gone offline, misbehaved, or whose reputation has dropped too low.

---

## 8. Custom Price Sources

The default sources (MEXC + CoinEx) work for everyone. If you want to add your own:

### 8.1 HTTP API source

Edit `~/.xelis-vault/custom_sources.json`:

```json
[
  {
    "type": "http",
    "name": "my_exchange",
    "url": "https://api.myexchange.com/v1/xel_usd",
    "json_path": "data.price",
    "headers": {
      "Authorization": "Bearer YOUR_API_KEY"
    }
  }
]
```

The script will fetch this URL, walk the JSON path (`data.price`), and include the result in the median alongside MEXC and CoinEx.

### 8.2 External command source

```json
[
  {
    "type": "command",
    "name": "my_node",
    "command": "/usr/local/bin/my_price_feed --json"
  }
]
```

The script runs the command and parses stdout as a JSON object with a `price` field.

### 8.3 Using the interactive helper

```bash
python3 scripts/xelis_vault_miner.py --add-source
```

### 8.4 Enabling your custom source

Edit `~/.xelis-vault/miner_config.json` and add your source name to the `sources` array:

```json
"oracle_config": {
  "sources": ["mexc", "coinex", "my_exchange", "my_node"]
}
```

The script uses a median of all sources, with outliers (>10% from median) excluded. You need at least 2 valid sources for a price to be submitted.

### 8.5 Testing your sources

```bash
python3 scripts/xelis_vault_miner.py --test-sources
```

Output:

```
======================================================================
  TESTING PRICE SOURCES
======================================================================
  ✓ mexc: $0.482301
  ✓ coinex: $0.481900
  ✓ my_exchange (custom): $0.482500
  ! my_node (custom): FAIL
```

An example custom sources file is provided at [`scripts/custom_sources.example.json`](../scripts/custom_sources.example.json).

---

## 9. Heartbeats

The script automatically sends a heartbeat every ~8 minutes (96 blocks × 5s = 480s) via `XelisVaultMiner.submit_heartbeat()`.

Heartbeats serve two purposes:

1. **Proof of life** — if you stop sending heartbeats for more than `HEARTBEAT_TIMEOUT` (300 blocks ≈ 25 min), other miners/services can report you as offline (severity 1, -200 reputation, 2% stake slash)
2. **Reputation regeneration** — each heartbeat gives +1 reputation if you've had no infraction in the last 1,000 blocks

You don't need to do anything — the script handles heartbeats for you.

---

## 10. Monitoring

### 10.1 Service status

```bash
sudo systemctl status xelis-vault-miner
```

### 10.2 Logs

```bash
# Live tail
tail -f ~/.xelis-vault/miner.log

# systemd journal
sudo journalctl -u xelis-vault-miner -f
```

### 10.3 Prometheus metrics

The script exposes metrics on port 9091:

```bash
curl http://localhost:9091/metrics
```

Key metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `xelis_miner_up` | gauge | 1 if the miner is running |
| `xelis_miner_prices_submitted_total` | counter | Total oracle prices submitted |
| `xelis_miner_heartbeats_total` | counter | Total heartbeats sent |
| `xelis_miner_last_price` | gauge | Last XEL price submitted (USD) |

### 10.4 On-chain status

```bash
# Quick status
python3 scripts/xelis_vault_miner.py --status

# Full miner info
xelis_wallet call-contract <XelisVaultMiner> read get_miner <your_addr>

# Reputation tier
xelis_wallet call-contract <XelisVaultMiner> read get_reputation_tier <your_addr>

# Budget info
xelis_wallet call-contract <XelisVaultMiner> read get_budget_info

# Active miners per service
xelis_wallet call-contract <XelisVaultMiner> read get_active_miners_for_service 1   # oracle
xelis_wallet call-contract <XelisVaultMiner> read get_active_miners_for_service 2   # chat
```

---

## 11. Troubleshooting

### 11.1 "Cannot connect to XELIS daemon"

```bash
# Check daemon is running
sudo systemctl status xelis-daemon

# Check RPC is accessible
curl http://127.0.0.1:8080 -X POST \
    -H "Content-Type: application/json" \
    -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}'
```

If you don't have a daemon yet, re-run `python3 scripts/xelis_vault_miner.py --setup` and choose to install it.

### 11.2 "insstake" error on register_miner

You don't have enough VLT deposited. The `register_miner` call expects a `--deposit` of at least 100 VLT (= 10,000,000,000 atomic units) of the VLT asset.

```bash
# Check your VLT balance
xelis_wallet balance <your_addr> <VLT_ASSET_HASH>

# If insufficient, claim from faucet (testnet) or buy on VaultSwap (mainnet)
```

### 11.3 Your reputation is dropping

- Check the log for "outlier" messages → your price sources may be returning bad data
- Run `python3 scripts/xelis_vault_miner.py --test-sources` to verify each source
- Add a more reliable source (MEXC and CoinEx are both production-tested)
- If reputation is in Critical tier (< 2,000), stop, fix your setup, and let heartbeats regenerate you

### 11.4 "notauth" error when calling distribute_reward

You are not an authorized service contract. Only `StakedOracle` and `VaultChat` (or other contracts registered via `register_service()`) can call `distribute_reward()` and `slash_miner()`. If you see this error, it's a contract-level issue, not something miners should encounter.

### 11.5 Chat anchoring is failing

- Make sure `chat_contract` is set in your config
- Make sure you have the chat bit set in your `services_mask` (use `enable_service 2`)
- Make sure your relayer is reachable at the `endpoint_url` you registered with
- Check that your storage directory is writable

### 11.6 Service won't start on boot

```bash
# Re-enable
sudo systemctl daemon-reload
sudo systemctl enable xelis-vault-miner
sudo systemctl start xelis-vault-miner

# Check the unit file
cat /etc/systemd/system/xelis-vault-miner.service
```

---

## 12. FAQ

### Do I need to also be a XELIS BlockDAG miner?
No. Vault mining and BlockDAG mining are completely independent. You can run a Vault miner on a $10 VPS without ever mining a block.

### Can I run oracle without chat?
Yes. Set `services_mask = 1` (or use `--setup` and answer "no" to chat). You will only earn oracle rewards.

### Can I run chat without oracle?
Yes. Set `services_mask = 2`. You will only earn chat rewards. This is useful for miners who want to focus on the relayer business.

### What happens if I run out of stake?
If your stake drops below 100 VLT (after cumulative slashing), you are auto-deactivated. Call `increase_stake()` to top up and re-activate:

```bash
xelis_wallet call-contract <XelisVaultMiner> increase_stake 5000000000 \
    --signer mywallet --deposit <VLT_ASSET_HASH> 5000000000   # +50 VLT
```

### What happens if my reputation drops below 1,000?
You are auto-deactivated. You don't lose your stake, but you stop earning rewards. Send heartbeats (the script does this automatically) to regenerate reputation. Once you cross back above 1,000, you are reactivated.

### How do I withdraw my stake?
```bash
xelis_wallet call-contract <XelisVaultMiner> deregister_miner --signer mywallet
```
This returns your full stake and removes you from the miner registry. If you were in a pool, leave it first.

### Can I run multiple miners from the same wallet?
No. One address = one miner registration. Use a different wallet for each miner instance.

### Can I run multiple miners from the same machine?
Yes, but they must use different wallets and different Prometheus ports. Edit `prometheus_port` in `miner_config.json` for each instance.

### Do I earn more in a pool or solo?
Mathematically, pools and solo earn the same total rewards (minus the creator commission). Pools trade a small commission for higher availability and reduced operational risk. The choice depends on your reliability and infrastructure.

### How are rewards taxed / reported?
XELIS Vault is a protocol, not a tax authority. Track your own rewards via the `get_miner` view (which returns `total_rewards_earned`). Consult a tax professional in your jurisdiction.

---

## 13. Support

- **Discord**: [https://discord.gg/UHpYAWbG](https://discord.gg/UHpYAWbG) — `#mining` channel for XELIS Vault miner questions
- **Twitter / X**: [https://x.com/xelisvault](https://x.com/xelisvault) — announcements
- **Email**: `mining@xelisvault.io`
- **GitHub Issues**: [XelisVault/xelis-vault/issues](https://github.com/XelisVault/xelis-vault/issues)

---

## 14. References

- [Whitepaper v3.1 §8 — XelisVaultMiner](WHITEPAPER.md#8-xelisvaultminer--unified-mining-layer)
- [Whitepaper v3.1 §9 — MinerPool](WHITEPAPER.md#9-minerpool--composable-miner-pools)
- [Whitepaper v3.1 §10 — VaultChat](WHITEPAPER.md#10-vaultchat--end-to-end-encrypted-chat)
- [Whitepaper v3.1 §11 — PrivacyMixer](WHITEPAPER.md#11-privacymixer--anonymity-mixer)
- [Architecture](ARCHITECTURE.md) — contract interactions and entry IDs
- [Provider Guide](PROVIDER_GUIDE.md) — for the standalone `price_provider.py` (legacy path)
- [XELIS Mining Documentation](https://docs.xelis.io/features/mining) — for XELIS BlockDAG mining (separate from Vault mining)
- [XELIS Daemon Configuration](https://docs.xelis.io/getting-started/configuration/xelis_daemon)

---

*Last updated: June 2026 — v4.3*
