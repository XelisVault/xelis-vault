# Compatibility Table — XELIS Vault v4.2

> Reference document for all cross-contract calls.

---

## 📊 Overview

**29 Silex contracts** organized in 14 categories:

| # | Catégorie | Contrats |
|---|-----------|----------|
| 1 | Token | VLTToken, xUSD |
| 2 | Oracle | StakedOracle |
| 3 | Governance | OracleGovernance, GovernanceVault, Governor, Timelock, GuardianMultisig |
| 4 | Lending | VaultEngineV3, LendingMarket, PeerLoan, SyndicatePool |
| 5 | AMM | VaultSwapV2, PSM |
| 6 | Savings | SavingsRate |
| 7 | Flash Loan | FlashLoan, FlashCallback |
| 8 | Auction | SealedBidAuction |
| 9 | RWA | AssetVault |
| 10 | Treasury | TreasuryVault, RevenueShare, Payroll |
| 11 | Insurance | InsurancePool, PrivateInsurance |
| 12 | Compliance | ComplianceModule |
| 13 | Testnet | FaucetContract |
| 14 | Infrastructure | ContractRegistry, Upgradeable, InterestRateModel |

---

## 🔗 Cross-Contract Dependencies

### VLTToken.slx — Entry IDs
| ID | Entry | Called by |
|----|-------|------------|
| 0 | `mint_to(to, amount)` | StakedOracle, deploy |
| 1 | `burn_own(amount)` | TreasuryVault, admin |
| 2 | `burn_from(amount)` (pub fn) | StakedOracle (slashing) |
| 3 | `mint_batch(recipients, amounts)` | deploy |
| 4 | `set_minter(hash, enabled)` | Timelock |
| 5 | `set_burner(hash, enabled)` | Timelock |
| 6 | `get_asset_hash() -> Hash` (pub fn) | deploy, scripts |
| 7 | `get_max_supply() -> u64` (pub fn) | dashboard |
| 8 | `get_total_burned() -> u64` (pub fn) | dashboard |
| 9 | `get_circulating_supply() -> u64` (pub fn) | dashboard |

### xUSD.slx — Entry IDs
| ID | Entry | Called by |
|----|-------|------------|
| 0 | `create_asset()` | deploy |
| 1 | `mint_tokens(to, amount)` (pub fn) | VaultEngine, VaultSwap, PSM, SavingsRate |
| 2 | `mint_split(to, amount, treasury, fee)` (pub fn) | VaultEngine, PSM |
| 3 | `burn_tokens(amount)` (pub fn) | VaultEngine, VaultSwap, PSM |
| 4 | `transfer_tokens(to, amount)` | user |
| 5 | `get_asset_hash() -> Hash` (pub fn) | scripts, deploy |
| 6 | `get_asset_info()` (pub fn) | dashboard |
| 7 | `set_minter(hash, enabled)` | Timelock |
| 8 | `set_burner(hash, enabled)` | Timelock |

### StakedOracle.slx — Entry IDs
| ID | Entry | Called by |
|----|-------|------------|
| 0 | `register_provider()` | user/provider |
| 1 | `increase_stake(amount)` | provider |
| 2 | `decrease_stake(amount)` | provider |
| 3 | `deregister_provider()` | provider |
| 4 | `submit_price(feed_id, price)` | provider |
| 5 | `aggregate_now(feed_id)` | keeper |
| 6 | `add_feed(name, asset, decimals, min, max)` | OracleGovernance |
| 7 | `update_feed(feed_id, min, max, decimals)` | OracleGovernance |
| 8 | `set_feed_active(feed_id, active)` | OracleGovernance |
| 9 | `trigger_feed_cb(feed_id, reason)` | GuardianMultisig |
| 10 | `reset_feed_cb(feed_id)` | Timelock |
| 11 | `pause(reason)` | GuardianMultisig |
| 12 | `unpause()` | Timelock |
| 13 | `set_min_stake(amount)` | Timelock |
| 14 | `set_reward_per_cycle(amount)` | OracleGovernance |
| 15 | `set_slash_bps(bps)` | Timelock |
| 16 | `set_max_deviation_bps(bps)` | OracleGovernance |
| 17 | `set_cb_threshold_bps(bps)` | OracleGovernance |
| 18 | `set_aggregation_blocks(n)` | OracleGovernance |
| 19 | `set_max_stale_blocks(n)` | OracleGovernance |
| 20 | `set_hard_stale_blocks(n)` | OracleGovernance |
| pub fn | `get_price(name) -> u64` | VaultEngine, VaultSwap, PSM, LendingMarket |
| pub fn | `get_price_for_asset(asset) -> u64` | VaultEngine, LendingMarket |
| pub fn | `get_feed_id(name) -> u64` | scripts, deploy |
| pub fn | `get_provider(addr)` | dashboard |
| pub fn | `get_providers_count() -> u64` | dashboard |
| pub fn | `get_price_meta(feed_id)` | dashboard |

### ContractRegistry.slx — Entry IDs
| ID | Entry | Called by |
|----|-------|------------|
| 0 | `get(name) -> Hash` (pub fn) | Tous les contrats |
| 1 | `register(name, hash)` | deploy |
| 2 | `upgrade(name, new_hash)` | Timelock |
| 3 | `rollback(name)` | Timelock |
| 4 | `get_version(name) -> u64` (pub fn) | dashboard |
| 5 | `list_names() -> u64` (pub fn) | dashboard |

### VaultEngineV3.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `reg.call(0u16, ["StakedOracle"], {})` | ContractRegistry | 0 | Resolve oracle |
| `oracle.call(0u16, [Hash::zero()], {})` | StakedOracle | pub fn | Get XEL price |
| `xusd.call(2u16, [caller, net, treasury, fee], {})` | xUSD | 2 | mint_split on borrow |
| `xusd.call(3u16, [repay_amount], {})` | xUSD | 3 | burn_tokens on repay/redeem |

### PSM.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `oracle.call(0u16, ["XEL/USD"], {})` | StakedOracle | pub fn | Get XEL price |
| `xusd.call(2u16, [caller, net_xusd, treasury, fee], {})` | xUSD | 2 | mint_split on PSM mint |
| `xusd.call(3u16, [xusd_amount], {})` | xUSD | 3 | burn_tokens on PSM redeem |

### VaultSwapV2.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `reg.call(0u16, ["StakedOracle"], {})` | ContractRegistry | 0 | Resolve oracle |
| `oracle.call(0u16, [XEL_ASSET], {})` | StakedOracle | pub fn | Get XEL price for PSM |
| `xusd.call(2u16, [caller, net_xusd, treasury, fee], {})` | xUSD | 2 | mint_split (legacy PSM) |
| `xusd.call(3u16, [xusd_amount], {})` | xUSD | 3 | burn_tokens (legacy PSM) |

### StakedOracle.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `vlt.call(0u16, [provider_addr, amount], {})` | VLTToken | 0 | mint_to (rewards) |
| `burn(burn_amount, vlt_asset)` | native XELIS | - | Burn slashed VLT (50%) |
| `transfer(treasury, treasury_amount, vlt_asset)` | native XELIS | - | Transfer slashed VLT (50%) |

### OracleGovernance.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `gv.call(0u16, [addr], {})` | GovernanceVault | pub fn | Get voting power |
| `oracle.call(6u16, [...], {})` | StakedOracle | 6 | add_feed (after vote) |
| `oracle.call(7u16, [...], {})` | StakedOracle | 7 | update_feed |
| `oracle.call(8u16, [...], {})` | StakedOracle | 8 | set_feed_active |
| `oracle.call(14u16, [...], {})` | StakedOracle | 14 | set_reward_per_cycle |
| `oracle.call(16u16, [...], {})` | StakedOracle | 16 | set_max_deviation_bps |
| `oracle.call(9u16, [...], {})` | StakedOracle | 9 | trigger_feed_cb |
| `oracle.call(10u16, [...], {})` | StakedOracle | 10 | reset_feed_cb |

### Governor.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `gv.call(3u16, [addr], {})` | GovernanceVault | pub fn | Get voting power |
| `gv.call(5u16, [], {})` | GovernanceVault | pub fn | Get total voting power |
| `tl.call(0u16, [...], {})` | Timelock | 0 | submit_proposal (after queue) |

### Timelock.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `target.call(entry_id, [], params)` | Any target | varies | Execute approved proposal |

### LendingMarket.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `oracle.call(0u16, [asset], {})` | StakedOracle | pub fn | Get asset price |
| `irm.call(0u16, [utilization], {})` | InterestRateModel | pub fn | Get borrow rate |
| `irm.call(1u16, [utilization], {})` | InterestRateModel | pub fn | Get supply rate |

### FlashLoan.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `cb.call(0u16, [...], {})` | FlashCallback | 0 | on_flash_loan callback |

### AssetVault.slx — Outgoing Calls
| Appel | Contrat cible | Entry ID | But |
|-------|---------------|----------|-----|
| `compliance.call(0u16, [...], {})` | ComplianceModule | pub fn | check_transfer |

---

## ✅ Silex API Validation Results

Benchmark against official XELIS docs (docs.xelis.io).

| # | API | Status | Notes |
|---|-----|--------|-------|
| 1 | **Ciphertext** | ⚠️ PARTIAL | `Ciphertext::new(addr, amount)` documented (not `encrypt`). `.add(plaintext)`, `.sub(plaintext)`, `.zero()` confirmed. `.decrypt()` **NOT in docs** — code fixed to match documented API |
| 2 | **Asset::create** | ✅ LIKELY | `Asset::create(max_supply, name, ticker, decimals, MaxSupplyMode)` matches asset docs. Needs compilation verification |
| 3 | **Dynamic arrays** | ✅ CONFIRMED | `T[]`, `array.push(el)`, `array.len()`, `array[i]` all documented in Silex Lang + Std Lib |
| 4 | **Contract::call** | ✅ CONFIRMED | `contract.call(entry_id: u16, args: any[], deposits: map<Hash, u64>)` matches documented pattern. Mixed types via `any[]` |
| 5 | **Hash → Address** | ❌ UNDOCUMENTED | `.to_address()` NOT in docs. Hash has `.to_hex()`, `.to_bytes()`, `.to_u256()` only. Must ask XELIS-Forge |
| 6 | **hash() function** | ❌ FIXED | Bare `hash(str)` doesn't exist. Use `Hash::blake3(input.to_bytes())`. Fixed in SealedBidAuction |
| 7 | **burn() native** | ✅ CONFIRMED | `burn(amount: u64, asset: Hash) → bool` documented. Burns from contract balance |

### Code Changes Applied

- `VaultEngineV3.slx`: `Ciphertext::encrypt(amount, addr)` → `Ciphertext::new(addr, amount)`. `.add(Ciphertext)` / `.sub(Ciphertext)` → `.add(plaintext)` / `.sub(plaintext)` (in-place, per docs)
- `SealedBidAuction.slx`: `hash(reveal_data)` → `Hash::blake3(reveal_data.to_bytes())`

### Remaining Unknowns (ask XELIS-Forge)

1. Does `Ciphertext::decrypt()` exist in Silex? Used heavily in VaultEngineV3 for reading vault state.
2. Does `Hash::to_address()` exist? Used in FlashLoan.slx and FlashCallback.slx for Hash→Address conversion.
3. Is `Asset::create()` signature confirmed as `(max_supply, name, ticker, decimals, MaxSupplyMode)`?

---

## ✅ Consistency Checklist

- [x] Tous les contrats ont un `hook constructor()` qui initialise l'admin
- [x] Tous ont `only_admin()` avec fallback Timelock
- [x] Tous ont `pause()` / `unpause()` (sauf InterestRateModel qui est read-only)
- [x] Tous ont `set_timelock()` + `set_timelock_tl()` (pub fn)
- [x] Tous ont `transfer_admin()`
- [x] Tous ont `get_version()`
- [x] Tous utilisent `Hash::zero()` pour XEL natif
- [x] VaultEngine, VaultSwap, PSM utilisent tous entry ID 3 pour `xUSD.burn_tokens()`
- [x] VaultEngine, VaultSwap, PSM utilisent tous entry ID 2 pour `xUSD.mint_split()`
- [x] StakedOracle utilise entry ID 0 pour `VLTToken.mint_to()`
- [x] Tous les contrats résolvent leurs dépendances via ContractRegistry (quand applicable)

---

*Last updated: June 2026 — v4.2*
