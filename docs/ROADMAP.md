# XELIS Vault — Roadmap

> *Last updated: June 12, 2026*

---

## Legend

- ✅ **Done** — Deployed and/or verified on testnet
- 🔧 **In progress** — Currently being actively worked on
- 📅 **Planned** — Scheduled for future iteration

---

## Phase 0: Contracts & Compilation ✅

| Task | Status |
|------|--------|
| Whitepaper v2 | ✅ |
| Architecture docs | ✅ |
| All 23 smart contracts (core, pools, markets, treasury, compliance, governance, savings) | ✅ Written |
| Compilation & static analysis | ✅ |
| Comprehensive security audit (critical, high, medium bugs fixed) | ✅ Complete |
| Emergency withdraw pattern on all contracts | ✅ Complete |

---

## Phase 1: Core Lending Testnet ✅

| Task | Status |
|------|--------|
| Deploy PriceOracle (with `invoke`, constructor ran) | ✅ |
| Create xUSD confidential asset | ✅ |
| Deploy VaultEngine (with `invoke`, hook confirmed) | ✅ |
| Propose & execute oracle price | ✅ |
| Configure VaultEngine (set_oracle, set_xusd, set_xusd_asset) | ✅ |
| Fix `mint_tokens` auth (get_caller → get_contract_caller) | ✅ |
| Fix vault ID conflict (COUNTER_KEY=1, not 0) | ✅ |
| Fix redeem while-loop variable corruption (storage workaround) | ✅ |
| Fix all entry returns (non-zero = state rollback) | ✅ |
| Test deposit → borrow → repay → withdraw | ✅ |
| Test redemption path | ✅ |
| Test liquidation path (price manipulation) | ✅ |
| **All core flows verified end-to-end on testnet** | ✅ Complete |

---

## Phase 2: Non-Core Contracts Testnet ✅

| Task | Status |
|------|--------|
| Deploy InterestRateModel | ✅ |
| Deploy FlashLoan + FlashCallback | ✅ |
| Deploy InsurancePool + PrivateInsurance | ✅ |
| Deploy PeerLoan | ✅ |
| Deploy ComplianceModule | ✅ |
| Deploy AssetVault + TreasuryVault | ✅ |
| Deploy RevenueShare + Payroll | ✅ |
| Deploy SealedBidAuction + SyndicatePool | ✅ |
| Deploy LendingMarket | ✅ |
| Deploy SavingsRate | ✅ |
| Emergency_withdraw functional tests (14/14 passed, 5 wallet nonce races) | ✅ Complete |
| Functional tests on all non-core contracts | ✅ Complete |

---

## Phase 3: Governance Testnet ✅

| Task | Status |
|------|--------|
| Deploy VLT token (10M confidential asset) | ✅ |
| Deploy Timelock v4 (with emergency addresses) | ✅ |
| Deploy Governor v3 (with emergency addresses) | ✅ |
| Deploy GovernanceVault v2 | ✅ |
| Cross-contract configuration (Gov→GV, Gov→TL, TL→Gov) | ✅ |
| VLT.create_asset mints all 10M | ✅ |
| GovernanceVault staking test | ✅ |
| Governor proposal + queue + execute test | ✅ |

---

## Phase 4: VaultSwap (AMM + PSM) 🔧

| Task | Status |
|------|--------|
| **VaultSwap.slx** — custom multi-pool AMM with PSM | ✅ Written & compiled |
| Cross-contract integration (PriceOracle entry 4, xUSD entries 3/5) | ✅ Designed |
| Fee structure (swap 0.3%, PSM mint 0.5%, PSM redeem 0.1%) | ✅ Designed |
| Compile bytecode | ✅ Compiled |
| Deploy to testnet | 🔧 Blocked by syscall ID mismatch |
| Configure (set_oracle, set_xusd, set_treasury) | 📅 |
| Create xUSD/XEL pool with PSM | 📅 |
| Create VLT/XEL pool | 📅 |
| Test add/remove liquidity | 📅 |
| Test swap | 📅 |
| Test PSM mint/redeem | 📅 |

---

## Phase 5: Full Integration 📅

| Task | Timeline |
|------|----------|
| Resolve syscall ID mismatch (compile for public node) | This week |
| Deploy VaultSwap | This week |
| Deploy xUSD+VaultEngine+VLT security fixes (redeploy with emergency) | This week |
| SDK integration tests for all contracts | This week |
| Dashboard MVP | Next week |

---

## Phase 6: Production 📅

| Task | Timeline |
|------|----------|
| Professional Security Audit | Q3 2026 |
| Bug Bounty Program | Q3 2026 |
| Public Testnet Launch | Q3 2026 |
| Mainnet Launch | Q3 2026 |
| Cross-chain xUSD (Trocador) | Q3 2026 |
| Position NFTs (tradeable debt) | Q3 2026 |
| Credit scores (under-collateralized loans) | Q3 2026 |
| Full DAO governance | Q3 2026 |
| Institutional API | Q4 2026 |

---

## Phase 7: VaultSwap Expansion 📅

| Task | Timeline |
|------|----------|
| Multi-hop swaps | Q4 2026 |
| Concentrated liquidity pools | Q4 2026 |
| TWAP oracles | Q4 2026 |
| Yield-bearing LP tokens | Q4 2026 |
| VaultSwap governance (fee voting) | Q4 2026 |

---

## Current Sprint (June 12)

### ✅ Completed
- **VaultSwap.slx** — Full AMM + PSM contract written and compiled
- PSM integration with PriceOracle (entry 4) and xUSD (entries 3/5) designed
- Protocol revenue model finalized (swap 0.3%, PSM mint 0.5%, PSM redeem 0.1%)
- All 8 core contracts updated with emergency withdraw pattern in source
- AGENTS.md updated with complete VaultSwap architecture and entry IDs

### This Week
- [ ] Resolve syscall ID mismatch (public node rejects bytecode with syscall ID 489)
- [ ] Deploy VaultSwap to testnet
- [ ] Configure xUSD.set_psm to point to VaultSwap
- [ ] Create xUSD/XEL pool with initial liquidity
- [ ] Create VLT/XEL pool

### Next Week
- [ ] Deploy security fixes to xUSD, VaultEngine, VLT (emergency_withdraw)
- [ ] Full integration testing of VaultSwap with VaultEngine
- [ ] Dashboard MVP with pool UI
- [ ] SDK updates for VaultSwap

### Coming Up
- [ ] Public testnet announcement
- [ ] Bug bounty program
- [ ] Mainnet launch planning

---

[⬅ Back to README](../README.md)
