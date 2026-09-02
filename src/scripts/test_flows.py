#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Flow tests (test_flows.py)
============================================================================
Exercises every protocol flow against the live testnet and reports
pass/fail with the revert reason when a flow fails.

Flows:
  1. PSM      mint XEL -> xUSD / redeem xUSD -> XEL (oracle-priced 1:1)
  2. Vault    deposit XEL collateral -> borrow xUSD -> repay -> withdraw
  3. Swap     create pool, add liquidity, swap (AMM + psm helpers)
  4. Governance  stake VLT / unstake / claim rewards
  5. Mixer    deposit
  6. Insurance  stake / unstake
  7. Vesting  claim (expect locked)
  8. Delegation  register profile / delegate / undelegate
  9. Savings  deposit / withdraw
  10. Chat    register session / anchor
  11. Faucet  distribute

Usage:
  python3 scripts/test_flows.py [--wallet-rpc URL] [--verbose]
============================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import (Protocol, VLT_ASSET, XEL_ASSET, XUSD_ASSET, ADMIN,
                     oracle_feed_info, oracle_active_providers,
                     psm_mint, psm_redeem,
                     vault_deposit, vault_borrow, vault_repay, vault_withdraw,
                     vault_total,
                     swap_create_pool, swap_add_liquidity, swap_swap,
                     swap_psm_mint, swap_psm_redeem, swap_pools_count,
                     gov_stake, gov_unstake, gov_claim_rewards, gov_stakes_count,
                     mixer_deposit, mixer_withdraw,
                     insurance_stake, insurance_unstake,
                     vesting_claim,
                     delegation_register_profile, delegation_delegate,
                     delegation_undelegate,
                     savings_deposit, savings_withdraw,
                     chat_register_session, chat_anchor_messages,
                     faucet_distribute, FEED_XEL_USD)

WALLET_URL = "http://127.0.0.1:18082/json_rpc"
AUTH = ("wallet", "testpass")

PASS, FAIL = 0, 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label} {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


def run(p: Protocol, label: str, fn, *args, expect_error: str | None = None) -> tuple[bool, str]:
    transient = ("proof verification", "already used", "nonce")
    for attempt in range(4):
        before = p.wallet._call("get_nonce")
        try:
            tx = fn(*args)
            p.confirm(tx, "")
            err = p.revert_reason(tx)
            if err is None:
                p.wallet.wait_nonce_advance(int(before))
            if expect_error:
                ok = err is not None and expect_error.lower() in str(err).lower()
                return ok, f"(expected {expect_error!r}, got {err!r})"
            ok = err is None
            return ok, f"tx={tx[:12]}" + (f" error={err}" if err else "")
        except Exception as e:
            msg = str(e)
            if attempt < 3 and any(t in msg.lower() for t in transient):
                time.sleep(15)
                continue
            return False, f"exception: {e}"
    return False, "unreachable"


def main() -> None:
    parser = argparse.ArgumentParser(description="XELIS Vault flow tests")
    parser.add_argument("--wallet-rpc", default=WALLET_URL)
    parser.add_argument("--user", default=AUTH[0])
    parser.add_argument("--password", default=AUTH[1])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    p = Protocol(wallet_url=args.wallet_rpc,
                 wallet_auth=(args.user, args.password))
    admin = p.wallet.address()
    print(f"wallet: {admin}")
    print(f"XEL: {p.balance() / 1e8:.4f}  VLT: {p.balance(VLT_ASSET) / 1e8:.4f}  "
          f"xUSD: {p.balance(XUSD_ASSET) / 1e8:.4f}")
    p.wallet.track_asset(XUSD_ASSET)
    time.sleep(2)

    feed = oracle_feed_info(p, FEED_XEL_USD)
    price = feed.get("agg_price")
    print(f"oracle XEL/USD: {price / 1e8 if price else None}  "
          f"sources={feed.get('agg_sources')}  providers={oracle_active_providers(p)}")
    if not price:
        print("ERROR: no aggregated oracle price — aborting price-dependent tests")
        sys.exit(1)

    # ---------------------------------------------------------------- PSM --
    print("\n=== 1. PSM (oracle-priced XEL <-> xUSD) ===")
    xel_in = 5 * 10 ** 8            # 5 XEL
    xusd_expected = xel_in * price // 10 ** 8
    min_out = int(xusd_expected * 0.95)
    ok, d = run(p, "psm_mint 5 XEL", psm_mint, p, xel_in, min_out)
    report("psm_mint", ok, d)
    time.sleep(180)   # let minted xUSD UTXOs become spendable (need ~60+ blocks)
    xusd_now = p.balance(XUSD_ASSET)
    report(f"xUSD balance after mint (>= {min_out})", xusd_now >= min_out,
           f"got {xusd_now / 1e8:.4f} xUSD")
    if xusd_now > 0:
        # redeem only 0.9 xUSD worth to not exceed PSM reserve
        redeem_amt = min(9 * 10**8, xusd_now)  # max 0.9 xUSD
        min_xel = int(redeem_amt * 10 ** 8 // price * 0.95) if price else 1
        ok, d = run(p, "psm_redeem", psm_redeem, p, redeem_amt, max(min_xel, 1))
        report("psm_redeem", ok, d)
        time.sleep(30)

    # -------------------------------------------------------------- Vault --
    print("\n=== 2. VaultEngine (XEL collateral -> xUSD debt) ===")
    n_before = vault_total(p)
    collat = 10 * 10 ** 8           # 10 XEL
    ok, d = run(p, "vault_deposit 10 XEL", vault_deposit, p, collat, "0" * 64)
    report("vault_deposit", ok, d)
    time.sleep(2)
    n_after = vault_total(p)
    vault_id = n_after - 1
    report(f"vault created (id {vault_id})", n_after > n_before)
    if n_after > n_before:
        borrow = int(collat * price // 10 ** 8 * 45 // 100)   # 45% LTV (margin for health factor)
        borrow = max(borrow, 1000)
        ok, d = run(p, "vault_borrow", vault_borrow, p, vault_id, borrow)
        report("vault_borrow", ok, d)
        time.sleep(180)   # let minted xUSD UTXOs become spendable (need ~60+ blocks)
        xusd2 = p.balance(XUSD_ASSET)
        if xusd2 > 0:
            # repay exactly the borrowed amount
            ok, d = run(p, "vault_repay", vault_repay, p, vault_id, borrow)
            report("vault_repay", ok, d)
            time.sleep(30)
        # withdraw small amount (10%) to keep vault healthy
        ok, d = run(p, "vault_withdraw", vault_withdraw, p, vault_id, collat // 10)
        report("vault_withdraw", ok, d)

    # --------------------------------------------------------------- Swap --
    print("\n=== 3. VaultSwap (AMM) ===")
    pc = swap_pools_count(p)
    ok, d = run(p, "swap_create_pool XEL/xUSD", swap_create_pool, p, XEL_ASSET, XUSD_ASSET)
    report("swap_create_pool", ok or "error=exists" in d, d)
    time.sleep(2)
    if swap_pools_count(p) > pc:
        amt_a = 2 * 10 ** 8
        amt_b = int(amt_a * price // 10 ** 8)
        amt_b = max(amt_b, 1000)
        ok, d = run(p, "swap_add_liquidity", swap_add_liquidity, p,
                    XEL_ASSET, XUSD_ASSET, amt_a, amt_b)
        report("swap_add_liquidity", ok, d)
        time.sleep(2)
        if p.balance(XUSD_ASSET) > 0:
            amt_in = int(p.balance(XUSD_ASSET) * 0.5)
            ok, d = run(p, "swap_swap xUSD->XEL", swap_swap, p,
                        XUSD_ASSET, XEL_ASSET, amt_in, 1)
            report("swap_swap", ok, d)

    # -------------------------------------------------------- Governance --
    print("\n=== 4. GovernanceVault (VLT staking) ===")
    vlt_avail = p.balance(VLT_ASSET)
    stake = min(100 * 10 ** 8, vlt_avail)      # 100 VLT
    if stake >= 10 ** 8:
        stake_id = gov_stakes_count(p)   # id of the stake we are about to create
        ok, d = run(p, "gov_stake 100 VLT", gov_stake, p, stake, 7)
        report("gov_stake", ok, d)
        time.sleep(2)
        ok, d = run(p, "gov_claim_rewards", gov_claim_rewards, p)
        report("gov_claim_rewards", ok, d)
        ok, d = run(p, "gov_unstake (expect locked)", gov_unstake, p, stake_id,
                    expect_error="locked")
        report("gov_unstake", ok, d)

    # ------------------------------------------------------------- Mixer --
    print("\n=== 5. PrivacyMixer v2 ===")
    secret = __import__("secrets").token_bytes(32).hex()
    ok, d = run(p, "mixer_deposit", mixer_deposit, p, XEL_ASSET, 1_000_000, secret)
    report("mixer_deposit", ok, d)
    ok, d = run(p, "mixer_withdraw", mixer_withdraw, p, admin, XEL_ASSET, 1_000_000, secret)
    report("mixer_withdraw", ok, d)

    # ---------------------------------------------------------- Insurance --
    print("\n=== 6. InsurancePool ===")
    time.sleep(30)   # let xUSD mature before insurance
    xusd_avail = p.balance(XUSD_ASSET)
    amt = min(10 * 10 ** 8, xusd_avail)
    if amt > 0:
        ok, d = run(p, "insurance_stake", insurance_stake, p, amt)
        report("insurance_stake", ok, d)
        time.sleep(10)
        ok, d = run(p, "insurance_unstake", insurance_unstake, p, amt)
        report("insurance_unstake", ok, d)
    else:
        print("  [SKIP] insurance — no xUSD available")

    # ------------------------------------------------------------ Vesting --
    print("\n=== 7. FounderVesting (claim expected cliffnotpassed) ===")
    ok, d = run(p, "vesting_claim 4y (cliff?)", vesting_claim, p, "FounderVesting4y",
                expect_error="cliffnotpassed")
    report("vesting_claim 4y", ok, d)

    # --------------------------------------------------------- Delegation --
    print("\n=== 8. MinerDelegation ===")
    ok, d = run(p, "delegation register profile (admin)", delegation_register_profile,
                p, "Test Miner", "flow test", 500)
    report("delegation_register_profile", ok, d)
    time.sleep(2)
    # Provider1 must have a miner profile: register it from provider1's wallet
    p1 = Protocol(wallet_url="http://127.0.0.1:18084/json_rpc",
                  wallet_auth=("wallet", "testpass"))
    p1.wallet.track_asset(VLT_ASSET)
    ok, d = run(p1, "delegation register profile (provider1)",
                delegation_register_profile, p1, "Provider1 Miner", "flow test", 500)
    report("delegation_register_profile p1", ok, d)
    time.sleep(2)
    vlt2 = p.balance(VLT_ASSET)
    d_amt = min(50 * 10 ** 8, vlt2)
    if d_amt > 0:
        ok, d = run(p, "delegation delegate 50 VLT", delegation_delegate,
                    p, "xet:REPLACE_WITH_TEST_MINER_ADDRESS",
                    d_amt, False)
        report("delegation_delegate", ok, d)
        time.sleep(2)
        ok, d = run(p, "delegation undelegate", delegation_undelegate, p, d_amt)
        report("delegation_undelegate", ok, d)

    # ------------------------------------------------------------ Savings --
    print("\n=== 9. SavingsRate ===")
    time.sleep(30)   # let xUSD mature
    xusd3 = p.balance(XUSD_ASSET)
    s_amt = min(2 * 10 ** 8, xusd3)  # smaller amount
    if s_amt > 0:
        ok, d = run(p, "savings_deposit", savings_deposit, p, s_amt)
        report("savings_deposit", ok, d)
        time.sleep(5)
        ok, d = run(p, "savings_withdraw", savings_withdraw, p, s_amt)
        report("savings_withdraw", ok, d)
    else:
        print("  [SKIP] savings — no xUSD available")

    # --------------------------------------------------------------- Chat --
    print("\n=== 10. VaultChat ===")
    pubkey = "11" * 32
    ok, d = run(p, "chat_register_session", chat_register_session, p, pubkey)
    report("chat_register_session", ok, d)
    time.sleep(2)
    merkle = "22" * 32
    ok, d = run(p, "chat_anchor_messages", chat_anchor_messages, p, merkle, 3, 1, 0)
    report("chat_anchor_messages", ok or "ratelimit" in d, d)

    # ------------------------------------------------------------- Faucet --
    print("\n=== 11. FaucetContract ===")
    ok, d = run(p, "faucet_distribute", faucet_distribute, p, [admin])
    report("faucet_distribute", ok, d)

    print("\n" + "=" * 50)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()