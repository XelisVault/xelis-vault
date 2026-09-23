# RUNBOOK 3 — Mainnet contract interactions (XELIS mainnet LIVE)

> Network: **official XELIS mainnet** (explorer `https://explorer.xelis.io`),
> height ~7 793 000, block version **V7**, Smart Contracts active since
> height 3 282 150. Deployment **executed and verified on-chain on 23/09/2026**.
>
> This file lists **every command** to interact with `VaultLaunch` (the
> launchpad) and `LaunchDEX` (the DEX) on mainnet: the contract addresses,
> the deployment/config record (real TX hashes), the full creator flow
> (propose → vote → buy/sell → migrate), DEX swaps, and all data reads.
>
> ⚠️ On mainnet this wallet (**admin = user**) is the only signer. There are
> no "test" transactions: every command is real and final.

---

## 0. Material (mainnet — current state)

| Item | Value |
|---|---|
| Network explorer | `https://explorer.xelis.io` |
| Target block time | 5 s (measured average ~5.15 s) |
| Validation window (vdt) | **720 topos ≈ 1 h** |
| Wallet (admin = user) RPC | `http://127.0.0.1:8083/json_rpc` — `dev`/`dev` (local port) |
| Daemon (TLS relay, broken DNS) | `http://127.0.0.1:8085/json_rpc` → `fr-node.xelis.io:443` |
| **Wallet address** | `xel:sel92pcaegt0kenv3q35ycnzpd4xfl0md93usnkxq0rsjtha6cjsqe2xwch` |
| **VaultLaunch (Vault)** | `45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54` |
| **LaunchDEX (DEX)** | `bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d` |
| XEL asset | `0000000000000000000000000000000000000000000000000000000000000000` |

Helper: `python3 scripts/xrpc.py`, pointed at mainnet via environment
variables:

```bash
export XELIS_WALLET_URL=http://127.0.0.1:8083/json_rpc
export XELIS_WALLET_USER=dev
export XELIS_WALLET_PASS=dev
export XELIS_DAEMON_URL=http://127.0.0.1:8085/json_rpc
```

XELIS typed-parameter format (same as testnet):
- `u64(v)`      → `{"type":"primitive","value":{"type":"u64","value":"v"}}`
- `string(v)`   → `{"type":"primitive","value":{"type":"string","value":v}}`
- `hash(h)`     → `{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":h}}}`
- `address(a)`  → `{"type":"primitive","value":{"type":"opaque","value":{"type":"Address","value":a}}}`
- `bool(b)`     → `{"type":"primitive","value":{"type":"boolean","value":b}}`

Deposit attached to an invoke:
`--deposits '{"<asset_hex>": <atomic_amount>}'` (100000000 atomic = 1 XEL).

> ⚠️ System DNS is broken on this machine (getaddrinfo fails): the daemon RPC
> goes through the local relay `xelis_rpc_relay.py` (port 8085, persistent
> TLS to `fr-node.xelis.io`, bypasses Cloudflare rate-limits). Without it, or
> on a healthy host, point `XELIS_DAEMON_URL` at any reachable mainnet node.

---

## 1. Mainnet deployment & configuration (DONE — real hashes)

Sequence executed and **confirmed on-chain** (each TX verified with
`wait-tx` before the next one; every invoke then read back from storage).

| Step | Action | TX hash (full) | topo |
|---|---|---|---|
| D1 | Deploy **LaunchDEX** (= DEX address) | `bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d` | 9041909 |
| D2 | Deploy **VaultLaunch** (= Vault address) | `45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54` | 9041917 |
| E1 | Vault **50** `set_dex_address(hash DEX)` | `70c8c747ffd7bbb752305bc3f598bc2b63bd2a61a4026addc5fe8b987ac1d697` | 9041922 |
| E2 | DEX **13** `set_launchpad(address wallet)` | `414a41d259b3379867981c8af7033ce3448ad66f5ea04ac346e5320d05414502` | 9041927 |
| E3.1 | Vault **34** `set_submission_fee(2_500_000_000)` | `e0d7a5ca5ba85b805d90bf21b6d657685b801035973cd944b426872fb8defaeb` | 9041930 |
| E3.2 | Vault **48** `set_asset_budget(100_000_000)` | `a7a5b1fba1dc7f4515359fa3eb5cd4931e9d98ee47331a28ac4be3f8c9d302a9` | 9041934 |
| E3.3 | Vault **40** `set_min_participants(1)` | `c82c341666a8694e310efb135d9f0b0e5de9a4e846d1b2edf30ed35364824c8e` | 9041942 |
| E3.4 | Vault **42** `set_validation_duration(720)` | `24bed17315f049c58a88903671f2d24309738a5270aa2d4bf186a071164adac7` | 9041944 |
| E3.5 | Vault **43** `set_graduation_multiplier(2)` | `263c86cbb0f3480332358e8b7c089568266325b2aeb2b75fdce8239040b2ded1` | 9041949 |
| E3.6 | Vault **49** `set_vote_deposit(0)` | `47151310e39a6f4aa7f66ccbe8f2f7a10c023c670d9fb85c282747f2a304ff93` | 9041953 |
| E4 | DEX **29** `set_fee_split(5000)` (50 % LP) | `254e3cc01273fc24c94cb08b662ade73510d171d25c8c2a93785c5cadee7a540` | 9041983 |

Measured fees: VaultLaunch 225 000 atomic, LaunchDEX 125 000 atomic
(dry-run before broadcast). Total cost of the operation < 0.01 XEL.

---

## 2. On-chain parameters (verified by storage reads, 23/09/2026)

### VaultLaunch — `45baf014…`

| Key | On-chain value | Meaning |
|---|---|---|
| `sub` | `2500000000` (25 XEL) | submission fee |
| `abd` | `100000000` (1 XEL) | asset budget guarantee |
| `mnl` | `50000000000` (500 XEL) | minimum seed liquidity (default) |
| `mnp` | `1` | minimum participants to pass validation |
| `mab` | `8000` (80 %) | approval ratio (default) |
| `vdt` | `720` topos | validation duration (~1 h) |
| `gmu` | `2` | graduation multiplier (×2) |
| `vdp` | `0` | no vote deposit required |
| `tfe` / `gfe` / `mgf` | `50` / `25` / `50` | bonding / graduated / migration fees (defaults) |
| `dlt` | `200000000000` (2000 XEL) | direct-listing threshold (default) |
| `dxa` | DEX hash | **pin**: only DEX `bce37bde…` can receive `migrate` |
| `pc` | 0 | project counter |

> Graduation: a small-float project is listed when
> `reserves ≥ liquidity × gmu` (×2). With a 500 XEL seed → graduation at
> **1 000 XEL** of reserves (never 2 000). With `liquidity ≥ dlt`
> (2 000 XEL deposited at propose) → **direct listing** right after
> validation, no bonding phase.

### LaunchDEX — `bce37bde…`

| Key | On-chain value | Meaning |
|---|---|---|
| `sfe` | `30` (0.30 %) | swap fee (default) |
| `fsl` | `5000` (50 %) | LP share of the fee (`set_fee_split`) |
| `lpx` | `xel:sel92…` | **pin**: only this wallet can `create_pool` |
| `pc` | 0 | pool counter |

---

## 3. VaultLaunch — creator flow (entry IDs, mainnet)

Vault = `45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54`
(command prefix: `python3 scripts/xrpc.py invoke <VAULT> <id> '<params>'`)

### 3.1 propose (id 20) — create a project

Parameters: `name, symbol, description, website, logo, twitter, telegram,
discord, total_supply, team_bps, vesting_duration`.

> Required XEL deposit at propose (mainnet):
> `sub (2.5e9) + abd (1e8) + mnl (5e10)` = **52 600 000 000 atomic = 526 XEL**
> minimum. Anything above becomes extra liquidity on the curve
> (liquidity = deposit − sub − budget).

```bash
python3 scripts/xrpc.py invoke 45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54 20 \
  '[{"type":"primitive","value":{"type":"string","value":"MyCoin"}},
    {"type":"primitive","value":{"type":"string","value":"MYC"}},
    {"type":"primitive","value":{"type":"string","value":"First community coin"}},
    {"type":"primitive","value":{"type":"string","value":"https://mycoin.io"}},
    {"type":"primitive","value":{"type":"string","value":"https://mycoin.io/logo.png"}},
    {"type":"primitive","value":{"type":"string","value":"https://x.com/mycoin"}},
    {"type":"primitive","value":{"type":"string","value":"https://t.me/mycoin"}},
    {"type":"primitive","value":{"type":"string","value":"https://discord.gg/mycoin"}},
    {"type":"primitive","value":{"type":"u64","value":"1000000000"}},
    {"type":"primitive","value":{"type":"u64","value":"500"}},
    {"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits '{"0000000000000000000000000000000000000000000000000000000000000000":52600000000}'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```

Returns the `pid` (project index, e.g. 0). Example values: total_supply 1e9,
team_bps 500 = 5 % team allocation, vesting_duration 0 = team allocation
claimable immediately at graduation (otherwise a duration between `vmn` and
`vmx`, or `badplan`). Out-of-bounds supply raises `badsupply`.

### 3.2 support (id 21) — vote for a project

`vdp = 0` → **no deposit required** to vote.

```bash
python3 scripts/xrpc.py invoke <VAULT> 21 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```

Validation passes once `participants ≥ mnp (1)` and
`approval ≥ mab (80 %)` after `vdt` = 720 topos.

### 3.3 finalize_validation (id 23)

After the window (`vdt` elapsed, participants reached):

```bash
python3 scripts/xrpc.py invoke <VAULT> 23 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```

→ project enters **bonding** (st=2), the asset is minted (budget `abd`
covers the asset fee). If `liquidity ≥ dlt` → **direct listing** (no bonding
phase).

### 3.4 buy (id 24) — buy on the curve

Minimum XEL deposit `MIN_BUY_XEL` = 1 000 000 atomic (0.01 XEL):

```bash
python3 scripts/xrpc.py invoke <VAULT> 24 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits '{"0000000000000000000000000000000000000000000000000000000000000000":1000000000}'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```

Buy until `reserves ≥ liquidity × gmu` (×2) → the project **graduates**
(st=3); selling on the curve stays open.

### 3.5 sell (id 25) — sell tokens

Deposit tokens (e.g. 100 000 000) → sells on the curve:
```bash
python3 scripts/xrpc.py invoke <VAULT> 25 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits '{"<ASSET_HEX>":100000000}'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```
Rejected if the project is already migrated to the DEX (`migrated`).

### 3.6 migrate (id 32) — graduate to the DEX (creator)

```bash
python3 scripts/xrpc.py invoke <VAULT> 32 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'
python3 scripts/xrpc.py wait-tx <TX_HASH>
```
Cross-calls `LaunchDEX.create_pool` — accepted because `dxa` is pinned to
`bce37bde…`. After migration, all trading continues on the DEX pool.

### 3.7 Other user entries

| ID | Function | Params | Notes |
|---|---|---|---|
| 26 | `claim_refund` | `u64(pid)` | refund of deposits if the project was rejected |
| 27 | `claim_vote_deposit` | `u64(pid), u64(round)` | reclaims the locked vote deposit (none here, vdp=0) |
| 28 | `request_revalidation` | `u64(pid)` | rejected if already graduated |
| 29 | `update_project_info` | `u64(pid)` + 6 strings | creator only |
| 30 | `start_team_vesting` | `u64(pid), u64(duration)` | creator only |
| 31 | `claim_team_allocation` | `u64(pid)` | creator only |
| 33 | `sync_trust_to_dex` | `u64(pid)` | sync the trust flag to the DEX |

---

## 4. VaultLaunch — admin setters (id 34 → 53)

Vault = `45baf014…`. **Do not replay** (config done) — touch only for a
deliberate change.

| ID | Function | Storage |
|---|---|---|
| 34 | `set_submission_fee(u64)` | `sub` |
| 35 | `set_trading_fee(u64 bps)` | `tfe` |
| 36 | `set_graduated_trading_fee(u64 bps)` | `gfe` |
| 37 | `set_migration_fee(u64 bps)` | `mgf` |
| 38 | `set_direct_listing_threshold(u64)` | `dlt` |
| 39 | `set_min_liquidity(u64)` | `mnl` |
| 40 | `set_min_participants(u64)` | `mnp` |
| 41 | `set_min_approval_ratio(u64 bps)` | `mab` |
| 42 | `set_validation_duration(u64 topos)` | `vdt` |
| 43 | `set_graduation_multiplier(u64)` | `gmu` |
| 44 | `set_team_unlock_delay(u64 topos)` | `tdy` |
| 45 | `set_vesting_bounds(u64, u64)` | `vmn`, `vmx` |
| 46 | `set_recovery_fee(u64)` | `rfe` |
| 47 | `set_recovery_params(u64, u64)` | `rmp`, `rmr` |
| 48 | `set_asset_budget(u64)` | `abd` |
| 49 | `set_vote_deposit(u64)` | `vdp` |
| 50 | `set_dex_address(hash(addr))` | `dxa` |
| 51 | `set_admin(address)` | — |
| 52 | `set_paused(bool)` | `pz` (blocks buy/support…) |
| 53 | `withdraw_fees(u64)` | empties `pfe` |

Example (read → set → verify → restore, see testnet RUNBOOK1):
```bash
python3 scripts/xrpc.py invoke 45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54 34 '[{"type":"primitive","value":{"type":"u64","value":"2000000000"}}]'
python3 scripts/xrpc.py state 45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54 sub
```

---

## 5. LaunchDEX — swaps, liquidity, fees (entry IDs)

DEX = `bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d`

| ID | Function | Params | Notes |
|---|---|---|---|
| **8** | `swap_xel_for_token` | `hash(asset), u64(min_tokens_out)` | deposit XEL; fee split LP |
| **9** | `swap_token_for_xel` | `hash(asset), u64(min_xel_out)` | deposit tokens |
| **10** | `add_liquidity` | `hash(asset)` | deposit XEL + tokens (excess refunded) |
| 11 | `set_swap_fee` | `u64(bps)` | `sfe` |
| 12 | `set_trade_bounds` | 6 u64 | `mnx,lnt,mnt,tsw,mst,mxs` |
| 13 | `set_launchpad` | `address(addr)` | only this wallet can `create_pool` |
| 14 | `set_admin` | `address(new_admin)` | — |
| 15 | `set_paused` | `bool(flag)` | `xpa` |
| 16 | `withdraw_fees` | `hash, u64, u64` | pools `xf`/`yf` |
| **29** | `set_fee_split` | `u64(lp_bps)` | 2500 ≤ lp ≤ 7500; `fsl` |
| **30** | `claim_lp_fees` | `hash(asset)` | crystallized LP share |

Trading examples (after a `migrate`, a pool exists for `<ASSET>`):

```bash
# Buy tokens on the DEX (XEL deposit, min_tokens_out = 1)
python3 scripts/xrpc.py invoke bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d 8 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET_HEX>"}}},{"type":"primitive","value":{"type":"u64","value":"1"}}]' \
  --deposits '{"0000000000000000000000000000000000000000000000000000000000000000":10000000}'

# Sell tokens for XEL (min_xel_out = 1)
python3 scripts/xrpc.py invoke bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d 9 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET_HEX>"}}},{"type":"primitive","value":{"type":"u64","value":"1"}}]' \
  --deposits '{"<ASSET_HEX>":10000000}'

# Add liquidity (XEL + tokens deposit; skip if the pool already exists)
python3 scripts/xrpc.py invoke bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d 10 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET_HEX>"}}}]' \
  --deposits '{"0000000000000000000000000000000000000000000000000000000000000000":100000000,"<ASSET_HEX>":100000000}'

# Claim your LP fees on the pool
python3 scripts/xrpc.py invoke bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d 30 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET_HEX>"}}}]'
```

---

## 6. Data reads (on-chain state)

### 6.1 Via `xrpc.py state` (contract storage)

```bash
python3 scripts/xrpc.py state 45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54 sub
python3 scripts/xrpc.py state 45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54 dxa
python3 scripts/xrpc.py state bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d lpx
python3 scripts/xrpc.py state bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d sfe
```

Project keys (Vault, project pid `p`): `p:<pid>:nm` (name), `p:<pid>:sy`
(symbol), `p:<pid>:st` (status: 0 validation, 1 vote, 2 bonding, 3 graduated),
`p:<pid>:li` (seed liquidity), `p:<pid>:rs` (reserves), `p:<pid>:cv` (curve
supply), `p:<pid>:mi` (migrated?), `p:<pid>:dl` (direct listing?).

Pool keys (DEX, asset `a`): `q:<asset>:xr` (XEL reserve), `q:<asset>:yr`
(token reserve), `q:<asset>:ls` (LP liquidity), `q:<asset>:xf` / `q:<asset>:lx`
(fee pots).

### 6.2 Raw JSON-RPC (`get_contract_data`) — verification without helper

```bash
curl -s http://127.0.0.1:8085/json_rpc -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"get_contract_data",
  "params":{"contract":"45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54",
            "key":{"type":"primitive","value":{"type":"string","value":"gmu"}}}}'
```

### 6.3 Wallet balance & address

```bash
python3 scripts/xrpc.py balance
python3 scripts/xrpc.py address
```

---

## 7. Cross-checking against the explorer

Every TX and every contract can be verified on `https://explorer.xelis.io`
(transaction / contract tab):

- LaunchDEX deployment: `bce37bde7ac8e0410656d5b67c398b172cbb6047f6b390041c9dbb3dbdeae11d`
- VaultLaunch deployment: `45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54`
- DEX pin → Vault: `dxa` = `bce37bde…`; launchpad pin → DEX: `lpx` =
  `xel:sel92…` (verified: `dxa` at topo 9041922, `lpx` at topo 9041927).

SHA-256/checksums of the deployed modules (cross-check with the ABI/SDK):
`out/VaultLaunch.hex` `b6e9cb47…`; `out/LaunchDEX.hex` `34067589…`.

---

## 8. Real chronological summary (MAINNET, 23/09/2026)

1. Mainnet wallet imported from the seed (`xel:sel92…`), balance 156.30 XEL,
   network confirmed (`get_info.network = mainnet`, V7).
2. Module build: checksums identical to the testnet-validated version.
3. Dry-runs `broadcast=False`: fees 225 000 / 125 000 atomic.
4. Deploys D1/D2 + config E1→E4 in sequence, **each TX confirmed in a real
   block before the next one** (topos 9 041 909 → 9 041 983).
5. Final storage verification: **16/16 keys read** (0.4 s via the persistent
   relay) — every parameter in §2 table confirmed on-chain.
6. Total cost < 0.01 XEL; unspent balance intact (~156.3 XEL).