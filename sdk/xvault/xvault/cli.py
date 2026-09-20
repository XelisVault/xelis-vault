#!/usr/bin/env python3
"""
xvault — CLI for the XELIS Vault protocol (v14, PrivacyMixer V5).

Privacy-first design: this CLI NEVER holds your keys. Writes are prepared
here and signed by your LOCAL wallet (xelis_wallet --rpc-server, or Genesix
via XSWD). Reads go to public nodes.

Dead-drop model (V5):
  * deposit sends ONLY a client-computed commitment + a random delay
    (~1h..~3d) — the recipient address never appears on-chain;
  * the payout happens automatically when anyone (a release bot earning the
    bounty, a friend, you from any wallet) triggers `release` after the
    unlock topoheight — funds ALWAYS land on the committed recipient, and
    the recipient itself NEVER needs gas or interacts with the contract.

Examples:
  xvault mixer status --contract <hash> --network testnet
  xvault mixer deposit --amount 100 --recipient xet:... --contract <hash> \
      --note-out note-001.json
  xvault mixer release --note note-001.json --contract <hash> --broadcast
  xvault mixer release-many --notes-dir notes/ --contract <hash> --broadcast
  xvault mixer probe --contract <hash> --network testnet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import crypto
from .mixer import (MixerReader, Note, deposit_deposits, deposit_params,
                    prepare_deposit, release_many_params, release_params)
from .protocol import (DaemonClient, MIXER_ENTRY_IDS, MIXER_ENTRY_IDS_ALT,
                       NETWORKS, WALLET_AUTH, WALLET_URL, WalletClient,
                       val_addr, val_str, val_u64)


def _daemon(network: str) -> DaemonClient:
    return DaemonClient(NETWORKS[network]["daemon"])


def _wallet(args) -> WalletClient:
    return WalletClient(args.wallet_url, tuple(args.wallet_auth.split(":", 1)))


def _require_contract(args) -> str:
    if not args.contract or len(args.contract) != 64:
        sys.exit("error: --contract must be the 64-hex deployed contract hash")
    return args.contract.lower()


def _load_note(args) -> Note:
    note = Note.load(args.note)
    contract = _require_contract(args)
    if note.contract != contract:
        sys.exit(f"error: note is for contract {note.contract[:16]}…, "
                 f"not this one")
    if note.network != args.network:
        sys.exit(f"error: note is for {note.network}, not {args.network}")
    return note


# ---------------------------------------------------------------------------
# mixer status
# ---------------------------------------------------------------------------

def cmd_mixer_status(args) -> None:
    contract = _require_contract(args)
    d = _daemon(args.network)
    reader = MixerReader(d, contract)
    xel = NETWORKS[args.network]["xelis_asset"]
    h = reader.health(xel)
    print(f"PrivacyMixer V5 — {contract[:16]}… ({args.network})")
    print(f"  notes issued   : {h['notes_issued']}")
    print(f"  notes spent    : {h['notes_spent']}")
    print(f"  pool pending   : {crypto.fmt_xel(h['pending'])}")
    print(f"  contract bal.  : {crypto.fmt_xel(h['balance'])}")
    print(f"  solvent        : {'YES' if h['solvent'] else 'NO — INSOLVABLE, raise the alarm!'}")
    print(f"  fees owed      : {crypto.fmt_xel(h['fees_owed'])} @ {h['fee_bps'] / 100:.2f}%")
    print(f"  release bounty : {crypto.fmt_xel(h['bounty'])}")
    print(f"  total deposited: {crypto.fmt_xel(h['total_deposited'])}")
    print(f"  total released : {crypto.fmt_xel(h['total_released'])}")
    print(f"  window         : {crypto.MIN_DELAY_TOPO}..{crypto.MAX_DELAY_TOPO} topos "
          f"(~1h..~3d)")
    print(f"  state          : {'DEPOSITS PAUSED' if h['paused'] else 'live'}"
          f"{' + EMERGENCY EXIT' if h['emode'] else ''}"
          f"  (releases always open)")
    root = reader.root()
    print(f"  merkle root    : {root or '(none)'}")


# ---------------------------------------------------------------------------
# mixer deposit
# ---------------------------------------------------------------------------

def cmd_mixer_deposit(args) -> None:
    contract = _require_contract(args)
    amount = int(round(args.amount * 1e8))
    delay = args.delay  # None = uniform random in the window
    note = prepare_deposit(args.network, contract, amount, args.recipient, delay)

    print("New dead-drop note generated (client-side, never sent on-chain):")
    print(f"  secret     : {note.secret}")
    print(f"  recipient  : {note.recipient}  (hidden in the commitment)")
    print(f"  amount     : {crypto.fmt_xel(note.amount)}")
    print(f"  commitment : {note.commitment}")
    print(f"  delay      : {note.delay} topos "
          f"(~{note.delay * 5 / 3600:.1f}h)")
    params = deposit_params(note)
    deposits = deposit_deposits(note, NETWORKS[args.network]["xelis_asset"])
    print(f"  entry      : deposit (chunk {MIXER_ENTRY_IDS['deposit']})")
    print(f"  params     : [Hash(commitment), u64(delay)]  — NO address, NO secret")
    print(f"  attached   : {crypto.fmt_xel(note.amount)} of XEL")

    if not args.note_out:
        sys.exit("\nerror: --note-out is required — without the note file the "
                 "funds are UNRECOVERABLE (nobody can reconstruct the secret)")

    if args.broadcast:
        w = _wallet(args)
        print(f"\nwallet address: {w.address()}")
        before = w.nonce()
        tx = w.invoke(contract, MIXER_ENTRY_IDS["deposit"], params,
                      deposits=deposits)
        print(f"broadcast: {tx}")
        w.wait_nonce_advance(before)
        print("confirmed — reading your leaf index from the contract…")
        reader = MixerReader(_daemon(args.network), contract)
        note.leaf_index = reader.leaf_count() - 1
        unlock = reader.unlock_topoheight(note.leaf_index)
        note.unlock_topoheight = unlock
        note.created_topoheight = reader.d.topoheight()

    note.save(args.note_out)
    print(f"\nnote written to {args.note_out} (chmod 600). KEEP IT SAFE: the "
          "note is the only proof of your deposit. Losing it = losing the funds.")
    if note.leaf_index is not None:
        print(f"leaf index: {note.leaf_index} — payable at topoheight "
              f"{note.unlock_topoheight}")
    print("\nNothing else to do: after the unlock, anyone can release the "
          "note — the funds will arrive at the recipient wallet on their own.")


# ---------------------------------------------------------------------------
# mixer release (permissionless dead-drop payout)
# ---------------------------------------------------------------------------

def cmd_mixer_release(args) -> None:
    note = _load_note(args)
    reader = MixerReader(_daemon(args.network), args.contract)

    print("Preparing release proof from live contract storage…")
    params = release_params(note, reader)
    fee_bps = reader.fee_bps()
    bounty = reader.bounty()
    fee = crypto.fee_for(note.amount, fee_bps) if not reader.emode() else 0
    payout = note.amount - fee - bounty
    print(f"  leaf       : {note.leaf_index}")
    print(f"  recipient  : {note.recipient}  (committed — cannot be redirected)")
    print(f"  amount     : {crypto.fmt_xel(note.amount)}")
    print(f"  fee        : {crypto.fmt_xel(fee)} ({fee_bps / 100:.2f}%)"
          + (" (waived — emergency exit)" if reader.emode() else ""))
    print(f"  bounty     : {crypto.fmt_xel(bounty)} (to the releaser)")
    print(f"  recipient gets: {crypto.fmt_xel(payout)}")
    print(f"  entry      : release (chunk {MIXER_ENTRY_IDS['release']})")
    print("  note       : release is PERMISSIONLESS — broadcast from ANY "
          "funded wallet (bot, friend, burner). The payout always lands on "
          "the committed recipient; front-running is harmless.")

    if args.broadcast:
        w = _wallet(args)
        print(f"\nreleasing from wallet: {w.address()} (any wallet works)")
        before = w.nonce()
        tx = w.invoke(args.contract, MIXER_ENTRY_IDS["release"], params)
        print(f"broadcast: {tx}")
        w.wait_nonce_advance(before)
        print(f"confirmed — note spent, payout sent to {note.recipient}. "
              "Archive or delete the note file.")


def cmd_mixer_release_many(args) -> None:
    contract = _require_contract(args)
    notes_dir = Path(args.notes_dir)
    paths = sorted(notes_dir.glob("*.json"))
    if not paths:
        sys.exit(f"error: no note files found in {notes_dir}")
    notes = []
    for p in paths:
        note = Note.load(str(p))
        if note.contract != contract:
            print(f"  skip {p.name}: different contract")
            continue
        if note.network != args.network:
            print(f"  skip {p.name}: different network")
            continue
        if note.leaf_index is None:
            print(f"  skip {p.name}: no leaf index yet (deposit unconfirmed)")
            continue
        notes.append(note)
    if not notes:
        sys.exit("error: no releasable notes")

    reader = MixerReader(_daemon(args.network), contract)
    print(f"Preparing batch release of {len(notes)} notes (all-or-nothing)…")
    params = release_many_params(notes, reader)
    print(f"  entry      : release_many (chunk {MIXER_ENTRY_IDS['release_many']})")

    if args.broadcast:
        w = _wallet(args)
        print(f"\nreleasing from wallet: {w.address()} (any wallet works)")
        before = w.nonce()
        tx = w.invoke(contract, MIXER_ENTRY_IDS["release_many"], params)
        print(f"broadcast: {tx}")
        w.wait_nonce_advance(before)
        print(f"confirmed — {len(notes)} notes spent, payouts sent to their "
              "committed recipients.")


# ---------------------------------------------------------------------------
# mixer note-info
# ---------------------------------------------------------------------------

def cmd_mixer_note_info(args) -> None:
    note = _load_note(args)
    reader = MixerReader(_daemon(args.network), args.contract)
    print(f"note file   : {args.note}")
    print(f"network     : {note.network}")
    print(f"amount      : {crypto.fmt_xel(note.amount)}")
    print(f"recipient   : {note.recipient}")
    print(f"delay       : {note.delay} topos (~{note.delay * 5 / 3600:.1f}h)")
    print(f"leaf index  : {note.leaf_index}")
    if note.leaf_index is not None:
        spent = reader.is_spent(note.leaf_index)
        print(f"spent       : {'YES' if spent else 'no'}")
        if not spent:
            unlock = reader.unlock_topoheight(note.leaf_index)
            topo = reader.topoheight()
            if unlock is None:
                print("unlock      : (not found on-chain)")
            elif topo >= unlock:
                print(f"unlock      : PASSED (topo {topo} >= {unlock}) — releasable NOW")
            else:
                remaining = unlock - topo
                print(f"unlock      : locked for {remaining} topos "
                      f"(~{remaining * 5 / 3600:.1f}h, until topo {unlock})")
        leaf = reader.leaf(note.leaf_index)
        print(f"on-chain leaf: {leaf or '(not found)'}")


# ---------------------------------------------------------------------------
# mixer probe — resolve the entry-id numbering on a live network
# ---------------------------------------------------------------------------

def cmd_mixer_probe(args) -> None:
    """Send a harmless raise_alarm invoke with BOTH numbering tables and see
    which one the VM accepts (exit value 0/1 = valid entry; error = wrong id).
    Run this once on testnet before trusting any mainnet interaction."""
    contract = _require_contract(args)
    w = _wallet(args)
    print(f"wallet: {w.address()} — probing raise_alarm on {contract[:16]}… "
          f"({args.network})")
    print("(raise_alarm is free of side effects when the pool is healthy: "
          "it returns 1 and stores nothing)\n")
    for label, table in (("compiler numbering (all functions)", MIXER_ENTRY_IDS),
                         ("entries-only numbering (legacy)", MIXER_ENTRY_IDS_ALT)):
        eid = table["raise_alarm"]
        try:
            before = w.nonce()
            tx = w.invoke(contract, eid, [], broadcast=False)
            print(f"  {label}: entry_id={eid} — build OK ({tx[:16]}…)")
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: entry_id={eid} — REJECTED: {e}")
    print("\nBroadcast a real raise_alarm from the wallet with the winning "
          "numbering, then check get_version/exit_value in the tx logs.")


# ---------------------------------------------------------------------------
# owner operations
# ---------------------------------------------------------------------------

def cmd_owner(args) -> None:
    contract = _require_contract(args)
    w = _wallet(args)
    params = []
    entry = args.action
    if args.action == "set-fee":
        params = [val_u64(args.value)]
    elif args.action == "set-bounty":
        params = [val_u64(int(round(args.value * 1e8)))]
    elif args.action == "set-fee-recipient":
        params = [val_addr(args.address)]
    elif args.action == "propose-owner":
        params = [val_addr(args.address)]
    elif args.action == "claim-fees":
        params = [val_u64(int(round(args.value * 1e8)))]

    print(f"owner op: {entry} (chunk {MIXER_ENTRY_IDS[entry.replace('-', '_')]})")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    before = w.nonce()
    tx = w.invoke(contract, MIXER_ENTRY_IDS[entry.replace("-", "_")], params)
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed")


# ---------------------------------------------------------------------------
# alarm
# ---------------------------------------------------------------------------

def cmd_alarm(args) -> None:
    contract = _require_contract(args)
    d = _daemon(args.network)
    reader = MixerReader(d, contract)
    h = reader.health(NETWORKS[args.network]["xelis_asset"])
    if h["solvent"]:
        print("pool is solvent — nothing to report.")
        return
    print("!! INSOLVENCY DETECTED — balance < pending")
    if args.broadcast:
        w = _wallet(args)
        before = w.nonce()
        tx = w.invoke(contract, MIXER_ENTRY_IDS["raise_alarm"], [])
        print(f"raise_alarm broadcast: {tx}")
        w.wait_nonce_advance(before)
        print("new deposits are now frozen on-chain (releases stay open).")
    else:
        print("run with --broadcast to persist the deposit freeze on-chain.")


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

def cmd_entries(args) -> None:
    print("PrivacyMixer V5 chunk ids — compiler numbering "
          "(constructor=0 + every function in declaration order, CI-verified):")
    for name, eid in sorted(MIXER_ENTRY_IDS.items(), key=lambda kv: kv[1]):
        print(f"  {eid:>3}  {name}")
    print("\nlegacy entries-only numbering (kept for probe only):")
    for name, eid in sorted(MIXER_ENTRY_IDS_ALT.items(), key=lambda kv: kv[1]):
        print(f"  {eid:>3}  {name}")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xvault",
        description="XELIS Vault protocol CLI (v14) — dead-drop mixer, "
                    "key-less by design.")
    p.add_argument("--wallet-url", default=WALLET_URL,
                   help="local wallet RPC url (default: %(default)s)")
    p.add_argument("--wallet-auth", default=":".join(WALLET_AUTH),
                   help="local wallet basic auth user:pass")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, need_contract=True):
        sp.add_argument("--network", choices=list(NETWORKS), default="testnet")
        if need_contract:
            sp.add_argument("--contract", help="deployed contract hash (64 hex)")

    m = sub.add_parser("mixer", help="PrivacyMixer V5 operations")
    ms = m.add_subparsers(dest="mixer_cmd", required=True)

    sp = ms.add_parser("status"); common(sp)
    sp.set_defaults(func=cmd_mixer_status)

    sp = ms.add_parser("deposit")
    common(sp)
    sp.add_argument("--amount", type=float, required=True,
                    help="exact denomination: 10, 100 or 1000 (XEL)")
    sp.add_argument("--recipient", required=True,
                    help="FRESH address that will receive the payout "
                         "(never appears on-chain)")
    sp.add_argument("--delay", type=int, default=None,
                    help="unlock delay in topoheights "
                         f"[{crypto.MIN_DELAY_TOPO}..{crypto.MAX_DELAY_TOPO}] "
                         "(default: uniform random ~1h..~3d)")
    sp.add_argument("--note-out", help="where to save the bearer note JSON")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_mixer_deposit)

    sp = ms.add_parser("release")
    common(sp)
    sp.add_argument("--note", required=True, help="note JSON from deposit")
    sp.add_argument("--broadcast", action="store_true")
    sp.set_defaults(func=cmd_mixer_release)

    sp = ms.add_parser("release-many")
    common(sp)
    sp.add_argument("--notes-dir", required=True,
                    help="directory of note JSON files (max 16 releasable)")
    sp.add_argument("--broadcast", action="store_true")
    sp.set_defaults(func=cmd_mixer_release_many)

    sp = ms.add_parser("note-info"); common(sp)
    sp.add_argument("--note", required=True)
    sp.set_defaults(func=cmd_mixer_note_info)

    sp = ms.add_parser("probe"); common(sp)
    sp.set_defaults(func=cmd_mixer_probe)

    o = sub.add_parser("owner", help="privileged mixer operations")
    o.add_argument("--network", choices=list(NETWORKS), default="testnet")
    o.add_argument("--contract", required=True)
    o.add_argument("--action", required=True,
                   choices=["pause", "unpause", "emergency-exit", "set-fee",
                            "set-bounty", "set-fee-recipient", "claim-fees",
                            "propose-owner", "accept-owner", "renounce-ownership"])
    o.add_argument("--value", type=float,
                   help="bps for set-fee, XEL for set-bounty/claim-fees")
    o.add_argument("--address", help="address for set-fee-recipient/propose-owner")
    o.add_argument("--broadcast", action="store_true")
    o.set_defaults(func=cmd_owner)

    a = sub.add_parser("alarm", help="check & report pool insolvency")
    common(a)
    a.add_argument("--broadcast", action="store_true")
    a.set_defaults(func=cmd_alarm)

    e = sub.add_parser("entries", help="show mixer chunk-id tables")
    e.set_defaults(func=cmd_entries, need_contract=False)

    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
