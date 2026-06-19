# XELIS Vault — Technical Whitepaper v3.1

> *The First Confidential Financial Platform on XELIS BlockDAG*
>
> *Confidential lending, tokenization, treasury, compliance, markets, encrypted chat, and anonymity mixing — powered by native homomorphic encryption, a decentralized staked oracle, and a unified miner network*

**Version**: 3.1 (June 2026)
**Status**: Draft for community review
**Authors**: XELIS Vault team

---

## Abstract

XELIS Vault is a decentralized financial platform built on the XELIS BlockDAG. It leverages XELIS native **Twisted ElGamal homomorphic encryption** to provide the first truly confidential financial ecosystem in blockchain history. The platform encompasses:

- **Confidential Lending** — overcollateralized loans with private positions
- **Private Lending Marketplace** — multi-pool, multi-collateral lending with dynamic rates
- **Real-World Asset (RWA) Tokenization** — standard for issuing private tokens representing real assets
- **Private Treasury Management** — multi-signature confidential treasuries for DAOs and institutions
- **Compliance & Identity Layer** — ZK-based KYC/AML proofs without exposing identity
- **Private Sealed-Bid Auctions** — fully confidential bidding
- **Governance Token (VLT)** — protocol ownership, parameter voting, and oracle participation
- **Unified Miner Network (XelisVaultMiner)** — reputation-based mining system where miners stake 100 VLT and serve the oracle, the encrypted chat, or both
- **Miner Pools** — miners can mutualize stake, reputation, and rewards into composable pools
- **Encrypted Chat (VaultChat)** — end-to-end encrypted messaging anchored on-chain, served by miner relayers
- **Anonymity Mixer (PrivacyMixer)** — Tornado Cash-style ZK mixer for unlinkable transfers in fixed denominations

The v3.1 whitepaper introduces a **fundamental redesign of the oracle system**: instead of relying on permissioned price bots (v1/v2) or XELIS miners only (v3), the v4 architecture uses a **permissionless staked oracle** where any VLT holder can become a price provider by staking VLT as collateral. This eliminates single points of failure, aligns incentives through slashing, and creates a deflationary pressure on VLT through systematic burning.

v3.1 also introduces the **unified mining layer** (`XelisVaultMiner`), which formalizes how miners contribute to multiple protocol services (oracle, chat, and future ones), with a precise reputation system, dynamic reward calibration, and an automatic 10-year budget control mechanism.

---

## 1. Introduction

### 1.1 The Privacy Gap in DeFi

Current DeFi operates on fully transparent ledgers. Every position, liquidation, and transfer is visible to everyone — including MEV bots, competitors, and regulators. This transparency creates fundamental problems:

- **Front-running and MEV** — bots extract value from public transactions
- **Institutional exclusion** — regulated entities cannot reveal their positions
- **Privacy loss** — financial history is permanently public
- **Competitive disadvantage** — strategies, leverage, and holdings are exposed

### 1.2 The Oracle Problem

Even privacy-focused DeFi platforms suffer from a critical weakness: their oracles. Most oracles are either:

- **Admin-controlled** — a single entity can manipulate prices (MakerDAO's early days)
- **Permissioned** — only whitelisted node operators can submit prices (Chainlink, Pyth)
- **Miner-dependent** — limited to a small set of miners (v3 MinerOracle design)

Each of these creates centralization risks and attack vectors. XELIS Vault v4.2 solves this with a **permissionless staked oracle**: anyone can participate, but must stake VLT as collateral. Bad behavior is slashed; good behavior is rewarded.

### 1.3 The XELIS Opportunity

XELIS provides the cryptographic primitives to solve both problems:

- **Twisted ElGamal over Ristretto255** — homomorphic encryption at the protocol level
- **Confidential Assets** — every token is private by default
- **XVM + Silex** — a capable smart contract environment
- **BlockDAG Architecture** — 5-second blocks, high throughput

XELIS Vault is the first platform to productize these primitives into a complete, institution-grade financial ecosystem with a truly decentralized oracle.

---

## 2. Protocol Architecture v4.2

### 2.1 Smart Contract Layers

```
┌──────────────────────────────────────┐
│           TOKEN LAYER                │
│         VLTToken.slx                  │
│ (10M fixed supply, deflationary)     │
└──────────────────────────────────────┘
              ▲
              │ stake VLT
              │
┌──────────────────────────────────────┐
│         ORACLE LAYER                  │
│  StakedOracle.slx                     │
│  OracleGovernance.slx                 │
│ (permissionless providers + slashing) │
└──────────────────────────────────────┘
              │
              │ get_price("XEL/USD")
              ▼
┌──────────────────────────────────────┐
│         CORE LENDING                  │
│  VaultEngineV3.slx                    │
│  xUSD.slx                             │
│  SavingsRate.slx                      │
│  FlashLoan.slx                        │
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│           AMM LAYER                   │
│  VaultSwapV2.slx (AMM + PSM)         │
│  with MEV protection                  │
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│         INFRASTRUCTURE                │
│  ContractRegistry.slx                 │
│  ReentrancyGuard.slx                  │
│  Pausable.slx                         │
│  Timelock.slx                         │
└──────────────────────────────────────┘
```

### 2.2 Contract Catalog

XELIS Vault v4.2 ships **33 smart contracts** organized in 14 categories. The 8 core contracts are summarized below; the full list is maintained in [`docs/COMPATIBILITY_TABLE.md`](COMPATIBILITY_TABLE.md) and [`README.md`](../README.md).

| Contract | Type | Purpose |
|----------|------|---------|
| `VLTToken.slx` | Token | Governance token, 10M fixed supply, deflationary via burn |
| `StakedOracle.slx` | Oracle | Permissionless price oracle with staking + slashing |
| `OracleGovernance.slx` | Governance | VLT stakers vote to add/modify feeds |
| `VaultEngineV3.slx` | Core | Overcollateralized lending with Ciphertext-encrypted positions |
| `VaultSwapV2.slx` | AMM | Constant product AMM + PSM with slippage protection |
| `XelisVaultMiner.slx` | Mining | Unified miner registry: reputation, dynamic rewards, 10-year budget control |
| `MinerPool.slx` | Mining | Composable miner pools with mutualized stake and reputation |
| `VaultChat.slx` | Chat | End-to-end encrypted chat with on-chain merkle anchoring |
| `PrivacyMixer.slx` | Privacy | Tornado-style ZK anonymity mixer (denominations 10 / 100 / 1000) |
| `ContractRegistry.slx` | Infra | Versioned registry for upgrade pattern |
| `ReentrancyGuard.slx` | Lib | Anti-reentrancy module |
| `Pausable.slx` | Lib | Emergency pause module |

---

## 3. VLT Token — Fixed Supply, Deflationary

### 3.1 Token Specifications

> **Note (v3.1):** the minimum stake to become a miner/provider on `XelisVaultMiner` and `StakedOracle` is **100 VLT** (was 1,000 VLT in earlier drafts). This 10x reduction makes the network accessible to a much broader set of participants without meaningfully weakening Sybil resistance, since the slashing and reputation mechanics still make attacks economically infeasible (see §4.4 and §8).

- **Name**: XELIS Vault
- **Ticker**: VLT
- **Decimals**: 8
- **Maximum Supply**: 10,000,000 VLT (fixed, never increased)
- **Asset Type**: XELIS Confidential Asset (private by default)

### 3.2 Initial Distribution

| Allocation | % | Amount | Vesting |
|------------|---|--------|---------|
| Oracle Rewards | 60% | 6,000,000 VLT | Distributed over 10 years |
| Team | 15% | 1,500,000 VLT | 4 years vesting, 1 year cliff |
| Treasury | 12% | 1,200,000 VLT | Governance-controlled |
| DEX Liquidity | 10% | 1,000,000 VLT | VaultSwap initial pools |
| Airdrop | 2% | 200,000 VLT | 1 year post-mainnet |
| Bug Bounty | 1% | 100,000 VLT | Perpetual |

### 3.3 Deflation Mechanism

VLT is **deflationary** through three independent burn sources:

**Burn #1 — 50% of protocol fees**
All protocol fees (swap fees, PSM mint/redeem fees, borrowing fees, redemption fees) are split: 50% burned, 50% to treasury. The more the protocol is used, the faster VLT supply decreases.

**Burn #2 — 50% of slashing**
When a price provider is slashed for submitting an outlier price, 50% of the slash is burned (reducing total supply) and 50% goes to treasury. This penalizes attackers twice: they lose their stake AND the global supply decreases (benefiting all holders).

**Burn #3 — Governance burn (optional)**
A governance proposal can decide to burn a portion of the treasury to accelerate deflation. Requires an enhanced quorum of 15%.

### 3.4 Supply Projection

Based on moderate protocol usage ($50k/day volume):

| Period | Supply | Cumulative Burn |
|--------|--------|-----------------|
| Launch (Year 0) | 10,000,000 | 0 |
| Year 1 | ~9,200,000 | ~800,000 |
| Year 3 | ~7,500,000 | ~2,500,000 |
| Year 5 | ~6,000,000 | ~4,000,000 |
| Year 10 | ~3,000,000 | ~7,000,000 |

In the high-adoption scenario, supply could be divided by 3 in 10 years.

---

## 4. StakedOracle — Permissionless Decentralized Oracle

### 4.1 Design Principles

The StakedOracle is built on three principles:

1. **Permissionless** — Anyone can become a price provider by staking VLT
2. **Sybil-resistant** — Stake acts as collateral, slashable for bad behavior
3. **Self-balancing** — More providers = lower per-provider rewards = natural equilibrium

### 4.2 Provider Lifecycle

```
┌──────────────────────────────────────────────────┐
│ 1. REGISTER: stake 100 VLT via register_provider  │
└──────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ 2. SUBMIT: send prices every cycle (25s)          │
│    - Read external sources (MEXC, CoinEx, etc.)   │
│    - Compute median locally                       │
│    - Call submit_price(feed_id, price_atomic)     │
└──────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ 3. REWARD: if price is valid (within 5% of median)│
│    → receive REWARD_PER_CYCLE / n_valid VLT       │
└──────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ 4. SLASH: if price is outlier (>5% from median)   │
│    → lose 1% of stake (50% burned, 50% treasury)  │
└──────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ 5. DEREGISTER: withdraw full stake at any time    │
│    via deregister_provider                         │
└──────────────────────────────────────────────────┘
```

### 4.3 Aggregation Cycle

Every `AGGREGATION_BLOCKS` (default 5 blocks = 25 seconds), the oracle:

1. **Collects** all submissions for the current cycle
2. **Sorts** prices in ascending order
3. **Computes median** (the official aggregated price)
4. **Identifies valid prices** (within `MAX_DEVIATION_BPS` = 5% of median)
5. **Distributes rewards**: `REWARD_PER_CYCLE / n_valid` VLT to each valid provider
6. **Slashes outliers**: 1% of stake per outlier (50% burned, 50% treasury)
7. **Updates the aggregated price** on-chain
8. **Circuit breaker check**: if new price differs >20% from previous, feed pauses

### 4.4 Anti-Sybil Economics

To manipulate the median, an attacker must control >50% of active providers. If 100 providers are active, the attacker needs 51 providers, requiring 51 × 100 = 5,100 VLT stake (0.05% of total supply).

The lower absolute stake is offset by the **reputation system** (§8.2): a brand-new attacker starts at reputation 10,000 but is rapidly drained by outliers (-50 rep/each, plus 1% of stake), and once their reputation falls below `REP_CRITICAL` (1,000), the miner is automatically deactivated and stops earning rewards. To re-activate, they must keep submitting valid prices to climb back above the threshold — meaning the attack surface is bounded by the *reputation regeneration rate*, not just the stake amount.

Even if successful for a short window, the attacker would be slashed at every cycle (50% of their providers would be outliers), losing ~5.1 VLT per cycle per provider in stake alone. Over one day (3,456 cycles), an attacker running 51 sybil providers would lose ~900,000 VLT combined (stake + reputation) — far more than any price manipulation gain.

### 4.5 Reward Calibration

- Block time: 5 seconds
- 17,280 blocks/day → 3,456 cycles/day
- Budget: 6M VLT / 10 years = 1,644 VLT/day
- `REWARD_PER_CYCLE = 0.48 VLT` (47,564,687 atomic)

| Active Providers | Reward per provider/cycle | Per day | ROI on 100 VLT stake |
|------------------|---------------------------|---------|------------------------|
| 10 | 0.048 VLT | 165 VLT | <1 day |
| 25 | 0.019 VLT | 66 VLT | 1.5 days |
| 50 | 0.0095 VLT | 33 VLT | 3 days |
| 100 | 0.0048 VLT | 16 VLT | 6 days |
| 200 | 0.0024 VLT | 8 VLT | 12 days |

The system self-balances: too few providers → high ROI → attracts more; too many → low ROI → some leave.

### 4.6 Supported Feeds

At launch, only one feed is active:
- **XEL/USD** — XEL price in USD (8 decimals)

Through governance, VLT stakers can vote to add new feeds:
- **XAU/USD** — Gold price (for RWA gold tokens)
- **EUR/USD** — Euro exchange rate (for euro-denominated products)
- **BTC/USD** — Bitcoin price (for BTC-collateralized vaults)
- Any other asset with reliable external price sources

### 4.7 Sources Validation

The price provider script (`scripts/price_provider.py`) was tested against live APIs in June 2026:

| Source | Status | Latency | Notes |
|--------|--------|---------|-------|
| MEXC | ✅ OK | ~150ms | XEL listed, ~$17k daily volume |
| CoinEx | ✅ OK | ~80ms | XEL listed, ~$6k daily volume |
| CoinGecko | ✅ OK | ~270ms | Aggregator, rate-limited (30/min) |
| CoinMarketCap | ✅ OK | ~200ms | Requires API key |
| Binance | ❌ Not listed | — | XEL not yet on Binance |
| Gate.io | ❌ Not listed | — | XEL not on Gate.io |
| Kraken | ❌ Not listed | — | XEL not on Kraken |

---

## 5. Confidential Lending (VaultEngineV3)

### 5.1 Vault Positions

Each vault is a `VaultSnapshot` stored on-chain:

```silex
struct VaultSnapshot {
    owner: Address,
    collateral_asset: Hash,
    collateral_cipher: Ciphertext,   // Encrypted collateral amount
    borrow_cipher: Ciphertext,       // Encrypted debt amount
    last_update_topo: u64,
    liquidated: bool,
    created_at: u64,
    id: u64
}
```

**Privacy design**: The `collateral_cipher` and `borrow_cipher` fields store encrypted amounts using XELIS native `Ciphertext` type. The VM can decrypt internally during transaction execution (to verify health factor), but this decryption is **never persisted**. After the transaction ends, only the ciphertexts remain on-chain.

### 5.2 Homomorphic Operations

XELIS Ciphertext supports homomorphic addition and subtraction:

- **Deposit**: `vault.collateral_cipher.add(Ciphertext::encrypt(amount, owner))`
- **Borrow**: `vault.borrow_cipher.add(Ciphertext::encrypt(amount, owner))`
- **Repay**: `vault.borrow_cipher.sub(Ciphertext::encrypt(amount, owner))`
- **Withdraw**: `vault.collateral_cipher.sub(Ciphertext::encrypt(amount, owner))`

This allows updating balances without ever decrypting them on-chain.

### 5.3 Collateral Ratio

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Min Collateral Ratio | 200% (10,000 bps) | Conservative margin |
| Liquidation Penalty | 10% (1,000 bps) | Covers bad debt |
| Protocol Fee | 0.5% (50 bps) | Revenue |
| Insurance Fee | 0.1% (10 bps) | Insurance pool funding |
| Redemption Fee | 0.5% (50 bps) | Peg maintenance |
| Grace Period | 10 blocks (~50s) | Time to add collateral |

### 5.4 Health Factor

```
Health Factor = (Collateral Value / Debt Value) × 10,000

If HF >= 10,000 (1.0x): healthy
If HF < 10,000 (1.0x): liquidatable (after grace period)
```

---

## 6. VaultSwap — AMM + PSM with MEV Protection

### 6.1 Key Features

- **Constant product AMM** (x*y=k) for XEL/xUSD and VLT/XEL pools
- **Peg Stability Module** (PSM) for xUSD: mint/redeem at oracle price
- **Mandatory slippage protection**: `min_amount_out` required
- **Flash loan resistance**: max 5% of pool per swap
- **Per-pool circuit breaker**: rejects swaps that would move price >10%
- **Dynamic fees**: 0.3% normal, 1% during high volatility
- **TWAP oracle**: 30-sample rolling window for price history

### 6.2 Revenue Model

| Fee | Rate | Recipient |
|-----|------|-----------|
| Swap fee | 0.3% | 0.25% LPs, 0.05% treasury |
| PSM mint fee | 0.5% | Treasury |
| PSM redeem fee | 0.1% | Treasury |

50% of treasury's share is **burned** (deflationary).

---

## 7. Governance

### 7.1 VLT Staking

VLT holders stake their tokens in `GovernanceVault` to:
- Vote on governance proposals
- Earn staking rewards
- Boost voting power (up to 2x with timelock)

### 7.2 OracleGovernance

VLT stakers can propose and vote on:
- **AddFeed** — Add a new price feed (e.g., XAU/USD for gold)
- **UpdateFeed** — Modify an existing feed's parameters
- **RemoveFeed** — Deactivate an obsolete feed
- **SetParam** — Adjust oracle parameters (max deviation, etc.)
- **SetReward** — Change `REWARD_PER_CYCLE`
- **EmergencyCB** — Trigger circuit breaker on a feed
- **ResetFeed** — Reset a feed's state after an incident

### 7.3 Voting Parameters

- **Voting power**: 1 VLT staked = 1 vote, boosted 2x if locked >90 days
- **Quorum**: 10% of total staked (default)
- **Approval**: 60% of votes cast
- **Voting period**: 7 days
- **Timelock**: 48 hours after approval before execution

---

## 8. XelisVaultMiner — Unified Mining Layer

### 8.1 Design Principles

The original v3/v4 design had a single, narrow role for miners: submit prices to the oracle. In practice, the same miners who run a price provider are perfectly positioned to serve other protocol-level services — storing encrypted chat messages, anchoring data on-chain, and (in future versions) running an indexer or storage node.

`XelisVaultMiner.slx` formalizes this by acting as a **single registry and incentive layer** for all protocol miners:

1. **Unified registration** — a miner stakes **100 VLT** once, declares a service mask (oracle, chat, or both), and gets a single on-chain identity
2. **Cross-service reputation** — one reputation score (0–10,000) is updated by *all* services the miner participates in, making a misbehaving chat node also lose oracle rewards
3. **Dynamic rewards** — per-cycle rewards scale with reputation and with a global *budget factor* that auto-adjusts to make the 6M VLT reward pool last exactly 10 years
4. **Budget control** — every ~1 week (2016 blocks), the contract compares the actual distribution rate against the target rate and gently corrects the `budget_factor` (clamped between 0.5× and 2×)

### 8.2 Reputation System (0–10,000)

Each miner has a reputation score in the range `0`–`10,000`. New miners start at the maximum (`10,000`). The score affects both reward multiplier and active status.

**Reputation gains:**

| Action | Gain |
|--------|------|
| Valid oracle price submitted | +1 |
| Successful VaultChat anchor | +5 |
| Heartbeat (proof of life) | +1 |
| Bonus per day without infraction | +10 |

**Reputation losses:**

| Infraction | Loss | Slash |
|------------|------|-------|
| Oracle outlier price | -50 | 1% of stake |
| Node offline detected | -200 | 2% of stake |
| Chat data loss | -500 | 5% of stake |
| Chat censorship | -1,000 | 10% of stake |
| Malicious behavior | -5,000 | 50% of stake |

**Reputation tiers and multipliers:**

| Tier | Score range | Reward multiplier | Behavior |
|------|-------------|-------------------|----------|
| Excellent | 10,000 – 8,000 | 1.5× | Bonus rewards for reliable miners |
| Good | 8,000 – 5,000 | 1.0× | Normal |
| Warning | 5,000 – 2,000 | 0.5× | Reduced rewards (encourages improvement) |
| Critical | 2,000 – 1,000 | 0.25× | Heavily reduced (last chance) |
| Banned | < 1,000 | 0× | Auto-deactivated until reputation regenerates |

Reputation regenerates naturally: each heartbeat (every ~8 minutes) awards +1 point if the miner has had no infraction in the last 1,000 blocks (~83 minutes).

### 8.3 Dynamic Rewards

The reward paid for a single valid submission is computed as:

```
dynamic_reward = base_reward × reputation_mult × budget_factor
```

Where:
- `base_reward` — `BASE_REWARD_ORACLE` (0.48 VLT) for oracle service, `BASE_REWARD_CHAT` (0.5 VLT) for chat anchoring
- `reputation_mult` — 0× / 0.25× / 0.5× / 1.0× / 1.5× depending on tier
- `budget_factor` — global multiplier (in basis points, 10,000 = 1.0×) maintained by the budget control loop

If the miner's reputation is in the Banned tier (`< 1,000`), `distribute_reward()` returns 0 — no VLT is minted, regardless of submission validity. This means an attacker cannot profit from a corrupted node.

### 8.4 Budget Control (10-Year Distribution)

The reward budget is sourced from the 60% VLT allocation (6,000,000 VLT). To guarantee this lasts exactly 10 years (`TARGET_DURATION_BLOCKS = 63,072,000` blocks at 5s/block), the contract self-adjusts:

1. Every `BUDGET_ADJUST_INTERVAL` (2,016 blocks ≈ 1 week), `maybe_adjust_budget()` runs
2. It computes the **actual distribution rate** = `distributed / elapsed_blocks`
3. It computes the **target rate** = `remaining_budget / remaining_blocks`
4. It updates `budget_factor` toward the ratio `target_rate / actual_rate`, using a 50/50 blend with the previous factor to avoid shocks
5. The new factor is clamped to `[5,000; 20,000]` (i.e. 0.5× to 2.0×)

This guarantees the budget lasts the full 10 years regardless of how many miners join or leave, what their reputation is, or how much volume the network handles.

### 8.5 Service Mask

Miners declare which services they run via a bitmask (`services_mask`):

| Bit | Service ID | Service |
|-----|------------|---------|
| 0   | 1          | Oracle (price submission) |
| 1   | 2          | Chat (message storage + anchoring) |
| 2-7 | 3–8        | Reserved (storage, indexer, etc.) |

Miners can enable or disable services at any time via `enable_service()` / `disable_service()`. Per-service counters let users and the frontend find miners running a specific service.

### 8.6 Heartbeats and Slashing

- **Heartbeat** (`submit_heartbeat()`): every ~8 minutes (100 blocks), miners call this entry as a proof of life. It also triggers reputation regeneration and the budget adjustment check.
- **Slash** (`slash_miner()`): callable only by an authorized service contract (StakedOracle, VaultChat, …) — never directly by users. The service reports the offending miner, a severity (0–4), and an optional reporter address. The slash is split: 50% burned, 10% to the reporter, 40% to the treasury.

### 8.7 Relationship with StakedOracle

`StakedOracle` and `XelisVaultMiner` are complementary:

- `StakedOracle` handles the **aggregation logic** (median, deviation, circuit breaker, feeds)
- `XelisVaultMiner` handles the **miner lifecycle** (registration, reputation, budget, slashing)

In the current deployment, the StakedOracle calls `XelisVaultMiner.distribute_reward()` and `XelisVaultMiner.slash_miner()` instead of minting rewards or slashing stakes itself. This avoids duplicating the reward budget logic and gives a single source of truth for "is this miner active and reputable?".

---

## 9. MinerPool — Composable Miner Pools

### 9.1 Why Pools?

Some services (especially VaultChat storage) benefit from **mutualized availability**: if one miner goes down, others in the same pool take over. Pools also let smaller miners combine their stakes and reputation to compete with larger operators.

A `MinerPool` is a lightweight, opt-in grouping of miners that:

- Mutualizes their stake (the pool's total stake is the sum of members')
- Publishes a **pool reputation** (average of members' reputations)
- Receives rewards from `XelisVaultMiner.distribute_reward()` and distributes them proportionally to each member's stake
- Charges a configurable **creator commission** (default 5%, max 20%) to the pool creator

### 9.2 Pool Lifecycle

```
┌─────────────────────────────────────────────────┐
│ 1. CREATE POOL                                  │
│    create_pool(name, description, commission)   │
│    → must already be a registered miner         │
│    → creator automatically becomes member #1    │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ 2. JOIN POOL                                    │
│    join_pool(pool_id)                           │
│    → must be a registered miner                 │
│    → max 50 members per pool                    │
│    → one pool per miner at a time               │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ 3. EARN (passive)                               │
│    When XelisVaultMiner pays a reward to a      │
│    member, the pool receives it via             │
│    distribute_pool_rewards() and accumulates    │
│    it pending distribution                     │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ 4. CLAIM                                        │
│    claim_pool_rewards()                         │
│    → share = pending × (own_stake / total)      │
│    → commission deducted and sent to creator    │
│    → net share transferred to member            │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ 5. LEAVE (or KICK by creator)                   │
│    leave_pool() / kick_member()                 │
│    → pending share paid out on exit             │
│    → creator cannot leave (must dissolve pool)  │
└─────────────────────────────────────────────────┘
```

### 9.3 Choosing a Pool (User Perspective)

VaultChat users can elect to store their messages with a specific pool rather than with individual miners. The frontend ranks pools by:

- **Pool reputation** (mean of member reputations)
- **Total stake** (higher = stronger economic security)
- **Member count** (higher = better availability through redundancy)
- **Creator commission** (lower = more rewards to members, but creators who charge more may also run better infrastructure)

This creates a market where pool operators compete on quality of service, not just on price.

### 9.4 Reward Distribution Math

When a member submits a valid action and `XelisVaultMiner` would normally pay them `R` VLT directly, the flow is:

```
1. XelisVaultMiner.distribute_reward(member, service, valid) → R
2. If member is in pool P:
     → MinerPool.distribute_pool_rewards(P, R)
       (accumulates R in P's pending pool)
3. Member calls claim_pool_rewards():
     → share = pending × (member_stake / pool.total_stake)
     → commission = share × creator_commission_bps / 10_000
     → net = share - commission
     → transfer(net, member)
     → transfer(commission, pool.creator)
     → pending -= share
```

This means members don't need to claim every cycle — they can accumulate rewards and claim them on their own schedule.

---

## 10. VaultChat — End-to-End Encrypted Chat

### 10.1 Problem Statement

A naive on-chain chat requires either (a) one transaction per message (expensive, terrible UX) or (b) plaintext messages (no privacy). VaultChat solves both problems with a **sign-once + E2E encryption + off-chain relayers + on-chain anchoring** design.

### 10.2 Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  User A      │     │  Relayer        │     │  User B      │
│  (frontend)  │     │  (off-chain)    │     │  (frontend)  │
│              │     │                 │     │              │
│ 1. Register  │     │                 │     │ 1. Register  │
│    session   │─────┼─→ on-chain      │     │    session   │
│    (1 tx)    │     │                 │     │    (1 tx)    │
│              │     │                 │     │              │
│ 2. Encrypt   │     │                 │     │              │
│    msg with  │     │                 │     │              │
│    B's pubkey│     │                 │     │              │
│              │     │                 │     │              │
│ 3. Sign msg  │──┐  │                 │     │              │
│    locally   │  │  │                 │     │              │
│    (0 gas)   │  │  │                 │     │              │
│              │  └─→│ 4. Verify sig   │     │              │
│              │     │    Store msg    │     │              │
│              │     │    (off-chain)  │     │              │
│              │     │                 │     │              │
│              │     │ 5. Push to B    │────→│ 6. Decrypt   │
│              │     │    via WS/poll  │     │    with      │
│              │     │                 │     │    A's pubkey│
│              │     │                 │     │    + priv key│
└──────────────┘     └────────┬────────┘     └──────────────┘
                              │
                              │ 7. Every hour:
                              │    anchor merkle root
                              │    of all messages
                              ▼
                    ┌─────────────────┐
                    │  XELIS Chain    │
                    │  VaultChat.slx  │
                    │  anchor_messages│
                    │  (1 tx/hour)    │
                    └─────────────────┘
```

### 10.3 End-to-End Encryption (Diffie-Hellman)

Each user generates a long-lived X25519 keypair (or equivalent). The **private key never leaves the user's device**; the **public key** is registered on-chain via `register_session(chat_pubkey)` — a single, one-time transaction.

To send a message to B:

1. A fetches B's public key from the contract (`get_session(B)`)
2. A computes `shared_secret = DH(A_priv, B_pub)`
3. A encrypts: `ciphertext = encrypt(msg, shared_secret)`
4. A signs the ciphertext: `signature = sign(ciphertext, A_priv)`
5. A sends `(ciphertext, signature)` to a relayer (off-chain, **0 gas**)

To read a message from A:

1. B fetches A's public key from the contract
2. B computes the same `shared_secret = DH(B_priv, A_pub)`
3. B decrypts: `msg = decrypt(ciphertext, shared_secret)`

The relayer sees ciphertexts but cannot decrypt them. The contract stores **no messages** — only public keys, sessions, group metadata, and merkle roots.

### 10.4 Groups

For group chats, a **group key** is used:

1. The group creator generates a random `group_key` locally and creates the group on-chain via `create_group(group_pubkey)`
2. For each member, the creator encrypts the `group_key` with the member's public key (`add_group_member(group_id, member, encrypted_group_key)`)
3. Group messages are encrypted with the `group_key`
4. When a member leaves or is removed, the creator regenerates the `group_key` and redistributes it (forward secrecy)

### 10.5 On-Chain Anchoring

Once per hour, an authorized relayer computes a Merkle root over all messages (DMs + groups) seen in the last hour and submits it via `anchor_messages(merkle_root, count, msg_type)`. This:

- Proves **immutability** of the message log without revealing contents
- Allows clients to verify that a specific message was included in a specific anchor (Merkle proof)
- Costs only ~1 transaction per hour, regardless of message volume

### 10.6 Confidentiality Properties

- The contract stores **no messages, no ciphertexts** — only public keys, sessions, group metadata, and Merkle roots
- Relayers see ciphertexts but cannot decrypt them
- Only sender and receiver can decrypt (E2E)
- Moderation: the guardian/admin can revoke a user's session (`revoke_session(user)`) — relayers then refuse to accept messages from that user

### 10.7 Miner Integration

Miners running the Chat service (bit 2 in `XelisVaultMiner`) operate relayer nodes:

- Receive and verify signed ciphertexts from users
- Store ciphertexts off-chain (with redundancy inside a `MinerPool`)
- Compute hourly Merkle roots and call `anchor_messages()`
- Earn chat rewards via `XelisVaultMiner.distribute_reward(miner, 2, true)`

A miner that loses stored messages is reported with severity 2 (data loss) → -500 reputation + 5% stake slash. A miner that censors valid messages is reported with severity 3 (censorship) → -1,000 reputation + 10% stake slash.

---

## 11. PrivacyMixer — Anonymity Mixer

### 11.1 Principle

`PrivacyMixer.slx` is a Tornado Cash–style anonymity mixer adapted to XELIS Confidential Assets. It allows users to deposit a fixed amount of xUSD or VLT, then later withdraw the same amount to a **different address** with no on-chain link between the deposit and the withdrawal.

### 11.2 Denominations

To preserve anonymity sets, deposits must match one of three fixed denominations:

| Denomination ID | Amount (xUSD or VLT) | Atomic units |
|-----------------|----------------------|--------------|
| 0               | 10                   | 1,000,000,000 |
| 1               | 100                  | 10,000,000,000 |
| 2               | 1,000                | 100,000,000,000 |

Each denomination × asset pair forms an independent anonymity set.

### 11.3 Mechanism

**Deposit (entry `deposit(asset, denomination_id, commitment)`):**

1. User generates a random `secret` and `nonce` locally (never revealed on-chain)
2. User computes `commitment = hash(secret || nonce)`
3. User calls `deposit(asset, denom_id, commitment)` with the deposit amount of the asset
4. The contract inserts `commitment` as a new leaf in the Merkle tree at the current `leaf_index`
5. The Merkle root is updated incrementally (depth 24 → supports up to 2²⁴ ≈ 16.7M deposits per asset)

**Withdraw (entry `withdraw(asset, denom_id, nullifier, recipient, merkle_root, zk_proof)`):**

1. From a **new address** (different from the deposit address), the user generates a ZK proof showing:
   - They know a `(secret, nonce)` whose hash is some leaf in the tree
   - The Merkle root they're proving against matches the contract's current root
   - The `nullifier` they're presenting is `hash(secret)` (a unique identifier for this deposit)
2. The contract checks that the nullifier has **not** been used before (prevents double-spending)
3. The contract verifies the ZK proof via the configured verifier contract
4. The contract marks the nullifier as used and transfers the denomination amount to `recipient`

The ZK proof reveals nothing about which leaf was used — the deposit and withdrawal are cryptographically unlinkable.

### 11.4 Privacy Guarantees

- **Unlinkability**: An observer cannot connect a withdrawal to a specific deposit, even if they see all transactions
- **Double-spend protection**: Each deposit's `nullifier` can only be used once
- **Resistance to the "1-out-of-N" attack**: Larger anonymity sets (more deposits) make correlation exponentially harder
- **No relayer needed**: The withdraw transaction can be submitted from any address; the ZK proof does the authentication

### 11.5 Operational Notes

- The ZK verifier contract is configurable via `set_zk_verifier()` (Timelock-gated). This lets the protocol upgrade the proof system without redeploying the mixer
- An `emergency_withdraw()` function is reserved for the admin in case of catastrophic bug — it allows recovery of stuck funds, but does not compromise privacy
- All deposits/withdrawals are XELIS Confidential Asset transfers — meaning the **amount** is already hidden by XELIS native privacy. The mixer adds **address unlinkability** on top

### 11.6 Composability

The mixer works with any XELIS Confidential Asset registered via `asset` parameter. Initial deployment supports xUSD and VLT; community governance can whitelist additional assets in future versions.

---

## 12. Upgrade Pattern

Since Silex/XELIS does not support `delegatecall` (unlike Solidity's EIP-1967), we use a **Versioned Registry** pattern:

1. All contracts register their address in `ContractRegistry` under a logical name
2. Contracts resolve dependencies at runtime via `ContractRegistry.get("StakedOracle")`
3. To upgrade: deploy new version → propose upgrade via Timelock → execute → migrate state
4. Rollback is trivial: re-point registry to previous version

See [`docs/UPGRADE.md`](docs/UPGRADE.md) for the full upgrade procedure.

---

## 13. Security

### 13.1 Defense in Depth (10 layers)

1. **Staking** — 100 VLT minimum per provider/miner (Sybil resistance)
2. **Slashing** — 1% of stake per outlier (economic penalty)
3. **Median aggregation** — Resistant to outliers
4. **Deviation check** — Outliers get no reward
5. **Circuit breaker** — Auto-pause if price moves >20%
6. **Range check** — Prices outside [min, max] rejected per feed
7. **Anti-spam** — 1 submission per provider per feed per cycle
8. **Hard stale** — `get_price()` reverts if no update for >100 blocks
9. **Timelock** — 48h delay on all config changes
10. **Guardian multisig** — Emergency pause capability

Additionally, the unified mining layer (§8) adds:
11. **Reputation system** — misbehaving miners lose reputation and get auto-deactivated below threshold
12. **Dynamic budget factor** — auto-throttles rewards if distribution runs ahead of schedule

### 13.2 Audit Status

- **Internal audit v4.2**: Complete (see `docs/AUDIT.md`)
- **External audit**: Planned for Q3 2026 (Trail of Bits or OpenZeppelin)
- **Bug bounty**: To be launched on Immunefi before mainnet

---

## 14. Roadmap Summary

| Quarter | Milestone |
|---------|-----------|
| Q2 2026 | v4.2 architecture finalized, internal audit complete |
| Q3 2026 | Testnet deployment, external security audit, bug bounty launch |
| Q4 2026 | Mainnet launch (VLTToken + StakedOracle + VaultEngine + VaultSwap) |
| Q1 2027 | RWA tokenization, first governance vote for XAU/USD feed |
| Q2 2027 | LendingMarket, PeerLoan, SyndicatePool |
| Q3 2027 | InsurancePool, PrivateInsurance |
| Q4 2027 | Full feature set (33 contracts total) |

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for detailed timeline.

---

## 15. Conclusion

XELIS Vault v4.2 represents a fundamental advance in decentralized finance: a **fully permissionless, confidential, deflationary** financial platform. By combining XELIS's native homomorphic encryption with a staked oracle design, a unified miner reputation system, end-to-end encrypted chat, and a ZK anonymity mixer, we solve both the privacy problem and the oracle problem in a single coherent architecture — and extend privacy from "hidden balances" to "hidden conversations" and "unlinkable transfers".

The VLT token's fixed supply and deflationary burn mechanism ensure that early participants are rewarded as the protocol grows, while the permissionless provider model and the unified miner reputation system ensure long-term decentralization and censorship resistance. The 10-year budget control loop guarantees the reward pool lasts exactly as long as intended, regardless of how the network grows.

We invite the community to review the code, run a miner (oracle, chat, or both), and help build the future of confidential finance.

---

## References

- [XELIS Documentation](https://docs.xelis.io)
- [XELIS Virtual Machine (xelis-vm)](https://github.com/xelis-project/xelis-vm)
- [XELIS Blockchain](https://github.com/xelis-project/xelis-blockchain)
- [XELIS-Forge Smart Contracts](https://github.com/XELIS-Forge/smart-contracts)
- [Twisted ElGamal on Ristretto255](https://github.com/xelis-project/xelis-he)
- [Chainlink Staking v0.2](https://blog.chain.link/chainlink-staking-v0-2/) — inspiration for slashing design
- [Pyth Network Integrity Staking](https://pyth.network/) — inspiration for provider model

---

*XELIS Vault — Confidential Finance for the Privacy Era*
