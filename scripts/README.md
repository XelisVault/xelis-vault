# CI tools — XelisVault protocol

These scripts are the four quality gates of the `strict-ci` GitHub Actions
workflow (`.github/workflows/ci.yml`). They run on every push and pull
request on `main`; any BLOCKER/ERROR or FAIL fails the build. All of them are
plain Python 3.12 with zero dependencies so they also run locally:

```bash
python3 scripts/lint_silex.py --contracts contracts --json reports/lint-report.json
python3 scripts/verify_chunk_ids.py --contracts contracts
python3 scripts/check_structure.py
python3 -m pytest tests -v
```

## lint_silex.py — strict Silex static linter

Static security linter for `.slx` contracts that encodes every dangerous
pattern found by the v12 audit as a rule with a severity (R1–R10: swallowed
transfer failures `let _ = transfer`, fire-and-forget transfers,
`execute_emergency_withdraw` rug switches and whole-balance transfers to the
caller, unguarded `.expect()`/`.unwrap()` panics (guarded = a
require/is_some check within the 3 preceding lines; constructor occurrences
are tolerated as deployment data), 68-hex-char literals (34-byte addresses),
`unwrap_or(Hash::zero())` used as a transfer/destination fallback, public
entries that write storage without an access guard, loops without a static
bound, stale function-number comments, and dead private functions). It prints
a readable console report and (with `--json`) a machine-readable report that
CI uploads as an artifact; exit code is non-zero when any BLOCKER/ERROR is
found. `--scan-legacy PATH` is a non-CI validation mode that runs the same
rules on the archived v12 contracts to prove the linter still catches the
audited bugs (e.g. it flags `let _ = transfer_contract(...)` at line 244 and
the unverified `transfer(caller, bal, asset)` of `execute_emergency_withdraw`
at line 392 of `legacy/contracts/privacy/PrivacyMixer.slx`).

## verify_chunk_ids.py — XELIS chunk-ID verifier

Verifies the XELIS entry-point numbering: `hook constructor` is chunk 0 and
every function (`fn`, `entry`, `pub fn`) takes the next chunk ID in source
declaration order (validated 51/51 against the compiler-emitted
`legacy/build/chunkmap_*.txt`). For each active contract it checks that the
CHUNK TABLE documented in the header matches the real declaration order
exactly, regenerates the table for easy copy-paste, and detects
inter-contract calls (`Contract::new` / `.call(Nu16, ...)` / `.delegate`):
for `contracts/mixer/` the invariant is **zero** inter-contract calls (the
mixer is deliberately self-contained — any cross-call is a BLOCKER), and the
report explicitly affirms "0 inter-contract calls" when the invariant holds.
`--validate-legacy` re-checks the numbering rule against the compiled
chunkmaps (dev tool, not a CI gate).

## check_structure.py — repo structure & hygiene gate

Enforces the v13 repository layout: `contracts/` may only contain `.slx`
files under `contracts/mixer/`; no active script may `import` the archived
`legacy/` package or put it on `sys.path` (reading legacy files as data, like
the linter's `--scan-legacy` mode, is fine); no secrets in active files
(GitHub PATs `github_pat_…`/`ghp_…`, API keys `sk-…`, `BEGIN … PRIVATE KEY`
blocks — patterns are length-checked so documentation mentions don't
self-trigger, and a hit is a hard FAIL); and no binary blobs larger than 5 MB
outside `legacy/` (v13 removed 29 MB of `.exe` from git). Exit code is
non-zero on any violation.

## silex_parse.py — shared parser (not a CI gate)

The single lightweight Silex parser used by both `lint_silex.py` and
`verify_chunk_ids.py`: masks comments/strings (preserving offsets), extracts
functions with their spans and kinds (`hook`/`fn`/`entry`/`pub_fn`),
constants, string literals, and provides call/argument/assignment scanning
helpers. Both CI tools MUST share this module so they can never disagree
about what a function (and therefore a chunk ID) is.

## tests/ — pytest suite

`tests/test_ci_sanity.py` is the permanent placeholder that keeps the pytest
job meaningful while the functional suite grows: it asserts the active
contract exists, is more than 500 lines, and documents its CHUNK TABLE.

## verify_pass3_math.py — the v18.4 independent math re-derivation (one-shot)

Re-derives CommunityLaunch's virtual-reserve curve math from the SPEC
(docs/COMMUNITY_LAUNCH.md §3) WITHOUT importing the SDK or the test
helpers, then checks it against the contract source text and
brute-forces it: 200 random (vx, y0, gdx) regimes x 250 random trades
asserting k never decreases, real reserves stay non-negative, the
whale guard bounds buys and the worst-case sell is exactly covered
(IC3/IC4); plus the graduation economics at the defaults (launch FDV
50 XEL, graduation at ~2/3 sold / ~3x FDV, pool opens >= spot) and the
2-XEL unit economics. Run: `python3 scripts/verify_pass3_math.py`.

## verify_pass4_parity.py — the v18.4 cross-contract parity check (one-shot)

Machine-checks the cross-contract protocol end to end: the pinned
chunks (create_pool=6, set_pool_buys_paused=7, create_pool_open=33)
against the DEX's real declaration order on BOTH callers, the call
signature and deposit protocol (what the factory sends IS the seed,
fee carved before the deposits are built), the v1.4 return-value
convention (both endpoints return 0, both callers require 0), and the
three-way ABI agreement (contract chunk tables <-> SDK dicts <->
abi/*.json, param names included). Run:
`python3 scripts/verify_pass4_parity.py`.
