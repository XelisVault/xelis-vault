# XELIS Vault — Development Roadmap

> Last updated: 2026-06-24 — v5.0 release
> All dates are target estimates and may shift based on audit feedback, testnet stability, and community input.

## Current Status

**v5.0 (June 2026)** — Audit-remediated release. All 15 vulnerabilities from the v4.3 internal audit have been fixed. 33 Silex contracts written (13,220 lines, 630 entry functions). Source code ready for compilation with the official Silex compiler.

| Milestone | Status | Notes |
|-----------|--------|-------|
| Architecture design (v1 → v4.3) | ✅ Complete | 4 iterations based on internal review + Slixe feedback |
| Internal security audit (v4.3) | ✅ Complete | 15 findings (5 critical, 4 high, 4 medium, 2 low) |
| Remediation (v5.0) | ✅ Complete | All 15 findings fixed, Silex API compliance verified |
| Compilation (official Silex compiler) | ⏳ Pending | Awaiting Silex compiler availability for the team |
| Testnet deployment | ⏳ Pending | Q3 2026 target |
| External audit (Slixe / Hacken / Trail of Bits) | ⏳ Pending | Q4 2026 target |
| Mainnet deployment | ⏳ Pending | Q1 2027 target |

---

## Phase 1 — Testnet Launch (Q3 2026)

### Goal
Deploy the full XELIS Vault stack on XELIS testnet, validate end-to-end functionality with a small set of trusted miners, and gather community feedback.

### Deliverables

**1.1 Compilation & unit tests (July 2026)**
- Compile all 33 `.slx` files with the official Silex compiler
- Write unit tests for each contract (target: 80% branch coverage)
- Validate `docs/ENTRY_IDS.md` matches compiler-emitted entry table
- Set up CI pipeline running `scripts/extract_entry_ids.py` on every commit

**1.2 Testnet deployment (August 2026)**
- Deploy contracts in canonical order (see `WHITEPAPER.md` § 11)
- Initialize VLT token with `mint_batch` for team + treasury + DEX liquidity
- Register 3–5 initial miners (team-operated)
- Add first price feeds: XEL/USD, XEL/BTC, XEL/ETH
- Launch 2–3 `aggregation_keeper.py` instances on distinct servers
- Verify price feeds flow from `StakedOracle` → `VaultEngine` → `PSM` → `VaultSwapV2`

**1.3 Frontend dApp (August 2026)**
- Multi-page dApp: Dashboard, Vaults, Oracle, Swap, Chat, Mixer, Governance
- Wallet integration (XELIS Wallet, Genesix Wallet)
- Real-time price feed display, vault health factor monitoring
- Governance proposal creation/voting UI

**1.4 Documentation portal (August 2026)**
- Developer docs (Silex contract walkthroughs, integration guides)
- User guides (how to mine, how to borrow, how to swap)
- API reference (auto-generated from `docs/ENTRY_IDS.md`)
- Video tutorials

### Success Criteria
- All 33 contracts compile without errors
- Price feeds update every 25 seconds (5 blocks) with ≤5% deviation
- VaultEngine deposits/borrows/repays/liquidations work end-to-end
- PSM maintains xUSD peg within ±1% of $1
- Governance proposals can be created, voted on, queued, and executed

---

## Phase 2 — Testnet Stable & Community Onboarding (Q4 2026)

### Goal
Open testnet to public miners, grow to 10+ active miners, validate economic model, and prepare for mainnet.

### Deliverables

**2.1 Public miner onboarding (September 2026)**
- Open `XelisVaultMiner.register_miner` to public (still testnet VLT, no real value)
- Publish Miner Guide (how to set up `price_provider.py`, `aggregation_keeper.py`, `xelis_vault_miner.py`)
- Set up Discord `#miner-support` channel
- Target: 10+ active miners by end of September

**2.2 Bootstrap mode → Normal mode transition (October 2026)**
- Once 20+ active miners registered, call `StakedOracle.disable_bootstrap()`
- Min stake increases from 3 to 10 providers for price reads
- Lock-in period increases from 1 hour to 30 days
- Monitor for any service disruption

**2.3 External security audit (October–November 2026)**
- Engage Slixe (preferred — Silex expertise) for full review
- Engage second auditor (Hacken, Trail of Bits, or OpenZeppelin) for cross-validation
- Address any findings in v5.1 release
- Publish audit reports publicly

**2.4 Bug bounty launch (November 2026)**
- Launch on Immunefi
- 1% VLT allocation (100,000 VLT) over 2 years
- Reward distribution: 50% critical, 30% high, 15% medium, 5% low
- Max payout per critical: 25,000 VLT

**2.5 Mainnet preparation (November–December 2026)**
- Finalize mainnet contract addresses
- Prepare deployment scripts (`deploy/deploy_mainnet.py`)
- Set up monitoring infrastructure (keepers, dashboards, alerts)
- Recruit 20+ mainnet miners (KYC optional, stake required)
- Establish GuardianMultisig with 5 reputable community members

### Success Criteria
- 10+ active public miners
- 30+ days of continuous testnet operation without major incident
- External audit completed with no unresolved critical findings
- Bug bounty program live with ≥3 valid submissions
- 20+ mainnet miners committed

---

## Phase 3 — Mainnet Launch (Q1 2027)

### Goal
Deploy XELIS Vault on XELIS mainnet with real value, transition governance to community control, and establish long-term sustainability.

### Deliverables

**3.1 Mainnet deployment (January 2027)**
- Deploy all 33 contracts on XELIS mainnet
- Initialize VLT token with full 10M supply distribution
- Transfer admin role from deployer EOA to Timelock contract
- Set GuardianMultisig as `guardian_contract` on Timelock
- Activate first price feed (XEL/USD)
- Open VaultEngine for deposits/borrows

**3.2 Liquidity bootstrap (January–February 2027)**
- Seed VaultSwapV2 pools: VLT/XEL, xUSD/XEL, VLT/xUSD
- Provide initial PSM liquidity (10,000 XEL)
- Airdrop 200,000 VLT to community (1-year lock)
- Listing on first CEX/DEX (negotiations in progress)

**3.3 Governance handover (February 2027)**
- First community governance proposal: adjust `BASE_REWARD_ORACLE` based on testnet data
- Transfer `ADMIN_KEY` on all contracts to `Address::zero()` (admin fully via Timelock)
- GuardianMultisig operational with 5/7 quorum
- Establish OracleGovernance cadence (weekly proposals for parameter tweaks)

**3.4 Ecosystem expansion (March 2027)**
- Launch SavingsRate for xUSD holders (4% APR default)
- Launch RevenueShare distributing treasury fees to VLT stakers
- Launch Payroll for recurring on-chain salary payments
- Launch AssetVault for first RWA tokenization (real estate pilot)

### Success Criteria
- Mainnet live with $1M+ TVL within 30 days
- 20+ active miners maintaining 99.9% uptime
- xUSD peg maintained within ±2% of $1 for 30 consecutive days
- First community governance proposal executed successfully
- No critical security incidents

---

## Phase 4 — Scaling & Cross-Chain (Q2 2027 — Q4 2027)

### Goal
Scale the protocol to multi-chain, expand product surface, and become the default DeFi layer for the XELIS ecosystem.

### Deliverables

**4.1 VaultSwapV2 liquidity mining (April 2027)**
- Reward LPs with VLT emissions from treasury
- Target: $10M+ TVL across all pools
- Add more trading pairs (BTC, ETH, USDC via bridges)

**4.2 PrivacyMixer launch (May 2027)**
- Deploy ZK verifier contract
- Integrate with frontend dApp
- 3 denominations: 10, 100, 1000 XEL
- Optional: add VLT and xUSD mixing

**4.3 VaultChat launch (June 2027)**
- E2E encrypted messaging on XELIS
- Group chat with up to 50 members
- Message anchoring every 100 blocks
- Mobile wallet integration

**4.4 Cross-chain bridges (Q3 2027)**
- XELIS ↔ Ethereum bridge (for VLT and xUSD)
- XELIS ↔ BSC bridge
- XELIS ↔ Solana bridge (if Solana ZK proofs mature)
- Wrapped VLT (wVLT) on target chains for DeFi composability

**4.5 RWA marketplace (Q4 2027)**
- Tokenized real estate (first pilot: 1–3 properties)
- SealedBidAuction integration for private sales
- ComplianceModule for KYC/AML checks
- InsurancePool for RWA-specific risks

**4.6 Mobile wallet (Q4 2027)**
- iOS and Android apps
- Full XELIS Vault integration (view vaults, swap, govern)
- Biometric authentication
- Hardware wallet support (Ledger, Trezor)

### Success Criteria
- $50M+ TVL across all XELIS Vault products
- 50+ active miners
- 10,000+ unique wallet addresses
- Cross-chain bridges processing $1M+/month in volume
- First RWA tokenization completed

---

## Phase 5 — Long-Term Vision (2028+)

### Decentralization milestones
- **GuardianMultisig expansion** — from 5 to 7 guardians, all elected by VLT governance
- **Miner decentralization** — 100+ active miners, no single miner >5% of total stake
- **Oracle expansion** — 50+ price feeds (crypto, forex, commodities, stocks)
- **DAO transition** — all protocol parameters governed by VLT holders, no team veto

### Product surface expansion
- **Perpetual futures** — leveraged trading on VaultSwapV2 (long/short XEL, VLT, xUSD)
- **Options** — European-style options on VaultSwapV2
- **Yield aggregator** — auto-compounding vaults for LP positions
- **Insurance marketplace** — peer-to-peer coverage for smart contract risks
- **Identity** — XELIS-native DID system integrated with VaultChat and ComplianceModule

### Research areas
- **ZK-proof compression** — reduce on-chain verification cost for PrivacyMixer
- **Threshold signature schemes** — for GuardianMultisig (no single point of failure)
- **Cross-chain atomic swaps** — trustless XEL ↔ BTC swaps
- **Layer-2 scaling** — rollups or state channels for high-frequency VaultChat messages

### Sustainability
- **Treasury diversification** — convert 50% of treasury VLT to xUSD and XEL to reduce volatility
- **Revenue sharing** — 50% of treasury revenue distributed to VLT stakers, 50% reinvested
- **Bug bounty perpetual fund** — replenished from 1% of treasury annually

---

## Risk Factors & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Silex compiler bugs | Medium | High | External audit + bug bounty + formal verification of critical contracts |
| Oracle manipulation | Low | Critical | 10-layer security (range, deviation, circuit breaker, stale, bootstrap) + 30-day lock for mainnet miners |
| xUSD depeg | Medium | High | PSM arbitrage + redemption queue + stability fee + insurance pool |
| Governance capture | Low | High | 7-day timelock + 10% quorum + 50% approval + GuardianMultisig veto |
| Regulatory action | Medium | Medium | ComplianceModule for KYC/AML + jurisdictional restrictions + legal opinion |
| XELIS chain consensus failure | Low | Critical | XELIS BlockDAG has been audited and running on testnet for 12+ months |
| Miner collusion | Low | Medium | Median aggregation + 50% slash for malicious actors + reputation system |
| Frontend compromise | Medium | Medium | Static site generation + IPFS hosting + multi-sig controlled frontend keys |

---

## Community & Communication

### Channels
- **Discord** (primary): https://discord.gg/UHpYAWbG — real-time support, governance discussions, miner coordination
- **Twitter**: https://x.com/xelisvault — announcements, milestones, educational content
- **GitHub**: https://github.com/XelisVault/xelis-vault — source code, issues, PRs
- **Blog**: Medium publication (launching Q3 2026) — deep-dive articles, technical analyses
- **Newsletter**: monthly summary of progress, governance proposals, ecosystem updates

### Governance cadence
- **Weekly** — OracleGovernance proposals (parameter tweaks, feed additions)
- **Bi-weekly** — XelisVaultMiner budget factor auto-adjustment (on-chain, no governance needed)
- **Monthly** — community call on Discord (progress review, Q&A, roadmap updates)
- **Quarterly** — Governor proposals (major parameter changes, new product launches)
- **Annually** — full protocol review + audit + roadmap update

### Transparency commitments
- All governance proposals public 7 days before execution (timelock)
- All treasury transactions visible on-chain
- All miner slashing events emit on-chain events + Discord notification
- Quarterly transparency report (TVL, volume, fees earned, VLT burned, miners active)

---

## Change Log

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03 | Initial architecture (23 contracts) |
| v2.0 | 2026-04 | Added MinerPool, SyndicatePool, AssetVault, SealedBidAuction, PrivacyMixer, VaultChat |
| v3.0 | 2026-05 | Refactored to 33 contracts, unified XelisVaultMiner + StakedOracle |
| v4.0 | 2026-05 | Slixe fixes (bootstrap mode, 30-day lock, min 10 providers) |
| v4.1 | 2026-06 | Internal audit (18 bugs found, all fixed) |
| v4.2 | 2026-06 | Distribution corrected (60% oracle rewards, 10-year budget) |
| v4.3 | 2026-06 | Pre-audit polish |
| **v5.0** | **2026-06** | **Audit remediation — all 15 vulnerabilities fixed, Silex API compliance verified** |

---

## How to Contribute

### Developers
- Fork the repo, create a feature branch, submit a PR
- All PRs must pass CI (entry ID drift check + Silex compilation)
- Critical contract changes require a governance proposal + timelock execution

### Miners
- Read `docs/REWARD_SYSTEM.md` for the full reward mechanics
- Set up `price_provider.py` with API keys from CoinEx, MEXC, XELIS native price
- Stake 100 VLT and register via `XelisVaultMiner.register_miner`
- Run `aggregation_keeper.py` to trigger median aggregation

### Community
- Join Discord, introduce yourself in `#introductions`
- Participate in governance discussions in `#governance`
- Report bugs via GitHub Issues or Immunefi (for bounty-eligible findings)
- Help translate documentation (bounties available for non-English translations)

---

*XELIS Vault is an open-source, community-governed protocol. This roadmap is a living document — submit PRs to propose changes, additions, or corrections.*
