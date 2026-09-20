#!/usr/bin/env python3
"""
airdrop_indexer.py — Bot that listens to XELIS Vault contract events
and records user activities to AirdropTracker.

This bot runs off-chain and:
  1. Listens to events emitted by VaultEngine, VaultSwap, PSM, Governor, etc.
  2. Calls AirdropTracker.record_*() for each user action
  3. Handles contracts that don't directly call AirdropTracker

Usage:
    python3 scripts/airdrop_indexer.py \\
        --rpc http://testnet-rpc.xelis.io \\
        --tracker <airdrop_tracker_contract_hash> \\
        --wallet <your_wallet_name>

The wallet must be authorized as a recorder in AirdropTracker
(admin must call set_authorized_recorder(wallet_address, true)).
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("airdrop_indexer")


# Events to listen for, mapped to AirdropTracker record_* calls
EVENT_MAPPING = {
    # Mining events
    "PriceSubmitted": {
        "contract": "StakedOracle",
        "record_fn": "record_mining_activity",
        "extract": lambda e: {
            "miner": e["miner"],
            "valid_submissions": 1,
            "runtime_blocks": 0,
        },
    },
    "MinerRegistered": {
        "contract": "XelisVaultMiner",
        "record_fn": "record_mining_activity",
        "extract": lambda e: {
            "miner": e["miner"],
            "valid_submissions": 0,
            "runtime_blocks": 720,  # 1 hour of uptime assumed
        },
    },
    "HeartbeatSubmitted": {
        "contract": "XelisVaultMiner",
        "record_fn": "record_mining_activity",
        "extract": lambda e: {
            "miner": e["miner"],
            "valid_submissions": 0,
            "runtime_blocks": 720,  # 1 hour
        },
    },

    # Chat events
    "MessagesAnchored": {
        "contract": "VaultChat",
        "record_fn": "record_relayer_activity",
        "extract": lambda e: {
            "relayer": e["relayer"],
            "valid_anchors": 1,
            "uptime_blocks": 0,
        },
    },
    "MessageStored": {
        "contract": "VaultChat",
        "record_fn": "record_chat_message",
        "extract": lambda e: {
            "sender": e["sender"],
        },
    },
    "GroupCreated": {
        "contract": "VaultChat",
        "record_fn": "record_chat_group_created",
        "extract": lambda e: {
            "creator": e["creator"],
        },
    },

    # Governance events
    "VoteCast": {
        "contract": "Governor",
        "record_fn": "record_governance_vote",
        "extract": lambda e: {
            "voter": e["voter"],
            "proposal_id": e["proposal_id"],
        },
    },
    "ProposalCreated": {
        "contract": "Governor",
        "record_fn": "record_governance_proposal",
        "extract": lambda e: {
            "proposer": e["proposer"],
            "proposal_id": e["proposal_id"],
        },
    },

    # Liquidity events
    "Deposit": {
        "contract": "VaultEngineV3",
        "record_fn": "record_liquidity_provided",
        "extract": lambda e: {
            "user": e["user"],
            "xel_amount": e["amount"],
        },
    },
    "LiquidityAdded": {
        "contract": "VaultSwapV2",
        "record_fn": "record_liquidity_provided",
        "extract": lambda e: {
            "user": e["provider"],
            "xel_amount": e["xel_amount"],
        },
    },
    "PSMMint": {
        "contract": "PSM",
        "record_fn": "record_liquidity_provided",
        "extract": lambda e: {
            "user": e["user"],
            "xel_amount": e["xel_amount"],
        },
    },
}


class AirdropIndexer:
    """Listens to events and records them to AirdropTracker."""

    def __init__(self, rpc_url: str, tracker_hash: str, wallet: str):
        self.rpc_url = rpc_url
        self.tracker_hash = tracker_hash
        self.wallet = wallet
        self.last_topo = 0
        self.processed_events = set()

        log.info(f"Initialized indexer")
        log.info(f"  RPC: {rpc_url}")
        log.info(f"  Tracker: {tracker_hash}")
        log.info(f"  Wallet: {wallet}")

    def get_topoheight(self) -> int:
        """Get current topoheight from XELIS daemon."""
        # In production: JSON-RPC call to xelis-daemon
        # curl -X POST http://testnet-rpc.xelis.io -H "Content-Type: application/json"
        #   -d '{"jsonrpc":"2.0","method":"get_topoheight","params":[],"id":1}'
        return 0

    def get_new_events(self, from_topo: int, to_topo: int) -> list:
        """Fetch new events from contracts in the topo range."""
        # In production: query each contract's events via JSON-RPC
        # For now, return empty list
        return []

    def record_to_tracker(self, record_fn: str, params: dict) -> bool:
        """Call AirdropTracker.record_*() with the given params."""
        # In production: build a transaction calling the tracker contract
        # entry record_fn with params, sign with wallet, submit
        log.info(f"  → record {record_fn}({params})")
        return True

    def process_event(self, event: dict) -> bool:
        """Process a single event and record it to AirdropTracker."""
        event_type = event.get("type")
        event_data = event.get("data", {})

        if event_type not in EVENT_MAPPING:
            return False

        mapping = EVENT_MAPPING[event_type]
        params = mapping["extract"](event_data)
        record_fn = mapping["record_fn"]

        return self.record_to_tracker(record_fn, params)

    def run_loop(self, poll_interval: int = 10):
        """Main loop: poll for new events every poll_interval seconds."""
        log.info(f"Starting indexer loop (poll every {poll_interval}s)")

        while True:
            try:
                current_topo = self.get_topoheight()
                if current_topo <= self.last_topo:
                    time.sleep(poll_interval)
                    continue

                log.info(f"Scanning blocks {self.last_topo} → {current_topo}")

                events = self.get_new_events(self.last_topo, current_topo)
                log.info(f"Found {len(events)} events to process")

                processed = 0
                for event in events:
                    event_id = f"{event.get('topo', 0)}_{event.get('tx_hash', '')}"
                    if event_id in self.processed_events:
                        continue

                    if self.process_event(event):
                        self.processed_events.add(event_id)
                        processed += 1

                log.info(f"Processed {processed} new events")
                self.last_topo = current_topo

                # Sleep before next poll
                time.sleep(poll_interval)

            except KeyboardInterrupt:
                log.info("Shutting down indexer (Ctrl+C)")
                break
            except Exception as e:
                log.error(f"Error in main loop: {e}")
                time.sleep(poll_interval * 2)


def main():
    parser = argparse.ArgumentParser(
        description="XELIS Vault Airdrop Indexer — records user activities to AirdropTracker"
    )
    parser.add_argument(
        "--rpc",
        default="http://testnet-rpc.xelis.io",
        help="XELIS testnet RPC URL",
    )
    parser.add_argument(
        "--tracker",
        required=True,
        help="AirdropTracker contract hash",
    )
    parser.add_argument(
        "--wallet",
        required=True,
        help="Wallet name (must be authorized recorder)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Poll interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--from-topo",
        type=int,
        default=0,
        help="Start from this topoheight (default: 0 = from current)",
    )

    args = parser.parse_args()

    indexer = AirdropIndexer(args.rpc, args.tracker, args.wallet)
    indexer.last_topo = args.from_topo

    indexer.run_loop(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
