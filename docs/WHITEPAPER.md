# XELIS Vault — Technical Whitepaper v3.0

> *The First Confidential Financial Platform on XELIS BlockDAG*
>
> *Confidential lending, tokenization, treasury, compliance, and markets — powered by native homomorphic encryption and a decentralized staked oracle*

**Version**: 3.0 (June 2026)
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

The v3 whitepaper introduces a **fundamental redesign of the oracle system**: instead of relying on permissioned price bots (v1/v2) or XELIS miners only (v3), the v4 architecture uses a **permissionless staked oracle** where any VLT holder can become a price provider by staking VLT as collateral. This eliminates single points of failure, aligns incentives through slashing, and creates a deflationary pressure on VLT through systematic burning.

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
│  Timelock.slx                         │
└──────────────────────────────────────┘
```

### 2.2 Contract Catalog

| Contract | Type | Purpose |
|----------|------|---------|
| `VLTToken.slx` | Token | Governance token, 10M fixed supply, deflationary via burn |
| `StakedOracle.slx` | Oracle | Permissionless price oracle with staking + slashing |
| `OracleGovernance.slx` | Governance | VLT stakers vote to add/modify feeds |
| `VaultEngineV3.slx` | Core | Overcollateralized lending with Ciphertext-encrypted positions |
| `VaultSwapV2.slx` | AMM | Constant product AMM + PSM with slippage protection |
| `ContractRegistry.slx` | Infra | Versioned registry for upgrade pattern |

---

## 3. VLT Token — Fixed Supply, Deflationary

### 3.1 Token Specifications

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
│ 1. REGISTER: stake 1,000 VLT via register_provider│
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

To manipulate the median, an attacker must control >50% of active providers. If 100 providers are active, the attacker needs 51 providers, requiring 51 × 1,000 = 51,000 VLT stake (0.5% of total supply).

Even if successful, the attacker would be slashed at every cycle (50% of their providers would be outliers), losing ~510 VLT per cycle. Over one day (3,456 cycles), they would lose ~1.76M VLT — far more than their initial stake.

### 4.5 Reward Calibration

- Block time: 5 seconds
- 17,280 blocks/day → 3,456 cycles/day
- Budget: 6M VLT / 10 years = 1,644 VLT/day
- `REWARD_PER_CYCLE = 0.48 VLT` (47,564,687 atomic)

| Active Providers | Reward per provider/cycle | Per day | ROI on 1,000 VLT stake |
|------------------|---------------------------|---------|-------------------------|
| 10 | 0.048 VLT | 165 VLT | 6 days |
| 25 | 0.019 VLT | 66 VLT | 15 days |
| 50 | 0.0095 VLT | 33 VLT | 30 days |
| 100 | 0.0048 VLT | 16 VLT | 61 days |
| 200 | 0.0024 VLT | 8 VLT | 122 days |

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

## 8. Upgrade Pattern

Since Silex/XELIS does not support `delegatecall` (unlike Solidity's EIP-1967), we use a **Versioned Registry** pattern:

1. All contracts register their address in `ContractRegistry` under a logical name
2. Contracts resolve dependencies at runtime via `ContractRegistry.get("StakedOracle")`
3. To upgrade: deploy new version → propose upgrade via Timelock → execute → migrate state
4. Rollback is trivial: re-point registry to previous version

See [`docs/UPGRADE.md`](docs/UPGRADE.md) for the full upgrade procedure.

---

## 9. Security

### 9.1 Defense in Depth (10 layers)

1. **Staking** — 1,000 VLT minimum per provider (Sybil resistance)
2. **Slashing** — 1% of stake per outlier (economic penalty)
3. **Median aggregation** — Resistant to outliers
4. **Deviation check** — Outliers get no reward
5. **Circuit breaker** — Auto-pause if price moves >20%
6. **Range check** — Prices outside [min, max] rejected per feed
7. **Anti-spam** — 1 submission per provider per feed per cycle
8. **Hard stale** — `get_price()` reverts if no update for >100 blocks
9. **Timelock** — 48h delay on all config changes
10. **Guardian multisig** — Emergency pause capability

### 9.2 Audit Status

- **Internal audit v4.2**: Complete (see `docs/AUDIT.md`)
- **External audit**: Planned for Q3 2026 (Trail of Bits or OpenZeppelin)
- **Bug bounty**: To be launched on Immunefi before mainnet

---

## 10. Roadmap Summary

| Quarter | Milestone |
|---------|-----------|
| Q2 2026 | v4.2 architecture finalized, internal audit complete |
| Q3 2026 | Testnet deployment, external security audit, bug bounty launch |
| Q4 2026 | Mainnet launch (VLTToken + StakedOracle + VaultEngine + VaultSwap) |
| Q1 2027 | RWA tokenization, first governance vote for XAU/USD feed |
| Q2 2027 | LendingMarket, PeerLoan, SyndicatePool |
| Q3 2027 | InsurancePool, PrivateInsurance |
| Q4 2027 | Full feature set (23 contracts total) |

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for detailed timeline.

---

## 11. Conclusion

XELIS Vault v4.2 represents a fundamental advance in decentralized finance: a **fully permissionless, confidential, deflationary** financial platform. By combining XELIS's native homomorphic encryption with a staked oracle design, we solve both the privacy problem and the oracle problem in a single coherent architecture.

The VLT token's fixed supply and deflationary burn mechanism ensure that early participants are rewarded as the protocol grows, while the permissionless provider model ensures long-term decentralization and censorship resistance.

We invite the community to review the code, run a price provider, and help build the future of confidential finance.

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
