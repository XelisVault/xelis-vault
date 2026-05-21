# XELIS Vault

### The First Confidential Lending Protocol on XELIS BlockDAG

Deposit XEL, borrow xUSD, earn yield, and keep everything private — powered by XELIS native Twisted ElGamal homomorphic encryption.

[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Why XELIS Vault?

Every other lending protocol (Aave, Compound, Morpho) operates on fully transparent ledgers. Your collateral, your debt, your liquidation risk — visible to everyone, including MEV bots.

**XELIS Vault changes that.**

Built on XELIS native homomorphic encryption, XELIS Vault is the world's first lending protocol where:
- Your position is **encrypted** — no one sees your collateral or debt
- Your xUSD balance is **private** — encrypted transfers by default
- Your liquidations are **MEV-resistant** — no front-running
- Your savings yield is **confidential** — earn without exposing your wealth

---

## How It Works

```
1. Deposit XEL as collateral    → vault created (encrypted)
2. Borrow xUSD stablecoin       → minted as confidential asset
3. Repay xUSD anytime           → debt reduced (encrypted update)
4. Withdraw XEL                 → collateral released if healthy
```

---

## Smart Contracts

| Contract | Description |
|----------|-------------|
| **VaultEngine** | Core lending — deposit, borrow, repay, withdraw |
| **xUSD** | Private stablecoin — encrypted balances & transfers |
| **PriceOracle** | XEL price feed with timelock |
| **InterestRateModel** | Dynamic kinked interest rates |
| **InsurancePool** | Community protection against bad debt |
| **FlashLoan** | Confidential uncollateralized flash loans |

---

## Progress

| Phase | Status |
|-------|--------|
| **Core Lending** — deposit, borrow, repay, withdraw | ✅ Live on devnet |
| **xUSD Stablecoin** — mint/burn as Confidential Asset | ✅ Live on devnet |
| **Price Oracle** — XEL price feed | ✅ Live on devnet |
| **Interest Rate Model** — kinked rates | ✅ Live on devnet |
| **Insurance Pool** — stake & claim | ✅ Compiled |
| **Flash Loans** — uncollateralized lending | ✅ Compiled |
| **Dashboard** — React UI | 🚧 In progress |
| **TypeScript SDK** | ✅ Built |
| **Liquidation Bot** | ✅ Built |
| **Testnet Launch** | 📅 Next |
| **Mainnet** | 📅 2026 |

---

## Community

XELIS Vault is open-source and community-driven. We believe privacy in DeFi should be accessible to everyone.

**How you can help:**
- **Contribute code** — PRs welcome on contracts, SDK, dashboard, and bot
- **Review security** — audit the contracts, report vulnerabilities
- **Spread the word** — share XELIS Vault with your community
- **Build on top** — create tools, integrations, and composable DeFi products
- **Run a node** — help decentralize the XELIS network
- **Translate** — help make XELIS Vault accessible globally
- **Design** — improve the dashboard UX, create educational content

Every contribution, big or small, moves us toward a more private financial future.

---

## Resources

[📄 Whitepaper](docs/WHITEPAPER.md)
·
[🗺️ Roadmap](docs/ROADMAP.md)
·
[🏗️ Architecture](docs/ARCHITECTURE.md)
·
[🌐 XELIS Blockchain](https://xelis.io)

---

*XELIS Vault — Confidential Lending for the Privacy Era*
