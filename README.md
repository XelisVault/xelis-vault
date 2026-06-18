# XELIS Vault

### *The First Confidential Financial Platform on XELIS BlockDAG*

Deposit XEL, borrow xUSD, trade on **VaultSwap** (custom AMM with PSM), tokenize real-world assets, manage treasuries, lend peer-to-peer, and govern privately — all secured by native Twisted ElGamal homomorphic encryption on the XELIS BlockDAG.

[![XELIS](https://img.shields.io/badge/XELIS-BlockDAG-8B5CF6)](https://xelis.io)
[![License](https://img.shields.io/badge/License-GPL--3.0-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-v4.2-orange)](CHANGELOG.md)

---

## 🆕 What's New in v4.2

XELIS Vault v4.2 introduces a **fundamental architectural redesign** of the oracle system:

- **StakedOracle**: Anyone can become a price provider by staking VLT (not just miners)
- **VLT Token**: Fixed supply of 10M VLT, **deflationary** via 3 burn mechanisms
- **Slashing**: 1% of stake per outlier price (50% burned, 50% treasury)
- **Fair Distribution**: Rewards divided among all valid providers
- **Governance Extension**: Vote to add new feeds (XAU/USD, EUR/USD, etc.)

See [`CHANGELOG.md`](CHANGELOG.md) for the full history.

---

## Why XELIS Vault?

Every other DeFi platform operates on fully transparent ledgers. Your positions, your strategies, your holdings — visible to everyone, including bots, competitors, and regulators.

**XELIS Vault changes that.** Built on XELIS native homomorphic encryption, XELIS Vault is the first platform where:

- Your **lending position** is encrypted — nobody sees your collateral or debt
- Your **stablecoin balance** is private — encrypted transfers by default
- Your **treasury** is confidential — only authorized signers see balances
- Your **auction bids** are sealed — no front-running, no sniping
- Your **compliance** is zero-knowledge — prove eligibility without revealing identity
- Your **trades** are settled on a custom AMM with built-in peg stability
- Your **governance** is decentralized — VLT holders control protocol parameters

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    PRICE PROVIDERS (anyone)                       │
│  Stake VLT → fetch prices from MEXC/CoinEx/CoinGecko → submit    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   StakedOracle.slx (on-chain)                     │
│  - Aggregates submissions (median) every 5 blocks (~25s)         │
│  - Distributes VLT rewards to valid providers                    │
│  - Slashes outliers (1% stake, 50% burned, 50% treasury)         │
│  - Circuit breaker if price moves >20%                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ get_price("XEL/USD")
                               ▼
┌─────────────────┬──────────────────┬─────────────────┬───────────┐
│  VaultEngine    │   VaultSwap      │  SavingsRate    │  PSM      │
│  (lending)      │   (AMM)          │  (yield)        │  (peg)    │
└─────────────────┴──────────────────┴─────────────────┴───────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                  VLTToken.slx (governance token)                  │
│  - 10M fixed supply, deflationary (burn mechanism)                │
│  - 60% allocated to oracle rewards (10 years)                     │
│  - Staked as collateral by price providers                        │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│              OracleGovernance.slx (VLT stakers vote)              │
│  - Add new feeds (XAU/USD for gold, EUR/USD, etc.)                │
│  - Update feed parameters                                         │
│  - Adjust oracle config (rewards, slashing, etc.)                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Smart Contracts (v4.2)

**29 contracts** organized in 12 categories. See [`docs/COMPATIBILITY_TABLE.md`](docs/COMPATIBILITY_TABLE.md) for entry IDs and cross-contract calls.

### Token Layer
| Contract | File | Purpose |
|----------|------|---------|
| **VLTToken** | [`contracts/token/VLTToken.slx`](contracts/token/VLTToken.slx) | Governance token, 10M fixed supply, deflationary |
| **xUSD** | [`contracts/usd/xUSD.slx`](contracts/usd/xUSD.slx) | Stablecoin pegged to $1 USD via PSM + overcollateralization |

### Oracle Layer
| Contract | File | Purpose |
|----------|------|---------|
| **StakedOracle** | [`contracts/oracle/StakedOracle.slx`](contracts/oracle/StakedOracle.slx) | Decentralized oracle based on VLT staking + slashing |
| **InterestRateModel** | [`contracts/interest/InterestRateModel.slx`](contracts/interest/InterestRateModel.slx) | Kinked interest rate model for LendingMarket |

### Governance Layer
| Contract | File | Purpose |
|----------|------|---------|
| **OracleGovernance** | [`contracts/governance/OracleGovernance.slx`](contracts/governance/OracleGovernance.slx) | VLT holders vote to add/modify feeds |
| **GovernanceVault** | [`contracts/governance/GovernanceVault.slx`](contracts/governance/GovernanceVault.slx) | VLT staking for voting power + rewards |
| **Governor** | [`contracts/governance/Governor.slx`](contracts/governance/Governor.slx) | On-chain governance proposals + voting |
| **Timelock** | [`contracts/governance/Timelock.slx`](contracts/governance/Timelock.slx) | 48h delay on all parameter changes |
| **GuardianMultisig** | [`contracts/governance/GuardianMultisig.slx`](contracts/governance/GuardianMultisig.slx) | Emergency pause multisig (security) |

### Core Lending
| Contract | File | Purpose |
|----------|------|---------|
| **VaultEngineV3** | [`contracts/vault/VaultEngineV3.slx`](contracts/vault/VaultEngineV3.slx) | Overcollateralized lending (XEL collateral, xUSD borrow) |
| **LendingMarket** | [`contracts/lending/LendingMarket.slx`](contracts/lending/LendingMarket.slx) | Multi-pool multi-collateral lending marketplace |
| **PeerLoan** | [`contracts/lending/PeerLoan.slx`](contracts/lending/PeerLoan.slx) | Bilateral P2P loans with custom terms |
| **SyndicatePool** | [`contracts/lending/SyndicatePool.slx`](contracts/lending/SyndicatePool.slx) | Multi-lender syndicated credit pools |

### AMM & PSM
| Contract | File | Purpose |
|----------|------|---------|
| **VaultSwapV2** | [`contracts/amm/VaultSwapV2.slx`](contracts/amm/VaultSwapV2.slx) | AMM with MEV protection (XEL/VLT, etc.) |
| **PSM** | [`contracts/amm/PSM.slx`](contracts/amm/PSM.slx) | Peg Stability Module — mint/redeem xUSD at $1 oracle price |

### Savings & Flash Loans
| Contract | File | Purpose |
|----------|------|---------|
| **SavingsRate** | [`contracts/savings/SavingsRate.slx`](contracts/savings/SavingsRate.slx) | Earn adjustable APY on xUSD deposits |
| **FlashLoan** | [`contracts/flashloan/FlashLoan.slx`](contracts/flashloan/FlashLoan.slx) | Uncollateralized flash loans with reentrancy guard |
| **FlashCallback** | [`contracts/flashloan/FlashCallback.slx`](contracts/flashloan/FlashCallback.slx) | Template for flash loan receivers |

### Auctions
| Contract | File | Purpose |
|----------|------|---------|
| **SealedBidAuction** | [`contracts/auction/SealedBidAuction.slx`](contracts/auction/SealedBidAuction.slx) | Confidential sealed-bid auctions (commit-reveal) |

### RWA & Treasury
| Contract | File | Purpose |
|----------|------|---------|
| **AssetVault** | [`contracts/rwa/AssetVault.slx`](contracts/rwa/AssetVault.slx) | Template for issuing confidential RWA tokens |
| **TreasuryVault** | [`contracts/treasury/TreasuryVault.slx`](contracts/treasury/TreasuryVault.slx) | Multi-signature confidential treasury management |
| **RevenueShare** | [`contracts/revenue/RevenueShare.slx`](contracts/revenue/RevenueShare.slx) | Confidential revenue distribution to holders |
| **Payroll** | [`contracts/payroll/Payroll.slx`](contracts/payroll/Payroll.slx) | Private recurring payments with time-based accrual |

### Insurance
| Contract | File | Purpose |
|----------|------|---------|
| **InsurancePool** | [`contracts/insurance/InsurancePool.slx`](contracts/insurance/InsurancePool.slx) | Community-backed insurance pool (stake → earn premiums) |
| **PrivateInsurance** | [`contracts/insurance/PrivateInsurance.slx`](contracts/insurance/PrivateInsurance.slx) | P2P insurance and derivatives markets |

### Compliance
| Contract | File | Purpose |
|----------|------|---------|
| **ComplianceModule** | [`contracts/compliance/ComplianceModule.slx`](contracts/compliance/ComplianceModule.slx) | ZK-based KYC/AML verification layer (MiCA/MiFID compatible) |

### Testnet Infrastructure
| Contract | File | Purpose |
|----------|------|---------|
| **FaucetContract** | [`contracts/faucet/FaucetContract.slx`](contracts/faucet/FaucetContract.slx) | Testnet faucet with anti-abuse (100 XEL + 200 VLT per 24h) |

### Infrastructure
| Contract | File | Purpose |
|----------|------|---------|
| **ContractRegistry** | [`contracts/proxy/ContractRegistry.slx`](contracts/proxy/ContractRegistry.slx) | Versioned registry for upgrade pattern |
| **Upgradeable** | [`contracts/proxy/Upgradeable.slx`](contracts/proxy/Upgradeable.slx) | Template mixin for upgrade-aware contracts |

### Scripts (off-chain)
| Script | File | Purpose |
|--------|------|---------|
| **price_provider.py** | [`scripts/price_provider.py`](scripts/price_provider.py) | Run by price providers to submit prices |
| **aggregation_keeper.py** | [`scripts/aggregation_keeper.py`](scripts/aggregation_keeper.py) | Triggers aggregation every block |

---

## VLT Token Economics

### Distribution (10,000,000 VLT fixed supply)

| Allocation | % | Amount | Vesting |
|------------|---|--------|---------|
| **Oracle Rewards** | **60%** | **6,000,000 VLT** | Distributed over 10 years |
| Team | 15% | 1,500,000 VLT | 4 years, 1 year cliff |
| Treasury | 12% | 1,200,000 VLT | Governance-controlled |
| DEX Liquidity | 10% | 1,000,000 VLT | VaultSwap pools |
| Airdrop | 2% | 200,000 VLT | 1 year post-mainnet |
| Bug Bounty | 1% | 100,000 VLT | Perpetual |

### Deflation Mechanism

VLT is **deflationary** through 3 burn sources:

1. **50% of protocol fees** burned (swap, PSM, borrow, redemption fees)
2. **50% of slashing** burned (when providers submit bad prices)
3. **Governance burn** (optional, quorum 15%)

**Projected supply**:
- Year 0: 10.0M VLT
- Year 5: ~6.0M VLT
- Year 10: ~3.0M VLT (supply divided by 3)

### Oracle Rewards Calibration

- Block time: **5 seconds** (XELIS BlockDAG)
- 17,280 blocks/day → 3,456 cycles/day (1 cycle = 5 blocks = 25s)
- Budget: 6M VLT / 10 years = 1,644 VLT/day
- `REWARD_PER_CYCLE = 0.48 VLT` (= 47,564,687 atomic units)
- With 50 active providers: 33 VLT/day each → ROI ~30 days

---

## StakedOracle — How It Works

### Anyone Can Be a Price Provider

Unlike traditional oracles (Chainlink, Pyth) that require permissioned node operators, XELIS Vault's StakedOracle is **permissionless**: anyone can become a provider by staking 1,000 VLT.

### Anti-Sybil via Staking

To submit a price, you must be a registered provider with stake ≥ MIN_STAKE. An attacker wanting to create 1,000 bots to manipulate the median would need to stake 1,000,000 VLT (10% of total supply) — economically infeasible.

### Reward Distribution

Every cycle (25 seconds), the oracle:
1. Collects all submissions from active providers
2. Sorts prices and computes the **median**
3. Identifies **valid prices** (within 5% of median)
4. Distributes `REWARD_PER_CYCLE / n_valid` VLT to each valid provider
5. **Slashes outliers**: 1% of stake (50% burned, 50% to treasury)

### Slashing Math

- Default slash: 1% of stake per outlier (= 10 VLT on a 1,000 VLT stake)
- If stake falls below MIN_STAKE after cumulative slashes → provider auto-deactivated
- No slashing if you submit a valid price (within 5% of median)
- Slashing is deterministic and transparent

---

## Quick Start

### 🚀 One-Command Install (Linux / macOS / Windows)

The easiest way to get started — the installer does everything for you:

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python3
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python
```

The installer will:
1. ✅ Detect your OS and architecture
2. ✅ Install XELIS daemon/wallet/miner if needed (from source, precompiled, or Docker)
3. ✅ Help you create or import your wallet
4. ✅ Ask what you want to do (provider, user, miner, keeper)
5. ✅ Download and configure the scripts
6. ✅ Install systemd/launchd/Windows services for auto-start
7. ✅ Show you the final instructions (faucet claim, stake, etc.)

**No technical knowledge required** — the installer is 100% interactive and guided.

---

### Manual Setup (advanced)

If you prefer to set things up manually:

#### Get Testnet Funds from Faucet

Once deployed, the Faucet contract distributes:
- **100 XEL testnet** per 24h (enough for transactions)
- **200 VLT** per 24h (enough to stake as provider)

```bash
# Claim both XEL and VLT
xelis_wallet call-contract <FaucetContract> claim_both --signer mywallet
```

Limits:
- Cooldown: 24h between claims per address
- Daily cap: 5000 XEL / 10000 VLT (50 users/day)
- Lifetime cap per address: 1000 XEL / 2000 VLT

#### For Price Providers

```bash
# 1. Get VLT tokens (claim from faucet or buy on VaultSwap)
# 2. Stake 100 VLT (minimum) via StakedOracle
xelis_wallet call-contract StakedOracle register_provider \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 10000000000

# 3. Configure the price provider script
cp scripts/price_provider.py /opt/xelis-vault/
export PROVIDER_ADDRESS=xet1...
export STAKED_ORACLE_CONTRACT=0x...
export XELIS_RPC=http://127.0.0.1:8080

# 4. Run it
python3 /opt/xelis-vault/price_provider.py
```

See [`docs/PROVIDER_GUIDE.md`](docs/PROVIDER_GUIDE.md) for detailed instructions.

#### For Miners

If you also mine XELIS blocks, you can run the aggregation keeper to ensure the oracle stays healthy:

```bash
export STAKED_ORACLE_CONTRACT=0x...
python3 scripts/aggregation_keeper.py
```

#### For Users

Once the oracle is live, you can use XELIS Vault normally:

```bash
# Deposit XEL as collateral (1 XEL = 100000000 atomic)
xelis_wallet call-contract VaultEngine deposit 0x0 100000000

# Borrow xUSD (max 50% LTV)
xelis_wallet call-contract VaultEngine borrow 1 50000000

# Swap on VaultSwap (with slippage protection)
xelis_wallet call-contract VaultSwap swap 0x0 <xUSD_hash> 1000000 990000
```

See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for the full user guide.

---

## Documentation

- [📄 Whitepaper v3](docs/WHITEPAPER.md) — Full technical specification
- [🗺️ Roadmap](docs/ROADMAP.md) — Development timeline
- [🏗️ Architecture](docs/ARCHITECTURE.md) — System design and contract interactions
- [🔧 Testnet Deployment Guide](docs/TESTNET_DEPLOYMENT.md) — Deploy on XELIS testnet
- [⚙️ Provider Guide](docs/PROVIDER_GUIDE.md) — Become a price provider
- [⛏️ Miner Guide](docs/MINER_GUIDE.md) — Configure xelis_miner + keeper
- [📋 Audit Report](docs/AUDIT.md) — Internal audit v4.2
- [🔄 Upgrade Pattern](docs/UPGRADE.md) — How contract upgrades work

---

## Current Status

| Milestone | Status |
|-----------|--------|
| **VLTToken v4.2** — fixed supply, deflationary | ✅ Complete |
| **StakedOracle v4.2** — staking + slashing + rewards | ✅ Complete |
| **OracleGovernance** — feed management via vote | ✅ Complete |
| **VaultEngineV3** — confidential lending with Ciphertext | ✅ Complete |
| **VaultSwapV2** — AMM + PSM with MEV protection | ✅ Complete |
| **ContractRegistry** — versioned upgrade pattern | ✅ Complete |
| **price_provider.py** — tested with live MEXC/CoinEx/CoinGecko | ✅ Complete |
| **aggregation_keeper.py** — keeps oracle healthy | ✅ Complete |
| **Testnet deployment** | 🚧 In progress |
| **External security audit** | 📅 Q3 2026 |
| **Mainnet launch** | 📅 Q4 2026 |

---

## Community

XELIS Vault is open-source and community-driven. Privacy in finance should be accessible to everyone.

- **Build** — PRs welcome on contracts, scripts, dashboard, SDK
- **Security** — Review contracts, report vulnerabilities to `security@xelisvault.io`
- **Become a provider** — Stake VLT and earn rewards by providing accurate prices
- **Translate** — Help make XELIS Vault accessible globally

### Links

- [GitHub](https://github.com/XelisVault/xelis-vault)
- [XELIS BlockDAG](https://xelis.io)
- [XELIS Documentation](https://docs.xelis.io)
- [XELIS Forge](https://github.com/XELIS-Forge) — production smart contract examples

---

## License

All smart contracts and scripts are licensed under **GNU General Public License v3.0** (GPL-3.0) — consistent with the XELIS ecosystem.

---

## Security Disclaimer

These contracts are provided as-is. While extensive internal audits have been performed (see [`docs/AUDIT.md`](docs/AUDIT.md)), **no external audit has been completed yet**. Do not deploy to mainnet without:

- Comprehensive external security audit (Trail of Bits, OpenZeppelin, Hacken)
- Extensive testnet testing (>3 months)
- Bug bounty program (Immunefi recommended)
- Community review

**Never deploy with funds you cannot afford to lose.**

---

*XELIS Vault — Confidential Finance for the Privacy Era*
