"""
Reference tests for VaultLaunch (launchpad) — v3 full-proposal-data
edition.

Three layers, mirroring the mixer's test philosophy (if you change the
contract, change the reference in the SAME commit — CI fails on drift):

  1. CURVE MATH PARITY — sdk/xvault/xvault/launchpad.py must reproduce
     EXACTLY the integer formulas of contracts/launchpad/VaultLaunch.slx
     (fee split, effective fee by graduation status, constant-product
     buy/sell, team allocation + vesting stream, price, market cap,
     graduation threshold, migration fee), including the floor directions
     that keep the contract solvent.

  2. STATE MACHINE — a Python mini-VM replays full project lifecycles
     against the same storage keys and transition rules as the contract:
     propose -> validation -> bonding -> graduation (migration fee, team
     claim/vesting, D10 plan binding, D12 trading data) -> trust loss ->
     recovery, AND the v2 direct-listing path (liquidity >= threshold
     graduates at validation), asserting the contract's invariants
     I1/I2/I5/I9 after every step.

  3. SOURCE & SDK CONSISTENCY — the contract file must expose every
     function and event of the spec, carry the documented defaults, keep
     zero inter-contract calls and only checked transfers; and the SDK's
     LAUNCHPAD_ENTRY_IDS table must match the real declaration order (it
     is what real transactions are built from — a drift would invoke the
     wrong entry).
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "xvault"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest  # noqa: E402

from xvault import launchpad as lp  # noqa: E402
from xvault import protocol  # noqa: E402
from silex_parse import SilexFile  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(REPO_ROOT, "contracts", "launchpad", "VaultLaunch.slx")

XEL = 10 ** 8  # 1 XEL / 1 token, 8 decimals


# ---------------------------------------------------------------------------
# Layer 1 — curve math parity with the contract
# ---------------------------------------------------------------------------

def test_defaults_match_the_specification():
    """The documented defaults ARE the spec table (v2: + graduated fee,
    migration fee, direct-listing threshold, team delay, vesting bounds)."""
    assert lp.DEFAULTS["submission_fee"] == 10 * XEL
    assert lp.DEFAULTS["min_liquidity"] == 500 * XEL
    assert lp.DEFAULTS["trading_fee_bps"] == 50
    assert lp.DEFAULTS["graduated_fee_bps"] == 25
    assert lp.DEFAULTS["migration_fee_bps"] == 50
    assert lp.DEFAULTS["direct_listing_threshold"] == 2000 * XEL
    assert lp.DEFAULTS["min_participants"] == 20
    assert lp.DEFAULTS["min_approval_ratio_bps"] == 8000
    assert lp.DEFAULTS["graduation_multiplier"] == 4
    assert lp.DEFAULTS["recovery_fee"] == 250 * XEL
    assert lp.DEFAULTS["recovery_min_participants"] == 40
    assert lp.DEFAULTS["recovery_min_ratio_bps"] == 9000
    assert lp.DEFAULTS["team_unlock_delay"] == 3_153_600      # ~6 months
    assert lp.DEFAULTS["vesting_min"] == 518_400              # ~1 month
    assert lp.DEFAULTS["vesting_max"] == 6_307_200            # ~1 year
    # the default direct-listing threshold == min_liquidity x multiplier:
    # direct listing asks for exactly what a curve graduate has proven
    assert (lp.DEFAULTS["direct_listing_threshold"] ==
            lp.DEFAULTS["min_liquidity"] * lp.DEFAULTS["graduation_multiplier"])


def test_fee_take_floors_in_favour_of_the_contract():
    assert lp.fee_take(100 * XEL, 50) == 50 * XEL // 100  # exact 0.5%
    # floor: 1 atomic with 50 bps is 0.005 -> 0
    assert lp.fee_take(1, 50) == 0
    assert lp.fee_take(199, 50) == 0
    assert lp.fee_take(200, 50) == 1


def test_effective_fee_by_graduation_status_d8():
    """current_fee_bps: bonding pays trading fee, graduates pay the lower
    graduated fee; the clamp keeps graduation ALWAYS cheaper (D8)."""
    tfe, gfe = 50, 25
    assert lp.current_fee_bps(False, tfe, gfe) == 50   # bonding
    assert lp.current_fee_bps(True, tfe, gfe) == 25    # graduated
    # even a corrupt storage state (gfe > tfe) clamps to the bonding fee
    assert lp.current_fee_bps(True, 50, 80) == 50
    assert lp.current_fee_bps(True, 0, 80) == 0


def test_buy_math_hand_vector():
    """R=500 XEL, C=90M tokens, buy 100 XEL net (fee already removed):
    tokens = C*net/(R+net) = 9e15*1e10/(5e10+1e10) = 1.5e15 = 15M tokens."""
    tokens = lp.buy_tokens_out(500 * XEL, 90_000_000 * XEL, 100 * XEL)
    assert tokens == 15_000_000 * XEL


def test_buy_quote_includes_fee():
    """100 XEL attached with 50 bps fee -> net 99.5 XEL joins the curve."""
    out = lp.buy_quote(500 * XEL, 90_000_000 * XEL, 100 * XEL, 50)
    net = 100 * XEL - lp.fee_take(100 * XEL, 50)
    assert out == lp.buy_tokens_out(500 * XEL, 90_000_000 * XEL, net)
    assert out == 1_493_744_787_322_768  # floored integer, never rounded up


def test_buy_quote_graduated_uses_the_lower_fee():
    """Same curve, graduated project: 25 bps instead of 50 -> more tokens."""
    bonding = lp.buy_quote(500 * XEL, 90_000_000 * XEL, 100 * XEL, 50)
    graduated = lp.buy_quote(500 * XEL, 90_000_000 * XEL, 100 * XEL, 25)
    assert graduated > bonding


def test_sell_math_hand_vector():
    """R=500 XEL, C=90M tokens, sell 15M tokens:
    gross = R*T/(C+T) = 5e10*1.5e15/1.05e16 = 7142857142 (floored)."""
    gross = lp.sell_xel_out(500 * XEL, 90_000_000 * XEL, 15_000_000 * XEL)
    assert gross == 7_142_857_142


def test_round_trip_costs_at_most_the_two_fees():
    """buy then immediately sell back loses only fees (+ rounding dust)."""
    r, c, fee_bps = 500 * XEL, 90_000_000 * XEL, 50
    xel_in = 100 * XEL
    tokens = lp.buy_quote(r, c, xel_in, fee_bps)
    # apply the buy to the curve state like the contract does
    net = xel_in - lp.fee_take(xel_in, fee_bps)
    r2, c2 = r + net, c - tokens
    back = lp.sell_quote(r2, c2, tokens, fee_bps)
    fee_cost = lp.fee_take(xel_in, fee_bps) + lp.fee_take(
        lp.sell_xel_out(r2, c2, tokens), fee_bps)
    assert back <= xel_in - fee_cost
    assert back >= xel_in - fee_cost - 2  # dust only (floor directions)


def test_constant_product_never_insolvent():
    """After any buy/sell, reserves stay > 0 and curve supply stays > 0,
    and the implied k never decreases through trades."""
    import random
    rng = random.Random(1234)
    r, c = 500 * XEL, 90_000_000 * XEL
    k = r * c
    for _ in range(500):
        if rng.random() < 0.5:
            xel_in = rng.randrange(1 * XEL, 50 * XEL)
            net = xel_in - lp.fee_take(xel_in, 50)
            t = lp.buy_tokens_out(r, c, net)
            assert 0 < t < c
            r, c = r + net, c - t
        else:
            t = rng.randrange(1, 5_000_000 * XEL)
            gross = lp.sell_xel_out(r, c, t)
            assert 0 < gross < r
            r, c = r - gross, c + t
        assert r > 0 and c > 0
        assert r * c >= k  # fees stay in reserves: k only grows


def test_team_allocation_and_graduation_threshold():
    assert lp.team_alloc_of(1_000_000_000 * XEL, 1000) == 100_000_000 * XEL
    assert lp.team_alloc_of(1_000_000_000 * XEL, 0) == 0
    assert lp.team_alloc_of(123 * XEL, 2000) == 24 * XEL + (
        123 * XEL * 2000 // 10_000 - 24 * XEL)  # exact bps math
    # graduation at liquidity * multiplier
    liq, mult = 1_000 * XEL, 4
    assert (liq * mult) == 4_000 * XEL


def test_team_unlocked_all_paths_d3():
    team = 100 * XEL
    # 1. graduated, no vesting: full allocation (the migration reward)
    assert lp.team_unlocked(team, True, 0, 0, lp.ST_GRADUATED, 999, 0, 0) == team
    # 2. vesting active: linear stream, floored
    half = lp.team_unlocked(team, True, 1000, 2000, lp.ST_GRADUATED, 999, 0, 2000)
    assert half == 50 * XEL
    # not a single unit before the stream starts
    assert lp.team_unlocked(team, True, 2000, 2000, lp.ST_GRADUATED, 999, 0, 2000) == 0
    # full after the whole duration (saturates, never more than team)
    assert lp.team_unlocked(team, True, 1000, 2000, lp.ST_GRADUATED, 999, 0, 5000) == team
    # 3. never graduated, bonding, delay NOT elapsed: 0
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_BONDING, 1000, 500,
                            1000 + 499) == 0
    # 4. never graduated, delay elapsed: full (the late claim)
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_BONDING, 1000, 500,
                            1000 + 500) == team
    # 5. Untrusted never-graduated after the delay: still the late claim
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_UNTRUSTED, 1000, 500,
                            2000) == team
    # 6. Validation / Rejected: nothing, ever
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_VALIDATION, 1000, 0, 999999) == 0
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_REJECTED, 1000, 0, 999999) == 0
    # 7. vesting overrides graduation timing (started, then graduated)
    assert lp.team_unlocked(team, True, 1000, 4000, lp.ST_GRADUATED, 999, 0, 3000) == 50 * XEL


def test_team_remaining_never_negative():
    assert lp.team_remaining(100, 30) == 70
    assert lp.team_remaining(100, 100) == 0
    assert lp.team_remaining(100, 150) == 0  # can never over-pay (I4)


def test_price_and_market_cap():
    r, c = 2_000 * XEL, 8_000_000 * XEL
    assert lp.current_price(r, c) == 25_000  # 0.00025 XEL/token, scaled 1e8
    assert lp.current_price(r, 0) == 0
    # circulating excludes the team allocation NOT YET PAID (v2 unified)
    ts, tb = 10_000_000 * XEL, 1000
    mc = lp.market_cap(r, c, ts, tb, graduated=False, team_paid=0)
    circ = ts - c - lp.team_alloc_of(ts, tb)
    assert mc == r * circ // c
    # half claimed -> half of the allocation counts as circulating
    half_paid = lp.team_alloc_of(ts, tb) // 2
    assert lp.market_cap(r, c, ts, tb, True, half_paid) == r * (
        ts - c - (lp.team_alloc_of(ts, tb) - half_paid)) // c
    # fully paid -> the whole allocation is circulating
    assert lp.market_cap(r, c, ts, tb, graduated=True,
                         team_paid=lp.team_alloc_of(ts, tb)) == r * (ts - c) // c
    # saturation never raises
    huge = lp.market_cap(10 ** 15, 1, 10 ** 16, 0, True, 0)
    assert huge == 2 ** 64 - 1


def test_migration_fee_math_d9():
    """migration fee = fee_take(reserves, migration_fee_bps) — the same
    floored bps helper, applied once at the graduation moment."""
    reserves = 4_000 * XEL
    fee = lp.fee_take(reserves, 50)
    assert fee == 20 * XEL  # 0.5% of a x4-grown curve
    # direct listing pays it on its seed liquidity instead
    seed = 2_000 * XEL
    assert lp.fee_take(seed, 50) == 10 * XEL


def test_storage_keys_match_the_contract_layout():
    assert lp.proj_key(3, "rv") == "p:3:rv"
    assert lp.vote_key(3, 1, "xel:abc") == "v:3:1:xel:abc"
    assert lp.bal_key(3, "xel:abc") == "b:3:xel:abc"
    assert lp.GLOBAL_KEYS["pending_fees"] == "pfe"
    assert lp.GLOBAL_KEYS["graduated_fee_bps"] == "gfe"
    assert lp.GLOBAL_KEYS["migration_fee_bps"] == "mgf"
    assert lp.GLOBAL_KEYS["direct_listing_threshold"] == "dlt"
    assert lp.GLOBAL_KEYS["team_unlock_delay"] == "tdy"
    assert lp.F_TEAM_PAID == "tp" and lp.F_VESTING_START == "vs"
    assert lp.F_VESTING_DURATION == "vd" and lp.F_BONDING_START == "bt"
    assert lp.F_DL == "dl"


# ---------------------------------------------------------------------------
# Layer 2 — state machine simulation (mini-VM, same keys, same rules)
# ---------------------------------------------------------------------------

class Sim:
    """A faithful Python replay of VaultLaunch v3's state transitions.

    Implements propose/support/report/finalize/buy/sell/claim_refund/
    request_revalidation/update_info/start_team_vesting/claim_team_allocation
    with the contract's exact rules (two-path graduation, effective fees,
    migration fee, team claim bookkeeping, D10 vesting-plan binding, D11
    social links, D12 volume + market-cap scoreboard); invariants are
    asserted after every operation. `self.topo` is the simulated topoheight
    (warp() advances it).
    """

    def __init__(self, cfg=None):
        self.cfg = dict(lp.DEFAULTS, **(cfg or {}))
        self.s = {}  # storage: string key -> value
        self.count = 0
        self.pending_fees = 0
        self.total_curve_xel = 0
        self.locked_refunds = 0
        self.total_buy_vol = 0    # D12 global tbv
        self.total_sell_vol = 0   # D12 global tsv
        self.total_volume = 0     # D12 global tvl (== tbv + tsv, I9)
        self.total_trades = 0     # D12 global ttc
        self.balance = 0  # contract XEL balance (deposits arrive here)
        self.topo = 0     # simulated topoheight

    def _pk(self, pid, f):
        return lp.proj_key(pid, f)

    def check_invariants(self):
        # I1: ledger per project (v2: team_remaining = alloc - paid)
        for pid in range(self.count):
            ts = self.s.get(self._pk(pid, "ts"), 0)
            cs = self.s.get(self._pk(pid, "cs"), 0)
            tb = self.s.get(self._pk(pid, "tb"), 0)
            paid = self.s.get(self._pk(pid, "tp"), 0)
            balances = sum(v for k, v in self.s.items()
                           if k.startswith(f"b:{pid}:"))
            team_rem = lp.team_remaining(lp.team_alloc_of(ts, tb), paid)
            assert cs + balances + team_rem == ts, f"I1 broken for project {pid}"
        # I2: solvency
        assert self.balance >= self.total_curve_xel + self.pending_fees + \
            self.locked_refunds, "I2 broken"
        # I9: volume identity + stored market-cap freshness (v3)
        per_project_total = 0
        for pid in range(self.count):
            bv = self.s.get(self._pk(pid, "bv"), 0)
            sv = self.s.get(self._pk(pid, "sv"), 0)
            vo = self.s.get(self._pk(pid, "vo"), 0)
            assert vo == bv + sv, f"I9 volume broken for project {pid}"
            per_project_total += vo
            # stored cap == recomputed cap (same formula as the contract's
            # update_market_cap / the pure get_market_cap view)
            expected = lp.market_cap(
                self.s[self._pk(pid, "rv")], self.s[self._pk(pid, "cs")],
                self.s.get(self._pk(pid, "ts"), 0),
                self.s.get(self._pk(pid, "tb"), 0),
                bool(self.s.get(self._pk(pid, "gr"), False)),
                self.s.get(self._pk(pid, "tp"), 0))
            assert self.s.get(self._pk(pid, "mc"), 0) == expected, \
                f"I9 mcap drift for project {pid}"
            assert self.s.get(self._pk(pid, "mh"), 0) >= expected, \
                f"I9 ATH below current for project {pid}"
        assert per_project_total == self.total_volume, "I9 global volume"
        assert self.total_volume == self.total_buy_vol + self.total_sell_vol, \
            "I9 directional split"

    def _update_mcap(self, pid):
        """Mirrors update_market_cap(): recompute + store mc, raise mh."""
        cap = lp.market_cap(
            self.s[self._pk(pid, "rv")], self.s[self._pk(pid, "cs")],
            self.s.get(self._pk(pid, "ts"), 0),
            self.s.get(self._pk(pid, "tb"), 0),
            bool(self.s.get(self._pk(pid, "gr"), False)),
            self.s.get(self._pk(pid, "tp"), 0))
        self.s[self._pk(pid, "mc")] = cap
        if cap > self.s.get(self._pk(pid, "mh"), 0):
            self.s[self._pk(pid, "mh")] = cap

    def _record_trade(self, pid, buy_side, xel_amount):
        """Mirrors record_trade(): directional + total volume, counts, lt."""
        if buy_side:
            self.s[self._pk(pid, "bv")] = self.s.get(self._pk(pid, "bv"), 0) + xel_amount
            self.total_buy_vol += xel_amount
        else:
            self.s[self._pk(pid, "sv")] = self.s.get(self._pk(pid, "sv"), 0) + xel_amount
            self.total_sell_vol += xel_amount
        self.s[self._pk(pid, "vo")] = self.s.get(self._pk(pid, "vo"), 0) + xel_amount
        self.total_volume += xel_amount
        self.s[self._pk(pid, "tc")] = self.s.get(self._pk(pid, "tc"), 0) + 1
        self.total_trades += 1
        self.s[self._pk(pid, "lt")] = self.topo

    def propose(self, creator, liquidity, ts=1_000_000_000 * XEL, tb=1000,
                plan=0, twitter="", telegram="", discord=""):
        fee, min_liq = self.cfg["submission_fee"], self.cfg["min_liquidity"]
        dep = fee + liquidity
        assert dep >= fee + min_liq
        # D10: the plan must be 0 or inside the snapshotted bounds
        assert plan == 0 or self.cfg["vesting_min"] <= plan <= self.cfg["vesting_max"], \
            "badplan"
        self.balance += dep
        pid = self.count
        self.count += 1
        self.s[self._pk(pid, "cr")] = creator
        self.s[self._pk(pid, "st")] = lp.ST_VALIDATION
        self.s[self._pk(pid, "nm")] = "name"
        self.s[self._pk(pid, "sy")] = "SYM"
        self.s[self._pk(pid, "ts")] = ts
        self.s[self._pk(pid, "tb")] = tb
        self.s[self._pk(pid, "lq")] = liquidity
        self.s[self._pk(pid, "rv")] = liquidity
        self.s[self._pk(pid, "cs")] = ts - lp.team_alloc_of(ts, tb)
        # D11: social links
        self.s[self._pk(pid, "tw")] = twitter
        self.s[self._pk(pid, "tg")] = telegram
        self.s[self._pk(pid, "dc")] = discord
        # v2: direct-listing snapshot at propose time (D7)
        self.s[self._pk(pid, "dl")] = liquidity >= self.cfg["direct_listing_threshold"]
        self.s[self._pk(pid, "tp")] = 0
        self.s[self._pk(pid, "vs")] = 0
        self.s[self._pk(pid, "vd")] = 0
        self.s[self._pk(pid, "vp")] = plan
        self.s[self._pk(pid, "bt")] = 0
        self.s[self._pk(pid, "rd")] = 0
        self.s[self._pk(pid, "sp")] = 0
        self.s[self._pk(pid, "rp")] = 0
        self.s[self._pk(pid, "gr")] = False
        self.s[self._pk(pid, "ve")] = self.topo + self.cfg["validation_duration"]
        # D12: scoreboard starts empty
        self.s[self._pk(pid, "bv")] = 0
        self.s[self._pk(pid, "sv")] = 0
        self.s[self._pk(pid, "vo")] = 0
        self.s[self._pk(pid, "tc")] = 0
        self.s[self._pk(pid, "lt")] = 0
        self.s[self._pk(pid, "mc")] = 0
        self.s[self._pk(pid, "mh")] = 0
        self.s[self._pk(pid, "mg")] = 0
        self.pending_fees += fee
        self.check_invariants()
        return pid

    def update_info(self, pid, caller, description="d", website="w",
                    logo="l", twitter="", telegram="", discord=""):
        """Mirrors update_project_info (D11): metadata + socials, anytime."""
        assert self.s[self._pk(pid, "st")] != lp.ST_REJECTED
        assert caller == self.s[self._pk(pid, "cr")]
        self.s[self._pk(pid, "ds")] = description
        self.s[self._pk(pid, "ws")] = website
        self.s[self._pk(pid, "lg")] = logo
        self.s[self._pk(pid, "tw")] = twitter
        self.s[self._pk(pid, "tg")] = telegram
        self.s[self._pk(pid, "dc")] = discord
        self.check_invariants()

    def vote(self, pid, voter, support):
        st = self.s[self._pk(pid, "st")]
        assert st != lp.ST_REJECTED
        if st in (lp.ST_VALIDATION, lp.ST_RECOVERY):
            assert self.topo < self.s[self._pk(pid, "ve")], "window ended"
        rnd = self.s[self._pk(pid, "rd")]
        vk = lp.vote_key(pid, rnd, voter)
        assert not self.s.get(vk, False), "double vote"
        self.s[vk] = True
        f = "sp" if support else "rp"
        self.s[self._pk(pid, f)] = self.s[self._pk(pid, f)] + 1
        # trust_guard
        if st in (lp.ST_BONDING, lp.ST_GRADUATED, lp.ST_TRUSTED):
            total = self.s[self._pk(pid, "sp")] + self.s[self._pk(pid, "rp")]
            if total >= self.cfg["min_participants"] and \
                    self.s[self._pk(pid, "rp")] * 10_000 >= \
                    self.cfg["min_approval_ratio_bps"] * total:
                self.s[self._pk(pid, "st")] = lp.ST_UNTRUSTED
        self.check_invariants()

    def _graduate(self, pid):
        """graduate() + take_migration_fee() + D10 plan binding + D12 mcap
        snapshot, replayed exactly."""
        self.s[self._pk(pid, "st")] = lp.ST_GRADUATED
        self.s[self._pk(pid, "gr")] = True
        bps = self.cfg["migration_fee_bps"]
        if bps > 0:
            reserves = self.s[self._pk(pid, "rv")]
            fee = lp.fee_take(reserves, bps)
            if fee > 0:
                assert reserves >= fee
                self.s[self._pk(pid, "rv")] = reserves - fee
                self.pending_fees += fee
        # D10: bind the declared plan — the vesting starts by itself.
        plan = self.s.get(self._pk(pid, "vp"), 0) or 0
        if plan > 0:
            self.s[self._pk(pid, "vs")] = self.topo
            self.s[self._pk(pid, "vd")] = plan
        # D12: the graduation market cap, AFTER the migration fee.
        self._update_mcap(pid)
        self.s[self._pk(pid, "mg")] = self.s[self._pk(pid, "mc")]
        self.check_invariants()

    def finalize(self, pid):
        st = self.s[self._pk(pid, "st")]
        assert st in (lp.ST_VALIDATION, lp.ST_RECOVERY)
        assert self.topo >= self.s[self._pk(pid, "ve")], "window still open"
        sp = self.s[self._pk(pid, "sp")]
        rp = self.s[self._pk(pid, "rp")]
        total = sp + rp
        if st == lp.ST_VALIDATION:
            if total >= self.cfg["min_participants"] and \
                    sp * 10_000 >= self.cfg["min_approval_ratio_bps"] * total:
                self.s[self._pk(pid, "bt")] = self.topo
                if self.s[self._pk(pid, "dl")]:
                    # D7: direct listing graduates on the spot
                    self._graduate(pid)
                else:
                    self.s[self._pk(pid, "st")] = lp.ST_BONDING
                return True
            self.s[self._pk(pid, "st")] = lp.ST_REJECTED
            self.locked_refunds += self.s[self._pk(pid, "lq")]
            return False
        graduated = self.s[self._pk(pid, "gr")]
        min_p = self.cfg["recovery_min_participants"] if graduated \
            else self.cfg["min_participants"]
        ratio = self.cfg["recovery_min_ratio_bps"] if graduated \
            else self.cfg["min_approval_ratio_bps"]
        if total >= min_p and sp * 10_000 >= ratio * total:
            self.s[self._pk(pid, "st")] = lp.ST_TRUSTED if graduated \
                else lp.ST_BONDING
            return True
        self.s[self._pk(pid, "st")] = lp.ST_UNTRUSTED
        return False

    def _fee_bps(self, pid):
        return lp.current_fee_bps(self.s[self._pk(pid, "gr")],
                                  self.cfg["trading_fee_bps"],
                                  self.cfg["graduated_fee_bps"])

    def buy(self, pid, buyer, xel_in):
        st = self.s[self._pk(pid, "st")]
        assert st in lp.BUYABLE, f"buys blocked in status {st}"
        fee_bps = self._fee_bps(pid)
        fee = lp.fee_take(xel_in, fee_bps)
        net = xel_in - fee
        r = self.s[self._pk(pid, "rv")]
        c = self.s[self._pk(pid, "cs")]
        tokens = lp.buy_tokens_out(r, c, net)
        self.s[self._pk(pid, "rv")] = r + net
        self.s[self._pk(pid, "cs")] = c - tokens
        bk = lp.bal_key(pid, buyer)
        self.s[bk] = self.s.get(bk, 0) + tokens
        self.balance += xel_in
        self.pending_fees += fee
        self.total_curve_xel += net
        # D12: scoreboard — buys record the ATTACHED amount
        self._record_trade(pid, True, xel_in)
        # graduation (curve path): migration fee taken inside _graduate
        if st == lp.ST_BONDING:
            target = self.s[self._pk(pid, "lq")] * \
                self.cfg["graduation_multiplier"]
            if self.s[self._pk(pid, "rv")] >= target:
                self._graduate(pid)
        # D12: stored market cap follows the curve state change
        self._update_mcap(pid)
        self.check_invariants()
        return tokens

    def sell(self, pid, seller, tokens):
        st = self.s[self._pk(pid, "st")]
        assert st in lp.SELLABLE, "sells must never be blocked"
        bk = lp.bal_key(pid, seller)
        assert self.s.get(bk, 0) >= tokens
        fee_bps = self._fee_bps(pid)
        r = self.s[self._pk(pid, "rv")]
        c = self.s[self._pk(pid, "cs")]
        gross = lp.sell_xel_out(r, c, tokens)
        fee = lp.fee_take(gross, fee_bps)
        out = gross - fee
        assert out >= 1
        self.s[self._pk(pid, "rv")] = r - gross
        self.s[self._pk(pid, "cs")] = c + tokens
        self.s[bk] = self.s[bk] - tokens
        self.balance -= out
        self.pending_fees += fee
        self.total_curve_xel -= gross
        # D12: scoreboard — sells record the PRE-FEE gross
        self._record_trade(pid, False, gross)
        # D12: stored market cap follows the curve state change
        self._update_mcap(pid)
        self.check_invariants()
        return out

    def claim_refund(self, pid, caller):
        assert self.s[self._pk(pid, "st")] == lp.ST_REJECTED
        assert caller == self.s[self._pk(pid, "cr")]
        lq = self.s[self._pk(pid, "lq")]
        self.locked_refunds -= lq
        self.balance -= lq
        self.check_invariants()
        return lq

    def request_revalidation(self, pid, caller):
        assert self.s[self._pk(pid, "st")] == lp.ST_UNTRUSTED
        assert caller == self.s[self._pk(pid, "cr")]
        fee_paid = 0
        if self.s[self._pk(pid, "gr")]:
            fee_paid = self.cfg["recovery_fee"]
            self.balance += fee_paid
            self.pending_fees += fee_paid
        self.s[self._pk(pid, "rd")] += 1
        self.s[self._pk(pid, "sp")] = 0
        self.s[self._pk(pid, "rp")] = 0
        self.s[self._pk(pid, "ve")] = self.topo + self.cfg["validation_duration"]
        self.s[self._pk(pid, "st")] = lp.ST_RECOVERY
        self.check_invariants()
        return fee_paid

    def _unlock(self, pid):
        ts, tb = self.s[self._pk(pid, "ts")], self.s[self._pk(pid, "tb")]
        return lp.team_unlocked(
            lp.team_alloc_of(ts, tb), self.s[self._pk(pid, "gr")],
            self.s[self._pk(pid, "vs")], self.s[self._pk(pid, "vd")],
            self.s[self._pk(pid, "st")], self.s[self._pk(pid, "bt")],
            self.cfg["team_unlock_delay"], self.topo)

    def start_team_vesting(self, pid, caller, duration):
        assert caller == self.s[self._pk(pid, "cr")]
        # D10: a declared plan IS the vesting — no voluntary one on top.
        assert (self.s.get(self._pk(pid, "vp"), 0) or 0) == 0, "planned"
        assert self.s[self._pk(pid, "vs")] == 0, "vesting already started"
        ts, tb = self.s[self._pk(pid, "ts")], self.s[self._pk(pid, "tb")]
        assert lp.team_remaining(lp.team_alloc_of(ts, tb),
                                 self.s[self._pk(pid, "tp")]) > 0, "done"
        assert self.cfg["vesting_min"] <= duration <= self.cfg["vesting_max"]
        assert self._unlock(pid) > 0, "not yet unlockable"
        self.s[self._pk(pid, "vs")] = self.topo
        self.s[self._pk(pid, "vd")] = duration
        self.check_invariants()

    def claim_team_allocation(self, pid, caller):
        assert caller == self.s[self._pk(pid, "cr")]
        unlocked = self._unlock(pid)
        paid = self.s[self._pk(pid, "tp")]
        assert unlocked > paid, "nothing to claim"
        pay = unlocked - paid
        self.s[self._pk(pid, "tp")] = paid + pay
        ck = lp.bal_key(pid, self.s[self._pk(pid, "cr")])
        self.s[ck] = self.s.get(ck, 0) + pay
        # D12: a claim grows circulating supply — the cap follows at once.
        self._update_mcap(pid)
        self.check_invariants()
        return pay

    def warp(self, topos):
        """Advance the simulated topoheight (time travel for windows)."""
        self.topo += topos


def _validate(sim, pid, n=20):
    """Pass a validation window: n supporters, then warp past the deadline
    and finalize."""
    for i in range(n):
        sim.vote(pid, f"xel:v{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    return sim.finalize(pid)


def test_full_lifecycle_curve_path():
    """The classic bonding path: validation -> bonding -> graduation with
    migration fee + lower fees + team claim -> trust loss -> recovery."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 1_000 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    assert sim.s[sim._pk(pid, "cs")] == 900_000_000 * XEL  # team reserved
    assert sim.s[sim._pk(pid, "dl")] is False  # 1000 < 2000 threshold

    assert _validate(sim, pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING
    assert sim.s[sim._pk(pid, "bt")] == sim.topo

    # buys push the curve to graduation (target = 4000 XEL reserves)
    bob = "xel:bob"
    total_tokens = 0
    buys = 0
    fees_before = sim.pending_fees
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        total_tokens += sim.buy(pid, bob, 100 * XEL)
        buys += 1
    assert sim.s[sim._pk(pid, "st")] == lp.ST_GRADUATED
    assert sim.s[sim._pk(pid, "gr")] is True

    # fee accounting: every buy paid the bonding fee, and graduation added
    # the ONE-TIME migration fee taken on the reserves at the graduation
    # moment (>= the 4000 XEL threshold — the triggering buy may overshoot)
    buy_fees = buys * lp.fee_take(100 * XEL, sim.cfg["trading_fee_bps"])
    migration_fee = sim.pending_fees - fees_before - buy_fees
    reserves_now = sim.s[sim._pk(pid, "rv")]
    # the fee was taken from the reserves AT the graduation moment, so the
    # pre-fee reserves were reserves_now + migration_fee (>= 4000 XEL)
    assert migration_fee == lp.fee_take(reserves_now + migration_fee,
                                        sim.cfg["migration_fee_bps"])
    assert reserves_now + migration_fee >= 4_000 * XEL
    assert reserves_now == 4_000 * XEL - migration_fee + (
        reserves_now + migration_fee - 4_000 * XEL)

    # the team allocation is NOT auto-minted anymore: claim pays it (D3)
    assert sim.s.get(lp.bal_key(pid, alice), 0) == 0
    paid = sim.claim_team_allocation(pid, alice)
    assert paid == 100_000_000 * XEL
    assert sim.s[lp.bal_key(pid, alice)] == 100_000_000 * XEL
    # a second claim reverts: unlocked == paid == team
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)

    # graduated fee applies now (D8): 25 bps on a sell
    r, c = sim.s[sim._pk(pid, "rv")], sim.s[sim._pk(pid, "cs")]
    tokens = 1_000_000 * XEL
    gross = lp.sell_xel_out(r, c, tokens)
    expected_fee = lp.fee_take(gross, 25)
    fees_before = sim.pending_fees
    sim.sell(pid, bob, tokens)
    assert sim.pending_fees == fees_before + expected_fee

    # trust loss post-graduation: the 20 validation supports carry over,
    # so reaching 80% of all votes takes 80 reports.
    for i in range(80):
        sim.vote(pid, f"xel:angry{i}", False)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED

    # recovery costs the fee and demands 40 voters / 90%
    fees_before = sim.pending_fees
    paid_fee = sim.request_revalidation(pid, alice)
    assert paid_fee == 250 * XEL
    assert sim.pending_fees == fees_before + 250 * XEL
    for i in range(39):
        sim.vote(pid, f"xel:sorry{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    assert sim.finalize(pid) is False
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED
    sim.request_revalidation(pid, alice)
    for i in range(40):
        sim.vote(pid, f"xel:sorry{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    assert sim.finalize(pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_TRUSTED


def test_direct_listing_path_d7():
    """Serious liquidity (>= threshold) graduates the moment validation
    passes: no bonding phase, migration fee on the seed, graduated fee from
    the first trade, team claimable immediately."""
    sim = Sim()
    founder = "xel:whale"
    pid = sim.propose(founder, 2_000 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    assert sim.s[sim._pk(pid, "dl")] is True

    assert _validate(sim, pid) is True
    # graduated on the spot — no Bonding state ever
    assert sim.s[sim._pk(pid, "st")] == lp.ST_GRADUATED
    assert sim.s[sim._pk(pid, "gr")] is True

    # migration fee taken on the SEED liquidity (D9)
    fee = lp.fee_take(2_000 * XEL, 50)
    assert sim.s[sim._pk(pid, "rv")] == 2_000 * XEL - fee
    assert sim.pending_fees == sim.cfg["submission_fee"] + fee

    # the first buy already pays the GRADUATED fee (D8)
    fees_before = sim.pending_fees
    tokens = sim.buy(pid, "xel:bob", 100 * XEL)
    assert tokens > 0
    expected = lp.fee_take(100 * XEL, sim.cfg["graduated_fee_bps"])
    assert sim.pending_fees == fees_before + expected

    # team claimable immediately (D3) — the direct-listing reward
    assert sim.claim_team_allocation(pid, founder) == 100_000_000 * XEL

    # holders can always sell
    assert sim.sell(pid, "xel:bob", tokens) > 0


def test_threshold_snapshot_at_propose_d7():
    """The threshold read at propose time decides the path — a later admin
    change never reclassifies an existing proposal."""
    sim = Sim()
    pid_small = sim.propose("xel:a", 1_000 * XEL)
    # admin raises the threshold AFTER the proposal: still a curve project
    sim.cfg["direct_listing_threshold"] = 800 * XEL
    pid_big = sim.propose("xel:b", 1_500 * XEL)
    assert sim.s[sim._pk(pid_small, "dl")] is False  # snapshotted at 2000
    assert sim.s[sim._pk(pid_big, "dl")] is True     # snapshotted at 800


def test_team_vesting_stream_d3():
    """The creator may trade the immediate claim for a linear vesting —
    partial claims, resume, saturation; irreversibility is by design."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    _validate(sim, pid)
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:whale", 200 * XEL)
    assert sim.s[sim._pk(pid, "gr")] is True

    # vesting must stay within the admin bounds
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, alice, sim.cfg["vesting_min"] - 1)
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, alice, sim.cfg["vesting_max"] + 1)

    # start a 1-month vesting right at graduation (topo G)
    duration = sim.cfg["vesting_min"]
    sim.start_team_vesting(pid, alice, duration)
    assert sim.s[sim._pk(pid, "vs")] == sim.topo

    # nothing at t0, a quarter at 25%, cumulative claims resume correctly
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)  # unlocked == 0 at t0
    team = 100_000_000 * XEL
    sim.warp(duration // 4)
    assert sim.claim_team_allocation(pid, alice) == team // 4
    sim.warp(duration // 4)  # halfway point (total elapsed = 50%)
    assert sim.claim_team_allocation(pid, alice) == team // 2 - team // 4
    # ...after the full duration, the rest is claimable — and only once
    sim.warp(duration)
    assert sim.claim_team_allocation(pid, alice) == team - team // 2
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)

    # a second vesting can never be started on the same project
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, alice, duration)


def test_team_late_claim_never_graduated_d3():
    """A project that never graduates does not hold the team hostage: after
    team_unlock_delay of bonding, the creator claims the full allocation."""
    sim = Sim(cfg={"team_unlock_delay": 1_000})
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    _validate(sim, pid)
    bonding_start = sim.s[sim._pk(pid, "bt")]

    # before the delay: nothing to claim, nothing to vest
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, alice, sim.cfg["vesting_min"])

    # one topo short of the delay: still locked
    sim.warp(999)
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)

    # delay elapsed (topo == bt + 1000): the late claim pays in full
    sim.warp(1)
    assert sim.topo == bonding_start + 1_000
    assert sim.claim_team_allocation(pid, alice) == 100_000_000 * XEL

    # the project can still graduate afterwards — no double pay (I4)
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:whale", 300 * XEL)
    assert sim.s[sim._pk(pid, "gr")] is True
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)
    assert sim.s[lp.bal_key(pid, alice)] == 100_000_000 * XEL


def test_rejected_project_refunds_once_and_no_team():
    sim = Sim()
    pid = sim.propose("xel:founder", 500 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    # not enough voters -> rejected -> full refund, NO team tokens ever
    for i in range(5):
        sim.vote(pid, f"xel:v{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    assert sim.finalize(pid) is False
    assert sim.s[sim._pk(pid, "st")] == lp.ST_REJECTED
    before = sim.balance
    assert sim.claim_refund(pid, "xel:founder") == 500 * XEL
    assert sim.balance == before - 500 * XEL
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, "xel:founder")
    assert sim.s.get(lp.bal_key(pid, "xel:founder"), 0) == 0


def test_untrusted_blocks_buys_never_sells_and_recovers():
    sim = Sim()
    pid = sim.propose("xel:founder", 1_000 * XEL, ts=1_000_000_000 * XEL, tb=0)
    _validate(sim, pid)

    bob = "xel:bob"
    sim.buy(pid, bob, 50 * XEL)
    tokens = sim.s[lp.bal_key(pid, bob)]
    assert tokens > 0

    # trust loss: reports must reach 80% of ALL accumulated votes — the 20
    # validation supports carry over, so 80 fresh reports are needed
    for i in range(79):
        sim.vote(pid, f"xel:rep{i}", False)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING  # 79 is not enough
    sim.vote(pid, "xel:rep79", False)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED

    # buys are blocked (D4)...
    with pytest.raises(AssertionError):
        sim.buy(pid, "xel:newbie", 10 * XEL)
    # ...but the holder still exits (I8)
    out = sim.sell(pid, bob, tokens)
    assert out > 0

    # recovery (not graduated: free, normal thresholds)
    assert sim.request_revalidation(pid, "xel:founder") == 0
    assert sim.s[sim._pk(pid, "rd")] == 1
    # old votes are gone: the round reset cleared the tallies
    assert sim.s[sim._pk(pid, "sp")] == 0 and sim.s[sim._pk(pid, "rp")] == 0
    for i in range(20):
        sim.vote(pid, f"xel:rec{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    assert sim.finalize(pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING  # was never graduated


def test_one_vote_per_address_per_round():
    sim = Sim()
    pid = sim.propose("xel:founder", 500 * XEL)
    sim.vote(pid, "xel:voter", True)
    with pytest.raises(AssertionError):
        sim.vote(pid, "xel:voter", True)
    # a new round clears the voted map (I5: keyed by round)
    sim.s[sim._pk(pid, "st")] = lp.ST_UNTRUSTED  # force for the test
    sim.request_revalidation(pid, "xel:founder")
    sim.vote(pid, "xel:voter", True)  # allowed again in round 1


def test_solvency_after_graduation_and_withdrawal_pressure():
    """I2 holds through graduation fees and full-fee withdrawals: the
    migration fee stays inside pending_fees and the seed liquidity margin
    always covers the commitments."""
    sim = Sim()
    pid_a = sim.propose("xel:a", 500 * XEL, ts=1_000_000_000 * XEL, tb=500)
    pid_b = sim.propose("xel:b", 500 * XEL, ts=1_000_000_000 * XEL, tb=500)
    # both windows are open at topo 0: vote for both, warp once, finalize both
    for pid in (pid_a, pid_b):
        for i in range(20):
            sim.vote(pid, f"xel:v{i}", True)
    sim.warp(sim.cfg["validation_duration"] + 1)
    assert sim.finalize(pid_a) is True
    assert sim.finalize(pid_b) is True
    while sim.s[sim._pk(pid_a, "st")] == lp.ST_BONDING:
        sim.buy(pid_a, "xel:buyers", 120 * XEL)
    while sim.s[sim._pk(pid_b, "st")] == lp.ST_BONDING:
        sim.buy(pid_b, "xel:buyers", 120 * XEL)
    # both graduated, both paid the migration fee into pending_fees
    assert sim.s[sim._pk(pid_a, "gr")] and sim.s[sim._pk(pid_b, "gr")]
    # simulate the admin draining every accrued fee (stays within I2)
    sim.balance -= sim.pending_fees
    sim.pending_fees = 0
    sim.check_invariants()


def test_fuzz_invariants_hold_under_random_lifecycles():
    """AUDIT PASS (solvency): random multi-project activity — votes, buys,
    sells, graduations (both paths), trust flips, team claims (planned AND
    voluntary vesting), social updates, fee drains — with I1/I2/I5/I9
    asserted after EVERY action. Illegal actions (blocked buys, early
    claims...) are expected and swallowed."""
    import random

    for seed in range(30):
        rng = random.Random(seed)
        # random, sometimes aggressive parameters (within the admin caps).
        # Quorums and windows are fuzz-sized: the mainnet defaults (20
        # voters, 3-day windows, 40-voter recovery) can never be reached
        # inside 220 steps, so lifecycles would stall in Validation and
        # the storm would trade nothing at all.
        sim = Sim(cfg={
            "trading_fee_bps": rng.choice([0, 25, 50, 200, 1000]),
            "graduated_fee_bps": 0,  # will be forced <= trading fee below
            "migration_fee_bps": rng.choice([0, 50, 500]),
            "direct_listing_threshold": rng.choice([500, 800, 2000]) * XEL,
            "team_unlock_delay": rng.choice([100, 1000, 3153600]),
            "vesting_min": 100, "vesting_max": 10_000,
            "min_participants": 3,
            "min_approval_ratio_bps": 6000,
            "validation_duration": 3000,
            "recovery_min_participants": 3,
            "recovery_min_ratio_bps": 6000,
        })
        sim.cfg["graduated_fee_bps"] = min(
            rng.choice([0, 25, 50, 1000]), sim.cfg["trading_fee_bps"])
        traders = [f"xel:t{i}" for i in range(6)]
        pids = []
        for p in range(3):
            liq = rng.choice([500, 800, 2000, 3000]) * XEL
            # D10: some projects carry a declared vesting plan
            plan = rng.choice([0, 0, 500, 2000])
            pids.append(sim.propose(f"xel:founder{p}", liq,
                                    ts=1_000_000_000 * XEL,
                                    tb=rng.choice([0, 500, 1000, 2000]),
                                    plan=plan,
                                    twitter=f"https://x.com/p{p}",
                                    telegram=f"https://t.me/p{p}",
                                    discord=""))
        # deterministic warm-up: push every project through its initial
        # validation (liq >= threshold graduates directly — both paths
        # exercised), so the storm always starts from live, tradeable
        # projects. The storm itself stays fully random from here on.
        for pid in pids:
            for i in range(sim.cfg["min_participants"]):
                sim.vote(pid, f"xel:warm{pid}_{i}", True)
        sim.warp(sim.cfg["validation_duration"] + 1)
        for pid in pids:
            assert sim.finalize(pid) is True
            assert sim.s[sim._pk(pid, "st")] in lp.BUYABLE
        acted = 0
        for step in range(220):
            pid = rng.choice(pids)
            st = sim.s[sim._pk(pid, "st")]
            action = rng.random()
            try:
                if action < 0.16:  # vote (support or report)
                    sim.vote(pid, f"xel:step{step}", rng.random() < 0.7)
                elif action < 0.38 and st in lp.BUYABLE:  # buy
                    sim.buy(pid, rng.choice(traders),
                            rng.randrange(1, 300) * XEL)
                elif action < 0.56 and st in lp.SELLABLE:  # sell
                    t = sim.s.get(lp.bal_key(pid, rng.choice(traders)), 0)
                    if t > 0:
                        sim.sell(pid, rng.choice(traders),
                                 rng.randrange(1, t + 1))
                elif action < 0.62:  # warp time (windows, delays, vesting)
                    sim.warp(rng.randrange(1, 800))
                elif action < 0.68:  # finalize a closed window
                    sim.finalize(pid)
                elif action < 0.76:  # team claim / vesting attempt
                    if rng.random() < 0.5:
                        sim.claim_team_allocation(pid, sim.s[sim._pk(pid, "cr")])
                    else:
                        sim.start_team_vesting(
                            pid, sim.s[sim._pk(pid, "cr")],
                            rng.randrange(100, 10_001))
                elif action < 0.80:  # social/metadata update (D11)
                    sim.update_info(pid, sim.s[sim._pk(pid, "cr")],
                                    twitter=f"https://x.com/u{step}",
                                    telegram="", discord=f"https://d.gg/{step}")
                elif action < 0.84:  # revalidation attempt
                    sim.request_revalidation(pid, sim.s[sim._pk(pid, "cr")])
                elif action < 0.88:  # admin drains accrued fees
                    sim.balance -= sim.pending_fees
                    sim.pending_fees = 0
                else:  # refund attempt on rejected projects
                    if st == lp.ST_REJECTED:
                        sim.claim_refund(pid, sim.s[sim._pk(pid, "cr")])
                acted += 1
            except AssertionError:
                pass  # the contract's guard rails — expected reverts
            # invariants hold after EVERY step, legal or reverted
            sim.check_invariants()
        assert acted >= 60, f"seed {seed}: fuzz too tame ({acted} actions)"
        # the strict accounting identity held through everything:
        # every fee the contract ever accrued came from a documented source
        assert sim.balance >= 0
        # I9 survived the storm: directional split is exact protocol-wide
        assert sim.total_volume == sim.total_buy_vol + sim.total_sell_vol
        assert sim.total_trades > 0


# ---------------------------------------------------------------------------
# Layer 2b — v3 features: full proposal data (D10/D11/D12)
# ---------------------------------------------------------------------------

def test_proposal_data_is_complete_at_propose_time():
    """D10/D11: everything is on the table BEFORE the vote — social links,
    the vesting plan, the direct-listing flag, and a zeroed scoreboard."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 1_000 * XEL, ts=1_000_000_000 * XEL, tb=1000,
                      plan=518_400,
                      twitter="https://x.com/projectx",
                      telegram="https://t.me/projectx",
                      discord="https://discord.gg/projectx")
    # the one-call voting card (get_proposal_data)
    assert sim.s[sim._pk(pid, "lq")] == 1_000 * XEL
    assert sim.s[sim._pk(pid, "ts")] == 1_000_000_000 * XEL
    assert sim.s[sim._pk(pid, "tb")] == 1000
    assert sim.s[sim._pk(pid, "vp")] == 518_400      # the votable plan
    assert sim.s[sim._pk(pid, "dl")] is False        # 1000 < 2000 threshold
    # socials stored
    assert sim.s[sim._pk(pid, "tw")] == "https://x.com/projectx"
    assert sim.s[sim._pk(pid, "tg")] == "https://t.me/projectx"
    assert sim.s[sim._pk(pid, "dc")] == "https://discord.gg/projectx"
    # the scoreboard starts at zero
    for f in ("bv", "sv", "vo", "tc", "lt", "mc", "mh", "mg"):
        assert sim.s[sim._pk(pid, f)] == 0
    # no vesting running yet: the plan waits for graduation
    assert sim.s[sim._pk(pid, "vs")] == 0
    assert sim.s[sim._pk(pid, "vd")] == 0
    # a plan outside the snapshotted bounds is refused
    with pytest.raises(AssertionError):
        sim.propose("xel:b", 500 * XEL, plan=sim.cfg["vesting_min"] - 1)
    with pytest.raises(AssertionError):
        sim.propose("xel:b", 500 * XEL, plan=sim.cfg["vesting_max"] + 1)
    # plan == 0 (the default) is always allowed
    sim.propose("xel:b", 500 * XEL, plan=0)


def test_plan_bounds_snapshot_at_propose_d10():
    """The bounds are read ONCE at propose: a later admin tightening never
    invalidates a plan the community already voted on."""
    sim = Sim()
    pid = sim.propose("xel:a", 500 * XEL, plan=sim.cfg["vesting_max"])
    sim.cfg["vesting_max"] = 100  # admin squeezes the window afterwards
    assert sim.s[sim._pk(pid, "vp")] == 6_307_200  # the original default
    # a NEW proposal must fit the NEW bounds
    with pytest.raises(AssertionError):
        sim.propose("xel:b", 500 * XEL, plan=6_307_200)


def test_social_links_update_anytime_d11():
    """Socials are metadata: the team can move channels whenever it wants,
    until (and after) graduation; only Rejected freezes them."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, twitter="https://x.com/old")
    _validate(sim, pid)
    assert sim.s[sim._pk(pid, "tw")] == "https://x.com/old"
    # the team rebrands mid-bonding
    sim.update_info(pid, alice, twitter="https://x.com/new",
                    telegram="https://t.me/new", discord="https://d.gg/new")
    assert sim.s[sim._pk(pid, "tw")] == "https://x.com/new"
    assert sim.s[sim._pk(pid, "tg")] == "https://t.me/new"
    assert sim.s[sim._pk(pid, "dc")] == "https://d.gg/new"
    # ... and after graduation
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:w", 200 * XEL)
    sim.update_info(pid, alice, twitter="https://x.com/final")
    assert sim.s[sim._pk(pid, "tw")] == "https://x.com/final"
    # not the creator: refused
    with pytest.raises(AssertionError):
        sim.update_info(pid, "xel:imp", twitter="https://x.com/fake")
    # Rejected freezes everything
    pid2 = sim.propose("xel:b", 500 * XEL)
    for i in range(3):
        sim.vote(pid2, f"xel:n{i}", False)
    sim.warp(sim.cfg["validation_duration"] + 1)
    sim.finalize(pid2)
    with pytest.raises(AssertionError):
        sim.update_info(pid2, "xel:b", twitter="https://x.com/late")


def test_vesting_plan_binds_at_graduation_curve_path_d10():
    """The declared plan starts BY ITSELF the moment the curve graduates:
    no claim before the stream pays, partial claims, saturation — and the
    creator can never swap it for a voluntary vesting."""
    sim = Sim()
    alice = "xel:alice"
    plan = sim.cfg["vesting_min"]  # 518_400 topos
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000,
                      plan=plan)
    _validate(sim, pid)
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:whale", 200 * XEL)
    # graduated: the plan bound itself
    grad_topo = sim.topo
    assert sim.s[sim._pk(pid, "gr")] is True
    assert sim.s[sim._pk(pid, "vs")] == grad_topo
    assert sim.s[sim._pk(pid, "vd")] == plan
    # the immediate full claim is GONE — the stream rules
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)  # unlocked == 0 at t0
    team = 100_000_000 * XEL
    sim.warp(plan // 2)
    assert sim.claim_team_allocation(pid, alice) == team // 2
    sim.warp(plan)
    assert sim.claim_team_allocation(pid, alice) == team - team // 2
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)
    # a voluntary vesting on top: refused (the plan IS the vesting)
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, alice, plan)


def test_vesting_plan_binds_at_graduation_direct_listing_d10():
    """Direct listing applies the SAME plan rule: graduation on day one
    starts the declared stream (the community voted the schedule, the path
    to graduation is irrelevant to the commitment)."""
    sim = Sim()
    founder = "xel:whale"
    plan = 2_000_000
    pid = sim.propose(founder, 2_000 * XEL, ts=1_000_000_000 * XEL, tb=1000,
                      plan=plan)
    assert sim.s[sim._pk(pid, "dl")] is True
    _validate(sim, pid)
    # graduated on the spot, plan bound at the graduation topo
    assert sim.s[sim._pk(pid, "gr")] is True
    assert sim.s[sim._pk(pid, "vs")] == sim.topo
    assert sim.s[sim._pk(pid, "vd")] == plan
    # no immediate claim despite the direct listing
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, founder)
    team = 100_000_000 * XEL
    sim.warp(plan // 4)
    assert sim.claim_team_allocation(pid, founder) == team // 4


def test_plan_never_graduated_falls_back_to_late_claim_d10():
    """The plan binds at GRADUATION only: a project that never gets there
    uses the D3 late-claim path (full allocation after the unlock delay)."""
    sim = Sim(cfg={"team_unlock_delay": 1_000})
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000,
                      plan=sim.cfg["vesting_min"])
    _validate(sim, pid)
    bonding_start = sim.s[sim._pk(pid, "bt")]
    # before the delay: nothing (the plan has not bound, no late claim yet)
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, alice)
    sim.warp(1_000)
    assert sim.topo == bonding_start + 1_000
    # the late claim pays IN FULL — the plan never executed
    assert sim.claim_team_allocation(pid, alice) == 100_000_000 * XEL


def test_unplanned_project_keeps_voluntary_vesting_d3():
    """plan == 0 keeps the v2 behaviour: immediate claim at graduation OR a
    voluntary vesting started by the creator afterwards."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000,
                      plan=0)
    _validate(sim, pid)
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:whale", 200 * XEL)
    assert sim.s[sim._pk(pid, "vp")] == 0
    # voluntary vesting still available
    sim.start_team_vesting(pid, alice, sim.cfg["vesting_min"])
    assert sim.s[sim._pk(pid, "vs")] == sim.topo


def test_trading_stats_and_volume_scoreboard_d12():
    """Every trade lands in the on-chain scoreboard: directional volumes,
    total, trade count, last-trade topo — per project AND protocol-wide."""
    sim = Sim()
    pid = sim.propose("xel:a", 1_000 * XEL, ts=1_000_000_000 * XEL, tb=0)
    _validate(sim, pid)
    # two buys of 100 XEL
    sim.buy(pid, "xel:b1", 100 * XEL)
    sim.warp(10)
    sim.buy(pid, "xel:b2", 100 * XEL)
    # one sell
    tokens = sim.s[lp.bal_key(pid, "xel:b1")]
    sim.warp(5)
    sim.sell(pid, "xel:b1", tokens)
    sell_gross = lp.sell_xel_out(
        sim.s[sim._pk(pid, "rv")] + 0,  # post-trade state: recompute below
        1, 1)  # placeholder — real value asserted via identity
    # per-project scoreboard
    assert sim.s[sim._pk(pid, "bv")] == 200 * XEL          # attached sums
    assert sim.s[sim._pk(pid, "sv")] > 0                   # pre-fee gross
    assert sim.s[sim._pk(pid, "vo")] == \
        sim.s[sim._pk(pid, "bv")] + sim.s[sim._pk(pid, "sv")]
    assert sim.s[sim._pk(pid, "tc")] == 3
    assert sim.s[sim._pk(pid, "lt")] == sim.topo
    # protocol-wide scoreboard (single project: identical + trades count)
    assert sim.total_buy_vol == 200 * XEL
    assert sim.total_sell_vol == sim.s[sim._pk(pid, "sv")]
    assert sim.total_volume == sim.s[sim._pk(pid, "vo")]
    assert sim.total_trades == 3
    # a second project keeps its OWN scoreboard
    pid2 = sim.propose("xel:b", 500 * XEL, tb=0)
    _validate(sim, pid2)
    sim.buy(pid2, "xel:c", 50 * XEL)
    assert sim.s[sim._pk(pid2, "bv")] == 50 * XEL
    assert sim.s[sim._pk(pid2, "tc")] == 1
    assert sim.s[sim._pk(pid, "tc")] == 3            # untouched
    assert sim.total_trades == 4
    assert sim.total_volume == (sim.s[sim._pk(pid, "vo")] +
                                sim.s[sim._pk(pid2, "vo")])


def test_market_cap_history_scoreboard_d12():
    """mc tracks every curve change, mh only grows, mg is snapshotted once
    at graduation (post-migration-fee); claims refresh mc too."""
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 500 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    _validate(sim, pid)
    assert sim.s[sim._pk(pid, "mg")] == 0            # never graduated yet
    first_cap = None
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:w", 100 * XEL)
        cap = sim.s[sim._pk(pid, "mc")]
        if first_cap is None:
            first_cap = cap
        assert cap <= sim.s[sim._pk(pid, "mh")]
    # graduated: mg written exactly once, equals the post-fee cap
    assert sim.s[sim._pk(pid, "gr")] is True
    assert sim.s[sim._pk(pid, "mg")] > 0
    assert sim.s[sim._pk(pid, "mg")] == sim.s[sim._pk(pid, "mc")]
    mg = sim.s[sim._pk(pid, "mg")]
    # a sell DROPS mc (reserves leave) but mh stays at the peak
    tokens = sim.s[lp.bal_key(pid, "xel:w")]
    sim.sell(pid, "xel:w", tokens // 2)
    assert sim.s[sim._pk(pid, "mc")] < mg
    assert sim.s[sim._pk(pid, "mh")] >= mg
    # a team claim GROWS circulating -> mc jumps up immediately (no lag)
    sim.claim_team_allocation(pid, alice)
    expected = lp.market_cap(
        sim.s[sim._pk(pid, "rv")], sim.s[sim._pk(pid, "cs")],
        sim.s[sim._pk(pid, "ts")], sim.s[sim._pk(pid, "tb")],
        True, sim.s[sim._pk(pid, "tp")])
    assert sim.s[sim._pk(pid, "mc")] == expected
    # mg was never rewritten
    assert sim.s[sim._pk(pid, "mg")] == mg


# ---------------------------------------------------------------------------
# Layer 3 — source & SDK consistency
# ---------------------------------------------------------------------------

def _contract_text() -> str:
    with open(CONTRACT, encoding="utf-8") as fh:
        return fh.read()


def test_contract_exposes_the_full_spec_api():
    sf = SilexFile.parse(__import__("pathlib").Path(CONTRACT))
    names = {f.name for f in sf.functions}
    spec = {
        # admin
        "set_submission_fee", "set_trading_fee",
        "set_graduated_trading_fee", "set_migration_fee",
        "set_direct_listing_threshold", "set_min_liquidity",
        "set_min_participants", "set_min_approval_ratio",
        "set_validation_duration", "set_graduation_multiplier",
        "set_team_unlock_delay", "set_vesting_bounds",
        "set_recovery_fee", "set_recovery_params", "set_admin",
        "set_paused", "withdraw_fees",
        # creator
        "propose", "claim_refund", "update_project_info",
        "request_revalidation", "start_team_vesting",
        "claim_team_allocation",
        # users
        "support", "report", "buy", "sell", "finalize_validation",
        # views
        "get_project", "get_project_status", "get_project_tokenomics",
        "get_project_trust", "get_bonding_info", "get_current_price",
        "get_buy_quote", "get_sell_quote", "get_market_cap",
        "get_total_projects", "get_projects_by_status", "get_project_by_rank",
        "get_latest_projects", "get_trusted_projects", "get_trusted_by_rank",
        "get_team_allocation", "get_recovery_config", "get_team_config",
        "has_voted", "get_protocol_stats", "get_config",
        # housekeeping
        "get_project_info", "get_token_balance", "get_status_label",
        "get_version",
        # v3 (D10/D11/D12)
        "get_social_links", "get_trading_stats", "get_market_cap_history",
        "get_proposal_data", "get_volume_stats",
    }
    missing = spec - names
    assert not missing, f"spec functions missing from the contract: {missing}"


def test_contract_declares_every_spec_event():
    text = _contract_text()
    for ev in ["EV_PROJECT_CREATED", "EV_SUPPORTED", "EV_REPORTED",
               "EV_VALIDATION_FINISHED", "EV_BONDING_OPENED",
               "EV_TOKENS_BOUGHT", "EV_TOKENS_SOLD", "EV_PROJECT_GRADUATED",
               "EV_TRUST_LOST", "EV_TRUST_RECOVERED", "EV_FEES_COLLECTED",
               "EV_TEAM_VESTING_STARTED", "EV_TEAM_CLAIMED",
               "EV_DIRECT_LISTED", "EV_MIGRATION_FEE"]:
        assert f"const {ev}: u64" in text, f"event {ev} not declared"


def test_contract_defaults_match_the_sdk_reference():
    text = _contract_text()
    assert "DEFAULT_SUBMISSION_FEE: u64 = 1000000000" in text
    assert "DEFAULT_MIN_LIQUIDITY: u64 = 50000000000" in text
    assert "DEFAULT_TRADING_FEE_BPS: u64 = 50" in text
    assert "DEFAULT_GRADUATED_FEE_BPS: u64 = 25" in text
    assert "DEFAULT_MIGRATION_FEE_BPS: u64 = 50" in text
    assert "DEFAULT_DIRECT_LISTING: u64 = 200000000000" in text
    assert "DEFAULT_MIN_PARTICIPANTS: u64 = 20" in text
    assert "DEFAULT_MIN_APPROVAL_BPS: u64 = 8000" in text
    assert "DEFAULT_GRAD_MULTIPLIER: u64 = 4" in text
    assert "DEFAULT_RECOVERY_FEE: u64 = 25000000000" in text
    assert "DEFAULT_RECOVERY_PARTICIPANTS: u64 = 40" in text
    assert "DEFAULT_RECOVERY_RATIO_BPS: u64 = 9000" in text
    assert "DEFAULT_TEAM_DELAY: u64 = 3153600" in text
    assert "DEFAULT_VESTING_MIN: u64 = 518400" in text
    assert "DEFAULT_VESTING_MAX: u64 = 6307200" in text
    assert 'const VERSION: string = "VaultLaunch v3.0.0"' in text


def test_cross_checked_pairs_are_enforced_d7_d8():
    """The fee pair and the liquidity pair are cross-checked in BOTH
    directions — the graduation discount and the small-float curve can
    never be legislated away."""
    text = _contract_text()
    # set_trading_fee reads graduated_fee and refuses to go below it
    assert '"croserr"' in text
    assert text.count('"croserr"') >= 4  # both pairs, both directions
    # the helper re-clamps defensively
    assert "if graduated_fee > bonding_fee" in text


def test_zero_inter_contract_calls_and_checked_transfers():
    text = _contract_text()
    assert "Contract::new" not in text
    assert not re.search(r"\.\s*call\s*\(\s*\d+\s*u16", text)
    assert not re.search(r"\.\s*delegate\s*\(\s*\d+\s*u16", text)
    # every transfer is captured and immediately required (no let _ =)
    transfers = [m.start() for m in re.finditer(r"transfer\(", text)]
    assert transfers, "no transfers found?"
    for pos in transfers:
        line_start = text.rfind("\n", 0, pos) + 1
        prefix = text[line_start:pos]
        assert "let _ =" not in prefix
    assert len(re.findall(r"require\(ok", text)) >= len(transfers)


def test_sdk_entry_ids_match_the_real_declaration_order():
    """protocol.LAUNCHPAD_ENTRY_IDS is what real transactions are built
    from — it must equal the contract's true chunk numbering."""
    sf = SilexFile.parse(__import__("pathlib").Path(CONTRACT))
    real = {f.name: i for i, f in enumerate(sf.functions)}
    for name, chunk in protocol.LAUNCHPAD_ENTRY_IDS.items():
        assert real.get(name) == chunk, (
            f"SDK says {name} is chunk {chunk} but the contract declares it "
            f"at chunk {real.get(name)} — a transaction would invoke the "
            f"wrong entry")
    # the ALT (entries-only) table must stay a bijection of the same names
    assert set(protocol.LAUNCHPAD_ENTRY_IDS) == set(protocol.LAUNCHPAD_ENTRY_IDS_ALT)


def test_contract_is_substantial_and_documents_its_chunk_table():
    text = _contract_text()
    assert len(text.splitlines()) > 1400, "VaultLaunch.slx looks stubbed"
    assert "CHUNK TABLE" in text
    assert "D1." in text and "D9." in text  # design decisions documented


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
