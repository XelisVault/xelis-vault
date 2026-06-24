# ENTRY IDs — XELIS Vault v5.0

Auto-generated from `contracts/` by `scripts/extract_entry_ids.py`.

Each `entry` function gets a sequential ID starting at 0 in declaration order.
**Total entry functions across 33 contracts:** 630

`pub fn` and `fn` do NOT count for ID numbering — they are not callable via `Contract::call`.


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
| 21 | `set_xusd_asset` | `xa: Hash` | `u` |
| 22 | `set_xusd_contract` | `xc: Hash` | `u` |
| 23 | `set_treasury` | `t: Address` | `u` |
| 24 | `set_timelock` | `tl: Hash` | `u` |
| 25 | `set_guardian` | `g: Address` | `u` |
| 26 | `set_emergency` | `e: Address` | `u` |
| 27 | `transfer_admin` | `new_admin: Address` | `u` |
| 28 | `get_version` | `—` | `s` |
| 29 | `request_emergency_withdraw` | `—` | `u` |
| 30 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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
| 4 | `anchor_messages` | `merkle_root: Hash, message_count: u64, msg_type: u8` | `u` |
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

## `compliance/ComplianceModule.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `check_transfer_entry` | `from: Address, to: Address, asset: Hash, amount: u64` | `b` |
| 1 | `verify_proof_entry` | `merkle_proof: Hash, merkle_root: Hash` | `b` |
| 2 | `is_compliant_entry` | `addr: Address` | `b` |
| 3 | `get_current_root_entry` | `—` | `H` |
| 4 | `get_verifiers_count_entry` | `—` | `u` |
| 5 | `update_merkle_root` | `new_root: Hash` | `u` |
| 6 | `mark_compliant` | `addr: Address, compliant: bool` | `u` |
| 7 | `add_verifier` | `verifier: Address` | `u` |
| 8 | `remove_verifier` | `verifier: Address` | `u` |
| 9 | `set_compliance_required` | `asset: Hash, required: bool` | `u` |
| 10 | `set_registry` | `reg: Hash` | `u` |
| 11 | `set_timelock` | `tl: Hash` | `u` |
| 12 | `pause` | `reason: string` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `transfer_admin` | `new_admin: Address` | `u` |
| 15 | `get_version` | `—` | `s` |

## `faucet/FaucetContract.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `claim_both` | `—` | `u` |
| 1 | `refill_xel` | `amount: u64` | `u` |
| 2 | `refill_vlt` | `amount: u64` | `u` |
| 3 | `set_claim_amounts` | `xel_amt: u64, vlt_amt: u64` | `u` |
| 4 | `set_cooldown_blocks` | `n: u64` | `u` |
| 5 | `set_daily_caps` | `xel_cap: u64, vlt_cap: u64` | `u` |
| 6 | `set_lifetime_caps` | `xel_cap: u64, vlt_cap: u64` | `u` |
| 7 | `pause` | `reason: string` | `u` |
| 8 | `unpause` | `—` | `u` |
| 9 | `set_vlt_asset` | `va: Hash` | `u` |
| 10 | `set_vlt_contract` | `vc: Hash` | `u` |
| 11 | `set_guardian` | `g: Address` | `u` |
| 12 | `set_emergency` | `e: Address` | `u` |
| 13 | `transfer_admin` | `new_admin: Address` | `u` |
| 14 | `get_faucet_info_entry` | `—` | `(` |
| 15 | `get_user_claims_entry` | `addr: Address` | `(` |
| 16 | `get_faucet_vlt_balance_entry` | `—` | `u` |
| 17 | `get_version` | `—` | `s` |
| 18 | `request_emergency_withdraw` | `—` | `u` |
| 19 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `flashloan/FlashCallback.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `on_flash_loan` | `asset: Hash, amount: u64, fee: u64, caller: Address, data: bytes` | `u` |
| 1 | `claim_profit` | `asset: Hash` | `u` |
| 2 | `set_flash_loan` | `fl: Hash` | `u` |
| 3 | `set_registry` | `reg: Hash` | `u` |
| 4 | `transfer_admin` | `new_admin: Address` | `u` |
| 5 | `get_version` | `—` | `s` |

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

## `governance/GovernanceVault.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `stake` | `amount: u64, lock_days: u64` | `u` |
| 1 | `unstake` | `stake_id: u64` | `u` |
| 2 | `claim_rewards` | `—` | `u` |
| 3 | `get_voting_power_entry` | `addr: Address` | `u` |
| 4 | `get_total_voting_power_entry` | `—` | `u` |
| 5 | `get_total_staked_entry` | `—` | `u` |
| 6 | `get_user_staked_entry` | `addr: Address` | `u` |
| 7 | `get_stakes_count_entry` | `—` | `u` |
| 8 | `notify_reward_amount` | `amount: u64` | `u` |
| 9 | `set_reward_distributor` | `contract_hash: Hash, enabled: bool` | `u` |
| 10 | `set_vlt_contract` | `vc: Hash` | `u` |
| 11 | `set_vlt_asset` | `va: Hash` | `u` |
| 12 | `set_registry` | `reg: Hash` | `u` |
| 13 | `set_timelock` | `tl: Hash` | `u` |
| 14 | `pause` | `reason: string` | `u` |
| 15 | `unpause` | `—` | `u` |
| 16 | `transfer_admin` | `new_admin: Address` | `u` |
| 17 | `set_emergency` | `e: Address` | `u` |
| 18 | `get_version` | `—` | `s` |
| 19 | `request_emergency_withdraw` | `—` | `u` |
| 20 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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
| 0 | `submit_proposal` | `target: Hash, entry_id: u16, params: bytes, delay: u64` | `u` |
| 1 | `execute_proposal` | `proposal_id: u64` | `u` |
| 2 | `cancel_proposal` | `proposal_id: u64` | `u` |
| 3 | `submit_emergency_proposal` | `target: Hash, entry_id: u16, params: bytes` | `u` |
| 4 | `set_min_delay` | `delay: u64` | `u` |
| 5 | `set_max_delay` | `delay: u64` | `u` |
| 6 | `set_governor` | `gov: Hash` | `u` |
| 7 | `set_guardian` | `g: Address` | `u` |
| 8 | `set_guardian_contract` | `gc: Hash` | `u` |
| 9 | `set_emergency` | `e: Address` | `u` |
| 10 | `transfer_admin` | `new_admin: Address` | `u` |
| 11 | `get_version` | `—` | `s` |
| 12 | `request_emergency_withdraw` | `—` | `u` |
| 13 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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
| 7 | `slash_miner` | `miner_addr: Address, severity: u8, reporter: Address` | `u` |
| 8 | `distribute_reward` | `miner_addr: Address, service_id: u8, is_valid: bool` | `u` |
| 9 | `is_miner_active_entry` | `addr: Address, service_id: u8` | `u` |
| 10 | `get_miner_stake_entry` | `addr: Address` | `u` |
| 11 | `get_miner_reputation_entry` | `addr: Address` | `u` |
| 12 | `get_active_miners_for_service_entry` | `service_id: u8` | `u` |
| 13 | `get_miners_count_entry` | `—` | `u` |
| 14 | `get_total_staked_entry` | `—` | `u` |
| 15 | `get_base_reward_oracle_entry` | `—` | `u` |
| 16 | `register_service` | `service_id: u8, contract_hash: Hash` | `u` |
| 17 | `unregister_service` | `contract_hash: Hash` | `u` |
| 18 | `set_min_stake` | `amount: u64` | `u` |
| 19 | `set_heartbeat_interval` | `blocks: u64` | `u` |
| 20 | `set_heartbeat_timeout` | `blocks: u64` | `u` |
| 21 | `set_base_reward_oracle` | `amount: u64` | `u` |
| 22 | `set_base_reward_chat` | `amount: u64` | `u` |
| 23 | `set_total_budget` | `amount: u64` | `u` |
| 24 | `set_target_duration` | `blocks: u64` | `u` |
| 25 | `set_vlt_contract` | `vc: Hash` | `u` |
| 26 | `set_vlt_asset` | `va: Hash` | `u` |
| 27 | `set_treasury` | `t: Address` | `u` |
| 28 | `set_registry` | `reg: Hash` | `u` |
| 29 | `set_timelock` | `tl: Hash` | `u` |
| 30 | `set_guardian` | `g: Address` | `u` |
| 31 | `set_emergency` | `e: Address` | `u` |
| 32 | `pause` | `reason: string` | `u` |
| 33 | `unpause` | `—` | `u` |
| 34 | `transfer_admin` | `new_admin: Address` | `u` |
| 35 | `get_version` | `—` | `s` |
| 36 | `request_emergency_withdraw` | `—` | `u` |
| 37 | `cancel_emergency_withdraw` | `—` | `u` |
| 38 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

## `oracle/StakedOracle.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `add_feed` | `name: string, asset: Hash, decimals: u8, min_price: u64, max_price: u64` | `u` |
| 1 | `update_feed` | `feed_id: u64, min_price: u64, max_price: u64, decimals: u8` | `u` |
| 2 | `set_feed_active` | `feed_id: u64, active: bool` | `u` |
| 3 | `trigger_feed_cb` | `feed_id: u64, reason: string` | `u` |
| 4 | `reset_feed_cb` | `feed_id: u64` | `u` |
| 5 | `submit_price` | `feed_id: u64, price: u64` | `u` |
| 6 | `aggregate_now` | `feed_id: u64` | `u` |
| 7 | `get_price_by_feed_entry` | `feed_id: u64` | `u` |
| 8 | `get_price_entry` | `name: string` | `u` |
| 9 | `get_price_for_asset_entry` | `asset: Hash` | `u` |
| 10 | `get_feed_id_entry` | `name: string` | `u` |
| 11 | `pause` | `reason: string` | `u` |
| 12 | `unpause` | `—` | `u` |
| 13 | `set_max_deviation_bps` | `bps: u64` | `u` |
| 14 | `set_cb_threshold_bps` | `bps: u64` | `u` |
| 15 | `set_aggregation_blocks` | `n: u64` | `u` |
| 16 | `set_max_stale_blocks` | `n: u64` | `u` |
| 17 | `set_hard_stale_blocks` | `n: u64` | `u` |
| 18 | `disable_bootstrap` | `—` | `u` |
| 19 | `set_bootstrap_min_providers` | `n: u64` | `u` |
| 20 | `set_min_providers` | `n: u64` | `u` |
| 21 | `set_miner_contract` | `mc: Hash` | `u` |
| 22 | `set_registry` | `reg: Hash` | `u` |
| 23 | `set_timelock` | `tl: Hash` | `u` |
| 24 | `set_guardian` | `g: Address` | `u` |
| 25 | `set_emergency` | `e: Address` | `u` |
| 26 | `transfer_admin` | `new_admin: Address` | `u` |
| 27 | `get_version` | `—` | `s` |

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
| 0 | `deposit` | `asset: Hash, denomination_id: u64, commitment: Hash` | `u` |
| 1 | `withdraw` | `asset: Hash, denomination_id: u64, nullifier: Hash, recipient: Address, merkle_root: Hash, zk_proof: bytes` | `u` |
| 2 | `get_merkle_root_entry` | `—` | `H` |
| 3 | `get_deposit_count_entry` | `—` | `u` |
| 4 | `is_nullifier_used_entry` | `nullifier: Hash` | `b` |
| 5 | `get_denomination_amount_entry` | `denom_id: u64` | `u` |
| 6 | `get_deposit_count_for_denom_entry` | `asset: Hash, denom_id: u64` | `u` |
| 7 | `get_merkle_leaf_entry` | `level: u64, index: u64` | `H` |
| 8 | `set_zk_verifier` | `zv: Hash` | `u` |
| 9 | `set_registry` | `reg: Hash` | `u` |
| 10 | `set_timelock` | `tl: Hash` | `u` |
| 11 | `set_guardian` | `g: Address` | `u` |
| 12 | `pause` | `reason: string` | `u` |
| 13 | `unpause` | `—` | `u` |
| 14 | `transfer_admin` | `new_admin: Address` | `u` |
| 15 | `get_version` | `—` | `s` |
| 16 | `request_emergency_withdraw` | `—` | `u` |
| 17 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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

## `proxy/Upgradeable.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `migrate_from` | `prev_hash: Hash` | `u` |
| 1 | `get_version` | `—` | `s` |

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

## `token/VLTToken.slx`

| ID | Name | Parameters | Return |
|----|------|------------|--------|
| 0 | `mint_to` | `to: Address, amount: u64` | `u` |
| 1 | `burn_own` | `amount: u64` | `u` |
| 2 | `mint_batch` | `recipients: Address[], amounts: u64[]` | `u` |
| 3 | `set_minter` | `contract_hash: Hash, enabled: bool` | `u` |
| 4 | `set_burner` | `contract_hash: Hash, enabled: bool` | `u` |
| 5 | `create_asset` | `—` | `u` |
| 6 | `set_registry` | `reg: Hash` | `u` |
| 7 | `set_timelock` | `tl: Hash` | `u` |
| 8 | `transfer_admin` | `new_admin: Address` | `u` |
| 9 | `set_emergency` | `e: Address` | `u` |
| 10 | `get_version` | `—` | `s` |
| 11 | `get_asset_hash_entry` | `—` | `H` |
| 12 | `get_max_supply_entry` | `—` | `u` |
| 13 | `get_total_burned_entry` | `—` | `u` |
| 14 | `get_circulating_supply_entry` | `—` | `u` |
| 15 | `request_emergency_withdraw` | `—` | `u` |
| 16 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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
| 1 | `mint_tokens` | `to: Address, amount: u64` | `u` |
| 2 | `mint_split` | `to: Address, amount: u64, treasury: Address, fee: u64` | `u` |
| 3 | `burn_tokens` | `amount: u64` | `u` |
| 4 | `transfer_tokens` | `to: Address, amount: u64` | `u` |
| 5 | `set_minter` | `contract_hash: Hash, enabled: bool` | `u` |
| 6 | `set_burner` | `contract_hash: Hash, enabled: bool` | `u` |
| 7 | `set_registry` | `reg: Hash` | `u` |
| 8 | `set_timelock` | `tl: Hash` | `u` |
| 9 | `transfer_admin` | `new_admin: Address` | `u` |
| 10 | `set_emergency` | `e: Address` | `u` |
| 11 | `get_version` | `—` | `s` |
| 12 | `get_asset_hash_entry` | `—` | `H` |
| 13 | `get_asset_info_entry` | `—` | `(` |
| 14 | `get_balance_entry` | `addr: Address` | `u` |
| 15 | `request_emergency_withdraw` | `—` | `u` |
| 16 | `execute_emergency_withdraw` | `asset: Hash` | `u` |

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
