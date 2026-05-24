# XELIS Vault

### The First Confidential Financial Platform on XELIS BlockDAG

Deposit XEL, borrow xUSD, tokenize real-world assets, manage treasuries, trade privately — all secured by native Twisted ElGamal homomorphic encryption.

[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Why XELIS Vault?

Every other platform operates on fully transparent ledgers. Your positions, your strategies, your holdings — visible to everyone.

**XELIS Vault changes that.**

Built on XELIS native homomorphic encryption, XELIS Vault is the first platform where:
- Your **lending position** is encrypted — no one sees your collateral or debt
- Your **stablecoin balance** is private — encrypted transfers by default
- Your **treasury** is confidential — only authorized signers see balances
- Your **auction bids** are sealed — no front-running, no sniping
- Your **compliance** is zero-knowledge — prove eligibility without revealing identity
- Your **governance** is decentralized — VLT holders control protocol parameters

---

## Products

| Product | Description | Status |
|---------|-------------|--------|
| **Confidential Lending** | Overcollateralized loans with private positions | ✅ Compiled |
| **xUSD Stablecoin** | Privacy-preserving stablecoin | ✅ Compiled |
| **Redemption** | Fair-queue XEL redemption for peg | ✅ Compiled |
| **Private Marketplace** | Multi-pool, multi-collateral lending | ✅ Compiled |
| **RWA Tokenization** | Standard for private real-world asset tokens | ✅ Compiled |
| **Treasury Vault** | Confidential multi-sig for DAOs/institutions | ✅ Compiled |
| **Peer Loans** | Bilateral confidential lending | ✅ Compiled |
| **Syndicated Loans** | Multi-lender credit pools | ✅ Compiled |
| **Sealed-Bid Auctions** | Confidential bidding with reveal window | ✅ Compiled |
| **Compliance Layer** | KYC/AML verification with address dedup | ✅ Compiled |
| **Governance (VLT)** | Token-based protocol governance | ✅ Compiled |

---

## Smart Contracts

| Contract | Type | Description | Status |
|----------|------|-------------|--------|
| **VaultEngine** | Core | Deposit, borrow, repay, withdraw, liquidate, redeem | ✅ 380 LOC |
| **xUSD** | Core | Confidential stablecoin (mint/burn/transfer with self-xfer guard) | ✅ |
| **PriceOracle** | Core | XEL price feed via contract call | ✅ |
| **InterestRateModel** | Core | Dynamic kinked interest rates | ✅ |
| **LendingMarket** | Market | Multi-pool lending with individual borrow positions | ✅ |
| **PeerLoan** | Market | Bilateral P2P loans | ✅ |
| **SyndicatePool** | Market | Syndicated credit pools | ✅ |
| **SealedBidAuction** | Market | Confidential auctions with bid/reveal/settle | ✅ |
| **AssetVault** | Tokenization | RWA token standard with revaluation | ✅ |
| **TreasuryVault** | Treasury | Multi-sig treasury | ✅ |
| **RevenueShare** | Treasury | Revenue distribution with holder tracking | ✅ |
| **Payroll** | Treasury | Recurring payments with time-based accrual | ✅ |
| **InsurancePool** | Insurance | Community insurance with member tracking | ✅ |
| **PrivateInsurance** | Insurance | P2P risk markets with dedup join | ✅ |
| **FlashLoan** | Core | Confidential flash loans | ✅ |
| **ComplianceModule** | Compliance | KYC/AML with address-indexed records | ✅ |
| **VLT** | Governance | Governance token (create/mint/burn/transfer) | ✅ |
| **GovernanceVault** | Governance | Staking & voting with absolute locktopo | ✅ |
| **Timelock** | Governance | 48h execution delay with reentrancy protection | ✅ |

---

## How It Works

### 1. Deposit XEL → Mint xUSD

1. **Deposit** XEL into VaultEngine (privacy-preserving).
2. **Borrow** xUSD up to 50% LTV (configurable).
3. **Interest** is dynamic based on utilization via InterestRateModel.
4. **Repay** xUSD → unlock your XEL collateral.
5. If LTV > max, anyone can **liquidate** — repays xUSD, claims discounted collateral.

### 2. xUSD Peg

- xUSD is minted one-to-one when borrowing against XEL.
- **Redemption**: anyone can burn xUSD and claim XEL at face value (1 xUSD = 1 XEL worth of collateral) via a fair queue.
- Excess demand for XEL creates an arbitrage: buy cheap xUSD → redeem → sell XEL (or vice versa).

### 3. Sealed-Bid Auctions

1. **Bid**: commit a hash of your bid + deposit during the bidding window.
2. **Reveal**: submit your actual bid during the reveal window.
3. **Settle**: winner pays their bid amount, seller receives funds.
4. No one sees your bid until you reveal it — no front-running.

### 4. Governance & Treasury

- **VLT** is the governance token (10M supply, confidential asset).
- **GovernanceVault**: stake VLT, earn boosted voting power (up to 2x via timelock).
- **Timelock**: 48h delay on all parameter changes.
- **TreasuryVault**: multi-sig for DAO funds with configurable signers.
- **RevenueShare**: distribute protocol revenue to VLT stakers.

### 5. Compliance

- **ComplianceModule**: stores KYC/AML records indexed by wallet address.
- Addresses are de-duplicated (one record per address).
- The `is_accredited` check calls the underlying `is_kyc_valid` function.
- All privacy-preserving: compliance is verified without on-chain identity.

---

## Bug Fixes Applied (Static Analysis + Compilation)

| # | Bug | File | Fix |
|---|-----|------|-----|
| 1 | `last_update_topo = vault_id` | VaultEngine | Changed to `get_current_topoheight()` |
| 2 | AssetVault division guard missing | AssetVault | Added `total_shares > 0` check in `buy_shares` |
| 3 | RevenueShare `asset_hash` used instead of `Hash::zero()` | RevenueShare | All distributions use `Hash::zero()` |
| 4 | InsurancePool claim didn't transfer XEL | InsurancePool | Added `transfer(caller, amount, Hash::zero())` |
| 5 | GovernanceVault `locked_until` stored days | GovernanceVault | Changed to absolute `locked_until_topo` using `BLOCKS_PER_DAY` |
| 6 | Timelock `Contract::call` before state save | Timelock | Moved call after `executed = true` |
| 7 | InterestRateModel precision | InterestRateModel | Uses bps-based calculations |
| 8 | LendingMarket repay used `-=` instead of `+=` | LendingMarket | Repay now adds to liquidity |
| 9 | SealedBidAuction hardcoded `1u64` transfer | SealedBidAuction | Uses `asset_amount` field |
| 10 | SealedBidAuction `withdraw_bid` after end | SealedBidAuction | Added `reveal_end_topo` window |
| 11 | PrivateInsurance join dedup missing | PrivateInsurance | Added `get_member_key()` check |
| 12 | xUSD `transfer_tokens` sent to caller | xUSD/VLT | Changed `transfer(to, amount, hash)` |
| 13 | VLT `burn` conflicts with builtin | VLT | Renamed to `burn_vlt` |
| 14 | `Hash::from_u256(u64)` no cast | SealedBidAuction | Added `as u256` cast |
| 15 | `null` not valid for MaxSupplyMode | VLT/xUSD/AssetVault | Replaced with `MaxSupplyMode::None` |
| 16 | State save before external call (reentrancy) | FlashLoan/Payroll/RevenueShare | Moved `ws.store()` before `transfer()` |
| 17 | `let mut` not valid in Silex | All contracts | Changed to `let` (vars are mutable by default) |
| 18 | entry called from another entry | ComplianceModule | Extracted `is_kyc_valid` as `fn` |

---

## Progress

| Phase | Status |
|-------|--------|
| **19 Smart Contracts** — all compiled, bug-fixed, hex generated | ✅ Complete |
| **Core Lending** — deposit, borrow, repay, withdraw, liquidate | ✅ Compiled |
| **xUSD Stablecoin** — mint/burn with self-xfer guard | ✅ Compiled |
| **Redemption** — fair-queue XEL↔xUSD pivot | ✅ Compiled |
| **Price Oracle** | ✅ Compiled |
| **Interest Rate Model** | ✅ Compiled |
| **Insurance Pool** | ✅ Compiled |
| **Flash Loans** — reentrancy-safe | ✅ Compiled |
| **Sealed-Bid Auctions** — bid/reveal/settle | ✅ Compiled |
| **Lending Marketplace** — borrow positions tracked | ✅ Compiled |
| **RWA Tokenization** — AssetVault + revaluation | ✅ Compiled |
| **Treasury Vault** + Revenue Share + Payroll | ✅ Compiled |
| **Compliance Module** — address-indexed KYC | ✅ Compiled |
| **VLT + GovernanceVault + Timelock** | ✅ Compiled |
| **Dashboard** | 🚧 In progress |
| **TypeScript SDK** | ✅ Built |
| **Liquidation Bot** | ✅ Built |
| **Devnet Deployment** |🚧 In progress|
| **Testnet Launch** | 📅 Post-VM-fix |
| **Mainnet** | 📅 Q3 2026 |

---

## Documentation

- [📄 Whitepaper](docs/WHITEPAPER.md) — Full technical specification
- [🗺️ Roadmap](docs/ROADMAP.md) — Development timeline
- [🏗️ Architecture](docs/ARCHITECTURE.md) — System design

---

## Community

XELIS Vault is open-source and community-driven. Privacy in finance should be accessible to everyone.

**How to contribute:**
- **Code** — PRs welcome on contracts, SDK, dashboard, CLI, and bot
- **Security** — Review contracts, report vulnerabilities
- **Build** — Create tools, integrations, and composable products
- **Translate** — Help make XELIS Vault accessible globally
- **Design** — Improve UX, create educational content
- **Run a node** — Help decentralize the XELIS network

---

## Links

[![GitHub](https://img.shields.io/badge/GitHub-XelisVault-181717)](https://github.com/XelisVault/xelis-vault)
[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)

---

*XELIS Vault — Confidential Finance for the Privacy Era*
