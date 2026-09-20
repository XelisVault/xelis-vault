#!/usr/bin/env python3
"""
xvault — CLI for the XELIS Vault protocol (v13).

Privacy-first design: this CLI NEVER holds your keys. Writes are prepared
here and signed by your LOCAL wallet (xelis_wallet --rpc-server, or Genesix
via XSWD). Reads go to public nodes.

Examples:
  xvault mixer status --contract <hash> --network testnet
  xvault mixer deposit --amount 100 --recipient xel:... --contract <hash> \
      --note-out note-001.json
  xvault mixer withdraw --note note-001.json --contract <hash>
  xvault mixer probe --contract <hash> --network testnet
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import crypto
from .mixer import MixerReader, Note, deposit_deposits, deposit_params, prepare_deposit, withdraw_params
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


# ---------------------------------------------------------------------------
# mixer status
# ---------------------------------------------------------------------------

def cmd_mixer_status(args) -> None:
    contract = _require_contract(args)
    d = _daemon(args.network)
    reader = MixerReader(d, contract)
    xel = NETWORKS[args.network]["xelis_asset"]
    h = reader.health(xel)
    print(f"PrivacyMixer V4 — {contract[:16]}… ({args.network})")
    print(f"  notes issued   : {h['notes_issued']}")
    print(f"  notes spent    : {h['notes_spent']}")
    print(f"  pool pending   : {crypto.fmt_xel(h['pending'])}")
    print(f"  contract bal.  : {crypto.fmt_xel(h['balance'])}")
    print(f"  solvent        : {'YES' if h['solvent'] else 'NO — INSOLVABLE, raise the alarm!'}")
    print(f"  fees owed      : {crypto.fmt_xel(h['fees_owed'])} @ {h['fee_bps'] / 100:.2f}%")
    print(f"  total deposited: {crypto.fmt_xel(h['total_deposited'])}")
    print(f"  total withdrawn: {crypto.fmt_xel(h['total_withdrawn'])}")
    print(f"  state          : {'PAUSED' if h['paused'] else 'live'}"
          f"{' + EMERGENCY EXIT' if h['emode'] else ''}")
    root = reader.root()
    print(f"  merkle root    : {root or '(none)'}")


# ---------------------------------------------------------------------------
# mixer deposit
# ---------------------------------------------------------------------------

def cmd_mixer_deposit(args) -> None:
    contract = _require_contract(args)
    amount = int(round(args.amount * 1e8))
    note = prepare_deposit(args.network, contract, amount, args.recipient)

    print("New bearer note generated (client-side, never sent on-chain):")
    print(f"  secret     : {note.secret}")
    print(f"  recipient  : {note.recipient}")
    print(f"  amount     : {crypto.fmt_xel(note.amount)}")
    params = deposit_params(note)
    deposits = deposit_deposits(note, NETWORKS[args.network]["xelis_asset"])
    print(f"  entry      : deposit (chunk {MIXER_ENTRY_IDS['deposit']})")
    print(f"  params     : [Hash(secret), Address(recipient)]")
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
        note.created_topoheight = reader.d.topoheight()

    note.save(args.note_out)
    print(f"\nnote written to {args.note_out} (chmod 600). KEEP IT SAFE: the "
          "note is the only proof of your deposit. Losing it = losing the funds.")
    if note.leaf_index is not None:
        print(f"leaf index: {note.leaf_index}")


# ---------------------------------------------------------------------------
# mixer withdraw
# ---------------------------------------------------------------------------

def cmd_mixer_withdraw(args) -> None:
    contract = _require_contract(args)
    note = Note.load(args.note)
    if note.contract != contract:
        sys.exit(f"error: note is for contract {note.contract[:16]}…, "
                 f"not this one")
    if note.network != args.network:
        sys.exit(f"error: note is for {note.network}, not {args.network}")

    reader = MixerReader(_daemon(args.network), contract)

    print("Preparing withdrawal proof from live contract storage…")
    params = withdraw_params(note, reader)
    fee_bps = reader.fee_bps()
    fee = crypto.fee_for(note.amount, fee_bps) if not reader.emode() else 0
    print(f"  leaf       : {note.leaf_index}")
    print(f"  amount     : {crypto.fmt_xel(note.amount)}")
    print(f"  fee        : {crypto.fmt_xel(fee)} ({fee_bps / 100:.2f}%)"
          + (" (waived — emergency exit)" if reader.emode() else ""))
    print(f"  you receive: {crypto.fmt_xel(note.amount - fee)}")
    print(f"  entry      : withdraw (chunk {MIXER_ENTRY_IDS['withdraw']})")
    print("  IMPORTANT  : broadcast this from the note's RECIPIENT wallet "
          f"({note.recipient[:24]}…) — any other wallet fails the proof.")

    if args.broadcast:
        w = _wallet(args)
        address = w.address()
        if address != note.recipient:
            sys.exit(f"error: connected wallet {address} is not the note "
                     f"recipient {note.recipient} — the proof would fail")
        before = w.nonce()
        tx = w.invoke(contract, MIXER_ENTRY_IDS["withdraw"], params)
        print(f"broadcast: {tx}")
        w.wait_nonce_advance(before)
        print("confirmed — note spent. Archive or delete the note file.")


# ---------------------------------------------------------------------------
# mixer note-info
# ---------------------------------------------------------------------------

def cmd_mixer_note_info(args) -> None:
    note = Note.load(args.note)
    contract = _require_contract(args)
    reader = MixerReader(_daemon(args.network), contract)
    print(f"note file   : {args.note}")
    print(f"network     : {note.network}")
    print(f"amount      : {crypto.fmt_xel(note.amount)}")
    print(f"recipient   : {note.recipient}")
    print(f"leaf index  : {note.leaf_index}")
    if note.leaf_index is not None:
        print(f"spent       : {'YES' if reader.is_spent(note.leaf_index) else 'no'}")
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
        print("contract is now paused persistently.")
    else:
        print("run with --broadcast to persist the pause on-chain.")


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

def cmd_entries(args) -> None:
    print("PrivacyMixer V4 chunk ids — compiler numbering "
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
        description="XELIS Vault protocol CLI (v13) — mixer-first, "
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

    m = sub.add_parser("mixer", help="PrivacyMixer V4 operations")
    ms = m.add_subparsers(dest="mixer_cmd", required=True)

    sp = ms.add_parser("status"); common(sp)
    sp.set_defaults(func=cmd_mixer_status)

    sp = ms.add_parser("deposit")
    common(sp)
    sp.add_argument("--amount", type=float, required=True,
                    help="exact denomination: 10, 100 or 1000 (XEL)")
    sp.add_argument("--recipient", required=True,
                    help="FRESH address that will withdraw the note")
    sp.add_argument("--note-out", help="where to save the bearer note JSON")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_mixer_deposit)

    sp = ms.add_parser("withdraw")
    common(sp)
    sp.add_argument("--note", required=True, help="note JSON from deposit")
    sp.add_argument("--broadcast", action="store_true")
    sp.set_defaults(func=cmd_mixer_withdraw)

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
                            "set-fee-recipient", "claim-fees", "propose-owner",
                            "accept-owner", "renounce-ownership"])
    o.add_argument("--value", type=float, help="bps for set-fee, XEL for claim-fees")
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
