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
from . import dex as dexmod
from .dex import (DexReader, claim_lp_fees_params, set_fee_split_params,
                  spot_price as dex_math_spot_price,
                  tokens_to_xel_out, xel_to_tokens_out)
from .launchpad import (DEFAULTS, LaunchpadReader, buy_quote, claim_vote_deposit_params,
                         current_price, fmt_token, market_cap, pid_params,
                         propose_deposits, propose_params, sell_quote,
                         set_vote_deposit_params, team_alloc_of)
from .mixer import (MixerReader, Note, deposit_deposits, deposit_params,
                    prepare_deposit, release_many_params, release_params)
from .protocol import (DaemonClient, MIXER_ENTRY_IDS, MIXER_ENTRY_IDS_ALT,
                       LAUNCHDEX_ENTRY_IDS, LAUNCHDEX_ENTRY_IDS_ALT,
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
    print(f"  budget escrow   : {crypto.fmt_xel(st['total_budgets'])} "
          f"(earmarked asset creation costs, D13)")
    print(f"  contract bal.   : {crypto.fmt_xel(balance)}")
    solvent = balance >= (st['total_curve_xel'] + st['locked_refunds']
                          + st['pending_fees'] + st['total_budgets'])
    print(f"  solvent         : {'YES' if solvent else 'NO — balance below commitments!'}")
    print(f"  pending fees    : {crypto.fmt_xel(st['pending_fees'])} "
          f"(lifetime {crypto.fmt_xel(st['fees_collected_lifetime'])})")
    print(f"  migrated        : {st['migrated_count']} project(s) on LaunchDEX "
          f"(pin {'FROZEN' if st['migrated_count'] else 'still settable'})")
    dex = st.get('dex_address')
    print(f"  dex pin         : {dex or 'NOT SET — set before the first migration (chunk 48)'}")
    print(f"  total volume    : {crypto.fmt_xel(st['total_volume'])} "
          f"(buy {crypto.fmt_xel(st['total_buy_volume'])} / "
          f"sell {crypto.fmt_xel(st['total_sell_volume'])}, "
          f"{st['total_trades']} trades — curve era; pool era on LaunchDEX)")
    vc = reader.vote_config()
    print(f"  vote dial       : {crypto.fmt_xel(vc['vote_deposit'])}"
          f"{' (FREE voting — the D21 dial is off)' if vc['vote_deposit'] == 0 else ' REFUNDABLE deposit per vote (D21)'}"
          f", {crypto.fmt_xel(vc['vote_pots'])} locked in pots")
    print("  parameters      :")
    print(f"    submission fee        : {crypto.fmt_xel(cfg['submission_fee'])}")
    print(f"    asset budget          : {crypto.fmt_xel(cfg['asset_budget'])} "
          f"(unused part refunded at creation)")
    print(f"    min liquidity         : {crypto.fmt_xel(cfg['min_liquidity'])}")
    print(f"    trading fee           : {cfg['trading_fee_bps'] / 100:.2f}% (bonding)")
    print(f"    graduated fee         : {cfg['graduated_fee_bps'] / 100:.2f}% "
          f"(curve trades until migration)")
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
    socials = [x for x in (
        ("twitter", p['twitter']), ("telegram", p['telegram']),
        ("discord", p['discord'])) if x[1]]
    if socials:
        print("  socials    : " + "  ".join(
            f"{name}={link}" for name, link in socials))
    print(f"  supply     : {fmt_token(p['total_supply'])} "
          f"({p['total_supply'] / 1e8:,.0f} tokens), "
          f"team {p['team_bps'] / 100:.0f}%"
          + (f", vesting plan {p['vesting_plan']} topos (D10)"
             if p['vesting_plan'] else ""))
    print(f"  liquidity  : {crypto.fmt_xel(p['liquidity'])} deposited"
          + (" (direct-listing eligible)" if p['direct_listing'] else ""))
    print(f"  curve      : {crypto.fmt_xel(p['reserves'])} reserves, "
          f"{fmt_token(p['curve'])} sellable")
    print(f"  price      : {q['price'] / 1e8:.8f} XEL/token  "
          f"(mc {crypto.fmt_xel(q['market_cap'])})")
    mc = reader.market_cap_history(args.id)
    if mc['all_time_high'] or mc['at_graduation']:
        print(f"  mcap       : now {crypto.fmt_xel(mc['current'])} / "
              f"ATH {crypto.fmt_xel(mc['all_time_high'])}"
              + (f" / at graduation {crypto.fmt_xel(mc['at_graduation'])}"
                 if mc['at_graduation'] else ""))
    print(f"  fee        : {q['fee_bps'] / 100:.2f}% "
          f"({'graduated' if q['graduated'] else 'bonding'} rate)")
    print(f"  votes      : {p['supports']} support / {p['reports']} report "
          f"(round {p['round']}, graduated: {bool(p['graduated'])})")
    print(f"  volume     : {crypto.fmt_xel(p['volume'])} total "
          f"(buy {crypto.fmt_xel(p['buy_volume'])} / "
          f"sell {crypto.fmt_xel(p['sell_volume'])}, "
          f"{p['trades']} trades, last at topo {p['last_trade_topo']})")
    a = reader.asset_info(args.id)
    if a['created']:
        print(f"  asset      : {a['asset']} (native confidential asset, "
              "Fixed supply — real tokens in real wallets)")
    else:
        print("  asset      : not created yet (born at validation success, D13)")
    m = reader.migration_info(args.id)
    if m['migrated']:
        print(f"  migrated   : YES at topo {m['migrated_at']} — "
              f"{crypto.fmt_xel(m['xel_sent'])} + "
              f"{fmt_token(m['tokens_sent'])} tokens seeded the permanent "
              f"LaunchDEX pool (curve closed; sells on the DEX)")
    elif p['graduated']:
        print("  migrated   : pending — anyone may call migrate() "
              f"(chunk {LAUNCHPAD_ENTRY_IDS['migrate']}, needs the "
              "contract-call permission)")
    if args.owner:
        print(f"  note       : token balances live in wallets now (v4) — "
              f"check {args.owner} in any XELIS wallet/daemon")


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
        source = "declared plan" if t['vesting_plan'] == t['vesting_duration'] and t['vesting_plan'] > 0 else "voluntary"
        print(f"  vesting     : started topo {t['vesting_start']}, "
              f"{t['vesting_duration']} topos linear "
              f"({done / t['vesting_duration'] * 100:.1f}% elapsed, {source})")
    elif t['vesting_plan'] > 0:
        print(f"  vesting     : PLAN {t['vesting_plan']} topos declared at "
              f"propose — binds automatically at graduation (D10)")
    else:
        print("  vesting     : none started (immediate full claim available "
              "once unlocked; a plan can only be declared at propose)")
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
    # D10: the vesting plan must be 0 or inside the admin window (checked
    # against the CURRENT bounds — the contract snapshots them at propose).
    if not (args.vesting == 0 or
            cfg["vesting_min"] <= args.vesting <= cfg["vesting_max"]):
        sys.exit(f"error: --vesting must be 0 (claim at graduation) or "
                 f"within [{cfg['vesting_min']}, {cfg['vesting_max']}] topos")
    for label, link in (("--twitter", args.twitter),
                        ("--telegram", args.telegram),
                        ("--discord", args.discord)):
        if len(link) > 256:
            sys.exit(f"error: {label} longer than 256 characters")
    deposit = cfg["submission_fee"] + cfg["asset_budget"] + liquidity
    team = team_alloc_of(total_supply, args.team_bps)

    print(f"propose() — chunk {LAUNCHPAD_ENTRY_IDS['propose']}")
    print(f"  name/symbol : {args.name} ({args.symbol})")
    print(f"  supply      : {args.supply:,.0f} tokens, "
          f"team {args.team_bps / 100:.0f}% ({team / 1e8:,.0f} tokens, "
          f"claimable at graduation or via vesting)")
    print(f"  deposit     : {crypto.fmt_xel(deposit)} total = "
          f"{crypto.fmt_xel(cfg['submission_fee'])} fee + "
          f"{crypto.fmt_xel(cfg['asset_budget'])} asset budget + "
          f"{crypto.fmt_xel(liquidity)} seed liquidity")
    if liquidity >= cfg["direct_listing_threshold"]:
        print(f"  path        : DIRECT LISTING — liquidity >= threshold "
              f"({crypto.fmt_xel(cfg['direct_listing_threshold'])}): graduates "
              f"the moment validation passes")
    else:
        print(f"  path        : bonding curve (direct listing needs >= "
              f"{crypto.fmt_xel(cfg['direct_listing_threshold'])})")
    if args.vesting > 0:
        print(f"  vesting     : PLAN {args.vesting} topos — the community "
              f"votes on this exact schedule; the contract binds it at "
              f"graduation (D10, irreversible)")
    else:
        print("  vesting     : no plan — team claims at graduation (or may "
              "start a voluntary vesting later)")
    socials = [(n, l) for n, l in (("twitter", args.twitter),
                                   ("telegram", args.telegram),
                                   ("discord", args.discord)) if l]
    if socials:
        print("  socials     : " + "  ".join(
            f"{name}={link}" for name, link in socials))
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    params = propose_params(args.name, args.symbol, args.description,
                            args.website, args.logo, args.twitter,
                            args.telegram, args.discord, total_supply,
                            args.team_bps, args.vesting)
    deposits = propose_deposits(cfg["submission_fee"], cfg["asset_budget"],
                                liquidity,
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


def cmd_launchpad_migrate(args) -> None:
    """Prepare the permissionless migration to LaunchDEX (D15) — atomic:
    curve reserves + inventory -> permanent pool. Needs the wallet's
    contract-call permission on the transaction."""
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    if args.id >= reader.count():
        sys.exit(f"error: project {args.id} does not exist")
    p = reader.project(args.id)
    m = reader.migration_info(args.id)
    if not p['graduated']:
        sys.exit("error: project has not graduated yet")
    if m['migrated']:
        sys.exit("error: already migrated "
                 f"(at topo {m['migrated_at']})")
    if not m['dex_address']:
        sys.exit("error: the admin must pin the DEX address first "
                 "(set_dex_address, chunk 48)")
    xel_out = p['reserves'] or 0
    tok_out = p['curve'] or 0
    print(f"migrate() — chunk {LAUNCHPAD_ENTRY_IDS['migrate']} "
          f"(permissionless, atomic)")
    print(f"  pool seed  : {crypto.fmt_xel(xel_out)} + "
          f"{fmt_token(tok_out)} tokens (team escrow stays on the "
          "launchpad)")
    print(f"  dex        : {m['dex_address']}")
    print("  permission : the transaction MUST carry the contract-call "
          "permission (XSWD 'all' or LaunchDEX allowlist)")
    if p['status_label'] == 'untrusted':
        print("  note       : project is Untrusted — the pool's buys will be "
              "paused in the same transaction (D17)")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHPAD_ENTRY_IDS["migrate"],
                  pid_params(args.id), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — the curve is closed, trading continues on LaunchDEX")


def cmd_launchpad_sync(args) -> None:
    """Prepare the trust sync to the DEX pool (D17): Untrusted -> pool
    buys paused; recovered -> pool buys unpaused. Permissionless keeper."""
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    if args.id >= reader.count():
        sys.exit(f"error: project {args.id} does not exist")
    p = reader.project(args.id)
    m = reader.migration_info(args.id)
    if not m['migrated']:
        sys.exit("error: project has not migrated to the DEX yet")
    flag = p['status_label'] == 'untrusted'
    if bool(p['dex_synced']) == flag:
        sys.exit("note: the pool already mirrors the trust status "
                 "(nothing to sync)")
    print(f"sync_trust_to_dex() — chunk {LAUNCHPAD_ENTRY_IDS['sync_trust_to_dex']}")
    print(f"  action     : {'PAUSE pool buys (project Untrusted)' if flag else 'UNPAUSE pool buys (trust recovered)'}")
    print("  permission : the transaction MUST carry the contract-call permission")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHPAD_ENTRY_IDS["sync_trust_to_dex"],
                  pid_params(args.id), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — the pool mirrors the launchpad trust status")


def cmd_launchpad_claim_deposit(args) -> None:
    """D21: claim YOUR refundable vote deposit for a closed round."""
    contract = _require_contract(args)
    reader = LaunchpadReader(_daemon(args.network), contract)
    if args.id >= reader.count():
        sys.exit(f"error: project {args.id} does not exist")
    print(f"claim_vote_deposit({args.id}, round {args.round}) — chunk "
          f"{LAUNCHPAD_ENTRY_IDS['claim_vote_deposit']}")
    print("  rules     : the round must be CLOSED (a newer round exists, or "
          "the deadline passed)")
    print("  refund    : exactly the amount locked at vote time (read from "
          "YOUR vote slot v:{pid}:{round}:{addr})")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHPAD_ENTRY_IDS["claim_vote_deposit"],
                  claim_vote_deposit_params(args.id, args.round), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — deposit refunded")


def cmd_launchpad_set_vote_deposit(args) -> None:
    """Admin: raise/lower the D21 sybil dial (0 = free voting, cap 10 XEL)."""
    contract = _require_contract(args)
    amount = int(round(args.amount * 1e8))
    if amount > 1_000_000_000:
        sys.exit("error: the dial is capped at 10 XEL (a sybil cost, "
                 "never a participation toll)")
    print(f"set_vote_deposit({amount}) — chunk "
          f"{LAUNCHPAD_ENTRY_IDS['set_vote_deposit']}")
    print(f"  effect    : every FUTURE support()/report() attaches "
          f"{crypto.fmt_xel(amount)} (refundable via claim_vote_deposit)")
    print("  note      : already-locked deposits refund at their own amount")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHPAD_ENTRY_IDS["set_vote_deposit"],
                  set_vote_deposit_params(amount), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — dial updated")


# dex status / pool / quote / swap / add-liquidity / entries
# ---------------------------------------------------------------------------

def cmd_dex_status(args) -> None:
    contract = _require_contract(args)
    reader = DexReader(_daemon(args.network), contract)
    cfg = reader.config()
    print(f"LaunchDEX — {contract[:16]}… ({args.network})")
    print(f"  pools           : {reader.pools_count()}")
    print(f"  emergency       : {'YES — buys frozen, SELLS STAY OPEN (IX6)' if cfg['emergency'] else 'no'}")
    print(f"  swap fee        : {cfg['swap_fee_bps'] / 100:.2f}% on inputs "
          f"(cap 10%) — split {100 - cfg['lp_share_bps'] / 100:.2f}% admin / "
          f"{cfg['lp_share_bps'] / 100:.2f}% providers (X10, dial bounded "
          f"25–75%)")
    print(f"  launchpad pin   : {cfg['launchpad'] or 'NOT SET'} "
          f"({'FROZEN — first pool exists' if cfg['launchpad_pinned'] else 'still settable'})")
    print(f"  trade bounds    : swaps "
          f"{crypto.fmt_xel(cfg['min_swap_xel'])}.."
          f"{crypto.fmt_xel(cfg['max_swap_xel'])} XEL, "
          f"{fmt_token(cfg['min_swap_tokens'])}.."
          f"{fmt_token(cfg['max_swap_tokens'])} tokens")
    print("  liquidity       : SEED PERMANENT (the migration's parts are\n"
          "                    protocol-locked FOREVER, X11 — the anti-rug\n"
          "                    floor), PRICE-NEUTRAL to add (X7), providers may\n"
          "                    EXIT pro-rata ANYTIME (remove_liquidity, X12), and\n"
          "                    it EARNS: every part gets its pro-rata share of\n"
          "                    every fee (claim_lp_fees, X10) — the seed included\n"
          "                    (it accrues to the protocol's own position)")


def cmd_dex_pool(args) -> None:
    contract = _require_contract(args)
    reader = DexReader(_daemon(args.network), contract)
    q = reader.pool(args.asset.lower())
    if q['xel_reserve'] is None:
        sys.exit("error: no pool for this asset")
    print(f"pool {args.asset}")
    print(f"  reserves   : {crypto.fmt_xel(q['xel_reserve'] or 0)} XEL / "
          f"{fmt_token(q['token_reserve'] or 0)} tokens")
    print(f"  price      : {(q['price'] or 0) / 1e8:.8f} XEL/token")
    print(f"  status     : {q['status_label']}")
    print(f"  volume     : buy {crypto.fmt_xel(q['buy_volume'] or 0)} / "
          f"sell {crypto.fmt_xel(q['sell_volume'] or 0)} "
          f"({q['trades'] or 0} trades, last at topo {q['last_trade_topo'] or 0})")
    print(f"  fees       : admin pot {crypto.fmt_xel(q['xel_fees'] or 0)} XEL + "
          f"{fmt_token(q['token_fees'] or 0)} tokens; provider pot "
          f"{crypto.fmt_xel(q['lp_pot_xel'] or 0)} XEL + "
          f"{fmt_token(q['lp_pot_tokens'] or 0)} tokens "
          f"(lifetime fees {crypto.fmt_xel(q['lifetime_fees'] or 0)})")
    depth = q['lp_total_depth'] or 0
    locked = q['lp_locked_depth'] or 0
    share = (q['xel_reserve'] and depth * 100 // q['xel_reserve']) or 0
    print(f"  providers : {q['lp_deposits'] or 0} entries, "
          f"{crypto.fmt_xel(depth)} total depth "
          f"({share}% of the pool's XEL side) — each earns pro-rata of the "
          "LP fee share (X10) and may exit pro-rata anytime (X12)")
    floor_pct = (depth and locked * 100 // depth) or 0
    print(f"  seed floor: {crypto.fmt_xel(locked)} of the depth "
          f"({floor_pct}%) is the migration itself — PROTOCOL-LOCKED "
          "FOREVER, never withdrawable by anyone (X11)")


def cmd_dex_quote(args) -> None:
    """Offline pool calculator — mirrors the LaunchDEX math exactly."""
    x = int(round(args.x_reserve * 1e8))
    y = int(round(args.y_reserve * 1e8))
    if x <= 0 or y <= 0:
        sys.exit("error: --x-reserve and --y-reserve must be positive")
    price = dex_math_spot_price(x, y)
    print(f"pool: {crypto.fmt_xel(x)} XEL / {fmt_token(y)} tokens "
          f"-> price {price / 1e8:.8f} XEL/token")
    if args.buy is not None:
        xel_in = int(round(args.buy * 1e8))
        out = xel_to_tokens_out(x, y, xel_in, args.fee_bps)
        print(f"buy  {crypto.fmt_xel(xel_in)} (fee {args.fee_bps / 100:.2f}%) "
              f"-> {fmt_token(out)} tokens")
    if args.sell is not None:
        tokens = int(round(args.sell * 1e8))
        out = tokens_to_xel_out(x, y, tokens, args.fee_bps)
        print(f"sell {fmt_token(tokens)} tokens "
              f"-> {crypto.fmt_xel(out)} out (fee {args.fee_bps / 100:.2f}%)")


def cmd_dex_entries(args) -> None:
    print("LaunchDEX chunk ids — compiler numbering "
          "(CI-verified; 6/7 are what VaultLaunch cross-calls — D19):")
    for name, eid in sorted(LAUNCHDEX_ENTRY_IDS.items(), key=lambda kv: kv[1]):
        pin = "  <- pinned (launchpad cross-call)" if eid in (6, 7) else ""
        print(f"  {eid:>3}  {name}{pin}")
    print("\nentries-only numbering (probe only):")
    for name, eid in sorted(LAUNCHDEX_ENTRY_IDS_ALT.items(), key=lambda kv: kv[1]):
        print(f"  {eid:>3}  {name}")


def cmd_dex_lp(args) -> None:
    """X10/D23: YOUR provider position in a pool (parts + live earnings)."""
    contract = _require_contract(args)
    reader = DexReader(_daemon(args.network), contract)
    pos = reader.lp_info(args.asset.lower(), args.wallet)
    if not pos["parts"]:
        sys.exit("error: this wallet has no LP parts in this pool "
                 "(add_liquidity to become a provider)")
    print(f"provider position — pool {args.asset[:16]}…")
    print(f"  parts        : {crypto.fmt_xel(pos['parts'])} of the pool's "
          "LP depth (pro-rata of the LP fee share, X10)")
    w = pos.get('withdrawable') or 0
    if w:
        out_x, out_y = dexmod.remove_outs(
            reader._key(dexmod.pool_key(args.asset.lower(),
                                        dexmod.F_XEL_RESERVE), 0) or 0,
            reader._key(dexmod.pool_key(args.asset.lower(),
                                        dexmod.F_TOK_RESERVE), 0) or 0,
            w, reader._key(dexmod.pool_key(args.asset.lower(),
                                           dexmod.F_LP_TOTAL), 0) or 0)
        print(f"  withdrawable : {crypto.fmt_xel(w)} parts — the exit quote "
              f"is {crypto.fmt_xel(out_x)} XEL + {fmt_token(out_y)} tokens "
              "(remove-liquidity, X12)")
    else:
        print("  withdrawable : 0 parts (the protocol's seed position is "
              "fees-only, forever — X11)")
    print(f"  available    : {crypto.fmt_xel(pos['available_xel'])} XEL + "
          f"{fmt_token(pos['available_tokens'])} tokens "
          "(claimable now — claim-lp-fees)")
    print(f"  crystallised : {crypto.fmt_xel(pos['claimable_xel'])} XEL + "
          f"{fmt_token(pos['claimable_tokens'])} tokens "
          "(rest = accrued since your last touch)")


def cmd_dex_claim_lp_fees(args) -> None:
    """X10/D23: claim YOUR accrued provider fees (pull, both sides)."""
    contract = _require_contract(args)
    asset = args.asset.lower()
    reader = DexReader(_daemon(args.network), contract)
    print(f"claim_lp_fees({asset[:16]}…) — chunk "
          f"{LAUNCHDEX_ENTRY_IDS['claim_lp_fees']}")
    print("  rules     : pays YOUR own accrued fees only (keys embed your "
          "address); principal untouchable (no remove_liquidity)")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    pos = reader.lp_info(asset, w.address())
    if not pos["parts"]:
        sys.exit("error: this wallet has no LP parts in this pool")
    print(f"  available : {crypto.fmt_xel(pos['available_xel'])} XEL + "
          f"{fmt_token(pos['available_tokens'])} tokens")
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHDEX_ENTRY_IDS["claim_lp_fees"],
                  claim_lp_fees_params(asset), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — provider fees paid out")


def cmd_dex_remove_liquidity(args) -> None:
    """X12 (v1.3): burn YOUR withdrawable parts for their exact pro-rata
    share of both reserves at the current ratio."""
    contract = _require_contract(args)
    asset = args.asset.lower()
    reader = DexReader(_daemon(args.network), contract)
    print(f"remove_liquidity({asset[:16]}…, {args.parts}) — chunk "
          f"{LAUNCHDEX_ENTRY_IDS['remove_liquidity']}")
    print("  rules     : burns YOUR OWN withdrawable parts only (the "
          "migration's seed is protocol-locked FOREVER, X11); payout = "
          "exact floored pro-rata of BOTH reserves at the current ratio; "
          "NO gate — works under any pause (X12)")
    wallet_addr = args.wallet or (_wallet(args).address() if args.broadcast else None)
    if wallet_addr:
        pos = reader.lp_info(asset, wallet_addr)
        w = pos.get('withdrawable') or 0
        if not w:
            sys.exit("error: this wallet has no WITHDRAWABLE parts in this "
                     "pool (the seed position is fees-only — X11)")
        if args.parts > w:
            sys.exit(f"error: you only hold {w} withdrawable parts "
                     f"(asked {args.parts}) — the rest is locked forever")
        x = reader._key(dexmod.pool_key(asset, dexmod.F_XEL_RESERVE), 0) or 0
        y = reader._key(dexmod.pool_key(asset, dexmod.F_TOK_RESERVE), 0) or 0
        tl = reader._key(dexmod.pool_key(asset, dexmod.F_LP_TOTAL), 0) or 0
        out_x, out_y = dexmod.remove_outs(x, y, args.parts, tl)
        print(f"  quote     : burn {args.parts} parts -> "
              f"{crypto.fmt_xel(out_x)} XEL + {fmt_token(out_y)} tokens")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    if not args.wallet:
        pos = reader.lp_info(asset, w.address())
        if args.parts > (pos.get('withdrawable') or 0):
            sys.exit("error: not enough withdrawable parts (\"locked\")")
    min_x = int(round(args.min_xel_out * 1e8)) if args.min_xel_out is not None else 0
    min_t = int(round(args.min_tokens_out * 1e8)) if args.min_tokens_out is not None else 0
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHDEX_ENTRY_IDS["remove_liquidity"],
                  dexmod.remove_liquidity_params(asset, args.parts, min_x, min_t),
                  deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — pro-rata payout sent; accrued fees preserved "
          "(claim them with claim-lp-fees)")


def cmd_dex_set_fee_split(args) -> None:
    """Admin: set the admin/providers fee split (X10, bounded 25–75%)."""
    contract = _require_contract(args)
    lp_bps = int(round(args.percent * 100))
    if not (dexmod.MIN_LP_SHARE_BPS <= lp_bps <= dexmod.MAX_LP_SHARE_BPS):
        sys.exit(f"error: the LP share is hard-bounded "
                 f"{dexmod.MIN_LP_SHARE_BPS / 100:.0f}%–"
                 f"{dexmod.MAX_LP_SHARE_BPS / 100:.0f}% "
                 "(providers can never be cut to zero, treasury can never "
                 "be starved)")
    print(f"set_fee_split({lp_bps}) — chunk "
          f"{LAUNCHDEX_ENTRY_IDS['set_fee_split']}")
    print(f"  effect    : every FUTURE fee splits "
          f"{100 - args.percent}% admin / {args.percent}% providers")
    print("  note      : accrued claimables keep their recorded amounts")
    if not args.broadcast:
        print("dry-run (pass --broadcast to send via the local wallet)")
        return
    w = _wallet(args)
    before = w.nonce()
    tx = w.invoke(contract, LAUNCHDEX_ENTRY_IDS["set_fee_split"],
                  set_fee_split_params(lp_bps), deposits={})
    print(f"broadcast: {tx}")
    w.wait_nonce_advance(before)
    print("confirmed — split updated")


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
    sp.add_argument("--twitter", default="", help="Twitter/X link (D11, updatable anytime)")
    sp.add_argument("--telegram", default="", help="Telegram link (D11, updatable anytime)")
    sp.add_argument("--discord", default="", help="Discord invite (D11, updatable anytime)")
    sp.add_argument("--supply", type=float, required=True,
                    help="total supply in whole tokens (1..100M)")
    sp.add_argument("--team-bps", type=int, default=1000,
                    help="team allocation in bps, max 2000 (default: 10%%)")
    sp.add_argument("--liquidity", type=float, required=True,
                    help="seed liquidity in XEL (>= min_liquidity)")
    sp.add_argument("--vesting", type=int, default=0,
                    help="vesting PLAN in topos (D10): 0 = claim at "
                         "graduation, else within [vesting_min, vesting_max] "
                         "- the contract binds it at graduation")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_launchpad_propose)

    sp = ls.add_parser("entries")
    sp.set_defaults(func=cmd_launchpad_entries, need_contract=False)

    sp = ls.add_parser("migrate"); common(sp)
    sp.add_argument("--id", type=int, required=True, help="project id")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_launchpad_migrate)

    sp = ls.add_parser("sync"); common(sp)
    sp.add_argument("--id", type=int, required=True, help="project id")
    sp.add_argument("--broadcast", action="store_true")
    sp.set_defaults(func=cmd_launchpad_sync)

    sp = ls.add_parser("claim-deposit"); common(sp)
    sp.add_argument("--id", type=int, required=True, help="project id")
    sp.add_argument("--round", type=int, default=0,
                    help="the voting round you locked the deposit in "
                         "(default: 0)")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_launchpad_claim_deposit)

    sp = ls.add_parser("set-vote-deposit"); common(sp)
    sp.add_argument("--amount", type=float, required=True,
                    help="deposit per vote in XEL (0 = free voting, "
                         "max 10)")
    sp.add_argument("--broadcast", action="store_true",
                    help="send via local wallet (default: prepare only)")
    sp.set_defaults(func=cmd_launchpad_set_vote_deposit)

    dx = sub.add_parser("dex", help="LaunchDEX operations")
    ds = dx.add_subparsers(dest="dex_cmd", required=True)

    sp = ds.add_parser("status"); common(sp)
    sp.set_defaults(func=cmd_dex_status)

    sp = ds.add_parser("pool"); common(sp)
    sp.add_argument("--asset", required=True,
                    help="asset hash (64 hex) of the pool's token")
    sp.set_defaults(func=cmd_dex_pool)

    sp = ds.add_parser("quote")
    sp.add_argument("--x-reserve", type=float, required=True,
                    help="pool XEL reserves")
    sp.add_argument("--y-reserve", type=float, required=True,
                    help="pool token reserves")
    sp.add_argument("--buy", type=float, help="XEL amount to quote a buy")
    sp.add_argument("--sell", type=float, help="token amount to quote a sell")
    sp.add_argument("--fee-bps", type=int,
                    default=dexmod.DEFAULTS["swap_fee_bps"],
                    help="swap fee in bps (default: %(default)s)")
    sp.set_defaults(func=cmd_dex_quote, need_contract=False)

    sp = ds.add_parser("entries")
    sp.set_defaults(func=cmd_dex_entries, need_contract=False)

    sp = ds.add_parser("lp"); common(sp)
    sp.add_argument("--asset", required=True,
                    help="asset hash (64 hex) of the pool's token")
    sp.add_argument("--wallet", required=True,
                    help="the PROVIDER's address (read-only view)")
    sp.set_defaults(func=cmd_dex_lp)

    sp = ds.add_parser("claim-lp-fees"); common(sp)
    sp.add_argument("--asset", required=True,
                    help="asset hash (64 hex) of the pool's token")
    sp.add_argument("--broadcast", action="store_true",
                    help="send the transaction (default: dry-run)")
    sp.set_defaults(func=cmd_dex_claim_lp_fees)

    sp = ds.add_parser("remove-liquidity"); common(sp)
    sp.add_argument("--asset", required=True,
                    help="asset hash (64 hex) of the pool's token")
    sp.add_argument("--parts", type=int, required=True,
                    help="atomic parts to burn (see: dex lp)")
    sp.add_argument("--wallet", help="quote THIS wallet's position "
                    "(default: the local wallet)")
    sp.add_argument("--min-xel-out", type=float,
                    help="slippage floor on the XEL side (XEL)")
    sp.add_argument("--min-tokens-out", type=float,
                    help="slippage floor on the token side (whole tokens)")
    sp.add_argument("--broadcast", action="store_true",
                    help="send the transaction (default: dry-run)")
    sp.set_defaults(func=cmd_dex_remove_liquidity)

    sp = ds.add_parser("set-fee-split"); common(sp)
    sp.add_argument("--percent", type=float, required=True,
                    help="LP share of every fee, in %% (25–75)")
    sp.add_argument("--broadcast", action="store_true",
                    help="send the transaction (default: dry-run)")
    sp.set_defaults(func=cmd_dex_set_fee_split)

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
