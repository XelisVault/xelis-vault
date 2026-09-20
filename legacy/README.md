# LEGACY ARCHIVE — v12 contracts (DO NOT DEPLOY)

This directory archives the complete v12 codebase: 51 Silex contracts plus
their build artifacts, scripts, deployment tooling and documentation.

## Status: NOT DEPLOYABLE

A full audit (September 2026) found the v12 stack unsafe, including but not
limited to:

- transfers paid from shared contract balances without collecting the
  user's deposit (trivial drains in chat/miner/lending/auction stacks)
- 91 swallowed transfer failures (`let _ = transfer(...)`) across 22
  contracts
- a global DoS triggerable by anyone through miner deregistration
- reward pools with accounting-only distributions (promises with no funds)
- ~100 privileged entries all initialized to the deployer, single-step
  admin transfer everywhere, and 15 single-key emergency-withdraw switches
- oracle slash-all deviation logic and a `PrivacyMixer` whose withdrawal
  revealed the note secret in clear parameters

Machine-checkable report:

```bash
python3 scripts/lint_silex.py --scan-legacy   # 1316 blocker/error findings
```

## Why keep it?

1. It is the regression corpus for the CI security rules — the linter must
   keep detecting every one of these patterns.
2. Several ideas (miner bonding, lazy reward settlement, sealed-bid
   auctions, delegation indexing) are worth re-implementing under the v13
   bar: single-contract, lint-clean, threat-model-documented.
3. History. Nothing here is deleted; nothing here is trusted.

The v13 production tree lives at the repository root. See
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the consolidation
plan.
