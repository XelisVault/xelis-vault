# VaultLaunch — Design Specification

> contracts/launchpad/VaultLaunch.slx + contracts/dex/LaunchDEX.slx ·
> VaultLaunch v4.2.0 / LaunchDEX v1.2.0 · mainnet-ready (testnet first)

A serious launchpad for XEL: real projects are filtered by a community
validation vote, priced by a constant-product bonding curve, and held to a
long-term community trust standard (Trusted / Untrusted). Every fee is
configurable by the admin; the launchpad's revenue goes 100% to the admin
and the DEX's swap fees are SPLIT between the admin and the liquidity
providers (default 50/50, dial hard-bounded [25%, 75%]) — nothing is
burned. This is NOT a memecoin casino: the vote window is the quality
filter, the trust system keeps founders accountable forever, and the
curve math is integer-exact and solvent by construction.

**v2 — graduation is worth reaching.** Two paths lead to graduation:
a founder who locks serious liquidity (≥ the direct-listing threshold)
graduates the moment validation passes; smaller floats discover price on
the bonding curve and graduate when their reserves grow ×4. Graduated
projects trade at a LOWER fee, the team allocation unlocks (immediate
claim or votable vesting), and a small one-time migration fee — taken
from the curve, pump.fun-style but smaller — funds the protocol.

**v3 — everything on the table, everything on-chain.** The vote happens
with EVERY piece of data visible: the creator declares the **team vesting
plan at proposition time** and the contract binds it automatically at
graduation (D10). Projects carry **social links** (Twitter / Telegram /
Discord) the team can update at any time (D11). And the contract keeps
**the market's scoreboard itself** (D12): volumes, trade counts, the spot
market cap and its history — computed AND stored on-chain.

**v4 — REAL ASSETS, REAL MIGRATION (D13–D20).** Every launched token is
now a **true XELIS confidential asset**: the contract creates it at
validation success via `Asset::create` with `MaxSupplyMode::Fixed` — the
ENTIRE supply exists from birth, is held by the contract, and can NEVER
be minted past its cap (the cap is enforced by the XELIS protocol itself).
Buyers hold real tokens in their own wallets from the first second —
fully confidential balances, transferable anywhere on XELIS, usable by
every wallet and service. The bonding curve trades real deposits (buy:
attach XEL, receive tokens in your wallet; sell: attach tokens, receive
XEL — the whole deposit, nothing stranded). And graduation now really
means **migration**: the curve's XEL reserves and its token inventory
move ATOMICALLY into a **LaunchDEX** pool (one cross-contract call with
attached deposits) whose SEED is protocol-locked FOREVER — the seed's
LP parts carry no withdrawable balance, so the migration can never be
drained by anyone: that is the anti-rug floor. Providers who deepen
the pool afterwards can exit pro-rata at any time
(`remove_liquidity`); the floor cannot (DEX.md X11/X12). The launchpad
keeps the project's home (votes, socials, trust, team escrow); the
pool owns the market.

**v4.1 — HARDENED BY THE FOUNDER RISK REVIEW (D21/D22).** Six risks were
raised before going live; six are now closed in code and docs. (1) DEX
`add_liquidity` is now **price-neutral** (Uniswap-style ratio fit — a
skewed or one-sided donation only deepens the pool at its CURRENT price,
the excess side is refunded in the same transaction; only swaps can move
a pool's price). (2) **Sells are ungated, absolutely**: the DEX emergency
pause now gates buys, pool creation and liquidity adds ONLY — no code
path on either venue can ever block a sell; a compromised admin can tax
(fees are hard-capped) but never trap holders. (3) The upgrade path is
**documented as a runbook** (both pins freeze at first use; a new
launchpad generation means a new LaunchDEX side-by-side — old venues
keep serving their pools forever, the site aggregates generations via
`get_launchpad` + `get_migrated_by_rank`). (4) The cross-called chunk
ids stay **pinned and CI-asserted on both sides** (append-only rule:
new DEX functions go at the end, ids 6/7 never move). (5) The **sybil
dial (D21)**: an admin-settable, REFUNDABLE vote deposit (default 0 =
free voting, cap 10 XEL) — raise it under attack, every vote then locks
capital that `claim_vote_deposit` refunds once the round closes; XELIS
confidentiality rules out balance-weighted voting, so capital lock is
the honest lever, and it is documented as a mitigation, not a cure.
(6) The **privacy model is documented honestly** (see §5a): deposits
attached to contract calls are public by chain design; wallet balances
stay confidential — nobody should promise "total privacy". And for the
site (statically hosted, stateless): **D22** adds the asset→project
reverse bridge (`get_project_by_asset`) and the migrated index
(`get_migrated_count` / `get_migrated_by_rank`) — every listing, stat
and link the frontend shows is enumerable from views alone.

**v4.2 — PROVIDERS EARN, VOTERS PAY (A LITTLE).** The founder risk
review's first two points, closed in code. (1) **LaunchDEX v1.2 — LP
fee share (X10/D23)**: adding liquidity to a migrated pool now EARNED
its keep — every swap fee splits between the admin pot and the pool's
liquidity providers, pro-rata of each provider's share of the pool's LP
depth. Default 50/50, admin-settable but hard-bounded [25%, 75%].
(v1.3, the third founder review) **the seed mints LP parts to the
protocol (X11)** — the first external add mints its marginal depth
(1 XEL on a 4000 XEL pool = 1/4001 of the fees, not 100%), and the
protocol earns the provider share on its position (fees-only, forever);
**providers can exit pro-rata at any time (X12, `remove_liquidity`)**
while the seed never leaves (no withdrawable balance is ever minted
for it — the anti-rug floor is absolute). The full design, the accrual
math and the IX8/IX9 proofs live in `docs/DEX.md`. (2) **The sybil
dial ships ON by default**: `vote_deposit` now defaults to **0.5 XEL
refundable** — 20 farmed wallets deciding a validation park 10 XEL of
capital while they do it; the admin can still zero it or raise it
(cap 10 XEL), and a raise never touches already-locked deposits.

Two contracts, one architecture. Zero other dependencies.

---

## 1. Lifecycle

```
                 propose() [fee + asset budget + seed liquidity]
                        |
                        v
                0 VALIDATION
                (support / report window,
                 ends at validation_end topo)
        pass >= 20 voters AND >= 80%      fail
        |----------------------------------|
        |                                  v
        |                    [NO asset created — D13]
        |                           1 REJECTED
        |                           claim_refund() -> 100% of the
        |                           founder's liquidity + asset budget,
        |                           once (NO team tokens — a rejected
        |                            launch never mints)
        |
        |  [D13] Asset::create — the REAL confidential asset is born:
        |  Fixed supply, whole balance held by the contract, cap forever
        |
        +-- liquidity >= direct_listing_threshold (snapshotted at propose)
        |            |
        |            v  DIRECT LISTING (D7)
        |   3 GRADUATED on the spot: migration fee taken on the seed,
        |      graduated fee from the first trade, Trusted badge,
        |      team unlock — the full graduation set, day one
        |
        |            v  (same block or any time later: migrate())
        |               pool seeded on LaunchDEX (D15)
        |
        v  else (smaller float)
  2 BONDING
  buy / sell live — REAL tokens in/out of wallets (D14)
  votes continue (trust)
        |
        | reserves >= liquidity x 4 (default)
        v  CURVE GRADUATION
  3 GRADUATED (+ Trusted)
  one-time migration fee taken from the grown reserves (D9)
  team allocation claimable (D3); the curve keeps trading at the
  graduated fee UNTIL the migration (admin-lag tolerant, D15)
        |
        | migrate() — permissionless, ATOMIC (D15)
        v
  [MIGRATED] curve closed forever; XEL reserves + token inventory
  seed a PERMANENT LaunchDEX pool; team escrow stays on the launchpad;
  votes, socials, trust and team claims continue here (D17)
        |
        | reports reach 80% of all votes
        v
  5 UNTRUSTED  <-------------------------------------.
  buys BLOCKED (curve directly, pool once synced — D17),   |
  sells ALWAYS open, votes open                            |
  (graduated projects KEEP the lower fee:                  |
   the milestone is rewarded, not punished)                |
        | request_revalidation()                      | fail
        |  - not graduated: free, normal thresholds   |
        |  - graduated: 250 XEL fee, 40 voters, 90%   |
        v                                              |
  6 RECOVERY (new voting round, tallies reset) --------'
        | pass
        v
  2 BONDING (never graduated) or 4 TRUSTED (graduated)
  (a recovered migrated project: sync_trust_to_dex() unpauses the pool)
```

Status codes (see `get_status_label`): `0 validation, 1 rejected,
2 bonding, 3 graduated, 4 trusted, 5 untrusted, 6 recovery`. The
**migrated** state is a flag on top (`get_migration_info`), not a status —
the launchpad remains the project's home after the move.

**Who triggers what.** XELIS has no timers: every transition is
event-driven. Graduation fires inside the `buy()` that crosses the
threshold, or inside `finalize_validation()` for a direct listing; trust
loss fires inside the vote that crosses the ratio; window outcomes are
applied by `finalize_validation()`, callable by
ANYONE after the deadline (the outcome is fully determined by the public
tallies — the finalizer only executes it). The **migration** is equally
permissionless: `migrate()`, callable by anyone once the project
graduated — the outcome is fully determined by the project's state (no
destination, no amount, no caller choice anywhere). The vesting stream
and the team unlock delay are evaluated lazily, at claim time, against
the current topoheight.

---

## 1a. Real confidential assets (v4, D13/D14/D18)

**Creation.** The asset is born at `finalize_validation()`, the moment
the community says yes — failed proposals never pollute the chain and
never pay the creation cost. The contract calls:

```
Asset::create(pid, name, symbol, 8, MaxSupplyMode::Fixed { max_supply: total_supply })
```

* the **project id** is the asset's local id (bidirectional lookup:
`Asset::get_by_id(pid)`);
* **8 decimals** — XEL parity, so the curve math is unit-honest;
* **Fixed supply**: the WHOLE `total_supply` is minted to the contract at
  creation and `is_mintable()` reads false FOREVER — the max cap is
  enforced by the XELIS protocol itself, not by our code. The frontend
can show this as the on-chain proof of the cap (`get_asset_info`).

**The creation cost, measured and refunded (D13).** Asset creation has a
protocol cost, paid from the contract's balance. Every proposal
**earmarks an asset budget** (default 10 XEL, admin-settable) at propose
time; at creation the contract **measures the actual fee by
balance-delta** (robust to any future fee change), accepts a **top-up
deposit** on the finalize transaction if the chain got more expensive,
and **refunds the unused part to the creator immediately**. A rejected
project refunds the budget with the liquidity.

**Trading real tokens (D14).** `buy(pid)`: attach XEL, receive real
tokens in your wallet (a native confidential transfer from the
contract's inventory). `sell(pid)`: attach tokens — the WHOLE deposit is
sold (symmetric with buy; nothing can be stranded) — and receive XEL.
The identity `launchpad asset balance == curve inventory + unpaid team
allocation` holds at every block (invariant I1) — auditable by anyone.

**Privacy (D18).** Native XELIS confidentiality: balances and transfer
amounts are encrypted at the base layer for every launched token.
Team claims pay from escrow via confidential transfers and the
`TeamClaimed` event carries NO amount — the payout is the creator's
private business. Honest limitation, by chain design: deposits ATTACHED
to contract invocations are public (the contract must read the amount) —
inputs to curve trades and DEX swaps are therefore public; everything
else is confidential.

---

## 1b. Migration to LaunchDEX (v4, D15–D20)

**Graduation ≠ migration.** Crossing the graduation threshold (or passing
validation as a direct listing) flips the milestone — fee discount, team
unlock, vesting bind, migration fee — but moves no funds: the curve keeps
trading at the graduated fee until the pool exists (an admin lag never
strands a hot project).

**`migrate(pid)` — permissionless, atomic.** One transaction, callable by
anyone: the curve's whole XEL reserves and its whole token inventory
(team escrow excepted) seed a LaunchDEX pool whose seed is
protocol-locked forever, via a single cross-contract call with
**attached deposits** (the funds and the pool creation are one atomic
operation — a failure anywhere reverts everything). After it: the curve
is closed forever (`"migrated"`), the pool owns the market, and the
launchpad keeps the project's home —
votes, socials, trust system, team escrow claims.

**The DEX pin (D19).** `set_dex_address` (admin) is possible only while
no project has ever migrated; after the first migration the pin is
FROZEN forever (the pools live inside that contract). LaunchDEX mirrors
the freeze: its launchpad pin freezes at its first pool. The two
cross-called chunk ids are pinned constants, asserted against the real
chunk tables by CI — renumbering either contract without the other fails
the build.

**Trust across venues (D17).** The trust flip stays a pure launchpad
state change (no permission traps for voters); a separate permissionless
keeper entry, `sync_trust_to_dex(pid)`, mirrors it to the pool's
**buys-pause** — keeper bots, a frontend button, or anyone. If the
project is Untrusted AT migration time, `migrate()` pauses the pool's
buys in the SAME transaction (no unprotected window). Sells on the pool
are never pausable (D4).

**The anti-rug core (D16 / LaunchDEX X11+X12).** The seed is protocol-locked
FOREVER: the migrated liquidity's LP parts are minted to the protocol's
own position with NO withdrawable balance, so nobody — not the admin,
not the founder, not the launchpad — can ever drain a pool below its
migration. Providers who deepen the pool with
`add_liquidity` hold withdrawable parts and may exit pro-rata at any
time (`remove_liquidity`, price-neutral, fees crystallised first) — a
provider is never trapped; the floor never moves. Say it loudly on the
frontend: **PROVIDERS CAN LEAVE AT ANY TIME, THE MIGRATED SEED NEVER
LEAVES.**

See `docs/DEX.md` for the LaunchDEX specification.

---

## 2. The bonding curve (constant product, integer-exact)

State per project: `R` = real XEL reserves, `C` = curve token supply (the
sellable balance held by the curve). Spot price = `R / C`.

```
buy  with X XEL attached:   fee = X * fee_bps / 10000
                            net = X - fee                  (joins R)
                            tokens_out = C * net / (R + net)     (floored)
sell of T tokens:          gross = R * T / (C + T)         (leaves R)
                            fee  = gross * fee_bps / 10000
                            out  = gross - fee              (to caller)
```

Both directions floor (integer division) in favour of the contract, so
the pool can never go insolvent from rounding. All intermediates are
computed in u128 (products reach 1e31; u64 would overflow). The implied
`k = R * C` never decreases through trades — fees stay in the reserves
on the buy side and only the net is paid out on the sell side.

### 2a. The fee schedule — graduation pays (v2)

`fee_bps` is **per-project**, resolved by the `current_fee_bps()` helper:

| project state        | fee applied                | default |
|----------------------|----------------------------|---------|
| bonding              | `trading_fee_bps`          | 0.50%   |
| graduated (any path) | `graduated_fee_bps`        | 0.25%   |
| migrated (pool era)  | LaunchDEX `swap_fee_bps`   | 0.30%   |

- v4 scopes the curve fees to the **curve era**: between graduation and
  migration the curve trades at the graduated rate; after `migrate()`
  the curve is closed and trading happens on the LaunchDEX pool at the
  DEX's own fee (set on the DEX contract, default 0.30% — below the
  bonding 0.50%, so the graduation discount survives the venue change).

- The discount is acquired at graduation and is **irreversible**: a
  project that later loses trust keeps the lower fee on sells (holders
  exit cheap — D4 in the contract header). The milestone is what is
  rewarded.
- The setters cross-check the pair in BOTH directions
  (`set_trading_fee` refuses to go below `graduated_fee_bps`;
  `set_graduated_trading_fee` refuses to exceed `trading_fee_bps`), and
  the helper re-clamps at read time — no parameter sequence can invert
  the discount.
- Both quotes (`get_buy_quote`, `get_sell_quote`) use the same helper as
  the trades — a quote can never disagree with the trade it previews.

### 2b. Graduation, the two paths (v2)

| path            | trigger                                          | migration fee taken on |
|-----------------|--------------------------------------------------|------------------------|
| curve growth    | `R >= liquidity × graduation_multiplier` (×4)     | the grown reserves     |
| direct listing  | `liquidity >= direct_listing_threshold` at propose | the seed liquidity     |

- The threshold (default 2000 XEL = 500 × 4 — exactly what a curve
  graduate has proven) is **snapshotted per project at propose time**:
  the founder gets the rules they signed up with; later admin tuning
  never reclassifies an existing proposal.
- Both paths converge in the same `graduate()` — one set of
  post-graduation rules, no special cases.
- The threshold is cross-checked against `min_liquidity` in both
  directions: the fast track can never swallow every proposal, and a
  small float always gets its curve.

**What being migrated buys a project** (the full graduation set):

1. **Half the trading fee** (0.25% vs 0.50% by default) — every holder
   and every future buyer saves on every trade.
2. **Team unlock** — the allocation becomes claimable (§3).
3. **The Trusted badge** — Graduated/Trusted projects are listed by
   `get_trusted_projects` / `get_trusted_by_rank`, the frontend's
   "serious" shelf.
4. **Deep reserves from day one** (direct listing) or **proven demand**
   (curve path: the community put 4× the seed into the curve).
5. **Permanence** — the contract is the token's venue forever; liquidity
   can never be pulled (the founder's seed is locked in the curve).

What graduation does NOT buy: immunity. Trust votes continue for the
life of the project; 80% of all accumulated votes can flip it Untrusted
(buys blocked, sells never).

### 2c. The migration fee (v2, D9)

When a project graduates — by curve growth or direct listing —
`migration_fee_bps` (default 0.5%, hard cap 5%) is taken ONCE from the
project's reserves and accrues to `pending_fees` (admin revenue, like
every other fee — nothing is burned). Reserves dip by exactly that fee
and every subsequent trade prices it in; there is no further migration
cost, ever. A direct listing pays the fee on its seed liquidity; a curve
graduate on its ≥ 4×-larger grown reserves — the fee naturally scales
with the value the launchpad helped create.

Solvency note (invariant I2): the fee moves value from a curve's
reserves into `pending_fees` without touching `total_curve_xel`. This is
safe because every live project's seed liquidity sits uncommitted in the
contract balance (it only ever leaves as a rejected refund, which is
counted in `locked_refunds`), and the fee is capped at 5% of reserves
while reserves at graduation are at least the seed — the margin always
covers the fee many times over. The reference tests exercise graduation
plus a full admin fee drain and assert I2 throughout.

---

## 3. The team allocation (v2 D3, v3 D10)

The founder declares `team_bps` (≤ 20%) at propose time. The allocation
is **reserved in the curve from day one** (the sellable supply excludes
it), so it can never be over-sold — and it is **paid out exactly once
across all claim paths** (invariant I4), debited against a running
`team_paid` counter.

### 3a. The vesting plan — a votable commitment (v3, D10)

`propose()` takes a `vesting_duration`:

- `0` (default) — "team claims at graduation": the classic migration
  reward, `claim_team_allocation()` or a voluntary `start_team_vesting`
  afterwards (the v2 behaviour, unchanged).
- **any value inside `[vesting_min, vesting_max]`** (default ~1 month to
  ~1 year, admin-bounded) — a **DECLARED PLAN**. It is stored at propose
time, shown on the voting card (`get_proposal_data` → `vesting_plan`),
  and **bound automatically by `graduate()`**: the linear vesting starts
  itself, with exactly that duration, the moment the project graduates —
  whichever path gets it there. A planned project can never swap, retune
  or duplicate its vesting (`start_team_vesting` refuses it: `"planned"`)
  — the plan IS the vesting, and it is the schedule the community voted
  on.

The plan is validated against the bounds **snapshotted at propose time**
(D7-consistent: the founder gets the rules they signed up with), and it
only binds at graduation — a project that never graduates falls back to
the late-claim path below (plan or no plan, the team is never hostage).

### 3b. The three unlock paths

Evaluated lazily at claim time:

| situation                                  | unlocked amount               |
|--------------------------------------------|-------------------------------|
| vesting started (`vs > 0`)                 | `team × elapsed / duration` (linear, floored, saturating) |
| graduated, no vesting                      | the full allocation           |
| never graduated, `≥ team_unlock_delay` of bonding | the full allocation (the late claim) |
| anything else (validation, rejected, too early) | 0                         |

- **At migration, the creator chooses**: `claim_team_allocation()` pays
  the full remaining allocation immediately, OR `start_team_vesting(
  duration)` locks it into a linear stream (duration within the admin
  window, default ~1 month..~1 year) claimed incrementally. The vesting
  is a **public commitment signal** — the frontend shows it via
  `get_team_allocation`, and a vesting founder cannot dump.
  (Planned projects skip the choice: their vesting started itself at
  graduation — §3a.)
- **The vesting is irreversible** (one per project) — that is the point
  of a commitment.
- **The late claim keeps founders motivated**: a project that never
  graduates does not hold the team hostage. After the unlock delay
  (default ~6 months of bonding; the project may even be Untrusted or in
  Recovery — if it is still alive, the delay keeps running) the creator
  may claim in full (or start a vesting). Buyers are never diluted by
  this: the allocation was reserved in the curve's supply from day one,
  so its late release changes WHO holds those tokens, not how many
  exist (invariant I1: `curve_supply + balances + team_remaining ==
  total_supply`, always).
- A **rejected** project mints nothing: the launch never happened, the
  liquidity is refunded 100%, the team gets a lesson instead.

---

## 3c. Social links — mutable project metadata (v3, D11)

Twitter, Telegram and Discord links are part of the proposal (empty
string = "no link") and ride along with description/website/logo in
`propose()` and `update_project_info()`. The **team can change them at
any time** (the only frozen state is Rejected): communities move,
channels get rebuilt, and a launchpad that freezes social pointers
forces teams to abandon their own project page. Read them with
`get_social_links(pid) -> (twitter, telegram, discord)` or via the
`p:{id}:tw / tg / dc` storage keys.

Length-capped display metadata (≤ 256 chars each), same trust model as
the website field: the frontend renders, the voters judge. Name,
symbol, supply, team allocation and the vesting plan stay immutable
(structural — the plan is the ballot, changing it after the vote would
be changing the vote itself).

---

## 3d. The on-chain scoreboard — volume & market cap (v3, D12)

The contract itself calculates and stores the market data — no indexer,
no off-chain oracle, no trust:

**Volume** (per project AND protocol-wide), maintained by `record_trade`
on every buy/sell:

- `buy_volume` — sums the **attached XEL of every buy** (fee included:
  an exchange's quote-side convention)
- `sell_volume` — sums the **pre-fee gross XEL out** of every sell
- `total_volume = buy + sell` (invariant I9, exact at all times), plus
  the trade count and the last-trade topoheight
- read per project: `get_trading_stats` (keys `bv sv vo tc lt`);
  protocol-wide: `get_volume_stats` (keys `tbv tsv tvl ttc`)

**Market cap** = `R × circulating / C` (u128, saturating at u64 max),
where `circulating = total_supply − curve_supply − team_remaining` — the
tokens actually in holders' hands, excluding both the curve's sellable
balance and the team's unclaimed allocation. Maintained by
`update_market_cap()` after EVERY change of its inputs (buy, sell,
graduation fee, team claim):

- `mc` — the stored spot value, rewritten after every trade (it can
  never drift from the live state: same formula as the pure
  `get_market_cap` view)
- `mh` — the all-time high (only ever grows)
- `mg` — the market cap **at graduation**, snapshotted once, after the
  migration fee (the honest post-graduation number; 0 = never graduated,
  or a direct listing at t0 — nothing circulates before the first buy, so
  the honest snapshot is 0 and mc/mh light up on the first trade)
- read: `get_market_cap_history` → `(current, all_time_high,
  at_graduation)`

All accumulator additions are overflow-guarded (`checked_add` — a
corrupted counter is worse than a refused trade).

---

## 4. Fees & parameters (all admin-settable, all range-checked)

| parameter                  | default     | hard bounds                     |
|----------------------------|-------------|---------------------------------|
| submission_fee             | 10 XEL      | ≤ 100 XEL                       |
| asset_budget (D13)         | 10 XEL      | ≤ 100 XEL                       |
| min_liquidity              | 500 XEL     | [1 XEL, 100k XEL] and ≤ threshold |
| trading_fee_bps (bonding)  | 50 (0.5%)   | ≤ 1000 and ≥ graduated fee      |
| graduated_fee_bps          | 25 (0.25%)  | ≤ 1000 and ≤ trading fee        |
| migration_fee_bps          | 50 (0.5%)   | ≤ 500 (5%)                      |
| direct_listing_threshold   | 2000 XEL    | ≥ min_liquidity, ≤ 10M XEL      |
| validation window          | 51840 topos | [~1h, ~15d]                     |
| min_participants           | 20          | [1, 100k]                       |
| min_approval_ratio_bps     | 8000 (80%)  | (50%, 100%]                     |
| graduation_multiplier      | 4           | [2, 100]                        |
| team_unlock_delay          | 3,153,600 topos (~6 mo) | [~5d, ~2y]           |
| vesting bounds             | 518400..6307200 topos (~1..12 mo) | [~1d, ~2y], min < max |
| recovery_fee               | 250 XEL     | ≤ 1000 XEL                      |
| recovery thresholds        | 40 voters / 90% | stricter than validation    |
| vote_deposit (D21, v4.1)   | 0.5 XEL since v4.2 | ≤ 10 XEL — the REFUNDABLE sybil dial |

LaunchDEX parameters (set on the DEX contract — see `docs/DEX.md`):
`swap_fee_bps` 30 (≤ 1000), trade bounds, the launchpad pin (frozen at
the first pool), and **`lp_share_bps` 5000 — the admin/providers split
of every swap fee, hard-bounded [2500, 7500] (X10, v1.2)**.

**The sybil dial (D21)** deserves its own paragraph because it changes
UX. Since v4.2 the default is **0.5 XEL refundable** (founder risk
review, point 2): every `support()` and `report()` attaches it, it is
locked for the round's duration and refunded in full by
`claim_vote_deposit(pid, round)` once the round has closed (a newer
round exists, or the deadline passed). Honest voters only ever lend
capital — and half an XEL of it by default; sybil farmers must lock
N × deposit across wallets and rounds (20 farmed wallets deciding a
validation park 10 XEL while they do it). A raise only affects future
votes — already-locked deposits refund at their own recorded amount.
The admin can zero the dial at any time (0 = free voting) or move it
with `set_vote_deposit` (say 5 XEL under attack). Read the
dial and the locked total with `get_vote_config()`; the locked pots are
part of the committed side of the solvency invariant (I2) — the admin
can NEVER withdraw them as fees. The cap (10 XEL) keeps the dial a
sybil cost, never a participation toll. One honest nuance: the hard
lock applies to VALIDATION and RECOVERY windows (the gates a sybil
actually attacks); ongoing trust votes in Bonding/Graduated use a round
whose deadline is already past, so their deposit is only flash-locked
(vote transaction, then claim transaction) — the tallies still count
each address exactly once per round either way.

**Cross-checked pairs** (the two invariants the setters enforce between
each other): `graduated_fee_bps ≤ trading_fee_bps` (the graduation
discount can never invert) and `min_liquidity ≤ direct_listing_threshold`
(the fast track can never swallow every proposal). A compromised admin
can hurt the fee model, never the funds.

**Revenue model**: submission fees + trading fees (both rates) +
migration fees + recovery fees — 100% to the admin via `withdraw_fees`,
zero burn. The withdrawal is double-capped (accrued `pending_fees` AND
the uncommitted balance), so curves and refunds are always covered first
(invariant I2).

Read the live configuration with the views: `get_config()` (launch
parameters), `get_recovery_config()`, `get_team_config()`.

---

## 5. Security model (honest threat documentation)

- The admin is a hot role: it sets every parameter, pins the DEX
  (before the first migration only — D19) and can pause NEW proposals
  and NEW buys. It can NEVER move curve reserves, the token inventory,
  the team escrow, refundable rejections or earmarked budgets —
  `withdraw_fees` is its only XEL exit, double-capped (accrued
  `pending_fees` AND the uncommitted balance — live reserves + locked
  refunds + earmarked budgets, D20). Sells, votes, refunds, team
  claims, migration and finalization are never pausable.
- The migration is permissionless and its outcome fully determined:
  `migrate()` can only send the project's OWN reserves and inventory to
  the PINNED DEX contract — no destination, no amount, no caller
  choice. The pool it seeds has a PROTOCOL-LOCKED floor (the seed's
  parts are never withdrawable by anyone — D16/X11), and the protocol
  earns the provider share of every fee on its seed position (X11).
- The cross-contract surface is exactly two outbound calls
  (`create_pool`, `set_pool_buys_paused`), both inbound-guarded on the
  DEX side (pinned launchpad) and outbound-guarded here (frozen dex
  pin + `is_contract_callable` permission precheck, clear "txperm"
  refusal). The CALLING transaction must carry the contract-call
  permission — documented for wallets (XSWD "all" or an allowlist).
- Asset creation is balance-verified: if Fixed-mode semantics ever
  delivered less than the full supply, finalize reverts ("assetbal") —
  no partial-asset project can ever open.
- No reentrancy surface: XELIS invokes are atomic; the two outbound
  calls happen last in their entries (state first), and LaunchDEX
  calls no contract at all.
- Voting sybil-resistance is the network fee by default, plus the D21
  dial when raised: 1 address = 1 vote per round, and while the
  community is small, 20 wallets can decide a validation — this is a
  KNOWN product weakness, mitigated (not cured) by `min_participants`,
  the refundable vote deposit, and the report/trust system. XELIS
  confidentiality makes balance- or age-weighted voting impossible
  (nobody can read anyone's balance) — capital lock is the honest lever.
  The trust tallies accumulate for the whole life of the project.
- Front-running buys/sells is possible (no mempool privacy) — same as
  every public DEX on XELIS today; quotes are view functions, use them.
- Storage keys are fully namespaced (`p:`, `v:`, `t:` prefixes); the
  ticker registry key is built from a length-capped symbol in its own
  namespace. Every panic message is a fixed short literal.
- Storage growth is bounded: 8192 projects max, per-project state is a
  fixed key set, votes are one key per (project, round, address).

### 5a. The privacy model — what is public, what is private (D18, v4.1)

Say it plainly on the site; never promise total privacy.

| data                                        | public? | why                                     |
|---------------------------------------------|---------|-----------------------------------------|
| Wallet balances (XEL and launched assets)  | PRIVATE | native XELIS confidential balances      |
| Wallet-to-wallet transfers of launched tokens | PRIVATE | native confidential transfers        |
| Team allocation payouts (TeamClaimed)       | PRIVATE | the event carries NO amount (D18)       |
| Asset max supply / mintability              | PUBLIC  | protocol-level asset properties         |
| Deposits ATTACHED to contract calls         | PUBLIC  | the contract must read the amount       |
| Curve buys (XEL in) / sells (tokens in)     | PUBLIC  | they are attached deposits              |
| DEX swaps' input side                       | PUBLIC  | attached deposits                       |
| Vote deposits (the D21 amount attached)     | PUBLIC  | attached deposit — refunded later, but the amount was visible |
| LP parts & live provider earnings (v1.2)    | PUBLIC  | contract storage is public (l:{asset}:{wallet}:*) |
| Vote participation (which address voted)    | PUBLIC  | the vote event carries the voter        |
| Everything the views return (reserves, volumes, market caps) | PUBLIC | on-chain scoreboard by design |

The honest summary for users: **your balances and your wallet-to-wallet
transfers are confidential; your participation in the launchpad's
markets (what you attach to a buy/sell/swap/vote/liquidity add) is
public by chain design** — exactly like every contract interaction on
XELIS. If you do not want an amount to be public, do not attach it to a
contract call: there is no in-between, and any product that claims
total transactional privacy on XELIS contracts is lying.

### 5b. Upgrade runbook — the two frozen pins (D19, v4.1)

Both pins are one-way doors, on purpose: `set_dex_address` freezes at
the launchpad's first migration, and LaunchDEX's launchpad pin freezes
at its first pool. A frozen pin can never be repointed — not even by
the admin — which is what makes live pools un-orphanable. The
operational consequence is assumed: **a new VaultLaunch generation
requires a NEW LaunchDEX deployment**, side by side. **The full,
step-by-step runbook lives in `docs/UPGRADES.md`** (phase 0 gates →
testnet rehearsal → mainnet cut → site registry, plus the worst-case
playbook for a critical bug on a live generation); the summary:

1. Deploy the new LaunchDEX, pin the NEW launchpad on it
   (`set_launchpad`) BEFORE its first pool.
2. Deploy/point the new VaultLaunch, `set_dex_address` to the new DEX
   BEFORE its first migration.
3. Old venues keep serving their pools and curves FOREVER (the seed
   floor is protocol-locked in every generation) — nothing migrates,
   nothing breaks.
4. The site aggregates generations: each launchpad instance enumerates
   its own projects; each DEX instance exposes `get_launchpad()` so the
   frontend can verify which generation owns which pools, and every
   launchpad's `get_migrated_by_rank` lists its migrated set across
   DEX generations.

Never try to "reuse" a pinned DEX with a new launchpad: the pin refuses
("pinned"), and that refusal is the security model working.

---

## 6. Events (V6 contract events)

| id | event                 | fields                              |
|----|-----------------------|-------------------------------------|
| 1  | ProjectCreated        | id, name, symbol, liquidity         |
| 2  | ProjectSupported      | id, round, voter                    |
| 3  | ProjectReported       | id, round, voter                    |
| 4  | ValidationFinished    | id, "1"\|"0"                        |
| 5  | BondingOpened         | id                                  |
| 6  | TokensBought          | id, xel_in, tokens_out, fee         |
| 7  | TokensSold            | id, tokens_in, xel_out, fee         |
| 8  | ProjectGraduated      | id, reserves, team_allocation       |
| 9  | TrustLost             | id, reports, supports               |
| 10 | TrustRecovered        | id                                  |
| 11 | FeesCollected         | amount                              |
| 12 | ParamSet              | param, value                        |
| 13 | Paused                | "admin"                             |
| 14 | Unpaused              | "admin"                             |
| 15 | AdminSet              | new_admin                           |
| 16 | RefundClaimed         | id, amount                          |
| 17 | RecoveryRequested     | id, round                           |
| 18 | ProjectInfoUpdated    | id                                  |
| 19 | TeamVestingStarted    | id, duration                        |
| 20 | TeamClaimed           | id (**no amount** — D18 privacy)    |
| 21 | DirectListed          | id, liquidity                       |
| 22 | MigrationFeeTaken     | id, fee                             |
| 23 | AssetCreated          | id, asset_hex, fee_paid (D13)       |
| 24 | MigratedToDex         | id, xel_sent, tokens_sent (D15)     |
| 25 | DexTrustSynced        | id, "1"\|"0" (D17)                  |
| 26 | DexAddressSet         | dex_hex (D19)                       |
| 27 | VoteDepositClaimed    | id, round, amount (D21, v4.1)       |

---

## 7. Frontend integration guide

Storage keys are plain strings (read via `get_contract_data` with a
string key — see `sdk/xvault/xvault/launchpad.py`, which is a complete
Python reference):

- global: `pc` (project count), `sub abd mnl tfe gfe mgf dlt mnp mab
  vdt gmu tdy vmn vmx rfe rmp rmr` (parameters — `abd` = asset budget,
  D13), `pfe fcl tvl tcx lrf pz` (accounting), `tbv tsv ttc` (protocol
  volume scoreboard, D12), `tbb` (earmarked asset budgets, D20), `mgc`
  (migrated count — freezes the DEX pin at 1, D19), `dxa` (pinned DEX
  address), `adm` (admin), `xa` (XEL asset)
- project fields `p:{id}:{field}`: `cr` creator, `st` status, `nm sy ds
  ws lg tw tg dc` metadata (socials: D11), `ts tb lq rv cs` tokenomics,
  `ct ve` window, `sp rp rd` votes, `gr` graduated, `rc` refund claimed,
  `vo bv sv tc lt` volume scoreboard (D12), `dl` direct-listing eligible,
  `bt` bonding start, `tp` team paid, `vs vd vp` vesting start/duration/
  DECLARED PLAN (D10), `mc mh mg` market cap series (D12), `ah` ASSET
  HASH (D13 — query the asset itself on-chain), `ab` budget earmark,
  `mi ma mx mt` migration state (D15), `ds` dex trust synced (D17)
- votes `v:{id}:{round}:{addr}` (D21: the slot holds the voter's LOCKED
  deposit amount — presence IS the vote marker, a claimed deposit is
  zeroed but kept); ticker registry `t:{symbol}` (D11); reverse bridge
  `a:{asset_hex}` → project id (D22); migrated index `m:{rank}` →
  project id (D22)
- **token balances live in the WALLETS now** (v4): query the daemon for
  the asset (`ah`) like any XELIS balance — there is no `b:` ledger
- global (v4.1 additions): `vdp` vote deposit dial (D21), `tvp` total
  locked vote pots (D21 — part of I2's committed side)

Card layout suggestion (per project):

1. name/symbol/logo, status badge (`get_status_label`), Trusted badge if
   Graduated/Trusted, "direct listing" tag if `dl`
2. price (`get_current_price`), market cap (`get_market_cap`), fee badge
   (bonding vs graduated rate — buyers see what graduation saves them)
3. graduation progress: `reserves / graduation_target` (from
   `get_bonding_info`) for curve projects; "graduated" for the rest
4. votes: `sp / rp` and the current round (`get_project_trust`)
5. team panel (`get_team_allocation`, now 6 fields): allocation, paid,
   vesting stream progress, claimable now, **vesting plan** — and social
   links row (`get_social_links`): Twitter / Telegram / Discord
6. trade panel: `get_buy_quote` / `get_sell_quote` (they already use the
   project's effective fee); **v4**: wallet token balance = the real asset
   (`ah` via `get_asset_info`) — show it from the wallet daemon like any
   XELIS balance; the asset's `max_supply`/`mintable` (false forever) are
   the on-chain proof of the Fixed cap
7. market panel (D12): `get_trading_stats` (buy/sell split, trade count,
   last trade) + `get_market_cap_history` (current, ATH, at graduation —
   show the graduation milestone number). **v4 post-migration**: the
   curve panel freezes; compose the pool era with LaunchDEX
   (`get_pool_state` + `get_spot_price` + `get_pool_volume` on the asset
   hash) — the SDK (`xvault.dex`) does the composition
8. migration panel (D15): `get_migration_info` — migrated flag, when,
   exactly what seeded the pool, DEX pin, trust-sync state; while a
   graduated project awaits migration, show the "anyone can migrate"
   call-to-action (the frontend button calls `migrate`, needs the
   contract-call permission)

**The voting card** (Validation/Recovery status): ONE call gives the
community everything it votes on — `get_proposal_data` → (liquidity,
total_supply, team_bps, **vesting_plan**, direct_listed, created_topo,
validation_end) — plus `get_project_info` + `get_social_links` for the
metadata and `get_team_config` for the vesting window. The plan is on
the table BEFORE a single vote is cast (D10): `vesting_plan == 0` →
"team claims at graduation", any other value → "linear vesting of
exactly that length, enforced by the contract, starting at graduation".

Protocol dashboard: `get_protocol_stats` + `get_volume_stats` (the
launchpad's own total volume, buy/sell split and trade count).

Listings: `get_projects_by_status` + `get_project_by_rank` (paginated,
count-then-rank — Silex ABIs return no arrays), `get_latest_projects`,
`get_trusted_projects` + `get_trusted_by_rank` (the graduated shelf).

### 7a. The stateless-site data contract (D22, v4.1) — Vercel-proof

The site is statically hosted: it persists NOTHING. Every page must be
rebuildable from views alone, on every request. The complete recipe:

**Home / discover** — the four shelves:
1. Validating (vote now): `get_projects_by_status(0)` →
   `get_project_by_rank(0, r)` for r in 0..count
2. On the curve (bonding): status 2, same pattern
3. Graduated (pre-migration, curve still trading): status 3 (+4 Trusted)
4. Live on the DEX: `get_migrated_count()` → `get_migrated_by_rank(r)`
   → per pid: `get_migration_info` (which DEX) + `get_asset_info`
   (asset hash) → the pool itself on that DEX
   (`get_pools_count`/`get_pool_by_index`/`get_pool_state`/
   `get_spot_price`/`get_pool_volume` — or one `get_launchpad()` call to
   identify the generation)

**DEX → project page (the bridge)**: a pool enumerates as an ASSET hash;
`get_project_by_asset(asset)` returns the launchpad pid — from there the
full project card (name, socials, trust, vesting, curve-era scoreboard)
is the standard per-pid view set. This works across DEX generations:
each launchpad keeps its own reverse index, written at asset creation.

**Rejections/blackholes**: status 1 (for the record), no trading.

**Project page** = the 8-point card layout above + `get_vote_config()`
when the D21 dial is raised (show "5 XEL refundable deposit to vote").

**Provider dashboard (X10, v1.2)**: for a connected wallet with LP
parts in a pool, one `get_lp_info(asset, wallet)` per pool returns
(parts, available XEL, available tokens) — enough for a live "your
position / your earnings / claim" panel, `claim_lp_fees` being the
claim itself. The pool card adds the LP context from `get_pool_state`
(provider pots + total depth): the site can quote a prospective
provider's pro-rata share of the LP fee stream before they deposit.

**Protocol dashboard**: `get_protocol_stats` (now 12 fields — includes
`vote_pots`) + `get_volume_stats` + the DEX's own `get_pools_count`.

Every value the site shows — every listing, price, market cap, volume,
social link, trust badge, vesting progress, pool state — comes from a
view or a storage key documented above. No indexer, no database, no
server state, no cache to invalidate: the chain IS the backend.

Events (§6) drive the live feed: watch for `ProjectCreated`,
`ValidationFinished`, `TokensBought/Sold`, `ProjectGraduated`,
`DirectListed`, `TrustLost/Recovered`, `TeamVestingStarted/Claimed`,
`MigrationFeeTaken`, **`AssetCreated` (D13), `MigratedToDex` (D15),
`DexTrustSynced` (D17)**.

---

## 8. CLI

```
xvault launchpad status   --contract <hash>            # params, solvency, volume scoreboard
xvault launchpad project  --contract <hash> --id 0
                                                        # + socials, mcap series, plan,
                                                        #   asset hash, migration state
xvault launchpad team     --contract <hash> --id 0 [--topo N]
xvault launchpad quote    --reserves 500 --curve 90000000 --buy 100 [--fee-bps 50]
xvault launchpad propose  --name "Real Project" --symbol RPR \
    --supply 1000000 --team-bps 1000 --liquidity 500 \
    [--vesting N] [--twitter URL] [--telegram URL] [--discord URL] [--broadcast]
xvault launchpad migrate  --contract <hash> --id 0 [--broadcast]
                                                        # the atomic move to LaunchDEX
xvault launchpad sync     --contract <hash> --id 0 [--broadcast]
                                                        # trust -> pool buys-pause
xvault launchpad entries                                # chunk-id tables
xvault dex status        --contract <hash>              # pools, fee + split, pin state
xvault dex pool          --contract <hash> --asset <hash64>
                                                        # + provider pots & depth
xvault dex lp            --contract <hash> --asset <hash64> --wallet <addr>
                                                        # YOUR parts & live earnings
xvault dex claim-lp-fees --contract <hash> --asset <hash64> [--broadcast]
                                                        # pull YOUR provider fees
xvault dex set-fee-split --contract <hash> --percent 50 [--broadcast]
                                                        # admin: the split dial (25–75)
xvault dex quote         --x-reserve 2000 --y-reserve 900000000 \
    [--buy 100] [--sell 1000] [--fee-bps 30]
xvault dex entries                                     # + the pinned chunks 6/7
```

`propose` prints whether the liquidity qualifies for a direct listing
(and the deposit split — now fee + **asset budget** + liquidity),
validates the vesting plan against the live bounds, and shows the plan's
meaning (votable, bound at graduation). `team` shows the allocation
panel: paid, remaining, vesting progress (marked `declared plan` or
`voluntary`), late-claim countdown, claimable now. `project` prints the
socials row, the buy/sell volume split with trade count, the market-cap
series (now / ATH / at graduation), **the asset hash (real confidential
asset) and the migration state**. `migrate` prepares/sends the atomic
migration (reminding about the contract-call permission); `sync` mirrors
the trust status to the pool. `dex` subcommands read the pool era — and
since v1.2 also the PROVIDER era: `lp` shows a wallet's parts and live
earnings, `claim-lp-fees` pulls them (both sides), `set-fee-split` is
the admin's revenue dial.

---

## 9. Deployment checklist

1. Deploy **`LaunchDEX.slx` FIRST** on testnet; the deployer becomes the
   DEX admin. `set_launchpad(<launchpad_address>)` — the pin freezes at
   the first pool (X4).
2. Deploy `VaultLaunch.slx`; the deployer becomes the admin (use a cold
   wallet — `set_admin` is single-step). `set_dex_address(<dex_hash>)`
   — the pin freezes at the first migration (D19).
3. Sanity: `get_version` → `VaultLaunch v4.0.0` (and `LaunchDEX
   v1.0.0` on the DEX), `get_config` → the documented defaults,
   `get_migration_info` shows the pinned DEX.
4. Dry-run the two paths: propose a small float (bonding path) and a
   ≥ 2000 XEL float (direct listing); pass both validations (20 voters,
   80%); confirm `AssetCreated` (D13 — verify the asset exists in a
   real wallet with the Fixed cap, `mintable == false`), then
   `BondingOpened` vs `DirectListed` + `ProjectGraduated` +
   `MigrationFeeTaken` in the events.
5. Trade both: buy → check the fee rate matches the state (50 bps
   bonding, 25 bps graduated) and **the tokens arrive in the wallet**;
   sell (attach the whole position or part of it — whole-deposit
   semantics) → check the payout and the never-blocked exit. After each
   trade, verify the scoreboard: `get_trading_stats` +
   `get_market_cap_history` (mc follows every trade; mh only grows; mg
   == 0 until graduation).
6. **Migration drill (D15)**: on the graduated project, `migrate` (any
   wallet, contract-call permission) → `MigratedToDex`; curve closed
   (buy/sell now revert "migrated"); the LaunchDEX pool holds exactly
   `mx`/`mt`; swap both ways on the DEX (`swap_xel_for_token` /
   `swap_token_for_xel`) with real wallet balances; `add_liquidity`
   deepens the pool and mints withdrawable parts; `remove_liquidity`
   pays the exact pro-rata exit (and MUST refuse the seed — "locked");
   `claim_lp_fees` pays provider fees (the admin's seed position
   included); `withdraw_fees` on the DEX pays the pending pots to the
   DEX admin.
7. **Trust drill across venues (D17)**: report a project to 80% → buys
   blocked on the curve; migrate or `sync_trust_to_dex` → pool buys
   paused, pool sells still open; `request_revalidation` (250 XEL when
   graduated) → recovery vote → Trusted → `sync_trust_to_dex` again →
   pool buys resume.
8. Team panel: `claim_team_allocation` on the graduated project (full —
   real tokens in the creator's wallet), `start_team_vesting` +
   incremental claims on the other; verify `get_team_allocation` at
   every step. Also propose a third project WITH a declared plan
   (`--vesting`): verify the plan binds itself at graduation.
9. Metadata drill (D11): `update_project_info` with new socials mid-
   bonding and after graduation → `get_social_links` follows; non-creator
   refused; Rejected project refused. Also verify the ticker registry:
   a second propose with the same symbol reverts ("tick").
10. Fees: `withdraw_fees(pending)` and verify the double cap — the
    withdrawal can never make the contract insolvent (the committed sum
    now includes the earmarked asset budgets, D20).
11. Tune parameters if needed (range + cross-checks enforced on-chain),
    then announce the mainnet deployment with the config table. Repeat
    the checklist on mainnet (DEX first, then launchpad).
