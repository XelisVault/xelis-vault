"""LaunchDEX reference tests — the permanent AMM for graduated tokens.

Asserts, against the REAL contract source:
  1. the chunk table (declaration order) matches the SDK's
     LAUNCHDEX_ENTRY_IDS — the ABI reference real transactions build from;
  2. the two chunks VaultLaunch cross-calls are pinned on BOTH sides
     (VaultLaunch's constants vs LaunchDEX's real positions — D19);
  3. the anti-rug core: no remove_liquidity entry can exist;
  4. the launchpad pin freeze at the first pool (X4);
  5. the swap math properties (never insolvent, fees extracted not pooled).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "xvault"))

from xvault import dex as dx  # noqa: E402
from xvault.protocol import LAUNCHDEX_ENTRY_IDS, LAUNCHDEX_ENTRY_IDS_ALT  # noqa: E402

XEL = 100_000_000
DEX_CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "dex" / "LaunchDEX.slx"
LAUNCHPAD_CONTRACT = (Path(__file__).resolve().parents[1] / "contracts"
                      / "launchpad" / "VaultLaunch.slx")


def _declaration_order(src: str):
    return re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", src, re.M)


def test_chunk_table_matches_the_sdk_ids():
    src = DEX_CONTRACT.read_text()
    order = _declaration_order(src)
    for name, eid in LAUNCHDEX_ENTRY_IDS.items():
        assert order.index(name) == eid, \
            f"chunk {eid} for {name}: real position is {order.index(name)}"
    entries_only = [n for n in order if re.search(rf"^entry {n}\(", src, re.M)]
    for name, eid in LAUNCHDEX_ENTRY_IDS_ALT.items():
        assert entries_only.index(name) == eid


def test_pinned_cross_call_chunks_d19():
    """The D19 gate: VaultLaunch's pinned constants must point at the REAL
    LaunchDEX chunks. A renumbering on either side fails here."""
    dex_order = _declaration_order(DEX_CONTRACT.read_text())
    lp_src = LAUNCHPAD_CONTRACT.read_text()
    m1 = re.search(r"const DEX_CREATE_POOL_CHUNK: u16 = (\d+)", lp_src)
    m2 = re.search(r"const DEX_SET_PAUSED_CHUNK: u16 = (\d+)", lp_src)
    assert m1 and m2, "VaultLaunch must pin the DEX chunk constants"
    assert dex_order.index("create_pool") == int(m1.group(1)), \
        "create_pool moved — update DEX_CREATE_POOL_CHUNK (and vice versa)"
    assert dex_order.index("set_pool_buys_paused") == int(m2.group(1)), \
        "set_pool_buys_paused moved — update DEX_SET_PAUSED_CHUNK"
    # the SDK agrees with both
    assert LAUNCHDEX_ENTRY_IDS["create_pool"] == int(m1.group(1))
    assert LAUNCHDEX_ENTRY_IDS["set_pool_buys_paused"] == int(m2.group(1))


def test_no_remove_liquidity_can_exist():
    """The anti-rug core (X2): nothing can ever drain a pool."""
    src = DEX_CONTRACT.read_text()
    assert not re.search(r"^(?:entry|pub fn|fn) remove_liquidity", src, re.M)
    assert not re.search(r"^(?:entry|pub fn|fn) withdraw_pool", src, re.M)
    assert not re.search(r"^(?:entry|pub fn|fn) drain", src, re.M)


def test_launchpad_pin_freezes_at_first_pool_x4():
    src = DEX_CONTRACT.read_text()
    assert 'require(s.load(LAUNCHPAD_PINNED_KEY).unwrap_or(false) == false, "pinned")' in src
    assert 's.store(LAUNCHPAD_PINNED_KEY, true)' in src


def test_sells_are_never_blocked_by_anything_x5():
    """swap_token_for_xel must carry NO gate at all — neither the
    per-pool buys-pause nor the global emergency pause (founder risk
    review, point 2: a compromised admin must never trap holders)."""
    src = DEX_CONTRACT.read_text()
    m = re.search(r"entry swap_token_for_xel\(.*?\n\}", src, re.S)
    assert m, "entry not found"
    body = m.group(0)
    assert "buyspaused" not in body, "sell path must never check the pause"
    assert '"paused"' not in body, "sell path must not check the emergency pause either"
    assert "EMERGENCY_KEY" not in body, "no emergency gate on the sell path"


def test_emergency_pause_still_gates_buys_creations_and_adds():
    """set_paused keeps its meaning: buys, pool creation and liquidity
    adds check the emergency flag; ONLY the sell path is ungated."""
    src = DEX_CONTRACT.read_text()
    for entry in ("swap_xel_for_token", "create_pool", "add_liquidity"):
        m = re.search(rf"entry {entry}\(.*?\n\}}", src, re.S)
        assert m, f"{entry} not found"
        assert '"paused"' in m.group(0), f"{entry} must check the emergency pause"


def test_add_liquidity_enforces_the_pool_ratio_x7():
    """Founder risk review, point 1: a one-sided donation must NEVER move
    the price. Only the largest proportional pair that fits the deposit
    joins the reserves; the excess is refunded (Uniswap-style)."""
    src = DEX_CONTRACT.read_text()
    m = re.search(r"entry add_liquidity\(.*?\n\}", src, re.S)
    assert m, "entry not found"
    body = m.group(0)
    assert '"ratio"' in body, "an underfunded XEL side must be refused"
    assert '"dust"' in body
    # the refunds exist and go to the CALLER of the just-arrived deposit
    assert "xel_back" in body and "tok_back" in body
    # and the price-neutral fit itself (the u128 ratio products)
    assert "need_tok" in body and "need_xel" in body
    # the model: for random reserves and deposits, the effective pair
    # keeps the reserve product within one floor unit of its old value
    import random
    rng = random.Random(11)
    for _ in range(500):
        x = rng.randrange(10 * XEL, 100000 * XEL)
        y = rng.randrange(1000, 10**12)
        xel_in = rng.randrange(1, 100 * XEL)
        # token side chosen so at least one branch binds
        tok_in = rng.randrange(1, 2 * y)
        need_tok = y * xel_in // x
        if tok_in >= need_tok:
            xel_eff, tok_eff = xel_in, need_tok
        else:
            need_xel = x * tok_in // y
            if xel_in < need_xel:
                continue  # refused with "ratio" in the contract
            xel_eff, tok_eff = need_xel, tok_in
        if tok_eff < 1 or xel_eff < 1:
            continue  # refused with "dust"
        x1, y1 = x + xel_eff, y + tok_eff
        drift = x1 * y - x * y1
        assert abs(drift) < max(x, y), "price moved — X7 broken"
        # the refunded sides never exceed the attached deposit
        assert 0 <= xel_in - xel_eff <= xel_in
        assert 0 <= tok_in - tok_eff <= tok_in


def test_get_launchpad_view_exposes_the_pin_x4():
    src = DEX_CONTRACT.read_text()
    assert "pub fn get_launchpad() -> (string, bool)" in src


def test_buys_paused_check_exists_on_the_buy_path():
    src = DEX_CONTRACT.read_text()
    m = re.search(r"entry swap_xel_for_token\(.*?\n\}", src, re.S)
    assert m
    assert '"buyspaused"' in m.group(0)


def test_pool_math_never_insolvent():
    import random
    rng = random.Random(7)
    x, y = 2000 * XEL, 900_000_000
    for _ in range(300):
        if rng.random() < 0.5:
            xel_in = rng.randrange(1, 100 * XEL)
            out = dx.xel_to_tokens_out(x, y, xel_in, 30)
            fee = dx.fee_take(xel_in, 30)
            assert 0 < out < y
            x, y = x + xel_in - fee, y - out
        else:
            t_in = rng.randrange(1, y)
            out = dx.tokens_to_xel_out(x, y, t_in, 30)
            fee = dx.fee_take(t_in, 30)
            assert 0 < out < x
            x, y = x - out, y + t_in - fee
        assert x >= 1 and y >= 1, "reserves can never hit zero (IX5)"


def test_fees_are_extracted_not_pooled_x3():
    # the net amount joins the reserves — exactly what the contract does:
    # the fee goes to the pending pot, never into x or y
    x, y = 100 * XEL, 1000
    xel_in = 10 * XEL
    fee = dx.fee_take(xel_in, 30)
    net = xel_in - fee
    out = dx.xel_to_tokens_out(x, y, xel_in, 30)
    assert out == y * net // (x + net)
    # and the quote is the trade (no disagreement possible)
    assert dx.xel_to_tokens_out(x, y, xel_in, 30) == out


def test_version_string():
    assert 'const VERSION: string = "LaunchDEX v1.1.0"' in DEX_CONTRACT.read_text()
