# Miner Guide — XELIS Vault v5.0

> Complete guide for becoming a XELIS Vault miner: stake 100 VLT, choose your
> services (oracle, chat, or both), and earn rewards through the unified
> `XelisVaultMiner` contract.

---

## 1. Introduction

### 1.1 What is a XELIS Vault miner?

A XELIS Vault miner is **not** the same as a XELIS BlockDAG miner. BlockDAG
miners produce blocks and earn XEL; Vault miners run **protocol services** and
earn **VLT** rewards. The two roles are independent — you can be one, the
other, or both.

A Vault miner signs up with the `XelisVaultMiner` contract, locks **100 VLT**
as stake, picks one or more services from a bitmask, and then keeps a daemon
process running that submits proofs/heartbeats every few minutes. In return
the protocol mints VLT to the miner address on every valid action.

| Service ID | Service | What you do | How you earn |
|------------|---------|-------------|--------------|
| 1 | **Oracle** | Fetch XEL prices from MEXC/CoinEx/your own sources and submit them on-chain every ~25s | `BASE_REWARD_ORACLE` (≈0.4756 VLT) × reputation mult × budget factor |
| 2 | **Chat** | Run a VaultChat relayer: receive signed encrypted messages, store them, anchor a Merkle root on-chain every hour | `BASE_REWARD_CHAT` (≈0.5 VLT) × reputation mult × budget factor |
| 3–8 | Reserved | Future services: storage, indexer, etc. | — |

### 1.2 Why it matters

Every swap, loan, liquidation and PSM mint on XELIS Vault reads a price from
the on-chain `StakedOracle`. If the oracle is wrong, money moves incorrectly.
Miners — by submitting prices and heartbeats — are the **decentralised defence
layer** that keeps the protocol honest. The more reliable miners there are,
the harder it is for any single party to push a bad price.

### 1.3 Expected earnings

Reward formula (v5.0):

```
dynamic_reward = BASE_REWARD_ORACLE (0.4756 VLT)
               × reputation_multiplier      (1.5× if Excellent tier, see §10)
               × budget_factor / 10000      (starts at 1.0×, auto-adjusts)
```

| Miners active | Est. reward/miner/day | ROI on 100 VLT stake |
|---------------|------------------------|-----------------------|
| 10            | ~55 VLT                | < 2 days              |
| 50            | ~11 VLT                | ~9 days               |
| 200           | ~2.7 VLT               | ~37 days              |
| 1,000         | ~0.55 VLT              | ~6 months             |

These figures assume the default `budget_factor = 10,000` (1.0×) and
Excellent-tier reputation. The protocol self-adjusts the factor every 2,016
blocks so the 6,000,000 VLT reward pool always lasts ~10 years.

---

## 2. Requirements

### 2.1 Hardware

| Setup                       | CPU    | RAM   | Disk      | Network      | Cost          |
|-----------------------------|--------|-------|-----------|--------------|---------------|
| **Minimal** (oracle only)   | 2 cores| 2 GB  | 50 GB SSD | 100 Mbps, port 8080 open | ~$5–10/mo VPS |
| **Recommended** (oracle+chat)| 4 cores| 8 GB | 200 GB SSD| 100 Mbps     | ~$20–30/mo VPS|
| **Pool operator**           | 4+ cores | 8+ GB | 500 GB NVMe | 1 Gbps    | ~$40–80/mo VPS|

### 2.2 Software

- **Python 3.10+** (`python3 --version`)
- **`requests`** + **`python-dotenv`** (auto-installed by `install.py`)
- **XELIS daemon** synced on testnet or mainnet
  (`xelis_daemon --network testnet --rpc-server`)
- **XELIS wallet** with at least **100 VLT** balance (testnet faucet or
  mainnet purchase — see §3)
- A public endpoint URL reachable from the internet (e.g.
  `https://my-miner.example.com:8080`). This is the `endpoint_url` you will
  register on-chain so users can reach your chat relayer or oracle RPC.

### 2.3 Network

- Open TCP **port 8080** on your firewall / security group so the daemon's
  JSON-RPC is reachable.
- Stable uplink with packet loss < 1 % — price submissions must be every
  ~25 s.
- Static IP or a stable DNS hostname. The `endpoint_url` you register is
  public and used by other miners / relayers.

---

## 3. Step 1 — Get VLT tokens

You need **at least 100 VLT** (10,000,000,000 atomic units at 8 decimals) to
register. Anything beyond 100 VLT is not staked automatically — call
`increase_stake` (entry ID 3) if you want a larger stake to absorb any
slashing.

### Testnet

```bash
# 1. Sync daemon + create wallet (see §4)
# 2. Claim from the FaucetContract (entry: claim_both)
xelis_wallet call-contract <FaucetContract> claim_both --signer mywallet
#   → 100 XEL testnet (for gas) + 200 VLT (more than enough to stake)
```

### Mainnet

1. Buy XEL on **MEXC** or **CoinEx** (both list XEL/USDT).
2. Withdraw XEL to your XELIS wallet address.
3. Swap XEL → VLT on **VaultSwap** (`VaultSwapV2` contract, see
   [USER_GUIDE.md](USER_GUIDE.md) §7).
4. Or buy VLT OTC from an existing holder.

---

## 4. Step 2 — Set up your XELIS wallet

```bash
# Install xelis_wallet (build from source or download a release)
git clone https://github.com/xelis-project/xelis-blockchain.git
cd xelis-blockchain
cargo build --release --bin xelis_wallet
sudo cp target/release/xelis_wallet /usr/local/bin/

# Start the wallet daemon (with RPC server so the miner script can talk to it)
xelis_wallet --network testnet --rpc-server &

# In another terminal, attach and create a wallet
xelis_wallet --network testnet
> create-wallet mywallet
#   → set a strong password (SAVE IT)
#   → write down the 24-word mnemonic (SAVE IT OFFLINE — see §12 privacy)

> get-address
#   → xet1abc...   ← this is your miner address

> get-balance
#   → confirm you have ≥ 100 VLT and some XEL for gas
```

> **Privacy note:** The miner script never logs your mnemonic or private key.
> It only talks to the wallet RPC over localhost. Keep your mnemonic offline
> (paper / hardware) — anyone with it controls your stake.

---

## 5. Step 3 — Install the XELIS Vault miner software

The `install.py` script in this repository bootstraps everything:

```bash
cd /path/to/xelis-vault-v5
python3 install.py
```

What it does:

1. Checks Python ≥ 3.10.
2. Creates a virtualenv at `~/.xelis-vault/venv`.
3. Installs `requests`, `xelis-sdk` (placeholder) and `python-dotenv`.
4. Creates `~/.xelis-vault/` with subdirs `logs/`, `config/`, `wallet/`.
5. Copies `scripts/custom_sources.example.json` →
   `~/.xelis-vault/config/custom_sources.json`.
6. Generates `~/.xelis-vault/config/.env` with placeholders.
7. Prints next steps (register miner, start daemon).

To uninstall:

```bash
python3 install.py --uninstall
```

> **Privacy note:** `install.py` does **not** collect telemetry, phone home,
> or send any wallet info anywhere. It runs entirely offline.

---

## 6. Step 4 — Configure price sources

Edit `~/.xelis-vault/config/custom_sources.json` to add API keys for the
exchanges you want to use. The default example includes CoinEx, MEXC, the
XELIS native daemon, and a generic HTTP source template (see
[`scripts/custom_sources.example.json`](../scripts/custom_sources.example.json)
and the [Provider Guide](PROVIDER_GUIDE.md) §3 for the full schema).

```json
{
  "sources": [
    {
      "name": "coinex",
      "enabled": true,
      "api_key": "YOUR_COINEX_API_KEY",
      "api_secret": "YOUR_COINEX_API_SECRET",
      "symbols": ["XEL/USDT", "XEL/BTC"],
      "poll_interval_seconds": 5
    },
    {
      "name": "mexc",
      "enabled": true,
      "api_key": "YOUR_MEXC_API_KEY",
      "api_secret": "YOUR_MEXC_API_SECRET",
      "symbols": ["XEL/USDT"],
      "poll_interval_seconds": 5
    }
  ]
}
```

> **Privacy note:** API keys are read from this local file and never logged.
> The miner log only shows the source **name**, the **price**, and the
> **timestamp** — never the API key.

Test your sources:

```bash
python3 scripts/price_provider.py --dry-run --verbose
```

You should see one line per enabled source with a fetched price.

---

## 7. Step 5 — Register as a miner

You must register **on-chain** with the `XelisVaultMiner` contract. The
register call is entry **ID 0**:

```
register_miner(endpoint_url: String, miner_pubkey: Hash, services_mask: u64)
```

### Services mask (bitmask)

| Value | Meaning                                  |
|-------|------------------------------------------|
| `1`   | Oracle only                              |
| `2`   | Chat only                                |
| `3`   | Both oracle and chat (maximum rewards)   |

You must also send **100 VLT** as deposit in the same transaction (this
becomes your stake).

```bash
xelis_wallet call-contract <XelisVaultMiner> register_miner \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 10000000000 \
    "https://my-miner.example.com:8080" \   # endpoint_url
    0x<your_chat_pubkey_or_zero_hash>        \  # miner_pubkey (0x0..0 if no chat)
    1                                            # services_mask = oracle only
```

- `endpoint_url`: public URL where users can reach your chat relayer. Leave
  as an empty string `""` if you only run oracle.
- `miner_pubkey`: X25519 public key for chat verification. Use `Hash::zero()`
  (32 zero bytes) if you are not running chat.
- The deposit (100 VLT) is locked as your stake and returned on deregistration
  (entry ID 5).

### Verify registration

```bash
# Read-only check via entry ID 11 (get_miner_reputation_entry)
xelis_wallet call-contract <XelisVaultMiner> get_miner_reputation_entry \
    xet1abc...
#   → 10000   (new miners start at maximum reputation)
```

---

## 8. Step 6 — Start the miner daemon

```bash
python3 scripts/xelis_vault_miner.py \
    --wallet ~/.xelis/wallet \
    --rpc http://localhost:8080 \
    --endpoint https://my-miner.example.com:8080 \
    --services 1
```

The daemon will:

1. Load config from `~/.xelis-vault/config/config.json` (created by
   `install.py`).
2. Connect to the XELIS daemon RPC.
3. Verify your wallet has ≥ 100 VLT (calls `VLTToken` entry **11**
   `get_asset_hash_entry`, then checks balance).
4. If you are not yet registered, call `register_miner` (entry ID **0**).
5. Loop:
   - Every **100 blocks (~8 min)**: call `submit_heartbeat` (entry ID **6**).
   - Read `get_miner_reputation_entry(addr)` (entry ID **11**). If
     reputation < 5,000 (Good tier floor), log a warning.
   - Read `is_miner_active_entry(addr, 1)` (entry ID **9**). If not active,
     attempt recovery (re-heartbeat, re-register if needed).
   - Log every action to `~/.xelis-vault/logs/miner.log` with timestamps.

### Run as a systemd service (recommended for production)

```bash
sudo tee /etc/systemd/system/xelis-vault-miner.service <<EOF
[Unit]
Description=XELIS Vault Miner v5.0
After=network.target xelis-daemon.service

[Service]
Type=simple
User=$(whoami)
ExecStart=/home/$(whoami)/.xelis-vault/venv/bin/python3 \
    /home/$(whoami)/xelis-vault-v5/scripts/xelis_vault_miner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now xelis-vault-miner
sudo journalctl -u xelis-vault-miner -f
```

### CLI flags

| Flag           | Default                              | Description                              |
|----------------|--------------------------------------|------------------------------------------|
| `--wallet`     | `~/.xelis/wallet`                    | Wallet storage path                      |
| `--rpc`        | `http://localhost:8080`              | XELIS daemon JSON-RPC URL                |
| `--endpoint`   | from config                          | Public endpoint URL                      |
| `--services`   | `1`                                  | Services mask (1/2/3)                    |
| `--dry-run`    | off                                  | Don't submit, just log what would happen |
| `--verbose`    | off                                  | DEBUG-level logging                      |

---

## 9. Step 7 — Monitor

### 9.1 Live log

```bash
tail -f ~/.xelis-vault/logs/miner.log
```

Sample output (privacy-masked):

```
2026-07-15 14:32:11 INFO  Topoheight=1,847,221  block_time=5s
2026-07-15 14:32:11 INFO  Heartbeat sent        tx=0x9f3a...c1  topo=1,847,221
2026-07-15 14:32:11 INFO  Reputation=9820 (Excellent tier)  active=true
2026-07-15 14:32:11 INFO  Wallet balance: **** (masked)
2026-07-15 14:40:08 INFO  Heartbeat sent        tx=0x4b2e...a8  topo=1,847,317
```

### 9.2 On-chain status

```bash
# Reputation (entry ID 11)
xelis_wallet call-contract <XelisVaultMiner> get_miner_reputation_entry xet1abc...
# → 9820

# Stake (entry ID 10)
xelis_wallet call-contract <XelisVaultMiner> get_miner_stake_entry xet1abc...
# → 10000000000   (= 100 VLT)

# Active? (entry ID 9)  — pass service_id=1 for oracle
xelis_wallet call-contract <XelisVaultMiner> is_miner_active_entry xet1abc... 1
# → 1   (true)

# Active miners per service (entry ID 12)
xelis_wallet call-contract <XelisVaultMiner> get_active_miners_for_service_entry 1
# → 47   (47 oracle miners currently active)

# Total staked across all miners (entry ID 14)
xelis_wallet call-contract <XelisVaultMiner> get_total_staked_entry
# → 4700000000000   (= 47,000 VLT staked network-wide)
```

### 9.3 Dashboard

A Grafana template ships at `scripts/grafana_dashboard.json` (see
[Provider Guide](PROVIDER_GUIDE.md) §8). It exposes:

- `xelis_miner_up` (gauge)
- `xelis_miner_heartbeats_total` (counter)
- `xelis_miner_reputation` (gauge)
- `xelis_miner_last_reward_vlt` (gauge)

---

## 10. Reward calculation

Every valid submission triggers `XelisVaultMiner.distribute_reward(miner_addr,
service_id, is_valid=true)` (entry ID **8** — called by the StakedOracle, not
by the miner). The reward is:

```
dynamic_reward = base_reward
               × reputation_multiplier
               × (budget_factor / 10000)
```

| Component              | Default | Source                                |
|------------------------|---------|---------------------------------------|
| `BASE_REWARD_ORACLE`   | 0.4756 VLT | `set_base_reward_oracle` (entry 21) |
| `BASE_REWARD_CHAT`     | 0.5 VLT    | `set_base_reward_chat`   (entry 22) |
| `budget_factor`        | 10,000 (=1.0×) | auto-adjusted every 2,016 blocks |
| Reputation multiplier  | 1.5× / 1.0× / 0.5× / 0.25× / 0× | based on tier (see §11) |

### Example

Miner with reputation 9,200 (Excellent tier) submitting a valid oracle price
when `budget_factor = 12,000` (1.2×):

```
dynamic_reward = 0.4756 × 1.5 × 1.2 = 0.8561 VLT
```

A miner with reputation 3,500 (Warning tier) submitting the same price:

```
dynamic_reward = 0.4756 × 0.5 × 1.2 = 0.2854 VLT
```

A miner with reputation 800 (Banned tier):

```
dynamic_reward = 0   ← no reward minted, regardless of validity
```

Read the current budget via `get_base_reward_oracle_entry` (entry ID 15) and
the global budget info via the `XelisVaultMiner` `get_budget_info` pub-fn.

---

## 11. Reputation management

Every miner has a reputation score between 0 and 10,000. New miners start at
the maximum (10,000). The score affects two things:

1. Your reward multiplier (see §10).
2. Your active status — below 1,000 you are auto-deactivated and stop earning
   until you climb back up.

### 11.1 Tiers

| Tier       | Score range     | Multiplier | Effect                                   |
|------------|-----------------|------------|------------------------------------------|
| Excellent  | 10,000 – 8,000  | **1.5×**   | Bonus rewards for top miners             |
| Good       | 8,000 – 5,000   | 1.0×       | Normal                                   |
| Warning    | 5,000 – 2,000   | 0.5×       | Half rewards — fix your setup            |
| Critical   | 2,000 – 1,000   | 0.25×      | Quarter rewards — last chance            |
| Banned     | < 1,000         | 0×         | Auto-deactivated, no rewards until regen |

**Goal: stay above 8,000 (Excellent tier).**

### 11.2 Gains

| Action                                            | Gain |
|---------------------------------------------------|------|
| Submit a valid oracle price                       | +1   |
| Anchor a batch of chat messages                   | +5   |
| Heartbeat (with no infraction in last 1,000 blk)  | +1   |
| Bonus per day with zero infractions               | +10  |

### 11.3 Losses

| Infraction                                | Rep loss | Stake slash | Severity |
|-------------------------------------------|----------|-------------|----------|
| Oracle outlier price (>5 % from median)   | -50      | 1 %         | 0        |
| Node offline detected                     | -200     | 2 %         | 1        |
| Chat data loss (lost stored messages)     | -500     | 5 %         | 2        |
| Chat censorship (refused valid messages)  | -1,000   | 10 %        | 3        |
| Malicious behaviour (proven)              | -5,000   | 50 %        | 4        |

Stake slash split: **50 % burned** (deflationary), **10 % to the reporter**
(incentive for watchdogs), **40 % to the treasury**.

### 11.4 Regenerating reputation

Each heartbeat (every ~8 min) gives +1 reputation **if** you have had no
infraction in the last 1,000 blocks (~83 min):

- One outlier (-50) → ~50 heartbeats = ~7 h of clean operation.
- One censorship event (-1,000) → ~1,000 heartbeats = ~5.5 days.
- Banned tier → must climb back above 1,000 before re-activation.

### 11.5 How to stay Excellent

1. Use **≥ 2 reliable price sources** (MEXC + CoinEx minimum).
2. **Validate locally** before submitting: reject prices >5 % from your own
   median, or older than 30 s.
3. **Monitor heartbeat** — the daemon sends one every 100 blocks; alert if
   `last_heartbeat_block` falls behind by more than 300 blocks.
4. Run the daemon under systemd with `Restart=always`.
5. Keep your stake topped up (≥ 100 VLT) so a few slashes don't de-activate
   you.

---

## 12. Slashing

### 12.1 What triggers it

Anyone (other miner, watchdog bot, or governance) can call
`slash_miner(miner_addr, severity, reporter)` (entry ID **7**) on
`XelisVaultMiner`. Severity codes are 0–4 (see §11.3). The contract verifies
the report — for severities 0 and 1 it accepts the call from
`StakedOracle`/`VaultChat` directly; for higher severities it requires
governance or guardian approval (see `GuardianMultisig`).

### 12.2 How to avoid it

| Risk                 | Mitigation                                            |
|----------------------|-------------------------------------------------------|
| Outlier (-50)        | Use ≥ 2 sources; reject prices >5 % from local median |
| Offline (-200)       | systemd `Restart=always`; monitor `last_heartbeat`    |
| Data loss (-500)     | Replicate chat storage; fsync before anchoring        |
| Censorship (-1,000)  | Don't filter messages — accept all signed by sender   |
| Malicious (-5,000)   | Never submit prices you know to be wrong              |

### 12.3 Reporting others

If you observe a misbehaving miner, collect evidence (block range, submission
hashes) and submit a slash proposal via `GuardianMultisig` (see
[USER_GUIDE.md](USER_GUIDE.md) §8). The reporter receives 10 % of the slash.

> **Privacy note:** Slash events are public on-chain (miner address +
> severity + reporter). The miner daemon logs them locally but never logs
> other miners' IP addresses or wallet balances.

---

## 13. Deregistration

When you want to exit:

1. **Stop the daemon** (`systemctl stop xelis-vault-miner`).
2. **Leave any pool** if you joined one (call `MinerPool.leave_pool`).
3. **Call deregister** (entry ID **5**):

```bash
xelis_wallet call-contract <XelisVaultMiner> deregister_miner --signer mywallet
```

### What happens to your stake?

- Your **full stake** (100 VLT minus any accumulated slash) is transferred
  back to your wallet address.
- Your miner entry is removed from the registry (subsequent heartbeats will
  revert with `notreg`).
- Any **pending rewards** in the contract are paid out before the stake is
  returned.
- Your historical stats (`total_rewards_earned`, `total_slashed`) are kept
  on-chain forever for transparency.

If you ever want to come back, just call `register_miner` again with a fresh
100 VLT deposit. Your reputation resets to 10,000.

---

## 14. Troubleshooting

### 14.1 `insstake` error on `register_miner`

You don't have 100 VLT deposited. The `register_miner` call expects a
`--deposit` of at least 10,000,000,000 atomic units (100 VLT) of the VLT
asset.

```bash
xelis_wallet balance <your_addr> <VLT_ASSET_HASH>
# If insufficient: claim from faucet (testnet) or buy on VaultSwap (mainnet)
```

### 14.2 `alreadyreg` error

You are already registered. Check with `is_miner_active_entry(addr, 1)`
(entry ID 9). If you want to change services mask, use `enable_service` /
`disable_service` (entries 1 and 2) instead of re-registering.

### 14.3 `hbtoosoon` error

You sent a heartbeat less than `HEARTBEAT_INTERVAL` blocks ago (default 100
blocks ≈ 8 min). The daemon throttles heartbeats automatically — if you see
this, your clock or the daemon's loop interval is misconfigured.

### 14.4 `oorange` error on `submit_price`

Your price is outside the `[min_price, max_price]` range for the feed (set
when the feed was created via `add_feed`, entry ID 0 on `StakedOracle`).
Test your sources:

```bash
python3 scripts/price_provider.py --dry-run --verbose
```

### 14.5 Reputation keeps dropping

- Run `python3 scripts/xelis_vault_miner.py --test-sources` to verify each
  source.
- Add a more reliable source (MEXC + CoinEx are production-tested).
- If reputation is in Critical (< 2,000), **stop**, fix your setup, and let
  heartbeats regenerate you (~7 h per 50 points).

### 14.6 `notauth` error when calling `distribute_reward`

Only `StakedOracle` and `VaultChat` (or other contracts registered via
`register_service` entry ID 16) can call `distribute_reward` and
`slash_miner`. If you see this error as a miner, it's a contract-level issue —
report it on GitHub.

### 14.7 Daemon cannot connect to RPC

```bash
# Check daemon is running and synced
curl -X POST http://127.0.0.1:8080 \
    -H "Content-Type: application/json" \
    -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}'
# Should return {"result":{"synced":true,"topoheight":...}}
```

### 14.8 Wallet balance shows **** in logs

That's intentional — the daemon masks wallet balances in logs by default. To
see the real balance, use `xelis_wallet get-balance` directly.

---

## 15. FAQ

### Q1. How much can I earn per day?
At 50 active miners and Excellent reputation: ~11 VLT/day. At 200 miners:
~2.7 VLT/day. The protocol auto-adjusts `budget_factor` so the 6M VLT pool
always lasts ~10 years (see §10).

### Q2. Can I run multiple miners from the same wallet?
No. One address = one miner registration. Use a separate wallet per miner
instance.

### Q3. Can I run multiple miners on the same machine?
Yes, but they need different wallets and different Prometheus ports (set
`PROMETHEUS_PORT` per instance).

### Q4. What if my node goes offline?
No penalty for being offline **briefly** (you just miss reward cycles). After
`HEARTBEAT_TIMEOUT` (300 blocks ≈ 25 min) other miners can report you as
offline → severity 1 → -200 reputation, 2 % stake slash.

### Q5. Do I need to also be a XELIS BlockDAG miner?
No. Vault mining and BlockDAG mining are completely independent. You can run
a Vault miner on a $5 VPS without ever mining a block.

### Q6. Can I run oracle without chat?
Yes — set `services_mask = 1` (or pass `--services 1` to the daemon).

### Q7. What happens if my stake drops below 100 VLT?
After cumulative slashing, you are auto-deactivated. Call
`increase_stake(amount)` (entry ID 3) to top up and re-activate.

### Q8. How do I withdraw my stake?
Call `deregister_miner` (entry ID 5). Your full stake is returned. See §13.

### Q9. Is my IP address public?
The `endpoint_url` you register is public (so users can reach your chat
relayer). If you run oracle only, register an empty string `""` as the
endpoint to keep your IP private. Your wallet address is always public
on-chain (it signs transactions).

### Q10. Can I use a hardware wallet?
Yes. The miner daemon talks to `xelis_wallet` over RPC; if your wallet is
backed by a hardware signer, the daemon will simply route each signing
request to it.

### Q11. What happens to rewards if the oracle is paused?
When `StakedOracle.pause(reason)` (entry ID 11) is called, no new prices are
accepted, so no `distribute_reward` calls happen. Your stake and reputation
are unaffected. Mining resumes when `unpause()` (entry ID 12) is called.

### Q12. Where do I get help?
- Discord: https://discord.gg/UHpYAWbG — `#mining` channel
- Twitter / X: https://x.com/xelisvault
- Email: `mining@xelisvault.io`
- GitHub Issues: https://github.com/XelisVault/xelis-vault/issues

---

## 16. References

- [Whitepaper v5.0 — XelisVaultMiner](WHITEPAPER.md)
- [Reward System](REWARD_SYSTEM.md) — full math + budget auto-adjustment
- [Architecture](../README.md) — contract interactions and entry IDs
- [Entry IDs v5.0](ENTRY_IDS.md) — canonical list of all 630 entry functions
- [Provider Guide](PROVIDER_GUIDE.md) — for the standalone `price_provider.py`
- [User Guide](USER_GUIDE.md) — lending, swap, governance, mixer, chat
- [XELIS Mining Documentation](https://docs.xelis.io/features/mining) — for
  XELIS BlockDAG mining (separate from Vault mining)

---

*Last updated: July 2026 — v5.0*
