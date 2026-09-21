# Security Policy — XelisVault Protocol v17

## Reporting

Report vulnerabilities privately to the repository owner (GitHub security
advisory: *Security → Report a vulnerability*). Please include a minimal
reproduction, affected entry points and impact. Coordinated disclosure with
credit; no bounties yet (community project).

## State of the codebase

### v17 (current, this tree)

- `contracts/launchpad/VaultLaunch.slx` — the launchpad (v2: two-path
  graduation, graduated fee, migration fee, team vesting; v3: declared
  vesting plans, mutable social links, on-chain volume/market-cap
  scoreboard), built to the same bar as the mixer and machine-checked on
  every push:
  - zero `let _ = transfer` (swallowed transfer failures) — linter rule R1
  - zero unchecked transfers — R2
  - zero owner-drain entries; the admin's only XEL exit is
    `withdraw_fees`, double-capped (accrued fees AND uncommitted balance) —
    R3 + the I2 solvency invariant
  - every `.expect()`/`.unwrap()` guarded by a preceding `require` — R4
  - every admin parameter range-checked against hard caps (trading and
    graduated fees can never exceed 10%, the migration fee 5%) and the
    fee/liquidity pairs CROSS-CHECKED (`graduated_fee ≤ trading_fee`,
    `min_liquidity ≤ direct_listing_threshold`) — documented in
    docs/LAUNCHPAD.md §4
  - public-by-design entries (`sell`, `finalize_validation`) carry written
    exemptions in the linter; `support`/`report` are caller-bound by the
    vote-marker key itself — R7
  - listing views use const-bounded loops (R8) and rank accessors instead
    of array returns (no compiled ABI ever returned an array — verified
    against the v12 compiler ground truth)
  - the team allocation is paid EXACTLY once across all claim paths
    (immediate, vesting stream, late claim) via the `team_paid` debit
    counter — invariant I4, asserted by the reference mini-VM after
    every operation
  - the v3 scoreboard is overflow-guarded end to end: every volume
    accumulator grows only through `record_trade` with `checked_add`
    (u128-wide, explicit overflow refusal), the stored market cap is
    recomputed from storage by `update_market_cap` after EVERY change of
    its inputs (it can never drift from the pure `get_market_cap`
    formula — invariant I9, asserted per-step by the fuzz), `mh` is
    monotone and `mg` is written exactly once, at graduation
  - the declared vesting plan (D10) is validated against the bounds
    snapshotted at propose time and bound automatically at graduation;
    `start_team_vesting` refuses planned projects ("planned") — the
    votable commitment can never be swapped, retuned or duplicated
  - the SDK's entry-id table is CI-pinned to the contract's real chunk
    numbering (tests/test_launchpad_reference.py) — a drift would invoke
    the wrong entry, so it cannot happen silently
- `contracts/mixer/PrivacyMixerV5.slx` — the privacy pool. Same lint bar,
  fully implemented and tested, **on hold for mainnet** pending VM zk
  primitives (see the status note in docs/MIXER.md).
- `sdk/xvault` — client tooling; never handles keys (writes are prepared
  here, signed by your local wallet). The deposit commitment is computed
  client-side with a byte-exact port of Silex `Address::to_bytes()` (XELIS
  Bech32, separator `:` — verified against xelis-blockchain source).

### PrivacyMixer V4 disclosure (superseded before deployment)

V4 was never deployed on any network. During the V5 design review two
flaws were found and are documented so they can never be reintroduced:

1. **Recipient leak at deposit time** — `deposit(secret, recipient)` carried
   the payout address in plaintext invoke parameters, linking depositor and
   recipient in the deposit transaction itself. Lint rule R11 now blocks
   this pattern repository-wide; the archived file is the regression
   corpus.
2. **Recipient-gas problem** — `withdraw` required the recipient wallet to
   pay gas, forcing an on-chain funding transaction that defeats the mixer.
   V5's dead-drop model removes the need for the recipient to transact at
   all.

The archived contract lives in `contracts/mixer/superseded/` with a
banner; it is excluded from CI lint but scanned explicitly by the test
suite to prove R11 still detects the flaw.

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

1. **silex-lint** — the 11 audit-derived rules; any BLOCKER/ERROR fails the
   build. Reports are uploaded as artifacts.
2. **chunk-ids** — the documented chunk table of each contract must match
   the declaration order exactly, and the mixer must contain **zero**
   inter-contract calls (single-contract invariant).
3. **tests** — the reference test-suite proves the Python reference
   (`sdk/xvault/xvault/crypto.py`) reproduces the contract's hashing (incl.
   the XELIS Bech32 address encoding and `Address::to_bytes()` format),
   tree, fee/bounty and emergency-exit math byte-for-byte, and models the
   front-run resistance of the release flow.
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
| pause/unpause (deposits only) | owner | gone |
| emergency_exit | owner | gone (if never used before) |
| fee up to 1% | owner, hard-capped | fee rate frozen at last value |
| release bounty up to 0.5 XEL | owner, hard-capped | frozen at last value |
| fee collection | fee_recipient | unchanged (revenue continues) |
| releases (exits) | **nobody can block them** — not even the owner, not even paused | unchanged |
| user funds | **nobody** — not even the owner | unchanged |

Recommended community timeline: renounce 30–90 days after a stable mainnet
launch, after exercising the escape hatch once on testnet.
