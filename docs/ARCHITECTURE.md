# Architecture Documentation — XELIS Vault v4.2

> System design and contract interaction patterns.

---

## Overview

XELIS Vault v4.2 is built on 8 smart contracts organized in 4 layers:

1. **Token Layer** — VLTToken (governance token)
2. **Oracle Layer** — StakedOracle + OracleGovernance
3. **Application Layer** — VaultEngine + VaultSwap
4. **Infrastructure Layer** — ContractRegistry + security modules

---

## Contract Dependency Graph

```
                    ┌─────────────────┐
                    │ ContractRegistry│
                    │   (upgrade)     │
                    └────────┬────────┘
                             │
                             │ resolve("X")
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌────────────────┐   ┌───────────────┐
│  VLTToken     │   │ StakedOracle   │   │ VaultEngineV3 │
│  (token)      │   │  (oracle)      │   │  (lending)    │
└───────┬───────┘   └────────┬───────┘   └───────┬───────┘
        │                    │                   │
        │ mint_to()          │ get_price()       │ get_price()
        │ (minter)           │                   │
        └────────────────────┼───────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  VaultSwapV2   │
                    │  (AMM + PSM)   │
                    └────────────────┘

                    ┌────────────────┐
                    │OracleGovernance│
                    │   (vote)       │
                    └────────┬───────┘
                             │
                             │ add_feed(), set_*()
                             │ (via Timelock)
                             ▼
                    ┌────────────────┐
                    │ StakedOracle   │
                    └────────────────┘
```

---

## Entry IDs Reference

For cross-contract calls, each contract exposes entries by ID. The IDs are determined by the order of `entry` declarations in the source file.

### VLTToken.slx
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `mint_to(to: Address, amount: u64)` | StakedOracle (rewards) |
| 1 | `burn_own(amount: u64)` | Any holder |
| 2 | `burn_from(amount: u64)` (pub fn) | Authorized burners |
| 3 | `get_asset_hash() -> Hash` (pub fn) | Dashboard, scripts |
| 4 | `get_max_supply() -> u64` (pub fn) | Dashboard |
| 5 | `get_total_burned() -> u64` (pub fn) | Dashboard |
| 6 | `get_circulating_supply() -> u64` (pub fn) | Dashboard |
| 7 | `set_minter(contract_hash: Hash, enabled: bool)` | Admin (Timelock) |
| 8 | `set_burner(contract_hash: Hash, enabled: bool)` | Admin (Timelock) |

### StakedOracle.slx
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `register_provider()` | User (provider registration) |
| 1 | `increase_stake(amount: u64)` | Provider |
| 2 | `decrease_stake(amount: u64)` | Provider |
| 3 | `deregister_provider()` | Provider |
| 4 | `submit_price(feed_id: u64, price: u64)` | Provider |
| 5 | `aggregate_now(feed_id: u64)` | Keeper |
| 6 | `add_feed(name, asset, decimals, min, max)` | OracleGovernance |
| 7 | `update_feed(feed_id, min, max, decimals)` | OracleGovernance |
| 8 | `set_feed_active(feed_id, active)` | OracleGovernance |
| 9 | `trigger_feed_cb(feed_id, reason)` | Guardian |
| 10 | `reset_feed_cb(feed_id)` | Admin |
| 11 | `pause(reason: string)` | Guardian |
| 12 | `unpause()` | Admin |
| 13 | `set_min_stake(amount)` | Admin |
| 14 | `set_reward_per_cycle(amount)` | OracleGovernance |
| 15 | `set_slash_bps(bps)` | Admin |
| 16 | `set_max_deviation_bps(bps)` | OracleGovernance |
| 17 | `set_cb_threshold_bps(bps)` | OracleGovernance |
| 18 | `set_aggregation_blocks(n)` | OracleGovernance |
| 19 | `set_max_stale_blocks(n)` | OracleGovernance |
| 20 | `set_hard_stale_blocks(n)` | OracleGovernance |
| 21-28 | `set_*()` (wiring) | Admin |

### ContractRegistry.slx (inherited from v2)
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `get(name: string) -> Hash` (pub fn) | All contracts |
| 1 | `register(name, hash)` | Admin |
| 2 | `upgrade(name, new_hash)` | Timelock |
| 3 | `rollback(name)` | Timelock |

---

## Cross-Contract Call Examples

### VaultEngineV3 → StakedOracle (get XEL price)

```silex
fn get_oracle() -> Contract {
    let s: Storage = Storage::new()
    let reg_hash: Hash = s.load(REGISTRY_KEY).expect("regnoset")
    let reg: Contract = Contract::new(reg_hash).expect("regnf")
    let oracle_hash: Hash = reg.call(0u16, ["StakedOracle"], {})
    require(oracle_hash != Hash::zero(), "oraclenotfound")
    return Contract::new(oracle_hash).expect("oraclenf")
}

fn get_xel_price() -> u64 {
    let oracle: Contract = get_oracle()
    let price: u64 = oracle.call(0u16, [Hash::zero()], {})
    //                          ^ get_price_for_asset(Hash::zero())
    //                          Note: get_price_for_asset is the first pub fn
    //                          If it's not ID 0, adjust accordingly
    require(price > 0, "noprice")
    return price
}
```

### StakedOracle → VLTToken (mint rewards)

```silex
fn distribute_reward(provider_addr: Address, amount: u64) {
    let s: Storage = Storage::new()
    let vlt_hash: Hash = s.load(VLT_CONTRACT_KEY).expect("vcnoset")
    let vlt: Contract = Contract::new(vlt_hash).expect("vcnf")
    // VLT.mint_to(to, amount) — entry ID 0
    let _ = vlt.call(0u16, [provider_addr, amount], {})
    // ...
}
```

### OracleGovernance → StakedOracle (add feed)

```silex
// After governance vote approved
// StakedOracle.add_feed(name, asset, decimals, min, max) — entry ID 6
let _ = oracle.call(6u16, [
    proposal.feed_name,
    proposal.feed_asset.to_string(),
    proposal.feed_decimals as u64,
    proposal.feed_min,
    proposal.feed_max
], {})
```

---

## Storage Layout

Each contract uses its own storage namespace (no collision possible).

### VLTToken Storage Keys
- `"a"` — Admin address
- `"tl"` — Timelock contract hash
- `"ea"` — Emergency address
- `"reg"` — ContractRegistry hash
- `"ah"` — VLT asset hash
- `"ms"` — Max supply (10M)
- `"tb"` — Total burned counter
- `"mi_<hash>"` — Minter authorization (bool)
- `"bu_<hash>"` — Burner authorization (bool)

### StakedOracle Storage Keys
- `"a"`, `"tl"`, `"ea"`, `"gd"`, `"reg"`, `"pz"` — Standard admin/guardian/pause
- `"vc"`, `"va"`, `"tr"` — VLT contract hash, VLT asset hash, treasury address
- `"ms"`, `"rpc"`, `"sb"`, `"mdb"`, `"cbt"`, `"ab"`, `"msb"`, `"hsb"` — Config
- `"pc"` — Providers count
- `"pv_<addr>"` — Provider struct
- `"pid_<addr>"` — Provider index
- `"pl_<idx>"` — Provider address (for iteration)
- `"fc"` — Feeds count
- `"fd_<id>"` — Feed struct
- `"fn_<id>"` — Feed name
- `"fa_<id>"` — Feed active flag
- `"fg_<id>"` — Aggregated price
- `"cb_<id>"` — Feed circuit breaker flag
- `"sc_<feed>_<cycle>"` — Submission count for cycle
- `"se_<feed>_<cycle>_<idx>"` — Submission entry
- `"sp_<feed>_<cycle>_<addr>"` — Anti-spam flag
- `"cy_<id>"` — Current cycle per feed
- `"la_<id>"` — Last aggregation topoheight

---

## Security Model

### Access Control Hierarchy

```
Guardian (multisig)
   ├── Can pause contracts in emergency
   └── Cannot unpause (only admin can)

Admin (governance via Timelock)
   ├── Can change all configuration
   ├── Can transfer admin
   ├── Can unpause
   └── Cannot bypass Timelock (48h delay)

Timelock (48h delay)
   ├── Executes governance proposals
   └── Emergency mode (2h delay, guardian-only)

Emergency address
   └── Can withdraw funds in catastrophic failure
```

### Slashing Mechanics

When a provider submits an outlier price (outside 5% of median):

```
Provider stake: 1000 VLT
Slash amount: 1% × 1000 = 10 VLT

10 VLT split:
├── 5 VLT burned (VLTToken.burn)
└── 5 VLT to treasury (transfer)

Provider stake after: 990 VLT
Provider status: still active (>= MIN_STAKE = 1000 VLT? NO)
                → if stake < 1000 VLT, provider deactivated
```

In this example, the provider would be deactivated after 10 outliers (loss of 100 VLT = 10% of stake). To reactivate, they must call `increase_stake()` to bring stake back above MIN_STAKE.

---

## Upgrade Pattern

Since Silex doesn't support `delegatecall`, we use a **Versioned Registry** pattern:

1. **Deploy new version** of a contract (e.g., StakedOracle v4.3)
2. **Propose upgrade** via Timelock: `ContractRegistry.upgrade("StakedOracle", new_hash)`
3. **Wait 48h** (Timelock delay)
4. **Execute** the upgrade
5. **Call `migrate_from(old_hash)`** on the new version to copy state
6. **Verify** migration: `new_version.get_providers_count() == old_version.get_providers_count()`
7. **Update frontend** to point to new address (or use registry directly)

Rollback: `ContractRegistry.rollback("StakedOracle")` — reverts to previous version.

See `docs/UPGRADE.md` for the complete upgrade procedure.

---

## Performance Considerations

### Aggregation Cycle Cost

Each aggregation cycle involves:
- Iterating through N submissions (N ≤ 256)
- Sorting (bubble sort, O(N²) worst case)
- Computing median, deviation
- Distributing rewards (M mint_to calls, M ≤ N)

For 50 providers, gas cost is ~50,000 XELIS operations per cycle. At 1 cycle per 25s = 3,456 cycles/day, that's 172.8M operations/day — well within XELIS BlockDAG capacity.

### Storage Growth

Each cycle stores:
- Submission entries: N entries × ~100 bytes = 25 KB per cycle (for 50 providers)
- These are cleaned up after aggregation

Per day: 3,456 × 25 KB = ~85 MB/day of storage churn (mostly cleaned up)

### Recommendation
Run an auto-pruning daemon: `xelis_daemon --auto-prune-keep-n-blocks 10000`

---

## Monitoring Recommendations

### Critical Metrics

1. **Oracle health**
   - `staked_oracle_cycle` — should increment every 25s
   - `staked_oracle_aggregated_price` — should be non-zero
   - `staked_oracle_providers_count` — should be ≥ 5

2. **VLT economics**
   - `vlt_circulating_supply` — should decrease over time (deflation)
   - `vlt_total_burned` — should increase
   - `vlt_max_supply` — constant at 10M

3. **Provider economics**
   - `provider_estimated_rewards_vlt` — should increase
   - `provider_total_slashed` — should stay low

4. **System health**
   - Daemon synced: `get_info.synced == true`
   - Topoheight advancing
   - All systemd services active

### Alerting

Set up alerts for:
- Oracle cycle not advancing for >2 minutes
- Aggregated price = 0
- Provider count drops below 5
- VLT supply increases (should never happen — would indicate a bug)
- Daemon not synced for >5 minutes

---

## Future Considerations

### Reputation System (v5.0)
Add a reputation score per provider:
- +1 per valid price
- -3 per outlier
- Provider auto-deactivated if reputation < threshold
- Reputation affects reward multiplier (1.0x to 1.5x)

### Multi-asset Collateral (v5.0)
Extend VaultEngine to accept any XELIS Confidential Asset as collateral, not just XEL. Each asset would need its own price feed in StakedOracle.

### Cross-chain Bridges (v6.0)
Bridge xUSD to other chains (Ethereum, Solana) via atomic swaps or wrapped tokens. VLT remains XELIS-native.

### ZK Compliance Layer (v5.0)
Allow providers to prove KYC/AML compliance without revealing identity. Required for institutional adoption.

---

## References

- [Silex Language Documentation](https://docs.xelis.io/features/smart-contracts/silex)
- [XELIS Virtual Machine](https://github.com/xelis-project/xelis-vm)
- [XELIS-Forge Smart Contracts](https://github.com/XELIS-Forge/smart-contracts)
- [Twisted ElGamal on Ristretto255](https://github.com/xelis-project/xelis-he)

---

*Last updated: June 2026 — v4.2*
