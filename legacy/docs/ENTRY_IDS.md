# ENTRY IDs — XELIS Vault v11.3

Auto-generated from `contracts/` by `scripts/extract_entry_ids.py`.

Each `entry` function gets a sequential ID starting at 0 in declaration order.
**Total entry functions across 51 contracts:** 961

`pub fn` and `fn` do NOT count for ID numbering — they are not callable via `Contract::call`.


## `airdrop/AirdropClaim.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `claim` | `testnet_addr: Address, mainnet_addr: Address, amount: u64, proof: Hash[]` | `u` |
| 1 | `emergency_withdraw_unclaimed` | `to: Address` | `u` |
| 2 | `set_vlt_contract` | `vc: Hash` | `u` |
| 3 | `set_merkle_root` | `root: Hash` | `u` |
| 4 | `set_registry` | `registry: Hash` | `u` |
| 5 | `set_timelock` | `tl: Hash` | `u` |
| 6 | `set_guardian` | `g: Address` | `u` |
| 7 | `pause` | `—` | `u` |
| 8 | `unpause` | `—` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `get_version` | `—` | `s` |

## `airdrop/AirdropTracker.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `record_mining_activity` | `miner: Address, valid_submissions: u64, runtime_blocks: u64` | `u` |
| 1 | `record_relayer_activity` | `relayer: Address, valid_anchors: u64, uptime_blocks: u64` | `u` |
| 2 | `record_governance_vote` | `voter: Address, _proposal_id: u64` | `u` |
| 3 | `record_governance_proposal` | `proposer: Address, _proposal_id: u64` | `u` |
| 4 | `record_chat_message` | `sender: Address` | `u` |
| 5 | `record_chat_group_created` | `creator: Address` | `u` |
| 6 | `record_liquidity_provided` | `user: Address, xel_amount: u64` | `u` |
| 7 | `record_bug_bounty` | `reporter: Address, severity: u8` | `u` |
| 8 | `record_manual_attribution` | `user: Address, category: u8, points: u64, reason: string` | `u` |
| 9 | `record_mainnet_address` | `mainnet_addr: Address` | `u` |
| 10 | `freeze_points` | `—` | `u` |
| 11 | `finalize_distribution` | `—` | `u` |
| 12 | `set_merkle_root` | `root: Hash` | `u` |
| 13 | `record_manual_attribution_batch` | `users: Address[], category: u8, points: u64, reason: string` | `u` |
| 14 | `deduct_points` | `user: Address, category: u8, points: u64, reason: string` | `u` |
| 15 | `disqualify_user` | `user: Address, reason: string` | `u` |
| 16 | `revoke_disqualification` | `user: Address, reason: string` | `u` |
| 17 | `force_qualify_user` | `user: Address, reason: string` | `u` |
| 18 | `revoke_force_qualification` | `user: Address, reason: string` | `u` |
| 19 | `set_user_bonus_multiplier` | `user: Address, multiplier_bps: u64, reason: string` | `u` |
| 20 | `set_manual_attribution_cap` | `new_cap: u64` | `u` |
| 21 | `set_authorized_recorder` | `addr: Address, authorized: bool` | `u` |
| 22 | `set_vlt_contract` | `vc: Hash` | `u` |
| 23 | `set_registry` | `registry: Hash` | `u` |
| 24 | `set_timelock` | `tl: Hash` | `u` |
| 25 | `set_guardian` | `g: Address` | `u` |
| 26 | `pause` | `—` | `u` |
| 27 | `unpause` | `—` | `u` |
| 28 | `transfer_admin` | `new_admin: Address` | `u` |
| 29 | `get_version` | `—` | `s` |

## `amm/PSM.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `mint` | `xel_amount: u64, min_xusd_out: u64` | `u` |
| 1 | `redeem` | `xusd_amount: u64, min_xel_out: u64` | `u` |
| 2 | `get_reserves_entry` | `—` | `(` |
| 3 | `get_mint_fee_entry` | `—` | `u` |
| 4 | `get_redeem_fee_entry` | `—` | `u` |
| 5 | `get_daily_usage_entry` | `—` | `(` |
| 6 | `set_mint_fee_bps` | `bps: u64` | `u` |
| 7 | `set_redeem_fee_bps` | `bps: u64` | `u` |
| 8 | `set_daily_caps` | `mint_cap: u64, redeem_cap: u64` | `u` |
| 9 | `pause` | `reason: string` | `u` |
| 10 | `unpause` | `—` | `u` |
| 11 | `request_emergency_withdraw` | `—` | `u` |
| 12 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 13 | `set_xusd_contract` | `xc: Hash` | `u` |
| 14 | `set_xusd_asset` | `xa: Hash` | `u` |
| 15 | `set_oracle` | `oracle: Hash` | `u` |
| 16 | `set_treasury` | `t: Address` | `u` |
| 17 | `set_registry` | `reg: Hash` | `u` |
| 18 | `set_timelock` | `tl: Hash` | `u` |
| 19 | `set_guardian` | `g: Address` | `u` |
| 20 | `set_emergency` | `e: Address` | `u` |
| 21 | `transfer_admin` | `new_admin: Address` | `u` |
| 22 | `get_version` | `—` | `s` |

## `amm/VaultSwapV2.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_pool` | `asset_a: Hash, asset_b: Hash, is_psm: bool` | `u` |
| 1 | `add_liquidity` | `asset_a: Hash, asset_b: Hash, amount_a: u64, amount_b: u64` | `u` |
| 2 | `swap` | `asset_in: Hash, asset_out: Hash, amount_in: u64, min_amount_out: u64` | `u` |
| 3 | `psm_mint` | `xel_amount: u64, min_xusd_out: u64` | `u` |
| 4 | `psm_redeem` | `xusd_amount: u64, min_xel_out: u64` | `u` |
| 5 | `get_pool_entry` | `asset_a: Hash, asset_b: Hash` | `(` |
| 6 | `get_amount_out_view_entry` | `asset_in: Hash, asset_out: Hash, amount_in: u64` | `u` |
| 7 | `get_twap_entry` | `asset_a: Hash, asset_b: Hash` | `u` |
| 8 | `get_volatility_bps_entry` | `asset_a: Hash, asset_b: Hash` | `u` |
| 9 | `get_pools_count_entry` | `—` | `u` |
| 10 | `get_pool_by_index_entry` | `index: u64` | `(` |
| 11 | `get_fees_entry` | `—` | `(` |
| 12 | `pause` | `reason: string` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `set_base_fee_bps` | `f: u64` | `u` |
| 15 | `set_treasury_fee_bps` | `f: u64` | `u` |
| 16 | `set_max_volatility_bps` | `v: u64` | `u` |
| 17 | `set_max_swap_pct_bps` | `p: u64` | `u` |
| 18 | `set_psm_mint_fee_bps` | `f: u64` | `u` |
| 19 | `set_psm_redeem_fee_bps` | `f: u64` | `u` |
| 20 | `set_registry` | `reg: Hash` | `u` |
| 21 | `set_oracle` | `oracle: Hash` | `u` |
| 22 | `set_xusd_asset` | `xa: Hash` | `u` |
| 23 | `set_xusd_contract` | `xc: Hash` | `u` |
| 24 | `set_treasury` | `t: Address` | `u` |
| 25 | `set_timelock` | `tl: Hash` | `u` |
| 26 | `set_guardian` | `g: Address` | `u` |
| 27 | `set_emergency` | `e: Address` | `u` |
| 28 | `transfer_admin` | `new_admin: Address` | `u` |
| 29 | `get_version` | `—` | `s` |
| 30 | `request_emergency_withdraw` | `—` | `u` |
| 31 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `analytics/AnalyticsCollector.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `record_tvl_snapshot` | `total_tvl: u64, xel_tvl: u64, xusd_supply: u64, vlt_staked: u64` | `u` |
| 1 | `record_swap_volume` | `volume_atomic: u64` | `u` |
| 2 | `record_liquidation` | `collateral_seized: u64` | `u` |
| 3 | `record_vault_opened` | `—` | `u` |
| 4 | `record_vault_closed` | `—` | `u` |
| 5 | `record_rewards_distributed` | `amount: u64` | `u` |
| 6 | `record_health_factor_bucket` | `bucket: u8` | `u` |
| 7 | `record_active_user` | `—` | `u` |
| 8 | `set_registry` | `registry: Hash` | `u` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `set_guardian` | `g: Address` | `u` |
| 11 | `transfer_admin` | `new_admin: Address` | `u` |
| 12 | `get_version` | `—` | `s` |

## `auction/SealedBidAuction.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_auction` | `asset: Hash, amount: u64, bid_asset: Hash, min_bid: u64, commit_duration: u64, reveal_duration: u64` | `u` |
| 1 | `commit` | `auction_id: u64, bid_hash: Hash` | `u` |
| 2 | `reveal` | `auction_id: u64, bid_amount: u64, nonce: u64` | `u` |
| 3 | `settle` | `auction_id: u64` | `u` |
| 4 | `declare_winner` | `auction_id: u64, winner: Address, winning_bid: u64` | `u` |
| 5 | `refund_bid` | `auction_id: u64` | `u` |
| 6 | `claim_asset` | `auction_id: u64` | `u` |
| 7 | `claim_proceeds` | `auction_id: u64` | `u` |
| 8 | `get_auction_entry` | `auction_id: u64` | `(` |
| 9 | `get_auctions_count_entry` | `—` | `u` |
| 10 | `pause` | `reason: string` | `u` |
| 11 | `unpause` | `—` | `u` |
| 12 | `set_registry` | `reg: Hash` | `u` |
| 13 | `set_treasury` | `t: Address` | `u` |
| 14 | `set_timelock` | `tl: Hash` | `u` |
| 15 | `set_guardian` | `g: Address` | `u` |
| 16 | `set_emergency` | `e: Address` | `u` |
| 17 | `transfer_admin` | `new_admin: Address` | `u` |
| 18 | `get_version` | `—` | `s` |
| 19 | `request_emergency_withdraw` | `—` | `u` |
| 20 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `chat/VaultChat.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `register_session` | `chat_pubkey: Hash` | `u` |
| 1 | `create_group` | `group_pubkey: Hash` | `u` |
| 2 | `add_group_member` | `group_id: u64, member: Address, encrypted_group_key: bytes` | `u` |
| 3 | `remove_group_member` | `group_id: u64, member: Address` | `u` |
| 4 | `anchor_messages` | `merkle_root: Hash, message_count: u64, sender_count: u64, msg_type: u8` | `u` |
| 5 | `revoke_session` | `user: Address` | `u` |
| 6 | `get_session_entry` | `user: Address` | `(` |
| 7 | `get_group_entry` | `group_id: u64` | `(` |
| 8 | `get_group_member_key_entry` | `group_id: u64, member: Address` | `H` |
| 9 | `is_session_active_entry` | `user: Address` | `b` |
| 10 | `get_last_anchor_entry` | `—` | `(` |
| 11 | `get_groups_count_entry` | `—` | `u` |
| 12 | `get_group_members_count_entry` | `group_id: u64` | `u` |
| 13 | `set_relayer` | `addr: Address, enabled: bool` | `u` |
| 14 | `set_timelock` | `tl: Hash` | `u` |
| 15 | `set_guardian` | `g: Address` | `u` |
| 16 | `pause` | `reason: string` | `u` |
| 17 | `unpause` | `—` | `u` |
| 18 | `transfer_admin` | `new_admin: Address` | `u` |
| 19 | `get_version` | `—` | `s` |
| 20 | `request_emergency_withdraw` | `—` | `u` |
| 21 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 22 | `store_message` | `recipient: Address, encrypted_blob: bytes, timestamp: u64` | `u` |
| 23 | `delete_message` | `recipient: Address, slot: u64` | `u` |
| 24 | `delete_conversation` | `peer: Address` | `u` |
| 25 | `set_group_admin` | `group_id: u64, new_admin: Address` | `u` |
| 26 | `admin_delete_group_message` | `group_id: u64, msg_slot: u64` | `u` |
| 27 | `admin_kick_member` | `group_id: u64, member: Address` | `u` |
| 28 | `store_group_message` | `group_id: u64, encrypted_blob: bytes, timestamp: u64` | `u` |
| 29 | `set_relayer_fee` | `fee_amount: u64, token: u8` | `u` |
| 30 | `pay_premium_message` | `relayer: Address` | `u` |
| 31 | `claim_relayer_fees` | `—` | `u` |
| 32 | `rotate_group_key` | `group_id: u64, new_group_pubkey: Hash` | `u` |
| 33 | `distribute_new_key` | `group_id: u64, member: Address, new_encrypted_key: bytes` | `u` |
| 34 | `mark_read` | `recipient: Address, slot: u64` | `u` |
| 35 | `store_ephemeral_message` | `recipient: Address, encrypted_blob: bytes, timestamp: u64, ttl_blocks: u64` | `u` |
| 36 | `register_as_relayer` | `endpoint: string, free_daily_limit: u64, free_wallet_slots: u64` | `u` |
| 37 | `claim_free_slot` | `—` | `u` |
| 38 | `consume_free_message` | `relayer: Address` | `u` |
| 39 | `report_free_usage` | `user: Address` | `u` |
| 40 | `create_plan` | `plan_type: u8, amount: u64, duration_blocks: u64, msg_count: u64, token: u8` | `u` |
| 41 | `update_plan` | `plan_id: u64, amount: u64, duration_blocks: u64, msg_count: u64` | `u` |
| 42 | `delete_plan` | `plan_id: u64` | `u` |
| 43 | `buy_plan` | `relayer: Address, plan_id: u64, recipient: Address` | `u` |
| 44 | `consume_credit` | `user: Address` | `u` |
| 45 | `set_batch_interval` | `blocks: u64` | `u` |
| 46 | `anchor_batch` | `merkle_root: Hash, message_count: u64` | `u` |
| 47 | `blacklist_relayer` | `bad_relayer: Address, reason: string` | `u` |
| 48 | `set_protocol_fee_bps` | `bps: u64` | `u` |
| 49 | `set_treasury` | `addr: Address` | `u` |
| 50 | `set_prune_interval` | `blocks: u64` | `u` |
| 51 | `report_storage_stats` | `total_gb: u64, used_gb: u64, messages_stored: u64` | `u` |
| 52 | `create_payment_request` | `to: Address, amount: u64, asset: Hash, memo: string` | `u` |
| 53 | `fulfill_payment_request` | `req_id: u64` | `u` |
| 54 | `cancel_payment_request` | `req_id: u64` | `u` |
| 55 | `create_giveaway` | `scope: string, amount_per_claim: u64, max_claims: u64, asset: Hash` | `u` |
| 56 | `claim_giveaway` | `giveaway_id: u64` | `u` |
| 57 | `cancel_giveaway` | `giveaway_id: u64` | `u` |
| 58 | `send_direct_message` | `recipient: Address, encrypted_blob: bytes, timestamp: u64` | `u` |
| 59 | `delete_direct_message` | `recipient: Address, slot: u64` | `u` |
| 60 | `toggle_relayer_paused` | `—` | `u` |
| 61 | `update_relayer_endpoint` | `new_endpoint: string` | `u` |
| 62 | `update_free_tier` | `free_daily_limit: u64, free_wallet_slots: u64` | `u` |
| 63 | `stake_relayer_bond` | `bond_amount: u64` | `u` |
| 64 | `slash_relayer_bond` | `relayer: Address, slash_bps: u64, reason: string` | `u` |
| 65 | `withdraw_relayer_bond` | `—` | `u` |
| 66 | `rate_relayer_weighted` | `relayer: Address, score: u8` | `u` |
| 67 | `set_member_role` | `group_id: u64, member: Address, new_role: u8` | `u` |
| 68 | `mute_member` | `group_id: u64, member: Address, duration_blocks: u64` | `u` |

## `compliance/ComplianceModule.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `verify_proof_entry` | `merkle_proof: Hash, merkle_root: Hash` | `b` |
| 1 | `is_compliant_entry` | `addr: Address` | `b` |
| 2 | `get_current_root_entry` | `—` | `H` |
| 3 | `get_verifiers_count_entry` | `—` | `u` |
| 4 | `update_merkle_root` | `new_root: Hash` | `u` |
| 5 | `mark_compliant` | `addr: Address, compliant: bool` | `u` |
| 6 | `add_verifier` | `verifier: Address` | `u` |
| 7 | `remove_verifier` | `verifier: Address` | `u` |
| 8 | `set_compliance_required` | `asset: Hash, required: bool` | `u` |
| 9 | `set_registry` | `reg: Hash` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `pause` | `reason: string` | `u` |
| 12 | `unpause` | `—` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_version` | `—` | `s` |

## `credit/CreditScore.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `record_loan_opened` | `borrower: Address, amount: u64, collateral_ratio_bps: u64` | `u` |
| 1 | `record_loan_repaid` | `borrower: Address, amount: u64, duration_blocks: u64, days_late: u64` | `u` |
| 2 | `record_loan_defaulted` | `borrower: Address, amount: u64` | `u` |
| 3 | `set_registry` | `registry: Hash` | `u` |
| 4 | `set_timelock` | `tl: Hash` | `u` |
| 5 | `set_guardian` | `g: Address` | `u` |
| 6 | `pause` | `—` | `u` |
| 7 | `unpause` | `—` | `u` |
| 8 | `transfer_admin` | `new_admin: Address` | `u` |
| 9 | `get_version` | `—` | `s` |

## `faucet/FaucetContract.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `refill_xel` | `—` | `u` |
| 1 | `refill_vlt` | `amount: u64` | `u` |
| 2 | `distribute` | `addresses: Address[]` | `u` |
| 3 | `set_claim_amounts` | `xel_amount: u64, vlt_amount: u64` | `u` |
| 4 | `set_cooldown_blocks` | `blocks: u64` | `u` |
| 5 | `set_lifetime_caps` | `xel_cap: u64, vlt_cap: u64` | `u` |
| 6 | `pause` | `—` | `u` |
| 7 | `unpause` | `—` | `u` |
| 8 | `set_vlt_contract` | `vc: Hash` | `u` |
| 9 | `set_vlt_asset` | `va: Hash` | `u` |
| 10 | `set_registry` | `registry: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `set_guardian` | `g: Address` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_version` | `—` | `s` |
| 15 | `request_emergency_withdraw` | `—` | `u` |
| 16 | `execute_emergency_withdraw` | `—` | `u` |

## `flashloan/FlashCallback.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `claim_profit` | `asset: Hash` | `u` |
| 1 | `set_flash_loan` | `fl: Hash` | `u` |
| 2 | `set_registry` | `reg: Hash` | `u` |
| 3 | `transfer_admin` | `new_admin: Address` | `u` |
| 4 | `get_version` | `—` | `s` |

## `flashloan/FlashLoan.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `flash_loan` | `asset: Hash, amount: u64, callback_contract: Hash, callback_data: bytes` | `u` |
| 1 | `get_fee_bps_entry` | `—` | `u` |
| 2 | `get_total_earned_entry` | `—` | `u` |
| 3 | `get_available_liquidity_entry` | `asset: Hash` | `u` |
| 4 | `set_fee_bps` | `bps: u64` | `u` |
| 5 | `pause` | `reason: string` | `u` |
| 6 | `unpause` | `—` | `u` |
| 7 | `set_treasury` | `t: Address` | `u` |
| 8 | `set_registry` | `reg: Hash` | `u` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `set_guardian` | `g: Address` | `u` |
| 11 | `set_emergency` | `e: Address` | `u` |
| 12 | `transfer_admin` | `new_admin: Address` | `u` |
| 13 | `get_version` | `—` | `s` |
| 14 | `request_emergency_withdraw` | `—` | `u` |
| 15 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 16 | `verify_callback` | `callback_contract: Hash` | `u` |
| 17 | `revoke_callback` | `callback_contract: Hash` | `u` |

## `founder/FeeDistributor.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `collect_fee` | `asset: Hash, amount: u64` | `u` |
| 1 | `claim_founder_share` | `—` | `u` |
| 2 | `claim_treasury_share` | `—` | `u` |
| 3 | `burn_deflationary_share` | `—` | `u` |
| 4 | `set_founder` | `new_founder: Address` | `u` |
| 5 | `set_treasury` | `tr: Hash` | `u` |
| 6 | `set_vlt_contract` | `vc: Hash` | `u` |
| 7 | `set_vlt_asset` | `va: Hash` | `u` |
| 8 | `set_registry` | `registry: Hash` | `u` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `set_guardian` | `g: Address` | `u` |
| 11 | `pause` | `—` | `u` |
| 12 | `unpause` | `—` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_version` | `—` | `s` |

## `founder/FounderVesting.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `claim_founder_tokens` | `—` | `u` |
| 1 | `set_founder` | `new_founder: Address` | `u` |
| 2 | `set_vlt_contract` | `vc: Hash` | `u` |
| 3 | `set_vlt_asset` | `va: Hash` | `u` |
| 4 | `set_registry` | `registry: Hash` | `u` |
| 5 | `set_timelock` | `tl: Hash` | `u` |
| 6 | `set_guardian` | `g: Address` | `u` |
| 7 | `pause` | `—` | `u` |
| 8 | `unpause` | `—` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `get_version` | `—` | `s` |

## `founder/RevenueShareDelegation.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `set_share` | `contributor: Address, percentage_bps: u64, duration_blocks: u64` | `u` |
| 1 | `revoke_share` | `contributor: Address` | `u` |
| 2 | `update_share_percentage` | `contributor: Address, new_percentage_bps: u64` | `u` |
| 3 | `extend_share_duration` | `contributor: Address, additional_blocks: u64` | `u` |
| 4 | `claim_founder_revenue` | `—` | `u` |
| 5 | `claim_contributor_revenue` | `—` | `u` |
| 6 | `receive_fee` | `asset: Hash, amount: u64` | `u` |
| 7 | `set_vlt_contract` | `vc: Hash` | `u` |
| 8 | `set_xel_asset` | `xa: Hash` | `u` |
| 9 | `set_registry` | `registry: Hash` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `set_guardian` | `g: Address` | `u` |
| 12 | `pause` | `—` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `transfer_admin` | `new_admin: Address` | `u` |
| 15 | `get_version` | `—` | `s` |

## `governance/GovernanceDelegation.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `delegate` | `delegate_addr: Address` | `u` |
| 1 | `undelegate` | `—` | `u` |
| 2 | `delegate_by_topic` | `topic: u8, delegate_addr: Address` | `u` |
| 3 | `undelegate_by_topic` | `topic: u8` | `u` |
| 4 | `record_vote` | `delegate_addr: Address, voted_with_majority: bool` | `u` |
| 5 | `set_governance_vault` | `gv: Address` | `u` |
| 6 | `set_registry` | `registry: Hash` | `u` |
| 7 | `set_timelock` | `tl: Hash` | `u` |
| 8 | `set_guardian` | `g: Address` | `u` |
| 9 | `pause` | `—` | `u` |
| 10 | `unpause` | `—` | `u` |
| 11 | `transfer_admin` | `new_admin: Address` | `u` |
| 12 | `get_version` | `—` | `s` |

## `governance/GovernanceVault.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `stake` | `amount: u64, lock_days: u64` | `u` |
| 1 | `unstake` | `stake_id: u64` | `u` |
| 2 | `claim_rewards` | `—` | `u` |
| 3 | `get_total_staked_entry` | `—` | `u` |
| 4 | `get_user_staked_entry` | `addr: Address` | `u` |
| 5 | `get_stakes_count_entry` | `—` | `u` |
| 6 | `notify_reward_amount` | `amount: u64` | `u` |
| 7 | `set_reward_distributor` | `contract_hash: Hash, enabled: bool` | `u` |
| 8 | `set_vlt_contract` | `vc: Hash` | `u` |
| 9 | `set_vlt_asset` | `va: Hash` | `u` |
| 10 | `set_registry` | `reg: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `pause` | `reason: string` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `transfer_admin` | `new_admin: Address` | `u` |
| 15 | `set_emergency` | `e: Address` | `u` |
| 16 | `get_version` | `—` | `s` |
| 17 | `request_emergency_withdraw` | `—` | `u` |
| 18 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `governance/Governor.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `propose` | `target: Hash, entry_id: u16, params: bytes, description: string` | `u` |
| 1 | `vote` | `proposal_id: u64, support: u8` | `u` |
| 2 | `queue` | `proposal_id: u64` | `u` |
| 3 | `cancel` | `proposal_id: u64` | `u` |
| 4 | `get_proposal_count_entry` | `—` | `u` |
| 5 | `set_governance_vault` | `gv: Hash` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `set_voting_period` | `blocks: u64` | `u` |
| 8 | `set_quorum_bps` | `bps: u64` | `u` |
| 9 | `set_approval_bps` | `bps: u64` | `u` |
| 10 | `set_proposal_threshold` | `threshold: u64` | `u` |
| 11 | `transfer_admin` | `new_admin: Address` | `u` |
| 12 | `get_version` | `—` | `s` |

## `governance/GuardianMultisig.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `propose_emergency_action` | `target: Hash, action: u8, params: bytes` | `u` |
| 1 | `confirm` | `proposal_id: u64` | `u` |
| 2 | `execute` | `proposal_id: u64` | `u` |
| 3 | `add_guardian_via_proposal` | `guardian: Address, params: bytes` | `u` |
| 4 | `remove_guardian_via_proposal` | `guardian: Address, params: bytes` | `u` |
| 5 | `set_quorum_via_proposal` | `new_quorum: u64, params: bytes` | `u` |
| 6 | `get_proposal_entry` | `proposal_id: u64` | `(` |
| 7 | `get_guardians_info_entry` | `—` | `(` |
| 8 | `is_guardian_entry` | `addr: Address` | `b` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `transfer_admin` | `new_admin: Address` | `u` |
| 11 | `get_version` | `—` | `s` |
| 12 | `request_emergency_withdraw` | `—` | `u` |
| 13 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `governance/OracleGovernance.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `propose_add_feed` | `name: string, asset: Hash, decimals: u8, min_price: u64, max_price: u64, description: string` | `u` |
| 1 | `propose_update_feed` | `feed_id: u64, min_price: u64, max_price: u64, decimals: u8, description: string` | `u` |
| 2 | `propose_remove_feed` | `feed_id: u64, description: string` | `u` |
| 3 | `propose_set_param` | `param_key: u8, param_value: u64, description: string` | `u` |
| 4 | `propose_set_reward` | `reward_amount: u64, description: string` | `u` |
| 5 | `propose_emergency_cb` | `feed_id: u64, description: string` | `u` |
| 6 | `propose_reset_feed` | `feed_id: u64, description: string` | `u` |
| 7 | `vote` | `proposal_id: u64, support: bool` | `u` |
| 8 | `execute_proposal` | `proposal_id: u64` | `u` |
| 9 | `cancel_proposal` | `proposal_id: u64` | `u` |
| 10 | `set_voting_period` | `blocks: u64` | `u` |
| 11 | `set_quorum_bps` | `bps: u64` | `u` |
| 12 | `set_approval_bps` | `bps: u64` | `u` |
| 13 | `set_execution_delay` | `blocks: u64` | `u` |
| 14 | `set_oracle` | `oracle: Hash` | `u` |
| 15 | `set_governance_vault` | `gv: Hash` | `u` |
| 16 | `set_miner_contract` | `mc: Hash` | `u` |
| 17 | `set_timelock` | `tl: Hash` | `u` |
| 18 | `set_guardian` | `g: Address` | `u` |
| 19 | `transfer_admin` | `new_admin: Address` | `u` |
| 20 | `get_version` | `—` | `s` |

## `governance/Timelock.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `execute_proposal` | `proposal_id: u64` | `u` |
| 1 | `cancel_proposal` | `proposal_id: u64` | `u` |
| 2 | `set_min_delay` | `delay: u64` | `u` |
| 3 | `set_max_delay` | `delay: u64` | `u` |
| 4 | `set_governor` | `gov: Hash` | `u` |
| 5 | `set_guardian` | `g: Address` | `u` |
| 6 | `set_guardian_contract` | `gc: Hash` | `u` |
| 7 | `set_emergency` | `e: Address` | `u` |
| 8 | `transfer_admin` | `new_admin: Address` | `u` |
| 9 | `get_version` | `—` | `s` |
| 10 | `request_emergency_withdraw` | `—` | `u` |
| 11 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `insurance/InsurancePool.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `stake` | `amount: u64` | `u` |
| 1 | `unstake` | `amount: u64` | `u` |
| 2 | `claim_premium` | `—` | `u` |
| 3 | `submit_claim` | `amount: u64, evidence_hash: Hash` | `u` |
| 4 | `approve_claim` | `claim_id: u64` | `u` |
| 5 | `reject_claim` | `claim_id: u64` | `u` |
| 6 | `pay_premium` | `amount: u64` | `u` |
| 7 | `get_pool_info_entry` | `—` | `(` |
| 8 | `get_staker_entry` | `addr: Address` | `(` |
| 9 | `set_asset` | `a: Hash` | `u` |
| 10 | `set_registry` | `reg: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `set_guardian` | `g: Address` | `u` |
| 13 | `set_emergency` | `e: Address` | `u` |
| 14 | `pause` | `reason: string` | `u` |
| 15 | `unpause` | `—` | `u` |
| 16 | `transfer_admin` | `new_admin: Address` | `u` |
| 17 | `get_version` | `—` | `s` |
| 18 | `request_emergency_withdraw` | `—` | `u` |
| 19 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `insurance/PrivateInsurance.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_policy` | `asset: Hash, coverage_amount: u64, premium: u64, duration_blocks: u64, trigger_hash: Hash` | `u` |
| 1 | `buy_policy` | `policy_id: u64` | `u` |
| 2 | `claim` | `policy_id: u64, evidence_hash: Hash` | `u` |
| 3 | `approve_claim` | `policy_id: u64` | `u` |
| 4 | `cancel_policy` | `policy_id: u64` | `u` |
| 5 | `expire_policy` | `policy_id: u64` | `u` |
| 6 | `get_policy_entry` | `policy_id: u64` | `(` |
| 7 | `get_policies_count_entry` | `—` | `u` |
| 8 | `set_registry` | `reg: Hash` | `u` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `set_emergency` | `e: Address` | `u` |
| 11 | `pause` | `reason: string` | `u` |
| 12 | `unpause` | `—` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_version` | `—` | `s` |
| 15 | `request_emergency_withdraw` | `—` | `u` |
| 16 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `insurance/VaultInsurance.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `insure_vault` | `vault_id: u64, borrow_amount: u64` | `u` |
| 1 | `cancel_insurance` | `vault_id: u64` | `u` |
| 2 | `trigger_auto_repay` | `vault_id: u64, current_health_bps: u64` | `u` |
| 3 | `claim_residual_collateral` | `vault_id: u64` | `u` |
| 4 | `stake_to_pool` | `amount: u64` | `u` |
| 5 | `unstake_from_pool` | `amount: u64` | `u` |
| 6 | `claim_staker_rewards` | `—` | `u` |
| 7 | `set_vault_engine` | `ve: Hash` | `u` |
| 8 | `set_registry` | `registry: Hash` | `u` |
| 9 | `set_timelock` | `tl: Hash` | `u` |
| 10 | `set_guardian` | `g: Address` | `u` |
| 11 | `pause` | `—` | `u` |
| 12 | `unpause` | `—` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_version` | `—` | `s` |

## `interest/InterestRateModel.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `get_borrow_rate_entry` | `utilization_bps: u64` | `u` |
| 1 | `get_supply_rate_entry` | `utilization_bps: u64` | `u` |
| 2 | `annual_to_per_block_entry` | `annual_rate_bps: u64` | `u` |
| 3 | `get_rates_entry` | `—` | `(` |
| 4 | `set_rates` | `base: u64, multiplier: u64, jump: u64, kink: u64` | `u` |
| 5 | `set_reserve_factor` | `factor_bps: u64` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `transfer_admin` | `new_admin: Address` | `u` |
| 8 | `get_version` | `—` | `s` |

## `lending/LendingMarket.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_pool` | `collateral_asset: Hash, borrow_asset: Hash, collateral_factor_bps: u64, liquidation_threshold_bps: u64, liquidation_penalty_bps: u64, reserve_factor_bps: u64, interest_rate_model: Hash` | `u` |
| 1 | `supply` | `pool_id: u64, amount: u64` | `u` |
| 2 | `borrow` | `pool_id: u64, amount: u64` | `u` |
| 3 | `repay` | `pool_id: u64, amount: u64` | `u` |
| 4 | `withdraw` | `pool_id: u64, amount: u64` | `u` |
| 5 | `liquidate` | `pool_id: u64, user: Address, repay_amount: u64` | `u` |
| 6 | `get_pool_info_entry` | `pool_id: u64` | `(` |
| 7 | `get_user_position_entry` | `pool_id: u64, user: Address` | `(` |
| 8 | `get_pools_count_entry` | `—` | `u` |
| 9 | `pause` | `reason: string` | `u` |
| 10 | `unpause` | `—` | `u` |
| 11 | `set_oracle` | `oracle: Hash` | `u` |
| 12 | `set_treasury` | `t: Address` | `u` |
| 13 | `set_registry` | `reg: Hash` | `u` |
| 14 | `set_timelock` | `tl: Hash` | `u` |
| 15 | `set_guardian` | `g: Address` | `u` |
| 16 | `set_emergency` | `e: Address` | `u` |
| 17 | `transfer_admin` | `new_admin: Address` | `u` |
| 18 | `get_version` | `—` | `s` |
| 19 | `request_emergency_withdraw` | `—` | `u` |
| 20 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `lending/PeerLoan.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_offer` | `asset_lent: Hash, amount: u64, interest_bps: u64, duration_blocks: u64, collateral_asset: Hash, collateral_amount: u64` | `u` |
| 1 | `cancel_offer` | `offer_id: u64` | `u` |
| 2 | `accept_offer` | `offer_id: u64` | `u` |
| 3 | `repay` | `offer_id: u64` | `u` |
| 4 | `claim_collateral` | `offer_id: u64` | `u` |
| 5 | `get_offer_entry` | `offer_id: u64` | `(` |
| 6 | `get_offers_count_entry` | `—` | `u` |
| 7 | `pause` | `reason: string` | `u` |
| 8 | `unpause` | `—` | `u` |
| 9 | `set_oracle` | `oracle: Hash` | `u` |
| 10 | `set_treasury` | `t: Address` | `u` |
| 11 | `set_registry` | `reg: Hash` | `u` |
| 12 | `set_timelock` | `tl: Hash` | `u` |
| 13 | `set_guardian` | `g: Address` | `u` |
| 14 | `set_emergency` | `e: Address` | `u` |
| 15 | `transfer_admin` | `new_admin: Address` | `u` |
| 16 | `get_version` | `—` | `s` |
| 17 | `request_emergency_withdraw` | `—` | `u` |
| 18 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `lending/SyndicatePool.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_pool` | `asset_lent: Hash, total_amount: u64, interest_bps: u64, duration_blocks: u64, collateral_asset: Hash, collateral_amount: u64` | `u` |
| 1 | `supply` | `pool_id: u64, amount: u64` | `u` |
| 2 | `withdraw_supply` | `pool_id: u64, amount: u64` | `u` |
| 3 | `activate_pool` | `pool_id: u64` | `u` |
| 4 | `repay` | `pool_id: u64, amount: u64` | `u` |
| 5 | `claim` | `pool_id: u64` | `u` |
| 6 | `get_pool_entry` | `pool_id: u64` | `(` |
| 7 | `get_lender_position_entry` | `pool_id: u64, lender: Address` | `u` |
| 8 | `get_pools_count_entry` | `—` | `u` |
| 9 | `pause` | `reason: string` | `u` |
| 10 | `unpause` | `—` | `u` |
| 11 | `set_oracle` | `oracle: Hash` | `u` |
| 12 | `set_treasury` | `t: Address` | `u` |
| 13 | `set_registry` | `reg: Hash` | `u` |
| 14 | `set_timelock` | `tl: Hash` | `u` |
| 15 | `set_guardian` | `g: Address` | `u` |
| 16 | `set_emergency` | `e: Address` | `u` |
| 17 | `transfer_admin` | `new_admin: Address` | `u` |
| 18 | `get_version` | `—` | `s` |
| 19 | `request_emergency_withdraw` | `—` | `u` |
| 20 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `liquidation/LiquidationMarket.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `register_liquidator` | `endpoint_url: string` | `u` |
| 1 | `stake_for_priority` | `amount: u64` | `u` |
| 2 | `unstake` | `amount: u64` | `u` |
| 3 | `record_liquidation` | `liq_addr: Address, blocks_to_act: u64, reward_amount: u64` | `u` |
| 4 | `report_inactive` | `liq_addr: Address` | `u` |
| 5 | `claim_rewards` | `—` | `u` |
| 6 | `set_registry` | `registry: Hash` | `u` |
| 7 | `set_timelock` | `tl: Hash` | `u` |
| 8 | `set_guardian` | `g: Address` | `u` |
| 9 | `pause` | `—` | `u` |
| 10 | `unpause` | `—` | `u` |
| 11 | `transfer_admin` | `new_admin: Address` | `u` |
| 12 | `get_version` | `—` | `s` |

## `liquidation/VaultBounties.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `report_unhealthy_vault` | `vault_id: u64, vault_owner: Address, collateral_amount: u64, current_health_bps: u64` | `u` |
| 1 | `claim_bounty` | `vault_id: u64` | `u` |
| 2 | `set_vault_engine` | `ve: Hash` | `u` |
| 3 | `set_registry` | `registry: Hash` | `u` |
| 4 | `set_timelock` | `tl: Hash` | `u` |
| 5 | `set_guardian` | `g: Address` | `u` |
| 6 | `pause` | `—` | `u` |
| 7 | `unpause` | `—` | `u` |
| 8 | `transfer_admin` | `new_admin: Address` | `u` |
| 9 | `get_version` | `—` | `s` |

## `miner/MinerDelegation.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `register_miner_profile` | `name: string, description: string, commission_bps: u64` | `u` |
| 1 | `update_miner_profile` | `name: string, description: string, commission_bps: u64` | `u` |
| 2 | `delegate` | `miner_addr: Address, amount: u64, auto_compound: bool` | `u` |
| 3 | `undelegate` | `amount: u64` | `u` |
| 4 | `execute_undelegate` | `—` | `u` |
| 5 | `claim_delegator_rewards` | `—` | `u` |
| 6 | `claim_miner_rewards` | `—` | `u` |
| 7 | `distribute_rewards` | `miner_addr: Address, total_reward: u64` | `u` |
| 8 | `apply_slashing` | `miner_addr: Address, slash_amount: u64` | `u` |
| 9 | `set_miner_own_stake` | `miner_addr: Address, own_stake: u64` | `u` |
| 10 | `set_miner_contract_hash` | `mc_hash: Hash` | `u` |
| 11 | `set_min_commission` | `bps: u64` | `u` |
| 12 | `set_max_commission` | `bps: u64` | `u` |
| 13 | `set_undelegate_delay` | `blocks: u64` | `u` |
| 14 | `set_cap_stake` | `cap: u64` | `u` |
| 15 | `set_vlt_asset` | `va: Hash` | `u` |
| 16 | `set_registry` | `registry: Hash` | `u` |
| 17 | `set_timelock` | `tl: Hash` | `u` |
| 18 | `set_guardian` | `g: Address` | `u` |
| 19 | `pause` | `—` | `u` |
| 20 | `unpause` | `—` | `u` |
| 21 | `transfer_admin` | `new_admin: Address` | `u` |
| 22 | `get_miner_total_stake_entry` | `miner_addr: Address` | `u` |
| 23 | `get_version` | `—` | `s` |

## `miner/MinerPool.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_pool` | `name: string, description: string, creator_commission_bps: u64` | `u` |
| 1 | `join_pool` | `pool_id: u64` | `u` |
| 2 | `leave_pool` | `—` | `u` |
| 3 | `kick_member` | `member: Address` | `u` |
| 4 | `distribute_pool_rewards_entry` | `pool_id: u64, amount: u64` | `u` |
| 5 | `claim_pool_rewards` | `—` | `u` |
| 6 | `get_pool_entry` | `pool_id: u64` | `(` |
| 7 | `get_pool_members_entry` | `pool_id: u64` | `u` |
| 8 | `get_pool_reputation_entry` | `pool_id: u64` | `u` |
| 9 | `get_user_pool_entry` | `addr: Address` | `u` |
| 10 | `get_pools_count_entry` | `—` | `u` |
| 11 | `get_pool_pending_rewards_entry` | `pool_id: u64` | `u` |
| 12 | `is_pool_member_entry` | `pool_id: u64, addr: Address` | `b` |
| 13 | `set_miner_contract` | `mc: Hash` | `u` |
| 14 | `set_vlt_asset` | `va: Hash` | `u` |
| 15 | `set_registry` | `reg: Hash` | `u` |
| 16 | `set_timelock` | `tl: Hash` | `u` |
| 17 | `set_emergency` | `e: Address` | `u` |
| 18 | `pause` | `reason: string` | `u` |
| 19 | `unpause` | `—` | `u` |
| 20 | `transfer_admin` | `new_admin: Address` | `u` |
| 21 | `get_version` | `—` | `s` |
| 22 | `request_emergency_withdraw` | `—` | `u` |
| 23 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `miner/XelisVaultMiner.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `register_miner` | `endpoint_url: string, miner_pubkey: Hash, services_mask: u8` | `u` |
| 1 | `enable_service` | `service_id: u8` | `u` |
| 2 | `disable_service` | `service_id: u8` | `u` |
| 3 | `increase_stake` | `amount: u64` | `u` |
| 4 | `decrease_stake` | `amount: u64` | `u` |
| 5 | `deregister_miner` | `—` | `u` |
| 6 | `submit_heartbeat` | `—` | `u` |
| 7 | `get_miner_stake_entry` | `addr: Address` | `u` |
| 8 | `get_miner_reputation_entry` | `addr: Address` | `u` |
| 9 | `get_miners_count_entry` | `—` | `u` |
| 10 | `get_total_staked_entry` | `—` | `u` |
| 11 | `get_base_reward_oracle_entry` | `—` | `u` |
| 12 | `register_service` | `service_id: u8, contract_hash: Hash` | `u` |
| 13 | `unregister_service` | `contract_hash: Hash` | `u` |
| 14 | `set_min_stake` | `amount: u64` | `u` |
| 15 | `set_heartbeat_interval` | `blocks: u64` | `u` |
| 16 | `set_heartbeat_timeout` | `blocks: u64` | `u` |
| 17 | `set_base_reward_chat` | `amount: u64` | `u` |
| 18 | `set_total_budget` | `amount: u64` | `u` |
| 19 | `set_target_duration` | `blocks: u64` | `u` |
| 20 | `set_vlt_contract` | `vc: Hash` | `u` |
| 21 | `set_vlt_asset` | `va: Hash` | `u` |
| 22 | `set_delegation_contract` | `dck: Hash` | `u` |
| 23 | `set_treasury` | `t: Address` | `u` |
| 24 | `set_registry` | `reg: Hash` | `u` |
| 25 | `set_timelock` | `tl: Hash` | `u` |
| 26 | `set_guardian` | `g: Address` | `u` |
| 27 | `set_emergency` | `e: Address` | `u` |
| 28 | `pause` | `reason: string` | `u` |
| 29 | `unpause` | `—` | `u` |
| 30 | `transfer_admin` | `new_admin: Address` | `u` |
| 31 | `get_version` | `—` | `s` |
| 32 | `request_emergency_withdraw` | `—` | `u` |
| 33 | `cancel_emergency_withdraw` | `—` | `u` |
| 34 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 35 | `set_compound` | `enabled: bool` | `u` |
| 36 | `set_rep_decay_params` | `interval: u64, amount: u64` | `u` |
| 37 | `get_active_miners_count_entry` | `—` | `u` |
| 38 | `get_miner_at_entry` | `index: u64` | `A` |
| 39 | `emergency_slash_miner` | `miner_addr: Address, slash_bps: u64, reason: string` | `u` |
| 40 | `emergency_ban_miner` | `miner_addr: Address, reason: string` | `u` |
| 41 | `emergency_freeze_rewards` | `frozen: bool` | `u` |
| 42 | `set_min_stake_entry` | `new_min_stake: u64` | `u` |
| 43 | `set_max_delegation_pct` | `bps: u64` | `u` |
| 44 | `get_miner_own_stake_entry` | `addr: Address` | `u` |
| 45 | `is_rewards_frozen_entry` | `—` | `b` |

## `nft/VaultNFT.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `mint_nft` | `vault_id: u64` | `u` |
| 1 | `transfer_nft` | `nft_id: u64, to: Address` | `u` |
| 2 | `burn_nft` | `nft_id: u64` | `u` |
| 3 | `list_for_sale` | `nft_id: u64, price: u64` | `u` |
| 4 | `cancel_sale` | `nft_id: u64` | `u` |
| 5 | `buy_nft` | `nft_id: u64` | `u` |
| 6 | `make_offer` | `nft_id: u64, price: u64` | `u` |
| 7 | `cancel_offer` | `offer_id: u64` | `u` |
| 8 | `accept_offer` | `offer_id: u64` | `u` |
| 9 | `fractionalize` | `nft_id: u64, share_count: u64` | `u` |
| 10 | `set_vault_engine` | `ve: Hash` | `u` |
| 11 | `set_registry` | `registry: Hash` | `u` |
| 12 | `set_timelock` | `tl: Hash` | `u` |
| 13 | `set_guardian` | `g: Address` | `u` |
| 14 | `pause` | `—` | `u` |
| 15 | `unpause` | `—` | `u` |
| 16 | `transfer_admin` | `new_admin: Address` | `u` |
| 17 | `get_version` | `—` | `s` |

## `notifications/NotificationCenter.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `register_preferences` | `encrypted_push_token: bytes, encrypted_email_hash: Hash, encrypted_telegram_id: bytes, notification_mask: u8, channel_mask: u8, min_severity: u8, quiet_start: u32, quiet_end: u32` | `u` |
| 1 | `update_contact_info` | `encrypted_push_token: bytes, encrypted_telegram_id: bytes` | `u` |
| 2 | `update_notification_prefs` | `notification_mask: u8, channel_mask: u8, min_severity: u8, quiet_start: u32, quiet_end: u32` | `u` |
| 3 | `unsubscribe` | `—` | `u` |
| 4 | `emit_notification_event` | `recipient: Address, notification_type: u8, severity: u8, encrypted_payload: bytes` | `u` |
| 5 | `set_registry` | `registry: Hash` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `set_guardian` | `g: Address` | `u` |
| 8 | `pause` | `—` | `u` |
| 9 | `unpause` | `—` | `u` |
| 10 | `transfer_admin` | `new_admin: Address` | `u` |
| 11 | `get_version` | `—` | `s` |

## `oracle/StakedOracle.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `add_feed_entry` | `name: string, asset: Hash, decimals: u8, min_price: u64, max_price: u64` | `u` |
| 1 | `submit_price` | `feed_id: u64, price: u64` | `u` |
| 2 | `aggregate_now` | `feed_id: u64` | `u` |
| 3 | `get_price_by_feed_entry` | `feed_id: u64` | `u` |
| 4 | `get_price_entry` | `name: string` | `u` |
| 5 | `get_price_for_asset_entry` | `asset: Hash` | `u` |
| 6 | `get_feed_id_entry` | `name: string` | `u` |
| 7 | `disable_bootstrap` | `—` | `u` |
| 8 | `set_bootstrap_min_providers` | `n: u64` | `u` |
| 9 | `set_min_providers` | `n: u64` | `u` |
| 10 | `set_miner_contract` | `mc: Hash` | `u` |
| 11 | `set_delegation_contract` | `dc: Hash` | `u` |
| 12 | `set_registry` | `reg: Hash` | `u` |
| 13 | `set_timelock` | `tl: Hash` | `u` |
| 14 | `set_guardian` | `g: Address` | `u` |
| 15 | `set_emergency` | `e: Address` | `u` |
| 16 | `transfer_admin` | `new_admin: Address` | `u` |
| 17 | `get_version` | `—` | `s` |
| 18 | `set_max_deviation_bps_entry` | `bps: u64` | `u` |
| 19 | `set_cb_threshold_bps_entry` | `bps: u64` | `u` |
| 20 | `set_aggregation_blocks_entry` | `n: u64` | `u` |
| 21 | `set_max_stale_blocks_entry` | `n: u64` | `u` |
| 22 | `set_hard_stale_blocks_entry` | `n: u64` | `u` |
| 23 | `pause_entry` | `reason: string` | `u` |
| 24 | `unpause_entry` | `—` | `u` |
| 25 | `force_update_price` | `feed_id: u64, new_price: u64` | `u` |

## `payroll/Payroll.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `add_employee` | `addr: Address, asset: Hash, rate_per_block: u64, start_topo: u64, end_topo: u64` | `u` |
| 1 | `update_employee` | `addr: Address, rate_per_block: u64, end_topo: u64` | `u` |
| 2 | `remove_employee` | `addr: Address` | `u` |
| 3 | `claim` | `—` | `u` |
| 4 | `set_treasury` | `t: Address` | `u` |
| 5 | `set_registry` | `reg: Hash` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `set_emergency` | `e: Address` | `u` |
| 8 | `pause` | `reason: string` | `u` |
| 9 | `unpause` | `—` | `u` |
| 10 | `transfer_admin` | `new_admin: Address` | `u` |
| 11 | `deposit_funds` | `asset: Hash, amount: u64` | `u` |
| 12 | `get_pending_entry` | `addr: Address` | `u` |
| 13 | `get_employees_count_entry` | `—` | `u` |
| 14 | `get_version` | `—` | `s` |
| 15 | `request_emergency_withdraw` | `—` | `u` |
| 16 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `privacy/PrivacyMixer.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `deposit` | `recipient: Address, asset: Hash, min_anonymity: u64` | `u` |
| 1 | `execute_mix` | `—` | `u` |
| 2 | `execute_refund` | `—` | `u` |
| 3 | `set_min_threshold` | `threshold: u64` | `u` |
| 4 | `set_max_threshold` | `threshold: u64` | `u` |
| 5 | `set_timeout_blocks` | `blocks: u64` | `u` |
| 6 | `set_withdraw_fee_bps` | `bps: u64` | `u` |
| 7 | `set_admin_fee_bps` | `bps: u64` | `u` |
| 8 | `set_admin_fee_addr` | `addr: Address` | `u` |
| 9 | `set_treasury` | `tr: Hash` | `u` |
| 10 | `set_registry` | `reg: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `set_guardian` | `g: Address` | `u` |
| 13 | `pause` | `reason: string` | `u` |
| 14 | `unpause` | `—` | `u` |
| 15 | `transfer_admin` | `new_admin: Address` | `u` |
| 16 | `request_emergency_withdraw` | `—` | `u` |
| 17 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 18 | `get_version` | `—` | `s` |

## `proxy/ContractRegistry.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `get_entry` | `name: string` | `H` |
| 1 | `register` | `name: string, contract_hash: Hash` | `u` |
| 2 | `upgrade` | `name: string, new_hash: Hash` | `u` |
| 3 | `rollback` | `name: string` | `u` |
| 4 | `list_names_entry` | `—` | `u` |
| 5 | `get_name_at_entry` | `index: u64` | `s` |
| 6 | `get_version_entry` | `name: string` | `u` |
| 7 | `get_previous_entry` | `name: string` | `H` |
| 8 | `set_timelock` | `tl: Hash` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `set_emergency` | `e: Address` | `u` |
| 11 | `get_version_str` | `—` | `s` |
| 12 | `request_emergency_withdraw` | `—` | `u` |
| 13 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `revenue/RevenueShare.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `deposit_revenue` | `asset: Hash, amount: u64` | `u` |
| 1 | `claim` | `asset: Hash` | `u` |
| 2 | `set_share_token` | `st: Hash` | `u` |
| 3 | `set_total_supply` | `ts: u64` | `u` |
| 4 | `set_registry` | `reg: Hash` | `u` |
| 5 | `set_timelock` | `tl: Hash` | `u` |
| 6 | `set_emergency` | `e: Address` | `u` |
| 7 | `pause` | `reason: string` | `u` |
| 8 | `unpause` | `—` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `get_claimable_entry` | `addr: Address, asset: Hash` | `u` |
| 11 | `get_total_distributed_entry` | `asset: Hash` | `u` |
| 12 | `get_accum_per_token_entry` | `asset: Hash` | `u` |
| 13 | `get_version` | `—` | `s` |
| 14 | `request_emergency_withdraw` | `—` | `u` |
| 15 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `rwa/AssetVault.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_asset` | `name: string, ticker: string, decimals: u8, max_supply: u64` | `u` |
| 1 | `mint` | `to: Address, amount: u64` | `u` |
| 2 | `transfer_asset` | `to: Address, amount: u64` | `u` |
| 3 | `pause` | `reason: string` | `u` |
| 4 | `unpause` | `—` | `u` |
| 5 | `set_compliance` | `cm: Hash` | `u` |
| 6 | `set_registry` | `reg: Hash` | `u` |
| 7 | `set_timelock` | `tl: Hash` | `u` |
| 8 | `set_emergency` | `e: Address` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `get_asset_info_entry` | `—` | `(` |
| 11 | `get_asset_hash_entry` | `—` | `H` |
| 12 | `get_total_supply_entry` | `—` | `u` |
| 13 | `get_version` | `—` | `s` |
| 14 | `request_emergency_withdraw` | `—` | `u` |
| 15 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `safety/EmergencyShutdown.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `trigger_soft_pause` | `reason: string` | `u` |
| 1 | `trigger_full_shutdown` | `reason: string` | `u` |
| 2 | `propose_recovery` | `proposal_id: u64` | `u` |
| 3 | `execute_recovery` | `—` | `u` |
| 4 | `set_registry` | `registry: Hash` | `u` |
| 5 | `set_timelock` | `tl: Hash` | `u` |
| 6 | `set_guardian` | `g: Address` | `u` |
| 7 | `set_governor` | `gov: Address` | `u` |
| 8 | `transfer_admin` | `new_admin: Address` | `u` |
| 9 | `get_version` | `—` | `s` |

## `savings/SavingsRate.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `deposit` | `amount: u64` | `u` |
| 1 | `withdraw` | `amount: u64` | `u` |
| 2 | `claim_interest` | `—` | `u` |
| 3 | `set_apy_bps` | `apy: u64` | `u` |
| 4 | `pause` | `reason: string` | `u` |
| 5 | `unpause` | `—` | `u` |
| 6 | `set_xusd_contract` | `xc: Hash` | `u` |
| 7 | `set_xusd_asset` | `xa: Hash` | `u` |
| 8 | `set_treasury` | `t: Address` | `u` |
| 9 | `set_registry` | `reg: Hash` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `set_guardian` | `g: Address` | `u` |
| 12 | `set_emergency` | `e: Address` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_balance_entry` | `addr: Address` | `(` |
| 15 | `get_total_deposits_entry` | `—` | `u` |
| 16 | `get_apy_entry` | `—` | `u` |
| 17 | `get_version` | `—` | `s` |
| 18 | `request_emergency_withdraw` | `—` | `u` |
| 19 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `social/SocialTrading.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `make_vault_public` | `vault_id: u64` | `u` |
| 1 | `make_vault_private` | `—` | `u` |
| 2 | `follow_leader` | `leader: Address, ratio_bps: u64` | `u` |
| 3 | `stop_follow` | `leader: Address` | `u` |
| 4 | `emit_leader_action` | `leader: Address, action_type: u8, amount: u64, asset: Hash` | `u` |
| 5 | `set_registry` | `registry: Hash` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `set_guardian` | `g: Address` | `u` |
| 8 | `pause` | `—` | `u` |
| 9 | `unpause` | `—` | `u` |
| 10 | `transfer_admin` | `new_admin: Address` | `u` |
| 11 | `get_version` | `—` | `s` |

## `token/VLTToken.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `burn_own` | `amount: u64` | `u` |
| 1 | `mint_batch` | `recipients: Address[], amounts: u64[]` | `u` |
| 2 | `set_minter` | `contract_hash: Hash, enabled: bool` | `u` |
| 3 | `set_burner` | `contract_hash: Hash, enabled: bool` | `u` |
| 4 | `create_asset` | `—` | `u` |
| 5 | `set_registry` | `reg: Hash` | `u` |
| 6 | `set_timelock` | `tl: Hash` | `u` |
| 7 | `transfer_admin` | `new_admin: Address` | `u` |
| 8 | `set_emergency` | `e: Address` | `u` |
| 9 | `get_version` | `—` | `s` |
| 10 | `get_asset_hash_entry` | `—` | `H` |
| 11 | `get_max_supply_entry` | `—` | `u` |
| 12 | `get_total_burned_entry` | `—` | `u` |
| 13 | `get_circulating_supply_entry` | `—` | `u` |
| 14 | `request_emergency_withdraw` | `—` | `u` |
| 15 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 16 | `mint_to_entry` | `to: Address, amount: u64` | `u` |

## `treasury/TreasuryVault.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `propose` | `asset: Hash, to: Address, amount: u64, data: bytes` | `u` |
| 1 | `confirm` | `proposal_id: u64` | `u` |
| 2 | `revoke` | `proposal_id: u64` | `u` |
| 3 | `execute` | `proposal_id: u64` | `u` |
| 4 | `add_signer` | `new_signer: Address` | `u` |
| 5 | `remove_signer` | `signer: Address` | `u` |
| 6 | `set_quorum` | `new_quorum: u64` | `u` |
| 7 | `deposit` | `asset: Hash, amount: u64` | `u` |
| 8 | `pause` | `reason: string` | `u` |
| 9 | `unpause` | `—` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `set_emergency` | `e: Address` | `u` |
| 12 | `transfer_admin` | `new_admin: Address` | `u` |
| 13 | `get_proposal_entry` | `proposal_id: u64` | `(` |
| 14 | `get_signers_entry` | `—` | `(` |
| 15 | `is_signer_entry` | `addr: Address` | `b` |
| 16 | `get_balance_entry` | `asset: Hash` | `u` |
| 17 | `get_proposals_count_entry` | `—` | `u` |
| 18 | `get_version` | `—` | `s` |
| 19 | `request_emergency_withdraw` | `—` | `u` |
| 20 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `usd/xUSD.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_asset` | `—` | `u` |
| 1 | `transfer_tokens` | `to: Address, amount: u64` | `u` |
| 2 | `get_asset_info` | `—` | `(` |
| 3 | `set_vault_contract` | `contract_hash: Hash` | `u` |
| 4 | `set_timelock` | `tl: Hash` | `u` |
| 5 | `transfer_admin` | `new_admin: Address` | `u` |
| 6 | `set_psm` | `hash: Hash` | `u` |
| 7 | `set_emergency` | `e: Address` | `u` |
| 8 | `emergency_withdraw` | `—` | `u` |
| 9 | `set_savings` | `hash: Hash` | `u` |
| 10 | `set_minter` | `contract_hash: Hash, enabled: bool` | `u` |
| 11 | `set_burner` | `contract_hash: Hash, enabled: bool` | `u` |
| 12 | `set_registry` | `reg: Hash` | `u` |
| 13 | `get_version` | `—` | `s` |
| 14 | `get_asset_hash_entry` | `—` | `H` |
| 15 | `get_asset_info_entry` | `—` | `(` |
| 16 | `get_balance_entry` | `addr: Address` | `u` |
| 17 | `request_emergency_withdraw` | `—` | `u` |
| 18 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `vault/MultiCollateralVault.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `create_multi_vault` | `—` | `u` |
| 1 | `add_collateral` | `vault_id: u64, asset: Hash, amount: u64` | `u` |
| 2 | `remove_collateral` | `vault_id: u64, asset: Hash, amount: u64, current_total_collateral_value: u64` | `u` |
| 3 | `borrow_multi` | `vault_id: u64, borrow_amount: u64, total_collateral_value: u64` | `u` |
| 4 | `repay_multi` | `vault_id: u64, repay_amount: u64` | `u` |
| 5 | `liquidate_multi` | `vault_id: u64, current_total_collateral_value: u64` | `u` |
| 6 | `set_asset_ltv` | `asset_name: string, ltv_bps: u64` | `u` |
| 7 | `set_registry` | `registry: Hash` | `u` |
| 8 | `set_timelock` | `tl: Hash` | `u` |
| 9 | `set_guardian` | `g: Address` | `u` |
| 10 | `pause` | `—` | `u` |
| 11 | `unpause` | `—` | `u` |
| 12 | `transfer_admin` | `new_admin: Address` | `u` |
| 13 | `get_version` | `—` | `s` |

## `vault/VaultEngineV3.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `deposit` | `collateral_asset: Hash, collateral_amount: u64, salt: Hash` | `u` |
| 1 | `borrow` | `vault_id: u64, amount: u64` | `u` |
| 2 | `repay` | `vault_id: u64, amount: u64` | `u` |
| 3 | `withdraw` | `vault_id: u64, amount: u64` | `u` |
| 4 | `liquidate` | `vault_id: u64, max_borrow_to_repay: u64` | `u` |
| 5 | `redeem` | `xusd_amount: u64` | `u` |
| 6 | `get_health_factor_entry` | `vault_id: u64` | `u` |
| 7 | `total_vaults_entry` | `—` | `u` |
| 8 | `redemption_queue_size_entry` | `—` | `u` |
| 9 | `get_vault_entry` | `vault_id: u64` | `(` |
| 10 | `get_accrued_borrow_entry` | `vault_id: u64` | `u` |
| 11 | `get_config_public_entry` | `—` | `(` |
| 12 | `get_stability_fee_index_entry` | `—` | `u` |
| 13 | `pause` | `reason: string` | `u` |
| 14 | `unpause` | `—` | `u` |
| 15 | `set_min_cr_bps` | `cr: u64` | `u` |
| 16 | `set_liq_penalty_bps` | `p: u64` | `u` |
| 17 | `set_protocol_fee_bps` | `f: u64` | `u` |
| 18 | `set_insurance_fee_bps` | `f: u64` | `u` |
| 19 | `set_redemption_fee_bps` | `f: u64` | `u` |
| 20 | `set_grace_period_blocks` | `p: u64` | `u` |
| 21 | `set_stability_fee_bps` | `bps: u64` | `u` |
| 22 | `set_queue_cap` | `cap: u64` | `u` |
| 23 | `set_registry` | `reg: Hash` | `u` |
| 24 | `set_xusd_contract` | `xc: Hash` | `u` |
| 25 | `set_xusd_asset` | `xa: Hash` | `u` |
| 26 | `set_treasury` | `t: Address` | `u` |
| 27 | `set_insurance_pool` | `ic: Hash` | `u` |
| 28 | `set_timelock` | `tl: Hash` | `u` |
| 29 | `set_guardian` | `g: Address` | `u` |
| 30 | `transfer_admin` | `new_admin: Address` | `u` |
| 31 | `set_emergency` | `e: Address` | `u` |
| 32 | `get_version` | `—` | `s` |
| 33 | `is_paused` | `—` | `b` |
| 34 | `request_emergency_withdraw` | `—` | `u` |
| 35 | `execute_emergency_withdraw` | `asset: Hash` | `u` |
| 36 | `deposit_confidential` | `collateral_cipher: Ciphertext, collateral_proof: RangeProof` | `u` |
| 37 | `borrow_confidential` | `vault_id: u64, borrow_cipher: Ciphertext, borrow_proof: RangeProof, collateral_proof: RangeProof` | `u` |
| 38 | `repay_confidential` | `vault_id: u64, repay_cipher: Ciphertext, repay_proof: RangeProof` | `u` |
| 39 | `update_channel_meta` | `channel_id: u64, encrypted_meta: EncryptedChannelMeta` | `u` |

## `vault/VaultTemplates.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `execute_safe_vault` | `collateral_amount: u64, min_borrow_out: u64` | `u` |
| 1 | `execute_leverage_loop` | `initial_collateral: u64, min_final_collateral: u64` | `u` |
| 2 | `execute_yield_farmer` | `collateral_amount: u64, min_borrow_out: u64` | `u` |
| 3 | `execute_psm_arbitrage` | `amount: u64, current_xusd_price_cents: u64` | `u` |
| 4 | `execute_lp_strategy` | `collateral_amount: u64, min_borrow_out: u64` | `u` |
| 5 | `emergency_exit` | `execution_id: u64` | `u` |
| 6 | `set_vault_engine` | `ve: Hash` | `u` |
| 7 | `set_psm` | `psm: Hash` | `u` |
| 8 | `set_vault_swap` | `vs: Hash` | `u` |
| 9 | `set_savings_rate` | `sr: Hash` | `u` |
| 10 | `set_registry` | `registry: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `set_guardian` | `g: Address` | `u` |
| 13 | `pause` | `—` | `u` |
| 14 | `unpause` | `—` | `u` |
| 15 | `transfer_admin` | `new_admin: Address` | `u` |
| 16 | `get_version` | `—` | `s` |

## `vault/YieldOptimizer.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `opt_in` | `amount: u64, strategy: u8` | `u` |
| 1 | `opt_out` | `—` | `u` |
| 2 | `set_strategy` | `new_strategy: u8` | `u` |
| 3 | `execute_strategy` | `user: Address, savings_apr_bps: u64, lending_apr_bps: u64, gov_apr_bps: u64` | `u` |
| 4 | `reinvest_rewards` | `user: Address, rewards_amount: u64` | `u` |
| 5 | `claim_rewards` | `—` | `u` |
| 6 | `set_savings_rate` | `sr: Hash` | `u` |
| 7 | `set_lending_market` | `lm: Hash` | `u` |
| 8 | `set_gov_vault` | `gv: Hash` | `u` |
| 9 | `set_registry` | `registry: Hash` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `set_guardian` | `g: Address` | `u` |
| 12 | `pause` | `—` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `transfer_admin` | `new_admin: Address` | `u` |
| 15 | `get_version` | `—` | `s` |
