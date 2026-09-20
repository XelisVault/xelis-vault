# VaultLaunch — Design Specification

> contracts/launchpad/VaultLaunch.slx · v1.0.0 · mainnet-ready (testnet first)

A serious launchpad for XEL: real projects are filtered by a community
validation vote, priced by a constant-product bonding curve, and held to a
long-term community trust standard (Trusted / Untrusted). Every fee is
configurable by the admin and 100% of the revenue goes to the admin —
nothing is burned. This is NOT a memecoin casino: the vote window is the
quality filter, the trust system keeps founders accountable forever, and
the curve math is integer-exact and solvent by construction.

One file. Zero inter-contract calls. Zero external dependencies.

---

## 1. Lifecycle

```
                 propose() [fee + seed liquidity]
                        |
                        v
                0 VALIDATION
                (support / report window,
                 ends at validation_end topo)
        pass >= 20 voters AND >= 80%      fail
        |----------------------------------|
        v                                  v
  2 BONDING                        1 REJECTED
  buy / sell live                  claim_refund() -> 100% of the
  votes continue (trust)           founder's liquidity, once
        |
        | reserves >= liquidity x 4 (default)
        v
  3 GRADUATED (+ Trusted)
  team allocation minted to the creator
  trading CONTINUES (the contract is the
  token's permanent venue)
        |
        | reports reach 80% of all votes
        v
  5 UNTRUSTED  <-------------------------------------.
  buys BLOCKED, sells open, votes open                |
        | request_revalidation()                      | fail
        |  - not graduated: free, normal thresholds   |
        |  - graduated: 250 XEL fee, 40 voters, 90%   |
        v                                              |
  6 RECOVERY (new voting round, tallies reset) --------'
        | pass
        v
  2 BONDING (never graduated) or 4 TRUSTED (graduated)
```

Status codes (see `get_status_label`): `0 validation, 1 rejected,
2 bonding, 3 graduated, 4 trusted, 5 untrusted, 6 recovery`.

**Who triggers what.** XELIS has no timers: every transition is
event-driven. Graduation fires inside the `buy()` that crosses the
threshold; trust loss fires inside the vote that crosses the ratio;
window outcomes are applied by `finalize_validation()`, callable by
ANYONE once the deadline passed (the founder has a natural incentive to
finalize a refund, the community to finalize a launch).

## 2. The bonding curve (constant product, integer-exact)

State per project: `R` = real XEL reserves, `C` = curve token supply
(the sellable balance the curve holds). Price = `R / C`.

```
buy  X XEL:   fee   = X * trading_fee_bps / 10000        -> admin (pending)
              net   = X - fee                            -> joins R
              out   = C * net / (R + net)                -> buyer (floored)

sell T tokens: gross = R * T / (C + T)                   -> leaves R (floored)
              fee   = gross * trading_fee_bps / 10000     -> admin (pending)
              out   = gross - fee                         -> seller (checked transfer)
```

Both directions floor in favour of the contract, so rounding can never
make a curve insolvent. All intermediates are computed in u128 (products
reach 1e31; u64 would overflow). Defaults: trading fee 50 bps (0.5%),
hard-capped at 1000 bps (10%) by the setter.

**Worked example.** A founder deposits 1000 XEL with 1B supply and 10%
team: `C = 900M` tokens, `R = 1000 XEL`, opening price ≈ 1.11 µXEL. A
100 XEL buy at 0.5% fee nets 99.5 XEL into `R` → buyer receives ≈
82.6M tokens. Graduation needs `R >= 4000 XEL` (liquidity × 4): net buys
must add ~3000 XEL. At graduation the 100M team tokens are minted to the
creator (they were excluded from `C` from block one, so they can never
be over-sold), and trading simply continues.

**Solvency invariant (I2).** The contract's XEL balance always covers
`Σ curve reserves + pending fees + refundable rejections`. `withdraw_fees`
is double-capped (accrued fees AND uncommitted balance) — the admin can
never touch curve funds, user balances or refunds.

## 3. Design decisions (the important trade-offs)

| # | Decision | Why |
|---|----------|-----|
| D1 | Tokens are an **internal ledger** in this contract | XELIS has no inter-contract calls today; a launched token cannot be a separate contract the launchpad drives. Balances live in `b:{id}:{addr}` keys and trade only against the curve here. Migration becomes possible the day the VM ships cross-calls. |
| D2 | **Graduation does not stop trading** | There is no external DEX to migrate to (D1); freezing the curve would trap holders. The bonding PHASE ends, the milestone is recorded, the same math serves trades forever. |
| D3 | **Team tokens mint at graduation** | The allocation is excluded from the curve's sellable supply from day one (no over-sale possible) but only credited to the creator on graduation. A project that never graduates pays the team nothing — and the founder's liquidity stays locked in the curve. |
| D4 | **Untrusted blocks buys, never sells** | Losing trust must protect new entrants without trapping existing ones. The trust flip can never freeze funds. |
| D5 | **Fees accrue, admin pulls** | Submission + trading + recovery fees accumulate in `pending_fees`; `withdraw_fees()` is the single, capped exit. 100% to the admin, zero burn. |
| D6 | **1 address = 1 vote per round** | The network fee is the only (honest) sybil cost on XELIS today. Votes reset when a new round opens; trust tallies otherwise accumulate for the project's whole life — early supports cushion later reports, early reports are never forgotten. |

## 4. Fees & parameters (all admin-settable, all range-checked)

| Parameter | Default | Hard range | Storage key |
|---|---|---|---|
| submission_fee | 10 XEL | ≤ 100 XEL | `sub` |
| min_liquidity | 500 XEL | [1 XEL, 100k XEL] | `mnl` |
| trading_fee_bps | 50 (0.5%) | ≤ 1000 (10%) | `tfe` |
| min_participants | 20 | [1, 100k] | `mnp` |
| min_approval_ratio_bps | 8000 (80%) | (50%, 100%] | `mab` |
| validation_duration | 51840 topos (~3d) | [~1h, ~15d] | `vdt` |
| graduation_multiplier | 4 | [2, 100] | `gmu` |
| recovery_fee | 250 XEL | ≤ 1000 XEL | `rfe` |
| recovery_min_participants | 40 | [1, 100k] | `rmp` |
| recovery_min_ratio_bps | 9000 (90%) | (50%, 100%] | `rmr` |

Per-project caps (in `propose`): supply in [1, 100M] tokens, team ≤ 20%,
name ≤ 64 chars, symbol ≤ 16, description ≤ 512, website/logo ≤ 256.
Trade caps: buys in [0.01 XEL, 100k XEL] per call.

`set_paused(true)` freezes NEW proposals and NEW buys only — sells,
votes, refunds and finalization are never pausable (exits and community
decisions cannot be frozen).

## 5. Security model (honest threat documentation)

- **Admin is a hot role with a cold wallet's job.** It sets fees and can
  pause new activity, but it can NEVER move curve reserves, token
  balances or refunds: the only XEL exit for the admin is
  `withdraw_fees`, capped twice. Use a dedicated cold address as admin.
- **Sybil resistance = the network fee.** Nothing else. 20 validating
  votes or 80 trust-flip votes each cost a real transaction fee; cheap
  griefing is possible, cheap *validation* of junk is not.
- **Carry-over tallies cut both ways.** Validation supports cushion later
  reports (80% of ALL votes are needed to flip); symmetrically, early
  reports keep counting against recovery. A project's whole voting
  history matters, which is the point of a long-term trust system.
- **Front-running is possible** (public mempool, no batch auctions on
  XELIS today). Quotes (`get_buy_quote`, `get_sell_quote`) are views —
  frontends should display them and let users set expectations. Slippage
  parameters can be added client-side by comparing quote vs expectation
  before broadcasting.
- **No reentrancy surface**: invokes are atomic, no external calls.
- **Unguarded panics**: none reachable with public data — every optional
  load uses a safe default or a guarded `.expect` (linter R4 enforces
  this on every push).

## 6. Events (V6 contract events)

| id | Event | Fields |
|---|---|---|
| 1 | ProjectCreated | id, name, symbol, liquidity |
| 2 | ProjectSupported | id, round, voter |
| 3 | ProjectReported | id, round, voter |
| 4 | ValidationFinished | id, "1"/"0" |
| 5 | BondingOpened | id |
| 6 | TokensBought | id, xel_in, tokens_out, fee |
| 7 | TokensSold | id, tokens_in, xel_out, fee |
| 8 | ProjectGraduated | id, reserves, team_minted |
| 9 | TrustLost | id, reports, supports |
| 10 | TrustRecovered | id |
| 11 | FeesCollected | amount |
| 12 | ParamSet | param, value |
| 13/14 | Paused / Unpaused | "admin" |
| 15 | AdminSet | new_admin |
| 16 | RefundClaimed | id, amount |
| 17 | RecoveryRequested | id, round |
| 18 | ProjectInfoUpdated | id |

## 7. Frontend integration guide

**Project data** — one card needs three view calls:

```
get_project(id)        -> (creator, status, created_topo, deadline, graduated)
get_project_info(id)   -> (name, symbol, description, website, logo)
get_project_tokenomics(id) -> (total_supply, team_bps, liquidity, reserves, curve)
get_current_price(id)  -> XEL*1e8 per token   (divide by 1e8 for display)
get_market_cap(id)     -> atomic XEL          (fmt like XEL amounts)
```

**Listings** — Silex has no array returns (verified against every ABI the
v12 compiler emitted), so listings are count + rank accessors:

```
total   = get_total_projects()
ids     = [get_latest_projects(rank) for rank in range(N)]        # newest first
trusted = [get_trusted_by_rank(rank) for rank in range(get_trusted_projects())]
by_status(n) = [get_project_by_rank(n, rank) for rank in range(get_projects_by_status(n))]
```

Sentinel: an accessor returns `project_count` (an invalid id) when the
rank does not exist. Balances: `get_token_balance(id, address)`;
vote state: `has_voted(id, address)`.

**Direct storage reads** (cheaper for indexers, daemon RPC
`get_contract_data` with string keys):

```
p:{id}:{field}   project fields (cr st nm sy ds ws lg ts tb lq rv cs ct ve sp rp gr rc rd vo)
b:{id}:{addr}    token balance          v:{id}:{round}:{addr}  vote marker
adm pc sub mnl tfe mnp mab vdt gmu rfe rmp rmr pfe fcl tvl tcx lrf pz  globals
```

**Entry points** — invoke by chunk id (see `xvault launchpad entries`):
propose=12, support=13, report=14, finalize_validation=15, buy=16,
sell=17, claim_refund=18, request_revalidation=19, update_project_info=20,
admin setters 21-31, withdraw_fees=32. Buys attach XEL via the invoke
deposit; sells take `(pid, token_amount)` and pay out to the caller.

## 8. CLI

```bash
pip install ./sdk/xvault

xvault launchpad status --contract <hash> --network testnet
xvault launchpad project --contract <hash> --id 0 --owner xel:...
xvault launchpad quote --reserves 500 --curve 90000000 --buy 100 --sell 1000000
xvault launchpad propose --name "Real Project" --symbol RPR --supply 1000000 \
    --team-bps 1000 --liquidity 500 --contract <hash> --network testnet
xvault launchpad entries
```

The CLI never holds keys: `--broadcast` sends through the local wallet
RPC (xelis_wallet --rpc-server), exactly like the mixer commands.

## 9. Deployment checklist

1. **Testnet first.** Deploy, propose a throwaway project, run the full
   lifecycle (vote → finalize → buy → graduate → trust loss → recovery),
   verify every event and storage key with `xvault launchpad project`.
2. **Admin = cold wallet.** The deployer is the admin; move it to a
   dedicated cold address with `set_admin` right after deployment.
3. **Sanity params** before the first real proposal: review
   `get_config()` against §4; the defaults are conservative.
4. **Probe the entry ids** on testnet (`invoke` with `xvault` and
   confirm the chunk numbering the VM expects — the ALT table exists in
   the SDK for exactly this).
5. **Mainnet**: deploy, `set_admin` to the cold wallet, announce the
   contract hash, list the first serious project. The submission fee and
   min liquidity gate spam; the vote window gates quality.
6. **Revenue**: `withdraw_fees` at will — it can never exceed the
   uncommitted balance, depositors and holders always come first.
