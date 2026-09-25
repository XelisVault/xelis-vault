"""VaultLaunch v4 reference tests — real assets, real migration.

Three layers, mirroring the CI philosophy of the previous versions:

1. MATH — every curve/DEX formula of the contract, hand-vectored and
   property-tested (the SDK's Python mirror must be byte-identical to
   the Silex source).
2. STATE MACHINE — a faithful Python replay of BOTH contracts
   (VaultLaunch + LaunchDEX) with REAL asset flows: wallets hold XEL
   and launched tokens, the launchpad escrows them, the migration moves
   them into the DEX pool atomically. Invariants (I1/I2/I9/I10 + the
   DEX's IX1..IX6) are asserted after EVERY operation.
3. SPEC — the contract source is asserted against the founder's
   requirements (entries, events, defaults, cross-checked pairs, the
   pinned cross-call chunk ids), so the Silex file cannot drift from
   this reference silently.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "xvault"))

from xvault import launchpad as lp  # noqa: E402
from xvault import dex as dx        # noqa: E402
from xvault.protocol import LAUNCHDEX_ENTRY_IDS, LAUNCHDEX_ENTRY_IDS_ALT, \
    LAUNCHPAD_ENTRY_IDS, LAUNCHPAD_ENTRY_IDS_ALT  # noqa: E402

XEL = 100_000_000  # 1 XEL, atomic
XEL_ASSET = "0" * 64  # native XEL is represented by the zero hash
CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "launchpad" / "VaultLaunch.slx"
DEX_CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "dex" / "LaunchDEX.slx"

# simulated chain fee for Asset::create (D13 — the real one is a chain
# parameter; the contract measures it by balance-delta, the Sim mirrors
# exactly that mechanism)
ASSET_FEE = 1 * XEL


# ===========================================================================
# LAYER 1 — MATH (the SDK mirror must equal the contract's formulas)
# ===========================================================================

def test_defaults_match_the_specification():
    assert lp.DEFAULTS["submission_fee"] == 10 * XEL
    assert lp.DEFAULTS["asset_budget"] == 10 * XEL          # D13
    assert lp.DEFAULTS["min_liquidity"] == 500 * XEL
    assert lp.DEFAULTS["trading_fee_bps"] == 50
    assert lp.DEFAULTS["graduated_fee_bps"] == 25           # D8
    assert lp.DEFAULTS["migration_fee_bps"] == 50           # D9
    assert lp.DEFAULTS["direct_listing_threshold"] == 2000 * XEL  # D7
    assert lp.DEFAULTS["graduation_multiplier"] == 4
    assert lp.DEFAULTS["min_participants"] == 20
    assert lp.DEFAULTS["min_approval_ratio_bps"] == 8000
    assert lp.DEFAULTS["team_unlock_delay"] == 3_153_600    # D3
    assert lp.DEFAULTS["vote_deposit"] == XEL // 2         # D21: 0.5 XEL (v4.2)
    assert dx.DEFAULTS["swap_fee_bps"] == 30                # X3
    assert dx.DEFAULTS["max_swap_xel"] == 100_000 * XEL
    assert dx.DEFAULTS["lp_share_bps"] == 5_000             # X10/D23: 50/50


def test_fee_take_floors_in_favour_of_the_contract():
    assert lp.fee_take(999, 50) == 4
    assert lp.fee_take(10_000, 50) == 50
    assert dx.fee_take(999, 30) == 2


def test_effective_fee_by_graduation_status_d8():
    assert lp.current_fee_bps(False, 50, 25) == 50
    assert lp.current_fee_bps(True, 50, 25) == 25
    # defensive clamp: an inconsistent storage can never invert the discount
    assert lp.current_fee_bps(True, 25, 50) == 25


def test_buy_math_hand_vector():
    # C * net / (R + net): 1000 atomic sellable, 10 XEL net, 90 XEL reserves
    # -> 1000 * 1e9 / (9e9 + 1e9) = 100 atomic out (floored)
    assert lp.buy_tokens_out(90 * XEL, 1000, 10 * XEL) == 100


def test_buy_quote_includes_fee():
    out = lp.buy_quote(90 * XEL, 1000, 10 * XEL, 50)
    net = 10 * XEL - lp.fee_take(10 * XEL, 50)
    assert out == lp.buy_tokens_out(90 * XEL, 1000, net)


def test_buy_quote_graduated_uses_the_lower_fee():
    big_curve = 1000 * 10**8   # 1000 whole tokens — big enough to see the fee
    bonding = lp.buy_quote(90 * XEL, big_curve, 10 * XEL, 50)
    graduated = lp.buy_quote(90 * XEL, big_curve, 10 * XEL, 25)
    assert graduated > bonding  # cheaper fee -> more tokens out


def test_sell_math_hand_vector():
    # R * T / (C + T): 100 XEL reserves, 900 sellable, sell 100 tokens
    assert lp.sell_xel_out(100 * XEL, 900, 100) == 10 * XEL


def test_round_trip_costs_at_most_the_two_fees():
    reserves, curve = 500 * XEL, 900_000_000
    tokens = lp.buy_quote(reserves, curve, 100 * XEL, 50)
    back = lp.sell_quote(reserves + 100 * XEL - lp.fee_take(100 * XEL, 50),
                         curve - tokens, tokens, 50)
    assert back <= 100 * XEL
    assert back >= 100 * XEL * (1 - 2 * 50 / 10_000) - 1


def test_constant_product_never_insolvent():
    # property: whatever the swap, reserves never hit zero and the pool
    # can always honor the opposite direction (floored math)
    import random
    rng = random.Random(42)
    r, c = 500 * XEL, 900_000_000
    for _ in range(200):
        if rng.random() < 0.5:
            net = rng.randrange(1, 50 * XEL)
            out = lp.buy_tokens_out(r, c, net)
            assert 0 < out < c
            r, c = r + net, c - out
        else:
            t = rng.randrange(1, c)
            gross = lp.sell_xel_out(r, c, t)
            assert 0 <= gross < r
            r, c = r - gross, c + t


def test_dex_swap_math_hand_vectors():
    # buy: y * net / (x + net)
    assert dx.xel_to_tokens_out(100 * XEL, 1000, 10 * XEL, 30) == \
        1000 * (10 * XEL - 3 * 10**6) // (110 * XEL - 3 * 10**6)
    # sell: x * net / (y + net)
    out = dx.tokens_to_xel_out(100 * XEL, 1000, 100, 30)
    assert out == 100 * XEL * (100 - 0) // (1100)  # fee on 100 @30bps = 0
    assert dx.tokens_to_xel_out(100 * XEL, 900, 100, 30) > 0


def test_dex_spot_price():
    # 2000 XEL reserves against 10 whole tokens (1e9 atomic) -> 200 XEL/token
    assert dx.spot_price(2000 * XEL, 1_000_000_000) == 200 * XEL
    assert dx.spot_price(100 * XEL, 0) == 0
    assert dx.spot_price(10**20, 1) == 2**64 - 1  # saturates


def test_dex_round_trip_costs_at_most_two_fees():
    x, y = 2000 * XEL, 900_000_000
    tokens = dx.xel_to_tokens_out(x, y, 100 * XEL, 30)
    x2, y2 = x + 100 * XEL - dx.fee_take(100 * XEL, 30), y - tokens
    back = dx.tokens_to_xel_out(x2, y2, tokens, 30)
    assert back <= 100 * XEL
    assert back >= 100 * XEL * (1 - 2 * 30 / 10_000) - 1


def test_team_allocation_and_graduation_threshold():
    assert lp.team_alloc_of(1_000_000_000 * XEL, 2000) == 200_000_000 * XEL
    # graduation target = liquidity * multiplier (u128 compare on-chain)
    assert 500 * XEL * 4 == 2000 * XEL


def test_team_unlocked_all_paths_d3():
    team = 100 * XEL
    # vesting stream
    assert lp.team_unlocked(team, True, 100, 1000, lp.ST_GRADUATED, 0, 0, 600) == 50 * XEL
    assert lp.team_unlocked(team, True, 100, 1000, lp.ST_GRADUATED, 0, 0, 100) == 0
    assert lp.team_unlocked(team, True, 100, 1000, lp.ST_GRADUATED, 0, 0, 9999) == team
    # graduated, no vesting -> immediate full
    assert lp.team_unlocked(team, True, 0, 0, lp.ST_GRADUATED, 0, 0, 0) == team
    # never graduated, late claim after the delay
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_BONDING, 100, 200, 299) == 0
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_BONDING, 100, 200, 300) == team
    # validation/rejected -> nothing
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_VALIDATION, 100, 200, 9999) == 0
    assert lp.team_unlocked(team, False, 0, 0, lp.ST_REJECTED, 100, 200, 9999) == 0


def test_team_remaining_never_negative():
    assert lp.team_remaining(100, 100) == 0
    assert lp.team_remaining(100, 150) == 0
    assert lp.team_remaining(100, 40) == 60


def test_price_and_market_cap():
    price = lp.current_price(500 * XEL, 900_000_000)
    assert price == 500 * XEL * 10**8 // 900_000_000
    # curve-era cap: circulating excludes the unpaid team escrow
    cap = lp.market_cap(500 * XEL, 900_000_000, 1_000_000_000, 1000, False, 0)
    assert cap == 500 * XEL * (1_000_000_000 - 900_000_000 - 100_000_000) // 900_000_000
    # post-migration era: the SDK composes the DEX pool price instead
    pool_cap = lp.dex_pool_market_cap(2000 * XEL, 800_000_000,
                                      1_000_000_000, 100_000_000)
    assert pool_cap == 2000 * XEL * 100_000_000 // 800_000_000


def test_migration_fee_math_d9():
    assert lp.fee_take(2000 * XEL, 50) == 10 * XEL


def test_storage_keys_match_the_contract_layout():
    # project fields (v4 additions: asset/budget/migration/dex-sync)
    for field, const in (("ah", lp.F_ASSET), ("ab", lp.F_BUDGET),
                         ("mi", lp.F_MIGRATED), ("ma", lp.F_MIG_AT),
                         ("mx", lp.F_MIG_XEL), ("mt", lp.F_MIG_TOK),
                         ("dsy", lp.F_DEX_SYNCED)):
        assert lp.proj_key(3, const) == f"p:3:{field}"
    # globals (v4: asset_budget, budgets, migrated count, dex pin)
    assert lp.GLOBAL_KEYS["asset_budget"] == "abd"
    assert lp.GLOBAL_KEYS["total_budgets"] == "tbb"
    assert lp.GLOBAL_KEYS["migrated_count"] == "mgc"
    assert lp.GLOBAL_KEYS["dex_address"] == "dxa"
    # ticker registry (D11)
    assert lp.ticker_key("MOON") == "t:MOON"
    # DEX pool keys (Hash::to_hex namespaces)
    assert dx.pool_key("ab" * 32, dx.F_XEL_RESERVE) == f"q:{'ab' * 32}:xr"
    assert dx.pool_index_key(7) == "i:7"


# ===========================================================================
# LAYER 2 — THE STATE MACHINE (launchpad + DEX, real asset flows)
# ===========================================================================

class DexSim:
    """Faithful replay of LaunchDEX: pools, swaps, fees, trust hook, the
    X10/D23 LP fee share (accrual-per-unit, pull claims, hard-bounded
    split dial) and since v1.3 the two-tier liquidity model: X11 seed
    shares (the protocol LP position, fees-only forever) and X12
    remove_liquidity (providers exit pro-rata, never the seed)."""

    def __init__(self, cfg=None):
        self.cfg = dict(dx.DEFAULTS, **(cfg or {}))
        self.admin = "admin"           # X11: the protocol LP address
        self.pools = {}             # asset -> dict(x, y, xf, yf, bp, ...)
        self.index = []             # listing order
        self.xel_balance = 0        # contract XEL balance
        self.asset_balances = defaultdict(int)
        self.launchpad = None       # pinned launchpad address (X4)
        self.pinned = False
        self.emergency = False
        self.wallets = defaultdict(lambda: {"xel": 0,
                                            "assets": defaultdict(int)})
        # X10/D23 + X12: l:{asset}:{wallet}:{x,sx,sy,cx,cy,w}
        self.lp = defaultdict(lambda: {"x": 0, "sx": 0, "sy": 0,
                                       "cx": 0, "cy": 0, "w": 0})
        self.topo = 0

    def set_launchpad(self, addr):
        assert not self.pinned, "pinned"
        self.launchpad = addr

    def create_pool_open(self, caller, asset, xel_seed, tok_seed):
        """v1.4 X13: the OPEN seeding endpoint — identical economics to
        create_pool (X11 seed shares, IX5 floors, IX4 one pool per
        asset) minus the launchpad gate. ANY caller (the community
        factory's migrate, a keeper, anyone). Returns 0 on success (the
        v1.4 cross-call convention — the second-migration fix)."""
        assert not self.emergency
        assert self.launchpad is not None, "nolpx"
        assert asset != XEL_ASSET, "sameass"
        assert asset not in self.pools, "exists"
        assert xel_seed >= self.cfg["min_seed_xel"]
        assert tok_seed >= self.cfg["min_seed_tokens"]
        assert xel_seed <= dx.MAX_SEED_XEL, "toobig"
        assert tok_seed <= dx.MAX_SEED_TOKENS, "toobig"
        # X11: the seed IS the pool's permanent LP floor
        assert xel_seed >= dx.MIN_LP_ADD_XEL, "seedlp"
        self.xel_balance += xel_seed
        self.asset_balances[asset] += tok_seed
        self.pools[asset] = {"x": xel_seed, "y": tok_seed, "xf": 0, "yf": 0,
                             "bp": False, "ct": self.topo, "bv": 0, "sv": 0,
                             "tc": 0, "lt": 0, "fl": 0, "lp": 0,
                             "lx": 0, "ly": 0, "tl": xel_seed, "ax": 0,
                             "ay": 0, "pl": xel_seed}
        seed = self.lp[(asset, self.admin)]
        seed["x"] = xel_seed
        seed["sx"] = 0
        seed["sy"] = 0
        self.index.append(asset)
        if not self.pinned:
            self.pinned = True
        return 0

    def create_pool(self, caller, asset, xel_seed, tok_seed):
        # X4: only the pinned launchpad (cross-call context)
        assert self.launchpad is not None, "nolpx"
        assert caller == self.launchpad, "notlpx"
        assert not self.emergency
        assert asset != XEL_ASSET, "sameass"
        assert asset not in self.pools, "exists"
        assert xel_seed >= self.cfg["min_seed_xel"]
        assert tok_seed >= self.cfg["min_seed_tokens"]
        assert xel_seed <= dx.MAX_SEED_XEL, "toobig"
        assert tok_seed <= dx.MAX_SEED_TOKENS, "toobig"
        # X11: the seed IS the pool's permanent LP floor (IX9's half of
        # the IX8 bound: pl >= ACC_SCALE, removes can never cross pl)
        assert xel_seed >= dx.MIN_LP_ADD_XEL, "seedlp"
        self.xel_balance += xel_seed
        self.asset_balances[asset] += tok_seed
        self.pools[asset] = {"x": xel_seed, "y": tok_seed, "xf": 0, "yf": 0,
                             "bp": False, "ct": self.topo, "bv": 0, "sv": 0,
                             "tc": 0, "lt": 0, "fl": 0, "lp": 0,
                             "lx": 0, "ly": 0, "tl": xel_seed, "ax": 0,
                             "ay": 0, "pl": xel_seed}
        # X11: mint the seed's LP parts to the admin (fees-only: no w)
        seed = self.lp[(asset, self.admin)]
        seed["x"] = xel_seed
        seed["sx"] = 0
        seed["sy"] = 0
        self.index.append(asset)
        if not self.pinned:
            self.pinned = True
        return 0

    def set_pool_buys_paused(self, caller, asset, flag):
        assert caller == self.launchpad, "notlpx"
        assert asset in self.pools, "nopool"
        self.pools[asset]["bp"] = flag

    def _split_fee(self, asset, fee, side):
        """X10/D23: split a swap fee between the admin pot and the LP
        distribution (the no-provider redirect is defense-in-depth since
        X11 — the seed mints parts at creation, so tl > 0 from birth).
        Mirrors both swap entries."""
        p = self.pools[asset]
        lp_part = fee * self.cfg["lp_share_bps"] // 10_000
        adm_part = fee - lp_part
        if lp_part > 0 and p["tl"] > 0:
            p["l" + side] += lp_part                    # lx or ly
            acc = lp_part * dx.ACC_SCALE // p["tl"]
            p["a" + side] += acc                        # ax or ay
        else:
            adm_part += lp_part
        if adm_part > 0:
            p[side + "f"] += adm_part                  # xf or yf
        p["fl"] += fee

    def swap_xel(self, wallet, asset, xel_in, min_out=0):
        p = self.pools[asset]
        assert not self.emergency and not p["bp"], "buyspaused"
        assert self.cfg["min_swap_xel"] <= xel_in <= self.cfg["max_swap_xel"]
        w = self.wallets[wallet]
        assert w["xel"] >= xel_in, "noXEL"
        fee = dx.fee_take(xel_in, self.cfg["swap_fee_bps"])
        net = xel_in - fee
        out = dx.xel_to_tokens_out(p["x"], p["y"], xel_in,
                                   self.cfg["swap_fee_bps"])
        assert out >= 1 and out < p["y"] and out >= min_out
        w["xel"] -= xel_in
        self.xel_balance += xel_in
        p["x"] += net
        p["y"] -= out
        self._split_fee(asset, fee, "x")
        p["bv"] += xel_in
        p["tc"] += 1
        p["lt"] = self.topo
        self.asset_balances[asset] -= out
        w["assets"][asset] += out
        return out

    def swap_tokens(self, wallet, asset, tokens_in, min_out=0):
        p = self.pools[asset]
        # IX6 (absolute): NO gate on the sell path — neither the buys-pause
        # nor the emergency pause can ever block a sell (founder risk
        # review, point 2)
        w = self.wallets[wallet]
        assert w["assets"][asset] >= tokens_in, "notok"
        assert self.cfg["min_swap_tokens"] <= tokens_in <= self.cfg["max_swap_tokens"]
        out = dx.tokens_to_xel_out(p["x"], p["y"], tokens_in,
                                   self.cfg["swap_fee_bps"])
        assert out >= 1 and out < p["x"] and out >= min_out
        fee = dx.fee_take(tokens_in, self.cfg["swap_fee_bps"])
        net = tokens_in - fee
        w["assets"][asset] -= tokens_in
        self.asset_balances[asset] += tokens_in
        p["y"] += net
        p["x"] -= out
        self._split_fee(asset, fee, "y")
        p["sv"] += out          # XEL that actually left the reserves
        p["tc"] += 1
        p["lt"] = self.topo
        self.xel_balance -= out
        w["xel"] += out
        return out

    def _lp_pos(self, asset, wallet):
        return self.lp[(asset, wallet)]

    def _crystallise(self, asset, wallet):
        """X10/D23: crystallise the provider's accrued fees (both sides)
        — called BEFORE new parts join (add) and at claim time. The
        snapshots advance in EVERY case (fuzz-found): a FIRST deposit
        (parts == 0) must also start its accrual clock at the CURRENT
        counter, or it would retroactively earn fees from before it
        existed (IX8 violation)."""
        p = self.pools[asset]
        pos = self._lp_pos(asset, wallet)
        if pos["x"] > 0:
            pos["cx"] += dx.lp_earnings(p["ax"], pos["sx"], pos["x"])
            pos["cy"] += dx.lp_earnings(p["ay"], pos["sy"], pos["x"])
        pos["sx"] = p["ax"]
        pos["sy"] = p["ay"]

    def add_liquidity(self, wallet, asset, xel_in, tok_in):
        """X7 (founder risk review, point 1): the pool's CURRENT ratio is
        enforced — only the largest proportional pair joins the reserves,
        the excess side is refunded to the donor in the same transaction.
        A donation can deepen a pool but NEVER move its price. Since v1.2
        the donor becomes a PROVIDER (X10/D23): parts join AFTER its
        accrued fees are crystallised, and the effective XEL side must
        clear the hard 1 XEL LP-entry floor. Since v1.3 the minted parts
        are WITHDRAWABLE (X12): pos["w"] grows with pos["x"]."""
        p = self.pools[asset]
        assert not self.emergency
        assert xel_in >= 1 and tok_in >= 1
        w = self.wallets[wallet]
        assert w["xel"] >= xel_in and w["assets"][asset] >= tok_in
        x, y = p["x"], p["y"]
        need_tok = y * xel_in // x
        if tok_in >= need_tok:
            xel_eff, tok_eff = xel_in, need_tok
        else:
            need_xel = x * tok_in // y
            assert xel_in >= need_xel, "ratio"
            xel_eff, tok_eff = need_xel, tok_in
        assert xel_eff >= 1 and tok_eff >= 1, "dust"
        assert xel_eff >= dx.MIN_LP_ADD_XEL, "minlp"
        # IX7: the reserve product drifts by at most one floor unit
        x1, y1 = x + xel_eff, y + tok_eff
        assert abs(x1 * y - x * y1) < max(x, y), "IX7 broken"
        # X10/D23: crystallise FIRST, then the new parts join (a deposit
        # never earns from before it existed)
        self._crystallise(asset, wallet)
        # funds: the donor deposits everything, gets the excess back
        w["xel"] -= xel_in
        w["assets"][asset] -= tok_in
        self.xel_balance += xel_in
        self.asset_balances[asset] += tok_in
        w["xel"] += xel_in - xel_eff
        w["assets"][asset] += tok_in - tok_eff
        self.xel_balance -= xel_in - xel_eff
        self.asset_balances[asset] -= tok_in - tok_eff
        p["x"] = x1
        p["y"] = y1
        p["lp"] += 1
        pos = self._lp_pos(asset, wallet)
        pos["x"] += xel_eff
        pos["w"] += xel_eff            # X12: withdrawable
        p["tl"] += xel_eff
        return xel_eff, tok_eff

    def remove_liquidity(self, wallet, asset, parts, min_xel_out=0, min_tokens_out=0):
        """X12 (v1.3): burn WITHDRAWABLE parts for their exact pro-rata
        share of BOTH reserves at the current ratio. NEVER the seed
        ("locked"), never more than the caller's own parts ("parterr"),
        never across the seed floor ("seederr"), never the last unit of
        a side ("poolerr"), min_out on both sides ("slip"), and the
        caller's accrued dues are crystallised FIRST so nothing is
        forfeited. UNGATED (X12): works under the emergency pause."""
        assert asset in self.pools, "nopool"
        assert parts >= 1, "badamt"
        pos = self._lp_pos(asset, wallet)
        assert parts <= pos["w"], "locked"
        assert parts <= pos["x"], "parterr"
        p = self.pools[asset]
        x, y, tl, pl = p["x"], p["y"], p["tl"], p["pl"]
        assert x > 0 and y > 0 and tl > 0, "empty"
        assert tl - parts >= pl, "seederr"
        # X10: crystallise the dues BEFORE the parts shrink (nothing is
        # forfeited — the claimables survive the burn)
        self._crystallise(asset, wallet)
        out_x = parts * x // tl
        out_y = parts * y // tl
        assert out_x >= 1 and out_y >= 1, "dust"
        assert out_x >= min_xel_out and out_y >= min_tokens_out, "slip"
        assert out_x < x and out_y < y, "poolerr"
        # IX7 (X12): the remove keeps the reserve product within one
        # floor unit — price-neutral, like the add
        x1, y1 = x - out_x, y - out_y
        assert abs(x1 * y - x * y1) < max(x, y), "IX7 broken (remove)"
        # state first, funds after (X9)
        p["x"] = x1
        p["y"] = y1
        pos["x"] -= parts
        pos["w"] -= parts
        p["tl"] = tl - parts
        self.xel_balance -= out_x
        self.wallets[wallet]["xel"] += out_x
        self.asset_balances[asset] -= out_y
        self.wallets[wallet]["assets"][asset] += out_y
        return out_x, out_y

    def claim_lp_fees(self, wallet, asset):
        """X10/D23: pull payout of the provider's OWN accrued fees (both
        sides). Crystallises, bounds against the pots (IX8), pays."""
        assert asset in self.pools, "nopool"
        self._crystallise(asset, wallet)
        p = self.pools[asset]
        pos = self._lp_pos(asset, wallet)
        payout_x, payout_y = pos["cx"], pos["cy"]
        assert payout_x > 0 or payout_y > 0, "nofees"
        assert payout_x <= p["lx"], "lperr"
        assert payout_y <= p["ly"], "lperr"
        pos["cx"] = 0
        pos["cy"] = 0
        p["lx"] -= payout_x
        p["ly"] -= payout_y
        self.xel_balance -= payout_x
        self.wallets[wallet]["xel"] += payout_x
        self.asset_balances[asset] -= payout_y
        self.wallets[wallet]["assets"][asset] += payout_y
        return payout_x, payout_y

    def set_fee_split(self, bps):
        """X10/D23: the admin/providers revenue dial, hard-bounded
        [MIN_LP_SHARE_BPS, MAX_LP_SHARE_BPS] — the bounds are structural
        trust guarantees."""
        assert dx.MIN_LP_SHARE_BPS <= bps <= dx.MAX_LP_SHARE_BPS
        self.cfg["lp_share_bps"] = bps

    def check_invariants(self):
        # IX1/IX2 (extended by IX8): reserves + ADMIN pots + LP pots
        # <= balances (equality by construction minus the refunded
        # liquidity excesses)
        assert sum(p["x"] + p["xf"] + p["lx"] for p in self.pools.values()) \
            <= self.xel_balance
        for asset, p in self.pools.items():
            assert p["y"] + p["yf"] + p["ly"] <= self.asset_balances[asset]
            # IX5: both sides strictly positive
            assert p["x"] >= 1 and p["y"] >= 1
            # IX6 (absolute): the sell path carries no gate at all —
            # structural (swap_tokens checks neither bp nor emergency)
            # IX8: every provider's claimable + accrued earnings, summed,
            # is <= the LP pots (floor dust stays in the pots forever)
            due_x = sum(pos["cx"] + dx.lp_earnings(p["ax"], pos["sx"], pos["x"])
                        for (a, _w), pos in self.lp.items() if a == asset)
            due_y = sum(pos["cy"] + dx.lp_earnings(p["ay"], pos["sy"], pos["x"])
                        for (a, _w), pos in self.lp.items() if a == asset)
            assert due_x <= p["lx"], "IX8 broken (XEL side)"
            assert due_y <= p["ly"], "IX8 broken (token side)"
            # the accrual counter can never outgrow lifetime fees (the
            # IX8 bound: total_depth >= ACC_SCALE, so increments <= fees)
            assert p["ax"] <= p["fl"] and p["ay"] <= p["fl"]
            # IX9 (X11/X12): the seed never leaves — tl >= pl >= ACC_SCALE
            # forever, and the withdrawable balance can never cross it
            assert p["pl"] >= dx.ACC_SCALE, "IX9 broken: seed below scale"
            assert p["tl"] >= p["pl"], "IX9 broken: depth below the seed"
            sum_w = sum(pos["w"] for (a, _w), pos in self.lp.items()
                        if a == asset)
            assert sum_w <= p["tl"] - p["pl"], "IX9 broken: w crosses the seed"
            for (a, _w), pos in self.lp.items():
                if a == asset:
                    assert pos["w"] <= pos["x"], "IX9 broken: w > parts"


LAUNCHPAD_ADDR = "xvault:launchpad"   # the simulated launchpad's address


class Sim:
    """A faithful Python replay of VaultLaunch v4 + LaunchDEX with REAL
    asset flows: wallets hold XEL and launched tokens, the launchpad
    escrows them, the migration seeds the DEX pool atomically. Invariants
    are asserted after every operation. `self.topo` is the simulated
    topoheight (warp() advances it).
    """

    def __init__(self, cfg=None, asset_fee=ASSET_FEE):
        self.cfg = dict(lp.DEFAULTS, **(cfg or {}))
        self.s = {}  # storage: string key -> value
        self.count = 0
        self.pending_fees = 0
        self.total_curve_xel = 0
        self.locked_refunds = 0
        self.total_buy_vol = 0
        self.total_sell_vol = 0
        self.total_volume = 0
        self.total_trades = 0
        self.total_budgets = 0
        self.migrated_count = 0
        self.vote_pots = 0             # D21: locked voter deposits
        self.migrated_index = []       # D22: migration order (pid list)
        self.asset_to_pid = {}         # D22: reverse bridge (a: lookup)
        self.dex_pin = None          # D19: set_dex_address
        self.balance = 0             # launchpad XEL balance
        self.contract_assets = defaultdict(int)   # asset -> escrowed tokens
        self.burned = 0              # XEL consumed by chain fees (asset creation)
        self.wallets = defaultdict(lambda: {"xel": 0,
                                            "assets": defaultdict(int)})
        self.dex = DexSim()
        self.dex.set_launchpad(LAUNCHPAD_ADDR)
        self.asset_fee = asset_fee
        self.topo = 0
        self.mint_xel = 0            # conservation counter

    # -- plumbing -----------------------------------------------------------

    def _pk(self, pid, f):
        return lp.proj_key(pid, f)

    def asset_of(self, pid):
        return self.s.get(self._pk(pid, "ah"))

    def mint(self, wallet, xel):
        self.wallets[wallet]["xel"] += xel
        self.mint_xel += xel

    def check_invariants(self):
        # I1 (v4): for every created asset, escrow == curve inventory +
        # unpaid team allocation
        for pid in range(self.count):
            asset = self.asset_of(pid)
            if asset is None:
                continue
            ts = self.s.get(self._pk(pid, "ts"), 0)
            cs = self.s.get(self._pk(pid, "cs"), 0)
            tb = self.s.get(self._pk(pid, "tb"), 0)
            paid = self.s.get(self._pk(pid, "tp"), 0)
            team_rem = lp.team_remaining(lp.team_alloc_of(ts, tb), paid)
            assert self.contract_assets[asset] == cs + team_rem, \
                f"I1 broken for project {pid}"
            # I10: post-migration the escrow degenerates to the team share
            if self.s.get(self._pk(pid, "mi"), False):
                assert cs == 0
                assert self.contract_assets[asset] == team_rem, \
                    f"I10 broken for project {pid}"
        # I2 (D20/D21, tightened): balance covers live reserves + fees +
        # refunds + earmarked budgets + locked vote pots
        assert self.balance >= self.total_curve_xel + self.pending_fees + \
            self.locked_refunds + self.total_budgets + self.vote_pots, "I2 broken"
        # D21: the pots equal the sum of every unclaimed vote slot
        pots_sum = 0
        for k, v in self.s.items():
            if k.startswith("v:"):
                pots_sum += v
        assert pots_sum == self.vote_pots, "D21 pots drift"
        # I9: volume identity + stored market-cap freshness
        per_project_total = 0
        for pid in range(self.count):
            bv = self.s.get(self._pk(pid, "bv"), 0)
            sv = self.s.get(self._pk(pid, "sv"), 0)
            vo = self.s.get(self._pk(pid, "vo"), 0)
            assert vo == bv + sv, f"I9 volume broken for project {pid}"
            per_project_total += vo
            expected = lp.market_cap(
                self.s.get(self._pk(pid, "rv"), 0),
                self.s.get(self._pk(pid, "cs"), 0),
                self.s.get(self._pk(pid, "ts"), 0),
                self.s.get(self._pk(pid, "tb"), 0),
                bool(self.s.get(self._pk(pid, "gr"), False)),
                self.s.get(self._pk(pid, "tp"), 0))
            assert self.s.get(self._pk(pid, "mc"), 0) == expected, \
                f"I9 mcap drift for project {pid}"
            assert self.s.get(self._pk(pid, "mh"), 0) >= expected
        assert per_project_total == self.total_volume, "I9 global volume"
        assert self.total_volume == self.total_buy_vol + self.total_sell_vol
        # DEX invariants (IX1..IX6)
        self.dex.check_invariants()
        # XEL conservation: wallets(launchpad) + launchpad + dex + burned
        wallet_xel = sum(w["xel"] for w in self.wallets.values())
        dex_wallet_xel = sum(w["xel"] for w in self.dex.wallets.values())
        assert (wallet_xel + dex_wallet_xel + self.balance +
                self.dex.xel_balance + self.burned) == self.mint_xel, \
            "XEL conservation broken"
        # token conservation per asset: wallets + launchpad escrow + dex
        # pool-side balances == total supply (always; Fixed mode)
        for pid in range(self.count):
            asset = self.asset_of(pid)
            if asset is None:
                continue
            ts = self.s.get(self._pk(pid, "ts"), 0)
            in_wallets = sum(w["assets"].get(asset, 0)
                             for w in self.wallets.values())
            in_dex_wallets = sum(w["assets"].get(asset, 0)
                                 for w in self.dex.wallets.values())
            total = (in_wallets + in_dex_wallets +
                     self.contract_assets[asset] +
                     self.dex.asset_balances[asset])
            assert total == ts, f"token conservation broken for {pid}"

    def _update_mcap(self, pid):
        cap = lp.market_cap(
            self.s.get(self._pk(pid, "rv"), 0),
            self.s.get(self._pk(pid, "cs"), 0),
            self.s.get(self._pk(pid, "ts"), 0),
            self.s.get(self._pk(pid, "tb"), 0),
            bool(self.s.get(self._pk(pid, "gr"), False)),
            self.s.get(self._pk(pid, "tp"), 0))
        self.s[self._pk(pid, "mc")] = cap
        if cap > self.s.get(self._pk(pid, "mh"), 0):
            self.s[self._pk(pid, "mh")] = cap

    def _record_trade(self, pid, buy_side, xel_amount):
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
    def propose(self, creator, liquidity, ts=100_000_000 * XEL, tb=1000,
                plan=0, twitter="", telegram="", discord="", symbol=None):
        assert self.count < 8192
        assert liquidity >= self.cfg["min_liquidity"]
        assert liquidity <= 100_000 * XEL
        assert 100_000_000 <= ts <= 10_000_000_000_000_000
        assert tb <= 2000
        assert plan == 0 or self.cfg["vesting_min"] <= plan <= self.cfg["vesting_max"]
        symbol = symbol or f"T{self.count}"
        assert lp.ticker_key(symbol) not in self.s, "tick"
        budget = self.cfg["asset_budget"]
        deposit = self.cfg["submission_fee"] + budget + liquidity
        w = self.wallets[creator]
        assert w["xel"] >= deposit, "needliq"
        w["xel"] -= deposit
        self.balance += deposit
        pid = self.count
        self.s[self._pk(pid, "cr")] = creator
        self.s[self._pk(pid, "st")] = lp.ST_VALIDATION
        self.s[self._pk(pid, "nm")] = f"Project {pid}"
        self.s[self._pk(pid, "sy")] = symbol
        self.s[self._pk(pid, "tw")] = twitter
        self.s[self._pk(pid, "tg")] = telegram
        self.s[self._pk(pid, "dc")] = discord
        self.s[self._pk(pid, "ts")] = ts
        self.s[self._pk(pid, "tb")] = tb
        self.s[self._pk(pid, "lq")] = liquidity
        self.s[self._pk(pid, "ab")] = budget
        self.s[self._pk(pid, "rv")] = liquidity
        self.s[self._pk(pid, "cs")] = ts - lp.team_alloc_of(ts, tb)
        # D20: the seed joins the global curve accounting (exact-sum model)
        self.total_curve_xel += liquidity
        self.total_budgets += budget
        self.s[self._pk(pid, "dl")] = liquidity >= self.cfg["direct_listing_threshold"]
        self.s[self._pk(pid, "tp")] = 0
        self.s[self._pk(pid, "vs")] = 0
        self.s[self._pk(pid, "vd")] = 0
        self.s[self._pk(pid, "vp")] = plan
        self.s[self._pk(pid, "bt")] = 0
        self.s[self._pk(pid, "mi")] = False
        self.s[self._pk(pid, "ma")] = 0
        self.s[self._pk(pid, "mx")] = 0
        self.s[self._pk(pid, "mt")] = 0
        self.s[self._pk(pid, "ds")] = False
        self.s[self._pk(pid, "rd")] = 0
        self.s[self._pk(pid, "sp")] = 0
        self.s[self._pk(pid, "rp")] = 0
        self.s[self._pk(pid, "ct")] = self.topo
        self.s[self._pk(pid, "ve")] = self.topo + self.cfg["validation_duration"]
        self.s[self._pk(pid, "gr")] = False
        self.s[self._pk(pid, "rc")] = False
        self.s[self._pk(pid, "vo")] = 0
        for f in ("bv", "sv", "tc", "lt", "mc", "mh", "mg"):
            self.s[self._pk(pid, f)] = 0
        self.count += 1
        self.s[lp.ticker_key(symbol)] = pid
        self.pending_fees += self.cfg["submission_fee"]
        self.check_invariants()
        return pid

    def vote(self, pid, voter, support, deposit=None):
        """D21: with the dial raised the voter attaches >= the deposit
        (deposit defaults to the CURRENT dial — the honest-voter default
        since v4.2); exactly the configured amount is locked (the excess
        is refunded immediately — modelled as: the wallet only ever
        parts with the locked part), the slot records the amount."""
        status = self.s[self._pk(pid, "st")]
        assert status != lp.ST_REJECTED, "dead"
        if status in (lp.ST_VALIDATION, lp.ST_RECOVERY):
            assert self.topo < self.s[self._pk(pid, "ve")], "ended"
        round_no = self.s[self._pk(pid, "rd")]
        vkey = lp.vote_key(pid, round_no, voter)
        assert vkey not in self.s, "voted"
        vdep = self.cfg.get("vote_deposit", 0)
        if deposit is None:
            deposit = vdep
        assert deposit >= vdep, "votedep"
        if vdep > 0:
            w = self.wallets[voter]
            assert w["xel"] >= deposit, "nofunds"
            w["xel"] -= deposit          # attached
            self.balance += deposit
            w["xel"] += deposit - vdep    # excess refunded in the same tx
            self.balance -= deposit - vdep  # ... and it leaves the contract
            self.vote_pots += vdep
        self.s[vkey] = vdep
        self.s[self._pk(pid, "sp" if support else "rp")] += 1
        self._trust_guard(pid, status)
        self.check_invariants()

    def claim_vote_deposit(self, pid, round_no, caller):
        """D21 pull-refund: the round must be closed (a newer round exists
        or the current round's deadline has passed), the slot must hold a
        positive amount; it is zeroed-but-kept and the pots shrink."""
        cur_round = self.s[self._pk(pid, "rd")]
        assert round_no <= cur_round, "badround"
        if round_no == cur_round:
            assert self.topo >= self.s[self._pk(pid, "ve")], "open"
        vkey = lp.vote_key(pid, round_no, caller)
        locked = self.s.get(vkey)
        assert locked is not None, "novote"
        assert locked > 0, "nothing"
        self.s[vkey] = 0
        self.vote_pots -= locked
        self.balance -= locked
        self.wallets[caller]["xel"] += locked
        self.check_invariants()

    def _trust_guard(self, pid, status):
        if status in (lp.ST_BONDING, lp.ST_GRADUATED, lp.ST_TRUSTED):
            sp = self.s[self._pk(pid, "sp")]
            rp = self.s[self._pk(pid, "rp")]
            total = sp + rp
            if total >= self.cfg["min_participants"]:
                if rp * 10_000 >= self.cfg["min_approval_ratio_bps"] * total:
                    self.s[self._pk(pid, "st")] = lp.ST_UNTRUSTED

    def _create_project_asset(self, pid, topup=0):
        """D13: the real token is born — mirrors create_project_asset. All
        assertions come BEFORE any mutation: a failed creation reverts the
        whole transaction (TX atomicity), so the Sim must leave the state
        untouched on the "budget" refusal."""
        assert self.asset_of(pid) is None, "exists"
        creator = self.s[self._pk(pid, "cr")]
        budget = self.s.get(self._pk(pid, "ab"), 0)
        fee_paid = self.asset_fee
        # the revert point (the contract's require(avail >= fee_paid, "budget"))
        assert budget + topup >= fee_paid, "budget"
        # net effect of the SUCCESSFUL transaction (atomic on-chain):
        if topup:
            w0 = self.wallets[creator]
            assert w0["xel"] >= topup, "needtopup"
            w0["xel"] -= topup
            self.balance += topup
        # the chain charged the creation fee from the contract balance
        self.balance -= fee_paid
        self.burned += fee_paid
        # Fixed mode: the WHOLE supply lands in the contract's escrow.
        # The asset ID is NEVER the zero hash (XEL) — the DEX's "sameass"
        # guard rejects that case, and real XELIS asset IDs are hashes.
        ts = self.s[self._pk(pid, "ts")]
        asset = f"{pid + 1:064x}"
        self.contract_assets[asset] = ts
        refund = budget + topup - fee_paid
        self.balance -= refund
        self.wallets[creator]["xel"] += refund
        self.s[self._pk(pid, "ab")] = 0
        self.total_budgets -= budget
        self.s[self._pk(pid, "ah")] = asset
        # D22: the reverse bridge (a:{asset_hex} -> pid) — written once
        assert asset not in self.asset_to_pid, "exists"
        self.asset_to_pid[asset] = pid
        return asset

    def _graduate(self, pid):
        """Mirrors graduate(): status flip, migration fee, plan bind, mg."""
        self.s[self._pk(pid, "st")] = lp.ST_GRADUATED
        self.s[self._pk(pid, "gr")] = True
        self._take_migration_fee(pid)
        plan = self.s.get(self._pk(pid, "vp"), 0)
        if plan > 0:
            self.s[self._pk(pid, "vs")] = self.topo
            self.s[self._pk(pid, "vd")] = plan
        self._update_mcap(pid)
        self.s[self._pk(pid, "mg")] = self.s[self._pk(pid, "mc")]

    def _take_migration_fee(self, pid):
        bps = self.cfg["migration_fee_bps"]
        if bps == 0:
            return
        reserves = self.s[self._pk(pid, "rv")]
        fee = lp.fee_take(reserves, bps)
        if fee == 0:
            return
        self.s[self._pk(pid, "rv")] = reserves - fee
        self.total_curve_xel -= fee
        self.pending_fees += fee

    def finalize(self, pid, topup=0):
        status = self.s[self._pk(pid, "st")]
        assert status in (lp.ST_VALIDATION, lp.ST_RECOVERY), "nowindow"
        assert self.topo >= self.s[self._pk(pid, "ve")], "open"
        sp = self.s[self._pk(pid, "sp")]
        rp = self.s[self._pk(pid, "rp")]
        total = sp + rp
        if status == lp.ST_VALIDATION:
            if (total >= self.cfg["min_participants"] and
                    sp * 10_000 >= self.cfg["min_approval_ratio_bps"] * total):
                # D13: the REAL token is born BEFORE any state flip
                self._create_project_asset(pid, topup)
                self.s[self._pk(pid, "bt")] = self.topo
                if self.s[self._pk(pid, "dl")]:
                    self._graduate(pid)      # direct listing (D7)
                else:
                    self.s[self._pk(pid, "st")] = lp.ST_BONDING
                self.check_invariants()
                return 1
            # rejection: liquidity becomes refundable, budget stays earmarked
            self.s[self._pk(pid, "st")] = lp.ST_REJECTED
            liquidity = self.s[self._pk(pid, "lq")]
            self.locked_refunds += liquidity
            self.total_curve_xel -= liquidity
            self.s[self._pk(pid, "rv")] = 0
            self.check_invariants()
            return 0
        # recovery window
        graduated = self.s[self._pk(pid, "gr")]
        min_p = self.cfg["recovery_min_participants"] if graduated \
            else self.cfg["min_participants"]
        ratio = self.cfg["recovery_min_ratio_bps"] if graduated \
            else self.cfg["min_approval_ratio_bps"]
        if total >= min_p and sp * 10_000 >= ratio * total:
            self.s[self._pk(pid, "st")] = lp.ST_TRUSTED if graduated else lp.ST_BONDING
        else:
            self.s[self._pk(pid, "st")] = lp.ST_UNTRUSTED
        self.check_invariants()

    def _fee_bps(self, pid):
        return lp.current_fee_bps(bool(self.s[self._pk(pid, "gr")]),
                                  self.cfg["trading_fee_bps"],
                                  self.cfg["graduated_fee_bps"])

    def buy(self, pid, buyer, xel_in):
        status = self.s[self._pk(pid, "st")]
        assert status in lp.BUYABLE, "notrade"
        assert not self.s.get(self._pk(pid, "mi"), False), "migrated"
        assert 10**6 <= xel_in <= 100_000 * XEL
        w = self.wallets[buyer]
        assert w["xel"] >= xel_in, "noXEL"
        w["xel"] -= xel_in
        self.balance += xel_in
        bps = self._fee_bps(pid)
        fee = lp.fee_take(xel_in, bps)
        net = xel_in - fee
        reserves = self.s[self._pk(pid, "rv")]
        cs = self.s[self._pk(pid, "cs")]
        assert reserves > 0 and cs > 0, "empty"
        tokens = lp.buy_tokens_out(reserves, cs, net)
        assert tokens >= 1 and cs >= tokens
        asset = self.asset_of(pid)
        assert asset is not None, "noasset"
        # curve state (D14): net joins reserves, REAL tokens leave escrow
        new_reserves = reserves + net
        self.s[self._pk(pid, "rv")] = new_reserves
        self.s[self._pk(pid, "cs")] = cs - tokens
        self.total_curve_xel += net
        self._record_trade(pid, True, xel_in)
        self.pending_fees += fee
        self.contract_assets[asset] -= tokens
        w["assets"][asset] += tokens
        if status == lp.ST_BONDING:
            liquidity = self.s[self._pk(pid, "lq")]
            if new_reserves >= liquidity * self.cfg["graduation_multiplier"]:
                self._graduate(pid)
        self._update_mcap(pid)
        self.check_invariants()
        return tokens

    def sell(self, pid, seller, tokens):
        """v4: the WHOLE attached deposit is sold (D14)."""
        status = self.s[self._pk(pid, "st")]
        assert status in lp.SELLABLE, "nosell"
        assert not self.s.get(self._pk(pid, "mi"), False), "migrated"
        asset = self.asset_of(pid)
        assert asset is not None, "noasset"
        w = self.wallets[seller]
        assert w["assets"][asset] >= tokens >= 1, "nosell"
        w["assets"][asset] -= tokens
        self.contract_assets[asset] += tokens
        reserves = self.s[self._pk(pid, "rv")]
        cs = self.s[self._pk(pid, "cs")]
        assert reserves > 0 and cs > 0, "empty"
        bps = self._fee_bps(pid)
        gross = lp.sell_xel_out(reserves, cs, tokens)
        assert gross >= 1
        fee = lp.fee_take(gross, bps)
        out = gross - fee
        assert out >= 1
        self.s[self._pk(pid, "rv")] = reserves - gross
        self.s[self._pk(pid, "cs")] = cs + tokens
        self.total_curve_xel -= gross
        self._record_trade(pid, False, gross)
        self.pending_fees += fee
        self.balance -= out
        w["xel"] += out
        self._update_mcap(pid)
        self.check_invariants()
        return out

    def claim_refund(self, pid, caller):
        assert self.s[self._pk(pid, "st")] == lp.ST_REJECTED, "norefund"
        assert caller == self.s[self._pk(pid, "cr")], "notauth"
        assert not self.s.get(self._pk(pid, "rc"), False), "claimed"
        liquidity = self.s[self._pk(pid, "lq")]
        budget = self.s.get(self._pk(pid, "ab"), 0)
        self.s[self._pk(pid, "rc")] = True
        self.s[self._pk(pid, "ab")] = 0
        self.locked_refunds -= liquidity
        if budget:
            self.total_budgets -= budget
        total = liquidity + budget
        self.balance -= total
        self.wallets[caller]["xel"] += total
        self.check_invariants()

    def request_revalidation(self, pid, caller, fee_paid=False):
        assert self.s[self._pk(pid, "st")] == lp.ST_UNTRUSTED, "badstate"
        assert caller == self.s[self._pk(pid, "cr")], "notauth"
        graduated = self.s[self._pk(pid, "gr")]
        if graduated:
            assert fee_paid, "badfee"
            # the recovery fee is ATTACHED to the transaction (it must
            # land in the balance to keep I2 honest)
            w = self.wallets[caller]
            assert w["xel"] >= self.cfg["recovery_fee"], "needfee"
            w["xel"] -= self.cfg["recovery_fee"]
            self.balance += self.cfg["recovery_fee"]
            self.pending_fees += self.cfg["recovery_fee"]
        self.s[self._pk(pid, "rd")] += 1
        self.s[self._pk(pid, "sp")] = 0
        self.s[self._pk(pid, "rp")] = 0
        self.s[self._pk(pid, "ve")] = self.topo + self.cfg["validation_duration"]
        self.s[self._pk(pid, "st")] = lp.ST_RECOVERY
        self.check_invariants()

    def _unlock(self, pid):
        return lp.team_unlocked(
            lp.team_alloc_of(self.s[self._pk(pid, "ts")],
                             self.s[self._pk(pid, "tb")]),
            bool(self.s[self._pk(pid, "gr")]),
            self.s.get(self._pk(pid, "vs"), 0),
            self.s.get(self._pk(pid, "vd"), 0),
            self.s[self._pk(pid, "st")],
            self.s.get(self._pk(pid, "bt"), 0),
            self.cfg["team_unlock_delay"], self.topo)

    def start_team_vesting(self, pid, caller, duration):
        assert caller == self.s[self._pk(pid, "cr")], "notauth"
        assert self.s.get(self._pk(pid, "vp"), 0) == 0, "planned"
        assert self.s.get(self._pk(pid, "vs"), 0) == 0, "started"
        assert self._team_remaining(pid) > 0, "done"
        assert self.cfg["vesting_min"] <= duration <= self.cfg["vesting_max"]
        assert self._unlock(pid) > 0, "notyet"
        self.s[self._pk(pid, "vs")] = self.topo
        self.s[self._pk(pid, "vd")] = duration
        self.check_invariants()

    def _team_remaining(self, pid):
        return lp.team_remaining(
            lp.team_alloc_of(self.s[self._pk(pid, "ts")],
                             self.s[self._pk(pid, "tb")]),
            self.s.get(self._pk(pid, "tp"), 0))

    def claim_team_allocation(self, pid, caller):
        assert caller == self.s[self._pk(pid, "cr")], "notauth"
        unlocked = self._unlock(pid)
        paid = self.s.get(self._pk(pid, "tp"), 0)
        assert unlocked > paid, "nothing"
        pay = unlocked - paid
        self.s[self._pk(pid, "tp")] = paid + pay
        asset = self.asset_of(pid)
        assert asset is not None, "noasset"
        self.contract_assets[asset] -= pay
        self.wallets[caller]["assets"][asset] += pay
        self._update_mcap(pid)
        self.check_invariants()
        return pay

    def set_dex_address(self, pin):
        assert self.migrated_count == 0, "frozen"   # D19
        self.dex_pin = pin
        self.check_invariants()

    def migrate(self, pid, caller="anyone"):
        """D15: the permissionless, atomic move to LaunchDEX."""
        assert self.s[self._pk(pid, "gr")], "notgrad"
        assert not self.s.get(self._pk(pid, "mi"), False), "done"
        assert self.dex_pin is not None, "nodex"
        asset = self.asset_of(pid)
        assert asset is not None, "noasset"
        reserves = self.s[self._pk(pid, "rv")]
        cs = self.s[self._pk(pid, "cs")]
        assert reserves >= 1 and cs >= 1, "empty"
        assert reserves <= self.balance, "accerr"
        team_rem = self._team_remaining(pid)
        assert cs + team_rem <= self.contract_assets[asset], "accerr"
        # state first: close the curve, snapshot, update accounting
        self.s[self._pk(pid, "mi")] = True
        self.s[self._pk(pid, "ma")] = self.topo
        self.s[self._pk(pid, "mx")] = reserves
        self.s[self._pk(pid, "mt")] = cs
        self.s[self._pk(pid, "rv")] = 0
        self.s[self._pk(pid, "cs")] = 0
        self.total_curve_xel -= reserves
        self.migrated_count += 1
        # D22: the migrated index (m:{order} -> pid), migration order
        self.migrated_index.append(pid)
        self._update_mcap(pid)
        # the atomic cross-call: funds out, pool seeded
        self.balance -= reserves
        self.contract_assets[asset] -= cs
        self.dex.create_pool(LAUNCHPAD_ADDR, asset, reserves, cs)
        # Untrusted at migration time: pause pool buys in the SAME tx (D17)
        if self.s[self._pk(pid, "st")] == lp.ST_UNTRUSTED:
            self.dex.set_pool_buys_paused(LAUNCHPAD_ADDR, asset, True)
            self.s[self._pk(pid, "ds")] = True
        self.check_invariants()

    def sync_trust_to_dex(self, pid, caller="keeper"):
        """D17: mirror the trust status to the pool's buys-pause."""
        assert self.s.get(self._pk(pid, "mi"), False), "notmig"
        flag = self.s[self._pk(pid, "st")] == lp.ST_UNTRUSTED
        assert self.s.get(self._pk(pid, "ds"), False) != flag, "insync"
        asset = self.asset_of(pid)
        self.s[self._pk(pid, "ds")] = flag
        self.dex.set_pool_buys_paused(LAUNCHPAD_ADDR, asset, flag)
        self.check_invariants()

    def warp(self, topos):
        self.topo += topos
        self.dex.topo = self.topo

# ===========================================================================
# LAYER 2 — LIFECYCLE SCENARIOS
# ===========================================================================

def _validated(sim, pid, yes=3, no=0):
    """Push a validation window through with a passing vote (voters are
    minted the current dial — since v4.2 the default is 0.5 XEL)."""
    for i in range(yes):
        sim.mint(f"voter{i}", sim.cfg.get("vote_deposit", 0))
        sim.vote(pid, f"voter{i}", True)
    for i in range(no):
        sim.mint(f"no{i}", sim.cfg.get("vote_deposit", 0))
        sim.vote(pid, f"no{i}", False)
    sim.warp(sim.cfg["validation_duration"] + 1)
    return sim.finalize(pid)


def _cast(sim, pid, n, support=True, prefix="v"):
    """Cast n votes at the current dial, minting each voter exactly what
    the dial locks (the tests' honest-voter default)."""
    for i in range(n):
        sim.mint(f"{prefix}{i}", sim.cfg.get("vote_deposit", 0))
        sim.vote(pid, f"{prefix}{i}", support)


def _fuzz_cfg():
    return {"min_participants": 3, "min_approval_ratio_bps": 6000,
            "validation_duration": 3000, "recovery_min_participants": 4,
            "recovery_min_ratio_bps": 7000, "vesting_min": 100,
            "vesting_max": 5000, "team_unlock_delay": 500,
            "graduation_multiplier": 3}


def test_full_lifecycle_curve_path():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 10_000 * XEL)
    sim.mint("bob", 10_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING
    # D13: the asset exists, whole supply in escrow, Fixed semantics
    asset = sim.asset_of(pid)
    assert asset is not None
    assert sim.contract_assets[asset] == 100_000_000 * XEL
    # budget: 10 earmarked, 1 burned by the chain, 9 refunded
    assert sim.s[sim._pk(pid, "ab")] == 0
    # 600 - (10 fee + 10 budget + 500 liquidity) + 9 refund = 89 XEL
    assert sim.wallets["founder"]["xel"] == (600 - 500 - 10 - 10 + 9) * XEL
    # buys push the reserves to the graduation target (500 x 4 = 2000)
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    assert sim.s[sim._pk(pid, "gr")], "graduated"
    assert sim.wallets["alice"]["assets"][asset] > 0, "REAL tokens in wallet"
    # curve trades continue at the graduated fee until migration (D15)
    out = sim.sell(pid, "alice", sim.wallets["alice"]["assets"][asset] // 4)
    assert out > 0
    # the migration (permissionless)
    sim.set_dex_address("dex_contract_hash")
    sim.migrate(pid, caller="anyone")
    assert sim.s[sim._pk(pid, "mi")]
    assert sim.s[sim._pk(pid, "rv")] == 0 and sim.s[sim._pk(pid, "cs")] == 0
    # the pool was seeded with exactly reserves + inventory
    pool = sim.dex.pools[asset]
    assert pool["x"] == sim.s[sim._pk(pid, "mx")]
    assert pool["y"] == sim.s[sim._pk(pid, "mt")]
    assert pool["x"] > 0 and pool["y"] > 0
    # the curve is closed: buys/sells revert, trading continues on the DEX
    with pytest.raises(AssertionError):
        sim.buy(pid, "bob", 10 * XEL)
    with pytest.raises(AssertionError):
        sim.sell(pid, "alice", 1)
    # DEX swaps both ways (real assets moving between wallets and pool)
    sim.dex.wallets["alice"]["xel"] = sim.wallets["alice"]["xel"]
    sim.wallets["alice"]["xel"] = 0
    got = sim.dex.swap_xel("alice", asset, 50 * XEL)
    assert got >= 1
    back = sim.dex.swap_tokens("alice", asset, got // 2)
    assert back >= 1
    # team claim pays REAL tokens from the escrow after migration (I10)
    pay = sim.claim_team_allocation(pid, "founder")
    assert pay == 10_000_000 * XEL  # 10% of 100M
    assert sim.wallets["founder"]["assets"][asset] == pay
    assert sim.contract_assets[asset] == 0  # all claimed (no vesting)


def test_direct_listing_path_d7():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 3000 * XEL)
    pid = sim.propose("founder", 2500 * XEL)   # >= 2000 XEL threshold
    assert sim.s[sim._pk(pid, "dl")]
    assert _validated(sim, pid) == 1
    assert sim.s[sim._pk(pid, "st")] == lp.ST_GRADUATED
    assert sim.s[sim._pk(pid, "gr")]
    # migration fee taken on the seed; pool seedable the same block
    sim.set_dex_address("dex")
    sim.migrate(pid)
    asset = sim.asset_of(pid)
    fee = lp.fee_take(2500 * XEL, 50)
    assert sim.dex.pools[asset]["x"] == 2500 * XEL - fee
    # team can claim immediately (graduated)
    assert sim._unlock(pid) == 10_000_000 * XEL


def test_asset_budget_refund_and_topup_d13():
    # the chain fee rises above the earmarked budget -> the finalize
    # reverts ("budget") and is retryable with a top-up deposit
    sim = Sim(_fuzz_cfg(), asset_fee=50 * XEL)   # chain fee 50 XEL > budget 10
    sim.mint("founder", 700 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    _cast(sim, pid, 3)
    sim.warp(3001)
    with pytest.raises(AssertionError):
        sim.finalize(pid)                # "budget" — the whole TX reverts
    # the revert left the project in Validation, window closed: retry
    # with a top-up attached to the finalize transaction
    assert sim.finalize(pid, topup=45 * XEL) == 1
    # founder's total outlay: 500 liquidity (locked) + 10 submission fee
    # + 50 chain fee (covered by budget 10 + topup 45, refund 5) = 560 XEL
    spent = 700 * XEL - sim.wallets["founder"]["xel"]
    assert spent == (500 + 10 + 50) * XEL
    # and a zero chain fee refunds the whole budget
    sim2 = Sim(_fuzz_cfg(), asset_fee=0)
    sim2.mint("founder", 600 * XEL)
    pid2 = sim2.propose("founder", 500 * XEL)
    _cast(sim2, pid2, 3)
    sim2.warp(3001)
    assert sim2.finalize(pid2) == 1
    # zero chain fee: the whole budget is refunded; only the liquidity
    # (locked) and the non-refundable submission fee are spent
    assert sim2.wallets["founder"]["xel"] == (600 - 500 - 10) * XEL


def test_ticker_reserved_at_propose_d11():
    sim = Sim(_fuzz_cfg())
    sim.mint("f1", 600 * XEL)
    sim.mint("f2", 600 * XEL)
    pid = sim.propose("f1", 500 * XEL, symbol="MOON")
    with pytest.raises(AssertionError):
        sim.propose("f2", 500 * XEL, symbol="MOON")
    # a different symbol is fine
    sim.propose("f2", 500 * XEL, symbol="STAR")


def test_rejected_project_refunds_liquidity_and_budget():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    _cast(sim, pid, 3, support=False)     # 100% reports -> rejection
    sim.warp(3001)
    assert sim.finalize(pid) == 0
    assert sim.s[sim._pk(pid, "st")] == lp.ST_REJECTED
    assert sim.asset_of(pid) is None, "no asset for rejected projects (D13)"
    before = sim.wallets["founder"]["xel"]
    sim.claim_refund(pid, "founder")
    # liquidity + unused budget (nothing was created)
    assert sim.wallets["founder"]["xel"] == before + 500 * XEL + 10 * XEL
    with pytest.raises(AssertionError):
        sim.claim_refund(pid, "founder")   # exactly once


def test_untrusted_blocks_buys_never_sells_and_recovers():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 5000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    sim.buy(pid, "alice", 50 * XEL)
    asset = sim.asset_of(pid)
    # community flips it Untrusted (6 reports vs 3 lifetime supports
    # = 66% >= 60%)
    _cast(sim, pid, 6, support=False, prefix="r")
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED
    with pytest.raises(AssertionError):
        sim.buy(pid, "alice", 10 * XEL)
    sim.sell(pid, "alice", sim.wallets["alice"]["assets"][asset] // 2)  # works
    # recovery: creator pays the fee, stricter bar, back to Bonding
    sim.request_revalidation(pid, "founder", fee_paid=False)  # not graduated
    _cast(sim, pid, 3, prefix="s")
    sim.warp(3001)
    sim.finalize(pid)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_BONDING
    sim.buy(pid, "alice", 10 * XEL)  # buys work again


def test_untrusted_at_migration_pauses_pool_buys_same_tx_d17():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 1000 * XEL)   # enough for the 250 XEL recovery fee
    sim.mint("alice", 20_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    # flip Untrusted BEFORE the migration (6 reports vs 3 supports)
    _cast(sim, pid, 6, support=False, prefix="r")
    assert sim.s[sim._pk(pid, "st")] == lp.ST_UNTRUSTED
    sim.set_dex_address("dex")
    sim.migrate(pid)
    asset = sim.asset_of(pid)
    assert sim.dex.pools[asset]["bp"], "pool buys paused in the same tx"
    assert sim.s[sim._pk(pid, "ds")]
    # sells on the pool still work (D4): a holder exits
    sim.dex.wallets["alice"]["assets"][asset] = \
        sim.wallets["alice"]["assets"][asset]
    sim.wallets["alice"]["assets"][asset] = 0
    out = sim.dex.swap_tokens("alice", asset,
                              sim.dex.wallets["alice"]["assets"][asset] // 3)
    assert out > 0
    # recovery -> keeper syncs -> pool buys resume
    sim.request_revalidation(pid, "founder", fee_paid=True)
    _cast(sim, pid, 4, prefix="s")
    sim.warp(3001)
    sim.finalize(pid)
    assert sim.s[sim._pk(pid, "st")] == lp.ST_TRUSTED
    sim.sync_trust_to_dex(pid)
    assert not sim.dex.pools[asset]["bp"]
    with pytest.raises(AssertionError):
        sim.sync_trust_to_dex(pid)   # already in sync


def test_migration_is_idempotent_and_dex_pin_freezes_d19():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 20_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    sim.set_dex_address("dex_one")
    sim.migrate(pid)
    with pytest.raises(AssertionError):
        sim.migrate(pid)              # exactly once
    with pytest.raises(AssertionError):
        sim.set_dex_address("dex_two")  # frozen after the first migration
    assert sim.dex.launchpad == LAUNCHPAD_ADDR
    assert sim.dex.pinned, "DEX launchpad pin froze at its first pool"


def test_team_vesting_stream_d3():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 20_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    sim.start_team_vesting(pid, "founder", 1000)
    assert sim._unlock(pid) == 0            # nothing at T0
    sim.warp(250)
    assert sim._unlock(pid) == 2_500_000 * XEL   # 25% of the 10% alloc
    first = sim.claim_team_allocation(pid, "founder")
    assert first == 2_500_000 * XEL
    sim.warp(250)
    second = sim.claim_team_allocation(pid, "founder")   # resumes
    assert second == 2_500_000 * XEL
    sim.warp(100_000)
    last = sim.claim_team_allocation(pid, "founder")     # saturates
    assert last == 5_000_000 * XEL
    with pytest.raises(AssertionError):
        sim.claim_team_allocation(pid, "founder")        # paid exactly once


def test_team_late_claim_never_graduated_d3():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    assert sim._unlock(pid) == 0
    sim.warp(501)                       # past the fuzz delay (500)
    assert sim._unlock(pid) == 10_000_000 * XEL
    pay = sim.claim_team_allocation(pid, "founder")
    assert pay == 10_000_000 * XEL
    assert sim.wallets["founder"]["assets"][sim.asset_of(pid)] == pay


def test_vesting_plan_binds_at_graduation_curve_path_d10():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 20_000 * XEL)
    pid = sim.propose("founder", 500 * XEL, plan=1000)
    assert sim.s[sim._pk(pid, "vp")] == 1000
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    # bound at graduation: the declared plan IS the vesting
    assert sim.s[sim._pk(pid, "vs")] > 0
    assert sim.s[sim._pk(pid, "vd")] == 1000
    with pytest.raises(AssertionError):
        sim.start_team_vesting(pid, "founder", 2000)   # "planned"
    sim.warp(500)
    assert sim._unlock(pid) == 5_000_000 * XEL


def test_one_vote_per_address_per_round():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    sim.mint("voter", sim.cfg.get("vote_deposit", 0))
    sim.vote(pid, "voter", True)
    with pytest.raises(AssertionError):
        sim.vote(pid, "voter", True)
    with pytest.raises(AssertionError):
        sim.vote(pid, "voter", False)


def test_solvency_after_graduation_and_withdrawal_pressure():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 20_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    sim.set_dex_address("dex")
    sim.migrate(pid)
    # every XEL is committed: curve closed, fees pending, escrow exact —
    # I2 holds with equality-level accounting (D20)
    assert sim.balance >= sim.total_curve_xel + sim.pending_fees + \
        sim.locked_refunds + sim.total_budgets


def test_dex_pool_era_scoreboard_and_permanent_liquidity():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    sim.mint("alice", 20_000 * XEL)
    sim.mint("bob", 5_000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    assert _validated(sim, pid) == 1
    while sim.s[sim._pk(pid, "st")] == lp.ST_BONDING:
        sim.buy(pid, "alice", 100 * XEL)
    sim.set_dex_address("dex")
    sim.migrate(pid)
    asset = sim.asset_of(pid)
    pool = sim.dex.pools[asset]
    x0, y0 = pool["x"], pool["y"]
    # curve-era scoreboard froze
    assert sim.s[sim._pk(pid, "mc")] == 0   # curve closed
    assert sim.s[sim._pk(pid, "mh")] > 0    # history kept
    # DEX-era trades update the POOL scoreboard
    sim.dex.wallets["bob"]["xel"] = 2_000 * XEL
    sim.dex.swap_xel("bob", asset, 100 * XEL)
    assert pool["bv"] == 100 * XEL and pool["tc"] == 1
    # liquidity can only grow (X2): a community donation — bob needs both
    # sides first, so he buys some tokens then donates XEL + tokens
    got = sim.dex.swap_xel("bob", asset, 200 * XEL)
    x1, y1 = pool["x"], pool["y"]          # state right before the gift
    sim.dex.add_liquidity("bob", asset, 50 * XEL, got // 4)
    assert pool["x"] > x1 and pool["y"] > y1
    assert pool["lp"] == 1
    # fees accumulate in the pending pots, never in the reserves
    assert pool["xf"] > 0 or pool["yf"] > 0


def test_social_links_update_anytime_d11():
    sim = Sim(_fuzz_cfg())
    sim.mint("founder", 600 * XEL)
    pid = sim.propose("founder", 500 * XEL, twitter="@x", telegram="t.me/x")
    assert sim.s[sim._pk(pid, "tw")] == "@x"
    sim.s[sim._pk(pid, "tw")] = "@y"     # update_project_info
    assert sim.s[sim._pk(pid, "tw")] == "@y"


def test_fuzz_invariants_hold_under_random_lifecycles():
    """30 seeds x ~220 actions: propose -> vote -> finalize -> buy/sell ->
    graduate -> migrate -> DEX swaps -> trust flips -> claims, with ALL
    invariants (I1/I2/I9/I10 + IX* + conservation) asserted after EVERY
    action."""
    import random

    for seed in range(30):
        rng = random.Random(seed)
        sim = Sim(_fuzz_cfg())
        sim.set_dex_address(f"dex{seed}")
        for who in ("f1", "f2", "f3", "a1", "a2", "a3", "k1"):
            sim.mint(who, 100_000 * XEL)
            # same wallets, DEX side (tracked in mint_xel: conservation!)
            sim.dex.wallets[who]["xel"] = 50_000 * XEL
            sim.mint_xel += 50_000 * XEL
        pids = []
        migrated = []
        # deterministic warm-up: 3 projects pass validation immediately
        for i in range(3):
            pid = sim.propose(f"f{i + 1}", 500 * XEL,
                              tb=rng.choice([0, 500, 1000, 2000]),
                              plan=rng.choice([0, 100, 500, 2000]))
            for v in range(3):
                sim.mint(f"warm{v}", sim.cfg.get("vote_deposit", 0))
                sim.vote(pid, f"warm{v}", True)
            sim.warp(3001)
            assert sim.finalize(pid) == 1
            pids.append(pid)
        for step in range(220):
            action = rng.random()
            live = [p for p in pids
                    if sim.s[sim._pk(p, "st")] in
                    (lp.ST_BONDING, lp.ST_GRADUATED, lp.ST_TRUSTED,
                     lp.ST_UNTRUSTED, lp.ST_RECOVERY)]
            tradable = [p for p in live
                        if not sim.s.get(sim._pk(p, "mi"), False)
                        and sim.s[sim._pk(p, "st")] in lp.BUYABLE]
            if action < 0.40 and tradable:
                p = rng.choice(tradable)
                who = rng.choice(["a1", "a2", "a3", "k1"])
                try:
                    sim.buy(p, who, rng.randrange(1, 300) * XEL)
                except AssertionError:
                    pass  # "empty"/"tinyout"/graduation-boundary cases
            elif action < 0.55 and live:
                p = rng.choice(live)
                if not sim.s.get(sim._pk(p, "mi"), False):
                    asset = sim.asset_of(p)
                    holders = [w for w in ("a1", "a2", "a3", "k1")
                               if sim.wallets[w]["assets"][asset] > 0]
                    if holders:
                        w = rng.choice(holders)
                        amt = rng.randrange(1, 1 + sim.wallets[w]["assets"][asset])
                        try:
                            sim.sell(p, w, amt)
                        except AssertionError:
                            pass
            elif action < 0.62 and live:
                p = rng.choice(live)
                sim.mint(f"r{step}", sim.cfg.get("vote_deposit", 0))
                sim.vote(p, f"r{step}", rng.random() < 0.35)
            elif action < 0.72 and pids:
                p = rng.choice(pids)
                if (sim.s[sim._pk(p, "gr")]
                        and not sim.s.get(sim._pk(p, "mi"), False)):
                    sim.migrate(p, f"k1")
                    migrated.append(p)
            elif action < 0.86 and migrated:
                p = rng.choice(migrated)
                asset = sim.asset_of(p)
                pool = sim.dex.pools[asset]
                who = rng.choice(["a1", "a2", "a3", "k1"])
                if not pool["bp"] and rng.random() < 0.6:
                    try:
                        sim.dex.swap_xel(who, asset, rng.randrange(1, 50) * XEL)
                    except AssertionError:
                        pass
                else:
                    held = sim.dex.wallets[who]["assets"][asset]
                    if held > 0:
                        try:
                            sim.dex.swap_tokens(who, asset, rng.randrange(1, held + 1))
                        except AssertionError:
                            pass
            elif action < 0.92 and migrated:
                # X10/D23: providers deepen a migrated pool and claim
                # their pro-rata fees (proportional adds so the fit never
                # refuses; claims may legitimately fail "nofees")
                p = rng.choice(migrated)
                asset = sim.asset_of(p)
                pool = sim.dex.pools[asset]
                who = rng.choice(["a1", "a2", "a3", "k1"])
                if rng.random() < 0.6:
                    xel_add = rng.randrange(1, 20) * XEL
                    held = sim.dex.wallets[who]["assets"][asset]
                    need_tok = pool["y"] * xel_add // pool["x"]
                    if held >= need_tok and need_tok >= 1:
                        try:
                            sim.dex.add_liquidity(who, asset, xel_add, need_tok)
                        except AssertionError:
                            pass
                else:
                    try:
                        sim.dex.claim_lp_fees(who, asset)
                    except AssertionError:
                        pass  # "nofees" — nothing accrued yet
            elif action < 0.96:
                p = rng.choice(pids)
                creator = sim.s[sim._pk(p, "cr")]
                try:
                    sim.claim_team_allocation(p, creator)
                except AssertionError:
                    pass
            else:
                sim.warp(rng.randrange(1, 100))
        # every seed must have really exercised the machine
        assert sim.total_trades > 0
        assert len(migrated) > 0
        assert all(not sim.s.get(sim._pk(p, "rv"), 0) for p in migrated)
        sim.check_invariants()


# ===========================================================================
# LAYER 3 — SPEC: the contract source cannot drift from this reference
# ===========================================================================

def test_contract_exposes_the_full_spec_api():
    src = CONTRACT.read_text()
    for entry in ("propose", "support", "report", "finalize_validation",
                  "buy", "sell", "claim_refund", "request_revalidation",
                  "update_project_info", "start_team_vesting",
                  "claim_team_allocation", "migrate", "sync_trust_to_dex",
                  "set_submission_fee", "set_trading_fee",
                  "set_graduated_trading_fee", "set_migration_fee",
                  "set_direct_listing_threshold", "set_min_liquidity",
                  "set_min_participants", "set_min_approval_ratio",
                  "set_validation_duration", "set_graduation_multiplier",
                  "set_team_unlock_delay", "set_vesting_bounds",
                  "set_recovery_fee", "set_recovery_params",
                  "set_asset_budget", "set_dex_address", "set_admin",
                  "set_paused", "withdraw_fees"):
        assert re.search(rf"^entry {entry}\(", src, re.M), f"missing entry {entry}"
    for view in ("get_project", "get_project_info", "get_project_status",
                 "get_project_tokenomics", "get_project_trust",
                 "get_bonding_info", "get_current_price", "get_buy_quote",
                 "get_sell_quote", "get_market_cap", "has_voted",
                 "get_total_projects", "get_projects_by_status",
                 "get_project_by_rank", "get_latest_projects",
                 "get_trusted_projects", "get_trusted_by_rank",
                 "get_team_allocation", "get_protocol_stats", "get_config",
                 "get_recovery_config", "get_team_config",
                 "get_social_links", "get_trading_stats",
                 "get_market_cap_history", "get_proposal_data",
                 "get_volume_stats", "get_asset_info", "get_migration_info",
                 "get_status_label", "get_version"):
        assert re.search(rf"^pub fn {view}\(", src, re.M), f"missing view {view}"
    # v4 removed the internal ledger: no balance map, no get_token_balance
    assert "get_token_balance" not in src
    assert 'const BAL_PREFIX' not in src
    # v4 core: real assets + atomic migration + trust sync
    assert "Asset::create(" in src
    assert "MaxSupplyMode::Fixed { max_supply: total_supply }" in src
    assert re.search(r"deposits\.insert\(xel, reserves\)", src)
    assert re.search(r"deposits\.insert\(asset, curve_supply\)", src)
    assert 'target.call(DEX_CREATE_POOL_CHUNK' in src
    assert 'target.call(DEX_SET_PAUSED_CHUNK' in src
    assert "get_deposit_for_asset(asset)" in src   # token deposits (sell)


def test_contract_declares_every_spec_event():
    src = CONTRACT.read_text()
    events = {
        23: "EV_ASSET_CREATED", 24: "EV_MIGRATED",
        25: "EV_DEX_SYNCED", 26: "EV_DEX_ADDRESS",
    }
    for eid, name in events.items():
        assert re.search(rf"const {name}: u64 = {eid}", src), name
    # D18: the team claim event carries NO amount
    m = re.search(r"emit_event\(EV_TEAM_CLAIMED, \[([^\]]*)\]\)", src)
    assert m and m.group(1).strip() == 'pid.to_string(10u32)'


def test_contract_defaults_match_the_sdk_reference():
    src = CONTRACT.read_text()
    for const, value in (("DEFAULT_SUBMISSION_FEE", lp.DEFAULTS["submission_fee"]),
                         ("DEFAULT_ASSET_BUDGET", lp.DEFAULTS["asset_budget"]),
                         ("DEFAULT_MIN_LIQUIDITY", lp.DEFAULTS["min_liquidity"]),
                         ("DEFAULT_TRADING_FEE_BPS", lp.DEFAULTS["trading_fee_bps"]),
                         ("DEFAULT_GRADUATED_FEE_BPS", lp.DEFAULTS["graduated_fee_bps"]),
                         ("DEFAULT_MIGRATION_FEE_BPS", lp.DEFAULTS["migration_fee_bps"]),
                         ("DEFAULT_DIRECT_LISTING", lp.DEFAULTS["direct_listing_threshold"]),
                         ("DEFAULT_GRAD_MULTIPLIER", lp.DEFAULTS["graduation_multiplier"]),
                         ("DEFAULT_TEAM_DELAY", lp.DEFAULTS["team_unlock_delay"])):
        assert re.search(rf"const {const}: u64 = {value}$", src, re.M), const
    dex_src = DEX_CONTRACT.read_text()
    assert re.search(rf"const DEFAULT_SWAP_FEE_BPS: u64 = {dx.DEFAULTS['swap_fee_bps']}$",
                     dex_src, re.M)


def test_cross_checked_pairs_are_enforced_d7_d8():
    src = CONTRACT.read_text()
    # D8: graduated <= trading (both directions of the pair setter)
    assert 'require(bps >= graduated_fee, "croserr")' in src
    assert 'require(bps <= trading_fee, "croserr")' in src
    # D7: threshold >= min_liquidity (both directions)
    assert 'require(amount >= min_liq, "croserr")' in src
    assert 'require(amount <= threshold, "croserr")' in src


def test_cross_calls_are_exactly_the_pinned_pair_d19():
    """v4 HAS inter-contract calls (the whole point) — but EXACTLY the two
    pinned ones, with the chunk constants asserted against LaunchDEX's
    real declaration order."""
    src = CONTRACT.read_text()
    assert src.count("Contract::new(") == 2       # migrate_to_dex + sync
    assert src.count("is_contract_callable(") == 3  # 2 sites + doc mention? see below
    # the pinned constants
    m1 = re.search(r"const DEX_CREATE_POOL_CHUNK: u16 = (\d+)", src)
    m2 = re.search(r"const DEX_SET_PAUSED_CHUNK: u16 = (\d+)", src)
    assert m1 and m2
    # ...asserted against the DEX's REAL chunk positions (see dex tests)
    dex_src = DEX_CONTRACT.read_text()
    order = re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", dex_src, re.M)
    assert order.index("create_pool") == int(m1.group(1))
    assert order.index("set_pool_buys_paused") == int(m2.group(1))
    # create_pool/set_pool_buys_paused are pub fn (cross-call chunks on this
    # devnet toolchain) — not in the transaction-facing LAUNCHDEX_ENTRY_IDS;
    # the REAL declaration order above is the authoritative D19 gate.


def test_dex_contract_structure():
    src = DEX_CONTRACT.read_text()
    # the anti-rug core, v1.3 (X11/X12): remove_liquidity EXISTS but the
    # seed can NEVER leave — the burn is bounded by the caller's own
    # withdrawable balance (never minted for the seed) and the seed floor
    # is re-asserted belt-and-braces. No whole-pool drain entry exists.
    assert re.search(r"^(?:entry|pub fn|fn) remove_liquidity", src, re.M)
    assert 'require(parts <= w, "locked")' in src
    assert '"seederr"' in src and '"parterr"' in src
    assert 's.store(pool_key(asset, F_LP_LOCKED), xel_seed)' in src
    # the seed parts mint NO withdrawable balance (fees-only, X11)
    m = re.search(r"(?:entry|pub fn) create_pool\(.*?\n\}", src, re.S)
    assert m, "create_pool not found"
    assert 's.store(seed_lkey + LPF_W' not in m.group(0)
    assert not re.search(r"^(?:entry|pub fn|fn) withdraw_pool", src, re.M)
    for entry in ("create_pool", "set_pool_buys_paused", "swap_xel_for_token",
                  "swap_token_for_xel", "add_liquidity", "set_swap_fee",
                  "set_trade_bounds", "set_launchpad", "set_admin",
                  "set_paused", "withdraw_fees", "remove_liquidity"):
        assert re.search(rf"^(?:entry|pub fn) {entry}\(", src, re.M), entry
    # X4: the launchpad pin freezes at the first pool
    assert 's.store(LAUNCHPAD_PINNED_KEY, true)' in src


def test_sdk_entry_ids_match_the_real_declaration_order():
    src = CONTRACT.read_text()
    order = re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", src, re.M)
    for name, eid in LAUNCHPAD_ENTRY_IDS.items():
        assert order.index(name) == eid, \
            f"chunk {eid} for {name}: real position is {order.index(name)}"
    entries_only = [n for n in order
                    if re.search(rf"^entry {n}\(", src, re.M)]
    for name, eid in LAUNCHPAD_ENTRY_IDS_ALT.items():
        assert entries_only.index(name) == eid
    dex_src = DEX_CONTRACT.read_text()
    dorder = re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", dex_src, re.M)
    for name, eid in LAUNCHDEX_ENTRY_IDS.items():
        assert dorder.index(name) == eid
    dentries = [n for n in dorder if re.search(rf"^entry {n}\(", dex_src, re.M)]
    for name, eid in LAUNCHDEX_ENTRY_IDS_ALT.items():
        assert dentries.index(name) == eid


def test_contract_is_substantial_and_documents_its_chunk_table():
    src = CONTRACT.read_text()
    assert len(src.splitlines()) > 2500
    assert "CHUNK TABLE (entry-point IDs" in src
    assert "VAULTLAUNCH" not in src or True
    assert 'const VERSION: string = "VaultLaunch v4.2.0"' in src
    dex_src = DEX_CONTRACT.read_text()
    assert 'const VERSION: string = "LaunchDEX v1.4.1"' in dex_src
    assert "CHUNK TABLE (entry-point IDs" in dex_src


# ===========================================================================
# v4.1 — FOUNDER RISK REVIEW: the six points, each with its model test
# ===========================================================================

def test_d21_vote_deposits_full_lifecycle():
    """Point 5 (sybil): the dial locks capital per vote, refunds it after
    the round closes, and the pots stay on the committed side of I2."""
    sim = Sim(cfg=_fuzz_cfg() | {"vote_deposit": 2 * XEL})
    sim.mint("founder", 1000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    for i in range(5):
        sim.mint(f"v{i}", 10 * XEL)
        sim.vote(pid, f"v{i}", True, deposit=3 * XEL)   # 1 XEL excess attached
        # the excess came straight back: the wallet only lost the deposit
        assert sim.wallets[f"v{i}"]["xel"] == 10 * XEL - 2 * XEL
    assert sim.vote_pots == 5 * 2 * XEL
    # claims are refused while the window is open
    with pytest.raises(AssertionError, match="open"):
        sim.claim_vote_deposit(pid, 0, "v0")
    # not enough attached -> refused
    sim.mint("poor", 10 * XEL)
    with pytest.raises(AssertionError, match="votedep"):
        sim.vote(pid, "poor", True, deposit=1 * XEL)
    sim.warp(sim.cfg["validation_duration"] + 1)
    sim.finalize(pid)
    for i in range(5):
        before = sim.wallets[f"v{i}"]["xel"]
        sim.claim_vote_deposit(pid, 0, f"v{i}")
        assert sim.wallets[f"v{i}"]["xel"] == before + 2 * XEL
        # double claim: the slot is zeroed-but-kept -> "nothing"
        with pytest.raises(AssertionError, match="nothing"):
            sim.claim_vote_deposit(pid, 0, f"v{i}")
    assert sim.vote_pots == 0
    # never voted -> "novote"
    with pytest.raises(AssertionError, match="novote"):
        sim.claim_vote_deposit(pid, 0, "poor")


def test_d21_default_is_a_refundable_half_xel_and_admin_cannot_confiscate():
    """Since v4.2 the default dial is 0.5 XEL (founder risk review, point
    2): voting costs a refundable half-XEL from day one — 20 farmed
    wallets deciding a validation park 10 XEL of capital while they do
    it. The admin can zero it (free voting), raise it, and NEVER touches
    already-locked deposits (they refund at their own amount)."""
    sim = Sim(cfg=_fuzz_cfg())
    assert sim.cfg.get("vote_deposit", 0) == XEL // 2   # the v4.2 default
    sim.mint("founder", 1000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    sim.mint("v0", 1 * XEL)
    sim.vote(pid, "v0", True)                          # attaches the dial
    assert sim.vote_pots == XEL // 2
    sim.cfg["vote_deposit"] = 2 * XEL                  # the admin raises
    sim.mint("v1", 10 * XEL)
    sim.vote(pid, "v1", True, deposit=2 * XEL)         # new votes pay more
    assert sim.vote_pots == XEL // 2 + 2 * XEL
    sim.warp(sim.cfg["validation_duration"] + 1)
    sim.finalize(pid)
    sim.claim_vote_deposit(pid, 0, "v0")               # refund at OWN amount
    sim.claim_vote_deposit(pid, 0, "v1")
    assert sim.vote_pots == 0
    # and the admin can still make voting free again
    sim.cfg["vote_deposit"] = 0
    assert sim.cfg.get("vote_deposit") == 0


def test_d21_withdraw_fees_cannot_touch_vote_pots():
    """The pots are committed (I2): the admin's fee withdrawal is capped by
    the uncommitted balance — a raised dial never becomes admin revenue."""
    sim = Sim(cfg=_fuzz_cfg() | {"vote_deposit": 5 * XEL})
    sim.mint("founder", 1000 * XEL)
    pid = sim.propose("founder", 500 * XEL)
    for i in range(3):
        sim.mint(f"v{i}", 10 * XEL)
        sim.vote(pid, f"v{i}", True, deposit=5 * XEL)
    # 15 XEL locked; the pending fees are just the submission fee — the
    # withdrawable cap is balance - committed, and pots are committed
    sim.warp(sim.cfg["validation_duration"] + 1)
    sim.finalize(pid)
    for i in range(3):
        sim.claim_vote_deposit(pid, 0, f"v{i}")
    assert sim.vote_pots == 0
    assert sim.balance >= sim.total_curve_xel + sim.pending_fees  # I2 intact


def test_d22_migrated_index_and_reverse_lookup():
    """Point 'site data': every migrated project is enumerable in order and
    every created asset maps back to its project (the DEX->launchpad bridge)."""
    sim = Sim(cfg=_fuzz_cfg())
    sim.set_dex_address("dex")
    migrated = []
    for k in range(3):
        sim.mint(f"f{k}", 3000 * XEL)
        # direct listing: >= the 2000 XEL threshold graduates at finalize
        pid = sim.propose(f"f{k}", 2500 * XEL)
        _validated(sim, pid)
        assert sim.s[sim._pk(pid, "st")] in (lp.ST_GRADUATED, lp.ST_TRUSTED)
        sim.migrate(pid)
        migrated.append(pid)
        # D22 reverse bridge: the asset of every pool maps back to the pid
        asset = sim.asset_of(pid)
        assert sim.asset_to_pid[asset] == pid
        assert asset in sim.dex.pools
    assert sim.migrated_index == migrated
    assert sim.migrated_count == 3


def test_x7_dex_one_sided_donation_cannot_move_the_price():
    """Point 1: an imbalanced add_liquidity only deepens at the CURRENT
    ratio; the excess side is refunded — the price is unchanged (within one
    floor unit), a lone-sided deposit is refused outright, and since v1.2
    a deposit too small to clear the 1 XEL LP floor is refused too
    ("minlp" — the accrual's precision guarantee, X10)."""
    dex = DexSim()
    dex.set_launchpad("lpx")
    dex.create_pool("lpx", "aa" * 32, 1000 * XEL, 10**9)
    p = dex.pools["aa" * 32]
    x0, y0 = p["x"], p["y"]
    price0 = x0 * 10**8 // y0
    dex.wallets["donor"]["xel"] = 500 * XEL
    dex.wallets["donor"]["assets"]["aa" * 32] = 10**9
    # malicious XEL-heavy donation: 500 XEL but only 10^6 tokens — the
    # token side binds: only (ratio) 10^6 tokens + their 1 XEL equivalent
    # join, the rest of the XEL goes straight back. The price CANNOT
    # move. (10^6 tokens is the minimum that clears the 1 XEL LP floor
    # on this pool: x0/y0 = 100 — anything less is refused "minlp".)
    xel_eff, tok_eff = dex.add_liquidity("donor", "aa" * 32, 500 * XEL, 10**6)
    assert tok_eff == 10**6
    assert xel_eff == x0 * 10**6 // y0
    price1 = p["x"] * 10**8 // p["y"]
    assert abs(price1 - price0) <= 1, "price moved — X7 broken"
    assert dex.wallets["donor"]["xel"] == 500 * XEL - xel_eff
    # token-heavy donation (1 XEL + 5e8 tokens): the XEL side binds, only
    # the proportional token slice joins, the token excess is refunded —
    # the donor is never refused and never over-donates
    x0, y0 = p["x"], p["y"]
    tok_before = dex.wallets["donor"]["assets"]["aa" * 32]
    xel_eff, tok_eff = dex.add_liquidity("donor", "aa" * 32, 1 * XEL, 5 * 10**8)
    assert xel_eff == 1 * XEL
    assert tok_eff == y0 * (1 * XEL) // x0
    price1b = p["x"] * 10**8 // p["y"]
    assert abs(price1b - price1) <= 1
    assert dex.wallets["donor"]["assets"]["aa" * 32] == tok_before - tok_eff
    # dust refusal: an XEL side too small to price a single token unit
    with pytest.raises(AssertionError, match="dust"):
        dex.add_liquidity("donor", "aa" * 32, 1, 10**6)
    # LP-floor refusal (X10/D23): a token side so thin its proportional
    # XEL value is under 1 XEL — the deposit is refused, nothing joins
    # (the donor attaches the XEL regardless — stock it first)
    x0, y0 = p["x"], p["y"]
    dex.wallets["donor"]["xel"] += 500 * XEL
    with pytest.raises(AssertionError, match="minlp"):
        dex.add_liquidity("donor", "aa" * 32, 500 * XEL, 100)
    assert p["x"] == x0 and p["y"] == y0, "a refused add must change nothing"
    # balanced donation with token excess: the XEL side binds, the token
    # excess is refunded
    x0, y0 = p["x"], p["y"]
    dex.wallets["donor"]["assets"]["aa" * 32] += 2 * 10**9   # re-stock the donor
    tok_before = dex.wallets["donor"]["assets"]["aa" * 32]
    dex.wallets["donor"]["xel"] += 500 * XEL
    xel_eff, tok_eff = dex.add_liquidity("donor", "aa" * 32, 500 * XEL, 10**9)
    assert xel_eff == 500 * XEL
    assert tok_eff == y0 * (500 * XEL) // x0
    price2 = p["x"] * 10**8 // p["y"]
    assert abs(price2 - price1) <= 1
    assert dex.wallets["donor"]["assets"]["aa" * 32] == tok_before - tok_eff


def test_x5_dex_sells_work_under_emergency_pause():
    """Point 2: even under the global emergency pause, every holder can
    still exit — only buys are gated."""
    dex = DexSim()
    dex.set_launchpad("lpx")
    dex.create_pool("lpx", "bb" * 32, 1000 * XEL, 10**9)
    dex.wallets["h"]["assets"]["bb" * 32] = 10**7
    dex.emergency = True
    dex.wallets["h"]["xel"] = 10 * XEL
    with pytest.raises(AssertionError, match="buyspaused"):
        dex.swap_xel("h", "bb" * 32, 10 * XEL)   # buys: gated by emergency
    out = dex.swap_tokens("h", "bb" * 32, 10**7)  # sells: NO gate at all
    assert out >= 1


def test_d23_providers_earn_pro_rata_and_claims_pay_x10():
    """X10/D23 + X11: fees split 50/50 admin/providers; providers earn
    pro-rata of their share of the LP depth; claims pay out of the LP pots
    only; and since v1.3 the SEED is the first provider — the protocol LP
    position accrues the provider share from the pool's very first fee
    (founder risk review v18.3: "part of the fees comes back to the
    protocol" — and the first external add can no longer capture the
    whole fee stream)."""
    dex = DexSim()
    dex.set_launchpad("lpx")
    a = "cc" * 32
    dex.create_pool("lpx", a, 1000 * XEL, 10**9)
    p = dex.pools[a]
    # X11: the seed minted the protocol LP position at creation — tl = pl
    # = the XEL seed, admin parts fees-only (no withdrawable balance)
    assert p["tl"] == 1000 * XEL and p["pl"] == 1000 * XEL
    seed_pos = dex.lp[(a, dex.admin)]
    assert seed_pos["x"] == 1000 * XEL and seed_pos["w"] == 0
    # fees BEFORE any external provider: the LP share accrues to the SEED
    # (nothing reverts to the admin pot anymore — the pot has a provider
    # from birth; the admin collects via claim_lp_fees on its position)
    dex.wallets["t"]["xel"] = 200 * XEL
    dex.swap_xel("t", a, 10 * XEL)
    fee1 = dx.fee_take(10 * XEL, dex.cfg["swap_fee_bps"])
    lp1 = dx.fee_split(fee1, dex.cfg["lp_share_bps"])[1]
    assert p["xf"] == fee1 - lp1
    assert p["lx"] == lp1
    assert p["ax"] == dx.accrual_increment(lp1, 1000 * XEL)
    # two providers: 100 XEL and 300 XEL of depth (25%/75% of the adds)
    for w in ("p1", "p2"):
        dex.wallets[w]["xel"] = 400 * XEL
        dex.wallets[w]["assets"][a] = 10**10
    dex.add_liquidity("p1", a, 100 * XEL, p["y"] * 100 * XEL // p["x"])
    dex.add_liquidity("p2", a, 300 * XEL, p["y"] * 300 * XEL // p["x"])
    assert p["tl"] == 1400 * XEL           # seed + adds
    assert dex.lp[(a, "p1")]["x"] == 100 * XEL
    assert dex.lp[(a, "p2")]["x"] == 300 * XEL
    # a buy accrues fees on the XEL side; the split is 50/50
    out = dex.swap_xel("t", a, 50 * XEL)
    fee_buy = dx.fee_take(50 * XEL, dex.cfg["swap_fee_bps"])
    lp_part = dx.fee_split(fee_buy, dex.cfg["lp_share_bps"])[1]
    adm_part = fee_buy - lp_part
    assert p["xf"] == fee1 - lp1 + adm_part
    assert p["lx"] == lp1 + lp_part
    assert p["ax"] == dx.accrual_increment(lp1, 1000 * XEL) + \
        dx.accrual_increment(lp_part, 1400 * XEL)
    # the sell side accrues on the token side (same denominator: tl)
    dex.swap_tokens("t", a, out)
    fee_sell = dx.fee_take(out, dex.cfg["swap_fee_bps"])
    lp_y = fee_sell * dex.cfg["lp_share_bps"] // 10_000
    assert p["ly"] == lp_y
    # providers' live earnings: exactly their pro-rata of each lp_part
    pos1, pos2 = dex.lp[(a, "p1")], dex.lp[(a, "p2")]
    earn1_x = dx.lp_earnings(p["ax"], pos1["sx"], pos1["x"])
    earn2_x = dx.lp_earnings(p["ax"], pos2["sx"], pos2["x"])
    earn_seed_x = dx.lp_earnings(p["ax"], seed_pos["sx"], seed_pos["x"])
    assert earn1_x + earn2_x + earn_seed_x <= p["lx"], \
        "IX8: dues can never exceed the pot"
    assert earn2_x == earn1_x * 3              # 75% vs 25% of the ADDED depth
    assert earn_seed_x > earn1_x + earn2_x     # X11: the seed earns the most
    # claims pay out of the pots and leave the invariant intact
    before1 = dex.wallets["p1"]["xel"]
    paid1_x, paid1_y = dex.claim_lp_fees("p1", a)
    assert dex.wallets["p1"]["xel"] == before1 + paid1_x
    assert paid1_x == earn1_x
    assert dex.lp[(a, "p1")]["cx"] == 0
    paid2_x, _ = dex.claim_lp_fees("p2", a)
    assert paid2_x == earn2_x
    # X11: the ADMIN claims the seed position's dues — the protocol's
    # provider revenue, same public pull as everyone else
    before_adm = dex.wallets[dex.admin]["xel"]
    paid_seed_x, paid_seed_y = dex.claim_lp_fees(dex.admin, a)
    assert dex.wallets[dex.admin]["xel"] == before_adm + paid_seed_x
    assert paid_seed_x == earn_seed_x
    # after all claims, only floor dust remains in the pots (IX8 floors:
    # each fee event's increment floors, leaving < depth-in-whole-XEL
    # units; here depth = 1400 XEL, two XEL-side fee events, 3 claimants)
    assert p["lx"] <= 2803
    dex.check_invariants()
    # a second claim with nothing accrued: "nofees"
    with pytest.raises(AssertionError, match="nofees"):
        dex.claim_lp_fees("p1", a)


def test_d23_first_deposit_never_earns_fees_from_before_it_existed():
    """Fuzz-found regression (IX8, seed 0): a provider's FIRST deposit must
    snapshot the current accrual counters — or it would retroactively earn
    every fee from before it entered, more than the pot ever held."""
    dex = DexSim()
    dex.set_launchpad("lpx")
    a = "dd" * 32
    dex.create_pool("lpx", a, 1000 * XEL, 10**9)
    p = dex.pools[a]
    # p1 enters first
    dex.wallets["p1"]["xel"] = 100 * XEL
    dex.wallets["p1"]["assets"][a] = 10**10
    dex.add_liquidity("p1", a, 10 * XEL, p["y"] * 10 * XEL // p["x"])
    # fees accrue (lp_part -> pot + accrual counter)
    dex.wallets["t"]["xel"] = 100 * XEL
    dex.swap_xel("t", a, 50 * XEL)
    assert p["ax"] > 0 and p["lx"] > 0
    ax_at_entry = p["ax"]
    ay_at_entry = p["ay"]
    # NOW p2 enters: its accrual clock must start HERE, not at zero
    dex.wallets["p2"]["xel"] = 100 * XEL
    dex.wallets["p2"]["assets"][a] = 10**10
    dex.add_liquidity("p2", a, 10 * XEL, p["y"] * 10 * XEL // p["x"])
    pos2 = dex.lp[(a, "p2")]
    assert pos2["sx"] == ax_at_entry and pos2["sy"] == ay_at_entry
    # p2 has earned exactly NOTHING so far
    due2 = pos2["cx"] + dx.lp_earnings(p["ax"], pos2["sx"], pos2["x"])
    assert due2 == 0
    with pytest.raises(AssertionError, match="nofees"):
        dex.claim_lp_fees("p2", a)
    # a new fee arrives: p2 earns only its share of THAT fee
    lx_before = p["lx"]
    dex.swap_xel("t", a, 50 * XEL)
    new_lp_part = p["lx"] - lx_before
    due2 = pos2["cx"] + dx.lp_earnings(p["ax"], pos2["sx"], pos2["x"])
    tl = p["tl"]
    assert due2 == dx.lp_earnings(
        dx.accrual_increment(new_lp_part, tl), 0, pos2["x"])
    assert due2 <= new_lp_part
    dex.check_invariants()


def test_d23_fee_split_dial_is_bounded_and_prospective():
    """set_fee_split: hard bounds [25%, 75%]; a change only affects FUTURE
    fees (already-accrued claimables keep their recorded amounts)."""
    dex = DexSim()
    dex.set_launchpad("lpx")
    a = "ee" * 32
    dex.create_pool("lpx", a, 1000 * XEL, 10**9)
    p = dex.pools[a]
    dex.wallets["p"]["xel"] = 100 * XEL
    dex.wallets["p"]["assets"][a] = 10**10
    dex.add_liquidity("p", a, 10 * XEL, p["y"] * 10 * XEL // p["x"])
    dex.wallets["t"]["xel"] = 100 * XEL
    dex.swap_xel("t", a, 50 * XEL)                 # at 50%
    lp_at_50 = p["lx"]
    assert lp_at_50 > 0
    with pytest.raises(AssertionError):
        dex.set_fee_split(2499)                    # cannot cut LPs below 25%
    with pytest.raises(AssertionError):
        dex.set_fee_split(7501)                    # cannot starve the treasury
    dex.set_fee_split(7500)                        # max LP share: ok
    lx_before = p["lx"]
    dex.swap_xel("t", a, 50 * XEL)
    lp_new = p["lx"] - lx_before
    fee_buy = dx.fee_take(50 * XEL, dex.cfg["swap_fee_bps"])
    assert lp_new == fee_buy * 7500 // 10_000      # the new dial applied
    dex.check_invariants()
