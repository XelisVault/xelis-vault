# Security Policy — XelisVault Protocol v13

## Reporting

Report vulnerabilities privately to the repository owner (GitHub security
advisory: *Security → Report a vulnerability*). Please include a minimal
reproduction, affected entry points and impact. Coordinated disclosure with
credit; no bounties yet (community project).

## State of the codebase

### v13 (current, this tree)

- `contracts/mixer/PrivacyMixerV4.slx` — the **only** production contract.
  Written against the full v12 audit findings; every dangerous pattern is
  excluded by construction and machine-checked on every push:
  - zero `let _ = transfer` (swallowed transfer failures) — linter rule R1
  - zero unchecked transfers — R2
  - zero owner-drain entries — R3
  - every `.expect()`/`.unwrap()` guarded by a preceding `require` — R4
  - zero 34-byte address literals — R5
  - storage-write entries are either guarded or intentionally public — R7
- `sdk/xvault` — client tooling; never handles keys (writes are prepared
  here, signed by your local wallet).

### legacy/ (read-only archive)

The 51 v12 contracts are archived **as-is**. The v13 audit found them not
deployable: trivial drains (transfers paid from contract balance without
collecting deposits), a global DoS via miner deregistration, reward pools
with accounting-only distributions, ~100 privileged entries all initialized
to the deployer, and single-key emergency-withdraw switches on every
module. **Do not deploy anything from `legacy/`.** The linter report
(`python3 scripts/lint_silex.py --scan-legacy`) documents 1316 blocker/error
findings across those files — kept on purpose as a regression corpus for
the CI rules.

## How the CI protects this repository

Every push and PR runs `.github/workflows/ci.yml`:

1. **silex-lint** — the 10 audit-derived rules; any BLOCKER/ERROR fails the
   build. Reports are uploaded as artifacts.
2. **chunk-ids** — the documented chunk table of each contract must match
   the declaration order exactly, and the mixer must contain **zero**
   inter-contract calls (single-contract invariant).
3. **tests** — the reference test-suite proves the Python reference
   (`sdk/xvault/xvault/crypto.py`) reproduces the contract's hashing, tree,
   fee and emergency-exit math byte-for-byte.
4. **structure** — layout rules and a secret scan (PATs, private keys,
   tokens) over all active files.

Local equivalents: `python3 scripts/lint_silex.py`,
`python3 scripts/verify_chunk_ids.py`, `python3 -m pytest tests/`.

## Notable findings from the v12 audit (selected)

1. **Unbalanced entry books** — v12's `entry_chunk_ids.json` numbered only
   `entry` functions (0-based among entries), while the compiler's chunk
   maps (and the cross-contract call sites that were validated against
   them) number constructor + every function. Any wallet invoke built from
   that JSON table targets the wrong chunk on contracts that declare
   private helpers before their first entry. The v13 SDK ships the
   compiler numbering plus a `xvault mixer probe` command that settles the
   mapping on a live network in one command before any mainnet use.
2. **Swallowed transfer failures** — 91 `let _ = transfer(...)` across 22
   contracts silently ate failed payouts (linter rule R1 exists because of
   this).
3. **Owner-drain switches** — 15 contracts let a single key sweep user
   funds after a 1-day delay (rule R3).
4. **Unguarded panics** — 1114 reachable `.expect()`/`.unwrap()` paths,
   several triggerable by any user (rule R4; the miner deregistration DoS
   was the worst case).

## Trust assumptions during launch (mixer only)

| Privilege | Holder | After `renounce_ownership()` |
|---|---|---|
| pause/unpause | owner | gone |
| emergency_exit | owner | gone (if never used before) |
| fee up to 1% | owner, hard-capped | fee rate frozen at last value |
| fee collection | fee_recipient | unchanged (revenue continues) |
| user funds | **nobody** — not even the owner | unchanged |

Recommended community timeline: renounce 30–90 days after a stable mainnet
launch, after exercising the escape hatch once on testnet.
