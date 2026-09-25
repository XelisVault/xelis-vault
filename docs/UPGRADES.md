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
[ ] pinned chunks (6/7/33) unchanged OR all sides updated + tests green
[ ] before ANY admin rotation: claim_lp_fees on the seed position of
    every live pool (the parts stay with their owner at creation, X11)
[ ] testnet lifecycle: full pass, provider fees claimed, pins frozen
[ ] versions consistent (contract / VERSION / docs / SDK / doc-parity)
[ ] CHANGELOG + announcement draft ready
[ ] mainnet addresses recorded, pins verified frozen after cross-pin
[ ] site generation registry updated
```

## 6. The v18.4 cut — one new DEX generation for BOTH tracks, and the gen-1 repin

The v1.4 generation (LaunchDEX v1.4 + CommunityLaunch v1.0) is cut per
§3 above, with ONE addition made possible by the fact that the gen-1
mainnet pair has created **no pool yet** (its pins froze at nothing):

1. **Deploy LaunchDEX v1.4** (testnet rehearsal first, always). This
   generation fixes the SECOND-MIGRATION BUG: gen-1's `create_pool`
   returns the pool's INDEX, and VaultLaunch's `migrate_to_dex` treats
   a non-zero cross-call result as failure ("poolerr") — only the
   FIRST project migration would ever have succeeded against a gen-1
   DEX. v1.4 chunks return 0 on success; the interface is unchanged
   (VaultLaunch v4.2 calls it byte-identically).
2. **Repin the gen-1 launchpad** (still possible while `dxa` is
   unfrozen — i.e. while IT has never migrated anything): invoke
   `set_dex_address` (entry 50) on the gen-1 VaultLaunch with the v1.4
   DEX's hash. The project track now migrates into the fixed DEX —
   every migration works, not just the first.
3. **Set the v1.4 DEX's launchpad pin** to the official wallet: it
   gates ONLY the moderation hook (`set_pool_buys_paused`, chunk 7 —
   pause a malicious pool's BUYS; sells never) and `create_pool`. It
   freezes at the first pool, whichever path created it.
4. **Deploy CommunityLaunch** and pin its `set_dex_address` to the
   same v1.4 DEX. The community track migrates through
   `create_pool_open` (chunk 33, permissionless — X13): no pinned
   signer can become a graduation bottleneck.
5. **The orphaned gen-1 DEX** (`bce37bde…`) simply never serves a
   pool. It keeps existing forever (honest cost of the fix); the
   golden-rule addresses in COMMUNITY.md must be updated to the new
   generation pair before the community interacts with either track.

The result: ONE DEX lineage serves both tracks — launchpad-pinned
`create_pool` for the projects, open `create_pool_open` for the
community coins — and the site's generation registry lists the new
pair alongside gen-1 (the stateless views enumerate everything;
LAUNCHPAD.md §7a).
