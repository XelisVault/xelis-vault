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


def test_sells_are_never_selectively_blocked_x5():
    """swap_token_for_xel must not check the buys-pause flag; only the
    global emergency pause gates it."""
    src = DEX_CONTRACT.read_text()
    m = re.search(r"entry swap_token_for_xel\(.*?\n\}", src, re.S)
    assert m, "entry not found"
    body = m.group(0)
    assert "buyspaused" not in body, "sell path must never check the pause"
    assert '"paused"' in body, "only the emergency pause gates sells"


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
    assert 'const VERSION: string = "LaunchDEX v1.0.0"' in DEX_CONTRACT.read_text()
