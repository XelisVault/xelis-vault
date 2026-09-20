# XelisVault Protocol

[![CI](https://github.com/XelisVault/xelis-vault/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
![Silex](https://img.shields.io/badge/contract-PrivacyMixer%20V5-8b5cf6)
![License](https://img.shields.io/badge/license-MIT-blue)

Privacy-first DeFi primitives for [XELIS](https://xelis.io), built in
[Silex](https://docs.xelis.io/). **v14** — one audited contract live beats
fifty contracts on paper.

## What ships today

**[PrivacyMixer V5 "Dead-Drop"](contracts/mixer/PrivacyMixerV5.slx)** — a
self-contained privacy pool for XEL:

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

xvault mixer status --contract <hash> --network mainnet
xvault mixer deposit --amount 100 --recipient xel:FRESH_ADDRESS \
    --contract <hash> --network mainnet --note-out note-001.json
# that's it — after the random delay (~1h..~3d) the funds arrive at the
# recipient on their own (release bots / anyone can trigger the payout;
# the payout is bound to the committed recipient and cannot be redirected)
xvault mixer note-info --note note-001.json --contract <hash> --network mainnet
```

The CLI never touches your keys: it prepares transactions, your local wallet
signs them. Full reference: [sdk/xvault/README.md](sdk/xvault/README.md).

## Repository layout

```
contracts/mixer/   production Silex contracts (mixer only, for now)
                   └─ superseded/  archived V4 (flawed, do not deploy)
sdk/xvault/        Python CLI + SDK
scripts/           CI tooling (linter, chunk-id verifier, structure check)
tests/             reference tests — Python crypto ↔ contract byte-parity
docs/              MIXER / SECURITY / ARCHITECTURE
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
start from a clean tree with the mixer as the first and only production
contract. Details: [docs/SECURITY.md](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
