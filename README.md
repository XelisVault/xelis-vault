<div align="center">

# XELIS Vault

**Privacy-First DeFi on XELIS BlockDAG**

CDP stablecoin · Decentralized oracle · AMM + PSM · Governance · Privacy mixer · E2E chat · Airdrop

[![Network](https://img.shields.io/badge/network-testnet-blue)](https://testnet-explorer.xelis.io/)
[![Contracts](https://img.shields.io/badge/contracts-51%20Silex%20%C2%B7%2051%2F51%20compile-11c263)](contracts/)
[![Version](https://img.shields.io/badge/version-v12-blueviolet)](CHANGELOG.md)
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

All three methods install `xvault` (community CLI), `xvault-miner` (miner dashboard) and
`xvault-relayer` (chat relayer daemon). No telemetry, no phone-home, all data stays local.

---

## Quick start

```bash
xvault            # Community CLI (wallet, vaults, swaps, governance, mixer, chat, airdrop, doctor)
xvault-miner      # Miner dashboard (setup guided, provider handbook, rewards, claim)
xvault-relayer    # Chat relayer daemon (stake 50 VLT, earn relayer rewards)
```

First run launches the **onboarding wizard**: it detects or downloads the XELIS wallet
binary, generates a 25-word seed locally (displayed twice, confirmed, backed up with
`chmod 600`), connects to the testnet node (local first, public fallback), loads the
contract addresses from `network/testnet.json` and configures the miner — no manual
address entry, no prerequisite.

**Something not working?** Open `xvault` → **Doctor — diagnose & fix my setup**.
It runs 8 families of checks (dependencies, node, wallet, asset tracking, contracts,
airdrop wiring, price feed, protocol health), auto-repairs what it can
(asset tracking, wallet relaunch) and prints **numbered next steps** for anything else.
Every transaction failure also shows a step-by-step remediation guide.

---

## What is XELIS Vault

A composable DeFi protocol written in [Silex](https://docs.xelis.io/features/smart-contracts/silex),
the native smart-contract language of XELIS. **51 contracts — all compiling
(`build/chunkmap_*.txt` is the machine-checked proof) — 975 entry functions**, in six layers:

| Layer | Contracts | Role |
|-------|-----------|------|
| Registry | ContractRegistry | Name→hash resolution, versioned upgrades (`prev_` rollback) |
| Tokens | VLTToken, xUSD | Governance token (10M supply) and CDP stablecoin |
| Oracle | XelisVaultMiner, StakedOracle | Staked miner registry, reputation, slashing, median aggregation |
| DeFi | VaultEngineV3, LendingMarket, PSM, VaultSwapV2, PeerLoan, SyndicatePool | Lending, AMM, peg stability, peer-to-peer credit |
| Governance | GovernanceVault, Governor, Timelock, GuardianMultisig, OracleGovernance | Staking, proposals, delayed execution, multisig guardian |
| Auxiliary | FlashLoan, SealedBidAuction, PrivacyMixer, VaultChat, InsurancePool, AssetVault, TreasuryVault, RevenueShare, SavingsRate, Payroll, FaucetContract, ComplianceModule, MinerDelegation, AirdropTracker, AirdropClaim, … | Capital efficiency, RWA, mixer, encrypted chat, treasury, savings, airdrop |

---

## What's new in v12

### 1. Airdrop points now record THEMSELVES on-chain
The v11 tracker expected protocol contracts to call its `record_*` entries — but XVM
entries are wallet-only, so **nothing ever auto-recorded** and every point had to be
injected manually. v12 adds `record_activity_cross` (pub fn, chunk 77) — fail-safe by
construction — wired end-to-end into 10 contracts:

| Action | Contract | Points |
|---|---|---|
| Price submission accepted | StakedOracle | MINING 1 |
| Heartbeat | XelisVaultMiner | MINING 50 |
| Valid oracle/chat submission | XelisVaultMiner | MINING 1 |
| Chat messages / groups | VaultChat | CHAT 1 / 100 |
| Anchors, relayer registration, bond | VaultChat | RELAYER 10 / 50 / 5 |
| Votes / proposals / governance stake | Governor / GovernanceVault | GOV 50 / 500 / 5 |
| Mint, liquidity, savings, collateral | PSM / VaultSwap / Savings / VE3 | LIQ 10 per XEL |
| Mixer deposit | PrivacyMixer | LIQ 10 per unit |

Daily caps stay enforced by the tracker. PoW block mining (invisible to contracts)
is still counted by the off-chain indexer daemon. Migration of the existing season
(43 users, 316k points — **including days_active and mainnet addresses**) is built in:
`deploy/upgrade_v12.py --phase d`. Full guide: [`docs/UPGRADE_v12.md`](docs/UPGRADE_v12.md).

### 2. Miner rewards fixed — per-block emission, really
Diagnosis (on-chain): the protocol distributed **4.86 VLT in ~2 weeks** against a
5.5M budget and a 2.75M VLT/year emission target. Root cause: rewards were paid per
*submission* (~57/day) instead of per *block*, and the STAKE_FLOOR anti-Sybil
denominator crushed the share on top. v12.1 settles the accrual **lazily per block**:

```
reward = block_reward(epoch) x elapsed_blocks x stake_share x reputation_mult
```

The settle is triggered cross-contract (`settle_rewards_cross`, chunk 90) by the oracle
aggregator and the chat anchor flow, plus a manual `claim_rewards` entry. With the same
parameters a 1000 VLT miner now earns **~50 VLT/day** (was ~0.25). Each payment also
grows a **confidential earnings view**: an ElGamal `Ciphertext` encrypted for the miner
(`ect_<addr>`, homomorphic add) — decryptable only by the miner's wallet.

### 3. PrivacyMixer v3 — Tornado-style, no intermediary, no stored amounts
- Fixed denominations (1 / 10 / 100 units of XEL or VLT) — perfect fungibility per class
- Nullifier notes: only `blake3(secret)` is stored — **no sender, no recipient, no amount, no timestamp**
- Withdraw to ANY address, note consumed atomically — no balance proof needed
- Zero protocol fees by default; XELIS L1 keeps every transfer amount encrypted

### 4. Everything else
- **Doctor screen** + error→steps guides in the CLI (the #1 community request)
- **Mixer/claim/provider flows** in both CLIs; live-hash loading in the airdrop indexer
- Two pre-existing broken contracts (AnalyticsCollector, CreditScore) fixed and now compiling
- Repo restructure: stale `src/` duplicate removed, legacy scripts archived
- `docs/entry_chunk_ids.json` regenerated from real compilation (51/51, names+kinds)
- `build/` — compiled bytecode + chunk maps for every contract, machine-verifiable

---

## For miners

Minimum stake: **1,000 VLT**. Rewards: per-block emission (Bitcoin-style halving every
6,307,200 blocks), stake-weighted with a reputation multiplier:

| Tier | Reputation | Multiplier |
|------|-----------|------------|
| Excellent | 8000+ | 1.5x |
| Good | 6500-7999 | 1.2x |
| Warning | 2500-6499 | 0.8x |
| Critical | 0-2499 | 0.5x |

```bash
xvault-miner --miner    # start mining immediately
xvault-miner            # interactive dashboard (setup, handbook, claim)
```

Full economics in [`docs/MINER_ECONOMICS.md`](docs/MINER_ECONOMICS.md).

## For price providers

`price_provider.py` polls sources (CoinEx, MEXC, XELIS daemon, custom), computes a
median with outlier/staleness rejection, and submits to `StakedOracle`.
`oracle_keeper3.py` triggers aggregation + heartbeats. Run `xvault-miner` → `p` for the
guided handbook. Templates in [`scripts/custom_sources.example.json`](scripts/custom_sources.example.json).

## For chat relayers

Stake 50 VLT (slashable bond), run `xvault-relayer` — a real HTTP relayer service
(inbox/group queries, message relay, Merkle anchoring for VLT rewards), optionally
exposed publicly via a free Cloudflare quick tunnel, all automated from the CLI.
Ten anti-abuse layers documented in [`docs/CHAT_GUIDE.md`](docs/CHAT_GUIDE.md).

## Airdrop

700,000 VLT (7% of supply): 500,000 across testnet contributors (points, see above —
now **auto-recorded on-chain**) + 200,000 FCFS at mainnet. Qualification: 1,000 points,
7 distinct active days, mainnet address registered (`xvault` → Airdrop screen).
Full plan in [`docs/AIRDROP_PLAN.md`](docs/AIRDROP_PLAN.md).

## Tokenomics

10M VLT over 10 years — 55% oracle rewards (halving), 10% relayer rewards, 10% DEX
liquidity, 5% founder vesting (4y, 1y cliff), 5% treasury, 5% testnet airdrop, 5%
founder ongoing, 2% launch airdrop, 2% reserve, 1% bug bounty. No per-transaction tax.
Details: [`docs/TOKENOMICS_v10.3.md`](docs/TOKENOMICS_v10.3.md).

---

## Security

- Public audit remediation reports: [v5.0](docs/AUDIT_v5.0_REMEDIATION.md) · [v10.5](docs/AUDIT_v10.5.md) · [v11.5](docs/AUDIT_v11.5_REMEDIATION.md)
- v12 hardening: all mutating entries return 0 (VM: non-zero return = discarded state);
  two-step `emergency_withdraw` everywhere; reentrancy guards; fail-safe airdrop
  recording (a paused tracker can never break a protocol entry); chunk-layout
  compatibility machine-verified on every contract
- 51/51 contracts compile — `python3 scripts/compile_all.py` (needs the silexc toolchain, see `build/README.md`)

## Directory structure

```
xelis-vault/
├── contracts/              # 51 Silex smart contracts (source of truth)
├── build/                  # Compiled bytecode + chunk maps (51/51)
├── scripts/                # CLIs, daemons, indexer, injector, tests
│   └── legacy/             # Archived superseded scripts
├── docs/                   # Whitepaper, tokenomics, guides, audits, UPGRADE_v12
├── deploy/                 # deploy_testnet.py · deploy_v12.py · upgrade_v12.py
├── tests/                  # Protocol simulation + all-contracts test
├── bin/                    # Launcher scripts + prebuilt Windows binaries
├── config/                 # Default config
├── network/                # Deployed contract addresses (testnet.json)
├── install / install.sh / install.ps1 / install.bat
└── AGENTS.md               # Operator notes (live deployment history)
```

## Uninstall

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

## Links

| Resource | URL |
|----------|-----|
| GitHub | https://github.com/XelisVault/xelis-vault |
| Discord | https://discord.gg/EjyvHFakY9 |
| X (XELIS Vault) | https://x.com/XelisVault |
| X (XELIS Layer-1) | https://x.com/xelis_crypto |
| Testnet explorer | https://testnet-explorer.xelis.io/ |
| XELIS documentation | https://docs.xelis.io |
| **v12 upgrade guide** | [docs/UPGRADE_v12.md](docs/UPGRADE_v12.md) |
| Whitepaper | [docs/WHITEPAPER.md](docs/WHITEPAPER.md) |
| Airdrop plan | [docs/AIRDROP_PLAN.md](docs/AIRDROP_PLAN.md) |
| Audit reports | [docs/AUDIT_v11.5_REMEDIATION.md](docs/AUDIT_v11.5_REMEDIATION.md) |
| Roadmap | [docs/ROADMAP.md](docs/ROADMAP.md) |

---

**Testnet software — do not use mainnet funds.** Backup your seed
(`~/.xelis-vault/wallet/`, plus the onboarding's `seed_backup/` copy) — it cannot be
recovered if lost. No financial advice. License: MIT.
