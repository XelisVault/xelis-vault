# Architecture — XelisVault Protocol v15

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
  launchpad/VaultLaunch.slx  the launchpad (active product, self-contained)
  mixer/PrivacyMixerV5.slx   the privacy pool (on hold pending VM features)
  mixer/superseded/          archived V4 (the R11 regression corpus)
sdk/xvault/                  Python CLI + SDK (key-less by design)
scripts/                     CI tooling: linter, chunk-id verifier, structure check
tests/                       reference tests (Python ↔ contract parity)
docs/                        LAUNCHPAD / MIXER / SECURITY / ARCHITECTURE
legacy/                      the 51 v12 contracts, archived read-only
.github/workflows/ci.yml     strict CI: lint + chunks + tests + structure
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
| Launchpad | no community filter, no curve, no trust system | **done — VaultLaunch v1: validation vote, bonding curve, trust system** |
| Privacy mixer | secrets leaked in withdraw params | **done — V5 dead-drop; on hold pending VM zk primitives** |
| Vault engine | debts erased for free, collateral math broken | rewrite as one contract, XEL-only first |
| Oracle | slash-all deviation logic, global DoS via miner list | staked-report median with bounded slash, no global iteration |
| Governance | quorum never checked, timelock incompatible delays | minimal governor: snapshot, quorum, timelock ≥ delay |
| Registry | single-key redirect of any contract name | frozen hash pins or multi-sig only |

Each module ships only after: lint clean, chunk table verified, reference
tests green, and a written threat model in docs/.

## Fee model (protocol revenue)

- Launchpad: submission fee (default 10 XEL) + trading fee (default 0.5%,
  cap 10%) + recovery fee (default 250 XEL on graduated projects) — 100%
  to the admin, zero burn. Fees accrue in the contract and leave ONLY
  through `withdraw_fees`, double-capped by the accrued amount and by the
  uncommitted balance (curves and refunds are always covered first).
- Mixer: withdrawal fee, default 0.3%, hard cap 1%, collected into the
  contract and claimable by `fee_recipient` up to `balance − pending`
  (depositors always first). The fee recipient is set **before** the first
  mainnet deposit and survives ownership renunciation — protocol revenue
  outlives centralization.
- Future modules follow the same pattern: capped, transparent, claim-only,
  never able to touch principal.
