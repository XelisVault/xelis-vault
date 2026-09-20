# Architecture — XelisVault Protocol v13

## Why a rewrite of the layout

The v12 repository held **51 contracts (~40k lines of Silex)** spanning
chat, mining, lending, governance, auctions, insurance, payroll, analytics,
social trading, RWA and NFT modules. The v13 audit concluded that most of
them were not deployable (see docs/SECURITY.md), and that the surface area
itself was the problem: nobody can audit 51 contracts, so nothing was
actually safe — including the good ideas buried inside.

v13 takes the opposite bet:

> **one audited contract live on mainnet beats fifty contracts on paper.**

## Layout

```
contracts/
  mixer/PrivacyMixerV4.slx   the production contract (self-contained)
sdk/xvault/                  Python CLI + SDK (key-less by design)
scripts/                     CI tooling: linter, chunk-id verifier, structure check
tests/                       reference tests (crypto ↔ contract byte-parity)
docs/                        MIXER / SECURITY / ARCHITECTURE (this file)
legacy/                      the 51 v12 contracts, archived read-only
.github/workflows/ci.yml     strict CI: lint + chunks + tests + structure
```

## Principles

1. **Single-contract deployments.** A contract that calls no other contract
   has no chunk-id drift, no permission graph, no compositional failure
   modes. The mixer is the template: state, invariants and escape hatches
   all in one file.
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
re-scoped as small, single-purpose contracts that pass the same bar as the
mixer:

| Module | v12 state | v13 plan |
|---|---|---|
| Privacy mixer | secrets leaked in withdraw params | **done — V4, mainnet-ready** |
| Vault engine | debts erased for free, collateral math broken | rewrite as one contract, XEL-only first |
| Oracle | slash-all deviation logic, global DoS via miner list | staked-report median with bounded slash, no global iteration |
| Governance | quorum never checked, timelock incompatible delays | minimal governor: snapshot, quorum, timelock ≥ delay |
| Registry | single-key redirect of any contract name | frozen hash pins or multi-sig only |

Each module ships only after: lint clean, chunk table verified, reference
tests green, and a written threat model in docs/.

## Fee model (protocol revenue)

- Mixer: withdrawal fee, default 0.3%, hard cap 1%, collected into the
  contract and claimable by `fee_recipient` up to `balance − pending`
  (depositors always first). The fee recipient is set **before** the first
  mainnet deposit and survives ownership renunciation — protocol revenue
  outlives centralization.
- Future modules follow the same pattern: capped, transparent, claim-only,
  never able to touch principal.
