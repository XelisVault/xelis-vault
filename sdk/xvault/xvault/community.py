"""
xvault.community — CommunityLaunch reference implementation & RPC reader.

Python mirror of contracts/community/CommunityLaunch.slx. Every formula
here MUST stay byte-identical to the contract (CI cross-checks the math
and the pinned cross-call chunk id in tests/test_community_reference.py).

CommunityLaunch is the permissionless community-coin factory (the
"pump.fun track"): anyone launches a REAL XELIS confidential asset for
~2 XEL, pricing starts on a VIRTUAL-RESERVE bonding curve (the coin has
a sensible price and slippage from the first buy, with zero founder
capital), graduation fires inside the buy() that crosses the depth floor
AND the price-continuity condition, and the permissionless migrate()
seeds a permanent LaunchDEX pool via the OPEN endpoint (create_pool_open,
chunk 33) — the buyers' own money becomes the protocol-locked floor.

Units: XEL and token amounts are atomic integers with 8 decimals
(1 XEL = 1 token = 100_000_000).
"""
from __future__ import annotations

from typing import Any, Dict

from . import protocol
from .protocol import DaemonClient, val_hash, val_u64

# ---------------------------------------------------------------------------
# Defaults (must match the contract constants exactly)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "submission_fee": 100_000_000,          # 1 XEL per launch
    "asset_budget": 100_000_000,            # 1 XEL asset-creation floor
    "curve_fee_bps": 100,                   # 1.00% while LIVE
    "graduated_fee_bps": 50,                # 0.50% once graduated
    "migration_fee_bps": 50,                # 0.50% once, carved from the seed
    "graduation_depth": 5_000_000_000,      # 50 XEL of REAL reserves
    "virtual_xel": 10_000_000_000,          # 100 XEL of simulated depth
}

# Bounds (must match the contract constants exactly)
MAX_CREATOR_BPS = 500                       # 5% creator allocation cap
MIN_COIN_SUPPLY = 10_000_000_000_000        # 1M whole tokens
MAX_COIN_SUPPLY = 1_000_000_000_000_000_000  # 10B whole tokens
MIN_BUY_XEL = 1_000_000                     # 0.01 XEL dust floor
MAX_TRADE_XEL = 10_000_000_000_000          # 100 000 XEL whale cap
PRICE_SCALE = 100_000_000

# Status codes
ST_LIVE = 0
ST_GRADUATED = 1
ST_MIGRATED = 2

# The pinned cross-call chunk (asserted against LaunchDEX's real
# declaration order by tests/test_community_reference.py).
DEX_CREATE_POOL_OPEN_CHUNK = 33


# ---------------------------------------------------------------------------
# Curve math — the contract's exact integer formulas (u128-safe)
# ---------------------------------------------------------------------------

def fee_take(amount: int, bps: int) -> int:
    """Curve fee on `amount`, floored in favour of the contract."""
    return amount * bps // 10_000


def buy_tokens_out(xr: int, yr: int, y0: int, vx: int, net_xel: int) -> int:
    """Buy math on the VIRTUAL pair: out = (yr+y0) * net / ((xr+vx) + net),
    floored. Mirrors buy_tokens_out / buy. The trade additionally enforces
    out <= yr (the whale guard — only the REAL inventory can be paid)."""
    y_total = yr + y0
    x_total = xr + vx
    return y_total * net_xel // (x_total + net_xel)


def sell_xel_out(xr: int, yr: int, y0: int, vx: int, tokens: int) -> int:
    """Sell math on the VIRTUAL pair: gross = (xr+vx) * T / ((yr+y0) + T),
    floored. Mirrors sell_xel_out / sell (pre-fee gross)."""
    y_total = yr + y0
    x_total = xr + vx
    return x_total * tokens // (y_total + tokens)


def spot_price(xr: int, yr: int, y0: int, vx: int,
               scale: int = PRICE_SCALE) -> int:
    """Spot price: XEL (scaled by 1e8) per 1 whole token =
    (xr+vx) * 1e8 / (yr+y0). Saturates at u64 max. Mirrors
    get_current_price."""
    y_total = yr + y0
    if y_total == 0:
        return 0
    return min((xr + vx) * scale // y_total, 2**64 - 1)


def market_cap(xr: int, yr: int, y0: int, vx: int, total_supply: int) -> int:
    """Market cap (FDV convention): (xr+vx) * ts / (yr+y0), saturating at
    u64 max. Mirrors get_market_cap."""
    y_total = yr + y0
    if y_total == 0:
        return 0
    return min((xr + vx) * total_supply // y_total, 2**64 - 1)


def graduated(xr: int, yr: int, y0: int, vx: int, gdx: int) -> bool:
    """The C2 graduation predicate, evaluated on the POST-trade state:
    depth (xr >= gdx) AND price-continuity (xr*y0 >= yr*vx — the real
    ratio has overtaken the virtual ratio, so the migrated pool opens at
    a price at or above the curve's spot: no graduation dump)."""
    return xr >= gdx and xr * y0 >= yr * vx


def launch_fdv(vx: int, y0: int, total_supply: int) -> int:
    """FDV the moment a coin is born: spot = vx/(2*y0), cap = spot * ts
    (the virtual token reserve mirrors the initial inventory). With the
    defaults: 50 XEL."""
    return vx * total_supply // (2 * y0)


# ---------------------------------------------------------------------------
# Deposit builders (XELIS typed-parameter format)
# ---------------------------------------------------------------------------

def launch_deposits(xel_asset: str, sub_fee: int, budget: int) -> dict:
    """The launch_coin deposit: submission fee + asset budget (attach
    more to cover a chain fee rise — the unused part is refunded in the
    same transaction)."""
    return {xel_asset: sub_fee + budget}


def buy_deposits(xel_asset: str, xel_amount: int) -> dict:
    """The buy deposit: the WHOLE attached XEL trades."""
    return {xel_asset: xel_amount}


def sell_deposits(asset: str, token_amount: int) -> dict:
    """The sell deposit: the WHOLE attached token amount is sold."""
    return {asset: token_amount}


# ---------------------------------------------------------------------------
# Reader (RPC)
# ---------------------------------------------------------------------------

class CommunityReader:
    """Read-only view client for a deployed CommunityLaunch contract."""

    def __init__(self, daemon: DaemonClient, contract: str):
        self.d = daemon
        self.c = contract

    def _invoke(self, entry_id: int, params: list):
        return self.d.invoke_contract_method(self.c, entry_id, params)

    # -- coin data ---------------------------------------------------------

    def count(self) -> int:
        """Total coins ever launched (get_total_coins)."""
        return protocol.val_u64(self._invoke(40, []))

    def coin(self, cid: int) -> dict:
        """Lifecycle snapshot (get_coin)."""
        r = self._invoke(32, [val_u64(cid)])
        return {"creator": r[0], "status": int(r[1]), "created": int(r[2]),
                "total_supply": int(r[3]), "migrated": r[4]}

    def meta(self, cid: int) -> dict:
        """The display card (get_coin_meta)."""
        r = self._invoke(33, [val_u64(cid)])
        keys = ("name", "symbol", "description", "website", "logo",
                "twitter", "telegram", "discord")
        return dict(zip(keys, r))

    def tokenomics(self, cid: int) -> dict:
        """Tokenomics (get_coin_tokenomics)."""
        r = self._invoke(34, [val_u64(cid)])
        return {"total_supply": int(r[0]), "creator_bps": int(r[1]),
                "creator_alloc": int(r[2]), "creator_paid": int(r[3]),
                "creator_remaining": int(r[4])}

    def curve(self, cid: int) -> dict:
        """The curve's live state (get_curve_info) — the inputs of every
        formula: real reserves, real inventory, virtual constants."""
        r = self._invoke(35, [val_u64(cid)])
        return {"xr": int(r[0]), "yr": int(r[1]), "y0": int(r[2]),
                "vx": int(r[3]), "gdx": int(r[4])}

    def trading_stats(self, cid: int) -> dict:
        """Scoreboard (get_trading_stats)."""
        r = self._invoke(47, [val_u64(cid)])
        return {"buy_volume": int(r[0]), "sell_volume": int(r[1]),
                "trades": int(r[2]), "last_trade": int(r[3]),
                "volume": int(r[4])}

    def status_label(self, cid: int) -> str:
        """Human status (get_status_label): live / graduated / migrated."""
        return self._invoke(49, [val_u64(cid)])

    # -- quotes & prices ---------------------------------------------------

    def buy_quote(self, cid: int, xel_amount: int) -> int:
        """Tokens out for an attached XEL amount (get_buy_quote — the
        SAME helper the trade uses)."""
        return int(self._invoke(37, [val_u64(cid), val_u64(xel_amount)]))

    def sell_quote(self, cid: int, token_amount: int) -> int:
        """XEL out (post-fee) for a token amount (get_sell_quote)."""
        return int(self._invoke(38, [val_u64(cid), val_u64(token_amount)]))

    def price(self, cid: int) -> int:
        """Spot price, scaled 1e8 (get_current_price)."""
        return int(self._invoke(36, [val_u64(cid)]))

    def market_cap(self, cid: int) -> int:
        """FDV-style market cap (get_market_cap)."""
        return int(self._invoke(39, [val_u64(cid)]))

    # -- listings & bridges ------------------------------------------------

    def coins_by_status(self, status: int) -> int:
        """COUNT of coins with a status code (get_coins_by_status)."""
        return int(self._invoke(41, [val_u64(status)]))

    def coin_by_rank(self, status: int, rank: int) -> int:
        """Id of the rank-th coin with a status, oldest first
        (get_coin_by_rank). Sentinel: coin_count when out of range."""
        return int(self._invoke(42, [val_u64(status), val_u64(rank)]))

    def latest_coin(self, rank: int) -> int:
        """Id of the rank-th LATEST coin (get_latest_coin)."""
        return int(self._invoke(43, [val_u64(rank)]))

    def coin_by_asset(self, asset: str) -> int:
        """The reverse bridge: asset hash -> coin id (get_coin_by_asset).
        Sentinel: coin_count when unknown."""
        return int(self._invoke(44, [val_hash(asset)]))

    def migrated_count(self) -> int:
        """Coins ever migrated (get_migrated_count)."""
        return int(self._invoke(45, []))

    def migrated_by_rank(self, rank: int) -> int:
        """Id of the rank-th migrated coin (get_migrated_by_rank)."""
        return int(self._invoke(46, [val_u64(rank)]))

    # -- config ------------------------------------------------------------

    def config(self) -> dict:
        """Config snapshot (get_config): fees, floors, pause, pin state."""
        r = self._invoke(48, [])
        return {"submission_fee": int(r[0]), "asset_budget": int(r[1]),
                "curve_fee_bps": int(r[2]), "graduated_fee_bps": int(r[3]),
                "migration_fee_bps": int(r[4]),
                "graduation_depth": int(r[5]), "virtual_xel": int(r[6]),
                "paused": r[7], "dex_pinned": r[8]}

    def version(self) -> str:
        return self._invoke(50, [])
