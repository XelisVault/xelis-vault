# Architecture Documentation — XELIS Vault v4.3

> System design and contract interaction patterns.

---

## Overview

XELIS Vault v4.3 is built on **33 smart contracts** organized in 14 layers:

1. **Token Layer** — VLTToken, xUSD
2. **Oracle Layer** — StakedOracle
3. **Mining Layer** — XelisVaultMiner, MinerPool  *(new in v4.3)*
4. **Governance Layer** — OracleGovernance, GovernanceVault, Governor, Timelock, GuardianMultisig
5. **Application Layer** — VaultEngine, VaultSwap, PSM, SavingsRate, FlashLoan, LendingMarket, PeerLoan, SyndicatePool
6. **RWA & Treasury Layer** — AssetVault, TreasuryVault, RevenueShare, Payroll
7. **Insurance Layer** — InsurancePool, PrivateInsurance
8. **Auction Layer** — SealedBidAuction
9. **Chat Layer** — VaultChat  *(new in v4.3)*
10. **Privacy Layer** — PrivacyMixer  *(new in v4.3)*
11. **Compliance Layer** — ComplianceModule
12. **Testnet Infrastructure** — FaucetContract
13. **Infrastructure Layer** — ContractRegistry, Upgradeable, ReentrancyGuard, Pausable, InterestRateModel
14. **Flash Loan Callbacks** — FlashCallback

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
        │                    │ distribute_reward │
        │                    │ slash_miner       │
        │                    │       │           │
        │                    └───────┼───────────┘
        │                            │
        │                            ▼
        │                   ┌────────────────┐
        │                   │ XelisVaultMiner│  ◄── new in v4.3
        │                   │  (miner layer) │
        │                   │  reputation   │
        │                   │  budget ctrl  │
        │                   └────┬────┬──────┘
        │                        │    │
        │           distribute_  │    │ distribute_
        │         pool_rewards   │    │  reward()
        │                        ▼    ▼
        │                   ┌────────┐ ┌──────────┐
        │                   │MinerPool│ │ VaultChat│  ◄── new in v4.3
        │                   │ (pools)│ │  (chat)  │
        │                   └────────┘ └────┬─────┘
        │                                  │ anchor_messages
        │                                  ▼
        │                           (XELIS Chain)
        │
        └────────────────────┬───────────────────┐
                             │                   │
                             ▼                   ▼
                    ┌────────────────┐   ┌────────────────┐
                    │  VaultSwapV2   │   │ PrivacyMixer   │  ◄── new in v4.3
                    │  (AMM + PSM)   │   │ (anonymity)    │
                    └────────────────┘   └────────────────┘

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

Key new flows in v4.3:

- `StakedOracle` no longer mints rewards directly. After aggregation, it calls `XelisVaultMiner.distribute_reward(miner_addr, 1, is_valid)`.
- `VaultChat` relayers (which are miners with the chat bit set in their `services_mask`) call `anchor_messages()` every hour. They earn chat rewards via `XelisVaultMiner.distribute_reward(miner_addr, 2, true)`.
- If a miner is in a pool, `XelisVaultMiner.distribute_reward()` forwards the reward to `MinerPool.distribute_pool_rewards()` instead of minting directly to the miner.
- `PrivacyMixer` is self-contained: it talks only to its configurable ZK verifier contract and the asset layer.

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
| pub fn | `get_price(name)` | VaultEngine, VaultSwap, PSM, LendingMarket |
| pub fn | `get_price_for_asset(asset)` | VaultEngine, LendingMarket |
| pub fn | `get_feed_id(name)` | scripts, deploy |
| pub fn | `get_provider(addr)` | dashboard |
| pub fn | `get_providers_count()` | dashboard |
| pub fn | `get_provider_at(index)` | dashboard |
| pub fn | `get_price_meta(feed_id)` | dashboard |
| pub fn | `get_cycle(feed_id)` | dashboard |
| pub fn | `get_submissions_count(feed_id, cycle)` | dashboard |
| pub fn | `get_feeds_count()` | dashboard |
| pub fn | `get_feed(feed_id)` | dashboard |
| pub fn | `get_config()` | dashboard |
| pub fn | `get_total_staked()` | dashboard |

### XelisVaultMiner.slx — Entry IDs *(new in v4.3)*
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `register_miner(endpoint_url, miner_pubkey, services_mask)` | Miner |
| 1 | `enable_service(service_id)` | Miner |
| 2 | `disable_service(service_id)` | Miner |
| 3 | `increase_stake(amount)` | Miner |
| 4 | `decrease_stake(amount)` | Miner |
| 5 | `deregister_miner()` | Miner |
| 6 | `submit_heartbeat()` | Miner (script) |
| pub fn | `slash_miner(miner_addr, severity, reporter)` | StakedOracle, VaultChat |
| pub fn | `distribute_reward(miner_addr, service_id, is_valid)` | StakedOracle, VaultChat |
| pub fn | `is_miner_active(addr, service_id) -> bool` | VaultChat, MinerPool |
| pub fn | `get_miner_stake(addr) -> u64` | MinerPool |
| pub fn | `get_miner_reputation(addr) -> u64` | MinerPool, dashboard |
| pub fn | `get_reputation_tier(rep) -> u8` | dashboard |
| pub fn | `get_miner(addr)` | dashboard |
| pub fn | `get_miners_count() -> u64` | dashboard |
| pub fn | `get_miner_at(index)` | dashboard |
| pub fn | `get_total_staked() -> u64` | dashboard |
| pub fn | `get_active_miners_count() -> u64` | dashboard |
| pub fn | `get_active_miners_for_service(service_id) -> u64` | dashboard |
| pub fn | `get_config()` | dashboard |
| pub fn | `get_budget_info()` | dashboard |
| pub fn | `is_authorized_service(contract_hash) -> bool` | scripts |
| entry | `register_service(service_id, contract_hash)` | Admin (Timelock) |
| entry | `unregister_service(contract_hash)` | Admin (Timelock) |
| entry | `set_min_stake(amount)` | Admin (Timelock) |
| entry | `set_heartbeat_interval(blocks)` | Admin (Timelock) |
| entry | `set_heartbeat_timeout(blocks)` | Admin (Timelock) |
| entry | `set_base_reward_oracle(amount)` | Admin (Timelock) |
| entry | `set_base_reward_chat(amount)` | Admin (Timelock) |
| entry | `set_total_budget(amount)` | Admin (Timelock) |
| entry | `set_target_duration(blocks)` | Admin (Timelock) |
| entry | `set_vlt_contract(vc)`, `set_vlt_asset(va)`, `set_treasury(t)`, `set_registry(reg)`, `set_timelock(tl)`, `set_guardian(g)`, `set_emergency(e)` | Admin (Timelock) |
| entry | `pause(reason)`, `unpause()`, `transfer_admin(new_admin)` | Admin / Guardian |

### MinerPool.slx — Entry IDs *(new in v4.3)*
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `create_pool(name, description, creator_commission_bps)` | Miner (creator) |
| 1 | `join_pool(pool_id)` | Miner |
| 2 | `leave_pool()` | Miner |
| 3 | `kick_member(member)` | Pool creator |
| pub fn | `distribute_pool_rewards(pool_id, amount)` | XelisVaultMiner (only) |
| entry | `claim_pool_rewards()` | Pool member |
| pub fn | `get_pool(pool_id)` | dashboard |
| pub fn | `get_pool_members(pool_id) -> u64` | dashboard |
| pub fn | `get_pool_reputation(pool_id) -> u64` | dashboard (approximate; frontend computes the true mean) |
| pub fn | `get_user_pool(addr) -> u64` | dashboard |
| pub fn | `get_pools_count() -> u64` | dashboard |
| pub fn | `get_pool_pending_rewards(pool_id) -> u64` | dashboard |
| pub fn | `is_pool_member(pool_id, addr) -> bool` | scripts |
| entry | `set_miner_contract(mc)`, `set_vlt_asset(va)`, `set_registry(reg)`, `set_timelock(tl)` | Admin (Timelock) |
| entry | `pause(reason)`, `unpause()`, `transfer_admin(new_admin)` | Admin |

### VaultChat.slx — Entry IDs *(new in v4.3)*
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `register_session(chat_pubkey)` | User (one-time) |
| 1 | `create_group(group_pubkey)` | Group creator |
| 2 | `add_group_member(group_id, member, encrypted_group_key)` | Group creator |
| 3 | `remove_group_member(group_id, member)` | Group creator |
| 4 | `anchor_messages(merkle_root, message_count, msg_type)` | Authorized relayer (miner) |
| 5 | `revoke_session(user)` | Admin / Guardian (moderation) |
| pub fn | `get_session(user) -> (Hash, u64, bool)` | frontend, scripts |
| pub fn | `get_group(group_id) -> (Hash, Address, u64, bool)` | frontend |
| pub fn | `get_group_member_key(group_id, member) -> bytes` | frontend |
| pub fn | `is_session_active(user) -> bool` | frontend, relayers |
| pub fn | `get_last_anchor() -> (Hash, u64, u64)` | dashboard |
| pub fn | `get_groups_count() -> u64` | dashboard |
| pub fn | `get_group_members_count(group_id) -> u64` | dashboard |
| entry | `set_relayer(addr, enabled)` | Admin |
| entry | `set_timelock(tl)`, `set_guardian(g)`, `pause(reason)`, `unpause()`, `transfer_admin(new_admin)` | Admin / Guardian |

### PrivacyMixer.slx — Entry IDs *(new in v4.3)*
| ID | Entry | Called by |
|----|-------|-----------|
| 0 | `deposit(asset, denomination_id, commitment)` | User |
| 1 | `withdraw(asset, denomination_id, nullifier, recipient, merkle_root, zk_proof)` | User (from a new address) |
| pub fn | `get_merkle_root() -> Hash` | scripts, frontend |
| pub fn | `get_deposit_count() -> u64` | dashboard |
| pub fn | `is_nullifier_used(nullifier) -> bool` | scripts |
| pub fn | `get_denomination_amount(denom_id) -> u64` | frontend |
| pub fn | `get_deposit_count_for_denom(asset, denom_id) -> u64` | dashboard |
| pub fn | `get_merkle_leaf(level, index) -> Hash` | scripts (for proof construction) |
| entry | `set_zk_verifier(zv)`, `set_registry(reg)`, `set_timelock(tl)`, `set_guardian(g)`, `pause(reason)`, `unpause()`, `transfer_admin(new_admin)` | Admin / Guardian |
| entry | `emergency_withdraw(asset)` | Admin (catastrophic recovery) |

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

### StakedOracle → XelisVaultMiner (distribute reward) *(new in v4.3)*

After aggregation, StakedOracle no longer mints VLT directly. Instead it delegates to XelisVaultMiner, which applies the reputation multiplier and budget factor before minting:

```silex
// For each valid provider in the cycle:
// XelisVaultMiner.distribute_reward(miner_addr, service_id=1, is_valid=true) -> u64
let reward: u64 = miner.call(0u16, [provider_addr, 1u8, true], {})
// XelisVaultMiner checks:
//   - is the miner active?
//   - is the miner's reputation above REP_CRITICAL?
//   - is there budget remaining?
//   - applies multiplier and budget factor
//   - mints the dynamic reward to the miner (or to their pool if they're in one)
```

### VaultChat → XelisVaultMiner (chat anchor reward) *(new in v4.3)*

When a miner-relayer successfully calls `anchor_messages()`, VaultChat calls back into XelisVaultMiner to pay the chat reward:

```silex
// XelisVaultMiner.distribute_reward(miner_addr, service_id=2, is_valid=true) -> u64
let reward: u64 = miner.call(0u16, [relayer_addr, 2u8, true], {})
```

If the relayer is later detected to have lost stored messages or censored messages, VaultChat calls:

```silex
// XelisVaultMiner.slash_miner(miner_addr, severity, reporter) -> u64
// severity: 2 = data_loss (5% slash, -500 rep)
// severity: 3 = censorship (10% slash, -1000 rep)
let slash: u64 = miner.call(0u16, [bad_relayer, 3u8, reporter_addr], {})
```

### XelisVaultMiner → MinerPool (pool reward distribution) *(new in v4.3)*

If `distribute_reward` finds that the miner is in a pool, the reward is forwarded to the pool instead of being minted directly:

```silex
// Look up the miner's pool
let pool_id: u64 = miner_pool.call(0u16, [miner_addr], {})  // get_user_pool
if pool_id > 0 {
    // Forward the reward to the pool
    let _ = miner_pool.call(0u16, [pool_id, reward], {})   // distribute_pool_rewards
    // Pool accumulates it; members claim later via claim_pool_rewards()
} else {
    // Mint directly to the miner
    let _ = vlt.call(0u16, [miner_addr, reward], {})       // VLTToken.mint_to
}
```

### MinerPool → XelisVaultMiner (read miner stake/reputation) *(new in v4.3)*

MinerPool needs to know each member's current stake and reputation to compute pool totals. It reads these from XelisVaultMiner's public functions:

```silex
// XelisVaultMiner.get_miner_stake(addr) -> u64
let stake: u64 = miner.call(0u16, [member_addr], {})

// XelisVaultMiner.get_miner_reputation(addr) -> u64
let rep: u64 = miner.call(0u16, [member_addr], {})
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

### XelisVaultMiner Storage Keys *(new in v4.3)*
- `"a"`, `"tl"`, `"gd"`, `"ea"`, `"pz"`, `"reg"` — Standard admin/guardian/pause
- `"vc"`, `"va"`, `"tr"` — VLT contract, VLT asset, treasury
- `"ms"` — MIN_STAKE (100 VLT)
- `"hi"`, `"ht"` — Heartbeat interval / timeout
- `"tb"` — TOTAL_BUDGET (6M VLT)
- `"dist"` — Distributed so far (cumulative)
- `"lt"` — Launch topoheight
- `"td"` — Target duration in blocks (10 years)
- `"bf"` — Budget factor (bps, 10000 = 1.0×)
- `"lba"`, `"bai"` — Last budget adjustment / interval
- `"bro"`, `"brc"` — Base reward oracle / chat
- `"svc_<hash>"` — Service authorization (service_id)
- `"mc"` — Miners count
- `"miner_<addr>"` — Miner struct
- `"ml_<idx>"` — Miner address list (for iteration)
- `"sm_<svc_id>"` — Active miners per service
- `"ts"` — Total staked across all miners

### MinerPool Storage Keys *(new in v4.3)*
- `"a"`, `"tl"`, `"pz"`, `"reg"` — Standard admin/pause
- `"mc"` — XelisVaultMiner contract hash
- `"va"` — VLT asset hash
- `"pc"` — Pools count
- `"pool_<id>"` — Pool struct
- `"pm_<pool>_<addr>"` — Member flag (bool)
- `"pmc_<pool>"` — Members count
- `"up_<addr>"` — User → pool_id mapping (0 = no pool)
- `"pr_<pool>"` — Pending rewards

### VaultChat Storage Keys *(new in v4.3)*
- `"a"`, `"tl"`, `"gd"`, `"pz"` — Standard admin/guardian/pause
- `"session_<addr>"` — Session struct (pubkey, registered_at, active)
- `"group_<id>"` — Group struct
- `"gm_<group_id>_<addr>"` — Encrypted group key for a member
- `"gmc_<group_id>"` — Group members count
- `"lmr"`, `"lat"`, `"tm"` — Last Merkle root / last anchor topo / total messages
- `"relayer_<addr>"` — Relayer authorization flag
- `"gc"` — Groups count

### PrivacyMixer Storage Keys *(new in v4.3)*
- `"a"`, `"tl"`, `"gd"`, `"pz"`, `"reg"` — Standard admin/guardian/pause
- `"mr"` — Current Merkle root
- `"leaf_<level>_<idx>"` — Merkle tree node (level 0 = leaves)
- `"lc"` — Leaf count (= total deposits)
- `"null_<nullifier>"` — Nullifier spent flag (bool)
- `"dd_<asset>_<denom>"` — Deposit count per asset × denomination
- `"zv"` — ZK verifier contract hash

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
Provider/miner stake: 100 VLT
Slash amount: 1% × 100 = 1 VLT (severity 0 = outlier)

1 VLT split:
├── 0.5 VLT burned (VLTToken.burn)
├── 0.1 VLT to reporter (if any)
└── 0.4 VLT to treasury (transfer)

Provider stake after: 99 VLT
Provider reputation: -50 (from 10,000 → 9,950)
Provider status: still active (reputation >> 1,000, stake >> MIN_STAKE)
```

A miner is auto-deactivated when **either** of these conditions becomes true:
- Stake falls below MIN_STAKE (100 VLT) — happens after ~100 outliers if they never top up
- Reputation falls below REP_CRITICAL (1,000) — happens after ~180 outliers

To re-activate, the miner must call `increase_stake()` (if stake is low) and/or send heartbeats to regenerate reputation (each heartbeat = +1 rep, if no infraction in the last 1,000 blocks).

The 5-tier severity scale (used by StakedOracle and VaultChat when calling `slash_miner`):

| Severity | Infraction | Stake slash | Reputation loss |
|----------|------------|-------------|------------------|
| 0 | Oracle outlier | 1% | -50 |
| 1 | Node offline | 2% | -200 |
| 2 | Chat data loss | 5% | -500 |
| 3 | Chat censorship | 10% | -1,000 |
| 4 | Malicious behavior | 50% | -5,000 |

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

### Multi-asset Collateral (v5.0)
Extend VaultEngine to accept any XELIS Confidential Asset as collateral, not just XEL. Each asset would need its own price feed in StakedOracle.

### Cross-chain Bridges (v6.0)
Bridge xUSD to other chains (Ethereum, Solana) via atomic swaps or wrapped tokens. VLT remains XELIS-native.

### ZK Compliance Layer (v5.0)
Allow providers to prove KYC/AML compliance without revealing identity. Required for institutional adoption.

### Additional Miner Services (v5.x)
Extend `XelisVaultMiner` with new service IDs beyond Oracle (1) and Chat (2):
- Service 3: Storage — miners store encrypted blobs (off-chain) and anchor roots on-chain
- Service 4: Indexer — miners index events for fast frontend queries
- Service 5–8: Reserved for community-proposed services

Each new service will follow the same pattern: registered as an authorized service contract via `XelisVaultMiner.register_service()`, then call `distribute_reward()` for valid contributions and `slash_miner()` for misbehavior. The reputation system and budget control loop already accommodate new services without configuration changes.

---

## References

- [Silex Language Documentation](https://docs.xelis.io/features/smart-contracts/silex)
- [XELIS Virtual Machine](https://github.com/xelis-project/xelis-vm)
- [XELIS-Forge Smart Contracts](https://github.com/XELIS-Forge/smart-contracts)
- [Twisted ElGamal on Ristretto255](https://github.com/xelis-project/xelis-he)

---

*Last updated: June 2026 — v4.3*
