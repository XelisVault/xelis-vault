# VaultLaunch — Design Specification

> contracts/launchpad/VaultLaunch.slx · v2.0.0 · mainnet-ready (testnet first)

A serious launchpad for XEL: real projects are filtered by a community
validation vote, priced by a constant-product bonding curve, and held to a
long-term community trust standard (Trusted / Untrusted). Every fee is
configurable by the admin and 100% of the revenue goes to the admin —
nothing is burned. This is NOT a memecoin casino: the vote window is the
quality filter, the trust system keeps founders accountable forever, and
the curve math is integer-exact and solvent by construction.

**v2 — graduation is worth reaching.** Two paths now lead to graduation:
a founder who locks serious liquidity (≥ the direct-listing threshold)
graduates the moment validation passes; smaller floats discover price on
the bonding curve and graduate when their reserves grow ×4. Graduated
projects trade at a LOWER fee, the team allocation unlocks (immediate
claim or voluntary vesting), and a small one-time migration fee — taken
from the curve, pump.fun-style but smaller — funds the protocol.

One file. Zero inter-contract calls. Zero external dependencies.

---

## 1. Lifecycle

```
                 propose() [fee + seed liquidity]
                        |
                        v
                0 VALIDATION
                (support / report window,
                 ends at validation_end topo)
        pass >= 20 voters AND >= 80%      fail
        |----------------------------------|
        |                                  v
        |                           1 REJECTED
        |                           claim_refund() -> 100% of the
        |                           founder's liquidity, once
        |                           (NO team tokens — a rejected
        |                            launch never mints)
        |
        +-- liquidity >= direct_listing_threshold (snapshotted at propose)
        |            |
        |            v  DIRECT LISTING (D7)
        |   3 GRADUATED on the spot: migration fee taken on the seed,
        |      graduated fee from the first trade, Trusted badge,
        |      team unlock — the full graduation set, day one
        |
        v  else (smaller float)
  2 BONDING
  buy / sell live
  votes continue (trust)
        |
        | reserves >= liquidity x 4 (default)
        v  CURVE GRADUATION
  3 GRADUATED (+ Trusted)
  one-time migration fee taken from the grown reserves (D9)
  team allocation claimable (D3); trading CONTINUES at the
  graduated fee (the contract is the token's permanent venue)
        |
        | reports reach 80% of all votes
        v
  5 UNTRUSTED  <-------------------------------------.
  buys BLOCKED, sells open, votes open                |
  (graduated projects KEEP the lower fee:             |
   the milestone is rewarded, not punished)           |
        | request_revalidation()                      | fail
        |  - not graduated: free, normal thresholds   |
        |  - graduated: 250 XEL fee, 40 voters, 90%   |
        v                                              |
  6 RECOVERY (new voting round, tallies reset) --------'
        | pass
        v
  2 BONDING (never graduated) or 4 TRUSTED (graduated)
```

Status codes (see `get_status_label`): `0 validation, 1 rejected,
2 bonding, 3 graduated, 4 trusted, 5 untrusted, 6 recovery`.

**Who triggers what.** XELIS has no timers: every transition is
event-driven. Graduation fires inside the `buy()` that crosses the
threshold, or inside `finalize_validation()` for a direct listing; trust
loss fires inside the vote that crosses the ratio; window outcomes are
applied by `finalize_validation()`, callable by
ANYONE after the deadline (the outcome is fully determined by the public
tallies — the finalizer only executes it). The vesting stream and the
team unlock delay are evaluated lazily, at claim time, against the
current topoheight.

**Why "graduation" at all, if trading never stops?** Graduation is a
status milestone with real economics attached — see §2a. It is the
launchpad's incentive spine: everyone (founder, buyers, community) is
pushed toward the same goal.

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

## 3. The team allocation (v2, D3)

The founder declares `team_bps` (≤ 20%) at propose time. The allocation
is **reserved in the curve from day one** (the sellable supply excludes
it), so it can never be over-sold — and it is **paid out exactly once
across all claim paths** (invariant I4), debited against a running
`team_paid` counter.

Three unlock paths, evaluated lazily at claim time:

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

## 4. Fees & parameters (all admin-settable, all range-checked)

| parameter                  | default     | hard bounds                     |
|----------------------------|-------------|---------------------------------|
| submission_fee             | 10 XEL      | ≤ 100 XEL                       |
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

- The admin is a hot role: it sets every parameter and can pause NEW
  proposals and NEW buys. It can NEVER move curve reserves, user token
  balances, refundable rejections, or team allocations — `withdraw_fees`
  is its only XEL exit, double-capped. Sells, votes, refunds, team
  claims and finalization are never pausable.
- No reentrancy surface: XELIS invokes are atomic, the contract calls no
  other contract, and every transfer happens after all state changes
  (checks-effects-interactions).
- Voting sybil-resistance is the network fee, nothing more (documented,
  not hidden). 20+ voting transactions at 80% agreement make cheap
  attack campaigns expensive; the trust tallies accumulate for the whole
  life of the project.
- Front-running buys/sells is possible (no mempool privacy) — same as
  every public DEX on XELIS today; quotes are view functions, use them.
- Storage keys are fully namespaced (`p:`, `v:`, `b:` prefixes); no
  user-controlled key material. Every panic message is a fixed short
  literal.
- Storage growth is bounded: 8192 projects max, per-project state is a
  fixed key set, votes are one key per (project, round, address).

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
| 20 | TeamClaimed           | id, amount                          |
| 21 | DirectListed          | id, liquidity                       |
| 22 | MigrationFeeTaken     | id, fee                             |

---

## 7. Frontend integration guide

Storage keys are plain strings (read via `get_contract_data` with a
string key — see `sdk/xvault/xvault/launchpad.py`, which is a complete
Python reference):

- global: `pc` (project count), `sub mnl tfe gfe mgf dlt mnp mab vdt
  gmu tdy vmn vmx rfe rmp rmr` (parameters), `pfe fcl tvl tcx lrf pz`
  (accounting), `adm` (admin), `xa` (XEL asset)
- project fields `p:{id}:{field}`: `cr` creator, `st` status, `nm sy ds
  ws lg` metadata, `ts tb lq rv cs` tokenomics, `ct ve` window, `sp rp
  rd` votes, `gr` graduated, `rc` refund claimed, `vo` volume, `dl`
  direct-listing eligible, `bt` bonding start, `tp` team paid, `vs vd`
  vesting start/duration
- balances `b:{id}:{addr}` (the launched token IS this ledger), votes
  `v:{id}:{round}:{addr}`

Card layout suggestion (per project):

1. name/symbol/logo, status badge (`get_status_label`), Trusted badge if
   Graduated/Trusted, "direct listing" tag if `dl`
2. price (`get_current_price`), market cap (`get_market_cap`), fee badge
   (bonding vs graduated rate — buyers see what graduation saves them)
3. graduation progress: `reserves / graduation_target` (from
   `get_bonding_info`) for curve projects; "graduated" for the rest
4. votes: `sp / rp` and the current round (`get_project_trust`)
5. team panel (`get_team_allocation`): allocation, paid, vesting stream
   progress, claimable now — a running vesting is a trust signal
6. trade panel: `get_buy_quote` / `get_sell_quote` (they already use the
   project's effective fee), token balance via `get_token_balance`

Listings: `get_projects_by_status` + `get_project_by_rank` (paginated,
count-then-rank — Silex ABIs return no arrays), `get_latest_projects`,
`get_trusted_projects` + `get_trusted_by_rank` (the graduated shelf).

Events (§6) drive the live feed: watch for `ProjectCreated`,
`ValidationFinished`, `TokensBought/Sold`, `ProjectGraduated`,
`DirectListed`, `TrustLost/Recovered`, `TeamVestingStarted/Claimed`,
`MigrationFeeTaken`.

---

## 8. CLI

```
xvault launchpad status   --contract <hash>            # params, solvency, stats
xvault launchpad project  --contract <hash> --id 0 --owner xel:...
xvault launchpad team     --contract <hash> --id 0 [--topo N]
xvault launchpad quote    --reserves 500 --curve 90000000 --buy 100 [--fee-bps 50]
xvault launchpad propose  --name "Real Project" --symbol RPR \
    --supply 1000000 --team-bps 1000 --liquidity 500 [--broadcast]
xvault launchpad entries                                # chunk-id tables
```

`propose` prints whether the liquidity qualifies for a direct listing
(and the deposit split). `team` shows the allocation panel: paid,
remaining, vesting progress, late-claim countdown, claimable now.

---

## 9. Deployment checklist

1. Deploy `VaultLaunch.slx` on **testnet**; the deployer becomes the
   admin (use a cold wallet — `set_admin` is single-step).
2. Sanity: `get_version` → `VaultLaunch v2.0.0`, `get_config` → the
   documented defaults.
3. Dry-run the two paths: propose a small float (bonding path) and a
   ≥ 2000 XEL float (direct listing); pass both validations (20 voters,
   80%); confirm `BondingOpened` vs `DirectListed` + `ProjectGraduated`
   + `MigrationFeeTaken` in the events.
4. Trade both: buy → check the fee rate matches the state (50 bps
   bonding, 25 bps graduated); sell → check the payout and the never-
   blocked exit.
5. Team panel: `claim_team_allocation` on the graduated project (full),
   `start_team_vesting` + incremental claims on the other; verify
   `get_team_allocation` at every step.
6. Trust drill: report a project to 80% of all votes → buys blocked,
   sells open; `request_revalidation` (250 XEL when graduated) →
   recovery vote → Trusted.
7. Fees: `withdraw_fees(pending)` and verify the double cap — the
   withdrawal can never make the contract insolvent.
8. Tune parameters if needed (range + cross-checks enforced on-chain),
   then announce the mainnet deployment with the config table.
