# XELIS Vault — Roadmap

> Last updated: June 2026
> Current version: v4.2

---

## Phase 1: Foundation (Q2 2026) ✅

### Architecture & Contracts
- ✅ VLTToken v4.2 — fixed supply (10M), deflationary via burn
- ✅ StakedOracle v4.2 — permissionless providers, staking, slashing
- ✅ OracleGovernance — VLT staker voting for feed management
- ✅ VaultEngineV3 — confidential lending with Ciphertext
- ✅ VaultSwapV2 — AMM + PSM with MEV protection
- ✅ ContractRegistry — versioned upgrade pattern
- ✅ Pause/reentrancy protection — built into each contract

### Off-chain Infrastructure
- ✅ price_provider.py — tested against live MEXC/CoinEx/CoinGecko APIs
- ✅ aggregation_keeper.py — keeps oracle cycles running
- ✅ Internal audit v4.2 — 18 bugs found and fixed

### Documentation
- ✅ Whitepaper v3
- ✅ Architecture documentation
- ✅ Provider guide
- ✅ Miner guide
- ✅ Testnet deployment guide

---

## Phase 2: Testnet & Audit (Q3 2026) 🚧

### July 2026
- 🚧 Deploy v4.2 contracts to XELIS testnet
- 🚧 Initial VLT distribution (testnet)
- 🚧 Recruit 10-20 bootstrap price providers (team + community)
- 🚧 Launch aggregation keepers (3+ instances for redundancy)
- 🚧 Verify oracle cycles, reward distribution, slashing

### August 2026
- 📅 Launch bug bounty program on Immunefi (up to $100k in VLT rewards)
- 📅 External security audit (Trail of Bits or OpenZeppelin)
- 📅 Community testnet campaign — invite users to test deposit/borrow/swap
- 📅 Dashboard v1 (React) — provider stats, price history, vault positions

### September 2026
- 📅 Fix any issues found in audit
- 📅 Finalize mainnet deployment parameters
- 📅 Governance bootstrap — initial VLT staking for voting power
- 📅 Public testnet results report

---

## Phase 3: Mainnet Launch (Q4 2026) 📅

### October 2026
- 📅 **Mainnet deployment**:
  - ContractRegistry
  - VLTToken (with initial distribution)
  - StakedOracle
  - VaultEngineV3
  - VaultSwapV2
- 📅 Initial VLT distribution (10M tokens allocated)
- 📅 First feed activated: XEL/USD
- 📅 First 50+ price providers staked

### November 2026
- 📅 Public announcement
- 📅 Dashboard v2 (full UX)
- 📅 SDK v1 (TypeScript)
- 📅 Integration with XELIS wallets (Genesix, CLI)
- 📅 7-day monitoring period (no critical issues)

### December 2026
- 📅 Open public provider registration
- 📅 First governance proposals
- 📅 End-of-year report and roadmap update

---

## Phase 4: Expansion (2027)

### Q1 2027 — RWA Tokenization
- 📅 AssetVault contract — issue confidential RWA tokens
- 📅 First RWA: physical gold backed 1:1
- 📅 **Governance vote to add XAU/USD feed** to StakedOracle
- 📅 TreasuryVault — multi-sig confidential treasury

### Q2 2027 — Advanced Lending
- 📅 LendingMarket — multi-pool, multi-collateral marketplace
- 📅 PeerLoan — bilateral P2P loans
- 📅 SyndicatePool — multi-lender syndicated credit
- 📅 SavingsRate — yield on xUSD deposits

### Q3 2027 — Insurance & Markets
- 📅 InsurancePool — community-backed insurance
- 📅 PrivateInsurance — P2P insurance and derivatives
- 📅 SealedBidAuction — confidential bidding

### Q4 2027 — Compliance & Identity
- 📅 ComplianceModule — ZK-based KYC/AML verification
- 📅 RevenueShare — confidential revenue distribution
- 📅 Payroll — private recurring payments
- 📅 FlashLoan — uncollateralized flash loans

---

## Phase 5: Maturity (2028+)

- 📅 Cross-chain bridges (xUSD to other chains via atomic swaps)
- 📅 Mobile wallet app (iOS/Android)
- 📅 Institution-grade API (custody, reporting)
- 📅 L2 scaling solution (if needed)
- 📅 Multi-asset collateral (BTC, ETH wrapped to XELIS)
- 📅 Governance v2 — quadratic voting, delegation

---

## Key Metrics Targets

### By end of 2026 (Mainnet launch)
- 50+ active price providers
- $100k+ TVL in VaultEngine
- $500k+ daily volume on VaultSwap
- VLT circulating supply: ~9.5M (5% burned)

### By end of 2027
- 200+ active price providers
- $5M+ TVL
- $2M+ daily volume
- 3+ active price feeds (XEL/USD, XAU/USD, EUR/USD)
- VLT circulating supply: ~7M (30% burned)

### By end of 2028
- 500+ active price providers
- $50M+ TVL
- $10M+ daily volume
- 10+ active price feeds
- VLT circulating supply: ~5M (50% burned)

---

## Risk Factors

Factors that could delay the roadmap:

1. **XELIS protocol upgrades** — XELIS network upgrades may require contract migrations
2. **Audit findings** — Critical bugs may require architecture changes
3. **Regulatory changes** — New regulations may require compliance adjustments
4. **Market conditions** — Bear market could slow adoption
5. **Community engagement** — Provider count depends on community interest

---

## Changelog

### v4.2 (June 2026)
- Replaced MinerOracle with StakedOracle (permissionless providers)
- Added VLTToken with fixed 10M supply + deflationary burn
- Recalibrated rewards: 60% allocation to oracle providers
- Fixed 18 bugs identified in internal audit

### v4.0 (May 2026)
- Initial StakedOracle design (with bugs)

### v3.0 (April 2026)
- MinerOracle — miners as price sources (too restrictive)

### v2.0 (March 2026)
- PriceOracleV2 — multi-source admin-controlled (too centralized)

### v1.0 (February 2026)
- Initial 23-contract architecture
- PriceOracle v1 — single admin-controlled bot

---

*XELIS Vault — Confidential Finance for the Privacy Era*
