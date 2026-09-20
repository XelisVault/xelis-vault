# xvault — XELIS Vault CLI & SDK

Python tooling for the XelisVault protocol (v14, PrivacyMixer V5). **Key-less
by design**: the CLI prepares transactions and reads state; your local wallet
(`xelis_wallet --rpc-server`, or Genesix via XSWD) signs and broadcasts.

## Install

```bash
pip install ./sdk/xvault      # or: pip install -e ./sdk/xvault[dev]
```

Requires Python ≥ 3.10. Dependencies: `requests`, `blake3`.

## Mixer workflow

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
