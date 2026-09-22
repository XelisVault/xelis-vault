

# XelisVault Protocol

[![CI](https://github.com/XelisVault/xelis-vault/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
![Silex](https://img.shields.io/badge/contracts-PrivacyMixer%20V5%20%2B%20VaultLaunch%20v4%20%2B%20LaunchDEX-8b5cf6)
![License](https://img.shields.io/badge/license-MIT-blue)

Privacy-first DeFi primitives for [XELIS](https://xelis.io), built in
[Silex](https://docs.xelis.io/). **v18.3** — real confidential assets,
real migration, two-tier liquidity with a PERMANENT SEED FLOOR (the
migration is protocol-locked forever; providers earn their pro-rata and
can exit pro-rata anytime), hardened by three founder risk reviews
(price-neutral DEX liquidity, ungated sells AND provider exits, sybil
dial ON by default, stateless-site data bridges).

## What ships today

**[VaultLaunch](contracts/launchpad/VaultLaunch.slx)** — a serious
launchpad: community validation before every launch, constant-product
bonding curve, **two-path graduation**, long-term Trusted/Untrusted
community trust system, every fee configurable and 100% of the revenue
to the admin (no burn):

- propose → 3-day community vote (≥ 20 voters, ≥ 80% support) → bonding
  curve opens; rejected projects refund 100% of the founder's liquidity
- constant-product curve, integer-exact and solvent by construction
  (u128 math, contract-favouring floors); bonding fee 0.5% (cap 10%)
- **graduation is worth reaching (v16)**: graduated projects trade at a
  LOWER fee (0.25% default, cross-checked to stay ≤ the bonding fee),
  the team allocation unlocks, and a one-time migration fee (0.5% of
  reserves, cap 5%) funds the protocol
- **two-path graduation (v16)**: lock ≥ the direct-listing threshold
  (default 2000 XEL, admin-tunable) and the project graduates the moment
  validation passes — no bonding phase; smaller floats discover price on
  the curve and graduate at `liquidity × 4`
- **the vote sees everything (v17)**: the team vesting plan is declared
  at propose time and bound by the contract at graduation (the community
  votes on the exact unlock schedule, not a promise — `get_proposal_data`
  shows it all before a single vote is cast)
- **social links (v17)**: Twitter / Telegram / Discord on the project
  card, updatable by the team at any time (`get_social_links`)
- **the contract keeps the scoreboard (v17)**: buy/sell volume, trade
  count, last trade, spot market cap, all-time-high market cap and the
  market cap at graduation — all computed AND stored on-chain
  (`get_trading_stats`, `get_market_cap_history`, `get_volume_stats`)
- **REAL confidential assets (v18)**: the token of every validated
  project is a true XELIS asset — `Asset::create` with
  `MaxSupplyMode::Fixed` at validation success: the ENTIRE supply exists
  from birth, whole supply held by the contract, and NOTHING can ever be
  minted past the cap (enforced by the XELIS protocol itself). Buyers
  hold real tokens in their own wallets from the first second — fully
  confidential balances, transferable anywhere on XELIS
- **real migration (v18)**: graduation moves the curve's XEL reserves
  and token inventory ATOMICALLY into a
  [LaunchDEX](contracts/dex/LaunchDEX.slx) pool (one cross-contract call
  with attached deposits; permissionless `migrate()`); the curve keeps
  trading at the graduated fee until the pool exists
- **LaunchDEX (v18.2+v18.3)**: the AMM for graduated tokens with a
  PERMANENT FLOOR — the migrated seed is protocol-locked FOREVER (its
  LP parts carry no withdrawable balance; nobody can ever drain a pool
  below its migration), while providers who deepen a pool
  (`add_liquidity`, PRICE-NEUTRAL since v1.1: the pool's ratio is
  enforced and the excess is refunded) hold withdrawable parts and may
  exit pro-rata at any time (`remove_liquidity` v1.3: exact floored
  payout, min_out both sides, NO gate — never the seed); fees 0.30%
  default split between the admin pot and the POOL'S PROVIDERS (v1.2:
  pro-rata of LP depth, 50/50 default, dial hard-bounded 25–75%,
  `claim_lp_fees` pull), and since v1.3 the seed itself mints the
  protocol's LP position (X11: the first external add mints 1/4001 of
  a 4000 XEL pool, not 100% — and the protocol earns the provider
  share on its position); per-pool scoreboard; the community trust
  system follows the tokens there (`sync_trust_to_dex` pauses pool buys,
  never sells — and the emergency pause itself can never block a sell,
  a claim or a remove)
- **founder risk review, closed (v18.1)**: (1) one-sided liquidity
  gifts can't skew markets (X7); (2) sells are ungated on BOTH venues;
  (3) the upgrade runbook assumes the frozen pins (side-by-side
  generations — now a FULL runbook, `docs/UPGRADES.md`); (4) cross-call
  chunk ids pinned + CI-asserted on both sides; (5) the REFUNDABLE
  vote-deposit dial (D21, `claim_vote_deposit`) raises sybil cost;
  (6) the privacy model documented in plain words (public deposits,
  private balances). The stateless site (Vercel) reads EVERYTHING from
  views — including the asset→project reverse bridge and the migrated
  index (D22)
- **founder risk review 2, closed (v18.2)**: (1) liquidity provision
  now EARNS — the LP fee share above; (2) the sybil dial ships ON by
  default (0.5 XEL refundable — 20 farmed wallets park 10 XEL to
  decide a validation); (3) front-running documented as an assumed
  ceiling (public mempool; `min_out` everywhere; no MEV protection
  claimed); (4) the generation runbook written out step by step
  (`docs/UPGRADES.md`)
- **founder risk review 3, closed (v18.3)**: (1) the seed's LP parts
  mint to the protocol — the first-add fee-capture bug is dead (1 XEL
  on a 4000 XEL pool = 1/4001 of the provider share, not 100%) and the
  protocol earns the provider share on its position; (2) providers are
  free — `remove_liquidity` pays the exact pro-rata exit under any
  state (fees crystallised first, nothing forfeited), while the seed
  floor is absolute ("locked"/"seederr" — not even the admin can
  withdraw the migration)
- team allocation (≤ 20%): claim in full at migration OR lock it in a
  linear vesting (public commitment signal); a project that never
  graduates releases the allocation after ~6 months of bonding —
  founders are never hostage, holders keep their exit
- losing trust (80% of all votes) blocks buys but NEVER sells; recovery
  for graduated projects costs a 250 XEL fee + a stricter re-vote
- admin can pause new proposals/buys and tune every parameter
  (range-checked, fee pairs cross-checked); it can never touch curve
  reserves, balances or refunds

Design, math, threat model, frontend guide: **[docs/LAUNCHPAD.md](docs/LAUNCHPAD.md)**.

**[PrivacyMixer V5 "Dead-Drop"](contracts/mixer/PrivacyMixerV5.slx)** — a
self-contained privacy pool for XEL (**status: on hold** pending VM
features — see the status note at the top of docs/MIXER.md):

- deposits carry ONLY a client-computed commitment — the recipient address
  and the secret never appear on-chain at deposit time
- the recipient never signs anything and never needs gas: after a random
  delay (~1h..~3d, on-chain bounded), the funds simply arrive in its wallet
- `release` is permissionless and front-run-proof — anyone (a bounty-funded
  bot, a friend, you from any wallet) can trigger the payout, but it ALWAYS
  lands on the committed recipient
- incremental Merkle tree, depth 20, ~1M notes, 64-root proof tolerance
- fixed denominations: 10 / 100 / 1000 XEL; withdrawal fee 0.3% (cap 1%);
  release bounty 0.05 XEL (cap 0.5 XEL)
- `pause` (deposits only — exits can never be frozen) + irreversible community
  `emergency_exit` + `renounce_ownership`
- **the owner can never move deposited funds** — no drain entry exists
- zero inter-contract calls, zero keepers, zero trusted relayers, one file

Design, threat model and guarantees: **[docs/MIXER.md](docs/MIXER.md)**.
Security policy and audit history: **[docs/SECURITY.md](docs/SECURITY.md)**.

## Quickstart (CLI)

```bash
pip install ./sdk/xvault          # installs the `xvault` command

# launchpad — status, one project, team panel, offline curve math, prepare a proposal
xvault launchpad status --contract <hash> --network mainnet
xvault launchpad project --contract <hash> --id 0 --owner xel:...
xvault launchpad team --contract <hash> --id 0
xvault launchpad quote --reserves 500 --curve 90000000 --buy 100
xvault launchpad propose --name "Real Project" --symbol RPR --supply 1000000 \
    --team-bps 1000 --liquidity 500 --contract <hash> --network mainnet

# mixer (on hold for mainnet until the VM ships the missing pieces)
xvault mixer status --contract <hash> --network testnet
```

The CLI never touches your keys: it prepares transactions, your local wallet
signs them. Full reference: [sdk/xvault/README.md](sdk/xvault/README.md).

## Repository layout

```
contracts/
  launchpad/        production Silex contracts (one per product family)
  └─ mixer/           PrivacyMixer V5 (on hold) + superseded/ V4 archive
sdk/xvault/        Python CLI + SDK
scripts/           CI tooling (linter, chunk-id verifier, structure check)
tests/             reference tests — Python ↔ contract parity
docs/              LAUNCHPAD / MIXER / SECURITY / ARCHITECTURE
legacy/            v12 archive (51 contracts) — testnet era, kept intact (see legacy/README.md)
```

## CI

Every push and PR runs strict checks (`.github/workflows/ci.yml`):

- **silex-lint** — 11 audit-derived security rules (swallowed transfers,
  owner drains, unguarded panics, deposit-params address leaks, …) —
  blockers fail the build
- **chunk-ids** — declared chunk tables must match the compiler numbering;
  the mixer must contain zero inter-contract calls
- **tests** — the Python reference must reproduce the contract's Merkle,
  commitment (incl. XELIS Bech32 / Address::to_bytes), fee and
  emergency-exit math exactly
- **structure** — layout rules + secret scanning

Run locally: `python3 scripts/lint_silex.py && python3 scripts/verify_chunk_ids.py && python3 -m pytest tests/`

## Audit status — read this before saying "audited"

**v12 (51 legacy contracts) was formally audited and retired** (1316
blocker/error findings; the corpus now powers the linter). PrivacyMixer
V4 was superseded before deployment (recipient leak in deposit params +
recipient-gas problem — see docs/SECURITY.md §V4 disclosure). **Those
audits cover NONE of the current production contracts.**

**VaultLaunch v4+ and LaunchDEX v1+ have NO external, independent
audit.** What they have is internal, CI-enforced verification on every
push: the audit-derived Silex linter, the full reference test suite
(Python mirrors replaying the contracts' exact math), five formal audit
scripts (spec traceability, security heuristics, SDK parity, doc
parity, randomized fuzz with invariants after every action) and the
chunk-id/structure/secret gates. The honest phrasing: *internally
audited, machine-checked in CI, no external audit yet.* Budget an
external review before any mainnet deployment carrying real value.

History: v13/v14 rebuilt the tree around the mixer; v15 added
VaultLaunch; v16 made graduation pay; v17 put everything on-chain
(vesting plans, socials, scoreboard); v18 shipped real assets + atomic
migration to LaunchDEX; v18.1 closed the first founder risk review
(X7, ungated sells, D21/D22); v18.2 closed the second (LP fee share,
sybil dial on by default, front-running documented, the generation
runbook); v18.3 closed the third (seed shares, free providers).
Details: [docs/SECURITY.md](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
