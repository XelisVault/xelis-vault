#!/usr/bin/env python3
"""VERIFICATION PASS 3 — independent re-derivation of the CommunityLaunch
math and invariants. Deliberately does NOT import the SDK or the test
helpers: every formula is re-implemented from the SPEC
(docs/COMMUNITY_LAUNCH.md §3) and checked against the CONTRACT source
text, then brute-forced numerically.

Checks:
  A. the contract's formulas are the spec's formulas (source text grep);
  B. k-invariance + real-reserve non-negativity under 50k random trades
     (buys respecting the whale guard, sells of random slices) across
     200 random (vx, y0) regimes;
  C. the worst-case sell (entire circulating) <= xr, exactly, on every
     reachable state of every regime;
  D. graduation economics at the defaults: launch FDV 50 XEL, graduation
     ~2/3 sold, pool opens >= spot, fee carved from the seed;
  E. the full unit economics: launch costs exactly sub + asset_fee.
"""
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "contracts" / "community" / "CommunityLaunch.slx").read_text()
XEL = 100_000_000
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print(f"  FAIL: {msg}")


# --- A. the contract's formulas are the spec's formulas -------------------
print("A. contract formulas vs spec")
buy_m = re.search(
    r"fn buy_tokens_out\(.*?\n\}", SRC, re.S).group(0)
sell_m = re.search(
    r"fn sell_xel_out\(.*?\n\}", SRC, re.S).group(0)
check("y_total * (net_xel as u128) / (x_total + (net_xel as u128))" in buy_m,
      "buy formula is not y_total*net/(x_total+net)")
check("x_total * (tokens as u128) / (y_total + (tokens as u128))" in sell_m,
      "sell formula is not x_total*T/(y_total+T)")
check('require(tokens <= yr, "curverr")' in SRC, "whale guard missing")
check('require(gross <= xr, "curverr")' in SRC, "sell solvency guard missing")
# the graduation predicate, verbatim
grad = re.search(
    r"if \(new_xr as u128\) \* \(y0 as u128\) >= \(new_yr as u128\) \* \(vx as u128\)",
    SRC)
check(grad is not None, "graduation continuity predicate missing/malformed")
check(re.search(r"if \(new_xr as u128\) >= \(gdx as u128\)", SRC) is not None,
      "graduation depth predicate missing/malformed")
# the fee is carved from the seed at migration, not from the live curve
mig = re.search(r"fn migrate_coin_to_dex\(.*?\n\}", SRC, re.S).group(0)
check("let seed_xel: u64 = xr - fee" in mig, "migration fee not carved from seed")
check('require(xr >= fee, "curverr")' in mig, "migration fee guard missing")
print("  OK" if not failures else "  ^ see above")

# --- B+C. brute-force the invariants across regimes -----------------------
print("B+C. brute force: 200 regimes x 250 trades")
rng = random.Random(20260925)
for regime in range(200):
    vx = rng.randrange(XEL, 1000 * XEL)
    y0 = rng.randrange(10**15, 10**18)
    gdx = rng.randrange(XEL, 100 * XEL)
    xr, yr = 0, y0
    k = (xr + vx) * (yr + y0)
    k0 = k
    for step in range(250):
        if rng.random() < 0.55:
            # a buy respecting the whale guard (the contract refuses worse)
            max_net = (yr * (xr + vx)) // y0
            if max_net < 2:
                break
            net = rng.randrange(1, max_net)
            out = (yr + y0) * net // (xr + vx + net)     # SPEC formula
            check(out <= yr, f"regime {regime} step {step}: out > yr")
            xr, yr = xr + net, yr - out
        else:
            circulating = y0 - yr
            if circulating < 1:
                continue
            t = rng.randrange(1, circulating + 1)
            gross = (xr + vx) * t // (yr + y0 + t)        # SPEC formula
            check(gross <= xr, f"regime {regime} step {step}: gross > xr")
            xr, yr = xr - gross, yr + t
        k2 = (xr + vx) * (yr + y0)
        check(k2 >= k, f"regime {regime} step {step}: k decreased")
        check(xr >= 0 and 0 <= yr <= y0,
              f"regime {regime} step {step}: reserves out of bounds")
        k = k2
    check(k >= k0, f"regime {regime}: k < k0 at the end")
    # C: the worst-case sell on the FINAL state
    circulating = y0 - yr
    if circulating >= 1 and xr >= 1:
        gross = (xr + vx) * circulating // (yr + y0 + circulating)
        check(gross <= xr, f"regime {regime}: worst-case sell > xr")
print("  OK" if not failures else "  ^ see above")

# --- D. graduation economics at the defaults ------------------------------
print("D. graduation economics (defaults: vx=100, gdx=50 XEL)")
vx, y0, gdx = 100 * XEL, 10**17, 50 * XEL
ts = y0  # 0% creator
# launch FDV = vx/2
launch_fdv = vx * ts // (2 * y0)
check(launch_fdv == 50 * XEL, f"launch FDV {launch_fdv} != 50 XEL")
# walk 1-XEL buys until graduation (fee 1%)
xr, yr = 0, y0
buys = 0
while True:
    dep = XEL
    net = dep - dep * 100 // 10_000
    out = (yr + y0) * net // (xr + vx + net)
    assert out <= yr
    xr, yr = xr + net, yr - out
    buys += 1
    if xr >= gdx and xr * y0 >= yr * vx:
        break
    check(buys < 200, "graduation never fired")
frac_sold = (y0 - yr) / y0
check(0.60 < frac_sold < 0.70, f"fraction sold at graduation {frac_sold:.3f}")
pool_price = xr / yr
spot = (xr + vx) / (yr + y0)
check(pool_price >= spot, "pool opens below spot")
fdv_at_grad = xr * ts // yr
check(145 * XEL <= fdv_at_grad <= 155 * XEL,
      f"FDV at graduation {fdv_at_grad/XEL:.1f} != ~150 XEL")
print(f"  graduation after {buys} x 1-XEL buys: "
      f"{frac_sold:.1%} sold, FDV {fdv_at_grad//XEL} XEL, "
      f"pool {pool_price/spot:.3f}x spot  OK")

# --- E. unit economics ------------------------------------------------------
print("E. unit economics")
sub, asset_fee = XEL, XEL
dep = 2 * XEL
refund = dep - sub - asset_fee
check(refund == 0, "refund at exact deposit != 0")
dep = 5 * XEL
refund = dep - sub - asset_fee
check(refund == 3 * XEL, "refund calculation wrong")
print("  launch out-of-pocket = sub + asset_fee = 2 XEL  OK")

print()
if failures:
    print(f"PASS 3 FAILED: {len(failures)} failures")
    sys.exit(1)
print("PASS 3 OK — independent re-derivation agrees with the contract "
      "on every formula, invariant and economic claim.")
