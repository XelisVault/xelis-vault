# Security Policy — XelisVault Protocol v18.3

## Reporting

Report vulnerabilities privately to the repository owner (GitHub security
advisory: *Security → Report a vulnerability*). Please include a minimal
reproduction, affected entry points and impact. Coordinated disclosure with
credit; no bounties yet (community project).

## What is audited — and what is NOT (read this first)

Honest words, because "audited" gets people hurt:

- **v12 (51 legacy contracts) was formally audited and retired** — 1316
  blocker/error findings; the corpus now powers the CI linter.
- **VaultLaunch v4+ and LaunchDEX v1+ have NO external, independent
  audit.** What they have is an INTERNAL, CI-enforced battery, run on
  every push: the strict Silex linter (audit-derived rules), the full
  reference test suite (Python mirrors replaying the contracts' exact
  math), five formal audit scripts (spec traceability founder-requirement
  by founder-requirement, security heuristics, SDK parity, doc parity,
  randomized fuzz with invariants asserted after every action) and the
  chunk-id/structure/secret gates.
- Internal audits find classes of bugs (accounting, bounds, rounding,
  access control) with high reliability — the v1.2 LP accrual design
  shipped with a snapshot bug the fuzz caught on seed 0 and a regression
  test now pins. They do NOT substitute for an independent review of
  novel mechanism design.
- **Do not describe VaultLaunch v4, LaunchDEX v1 or anything later as
  "audited"** in communications, listings or conversations. The honest
  phrasing: "internally audited, machine-checked in CI, no external
  audit yet". Budget an external review before any mainnet deployment
  that carries real value.

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

**The DEX's own threat model (v1.1, founder risk review; updated v1.3).**
The DEX admin can set the swap fee (cap 10%), the trade bounds, the
launchpad pin (before the first pool only), the fee split (bounded
[25%, 75%]) and trigger the global emergency pause. It can NEVER move
pool reserves: `withdraw_fees` is capped by the pending pots AND the
uncommitted balance (IX1/IX2). Since v1.3 the liquidity is two-tier:
**the migrated seed is protocol-locked FOREVER** (its LP parts are
minted to the protocol's position with NO withdrawable balance — even
a fully compromised admin cannot withdraw it), while providers' added
liquidity is withdrawable pro-rata by its owners only
(`remove_liquidity` burns the caller's OWN withdrawable parts,
"locked"; the seed floor is re-asserted belt-and-braces, "seederr").
**Every exit is ungated, absolutely (IX6 + X12)**: the per-pool flag
pauses buys only, and the emergency pause gates buys, pool creation
and liquidity adds ONLY — sells, provider fee claims AND provider
liquidity removes carry NO gate at all. A compromised admin can tax
sellers (fee hard-capped at 10%) but can NEVER trap ANYONE — holders
or providers. `add_liquidity` stays price-neutral (X7/IX7) and so is
`remove_liquidity` (v1.3, IX7 both sides): neither can steer a price —
only swaps move a pool's price. The honest trade-off, documented: the
depth ABOVE the seed floor depends on providers' goodwill and can
shrink back to the floor at any time (a market risk, not a rug — the
floor itself is immutable).

**The founder risk review, closed (v4.1, updated v4.2).** The six
pre-launch risks and their resolutions: (1) one-sided liquidity → X7
ratio fit with same-transaction refund of the excess; (2) emergency
pause trapping holders → sells carry no gate on either venue; (3)
frozen upgrade pins → assumed and documented as the side-by-side
runbook (**docs/UPGRADES.md** — the full procedure, not a note;
LAUNCHPAD.md §5b keeps the summary, `get_launchpad()` exposes the pin);
(4) hardcoded cross-call chunk ids → pinned constants asserted against
BOTH real tables by CI on every push (append-only rule for the DEX);
(5) sybil voting → the D21 refundable-deposit dial (**default 0.5 XEL
since v4.2** — ON from day one, not an opt-in; cap 10 XEL,
`claim_vote_deposit` refunds, pots committed in I2), honest that it
mitigates and does not cure; (6) public deposits → the privacy model
is documented in plain words (LAUNCHPAD.md §5a) — balances are
confidential, attached amounts are public, never promise total
privacy.

## v18.2/v18.3 — providers earn, the seed is locked (LaunchDEX v1.2/v1.3, X10-X12)

**New surface: the provider accounting.** Every swap fee now splits
between the admin pot and the pool's providers (pro-rata of the LP
depth, XEL side). Since v1.3 the anti-rug core is TWO-TIER: the seed
mints LP parts to the protocol (X11 — fees-only, forever) and
providers mint WITHDRAWABLE parts they may burn pro-rata at any time
(X12). Threat notes, plainly:

- The **split dial is hard-bounded [2500, 7500]**: a compromised
  admin can neither zero the providers' revenue nor dump the whole
  fee stream out of the treasury — and it can never touch the
  provider pots themselves (`withdraw_fees` reads the ADMIN pots
  only; `claim_lp_fees` pays the CALLER's own accrued fees, keys
  embed the caller's address, payouts bounded by the pots with
  belt-and-braces `"lperr"` reverts).
- **IX8 (LP solvency) holds by construction, removes included**: each
  accrual increment is `lp_part * ACC_SCALE / tl` with `tl ≥ pl ≥
  ACC_SCALE` (the seed floor guarantees it through removes since
  v1.3 — IX9; before that, the 1 XEL LP-entry floor alone carried
  the bound), so the accrual counter can never outgrow the pool's
  lifetime fees, and payouts are floor-rounded shares — the sum of
  all dues never exceeds the pot. The fuzz asserts this after every
  action, removes included.
- **Fuzz-found, fixed, pinned**: the first deposit of a wallet must
  snapshot the current accrual counters, or it would retroactively
  earn fees from before it existed (more than the pot ever held).
  The 30-seed fuzz caught exactly this (seed 0); the contract, the
  Sim and a dedicated regression test now pin the boundary.
- A deposit **crystallises before its parts join** — new money never
  earns from before it existed, old parts never lose a unit earned.
  Since v1.3 a REMOVE crystallises before its parts leave — an exit
  never forfeits a unit of what the burned parts already earned (the
  claimables survive and `claim_lp_fees` pays them later).
- Since v1.3 the pool always has a provider from birth (the seed), so
  no fee is ever stranded in a beneficiary-less pot; the pre-v1.3
  no-provider redirect to the admin pot remains as defense-in-depth.

## Front-running — an assumed ceiling, documented (not a bug)

The XELIS mempool is public, like every blockchain mempool: a pending
swap can be observed and front-run (sandwich). This is NOT a VaultLaunch
or LaunchDEX defect — it is the platform's transparency model, and these
contracts accept it as a ceiling rather than pretend to solve it. What
the design does about it, honestly:

- **`min_out` slippage protection on EVERY swap** (both venues): a
  sandwiched trade reverts (`"slip"`) instead of silently filling at
  the manipulated price. The CLI quotes (`quote`, `get_amount_out_*`)
  exist to compute a sane `min_out` before you sign.
- **No commit-reveal, no private mempool, no MEV protection of any
  kind** is implemented or claimed.
- Mitigations users can take: set a tight `min_out`, split large
  orders, avoid trading right after visible migrations.
- If XELIS ever ships mempool privacy or batch ordering, the swap
  entries need no change to benefit from it.

## Permissions note for integrators

Transactions that cross-call
(`migrate`, `sync_trust_to_dex`, and the DEX's launchpad-only entries)
must carry the wallet's contract-call permission (XSWD "all" or an
allowlist). The contracts refuse early with `"txperm"` instead of
failing opaquely. Voters and traders NEVER need the permission:
report/support/swap entries make no cross-calls (D17).
