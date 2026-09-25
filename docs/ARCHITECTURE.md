# Architecture — XelisVault Protocol v18

## Why a rewrite of the layout

The v12 repository held **51 contracts (~40k lines of Silex)** spanning
chat, mining, lending, governance, auctions, insurance, payroll, analytics,
social trading, RWA and NFT modules. The v13 audit concluded that most of
them were not deployable (see docs/SECURITY.md), and that the surface area
itself was the problem: nobody can audit 51 contracts, so nothing was
actually safe — including the good ideas buried inside.

v13 takes the opposite bet:

> **audited contracts live on mainnet beat fifty contracts on paper.**

## Layout

```
contracts/
  launchpad/VaultLaunch.slx    the launchpad (active product, self-contained)
  dex/LaunchDEX.slx            the AMM (v1.4: launchpad-pinned + open seeding)
  community/CommunityLaunch.slx  the permissionless community-coin factory
  mixer/PrivacyMixerV5.slx     the privacy pool (on hold pending VM features)
  mixer/superseded/            archived V4 (the R11 regression corpus)
abi/                           transaction-facing entry tables (compile artifacts)
sdk/xvault/                    Python CLI + SDK (key-less by design)
scripts/                       CI tooling: linter, chunk-id verifier, structure check
tests/                         reference tests (Python ↔ contract parity)
docs/                          LAUNCHPAD / DEX / COMMUNITY_LAUNCH / MIXER / SECURITY / ARCHITECTURE
legacy/                        the 51 v12 contracts, archived read-only
.github/workflows/ci.yml       strict CI: lint + chunks + tests + structure
```

Each active contract lives in its own family directory
(`contracts/<family>/`). Adding a family is a deliberate decision recorded
in scripts/check_structure.py (`active_families`), the CI workflow and
this file — in the same commit.

## Principles

1. **Single-contract deployments.** A contract that calls no other contract
   has no chunk-id drift, no permission graph, no compositional failure
   modes. The mixer and the launchpad are the templates: state, invariants
   and escape hatches all in one file each.
2. **Client-side logic wherever possible.** Merkle proofs, note generation
   and local verification live in the SDK — on-chain code stays minimal,
   and the gas bill lands on the party who benefits.
3. **Machine-checked documentation.** The chunk table in the contract
   header, the lint rules and the Python reference are all cross-checked by
   CI. Documentation that can drift is documentation that lies.
4. **Honest threat models.** docs/MIXER.md states exactly what the mixer
   does and does not hide. No marketing claims, no "military-grade" prose.

## Core protocol — consolidation plan (phase 2)

The vault/oracle/stablecoin ideas from v12 are not dead; they are being
re-scoped as small, single-purpose contracts that pass the same bar:

| Module | v12 state | v13+ plan |
|---|---|---|
| Launchpad | no community filter, no curve, no trust system | **done — VaultLaunch v3: validation vote, two-path graduation (curve / direct listing), trust system, team vesting with declared plans, mutable social links, on-chain volume/market-cap scoreboard** |
| Privacy mixer | secrets leaked in withdraw params | **done — V5 dead-drop; on hold pending VM zk primitives** |
| Vault engine | debts erased for free, collateral math broken | rewrite as one contract, XEL-only first |
| Oracle | slash-all deviation logic, global DoS via miner list | staked-report median with bounded slash, no global iteration |
| Governance | quorum never checked, timelock incompatible delays | minimal governor: snapshot, quorum, timelock ≥ delay |
| Registry | single-key redirect of any contract name | frozen hash pins or multi-sig only |

Each module ships only after: lint clean, chunk table verified, reference
tests green, and a written threat model in docs/.

## Fee model (protocol revenue)

- Launchpad: submission fee (default 10 XEL) + trading fee (default 0.5%
  bonding / 0.25% graduated, cap 10%, cross-checked pair) + migration fee
  (default 0.5% of reserves, once at graduation, cap 5%) + recovery fee
  (default 250 XEL on graduated projects) — 100% to the admin, zero burn.
  Fees accrue in the contract and leave ONLY through `withdraw_fees`,
  double-capped by the accrued amount and by the uncommitted balance
  (curves and refunds are always covered first).
- Mixer: withdrawal fee, default 0.3%, hard cap 1%, collected into the
  contract and claimable by `fee_recipient` up to `balance − pending`
  (depositors always first). The fee recipient is set **before** the first
  mainnet deposit and survives ownership renunciation — protocol revenue
  outlives centralization.
- Future modules follow the same pattern: capped, transparent, claim-only,
  never able to touch principal.


## v18 — VaultLaunch v4 + LaunchDEX (real assets, real migration)

**The launchpad finally launches REAL tokens.** Every validated project's
token is a native XELIS confidential asset: `Asset::create` with
`MaxSupplyMode::Fixed` at `finalize_validation` (D13) — the whole supply
is minted to the contract, the cap is enforced by the XELIS protocol
itself, and the creation cost is measured by balance-delta from an
earmarked budget (refunded if unused). The bonding curve trades real
deposits (D14): buys transfer actual tokens to wallets, sells consume
the whole attached token deposit. The internal ledger of v1-v3 is gone.

**Graduation is now a real migration (D15).** Between graduation and
migration the curve keeps trading at the graduated fee (admin-lag
tolerant); then `migrate()` — permissionless, atomic — seeds a
LaunchDEX pool with the curve's whole reserves and inventory via one
cross-contract call with attached deposits, and that seed is
protocol-locked FOREVER (X11 — the pool's depth can never fall below
the migration). The curve closes forever; the launchpad remains the
project's home (votes, socials, trust, team escrow).

**LaunchDEX (contracts/dex/).** Minimal AMM with a PERMANENT FLOOR:
one XEL-quote pool per asset, constant product, fees extracted to
per-pool pending pots and split admin/providers. The liquidity is
two-tier (v1.3): the migrated seed is protocol-locked forever (its
parts carry no withdrawable balance — the anti-rug floor), while
providers' `add_liquidity` parts are withdrawable pro-rata at any
time (`remove_liquidity` — price-neutral, ungated, never the seed).
The launchpad pin
freezes at the first pool (X4); the DEX pin on the launchpad freezes at
the first migration (D19); the two cross-called chunk ids are CI-asserted
on both sides. Trust follows the tokens: `sync_trust_to_dex` (a
permissionless keeper entry) mirrors the Untrusted status to the pool's
buys-pause — sells are never pausable on either venue (D17).

**Privacy (D18).** Native XELIS confidentiality for every launched
token: wallet balances and transfers are encrypted at the base layer.
Team claims pay via confidential transfers and the TeamClaimed event
carries no amount. Public by chain design: deposits attached to contract
invocations.

**Accounting (D20, I1/I2/I10 + IX1..IX6).** `total_curve_xel` is now the
EXACT sum of live curve reserves (seeds included) — the committed side
of I2 also includes pending fees, locked refunds, earmarked asset
budgets and (since v4.1) the locked vote pots (D21). Per-asset:
`launchpad asset balance == curve inventory + unpaid
team allocation` (I1), degenerating to the team escrow after migration
(I10). The DEX keeps its own solvency (reserves + pending pots ==
balances, IX1/IX2), verified by the fuzz suite after every action.

See docs/LAUNCHPAD.md (§1a/§1b) and docs/DEX.md for the full
specifications.

## v18.1 — the founder risk review, closed (hardening only)

Six risks were raised before communicating "it's live"; six are closed
WITHOUT changing the architecture (no storage migration, no renumbered
cross-call chunks — the DEX additions are append-only):

1. **One-sided liquidity** — `add_liquidity` now enforces the pool's
   CURRENT ratio (X7): only the proportional slice of a deposit joins
   the reserves, the excess side is refunded in the same transaction.
   New invariant IX7: the reserve product drifts by at most one floor
   unit per add — only swaps move a pool's price.
2. **Emergency pause too broad** — the DEX sell path now carries NO
   gate at all (IX6, absolute): the emergency pause gates buys, pool
   creation and liquidity adds only. A compromised admin can tax (fee
   cap 10%) but never trap holders.
3. **Upgrade path** — assumed operationally: the runbook deploys new
   generations side by side (old venues serve their pools forever); the
   new `get_launchpad()` DEX view exposes the pin for ops and the site.
4. **Hardcoded chunk ids** — already CI-frozen in v18; the rule is now
   written down: DEX functions append at the END only, ids 6/7 never
   move (`tests/test_dex_reference.py` asserts both sides).
5. **Sybil voting** — the D21 dial: an admin-settable REFUNDABLE vote
   deposit (default 0 = free, cap 10 XEL) with `claim_vote_deposit`
   pull-refunds; the pots are committed in I2 so fees can never touch
   them. Documented as mitigation, not cure.
6. **Public deposits** — the privacy model is now a doc table
   (LAUNCHPAD.md §5a): balances private, attached amounts public — the
   site must never promise total privacy.

**Site data (D22).** The statically-hosted site persists nothing; the
contracts now serve every listing through views: the asset→project
reverse bridge (`get_project_by_asset`, written at asset creation) maps
DEX pools back to launchpad pages, and the migrated index
(`get_migrated_count`/`get_migrated_by_rank`) enumerates every project
that ever moved to a pool — across DEX generations. The full
stateless-site recipe is LAUNCHPAD.md §7a.

## v18.2 — the second founder risk review, closed (providers earn, honest limits)

Four points raised; all closed. The architecture is unchanged (append-only
DEX additions, chunks 6/7 untouched, no storage migration):

1. **Liquidity provision earned nothing** — LaunchDEX v1.2 (X10/D23):
   every swap fee now splits between the admin pot and the pool's
   liquidity providers, pro-rata of each provider's share of the LP
   depth (XEL side, the fit rule keeps both sides proportional).
   Default 50/50; the dial (`set_fee_split`) is hard-bounded
   [2500, 7500] — a hostile admin can neither zero the providers nor
   starve the treasury. Distribution is accrual-per-unit with per-
   provider snapshots; `claim_lp_fees` is a public pull (own-key-only,
   bounded by the pots, works under the emergency pause). New invariant
   IX8 (LP solvency) holds by construction; the 1 XEL LP-entry floor is
   the precision bound that keeps the accrual counter inside u64 for
   the pool's whole life.
2. **Sybil voting still free by default** — the D21 dial now ships at
   0.5 XEL refundable (VaultLaunch v4.2): twenty farmed wallets deciding
   a validation park 10 XEL of capital while they do it. Still
   admin-settable [0, 10 XEL], refunds untouched.
3. **Frozen pins = no in-place upgrade** — the runbook is now a real
   document (`docs/UPGRADES.md`): the generation model, the exact
   procedure (gates → testnet rehearsal → mainnet cut → site registry),
   and the worst-case playbook for a critical bug on a live generation.
4. **Honesty about limits** — the security policy now states plainly
   what is audited and what is NOT (v4/v1.x: internal CI verification
   only, no external audit — never say "audited"), and front-running is
   documented as an assumed ceiling (public mempool, `min_out`
   everywhere, no MEV protection claimed).

## v18.3 — the third founder risk review, closed (seed shares, free providers)

Two points; both closed by LaunchDEX v1.3 (append-only, chunk 32, pins
6/7 untouched, no storage migration, VaultLaunch v4.2 unchanged):

1. **The migrated liquidity had no LP parts** — the economics bug:
   `create_pool` planted the reserves but left `tl = 0`, so the FIRST
   1 XEL add on a 4000 XEL pool captured 100% of the provider fee
   share. Fixed by X11 (seed shares): create_pool now mints LP parts
   equal to the XEL seed to the admin (the protocol LP position,
   snapshots posited at the zero accrual counters) and records them as
   the pool's protocol-locked parts (`pl`). The first external add
   mints its marginal depth (1/4001), and the protocol itself earns
   the provider share of every fee pro-rata on its position —
   fees-only forever (no withdrawable balance is ever minted for the
   seed, so not even a compromised admin can turn it into principal).
   The seed floor also carries the IX8 precision bound through
   removes (IX9: `tl >= pl >= ACC_SCALE` forever).
2. **Providers were locked in forever** — X12 (`remove_liquidity`,
   chunk 32): any provider burns withdrawable parts for their exact
   floored pro-rata share of BOTH reserves at the current ratio.
   Price-neutral (IX7 holds on removes), min_out on both sides, fees
   crystallised BEFORE the burn (an exit never forfeits earnings),
   UNGATED (no pause check — the IX6 principle extended to provider
   exits), and the seed floor is unreachable ("locked" +
   "seederr" belt-and-braces). The pool can never be emptied
   ("poolerr"/"parterr"). New view surface: `get_pool_state` exposes
   the seed floor (9th field), `get_lp_info` the withdrawable balance
   (4th field) — the frontend shows "depth X, of which the migration's
   Y is permanent" and the live exit quote.

---

## v18.4 — the two tracks: projects AND community coins (CommunityLaunch v1.0 + LaunchDEX v1.4)

**The launchpad grows a second shelf.** CommunityLaunch
(contracts/community/) is the permissionless community-coin factory —
the pump.fun track: anyone launches a REAL XELIS confidential asset in
one transaction for ~2 XEL, no vote, no founder liquidity. Pricing
starts on a VIRTUAL-RESERVE bonding curve (C1): a constant virtual XEL
reserve (default 100 XEL) and a mirrored virtual token reserve give
the coin a sensible price and single-digit slippage from the FIRST
buy, while only the buyers' real XEL accumulates — solvency is proved,
not hoped for (IC3/IC4: the curve product k never decreases through
trades, so the real reserves are non-negative by construction and the
worst-case sell is exactly covered). Graduation is a demand proof in
TWO conditions (C2): real depth (default 50 XEL, snapshotted per coin)
AND price continuity (xr·y0 ≥ yr·vx — the pool opens at or above the
curve's spot, no graduation dump by construction). The migration is
permissionless on BOTH sides (C6): anyone calls migrate(), and the DEX
endpoint it drives — create_pool_open, LaunchDEX v1.4 chunk 33 (X13) —
has no gate at all (on this VM get_caller() is the transaction signer
even cross-contract, so a factory-only gate cannot be expressed; the
deposits are the authorisation). The one-time migration fee is carved
from the POOL SEED, never the live curve (C4 — the k-invariance the
solvency proof needs). The creator allocation is small (≤ 5%), held
off-curve, and claimable ONLY post-migration (C5): a creator's payoff
is conditional on the coin graduating.

**LaunchDEX v1.4 also fixes the second-migration bug**: create_pool
used to return the pool's INDEX, and the launchpad's migrate_to_dex
treats a non-zero cross-call result as failure — only the FIRST
project migration would ever have succeeded on a gen-1 pair. v1.4
chunks return 0 on success; the fix is invisible to the v1 interface
(VaultLaunch v4.2 calls it unchanged) but needs a NEW generation to
reach mainnet — and since the gen-1 pins froze at nothing yet (no pool
exists), the recommended cut is: deploy ONE v1.4 DEX, repin the gen-1
launchpad to it (still possible), and pin the new factory to it too —
both tracks share the same DEX lineage, its launchpad pin serving only
as the moderation hook (per-pool buys-pause). See
COMMUNITY_LAUNCH.md §10 and UPGRADES.md §6.

---
