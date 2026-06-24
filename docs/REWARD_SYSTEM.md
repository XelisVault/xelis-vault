# XELIS Vault — Reward & Reputation System

> How miners earn VLT, how reputation gates rewards, and how the protocol stays economically sustainable over 10 years.

## Overview

The XELIS Vault reward system is a **budget-aware, reputation-weighted, dynamically-adjusted** incentive mechanism. It is designed to:

1. Distribute **6,000,000 VLT** (60% of total supply) to oracle providers over **10 years**.
2. Reward honest miners more than dishonest ones (up to 1.5× multiplier).
3. Penalize dishonest miners (up to 50% slash + reputation loss).
4. Auto-adjust distribution rate every 2 weeks so the budget lasts exactly 10 years.
5. Support multiple services (oracle, chat, future) with per-service reward rates.

The system lives entirely in [`contracts/miner/XelisVaultMiner.slx`](../contracts/miner/XelisVaultMiner.slx) — `StakedOracle` only calls `distribute_reward` and `slash_miner` when it aggregates prices.

---

## 1. Miner Lifecycle

### Registration

A miner registers via `XelisVaultMiner.register_miner(endpoint_url, miner_pubkey, services_mask)`:

- **Stake requirement:** 100 VLT (configurable via `set_min_stake`, min 10 VLT).
- **services_mask:** bitmask of services the miner will provide:
  - bit 0 (`mask & 1`): oracle (price feeds)
  - bit 1 (`mask & 2`): chat (message anchoring)
  - bits 2–7: reserved for future services
- **Initial reputation:** `REP_MAX = 10,000` (Excellent tier)
- **Active flag:** `true` (immediately eligible for rewards)

The 100 VLT stake is **locked** in the contract. It can be withdrawn only via `deregister_miner` (full unstake) or `decrease_stake` (partial). If stake drops below `MIN_STAKE`, the miner is marked inactive.

### Heartbeats

Miners must call `submit_heartbeat()` periodically (every 100 blocks ≈ 8 minutes by default). Each heartbeat:

- Resets `last_heartbeat`
- If no infraction in the last 1000 blocks, gains +1 reputation (capped at 10,000)

If a miner misses heartbeats for `HEARTBEAT_TIMEOUT` blocks (300 ≈ 25 min), `StakedOracle.check_miner` will return `false` and the miner cannot submit prices.

### Deregistration

`deregister_miner()` returns the full stake to the miner and deletes their record. There is **no time-lock on deregistration** — but if the miner had any recent infraction, slashing has already reduced their stake.

---

## 2. Reputation System

Reputation is a `u64` between `0` and `10,000` stored per-miner. It determines:

- Whether the miner is **active** (≥ `REP_CRITICAL = 1,000`)
- The miner's **reward multiplier** (0× to 1.5×)

### Reputation Tiers

| Tier | Range | Multiplier | Description |
|------|-------|------------|-------------|
| **Excellent** | 8,000 – 10,000 | 1.5× (15,000 bps) | Default tier for new miners |
| **Good** | 5,000 – 7,999 | 1.0× (10,000 bps) | Minor infractions |
| **Warning** | 2,000 – 4,999 | 0.5× (5,000 bps) | Multiple infractions |
| **Critical** | 1,000 – 1,999 | 0.25× (2,500 bps) | Last chance before ban |
| **Banned** | 0 – 999 | 0× (no rewards) | Cannot earn, must rebuild via heartbeats |

A miner with reputation < `REP_CRITICAL` is marked `active = false` and cannot submit prices until they rebuild reputation via heartbeats (+1 per heartbeat, capped at 1000-block cooldown).

### Reputation Gains

| Action | Gain | Trigger |
|--------|------|---------|
| Valid price submission (oracle) | +1 (`REP_GAIN_PRICE`) | `distribute_reward(addr, 1, true)` called by StakedOracle after median aggregation |
| Valid chat anchor | +5 (`REP_GAIN_ANCHOR`) | `distribute_reward(addr, 2, true)` called by VaultChat |
| Heartbeat (no recent infraction) | +1 (`REP_GAIN_HEARTBEAT`) | `submit_heartbeat()` if no infraction in last 1000 blocks |

### Reputation Losses

| Severity | Slash (bps) | Rep Loss | Trigger |
|----------|-------------|----------|---------|
| 0 (Outlier) | 100 (1%) | 50 | Price deviates >5% from median |
| 1 (Offline) | 200 (2%) | 200 | Missed heartbeats |
| 2 (Data loss) | 500 (5%) | 500 | Submitted invalid data |
| 3 (Censorship) | 1,000 (10%) | 1,000 | Refused to include transactions |
| 4 (Malicious) | 5,000 (50%) | 5,000 | Proven price manipulation |

Reputation cannot go below 0. `last_infraction_topo` is updated on every infraction, blocking heartbeat reputation gains for the next 1000 blocks.

---

## 3. Slashing Mechanics

When `StakedOracle` detects an outlier during `aggregate()`, it calls `XelisVaultMiner.slash_miner(addr, severity, reporter)` (entry ID 7).

### Slash Distribution

For a slash of amount `S`:

- **50% burned** — `burn(S/2, VLT_asset)` — permanently removed from supply
- **10% to reporter** — `transfer(reporter, S/10, VLT_asset)` — incentivizes whistleblowers
- **40% to treasury** — `transfer(treasury, S - S/2 - S/10, VLT_asset)` — protocol revenue

The reporter is the `GUARDIAN_KEY` address (set by governance). Future versions may allow any user to submit a slash proof and earn the 10% bounty.

### Example

A miner with 100 VLT stake submits a price 6% off median (severity 0, outlier):
- Slash amount = 100 × 100 / 10000 = **1 VLT**
- Burned: 0.5 VLT
- Reporter: 0.1 VLT
- Treasury: 0.4 VLT
- Miner new stake: 99 VLT
- Miner new reputation: 10,000 − 50 = 9,950 (still Excellent tier)

If the same miner submits a malicious price (severity 4):
- Slash amount = 100 × 5000 / 10000 = **50 VLT**
- Burned: 25 VLT
- Reporter: 5 VLT
- Treasury: 20 VLT
- Miner new stake: 50 VLT (still above 100 VLT minimum → would be marked inactive)
- Miner new reputation: 10,000 − 5,000 = 5,000 (drops to Good tier, 1× multiplier)

---

## 4. Reward Calculation

When `StakedOracle.aggregate()` completes median aggregation, it calls `XelisVaultMiner.distribute_reward(addr, service_id, is_valid)` (entry ID 8) for every valid provider.

### Formula

```
reward = base_reward × reputation_multiplier × budget_factor / 100,000,000
```

Where:
- `base_reward` = `BASE_REWARD_ORACLE_KEY` (default 47,564,687 = 0.4756 VLT) for service 1 (oracle), or `BASE_REWARD_CHAT_KEY` (default 50,000,000 = 0.5 VLT) for service 2 (chat)
- `reputation_multiplier` = 15,000 (Excellent), 10,000 (Good), 5,000 (Warning), 2,500 (Critical), 0 (Banned)
- `budget_factor` = dynamic, default 10,000 (1×), clamped between 5,000 (0.5×) and 20,000 (2×)
- Division by 100,000,000 = `multiplier (max 15,000) × budget_factor (max 20,000)` = 300,000,000 worst case

### Example

Excellent-tier miner submitting a valid oracle price with `budget_factor = 10,000`:
```
reward = 47,564,687 × 15,000 × 10,000 / 100,000,000
       = 47,564,687 × 150,000,000 / 100,000,000
       = 47,564,687 × 1.5
       = 71,347,030 (0.7135 VLT)
```

Warning-tier miner (same conditions):
```
reward = 47,564,687 × 5,000 × 10,000 / 100,000,000
       = 47,564,687 × 0.5
       = 23,782,343 (0.2378 VLT)
```

So an Excellent-tier miner earns **3× more** than a Warning-tier miner per valid submission.

### Budget Cap

Before minting, the contract checks:
```
if distributed + reward > total_budget:
    skip reward (return 0)
```

This guarantees the 6,000,000 VLT budget is never exceeded.

---

## 5. Dynamic Budget Adjustment

Every `BUDGET_ADJUST_INTERVAL` blocks (default 2,016 ≈ 2 weeks), `maybe_adjust_budget()` runs (called from `submit_heartbeat` and `distribute_reward`).

### Algorithm

```
elapsed = current_topo - launch_topo
remaining_budget = total_budget - distributed
remaining_time = target_duration - elapsed  (10 years in blocks)
target_rate = remaining_budget / remaining_time  (VLT per block)
actual_rate = distributed / elapsed
token_count = total_staked  (guard: if 0, skip adjustment)

if actual_rate > target_rate:
    # Distributing too fast — scale down proportionally
    ratio = target_rate / actual_rate
    new_factor = current_factor × ratio / 10000
elif actual_rate == 0:
    # No distribution yet — slight bump (+10%)
    new_factor = current_factor × 110 / 100
elif actual_rate < target_rate / 2:
    # Distributing too slow — scale up
    ratio = target_rate / actual_rate
    new_factor = (current_factor + ratio × current_factor / 10000) / 2
else:
    # On track — no change
    new_factor = current_factor

# Symmetric clamp
new_factor = max(5000, min(20000, new_factor))
```

### Why This Works

- **Target:** 6,000,000 VLT over 6,307,2,000 blocks (≈ 10 years at 5s/block) = ~951 VLT per block
- If actual distribution is 2× too fast, `budget_factor` halves → rewards halve → distribution slows down
- If actual distribution is 2× too slow, `budget_factor` increases up to 2× → rewards double → distribution speeds up
- The clamp (5,000–20,000) prevents runaway feedback loops

### Bootstrap Mode

For the first weeks/months, the protocol runs in **bootstrap mode**:
- Minimum 3 active providers (instead of 10) required to read prices
- 1-hour lock-in period (instead of 30 days)

Once 20+ active miners are registered, governance can call `StakedOracle.disable_bootstrap()` to switch to normal mode.

---

## 6. Economic Sustainability

### VLT Token Distribution (10,000,000 VLT total)

| Allocation | Amount | % | Vesting |
|------------|--------|---|---------|
| Oracle provider rewards | 6,000,000 | 60% | Distributed over 10 years via budget-aware mechanism |
| Founding team | 1,000,000 | 10% | 4-year vesting, 1-year cliff |
| Protocol treasury | 1,000,000 | 10% | Governance-controlled |
| DEX liquidity (VaultSwap) | 1,200,000 | 12% | 6-month linear unlock |
| Seed investors | 500,000 | 5% | 2-year vesting, 6-month cliff |
| Community airdrop | 200,000 | 2% | 1 year post-mainnet |
| Bug bounty | 100,000 | 1% | Perpetual |

### Burn Mechanisms (Deflationary Pressure)

1. **50% of every slash is burned** — At current outlier rate (~5% of submissions), this could burn 100–500 VLT/day.
2. **50% of protocol fees are burned** — VaultEngine borrow fees, PSM mint/redeem fees, VaultSwap swap fees.
3. **Governance burns** — Community can vote to burn treasury VLT.

### Revenue Streams (Treasury Income)

1. **VaultEngine stability fee** — 2% APR on all outstanding xUSD borrows
2. **VaultEngine one-shot fees** — 50 bps protocol + 10 bps insurance on borrow
3. **VaultEngine redemption fee** — 50 bps on redeem
4. **VaultEngine liquidation penalty** — 10% seized from liquidated collateral
5. **PSM mint fee** — 50 bps
6. **PSM redeem fee** — 10 bps
7. **VaultSwap base fee** — 30 bps
8. **VaultSwap treasury fee** — 5 bps (of swap output)
9. **VaultSwap high-volatility fee** — 100 bps (when TWAP volatility > 10%)
10. **LendingMarket reserve factor** — 10% of interest accrued
11. **PeerLoan protocol fee** — 10 bps on loan amount
12. **SealedBidAuction protocol fee** — 100 bps on winning bid

All revenue flows to `TREASURY_KEY` (the `TreasuryVault` contract) and is governable via `RevenueShare` to be distributed to VLT stakers in `GovernanceVault`.

---

## 7. GovernanceVault Staking Rewards

Separately from miner rewards, VLT holders can stake in `GovernanceVault` to:
- Earn voting power (1 VLT = 1 vote, up to 2× boost if locked 365 days)
- Earn staking rewards (distributed from treasury via `notify_reward_amount`)

### Reward Calculation (Synthetix-style)

```
reward_per_token (RPT) accumulates over time:
  RPT_delta = reward_amount × 1e12 / total_voting_power

Per user:
  earned = user_vp × (current_RPT - user_paid_RPT) / 1e12
```

`notify_reward_amount(amount)` is callable only by authorized distributors (e.g., `TreasuryVault`, `RevenueShare`). The `set_reward_distributor(contract_hash, enabled)` entry controls authorization.

### Voting Power Boost

```
boost_bps = 10,000 + (lock_days × 10,000 / 365)   // capped at 20,000 (2×)
voting_power = amount × boost_bps / 10,000
```

- 7-day lock (minimum): 1.19× boost
- 90-day lock: 1.5× boost
- 365-day lock (maximum): 2× boost

The `CR-01 FIX` enforces `lock_days >= 7` to prevent instant unstake/restake vote cycling.

---

## 8. Service-Specific Rewards

The system is designed to support multiple services with independent reward rates:

| Service ID | Description | Base Reward | Reputation Gain |
|------------|-------------|-------------|-----------------|
| 1 | Oracle (price feeds) | 0.4756 VLT (`BASE_REWARD_ORACLE`) | +1 per valid price |
| 2 | Chat (message anchoring) | 0.5 VLT (`BASE_REWARD_CHAT`) | +5 per valid anchor |
| 3–8 | Reserved for future services | Configurable via `set_base_reward_*` | TBD |

A miner can register for multiple services by setting the corresponding bits in `services_mask` (e.g., `0b11 = 3` for oracle + chat). The same stake backs all services.

---

## 9. Anti-Gaming Measures

1. **Anti-spam** — `submit_price` rejects if the same `(feed_id, cycle, provider)` already submitted (`SUB_PROVIDED_PREFIX`).
2. **Anti-flash-loan attack** — Stake must be deposited for at least 1 block before submitting prices (cannot borrow VLT, register, submit, get reward, deregister in the same block).
3. **Anti-collusion** — Median aggregation + deviation check means a single miner cannot move the price; collusion of >50% would slash all participants (severity 4).
4. **Anti-Sybil** — Each miner requires 100 VLT stake, so creating N Sybil identities costs 100×N VLT. The reputation system penalizes new identities (start at Excellent but a single infraction drops to Good).
5. **Anti-front-running** — XELIS BlockDAG has ~5s block time and homomorphic-encrypted balances, making on-chain front-running economically infeasible.

---

## 10. Monitoring & Upgrades

### On-Chain Views

- `XelisVaultMiner.get_miner(addr)` — full miner record
- `XelisVaultMiner.get_config()` — min_stake, base rewards, budget factor, distributed
- `XelisVaultMiner.get_budget_info()` — total budget, distributed, factor, launch topo, target duration
- `XelisVaultMiner.get_active_miners_count()` — current active miners
- `XelisVaultMiner.get_active_miners_for_service_entry(service_id)` — per-service count

### Governance-Adjustable Parameters

| Parameter | Entry | Range |
|-----------|-------|-------|
| Min stake | `set_min_stake` | ≥ 10 VLT |
| Heartbeat interval | `set_heartbeat_interval` | 10–1000 blocks |
| Heartbeat timeout | `set_heartbeat_timeout` | 100–10000 blocks |
| Base reward (oracle) | `set_base_reward_oracle` | ≤ 10 VLT |
| Base reward (chat) | `set_base_reward_chat` | ≤ 10 VLT |
| Total budget | `set_total_budget` | any |
| Target duration | `set_target_duration` | ≥ 1 year |
| Bootstrap min providers | `StakedOracle.set_bootstrap_min_providers` | 1–10 |
| Min providers (normal) | `StakedOracle.set_min_providers` | 3–100 |

### Upgrade Path

All parameter changes require either:
- Direct admin call (only during testnet phase), OR
- Timelock-queued proposal (after mainnet launch), with 720-block (1h) min delay.

Critical parameter changes (min_stake, base_reward, total_budget) should be queued with the max delay (604,800 blocks = 5 days) to give miners time to react.

---

## Summary

The XELIS Vault reward system is a **carefully balanced incentive mechanism**:

- **Miners** are rewarded for honest participation (up to 1.5× multiplier) and penalized for dishonesty (up to 50% slash + reputation loss).
- **The protocol** sustains itself over 10 years via dynamic budget adjustment, ensuring the 6M VLT budget is distributed evenly.
- **The community** benefits from deflationary pressure (burns) and treasury revenue (fees), both of which flow back to VLT stakers.

The system is fully transparent — every parameter is on-chain, every calculation is verifiable, every slash is appealable via governance. Combined with XELIS-native privacy (confidential balances, homomorphic encryption), this makes XELIS Vault one of the most economically sound DeFi protocols on a privacy chain.
