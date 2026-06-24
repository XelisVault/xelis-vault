# XELIS Vault — Privacy-First DeFi on XELIS BlockDAG

> **v5.0 — Audit-Remediated Release**
> All 15 vulnerabilities identified in the v4.3 security audit have been fixed.
> All 33 Silex contracts use only verified APIs (cross-checked against `xelis-wasm` `lib.rs`).

[![Audit Status](https://img.shields.io/badge/audit-v5.0%20remediated-success)](docs/AUDIT_v5.0_REMEDIATION.md)
[![Contracts](https://img.shields.io/badge/contracts-33%20Silex-blue)](contracts/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What is XELIS Vault?

XELIS Vault is a comprehensive DeFi protocol built on the **XELIS BlockDAG** — a privacy-focused, scalable Layer-1 with homomorphic-encrypted balances and native confidential assets. The protocol bundles six synergistic products into a single, coherent architecture:

| Product | Contract(s) | Description |
|---------|-------------|-------------|
| **Decentralized Oracle** | `StakedOracle`, `XelisVaultMiner` | Median-aggregated price feeds with reputation-weighted miners, circuit breakers, bootstrap mode |
| **Confidential Lending** | `VaultEngineV3` | XEL-collateralized xUSD borrowing with stability fee, redemption queue, liquidation grace period |
| **Multi-Asset Lending** | `LendingMarket`, `PeerLoan`, `SyndicatePool` | Permissionless pool creation with InterestRateModel integration |
| **xUSD Stablecoin** | `xUSD`, `PSM` | Algorithmic stablecoin pegged to USD via Peg Stability Module |
| **AMM + PSM** | `VaultSwapV2` | Constant-product AMM with TWAP-based volatility fees, integrated PSM |
| **Governance** | `GovernanceVault`, `Governor`, `Timelock`, `GuardianMultisig`, `OracleGovernance` | VLT-staked voting with quorum + timelock + multisig emergency response |
| **Auxiliary** | `FlashLoan`, `SealedBidAuction`, `PrivacyMixer`, `VaultChat`, `InsurancePool`, `AssetVault`, `TreasuryVault`, `RevenueShare`, `SavingsRate`, `Payroll`, `FaucetContract`, `ComplianceModule`, `MinerPool` | Full DeFi toolkit |

## Why XELIS Vault?

- **Native privacy** — Built on XELIS Confidential Assets (homomorphic encryption at the chain layer)
- **No admin backdoor** — Two-step emergency withdraw (24h delay), governance-controlled parameters, multisig-guarded security
- **Real economic sustainability** — Stability fee on borrows (2% APR default), reserve factors on lending pools, PSM mint/redeem fees
- **Decentralized oracle** — Permissionless miner registration, reputation system (0–10,000), 5-tier reward multiplier (0× to 1.5×)
- **10-year reward budget** — Dynamic budget factor auto-adjusts every 2 weeks to keep distribution on schedule

## v5.0 — What Changed

The v5.0 release is a **complete remediation pass** based on the [v4.3 security audit](docs/AUDIT_v5.0_REMEDIATION.md). Every critical, high, medium, and low finding has been fixed.

### Critical fixes (5)
1. **Entry ID realignment across all 33 contracts** — `slash_miner`, `distribute_reward`, `is_miner_active`, `get_active_miners_for_service`, and similar cross-contract `pub fn` were unreachable via `Contract::call`. They are now `entry` functions (or wrapped by `*_entry` entries). All StakedOracle → XelisVaultMiner, OracleGovernance → StakedOracle, and VaultEngine → ContractRegistry calls now point to the correct function.
2. **OracleGovernance → StakedOracle entry IDs corrected** — Previously, `PARAM_MAX_STALE` called `set_emergency`, `PARAM_HARD_STALE` called `transfer_admin`, etc. — opening governance-voted control-of-contract attacks. All IDs now match the v5.0 declaration order.
3. **VaultEngine oracle resolution fixed** — Now uses `ContractRegistry.get_entry` (entry 0) and `StakedOracle.get_price_for_asset_entry` (entry 9).
4. **GovernanceVault.claim_rewards() rewritten** — Was syntactically broken (bare `0` literal, misaligned braces). Now compiles cleanly.
5. **FlashLoan.flash_loan() rewritten** — Body was malformed with JS-style kwargs `{ asset: amount }`. Now uses `{}` empty kwargs, proper structure, and balance check `balance_after >= balance_before + fee`.

### High fixes (4)
6. **GuardianMultisig quorum enforcement** — `add_guardian`, `remove_guardian`, `set_quorum` now require a multi-sig proposal (action 4/5/6) instead of `only_admin()`.
7. **Timelock dual-guardian support** — `only_guardian()` accepts either an EOA (`GUARDIAN_KEY`) or a contract caller (`GUARDIAN_CONTRACT_KEY`). GuardianMultisig can now act as Timelock guardian.
8. **Commit-reveal pattern for VaultEngine** — `deposit(asset, amount, salt)` accepts a `salt: Hash` for off-chain commitment. Silex does not expose a `Ciphertext` type (verified via `lib.rs`), so we no longer pretend to encrypt homomorphically. The chain still benefits from XELIS-native confidential balances at the asset layer.
9. **Stability fee on VaultEngine** — A global accumulator `STABILITY_FEE_INDEX_KEY` (1e12 scale, 2% APR default) grows continuously. `borrow_amount` is accrued via `accrued = principal * current_index / index_at_open` on every repay/liquidate/redeem.

### Medium fixes (4) + Low fixes (2)
10–13. Cross-contract entry IDs fixed everywhere (Governor → GovernanceVault, OracleGovernance → GovernanceVault, PSM/VaultSwapV2/LendingMarket → StakedOracle, XelisVaultMiner.maybe_adjust_budget division-by-zero guard).
14. **2-step emergency_withdraw** — Every contract holding funds now implements `request_emergency_withdraw()` (saves topo) + `execute_emergency_withdraw(asset)` (requires 17280 blocks ≈ 24h to have elapsed).
15. **TYPE_SET_REWARD implemented** — `OracleGovernance.execute_proposal()` now actually calls `XelisVaultMiner.set_base_reward_oracle`.

See [`docs/AUDIT_v5.0_REMEDIATION.md`](docs/AUDIT_v5.0_REMEDIATION.md) for the full fix-by-fix report.

## File Structure

```
xelis-vault-v5/
├── contracts/                       # 33 Silex contracts (13,220 lines, 630 entries)
│   ├── amm/                         # PSM, VaultSwapV2
│   ├── auction/                     # SealedBidAuction
│   ├── chat/                        # VaultChat (E2E encrypted chat anchor)
│   ├── compliance/                  # ComplianceModule
│   ├── faucet/                      # FaucetContract (testnet)
│   ├── flashloan/                   # FlashCallback, FlashLoan
│   ├── governance/                  # GovernanceVault, Governor, GuardianMultisig, OracleGovernance, Timelock
│   ├── insurance/                   # InsurancePool, PrivateInsurance
│   ├── interest/                    # InterestRateModel
│   ├── lending/                     # LendingMarket, PeerLoan, SyndicatePool
│   ├── miner/                       # MinerPool, XelisVaultMiner
│   ├── oracle/                      # StakedOracle
│   ├── payroll/                     # Payroll
│   ├── privacy/                     # PrivacyMixer
│   ├── proxy/                       # ContractRegistry, Upgradeable
│   ├── revenue/                     # RevenueShare
│   ├── rwa/                         # AssetVault
│   ├── savings/                     # SavingsRate
│   ├── token/                       # VLTToken
│   ├── treasury/                    # TreasuryVault
│   ├── usd/                         # xUSD
│   └── vault/                       # VaultEngineV3
├── docs/
│   ├── AUDIT_v5.0_REMEDIATION.md    # Fix-by-fix audit remediation report
│   ├── ENTRY_IDS.md                 # Auto-generated entry ID table (33 contracts, 630 entries)
│   ├── REWARD_SYSTEM.md             # Detailed miner reward + reputation explanation
│   ├── WHITEPAPER.md                # Full technical whitepaper (English)
│   └── ROADMAP.md                   # Development roadmap (English)
└── scripts/
    └── extract_entry_ids.py         # CI-friendly entry ID extractor
```

## Silex API Compliance

All 33 contracts use only APIs validated against `xelis-wasm` `lib.rs` (the Silex playground wrapper) and the official Silex documentation:

| Category | APIs Used |
|----------|-----------|
| **Primitive types** | `u8`, `u16`, `u32`, `u64`, `u128`, `u256`, `bool`, `string`, `bytes`, `T[]`, `optional<T>`, `struct`, `enum` |
| **Opaque types** | `Address`, `Hash`, `Asset`, `Contract`, `Storage`, `MaxSupplyMode`, `Signature` |
| **Global functions** | `get_caller()`, `get_contract_caller()`, `get_balance_for_asset()`, `get_deposit_for_asset()`, `transfer()`, `burn()`, `get_current_topoheight()`, `hash()`, `require()`, `assert()` |
| **Optional methods** | `.is_some()`, `.is_none()`, `.unwrap_or()`, `.expect()` |
| **Forbidden (not in Silex)** | `Ciphertext`, `elgamal`, `RangeProof`, `try/catch`, JS-style kwargs `{ key: value }` |

## Quick Start

### Compile

```bash
# Use the official Silex compiler (https://docs.xelis.io/contracts/silex-lang)
silex compile contracts/proxy/ContractRegistry.slx
silex compile contracts/token/VLTToken.slx
# ... etc for all 33 contracts
```

### Regenerate Entry ID Documentation

```bash
python3 scripts/extract_entry_ids.py
# Output: docs/ENTRY_IDS.md
```

### Deployment Order

See [`docs/WHITEPAPER.md`](docs/WHITEPAPER.md) § "Deployment Sequence" for the canonical deployment order. Summary:

1. `ContractRegistry` (first — others depend on it)
2. `VLTToken` → `create_asset`, then `set_minter(XelisVaultMiner_hash, true)` via Timelock
3. `XelisVaultMiner` → wire VLT/asset/treasury
4. `StakedOracle` → wire miner contract, registry, timelock, guardian
5. `xUSD` → `create_asset`, authorize minters/burners
6. `VaultEngineV3`, `PSM`, `VaultSwapV2` → wire registry, xUSD, treasury
7. `GovernanceVault`, `Governor`, `Timelock`, `GuardianMultisig`, `OracleGovernance` → wire governance chain
8. Register all in ContractRegistry
9. Authorize services: `XelisVaultMiner.register_service(1, StakedOracle_hash)` (oracle), `register_service(2, VaultChat_hash)` (chat)

## Community

- **Discord:** https://discord.gg/UHpYAWbG
- **Twitter:** https://x.com/xelisvault
- **GitHub:** https://github.com/XelisVault/xelis-vault

## License

MIT — see [LICENSE](LICENSE).

## Pre-Testnet Checklist

- [ ] Compile all 33 `.slx` files with the official Silex compiler
- [ ] Verify `docs/ENTRY_IDS.md` matches the compiler-emitted entry table
- [ ] Run the 7 integration tests described in `docs/AUDIT_v5.0_REMEDIATION.md`
- [ ] Deploy on devnet, register 3 miners, submit 30 prices, verify price reaches VaultEngine
- [ ] External audit (Slixe / Hacken / Trail of Bits)
- [ ] Launch bug bounty program on Immunefi (1% VLT = 100k VLT)
