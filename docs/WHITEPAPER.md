# XELIS Vault — Technical Whitepaper

> **Version 2.0** — *The First Confidential Financial Platform on XELIS BlockDAG*
>
> *Confidential lending, tokenization, treasury, compliance, and markets — powered by native homomorphic encryption*

---

## Abstract

XELIS Vault is a decentralized financial platform built on the XELIS BlockDAG. It leverages XELIS native **Twisted ElGamal homomorphic encryption** to provide the first truly confidential financial ecosystem in blockchain history.

The platform encompasses:
- **Confidential Lending** — overcollateralized loans with private positions
- **Private Lending Marketplace** — multi-pool, multi-collateral lending with dynamic rates
- **Real-World Asset (RWA) Tokenization** — standard for issuing private tokens representing real assets
- **Private Treasury Management** — multi-signature confidential treasuries for DAOs and institutions
- **Private Syndicated Loans** — multi-lender, single-borrower credit pools
- **Private Peer-to-Peer Lending** — bilateral loans with custom terms
- **Compliance & Identity Layer** — ZK-based KYC/AML proofs without exposing identity
- **Private Sealed-Bid Auctions** — fully confidential bidding
- **Private Revenue Sharing & Payroll** — confidential recurring payments
- **Private Insurance & Derivatives** — peer-to-peer risk markets
- **Governance Token (VLT)** — protocol ownership, parameter voting, and revenue distribution

No existing platform (Aave, Compound, Maker, Morpho) offers this combination of privacy, breadth, and institutional readiness.

---

## 1. Introduction

### 1.1 The Privacy Gap in DeFi

Current DeFi operates on fully transparent ledgers. Every position, liquidation, and transfer is visible to everyone — including MEV bots, competitors, and regulators.

This transparency creates fundamental problems:
- **Front-running and MEV** — bots extract value from public transactions
- **Institutional exclusion** — regulated entities cannot reveal their positions
- **Privacy loss** — financial history is permanently public
- **Competitive disadvantage** — strategies, leverage, and holdings are exposed

### 1.2 The Opportunity

XELIS provides the cryptographic primitives to solve this:
- **Twisted ElGamal over Ristretto255** — homomorphic encryption at the protocol level
- **Confidential Assets** — every token is private by default
- **XVM + Silex** — a capable smart contract environment
- **BlockDAG Architecture** — 5-second blocks, high throughput

XELIS Vault is the first platform to productize these primitives into a complete, institution-grade financial ecosystem.

---

## 2. Protocol Architecture

### 2.1 Smart Contract Layers

```
                    ┌──────────────────────────────────────┐
                    │           CORE LENDING               │
                    │  VaultEngine  |  xUSD  |  FlashLoan  │
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
                    │         FINANCIAL MARKETS            │
                    │  LendingMarket  |  PeerLoan          │
                    │  SyndicatePool  |  SealedBidAuction  │
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
                    │       TOKENIZATION & TREASURY        │
                    │  AssetVault  |  TreasuryVault        │
                    │  RevenueShare  |  Payroll            │
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
                    │       COMPLIANCE & IDENTITY          │
                    │  ComplianceModule  |  ZK-Verifier    │
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
                    │       INSURANCE & DERIVATIVES        │
                    │  InsurancePool  |  PrivateInsurance  │
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
                    │         GOVERNANCE                   │
                    │  VLT Token  |  GovernanceVault       │
                    │  Timelock  |  GuardianMultisig       │
                    └──────────────────────────────────────┘
```

### 2.2 Contract Catalog

| Contract | Type | Purpose |
|----------|------|---------|
| `VaultEngine.slx` | Core | Overcollateralized lending (deposit, borrow, repay, withdraw, liquidate) |
| `xUSD.slx` | Core | Privacy-preserving stablecoin |
| `InterestRateModel.slx` | Core | Kinked interest rate calculation |
| `PriceOracle.slx` | Core | XEL price feed with timelock |
| `FlashLoan.slx` | Core | Confidential uncollateralized flash loans |
| `LendingMarket.slx` | Market | Multi-pool, multi-collateral lending marketplace |
| `PeerLoan.slx` | Market | Bilateral peer-to-peer confidential loans |
| `SyndicatePool.slx` | Market | Multi-lender, single-borrower syndicated credit |
| `SealedBidAuction.slx` | Market | Fully confidential sealed-bid auctions |
| `AssetVault.slx` | Tokenization | Standard template for RWA tokenization |
| `TreasuryVault.slx` | Treasury | Multi-signature confidential treasury management |
| `RevenueShare.slx` | Treasury | Confidential revenue distribution |
| `Payroll.slx` | Treasury | Private recurring payments |
| `InsurancePool.slx` | Insurance | Community-backed insurance pool |
| `PrivateInsurance.slx` | Insurance | Peer-to-peer insurance and derivatives |
| `ComplianceModule.slx` | Compliance | ZK-based KYC/AML verification layer |
| `VLT.slx` | Governance | Protocol governance token |
| `GovernanceVault.slx` | Governance | Token staking, voting, and parameter control |
| `Timelock.slx` | Governance | 48-hour timelock on all parameter changes |

---

## 3. Confidential Lending (Core)

### 3.1 Vault Positions

Each vault is a `VaultSnapshot` stored on-chain:

```
VaultSnapshot {
    owner: Address,
    collateral_asset: Hash,
    borrow_asset: Hash,
    collateral_cipher: Ciphertext,   // Encrypted balance
    borrow_cipher: Ciphertext,       // Encrypted debt
    collateral_plain: u64,           // Decrypted (for VM health checks)
    borrow_plain: u64,               // Decrypted (for VM health checks)
    last_update_topo: u64,
    liquidated: bool,
    created_at: u64,
    id: u64
}
```

**Privacy design:** The `_cipher` fields store encrypted amounts using XELIS native `Ciphertext` type. The `_plain` fields are used internally by the VM. From any third-party perspective, the `_cipher` values are unreadable.

### 3.2 Collateral Ratio

```
Minimum Collateral Ratio: 150%
Liquidation Penalty:      5%
Protocol Fee:             0.5% (borrow)

Health Factor = collateral_value × 100 / borrow_value
Liquidation at: health_factor < 150
```

### 3.3 Interest Rate Model

Kinked model based on utilization:

```
If utilization ≤ kink (80%):
    borrow_rate = base_rate + (utilization × multiplier / kink)
If utilization > kink (80%):
    borrow_rate = base_rate + multiplier + (excess × jump_multiplier / (100 - kink))
```

- `base_rate`: 0.5% APR
- `multiplier`: 10% APR
- `jump_multiplier`: 50% APR
- `reserve_factor`: 10%

### 3.4 Redemption (Peg Support)

Redemption is the primary mechanism for maintaining xUSD's peg and creating arbitrage demand:

1. Anyone holding xUSD can call `redeem(amount)` on VaultEngine
2. The contract automatically targets the vault with the **lowest health factor** above 150%
3. That vault's debt is reduced by the amount, and corresponding collateral is sent to the redeemer
4. A small redemption fee (0.5-1%) is charged and sent to the protocol treasury
5. The vault owner keeps their remaining debt and collateral — they are not liquidated

**Purpose:** Redemption creates automatic demand for xUSD when it trades below $1 on external DEXes like **XELIS Forge**. Arbitrageurs buy xUSD cheap on Forge, redeem it with the protocol for XEL at face value, and profit from the spread. This mechanism keeps xUSD pegged without requiring anyone to find vaults manually.

**Key difference from liquidation:** Redemption is voluntary, only targets healthy vaults (CR ≥ 150%), and the redeemer receives fair market collateral. Liquidation is forced, only targets underwater vaults (CR < 150%), and includes a penalty.

### 3.5 Liquidations

Liquidations handle vaults that fall below the minimum collateral ratio:

1. Keeper bot monitors vault health via `is_liquidatable()`
2. When CR drops below 150%, anyone can call `liquidate()`
3. The caller repays the debt and receives collateral minus a 5% liquidation penalty
4. The 5% penalty is burned, reducing total supply
5. Scheduled Executions batch-process liquidations at block boundaries

---

## 4. xUSD — Confidential Stablecoin

### 4.1 Design

xUSD is managed by VaultEngine:
- **Minted** when users borrow against collateral
- **Burned** when users repay their debt
- **All balances are confidential** via native Twisted ElGamal encryption
- **Elastic supply** — no maximum, expands and contracts with demand

### 4.2 Savings Rate

The xUSD Savings Rate is a protocol-level yield paid to xUSD depositors:
- Depositors lock xUSD in the savings contract
- Interest accrues automatically per block
- Rate is adjustable via governance (VLT holders)
- Earnings are confidential — no one sees your yield

### 4.3 Peg Mechanism

xUSD maintains its $1 peg through four mechanisms:

1. **Redemption (primary)** — When xUSD trades below $1 on external DEXes (XELIS Forge), arbitrageurs buy xUSD cheap on the DEX and call `redeem()` on VaultEngine to receive XEL at face value. This is the main demand driver for xUSD below peg.

2. **Borrow arbitrage** — When xUSD trades above $1, vault holders can borrow xUSD (at $1 face value) and sell it on the DEX for a profit. This increases supply and pushes price back down.

3. **Savings Rate** — Adjustable yield incentivizes holding xUSD when supply is high, and spending/borrowing when supply is low.

4. **Overcollateralization** — Every xUSD is backed by at least $1.50 of XEL, ensuring it can always be redeemed for underlying value.

**Why this works with Forge DEX:**
- xUSD/XEL liquidity pool on Forge enables market price discovery
- Arbitrageurs constantly monitor the pool for deviations from $1
- Redemption provides a guaranteed floor (you can always redeem xUSD for XEL at $1 worth)
- Borrowing provides a guaranteed ceiling (you can always borrow xUSD at $1 face value)

---

## 5. Financial Markets

### 5.1 Private Lending Marketplace

The `LendingMarket.slx` contract extends VaultEngine into a multi-pool system:

- **Liquidity Pools** — lenders deposit XEL, xUSD, or any supported token into confidential pools
- **Dynamic Rates** — utilization-based interest per pool
- **Multi-Collateral** — borrowers can use different assets as collateral
- **Confidential Positions** — individual deposits and borrows are encrypted
- **Liquidations** — automated, MEV-resistant, without revealing who is liquidated

Unlike VaultEngine's single-asset model, the marketplace allows:
- Lenders to earn yield by supplying liquidity
- Borrowers to choose the best pool for their needs
- Composability — positions can be used as collateral elsewhere
- **Forge DEX Integration** — xUSD liquidity pools enable market price discovery, arbitrage, and seamless swaps between all supported assets

### 5.2 Peer-to-Peer Lending

`PeerLoan.slx` enables direct bilateral loans:

1. Alice proposes a loan to Bob with terms (amount, interest rate, duration, collateral)
2. Bob accepts and locks collateral in the contract
3. Both the loan amount and repayment schedule are encrypted
4. Repayments are automatic — no manual intervention needed
5. Secondary market: Alice can sell the debt to a third party without revealing terms

Ideal for:
- Personal loans between trusted parties
- Business credit lines
- Private debt markets

### 5.3 Syndicated Loans

`SyndicatePool.slx` enables multi-lender, single-borrower credit:

1. A lead arranger creates a syndicate with target amount, interest rate, and duration
2. Multiple lenders commit capital confidentially
3. When the target is reached, funds are released to the borrower
4. Repayments are distributed proportionally to lenders
5. All terms and positions are encrypted — only participants see their share

Target market: institutional lending, real estate financing, working capital.

### 5.4 Sealed-Bid Auctions

`SealedBidAuction.slx` enables fully confidential bidding:

1. Seller lists an asset (token, NFT, collateral position)
2. Bidders submit encrypted offers
3. At auction end, bids are revealed and compared
4. Highest bidder wins, others are refunded
5. Nothing is public — not the number of bidders, not the amounts

Use cases:
- Liquidated collateral sales (no front-running)
- RWA secondary markets
- Private token sales
- Government/DAO asset sales

---

## 6. Tokenization & Treasury

### 6.1 Real-World Asset Tokenization

`AssetVault.slx` is a standardized contract for issuing confidential tokens representing real-world assets:

**Core features:**
- Deploy a new confidential token in one transaction
- Configure name, symbol, total supply, and metadata
- Built-in confidential transfers (Twisted ElGamal)
- Mint/burn permissions controlled by the issuer
- Interface for attaching off-chain proofs (audit reports, valuation certificates)

**Business model:** XELIS Vault does not originate or verify RWAs — it provides the standard template. Partners (tokenization platforms, asset managers, banks) deploy and manage their own RWA tokens.

**Supported asset types:**
- Real estate (fractional ownership)
- Commodities (gold, silver, oil)
- Bonds and treasury bills
- Equity and revenue shares
- Carbon credits
- Invoice factoring

### 6.2 Private Treasury Management

`TreasuryVault.slx` enables DAOs, companies, and funds to manage their assets confidentially:

**Features:**
- Multi-signature with configurable thresholds (2/3, 3/5, etc.)
- Role-based access: owner, signer, viewer, guardian
- Confidential balances — no one sees the treasury size
- Encrypted transaction history — only authorized signers can audit
- Budget allocation — assign spending limits per category
- Vesting schedules — private, automated token distribution
- Emergency recovery — guardian multi-sig for crisis scenarios

**Use cases:**
- DAO treasuries (no more public balance sheets)
- Corporate treasury management
- Venture capital funds
- Family offices
- Protocol-owned liquidity management

### 6.3 Revenue Sharing

`RevenueShare.slx` enables confidential revenue distribution:

- An issuer deposits revenue into the contract
- Shareholders receive proportional distributions
- All amounts are encrypted — no one knows total revenue or individual payouts
- Ideal for: creator monetization, protocol revenue distribution, partnership splits

### 6.4 Private Payroll

`Payroll.slx` enables confidential recurring payments:

- Employer deposits funds and defines payment schedules
- Employees receive confidential payments at each interval
- Each employee sees only their own salary
- Vesting cliffs and termination logic built-in
- Use cases: corporate payroll, DAO contributor payments, subscription billing

---

## 7. Compliance & Identity

### 7.1 Problem

Institutions cannot use DeFi because they must:
- Prove KYC/AML compliance
- Demonstrate they are not on sanctions lists
- Maintain audit trails
- All without exposing sensitive business data

### 7.2 Solution: ZK Compliance Layer

`ComplianceModule.slx` provides a reusable compliance framework:

1. A regulated verifier (e.g., licensed KYC provider) performs off-chain due diligence
2. The verifier issues a ZK proof on-chain: "address X is compliant until date Y"
3. The proof reveals **nothing** — not the identity, not the verifier, not the jurisdiction
4. Any contract on XELIS can query: "is this address allowed to interact?"
5. Users without compliance requirements can opt out entirely

**Key properties:**
- **Privacy-preserving** — no identity data ever touches the chain
- **Interoperable** — any contract can integrate compliance checks
- **Upgradable** — verifier set can be updated via governance
- **Portable** — one proof works across all contracts on XELIS

### 7.3 Regulatory Compatibility

| Regulation | How XELIS Vault Addresses It |
|------------|------------------------------|
| MiCA (EU) | Verifiable compliance without exposing positions |
| MiFID II (EU) | Confidential reporting for investment firms |
| FATF Travel Rule | Encrypted beneficiary data with ZK verification |
| SEC Custody Rule | Multi-sig treasury with audit trail |
| Basel III | Institutional risk management on-chain |

---

## 8. Insurance & Derivatives

### 8.1 Insurance Pool

`InsurancePool.slx` provides community-backed protection:
- Users stake XEL to earn insurance premiums (0.1% of all borrows)
- Claims can be submitted when a vault cannot be liquidated
- Claims are verified and approved by guardians
- Payouts drawn from the pooled stake

### 8.2 Private Insurance

`PrivateInsurance.slx` enables peer-to-peer risk markets:

- Create bilateral insurance policies with custom terms
- Example: "I want to insure my vault against liquidation for 30 days"
- Premiums and payouts are confidential
- Automatic settlement — no claims process needed
- Expandable to derivatives: private options on XEL price, settlement automatically executed

---

## 9. Governance

### 9.1 VLT Token

VLT is the governance and value-accrual token of XELIS Vault:

| Parameter | Value |
|-----------|-------|
| Total Supply | 10,000,000 VLT |
| Asset Type | Confidential Asset (XELIS native) |
| Transfers | Encrypted by default |

**Distribution:**

| Allocation | Percentage | Vesting |
|------------|-----------|---------|
| Liquidity Providers | 40% | Farmed over 4 years |
| Core Team | 20% | 2-year linear vesting |
| Protocol Treasury | 15% | Available via governance |
| XELIS Ecosystem Fund | 10% | Partnership grants |
| Early User Airdrop | 10% | Claim at TGE |
| Audits & Security | 5% | Bug bounties, audits |

### 9.2 Governance Powers

VLT holders control protocol parameters through `GovernanceVault.slx`:

| Parameter | Scope | Initial Value |
|-----------|-------|---------------|
| Min Collateral Ratio | Risk | 150% |
| Liquidation Penalty | Risk | 5% |
| Reserve Factor | Treasury | 10% |
| Base Rate | Interest | 0.5% |
| Kink | Interest | 80% |
| Multiplier | Interest | 10% |
| Jump Multiplier | Interest | 50% |
| Borrow Fee | Protocol | 0.5% |
| Insurance Premium | Insurance | 0.1% |
| Savings Rate | xUSD | Configurable |
| Asset Whitelist | Expansion | Governance vote |
| Oracle Source | Risk | Governance vote |
| Compliance Verifiers | Identity | Guardian vote |
| Emergency Pause | Security | Guardian multi-sig |

### 9.3 Timelock

All parameter changes pass through a 48-hour timelock (`Timelock.slx`):
- Users have 48 hours to react before changes take effect
- Guardians can veto malicious proposals during the timelock
- Compatible with on-chain and off-chain voting systems

### 9.4 Protocol Revenue

| Source | Rate | Allocation |
|--------|------|------------|
| Borrow fees | 0.5% upfront | Treasury |
| Interest spread | ~2% avg | Treasury |
| Liquidation fees | 0.5% | Treasury |
| Flash loan fees | 0.09% | Treasury |
| Insurance premiums | 0.1% | Insurance Pool |

**Revenue allocation:**

```
Revenue → Treasury
    ├── 50% → VLT buyback & burn
    ├── 30% → Development fund
    ├── 10% → Insurance pool
    └── 10% → XELIS ecosystem partnerships
```

---

## 10. Privacy Model

| Data | On-Chain | Visibility |
|------|----------|------------|
| Vault owner | Public (Address) | Everyone |
| Collateral amount | Encrypted (Ciphertext) | Owner only |
| Borrow amount | Encrypted (Ciphertext) | Owner only |
| Health factor | Computed (plaintext for VM) | No one (ZK verifiable) |
| Peer loan terms | Encrypted | Participants only |
| Syndicate contributions | Encrypted | Participant-only |
| Treasury balances | Encrypted | Authorized signers only |
| xUSD balance | Encrypted (native) | Owner only |
| Compliance status | ZK proof | Verifier only |
| Auction bids | Encrypted | Bidder only |
| Revenue shares | Encrypted | Recipient only |
| Insurance policy | Encrypted | Counterparties only |
| Liquidations | Public (event) | Everyone |
| Protocol fees | Public (plaintext) | Everyone |

---

## 11. Revenue Model

| Source | Rate | Annualized (est. $10M TVL) |
|--------|------|--------------------------|
| Borrow fees | 0.5% upfront | $50,000 |
| Interest spread | ~2% avg | $200,000 |
| Liquidation fees | 0.5% | $10,000 |
| Flash loan fees | 0.09% | $5,000 |
| Insurance premiums | 0.1% | $10,000 |
| **Total** | | **~$275,000** |

---

## 12. Security

### 12.1 Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| Oracle manipulation | Timelock (1h), multiple sources |
| Flash loan attacks | Fee + callback verification |
| Bad debt | Insurance pool + reserve fund |
| Smart contract bugs | Open source, audit, bug bounties |
| Governance attack | Timelock on all parameter changes |
| Liquidation cascade | Gradual liquidation, Scheduled Executions |
| Privacy leak | Homomorphic encryption + ZK proofs |
| Sybil attacks | Compliance module for institutions |

### 12.2 Emergency Procedures

1. **Pause** — Guardians can pause borrowing, lending, and liquidations
2. **Recover** — Admin functions for extreme scenarios (timelocked)
3. **Upgrade** — New contract versions deployed via governance (no upgradeable proxies)

---

## 13. Bug Report & Static Analysis

In May 2026, an automated static analysis was conducted across all 19 smart contracts. Every contract was audited line-by-line for business logic, system calls, token handling, and security vulnerabilities. **100% of contracts (19/19) contained at least one bug.**

### Summary

| Severity | Count | Impact |
|----------|-------|--------|
| **Critical** | 7 | Funds at direct risk — incorrect price, missing transfers, broken peg |
| **Elevated** | 8 | Logic flaws — timing attacks, incorrect asset handling, missing checks |
| **Medium** | 6 | Design issues — missing refunds, incorrect constraints, parameter gaps |
| **Minor** | 3 | Edge cases — return values, counter mismatches, collision risks |
| **Total** | **24** | |

### Critical Bugs

| Bug | Contract | Description | Fix |
|-----|----------|-------------|-----|
| Oracle stores 0 instead of deleting | `PriceOracle.slx` | `execute_price()` does `store(ORACLE_KEY, 0)` instead of `delete()` — 0 is interpreted as a valid $0 price, liquidating all positions | Replace with `delete(ORACLE_KEY)` |
| Wrong entry index for price oracle | `VaultEngine.slx` | `get_xel_price()` calls entry 3 instead of entry 2; reads return as `Ciphertext` instead of `u64` | Fix entry index (3→2) and return type |
| Borrow never sends xUSD to borrower | `VaultEngine.slx` | `borrow()` mints xUSD but never transfers it — borrower incurs debt without receiving funds | Add `transfer_tokens` after mint |
| Repay does not burn xUSD | `VaultEngine.slx` | `repay()` reduces stored debt without burning xUSD — repaid tokens remain in circulation, breaking the peg | Burn xUSD via `xusd_entry_burn` |
| Liquidate transfers nothing to liquidator | `VaultEngine.slx` | `liquidate()` calculates collateral but never calls `transfer_tokens` — liquidator pays debt but receives nothing | Add `transfer_tokens` for XEL collateral |
| Withdraw bypasses health check when remaining is 0 | `VaultEngine.slx` | `if collateral_plain > 0` skips the health check — a user can withdraw all collateral even while still in debt | Always verify health factor when borrow exists |
| GovernanceVault uses contract hash instead of asset hash | `GovernanceVault.slx` | `lock_tokens()` uses `get_contract_hash()` instead of `VLT_ASSET_KEY` — wrong asset identity for transfers | Store and use `VLT_ASSET_KEY` from init |

### Elevated Bugs

| Bug | Contract | Description | Fix |
|-----|----------|-------------|-----|
| Lock duration in blocks not days | `GovernanceVault.slx` | Lock times measured in blocks (~5s each) — a "30 day" lock lasts 2.5 minutes | Convert durations to seconds/days |
| `transfer_tokens` sends to caller, ignores "to" param | `xUSD.slx` / `VLT.slx` | `transfer()` accepts a `to: Address` parameter but calls `transfer_tokens(asset, caller, amount)` — recipient is always the caller | Replace `caller` with `to` |
| Flash loan repayment not atomic | `FlashLoan.slx` | Loan must be borrowed AND repaid in a single atomic transaction — no final balance check after callback | Add balance verification after callback |
| Reveal allowed before auction ends | `SealedBidAuction.slx` | Bids can be revealed before auction end, breaking sealed-bid privacy | Add `require(topo > auction.end_block)` |
| xor_hashes is not a standard function | `SealedBidAuction.slx` | Commit uses `xor_hashes(owner_hash, amount_hash)` which does not exist in XELIS VM | Replace with standard hash commitment |
| Claim payout can be called repeatedly | `PrivateInsurance.slx` | `claim_payout()` does not track prior payouts — member can drain the pool | Add `claimed: bool` per policy |
| Claim does not decrement total staked | `InsurancePool.slx` | When a claim is paid, `TOTAL_STAKED_KEY` remains unchanged — total staked desynchronizes from actual pool balance | Decrement `TOTAL_STAKED_KEY` on claim |
| No debt tracking per borrower | `LendingMarket.slx` | Pool has no per-borrower debt tracking — impossible to liquidate a specific borrower | Add `borrower_debt: Address → Ciphertext` per pool |

### Medium Bugs

| Bug | Contract | Description | Fix |
|-----|----------|-------------|-----|
| Anyone can use another's KYC record | `ComplianceModule.slx` | Verification checks only that a hash exists, not that the caller is the KYC subject | Link proof to subject address, verify caller matches |
| Funds lost if syndicate target not met | `SyndicatePool.slx` | No refund mechanism if the pool fails to reach its target — funds remain locked | Add `cancel_syndicate()` with refunds |
| Cumulative allocations can exceed 100% | `TreasuryVault.slx` | `add_allocation()` does not verify total ≤ 100% | Check `total_allocations + new ≤ MAX` |
| Mutation of immutable variable | `LendingMarket.slx` | Contract modifies a variable declared `immutable` after init — compilation error | Remove `immutable` modifier |
| Fund stream does not track per-stream amounts | `Payroll.slx` | `fund_stream()` adds to contract balance but not per-stream allocation | Store `total_funded` per stream_id |
| deposit_revenue always expects XEL | `RevenueShare.slx` | No asset parameter — revenue distribution limited to XEL only | Add `asset: Hash` parameter |

### Minor Bugs

| Bug | Contract | Description | Fix |
|-----|----------|-------------|-----|
| withdraw_liquidity returns 0 | `LendingMarket.slx` | Read-before-write order causes return value to always be 0 | Restructure: read → calculate → write → return |
| Asset ID collision risk | `AssetVault.slx` | Auto-incrementing IDs can collide across multiple AssetVault deployments | Prefix IDs with `get_contract_hash()` |
| remove_allocation does not decrement counter | `TreasuryVault.slx` | `ALLOC_COUNT_KEY` is not decremented on allocation removal | Decrement counter in `remove_allocation()` |

### Impact

All 24 bugs must be resolved before testnet deployment. The 7 critical and 8 elevated bugs directly affect fund safety, peg stability, and core protocol functionality. A dedicated **Phase 0.5 — Bug Fix Sprint** has been added to the roadmap.

---

## 14. XelisVault Messenger (VaultChat)

XelisVault Messenger (codename **VaultChat**) is a fully decentralized, wallet-to-wallet encrypted messaging protocol built directly on XELIS smart contracts. Think of it as a decentralized, uncensorable Telegram — but built natively on XELIS with maximum confidentiality.

### 14.1 Motivation

Blockchain communication today relies on off-chain platforms (Telegram, Discord, Signal) that:
- Require trust in centralized infrastructure — a single company controls the servers
- Expose metadata (who talks to whom, when, how often)
- Cannot natively integrate with on-chain actions (payments, proposals, governance)
- Can be blocked, censored, or shut down by governments
- Collect and monetize user data

XelisVault Messenger solves this by bringing communication **on-chain** where it inherits blockchain security, censorship resistance, and native payment integration. No central server, no data collection, no surveillance — just private, persistent communication.

### 14.2 Architecture

```
┌────────────────────────────────────────────────┐
│              XelisVault Messenger               │
├────────────────────────────────────────────────┤
│  MessageContract.slx — core messaging engine    │
│  GroupContract.slx — group/DAO channel mgmt     │
│  PaymentContract.slx — payment bundling         │
│  StorageContract.slx — encrypted message store  │
│  ReputationContract.slx — anti-spam (future)    │
└────────────────────────────────────────────────┘
```

### 14.3 Features

#### 14.3.1 One-to-One Messaging

- **End-to-end encrypted**: messages use XELIS public key cryptography — only sender and recipient can decrypt. The smart contract never sees message content.
- **Full conversation history**: all messages persisted on-chain, encrypted. Your entire chat history is always available, never lost.
- **Message status**: sent → received → read. Sender can verify delivery and read status without revealing content.
- **Timestamps**: precise timestamps (topoheight) on every message for ordering and proof.
- **Message deletion**: sender can delete their own messages. The blockchain retains the proof of deletion, not the content.
- **Address-based contact lookup**: search any XELIS wallet address and start a conversation.
- **Payment+message bundling**: send XEL, xUSD, or any confidential asset in the same transaction as a message. Example: "Here's the 500 xUSD I'm lending you" — the payment and message arrive together.

#### 14.3.2 Group Messaging

- **On-chain group creation**: create groups with up to 50-100 members at launch.
- **Private group channels**: only members can see the group, its member list, and its messages.
- **Role-based access**: admin, moderator, member, read-only. Admins can add/remove members and moderate content.
- **Encrypted invites**: invite new members with encrypted invitations. Optional: require an onboarding payment.
- **Thread replies**: reply to a specific message within a group — organized discussions instead of linear chat.
- **Group message history**: full searchable history available to members.

#### 14.3.3 Reactions & Engagement

- **Message reactions**: react with emojis (❤️, 👍, 😂, etc.) to any message. Reactions are also private — only participants see them.
- **Typing indicators**: see when someone is typing (lightweight on-chain signals).
- **Message replies**: quote and reply to specific messages, creating threaded conversations.

#### 14.3.4 Self-Destructing Messages

- **Time-locked auto-delete**: message automatically disappears after N blocks if unread.
- **Burn-after-reading**: message is permanently deleted from the blockchain after first read — no trace remains.
- **Configurable timers**: per-message expiration from minutes to days.
- **Sender-controlled**: the sender chooses the timer when writing the message.

#### 14.3.5 File Attachments

- **Off-chain storage**: files, images, and documents stored on Arweave or IPFS (decentralized permanent storage).
- **On-chain proof**: the file hash and encryption key are stored on-chain, verifiable by the recipient.
- **Encrypted attachments**: files are encrypted client-side before upload — no one but the recipient can decrypt.
- **Efficient**: only the hash and key metadata are stored on-chain, keeping storage costs minimal.

#### 14.3.6 Conversation Search

- **Search your own messages**: full-text search across your conversations. Search is performed client-side on decrypted messages — never exposed to the chain.
- **Filter by contact, date, or amount**: find specific messages or payment transactions quickly.

#### 14.3.7 DAO & Governance Integration

- **DAO private channels**: confidential governance discussion channels tied to GovernanceVault proposals. VLT holders can discuss proposals in encrypted threads.
- **Proposal-linked messaging**: each governance proposal has an associated encrypted channel visible only to eligible voters.
- **Vote-signaling**: react to messages with on-chain votes (yes/no/abstain) without revealing your position publicly.
- **Treasury notifications**: automatic encrypted notifications for TreasuryVault transactions — multi-sig signers are notified when a transaction requires approval.
- **Quick actions**: "Send Payment" button directly in a conversation — initiate a vault deposit, loan repayment, or DAO vote without leaving the chat.

### 14.4 User Experience

1. **Open** the XelisVault dashboard
2. **Go** to the "Messenger" tab
3. **Search** for a wallet address or contact
4. **Write** your message (optionally attach a payment)
5. **Send** — the recipient receives an encrypted notification
6. **Everything** stays private, persistent, and uncensorable

### 14.5 Privacy & Security Model

| Property | Implementation |
|----------|---------------|
| Message encryption | XELIS public key crypto (Curve25519) — E2E by default |
| Metadata protection | Commit-reveal delivery — no plaintext sender/recipient on-chain |
| Anti-spam | Payment-per-message micro-fees (configurable). Future: reputation system |
| Censorship resistance | No central server — messages on XELIS chain, immutable |
| Message ordering | TopoHeight-based sequencing — messages in exact order sent |
| Data collection | Zero. No servers, no logs, no metadata harvesting |
| File attachments | Off-chain (Arweave/IPFS) with on-chain hash + encryption key |
| Message deletion | Sender-controlled deletion with on-chain proof |
| Government resistance | Impossible to block — XELIS is a decentralized global network |

### 14.6 Comparison

| Feature | Telegram | Signal | WhatsApp | **VaultChat** |
|---------|----------|--------|----------|---------------|
| E2E encryption | Optional | ✅ | ✅ | ✅ |
| Decentralized | ❌ | ❌ | ❌ | ✅ |
| No server | ❌ | ❌ | ❌ | ✅ |
| Censorship-resistant | ❌ | ❌ | ❌ | ✅ |
| Native payments | ❌ | ❌ | ❌ | ✅ |
| On-chain history | ❌ | ❌ | ❌ | ✅ |
| No data collection | ❌ | ✅ | ❌ | ✅ |
| DAO integration | ❌ | ❌ | ❌ | ✅ |
| Self-destruct messages | ✅ | ❌ | ❌ | ✅ |
| File attachments | ✅ | ✅ | ✅ | ✅ (decentralized) |

### 14.7 Use Cases

| Use Case | How VaultChat Solves It |
|----------|------------------------|
| **P2P loan negotiation** | Borrower and lender discuss terms in an encrypted thread, then execute via PeerLoan in the same session — payment bundled with the final message |
| **Syndicate coordination** | Lead arranger communicates with all lenders privately within the syndicate's encrypted channel — no Telegram dependency |
| **Governance discussion** | VLT holders debate proposals in private encrypted channels, vote-signal without revealing position |
| **Treasury operations** | Multi-sig signers coordinate via encrypted notifications — every approval is automatically logged |
| **Institutional compliance** | Regulated entities communicate within ZK-verified channels — regulators can audit without breaking privacy |
| **Private auction bidding** | Bidder-auctioneer communication, sealed bid submission, and reveal — all within the messenger |
| **Personal finance** | Send money to friends with a message explaining why — "Happy birthday, here's 100 xUSD" |

### 14.8 Development Roadmap

| Phase | Features | Timeline |
|-------|----------|----------|
| **VaultChat 1.0** | 1-to-1 encrypted messaging, payment+message bundling, message status (sent/received/read), full conversation history, address search | Phase 7 (Q4 2026) |
| **VaultChat 2.0** | Groups (up to 50 members), roles (admin/mod/member), thread replies, reactions (❤️👍😂), self-destruct messages, message deletion | Phase 8 (Q1 2027) |
| **VaultChat 3.0** | DAO governance channels, proposal-linked messaging, VLT-gated access, vote-signaling, treasury notifications, quick actions | Phase 9 (Q2 2027) |
| **VaultChat 4.0** | File attachments (Arweave/IPFS), typing indicators, conversation search, mobile SDK, reputation-based anti-spam | Phase 10 (Q2-Q3 2027) |

---

## 15. Roadmap

### Phase 0 — Contract Development 

| Milestone | Status |
|-----------|--------|
| All 19 smart contracts written | ✅ Complete |
| Compilation & static analysis (18+ syntax bugs fixed) | ✅ Complete |
| TypeScript SDK + CLI + Liquidation Bot | ✅ Complete |
| Comprehensive bug audit (24 bugs found) | ✅ Complete |

### Phase 0.5 — Bug Fix Sprint (Current)

| Milestone | Target |
|-----------|--------|
| Fix 7 critical bugs (PriceOracle, VaultEngine, GovernanceVault) | Sprint 1 |
| Fix 8 elevated bugs (xUSD/VLT transfer, FlashLoan, SealedBidAuction, Insurance) | Sprint 2 |
| Fix 6 medium + 3 minor bugs | Sprint 3 |
| Re-test all contracts after fixes | Sprint 3 |
| Deploy and verify `Storage::store` / `Storage::load` on testnet | Sprint 1 |

### Phase 1 — VM & Deployment

| Milestone | Status |
|-----------|--------|
| Identify root cause (function registration order mismatch) | ✅ |
| Fix xstd registration order (remove iterator for V0) | ✅ |
| Rewrite stdlib.rs to match daemon's `build_environment()` exactly | ✅ |
| Deploy and test storage persistence on testnet | 🔧 In progress |
| Full vault lifecycle test (deposit → borrow → repay → withdraw) | 📅 |
| Liquidation path test | 📅 |

### Phase 2 — Core Lending on Testnet

| Milestone | Target |
|-----------|--------|
| Deploy PriceOracle (set initial XEL price) | Week 1 post-VM-fix |
| Deploy xUSD (create confidential asset) | Week 1 |
| Deploy InterestRateModel | Week 1 |
| Deploy VaultEngine (set oracle, xUSD, interest model) | Week 2 |
| Test deposit → borrow → repay → withdraw lifecycle | Week 2 |
| Test redemption path | Week 2 |
| Test liquidation path | Week 2 |
| Deploy InsurancePool + FlashLoan | Week 2 |

### Phase 3 — Peg, Governance & Markets

| Milestone | Target |
|-----------|--------|
| Forge DEX xUSD/XEL pool launch | Week 3 |
| Redemption mechanism (`redeem()`) | Week 3 |
| VLT token deployment (10M confidential asset) | Week 3 |
| GovernanceVault + Timelock | Week 3 |
| Private lending marketplace | Week 4 |
| Peer-to-peer lending | Week 4 |
| Sealed-bid auctions | Week 5 |

### Phase 4 — Institutional

| Milestone | Target |
|-----------|--------|
| Compliance module (ZK KYC/AML) | Week 6 |
| Syndicated loans | Week 6 |
| Treasury vault (multi-sig) | Week 7 |
| RWA tokenization standard (AssetVault) | Week 7 |

### Phase 5 — Expansion

| Milestone | Target |
|-----------|--------|
| Revenue sharing | Week 8 |
| Private payroll | Week 8 |
| Private insurance | Week 9 |
| Multi-collateral support | Week 9 |

### Phase 6 — Production

| Milestone | Target |
|-----------|--------|
| Professional security audit | Q3 2026 |
| Bug bounty program | Q3 2026 |
| Public testnet launch | Q3 2026 |
| Mainnet launch | Q3 2026 |
| Cross-chain xUSD (Trocador) | Q3 2026 |
| Position NFTs (tradeable debt) | Q3 2026 |
| Credit scores (under-collateralized loans) | Q3 2026 |
| Full DAO governance | Q3 2026 |
| Institutional API | Q4 2026 |

### Phase 7 — XelisVault Messenger 1.0

| Milestone | Target |
|-----------|--------|
| 1-to-1 encrypted messaging contract | Q4 2026 |
| Payment+message bundling | Q4 2026 |
| Proof-of-delivery | Q4 2026 |
| XELIS public key crypto integration | Q4 2026 |

### Phase 8 — XelisVault Messenger 2.0

| Milestone | Target |
|-----------|--------|
| Group messaging (50 members) | Q1 2027 |
| Role-based access (admin, mod, member) | Q1 2027 |
| Thread support | Q1 2027 |
| Self-destructing messages | Q1 2027 |

### Phase 9 — XelisVault Messenger 3.0

| Milestone | Target |
|-----------|--------|
| DAO governance channels | Q2 2027 |
| Proposal-linked messaging | Q2 2027 |
| VLT-gated access | Q2 2027 |
| Vote-signaling | Q2 2027 |

### Phase 10 — XelisVault Messenger 4.0

| Milestone | Target |
|-----------|--------|
| File attachments (IPFS/Arweave) | Q2 2027 |
| Reactions and typing indicators | Q2 2027 |
| Mobile SDK | Q3 2027 |

---

## 16. Conclusion

XELIS Vault is more than a lending protocol — it is **the first complete confidential financial platform** built on a privacy-native blockchain.

By combining:
- **Homomorphic encryption** for true confidentiality
- **Modular contract architecture** for extensibility
- **ZK proofs** for institutional compliance
- **Governance tokens** for decentralized control

...XELIS Vault enables financial applications that are impossible on transparent blockchains:
- Institutions can participate without exposing their strategies
- Individuals can borrow, lend, and trade without surveillance
- Markets can operate fairly without MEV
- Compliance can exist without sacrificing privacy

In a world where financial privacy is increasingly scarce, XELIS Vault provides the infrastructure for a truly confidential financial future.

---

## References

1. [XELIS Whitepaper V2](https://whitepaper.xelis.io/)
2. [XELIS Homomorphic Encryption](https://docs.xelis.io/features/privacy/homomorphic-encryption)
3. [Silex Language Reference](https://docs.xelis.io/features/smart-contracts/silex)
4. [Aave Protocol Whitepaper](https://github.com/aave/aave-v3-core)
5. [Compound Finance](https://compound.finance/)
6. [Liquity Protocol](https://www.liquity.org/)

---

*XELIS Vault — Confidential Finance for the Privacy Era*
