# XelisVault Protocol

[![CI](https://github.com/XelisVault/xelis-vault/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
![Silex](https://img.shields.io/badge/contracts-PrivacyMixer%20V5%20%2B%20VaultLaunch%20v4%20%2B%20LaunchDEX-8b5cf6)
![License](https://img.shields.io/badge/license-MIT-blue)

Privacy-first DeFi primitives for [XELIS](https://xelis.io), built in
[Silex](https://docs.xelis.io/). **v18** — real confidential assets,
real migration, permanent liquidity.

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
  and token inventory ATOMICALLY into a permanent
  [LaunchDEX](contracts/dex/LaunchDEX.slx) pool (one cross-contract call
  with attached deposits; permissionless `migrate()`); the curve keeps
  trading at the graduated fee until the pool exists
- **LaunchDEX (v18)**: the permanent AMM for graduated tokens — no
  remove_liquidity exists anywhere (the anti-rug guarantee), anyone can
  deepen a pool forever (`add_liquidity`), fees 0.30% default extracted
  to pending pots (100% admin), per-pool scoreboard; the community trust
  system follows the tokens there (`sync_trust_to_dex` pauses pool buys,
  never sells)
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

## Audit status

v12 was fully audited and retired (1316 blocker/error findings across 51
contracts — the corpus now powers the linter). PrivacyMixer V4 was
superseded before deployment (recipient leak in deposit params +
recipient-gas problem — see docs/SECURITY.md §V4 disclosure). v13/v14
rebuilt the tree around the mixer; v15 added VaultLaunch; v16 made
graduation pay (two-path graduation, lower graduated fee, one-time
migration fee, flexible team allocation); **v17 puts everything on the
table**: the vesting plan declared at propose and bound at graduation,
mutable social links, and the on-chain volume/market-cap scoreboard —
same bar: lint clean, chunk table verified, reference tests green
(incl. a 30-seed invariant fuzz), threat model written.
Details: [docs/SECURITY.md](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
