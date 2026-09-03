<div align="center">

# XELIS Vault

**Privacy-First DeFi on XELIS BlockDAG**

CDP stablecoin · Decentralized oracle · AMM + PSM · Governance · Privacy mixer · E2E chat

[![Network](https://img.shields.io/badge/network-testnet-blue)](https://testnet-explorer.xelis.io/)
[![Contracts](https://img.shields.io/badge/contracts-51%20Silex-blueviolet)](contracts/)
[![Version](https://img.shields.io/badge/version-v12R--3-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

---

## Install in one line

**Linux and macOS:**

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**

```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (Command Prompt):** download [`install.bat`](install.bat) and double-click it.

All three methods install `xvault` (community CLI), `xvault-miner` (miner dashboard), and `xvault-relayer` (chat relayer daemon). No telemetry, no phone-home, all data stays local.

---

## Quick start

After install, pick a role:

```bash
xvault-miner          # Miner dashboard (reputation, rewards, price feeds, submissions)
xvault                # Community CLI (wallet, vaults, swaps, governance, mixer, chat)
xvault-relayer        # Chat relayer daemon (stake 50 VLT, earn relayer rewards)
```

First run of `xvault-miner` or `xvault` launches the onboarding wizard: it detects or downloads the XELIS wallet binary, generates a seed locally (XELIS mnemonic scheme, 25 words), connects to the testnet node, and loads contract addresses from `network/testnet.json` automatically. No manual address entry.

If the launcher directory is not in your PATH, the installer tells you exactly what to do (usually `source ~/.bashrc` or restart the terminal).

---

## What is XELIS Vault

A composable DeFi protocol written in Silex, the native smart-contract language of XELIS. 51 contracts, 975 entry functions, organized in six layers:

| Layer | Contracts | Role |
|-------|-----------|------|
| Registry | ContractRegistry | Name to hash resolution, versioned upgrades, rollback |
| Tokens | VLTToken, xUSD | Governance token (10M supply) and CDP stablecoin |
| Oracle | XelisVaultMiner, StakedOracle | Staked miner registry, reputation, slashing, median aggregation |
| DeFi | VaultEngineV3, LendingMarket, PSM, VaultSwapV2, PeerLoan, SyndicatePool | Lending, AMM, peg stability, peer-to-peer credit |
| Governance | GovernanceVault, Governor, Timelock, GuardianMultisig, OracleGovernance | Staking, proposals, delayed execution, multisig guardian |
| Auxiliary | FlashLoan, SealedBidAuction, PrivacyMixer, VaultChat, InsurancePool, AssetVault, TreasuryVault, RevenueShare, SavingsRate, Payroll, FaucetContract, ComplianceModule, MinerDelegation, FlashCallback | Capital efficiency, RWA, mixer, encrypted chat, treasury, savings |

The full source is in [`contracts/`](contracts/) and [`src/contracts/`](src/contracts/). Documentation is in [`docs/`](docs/) and [`src/docs/`](src/docs/).

---

## Testnet status

**Network:** XELIS testnet (v12R-3, canonical chain redeployed 2026-08-24)

**Deployed contracts:** 36 registered in `network/testnet.json`, including ContractRegistry, VLTToken, xUSD, FaucetContract, XelisVaultMiner, StakedOracle, MinerDelegation, VaultEngineV3, VaultSwapV2, PSM, GovernanceVault, Governor, Timelock, GuardianMultisig, VaultChat, PrivacyMixer, and more.

**Testnet explorer:** [testnet-explorer.xelis.io](https://testnet-explorer.xelis.io/)

**Faucet:** run `xvault` and use the built-in faucet command, or interact with the FaucetContract directly.

---

## Airdrop

700,000 VLT (7% of supply) distributed across two envelopes:

- **500,000 VLT (5%)** to testnet contributors. Points accumulated on-chain by `AirdropTracker.slx` for mining, relaying, governance, chat, liquidity, bug bounty, and community contributions. Qualification: 1,000 points minimum, 7 distinct active days, mainnet address registered.
- **200,000 VLT (2%)** launch airdrop at mainnet, first-come-first-served.

Full plan in [`docs/AIRDROP_PLAN.md`](docs/AIRDROP_PLAN.md).

---

## Tokenomics

10 million VLT, distributed over 10 years. Full breakdown in [`docs/TOKENOMICS_v10.3.md`](docs/TOKENOMICS_v10.3.md).

| Allocation | Amount | % |
|-----------|--------|---|
| Oracle rewards (10y, Bitcoin-style halving) | 5,500,000 | 55% |
| Chat relayer rewards (10y, 100k/year) | 1,000,000 | 10% |
| DEX liquidity (6-month unlock) | 1,000,000 | 10% |
| Founder vesting 4y (1y cliff) | 500,000 | 5% |
| Treasury (governance) | 500,000 | 5% |
| Community airdrop (testnet) | 500,000 | 5% |
| Founder ongoing 10y (50k/year) | 500,000 | 5% |
| Launch airdrop (FCFS) | 200,000 | 2% |
| Protocol reserve | 200,000 | 2% |
| Bug bounty (perpetual) | 100,000 | 1% |

No per-transaction founder fee. Founder gets 10% of existing protocol fees via `FeeDistributor` (50% burn, 40% treasury, 10% founder). No new tax on users.

---

## For miners

Minimum stake: 1,000 VLT (raised from 100 in v10.7 for anti-Sybil). Rewards are stake-weighted with a reputation multiplier:

| Tier | Reputation | Multiplier |
|------|-----------|------------|
| Excellent | 8000+ | 1.5x |
| Good | 6500-7999 | 1.2x |
| Warning | 2500-6499 | 0.8x |
| Critical | 0-2499 | 0.5x |

Bitcoin-style halving: reward per block halves every 6,307,200 blocks (1 year). Budget lasts 30+ years without a fixed cap.

Run `xvault-miner --miner` to start mining immediately, or `xvault-miner` for the interactive dashboard.

Full economics in [`docs/MINER_ECONOMICS.md`](docs/MINER_ECONOMICS.md).

---

## For price providers

`price_provider.py` polls sources (CoinEx, MEXC, XELIS daemon, custom HTTP, external command), computes the median with 5% outlier rejection and 30-second staleness rejection, and submits to `StakedOracle` via the `submit_price` entry.

`aggregation_keeper.py` triggers `aggregate_now` every 25 seconds per feed and monitors stuck cycles.

Both daemons are designed to run on distinct servers by independent operators. That is what makes the oracle decentralized in practice.

Configuration templates in [`scripts/custom_sources.example.json`](scripts/custom_sources.example.json) (7 source templates documented).

---

## For chat relayers

Stake 50 VLT (slashable bond), run `xvault-relayer`. Ten anti-abuse layers documented in [`docs/CHAT_GUIDE.md`](docs/CHAT_GUIDE.md): rate limits, diminishing returns (100% to 20%), reputation multipliers, P2P consensus, dispute mechanism.

1 million VLT allocated over 10 years for relayer rewards, approximately 10k VLT/year per relayer with 10 relayers in parallel. Optional user subscription (95% to relayer, 5% to protocol) covers server costs.

---

## Security

The v11.5 audit remediation report is public: [`docs/AUDIT_v11.5_REMEDIATION.md`](docs/AUDIT_v11.5_REMEDIATION.md). 18 findings from a controlled disclosure audit (2 critical, 5 high, 8 medium, 3 low), all fixed and documented.

Two-step `emergency_withdraw` pattern applied uniformly across all contracts. Reentrancy guards on every state-mutating entry. Sequential cross-contract call graph with deterministic entry IDs auto-documented by `scripts/extract_entry_ids.py`.

---

## Directory structure

```
xelis-vault/
├── contracts/              # 51 Silex smart contracts (source of truth)
├── src/                    # Clean distribution (contracts + scripts + docs copy)
├── scripts/                # Python CLI, miner daemon, relayer, tests, tools
├── docs/                   # Whitepaper, tokenomics, guides, audit reports
├── deploy/                 # Deployment scripts (deploy_testnet.py)
├── tests/                  # Integration tests + protocol simulation
├── bin/                    # Pre-built Windows binaries + launcher scripts
├── config/                 # Default config (config.json, config.example.json)
├── network/                # Deployed contract addresses (testnet.json)
├── install                 # One-line installer (Linux/macOS)
├── install.ps1             # One-line installer (Windows PowerShell)
├── install.bat             # Windows .bat wrapper for install.ps1
├── VERSION                 # Protocol version (v12R-3)
├── CHANGELOG.md            # Full changelog
└── AGENTS.md               # Operator notes (deployment records, live state)
```

---

## Uninstall

**Linux and macOS:**

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**

```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

---

## Links

| Resource | URL |
|----------|-----|
| GitHub | https://github.com/XelisVault/xelis-vault |
| Discord | https://discord.gg/EjyvHFakY9 |
| X (XELIS Vault) | https://x.com/XelisVault |
| X (XELIS Layer-1) | https://x.com/xelis_crypto |
| Testnet explorer | https://testnet-explorer.xelis.io/ |
| XELIS official site | https://xelis.io |
| XELIS documentation | https://docs.xelis.io |
| XELIS YouTube | https://www.youtube.com/@xelis_blockchain |
| Whitepaper | [docs/WHITEPAPER.md](docs/WHITEPAPER.md) |
| Airdrop plan | [docs/AIRDROP_PLAN.md](docs/AIRDROP_PLAN.md) |
| Tokenomics | [docs/TOKENOMICS_v10.3.md](docs/TOKENOMICS_v10.3.md) |
| Audit report | [docs/AUDIT_v11.5_REMEDIATION.md](docs/AUDIT_v11.5_REMEDIATION.md) |
| Roadmap | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Deployment guide | [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) |

---

## Important notes

- **This is testnet software.** Do not use mainnet funds.
- **Backup your seed phrase.** Stored locally at `~/.xelis-vault/wallet/`. Cannot be recovered if lost.
- **No financial advice.** No price projection. The protocol builds in public, the testnet is open, the airdrop distribution is transparent.
- **License:** MIT. See [LICENSE](LICENSE).
