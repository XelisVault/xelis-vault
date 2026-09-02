<div align="center">

# XELIS Vault

**Privacy-First DeFi on XELIS BlockDAG**

CDP stablecoin · Decentralized oracle · AMM + PSM · Governance · Privacy mixer · E2E chat

[![Network](https://img.shields.io/badge/network-testnet-blue)](https://testnet-explorer.xelis.io/)
[![Contracts](https://img.shields.io/badge/contracts-51%20Silex-blueviolet)](contracts/)
[![Version](https://img.shields.io/badge/version-v12R--3-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

### Install everything in one line

**Linux & macOS:**

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**

```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (Command Prompt):** download [`install.bat`](install.bat) and double-click it.

All three methods install **both** `xvault` (community CLI) and `xvault-miner` (miner dashboard).

> **✅ LIVE ON TESTNET (v12R-3, 2026-08-24)**
>
> The core protocol is deployed and verified end-to-end on XELIS testnet.
> Authoritative addresses: [docs/deployment_state.json](docs/deployment_state.json)
> (resolved live via `ContractRegistry cur_<Name>`). Deployment history:
> [docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md).
>
> | Flow | Status |
> |---|---|
> | PSM mint / redeem (XEL ↔ xUSD) | ✅ verified on-chain |
> | Vault Engine V3 — deposit / borrow / repay / withdraw | ✅ full cycle verified |
> | VaultSwap AMM swap (xUSD → XEL) | ✅ verified |
> | SavingsRate deposit / withdraw | ✅ verified |
> | PrivacyMixer deposits + auto-mix | ✅ verified |
> | Faucet distribute · Miner register + heartbeat | ✅ verified |
> | VaultChat E2E (sessions, groups, anchoring, relayers) | ✅ 17/17 |
> | CLI write-path suite (`scripts/test_cli_ops.py`) | ✅ 14/14 |
>
> Governance/multisig, flash loans, auctions and confidential vault flows are
> deployed but not yet exercised in the automated suites.

---

**Miner?** Run `xvault-miner` after install. 
**Community member?** Run `xvault` after install.  
**Want to run a chat relayer?** Run `xvault-relayer` after install.

---

</div>

---

## Quick Start

### Step 1 — Install

**Linux & macOS:**

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**

```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (Command Prompt):** download [`install.bat`](install.bat) and double-click it.

This single command:
- Detects your OS and architecture (Linux, macOS, Windows)
- Clones the repository to `~/.xelis-vault/src` (or `%USERPROFILE%\.xelis-vault\src` on Windows)
- Creates a Python virtualenv with all dependencies
- Installs **two launchers**:
  - `xvault` — community CLI (wallet, vaults, swaps, governance, mixer, chat)
  - `xvault-miner` — miner dashboard (real-time TUI with reputation, rewards, stats)
- Generates config with testnet defaults
- No telemetry, no phone-home, all data stays local

If the launcher directory is not in your PATH, the installer tells you exactly what to do.

### Step 2 — Choose your role

#### For Miners

```bash
xvault-miner
```

Interactive dashboard that shows in real-time:
- **Reputation** (Excellent / Good / Warning / Critical / Banned) with progress bar
- **Stake & rewards** (VLT balance, total earned, total slashed)
- **Submission stats** (valid / total, success rate)
- **Protocol stats** (budget, distribution, budget factor, active miners)
- **Price feeds** (XEL/USD, deviation, sources count, staleness)
- **Service selection** (oracle only, chat only, or both)
- **MinerDelegation** — delegate VLT to miners, manage profile, claim rewards

Quick start with flags:
```bash
xvault-miner --miner                          # Start mining immediately
xvault-miner --services oracle                # Oracle only
xvault-miner --services chat                  # Chat only
xvault-miner --services both                  # Both (default)
xvault-miner --dry-run                        # Simulate without submitting
```

#### For Community Members

```bash
xvault
```

Interactive menu with:
- **Create or import** a XELIS wallet (auto-downloads official wallet binary)
- **View your balance** (XEL, VLT, xUSD)
- **Manage vaults** (deposit XEL, borrow xUSD, repay, withdraw, liquidate)
- **Swap** (XEL ↔ xUSD via PSM, XEL ↔ VLT via AMM)
- **Govern** (stake VLT, vote on proposals, create proposals)
- **Mix** (private transfers via PrivacyMixer with ZK proofs)
- **Chat** (E2E encrypted messaging anchored on-chain)
- **View stats** (protocol-wide statistics, all public on-chain data)

Quick commands:
```bash
xvault --balance     # Quick balance check
xvault --swap        # Quick swap menu
xvault --vault       # Vault management
xvault --governance  # Governance menu
```

### Uninstall

**Linux & macOS:**

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**

```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

---

## Architecture

```
XELIS Vault v12R-3 — 51 Silex contracts

┌─────────────────────────────────────────────────────────────┐
│                    CONTRACT REGISTRY                         │
│            (name → hash resolution, upgradeable)              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐    ┌──────────────────┐                │
│  │  StakedOracle    │───▶│  XelisVaultMiner  │              │
│  │  (decentralized  │    │  (stake, reput.,  │              │
│  │   median oracle) │    │   rewards, slash) │              │
│  └────┬────────────┘    └───────┬──────────┘                │
│       │                         │                            │
│       │ price                   │ mint VLT                   │
│       ▼                         ▼                            │
│  ┌─────────────┐    ┌──────────────────┐                    │
│  │ VaultEngine  │    │    VLTToken       │                   │
│  │ (CDP, XEL →  │    │  (10M fixed supply)│                   │
│  │  xUSD, stab. │    └──────────────────┘                    │
│  │  fee)        │                                            │
│  └──────┬───────┘    ┌──────────────────┐                    │
│         │            │      xUSD          │                   │
│         │ mint/burn  │  (elastic supply)  │                   │
│         └───────────▶│                    │                   │
│                      └────────┬───────────┘                   │
│                               │                               │
│  ┌─────────────┐    ┌────────┴───────────┐                   │
│  │     PSM      │◀──▶│   VaultSwapV2      │                   │
│  │ (peg stability│   │ (AMM + PSM, TWAP)  │                   │
│  │  xUSD ↔ XEL) │    │  VLT/XEL pool      │                   │
│  └─────────────┘    └────────────────────┘                   │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 MINER DELEGATION                        │  │
│  │  MinerDelegation — delegate VLT, earn rewards,          │  │
│  │  auto-compound, commission-based profiles               │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    GOVERNANCE                           │  │
│  │  GovernanceVault → Governor → Timelock → GuardianMultisig│  │
│  │  OracleGovernance (oracle params)                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ │
│  │FlashLoan│ │SealedBid│ │Privacy  │ │Vault   │ │Insurance││
│  │         │ │Auction  │ │Mixer    │ │Chat    │ │Pool     ││
│  └────────┘ └──────────┘ └─────────┘ └────────┘ └────────┘ │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           BRAINSTORMING FEATURES (v10.2)               │  │
│  │  NotificationCenter · CreditScore · EmergencyShutdown  │  │
│  │  GovernanceDelegation · VaultInsurance · Analytics     │  │
│  │  LiquidationMarket · VaultBounties · SocialTrading     │  │
│  │  YieldOptimizer · VaultTemplates · MultiCollateralVault│  │
│  │  VaultNFT (tokenized positions)                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Oracle: Decentralized & Graceful

XELIS Vault uses **StakedOracle** — a fully decentralized oracle with:

- **Median aggregation** (robust to outliers)
- **Multi-feed support** (XEL/USD, XEL/BTC, etc.)
- **Reputation-weighted rewards** (1.5× Excellent → 0× Banned)
- **Progressive slashing** (1% outlier → 50% malicious)
- **Circuit breaker** (pauses on >20% price movement)
- **Bootstrap mode** (works with 3 miners, scales to 100+)

### Graceful Degradation

The protocol **never stops working**, even if miners leave:

| Active miners | Mode | Behavior |
|--------------|------|----------|
| 0 | Emergency | Last known price used (marked stale) |
| 1–2 | Degraded | Price updates from single miner (no slashing) |
| 3–9 | Bootstrap | Median aggregation, no slashing |
| 10+ | Full | Median + slashing + circuit breaker |

This means: even if the project loses popularity and miners drop, the protocol **continues to function**. DeFi operations (vaults, swaps, PSM) keep using the last known price.

---

## Miner Rewards

```
Bitcoin-style halving: rewards halve every year, lasting 30+ years

block_reward = INITIAL_REWARD_PER_BLOCK / 2^epoch
  where epoch = (current_block - launch_block) / HALVING_INTERVAL

reward = block_reward × min(stake, CAP) / max(total, FLOOR)
       × reputation_mult / 10000
       × concentration_factor / 10000
```

**Concentration penalty curve** (progressive, not cliff):
| Miner % of total stake | Factor | Penalty |
|------------------------|--------|---------|
| 0-8% | 1.0x | 0% |
| 10% | 0.88x | 12% |
| 14% | 0.65x | 35% |
| 18% | 0.42x | 58% |
| 20%+ | 0.30x | 70% |

**Self-regulating like Bitcoin** — high early rewards attract miners, then decrease:

| Year | VLT/year | VLT/day | Cumul % | APY (100 miners) |
|------|----------|---------|---------|-------------------|
| 1 | 1,374,749 | 3,766 | 50% | 1,375% |
| 2 | 687,374 | 1,883 | 75% | 688% |
| 3 | 343,687 | 942 | 87.5% | 344% |
| 5 | 85,922 | 235 | 96.9% | 86% |
| 10 | 2,685 | 7 | 99.9% | 3% |

**Budget: 5,500,000 VLT** (geometric series, never truly exhausted).
**Halving: every 1 year** (6,307,200 blocks at 5s).
**Min stake: 1,000 VLT** (anti-Sybil).
**STAKE_FLOOR: 100,000 VLT** (bounds APY when few miners).
**CAP_STAKE_PER_MINER: 500,000 VLT** (hard cap on stake counted).
**No fixed end date** — rewards continue indefinitely at decreasing rates.

### Features

- **Auto-slash offline miners** — keepers slash miners who miss heartbeats
- **Reputation temporal decay** — inactive miners slowly lose reputation
- **Compound rewards** — auto re-stake rewards for compound growth
- **Graceful degradation** — protocol works with 1 to 100+ miners

---

## Miner Delegation

MinerDelegation lets VLT holders delegate their stake to miners without running infrastructure themselves.

- **Delegate VLT** — choose a miner and delegate your VLT (min 10 VLT)
- **Earn rewards** — share in the miner's rewards proportionally to your stake
- **Auto-compound** — automatically reinvest rewards for compound growth
- **Commission** — miners set a commission rate (0–20%) on delegated rewards
- **Undelegate** — queue undelegation with a 7-day delay before execution
- **Profile** — miners can register a public profile (name, description, commission)
- **Claim rewards** — claim delegator rewards or miner rewards at any time

Access via `xvault-miner` → **MinerDelegation: delegate / profile**.

---

## Tokenomics

### VLT Token (10,000,000 fixed supply — no presale, no seed investors)

| Allocation | Amount | % | Purpose |
|------------|--------|---|---------|
| Oracle rewards | 5,500,000 | 55% | Distributed to miners over 10 years |
| Chat relayer rewards | 1,000,000 | 10% | Relayer network over 10 years (100k VLT/year) |
| DEX liquidity | 1,000,000 | 10% | VLT/XEL pool seeding |
| Founder vesting (4y) | 500,000 | 5% | 4-year vesting, 1-year cliff |
| Treasury | 500,000 | 5% | Governance-controlled |
| Community airdrop | 500,000 | 5% | Testnet contributors (via AirdropTracker) |
| Launch airdrop | 200,000 | 2% | First 1,000 mainnet users (200 VLT each) |
| Bug bounty | 100,000 | 1% | Perpetual, Immunefi |
| Protocol reserve | 200,000 | 2% | Buffer for unforeseen needs |
| Founder ongoing (10y) | 500,000 | 5% | 10-year vesting, 50k VLT/year |

**100% fair launch** — no presale, no seed investors, no VC allocation.

### Fee Distribution (via FeeDistributor contract)

All protocol fees are split automatically:
- **50% burned** (deflationary pressure)
- **40% to treasury** (governance-controlled)
- **10% to founder** (ongoing XEL revenue, no extra cost to users)

### xUSD Stablecoin

- **Peg mechanism**: PSM (Peg Stability Module) — mint/redeem xUSD 1:1 with XEL at oracle price
- **Collateral**: VaultEngine CDPs — deposit XEL, borrow xUSD (200% min collateral ratio, governance adjustable)
- **Stability fee**: 2% APR on borrows (accrues continuously via global index)
- **Burn mechanisms**: 50% of all slashes burned + 50% of protocol fees burned

### VLT/XEL Liquidity Pool

The AMM pool (`VaultSwapV2`) includes a VLT/XEL pool where:
- Price varies with supply and demand (constant-product formula)
- LPs earn swap fees (30 bps base + 5 bps treasury)
- **Liquidity incentives**: Treasury distributes VLT to LPs proportionally
- Pool strengthens over time as more LPs join and fees compound

---

## CLI Reference

### Miner Dashboard (`xvault-miner`)

| Flag | Description |
|------|-------------|
| `--rpc <url>` | Daemon RPC URL |
| `--wallet-url <url>` | Wallet RPC URL |
| `--miner` | Start mining immediately |
| `--services <choice>` | oracle, chat, or both |
| `--dry-run` | Simulate without submitting |
| `--setup` | Run interactive setup |
| `-y` | Skip prompts |

### Community CLI (`xvault`)

```bash
xvault              # Launch the CLI (wallet auto-launches, address auto-detected)
```

**Features:**
- 📊 Dashboard — Overview, balances, airdrop stats
- 🏦 Vault — Deposit XEL, borrow xUSD, repay, withdraw
- 💱 Swap — PSM mint/redeem, AMM swap, add liquidity
- 🗳 Governance — Stake VLT, vote, create proposals
- 🔒 Mixer — Private transfers (10/100/1000 XEL denominations)
- 💬 Chat — E2E encrypted messaging
- 🪂 Airdrop — Points, leaderboard, register mainnet address
- 📈 Stats — Protocol statistics (real-time price, vaults, balances)
- 🔐 Admin Panel — Admin-only functions (auto-detected)
- 🛡 Guardian Panel — Guardian-only emergency controls (auto-detected)

**Admin Panel** (appears automatically if you're the admin):
- Pause/Unpause all contracts
- Faucet distribution (batch up to 50 addresses)
- Airdrop management (freeze, finalize, batch points, disqualify)
- Miner management (slash, rewards, services)
- Oracle management (add feed, force update)
- Protocol parameters (fees, LTV, caps)
- Founder vesting, revenue share, emergency shutdown
- Admin audit log viewer

**Guardian Panel** (appears automatically if you're a guardian):
- Emergency pause/unpause (guardians can act alone)
- Oracle force update
- Circuit breaker trigger
- Multisig proposals (view, confirm, execute)

**Role detection is automatic:**
- Guardian: verified on-chain via `GuardianMultisig.is_signer()`
- Admin: enabled in Settings, verified at call time by `only_admin()`
- No manual address entry — your address is auto-detected from your wallet

Full CLI guide: [`docs/CLI_GUIDE.md`](docs/CLI_GUIDE.md)

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/INSTALLATION.md) | Install on Linux, macOS, Windows (EN/FR/ZH/JA/AR) |
| [CLI Guide](docs/CLI_GUIDE.md) | Complete guide for `xvault` and `xvault-miner` |
| [Chat Guide](docs/CHAT_GUIDE.md) | How E2E encrypted chat works |
| [Whitepaper](docs/WHITEPAPER.md) | Full technical whitepaper |
| [Miner Guide](docs/MINER_GUIDE.md) | How to become a miner |
| [Provider Guide](docs/PROVIDER_GUIDE.md) | Price data provider setup |
| [User Guide](docs/USER_GUIDE.md) | End-user guide |
| [Reward System](docs/REWARD_SYSTEM.md) | Reward + reputation mechanics |
| [Roadmap](docs/ROADMAP.md) | Development roadmap |
| [Entry IDs](docs/ENTRY_IDS.md) | Auto-generated entry ID table (source order) |
| [Entry Chunk IDs](docs/entry_chunk_ids.json) | Compiled chunk indices — use these for `entry_id` in invokes |
| [Deployments](docs/DEPLOYMENTS.md) | Live testnet deployment record (updated after each step) |
| [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) | Order of deployment + configuration |
| [AGENTS.md](AGENTS.md) | Operator notes: RPC mechanics, gotchas, current state |

---

## Security

- **`pub fn` for cross-contract** — Silex requires `pub fn` for `Contract::call()`. Entry functions fail with "Chunk is not public".
- **2-step emergency withdraw** — 24h delay on all fund-holding contracts
- **ReentrancyGuard** — `non_reentrant()` on all state-changing entries
- **Progressive slashing** — 1% to 50% based on severity
- **Reputation system** — 5-tier multiplier prevents bad actors from earning
- **Circuit breaker** — oracle pauses on >20% price movement
- **Graceful degradation** — protocol works with 1 to 100+ miners

---

## Community

- **Discord:** https://discord.gg/vyXTVRNSyu
- **Twitter:** https://x.com/xelisvault
- **GitHub:** https://github.com/XelisVault/xelis-vault
- **Testnet Explorer:** https://testnet-explorer.xelis.io/
- **XELIS Blockchain:** https://xelis.io

---

## License

MIT — see [LICENSE](LICENSE).
