# abi/ — transaction-facing entry tables of the active contracts

Compile artifacts (emitted by `silex-cli abi` from the canonical
[xelis-project/silex-cli](https://github.com/xelis-project/silex-cli)
v1.0.0 build), kept here so the frontend and tooling can encode invokes
without re-deriving the tables. They are NOT contract source (contracts/
holds only `.slx` — the structure gate enforces it).

**Regenerate** (after a contract change): `silex-cli abi
contracts/<path>.slx -o abi/<Name>.abi.json`. The CI `compile` gate
reruns this and fails on any drift, so the committed files are always
the compiler's own output (including type-name casing).

| File | Contract | What it covers |
|---|---|---|
| `VaultLaunch.abi.json` | VaultLaunch v4.2 | the project launchpad (propose → vote → curve → graduation → migration) |
| `LaunchDEX.abi.json` | LaunchDEX v1.4.1 | the AMM (swaps, liquidity, fees, `remove_liquidity`) — `create_pool`/`set_pool_buys_paused`/`create_pool_open` are `pub fn` cross-call chunks, NOT transaction entries, so they are absent here (their chunk ids: 6 / 7 / 33) |
| `CommunityLaunch.abi.json` | CommunityLaunch v1.0.1 | the permissionless community-coin factory (launch → curve → graduation → open migration) |

The authoritative chunk tables (EVERY function, declaration order) live
in each contract's header comment and in `sdk/xvault/xvault/protocol.py`
(`*_ENTRY_IDS`), CI-verified by `scripts/verify_chunk_ids.py`,
`scripts/regen_sdk_entry_ids.py --check` and `tests/test_*_reference.py`.
