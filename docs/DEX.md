# LaunchDEX — Design Specification

> contracts/dex/LaunchDEX.slx · v1.1.0 · the permanent AMM for
> VaultLaunch-graduated tokens

LaunchDEX is the migration target of VaultLaunch: one XEL-quote pool per
asset, constant-product pricing, and liquidity that can only ever GROW.
There is **no `remove_liquidity` entry** — by design. Pools are seeded
atomically by the launchpad's `migrate()` and deepened by anyone via
`add_liquidity` (a permanent donation at the market's own price). That
is the anti-rug guarantee a serious launchpad owes its buyers: the
deeper the pool, the safer the market, and nobody — not the admin, not
the founder, not the launchpad — can ever drain it.

**v1.1 — hardened by the founder risk review.** (1) `add_liquidity` is
now **price-neutral** (X7): the pool's current ratio is enforced,
Uniswap-style — only the proportional slice of the deposit joins the
reserves, the excess side is refunded in the same transaction; a
one-sided or skewed donation can deepen a pool but can NEVER move its
price (only swaps do). (2) **Sells are ungated, absolutely** (IX6):
the emergency pause now gates buys, pool creation and liquidity adds
ONLY — the sell path carries no gate at all, so even a compromised
admin can never trap holders (it can tax, fees are hard-capped at 10%,
but never lock). (3) New `get_launchpad()` view exposes the pinned
launchpad and its freeze state — the ops/frontend bridge for the
upgrade runbook (LAUNCHPAD.md §5b).

**Why not the legacy VaultSwapV2?** The old AMM charges its treasury fee
from the contract's raw balance without reserve accounting (insolvency
grows with every swap), never implemented LP accounting, and carries
oracle/PSM/guardian baggage with dead routes. LaunchDEX is a clean-room
minimal design: no oracle, no PSM, no external calls of any kind.

---

## 1. Design decisions

| # | decision | why |
|---|----------|-----|
| X1 | one pool per asset, XEL on one side | launchpad tokens migrate here exactly once; per-asset solvency stays trivial |
| X2 | **permanent liquidity — no remove_liquidity** | the anti-rug core; `add_liquidity` is an open, permanent, price-neutral donation |
| X3 | fees extracted, not pooled | `fee_bps` of each input goes to a per-pool pending pot; only the NET joins the reserves; 100% admin, zero burn |
| X4 | `create_pool` is launchpad-only, pin frozen at the first pool | a repinned launchpad could orphan every live pool |
| X5 | per-pool **buys-pause** (launchpad-only), sells carry NO gate at all | the launchpad's trust system keeps meaning after migration; holders always exit, even under the emergency pause (D4 across venues) |
| X6 | own scoreboard | per-pool buy/sell volume, trades, last-trade topo, spot price — the pool era of the launchpad's D12 |
| X7 | **price-neutral adds** (v1.1) | the pool's CURRENT ratio is enforced; only the proportional slice joins, the excess is refunded — a donation can never steer the price |
| X8 | trade guards mirror the launchpad | dust floors + whale caps + `min_out` slippage protection; floors keep both reserves > 0 forever (IX5) |
| X9 | zero outbound calls | no reentrancy surface; the only cross-contract traffic is INBOUND from the launchpad |

## 2. The math (constant product, integer-exact)

State per pool: `x` = XEL reserves, `y` = token reserves. `price = x / y`.

```
buy  with D XEL attached:    fee = D * fee_bps / 10000
                             net = D - fee            (net joins x)
                             out  = y * net / (x + net)     (leaves y)
sell with T tokens attached: fee = T * fee_bps / 10000
                             net = T - fee            (net joins y)
                             out  = x * net / (y + net)     (leaves x)
```

Both directions floor (integer division) in favour of the pool: reserves
can never go insolvent from rounding. All intermediates in u128.
Quotes (`get_amount_out_xel`, `get_amount_out_token`) use exactly the
formulas the swaps execute — a quote can never disagree with its trade.

**The add_liquidity fit (X7, v1.1)** — the deposit's effective pair at
the pool's CURRENT ratio (floor division throughout):

```
need_tok = y * xel_in / x
if tok_in >= need_tok:   xel_eff, tok_eff = xel_in,  need_tok      (XEL side binds)
else:                   xel_eff, tok_eff = x*tok_in/y, tok_in      (token side binds)
require(xel_eff >= 1 && tok_eff >= 1)   — "dust"
refunds: xel_in - xel_eff XEL and tok_in - tok_eff tokens, same transaction
```

Invariant (IX7): after every add, `|x1*y0 - x0*y1| < max(x0, y0)` — the
reserve product drifts by at most one floor unit. **Only swaps move the
price.** The SDK mirror is `xvault.dex.liquidity_fit` (preview the
effective pair before donating).

## 3. Entries

| entry | caller | what it does |
|-------|--------|--------------|
| `create_pool(asset)` | **the pinned launchpad** (cross-call) | reads the attached XEL + asset deposits (what the launchpad sent IS the seed), writes the pool, freezes the launchpad pin if this is the first pool |
| `set_pool_buys_paused(asset, flag)` | **the pinned launchpad** (cross-call) | the trust hook: pause/resume BUYS only — sells never |
| `swap_xel_for_token(asset, min_tokens_out)` | anyone (attach XEL) | buy tokens; reverts `"slip"` below min_tokens_out |
| `swap_token_for_xel(asset, min_xel_out)` | anyone (attach tokens — the WHOLE deposit) | sell tokens; **NO gate at all** — not the buys-pause, not the emergency pause (v1.1, founder risk review point 2) |
| `add_liquidity(asset)` | anyone (attach BOTH assets) | a permanent, price-neutral donation (X7): the ratio is enforced, the excess side is refunded; no shares issued in v1 |
| `set_swap_fee(bps)` | admin | ≤ 10% |
| `set_trade_bounds(...)` | admin | seed floors/caps + swap floors/caps, cross-checked (`min < max`) |
| `set_launchpad(addr)` | admin, **before the first pool only** | the one-way pin (X4) |
| `set_admin(new_admin)` | admin | single-step — use a cold wallet |
| `set_paused(flag)` | admin | global EMERGENCY — gates buys, pool creation and liquidity adds ONLY; sells stay open (IX6); can never rug (nothing can leave the reserves) |
| `withdraw_fees(asset, xel_amount, token_amount)` | admin | pays the pending pots; double-capped (pending AND uncommitted balance — IX1/IX2) |

## 4. Views (the pool-era API)

`get_pool` (asset, created, buys_paused, lp_deposits) · `get_pool_state`
(xel/token reserves, both pending pots, lifetime fees) ·
`get_amount_out_xel` / `get_amount_out_token` (quotes) · `get_spot_price`
(XEL per 1 whole token, scaled 1e8) · `get_pool_volume` (buy/sell volume,
trades, last-trade topo) · `get_pools_count` + `get_pool_by_index`
(listings) · `get_config` · `get_status_label` (`live` / `buys-paused` /
`emergency`) · **`get_launchpad` (v1.1 — the pinned launchpad address +
frozen flag, the upgrade-runbook bridge)** · `get_version`.

The SDK mirror is `sdk/xvault/xvault/dex.py` (math + `DexReader`); the
frontend composes the launchpad's curve-era stats with the pool era via
the asset hash (see LAUNCHPAD.md §7).

## 5. Storage map

Global: `adm` admin, `pc` pools count, `sfe` swap fee, `lpx` launchpad
pin, `mnx lnt` seed floors, `mnt tsw mst mxs` swap bounds, `xpa`
emergency, `lpp` pin frozen, `xa` XEL asset.
Pool `q:{asset_hex}:{field}`: `xr yr` reserves, `xf yf` pending fees,
`bp` buys paused, `ct` created, `bv sv tc lt` scoreboard, `fl` lifetime
fees, `lp` donation count, `ah` asset echo.
Index: `i:{index}` → asset hash (listings).

## 6. Events

`1 PoolCreated [asset, xel_seed, token_seed, launchpad]` ·
`2 SwapXelForToken [asset, xel_in, tokens_out, fee]` ·
`3 SwapTokenForXel [asset, tokens_in, xel_out, fee]` ·
`4 LiquidityAdded [asset, xel_effective, tokens_effective, xel_refunded, tokens_refunded]` ·
`5 FeesWithdrawn [asset, xel, tokens]` · `6 ParamSet [param, value]` ·
`7/8 BuysPaused/Unpaused [asset]` · `9/10 EmergencyPaused/Unpaused` ·
`11 AdminSet` · `12 LaunchpadSet`.

## 7. Invariants

- **IX1** sum over pools of (x + xf) ≤ XEL balance — equality by
  construction (deposits arrive whole, split bookkeeping-wise on the spot).
- **IX2** per asset: y + yf ≤ asset balance.
- **IX3** reserves only grow (create_pool, add_liquidity) or move
  sideways (swaps, floors favouring the pool). No entry moves reserves
  to a wallet.
- **IX4** one pool per asset, forever; the launchpad pin freezes at the
  first pool.
- **IX5** live pool reserves are always > 0 on both sides (seed floors +
  swap floors) — price is always well-defined.
- **IX6** (v1.1, absolute) **sells are ungated**: the buys-pause is
  checked on the buy path only, and the emergency pause does not touch
  the sell path either — NO code path can ever block a sell. A
  compromised admin can tax (swap fee, hard-capped at 10%) but never
  trap holders.
- **IX7** (v1.1) **price-neutral liquidity**: after every add,
  `|x1*y0 - x0*y1| < max(x0, y0)` — one floor unit of drift. Only swaps
  move the price; donations can only deepen.

## 8. Cross-contract protocol with VaultLaunch (D19)

VaultLaunch pins `DEX_CREATE_POOL_CHUNK = 6` and
`DEX_SET_PAUSED_CHUNK = 7` — asserted against this contract's real chunk
table by `tests/test_dex_reference.py` on every CI run. Renumbering
either contract without the other fails the build. The calling wallet's
transaction must carry the contract-call permission (`is_contract_callable`
precheck — the clear `"txperm"` refusal).
