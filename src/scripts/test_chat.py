#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — VaultChat E2E + relayer economics (test_chat.py)
===========================================================================
Covers the flows left out of test_flows.py:
  1. register_session (admin + provider1)
  2. create_group / add_group_member
  3. store_group_message (member-posted)
  4. anchor_messages (admin-authorized)
  5. Relayer: stake_relayer_bond -> set_relayer (admin) ->
     register_as_relayer -> set_relayer_fee -> claim_relayer_fees
  6. On-chain state read-backs

Usage:
  python3 scripts/test_chat.py
===========================================================================
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import Protocol, VLT_ASSET, val_u64, val_u8, val_str, \
    val_addr, val_bool, val_bytes, val_hash

WALLET_URL = "http://127.0.0.1:18082/json_rpc"
AUTH = ("wallet", "testpass")
P1_URL = "http://127.0.0.1:18086/json_rpc"
P2_URL = "http://127.0.0.1:18087/json_rpc"

PASS, FAIL = 0, 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label} {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


def run(p: Protocol, chat_h: str, label: str, entry: int, params=None,
        deposits=None, expect_error=None, tolerate=()):
    transient = ("proof verification", "already used", "nonce")
    for attempt in range(4):
        before = p.wallet._call("get_nonce")
        try:
            tx = p.invoke_hash(chat_h, entry, params, deposits=deposits)
            p.confirm(tx, "")
            err = p.revert_reason(tx)
            if err is None:
                p.wallet.wait_nonce_advance(int(before))
            if expect_error:
                ok = err is not None and expect_error.lower() in str(err).lower()
                return ok, f"(expected {expect_error!r}, got {err!r})"
            if err and any(t in str(err).lower() for t in tolerate):
                return True, f"(tolerated {err})"
            return (err is None), f"tx={tx[:12]}" + (f" error={err}" if err else "")
        except Exception as e:
            msg = str(e)
            if attempt < 3 and any(t in msg.lower() for t in transient):
                time.sleep(15)
                continue
            return False, f"exception: {msg[:160]}"
    return False, "unreachable"


def main() -> None:
    admin_p = Protocol(wallet_url=WALLET_URL, wallet_auth=AUTH)
    p1 = Protocol(wallet_url=P1_URL, wallet_auth=AUTH)
    p2 = Protocol(wallet_url=P2_URL, wallet_auth=AUTH)

    admin = admin_p.wallet.address()
    addr1 = p1.wallet.address()
    addr2 = p2.wallet.address()
    chat = admin_p.resolve("VaultChat")
    print(f"admin : {admin}\np1    : {addr1}\np2    : {addr2}\nchat  : {chat}")

    for pw in (p1, p2):
        try:
            pw.wallet.track_asset(VLT_ASSET)
        except Exception:
            pass
    time.sleep(2)

    # -- preflight: p2 must be able to pay the 50 VLT bond + XEL gas --
    need_vlt = 60 * 10 ** 8
    bal2 = p2.wallet.balance(VLT_ASSET)
    if bal2 < need_vlt:
        top = need_vlt - bal2 + 10 ** 8          # marge 1 VLT
        tx = admin_p.wallet.transfer(addr2, top, VLT_ASSET)
        admin_p.confirm(tx, "")
        print(f"  top-up p2: +{top / 10 ** 8:.0f} VLT (maturity ~70 blocks)…")
        time.sleep(70 * 2.7)
    balx = p2.wallet.balance()
    if balx < 10 ** 7:                            # < 0.1 XEL
        tx = admin_p.wallet.transfer(addr2, 5 * 10 ** 7)
        admin_p.confirm(tx, "")
        print("  top-up p2: +0.5 XEL (gaz)")
        time.sleep(30)

    # ------------------------------------------------ sessions --
    print("\n=== 1. Sessions ===")
    ok, d = run(admin_p, chat, "register_session admin", 7, [val_hash("11" * 32)])
    report("register_session admin", ok or "exists" in d, d)
    ok, d = run(p1, chat, "register_session p1", 7, [val_hash("12" * 32)])
    report("register_session p1", ok or "exists" in d, d)
    time.sleep(3)

    s_admin = admin_p.read_contract(chat, f"session_{admin}") is not None
    s_p1 = admin_p.read_contract(chat, f"session_{addr1}") is not None
    report("state session_admin", s_admin)
    report("state session_p1", s_p1)

    # ------------------------------------------------ groups --
    print("\n=== 2. Groups ===")
    gc_before = admin_p.read_contract(chat, "gc")
    gid = int(gc_before) if gc_before is not None else 0
    ok, d = run(admin_p, chat, "create_group", 8, [val_hash("33" * 32)])
    report(f"create_group (id {gid})", ok, d)
    time.sleep(3)
    gc_after = admin_p.read_contract(chat, "gc")
    report("groups_count incremented", gc_after == gid + 1,
           f"gc={gc_after}")

    ok, d = run(admin_p, chat, "add_group_member p1", 9,
                [val_u64(gid), val_addr(addr1), val_bytes("ab" * 16)])
    report("add_group_member p1", ok, d)
    time.sleep(3)
    member = admin_p.read_contract(chat, f"gm_{gid}_{addr1}")
    report("state gm stored true", member is True, f"={member}")

    ok, d = run(p1, chat, "store_group_message (p1)", 48,
                [val_u64(gid), val_bytes("de" * 32), val_u64(int(time.time()))])
    report("store_group_message", ok, d)

    # ------------------------------------------------ anchoring --
    print("\n=== 3. Anchoring ===")
    ok, d = run(admin_p, chat, "anchor_messages", 11,
                [val_hash("44" * 32), val_u64(5), val_u64(2), val_u8(0)],
                tolerate=("ratelimit",))
    report("anchor_messages admin", ok, d)

    # ------------------------------------------------ relayer economics --
    print("\n=== 4. Relayer (p2) ===")
    bond = 50 * 10 ** 8                       # MIN_RELAYER_BOND = 50 VLT
    deps = {VLT_ASSET: {"amount": bond}}
    ok, d = run(p2, chat, "stake_relayer_bond 50 VLT", 121,
                [val_u64(bond)], deposits=deps)
    report("stake_relayer_bond", ok, d)
    time.sleep(3)

    ok, d = run(admin_p, chat, "set_relayer(p2, true)", 20,
                [val_addr(addr2), val_bool(True)])
    report("set_relayer enabled", ok, d)
    time.sleep(3)

    ok, d = run(p2, chat, "register_as_relayer", 66,
                [val_str("https://relayer2.vaultchat.test"), val_u64(10), val_u64(5)])
    report("register_as_relayer", ok, d)
    time.sleep(3)

    ok, d = run(p2, chat, "set_relayer_fee", 51, [val_u64(1000), val_u8(0)])
    report("set_relayer_fee", ok, d)
    time.sleep(3)

    ok, d = run(p2, chat, "claim_relayer_fees (zero)", 56,
                tolerate=("rfail", "zero", "nofee"))
    report("claim_relayer_fees", ok, d)

    rel = admin_p.read_contract(chat, f"relayer_{addr2}")
    report("state relayer_ true", rel is True, f"={rel}")

    ok, d = run(p1, chat, "set_relayer_fee as NON-relayer", 51,
                [val_u64(1000), val_u8(0)], expect_error="notrelayer")
    report("fee blocked for non-relayer", ok, d)

    print("\n" + "=" * 52)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
