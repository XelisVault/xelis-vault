# XelisVault Protocol

[![CI](https://github.com/XelisVault/xelis-vault/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
![Silex](https://img.shields.io/badge/contracts-PrivacyMixer%20V5%20%2B%20VaultLaunch-8b5cf6)
![License](https://img.shields.io/badge/license-MIT-blue)

Privacy-first DeFi primitives for [XELIS](https://xelis.io), built in
[Silex](https://docs.xelis.io/). **v15** — audited contracts live beat
fifty contracts on paper.

## What ships today

**[VaultLaunch](contracts/launchpad/VaultLaunch.slx)** — a serious
launchpad: community validation before every launch, constant-product
bonding curve, graduation at 4x liquidity, long-term Trusted/Untrusted
community trust system, every fee configurable and 100% of the revenue
to the admin (no burn):

- propose → 3-day community vote (≥ 20 voters, ≥ 80% support) → bonding
  curve opens; rejected projects refund 100% of the founder's liquidity
- constant-product curve, integer-exact and solvent by construction
  (u128 math, contract-favouring floors); trading fee 0.5% (cap 10%)
- graduation at `liquidity × 4` mints the team allocation (≤ 20%, capped)
  to the creator — never before; trading continues, the contract is the
  token's permanent venue (no inter-contract calls on XELIS)
- losing trust (80% of all votes) blocks buys but NEVER sells; recovery
  for graduated projects costs a 250 XEL fee + a stricter re-vote
- admin can pause new proposals/buys and tune every parameter
  (range-checked); it can never touch curve reserves, balances or refunds

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

# launchpad — status, one project, offline curve math, prepare a proposal
xvault launchpad status --contract <hash> --network mainnet
xvault launchpad project --contract <hash> --id 0 --owner xel:...
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
rebuilt the tree around the mixer; **v15 adds VaultLaunch**, the second
production contract, built to the same bar: lint clean, chunk table
verified, reference tests green, threat model written.
Details: [docs/SECURITY.md](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
