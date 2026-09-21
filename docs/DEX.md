# LaunchDEX — Design Specification

> contracts/dex/LaunchDEX.slx · v1.3.0 · the AMM for VaultLaunch-graduated
> tokens, with a PERMANENT FLOOR

LaunchDEX is the migration target of VaultLaunch: one XEL-quote pool per
asset, constant-product pricing, and a **two-tier liquidity model**:

* **the SEED** — the liquidity the launchpad's `migrate()` plants at pool
  creation (the buyers' own curve money) — is **protocol-locked FOREVER**
  (X11): its LP parts are minted to the protocol's own position with **no
  withdrawable balance**, so the pool's depth can never fall below the
  migration. That is the anti-rug floor.
* **everything added afterwards** by providers via `add_liquidity` is
  theirs: withdrawable **pro-rata at any time** through
  `remove_liquidity` (X12), price-neutrally, with accrued fees
  crystallised first so an exit never forfeits a unit of earnings.

**Say it loudly on every frontend: PROVIDERS CAN LEAVE AT ANY TIME, THE
MIGRATED SEED NEVER LEAVES.** A provider is never trapped; a project's
launch liquidity is never drainable. Before v1.3 the second half was
enforced by having NO remove entry at all — which trapped the first half
too (providers' capital was a permanent donation). Worse, the seed minted
no LP parts either, so the FIRST 1 XEL add on a 4000 XEL pool captured
**100% of the provider fee share** — the economics bug of the founder's
third risk review, fixed by X11 (the same add now mints 1/4001 of the
depth).

**v1.3 — seed shares + free providers (X11/X12, founder risk review
point 1).** `create_pool` mints LP parts equal to the XEL seed to the
admin (the protocol LP position) and records them as the pool's
protocol-locked parts (`pl`, the seed floor). Two consequences, both
wanted: the first-add fee-capture bug dies, and **the protocol itself
becomes the pool's first provider** — its seed position accrues the
provider share of every fee pro-rata (near-all of it until real providers
deepen the pool), claimable by the admin through the same public
`claim_lp_fees` pull as everyone else. That is the protocol's second
revenue channel, on top of the admin split — see
[Where the money goes](#where-the-money-goes). `remove_liquidity` lets
any provider burn their withdrawable parts for their exact pro-rata
share of BOTH reserves at the current ratio: price-neutral (the same
one-floor-unit bound as adds, IX7), ungated (no pause can ever block an
exit — the IX6 principle extended to providers), never the seed (the
burn is bounded by the caller's own withdrawable balance, and the floor
is re-asserted belt-and-braces).

**v1.2 — providers earn (X10, founder risk review v18.2 point 1).**
Every swap fee is split between the admin and the pool's **liquidity
providers**, pro-rata of each provider's share of the pool's LP depth
(measured on the XEL side). Default split **50/50**, admin-settable but
**hard-bounded [25%, 75%]** — a hostile admin can neither cut providers
to zero nor starve the treasury, and the principal stays untouchable
either way. Distribution is the classic accrual-per-unit pattern
(MasterChef lineage): the pool keeps a per-unit accrual counter per
side, each provider keeps a snapshot from their last touch, and
`claim_lp_fees` (public, pull, own-key-only) pays what accumulated.
Every parts mutation — add, remove or claim — crystallises the caller's
accrued fees first: new money never earns from before it existed, and a
remove never burns what the parts already earned.

**v1.1 — hardened by the founder risk review.** (1) `add_liquidity` is
**price-neutral** (X7): the pool's current ratio is enforced,
Uniswap-style — only the proportional slice of the deposit joins the
reserves, the excess side is refunded in the same transaction. (2)
**Sells are ungated, absolutely** (IX6): the emergency pause gates buys,
pool creation and liquidity adds ONLY — every exit path (sells, fee
claims, removes since v1.3) carries no gate at all. (3)
`get_launchpad()` exposes the pinned launchpad and its freeze state —
the ops/frontend bridge for the upgrade runbook (UPGRADES.md).

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
| X2 | **the seed is permanent, providers are free** (v1.3) | the anti-rug guarantee was never "nobody can leave" — it is "the buyers' migration money can never be taken out"; X11 locks exactly that, without trapping voluntary providers' capital forever |
| X3 | fees extracted, not pooled | `fee_bps` of each input splits admin pot / provider pots; only the NET joins the reserves; zero burn |
| X4 | `create_pool` is launchpad-only, pin frozen at the first pool | a repinned launchpad could orphan every live pool |
| X5 | per-pool **buys-pause** (launchpad-only); every EXIT is ungated | the launchpad's trust system keeps meaning after migration; holders, fee claimants and providers can always leave — the emergency pause gates buys, creations and adds only |
| X6 | own scoreboard | per-pool buy/sell volume, trades, last-trade topo, spot price — the pool era of the launchpad's D12 |
| X7 | **price-neutral adds** (v1.1) | the pool's CURRENT ratio is enforced; only the proportional slice joins, the excess is refunded — a donation can never steer the price |
| X8 | trade guards mirror the launchpad | dust floors + whale caps + `min_out` slippage protection; floors keep both reserves > 0 forever (IX5) |
| X9 | zero outbound calls | no reentrancy surface; the only cross-contract traffic is INBOUND from the launchpad |
| X10 | **LP fee share** (v1.2, D23) | providers earn their pro-rata share of every fee (default 50/50, dial hard-bounded [25%, 75%]); pull claims; only fees ever flow out of the pots |
| X11 | **seed shares — the protocol LP position** (v1.3) | the seed mints LP parts to the admin at creation: the first external add mints its marginal depth (1 XEL on 4000 XEL = 1/4001, not 100%), and the protocol earns the provider share pro-rata on its position — fees-only, forever (no withdrawable balance is ever minted for the seed) |
| X12 | **remove_liquidity — providers are free** (v1.3) | burn withdrawable parts for the exact floored pro-rata of BOTH reserves at the current ratio; min_out on both sides; fees crystallised before the burn; NO gate (works under any pause); the seed floor is unreachable ("locked" + "seederr" belt-and-braces) |

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
effective pair before depositing).

**The remove_liquidity payout (X12, v1.3)** — the burn's exact pro-rata
share of both reserves, floored on both sides (the pool keeps the
rounding):

```
out_xel = parts * x / tl          out_tok = parts * y / tl
require(parts <= w)               — "locked": w = the caller's withdrawable
                                    parts (every part minted by an add;
                                    the seed's carry none, X11)
require(tl - parts >= pl)         — "seederr": belt-and-braces, the floor
require(out_xel >= 1 && out_tok >= 1)   — "dust"
require(out_xel >= min_xel_out && out_tok >= min_tokens_out)   — "slip"
require(x > out_xel && y > out_tok)     — "poolerr": never the last unit
```

Same IX7 bound as the add: a remove can never steer the price. The SDK
mirror is `xvault.dex.remove_outs` (preview the exit before burning).

**The fee split & the provider accrual (X10, v1.2)** — every swap fee is
split the moment it is taken (`lp_share_bps` of the fee, floored on the
LP side; the rest to the admin pot):

```
lp_part = fee * lp_share_bps / 10000                 (floor; admin gets fee - lp_part)
pool:   lx += lp_part            (or ly, the token side)
        ax += lp_part * ACC_SCALE / tl               (per-unit accrual; ACC_SCALE = 1e8)
provider earnings since their last touch:
        due = (ax - sx) * parts / ACC_SCALE          (floor — dust stays in the pot)
```

`tl` is the pool's total LP depth (XEL side — the fit rule keeps both
sides proportional, so one denominator serves both assets). Since v1.3
`tl` includes the seed's parts from birth (X11), and the IX8 precision
bound is guaranteed through removes too: `tl >= pl >= ACC_SCALE`
forever (IX9 — the seed floor can never be crossed), so each accrual
increment stays `<= lp_part` and the counter can never outgrow the
pool's lifetime fees. The 1 XEL LP-entry floor (`MIN_LP_ADD_XEL` =
`ACC_SCALE`) is not a dust rule — it is the precision guarantee on the
entry side, and since v1.3 the seed must clear the same floor at
creation (`"seedlp"`), extending the guarantee to the pool's whole
life. A deposit, a remove AND a claim all crystallise
the caller's dues before parts move: new money never earns from before
it existed (fuzz-found, pinned by a regression test), and a burn never
forfeits a unit of what the removed parts earned. Providers read their
position with `get_lp_info(asset, wallet)` — parts, the live available
payout on both sides, and the withdrawable balance (0 for the protocol
seed position) — and collect with `claim_lp_fees`, a public pull that
pays the caller's OWN accrued fees only and works under any pause.

## Where the money goes

Two public, bounded revenue channels flow to the protocol, and nothing
else can ever leave the contract:

1. **the admin split** — `100% - lp_share_bps` of every fee lands in the
   admin pots (`withdraw_fees`), with the dial hard-bounded
   `[25%, 75%]` (`set_fee_split`);
2. **the seed position** (v1.3, X11) — the protocol's LP parts earn the
   provider share of every fee pro-rata of the pool's depth. At
   migration the seed IS the depth, so the protocol earns ~100% of the
   provider share; as real providers deepen the pool, the protocol's
   share decays towards `seed / depth` — the honest curve of a market
   that outgrows its launch.

Example: a pool migrated with 4000 XEL, dial at 50/50, no external
providers — every fee splits 50% admin pot + 50% to the seed position,
which the admin claims with the same public `claim_lp_fees` as anyone
else: the protocol captures ~100% of the fee flow. Once providers have
added another 4000 XEL, the protocol's take decays to ~50% + 25% = 75%
of each fee, and keeps decaying as the market deepens — while the seed
(the anti-rug floor) never moves. If the admin role is ever rotated,
CLAIM THE SEED POSITION FIRST: the parts stay with the address that
owned them at creation (UPGRADES.md, the runbook's Phase 0 checklist).

## 3. Entries

| entry | caller | what it does |
|-------|--------|--------------|
| `create_pool(asset)` | **the pinned launchpad** (cross-call) | reads the attached XEL + asset deposits (what the launchpad sent IS the seed), writes the pool, freezes the launchpad pin if this is the first pool, and **mints the seed's LP parts to the admin (X11)**: `tl = pl = xel_seed` from birth, fees-only (no withdrawable balance); the seed must clear the 1 XEL LP floor (`"seedlp"` — it carries the IX8 precision guarantee through removes, IX9) |
| `set_pool_buys_paused(asset, flag)` | **the pinned launchpad** (cross-call) | the trust hook: pause/resume BUYS only — sells never |
| `swap_xel_for_token(asset, min_tokens_out)` | anyone (attach XEL) | buy tokens; reverts `"slip"` below min_tokens_out |
| `swap_token_for_xel(asset, min_xel_out)` | anyone (attach tokens — the WHOLE deposit) | sell tokens; **NO gate at all** — not the buys-pause, not the emergency pause (v1.1, founder risk review point 2) |
| `add_liquidity(asset)` | anyone (attach BOTH assets) | a price-neutral deepening (X7): the ratio is enforced, the excess side is refunded; ≥ 1 XEL effective XEL depth (the LP floor, v1.2); the donor becomes a PROVIDER with **withdrawable parts** (X10 + X12: earns pro-rata forever, may exit pro-rata anytime) |
| `remove_liquidity(asset, parts, min_xel_out, min_tokens_out)` (v1.3) | anyone (a provider) | burns WITHDRAWABLE parts for their exact floored pro-rata share of BOTH reserves at the current ratio; fees crystallised FIRST (nothing forfeited); **NO gate — works under any pause**; never the seed (`"locked"` / `"seederr"`); the pool can never be emptied (`"poolerr"`) |
| `set_swap_fee(bps)` | admin | ≤ 10% |
| `set_trade_bounds(...)` | admin | seed floors/caps + swap floors/caps, cross-checked (`min < max`) |
| `set_fee_split(lp_bps)` (v1.2) | admin | the admin/providers revenue dial, **hard-bounded [2500, 7500]**; affects FUTURE fees only |
| `set_launchpad(addr)` | admin, **before the first pool only** | the one-way pin (X4) |
| `set_admin(new_admin)` | admin | single-step — use a cold wallet; **claim the seed position before rotating** (X11: the parts stay with their owner) |
| `set_paused(flag)` | admin | global EMERGENCY — gates buys, pool creation and liquidity adds ONLY; every exit (sells, claims, removes) stays open (IX6/X12); can never rug anything |
| `withdraw_fees(asset, xel_amount, token_amount)` | admin | pays the ADMIN pots; double-capped (pending AND uncommitted balance — IX1/IX2); the provider pots are untouchable here |
| `claim_lp_fees(asset)` (v1.2) | anyone (a provider) | pays the CALLER's own accrued fees on both sides, out of the provider pots only; belt-and-braces bounded (`"lperr"`); works under the emergency pause; **the admin uses it too — the seed position's earnings** |

## 4. Views (the pool-era API)

`get_pool` (asset, created, buys_paused, lp_deposits) · `get_pool_state`
(xel/token reserves, both admin pots, lifetime fees, both provider pots,
the LP total depth **+ the protocol-locked seed floor — v1.3: show
"depth X, of which the migration's Y is permanent"**) ·
`get_amount_out_xel` / `get_amount_out_token` (quotes) ·
`get_spot_price` (XEL per 1 whole token, scaled 1e8) · `get_pool_volume`
(buy/sell volume, trades, last-trade topo) · `get_pools_count` +
`get_pool_by_index` (listings) · `get_config` (… + `lp_share_bps`,
v1.2) · `get_status_label` (`live` / `buys-paused` / `emergency`) ·
`get_launchpad` (v1.1 — the pinned launchpad address + frozen flag, the
upgrade-runbook bridge) · `get_lp_info(asset, wallet)` (v1.3 — parts,
available XEL, available tokens **+ the withdrawable balance**: the
provider dashboard AND the exit quote in one call; 0 withdrawable =
the protocol's seed position) · `get_version`.

The SDK mirror is `sdk/xvault/xvault/dex.py` (math + `DexReader`); the
frontend composes the launchpad's curve-era stats with the pool era via
the asset hash (see LAUNCHPAD.md §7).

## 5. Storage map

Global: `adm` admin, `pc` pools count, `sfe` swap fee, `lpx` launchpad
pin, `mnx lnt` seed floors, `mnt tsw mst mxs` swap bounds, `xpa`
emergency, `lpp` pin frozen, `xa` XEL asset, `fsl` LP fee share bps (X10).
Pool `q:{asset_hex}:{field}`: `xr yr` reserves, `xf yf` admin pots,
`lx ly` provider pots, `tl` LP total depth, `ax ay` per-unit accruals,
**`pl` protocol-locked parts (the seed floor, X11 — never withdrawable,
IX9)**, `bp` buys paused, `ct` created, `bv sv tc lt` scoreboard, `fl`
lifetime fees (total, both sides, before the split), `lp` deposit count,
`ah` asset echo.
Provider `l:{asset_hex}:{wallet}:{field}`: `x` parts (XEL depth),
`sx sy` accrual snapshots, `cx cy` crystallised claimables,
**`w` WITHDRAWABLE parts (X12 — what remove_liquidity may burn; the
seed minted none)**.
Index: `i:{index}` → asset hash (listings).

A note on privacy: provider slots live in PUBLIC contract storage
(per-wallet parts and earnings are readable by anyone). This adds zero
new exposure — the attached deposits of every `add_liquidity` are
public by chain design anyway; only wallet BALANCES are confidential
on XELIS (LAUNCHPAD.md §5a's public/private table).

## 6. Events

`1 PoolCreated [asset, xel_seed, token_seed, launchpad]` ·
`2 SwapXelForToken [asset, xel_in, tokens_out, fee]` ·
`3 SwapTokenForXel [asset, tokens_in, xel_out, fee]` ·
`4 LiquidityAdded [asset, xel_effective, tokens_effective, xel_refunded, tokens_refunded]` ·
`5 FeesWithdrawn [asset, xel, tokens]` · `6 ParamSet [param, value]` ·
`7/8 BuysPaused/Unpaused [asset]` · `9/10 EmergencyPaused/Unpaused` ·
`11 AdminSet` · `12 LaunchpadSet` · `13 LpFeesClaimed [asset, xel, tokens]`
(v1.2) · **`14 LiquidityRemoved [asset, parts_burned, xel_out,
tokens_out]` (v1.3)**.

## 7. Invariants

- **IX1** sum over pools of (x + xf + lx) ≤ XEL balance — equality by
  construction (deposits arrive whole, split bookkeeping-wise on the
  spot).
- **IX2** per asset: y + yf + ly ≤ asset balance.
- **IX3** reserves grow (create_pool, add_liquidity), move sideways
  (swaps, floors favouring the pool) or shrink strictly pro-rata to
  burned withdrawable parts (remove_liquidity, X12 — floored on both
  sides). No entry moves reserves to a wallet any other way;
  `claim_lp_fees` pays from the provider POTS, never the reserves.
- **IX4** one pool per asset, forever; the launchpad pin freezes at the
  first pool.
- **IX5** live pool reserves are always > 0 on both sides (seed floors,
  swap floors, and removes that burn strictly less than the whole — the
  seed's parts are never withdrawable, so `parts < tl` strictly and
  both floored outs stay strictly below their reserves) — price is
  always well-defined.
- **IX6** (v1.1, absolute) **every exit is ungated**: the buys-pause is
  checked on the buy path only; the emergency pause touches neither
  sells, nor fee claims, nor liquidity removes (X12). A compromised
  admin can tax (swap fee, hard-capped at 10%) but never trap ANYONE —
  holders or providers.
- **IX7** (v1.1 + v1.3) **price-neutral liquidity**: after every add
  AND every remove, `|x1*y0 - x0*y1| < max(x0, y0)` — one floor unit of
  drift. Only swaps move the price.
- **IX8** (v1.2) **LP solvency**: for every pool and both sides, the sum
  of every provider's crystallised + accrued earnings is always ≤ the
  provider pot. Bound proof: each accrual increment is
  `lp_part * ACC_SCALE / tl` with `tl ≥ ACC_SCALE` — guaranteed through
  removes by IX9's floor, not just the entry floor — so the counter can
  never outgrow the pool's lifetime fees, and every payout is a
  floor-rounded share of the increments. Removes crystallise dues
  BEFORE shrinking parts, so a burn never strands or inflates earnings.
  The fuzz asserts this after every action; the `"lperr"` bounds make
  even a hypothetical accounting bug revert instead of touching the
  reserves.
- **IX9** (v1.3) **the seed never leaves**: the protocol-locked parts
  (`pl`) are minted once at create_pool (equal to the XEL seed, ≥
  ACC_SCALE by hard require) and are NEVER withdrawable — no `w`
  balance is ever minted for them, every remove is bounded by the
  caller's own withdrawable parts (sum of all `w` ≤ `tl - pl` by
  construction) plus the belt-and-braces `tl - parts ≥ pl` re-check
  (`"seederr"`). Therefore `tl ≥ pl ≥ ACC_SCALE` for the pool's whole
  life, and the pool's depth can never fall below the migrated seed:
  **the anti-rug floor is absolute**. The honest trade-off: the depth
  ABOVE the floor depends on providers' goodwill and can shrink back to
  the seed at any time (a market risk, not a rug — the floor itself is
  immutable). Frontends should show the floor next to the depth.

## 8. Cross-contract protocol with VaultLaunch (D19)

VaultLaunch pins `DEX_CREATE_POOL_CHUNK = 6` and
`DEX_SET_PAUSED_CHUNK = 7` — asserted against this contract's real chunk
table by `tests/test_dex_reference.py` on every CI run. Renumbering
either contract without the other fails the build. The calling wallet's
transaction must carry the contract-call permission (`is_contract_callable`
precheck — the clear `"txperm"` refusal). The v1.3 changes change
NOTHING on this interface: `create_pool` keeps its signature (the seed
mint and the floor are internal effects), so VaultLaunch v4.2 calls it
unchanged.
