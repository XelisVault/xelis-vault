# XELIS Vault — Privacy-First DeFi on XELIS BlockDAG

> **v5.0** — 33 smart contracts | 630 entry functions | Audit-remediated | MIT License

[![Audit](https://img.shields.io/badge/audit-v5.0%20remediated-success)](docs/AUDIT_v5.0_REMEDIATION.md)
[![Contracts](https://img.shields.io/badge/contracts-33%20Silex-blue)](contracts/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Overview

XELIS Vault is a complete DeFi protocol built on the **XELIS BlockDAG** — a privacy-focused Layer-1 with homomorphic-encrypted balances and native confidential assets. It combines a decentralized stablecoin, a lending engine, an AMM, an oracle network, and on-chain governance into one integrated system.

| Product | Contracts | What it does |
|---------|-----------|--------------|
| **xUSD Stablecoin** | `xUSD`, `PSM`, `VaultEngineV3` | Borrow xUSD against XEL collateral; redeem via PSM at oracle price |
| **Decentralized Oracle** | `StakedOracle`, `XelisVaultMiner` | Median-aggregated price feeds secured by reputation-weighted miners |
| **AMM + PSM** | `VaultSwapV2` | Constant-product AMM with TWAP volatility fees + integrated PSM |
| **Multi-Asset Lending** | `LendingMarket`, `PeerLoan`, `SyndicatePool`, `InterestRateModel` | Permissionless lending pools, P2P loans, syndicated credit |
| **Governance** | `GovernanceVault`, `Governor`, `Timelock`, `GuardianMultisig`, `OracleGovernance` | VLT-staked voting, timelock delay, multisig emergency control |
| **Infrastructure** | `ContractRegistry`, `FlashLoan`, `SealedBidAuction`, `PrivacyMixer`, `VaultChat`, `SavingsRate`, `RevenueShare`, `TreasuryVault`, `InsurancePool`, `PrivateInsurance`, `Payroll`, `FaucetContract`, `AssetVault`, `ComplianceModule`, `MinerPool`, `Upgradeable` | 17 supporting contracts for registry, flash loans, sealed-bid auctions, privacy, encrypted chat, savings, revenue sharing, treasury, insurance, payroll, faucet, RWA vault, compliance, and proxied upgrades |

> Read the [whitepaper](docs/WHITEPAPER.md) for full technical details.

---

## How It Works

### The xUSD Stablecoin

```
         ┌──────────────┐     oracle price      ┌──────────────┐
         │   VaultEngine │◄──────────────────────│ StakedOracle │
         │   (CDP)       │                       │ (price feed) │
         └──────┬───────┘                       └──────────────┘
                │
    deposit XEL │ borrow xUSD
    ↓           │ ↓
         ┌──────┴───────┐     mint/burn xUSD     ┌──────────────┐
         │    xUSD      │◄──────────────────────►│      PSM     │
         │   (token)    │                         │ (stability)  │
         └──────────────┘                         └──────────────┘
                                                      │
                                              mint xUSD │ redeem XEL
                                              at oracle  │ at oracle
                                                      ↓
                                                ┌──────────────┐
                                                │    User      │
                                                │  (you)       │
                                                └──────────────┘
```

1. **Deposit XEL** as collateral into VaultEngine → creates a vault
2. **Borrow xUSD** against your collateral (max ~66% LTV, 2% APR stability fee)
3. **Redeem xUSD for XEL** via PSM at oracle price (0.5% fee) or swap on VaultSwap
4. **Repay** your loan + accrued stability fee to unlock your XEL
5. **Liquidate** if collateral ratio drops below 150%

### The Oracle Network

```
 ┌─────────────┐   submit prices    ┌──────────────┐
 │ Price       │ ─────────────────► │ StakedOracle  │
 │ Providers   │    every 5 blocks  │ (aggregation) │
 │ (miners)    │                    └──────┬───────┘
 └─────────────┘                           │
                                           │ median price
                                           ▼
                                    ┌──────────────┐
                                    │  VaultEngine  │
                                    │  VaultSwap    │
                                    │  LendingMarket│
                                    │  PSM          │
                                    └──────────────┘
```

- **Miner registration** is permissionless: stake 100 VLT, set an endpoint, submit prices
- **Reputation system** (0–10,000): earn points via accurate price submissions and heartbeats; lose points for outliers, offline periods, or malicious data
- **5 reward tiers**: 0× (banned), 0.25× (critical), 0.50× (warning), 1.0× (good), 1.5× (excellent)
- **Circuit breakers**: max deviation (5%), callback threshold (20%), hard stale (100 blocks)
- **Bootstrap mode**: works with just 3 providers, auto-disables when 10+ are active

### The VLT Token

| Metric | Value |
|--------|-------|
| **Total supply** | 10,000,000 VLT |
| **Decimals** | 8 |
| **Rewards pool** | 6,000,000 VLT (60% — 10-year emission schedule) |
| **Team** | 1,500,000 VLT (15% — linear vesting via timelock) |
| **Treasury** | 1,200,000 VLT (12% — protocol-owned liquidity + operations) |
| **DEX liquidity** | 1,000,000 VLT (10% — initial VaultSwap pools) |
| **Airdrop** | 200,000 VLT (2% — community distribution) |
| **Bug bounty** | 100,000 VLT (1% — Immunefi program) |

Max supply is capped at 10,000,000 VLT. No additional minting. The rewards pool is distributed over ~10 years with a dynamic budget factor that auto-adjusts every 2 weeks (2016 blocks) to keep the schedule on track.

### Governance

```
 Proposal → Governor (vote) → Timelock (delay) → Execution
     ↑                            │
     │                     GuardianMultisig
     │                     (emergency override)
     └────────────────────────────────────┘
```

1. **Vote**: Stake VLT in GovernanceVault (365-day lock boost: up to 2× voting power)
2. **Propose**: Any address holding ≥ 100 VLT can submit a proposal
3. **Voting period**: 7 days (120,960 blocks), quorum = 10% of total voting power
4. **Timelock**: 5-day delay (34,560 blocks) between approval and execution
5. **Emergency**: GuardianMultisig (3-of-5 by default) can override via multisig proposals

---

## Architecture

```
                    ┌──────────────────────────┐
                    │     ContractRegistry      │
                    │   (contract lookup table) │
                    └────────┬─────────────────┘
                             │ resolves addresses
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ XelisVault   │   │  StakedOracle │   │  Governance  │
 │ Miner        │   │  (oracle)     │   │  (voting)    │
 │ (services)   │   └──────────────┘   └──────────────┘
 └──────────────┘
      │
      ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │  VLTToken    │──►│ VaultEngine  │──►│    xUSD      │
 │  (governance)│   │ (CDP engine) │   │ (stablecoin) │
 └──────────────┘   └──────┬───────┘   └──────┬───────┘
                           │                  │
                           ▼                  ▼
                    ┌──────────────┐   ┌──────────────┐
                    │  VaultSwap   │◄──│     PSM      │
                    │  (AMM)       │   │ (stability)  │
                    └──────────────┘   └──────────────┘
```

### Contract Map

All 33 contracts with their locations and entry counts:

| # | Contract | File | Entries | Role |
|---|----------|------|---------|------|
| 1 | `ContractRegistry` | `contracts/proxy/` | 12 | On-chain address book |
| 2 | `VLTToken` | `contracts/token/` | 15 | Protocol governance token |
| 3 | `XelisVaultMiner` | `contracts/miner/` | 40 | Miner registration, reputation, rewards |
| 4 | `StakedOracle` | `contracts/oracle/` | 28 | Price feed aggregation |
| 5 | `xUSD` | `contracts/usd/` | 17 | Algorithmic stablecoin |
| 6 | `VaultEngineV3` | `contracts/vault/` | 30 | CDP collateral engine |
| 7 | `PSM` | `contracts/amm/` | 22 | Peg stability module |
| 8 | `VaultSwapV2` | `contracts/amm/` | 40 | Constant-product AMM |
| 9 | `GovernanceVault` | `contracts/governance/` | 21 | VLT staking + voting power |
| 10 | `Governor` | `contracts/governance/` | 14 | Proposal + voting engine |
| 11 | `Timelock` | `contracts/governance/` | 20 | Governance delay |
| 12 | `GuardianMultisig` | `contracts/governance/` | 21 | Multisig emergency control |
| 13 | `OracleGovernance` | `contracts/governance/` | 20 | Oracle parameter governance |
| 14 | `FlashLoan` | `contracts/flashloan/` | 15 | Uncollateralized flash loans |
| 15 | `FlashCallback` | `contracts/flashloan/` | 6 | Flash loan callback interface |
| 16 | `SealedBidAuction` | `contracts/auction/` | 24 | Commit-reveal auction |
| 17 | `PrivacyMixer` | `contracts/privacy/` | 20 | ZK-anonymity pool |
| 18 | `VaultChat` | `contracts/chat/` | 22 | E2E encrypted chat anchoring |
| 19 | `SavingsRate` | `contracts/savings/` | 20 | xUSD savings (5% APY default) |
| 20 | `InsurancePool` | `contracts/insurance/` | 20 | XEL-staked cover pool |
| 21 | `PrivateInsurance` | `contracts/insurance/` | 21 | Private policy insurance |
| 22 | `InterestRateModel` | `contracts/interest/` | 9 | Utilization-rate interest curve |
| 23 | `LendingMarket` | `contracts/lending/` | 24 | Permissionless lending pools |
| 24 | `PeerLoan` | `contracts/lending/` | 20 | P2P collateralized loans |
| 25 | `SyndicatePool` | `contracts/lending/` | 21 | Syndicated loan pools |
| 26 | `RevenueShare` | `contracts/revenue/` | 17 | Revenue distribution to VLT stakers |
| 27 | `FaucetContract` | `contracts/faucet/` | 20 | Testnet faucet |
| 28 | `TreasuryVault` | `contracts/treasury/` | 22 | Multisig protocol treasury |
| 29 | `Payroll` | `contracts/payroll/` | 17 | Recurring per-block payroll |
| 30 | `AssetVault` | `contracts/rwa/` | 16 | Tokenized RWA vault |
| 31 | `ComplianceModule` | `contracts/compliance/` | 16 | KYC/AML compliance layer |
| 32 | `MinerPool` | `contracts/miner/` | 24 | Miner cooperative pools |
| 33 | `Upgradeable` | `contracts/proxy/` | 2 | Proxy migration mixin |

> Full entry ID table: [`docs/ENTRY_IDS.md`](docs/ENTRY_IDS.md)

---

## Security

### Audit

The v5.0 release remediates all **15 vulnerabilities** identified in the v4.3 security audit:

- **5 Critical**: entry ID realignment across all 33 contracts, cross-contract oracle resolution fixes, governance attack vectors closed (GovernanceVault, FlashLoan rewrites)
- **4 High**: GuardianMultisig quorum enforcement, Timelock dual-guardian support, VaultEngine commit-reveal, stability fee implementation
- **4 Medium + 2 Low**: cross-contract entry ID consistency, 2-step emergency withdraw on all contracts (17280-block ≈ 24h delay), division-by-zero guards, reward distribution fixes

Full report: [`docs/AUDIT_v5.0_REMEDIATION.md`](docs/AUDIT_v5.0_REMEDIATION.md)

### Emergency Procedures

Every contract holding funds implements:

1. `request_emergency_withdraw()` — records the current topoheight
2. `execute_emergency_withdraw(asset)` — available only after 17,280 blocks (~24h)

This prevents a compromised admin from draining funds in a single transaction.

### Security Model

- **No admin backdoor**: governance-controlled parameters, multisig-guarded security
- **Two-layer guardian**: Timelock accepts both an EOA guardian (for fast response) and a GuardianMultisig contract (for high-stakes changes)
- **Oracle circuit breakers**: max deviation (5%), callback threshold (20%), hard stale (100 blocks)
- **Reentrancy guard**: VaultSwapV2 implements a `RG_STATUS_KEY` (entered/not-entered) pattern

---

## How to Participate

### As a User

1. **Get XEL**: from a centralized exchange (MEXC, CoinEx) or the [testnet faucet](contracts/faucet/FaucetContract.slx)
2. **Open a vault**: deposit XEL → borrow xUSD → use it in the AMM or PSM
3. **Earn yield**: supply xUSD to SavingsRate (5% APY), or provide AMM liquidity
4. **Govern**: stake VLT and vote on protocol proposals

### As a Miner (Oracle Provider)

1. **Stake 100 VLT** and register on XelisVaultMiner
2. **Run the miner daemon** (`scripts/xelis_vault_miner.py`) — submits heartbeats, manages your endpoint
3. **Run the price provider** (`scripts/price_provider.py`) — fetches prices from MEXC/CoinEx/CoinGecko, submits to StakedOracle
4. **Earn VLT rewards** proportional to your reputation tier (up to 1.5× multiplier)

Requirements:
- A public HTTPS endpoint (for oracle service)
- A VLT balance ≥ 100 (staked)
- For chat service: a public WebSocket endpoint

### As a Developer

- **Use the contracts**: all 33 are MIT-licensed, Silex source in `contracts/`
- **Extend the protocol**: call any public entry via `Contract::call` — full ABI in [`docs/ENTRY_IDS.md`](docs/ENTRY_IDS.md)
- **Build on xUSD**: integrate the stablecoin into your dApp via PSM or VaultSwap
- **Run the aggregation keeper**: `scripts/aggregation_keeper.py` triggers price aggregation

---

## Quick Start

### Prerequisites

- Python 3.10+
- Silex compiler (`silex compile` or the [`compile-tool`](https://github.com/xelis-project/xelis-blockchain))
- XELIS daemon and wallet (testnet or mainnet)

### Deploy

```bash
# 1. Compile all contracts
silex compile contracts/proxy/ContractRegistry.slx
silex compile contracts/token/VLTToken.slx
# ... repeat for all 33

# 2. Deploy (see deploy/deploy_testnet.py for the full automation)
python3 deploy/deploy_testnet.py --signer deployer \
    --team xet1... --treasury xet1... \
    --airdrop xet1... --bug-bounty xet1...

# 3. Generate entry ID documentation
python3 scripts/extract_entry_ids.py
# Output: docs/ENTRY_IDS.md
```

### Deployment Order

```
1.  ContractRegistry         (foundation — all others depend on it)
2.  VLTToken                 (create_asset → authorize minters)
3.  XelisVaultMiner          (wire VLT asset, registry, treasury)
4.  StakedOracle             (wire miner contract + registry)
5.  xUSD                     (create_asset → authorize minters/burners)
6.  VaultEngineV3            (wire oracle, xUSD, registry)
7.  PSM                      (wire oracle, xUSD, registry)
8.  VaultSwapV2              (wire oracle, xUSD, registry)
9.  GovernanceVault          (wire VLT, registry)
10. Governor                 (wire GovernanceVault, Timelock)
11. Timelock                 (wire Governor, GuardianMultisig)
12. GuardianMultisig         (wire Timelock, registry)
13. OracleGovernance         (wire StakedOracle, GovernanceVault)
14-33. Remaining contracts   (FlashLoan, Auction, PrivacyMixer, ...)
```

### Verify

```bash
# Quick health check
python3 tests/test_all_contracts.py

# Manual on-chain checks
curl -X POST https://testnet-node.xelis.io/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"get_contract_data","params":{"contract":"<hash>","key":"a"},"id":1}'
```

---

## Repository Structure

```
xelis-vault/
├── contracts/           # 33 Silex smart contracts
│   ├── amm/             # PSM, VaultSwapV2
│   ├── auction/         # SealedBidAuction
│   ├── chat/            # VaultChat
│   ├── compliance/      # ComplianceModule
│   ├── faucet/          # FaucetContract
│   ├── flashloan/       # FlashCallback, FlashLoan
│   ├── governance/      # GovernanceVault, Governor, GuardianMultisig, OracleGovernance, Timelock
│   ├── insurance/       # InsurancePool, PrivateInsurance
│   ├── interest/        # InterestRateModel
│   ├── lending/         # LendingMarket, PeerLoan, SyndicatePool
│   ├── miner/           # MinerPool, XelisVaultMiner
│   ├── oracle/          # StakedOracle
│   ├── payroll/         # Payroll
│   ├── privacy/         # PrivacyMixer
│   ├── proxy/           # ContractRegistry, Upgradeable
│   ├── revenue/         # RevenueShare
│   ├── rwa/             # AssetVault
│   ├── savings/         # SavingsRate
│   ├── token/           # VLTToken
│   ├── treasury/        # TreasuryVault
│   ├── usd/             # xUSD
│   └── vault/           # VaultEngineV3
├── deploy/
│   └── deploy_testnet.py    # Semi-automated deployment script
├── docs/
│   ├── WHITEPAPER.md        # Full technical whitepaper
│   ├── AUDIT_v5.0_REMEDIATION.md  # Audit remediation report
│   ├── ENTRY_IDS.md         # Entry ID table (all 33 contracts)
│   ├── REWARD_SYSTEM.md     # Miner reward + reputation details
│   ├── PROVIDER_GUIDE.md    # Price provider setup
│   ├── MINER_GUIDE.md       # Miner daemon guide
│   ├── USER_GUIDE.md        # End-user guide
│   └── ROADMAP.md           # Development roadmap
├── scripts/
│   ├── xelis_vault_miner.py           # Miner daemon
│   ├── price_provider.py              # Price submission daemon
│   ├── aggregation_keeper.py          # Aggregation trigger
│   ├── extract_entry_ids.py           # Entry ID documentation generator
│   └── custom_sources.example.json    # Price source config template
├── tests/
│   └── test_all_contracts.py          # Integration test suite
├── install.py                          # Local environment bootstrap
├── LICENSE                             # MIT license
└── README.md                           # This file
```

---

## Community

- **Discord**: https://discord.gg/UHpYAWbG
- **Twitter / X**: https://x.com/xelisvault
- **GitHub**: https://github.com/XelisVault/xelis-vault
- **Whitepaper**: [`docs/WHITEPAPER.md`](docs/WHITEPAPER.md)

## License

MIT — see [`LICENSE`](LICENSE).
