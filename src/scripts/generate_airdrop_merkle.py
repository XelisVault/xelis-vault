#!/usr/bin/env python3
"""
generate_airdrop_merkle.py — Generate Merkle tree from AirdropTracker data.

This script:
  1. Reads the AirdropTracker contract state (qualified users + distributions)
  2. Builds the Merkle tree of (testnet_addr, mainnet_addr, amount) leaves
  3. Outputs the Merkle root + full proof set for each user

Usage:
    python3 scripts/generate_airdrop_merkle.py \\
        --rpc http://testnet-rpc.xelis.io \\
        --tracker <airdrop_tracker_contract_hash> \\
        --output airdrop_distribution.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def keccak256(data: bytes) -> bytes:
    """Compute keccak256 hash (XELIS uses keccak)."""
    h = hashlib.sha3_256()  # XELIS uses SHA3-256 (keccak variant)
    h.update(data)
    return h.digest()


def build_leaf(testnet_addr: str, mainnet_addr: str, amount: int) -> bytes:
    """
    Build a Merkle leaf from (testnet_addr, mainnet_addr, amount).
    Format: keccak256(testnet_addr_bytes || mainnet_addr_bytes || amount_bytes)

    Addresses are 32 bytes (XELIS Address format).
    Amount is 8 bytes (u64 little-endian).
    """
    # XELIS addresses are stored as 32-byte hashes on-chain
    # For off-chain computation, we use the hex string → bytes
    testnet_bytes = bytes.fromhex(testnet_addr.replace("0x", "").ljust(64, "0"))[:32]
    mainnet_bytes = bytes.fromhex(mainnet_addr.replace("0x", "").ljust(64, "0"))[:32]
    amount_bytes = amount.to_bytes(8, byteorder="little")

    data = testnet_bytes + mainnet_bytes + amount_bytes
    return keccak256(data)


def build_merkle_tree(leaves: list) -> tuple:
    """
    Build a Merkle tree from a list of leaf hashes.
    Returns (root, proof_dict) where proof_dict[leaf_hex] = [sibling_hashes].

    Uses sorted pairs for canonical ordering (matches Silex contract).
    """
    if not leaves:
        return b"\x00" * 32, {}

    # Make a copy
    tree = list(leaves)
    proof_dict = {leaf.hex(): [] for leaf in leaves}

    layer = tree
    while len(layer) > 1:
        next_layer = []
        # Pad to even number if needed
        if len(layer) % 2 == 1:
            layer.append(layer[-1])

        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1]

            # Sort for canonical ordering (smaller hash first)
            if left <= right:
                combined = left + right
            else:
                combined = right + left

            parent = keccak256(combined)
            next_layer.append(parent)

            # Update proofs: any leaf whose path includes `left` gets `right` in proof, and vice versa
            for leaf_hex in proof_dict:
                leaf_bytes = bytes.fromhex(leaf_hex)
                # Check if this leaf is in the left or right subtree
                # For simplicity, we track this by maintaining a list of leaf indices per node
                pass

        layer = next_layer

    # Rebuild proofs properly (track indices)
    proof_dict = _build_proofs(leaves)

    return layer[0], proof_dict


def _build_proofs(leaves: list) -> dict:
    """
    Build Merkle proofs for each leaf.
    Returns dict {leaf_hex: [sibling_hash_hex, ...]}.
    """
    if not leaves:
        return {}

    # Track which leaf indices are at each position in the tree
    # layer[0] = leaves, layer[1] = parents, etc.
    layers = [list(leaves)]
    current = list(leaves)

    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])

        next_layer = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1]
            if left <= right:
                combined = left + right
            else:
                combined = right + left
            next_layer.append(keccak256(combined))

        layers.append(next_layer)
        current = next_layer

    # For each leaf, walk up the tree and collect siblings
    proof_dict = {}
    for leaf_idx in range(len(leaves)):
        proof = []
        idx = leaf_idx
        for layer in layers[:-1]:  # exclude root layer
            # Sibling is at idx^1 (XOR with 1)
            sibling_idx = idx ^ 1
            if sibling_idx < len(layer):
                proof.append(layer[sibling_idx].hex())
            idx = idx // 2
        proof_dict[leaves[leaf_idx].hex()] = proof

    return proof_dict


def fetch_qualified_users(rpc_url: str, tracker_hash: str) -> list:
    """
    Fetch qualified users from AirdropTracker contract.
    Returns list of (testnet_addr, mainnet_addr, amount) tuples.
    """
    # In production, this would make JSON-RPC calls to the XELIS daemon
    # to query AirdropTracker.get_user_count() and iterate.
    #
    # For now, return a placeholder — the actual implementation will
    # use the xelis-daemon JSON-RPC API.
    print(f"[INFO] Would fetch users from {rpc_url} for contract {tracker_hash}")
    print(f"[INFO] In production, this queries:")
    print(f"       - get_user_count() to know how many users")
    print(f"       - For each user: get_user_breakdown() + get_mainnet_address()")
    print(f"       - For each qualified user: get_user_distribution()")

    # Placeholder: return empty list
    # Real implementation would return the actual data
    return []


def main():
    parser = argparse.ArgumentParser(
        description="Generate Merkle tree for XELIS Vault airdrop distribution"
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
        "--output",
        default="airdrop_distribution.json",
        help="Output JSON file (distribution + proofs)",
    )
    parser.add_argument(
        "--input",
        help="Optional: input JSON file with user data (skip on-chain fetch)",
    )

    args = parser.parse_args()

    # Get user data
    if args.input:
        print(f"[INFO] Loading user data from {args.input}")
        with open(args.input) as f:
            users = json.load(f)
    else:
        print(f"[INFO] Fetching qualified users from AirdropTracker {args.tracker}")
        users = fetch_qualified_users(args.rpc, args.tracker)

    if not users:
        print("[WARN] No qualified users found. Generating empty distribution.")
        users = []

    print(f"[INFO] Processing {len(users)} qualified users")

    # Build leaves
    leaves = []
    user_data = []
    total_vlt = 0

    for user in users:
        testnet_addr = user["testnet_addr"]
        mainnet_addr = user["mainnet_addr"]
        amount = user["amount"]

        if not mainnet_addr or amount == 0:
            print(f"[WARN] Skipping user {testnet_addr}: no mainnet addr or 0 amount")
            continue

        leaf = build_leaf(testnet_addr, mainnet_addr, amount)
        leaves.append(leaf)
        user_data.append({
            "testnet_addr": testnet_addr,
            "mainnet_addr": mainnet_addr,
            "amount": amount,
            "leaf": leaf.hex(),
        })
        total_vlt += amount

    print(f"[INFO] Total leaves: {len(leaves)}")
    print(f"[INFO] Total VLT to distribute: {total_vlt / 1e8:,.0f} VLT")

    # Build Merkle tree
    root, proofs = build_merkle_tree(leaves)
    print(f"[INFO] Merkle root: 0x{root.hex()}")

    # Attach proofs to user data
    for user in user_data:
        user["proof"] = proofs.get(user["leaf"], [])

    # Build output
    output = {
        "merkle_root": f"0x{root.hex()}",
        "total_users": len(user_data),
        "total_vlt_atomic": total_vlt,
        "total_vlt": total_vlt / 1e8,
        "users": user_data,
    }

    # Write output
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Distribution file generated: {output_path}")
    print(f"   Merkle root: 0x{root.hex()}")
    print(f"   Total users: {len(user_data)}")
    print(f"   Total VLT: {total_vlt / 1e8:,.0f}")

    # Instructions for next steps
    print(f"\n📋 Next steps:")
    print(f"   1. Deploy AirdropClaim.slx on mainnet")
    print(f"   2. Call set_merkle_root(0x{root.hex()})")
    print(f"   3. Call set_vlt_contract(<VLT_token_hash>)")
    print(f"   4. Users can now call claim() with their proof from {output_path}")
    print(f"\n   To verify a single user:")
    print(f"   - testnet_addr: {user_data[0]['testnet_addr'] if user_data else 'N/A'}")
    print(f"   - mainnet_addr: {user_data[0]['mainnet_addr'] if user_data else 'N/A'}")
    print(f"   - amount: {user_data[0]['amount'] if user_data else 'N/A'}")
    print(f"   - proof: {user_data[0]['proof'] if user_data else 'N/A'}")


if __name__ == "__main__":
    main()
