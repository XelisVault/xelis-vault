# CommunityLaunch — Design Specification

> contracts/community/CommunityLaunch.slx + contracts/dex/LaunchDEX.slx
> (v1.4.1) · CommunityLaunch v1.0.1 · the permissionless community-coin
> factory — the "pump.fun track" of XelisVault

CommunityLaunch is the casino next to VaultLaunch's serious shelf — and
it says so honestly. Where the launchpad filters every project through a
community validation vote (≥ 80% support, 526 XEL of founder skin), the
factory lets **ANYONE launch a coin in one transaction for ~2 XEL**: no
vote, no validation, no founder liquidity. The coin is born as a REAL
XELIS confidential asset (`Asset::create`, Fixed supply, cap enforced by
the XELIS protocol itself), priced from its first second on a
**virtual-reserve bonding curve** that simulates book depth with zero
founder capital. Graduation is a demand proof — the community's OWN
money must fill the curve — and the permissionless migration seeds a
permanent LaunchDEX pool through the **open seeding endpoint**
(`create_pool_open`, v1.4 X13), where the buyers' own money becomes the
protocol-locked anti-rug floor.

**This is NOT a quality filter.** Scams WILL launch here. The design
bounds what a scam can DO (fixed supply, no founder liquidity to pull,
locked pool seed, never-blockable sells, no honeypot surface), not what
a coin can BE — frontends must label community coins loudly
("community coin — no validation") and keep the two tracks visually
separate. See SECURITY.md for the honest threat model.

---

## 1. The two tracks, side by side

| | **Project track** (VaultLaunch) | **Community track** (CommunityLaunch) |
|---|---|---|
| Filter | community validation vote (≥ 80%) | **none — instant** |
| Launch cost | 526 XEL minimum (founder liquidity) | **~2 XEL** (1 fee + 1 asset cost) |
| Founder liquidity | ≥ 500 XEL locked in the curve | **zero — virtual reserves** |
| Curve | constant product on real reserves | constant product on **virtual** reserves |
| Graduation | reserves ≥ liquidity × gmu | depth ≥ gdx **AND** price continuity |
| Migration | `migrate()` → `create_pool` (pinned signer) | `migrate()` → `create_pool_open` (**permissionless both sides**) |
| Creator/team allocation | ≤ 20%, vesting plans, community-voted | **≤ 5%, no vesting, claimable only post-migration** |
| Trading fees | 0.5% bonding / 0.25% graduated | 1% live / 0.5% graduated |
| Trust system | Trusted/Untrusted votes forever | none (DEX-side moderation pause only) |

Both tracks migrate into the same LaunchDEX **lineage** (a v1.4
deployment serves both: its launchpad pin gates only the moderation
hook, its open endpoint gates nothing). The factory keeps its own
listing indexes and the asset → coin reverse bridge — the stateless
site needs no indexer on either track (LAUNCHPAD.md §7a recipe, same
shape).

---

## 2. Lifecycle

```
 launch_coin() [sub fee + asset budget attached]
       |
       v  Asset::create — the REAL confidential asset is born:
       |    Fixed supply, whole balance held by the factory, cap forever.
       |    The chain's creation cost is measured by balance-delta and
       |    the unused part of the deposit is refunded on the spot.
       |
 0 LIVE (bonding on the virtual-reserve curve; buys/sells open, fee cfe)
       |
       |  the buy() that crosses BOTH:
       |    depth:       xr >= gdx            (default 50 XEL)
       |    continuity:  xr * y0 >= yr * vx   (structural)
       v
 1 GRADUATED (curve keeps trading at the graduated fee gfe — the
       |         never-trap rule; no fee is taken here, see §5)
       |  migrate() — permissionless, atomic: mgf carved from the SEED,
       |  then ONE cross-contract call to LaunchDEX create_pool_open
       |  (chunk 33) carrying the whole real reserves + inventory
       v
 2 MIGRATED (curve closed forever; the pool owns the market; the
             factory keeps the coin's home — metadata, creator claim)
```

Status codes (`get_status_label`): `0 live, 1 graduated, 2 migrated`.
XELIS has no timers: graduation fires inside the `buy()` that crosses
the conditions; migration is executed by anyone (frontend button,
keeper bot, the last buyer) — the outcome is fully determined by the
coin's state, with no destination, amount or caller choice anywhere.

---

## 3. The virtual-reserve curve (C1)

State per coin: `xr` = real XEL in the curve (**starts at 0 — the
founder provides nothing**), `yr` = real curve inventory (starts
`total_supply - creator allocation`), plus two constants snapshotted at
launch: `vx` (virtual XEL, default 100 XEL) and `y0` (the initial
inventory — the virtual token reserve mirrors the real one). Every
formula uses the totals: `x_total = xr + vx`, `y_total = yr + y0`.

```
buy with D XEL attached:   fee = D * cfe / 10000          (extracted)
                           net = D - fee                  (joins xr)
                           out = y_total * net / (x_total + net)   (floored)
                           require(out <= yr)             — the whale guard

sell of T tokens:          gross = x_total * T / (y_total + T)      (floored)
                           require(gross <= xr)           — provably true
                           fee  = gross * cfe / 10000     (extracted)
                           out  = gross - fee             (to the seller)
```

Both floors favour the curve; all intermediates are u128. The implied
`k = x_total * y_total` **never decreases** through trades (fees are
EXTRACTED to pending_fees, never parked in the reserves), so
`k >= k0 = vx * 2*y0` forever; and since nothing circulates that was
not bought from the curve (`y_total <= 2*y0`), `x_total >= vx` — the
real reserves `xr` are non-negative **by construction**, and the
worst-case sell (the whole circulating supply in one transaction)
extracts EXACTLY xr, to the floor rounding. The virtual side is
mathematics, never a liability — the full proof is IC3/IC4 in the
contract header, machine-checked by `tests/test_community_reference.py`.

**What the defaults buy** (vx = 100 XEL, y0 = 1B tokens): launch FDV =
50 XEL; a 1 XEL buy moves the price ~1% (the virtual book absorbs it);
graduation at 50 XEL real depth lands with ~2/3 of the supply sold at
~3× the launch FDV; the pool opens at `xr/yr` within one migration fee
of the curve's spot price (see §4 — the honest, fee-aware reading).

**The degenerate monster buy**: a single buy can legally drain the
whole real inventory (`out == yr` exactly, ~100 XEL at launch). Such a
coin graduates and simply cannot `migrate()` until a sell re-fills the
inventory ("empty") — no funds at risk, the curve stays open, honest
state.

---

## 4. Graduation — demand proof in two conditions (C2)

A LIVE coin graduates inside the `buy()` that makes BOTH true,
evaluated on the post-trade state (the buyer's trade always completes
first — VaultLaunch's exact pattern):

| condition | formula | meaning |
|---|---|---|
| depth | `xr >= gdx` (default 50 XEL, snapshotted per coin) | the community put REAL money in |
| continuity | `xr * y0 >= yr * vx` (structural, hard-coded) | the pool opens at `xr/yr` ≥ the curve's virtual ratio — **no graduation dump by construction** |

The honest, fee-aware reading of the continuity claim: the migration
fee (mgf, default 0.5%) is carved from the XEL side of the seed (C4),
so the pool actually opens at `(xr − mgf·xr)/yr` — one fee haircut
below `xr/yr`. Since `xr/yr` is bounded ABOVE the curve's spot (see
below), the open is at worst `spot × (1 − mgf)` ≈ 99.5% of the spot at
the default — a rounding-level dip, not a dump, and it is *left of* the
full fee because the continuity invariant pushes `xr/yr` above spot:
with `xr/yr ≥ vx/y0` and `spot` the weighted mean of `xr/yr` and
`vx/y0`, `xr/yr ≥ spot ≥ vx/y0`. The pool can never open materially
below the price the market just paid for the coin.

Along the constant-k trajectory the continuity condition reduces to
`xr >= (√2−1)·vx ≈ 41.4 XEL` at the default vx — independent of how
much is sold. With the defaults the depth floor binds (50 > 41.4) and
graduation lands around 2/3 of the supply sold. Both parameters a coin
launches with are **snapshotted** (C8, the launchpad's D7 philosophy):
later admin tuning never reclassifies an existing coin.

Graduation itself moves NO funds and takes NO fee: the curve keeps
trading at the graduated fee (0.5% default, cross-checked ≤ the live
fee) until the migration happens. This is the never-trap rule — if the
DEX is emergency-paused the moment a coin graduates, holders still
have the curve; nothing is ever stuck.

---

## 5. Migration — permissionless on BOTH sides (C6 + X13)

`migrate(cid)` is callable by ANYONE; the DEX endpoint it drives —
`create_pool_open` (LaunchDEX v1.4, chunk 33) — is permissionless too.
On this VM `get_caller()` reports the original transaction signer even
inside a cross-contract call, so a "factory-only" gate cannot be
expressed on the DEX side; the design is honestly open instead: **the
deposits are the authorisation**, and what seeds the pool is exactly
what the factory sends. A frontend button or keeper bot executes the
migration in the same block as graduation — no pinned wallet can
become a graduation bottleneck.

The move is atomic: the one-time **migration fee (mgf, default 0.5%,
cap 5%) is carved from the SEED — never out of the live curve** (C4).
This divergence from the launchpad (which takes its fee at graduation)
is structural: the IC3/IC4 solvency proof requires k to stay exactly
invariant while the curve trades; taking the fee from the live curve
would shrink k by up to mgf and make the last sliver of a full
sell-back unpayable — a trap this design refuses. The fee therefore
only reduces the pool seed, and the pool opens at the real ratio the
market actually paid for.

Migration writes the terminal state **inside the same atomic move**:
`st = ST_MIGRATED (2)` and `migrated = true` are stored BEFORE the
cross-contract call (state first, call last — no store can be lost to
a revert). This matters for the views (§8): a migrated coin's
`get_status_label` reads `migrated`, and the creator claim gates on it
(C5). The pre-v1.0.1 build forgot the status write (the E2E showed `st`
stuck at 1 after migration) — v1.0.1 fixes it, and `get_current_price`,
`get_buy_quote`, `get_sell_quote` and `get_market_cap` all return **0**
once migrated (the curve is closed; the price lives on the pool).

The DEX pin (`set_dex_address`, admin, one-way, freezes at the first
migration) also gained a v1.0.1 sanity check: the address must be a
contract that is callable at the pinned chunk (`"baddex"` otherwise),
so an empty hash or an EOA cannot be pinned by mistake. This is an
operational guard, **not provenance**: the generation-1 signer
semantics of this VM mean the factory's trust boundary — the admin
choosing the DEX before any migration — is explicit in the deployment
runbook, and the DEX side must be configured in the right order too
(DEX.md v1.4.1: its `lpx` moderation pin must exist before the first
open pool).

After the migration: the curve is closed forever ("migrated"), the
pool owns the market (its seed is protocol-locked forever — DEX.md
X11/IX9: the buyers' own money is the anti-rug floor), and the factory
keeps the coin's home — metadata, trading scoreboard, creator claim.

---

## 6. The creator allocation (C5)

The creator declares up to **5%** at launch (`team_bps`, cap enforced
— 4× tighter than the project track). The allocation is:

- **reserved OFF the curve** — `y0` is net of it at birth, so the
  curve formula can never sell it (IC2: factory asset balance ==
  inventory + unclaimed reserve, per coin, at every block);
- **claimable ONLY after migration** — a creator's payoff is
  conditional on the coin graduating (the pump.fun alignment, written
  into the state machine). A never-graduating coin pays the creator
  NOTHING, forever;
- **paid exactly once** (IC5: the `cp` counter only grows, bounded by
  the allocation) via a confidential transfer; the `CreatorClaimed`
  event carries NO amount (D18 privacy, same rule as the launchpad's
  team claims).

No vesting on this track — the serious track has it; here the cap and
the post-migration gate ARE the protection.

---

## 7. Entries (transaction-facing; full chunk table in the header)

| entry | caller | what it does |
|---|---|---|
| `launch_coin(name, symbol, description, website, logo, twitter, telegram, discord, total_supply, team_bps)` | anyone (attach ≥ sub + abd) | the coin is born: asset created, curve opened, deposit refunded of everything unused |
| `buy(cid, min_tokens_out)` | anyone (attach XEL) | buy REAL tokens on the virtual curve; graduation fires here |
| `sell(cid, min_xel_out)` | anyone (attach tokens — whole deposit) | sell back for XEL; **NO pause gate ever** |
| `migrate(cid)` | anyone | the atomic move to the LaunchDEX pool (requires the contract-call permission) |
| `claim_creator_allocation(cid)` | the creator, post-migration | the 5% reserve, exactly once |
| `update_coin_info(cid, description, website, logo, twitter, telegram, discord)` | the creator | mutable card (name/symbol immutable) |
| `set_submission_fee` / `set_asset_budget` / `set_curve_fee` / `set_graduated_fee` / `set_migration_fee` / `set_graduation_depth` / `set_virtual_xel` | admin | the dials (all hard-capped; the fee pair cross-checked) |
| `set_dex_address(addr)` | admin, **before the first migration only** | the one-way DEX pin |
| `set_admin` / `set_paused` / `withdraw_fees` | admin | role transfer; circuit breaker (launches+buys only); revenue collection (double-capped) |

## 8. Views (the site's API — no indexer needed)

`get_coin` (creator/status/created/supply/migrated) · `get_coin_meta`
(the whole card) · `get_coin_tokenomics` (supply, creator bps/alloc/
paid/remaining) · `get_curve_info` (**the five curve inputs** — the
frontend computes everything from this) · `get_current_price` ·
`get_buy_quote` / `get_sell_quote` (the SAME helpers the trades use) ·
`get_market_cap` (FDV convention) · `get_total_coins` ·
`get_coins_by_status` + `get_coin_by_rank` (per-status listings) ·
`get_latest_coin` (newest-first) · `get_coin_by_asset` (**the reverse
bridge** — maps DEX pools back to coin pages) · `get_migrated_count` +
`get_migrated_by_rank` (the graduated shelf) · `get_trading_stats` ·
`get_config` · `get_status_label` (`live` / `graduated` / `migrated`)
· `get_version`.

**Migrated coins report zero on the curve views** (v1.0.1): when `st ==
ST_MIGRATED`, `get_current_price`, `get_buy_quote`, `get_sell_quote`
and `get_market_cap` return 0 — the curve is closed and those numbers
would be stale at best, misleading at worst. Frontends must check
`get_status_label` (or `get_coin`'s status field) first and switch to
the pool's price (`get_pool_state` / `get_amount_out_*` on LaunchDEX).
The SDK mirrors this: `CommunityReader.price()`, `buy_quote()`,
`sell_quote()`, `market_cap()` return what the contract returns (0
once migrated); the pure math helpers (`spot_price`, `market_cap`, …)
take reserves only and are the LIVE-curve formulas by design.

The SDK mirror is `sdk/xvault/xvault/community.py` (math + a
`CommunityReader`); the ABI table is `abi/CommunityLaunch.abi.json`.

## 9. Parameters, defaults and caps

| parameter | default | bounds |
|---|---|---|
| submission fee (`sub`) | 1 XEL | ≤ 100 XEL |
| asset budget (`abd`) | 1 XEL | ≤ 100 XEL (documented floor; actual cost measured) |
| curve fee (`cfe`) | 1% | ≤ 10%, ≥ gfe |
| graduated fee (`gfe`) | 0.5% | ≤ 10%, ≤ cfe |
| migration fee (`mgf`) | 0.5% | ≤ 5%, carved from the seed |
| graduation depth (`gdx`) | 50 XEL | [1 XEL, 100 000 XEL], snapshotted per coin; **gdx ≤ vx/2 (cross-invariant)** |
| virtual XEL (`vxs`) | 100 XEL | [1 XEL, 10 000 XEL], snapshotted per coin; **the same gdx ≤ vx/2** |
| creator allocation | — | ≤ 5% (hard) |
| total supply | — | [1M, 10B] whole tokens (both ends enforced at launch) |
| trade guards | 0.01 XEL dust | ≤ 100 000 XEL per buy |

**The gdx ≤ vx/2 cross-invariant** (v1.0.1): `vx` is the curve's
effective real-reserve ceiling as the real inventory drains, so a
graduation floor above half the virtual reserve would let a coin
graduate with no inventory left to migrate (a dead coin). The invariant
is enforced at launch AND in both admin setters (`set_graduation_depth`,
`set_virtual_xel`) — a parameter pair that violates it is unsettable.

**Fee accounting** (v1.0.1): every collected fee — the 1 XEL
submission, live/graduated curve cuts, and the migration fee — is
added to BOTH the withdrawable `pfe` (pending) pot and the lifetime
`fcl` counter at collection time. A withdrawal pays out of `pfe` only
and never touches `fcl`: lifetime revenue is a monotonically growing
scoreboard, not an accounting trick that inflates with payouts
(`get_config` exposes both; the pre-v1.0.1 build incremented `fcl`
at withdrawal instead — fixed).

**The unit economics** (defaults): a launch costs the creator exactly
`sub + asset_fee` ≈ 2 XEL out of pocket; the protocol nets ~1 XEL per
launch + 1% of every curve trade + 0.5% at migration + the DEX revenue
on every migrated pool (0.30% swaps split 50/50 + the protocol's seed
position earning the provider share forever — see DEX.md "Where the
money goes"). Each graduated coin is a permanent, self-funding micro
revenue stream; the track is designed to run at volume.

## 10. Deployment plan (additive — nothing is redeployed)

Following UPGRADES.md's generation model — **contracts are never
upgraded in place; a new version is a NEW deployment**:

1. **Testnet rehearsal** (Phase 1, always): deploy CommunityLaunch
   v1.0.1 + a LaunchDEX v1.4.1 generation, **configure the DEX's
   `set_launchpad` first** (v1.4.1 `nolpx`: the moderation pin must
   exist before any pool — see DEX.md), then pin the factory's
   `set_dex_address` to the DEX, and run the FULL lifecycle (launch →
   buy → graduate → migrate → pool swaps → creator claim), verifying
   the migrated status flips to 2, the curve views close, and both
   pins froze.
2. **Mainnet cut** (Phase 2): deploy both, pin the factory's
   `set_dex_address` to the new DEX. The gen-1 pair (VaultLaunch
   `45baf014…` + LaunchDEX `bce37bde…`) keeps serving the project
   track untouched — with ONE recommended adjustment while its pins
   are still unfrozen (no pool exists yet): **re-pin gen-1 VaultLaunch
   to the v1.4 DEX** (entry 50 `set_dex_address`) so the project track
   benefits from the second-migration fix (DEX.md v1.4: gen-1's
   `create_pool` returns its pool index, which the launchpad's
   `migrate_to_dex` treats as failure — only the FIRST project
   migration would ever succeed on the gen-1 DEX). Set the new DEX's
   `set_launchpad` to the official wallet: it keeps the moderation
   hook (per-pool buys-pause, chunk 7) for BOTH tracks.
3. **Site** (Phase 3): add the generation pair to the site's static
   registry; the stateless views enumerate everything (D22 recipe).

Cost: ~0.01 XEL of gas for the two deployments (measured on the gen-1
mainnet cut). The community decides where to launch; the two tracks
sell different things — seriousness and fun.
