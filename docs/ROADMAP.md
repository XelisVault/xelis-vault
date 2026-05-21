# XELIS Vault — Roadmap

> *Last updated: May 2026*

---

## Phase 0: Foundation ✅

| Task | Status |
|------|--------|
| Whitepaper v1 | ✅ |
| Architecture docs | ✅ |
| Smart contract design | ✅ |
| Devnet environment | ✅ |

## Phase 1: Core Vault ✅

| Task | Status |
|------|--------|
| VaultEngine — deposit / borrow / repay / withdraw | ✅ Live on devnet |
| xUSD Confidential Asset — mint & burn | ✅ Live on devnet |
| InterestRateModel — kinked rates | ✅ Live on devnet |
| PriceOracle — XEL price feed | ✅ Live on devnet |
| Deploy & test full lifecycle | ✅ Verified |
| Document VM constraints & workarounds | ✅ Documented |

> **Milestone achieved** — Single-asset lending fully working on devnet with all state mutations persisting correctly.

```
Test results (all passing):
  ✓ deposit(100000) → vault_id=1 created
  ✓ get_vault(1)    → returns VaultSnapshot with collateral=100000
  ✓ borrow(30000)   → borrow_plain updated to 30000
  ✓ repay(10000)    → borrow_plain reduced to 20000
  ✓ withdraw(50000) → collateral_plain reduced by 50000
```

## Phase 2: Yield & Automation 🚧

| Task | Status |
|------|--------|
| Dashboard (React) | 🚧 In progress |
| TypeScript SDK | ✅ Built |
| Liquidation Bot | ✅ Built |
| xUSD Savings Rate | 🔲 |
| Auto-Remining Loans | 🔲 |
| Testnet deployment | 🔲 |

> **Next milestone** — Full lending + savings + automation on testnet

## Phase 3: Launch 📅

| Task | Status |
|------|--------|
| Security audit | 🔲 |
| Bug bounties | 🔲 |
| Mainnet deployment | 🔲 |
| Community launch | 🔲 |
| Forge DEX xUSD/XEL pool | 🔲 |

> **Next milestone** — Live on mainnet with real TVL

## Phase 4: Expansion 📅

| Task | Status |
|------|--------|
| InsurancePool | ✅ Compiled |
| FlashLoan | ✅ Compiled |
| Multi-collateral support | 🔲 |
| Governance VLT token | 🔲 |
| DeFi composability (Forge DEX) | 🔲 |

## Phase 5: Dominance 📅

| Task | Status |
|------|--------|
| Cross-chain xUSD (Trocador) | 🔲 |
| Position NFTs | 🔲 |
| Credit scores | 🔲 |
| Full DAO governance | 🔲 |
| Institutional API | 🔲 |

---

## Legend

- ✅ **Done** — Deployed and verified
- 🚧 **In progress** — Currently being worked on
- 🔲 **Pending** — Not yet started
- 📅 **Planned** — Scheduled for future

---

[⬅ Back to README](../README.md)
