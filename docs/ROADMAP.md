# XELIS Vault — Roadmap

> *Last updated: May 31, 2026*

---

## Legend

- ✅ **Done** — Deployed and/or verified
- 🔧 **In progress** — Currently being actively worked on
- 📅 **Planned** — Scheduled for future iteration

---

## Phase 0: Contracts & Compilation ✅

| Task | Status |
|------|--------|
| Whitepaper v2 | ✅ |
| Architecture docs | ✅ |
| All 19 smart contracts (core, markets, treasury, compliance, governance) | ✅ Written |
| Compilation & static analysis (18+ syntax bugs fixed) | ✅ |
| Comprehensive bug audit (24 bugs: 7 critical, 8 elevated, 6 medium, 3 minor) | ✅ Complete |

All contracts compile cleanly. All 24 bugs identified and catalogued.

---

## Phase 0.5: Bug Fix Sprint ✅

| Task | Status |
|------|--------|
| Identify root cause of VM storage failure (syscall ID mismatch) | ✅ |
| Rewrite silex-cli stdlib to match daemon's `build_environment()` exactly | ✅ |
| Fix xstd registration order (remove iterator for V0) | ✅ |
| Fix Ciphertext method name (generate vs new) | ✅ |
| Remove extra compiler stubs causing ID shift | ✅ |
| Match ScheduledExecution registration order | ✅ |

**Root cause (resolved):** All native functions in XELIS VM share a single flat `Vec<NativeFunction>`. The syscall ID is simply the index in this vector. When the compiler and daemon registered functions in different orders, the resulting bytecode had wrong syscall IDs. The silex-cli environment is now byte-for-byte identical to the daemon's `build_environment()` for V0.

---

## Phase 1: Core Lending Deployment on Testnet 🔧

| Task | Status |
|------|--------|
| Deploy PriceOracle to testnet (with `invoke`, constructor ran) | ✅ |
| Create xUSD confidential asset on testnet | ✅ |
| Deploy VaultEngine to testnet (with `invoke`, hook confirmed) | ✅ |
| Call `propose_price` on PriceOracle (timelock set) | ✅ |
| Wallet recovery from seed on public testnet | ✅ |
| **Redeploy xUSD with proper hook** (old deploy had no invoke, constructor never ran) | 🔧 In progress |
| Execute oracle price (timelock expired) | 🔧 Next |
| Configure VaultEngine (set_oracle, set_xusd, set_xusd_asset) | 📅 |
| Test deposit → borrow → repay → withdraw lifecycle | 📅 |
| Test redemption path | 📅 |
| Test liquidation path | 📅 |

---

## Phase 2: Full Lending Suite 📅

| Task | Timeline |
|------|----------|
| Deploy InterestRateModel | Next week |
| Deploy InsurancePool + FlashLoan | Next week |
| Deploy remaining 16 contracts to testnet | Next week |
| SDK integration tests | Next week |

---

## Phase 3: Peg, Governance & Markets 📅

| Task | Timeline |
|------|----------|
| XELIS Forge xUSD/XEL pool | Week after lending live |
| VLT token deployment (10M confidential asset) | Week after lending live |
| GovernanceVault + Timelock | Week after lending live |
| Private Lending Marketplace | Week after lending live |
| Peer-to-Peer Lending | Week after lending live |
| Sealed-Bid Auctions | Week after lending live |

---

## Phase 4: Institutional 📅

| Task | Timeline |
|------|----------|
| Compliance Module (ZK KYC/AML) | Week 6 |
| Syndicated Loans | Week 6 |
| Treasury Vault (multi-sig) | Week 7 |
| RWA Tokenization Standard (AssetVault) | Week 7 |

---

## Phase 5: Expansion 📅

| Task | Timeline |
|------|----------|
| Revenue Sharing | Week 8 |
| Private Payroll | Week 8 |
| Private Insurance | Week 9 |
| Multi-Collateral Support | Week 9 |

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

## Phase 7: XelisVault Messenger 1.0 📅

| Task | Timeline |
|------|----------|
| 1-to-1 encrypted messaging contract | Q4 2026 |
| Payment+message bundling | Q4 2026 |
| Proof-of-delivery | Q4 2026 |
| XELIS public key crypto integration | Q4 2026 |

---

## Phase 8: XelisVault Messenger 2.0 📅

| Task | Timeline |
|------|----------|
| Group messaging (50 members) | Q1 2027 |
| Role-based access (admin, mod, member) | Q1 2027 |
| Thread support | Q1 2027 |
| Self-destructing messages | Q1 2027 |

---

## Phase 9: XelisVault Messenger 3.0 📅

| Task | Timeline |
|------|----------|
| DAO governance channels | Q2 2027 |
| Proposal-linked messaging | Q2 2027 |
| VLT-gated access | Q2 2027 |
| Vote-signaling | Q2 2027 |

---

## Phase 10: XelisVault Messenger 4.0 📅

| Task | Timeline |
|------|----------|
| File attachments (IPFS/Arweave) | Q2 2027 |
| Reactions and typing indicators | Q2 2027 |
| Mobile SDK | Q3 2027 |

---

## Current Sprint (May 31)

### Active
- **[Adrien]** Deploy new xUSD with hook=constructor (old xUSD had no invoke)
- **[Adrien]** Execute oracle price (timelock expired)
- **[Adrien]** Configure VaultEngine with oracle + xUSD + xUSD asset addresses

### This Week
- [ ] Deploy new xUSD contract (compiled 815 bytes with hook id=0)
- [ ] Execute price on PriceOracle (call execute_price now that timelock expired)
- [ ] Call set_oracle, set_xusd, set_xusd_asset on VaultEngine
- [ ] Test deposit → borrow → repay → withdraw lifecycle
- [ ] Update GitHub repo with testnet progress (README, roadmap)

### Next Week
- [ ] Deploy InterestRateModel + FlashLoan + InsurancePool
- [ ] Deploy all remaining 16 contracts
- [ ] Full integration testing on testnet
- [ ] SDK updates for testnet addresses

### Coming Up
- [ ] Dashboard MVP
- [ ] Public testnet announcement
- [ ] Bug bounty program
- [ ] XelisVault Messenger design phase

---

[⬅ Back to README](../README.md)
