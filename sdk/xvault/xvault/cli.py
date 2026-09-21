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
from .launchpad import (DEFAULTS, LaunchpadReader, buy_quote, current_price,
                         fmt_token, market_cap, propose_deposits,
                         propose_params, sell_quote, team_alloc_of)
from .mixer import (MixerReader, Note, deposit_deposits, deposit_params,
                    prepare_deposit, release_many_params, release_params)
from .protocol import (DaemonClient, MIXER_ENTRY_IDS, MIXER_ENTRY_IDS_ALT,
                       LAUNCHPAD_ENTRY_IDS, LAUNCHPAD_ENTRY_IDS_ALT,
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
# launchpad status / project / quote / propose
# ---------------------------------------------------------------------------

def cmd_launchpad_status(args) -> None:
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    cfg = reader.config()
    st = reader.stats()
    xel = NETWORKS[args.network]["xelis_asset"]
    balance = reader.d.get_contract_balance(contract, xel)
    print(f"VaultLaunch — {contract[:16]}… ({args.network})")
    print(f"  projects        : {st['count']}")
    print(f"  paused          : {'YES — new proposals & buys frozen' if st['paused'] else 'no'}")
    print(f"  curve XEL       : {crypto.fmt_xel(st['total_curve_xel'])}")
    print(f"  refundable XEL  : {crypto.fmt_xel(st['locked_refunds'])}")
    print(f"  contract bal.   : {crypto.fmt_xel(balance)}")
    solvent = balance >= (st['total_curve_xel'] + st['locked_refunds']
                          + st['pending_fees'])
    print(f"  solvent         : {'YES' if solvent else 'NO — balance below commitments!'}")
    print(f"  pending fees    : {crypto.fmt_xel(st['pending_fees'])} "
          f"(lifetime {crypto.fmt_xel(st['fees_collected_lifetime'])})")
    print(f"  total volume    : {crypto.fmt_xel(st['total_volume'])}")
    print("  parameters      :")
    print(f"    submission fee        : {crypto.fmt_xel(cfg['submission_fee'])}")
    print(f"    min liquidity         : {crypto.fmt_xel(cfg['min_liquidity'])}")
    print(f"    trading fee           : {cfg['trading_fee_bps'] / 100:.2f}% (bonding)")
    print(f"    graduated fee         : {cfg['graduated_fee_bps'] / 100:.2f}% "
          f"(post-graduation, always <= trading fee)")
    print(f"    migration fee         : {cfg['migration_fee_bps'] / 100:.2f}% "
          f"of reserves, once at graduation")
    print(f"    direct listing        : >= {crypto.fmt_xel(cfg['direct_listing_threshold'])} "
          f"liquidity skips bonding")
    print(f"    validation            : {cfg['min_participants']} voters, "
          f">= {cfg['min_approval_ratio_bps'] / 100:.0f}% support, "
          f"{cfg['validation_duration']} topos window")
    print(f"    graduation            : x{cfg['graduation_multiplier']} liquidity")
    print(f"    team unlock           : {cfg['team_unlock_delay']} topos delay "
          f"if never graduated; vesting "
          f"{cfg['vesting_min']}..{cfg['vesting_max']} topos")
    print(f"    recovery (graduated)  : {crypto.fmt_xel(cfg['recovery_fee'])}, "
          f"{cfg['recovery_min_participants']} voters, "
          f">= {cfg['recovery_min_ratio_bps'] / 100:.0f}%")


def cmd_launchpad_project(args) -> None:
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    if args.id >= reader.count():
        sys.exit(f"error: project {args.id} does not exist "
                 f"(total: {reader.count()})")
    p = reader.project(args.id)
    q = reader.quotes(args.id)
    print(f"#{p['id']} {p['name']} ({p['symbol']}) — {p['status_label']}")
    print(f"  creator    : {p['creator']}")
    print(f"  created    : topo {p['created_topo']}  "
          f"(window ends topo {p['deadline']})")
    if p['website']:
        print(f"  website    : {p['website']}")
    print(f"  supply     : {fmt_token(p['total_supply'])} "
          f"({p['total_supply'] / 1e8:,.0f} tokens), "
          f"team {p['team_bps'] / 100:.0f}%")
    print(f"  liquidity  : {crypto.fmt_xel(p['liquidity'])} deposited"
          + (" (direct-listing eligible)" if p['direct_listing'] else ""))
    print(f"  curve      : {crypto.fmt_xel(p['reserves'])} reserves, "
          f"{fmt_token(p['curve'])} sellable")
    print(f"  price      : {q['price'] / 1e8:.8f} XEL/token  "
          f"(mc {crypto.fmt_xel(q['market_cap'])})")
    print(f"  fee        : {q['fee_bps'] / 100:.2f}% "
          f"({'graduated' if q['graduated'] else 'bonding'} rate)")
    print(f"  votes      : {p['supports']} support / {p['reports']} report "
          f"(round {p['round']}, graduated: {bool(p['graduated'])})")
    print(f"  volume     : {crypto.fmt_xel(p['volume'])}")
    if args.owner:
        bal = reader.token_balance(args.id, args.owner)
        print(f"  balance    : {fmt_token(bal)} tokens ({args.owner})")


def cmd_launchpad_team(args) -> None:
    """Team allocation panel (D3): vesting state and claimable amount."""
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    if args.id >= reader.count():
        sys.exit(f"error: project {args.id} does not exist "
                 f"(total: {reader.count()})")
    p = reader.project(args.id)
    topo = args.topo if args.topo is not None else reader.d.topoheight()
    t = reader.team_allocation(args.id, topo)
    print(f"#{args.id} team allocation — {p['status_label']}")
    print(f"  allocation  : {fmt_token(t['team_alloc'])} tokens "
          f"({p['team_bps'] / 100:.0f}% of supply)")
    print(f"  paid so far : {fmt_token(t['team_paid'])}")
    print(f"  remaining   : {fmt_token(t['team_remaining'])}")
    if t['vesting_start'] > 0:
        done = min(max(topo - t['vesting_start'], 0), t['vesting_duration'])
        print(f"  vesting     : started topo {t['vesting_start']}, "
              f"{t['vesting_duration']} topos linear "
              f"({done / t['vesting_duration'] * 100:.1f}% elapsed)")
    else:
        print("  vesting     : none started (immediate full claim available "
              "once unlocked)")
    if p['graduated']:
        print("  unlock      : GRADUATED — full allocation unlockable")
    elif p['bonding_start']:
        cfg = reader.config()
        elapsed = topo - p['bonding_start']
        remaining = cfg['team_unlock_delay'] - elapsed
        if remaining > 0:
            print(f"  unlock      : late claim in {remaining} topos "
                  f"({remaining * 5 / 86400:.1f} days at 5s/topo) "
                  f"if never graduated")
        else:
            print("  unlock      : late claim AVAILABLE (delay elapsed)")
    else:
        print("  unlock      : none yet (project still in validation)")
    print(f"  claimable   : {fmt_token(t['claimable_now'])} tokens now "
          f"(chunk {LAUNCHPAD_ENTRY_IDS['claim_team_allocation']})")


def cmd_launchpad_quote(args) -> None:
    """Offline curve calculator — mirrors the contract math exactly."""
    reserves = int(round(args.reserves * 1e8))
    curve = int(round(args.curve * 1e8))
    fee_bps = args.fee_bps
    if reserves <= 0 or curve <= 0:
        sys.exit("error: --reserves and --curve must be positive")
    price = current_price(reserves, curve)
    print(f"curve: {crypto.fmt_xel(reserves)} reserves / "
          f"{fmt_token(curve)} sellable "
          f"-> price {price / 1e8:.8f} XEL/token")
    if args.buy is not None:
        xel_in = int(round(args.buy * 1e8))
        out = buy_quote(reserves, curve, xel_in, fee_bps)
        print(f"buy  {crypto.fmt_xel(xel_in)} (fee {fee_bps / 100:.2f}%) "
              f"-> {fmt_token(out)} tokens "
              f"(avg {out / (xel_in / 1e8) / 1e8:,.2f} tokens/XEL)")
    if args.sell is not None:
        tokens = int(round(args.sell * 1e8))
        out = sell_quote(reserves, curve, tokens, fee_bps)
        print(f"sell {fmt_token(tokens)} tokens "
              f"-> {crypto.fmt_xel(out)} out (fee {fee_bps / 100:.2f}%)")


def cmd_launchpad_propose(args) -> None:
    """Prepare a propose() invoke — signs & sends via the LOCAL wallet."""
    contract = _require_contract(args)
    if not (1 <= len(args.name) <= 64):
        sys.exit("error: --name length must be 1..64")
    if not (1 <= len(args.symbol) <= 16):
        sys.exit("error: --symbol length must be 1..16")
    total_supply = int(round(args.supply * 1e8))
    if not (100_000_000 <= total_supply <= 10_000_000_000_000_000):
        sys.exit("error: --supply must be within [1, 100M] tokens")
    if not (0 <= args.team_bps <= 2000):
        sys.exit("error: --team-bps must be within [0, 2000] (max 20%)")
    liquidity = int(round(args.liquidity * 1e8))

    reader = LaunchpadReader(_daemon(args.network), contract)
    cfg = reader.config()
    if liquidity < cfg["min_liquidity"]:
        sys.exit(f"error: liquidity below min_liquidity "
                 f"({crypto.fmt_xel(cfg['min_liquidity'])})")
    deposit = cfg["submission_fee"] + liquidity
    team = team_alloc_of(total_supply, args.team_bps)

    print(f"propose() — chunk {LAUNCHPAD_ENTRY_IDS['propose']}")
    print(f"  name/symbol : {args.name} ({args.symbol})")
    print(f"  supply      : {args.supply:,.0f} tokens, "
          f"team {args.team_bps / 100:.0f}% ({team / 1e8:,.0f} tokens, "
          f"claimable at graduation or via vesting)")
    print(f"  deposit     : {crypto.fmt_xel(deposit)} total = "
          f"{crypto.fmt_xel(cfg['submission_fee'])} fee + "
          f"{crypto.fmt_xel(liquidity)} seed liquidity")
    if liquidity >= cfg["direct_listing_threshold"]:
        print(f"  path        : DIRECT LISTING — liquidity >= threshold "
              f"({crypto.fmt_xel(cfg['direct_listing_threshold'])}): graduates "
              f"the moment validation passes")
    else:
        print(f"  path        : bonding curve (direct listing needs >= "
              f"{crypto.fmt_xel(cfg['direct_listing_threshold'])})")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    params = propose_params(args.name, args.symbol, args.description,
                            args.website, args.logo, total_supply, args.team_bps)
    deposits = propose_deposits(cfg["submission_fee"], liquidity,
                                NETWORKS[args.network]["xelis_asset"])
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHPAD_ENTRY_IDS["propose"], params,
                  deposits=deposits)
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — project created (id = total_projects - 1)")


def cmd_launchpad_entries(args) -> None:
    print("VaultLaunch chunk ids — compiler numbering "
          "(constructor=0 + every function in declaration order, CI-verified):")
    for name, eid in sorted(LAUNCHPAD_ENTRY_IDS.items(), key=lambda kv: kv[1]):
        print(f"  {eid:>3}  {name}")
    print("\nlegacy entries-only numbering (kept for probe only):")
    for name, eid in sorted(LAUNCHPAD_ENTRY_IDS_ALT.items(), key=lambda kv: kv[1]):
        print(f"  {eid:>3}  {name}")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xvault",
        description="XELIS Vault protocol CLI (v16) — dead-drop mixer + "
                    "VaultLaunch launchpad, key-less by design.")
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

    lp = sub.add_parser("launchpad", help="VaultLaunch operations")
    ls = lp.add_subparsers(dest="launchpad_cmd", required=True)

    sp = ls.add_parser("status"); common(sp)
    sp.set_defaults(func=cmd_launchpad_status)

    sp = ls.add_parser("project"); common(sp)
    sp.add_argument("--id", type=int, required=True, help="project id")
    sp.add_argument("--owner", help="check this address's token balance")
    sp.set_defaults(func=cmd_launchpad_project)

    sp = ls.add_parser("team"); common(sp)
    sp.add_argument("--id", type=int, required=True, help="project id")
    sp.add_argument("--topo", type=int,
                    help="reference topoheight (default: daemon's current)")
    sp.set_defaults(func=cmd_launchpad_team)

    sp = ls.add_parser("quote")
    sp.add_argument("--reserves", type=float, required=True,
                    help="curve XEL reserves")
    sp.add_argument("--curve", type=float, required=True,
                    help="curve sellable token supply")
    sp.add_argument("--buy", type=float, help="XEL amount to quote a buy")
    sp.add_argument("--sell", type=float, help="token amount to quote a sell")
    sp.add_argument("--fee-bps", type=int,
                    default=DEFAULTS["trading_fee_bps"],
                    help="trading fee in bps (default: %(default)s)")
    sp.set_defaults(func=cmd_launchpad_quote, need_contract=False)

    sp = ls.add_parser("propose"); common(sp)
    sp.add_argument("--name", required=True, help="token name (1..64 chars)")
    sp.add_argument("--symbol", required=True, help="symbol (1..16 chars)")
    sp.add_argument("--description", default="", help="short description")
    sp.add_argument("--website", default="", help="project website")
    sp.add_argument("--logo", default="", help="logo URL")
    sp.add_argument("--supply", type=float, required=True,
                    help="total supply in whole tokens (1..100M)")
    sp.add_argument("--team-bps", type=int, default=1000,
                    help="team allocation in bps, max 2000 (default: 10%%)")
    sp.add_argument("--liquidity", type=float, required=True,
                    help="seed liquidity in XEL (>= min_liquidity)")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_launchpad_propose)

    sp = ls.add_parser("entries")
    sp.set_defaults(func=cmd_launchpad_entries, need_contract=False)

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
