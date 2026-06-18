# Upgrade Pattern — XELIS Vault v4.2

> How contract upgrades work in XELIS Vault (Versioned Registry pattern).

---

## Why Not Use Standard Proxy Pattern?

Solidity's EIP-1967 proxy pattern relies on `delegatecall`, which allows a proxy contract to execute code from another contract while keeping its own storage. **Silex/XELIS does not support `delegatecall`** (as of June 2026), so this pattern cannot be used directly.

Instead, we use a **Versioned Registry** pattern that provides similar upgradeability with simpler auditability.

---

## How It Works

### ContractRegistry

A single contract (`ContractRegistry.slx`) stores the current address of every protocol contract by logical name:

```
ContractRegistry storage:
  "VLTToken"      → 0xabc123... (v4.2)
  "StakedOracle"  → 0xdef456... (v4.2)
  "VaultEngine"   → 0x789abc... (v3)
  "VaultSwap"     → 0x111222... (v2)
```

### Runtime Resolution

Contracts don't store the addresses of their dependencies directly. Instead, they resolve them at runtime:

```silex
fn get_oracle() -> Contract {
    let s: Storage = Storage::new()
    let reg_hash: Hash = s.load(REGISTRY_KEY).expect("regnoset")
    let reg: Contract = Contract::new(reg_hash).expect("regnf")
    let oracle_hash: Hash = reg.call(0u16, ["StakedOracle"], {})
    return Contract::new(oracle_hash).expect("oraclenf")
}
```

### Upgrade Procedure

To upgrade `StakedOracle` from v4.2 to v4.3:

1. **Deploy v4.3** (new contract hash, e.g., `0xnew789...`)
2. **Verify v4.3** compiles, passes tests, and is audited
3. **Submit Timelock proposal**: `ContractRegistry.upgrade("StakedOracle", 0xnew789...)`
4. **Wait 48 hours** (Timelock delay)
5. **Execute the proposal** — registry now points to v4.3
6. **Call `migrate_from(old_hash)`** on v4.3 to copy state from v4.2
7. **Verify migration**:
   ```bash
   # On v4.2 (old):
   xelis_wallet call-contract read <v4.2_hash> get_providers_count
   # On v4.3 (new):
   xelis_wallet call-contract read <v4.3_hash> get_providers_count
   # Should be equal
   ```
8. **Update frontend** to use registry (no SDK change needed if already using registry)

### Rollback

If a bug is discovered in v4.3 after migration:

```bash
# Submit Timelock proposal: ContractRegistry.rollback("StakedOracle")
# Wait 48h (or 2h in emergency mode)
# Execute — registry now points back to v4.2
```

State created between migration and rollback stays in v4.3 but doesn't affect v4.2 operation. Manual reconciliation may be needed if absolutely necessary.

---

## Migration Function Pattern

Each upgradeable contract should expose a `migrate_from(prev_hash: Hash)` entry:

```silex
entry migrate_from(prev_hash: Hash) -> u64 {
    only_admin()
    let s: Storage = Storage::new()
    let migrated: bool = s.load(MIGRATED_KEY).unwrap_or(false)
    require(!migrated, "alreadymigrated")

    let prev: Contract = Contract::new(prev_hash).expect("vnf")

    // Read state from previous version
    let total: u64 = prev.call(0u16, [], {}).expect("totalcount")

    // For each item, read from old, write to new
    let i: u64 = 1
    while i <= total {
        let item: SomeStruct = prev.call(1u16, [i], {}).expect("itemnf")
        // ... transform if needed ...
        s.store("item_" + i.to_string(10u32), item)
        i += 1
    }

    s.store(MIGRATED_KEY, true)
    return 0
}
```

For large states, use **paginated migration**:

```silex
entry migrate_from_batch(prev_hash: Hash, start: u64, end: u64) -> u64 {
    only_admin()
    // Same as migrate_from but only for items [start, end]
    // Useful when state is too large to migrate in one transaction
}
```

---

## Safeguards

### Cooldown Between Upgrades

The registry enforces a cooldown of **720 blocks (~1 hour)** between upgrades of the same contract. This prevents upgrade-spam attacks.

```silex
// In ContractRegistry.upgrade():
let last_topo: u64 = s.load(UPGRADE_TOPO_PREFIX + name).unwrap_or(0)
let now_topo: u64 = get_current_topoheight()
if now_topo > last_topo {
    require(now_topo - last_topo >= COOLDOWN_BLOCKS, "cooldown")
}
```

### Versioning

Each contract exposes `get_version() -> string`:

```silex
entry get_version() -> string {
    return VERSION  // "StakedOracle v4.2"
}
```

The registry also tracks version numbers:

```
ContractRegistry storage:
  "VLTToken"     → 0xabc123..., version 1
  "StakedOracle" → 0xdef456..., version 2 (was 1, upgraded)
```

### Previous Version Preserved

The registry stores the previous hash for each contract:

```
"prev_VLTToken"     → 0xold123...
"prev_StakedOracle" → 0xold456...
```

This enables instant rollback without re-deploying.

---

## Upgrade Checklist

Before upgrading any contract:

- [ ] New version compiles without warnings
- [ ] All existing tests pass against new version
- [ ] New tests cover the changes
- [ ] State migration function tested on testnet
- [ ] Diff between old and new code reviewed
- [ ] Security implications assessed
- [ ] Community notified (for major upgrades)
- [ ] Timelock proposal submitted (48h delay)
- [ ] Frontend SDK updated (if interface changed)
- [ ] Monitoring ready for new contract
- [ ] Rollback plan documented

---

## When NOT to Upgrade

Avoid upgrades when:
- The change is cosmetic (rename, comments) — wait for a substantive change
- The contract is paused due to an incident — fix the incident first
- The Timelock has pending proposals — wait for them to complete
- The chain is under attack — focus on mitigation, not upgrades

---

## Emergency Upgrade

For critical security fixes, the Timelock supports an **emergency mode** with reduced delay (2 hours instead of 48). Emergency mode requires:
- Guardian multisig approval (2/3 signers)
- Public disclosure of the vulnerability being fixed
- Post-upgrade audit within 7 days

```silex
// In Timelock contract (paraphrased)
entry submit_emergency_proposal(target, entry, value) -> u64 {
    only_guardian_multisig()
    // ... create proposal with 2h delay instead of 48h ...
}
```

---

## Historical Upgrades

### v4.0 → v4.2 (June 2026)
- **Upgraded**: StakedOracle (MinerOracle → StakedOracle)
- **Reason**: Permissionless design (anyone can be provider, not just miners)
- **Migration**: Manual — MinerOracle state was small (just feeds), no provider migration needed (fresh start)
- **Result**: Successful, no issues

### v3 → v4.0 (May 2026)
- **Upgraded**: PriceOracle → MinerOracle
- **Reason**: Decentralization (miners as sources, not admin bots)
- **Migration**: Manual — PriceOracle had no providers, just price history (not migrated)
- **Result**: Successful

### v2 → v3 (April 2026)
- **Upgraded**: PriceOracleV2 → MinerOracle
- **Reason**: Remove admin control
- **Migration**: Not needed (fresh deployment)
- **Result**: Successful

---

## Future: Automated Upgrades

For v5.0+, we plan to add:
- **Upgrade proposals** via governance (VLT stakers vote)
- **Automatic migration scripts** that paginate large states
- **Diff visualization** tools for community review
- **Testnet canary** — upgrade runs on testnet for 7 days before mainnet

---

## References

- [EIP-1967: Transparent Proxy Pattern](https://eips.ethereum.org/EIPS/eip-1967) — why we can't use this
- [OpenZeppelin Upgrades Plugins](https://docs.openzeppelin.com/upgrades-plugins/) — inspiration for migration patterns
- [Compound Governance Timelock](https://github.com/compound-finance/compound-protocol/tree/master/contracts/Timelock) — inspiration for our Timelock

---

*Last updated: June 2026 — v4.2*
