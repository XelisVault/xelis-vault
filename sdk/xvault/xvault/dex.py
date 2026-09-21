"""
xvault.dex — LaunchDEX reference implementation & RPC reader.

Python mirror of contracts/dex/LaunchDEX.slx. Every formula here MUST stay
byte-identical to the contract (CI cross-checks the math + the pinned
cross-call chunk ids in tests/test_dex_reference.py).

LaunchDEX is the permanent AMM for graduated tokens: one XEL-quote pool
per asset, constant-product pricing, and liquidity that can only ever
GROW (no remove_liquidity exists — the anti-rug core, X2). Pools are
seeded by VaultLaunch's atomic migration (cross-contract call with
attached deposits) and deepened by anyone via add_liquidity (a permanent
deepening). Since v1.2 every swap fee is SPLIT between the admin pot and
the pool's liquidity providers (X10/D23): each provider earns pro-rata
of their share of the pool's LP depth, claimable at any time via
claim_lp_fees (pull). The principal can never be clawed back — only
fees ever flow out.

Units: XEL and token amounts are atomic integers with 8 decimals
(1 XEL = 1 token = 100_000_000).
"""
from __future__ import annotations

from typing import Any, Dict

from . import protocol
from .protocol import DaemonClient, val_bool, val_hash, val_u64

# ---------------------------------------------------------------------------
# Defaults (must match the contract constants exactly)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "swap_fee_bps": 30,                        # 0.30% on swap inputs
    "min_seed_xel": 100_000_000,               # 1 XEL pool seed floor
    "min_seed_tokens": 1_000_000,              # 0.01 tokens seed floor
    "min_swap_xel": 1_000_000,                 # 0.01 XEL dust floor
    "max_swap_xel": 10_000_000_000_000,        # 100 000 XEL whale cap
    "min_swap_tokens": 1,
    "max_swap_tokens": 10_000_000_000_000_000, # 1e8 whole tokens
    "lp_share_bps": 5_000,                     # X10/D23: 50/50 admin/LP
}

# X10/D23 bounds (must match the contract constants exactly)
MIN_LP_SHARE_BPS = 2_500
MAX_LP_SHARE_BPS = 7_500
MIN_LP_ADD_XEL = 100_000_000                  # hard LP-entry floor (1 XEL)
ACC_SCALE = 100_000_000                       # accrual scale == floor

# ---------------------------------------------------------------------------
# Swap math — the contract's exact integer formulas (u128-safe)
# ---------------------------------------------------------------------------

def fee_take(amount: int, bps: int) -> int:
    """Swap fee on `amount`, floored in favour of the pool."""
    return amount * bps // 10_000


def xel_to_tokens_out(xel_reserve: int, token_reserve: int,
                      xel_in: int, fee_bps: int) -> int:
    """Buy quote: out = y * net / (x + net), floored (the pool keeps the
    rounding). Mirrors get_amount_out_xel / swap_xel_for_token."""
    net = xel_in - fee_take(xel_in, fee_bps)
    return token_reserve * net // (xel_reserve + net)


def tokens_to_xel_out(xel_reserve: int, token_reserve: int,
                      tokens_in: int, fee_bps: int) -> int:
    """Sell quote: out = x * net / (y + net), floored. Mirrors
    get_amount_out_token / swap_token_for_xel."""
    net = tokens_in - fee_take(tokens_in, fee_bps)
    return xel_reserve * net // (token_reserve + net)


def spot_price(xel_reserve: int, token_reserve: int,
               scale: int = 100_000_000) -> int:
    """Spot price: XEL (scaled by 1e8) per 1 whole token = x * 1e8 / y.
    Saturates at u64 max. Mirrors get_spot_price."""
    if token_reserve == 0:
        return 0
    return min(xel_reserve * scale // token_reserve, 2**64 - 1)


def liquidity_fit(xel_reserve: int, token_reserve: int,
                  xel_in: int, tok_in: int) -> tuple:
    """X7 (v1.1): the price-neutral fit add_liquidity enforces — the
    largest (xel_eff, tok_eff) pair at the pool's CURRENT ratio that fits
    inside the attached deposit. Returns (xel_eff, tok_eff, xel_back,
    tok_back): the effective liquidity and the refunded excess. Raises
    ValueError ("dust"/"ratio"/"minlp") exactly where the entry refuses.
    A donation can deepen a pool but NEVER move its price (founder risk
    review, point 1)."""
    x, y = xel_reserve, token_reserve
    if x <= 0 or y <= 0:
        raise ValueError("empty")
    need_tok = y * xel_in // x
    if tok_in >= need_tok:
        xel_eff, tok_eff = xel_in, need_tok
    else:
        need_xel = x * tok_in // y
        if xel_in < need_xel:
            raise ValueError("ratio")
        xel_eff, tok_eff = need_xel, tok_in
    if xel_eff < 1 or tok_eff < 1:
        raise ValueError("dust")
    if xel_eff < MIN_LP_ADD_XEL:
        raise ValueError("minlp")
    return xel_eff, tok_eff, xel_in - xel_eff, tok_in - tok_eff


def fee_split(fee: int, lp_bps: int) -> tuple:
    """X10/D23: split a swap fee between admin and providers.
    Returns (admin_part, lp_part), floored on the LP side in favour of
    the admin pot — exactly what both swap entries compute."""
    lp_part = fee * lp_bps // 10_000
    return fee - lp_part, lp_part


def lp_earnings(accrued: int, snapshot: int, parts: int) -> int:
    """X10/D23: a provider's fees earned since their last touch =
    (accrued - snapshot) * parts / ACC_SCALE, floored (the pot keeps the
    dust — by-construction over-collateralisation, IX8)."""
    if parts <= 0 or accrued <= snapshot:
        return 0
    return (accrued - snapshot) * parts // ACC_SCALE


def accrual_increment(lp_part: int, total_depth: int) -> int:
    """X10/D23: how much the per-unit accrual counter grows when lp_part
    reaches the pot: lp_part * ACC_SCALE / total_depth, floored. Result
    is always <= lp_part while total_depth >= ACC_SCALE (the 1 XEL LP
    floor) — IX8's bound."""
    if total_depth <= 0:
        return 0
    return lp_part * ACC_SCALE // total_depth


# ---------------------------------------------------------------------------
# Storage keys — must match the contract's key builders exactly
# ---------------------------------------------------------------------------

def pool_key(asset_hex: str, field: str) -> str:
    """q:{asset_hex}:{field} — `asset_hex` is the asset hash as 64 hex
    chars (Hash::to_hex() on-chain)."""
    return f"q:{asset_hex}:{field}"


def pool_index_key(index: int) -> str:
    return f"i:{index}"


F_XEL_RESERVE, F_TOK_RESERVE = "xr", "yr"
F_XEL_FEES, F_TOK_FEES = "xf", "yf"
F_BUYS_PAUSED, F_CREATED = "bp", "ct"
F_BUY_VOL, F_SELL_VOL, F_TRADES, F_LAST_TRADE = "bv", "sv", "tc", "lt"
F_LIFETIME_FEES, F_LP_COUNT, F_ASSET = "fl", "lp", "ah"
F_LP_POT_XEL, F_LP_POT_TOK = "lx", "ly"
F_LP_TOTAL, F_LP_ACC_XEL, F_LP_ACC_TOK = "tl", "ax", "ay"

# X10/D23 provider slots: l:{asset_hex}:{wallet}:{field}
LP_PREFIX = "l:"
LPF_XEL, LPF_SNAP_XEL, LPF_SNAP_TOK = "x", "sx", "sy"
LPF_CLAIM_XEL, LPF_CLAIM_TOK = "cx", "cy"


def lp_key(asset_hex: str, wallet: str, field: str) -> str:
    """l:{asset_hex}:{wallet}:{field} — a provider's slot in one pool.
    `wallet` is the address string exactly as Address::to_string()
    renders it on-chain (same format as the launchpad's v:{pid}:{round}
    vote keys)."""
    return f"l:{asset_hex}:{wallet}:{field}"

GLOBAL_KEYS = {
    "admin": "adm", "pools_count": "pc", "swap_fee_bps": "sfe",
    "launchpad": "lpx", "min_seed_xel": "mnx", "min_seed_tokens": "lnt",
    "min_swap_xel": "mnt", "max_swap_xel": "tsw",
    "min_swap_tokens": "mst", "max_swap_tokens": "mxs",
    "emergency": "xpa", "launchpad_pinned": "lpp",
    "fee_split_bps": "fsl",
}

# ---------------------------------------------------------------------------
# Invoke parameter builders (ValueCell) — positional, chunk-id addressed
# ---------------------------------------------------------------------------

def swap_xel_params(asset_hex: str, min_tokens_out: int) -> list:
    """swap_xel_for_token: attach XEL (the whole deposit swaps); the trade
    reverts if fewer than min_tokens_out would come out (slippage)."""
    return [val_hash(asset_hex), val_u64(min_tokens_out)]


def swap_token_params(asset_hex: str, min_xel_out: int) -> list:
    """swap_token_for_xel: attach the pool's tokens (whole deposit); sells
    are never selectively blocked (buys-pause blocks buys only — X5)."""
    return [val_hash(asset_hex), val_u64(min_xel_out)]


def swap_xel_deposits(xel_amount: int, xel_asset: str = "0" * 64) -> dict:
    return {xel_asset: xel_amount}


def swap_token_deposits(token_amount: int, asset_hex: str) -> dict:
    return {asset_hex: token_amount}


def add_liquidity_deposits(xel_amount: int, token_amount: int,
                           xel_asset: str = "0" * 64,
                           asset_hex: str = "") -> dict:
    """add_liquidity: attach BOTH assets (both must be > 0). A PERMANENT
    donation — there is no remove_liquidity (X2). `asset_hex` is the
    non-XEL side."""
    return {xel_asset: xel_amount, asset_hex: token_amount}


def add_liquidity_params(asset_hex: str) -> list:
    return [val_hash(asset_hex)]


def set_pool_buys_paused_params(asset_hex: str, flag: bool) -> list:
    """Launchpad-only entry (cross-called by sync_trust_to_dex — D17)."""
    return [val_hash(asset_hex), val_bool(flag)]


def set_swap_fee_params(bps: int) -> list:
    return [val_u64(bps)]


def set_trade_bounds_params(min_seed_xel: int, min_seed_tokens: int,
                            min_swap_xel: int, max_swap_xel: int,
                            min_swap_tokens: int, max_swap_tokens: int) -> list:
    return [val_u64(min_seed_xel), val_u64(min_seed_tokens),
            val_u64(min_swap_xel), val_u64(max_swap_xel),
            val_u64(min_swap_tokens), val_u64(max_swap_tokens)]


def set_launchpad_params(addr: str) -> list:
    from .protocol import val_addr
    return [val_addr(addr)]


def create_pool_params(asset_hex: str) -> list:
    """Launchpad-only entry (the migration endpoint — cross-called by
    VaultLaunch.migrate with the seed attached as deposits, D15)."""
    return [val_hash(asset_hex)]


def withdraw_fees_params(asset_hex: str, xel_amount: int,
                         token_amount: int) -> list:
    return [val_hash(asset_hex), val_u64(xel_amount), val_u64(token_amount)]


def set_fee_split_params(lp_bps: int) -> list:
    """set_fee_split (admin): the admin/providers revenue dial, in bps of
    every fee. Hard-bounded [2500, 7500] on-chain (MIN/MAX_LP_SHARE_BPS)."""
    return [val_u64(lp_bps)]


def claim_lp_fees_params(asset_hex: str) -> list:
    """claim_lp_fees (public, pull): pays the caller's OWN accrued
    provider fees on both sides (X10/D23). No deposits needed."""
    return [val_hash(asset_hex)]


# ---------------------------------------------------------------------------
# RPC reader (public nodes are fine — read-only)
# ---------------------------------------------------------------------------

class DexReader:
    def __init__(self, daemon: DaemonClient, contract: str):
        self.d = daemon
        self.contract = contract

    def _key(self, key: str, default: Any = None) -> Any:
        v = self.d.read_key(self.contract, key)
        return default if v is None else v

    def pools_count(self) -> int:
        return self._key(GLOBAL_KEYS["pools_count"], 0)

    def config(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            name: self._key(key, DEFAULTS.get(name, 0))
            for name, key in GLOBAL_KEYS.items()
            if name in DEFAULTS}
        out["launchpad"] = self._key(GLOBAL_KEYS["launchpad"])
        out["emergency"] = bool(self._key(GLOBAL_KEYS["emergency"], False))
        out["launchpad_pinned"] = bool(self._key(GLOBAL_KEYS["launchpad_pinned"], False))
        out["lp_share_bps"] = self._key(GLOBAL_KEYS["fee_split_bps"],
                                         DEFAULTS["lp_share_bps"])
        return out

    def pool_by_index(self, index: int) -> str:
        """Asset hash (hex) of the pool at `index` — listing enumeration."""
        return self._key(pool_index_key(index))

    def pool(self, asset_hex: str) -> Dict[str, Any]:
        """Everything the frontend needs for one pool card (mirrors
        get_pool + get_pool_state + get_pool_volume + get_spot_price)."""
        out: Dict[str, Any] = {"asset": asset_hex}
        for attr, field in (("xel_reserve", F_XEL_RESERVE),
                            ("token_reserve", F_TOK_RESERVE),
                            ("xel_fees", F_XEL_FEES),
                            ("token_fees", F_TOK_FEES),
                            ("buys_paused", F_BUYS_PAUSED),
                            ("created_topo", F_CREATED),
                            ("buy_volume", F_BUY_VOL),
                            ("sell_volume", F_SELL_VOL),
                            ("trades", F_TRADES),
                            ("last_trade_topo", F_LAST_TRADE),
                            ("lifetime_fees", F_LIFETIME_FEES),
                            ("lp_deposits", F_LP_COUNT),
                            ("lp_pot_xel", F_LP_POT_XEL),
                            ("lp_pot_tokens", F_LP_POT_TOK),
                            ("lp_total_depth", F_LP_TOTAL)):
            out[attr] = self._key(pool_key(asset_hex, field))
        x, y = out["xel_reserve"] or 0, out["token_reserve"] or 0
        out["price"] = spot_price(x, y)
        emergency = bool(self._key(GLOBAL_KEYS["emergency"], False))
        if emergency:
            # buys frozen, pool creation frozen, adds frozen — SELLS STAY
            # OPEN in every state (IX6; say so on the frontend)
            out["status_label"] = "emergency"
        elif out["buys_paused"]:
            out["status_label"] = "buys-paused"
        else:
            out["status_label"] = "live"
        return out

    def quotes(self, asset_hex: str, xel_amount: int = 0,
               token_amount: int = 0) -> Dict[str, int]:
        """Live quotes (mirrors get_amount_out_xel / get_amount_out_token):
        pass an xel_amount for the buy quote and/or a token_amount for the
        sell quote."""
        asset = asset_hex.lower()
        x = self._key(pool_key(asset, F_XEL_RESERVE), 0)
        y = self._key(pool_key(asset, F_TOK_RESERVE), 0)
        bps = self._key(GLOBAL_KEYS["swap_fee_bps"], DEFAULTS["swap_fee_bps"])
        out: Dict[str, int] = {"xel_reserve": x, "token_reserve": y,
                               "fee_bps": bps, "price": spot_price(x, y)}
        out["tokens_out"] = (xel_to_tokens_out(x, y, xel_amount, bps)
                             if xel_amount else 0)
        out["xel_out"] = (tokens_to_xel_out(x, y, token_amount, bps)
                          if token_amount else 0)
        return out

    def lp_info(self, asset_hex: str, wallet: str) -> Dict[str, int]:
        """X10/D23 provider position (mirrors get_lp_info): parts (XEL
        depth provided), crystallised claimables, and the LIVE available
        payout on both sides = claimables + everything accrued since the
        provider's last touch (computed here exactly like the contract's
        view — a pure read, nothing is claimed)."""
        a = asset_hex.lower()
        parts = self._key(lp_key(a, wallet, LPF_XEL), 0) or 0
        cx = self._key(lp_key(a, wallet, LPF_CLAIM_XEL), 0) or 0
        cy = self._key(lp_key(a, wallet, LPF_CLAIM_TOK), 0) or 0
        avail_x, avail_y = cx, cy
        if parts and parts > 0:
            ax = self._key(pool_key(a, F_LP_ACC_XEL), 0) or 0
            sx = self._key(lp_key(a, wallet, LPF_SNAP_XEL), 0) or 0
            avail_x += lp_earnings(ax, sx, parts)
            ay = self._key(pool_key(a, F_LP_ACC_TOK), 0) or 0
            sy = self._key(lp_key(a, wallet, LPF_SNAP_TOK), 0) or 0
            avail_y += lp_earnings(ay, sy, parts)
        return {"parts": parts, "claimable_xel": cx,
                "claimable_tokens": cy, "available_xel": avail_x,
                "available_tokens": avail_y}
