# UPGRADES — the generation runbook

> Why a runbook and not an upgrade path: both the launchpad pin (X4) and
> the DEX address pin (D19) FREEZE the moment the first pool exists. This
> is not an accident — a repinned venue could orphan every live pool. The
> consequence is honest and must be said plainly: **contracts are never
> upgraded in place. A new version of VaultLaunch or LaunchDEX is a NEW
> DEPLOYMENT (a new generation), and the old generation keeps serving its
> users forever.** This document is the exact procedure, not a note.

---

## 1. The generation model

A **generation** is a (VaultLaunch, LaunchDEX) pair bound by two pins:

1. `LaunchDEX.set_launchpad(launchpad_addr)` — only the pinned launchpad
   can call `create_pool` / `set_pool_buys_paused`. Freezes at the FIRST
   pool created on that DEX (X4).
2. `VaultLaunch.set_dex_address(dex_addr)` — only the pinned DEX can
   receive migrations. Freezes at the FIRST migration (D19).

Once both are frozen, the pair is immutable in its relationship. Pools
seeded into generation N live on generation N's DEX **for the lifetime of
the chain** — there is no remove_liquidity, so their liquidity never
moves either. That is the anti-rug guarantee, and it is also why
upgrades are generational: you cannot retarget live value, only serve it
where it lives.

**What carries over across generations (by design):** nothing on-chain —
each generation is self-contained. The **site** bridges generations
(stateless, LAUNCHPAD.md §7a): it reads every generation's views, maps
asset hashes back to projects (`get_project_by_asset` on each launchpad
generation), and lists migrated projects across generations
(`get_migrated_by_rank` on each launchpad generation). The user
experience is one continuous marketplace; the contracts underneath are
disjoint universes.

## 2. When to cut a new generation

Cut a new generation when a change is **not expressible** in the current
one. Everything parameter-like (fees, thresholds, bounds, the vote
deposit, the LP fee split) is admin-settable in place — no generation
needed. A new generation is required only for: new entries or views,
changed signatures, changed storage layout, changed entry ids of pinned
chunks, or protocol-level behavior changes.

Before cutting one, ask twice: (a) is the current generation actually
broken, or merely imperfect? (b) does the fix survive a fresh deployment
testnet pass? Every generation adds permanent on-chain surface; unused
generations still exist forever.

## 3. The procedure (step by step)

**Phase 0 — freeze the candidate (repo, no chain yet)**

1. All gates green on `main`: linter 0/0/0, full pytest suite, the five
   formal audits (spec traceability, security, SDK parity, doc parity,
   fuzz), `verify_chunk_ids`, `regen_sdk_entry_ids --check`,
   `check_structure`.
2. Version strings bumped consistently (contract, `VERSION` file, docs,
   SDK) and the doc-parity audit passes on the new versions.
3. CHANGELOG entry written: what changed, what the new generation fixes,
   what stays identical.
4. If pinned chunks moved (`DEX_CREATE_POOL_CHUNK` /
   `DEX_SET_PAUSED_CHUNK`): the cross-pin tests already fail the build —
   fix the constants on BOTH sides before anything else.

**Phase 1 — testnet rehearsal (always, no exception)**

5. Deploy the NEW LaunchDEX to testnet. Record its address.
6. Deploy the NEW VaultLaunch to testnet. Record its address.
7. Cross-pin them: `set_launchpad(<new launchpad>)` on the new DEX,
   `set_dex_address(<new dex>)` on the new launchpad.
8. Run the FULL lifecycle on testnet with the CLI: propose → validate
   (with the vote deposit paid and refunded) → bond → graduate → migrate
   → trade on the pool → add liquidity → **claim provider fees** → trust
   flip → recovery. Every step checked against the views (`status`,
   `project`, `dex pool`, `dex lp`).
9. Verify both pins FROZE (a second `set_launchpad` / `set_dex_address`
   must refuse with `"pinned"` / `"frozen"`).
10. Let it soak. Duration is a founder call; days, not minutes.

**Phase 2 — mainnet cut**

11. Announce the generation: addresses, what it fixes, the fact that
    current generations keep working unchanged. No forced migration —
    nothing CAN be force-migrated.
12. Deploy the new LaunchDEX to mainnet. Verify `get_launchpad()`
    reports `unset / not frozen`.
13. Deploy the new VaultLaunch to mainnet. Verify `get_dex_address` /
    `get_migration_info` report the DEX unset.
14. Cross-pin exactly like Phase 1 (steps 7–9), then re-run the CLI
    checks against mainnet (read-only: `status`, `entries`).
15. New projects propose on the new generation. The community decides
    where to launch; the old generation stays open for its own projects.

**Phase 3 — the site**

16. Add the new generation to the site's generation registry (a static
    config: both contract addresses per network). Nothing else — the
    stateless contract (LAUNCHPAD.md §7a) already enumerates everything
    through views.
17. Verify cross-generation rendering: old-generation projects show
    their pools and stats exactly as before; new-generation projects
    appear on the same listing pages.

## 4. The worst case: a critical bug on a live generation

There is **no code push**. The options, in order of preference:

- **Parameter containment** — if the bug can be blunted with a dial
  (fees, bounds, vote deposit, LP split), turn the dial. Parameters are
  live on frozen generations; that is what they are for.
- **Emergency pause** — `set_paused(true)` on the DEX freezes buys,
  pool creation and liquidity adds. It CANNOT freeze sells (IX6): every
  holder can always exit at market price. That is deliberate — a
  compromised or buggy pause must never become a trap. The launchpad has
  its own `set_paused` (freezing NEW activity only; existing curve sells
  and refunds keep working).
- **New generation** — if the bug is in the logic itself, cut the next
  generation per §3 and migrate the COMMUNITY, not the pools: announce,
  explain, let new projects launch on the fixed pair. Old pools keep
  trading; the bug stays bounded to what it already touched.

What never happens: a drain of old pools (no remove_liquidity exists on
any generation), a frozen exit (sells are ungated on every generation),
or a silent retarget of live value (pins are one-way doors).

## 5. Pre-deployment checklist (one page)

```
[ ] all CI gates green on the commit being deployed
[ ] pinned chunks (6/7) unchanged OR both sides updated + tests green
[ ] before ANY admin rotation: claim_lp_fees on the seed position of
    every live pool (the parts stay with their owner at creation, X11)
[ ] testnet lifecycle: full pass, provider fees claimed, pins frozen
[ ] versions consistent (contract / VERSION / docs / SDK / doc-parity)
[ ] CHANGELOG + announcement draft ready
[ ] mainnet addresses recorded, pins verified frozen after cross-pin
[ ] site generation registry updated
```
