# xvault — XELIS Vault CLI & SDK

Python tooling for the XelisVault protocol (v17, VaultLaunch + PrivacyMixer
V5). **Key-less by design**: the CLI prepares transactions and reads state;
your local wallet (`xelis_wallet --rpc-server`, or Genesix via XSWD) signs
and broadcasts.

## Install

```bash
pip install ./sdk/xvault      # or: pip install -e ./sdk/xvault[dev]
```

Requires Python ≥ 3.10. Dependencies: `requests`, `blake3`.

## Launchpad workflow (VaultLaunch v4 — real assets)

The launched tokens are REAL XELIS confidential assets now: buyers hold
them in their own wallets (query the daemon for the asset hash like any
balance — there is no internal ledger). Graduation migrates the curve
into a permanent LaunchDEX pool; trading continues there.

```bash

```bash
# protocol health, parameters, fee pot, solvency
xvault launchpad status --contract <hash> --network mainnet

# one project card (status, curve, price, votes, volume, balances,
# socials, market-cap series, vesting plan)
xvault launchpad project --contract <hash> --id 0 --owner xel:...

# team allocation panel: vesting stream (declared plan or voluntary),
# late-claim countdown, claimable now
xvault launchpad team --contract <hash> --id 0

# offline curve calculator (mirrors the contract math exactly)
xvault launchpad quote --reserves 500 --curve 90000000 --buy 100 --sell 1000000

# prepare / send a proposal (deposit = submission fee + ASSET BUDGET
# + seed liquidity — the budget covers the chain's Asset::create cost,
# unused part refunded at validation success)
# --vesting N declares the team vesting plan the community votes on
# (0 = claim at graduation); socials ride along and are updatable later
xvault launchpad propose --name "Real Project" --symbol RPR --supply 1000000 \
    --team-bps 1000 --liquidity 500 [--vesting 2592000] \
    [--twitter https://x.com/rpr] [--telegram https://t.me/rpr] \
    [--discord https://discord.gg/rpr] --contract <hash> --network mainnet
# add --broadcast to send via the local wallet

# entry-point chunk ids for every invoke
xvault launchpad entries
```

## Migration & the pool era (v4)

```bash
# the atomic, permissionless move: curve reserves + token inventory ->
# a PERMANENT LaunchDEX pool (no remove_liquidity exists — anti-rug)
xvault launchpad migrate --contract <launchpad> --id 0 [--broadcast]
# the transaction MUST carry the contract-call permission (XSWD "all")

# mirror the community trust to the pool: Untrusted -> pool buys paused
# (sells NEVER blocked, on either venue)
xvault launchpad sync   --contract <launchpad> --id 0 [--broadcast]

# the pool era: reserves, price, volume scoreboard, permanent liquidity
xvault dex status       --contract <dex>
xvault dex pool         --contract <dex> --asset <asset-hash-64hex>
xvault dex quote        --x-reserve 2000 --y-reserve 900000000 --buy 100
xvault dex entries      # chunk ids (6/7 are the pinned cross-calls)

# the provider era (v1.2, X10): liquidity EARNS its pro-rata fee share
xvault dex lp            --contract <dex> --asset <hash> --wallet <addr>
                                                        # parts + live earnings
xvault dex claim-lp-fees --contract <dex> --asset <hash> [--broadcast]
                                                        # pull YOUR fees (both sides)
xvault dex set-fee-split --contract <dex> --percent 50 [--broadcast]
                                                        # admin: the split dial (25-75)
```

Python: `from xvault import dex` — the math mirror (`xel_to_tokens_out`,
`tokens_to_xel_out`, `spot_price`, `liquidity_fit`, `fee_split`,
`lp_earnings`, `accrual_increment`), the `DexReader` (pools, quotes,
scoreboard, `lp_info` — the provider position) and the invoke builders
(`swap_xel_params`, `swap_token_params`, `add_liquidity_deposits`,
`claim_lp_fees_params`, `set_fee_split_params`...). The launchpad module
gained `sell_deposits` (whole-deposit token sales), `set_dex_address_params`,
`finalize_topup_deposits`, `dex_pool_market_cap` (the pool-era cap
composition) and the migration fields in `LaunchpadReader.project()`.

Other entries (support/report/finalize/buy/sell/claim_refund/
request_revalidation/start_team_vesting/claim_team_allocation + admin
setters) follow the same wallet flow: build
params with `xvault.launchpad`, invoke with the chunk ids from
`xvault launchpad entries`. The SDK's id table is CI-checked against the
contract's declaration order on every push.

## Mixer workflow (V5 — on hold for mainnet)

### 1. Deposit

```bash
xvault mixer deposit \
    --amount 100 \                # exactly 10, 100 or 1000 XEL
    --recipient xel:FRESH_ADDR \  # where the payout will land (never sent on-chain)
    --contract <mixer_hash> \
    --network mainnet \
    --note-out note-001.json \
    --broadcast                   # optional: send via local wallet RPC
    # --delay 51840               # optional: explicit delay (topoheights),
                                  # default: uniform random ~1h..~3d
```

Generates a 256-bit secret on your machine, computes the commitment
**client-side** (the secret and the recipient NEVER appear on-chain), draws
a random delay inside the dead-drop window (~1h..~3d) and saves a **bearer
note** JSON (`chmod 600`). The note is the only proof of your deposit —
losing it means losing the funds. Back it up encrypted.

The deposit invoke carries ONLY `[Hash(commitment), u64(delay)]` — no
address, no secret, nothing linkable.

### 2. Check

```bash
xvault mixer status --contract <hash> --network mainnet
xvault mixer note-info --note note-001.json --contract <hash> --network mainnet
```

`status` shows pool solvency (`balance ≥ pending`), fees, bounty, note
counts and state flags. `note-info` shows your note's leaf, spent status
and unlock countdown (releasable now / locked for ~Xh).

### 3. Nothing else to do (dead-drop)

After the unlock topoheight (deposit + your random delay), **anyone** can
release the note — a community release bot earning the bounty, a friend,
or you from any funded wallet. The payout ALWAYS lands on the committed
recipient: front-running a release is harmless (the copy only pays the
gas), and the recipient never needs gas or signs anything.

### 4. Release (optional — manual / bot)

```bash
xvault mixer release \
    --note note-001.json \
    --contract <hash> \
    --network mainnet \
    --broadcast

# batch (bots, all-or-nothing, up to 16 notes):
xvault mixer release-many --notes-dir notes/ --contract <hash> --network mainnet --broadcast
```

The CLI reads the 20 Merkle siblings from live contract storage, verifies
the proof **locally** against the current root, re-computes the commitment
to make sure it matches the stored leaf, checks that the unlock topoheight
has passed, then prepares the invoke. Any funded wallet can broadcast it —
the funds go to the committed recipient, the releaser only receives the
capped bounty (0.05 XEL by default).

### One-time setup on a new deployment

```bash
xvault mixer probe --contract <hash> --network testnet
```

XELIS entry ids have been observed under two numbering conventions (see
docs/SECURITY.md §3). `probe` builds a harmless `raise_alarm` invoke with
both tables so you can confirm which one the VM expects **before** trusting
real funds to a deployment.

## Owner operations

```bash
xvault owner --contract <hash> --action pause
xvault owner --contract <hash> --action set-fee --value 30          # bps
xvault owner --contract <hash> --action set-bounty --value 0.05      # XEL
xvault owner --contract <hash> --action set-fee-recipient --address xel:...
xvault owner --contract <hash> --action claim-fees --value 12.5     # XEL
xvault owner --contract <hash> --action propose-owner --address xel:...
xvault owner --contract <hash> --action accept-owner
xvault owner --contract <hash> --action emergency-exit               # IRREVERSIBLE
xvault owner --contract <hash> --action renounce-ownership           # IRREVERSIBLE
# add --broadcast to actually send
```

## Alarms

```bash
xvault alarm --contract <hash> --network mainnet --broadcast
```

Checks solvency off-chain; with `--broadcast`, persists an on-chain pause
via the permissionless `raise_alarm` entry if the pool is short.

## Using the SDK directly

```python
from xvault.protocol import DaemonClient, WalletClient, NETWORKS
from xvault.mixer import MixerReader, prepare_deposit, deposit_params, release_params
from xvault import crypto

daemon = DaemonClient(NETWORKS["mainnet"]["daemon"])
reader = MixerReader(daemon, CONTRACT_HASH)
health = reader.health(NETWORKS["mainnet"]["xelis_asset"])
assert health["solvent"]

note = prepare_deposit("mainnet", CONTRACT_HASH, crypto.DENOMINATIONS[1], "xel:...")
```

`xvault.crypto` is the byte-exact reference of the contract's hashing and
tree logic — `tests/test_mixer_reference.py` fails CI on any drift.

## Environment

- Wallet RPC: `--wallet-url http://127.0.0.1:18082/json_rpc`
  `--wallet-auth user:pass` (defaults from the official xelis_wallet).
- Nodes: mainnet `https://node.xelis.io/json_rpc`, testnet
  `https://testnet-node.xelis.io/json_rpc`.
- The SDK stores nothing, sends telemetry nowhere, and never sees a private
  key.
