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


---

## v18 — the real-asset attack surface (VaultLaunch v4 + LaunchDEX)

**New surface: the cross-contract calls (bounded, pinned, prechecked).**
Exactly two outbound calls exist in VaultLaunch: LaunchDEX `create_pool`
(chunk 6, from `migrate`) and `set_pool_buys_paused` (chunk 7, from
`sync_trust_to_dex` and the untrusted-at-migration path). Both are
inbound-guarded on the DEX (pinned launchpad address, frozen at the
first pool — X4) and outbound-guarded on the launchpad (DEX pin frozen
at the first migration — D19, plus the `is_contract_callable` precheck
with the clear `"txperm"` refusal). The pinned chunk ids are asserted
against the real chunk tables by CI (`tests/test_dex_reference.py`):
renumbering either contract without the other fails the build. A
malicious migrator gains nothing — `migrate()` has no destination, no
amount and no caller choice: it can only perform the migration the
community is waiting for, into a pool nobody can drain.

**Asset creation (D13).** Fixed-mode creation is balance-verified: if
the whole supply does not land in the contract, finalize reverts
(`"assetbal"`). The chain's creation fee is measured by balance-delta
and paid from the project's earmarked budget (+ optional finalize
top-up, unused part refunded) — the solvency invariant I2 now includes
the earmarked budgets (D20), so a fee hike can never be paid out of
other projects' reserves.

**Whole-deposit semantics (D14).** `sell(pid)` sells the ENTIRE attached
token deposit and `buy(pid)` the entire attached XEL deposit: nothing
can be stranded in the contract by a partial amount, and the per-asset
identity `balance == curve inventory + team escrow` (I1) holds at every
block. Post-migration the identity degenerates to the team escrow (I10)
— the migration sends exactly the inventory, never the escrow.

**The DEX's own threat model (v1.1, founder risk review).** The DEX
admin can set the swap fee (cap 10%), the trade bounds, the launchpad
pin (before the first pool only) and trigger the global emergency
pause. It can NEVER move pool reserves: `withdraw_fees` is capped by
the pending pots AND the uncommitted balance (IX1/IX2). No
remove_liquidity exists anywhere — permanent liquidity is the feature.
**Sells are ungated, absolutely (IX6)**: the per-pool flag pauses buys
only, and since v1.1 the emergency pause gates buys, pool creation and
liquidity adds ONLY — the sell path carries NO gate at all. A
compromised admin can tax sellers (fee hard-capped at 10%) but can
NEVER trap holders. And since v1.1 `add_liquidity` is price-neutral
(X7/IX7): a malicious one-sided donation cannot skew a market — only
swaps move a pool's price.

**The founder risk review, closed (v4.1).** The six pre-launch risks
and their resolutions: (1) one-sided liquidity → X7 ratio fit with
same-transaction refund of the excess; (2) emergency pause trapping
holders → sells carry no gate on either venue; (3) frozen upgrade
pins → assumed and documented as the side-by-side runbook
(LAUNCHPAD.md §5b, `get_launchpad()` exposes the pin); (4) hardcoded
cross-call chunk ids → pinned constants asserted against BOTH real
tables by CI on every push (append-only rule for the DEX); (5) sybil
voting → the D21 refundable-deposit dial (default off, cap 10 XEL,
`claim_vote_deposit` refunds, pots committed in I2), honest that it
mitigates and does not cure; (6) public deposits → the privacy model
is documented in plain words (LAUNCHPAD.md §5a) — balances are
confidential, attached amounts are public, never promise total
privacy.

**Permissions note for integrators.** Transactions that cross-call
(`migrate`, `sync_trust_to_dex`, and the DEX's launchpad-only entries)
must carry the wallet's contract-call permission (XSWD "all" or an
allowlist). The contracts refuse early with `"txperm"` instead of
failing opaquely. Voters and traders NEVER need the permission:
report/support/swap entries make no cross-calls (D17).
