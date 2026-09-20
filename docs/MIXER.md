# PrivacyMixer V4 — Design Specification

> contracts/mixer/PrivacyMixerV4.slx · v4.0.0 · mainnet-ready

A single, self-contained privacy pool for XEL. Zero inter-contract calls,
zero external dependencies, zero keepers. One file, ~800 lines, audited
against every failure class found in the v12 codebase.

---

## 1. Model — bearer-note pool mixer

```
note_commitment = blake3("XVMIX4:NOTE:" || secret || recipient_bytes || amount_dec)
node_hash       = blake3("XVMIX4:N:"    || left || right)
zero_chain      = z[0] = blake3("XVMIX4:Z:"),  z[i] = node_hash(z[i-1], z[i-1])
```

| Phase | Entry | What happens |
|---|---|---|
| Deposit | `deposit(secret, recipient)` | attached XEL must equal a denomination exactly; the commitment is inserted into an incremental Merkle tree (depth 20, ~1M notes); **nothing but the commitment is stored**; returns the leaf index |
| Withdraw | `withdraw(secret, amount, leaf_index, siblings)` | caller must be the recipient embedded in the commitment; Merkle proof checked against the last 64 roots; leaf marked spent; payout = denomination − fee, paid **to the caller** |

### Fixed denominations

10 / 100 / 1000 XEL (1e9 / 1e10 / 1e11 atomic). Fixed amounts make every
note of a class perfectly fungible: no amount-based correlation inside a
class, and XELIS L1 additionally encrypts transfer amounts for everyone
else.

### Why recipient binding matters (v3 did not have it)

- **Note theft is dead**: a leaked secret is useless — the payout only ever
  goes to `get_caller()`, who must satisfy the commitment.
- **Front-running is dead**: copying someone's withdrawal transaction from
  the mempool fails, because the thief's address is not the committed
  recipient.
- **Privacy window**: the recipient is hidden inside a hash until the note
  is spent. While a note is outstanding, nobody can tell who will withdraw.

## 2. Threat model — honest guarantees

XELIS encrypts balances and transfer amounts (confidential transactions),
**but smart-contract interactions are public**: invoke parameters, attached
deposits and contract balances are all readable. Silex exposes no
zk-SNARK primitives today. Therefore, like every non-ZK mixer, V4 does
**not** cryptographically break the deposit→withdraw graph: when a note is
spent, an observer can see which deposit is being consumed.

What V4 guarantees:

1. **Address separation** — withdraw with a fresh wallet; the on-chain
   history of your main wallet never touches the receiving address.
2. **Bearer semantics** — the secret is transferable off-chain (sell, gift,
   escrow). Self-withdrawal is indistinguishable from a secret that changed
   hands.
3. **Shared pool** — payouts come from the pooled balance, not from "your"
   deposit; all withdrawals of a class are identical.
4. **Theft & front-run resistance** — recipient binding (above).
5. **Fixed fees, capped at 1%**, depositor-priority accounting.

Operator guidance baked into the CLI: always withdraw from a fresh address;
wait for the pool to grow before withdrawing (timing obfuscation); never
chain deposits and withdrawals in the same block window.

Roadmap: if the XELIS VM ever exposes zk primitives (see the XELIS
whitepaper's contract-confidentiality plans), the Merkle tree here is
ZK-ready by construction — the note format and tree are the standard
Tornado-style shape.

## 3. Ownership — launch training wheels, renounceable

The owner can, at any time:

- `pause()` / `unpause()` — freeze everything (incident response);
- `emergency_exit()` — **irreversible**: deposits die forever, withdrawals
  stay open, fees are waived, accrued fees are trimmed to what the pool can
  spare after covering every outstanding note; withdrawals are then paid
  pro-rata of the live pool balance (u128 math, depositors have absolute
  priority — donations during the exit are shared fairly and the pool
  drains to zero);
- `set_fee_bps(bps)` — hard-capped at 100 (1%), dead in emergency mode;
- `set_fee_recipient(addr)` — the protocol's revenue address; it survives
  renunciation, so fees keep flowing after the contract becomes trustless;
- `propose_owner` / `accept_owner` — two-step transfer;
- `renounce_ownership()` — burns every privilege. The contract then runs
  fully autonomously: no pause, no fee change, no emergency exit, forever.

The owner can **never** move deposited funds. The only paths out of this
contract are a valid note withdrawal and the fee accumulator — there is no
owner drain entry, deliberately. (Single-key emergency-withdraw entries are
the rug-switch pattern; v12 shipped fifteen of them and every one was
flagged in the audit.)

`raise_alarm()` is **permissionless**: anyone who observes
`balance < pending` can persist a pause on-chain. Deposits and withdrawals
also enforce the solvency invariant inline (defense in depth — by
construction the invariant cannot break without a VM-level bug).

## 4. Invariants (CI-checked)

- **I1** `pending == Σ denominations of unspent notes`
- **I2** `balance ≥ pending` in normal mode
- **I3** a leaf is spent at most once (`sp:<index>` marker)
- **I4** valid proofs land on one of the last 64 roots
- **I5** payouts go to `get_caller()` after every check passes
- **I6** all transfers are checked (zero swallowed failures in the file)
- **I7** no panic path reachable with public data

## 5. Client flow (xvault CLI)

```
# 1. generate a note + prepare the deposit (no keys involved)
xvault mixer deposit --amount 100 --recipient xel:FRESH... \
    --contract <hash> --network mainnet --note-out note-001.json

# 2. broadcast from your wallet (local wallet RPC / Genesix XSWD)
#    ... confirm, note-001.json gets its leaf_index

# 3. later, from the RECIPIENT wallet:
xvault mixer withdraw --note note-001.json --contract <hash> \
    --network mainnet --broadcast
```

The CLI verifies the Merkle proof locally against the live root before
spending gas, and refuses to broadcast a withdrawal from the wrong wallet.

## 6. Deployment checklist

1. Compile with the current xelis toolchain; confirm the chunk table with
   `python3 scripts/verify_chunk_ids.py`.
2. Deploy to **testnet**; run `xvault mixer probe` to confirm the VM's
   entry-id numbering (see docs/SECURITY.md §3 — two numbering conventions
   exist in the wild).
3. Exercise: deposit → status → withdraw → pause/unpause →
   emergency_exit on a sacrificial testnet deployment.
4. Verify `get_stats()` accounting after each step.
5. Deploy to mainnet with `fee_recipient` set **before** the first deposit.
6. Announce the renunciation schedule (recommended: 30–90 days).

## 7. Gas notes (from XELIS stdlib tables)

- Deposit: ~20 × (store + blake3) + root bookkeeping ≈ well within the
  5 XEL per-tx gas cap.
- Withdraw: 20 × blake3 (3000 gas each) + storage reads — the client pays
  this from the withdrawing wallet, not the pool.
