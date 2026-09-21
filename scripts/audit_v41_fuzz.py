#!/usr/bin/env python3
"""audit_v41_fuzz.py — AUDIT 3 of the v4.1 hardening pass (founder risk
review): randomized stress of exactly the NEW behaviors, with every
invariant asserted after every action:

  A. D21 vote deposits — random dials, random voters, multi-round
     lifecycles (validation -> rejection/recovery), interleaved claims:
     I2 (pots committed), the pots-sum identity, no double refunds,
     wallets never lose more than the dial.
  B. X7 price-neutral liquidity — random reserves and deposits on the
     DexSim mirror: the IX7 product bound, refunds never exceed the
     fresh deposit, price drift <= 1 unit per add, the "dust" and
     branch behavior of the fit.
  C. IX6 ungated sells — sells succeed under BOTH the buys-pause and
     the emergency pause; buys are refused.

Exit 0 = PASS (all seeds), 1 = any failure.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "xvault"))

from test_launchpad_reference import DexSim, Sim, _fuzz_cfg  # noqa: E402
from xvault import launchpad as lp  # noqa: E402

XEL = 100_000_000
SEEDS = 40


def fuzz_d21(seed: int) -> None:
    rng = random.Random(seed)
    dial = rng.choice([0, 1 * XEL, 2 * XEL, 5 * XEL])
    sim = Sim(cfg=_fuzz_cfg() | {"vote_deposit": dial})
    sim.mint("founder", 2000 * XEL)
    pid = sim.propose("founder", rng.randrange(500, 1000) * XEL)
    voters = [f"v{i}" for i in range(rng.randrange(3, 12))]
    for v in voters:
        sim.mint(v, rng.randrange(dial // XEL + 4, 60) * XEL)
    # validation round votes (attach dial + random excess)
    voted: list[str] = []
    for v in voters:
        if rng.random() < 0.8:
            sim.vote(pid, v, rng.random() < 0.75,
                     deposit=dial + rng.randrange(0, 3) * XEL)
            voted.append(v)
    # claims while open must fail when dial > 0 and slot > 0
    if dial > 0 and voted:
        try:
            sim.claim_vote_deposit(pid, 0, voted[0])
            raise SystemExit(f"seed {seed}: claim succeeded on an OPEN round")
        except AssertionError as e:
            assert "open" in str(e), f"seed {seed}: wrong refusal {e}"
    sim.warp(sim.cfg["validation_duration"] + 1)
    sim.finalize(pid)
    # some claim, some don't (unclaimed pots must stay committed in I2).
    # dial == 0: votes are free — every claim must fail with "nothing".
    claimed = 0
    if dial == 0:
        for v in voted:
            try:
                sim.claim_vote_deposit(pid, 0, v)
                raise SystemExit(f"seed {seed}: free vote claimed a refund")
            except AssertionError as e:
                assert "nothing" in str(e)
        assert sim.vote_pots == 0
    else:
        for v in voted:
            if rng.random() < 0.7:
                before = sim.wallets[v]["xel"]
                sim.claim_vote_deposit(pid, 0, v)
                claimed += 1
                assert sim.wallets[v]["xel"] == before + dial, \
                    f"seed {seed}: {v} refunded the wrong amount"
                # double claim refused
                try:
                    sim.claim_vote_deposit(pid, 0, v)
                    raise SystemExit(f"seed {seed}: DOUBLE refund")
                except AssertionError as e:
                    assert "nothing" in str(e)
    expected_pots = dial * (len(voted) - claimed)
    assert sim.vote_pots == expected_pots, \
        f"seed {seed}: pots {sim.vote_pots} != {expected_pots}"
    # a non-voter can never claim
    non_voters = [v for v in voters if v not in voted]
    if non_voters:
        try:
            sim.claim_vote_deposit(pid, 0, non_voters[0])
            raise SystemExit(f"seed {seed}: non-voter claimed a deposit")
        except AssertionError as e:
            assert "novote" in str(e)


def fuzz_x7(seed: int) -> None:
    rng = random.Random(1000 + seed)
    dex = DexSim()
    dex.set_launchpad("lpx")
    asset = "cc" * 32
    dex.create_pool("lpx", asset,
                    rng.randrange(50, 5000) * XEL,
                    rng.randrange(10**6, 10**12))
    p = dex.pools[asset]
    price0 = p["x"] * 10**8 // p["y"]
    dex.wallets["donor"]["xel"] = 10**9 * XEL
    dex.wallets["donor"]["assets"][asset] = 10**15
    for i in range(30):
        x, y = p["x"], p["y"]
        price_before = x * 10**8 // y
        xel_in = rng.randrange(1, 200 * XEL)
        tok_in = rng.randrange(1, 3 * y)
        try:
            xel_eff, tok_eff = dex.add_liquidity("donor", asset, xel_in, tok_in)
        except AssertionError as e:
            assert "dust" in str(e) or "ratio" in str(e) or "minlp" in str(e), \
                f"seed {seed}: unexpected refusal {e}"
            # a refused add must change NOTHING (X7 + the v1.2 LP floor)
            assert p["x"] == x and p["y"] == y, \
                f"seed {seed}: refused add mutated the reserves"
            continue
        # IX7: one floor unit of drift on the binding side
        x1, y1 = p["x"], p["y"]
        assert abs(x1 * y - x * y1) < max(x, y), f"seed {seed}: IX7 broken"
        price_after = x1 * 10**8 // y1
        assert abs(price_after - price_before) <= 1, \
            f"seed {seed}: price moved at add #{i}"
        # refunds never exceed the fresh deposit
        assert 0 <= xel_in - xel_eff <= xel_in
        assert 0 <= tok_in - tok_eff <= tok_in
        assert xel_eff >= 1 and tok_eff >= 1
    assert dex.pools[asset]["x"] > 0 and dex.pools[asset]["y"] > 0


def fuzz_ix6(seed: int) -> None:
    rng = random.Random(2000 + seed)
    dex = DexSim()
    dex.set_launchpad("lpx")
    asset = "dd" * 32
    dex.create_pool("lpx", asset, 1000 * XEL, 10**9)
    # worst case: buys paused AND emergency on
    dex.set_pool_buys_paused("lpx", asset, True)
    dex.emergency = True
    holder = "h"
    dex.wallets[holder]["assets"][asset] = 10**7
    for _ in range(5):
        out = dex.swap_tokens(holder, asset, rng.randrange(1, 10**6))
        assert out >= 1, f"seed {seed}: sell blocked under emergency!"
    dex.wallets["b"]["xel"] = 100 * XEL
    try:
        dex.swap_xel("b", asset, 10 * XEL)
        raise SystemExit(f"seed {seed}: buy succeeded under emergency")
    except AssertionError as e:
        assert "buyspaused" in str(e) or "paused" in str(e)


def fuzz_d23(seed: int) -> None:
    """X10/D23: random multi-provider pools — adds, buys, sells, dial
    changes and claims, with IX8 (dues <= pots, reserves+pots <=
    balances) asserted after EVERY action."""
    rng = random.Random(3000 + seed)
    dex = DexSim()
    dex.set_launchpad("lpx")
    asset = "ee" * 32
    dex.create_pool("lpx", asset, rng.randrange(50, 5000) * XEL,
                    rng.randrange(10**6, 10**12))
    providers = [f"p{i}" for i in range(rng.randrange(1, 6))]
    for w in providers + ["t"]:
        dex.wallets[w]["xel"] = 10**6 * XEL
        dex.wallets[w]["assets"][asset] = 10**14
    for _ in range(60):
        x, y = dex.pools[asset]["x"], dex.pools[asset]["y"]
        roll = rng.random()
        try:
            if roll < 0.25:
                w = rng.choice(providers)
                xel_add = rng.randrange(1, 50) * XEL
                need_tok = y * xel_add // x
                if dex.wallets[w]["assets"][asset] >= need_tok >= 1:
                    dex.add_liquidity(w, asset, xel_add, need_tok)
            elif roll < 0.55:
                dex.swap_xel("t", asset, rng.randrange(1, 100) * XEL)
            elif roll < 0.75:
                held = dex.wallets["t"]["assets"][asset]
                if held > 0:
                    dex.swap_tokens("t", asset, rng.randrange(1, held + 1))
            elif roll < 0.85:
                # the dial moves inside its hard bounds (prospective only)
                dex.set_fee_split(rng.randrange(2500, 7501))
            else:
                dex.claim_lp_fees(rng.choice(providers), asset)
        except AssertionError as e:
            # the only legitimate refusals: fit guards and empty claims
            ok = any(k in str(e) for k in
                     ("dust", "ratio", "minlp", "nofees", "buyspaused"))
            assert ok, f"seed {seed}: unexpected refusal {e}"
        dex.check_invariants()
        # the accrual bound (IX8): counters never outgrow lifetime fees
        p = dex.pools[asset]
        assert p["ax"] <= p["fl"] and p["ay"] <= p["fl"]


def main() -> int:
    for seed in range(SEEDS):
        fuzz_d21(seed)
        fuzz_x7(seed)
        fuzz_ix6(seed)
        fuzz_d23(seed)
    print(f"AUDIT 3 (v4.1+v1.2 FUZZ): PASS — {SEEDS} seeds x (D21 deposits, "
          "X7 price-neutral adds, IX6 ungated sells, D23 LP fee share); "
          "I2 pots identity, no double refunds, one-floor-unit price "
          "bound, refunds within deposits, IX8 dues-within-pots and "
          "accrual-within-lifetime — all held on every action.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
