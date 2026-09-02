# Testnet Deployment Record

Live deployment state on XELIS **testnet** (block_version 6, V0/V1 contracts; daemon v1.25.0).

Operator: `xet:czr9q8k5xlzqdptq7n2vapyjfduldts6tw3e6apl99vknzvmu4zsq8z9j8v`
All contracts deployed as **V1** (version byte `01` embedded in module hex by the compile tool).

> Entry IDs for invokes = **compiled chunk indices** (see `docs/entry_chunk_ids.json`),
> NOT the source-order IDs listed in `docs/ENTRY_IDS.md`.

## Phase 1 — Registry + Compliance

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 1.1 | Deploy ContractRegistry | `840b810c32f24b516ba5d65accef8cb706355e076a2c41ea98f2afce009f1a14` | ✅ deployed, ctor ok (admin/emergency stored, count 0) | 150714 |
| 1.2 | Deploy ComplianceModule | `7d20ea3646e5c308b9153353f68c24e8f161bc43392f092ea138a5498f132f78` | ✅ deployed, ctor ok | — |
| 1.3 | ComplianceModule.set_registry (entry chunk 14, reg = registry hash) | `ec493026ea1e8a1486368b2c49d8d6daf63f5e7b332e78fe9ecc94b9021d9794` | ✅ stored `reg` = registry hash | 150758 |

> Note: an earlier invoke used entry 9 (wrong chunk) → runtime error `notverifier`, no state change.
> Chunk indices are the source of truth for `entry_id`.

## Phase 2 — Token Layer

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 2.1a | Deploy VLTToken | `efd53bfa46d9fbb7494cca716cd86990299851705d408fcbff0e05d00bb09ac6` | ✅ deployed | — |
| 2.1b | VLTToken.create_asset (chunk 9, +10 XEL deposit, 1 XEL burned) | `f581ff769d284f1f7ffaf80b6de8797027d244e822a967d722b621eebb99f1f9` | ✅ **VLT asset = `9d074e1b0c057dbd30897f10117e4feb1d8d6442306bc23ac763c87c9f73b89a`** | 150808 |
| 2.1c | VLTToken.set_registry (chunk 10) | `c93b6d36b01f5c6d06f355ff29dd0ac042fb9ba3ae992b566fa1c3833aaf58cf` | ✅ | 150811 |
| 2.1d | Registry.register "VLTToken" (chunk 3) | `5f45d3c72a6a2c2328446ddb6e852cb8c2b5694ac49630b39c345d5ee2dc8e0d` | ✅ `cur_VLTToken` stored, count=1 | 150812 |
| 2.1e | VLTToken.mint_to_entry (chunk 27): **500,000 VLT (airdrop share) → admin wallet** | `0826f873fb2177deeeac15f3bb8b82d819b5114559b4f702490f7c26c9a65e56` | ✅ admin holds 50,000,000,000,000 atomic; distribution left to operator | 150825 |
| 2.2a | Deploy xUSD | `87242c12262bf4d7144842a06e91d96af53e5ce5b786e10ccb5c687be4658ae8` | ✅ deployed | — |
| 2.2b | xUSD.create_asset (chunk 2, +10 XEL deposit, 1 XEL burned) | `e0b124a5a42914e3e0285f813df91005c4ce1bfd2bc4064f2f5df58c2e95ccfa` | ✅ **xUSD asset = `a04b10a46698c97f3e465882dee5827e62360c30060f33f3604179769bc65100`** | 150842 |
| 2.2c | xUSD.set_registry (chunk 20) | `863f6bc415783406e85e169ebea2e3c78fa06e5ccdd365a36098e87bebb32f4f` | ✅ | 150845 |
| 2.2d | Registry.register "xUSD" (chunk 3) | `97830346f1032ed2517aac7e96471f38b979fef671086af3e0c66d4e0e48fe51` | ✅ `cur_xUSD` stored, count=2 | 150848 |
| 2.3a | Deploy FaucetContract | `7da83d17c4db825083b4ae85ab95ff50654999ebf4847e284bcf11549f14256d` | ✅ deployed | — |
| 2.3b | Faucet.set_registry (chunk 14) | `9f6475eb02c90472eb2e17ec329342d7474d55eefe6b64e2b2e6abf21c156553` | ✅ | 150859 |

> VLT distribution note (operator decision): testnet airdrop contract skipped — the full 500k VLT
> airdrop share is minted to the admin wallet for manual distribution.
> Faucet refill deferred (operator-controlled VLT; refill later if desired).

## Phase 3 — Mining & Oracle

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 3.1a | Deploy XelisVaultMiner | `0dc49c50dabf9c97ee2efaa76d17013922a89855f63233821ed6d4c445505cbf` | ✅ | — |
| 3.1b | Miner.set_registry / set_vlt_contract / set_vlt_asset (chunks 44/40/41) | `5489960b…` `31c9c3d3…` `ea8f243b…` | ✅ verified | 150903-150909 |
| 3.1c | Registry.register "XelisVaultMiner" | `a3e724d0cf1a46a0abdf45e75e8ea981cb816b5f8346a86ef2929735556dd6c4` | ✅ | 150910 |
| 3.2a | Deploy StakedOracle **v2** (added `add_feed_entry` wrapper — pub fn chunks are not externally invokable; v1 `c60dea03…` discarded, nothing referenced it) | `68435e505623b3cc4dbfd4d1c23191889f0970df82c3e184db36983dfadd394c` | ✅ | — |
| 3.2b | Oracle.set_registry / set_miner_contract (chunks 46/44) | `c250143d…` `72d05980…` | ✅ | 150960-150961 |
| 3.2c | Oracle.add_feed_entry (chunk 10): "XEL/USD", asset=zero, decimals=8, min=1, max=1e11 | `a6da6cee5bf7fc459aab6f8d5099e870c03993f10f906e25a91d17edc61eee1c` | ✅ feed 0 stored | 150965 |
| 3.2d | Registry.register "StakedOracle" | `b5f8c2bc3ca99c75898bcdb0092983ba229a33ae8838969e48907bde7c129d58` | ✅ | 150966 |
| 3.2e | Miner.register_service (chunk 31): service_id=1 → oracle | `a8b5227e8d5d5bf038074a2c85c57625ee9b8db9fe3ce03d44eb813ee1e12c77` | ✅ `svc_<oracle>=1` | 150970 |
| 3.3a | Deploy MinerPool | `86895d2f16fc293f3e29234b9daa6a0482be4a061e76265af049baa13e9bd275` | ✅ | — |
| 3.3b | MinerPool.set_registry / set_miner_contract / set_vlt_asset (chunks 27/25/26) | `5185bacd…` `4ac12cc0…` `2e705faa…` | ✅ verified | 150976-150980 |
| 3.3c | Registry.register "MinerPool" | `b48dae9de1674bfada944e6275ca819f6f2b3ee900d810c2bdf444565917e144` | ✅ | 150984 |

> Guide corrections applied (v11.x sources): `add_feed` → `add_feed_entry` wrapper added to
> StakedOracle (chunk 10); `set_authorized_service` → `register_service` (chunk 31).
> Registry count: 5.

## Phase 4 — Lending Core

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 4.1a | Deploy InterestRateModel | `172214c5d10f967f73e3c12832b74a6b17ce05aa9d656936ce4be0d1fbd6e2de` | ✅ | — |
| 4.1b | IRM.set_rates (chunk 10): base=50, multiplier=1000, jump=5000, kink=8000 | `f77f9e3992d2b34b36c3f4557d244ee8388a7f2951e366a80d4c40cc205c27d1` | ✅ | 150988 |
| 4.1c | Registry.register "InterestRateModel" | `ed6d1ab019e290bf2572367d1dd419c315a0a936b230e988e769abb37978707c` | ✅ | 150994 |
| 4.2a | Deploy VaultEngineV3 | `1a818effa8a4eb5bac9ed4675e1be8abe93d438cc14d6297635bbeb75e471a53` | ✅ | — |
| 4.2b | VE.set_registry / set_xusd_contract / set_xusd_asset (chunks 40/41/42) | `f0758c00…` `c6dc8e44…` `d50ccfe9…` | ✅ verified | 151004-151008 |
| 4.2c | VE.set_treasury (chunk 43) — **temp = admin wallet** (TreasuryVault arrives Phase 8; mutable via set_treasury) | `e8046723…` | ✅ | 151013 |
| 4.2d | Registry.register "VaultEngine" | `61e05447988d41ffd347dca7e84a04506ef77113baa0bf74d1a57a91b5c0e742` | ✅ | 151016 |
| 4.2e | xUSD.set_minter / set_burner → VaultEngine (chunks 18/19) | `ab3d5d30…` `655c9240…` | ✅ `mi_`/`bu_` = true | 151017-151020 |
| 4.3a | Deploy SavingsRate | `a275a8e2cc97db7d5fb519c5d9a952fcaa9c36e55a5870339b468c7acc68c043` | ✅ | — |
| 4.3b | Savings.set_registry / set_xusd_contract / set_xusd_asset (chunks 17/14/15) | `d76557f6…` `f996b572…` `ef5a99c2…` | ✅ | 151036-151040 |
| 4.3c | Savings.set_treasury (chunk 16, temp=admin) | `38bcbcdb…` | ✅ | 151042 |
| 4.3d | xUSD.set_minter → SavingsRate | `76c3e250…` | ✅ `mi_`=true | 151048 |
| 4.3e | Registry.register "SavingsRate" | `014dc32aa2a91f317eb816269ec8eb6a1b1665ab75f8521ad729536480e487b3` | ✅ | 151050 |
| 4.4a | Deploy FlashCallback / FlashLoan | `f151220561b7d956fbd32b236111b6fc6c152c6a1d384c94b8bd5ea4fc76ea60` / `7dcbf096f4d6f30366316e38736eb75124a9b8054624a974d4cadae7f5edf729` | ✅ | — |
| 4.4b | FlashLoan.set_registry / set_treasury (chunks 14/13) | `75562737…` `34d785d2…` | ✅ | 151058-151062 |
| 4.4c | FlashLoan.verify_callback → FlashCallback (chunk 23) | `64c077dd…` | ✅ `vcb_`=true | 151068 |
| 4.4d | Registry.register "FlashLoan" / "FlashCallback" | `19a4452a…` `22d3c0f1…` | ✅ | 151069-151072 |

> Treasury is temporarily the admin wallet for VE/Savings/FlashLoan — swap to TreasuryVault when it deploys (Phase 8).
> Registry count: 10.

## Phase 5 — AMM

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 5.1a | **Patched VaultSwapV2**: added `set_oracle` entry (it had none — `set_registry` wrongly wrote the oracle key); fixed PSM-price calls 21→32 (`get_price_for_asset_entry` chunk in StakedOracle; 21 is the pub-fn `get_price(String)` → param mismatch revert). Same 21→32 fix in PSM. | `03d3adea88c15e41105814f3f67e58f2036f593ea96a307bfbf5336356f5782a` | ✅ | — |
| 5.1b | VS.set_registry(36) / set_oracle(37) / set_xusd_asset(38) / set_xusd_contract(39) / set_treasury(40, temp=admin) | `9a3db6e3…` `894c5a54…` `f76c2431…` `d60e4753…` `6c3fdbad…` | ✅ verified | 151210-151225 |
| 5.1c | xUSD.set_minter / set_burner → VaultSwap | `d3024130…` `0d37d201…` | ✅ | 151226-151231 |
| 5.1d | Registry.register "VaultSwap" | `38a729bbbf8bbc60026c1197bc10dd8c319c51b40f58998ffeb4f6bfe7965603` | ✅ | 151233 |
| 5.2a | Deploy PSM | `fb8609b547e52e1364776457d88ba9b3a84d80ecf60d28ac34700626c2d7c0a6` | ✅ | — |
| 5.2b | PSM.set_registry(25) / set_oracle(23) / set_xusd_contract(21) / set_xusd_asset(22) / set_treasury(24, temp=admin) | `5a21026d…` `d40b191e…` `e718edc2…` `09642f0c…` `56487b90…` | ✅ verified | 151237-151246 |
| 5.2c | xUSD.set_minter / set_burner → PSM | `df4838b8…` `7f14c096…` | ✅ | 151249-151254 |
| 5.2d | Registry.register "PSM" | `d0f55a7cdb8776358e9b8d076da68fe0cdaeeaf78defba26a7e000c2757a66db` | ✅ | 151257 |

> Both AMM oracle calls now target StakedOracle chunk 32 `get_price_for_asset_entry(Hash::zero())` = XEL/USD feed price.
> Registry count: 12.

## Cross-contract call audit (v11.3 fix pass)

Repo-wide audit of every hardcoded `.call(Nu16, ...)` against current compiled chunk layouts
found 25 stale/incorrect targets (All/pub-fn chunks ARE callable cross-contract — only the id
and param shape matter). Fixed in: LendingMarket (oracle 21→32, IRM 11→3 / 12→5), SyndicatePool
(21→32), VaultEngineV3 (21→32), VaultChat (22→23 + u8), StakedOracle (23→24, 22→23, 23→22,
67→12; u64→u8 service ids), OracleGovernance (add/remove/param/reward/emergency-cb/reset/
slash/stake/freeze/ban ids), GuardianMultisig (pause 33→34, unpause via timelock 12→34u16,
trigger 11→12). GuardianMultisig action 3 (custom call → hook 0) is still broken by design —
struct lacks an entry_id field; documented, not reachable in normal flow.

## Phase 6 — Lending Markets

| Step | Contract / Action | Address (tx hash) | Status | Topoheight |
|------|-------------------|-------------------|--------|-----------|
| 6.1a | Deploy LendingMarket (patched) | `74809c24efbb2817589a6d379922a3e92650857d447f7917905a1514293f1519` | ✅ | — |
| 6.1b | LM.set_registry(31) / set_oracle(29) / set_treasury(30, temp=admin) | `7ab92bac…` `53c9809e…` `ce05c78f…` | ✅ verified | 151505-151516 |
| 6.1c | Registry.register "LendingMarket" | `6cca271c8ab5a149cdcc7d2e60623555db0a8285a3abbfb794e5a21ee7e3652c` | ✅ | 151517 |
| 6.2a | Deploy PeerLoan | `39de766f32a9d297fc99eaf0c7ddefafc5b2785b4b78fd63d3a0f170e4dec485` | ✅ | — |
| 6.2b | PL.set_registry(17) / set_oracle(15) / set_treasury(16, temp=admin) | `a35e5ff1…` `5b9c532d…` `158613c1…` | ✅ | 151524-151530 |
| 6.2c | Registry.register "PeerLoan" | `133ebaa55baf962d1796a8d5a6721aa343960202002bdf96edf02d52e6e96911` | ✅ | 151531 |
| 6.3a | Deploy SyndicatePool (patched) | `6ac66dfa4407b7a126b223e0ba4d2159f423a4806bf3031d6a9c32742d26258a` | ✅ | — |
| 6.3b | SP.set_registry(21) / set_oracle(19) / set_treasury(20, temp=admin) | `53d44738…` `c9262361…` `51643694…` | ✅ | 151544-151550 |
| 6.3c | Registry.register "SyndicatePool" | `b9d77d79d2cf536aa52dca00718caf804cd8986960b9316702fc6c1232f724cc` | ✅ | 151557 |

> Registry count: 15. VaultEngine was redeployed as v2 (oracle 21→32 fix); register is
> one-way ("exists"), registry upgrade has a 720-block cooldown → **upgrade pending at
> topoheight ≥ 151736** (old `1a818eff…` still live until then; v2 `2c22a613…` fully configured).

## Phase 7 — Auctions & Privacy

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 7.1a | Deploy SealedBidAuction | `d3b48725a4a4327249130efb3405be80b6caadbe255db00b3bbb4b1d91be3155` | ✅ |
| 7.1b | Auction.set_registry (25) | `1c0b5dac95c8da6810a9c8c20746cbae70987e5d6d4ec568a01dd61ef3cf2a73` | ✅ |
| 7.1c | Registry.register "SealedBidAuction" | `75992ef4626ecac5cffa1ea518592b949110f0456989a08e9a99c7bf77637351` | ✅ |
| 7.2a | Deploy PrivacyMixer | `c78b2e903f366519884533d75c67428521f8397af02110f2a4fe4f90bfadb79d` | ✅ |
| 7.2b | Mixer.set_registry (20) | `8516b6446a648378b08a880d1ea018a3e32438d2a948d5aca267e0ba9b5bbb35` | ✅ |
| 7.2c | Registry.register "PrivacyMixer" | `549e79fbe72e8d847eb7752e2953941aa5842c289dab67fbbe48f4cc0fcf22e9` | ✅ |

## Phase 8 — Tokenization & Treasury

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 8.1a | Deploy AssetVault | `48806089766985050a81917bcfdf919dcd27df9780bcb6a16faa8e28bd06dd2b` | ✅ |
| 8.1b | AV.set_registry (10) / set_compliance (9) | `e3ed94f6…` `b27525da…` | ✅ |
| 8.1c | Registry.register "AssetVault" | `880ffa42387530e503f8267c7d4cfd1ea1cf75647060cbcb08dd65afe251c9b1` | ✅ |
| 8.2a | Deploy TreasuryVault (no set_registry; admin/signer/quorum=1 by ctor) | `0b2cf9761ebc8a746e4418b80fdfaef0e940f12891deef12e65b60df304c6d70` | ✅ |
| 8.2b | Registry.register "TreasuryVault" | `85937c22368a6b6230c06a803f94e723bf141282f1ee45ba7f0dba1305b9770f` | ✅ |
| 8.3a | Deploy RevenueShare | `beb733d651e682ab7023ca1ae41963837c5d80af6894343657051b29ac9eaa6c` | ✅ |
| 8.3b | RS.set_registry (10) / set_share_token VLT (8) | `c6039086…` `b9a2c79c…` | ✅ |
| 8.3c | Registry.register "RevenueShare" | `c978db7bb533716f3217b64a960d1cf798aad5f8819bcc6e2653c3cdc398f33e` | ✅ |
| 8.4a | Deploy Payroll | `edbfb5fd0a105aaf087b8bf7f0133bd99da6ac36b83b071780eac56e0df42771` | ✅ |
| 8.4b | Payroll.set_registry (9) / set_treasury (8, temp=admin) | `58dd4768…` `4cc5f579…` | ✅ |
| 8.4c | Registry.register "Payroll" | `226e9cd19b0c98f98b0c0514f4401d81750e52ae95671cc838863c473d1d24f2` | ✅ |

> Treasury redirect step NOT APPLICABLE: all set_treasury take Address; TreasuryVault is a
> contract (Hash). Fees stay on temp admin wallet until a future mechanism (RevenueShare).

## Registry upgrades (cooldown 720 blocks)

| Name | New hash | Old hash (prev_) | Status |
|------|----------|------------------|--------|
| VaultEngine | `2c22a613…` (v2, oracle 21→32 fix) | `1a818eff…` (v1) | ✅ `93feec25…` @151759 (first attempt @151733 reverted cooldown) |
| StakedOracle | `159594c8…` (v3, miner-call fixes) | `68435e…` (v2) | ✅ `e2827d2c…` @151775 |

## StakedOracle v3 migration (after upgrade)

- set_registry (46) `23ae5c1b…`; set_miner_contract (44) `9f95092a…` then corrected `94827a2b…`
  (⚠️ first call stored a corrupted miner hash — always cross-check against registry `cur_XelisVaultMiner`);
  feed XEL/USD re-added (add_feed_entry 10, `68c0ecab…`, id 0 active 8 decimals 1/1e11, agg 5 blocks,
  max deviation 500bps, cb threshold 2000bps, max stale 30, hard stale default); verified via `fc`/`fd_0`/`fa_0`.
- miner register_service (31) with service_id **1** (0 → `badservice`) `61ec83d2…`; key `svc_<oracle_hash>` = 1.
- set_oracle re-pointed → v3: VaultSwap (37) `f93698e7…`, PSM (23) `d936b461…`, LendingMarket (29) `597ee909…`,
  PeerLoan (15) `8cacb8ed…`, SyndicatePool (19) `e643919a…`. Verified `or` keys + `fd_0`/`fg_0`/`la_0`.
- xUSD: old VE1 minter/burner revoked (`9f958f71…` `e89e4268…`, mi_/bu_ false); VE2 mi_/bu_ still true.

## Phase 9 — Insurance

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 9.1a | Deploy InsurancePool | `24bbde405c556e3b5b7eec8535f74f95ea1c8eee957731e63ca40000537bb9cb` | ✅ |
| 9.1b | IP.set_registry (16) / set_asset xUSD (15) | `7e18025a…` `f521058f…` | ✅ |
| 9.1c | Registry.register "InsurancePool" | `bca59285…` | ✅ |
| 9.2a | Deploy PrivateInsurance | `7e313998ccba0651bfeab12c8d6ff7153cfcf14c0e7486c51194430dc045e20f` | ✅ |
| 9.2b | PI.set_registry (15) | `5caf1f24…` | ✅ |
| 9.2c | Registry.register "PrivateInsurance" | `56cf839d…` | ✅ |

## Phase 10 — Governance

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 10.1 | GovernanceVault `65138ab1…`; set_registry(16)/set_vlt_contract(14)/set_vlt_asset(15); register | `cc92b3ce…` `3d8f05d5…` `6edab0dc…` `b024ff3c…` | ✅ |
| 10.2 | Timelock `0c4742be…`; register; set_governor(11)→Governor; set_guardian_contract(13)→GuardianMultisig | `dcf7e115…` `0e220379…` `6821dda4…` | ✅ |
| 10.3 | Governor `bfdbbf77…`; set_governance_vault(10)/set_timelock(11); register | `bf96d662…` `397b4528…` `58d79cc9…` | ✅ |
| 10.4 | GuardianMultisig `435e001c…`; set_timelock(12); register | `35cb4039…` `19d1ee7c…` | ✅ |
| 10.5 | OracleGovernance `97f51a64…` (patched); set_gov_vault(19)/set_oracle(18)/set_timelock(21); register | `f52ab33e…` `0e9e1b65…` `d9c767ab…` `13e13809…` | ✅ |

> Deferred (needs multisig proposal flow): add 4 more guardians + set_quorum 3 on GuardianMultisig.

## Phase 11 — Chat

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 11.1 | VaultChat `7560b5e3…` (patched); set_relayer(20, admin); register | `e9e04cb2…` `6d1b587b…` | ✅ |

> Deferred: `set_miner_contract` (reward relaying) is a pub-fn (All chunk) → not externally
> invokable; requires the governance proposal path (Governor/Timelock cross-contract call).
> VaultChat has no registry reference (guide's set_registry is stale).

## Phase 12 — Founder & Fees

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 12.1 | FounderVesting 4y `99ee7012…`; set_founder(10)/set_vlt_contract(11)/set_vlt_asset(12); funded 500k VLT (deposit); register "FounderVesting4y" | `5a0845c9…` `a7e86e73…` `b864f281…` `ca539aff…` `99edd9d5…` | ✅ |
| 12.2 | FounderVesting 10y `d919ca28…`; same config; funded 500k VLT; register "FounderVesting10y" | `7b93c2d9…` `26109eb4…` `1dc168c0…` `885520a1…` `c054ca76…` | ✅ |
| 12.3 | FeeDistributor `29fb3abf…`; set_founder(15)/set_treasury(16→TreasuryVault hash)/set_vlt_contract(17)/set_vlt_asset(18)/set_registry(19); register | `0e001f8e…` `057d9dd7…` `211be9b9…` `64c53fe4…` `bac7a434…` `9ad2cc5c…` | ✅ |
| 12.4 | MinerDelegation `e3c2f0f7…`; set_vlt_asset(27)/set_miner_contract_hash(22)/set_registry(28); register | `ba9f55ea…` `eaa2bd7f…` `5939a5fe…` `2ea77b9e…` | ✅ |

> Note: VLT minted via `mint_to_entry` (VLTToken entry 27) goes to an ADDRESS only — vesting
> contracts were funded via invoke deposit (deposits `{<asset>: {"amount": N}}`). MAX_SUPPLY = 1e15.
> Fee routing to FeeDistributor deferred: fee destinations are Address-typed (xUSD mint_split);
> FeeDistributor is a contract (Hash) — needs a future funding mechanism.
> MinerDelegation own-stake push (miner → MD.set_miner_own_stake entry 14) deferred (only_miner_contract).

## Phase 13 — Airdrop

SKIPPED by design: airdrop share (500k VLT) minted to admin for manual distribution.

## Final verification

- **Registry**: 35 names registered (all guide core contracts except AirdropTracker, which is
  skipped; ComplianceModule + FaucetContract registered retroactively: `cc730128…` `9073b881…`).
- **VLT asset**: `9d074e1b…` owned by VLTToken, max supply 1e15 (10M VLT @8dp), decimals 8.
  Supply minted: initial + 500k airdrop + 500k FV4y + 500k FV10y (within cap).
- **Oracle v3**: feed 0 XEL/USD active, agg 5 blocks, max dev 500bps, cb 2000bps, max stale 30.
- **VaultEngine v2** live in registry; VE1 mint/burn revoked on xUSD.
- Key storage spot-checked on InsurancePool, PrivateInsurance, GovernanceVault, Governor,
  GuardianMultisig, OracleGovernance, VaultChat, FeeDistributor, MinerDelegation — all correct.
- Deposits to contracts use `deposits: {"<asset>": {"amount": N}}` (ContractDepositBuilder).
- Remaining deferred items (documented above): GuardianMultisig +3 guardians + quorum 3,
  VaultChat.set_miner_contract, FeeDistributor fee routing, MinerDelegation own-stake push.
  All require the governance proposal path (All-chunk cross-contract calls via Governor/Timelock).

## Registry count — 33 registered names; remaining guide checks:

- VaultEngine v2 live (`2c22a613…`), StakedOracle v3 live (`159594c8…`).
- Guarded/All-chunk configs deferred to governance path (documented above).

---

# v12R-3 — CANONICAL CHAIN (2026-08-24) — ÉTAT ACTUEL

⚠️ **Les phases 1-13 ci-dessus décrivent l'HISTORIQUE (pré-rollback + fork abandonné).**
Après le rollback du 08-22 et le re-alignement fast-sync du 08-24, la source de vérité
des adresses est **`docs/deployment_state.json`** + résolution live via
`ContractRegistry cur_<Name>` (hash registre: `19161543b9e5aef00c5a3e226058b946d847c78941f0c89e9b996c6332204970`).

## Upgrades v12R-3 (registry entry 4)

| Contract | cur_ hash | Raison |
|---|---|---|
| VaultEngineV3 | `dcefbd7bd5de056247b3e4195d52df42b32fa510361cd1dc31ed115d65450e48` | deposit retournait id≥1 → écritures jetées par la VM stock |
| PrivacyMixer | `1ade068cf7a970c9315a687983b27ab5359af9cadc8f79b71825738f717fa7e3` | idem (return pool_count) |
| FaucetContract | `ed6e2f58c9a98bd098534efce6f430a3b2abb77cf015e5e5b193c4f37d7e16a4` | idem (return len) |
| VaultChat | `73f7b78bef94c20a5115f8fdc9ed2cd8d8792cdb398f01a7f254163b30958e24` | v12R-2: collision gm_/gk_ |

Convention VM stock: **toute entry qui mute retourne 0** (sinon exit_code≠0 silencieux
+ état jeté, tx confirmée quand même). Les requires loggent `exit_error` avec message;
un abort silencieux = panic/return-non-zéro.

## Re-seed canon post-fork (08-24)
PSM réserve XEL (+40), contrat xUSD financé 16 xUSD (burn reserve redeem/repay),
pool VaultSwap XEL/xUSD créé + liq 2 XEL : 0.3464 xUSD + CB 3000 bps,
faucet refillé 10k XEL + 50k VLT (claims 1 XEL + 5 VLT), admin register_miner
(stake 1000 VLT = 1e11 atomiques).

## Validation E2E (écrites, via Backend CLI)
`scripts/test_cli_ops.py` 14/14 · `scripts/test_chat.py` 17/17.
Non encore exercés en auto: TreasuryVault multisig, GovernanceVault, FlashLoan,
PeerLoan/SyndicatePool/Auction, flux confidentiels VE3, mixer refund (timeout 1j).
