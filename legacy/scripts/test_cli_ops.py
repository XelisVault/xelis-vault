#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — CLI write-path E2E (test_cli_ops.py)
===========================================================================
Drives the SAME Backend methods the xvault TUI screens use, with real
transactions, and verifies on-chain outcome (confirm + revert_reason) for
each. Read path = public node (remote mode), wallet = local RPC.

Covers: PSM mint/redeem, Vault deposit/borrow/repay/withdraw, AMM swap,
Savings deposit/withdraw, Mixer deposits (auto-mix), Faucet distribute,
Miner heartbeat.

Usage: python3 scripts/test_cli_ops.py
===========================================================================
"""
from __future__ import annotations

import sys
import time
import secrets
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_backend
from cli_backend import Backend, OpResult
from protocol import Protocol

PUBLIC = "https://testnet-node.xelis.io"
WALLET_URL = "http://127.0.0.1:18082/json_rpc"
AUTH = ("wallet", "testpass")

PASS, FAIL = 0, 0


def report(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label} {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


def settle(b: Backend, tx: str, label: str, timeout=150) -> bool:
    """Confirm tx on the wallet's OWN daemon and assert no contract revert."""
    p = b.extra  # Protocol instance attached below (daemon = wallet daemon)
    try:
        p.confirm(tx, "")
    except TimeoutError:
        report(label, False, "timeout waiting for confirmation")
        return False
    err = p.revert_reason(tx)
    if err is None:
        report(label, True, f"tx={tx[:12]}")
        return True
    report(label, False, f"revert={err}")
    return False


def run_op(b: Backend, label: str, fn, *args, **kw) -> bool:
    res: OpResult = fn(*args, **kw)
    if not res.ok:
        report(label, False, f"reason={res.reason}")
        return False
    return settle(b, res.tx, label)


def main():
    cfg_data = {
        "rpc_url": PUBLIC,                       # remote mode: reads via public node
        "wallet_url": WALLET_URL,
        "wallet_user": AUTH[0], "wallet_pass": AUTH[1],
    }
    b = Backend(cfg_data)
    # attach a Protocol for confirm/revert checks — pointed at the SAME daemon
    # the wallet broadcasts to (local), not the public read node.
    b.extra = Protocol(wallet_url=WALLET_URL, wallet_auth=AUTH,
                       daemon_url="http://127.0.0.1:18081/json_rpc")

    print(f"address : {b.address}")
    print(f"topo    : {b.topo():,}   price XEL/USD: {b.price_usd()}")
    xel_bal = b.wallet.balance()
    print(f"balances: {xel_bal/1e8:.2f} XEL")

    n_vaults_before = len(b.my_vaults())

    # ------------------------------------------------ PSM mint + Vault open --
    print("\n=== A. PSM mint / Vault deposit+borrow ===")
    run_op(b, "psm_mint 1 XEL", b.psm_mint, int(1 * 1e8))
    ok = run_op(b, "vault_deposit 5 XEL", b.vault_deposit, int(5 * 1e8))
    vid = None
    deadline = time.time() + 150      # public-node propagation can lag blocks
    while time.time() < deadline:
        vaults = b.my_vaults()
        fresh = [v for v in vaults if len(vaults) > n_vaults_before]
        if len(vaults) > n_vaults_before:
            vid = sorted(v["id"] for v in vaults)[-1]
            break
        time.sleep(10)
    report("vault created", vid is not None,
           f"id={vid} (n_vaults polling {int(150-(deadline-time.time()))}s)")

    if vid:
        collat_usd = 5 * (b.price_usd() or 0.19)
        borrow = int(collat_usd * 0.40 * 1e8)      # 40% LTV — safe HF ~2.5
        run_op(b, f"vault_borrow {borrow/1e8:.4f} xUSD (id {vid})",
               b.vault_borrow, vid, borrow)
        debt = borrow

        # ------------------------------------------- mixer (v2 note+withdraw) --
        print("\n=== B. PrivacyMixer v2 (private note + shared pool) ===")
        secret = secrets.token_bytes(32).hex()
        ok = run_op(b, "mixer_deposit 0.02 XEL (note)",
                    b.mixer_deposit, b.xel_asset, int(0.02 * 1e8), secret)
        nb = b.mixer_note_balance(b.xel_asset, secret)
        report("note balance stored", nb == int(0.02 * 1e8) - int(0.02 * 1e8) * 1 // 10000,
               f"nb={nb}")
        time.sleep(4)
        ok = run_op(b, "mixer_withdraw to self (destroy note)",
                    b.mixer_withdraw, b.address, b.xel_asset, nb, secret)
        nb2 = b.mixer_note_balance(b.xel_asset, secret)
        report("note spent after withdraw", nb2 in (None, 0),
               f"nb2={nb2}")

        # ----------------------------------------------------- faucet/hb --
        print("\n=== C. Faucet + heartbeat ===")
        res = b.miner_heartbeat()
        if res.ok:
            ok = settle(b, res.tx, "miner_heartbeat")
            if ok:
                pass
        elif "toosoon" in (res.reason or ""):
            report("miner_heartbeat", True,
                   "(toosoon = interval 900 blk, comportement attendu)")
        else:
            report("miner_heartbeat", False, f"reason={res.reason}")
        res = b.faucet_distribute([b.address])
        if res.ok:
            settle(b, res.tx, "faucet_distribute([self])")
        elif "cooldown" in (res.reason or ""):
            report("faucet_distribute([self])", True,
                   "(cooldown = anti-spam, comportement attendu)")
        else:
            report("faucet_distribute([self])", False, f"reason={res.reason}")

        # ------------------------------- wait xUSD UTXO maturity (~70 blk) --
        target = b.topo() + 70
        print(f"\nwaiting until topo {target} for xUSD maturity ", end="", flush=True)
        while b.topo() < target:
            time.sleep(10)
            print(".", end="", flush=True)
        print()

        # ------------------------------------------------- xUSD consumers --
        print("\n=== D. Redeem / Swap / Savings / Repay+Withdraw ===")
        xusd = b.wallet.balance(b.xusd_asset)
        report("xUSD received (mint+borrow)", xusd >= debt,
               f"{xusd/1e8:.4f} xUSD")

        run_op(b, "psm_redeem 0.05 xUSD", b.psm_redeem, int(0.05 * 1e8))
        run_op(b, "amm_swap 0.005 xUSD->XEL", b.amm_swap, b.xusd_asset,
               b.xel_asset, int(0.005 * 1e8), 1)
        run_op(b, "savings_deposit 0.05 xUSD", b.savings_deposit, int(0.05 * 1e8))
        run_op(b, "savings_withdraw 0.05 xUSD", b.savings_withdraw, int(0.05 * 1e8))
        if xusd >= debt:
            run_op(b, f"vault_repay full ({debt/1e8:.4f})", b.vault_repay, vid, debt)
            time.sleep(6)
            run_op(b, "vault_withdraw 1 XEL", b.vault_withdraw, vid, int(1 * 1e8))

    print("\n" + "=" * 52)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
