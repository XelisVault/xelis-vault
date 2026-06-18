# Changelog

All notable changes to XELIS Vault are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v4.2] — 2026-06-17

### Added
- **VLTToken v4.2**: New token contract with fixed 10M supply and deflationary burn mechanism
- **xUSD**: Stablecoin contract pegged to $1 USD via PSM + overcollateralization
- **StakedOracle v4.2**: New oracle based on permissionless VLT staking (replaces MinerOracle)
- **OracleGovernance**: VLT staker voting for feed management (add/update/remove feeds)
- **FaucetContract**: Testnet faucet with anti-abuse (100 XEL + 200 VLT per 24h, lifetime caps)
- **One-command installer** (`install.py`): Interactive installer for Linux/macOS/Windows
- **aggregation_keeper.py**: New off-chain script to trigger aggregation every block
- **USER_GUIDE.md**: Complete guide for end users (deposit, borrow, swap, faucet)
- **Comprehensive documentation**: Whitepaper v3, Roadmap, Provider Guide, Miner Guide, Testnet Deployment Guide
- Anti-spam mechanism: 1 submission per provider per feed per cycle
- Circuit breaker per feed (auto-pause if price moves >20%)
- Hard stale protection (revert if no price update for >100 blocks)

### Changed
- **MIN_STAKE reduced**: 1000 VLT → 100 VLT (10x more accessible, ROI 6 days with 100 providers)
- **VLT distribution revised**: 60% to oracle rewards (was 20%), 15% team (was 30%), no investors allocation
- **Block time confirmation**: 5 seconds (XELIS BlockDAG), recalculated all economic parameters
- **REWARD_PER_CYCLE**: 0.48 VLT (= 47,564,687 atomic), calibrated for 6M VLT over 10 years
- **VaultEngineV3**: Now resolves "StakedOracle" instead of "MinerOracle" via ContractRegistry
- **OracleGovernance**: Entry IDs aligned with StakedOracle v4.2 contract
- **VaultEngineV3**: Fixed xUSD burn call (entry ID 3, was 4)
- **VaultSwapV2**: Fixed xUSD burn call (entry ID 3, was 4)
- **Deploy script**: Now deploys xUSD + FaucetContract, configures minters/burners, refills faucet

### Removed
- MinerOracle contract (replaced by StakedOracle — miners can still be providers, but it's not required)
- Investor allocation (5% / 500k VLT) — community-driven project, no external investors
- `reputation` field from Provider struct (simplified design)
- `get_block_miner()` dependency (no longer needed with staking approach)

### Fixed
- 18 bugs identified in internal audit (see `docs/AUDIT.md`):
  - **Critical**: Fixed invalid Silex syntax for fixed-size arrays (`[T; N]`) → use dynamic `T[]`
  - **Critical**: Fixed `burn_from()` cross-account issue → StakedOracle handles burn directly
  - **Critical**: Fixed phantom loop in `aggregate()` that collected no submissions
  - **Critical**: Fixed parenthesization error in deviation calculation
  - **Critical**: Fixed xUSD burn entry ID mismatch in VaultEngineV3 and VaultSwapV2
  - **High**: Added `aggregate_now()` entry to allow keeper-triggered aggregation
  - **High**: Fixed entry ID mismatches between OracleGovernance and StakedOracle
  - **Medium**: Added cleanup of submission entries after aggregation
  - **Medium**: Added `get_provider_at(index)` for iteration
  - And 10 more minor fixes

### Security
- Internal audit completed (see `docs/AUDIT.md`)
- 7 points identified for validation with XELIS-Forge team before mainnet

---

## [v4.0] — 2026-05-15

### Added
- Initial StakedOracle design (with bugs, fixed in v4.2)
- VLTToken v4.0 with `burn_from()` (buggy, fixed in v4.2)
- price_provider.py script for permissionless providers

### Notes
- This version had critical bugs and should not be deployed
- All bugs fixed in v4.2

---

## [v3.0] — 2026-04-10

### Added
- MinerOracle contract — uses XELIS miners as price sources
- OracleGovernance for feed management
- miner_price_submit.py script for miner integration

### Removed
- PriceOracleV2 multi-bot design (replaced by MinerOracle)

### Notes
- MinerOracle was too restrictive (excluded non-miners)
- Replaced by StakedOracle in v4.0+

---

## [v2.0] — 2026-03-05

### Added
- PriceOracleV2 — multi-source oracle with 4 admin-controlled bots
- ContractRegistry — versioned upgrade pattern
- ReentrancyGuard, Pausable — reusable security modules
- VaultSwapV2 — AMM with MEV protection (slippage, circuit breaker)
- VaultEngineV2 — with Ciphertext encryption (theoretical API)

### Changed
- VaultEngine: collateral_plain → collateral_cipher (true confidentiality)
- Liquidation penalty: 5% → 10%
- Min collateral ratio: 150% → 200%
- Added grace period before liquidation (10 blocks)

### Security
- Identified critical issue: v1 stored amounts in plaintext despite whitepaper claims

---

## [v1.0] — 2026-02-01

### Added
- Initial 23-contract architecture
- PriceOracle v1 (single admin-controlled bot)
- VaultEngine v1 (with plaintext amounts — security issue)
- VaultSwap v1 (no slippage protection)
- Initial whitepaper and documentation

### Known Issues (fixed in later versions)
- VaultEngine stored collateral_plain and borrow_plain in plaintext
- PriceOracle was fully admin-controlled (single point of failure)
- VaultSwap had no slippage protection (sandwich attack vulnerable)
- Liquidation penalty was only 5% (insufficient for bad debt coverage)
- No upgrade mechanism
- No reentrancy guard
- No emergency pause

---

## Versioning Scheme

- **Major** (X.0.0): Breaking architectural changes (e.g., v3 → v4 was MinerOracle → StakedOracle)
- **Minor** (0.X.0): New features, backward-compatible (e.g., new contract, new feed)
- **Patch** (0.0.X): Bug fixes, security patches

---

## Migration Guides

### v3 → v4.2
See `docs/AUDIT.md` Section 8 for migration plan.

Key steps:
1. Deploy ContractRegistry
2. Deploy VLTToken, create asset, distribute initial supply
3. Deploy StakedOracle, configure (VLT, treasury, registry)
4. Set VLTToken minter to StakedOracle
5. Deploy OracleGovernance
6. Migrate VaultEngine state (if v3 was deployed)
7. Update frontend SDK to resolve contracts via registry

### v2 → v4.2
Skip v3, follow v3 → v4.2 migration.

### v1 → v4.2
Major migration. Contact the team for assistance.

---

*XELIS Vault — Confidential Finance for the Privacy Era*
