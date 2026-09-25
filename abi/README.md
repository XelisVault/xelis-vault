# abi/ — transaction-facing entry tables of the active contracts

Compile artifacts (emitted by the xelis toolchain), kept here so the
frontend and tooling can encode invokes without re-deriving the tables.
They are NOT contract source (contracts/ holds only `.slx` — the
structure gate enforces it).

| File | Contract | What it covers |
|---|---|---|
| `VaultLaunch.abi.json` | VaultLaunch v4.2 | the project launchpad (propose → vote → curve → graduation → migration) |
| `LaunchDEX.abi.json` | LaunchDEX v1.4 | the AMM (swaps, liquidity, fees) — `create_pool`/`set_pool_buys_paused`/`create_pool_open` are `pub fn` cross-call chunks, NOT transaction entries, so they are absent here (their chunk ids: 6 / 7 / 33) |
| `CommunityLaunch.abi.json` | CommunityLaunch v1.0 | the permissionless community-coin factory (launch → curve → graduation → open migration) |

The authoritative chunk tables (EVERY function, declaration order) live
in each contract's header comment and in `sdk/xvault/xvault/protocol.py`
(`*_ENTRY_IDS`), CI-verified by `scripts/verify_chunk_ids.py`,
`scripts/regen_sdk_entry_ids.py --check` and `tests/test_*_reference.py`.
