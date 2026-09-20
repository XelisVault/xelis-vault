# PrivacyMixer V5 "Dead-Drop" — Design Specification

> contracts/mixer/PrivacyMixerV5.slx · v5.0.0 · mainnet-ready

A single, self-contained privacy pool for XEL. Zero inter-contract calls,
zero external dependencies, zero trusted relayers. One file, ~750 lines,
audited against every failure class found in the v12 codebase — and against
the two V4 design flaws (see §1).

---

## 1. Why V4 was superseded

V4 shipped two flaws, both fatal to the mixer's purpose:

1. **The recipient leaked at deposit time.** `deposit(secret, recipient)`
   carried the payout address in plaintext invoke parameters — anyone
   reading the blockchain could link depositor → recipient *immediately*,
   before any withdrawal.
2. **The recipient had to pay gas to withdraw.** The fresh receiving wallet
   had to fund itself first (from the depositor's wallet, usually), and that
   funding transaction painted the exact link the mixer was supposed to cut.

V5 inverts the model: the recipient never appears on-chain at deposit, never
signs anything, never needs gas. Funds arrive on their own, at a random
moment inside a bounded window. The archived V4 lives in
`contracts/mixer/superseded/` as the regression corpus for lint rule R11.

## 2. Model — bearer-note pool with dead-drop payouts

```
note_commitment = blake3("XVMIX5:NOTE:" || secret || recipient_bytes || amount_dec)
node_hash       = blake3("XVMIX5:N:"    || left || right)
zero_chain      = z[0] = blake3("XVMIX5:Z:"),  z[i] = node_hash(z[i-1], z[i-1])

recipient_bytes = Silex Address::to_bytes()
               = [mainnet(1)] [public_key(32)] [addr_type(1)]   // 34 bytes
address string  = XELIS Bech32, separator ':' ("xel:…" / "xet:…")
```

The commitment is computed **client-side** (xvault CLI). At deposit time
only the hash travels; the secret and the recipient never leave the
depositor's machine.

| Phase | Entry | What happens |
|---|---|---|
| Deposit | `deposit(commitment, delay)` | attached XEL must equal a denomination exactly; the commitment is inserted into an incremental Merkle tree (depth 20, ~1M notes); the note's unlock topoheight = current topoheight + delay is stored; **nothing but the commitment and the unlock number is stored**; returns the leaf index |
| Release | `release(recipient, secret, amount, leaf_index, siblings)` | **permissionless** — anyone can call it once the unlock topoheight is reached; the contract recomputes the commitment from the params and pays the **committed** recipient (never the caller, except the bounty); Merkle proof checked against the last 64 roots; leaf marked spent |
| Batch | `release_many(recipients[], secrets[], amounts[], leaf_indices[], siblings[])` | up to 16 notes per call, all-or-nothing; gas amortization for release bots |

### The dead-drop window

- `MIN_DELAY_TOPO = 720` (~1 hour at 5s topoheights)
- `MAX_DELAY_TOPO = 51 840` (~3 days)
- The depositor draws `delay` uniformly at random (client-side CSPRNG); the
  contract enforces the bound on-chain. The payout lands at a random moment
  inside the window — timing is decorrelated from the deposit.

### Who releases?

Anyone — and that is safe by construction:

- **The payout address is recovered from the commitment**, not taken from
  the caller: a front-runner who copies a release transaction verbatim only
  pays the gas; the funds still land on the committed recipient. Note theft
  and release hijacking are dead.
- A **bounty** (default 0.05 XEL, hard cap 0.5 XEL) is paid from the note to
  whoever releases it. Community release bots can run profitably and
  trustlessly — no registry, no whitelist, no power: they cannot steal,
  redirect or censor (delaying only risks their own bounty).
- The depositor's note is a **bearer instrument**: it can be sold, gifted or
  escrowed off-chain. Whoever holds it can release the note; the funds still
  go to the committed recipient.
- If no bot exists, the recipient, a friend, or the depositor from any
  funded wallet can release manually — notes never expire.

### Why not Scheduled Executions?

XELIS native Scheduled Executions *can* fire a future contract call without
a user transaction — but the scheduled call's parameters (including any
recipient address) are protocol state, public at deposit time. Putting the
recipient there would reintroduce the V4 leak. The permissionless
bounty-funded release keeps the recipient hidden until the payout moment
while staying fully automatic in practice (bots).

## 3. Threat model — honest guarantees

XELIS encrypts balances and transfer amounts (confidential transactions),
**but smart-contract interactions are public**: invoke parameters, attached
deposits and contract storage are all readable. Silex exposes no zk-SNARK
primitives today. Therefore, stated honestly:

- **While a note is outstanding, nothing on-chain links it to anyone.** The
  deposit shows a random-looking hash and a delay number. The recipient
  never appears, never transacts, never needs funding.
- **At release time**, the release transaction reveals (secret, recipient);
  an archive node can recompute the commitment and match it to the deposit.
  This is the fundamental limit of a non-ZK mixer. What protects users in
  practice:
  1. **Fresh recipient address** — no history, no funding trail, nothing to
     correlate with the depositor;
  2. **Random delay** — the payout time is uniform in [~1h, ~3d], breaking
     deposit→payout timing correlation;
  3. **Shared pool + fixed denominations** — every payout of a class is
     identical, from the same pool, with amounts additionally encrypted at L1;
  4. **Third-party release** — the release transaction comes from a bot or
     burner, not from the recipient, adding another unlinkable hop.
- **Theft & front-running are cryptographically dead** (commitment binding).
- The tree and note format are the standard Tornado-style shape: the day the
  XELIS VM exposes zk primitives, this becomes a ZK mixer without changing
  the tree.

## 4. Ownership — launch training wheels, renounceable

The owner can, at any time:

- `pause()` / `unpause()` — freeze **new deposits only**. Releases always
  work: the owner can never freeze exits (that is the rug-switch pattern
  v12 shipped fifteen of);
- `emergency_exit()` — **irreversible**: deposits die forever, fees are
  waived, releases keep working pro-rata of the live pool until the last
  note is spent (u128 math, depositors have absolute priority);
- `set_fee_bps(bps)` — hard-capped at 100 (1%), dead in emergency mode;
- `set_bounty(bounty)` — hard-capped at 0.5 XEL (bots' incentive, paid from
  the note, survives renunciation);
- `set_fee_recipient(addr)` — the protocol's revenue address; it survives
  renunciation, so fees keep flowing after the contract becomes trustless;
- `propose_owner` / `accept_owner` — two-step transfer;
- `renounce_ownership()` — burns every privilege. The contract then runs
  fully autonomously: no pause, no fee change, no emergency exit, forever.

The owner can **never** move deposited funds. The only paths out of this
contract are a valid note release and the fee accumulator — there is no
owner drain entry, deliberately.

`raise_alarm()` is **permissionless**: anyone who observes
`balance < pending` persists a deposit freeze on-chain. Deposits and
releases also enforce the solvency invariant inline (defense in depth).

## 5. Invariants (CI-checked)

- **I1** `pending == Σ denominations of unspent notes`
- **I2** `balance ≥ pending` in normal mode
- **I3** a leaf is spent at most once (`sp:<index>` marker)
- **I4** valid proofs land on one of the last 64 roots
- **I5** payouts go to the commitment-embedded recipient only; bounties to
  the release caller only, after every check passed
- **I6** all transfers are checked (zero swallowed failures in the file)
- **I7** no panic path reachable with public data
- **I8** a note can never be released before its unlock topoheight
- **I9** the owner can never block a release (pause affects deposits only)

CI additionally enforces **lint rule R11**: any `deposit*` entry taking an
`Address` parameter is a BLOCKER (the V4 flaw can never ship again).

## 6. Client flow (xvault CLI)

```
# 1. generate a note (secret + commitment stay local; delay drawn at random)
xvault mixer deposit --amount 100 --recipient xel:FRESH... \
    --contract <hash> --network mainnet --note-out note-001.json

# 2. nothing else to do — after the unlock (~1h..~3d), a release bot (or
#    anyone) triggers the payout and the funds arrive at the recipient

# 3. optional: check / self-release
xvault mixer note-info --note note-001.json --contract <hash> --network mainnet
xvault mixer release --note note-001.json --contract <hash> --network mainnet --broadcast
xvault mixer release-many --notes-dir notes/ --contract <hash> --network mainnet --broadcast
```

The CLI verifies locally (proof against the live root, unlock status,
commitment match) before spending gas, and computes the commitment with a
byte-exact port of `Address::to_bytes()` (XELIS Bech32, separator `:`).

## 7. Deployment checklist

1. Compile with the current xelis toolchain; confirm the chunk table with
   `python3 scripts/verify_chunk_ids.py`.
2. Deploy to **testnet**; run `xvault mixer probe` to confirm the VM's
   entry-id numbering (two numbering conventions exist in the wild).
3. Exercise: deposit → note-info (locked) → wait unlock → release by a
   THIRD wallet → confirm payout lands on the committed recipient →
   pause (deposits freeze, release still works) → emergency_exit on a
   sacrificial testnet deployment.
4. Verify `get_stats()` accounting after each step.
5. Deploy to mainnet with `fee_recipient` set **before** the first deposit.
6. Announce the renunciation schedule (recommended: 30–90 days).
7. Seed a release bot (any community member can — `release_many` + bounty).

## 8. Gas notes (from XELIS stdlib tables)

- Deposit: ~20 × (store + blake3) + root bookkeeping ≈ well within the
  per-tx gas cap.
- Release: 20 × blake3 (3000 gas each) + storage reads + 2 transfers — the
  releaser pays this from their own wallet and recovers the bounty.
- release_many amortizes the fixed cost across up to 16 notes.
