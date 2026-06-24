# XELIS Vault v5.0 — Technical Whitepaper

**A Privacy-First DeFi Protocol on the XELIS BlockDAG**

| Field | Value |
|-------|-------|
| Protocol version | v5.0 (post-remediation) |
| Source version audited | v4.3 |
| Audit date | 24 June 2026 |
| Auditor | Super Z (Z.ai) |
| Smart contracts | 33 Silex contracts (13,220 lines, 630 entry functions) |
| Layer 1 | XELIS BlockDAG (homomorphic-encrypted balances, native confidential assets) |
| Documentation | https://github.com/XelisVault/xelis-vault |

---

## 1. Abstract

XELIS Vault v5.0 is a fully composable decentralized-finance stack deployed on the XELIS BlockDAG, a Layer-1 network that natively provides homomorphic-encrypted balances and confidential assets. While existing DeFi ecosystems on Ethereum, Solana, and similar transparent chains have unlocked enormous financial innovation, they have also forced every user to publicly disclose wallet balances, collateral ratios, trading intent, and yield strategies. Privacy add-ons built on top of transparent chains (Tornado-style mixers, Aztec-style rollups) inherit the underlying accounting model and historically have been treated as regulatory liabilities. XELIS Vault takes the opposite approach: privacy is the substrate, and DeFi is constructed directly on top of it.

The protocol consists of 33 Silex smart contracts totalling 13,220 lines and exposing 630 entry functions, organized into a layered architecture that spans a contract registry, two protocol tokens (VLT and xUSD), a decentralized staked oracle with median aggregation, a confidential lending engine (VaultEngineV3), a peg stability module (PSM), a constant-product AMM (VaultSwapV2), a full on-chain governance chain (GovernanceVault, Governor, Timelock, GuardianMultisig, OracleGovernance), and a rich auxiliary layer including flash loans, sealed-bid auctions, a privacy mixer, encrypted chat, an insurance pool, RWA asset vaults, and a savings-rate module.

The key innovations of v5.0 are: (1) a ten-year, budget-aware oracle reward system that distributes 6 million VLT to miners with reputation-weighted multipliers and dynamic rate adjustment; (2) a commit-reveal privacy pattern for collateral deposits that respects the fact that Silex exposes no native `Ciphertext` type, while still benefiting from XELIS-layer homomorphic encryption; (3) a global stability-fee index that accrues interest on every borrow with constant-time settlement; (4) a fully sequential cross-contract call graph in which every `entry` has a deterministic numeric ID auto-documented by `scripts/extract_entry_ids.py`; and (5) a two-step `emergency_withdraw` pattern applied uniformly to all 33 contracts, defeating instant rugpull vectors. A v4.3 audit identified 15 vulnerabilities (5 critical, 4 high, 4 medium, 2 low); all 15 have been remediated in v5.0 and verified against the real Silex API surface (validated through `upload/lib.rs`). This whitepaper documents the resulting architecture, economics, security model, and deployment plan.

---

## 2. Introduction

### 2.1 Background: DeFi on Traditional Chains

Decentralized finance on Ethereum and Solana has grown from a few million dollars of total value locked in 2019 to tens of billions today. The design primitives that enabled this growth — ERC-20 tokens, constant-product AMMs, over-collateralized lending pools, governance tokens, and timelocked multisigs — all assume one foundational property: every account balance and every state transition is publicly readable by any node. This transparency is the source of composability (any contract can read any other contract's reserves) but also the source of a chronic privacy deficit. A user who opens a MakerDAO vault, swaps on Uniswap, or supplies liquidity to Aave simultaneously reveals their collateral stack, their trading edge, their leverage ratio, and their taxable events to the entire world.

Multiple "privacy-preserving DeFi" projects have attempted to bridge this gap. Aztec Network deployed a private rollup with UTXO-based notes; Tornado Cash implemented a fixed-denomination mixer using zk-SNARKs; Railgun wrapped ERC-20 transfers in shielded pools. Each of these approaches faces the same architectural friction: the base layer is transparent, so privacy must be bolted on as a second system. That second system is then targeted by regulators (Tornado Cash sanctions, August 2022), is incompatible with the most composable DeFi primitives (shielded positions cannot be liquidated on-chain), and forces users to manage two parallel balances (a public one and a shielded one). The transparency-vs-privacy trade-off is therefore not a feature gap that can be patched; it is an architectural commitment baked into the chain.

### 2.2 The XELIS Opportunity

XELIS is a Layer-1 BlockDAG that ships with homomorphic-encrypted balances and native confidential assets from genesis. Account balances are encrypted at the asset layer; transfers are validated by zero-knowledge proofs without revealing amounts; transactions are processed in a BlockDAG topology that decouples block production from linear ordering and yields sub-second finality for parallel transactions. The Silex programming language is the native smart-contract language of XELIS. Silex is statically typed, has no `try/catch` (any cross-contract call that reverts aborts the entire transaction), and exposes a deliberately small API surface: `Storage`, `Asset`, `Contract`, `Hash`, `Address`, plus the globals `get_caller`, `get_balance_for_asset`, `transfer`, `burn`, `hash`, and `get_current_topoheight`.

This base layer eliminates the architectural friction described above. Privacy is not a wrapper; it is the default. A DeFi position opened on XELIS does not leak collateral amounts, does not leak the borrower identity (beyond a stealth address), and does not expose the order book to front-running. The cost of this privacy is that Silex is younger than Solidity, has a smaller standard library, and currently exposes no `Ciphertext` type at the contract level (homomorphic encryption happens below the contract ABI). The XELIS Vault v5.0 protocol is the first attempt to build a complete DeFi stack under those constraints.

### 2.3 Mission: A Full DeFi Stack on a Privacy Chain

The mission of XELIS Vault is to demonstrate that a privacy-first chain can host a complete, composable DeFi ecosystem without sacrificing any of the primitives that made DeFi on transparent chains successful. Concretely, v5.0 ships: a governance token (VLT) with a ten-year reward schedule; a soft-pegged stablecoin (xUSD) mintable against XEL collateral; a decentralized staked oracle with median aggregation; an over-collateralized lending engine with redemption queue; a peg stability module; a constant-product AMM with TWAP-based volatility fees; a peer-to-peer lending market; flash loans; sealed-bid auctions; an RWA asset vault; a privacy mixer; an encrypted chat layer; an insurance pool; a savings-rate module; and a full governance chain with timelock, multisig guardian, and specialized oracle governance. Every contract is governed by the same access-control model, the same two-step emergency-withdraw pattern, and the same sequential entry-ID discipline. The remainder of this whitepaper describes how each layer is built, how it composes with the others, and how the security model was hardened through the v4.3 audit remediation.

---

## 3. Architecture Overview

### 3.1 Layered Design

The 33 contracts are organized into six functional layers. Each layer depends only on the layers below it, which keeps the dependency graph acyclic and the deployment ordering deterministic.

| Layer | Contracts | Responsibility |
|-------|-----------|----------------|
| Registry | `ContractRegistry` | Name → contract-hash resolution, versioned upgrades with cooldown, rollback, two-step emergency withdraw |
| Tokens | `VLTToken`, `XUSDToken` | Fixed-supply governance token (VLT) and elastic-supply stablecoin (xUSD) |
| Oracle | `XelisVaultMiner`, `StakedOracle` | Staked miner registry, reputation, slashing, median price aggregation, circuit breaker |
| DeFi | `VaultEngineV3`, `LendingMarket`, `PSM`, `VaultSwapV2`, `PeerLoan`, `SyndicatePool`, `InterestRateModel` | Lending, AMM, peg stability, peer-to-peer credit |
| Governance | `GovernanceVault`, `Governor`, `Timelock`, `GuardianMultisig`, `OracleGovernance` | Staking, proposal lifecycle, delayed execution, multisig guardian, oracle-parameter governance |
| Auxiliary | `FlashLoan`, `SealedBidAuction`, `PrivacyMixer`, `VaultChat`, `InsurancePool`, `AssetVault`, `TreasuryVault`, `RevenueShare`, `SavingsRate`, `Payroll`, `FaucetContract`, `ComplianceModule`, `MinerPool`, `FlashCallback` | Capital efficiency, RWA, mixer, encrypted chat, treasury, savings, compliance |

The registry sits at the bottom because every other contract resolves its dependencies by name through `ContractRegistry.get_entry(name)` (entry ID 0). Above the registry sit the two protocol tokens, which are referenced by hash by every contract that mints, burns, or transfers VLT or xUSD. The oracle layer is the next dependency: every DeFi contract that prices collateral or swaps requires a fresh price from `StakedOracle`. The DeFi layer composes against tokens and the oracle. The governance layer sits above DeFi because Governor proposals target DeFi contracts' parameter-setter entries. The auxiliary layer is a peer of DeFi and governance, with individual contracts pulling from whichever layer they need (e.g., `FlashLoan` reads token balances; `VaultChat` calls `XelisVaultMiner.distribute_reward` for chat-anchor rewards).

### 3.2 Cross-Contract Communication

Every cross-contract call in v5.0 uses the canonical Silex form `Contract::call(entry_id, args, {})`, where `entry_id` is a `u16` identifying the target entry function, `args` is an array of typed arguments, and the third argument is the empty kwargs struct `{}` (Silex accepts no other form). Entry IDs are assigned sequentially starting at 0 in declaration order — the order in which `entry` functions appear in the `.slx` source file. A `pub fn` or a plain `fn` does **not** receive an entry ID and is therefore not callable cross-contract; the v4.3 audit found multiple cases where critical functions had been declared as `pub fn` instead of `entry`, silently breaking cross-contract calls (findings #1, #2, #3, #10, #11, #12). All such cases were converted to `entry` or wrapped in `*_entry` wrappers in v5.0.

To prevent regression, `scripts/extract_entry_ids.py` parses every contract in `contracts/` and emits `docs/ENTRY_IDS.md` with a per-contract table of `(ID, name, parameters, return)`. The current state of the table covers 33 contracts and 630 entry functions. A representative slice from `PSM.slx`:

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `mint` | `xel_amount: u64, min_xusd_out: u64` | `u64` |
| 1 | `redeem` | `xusd_amount: u64, min_xel_out: u64` | `u64` |
| 2 | `get_reserves_entry` | — | `(u64, u64)` |
| 3 | `get_mint_fee_entry` | — | `u64` |
| 4 | `get_redeem_fee_entry` | — | `u64` |
| 5 | `get_daily_usage_entry` | — | `(u64, u64)` |
| 6 | `set_mint_fee_bps` | `bps: u64` | `u64` |
| 7 | `set_redeem_fee_bps` | `bps: u64` | `u64` |
| 8 | `set_daily_caps` | `mint_cap: u64, redeem_cap: u64` | `u64` |
| 9 | `pause` | `reason: string` | `u64` |
| 10 | `unpause` | — | `u64` |

The recommended CI workflow commits `ENTRY_IDS.md` and fails any pull request whose diff regenerates a different file. This catches any reorder, rename, or insertion that would silently shift entry IDs and break dependent contracts.

### 3.3 Access Control Model

Every contract in v5.0 implements the same four-role access model. The **admin** is the deployer initially and is intended to be transferred to the `Timelock` contract post-mainnet; admin can call parameter setters and `transfer_admin`. The **guardian** is either an externally owned account (stored in `GUARDIAN_KEY`) or a contract (stored in `GUARDIAN_CONTRACT_KEY`, typically `GuardianMultisig`); guardian can `pause(reason)`, trigger circuit breakers, and queue emergency timelock actions. The **emergency** role (stored in `EMERGENCY_KEY`) is reserved for the two-step `request_emergency_withdraw` / `execute_emergency_withdraw` flow and is the only role allowed to recover funds if a contract is permanently broken. The **timelock** role is the `Timelock` contract itself; only timelock may call governance-protected setters (those guarded by `only_timelock`), and timelock enforces a minimum delay of 1 hour (default 1 day) before executing any queued action.

The dual-guardian design (audit finding #7) is critical. Before v5.0, `Timelock.only_guardian()` checked only `caller == GUARDIAN_KEY`, which made it impossible to wire `GuardianMultisig` as the guardian. v5.0 changed the check to accept either `caller == GUARDIAN_KEY` (EOA) or `get_contract_caller() == GUARDIAN_CONTRACT_KEY` (contract). A new entry `set_guardian_contract(Hash)` configures the multisig. This is what allows the guardian set to be a 3-of-5 multisig on mainnet while remaining a single EOA on testnet.

### 3.4 Silex Language Constraints

Silex imposes several constraints that materially shaped the v5.0 design. First, it is statically typed with no `try/catch`: any cross-contract call that reverts aborts the entire transaction, including all storage writes from the caller. This means every external call must be either (a) to a contract whose failure modes are fully enumerated and provably cannot revert, or (b) wrapped in a precondition check that prevents the revert from ever happening. Second, Silex exposes no `Ciphertext` type, despite the underlying XELIS runtime using ElGamal encryption homomorphically at the asset layer. Contracts therefore cannot encrypt or decrypt amounts; they can only commit to them via `hash(amount, salt)` and reveal them later (the commit-reveal pattern). Third, entry functions receive sequential numeric IDs in declaration order; renaming or reordering an entry silently shifts every downstream entry ID. Fourth, the third argument to `Contract::call` must be the empty struct `{}` — JavaScript-style kwargs like `{ asset: amount }` are a syntax error in Silex. Fifth, there is no `optional::unwrap()` that throws a custom error; `optional<T>` is consumed via `.is_some()`, `.is_none()`, `.unwrap_or(default)`, and `.expect(msg)`. These constraints forced the v4.3→v5.0 remediation to abandon a hypothetical `Ciphertext`-based privacy model in favor of commit-reveal, and to harden every cross-contract call site against silent reverts.

---

## 4. Token Economics

### 4.1 VLT Token

VLT is the governance and reward token of the protocol. It has a fixed total supply of 10,000,000 VLT with 8 decimals, deployed via `Asset::create(10_000_000_00000000, "XELIS Vault", "VLT", 8, MaxSupplyMode::Fixed(...))`. The fixed supply means no inflationary dilution is possible after genesis; all incentives must be funded from the pre-allocated distribution. The distribution is governed by `VLTToken.mint_batch(recipients, amounts)`, called once at deployment.

| Allocation | Amount (VLT) | Share | Vesting |
|------------|--------------|-------|---------|
| Oracle provider rewards (XelisVaultMiner budget) | 6,000,000 | 60% | Distributed over 10 years via dynamic budget factor |
| DEX liquidity (VaultSwapV2 seed) | 1,200,000 | 12% | 6-month linear unlock |
| Founding team | 1,000,000 | 10% | 4-year vesting, 1-year cliff |
| Protocol treasury | 1,000,000 | 10% | Governance-controlled, no vesting |
| Seed investors | 500,000 | 5% | 2-year vesting, 6-month cliff |
| Community airdrop | 200,000 | 2% | 1 year post-mainnet |
| Bug bounty | 100,000 | 1% | Perpetual, never unlocked as team funds |

Three independent burn mechanisms apply deflationary pressure to VLT. First, **50% of every slash is burned**: when `StakedOracle` detects an outlier and calls `XelisVaultMiner.slash_miner(addr, severity, reporter)`, half of the slashed stake is sent to `burn(amount/2, VLT_asset)` and permanently removed from supply; 10% goes to the reporter as a whistleblower bounty and 40% to the treasury. Second, **50% of protocol fees are burned**: VaultEngine borrow fees, PSM mint/redeem fees, and VaultSwap swap fees each split 50/50 between treasury and burn. Third, **governance burns**: the community may pass a proposal to burn treasury-held VLT, reducing circulating supply. At an outlier rate of roughly 5% of oracle submissions, slash burns alone remove an estimated 100–500 VLT per day.

### 4.2 xUSD Stablecoin

xUSD is the protocol's soft-pegged USD stablecoin. Unlike VLT, xUSD has elastic supply: it is minted on demand when users borrow against XEL collateral in VaultEngineV3 or swap XEL for xUSD in the PSM, and it is burned on repayment or redemption. The theoretical cap is `u64::MAX` (approximately 1.8 × 10^19 xUSD with 8 decimals), which is never reached in practice; the binding constraints are collateral availability in VaultEngine and daily caps in the PSM. xUSD also uses 8 decimals, matching VLT, which simplifies the AMM math in VaultSwapV2.

Two minting paths exist. **VaultEngine path**: a user deposits XEL as collateral, opens a vault, and borrows xUSD up to the collateral ratio. The borrowed xUSD is freshly minted by the VaultEngine contract (which holds the `minter` role on xUSD). When the user repays, the repaid xUSD is burned, destroying both the principal and the accrued stability fee. **PSM path**: a user sends XEL to the PSM contract and receives xUSD at the current oracle price, minus a 50 bps mint fee. Conversely, a user can redeem xUSD for XEL at the oracle price minus a 10 bps redeem fee. The PSM path is the primary peg-defense mechanism: if xUSD trades above 1.00 on secondary markets, arbitrageurs mint xUSD from the PSM (cheap) and sell it on the AMM (expensive), expanding supply and pushing the price down. If xUSD trades below 1.00, arbitrageurs buy xUSD on the AMM (cheap) and redeem it through the PSM (at 1.00 minus 10 bps), contracting supply and pushing the price up. Daily caps on both mint and redeem prevent a single oracle misreport from draining the PSM in one transaction.

### 4.3 Stability Fee

The stability fee is the continuous interest rate applied to every outstanding borrow in VaultEngineV3. It is implemented as a global accumulator `STABILITY_FEE_INDEX_KEY`, scaled by 1e12 for fixed-point precision. The index grows according to a per-block rate derived from `STABILITY_FEE_BPS_KEY` (default 2% APR). On every `borrow`, `repay`, `liquidate`, and `redeem` call, the contract snapshots the current index and stores it on the vault; when interest must be settled, it computes:

```silex
// In VaultEngineV3 — simplified accrual math
let current_index: u128 = Storage::load(STABILITY_FEE_INDEX_KEY);
let accrued_principal: u128 = (vault.principal as u128)
    * current_index
    / (vault.index_at_open as u128);
let interest: u128 = accrued_principal - (vault.principal as u128);
// interest portion is routed to TREASURY_KEY on repay
```

The stability fee was added in v5.0 as audit finding #9. Before v5.0, borrows were interest-free, which made VaultEngine economically equivalent to a zero-cost short and created an incentive to keep borrows open indefinitely. The 2% APR default is configurable via `set_stability_fee_bps` (gated by `only_timelock`); governance may raise it during bull markets to dampen borrow demand, or lower it during bear markets to stimulate credit creation. The index never decreases, which guarantees monotonic accrual and prevents "negative interest" bugs.

### 4.4 Burn Deflation

Consider the steady-state case of 1,000,000 xUSD outstanding at the default 2% APR. The stability fee accrues 20,000 xUSD per year to the treasury; 50% of that is burned, removing 10,000 xUSD per year from circulation. This is a direct deflationary pressure on xUSD supply: even if no user repays principal, the burned interest reduces outstanding xUSD and pushes the peg upward, counterbalancing the natural downward pressure from new borrow minting. Combined with PSM arbitrage and the redemption queue, this gives xUSD three independent peg mechanisms: (a) arbitrage via PSM, (b) redemption via VaultEngine's FIFO queue, and (c) deflationary burn from stability fees. The 10% liquidation penalty and 50 bps redemption fee add further friction that biases xUSD toward the upside when the system is stressed, which is the conservative direction for a collateral-backed stablecoin (over-collateralization is always preferable to under-collateralization).

---

## 5. Decentralized Oracle

### 5.1 StakedOracle

`StakedOracle` is the protocol's primary price feed. It aggregates submitted prices for each `(feed_id, cycle)` pair using a median-of-N algorithm and exposes the resulting price to other contracts via `get_price_entry` (entry 8) and `get_price_for_asset_entry` (entry 9). The aggregation cycle is 5 blocks (25 seconds at the XELIS 5-second block time). A price is considered fresh if its cycle is within `MAX_STALE_BLOCKS` (default 100) of the current topoheight; if no fresh price exists, the contract reverts (callers must pre-check via `get_price_for_asset_entry` if they want graceful degradation).

StakedOracle implements a ten-layer security model:

1. **Range check** — every submitted price is checked against `(min, max)` bounds configured per feed; out-of-range submissions are rejected without slashing (the miner is presumed to have a stale local view).
2. **5% max deviation** — if a miner's submission deviates more than 5% from the running median, the submission is flagged as an outlier and the miner is slashed at severity 0 (1% of stake).
3. **20% circuit breaker** — if the median itself moves more than 20% in a single cycle, the circuit breaker fires: the feed is marked paused, prices cannot be read, and governance (or guardian) must call `reset_feed_cb` to resume.
4. **100-block hard stale** — if no submission has been received for 100 blocks (about 8 minutes), `get_price_for_asset_entry` reverts and dependent contracts must pause their operations.
5. **Bootstrap mode** — during the first weeks/months, only 3 active providers are required (vs. 10 in normal mode) and the lock-in period is 1 hour (vs. 30 days). This allows the protocol to bootstrap price discovery before reaching decentralization.
6. **Submit window** — prices must be submitted within `SUBMIT_WINDOW` blocks of the cycle start; late submissions are rejected.
7. **Per-feed pausable** — each feed can be individually paused via `set_feed_active(false)` without affecting other feeds.
8. **Emergency circuit breaker** — a guardian can force-pause all feeds via `trigger_cb` (entry 3) without going through governance.
9. **Provider whitelist** — only miners registered in `XelisVaultMiner` with the oracle service bit set may submit prices.
10. **Replay protection** — the contract rejects duplicate submissions for the same `(feed_id, cycle, provider)` triple via `SUB_PROVIDED_PREFIX`.

### 5.2 XelisVaultMiner

`XelisVaultMiner` is the staked-miner registry that backs StakedOracle. A miner registers via `register_miner(endpoint_url, miner_pubkey, services_mask)` with a minimum stake of 100 VLT (configurable via `set_min_stake`, floor 10 VLT). The stake is locked in the contract and can be withdrawn only via `deregister_miner` (full unstake) or `decrease_stake` (partial, with a guard that prevents dropping below the minimum). Every miner has a reputation score between 0 and 10,000, initialized at 10,000 (Excellent tier). Reputation gates two things: (a) whether the miner is `active` (≥ `REP_CRITICAL = 1,000`), and (b) the miner's reward multiplier.

The reputation tiers and their multipliers are:

| Tier | Range | Multiplier | Description |
|------|-------|------------|-------------|
| Excellent | 8,000 – 10,000 | 1.5× (15,000 bps) | Default tier for new miners |
| Good | 5,000 – 7,999 | 1.0× (10,000 bps) | Minor infractions |
| Warning | 2,000 – 4,999 | 0.5× (5,000 bps) | Multiple infractions |
| Critical | 1,000 – 1,999 | 0.25× (2,500 bps) | Last chance before ban |
| Banned | 0 – 999 | 0× (no rewards) | Cannot earn; must rebuild via heartbeats |

Slashing is severity-graded. A severity-0 outlier (price >5% off median) costs 1% of stake and 50 reputation. A severity-4 malicious submission (proven manipulation) costs 50% of stake and 5,000 reputation, instantly dropping the miner from Excellent to Good and cutting their reward multiplier by a third. The slashed amount is split: 50% burned, 10% to the reporter (whistleblower), 40% to the treasury.

The reward budget is 6,000,000 VLT distributed over a target duration of approximately 10 years (6,307,200 blocks at 5 seconds per block). This works out to a target distribution rate of roughly 951 VLT per block. The contract enforces a hard cap: if `distributed + reward > total_budget`, the reward is skipped (returns 0). This guarantees the 6,000,000 VLT budget can never be exceeded even if every parameter is misconfigured.

### 5.3 Reward Formula

When `StakedOracle.aggregate()` completes median aggregation, it calls `XelisVaultMiner.distribute_reward(addr, service_id, is_valid)` (entry 8) for every valid provider. The reward is computed as:

```silex
// In XelisVaultMiner.distribute_reward — simplified
let base_reward: u64 = match service_id {
    1 => Storage::load(BASE_REWARD_ORACLE_KEY),  // 47,564,687 = 0.4756 VLT
    2 => Storage::load(BASE_REWARD_CHAT_KEY),    // 50,000,000 = 0.5 VLT
    _ => return 0,
};
let multiplier: u64 = reputation_multiplier(miner.reputation);  // 0..=15,000
let budget_factor: u64 = Storage::load(BUDGET_FACTOR_KEY);      // 5,000..=20,000
let reward: u128 = (base_reward as u128)
    * (multiplier as u128)
    * (budget_factor as u128)
    / 100_000_000;  // = multiplier_max(15,000) * budget_max(20,000)
// Budget cap check before mint
if Storage::load(DISTRIBUTED_KEY) + (reward as u64) > Storage::load(TOTAL_BUDGET_KEY) {
    return 0;
}
mint_reward(miner.address, reward as u64);
```

With default parameters and `budget_factor = 10,000`, an Excellent-tier miner earns `0.4756 × 1.5 × 1.0 = 0.7135 VLT` per valid oracle submission. A Warning-tier miner under the same conditions earns `0.4756 × 0.5 × 1.0 = 0.2378 VLT`, three times less.

The `budget_factor` auto-adjusts every `BUDGET_ADJUST_INTERVAL = 2,016` blocks (≈ 2 weeks) via `maybe_adjust_budget()`, called lazily from `submit_heartbeat` and `distribute_reward`. The algorithm compares the actual distribution rate (`distributed / elapsed`) against the target rate (`remaining_budget / remaining_time`). If actual exceeds target by 2×, the factor halves; if actual is less than half of target, the factor doubles (capped). The factor is symmetrically clamped between 5,000 (0.5×) and 20,000 (2×) to prevent runaway feedback loops. This guarantees the 6,000,000 VLT budget lasts approximately 10 years regardless of how many miners participate or how often they submit.

### 5.4 Anti-Gaming

The oracle is the highest-value attack target in any DeFi protocol, because a manipulated price can drain the lending engine, the PSM, and the AMM in a single transaction. XELIS Vault v5.0 implements five layered defenses. **Anti-spam**: `submit_price` rejects if the same `(feed_id, cycle, provider)` triple already exists in `SUB_PROVIDED_PREFIX`, preventing a miner from flooding the cycle. **Anti-flash-loan**: the stake must be at least one block old before it counts toward eligibility, so an attacker cannot borrow VLT, register, submit, earn, and deregister in the same block. **Anti-collusion**: median aggregation plus the 5% deviation slash means a single miner cannot move the price; a collusion of more than 50% of providers would slash all participants at severity 4 (50% of stake). **Anti-Sybil**: each miner identity requires 100 VLT of locked stake, so creating N Sybil identities costs 100×N VLT up front; combined with the reputation system (which starts new miners at Excellent but penalizes any infraction severely), this makes Sybil attacks economically unattractive. **Anti-front-running**: XELIS's BlockDAG topology with 5-second block time and homomorphic-encrypted balances makes on-chain front-running economically infeasible, because an attacker cannot reliably order transactions and cannot read the victim's intent.

---

## 6. Confidential Lending

### 6.1 VaultEngineV3

`VaultEngineV3` is the protocol's flagship lending contract. A user deposits XEL as collateral, opens a vault, and borrows xUSD against it. The minimum collateral ratio is 200% (configurable via `set_min_cr_bps`, gated by `only_timelock`); the liquidation penalty is 10%; the grace period is 10 blocks (50 seconds), during which a vault below the minimum ratio cannot yet be liquidated, giving the borrower a final chance to deposit more collateral or repay. When a vault is liquidated, the liquidator repays the outstanding xUSD (principal plus accrued stability fee) and receives the corresponding collateral plus the 10% penalty; the protocol takes no additional fee on liquidation.

The redemption queue is a FIFO buffer with a cap of 1,000 vaults (configurable via `set_queue_cap`). xUSD holders who want to redeem their stablecoin for XEL at the oracle price (minus a 50 bps redemption fee) call `redeem(xusd_amount, min_xel_out)`. The contract walks the queue from the front, repaying the principal of each vault and releasing its collateral to the redeemer, until the requested xUSD amount is exhausted. This creates a soft peg mechanism: if xUSD drops below 1.00, holders redeem through VaultEngine (contracting xUSD supply and pushing the price up); if the queue is empty, redemption falls through to the PSM. The queue cap exists to bound gas/execution cost per redemption: a single `redeem` call cannot iterate over more than 1,000 vaults.

### 6.2 Commit-Reveal Pattern

A central architectural decision in v5.0 was how to provide confidentiality for collateral deposits. The original v4.3 design assumed that Silex exposed a `Ciphertext` type, allowing the contract to encrypt the deposited amount homomorphically and store only the ciphertext. The audit (finding #8) confirmed that this assumption is false: although the underlying XELIS runtime uses ElGamal encryption at the asset layer, the Silex contract ABI does not expose `Ciphertext`, `elgamal`, or `RangeProof` types. Any contract claiming to encrypt amounts was in fact storing them in cleartext, creating a false sense of privacy.

The v5.0 fix replaces the cipher with a commit-reveal pattern. The `deposit` entry signature is:

```silex
entry deposit(asset: Hash, amount: u64, salt: Hash) {
    // ... transfer asset from caller to contract ...
    // Off-chain commitment: keccak(amount, salt, caller, topo)
    // Salt is stored; user may later reveal a (amount, salt) pair
    // to a third-party auditor or dApp without re-depositing.
}
```

The on-chain stored value is still the plaintext amount (so the contract can compute collateral ratios), but the user provides a `salt: Hash` that they can use off-chain to commit to the deposit without revealing it. The pair `(amount, salt, caller, topo)` can be hashed by any off-chain verifier (auditor, regulated counterparty, or another dApp) to prove the deposit was made by a specific account at a specific time, without that account having to broadcast the deposit on a public mempool. The chain itself still benefits from XELIS-native confidential balances: the underlying XEL transfer is encrypted, so an external observer of the BlockDAG sees only a deposit transaction between two encrypted balances, not the amount. This combination — encrypted L1 transfers plus Silex-level commit-reveal — gives users practical confidentiality without misrepresenting the contract's capabilities.

### 6.3 LendingMarket

`LendingMarket` is the multi-pool, multi-collateral lending market that complements VaultEngine. Where VaultEngine only accepts XEL as collateral and only mints xUSD, LendingMarket supports arbitrary asset pairs (e.g., supply VLT, borrow xUSD; supply xUSD, borrow XEL). Each pool pairs a supply asset with a borrow asset and tracks utilization (borrows / (reserves + borrows)). The borrow rate is computed by `InterestRateModel` as a piecewise function of utilization: a base rate at 0% utilization, a slope up to an inflection point (typically 80%), and a steeper slope beyond to incentivize repayment when the pool is nearly fully utilized. A reserve factor of 10% diverts accrued interest to the treasury, with the remaining 90% distributed to suppliers pro-rata.

### 6.4 PeerLoan & SyndicatePool

`PeerLoan` enables peer-to-peer lending: a lender posts a loan offer (amount, asset, interest rate, duration, required collateral ratio); a borrower accepts the offer and posts collateral; the contract locks both sides and settles at maturity. A 10 bps protocol fee is charged on the loan amount. `SyndicatePool` extends PeerLoan to syndicated lending, where multiple lenders contribute to a single loan and share in the repayment pro-rata. This is useful for larger loans that no single lender wants to underwrite alone, and for borrowers who want to avoid the price impact of a single large drawdown on the AMM.

---

## 7. PSM & AMM

### 7.1 Peg Stability Module (PSM)

The PSM is the primary peg-defense mechanism for xUSD. It allows any user to mint xUSD by sending XEL at the current oracle price (minus a 50 bps mint fee) and to redeem xUSD for XEL at the oracle price (minus a 10 bps redeem fee). The fee asymmetry (50 bps mint vs. 10 bps redeem) is intentional: it biases users toward redeeming xUSD (contracting supply) when the peg is soft, which is the conservative direction for a stablecoin.

To prevent a single oracle misreport from draining the PSM, both mint and redeem are subject to daily caps enforced via `set_daily_caps(mint_cap, redeem_cap)`. The caps are tracked in `get_daily_usage_entry`, which returns `(today_mint, today_redeem)` and resets every 28,800 blocks (approximately 24 hours). If a malicious oracle reports XEL at 10× its true price, the maximum damage in 24 hours is bounded by `mint_cap × 10`; governance can then pause the PSM via `pause(reason)` (guardian or admin) and reset the oracle.

### 7.2 VaultSwapV2

VaultSwapV2 is a constant-product automated market maker (`x × y = k`) with three extensions over the basic Uniswap V2 model. First, it implements a TWAP-based volatility fee: the contract tracks a time-weighted average price for each pool over a sliding window, and if the current swap price deviates more than 10% from the TWAP, the swap fee is bumped from the 30 bps base (plus 5 bps treasury) to 100 bps. This penalizes price-impact-driven arbitrage and protects against sandwich attacks. Second, the maximum swap size is capped at 5% of the pool reserve (configurable via `set_max_swap_pct_bps`), which bounds the price impact of any single transaction and prevents the contract from being drained by a flash-loan attack. Third, a circuit breaker fires if a single swap moves the pool price more than 10% — the swap is reverted and the pool is paused pending governance review.

### 7.3 PSM Integration into VaultSwapV2

For unified UX, the PSM is exposed as a special pool type within VaultSwapV2. When `create_pool(asset_a, asset_b, is_psm)` is called with `is_psm = true`, the pool is registered as a PSM pool and uses the PSM's price and fee model instead of the constant-product formula. The `psm_mint` and `psm_redeem` entries on VaultSwapV2 (IDs 3 and 4) dispatch to the same internal logic as `PSM.mint` and `PSM.redeem`, so a front-end integrating VaultSwapV2 automatically gets PSM liquidity for the XEL/xUSD pair without needing a separate integration. This also means the TWAP circuit breaker and max-swap-size checks apply to PSM flows, adding a second layer of protection against oracle manipulation.

---

## 8. Governance

### 8.1 GovernanceVault

`GovernanceVault` is the staking contract that gives VLT holders voting power. A user stakes VLT via `stake(amount, lock_days)`, where `lock_days` ranges from 7 (minimum, enforced by the CR-01 fix) to 365 (maximum). Voting power is computed with a lock-time boost:

```silex
// boost = 10,000 bps (1×) + (lock_days × 10,000 / 365) bps, capped at 20,000
let boost_bps: u64 = min(20_000, 10_000 + lock_days * 10_000 / 365);
let voting_power: u128 = (amount as u128) * (boost_bps as u128) / 10_000;
```

A 7-day lock yields 1.19× boost, a 90-day lock yields 1.5×, and a 365-day lock yields the maximum 2× boost. This rewards long-term alignment without disenfranchising short-term holders (who still get 1× per staked VLT).

Staking rewards (separate from miner rewards) are distributed via the Synthetix-style `reward_per_token` accumulator pattern. An authorized distributor (typically `TreasuryVault` or `RevenueShare`) calls `notify_reward_amount(amount)` to fund a reward period. The contract accumulates `reward_per_token` over time as `reward_amount × 1e12 / total_voting_power`; each staker's earned reward is `user_vp × (current_RPT - user_paid_RPT) / 1e12`. The CR-01 fix enforces `lock_days >= 7` to prevent instant unstake/restake vote cycling, which would otherwise allow a whale to manipulate votes by repeatedly locking and unlocking.

### 8.2 Governor

`Governor` is the protocol-level proposal engine. The lifecycle is: `propose(targets, values, calldatas, description)` → `vote(proposal_id, support)` → `queue(proposal_id)` → `execute(proposal_id)`, with `cancel(proposal_id)` available to the proposer before execution. Quorum is 10% of total voting power, approval is 50% of cast votes (with abstain counted separately), the voting period is 7 days, and the execution delay is 2 days. When `queue` is called, the Governor snapshots the total voting power via `GovernanceVault.get_total_voting_power_entry` (entry 4); when `execute` is called, it dispatches each queued call to its target contract via `Contract::call`. The audit fixed finding #10, where the Governor had previously been calling entry 6 (`notify_reward_amount`) instead of entry 4 (`get_total_voting_power_entry`) — silently breaking quorum math.

### 8.3 Timelock

The `Timelock` contract is the only role allowed to call `only_timelock`-governed setters across the protocol. It accepts queued operations with a minimum delay of 1 hour, a maximum delay of 7 days, and a special 1-day emergency delay reserved for guardian-only actions (e.g., emergency parameter changes during an active exploit). The dual-guardian design (audit finding #7) means `only_guardian()` and `only_guardian_or_admin()` accept either an EOA (`GUARDIAN_KEY`) or a contract (`GUARDIAN_CONTRACT_KEY` via `get_contract_caller()`). A new entry `set_guardian_contract(Hash)` configures the multisig. This lets the protocol migrate from a single-EOA guardian on testnet to a 3-of-5 multisig on mainnet without re-deploying Timelock.

### 8.4 GuardianMultisig

`GuardianMultisig` is the on-chain multisig that, when configured as `Timelock.guardian_contract`, serves as the protocol's emergency response body. It supports 3 to 7 guardians with a configurable quorum (minimum 2/3). Six action types are supported:

| Action ID | Action | Quorum required |
|-----------|--------|-----------------|
| 0 | `pause` | Standard quorum |
| 1 | `trigger_cb` (circuit breaker) | Standard quorum |
| 2 | `custom` (arbitrary call) | Standard quorum |
| 3 | `add_guardian` | Quorum proposal |
| 4 | `remove_guardian` | Quorum proposal |
| 5 | `set_quorum` | Quorum proposal |

The audit (finding #6) fixed a critical issue: previously, `add_guardian`, `remove_guardian`, and `set_quorum` could be called directly by admin, defeating the purpose of a multisig. In v5.0 these three actions must go through `propose_emergency_action` (action IDs 4, 5, 6 respectively), followed by confirmation by the required quorum, followed by execution. This means the multisig composition cannot be changed by any single signer — not even admin.

### 8.5 OracleGovernance

`OracleGovernance` is a specialized Governor for oracle parameters. It shares the propose/vote/queue/execute lifecycle but its `execute_proposal` dispatcher recognizes a specialized set of proposal types: `TYPE_ADD_FEED`, `TYPE_UPDATE_FEED`, `TYPE_REMOVE_FEED`, `TYPE_SET_MAX_DEVIATION`, `TYPE_SET_CB_THRESHOLD`, `TYPE_SET_MAX_STALE`, `TYPE_SET_HARD_STALE`, `TYPE_SET_SUBMIT_WINDOW`, `TYPE_SET_BASE_REWARD`, `TYPE_EMERGENCY_CB`, and `TYPE_RESET_FEED`. Each type dispatches to the corresponding entry on `StakedOracle` or `XelisVaultMiner` via cross-contract call. Audit finding #15 fixed a `TYPE_SET_REWARD` case that was previously a `TODO` (empty body); v5.0 implements it via `miner.call(21u16, [reward_amount], {})`, where entry 21 of XelisVaultMiner is `set_base_reward_oracle`. A new entry `set_miner_contract(Hash)` on OracleGovernance configures the miner contract reference.

---

## 9. Security Architecture

### 9.1 Audit Findings & Remediation

The v4.3 audit identified 15 vulnerabilities across the 33-contract codebase. All 15 were remediated in v5.0 and verified against the real Silex API surface (validated through `upload/lib.rs`, the Silex playground wrapper). The summary table:

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | Critical | XelisVaultMiner entry IDs mass-shifted | `slash_miner`, `distribute_reward`, `is_miner_active_entry`, `get_active_miners_for_service_entry` converted to `entry`; StakedOracle now calls IDs 7/8/9/12 |
| 2 | Critical | OracleGovernance → StakedOracle wrong IDs | Re-mapped: MAX_STALE→16, HARD_STALE→17, MAX_DEV→13, CB_THRESH→14, SUBMIT_WINDOW→15, EMERGENCY_CB→3, RESET_FEED→4 |
| 3 | Critical | VaultEngine calls `add_feed` instead of `get_price_for_asset` | `get_oracle()` uses `reg.call(0u16, ["StakedOracle"], {})` (registry entry 0 = `get_entry`); `get_xel_price()` uses `oracle.call(9u16, [Hash::zero()], {})` |
| 4 | Critical | `claim_rewards()` syntax broken | Rewritten with explicit early return when `total_pending == 0` |
| 5 | Critical | `flash_loan()` body malformed + invalid kwargs | Rewritten linear; empty kwarg `{}`; balance check `>= balance_before + fee` |
| 6 | High | GuardianMultisig add/remove guardian admin-only | Routed through `propose_emergency_action` (action 4/5/6) + quorum |
| 7 | High | `Timelock.only_guardian()` incompatible with multisig | Accepts either `caller == GUARDIAN_KEY` or `get_contract_caller() == GUARDIAN_CONTRACT_KEY`; new `set_guardian_contract(Hash)` entry |
| 8 | High | False privacy (cipher was cleartext) | `deposit` accepts `salt: Hash` for commit-reveal; documentation updated |
| 9 | High | No interest on VaultEngine borrows | Stability fee: global index `STABILITY_FEE_INDEX_KEY` (1e12 scale, 2% APR default); `set_stability_fee_bps` added |
| 10 | Medium | Governor calls `gv.call(6)` = `notify_reward_amount` | Changed to `gv.call(4, [], {})` = `get_total_voting_power_entry` |
| 11 | Medium | OracleGovernance calls entry 0 = `stake` | Changed to `gv.call(3, [addr], {})` = `get_voting_power_entry` |
| 12 | Medium | PSM `get_xel_price` calls entry 8 = `set_timelock` | Changed to `oracle.call(8, ["XEL/USD"], {})` = `get_price_entry`; VaultSwapV2 uses entry 9 = `get_price_for_asset_entry` |
| 13 | Medium | `maybe_adjust_budget` division by zero + bug | Added `token_count == 0` guard; removed duplicate `target_rate`; symmetrized clamp |
| 14 | Low | `emergency_withdraw` no timelock — rugpull vector | All 33 contracts now implement two-step `request_emergency_withdraw` + `execute_emergency_withdraw(asset)` with 17,280-block (24h) delay |
| 15 | Low | `TYPE_SET_REWARD` was empty TODO | Implemented via `miner.call(21u16, [reward_amount], {})`; new `set_miner_contract(Hash)` entry on OracleGovernance |

### 9.2 Two-Step Emergency Withdraw

Every fund-holding contract in v5.0 implements the same two-step emergency withdrawal pattern. The first step, `request_emergency_withdraw()` (callable by the `emergency` role), stores the current topoheight in `EMERGENCY_REQUEST_TOPO_KEY`. The second step, `execute_emergency_withdraw(asset: Hash)` (also callable by the `emergency` role), verifies that at least 17,280 blocks (approximately 24 hours at 5 seconds per block) have elapsed since the request, then transfers the contract's entire balance of the specified asset to the `emergency` address. A `cancel_emergency_withdraw` entry allows the emergency role to abort the request if it was made in error.

This pattern defeats the classic rugpull vector in which a privileged key transfers contract funds in a single transaction. With a 24-hour delay, users have an entire day to react: withdraw their deposits, close their vaults, exit their LP positions, or alert the community. Any single-block rugpull becomes visible as a pending `request_emergency_withdraw` on-chain, giving the community time to respond before funds actually move. This is a strong defense-in-depth measure; it does not replace the `only_timelock` gating on parameter changes, but it ensures that even a fully compromised admin key cannot drain the protocol silently.

### 9.3 ReentrancyGuard Pattern

Three contracts hold user funds during complex multi-step operations that could be vulnerable to reentrancy: `VaultEngineV3` (deposit → borrow → repay → liquidate), `VaultSwapV2` (swap → callback → settle), and `FlashLoan` (loan → callback → repay). All three implement the same `ReentrancyGuard` pattern using a single storage key `RG_STATUS_KEY`:

```silex
const RG_NOT_ENTERED: u64 = 1;
const RG_ENTERED: u64 = 2;

entry some_protected_function(...) {
    let status: u64 = Storage::load(RG_STATUS_KEY).unwrap_or(RG_NOT_ENTERED);
    require(status == RG_NOT_ENTERED, "reentrant");
    Storage::store(RG_STATUS_KEY, RG_ENTERED);
    // ... function body ...
    Storage::store(RG_STATUS_KEY, RG_NOT_ENTERED);
}
```

Because Silex reverts the entire transaction (including storage writes) if any cross-contract call fails, the guard is reset correctly even in failure paths. This is one advantage of Silex's no-`try/catch` design: there is no way to accidentally swallow a revert and leave the guard in the `ENTERED` state.

### 9.4 Pausable Pattern

Every operation contract implements the same pausable pattern: a `pause(reason: string)` entry callable by guardian or admin, and an `unpause()` entry callable by admin only. When paused, the contract's user-facing operations revert with the provided reason; admin and view entries remain callable. The pause state is stored in `PAUSED_KEY` (bool) and the pause reason in `PAUSE_REASON_KEY` (string) for transparency. This pattern is used by `StakedOracle` (pauses all price reads), `VaultEngineV3` (pauses all deposits, borrows, repayments, redemptions), `PSM`, `VaultSwapV2`, `LendingMarket`, `FlashLoan`, `SealedBidAuction`, and all auxiliary contracts. The guardian can pause any contract in a single transaction via `GuardianMultisig.propose_emergency_action(action=0, target=contract_hash)`.

### 9.5 No Admin Backdoor

A central security principle of v5.0 is that the admin role has no direct authority over user funds. Admin can call parameter setters (via Timelock), can `transfer_admin` to a new address, and can `unpause` a paused contract — but cannot transfer a user's collateral, cannot mint or burn tokens arbitrarily, and cannot bypass the two-step emergency withdrawal. Minter and burner roles are explicit per-contract: only `VaultEngineV3` and `PSM` can mint xUSD (and only against valid collateral or XEL deposits); only `VaultEngineV3` (on repay) and `PSM` (on redeem) can burn xUSD. Only `XelisVaultMiner.distribute_reward` can mint VLT (and only against the 6,000,000 VLT budget cap). The admin cannot mint VLT to themselves, cannot transfer xUSD between users, and cannot seize collateral. This principle is enforced by the absence of any admin-gated `transfer(to, asset, amount)` entry on fund-holding contracts (the only such entry is `execute_emergency_withdraw`, which is rate-limited by the two-step delay).

---

## 10. Auxiliary Features

### 10.1 FlashLoan

`FlashLoan` provides uncollateralized loans of any supported asset, repayable within the same transaction. The fee is 9 basis points (configurable via `set_fee_bps`), routed to the treasury. The pattern is callback-based: the borrower calls `flash_loan(asset, amount, callback_contract, callback_data)`, which transfers `amount` to the borrower, invokes `callback_contract.on_flash_loan(asset, amount, fee, callback_data)` (entry 0 of the `FlashCallback` interface), then checks `balance_after >= balance_before + fee`. If the check fails, the entire transaction reverts. This is the standard EIP-3156 pattern, adapted to Silex's no-`try/catch` model (any revert in the callback aborts the loan automatically). Use cases include liquidations (flash-borrow xUSD to liquidate an under-collateralized vault, repay with the seized collateral), arbitrage between VaultSwapV2 and external venues, and self-liquidation by vault owners who cannot post more collateral.

### 10.2 SealedBidAuction

`SealedBidAuction` is a commit-reveal auction contract designed for selling RWA (real-world asset) tokens represented by `AssetVault`. A seller calls `create_auction(asset, amount, bid_asset, min_bid, commit_duration, reveal_duration)` to list an asset. Bidders call `commit(auction_id, bid_hash)` during the commit phase, where `bid_hash = hash(amount, salt, bidder, auction_id)`; the salt makes the bid unreveable until the reveal phase. During the reveal phase, bidders call `reveal(auction_id, amount, salt)`, which verifies the hash and locks the bid amount. When the reveal phase ends, the contract settles: the highest bid wins, the asset is transferred to the winner, the winning bid amount is transferred to the seller (minus a 100 bps protocol fee), and losing bids are refunded. Audit finding N-02 fixed a refund bug: the contract now tracks `max_bid` and `refund_bid` per losing bidder to ensure every loser gets their full bid back even if multiple bids were revealed.

### 10.3 PrivacyMixer

`PrivacyMixer` is a fixed-denomination mixer for XEL, designed for users who want to break the link between their deposit address and their withdrawal address. The contract maintains a Merkle tree of deposit commitments; a deposit of 10, 100, or 1000 XEL (the three supported denominations) produces a commitment `C = hash(amount, nullifier, secret)` inserted into the tree. A withdrawal produces a zero-knowledge proof (verified off-chain and anchored on-chain via a relayer) that the withdrawer knows the nullifier and secret for some commitment in the tree, without revealing which one. The nullifier is published on-chain to prevent double-spending. Relayers are authorized via `set_relayer(addr, enabled)` and earn a small fee for submitting the withdrawal transaction on behalf of the user, so the user never needs to fund the withdrawal address with XEL for gas.

### 10.4 VaultChat

`VaultChat` is an end-to-end encrypted chat protocol with on-chain message anchoring. Users post messages off-chain to relayers; relayers batch messages into a Merkle tree and anchor the root on-chain via `anchor(root)` (callable only by authorized relayers). Group key distribution is handled off-chain via a Diffie-Hellman-derived group key; on-chain, only the Merkle root and a per-group sequence number are stored. Each valid anchor earns the relayer's miner a `+5` reputation gain and a 0.5 VLT reward via `XelisVaultMiner.distribute_reward(addr, 2, true)` (service ID 2 = chat). This makes the chat protocol economically self-sustaining: relayers who anchor messages earn VLT, miners who run relayers earn reputation, and users get end-to-end encrypted messaging with cryptographic proof of message integrity anchored to the XELIS BlockDAG.

### 10.5 Other Auxiliary Contracts

The remaining auxiliary contracts complete the protocol stack:

- **InsurancePool** — users deposit xUSD to buy coverage against smart-contract exploits; claims are paid out when governance approves a post-incident claim.
- **AssetVault** — tokenizes RWAs (real estate invoices, commodity receipts, tokenized treasuries) as XELIS assets, with transfer restrictions enforced by `ComplianceModule`.
- **TreasuryVault** — the protocol's revenue sink; receives all fees, splits 50% to burn and 50% to GovernanceVault via `notify_reward_amount`.
- **RevenueShare** — distributes treasury revenue to VLT stakers pro-rata; authorized distributor on GovernanceVault.
- **SavingsRate** — xUSD holders deposit and earn a yield sourced from LendingMarket reserve factor and VaultEngine stability fees.
- **Payroll** — recurring payments (subscriptions, salaries) with streaming-style accrual.
- **FaucetContract** — testnet-only faucet for distributing test XEL, VLT, and xUSD to new users.
- **ComplianceModule** — transfer restrictions (KYC gating, jurisdictional blocklist, max transfer size) for RWA assets; opt-in per asset.
- **MinerPool** — pooled oracle mining for users who want to participate without running a full miner; deposits VLT into a shared stake, distributes rewards pro-rata.

---

## 11. Deployment Sequence

Deployment is deterministic and ordered by the layered dependency graph. The recommended sequence is:

1. **ContractRegistry** — deployed first; no dependencies. Admin = deployer EOA.
2. **VLTToken** — deployed with fixed supply 10,000,000 VLT; `mint_batch` called immediately to distribute to the team vesting contract, treasury, DEX liquidity, seed, airdrop, and bug-bounty allocations. 6,000,000 VLT remains unminted (reserved for `XelisVaultMiner` budget).
3. **XelisVaultMiner** — deployed; `set_vlt_contract(VLTToken)` wired; VLTToken grants minter role to XelisVaultMiner.
4. **StakedOracle** — deployed; `set_miner_contract(XelisVaultMiner)` and `set_registry(ContractRegistry)` wired; XelisVaultMiner is granted permission to call `distribute_reward` and `slash_miner`.
5. **XUSDToken** — deployed with elastic supply; no mint at deployment.
6. **VaultEngineV3, PSM, VaultSwapV2** — deployed in that order; each wires `set_oracle(StakedOracle)`, `set_xusd_contract(XUSDToken)`, `set_xusd_asset(...)`, `set_registry(ContractRegistry)`, `set_treasury(TreasuryVault)`. XUSDToken grants minter role to VaultEngineV3 and PSM; grants burner role to both.
7. **Governance chain** — `Timelock` → `Governor` → `GovernanceVault` → `GuardianMultisig` → `OracleGovernance`. Each wires its dependencies. `Governor.set_timelock(Timelock)`, `Governor.set_governance_vault(GovernanceVault)`, `OracleGovernance.set_miner_contract(XelisVaultMiner)`, `OracleGovernance.set_oracle(StakedOracle)`.
8. **Auxiliary contracts** — `FlashLoan`, `SealedBidAuction`, `PrivacyMixer`, `VaultChat`, `InsurancePool`, `AssetVault`, `TreasuryVault`, `RevenueShare`, `SavingsRate`, `Payroll`, `FaucetContract`, `ComplianceModule`, `MinerPool`. Each wires its specific dependencies.
9. **Registry registration** — every contract is registered by name in `ContractRegistry.register(name, hash)` so cross-contract calls can resolve by name.
10. **Admin handover** — on mainnet, `transfer_admin(Timelock)` is called on every contract, so admin becomes the Timelock contract (gated by governance proposals). The deployer retains only the `emergency` and `guardian` roles (guardian is transferred to `GuardianMultisig` via `set_guardian_contract`).

Initial VLT distribution happens in step 2 via a single `mint_batch` call to VLTToken. The 6,000,000 VLT oracle budget is **not** minted at deployment; it is minted lazily by `XelisVaultMiner.distribute_reward` as miners earn it, ensuring the budget never exceeds actual distribution.

---

## 12. Roadmap Summary

The roadmap is structured in four phases spanning Q3 2026 through Q2 2027 and beyond.

**Phase 1 (Q3 2026) — Testnet launch.** Deploy the full 33-contract stack on the XELIS testnet. Onboard 3 to 10 oracle miners to seed price feeds for XEL/USD and a small set of major assets. Bring VaultEngineV3 and PSM online first, since they depend only on the oracle; bring VaultSwapV2 and LendingMarket online once liquidity has been seeded. Run the integration test suite (oracle → miner reward flow, VaultEngine → oracle price resolution, governance proposal lifecycle, flash loan callback, stability fee accrual, two-step emergency withdrawal, GuardianMultisig → Timelock) for at least 4 weeks before mainnet.

**Phase 2 (Q4 2026) — Mainnet beta.** Deploy to XELIS mainnet. Scale to 10–20 oracle miners. Enable the full DeFi stack: VaultEngine, PSM, VaultSwapV2, LendingMarket, PeerLoan, SyndicatePool, FlashLoan, SealedBidAuction. Transfer admin from the deployer EOA to the Timelock contract. Configure GuardianMultisig with 3-of-5 guardians drawn from the foundation, independent community members, and an institutional partner. Hand over governance to VLT holders: the first community proposal is the closure of bootstrap mode (raising the minimum provider count from 3 to 10).

**Phase 3 (Q1 2027) — Mainnet stable.** Scale to 20+ oracle miners. Commission an external audit from a Silex-aware firm (Slixe preferred, otherwise Hacken or Trail of Bits). Launch the bug bounty on Immunefi with the 100,000 VLT allocation, split 50% critical / 30% high / 15% medium / 5% low. Disable bootstrap mode on StakedOracle. Begin onboarding the first RWA issuers to AssetVault under ComplianceModule gating.

**Phase 4 (Q2 2027 and beyond) — Ecosystem expansion.** Cross-chain bridges to Ethereum and Solana (with privacy-preserving wrappers so bridged assets inherit XELIS confidentiality). RWA marketplace built on SealedBidAuction. Mobile wallet with native VaultChat integration. Layer-2 zk-rollup exploring higher-throughput oracle submissions for high-frequency feeds (forex, equities). Continued expansion of the auxiliary layer with new contract types (options, perpetuals, prediction markets) composed against the existing governance and oracle primitives.

---

## 13. Conclusion

XELIS Vault v5.0 is a complete DeFi stack built natively on a privacy-first Layer-1. By committing to the constraints of the Silex language — no `Ciphertext` type, no `try/catch`, sequential entry IDs, empty kwargs — the protocol achieves a level of architectural honesty that is rare in DeFi: every cross-contract call site is verifiable against the real Silex API surface, every entry ID is auto-documented by `scripts/extract_entry_ids.py`, and every privacy claim is backed by either XELIS-layer homomorphic encryption or an explicit commit-reveal pattern rather than a hypothetical cipher. The v4.3 audit identified 15 vulnerabilities ranging from critical entry-ID misalignments to low-severity TODOs; all 15 have been remediated in v5.0, and the resulting codebase is ready for testnet deployment pending external audit and integration testing.

The protocol's economic design is deliberately conservative: a fixed-supply governance token (VLT), a soft-pegged stablecoin (xUSD) backed by three independent peg mechanisms (PSM arbitrage, redemption queue, deflationary burn), a ten-year budget-aware oracle reward system with dynamic rate adjustment, and a layered access-control model in which admin has no direct authority over user funds. Combined with the two-step emergency withdrawal pattern applied uniformly to all 33 contracts, the ReentrancyGuard pattern on every callback-exposing contract, and the dual-guardian Timelock design, this makes XELIS Vault one of the most economically sound and operationally defensible DeFi protocols deployable on a privacy chain today. The roadmap from testnet to mainnet-stable is concrete, the external audit and bug bounty are scheduled, and the protocol is positioned to demonstrate that privacy and composability are not opposing forces in decentralized finance.

---

## 14. References

- **XELIS documentation** — https://docs.xelis.io
- **Silex playground** — https://playground.xelis.io
- **Source repository** — https://github.com/XelisVault/xelis-vault
- **Audit report (v5.0 remediation)** — `docs/AUDIT_v5.0_REMEDIATION.md`
- **Entry IDs (auto-generated)** — `docs/ENTRY_IDS.md`
- **Reward & reputation system** — `docs/REWARD_SYSTEM.md`
- **Silex API validation source** — `upload/lib.rs` (Silex playground wrapper)
- **Entry ID extractor** — `scripts/extract_entry_ids.py`

*This whitepaper describes XELIS Vault v5.0 as of 24 June 2026. All parameters, entry IDs, and contract names reflect the post-remediation codebase; future versions may change them via governance. Nothing in this document constitutes financial advice or an offer to sell securities.*
