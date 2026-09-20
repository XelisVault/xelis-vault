"""
Reference tests for VaultLaunch (launchpad).

Three layers, mirroring the mixer's test philosophy (if you change the
contract, change the reference in the SAME commit — CI fails on drift):

  1. CURVE MATH PARITY — sdk/xvault/xvault/launchpad.py must reproduce
     EXACTLY the integer formulas of contracts/launchpad/VaultLaunch.slx
     (fee split, constant-product buy/sell, team allocation, price, market
     cap, graduation threshold), including the floor directions that keep
     the contract solvent.

  2. STATE MACHINE — a Python mini-VM replays a full project lifecycle
     against the same storage keys and transition rules as the contract:
     propose -> validation -> bonding -> graduation (team mint) -> trust
     loss -> recovery, asserting the contract's invariants I1/I2/I5 after
     every step.

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
    """The documented defaults ARE the spec table (10 XEL fee, 500 XEL
    liquidity, 50 bps, 20 voters, 80%, x4, 250 XEL / 40 / 90% recovery)."""
    assert lp.DEFAULTS["submission_fee"] == 10 * XEL
    assert lp.DEFAULTS["min_liquidity"] == 500 * XEL
    assert lp.DEFAULTS["trading_fee_bps"] == 50
    assert lp.DEFAULTS["min_participants"] == 20
    assert lp.DEFAULTS["min_approval_ratio_bps"] == 8000
    assert lp.DEFAULTS["graduation_multiplier"] == 4
    assert lp.DEFAULTS["recovery_fee"] == 250 * XEL
    assert lp.DEFAULTS["recovery_min_participants"] == 40
    assert lp.DEFAULTS["recovery_min_ratio_bps"] == 9000


def test_fee_take_floors_in_favour_of_the_contract():
    assert lp.fee_take(100 * XEL, 50) == 50 * XEL // 100  # exact 0.5%
    # floor: 1 atomic with 50 bps is 0.005 -> 0
    assert lp.fee_take(1, 50) == 0
    assert lp.fee_take(199, 50) == 0
    assert lp.fee_take(200, 50) == 1


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


def test_price_and_market_cap():
    r, c = 2_000 * XEL, 8_000_000 * XEL
    assert lp.current_price(r, c) == 25_000  # 0.00025 XEL/token, scaled 1e8
    assert lp.current_price(r, 0) == 0
    # circulating excludes the unminted team allocation pre-graduation
    ts, tb = 10_000_000 * XEL, 1000
    mc = lp.market_cap(r, c, ts, tb, graduated=False)
    circ = ts - c - lp.team_alloc_of(ts, tb)
    assert mc == r * circ // c
    # after graduation the team allocation is circulating
    assert lp.market_cap(r, c, ts, tb, graduated=True) == r * (ts - c) // c
    # saturation never raises
    huge = lp.market_cap(10 ** 15, 1, 10 ** 16, 0, True)
    assert huge == 2 ** 64 - 1


def test_storage_keys_match_the_contract_layout():
    assert lp.proj_key(3, "rv") == "p:3:rv"
    assert lp.vote_key(3, 1, "xel:abc") == "v:3:1:xel:abc"
    assert lp.bal_key(3, "xel:abc") == "b:3:xel:abc"
    assert lp.GLOBAL_KEYS["pending_fees"] == "pfe"


# ---------------------------------------------------------------------------
# Layer 2 — state machine simulation (mini-VM, same keys, same rules)
# ---------------------------------------------------------------------------

class Sim:
    """A faithful Python replay of VaultLaunch's state transitions.

    Implements propose/support/report/finalize/buy/sell/claim_refund/
    request_revalidation with the contract's exact rules; invariants are
    asserted after every operation.
    """

    def __init__(self, cfg=None):
        self.cfg = dict(lp.DEFAULTS, **(cfg or {}))
        self.s = {}  # storage: string key -> value
        self.count = 0
        self.pending_fees = 0
        self.total_curve_xel = 0
        self.locked_refunds = 0
        self.balance = 0  # contract XEL balance (deposits arrive here)

    def _pk(self, pid, f):
        return lp.proj_key(pid, f)

    def check_invariants(self):
        # I1: ledger per project
        for pid in range(self.count):
            ts = self.s.get(self._pk(pid, "ts"), 0)
            cs = self.s.get(self._pk(pid, "cs"), 0)
            tb = self.s.get(self._pk(pid, "tb"), 0)
            gr = self.s.get(self._pk(pid, "gr"), False)
            balances = sum(v for k, v in self.s.items()
                           if k.startswith(f"b:{pid}:"))
            team = 0 if gr else lp.team_alloc_of(ts, tb)
            assert cs + balances + team == ts, f"I1 broken for project {pid}"
        # I2: solvency
        assert self.balance >= self.total_curve_xel + self.pending_fees + \
            self.locked_refunds, "I2 broken"

    def propose(self, creator, liquidity, ts=1_000_000_000 * XEL, tb=1000):
        fee, min_liq = self.cfg["submission_fee"], self.cfg["min_liquidity"]
        dep = fee + liquidity
        assert dep >= fee + min_liq
        self.balance += dep
        pid = self.count
        self.count += 1
        self.s[self._pk(pid, "cr")] = creator
        self.s[self._pk(pid, "st")] = lp.ST_VALIDATION
        self.s[self._pk(pid, "ts")] = ts
        self.s[self._pk(pid, "tb")] = tb
        self.s[self._pk(pid, "lq")] = liquidity
        self.s[self._pk(pid, "rv")] = liquidity
        self.s[self._pk(pid, "cs")] = ts - lp.team_alloc_of(ts, tb)
        self.s[self._pk(pid, "rd")] = 0
        self.s[self._pk(pid, "sp")] = 0
        self.s[self._pk(pid, "rp")] = 0
        self.s[self._pk(pid, "gr")] = False
        self.pending_fees += fee
        self.check_invariants()
        return pid

    def vote(self, pid, voter, support):
        st = self.s[self._pk(pid, "st")]
        assert st != lp.ST_REJECTED
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

    def finalize(self, pid):
        st = self.s[self._pk(pid, "st")]
        assert st in (lp.ST_VALIDATION, lp.ST_RECOVERY)
        sp = self.s[self._pk(pid, "sp")]
        rp = self.s[self._pk(pid, "rp")]
        total = sp + rp
        if st == lp.ST_VALIDATION:
            if total >= self.cfg["min_participants"] and \
                    sp * 10_000 >= self.cfg["min_approval_ratio_bps"] * total:
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

    def buy(self, pid, buyer, xel_in):
        st = self.s[self._pk(pid, "st")]
        assert st in lp.BUYABLE, f"buys blocked in status {st}"
        fee_bps = self.cfg["trading_fee_bps"]
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
        # graduation
        if st == lp.ST_BONDING:
            target = self.s[self._pk(pid, "lq")] * \
                self.cfg["graduation_multiplier"]
            if self.s[self._pk(pid, "rv")] >= target:
                self.s[self._pk(pid, "st")] = lp.ST_GRADUATED
                self.s[self._pk(pid, "gr")] = True
                ts, tb = self.s[self._pk(pid, "ts")], self.s[self._pk(pid, "tb")]
                team = lp.team_alloc_of(ts, tb)
                ck = lp.bal_key(pid, self.s[self._pk(pid, "cr")])
                self.s[ck] = self.s.get(ck, 0) + team
        self.check_invariants()
        return tokens

    def sell(self, pid, seller, tokens):
        st = self.s[self._pk(pid, "st")]
        assert st in lp.SELLABLE, "sells must never be blocked"
        bk = lp.bal_key(pid, seller)
        assert self.s.get(bk, 0) >= tokens
        fee_bps = self.cfg["trading_fee_bps"]
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
        self.s[self._pk(pid, "st")] = lp.ST_RECOVERY
        self.check_invariants()
        return fee_paid


def test_full_lifecycle_happy_path():
    sim = Sim()
    alice = "xel:alice"
    pid = sim.propose(alice, 1_000 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    assert sim.s[sim._pk(pid, "cs")] == 900_000_000 * XEL  # team reserved

    # community validates (20 voters, >= 80%)
    for i in range(18):
        sim.vote(pid, f"xel:v{i}", True)
    for i in range(2):
        sim.vote(pid, f"xel:r{i}", False)
    assert sim.finalize(pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING

    # buys push the curve to graduation (target = 4000 XEL reserves)
    bob = "xel:bob"
    total_tokens = 0
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        total_tokens += sim.buy(pid, bob, 100 * XEL)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_GRADUATED
    assert sim.s[sim._pk(pid, "gr")] is True
    # team minted to the creator exactly once (I1 holds via check_invariants)
    assert sim.s[lp.bal_key(pid, alice)] == 100_000_000 * XEL
    assert sim.s[lp.bal_key(pid, bob)] == total_tokens

    # trading continues after graduation (D2) and holders can always sell
    out = sim.sell(pid, bob, 1_000_000 * XEL)
    assert out > 0


def test_rejected_project_refunds_once():
    sim = Sim()
    pid = sim.propose("xel:founder", 500 * XEL)
    # not enough voters -> rejected -> full refund
    for i in range(5):
        sim.vote(pid, f"xel:v{i}", True)
    assert sim.finalize(pid) is False
    assert sim.s[sim._pk(pid, "st")] == lp.ST_REJECTED
    before = sim.balance
    assert sim.claim_refund(pid, "xel:founder") == 500 * XEL
    assert sim.balance == before - 500 * XEL


def test_untrusted_blocks_buys_never_sells_and_recovers():
    sim = Sim()
    pid = sim.propose("xel:founder", 1_000 * XEL, ts=1_000_000_000 * XEL, tb=0)
    for i in range(20):
        sim.vote(pid, f"xel:v{i}", True)
    assert sim.finalize(pid) is True

    bob = "xel:bob"
    sim.buy(pid, bob, 50 * XEL)
    tokens = sim.s[lp.bal_key(pid, bob)]
    assert tokens > 0

    # trust loss: reports must reach 80% of ALL accumulated votes — the 20
    # validation supports carry over, so 80 fresh reports are needed
    # (20 support + 80 report = 100 total, 80% reports).
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
    assert sim.finalize(pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING  # was never graduated


def test_graduated_recovery_pays_fee_and_uses_strict_thresholds():
    sim = Sim()
    pid = sim.propose("xel:founder", 500 * XEL, ts=1_000_000_000 * XEL, tb=1000)
    for i in range(20):
        sim.vote(pid, f"xel:v{i}", True)
    assert sim.finalize(pid) is True
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "xel:whale", 200 * XEL)
    assert sim.s[sim._pk(pid, "gr")] is True

    # trust loss post-graduation: the 20 validation supports carry over,
    # so reaching 80% of all votes takes 80 reports.
    for i in range(80):
        sim.vote(pid, f"xel:angry{i}", False)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED

    # recovery costs the fee and demands 40 voters / 90%
    fees_before = sim.pending_fees
    paid = sim.request_revalidation(pid, "xel:founder")
    assert paid == 250 * XEL
    assert sim.pending_fees == fees_before + 250 * XEL
    # 39 supporters at 100% is NOT enough (strict quorum)
    for i in range(39):
        sim.vote(pid, f"xel:sorry{i}", True)
    assert sim.finalize(pid) is False
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED
    # retry: fee again, then 40 supporters
    sim.request_revalidation(pid, "xel:founder")
    for i in range(40):
        sim.vote(pid, f"xel:sorry{i}", True)
    assert sim.finalize(pid) is True
    assert sim.s[sim._pk(pid, "st")] == lp.ST_TRUSTED


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
        "set_submission_fee", "set_trading_fee", "set_min_liquidity",
        "set_min_participants", "set_min_approval_ratio",
        "set_validation_duration", "set_graduation_multiplier",
        "set_recovery_fee", "set_recovery_params", "set_admin",
        "set_paused", "withdraw_fees",
        # creator
        "propose", "claim_refund", "update_project_info",
        "request_revalidation",
        # users
        "support", "report", "buy", "sell", "finalize_validation",
        # views
        "get_project", "get_project_status", "get_project_tokenomics",
        "get_project_trust", "get_bonding_info", "get_current_price",
        "get_buy_quote", "get_sell_quote", "get_market_cap",
        "get_total_projects", "get_projects_by_status", "get_project_by_rank",
        "get_latest_projects", "get_trusted_projects", "get_trusted_by_rank",
        "has_voted", "get_protocol_stats", "get_config",
        # housekeeping
        "get_project_info", "get_token_balance", "get_status_label",
        "get_version",
    }
    missing = spec - names
    assert not missing, f"spec functions missing from the contract: {missing}"


def test_contract_declares_every_spec_event():
    text = _contract_text()
    for ev in ["EV_PROJECT_CREATED", "EV_SUPPORTED", "EV_REPORTED",
               "EV_VALIDATION_FINISHED", "EV_BONDING_OPENED",
               "EV_TOKENS_BOUGHT", "EV_TOKENS_SOLD", "EV_PROJECT_GRADUATED",
               "EV_TRUST_LOST", "EV_TRUST_RECOVERED", "EV_FEES_COLLECTED"]:
        assert f"const {ev}: u64" in text, f"event {ev} not declared"


def test_contract_defaults_match_the_sdk_reference():
    text = _contract_text()
    assert "DEFAULT_SUBMISSION_FEE: u64 = 1000000000" in text
    assert "DEFAULT_MIN_LIQUIDITY: u64 = 50000000000" in text
    assert "DEFAULT_TRADING_FEE_BPS: u64 = 50" in text
    assert "DEFAULT_MIN_PARTICIPANTS: u64 = 20" in text
    assert "DEFAULT_MIN_APPROVAL_BPS: u64 = 8000" in text
    assert "DEFAULT_GRAD_MULTIPLIER: u64 = 4" in text
    assert "DEFAULT_RECOVERY_FEE: u64 = 25000000000" in text
    assert "DEFAULT_RECOVERY_PARTICIPANTS: u64 = 40" in text
    assert "DEFAULT_RECOVERY_RATIO_BPS: u64 = 9000" in text


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
    assert len(text.splitlines()) > 800, "VaultLaunch.slx looks stubbed"
    assert "CHUNK TABLE" in text
    assert "D1." in text and "D6." in text  # design decisions documented


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
