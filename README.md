# XelisVault Protocol

[![CI](https://github.com/XelisVault/xelis-vault/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
![Silex](https://img.shields.io/badge/contract-PrivacyMixer%20V4-8b5cf6)
![License](https://img.shields.io/badge/license-MIT-blue)

Privacy-first DeFi primitives for [XELIS](https://xelis.io), built in
[Silex](https://docs.xelis.io/). **v13** — one audited contract live beats
fifty contracts on paper.

## What ships today

**[PrivacyMixer V4](contracts/mixer/PrivacyMixerV4.slx)** — a self-contained
privacy pool for XEL:

- bearer notes bound to the withdrawal address (theft-proof, front-run-proof)
- incremental Merkle tree, depth 20, ~1M notes, 64-root proof tolerance
- fixed denominations: 10 / 100 / 1000 XEL
- withdrawal fee 0.3% (hard cap 1%), depositor-first accounting
- `pause` + irreversible community `emergency_exit` + `renounce_ownership`
- **the owner can never move deposited funds** — no drain entry exists
- zero inter-contract calls, zero keepers, one file

Design, threat model and guarantees: **[docs/MIXER.md](docs/MIXER.md)**.
Security policy and audit history: **[docs/SECURITY.md](docs/SECURITY.md)**.

## Quickstart (CLI)

```bash
pip install ./sdk/xvault          # installs the `xvault` command

xvault mixer status --contract <hash> --network mainnet
xvault mixer deposit --amount 100 --recipient xel:FRESH_ADDRESS \
    --contract <hash> --network mainnet --note-out note-001.json
# broadcast from your wallet (local xelis_wallet RPC or Genesix/XSWD),
# then later, from the RECIPIENT wallet:
xvault mixer withdraw --note note-001.json --contract <hash> --network mainnet
```

The CLI never touches your keys: it prepares transactions, your local wallet
signs them. Full reference: [sdk/xvault/README.md](sdk/xvault/README.md).

## Repository layout

```
contracts/mixer/   production Silex contracts (mixer only, for now)
sdk/xvault/        Python CLI + SDK
scripts/           CI tooling (linter, chunk-id verifier, structure check)
tests/             reference tests — Python crypto ↔ contract byte-parity
docs/              MIXER / SECURITY / ARCHITECTURE
legacy/            v12 archive (51 contracts) — testnet era, kept intact (see legacy/README.md)
```

## CI

Every push and PR runs strict checks (`.github/workflows/ci.yml`):

- **silex-lint** — 10 audit-derived security rules (swallowed transfers,
  owner drains, unguarded panics, …) — blockers fail the build
- **chunk-ids** — declared chunk tables must match the compiler numbering;
  the mixer must contain zero inter-contract calls
- **tests** — the Python reference must reproduce the contract's Merkle,
  fee and emergency-exit math exactly
- **structure** — layout rules + secret scanning

Run locally: `python3 scripts/lint_silex.py && python3 scripts/verify_chunk_ids.py && python3 -m pytest tests/`

## Audit status

v12 was fully audited and retired (1316 blocker/error findings across 51
contracts — the corpus now powers the linter). v13 starts from a clean
tree with the mixer as the first and only production contract. Details:
[docs/SECURITY.md](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
