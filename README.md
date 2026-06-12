# XELIS Vault

### *The First Confidential Financial Platform on XELIS BlockDAG*

Deposit XEL, borrow xUSD, trade on **VaultSwap** (custom AMM with PSM), tokenize real-world assets, manage treasuries, lend peer-to-peer, and govern privately — all secured by native Twisted ElGamal homomorphic encryption on the XELIS BlockDAG.

[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Testnet](https://img.shields.io/badge/Testnet-Deployed-blue)](https://testnet-explorer.xelis.io/)

---

## Why XELIS Vault?

Every other DeFi platform operates on fully transparent ledgers. Your positions, your strategies, your holdings — visible to everyone, including bots, competitors, and regulators.

**XELIS Vault changes that.**

Built on XELIS native homomorphic encryption, XELIS Vault is the first platform where:

- Your **lending position** is encrypted — nobody sees your collateral or debt
- Your **stablecoin balance** is private — encrypted transfers by default
- Your **treasury** is confidential — only authorized signers see balances
- Your **auction bids** are sealed — no front-running, no sniping
- Your **compliance** is zero-knowledge — prove eligibility without revealing identity
- Your **trades** are settled on a custom AMM with built-in peg stability
- Your **governance** is decentralized — VLT holders control protocol parameters

---

## What We're Building

XELIS Vault is a complete suite of **23 smart contracts** covering every major DeFi primitive — all with built-in confidentiality via XELIS native Twisted ElGamal encryption.

### Core Lending

| Product | Description |
|---------|-------------|
| **VaultEngine** | Overcollateralized lending: deposit XEL, borrow xUSD (50% LTV max) |
| **xUSD Stablecoin** | Confidential stablecoin minted one-to-one against XEL collateral |
| **PriceOracle** | XEL price feed with timelock, callable from any contract |
| **InterestRateModel** | Kinked interest rates (80% utilization kink) |
| **Redemption** | Fair-queue arbitrage mechanism that keeps xUSD pegged to $1 |
| **FlashLoan** | Uncollateralized flash loans with reentrancy protection |
| **FlashCallback** | Reusable callback template for flash loan receivers |

### VaultSwap — Custom AMM + PSM

| Product | Description |
|---------|-------------|
| **VaultSwap** | Multi-pool AMM (constant product x*y=k) with integrated **Peg Stability Module** for xUSD. Supports xUSD/XEL (PSM-enabled) and VLT/XEL pools. Protocol revenue from swap fees (0.3%), PSM mint fees (0.5%), and PSM redeem fees (0.1%). |

### Financial Markets

| Product | Description |
|---------|-------------|
| **LendingMarket** | Multi-pool, multi-collateral private lending marketplace |
| **PeerLoan** | Bilateral confidential P2P loans with custom terms |
| **SyndicatePool** | Multi-lender, single-borrower syndicated credit pools |
| **SealedBidAuction** | Confidential bidding with commit/reveal/settle |

### Tokenization & Treasury

| Product | Description |
|---------|-------------|
| **AssetVault** | Standard template for issuing confidential RWA tokens |
| **TreasuryVault** | Multi-signature confidential treasury management |
| **RevenueShare** | Confidential revenue distribution to holders |
| **Payroll** | Private recurring payments with time-based accrual |

### Insurance & Derivatives

| Product | Description |
|---------|-------------|
| **InsurancePool** | Community-backed insurance pool (stake → earn premiums → claim) |
| **PrivateInsurance** | Peer-to-peer insurance and derivatives markets |

### Savings

| Product | Description |
|---------|-------------|
| **SavingsRate** | Earn yield on xUSD deposits with adjustable APY |

### Compliance & Governance

| Product | Description |
|---------|-------------|
| **ComplianceModule** | ZK-based KYC/AML verification layer (MiCA/MiFID compatible) |
| **VLT Token** | Governance token (10M supply, confidential asset) |
| **GovernanceVault** | Stake VLT, earn boosted voting power, control protocol parameters |
| **Timelock** | Configurable delay on all parameter changes with emergency override |

---

## xUSD Peg Mechanism

xUSD is designed to trade at $1 through four mechanisms:

- **Redemption** (primary) — Anyone can burn xUSD and claim XEL at face value via a fair queue. When xUSD trades below $1, arbitrageurs buy and redeem for profit.
- **VaultSwap PSM** (secondary) — Deposit XEL → mint xUSD at oracle price (0.5% fee), or redeem xUSD → receive XEL (0.1% fee). Maintains peg without relying on external DEX liquidity.
- **Borrow arbitrage** — When xUSD trades above $1, vault holders can borrow xUSD at face value and sell it for profit.
- **Overcollateralization** — Every xUSD is backed by at least $1.50 of XEL collateral.
- **Savings Rate** — Adjustable APY incentivizes holding or spending.

---

## VaultSwap Revenue Model

| Fee | Rate | Recipient |
|-----|------|-----------|
| **Swap fee** | 0.3% | 0.25% to LP providers, **0.05% to protocol treasury** |
| **PSM mint fee** | 0.5% | **Protocol treasury** |
| **PSM redeem fee** | 0.1% | **Protocol treasury** |

Protocol revenue is collected in the input token and sent to the treasury address. Fees are configurable by governance.

---

## Governance (VLT)

- **VLT** is the governance token (10M supply, confidential asset).
- **GovernanceVault**: stake VLT, earn up to 2x voting power via timelock commitments.
- VLT holders control: collateral ratios, liquidation penalties, interest rate parameters, asset whitelist, oracle sources, compliance verifiers.
- All parameter changes pass through a configurable **Timelock**.

---

## Current Status

| Milestone | Status |
|-----------|--------|
| **23 Smart Contracts** — all written, compiled, security-audited | ✅ Complete |
| **Core Contracts Testnet** — PriceOracle, xUSD, VaultEngine deployed & verified | ✅ Complete |
| **Core Flow Tested** — deposit, borrow, repay, withdraw, redeem, liquidate all pass | ✅ Complete |
| **Non-Core Contracts** — 14 contracts deployed, emergency_withdraw verified | ✅ Complete |
| **Governance** — Timelock v4, Governor v3, GovernanceVault deployed & cross-configured | ✅ Complete |
| **VaultSwap AMM+PSM** — custom contract written, ready for deployment | 🚧 Compiled |
| **TypeScript SDK** | ✅ Built |
| **Liquidation Bot** | ✅ Built |
| **Price Bot** — oracle price keeper | ✅ Running |
| **Dashboard (React)** | 🚧 In progress |
| **Full Testnet Deployment** (all 23 contracts) | 🚧 In progress |
| **Mainnet Launch** | 📅 Q3 2026 |

---

## Documentation

- [📄 Whitepaper](docs/WHITEPAPER.md) — Full technical specification
- [🗺️ Roadmap](docs/ROADMAP.md) — Development timeline and current sprint
- [🏗️ Architecture](docs/ARCHITECTURE.md) — System design and contract dependencies

---

## Community

XELIS Vault is open-source and community-driven. Privacy in finance should be accessible to everyone.

- **Build** — PRs welcome on contracts, SDK, dashboard, CLI, and bot
- **Security** — Review contracts, report vulnerabilities
- **Translate** — Help make XELIS Vault accessible globally
- **Run a node** — Help decentralize the XELIS network

---

## Links

[![GitHub](https://img.shields.io/badge/GitHub-XelisVault-181717)](https://github.com/XelisVault/xelis-vault)
[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)

---

*XELIS Vault — Confidential Finance for the Privacy Era*
