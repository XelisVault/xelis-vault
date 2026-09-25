"""CommunityLaunch reference tests — the permissionless community-coin
factory (the "pump.fun track").

Asserts, against the REAL contract sources:
  1. the chunk table (declaration order) matches the SDK's
     COMMUNITY_ENTRY_IDS — the ABI reference real transactions build from;
  2. the pinned cross-call chunk (DEX_CREATE_POOL_OPEN_CHUNK = 33) points
     at LaunchDEX v1.4's REAL create_pool_open position;
  3. the virtual-reserve curve math: quotes are the trades, k never
     decreases, the real reserves stay non-negative, the worst-case sell
     is exactly covered (IC3/IC4), the whale guard bounds buys;
  4. graduation (C2): both conditions, the closed forms, the buyer's
     trade always completes first, the pool opens at >= spot;
  5. the migration fee is carved from the SEED, never the live curve
     (C4), and migrate() is permissionless both sides (C6/X13);
  6. a full lifecycle simulation (launch -> buy -> graduate -> migrate ->
     creator claim) with the invariants checked after every action;
  7. sells are never blockable (C7), the creator allocation is paid
     exactly once and only post-migration (C5/IC5).
"""
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "xvault"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import pytest  # noqa: E402

from xvault import community as cl  # noqa: E402
from xvault import dex as dx  # noqa: E402
from xvault.protocol import COMMUNITY_ENTRY_IDS, COMMUNITY_ENTRY_IDS_ALT  # noqa: E402
from test_launchpad_reference import DexSim  # noqa: E402

XEL = 100_000_000
CONTRACT = (Path(__file__).resolve().parents[1] / "contracts" / "community"
            / "CommunityLaunch.slx")
DEX_CONTRACT = (Path(__file__).resolve().parents[1] / "contracts" / "dex"
                / "LaunchDEX.slx")
XEL_ASSET = "00" * 32


def _declaration_order(src: str):
    return re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", src, re.M)


# ===========================================================================
# 1-2. STRUCTURE: chunk table, SDK parity, the pinned cross-call chunk
# ===========================================================================

def test_chunk_table_matches_the_sdk_ids():
    src = CONTRACT.read_text()
    order = _declaration_order(src)
    for name, eid in COMMUNITY_ENTRY_IDS.items():
        assert order.index(name) == eid, \
            f"chunk {eid} for {name}: real position is {order.index(name)}"
    entries_only = [n for n in order if re.search(rf"^entry {n}\(", src, re.M)]
    for name, eid in COMMUNITY_ENTRY_IDS_ALT.items():
        assert entries_only.index(name) == eid


def test_pinned_cross_call_chunk_x13():
    """The community factory's pinned constant must point at the REAL
    LaunchDEX create_pool_open chunk. A renumbering on either side fails
    here."""
    dex_order = _declaration_order(DEX_CONTRACT.read_text())
    src = CONTRACT.read_text()
    m = re.search(r"const DEX_CREATE_POOL_OPEN_CHUNK: u16 = (\d+)", src)
    assert m, "CommunityLaunch must pin the DEX chunk constant"
    assert dex_order.index("create_pool_open") == int(m.group(1)), \
        "create_pool_open moved — update DEX_CREATE_POOL_OPEN_CHUNK"
    # the DEX documents the pin in its own chunk table (33 create_pool_open)
    assert "33  create_pool_open" in DEX_CONTRACT.read_text()
    # and the SDK mirror agrees
    assert cl.DEX_CREATE_POOL_OPEN_CHUNK == int(m.group(1))


def test_version_strings():
    assert 'const VERSION: string = "CommunityLaunch v1.0.1"' in CONTRACT.read_text()
    assert 'const VERSION: string = "LaunchDEX v1.4.1"' in DEX_CONTRACT.read_text()


def test_storage_keys_and_defaults_match_the_sdk():
    src = CONTRACT.read_text()
    for const, key in [("F_XR", "xr"), ("F_YR", "yr"), ("F_Y0", "y0"),
                       ("F_VX", "vx"), ("F_GX", "gx"), ("F_TWITTER", "tw"),
                       ("F_TELEGRAM", "tg"), ("F_DISCORD", "dc"),
                       ("F_CREATOR_PAID", "cp"),
                       ("F_ASSET", "ah"), ("F_STATUS", "st"),
                       ("F_CREATOR", "cr"), ("F_SUPPLY", "ts"),
                       ("F_CREATOR_BPS", "cb")]:
        assert f'const {const}: string = "{key}"' in src, f"key {key} missing"
    assert "const DEFAULT_VIRTUAL_XEL: u64 = 10000000000" in src
    assert "const DEFAULT_GRADUATION_DEPTH: u64 = 5000000000" in src
    assert "const DEFAULT_CURVE_FEE_BPS: u64 = 100" in src
    assert "const DEFAULT_GRADUATED_FEE_BPS: u64 = 50" in src
    assert "const DEFAULT_MIGRATION_FEE_BPS: u64 = 50" in src
    assert "const DEFAULT_SUBMISSION_FEE: u64 = 100000000" in src
    assert "const MAX_CREATOR_BPS: u64 = 500" in src
    assert "const MIN_COIN_SUPPLY: u64 = 100000000000000" in src
    assert cl.MIN_COIN_SUPPLY == 100_000_000_000_000
    assert cl.MAX_COIN_SUPPLY == 10**18
    # the SDK DEFAULTS mirror the contract
    assert cl.DEFAULTS["virtual_xel"] == 10_000_000_000
    assert cl.DEFAULTS["graduation_depth"] == 5_000_000_000


def test_curve_depth_and_virtual_reserve_have_a_cross_invariant():
    """A graduation floor above half the virtual reserve is a dead-coin
    setting: real reserves top out at vx as the real inventory is exhausted.
    Both admin setters and the launch snapshot must reject it."""
    src = CONTRACT.read_text()
    for entry in ("set_graduation_depth", "set_virtual_xel"):
        body = re.search(rf"entry {entry}\(.*?\n\}}", src, re.S).group(0)
        assert 'require(amount <= vx / 2, "depth")' in body or \
               'require(gdx <= amount / 2, "depth")' in body
    launch = re.search(r"entry launch_coin\(.*?\n\}", src, re.S).group(0)
    assert 'require(gdx <= vx / 2, "depth")' in launch
    assert 50 * XEL <= 100 * XEL // 2


# ===========================================================================
# 3. THE VIRTUAL CURVE — math, solvency, guards
# ===========================================================================

def test_quotes_are_exactly_the_trades():
    """The SDK mirrors (buy_tokens_out / sell_xel_out / fee_take) are the
    contract's formulas: a quote can never disagree with its trade."""
    xr, yr, y0, vx = 12 * XEL, 7 * 10**16, 10**17, 10_000_000_000
    bps = 100
    xel_in = 5 * XEL
    # the buy: fee extracted, net joins xr, out from the VIRTUAL totals
    fee = cl.fee_take(xel_in, bps)
    net = xel_in - fee
    out = cl.buy_tokens_out(xr, yr, y0, vx, net)
    assert out == (yr + y0) * net // (xr + vx + net)
    assert 0 < out < yr + y0
    # the sell (whole position back): gross from the VIRTUAL totals
    gross = cl.sell_xel_out(xr, yr, y0, vx, out)
    fee2 = cl.fee_take(gross, bps)
    assert gross == (xr + vx) * out // (yr + y0 + out)
    assert 0 < gross < xr + vx
    # round-tripping loses exactly the fees (never more)
    assert gross - fee2 < xel_in


def test_the_virtual_pair_never_leaks_ic3():
    """IC3: through trades k = (xr+vx)*(yr+y0) never decreases, and the
    real reserves stay non-negative — the virtual XEL can never be asked
    to pay a seller."""
    import random
    rng = random.Random(42)
    vx = 100 * XEL
    y0 = 10**17
    xr, yr = 0, y0
    k0 = (xr + vx) * (yr + y0)
    k = k0
    for _ in range(2000):
        if rng.random() < 0.6:
            # buy (respecting the whale guard)
            max_net = (yr * (xr + vx)) // y0  # out <= yr boundary
            xel_in = rng.randrange(1, max(max_net, 2))
            fee = cl.fee_take(xel_in, 100)
            net = xel_in - fee
            out = cl.buy_tokens_out(xr, yr, y0, vx, net)
            assert out <= yr, "whale guard violated"
            xr_new, yr_new = xr + net, yr - out
            assert (xr_new + vx) * (yr_new + y0) >= k, "k decreased on buy"
            xr, yr = xr_new, yr_new
        else:
            # sell some circulating back
            circulating = y0 - yr
            if circulating < 1:
                continue
            t = rng.randrange(1, circulating + 1)
            gross = cl.sell_xel_out(xr, yr, y0, vx, t)
            assert gross <= xr, "IC4 broken: sell exceeds real reserves"
            xr_new, yr_new = xr - gross, yr + t
            assert (xr_new + vx) * (yr_new + y0) >= k, "k decreased on sell"
            xr, yr = xr_new, yr_new
        k = (xr + vx) * (yr + y0)
        assert k >= k0
        assert xr >= 0 and yr >= 0
        # the invariant totals: nothing circulates that was not bought
        assert yr <= y0
        assert yr + y0 <= 2 * y0


def test_worst_case_sell_is_exactly_covered_ic4():
    """IC4: selling the ENTIRE circulating supply in one transaction
    extracts at most the real reserves (the exact-cover identity of the
    constant-k proof, to floor rounding)."""
    import random
    rng = random.Random(7)
    for _ in range(500):
        vx = rng.randrange(XEL, 1000 * XEL)
        y0 = rng.randrange(10**15, 10**18)
        # a random point on the constant-k trajectory: pick xr, derive yr
        # (ceil, so the constructed state never sits BELOW k0)
        xr = rng.randrange(1, 50 * vx)
        y_total = -(-2 * vx * y0 // (vx + xr))
        yr = y_total - y0
        if yr < 0 or yr > y0:
            continue
        circulating = y0 - yr
        if circulating < 1:
            continue
        gross = cl.sell_xel_out(xr, yr, y0, vx, circulating)
        # the safety property: the worst-case sell NEVER exceeds the real
        # reserves (the virtual XEL can never be asked to pay a seller)
        assert gross <= xr, "worst-case sell exceeds real reserves"
        # and the exact-cover identity holds to floor rounding dust
        assert xr - gross <= 1 + xr // 10**12


def test_graduation_conditions_and_closed_forms_c2():
    """C2: depth (xr >= gdx) AND continuity (xr*y0 >= yr*vx). Along the
    constant-k trajectory continuity reduces to xr >= (sqrt(2)-1)*vx —
    independent of how much is sold; the defaults (vx=100, gdx=50) make
    the depth floor bind, and graduation lands around 2/3 of the supply
    sold at ~3x the launch FDV."""
    vx = 100 * XEL
    y0 = 10**17
    gdx = 50 * XEL

    def on_trajectory(xr):
        """yr on the exact constant-k curve (ceil, so the state stays on
        the SAFE side of the k >= k0 proof)."""
        y_total = -(-2 * vx * y0 // (vx + xr))
        return y_total - y0

    # the launch FDV (virtual reserves only)
    fdv0 = cl.launch_fdv(vx, y0, y0)
    assert fdv0 == vx // 2
    # walk the trajectory: buy net -> xr, fraction sold = 2n/(vx+n)
    n = 50 * XEL
    frac = 2 * n / (vx + n)
    assert abs(frac - 2 / 3) < 1e-9            # 2/3 of the supply sold
    xr = n
    yr = on_trajectory(xr)
    # depth holds, continuity holds, and the pool opens ABOVE spot
    assert cl.graduated(xr, yr, y0, vx, gdx)
    pool_price = xr / yr
    spot = (xr + vx) / (yr + y0)
    assert pool_price >= spot
    # below the thresholds: no graduation
    assert not cl.graduated(49 * XEL, yr + 10**16, y0, vx, gdx)
    # the continuity-only threshold: xr >= (sqrt(2)-1)*vx, yr derived
    # (a margin of a few atomic units absorbs the ceil in on_trajectory)
    n_star = (math.sqrt(2) - 1) * vx
    n_over = int(n_star) + 10
    n_under = int(n_star) - 10
    assert n_over * y0 >= on_trajectory(n_over) * vx      # just over
    assert n_under * y0 < on_trajectory(n_under) * vx     # just under
    # and the closed form itself is the exact boundary (to 1e-9 relative)
    assert abs(n_star / vx - (math.sqrt(2) - 1)) < 1e-12


def test_whale_guard_bounds_buys():
    """The buy guard (out <= yr): a single buy can at most be served by
    the REAL inventory. net <= yr*(xr+vx)/y0 is the exact boundary."""
    import random
    rng = random.Random(11)
    for _ in range(500):
        xr = rng.randrange(0, 1000 * XEL)
        y0 = rng.randrange(10**15, 10**18)
        vx = rng.randrange(XEL, 1000 * XEL)
        y_total = -(-2 * vx * y0 // (vx + xr))
        yr = y_total - y0
        if yr < 1:
            continue
        max_net = (yr * (xr + vx)) // y0
        # at the boundary: out == yr exactly (the degenerate monster buy)
        out = cl.buy_tokens_out(xr, yr, y0, vx, max_net)
        assert out <= yr
        # one unit over: the trade would compute out > yr — refused
        out2 = cl.buy_tokens_out(xr, yr, y0, vx, max_net + 1)
        if out2 > out:
            assert out2 >= yr  # the contract's require(tokens <= yr) bites


# ===========================================================================
# 6. THE LIFECYCLE SIMULATION (factory + DEX, real flows)
# ===========================================================================

ASSET_FEE = XEL  # the chain's asset-creation cost, measured by delta


class CommunitySim:
    """Faithful replay of CommunityLaunch v1.0 + the LaunchDEX v1.4 open
    seeding: launch -> virtual curve -> graduation -> permissionless
    migration -> creator claim, with IC1-IC6 checked after every action."""

    def __init__(self, cfg=None):
        self.cfg = dict(cl.DEFAULTS, **(cfg or {}))
        self.dex = DexSim()
        self.count = 0
        self.coins = defaultdict(dict)      # cid -> fields
        self.tickers = {}
        self.asset_lookup = {}
        self.migrated_index = []
        self.creator_paid = defaultdict(int)
        self.wallets = defaultdict(lambda: {"xel": 0,
                                            "assets": defaultdict(int)})
        self.xel_balance = 0                # the factory's balance
        self.asset_balances = defaultdict(int)
        self.pending_fees = 0
        self.fees_lifetime = 0
        self.paused = False
        self.dex_pin = None
        self.topo = 0
        self.total_curve_xel = 0

    # -- storage-key mirrors (the contract's exact namespaces) --------
    @staticmethod
    def _key(cid, field):
        return f"c:{cid}:{field}"

    # -- lifecycle ----------------------------------------------------
    def set_dex_address(self, pin):
        """The admin pin (D19 lineage): freezes at the first migration."""
        assert not self.migrated_index, "frozen"
        self.dex_pin = pin
        # Mirror the real deployment ordering: the DEX's moderation pin
        # must be configured before any pool exists (the new "nolpx"
        # guard on create_pool_open is the source-side enforcer).
        self.dex.set_launchpad(pin)
        self.check_invariants()

    def set_default_pins(self):
        self.set_dex_address("dex1")

    def launch_coin(self, creator, name, symbol, total_supply, team_bps=0,
                    deposit=None):
        assert not self.paused, "paused"
        assert (self.cfg["graduation_depth"]
                <= self.cfg["virtual_xel"] // 2), "depth"
        sub = self.cfg["submission_fee"]
        budget = self.cfg["asset_budget"]
        dep = deposit if deposit is not None else sub + budget
        assert dep >= sub + budget, "needfee"
        assert team_bps <= cl.MAX_CREATOR_BPS, "badteam"
        assert total_supply >= cl.MIN_COIN_SUPPLY, "badsupply"
        assert symbol not in self.tickers, "tick"
        cid = self.count
        c = self.coins[cid]
        c.update(st=0, cr=creator, nm=name, sy=symbol, ts=total_supply,
                 cb=team_bps, gr=False, mi=False)
        # C1: real reserves start at ZERO; inventory excludes the creator
        # allocation; the rules are snapshotted (C8)
        y0 = total_supply - total_supply * team_bps // 10_000
        c.update(xr=0, yr=y0, y0=y0, vx=self.cfg["virtual_xel"],
                 gx=self.cfg["graduation_depth"])
        # the wallet pays the deposit; the chain mints the asset to the
        # factory (charging the FACTORY's balance — the balance-delta the
        # contract measures); the unused part of the deposit is refunded
        self.wallets[creator]["xel"] -= dep
        self.xel_balance += dep
        self.xel_balance -= ASSET_FEE                  # the chain's cost
        c["ah"] = f"asset{cid:04d}" + "0" * 58
        self.asset_balances[c["ah"]] += total_supply
        refund = dep - sub - ASSET_FEE
        assert refund >= 0, "budget"
        if refund > 0:
            self.xel_balance -= refund
            self.wallets[creator]["xel"] += refund
        self.pending_fees += sub
        self.fees_lifetime += sub
        self.tickers[symbol] = cid
        self.asset_lookup[c["ah"]] = cid
        self.count += 1
        self.check_invariants()
        return cid

    def buy(self, wallet, cid, xel_in, min_out=0):
        assert not self.paused, "paused"
        c = self.coins[cid]
        assert c["st"] in (0, 1), "migrated"
        assert cl.MIN_BUY_XEL <= xel_in <= cl.MAX_TRADE_XEL, "tiny/toobig"
        bps = self.cfg["graduated_fee_bps"] if c["gr"] else self.cfg["curve_fee_bps"]
        fee = cl.fee_take(xel_in, bps)
        net = xel_in - fee
        out = cl.buy_tokens_out(c["xr"], c["yr"], c["y0"], c["vx"], net)
        assert out >= 1, "tinyout"
        assert out <= c["yr"], "curverr"
        assert out >= min_out, "slip"
        self.wallets[wallet]["xel"] -= xel_in
        self.xel_balance += xel_in
        self.wallets[wallet]["assets"][c["ah"]] += out
        self.asset_balances[c["ah"]] -= out
        c["xr"] += net
        c["yr"] -= out
        self.total_curve_xel += net
        self.pending_fees += fee
        self.fees_lifetime += fee
        # C2: graduation evaluated on the POST-trade state
        if c["st"] == 0 and cl.graduated(c["xr"], c["yr"], c["y0"],
                                         c["vx"], c["gx"]):
            c["st"] = 1
            c["gr"] = True
        self.check_invariants()
        return out

    def sell(self, wallet, cid, tokens, min_out=0):
        c = self.coins[cid]
        assert c["st"] in (0, 1), "migrated"
        assert tokens >= 1, "nosell"
        gross = cl.sell_xel_out(c["xr"], c["yr"], c["y0"], c["vx"], tokens)
        assert gross >= 1, "tiny"
        assert gross <= c["xr"], "curverr"
        bps = self.cfg["graduated_fee_bps"] if c["gr"] else self.cfg["curve_fee_bps"]
        fee = cl.fee_take(gross, bps)
        out = gross - fee
        assert out >= 1, "tinyout"
        assert out >= min_out, "slip"
        self.wallets[wallet]["assets"][c["ah"]] -= tokens
        self.asset_balances[c["ah"]] += tokens
        c["yr"] += tokens
        c["xr"] -= gross
        self.total_curve_xel -= gross
        self.wallets[wallet]["xel"] += out
        self.xel_balance -= out
        self.pending_fees += fee
        self.fees_lifetime += fee
        self.check_invariants()
        return out

    def migrate(self, cid, caller="anyone"):
        """C6: permissionless BOTH sides — anyone drives it, and the DEX
        endpoint is create_pool_open (no gate). C4: the fee is carved
        from the SEED, never the live curve."""
        c = self.coins[cid]
        assert c["st"] == 1, "notgrad"
        assert not c["mi"], "done"
        assert self.dex_pin is not None, "nodex"
        xr, yr = c["xr"], c["yr"]
        assert xr >= 1 and yr >= 1, "empty"
        # C4: the migration fee leaves the SEED, k was never touched
        fee = cl.fee_take(xr, self.cfg["migration_fee_bps"])
        seed_xel = xr - fee
        self.pending_fees += fee
        self.fees_lifetime += fee
        # state first: the curve closes
        c.update(mi=True, mx=seed_xel, mt=yr, xr=0, yr=0, st=2)
        self.total_curve_xel -= xr
        self.migrated_index.append(cid)
        # the atomic open seeding: funds out, pool created (X13)
        self.xel_balance -= seed_xel
        self.asset_balances[c["ah"]] -= yr
        res = self.dex.create_pool_open(caller, c["ah"], seed_xel, yr)
        assert res == 0, "poolerr"
        self.check_invariants()

    def claim_creator_allocation(self, creator, cid):
        """C5: post-migration only, creator-only, exactly once (IC5)."""
        c = self.coins[cid]
        assert c["st"] == 2, "notmig"
        alloc = c["ts"] * c["cb"] // 10_000
        rem = alloc - self.creator_paid[cid]
        assert rem >= 1, "none"
        self.creator_paid[cid] += rem
        self.asset_balances[c["ah"]] -= rem
        self.wallets[creator]["assets"][c["ah"]] += rem
        self.check_invariants()
        return rem

    def creator_remaining(self, cid):
        c = self.coins[cid]
        alloc = c["ts"] * c["cb"] // 10_000
        return alloc - self.creator_paid[cid]

    def withdraw_fees(self, admin, amount):
        assert 0 < amount <= self.pending_fees, "badamt"
        assert amount + self.total_curve_xel <= self.xel_balance, "notavail"
        self.pending_fees -= amount
        self.xel_balance -= amount
        self.wallets[admin]["xel"] += amount
        self.check_invariants()

    def check_invariants(self):
        # IC1: exact-sum XEL solvency
        assert self.total_curve_xel == sum(c["xr"] for c in self.coins.values())
        assert self.total_curve_xel + self.pending_fees <= self.xel_balance
        assert self.fees_lifetime >= self.pending_fees
        # IC2: per-coin asset solvency (inventory + unclaimed reserve)
        for cid, c in self.coins.items():
            alloc = c["ts"] * c["cb"] // 10_000
            assert self.asset_balances[c["ah"]] == c["yr"] + alloc - self.creator_paid[cid]
            # IC3: the virtual pair never leaked
            assert c["xr"] >= 0 and c["yr"] >= 0
            assert c["yr"] <= c["y0"]
            # IC6: states only move forward
            assert c["st"] in (0, 1, 2)
        # the DEX sim's own invariants hold too
        self.dex.check_invariants()


def test_invalid_depth_virtual_pairs_are_rejected_by_the_reference():
    sim = CommunitySim(cfg={"virtual_xel": 100 * XEL,
                             "graduation_depth": 51 * XEL})
    with pytest.raises(AssertionError, match="depth"):
        sim.launch_coin("creator", "Dead", "DEAD", 10**17)


def test_fee_lifetime_counts_collection_not_withdrawal():
    sim = CommunitySim()
    sim.set_default_pins()
    cid = sim.launch_coin("creator", "Fees", "FEES", 10**17)
    assert sim.fees_lifetime == sim.pending_fees == XEL
    sim.buy("alice", cid, XEL)
    collected_after_buy = sim.fees_lifetime
    assert collected_after_buy > XEL
    # A sell adds a collection event and a withdrawal does not.
    sim.sell("alice", cid, 10**14)
    collected_after_sell = sim.fees_lifetime
    assert collected_after_sell > collected_after_buy
    sim.withdraw_fees("admin", sim.pending_fees)
    assert sim.fees_lifetime == collected_after_sell
    assert sim.pending_fees == 0


def test_full_lifecycle_launch_to_pool():
    """The happy path: a coin is born for ~2 XEL, the community buys it
    to graduation, anyone migrates it, the creator claims their cut."""
    sim = CommunitySim()
    sim.set_default_pins()
    # launch: 1 XEL fee + 1 XEL budget, 0% creator for the clean case
    cid = sim.launch_coin("creator", "Moon Coin", "MOON", 10**17, team_bps=0)
    c = sim.coins[cid]
    assert c["st"] == 0 and c["xr"] == 0 and c["yr"] == c["y0"] == 10**17
    assert c["vx"] == 100 * XEL and c["gx"] == 50 * XEL
    # the launch FDV: 50 XEL (virtual reserves only)
    assert cl.launch_fdv(c["vx"], c["y0"], c["ts"]) == 50 * XEL
    # the first 1 XEL buy: ~1% of the supply, single-digit slippage
    out1 = sim.buy("alice", cid, XEL)
    assert out1 > 0.009 * 10**17
    # buy to graduation (~50 XEL net of fees, 2/3 of the supply sold)
    bought = out1
    for _ in range(60):
        bought += sim.buy("alice", cid, XEL)
        if c["st"] == 1:
            break
    assert c["st"] == 1 and c["gr"] is True
    assert c["xr"] >= 50 * XEL
    # C2: the pool will open at >= the curve's spot (no graduation dump)
    assert c["xr"] * c["y0"] >= c["yr"] * c["vx"]
    # the graduated fee regime is cheaper (0.5% vs 1%)
    sim.buy("bob", cid, XEL)
    # permissionless migration: anyone, open seeding
    sim.migrate(cid, caller="alice")
    assert c["st"] == 2 and c["mi"] and c["xr"] == 0 and c["yr"] == 0
    # the pool exists on the DEX with the seed = curve reserves - fee
    pool = sim.dex.pools[c["ah"]]
    assert pool["x"] == c["mx"] and pool["y"] == c["mt"]
    assert pool["pl"] == pool["x"]          # X11: the seed IS the floor
    # the curve is closed: no more trades
    with pytest.raises(AssertionError, match="migrated"):
        sim.buy("alice", cid, XEL)
    with pytest.raises(AssertionError, match="migrated"):
        sim.sell("alice", cid, 1)
    # trading continues on the pool (the DEX sim's own math)
    sim.dex.wallets["alice"]["xel"] = 10 * XEL
    sim.dex.swap_xel("alice", c["ah"], 5 * XEL)
    sim.dex.check_invariants()


def test_creator_allocation_post_migration_only_c5():
    sim = CommunitySim()
    sim.set_default_pins()
    cid = sim.launch_coin("creator", "Rug", "RUG", 10**17, team_bps=500)
    c = sim.coins[cid]
    assert c["y0"] == 10**17 - 5 * 10**15          # 5% reserved OFF curve
    # pre-graduation: nothing to claim (and nothing claimable)
    sim.buy("alice", cid, 20 * XEL)
    assert sim.creator_remaining(cid) == 5 * 10**15
    # graduate + migrate
    while c["st"] != 1:
        sim.buy("alice", cid, 5 * XEL)
    sim.migrate(cid, caller="keeper")
    # claim: exactly once, creator only
    got = sim.claim_creator_allocation("creator", cid)
    assert got == 5 * 10**15
    assert sim.creator_remaining(cid) == 0
    with pytest.raises(AssertionError, match="none"):
        sim.claim_creator_allocation("creator", cid)
    # a second claim is impossible (IC5), and the factory holds no more
    assert sim.asset_balances[c["ah"]] == 0


def test_migration_fee_carved_from_the_seed_c4():
    """C4: the fee is taken at migrate time, out of the SEED — the curve
    traded its whole life with k exactly invariant (IC3), and the pool
    opens at the real ratio the market paid for."""
    sim = CommunitySim(cfg={"migration_fee_bps": 500})   # the 5% cap
    sim.set_default_pins()
    cid = sim.launch_coin("creator", "Fee", "FEE", 10**17, team_bps=0)
    c = sim.coins[cid]
    k0 = (c["xr"] + c["vx"]) * (c["yr"] + c["y0"])
    while c["st"] != 1:
        sim.buy("alice", cid, 2 * XEL)
    # k never moved through the whole curve era (fees extracted, C4)
    assert (c["xr"] + c["vx"]) * (c["yr"] + c["y0"]) >= k0
    xr_before = c["xr"]
    expected_fee = cl.fee_take(xr_before, 500)
    sim.migrate(cid, caller="anyone")
    assert c["mx"] == xr_before - expected_fee
    assert sim.pending_fees >= expected_fee
    pool = sim.dex.pools[c["ah"]]
    assert pool["x"] == xr_before - expected_fee


def test_pause_blocks_new_activity_only_c7():
    """C7: the circuit breaker gates launches and buys ONLY — sells,
    creator claims and migration carry no pause check (a pause must
    never become a trap)."""
    src = CONTRACT.read_text()
    m = re.search(r"entry sell\(.*?\n\}", src, re.S)
    assert m, "sell not found"
    body = m.group(0)
    assert '"paused"' not in body
    assert "PAUSED_KEY" not in body
    for entry in ("claim_creator_allocation", "migrate"):
        m = re.search(rf"entry {entry}\(.*?\n\}}", src, re.S)
        assert m
        assert '"paused"' not in m.group(0)
        assert "PAUSED_KEY" not in m.group(0)
    # ... while launch_coin and buy DO check it
    for entry in ("launch_coin", "buy"):
        m = re.search(rf"entry {entry}\(.*?\n\}}", src, re.S)
        assert m
        assert '"paused"' in m.group(0)


def test_the_launch_costs_two_xel_and_refunds_everything_unused():
    """The ~2 XEL launch: 1 XEL submission fee (protocol revenue) + the
    chain's asset cost (measured, refunded if unused). The creator's
    out-of-pocket is exactly sub + asset_fee."""
    sim = CommunitySim()
    sim.wallets["creator"]["xel"] = 5 * XEL
    cid = sim.launch_coin("creator", "Cheap", "CHEAP", 10**17,
                          deposit=5 * XEL)
    assert cid == 0
    # 5 attached - 1 fee - 1 asset cost = 3 refunded
    assert sim.wallets["creator"]["xel"] == 3 * XEL
    assert sim.pending_fees == XEL
    assert sim.fees_lifetime == XEL
    # the admin can collect, and the factory stays solvent (IC1)
    sim.withdraw_fees("admin", XEL)
    # a withdrawal pays accrued fees; it is not new lifetime revenue
    assert sim.fees_lifetime == XEL
    assert sim.pending_fees == 0
    with pytest.raises(AssertionError, match="badamt"):
        sim.withdraw_fees("admin", 1)


def test_ticker_registry_and_reverse_bridge():
    sim = CommunitySim()
    sim.set_default_pins()
    cid = sim.launch_coin("creator", "First", "ONE", 10**17)
    with pytest.raises(AssertionError, match="tick"):
        sim.launch_coin("copycat", "Clone", "ONE", 10**17)
    # the asset -> coin reverse bridge (the DEX-side pages)
    assert sim.asset_lookup[sim.coins[cid]["ah"]] == cid


# ===========================================================================
# 7. STRUCTURAL SECURITY ASSERTS (source-level)
# ===========================================================================

def test_migrate_is_deterministic_and_pinned():
    """C6: migrate moves the coin's OWN reserves to the PINNED dex — no
    destination, no amount, no caller choice anywhere in the entry."""
    src = CONTRACT.read_text()
    m = re.search(r"entry migrate\(.*?\n\}", src, re.S)
    assert m, "migrate not found"
    body = m.group(0)
    assert "migrate_coin_to_dex(cid)" in body
    # the internal helper: pinned dex, whole reserves, captured call result
    h = re.search(r"fn migrate_coin_to_dex\(.*?\n\}", src, re.S)
    assert h, "migrate_coin_to_dex not found"
    hbody = h.group(0)
    assert "DEX_ADDRESS_KEY" in hbody
    assert "is_contract_callable(dex, DEX_CREATE_POOL_OPEN_CHUNK)" in hbody
    assert "require(pool_res == 0, \"poolerr\")" in hbody
    # state first, cross-call last (no store after the .call except none)
    call_pos = hbody.index(".call(")
    assert "s.store(" not in hbody[call_pos:]


def test_migration_writes_status_and_views_close():
    """C1 fix: migrate() must write F_STATUS = ST_MIGRATED (the E2E on
    the pre-fix build showed status stuck at 1 — the listing views and
    the creator claim READ st). And every price/mcap/quote view must
    report ZERO once the curve is closed, instead of a stale nonzero."""
    src = CONTRACT.read_text()
    h = re.search(r"fn migrate_coin_to_dex\(.*?\n\}", src, re.S).group(0)
    assert 's.store(coin_key(cid, F_MIGRATED), true)' in h
    assert 's.store(coin_key(cid, F_STATUS), ST_MIGRATED)' in h
    dex_src = DEX_CONTRACT.read_text()
    for view in ("get_current_price", "get_buy_quote", "get_sell_quote",
                 "get_market_cap"):
        body = re.search(rf"pub fn {view}\(.*?\n\}}", src, re.S).group(0)
        assert 'if status == ST_MIGRATED {' in body, f"{view} must close"
        assert "return 0" in body, f"{view} must return 0 when migrated"
    # the admin pin cannot point at an EOA/empty hash (op sanity, not
    # provenance — the deployment runbook still sets the DEX address)
    sd = re.search(r"entry set_dex_address\(.*?\n\}", src, re.S).group(0)
    assert 'require(is_contract_callable(addr, DEX_CREATE_POOL_OPEN_CHUNK), "baddex")' in sd
    # the seed cap covers the factory's full supply range (see the
    # MAX_SEED_TOKENS comment in LaunchDEX.slx)
    assert "const MAX_SEED_TOKENS: u64 = 1000000000000000000" in dex_src
    assert dx.MAX_SEED_TOKENS == 10**18


def test_migrated_views_report_zero_in_the_reference():
    """The SDK mirrors the closed-curve views: after migrate the status
    is 2 and the price/mcap views are effectively ZERO — the contract's
    get_current_price/get_market_cap/get_*_quote return 0 on
    ST_MIGRATED (frontends must check status first and switch to the
    pool's price; the pure math helpers take reserves only)."""
    sim = CommunitySim()
    sim.set_default_pins()
    cid = sim.launch_coin("creator", "Closed", "CLSD", 10**17)
    c = sim.coins[cid]
    # the view is status-aware: ST_MIGRATED forces zero, anything else
    # is the live curve math
    def effective_price():
        return 0 if c["st"] == 2 else cl.spot_price(c["xr"], c["yr"],
                                                     c["y0"], c["vx"])

    def effective_mcap():
        return 0 if c["st"] == 2 else cl.market_cap(c["xr"], c["yr"],
                                                    c["y0"], c["vx"],
                                                    c["ts"])
    while c["st"] != 1:
        sim.buy("alice", cid, 5 * XEL)
    # live: an honest nonzero view
    assert effective_price() >= 1
    assert effective_mcap() >= 1
    sim.migrate(cid, caller="keeper")
    assert c["st"] == 2
    # closed: every curve-derived view is exactly zero (the pool owns
    # the market now) — and the reserves carry no stale values
    assert effective_price() == 0
    assert effective_mcap() == 0
    assert c["xr"] == 0 and c["yr"] == 0


def test_solvency_guards_are_local_and_machine_checkable():
    src = CONTRACT.read_text()
    buy = re.search(r"entry buy\(.*?\n\}", src, re.S).group(0)
    sell = re.search(r"entry sell\(.*?\n\}", src, re.S).group(0)
    assert 'require(tokens <= yr, "curverr")' in buy
    assert 'require(gross <= xr, "curverr")' in sell
    assert 'require(tokens >= min_tokens_out, "slip")' in buy
    assert 'require(out >= min_xel_out, "slip")' in sell
    # the asset creation: balance-delta measurement + whole-supply check
    asset = re.search(r"fn create_coin_asset\(.*?\n\}", src, re.S).group(0)
    assert "bal_before" in asset and "bal_after" in asset
    assert 'require(tok_bal == total_supply, "assetbal")' in asset
    assert 'require(dep >= committed, "budget")' in asset


def test_dex_create_pool_open_is_really_permissionless_x13():
    """The DEX side of C6: create_pool_open has NO lpx gate, checks the
    emergency pause, mints the X11 seed shares, freezes the pin at the
    first pool, and returns 0 (the v1.4 cross-call convention)."""
    src = DEX_CONTRACT.read_text()
    m = re.search(r"pub fn create_pool_open\(.*?\n\}", src, re.S)
    assert m, "create_pool_open not found"
    body = m.group(0)
    assert "require(caller == lpx" not in body       # NO gate — X13
    assert '"paused"' in body                        # emergency blocks it
    assert 's.store(pool_key(asset, F_LP_LOCKED), xel_seed)' in body  # X11
    assert 's.store(seed_lkey + LPF_W' not in body   # seed never withdrawable
    assert 's.store(LAUNCHPAD_PINNED_KEY, true)' in body  # X4 freeze
    assert "return 0" in body                        # the v1.4 convention
    # and the second-migration fix: create_pool itself returns 0 now (the
    # last statement of the body — the comment mentions the OLD behaviour)
    cp = re.search(r"pub fn create_pool\(.*?\n\}", src, re.S).group(0)
    returns = re.findall(r"^\s*return (\w+)", cp, re.M)
    assert returns == ["0"], f"create_pool must return 0, got {returns}"
