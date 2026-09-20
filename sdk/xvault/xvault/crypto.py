"""
xvault.crypto — cryptographic reference for PrivacyMixer V4.

Byte-exact mirror of contracts/mixer/PrivacyMixerV4.slx:
  note_commitment = blake3("XVMIX4:NOTE:" || secret || recipient_bytes || amount_dec)
  node_hash       = blake3("XVMIX4:N:" || left || right)
  zero chain      = z[0] = blake3("XVMIX4:Z:"), z[i] = node_hash(z[i-1], z[i-1])

tests/test_mixer_reference.py asserts that this module reproduces the
contract's incremental Merkle insertion and proof verification exactly.
"""
from __future__ import annotations

import secrets
from typing import List, Optional

import blake3

NOTE_DOMAIN = b"XVMIX4:NOTE:"
NODE_DOMAIN = b"XVMIX4:N:"
ZERO_DOMAIN = b"XVMIX4:Z:"

TREE_DEPTH = 20
CAPACITY = 1 << TREE_DEPTH
ROOT_HISTORY = 64

# Atomic units (8 decimals): 10 / 100 / 1000 XEL
DENOMINATIONS = [1_000_000_000, 10_000_000_000, 100_000_000_000]

DEFAULT_FEE_BPS = 30
MAX_FEE_BPS = 100


def b3(data: bytes) -> bytes:
    return blake3.blake3(data).digest()


def note_commitment(secret: bytes, recipient_bytes: bytes, amount: int) -> bytes:
    """Contract: Hash::blake3(NOTE_DOMAIN + secret + recipient + amount_dec)."""
    return b3(NOTE_DOMAIN + secret + recipient_bytes + str(amount).encode())


def node_hash(left: bytes, right: bytes) -> bytes:
    return b3(NODE_DOMAIN + left + right)


def zero_hashes(depth: int = TREE_DEPTH) -> List[bytes]:
    """z[0] = blake3(ZERO_DOMAIN); z[i] = node_hash(z[i-1], z[i-1])."""
    zeros = [b3(ZERO_DOMAIN)]
    for _ in range(depth):
        zeros.append(node_hash(zeros[-1], zeros[-1]))
    return zeros


def generate_secret() -> bytes:
    """32 random bytes — a bearer note secret. NEVER share it, NEVER commit it."""
    return secrets.token_bytes(32)


# ---------------------------------------------------------------------------
# Incremental Merkle tree (mirror of the contract's insertion)
# ---------------------------------------------------------------------------

class IncrementalMerkleTree:
    """Sparse-in-time incremental tree, identical semantics to the contract:
    each insertion stores the node at every level then folds with the sibling
    (zero hash when the index is even, stored left node when odd)."""

    def __init__(self, depth: int = TREE_DEPTH):
        self.depth = depth
        self.zeros = zero_hashes(depth)
        self.nodes: List[dict] = [dict() for _ in range(depth + 1)]
        self.leaf_count = 0
        self.roots: List[bytes] = [self.zeros[depth]]  # empty-tree root

    def _get(self, level: int, index: int) -> Optional[bytes]:
        return self.nodes[level].get(index)

    def insert(self, commitment: bytes) -> int:
        if self.leaf_count >= CAPACITY:
            raise ValueError("tree full")
        index = self.leaf_count
        current = commitment
        idx = index
        for level in range(self.depth):
            self.nodes[level][idx] = current
            if idx % 2 == 0:
                current = node_hash(current, self.zeros[level])
            else:
                left = self._get(level, idx - 1)
                if left is None:
                    raise RuntimeError("tree invariant violated (missing left sibling)")
                current = node_hash(left, current)
            idx //= 2
        self.roots.append(current)
        if len(self.roots) > ROOT_HISTORY:
            self.roots.pop(0)
        self.leaf_count += 1
        return index

    @property
    def root(self) -> bytes:
        return self.roots[-1]

    def proof(self, index: int) -> List[bytes]:
        """Sibling hashes from leaf level up to (excluding) the root."""
        if index >= self.leaf_count:
            raise ValueError("index not inserted yet")
        siblings = []
        idx = index
        for level in range(self.depth):
            sib = self._get(level, idx ^ 1)
            if sib is None:
                sib = self.zeros[level]
            siblings.append(sib)
            idx //= 2
        return siblings

    def valid_root(self, root: bytes) -> bool:
        return root in self.roots


def verify_proof(commitment: bytes, index: int, siblings: List[bytes]) -> bytes:
    """Recompute the root the same way the contract does."""
    if len(siblings) != TREE_DEPTH:
        raise ValueError(f"expected {TREE_DEPTH} siblings, got {len(siblings)}")
    current = commitment
    idx = index
    for level in range(TREE_DEPTH):
        sib = siblings[level]
        if idx % 2 == 0:
            current = node_hash(current, sib)
        else:
            current = node_hash(sib, current)
        idx //= 2
    return current


def fee_for(amount: int, fee_bps: int = DEFAULT_FEE_BPS) -> int:
    return amount * fee_bps // 10_000


def is_denomination(amount: int) -> bool:
    return amount in DENOMINATIONS


def fmt_xel(atomic: int) -> str:
    return f"{atomic / 1e8:,.8f}".rstrip("0").rstrip(".") + " XEL"
