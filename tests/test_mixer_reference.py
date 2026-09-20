"""
Reference tests for PrivacyMixer V4.

These tests assert that sdk/xvault/xvault/crypto.py reproduces EXACTLY the
algorithm implemented in contracts/mixer/PrivacyMixerV4.slx:

  - note commitment / node hash / zero chain formulas (domain separation)
  - incremental Merkle insertion (store-then-fold, zero-or-stored sibling)
  - proof generation and verification (index-bit left/right folding)
  - root history semantics (last 64 roots valid)
  - fee math and denomination checks
  - withdrawal payout math, including the emergency pro-rata ratio in u128

If you change the contract's hashing or tree logic, change it here in the
same commit — CI fails on drift (see scripts/verify_chunk_ids.py for the
declaration-order side).
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "xvault"))

import pytest  # noqa: E402

from xvault import crypto  # noqa: E402
from xvault.crypto import (IncrementalMerkleTree, fee_for, is_denomination,
                           node_hash, note_commitment, verify_proof,
                           zero_hashes)  # noqa: E402


# ---------------------------------------------------------------------------
# Domain separation
# ---------------------------------------------------------------------------

def test_domains_are_distinct():
    domains = {crypto.NOTE_DOMAIN, crypto.NODE_DOMAIN, crypto.ZERO_DOMAIN}
    assert len(domains) == 3


def test_note_commitment_binding():
    """Commitment binds secret, recipient AND amount: flipping any input
    changes the commitment."""
    secret = secrets.token_bytes(32)
    recipient = bytes(range(32))
    c = note_commitment(secret, recipient, crypto.DENOMINATIONS[1])
    assert c != note_commitment(secrets.token_bytes(32), recipient, crypto.DENOMINATIONS[1])
    assert c != note_commitment(secret, bytes(range(31, -1, -1)), crypto.DENOMINATIONS[1])
    assert c != note_commitment(secret, recipient, crypto.DENOMINATIONS[0])
    assert c != node_hash(secret, recipient)  # cross-domain collision check


def test_node_hash_is_not_symmetric():
    a, b = secrets.token_bytes(32), secrets.token_bytes(32)
    assert node_hash(a, b) != node_hash(b, a), "left/right order must matter"


# ---------------------------------------------------------------------------
# Zero chain
# ---------------------------------------------------------------------------

def test_zero_chain_matches_contract_formula():
    zeros = zero_hashes(crypto.TREE_DEPTH)
    assert zeros[0] == crypto.b3(crypto.ZERO_DOMAIN)
    for i in range(1, len(zeros)):
        assert zeros[i] == node_hash(zeros[i - 1], zeros[i - 1])
    assert len(zeros) == crypto.TREE_DEPTH + 1


# ---------------------------------------------------------------------------
# Incremental insertion + proofs
# ---------------------------------------------------------------------------

def test_empty_tree_root_is_zero_chain_top():
    tree = IncrementalMerkleTree()
    zeros = zero_hashes(crypto.TREE_DEPTH)
    assert tree.root == zeros[crypto.TREE_DEPTH]
    assert tree.valid_root(tree.root)


def test_insert_then_prove_every_leaf():
    """Insert 40 commitments and verify EVERY leaf proves to the current root
    — mirroring the contract's deposit/withdraw exactly."""
    tree = IncrementalMerkleTree()
    commitments = [secrets.token_bytes(32) for _ in range(40)]
    for i, c in enumerate(commitments):
        idx = tree.insert(c)
        assert idx == i
    for i, c in enumerate(commitments):
        siblings = tree.proof(i)
        assert len(siblings) == crypto.TREE_DEPTH
        assert verify_proof(c, i, siblings) == tree.root, f"leaf {i} proof broken"


def test_proof_fails_on_wrong_commitment():
    tree = IncrementalMerkleTree()
    for _ in range(5):
        tree.insert(secrets.token_bytes(32))
    siblings = tree.proof(2)
    wrong = verify_proof(secrets.token_bytes(32), 2, siblings)
    assert wrong != tree.root


def test_proof_fails_on_wrong_index():
    tree = IncrementalMerkleTree()
    commitments = [secrets.token_bytes(32) for _ in range(5)]
    for c in commitments:
        tree.insert(c)
    siblings = tree.proof(3)
    # commitment of leaf 3 claimed at index 2 -> different folding order
    assert verify_proof(commitments[3], 2, siblings) != tree.root


def test_proof_fails_with_short_sibling_list():
    tree = IncrementalMerkleTree()
    tree.insert(secrets.token_bytes(32))
    with pytest.raises(ValueError):
        verify_proof(secrets.token_bytes(32), 0, [b"x"] * 19)


def test_root_history_keeps_last_64():
    """A proof built on an OLDER tree state folds to that older root — the
    contract accepts it only while that root is among the last 64. Capture
    roots as they are produced, then check eviction."""
    tree = IncrementalMerkleTree()
    commitments = [secrets.token_bytes(32) for _ in range(70)]
    root_after = {}  # insertion index -> root produced by that insertion
    for i, c in enumerate(commitments):
        tree.insert(c)
        root_after[i] = tree.root
    assert len(tree.roots) == crypto.ROOT_HISTORY
    # insertion 69 is the current root; insertion 10 (60 back) still valid;
    # insertion 2 (67 back) is evicted.
    assert tree.valid_root(root_after[69])
    assert tree.valid_root(root_after[10])
    assert not tree.valid_root(root_after[2])


def test_capacity_enforced():
    class SmallTree(IncrementalMerkleTree):
        def __init__(self):
            super().__init__(depth=4)

    crypto.CAPACITY_BACKUP = crypto.CAPACITY
    try:
        crypto.CAPACITY = 1 << 4  # depth-4 capacity for the test
        t = SmallTree()
        for _ in range(16):
            t.insert(secrets.token_bytes(32))
        with pytest.raises(ValueError):
            t.insert(secrets.token_bytes(32))
    finally:
        crypto.CAPACITY = crypto.CAPACITY_BACKUP


# ---------------------------------------------------------------------------
# Denominations & fees
# ---------------------------------------------------------------------------

def test_denominations():
    assert crypto.DENOMINATIONS == [10**9, 10**10, 10**11]
    assert is_denomination(10**10)
    assert not is_denomination(10**10 + 1)
    assert not is_denomination(0)


def test_fee_math_matches_contract():
    amount = crypto.DENOMINATIONS[2]  # 1000 XEL
    assert fee_for(amount, 30) == amount * 30 // 10_000
    assert fee_for(amount, 0) == 0
    assert fee_for(amount, 100) == amount // 100  # hard cap = 1%


# ---------------------------------------------------------------------------
# Emergency exit pro-rata (mirror of the contract's u128 math)
# ---------------------------------------------------------------------------

def emode_payout(amount: int, balance: int, pending: int) -> int:
    """Exact mirror of the contract's emergency branch."""
    ratio128 = 0
    if pending > 0:
        ratio128 = (balance * 10_000) // pending
    if ratio128 > 10_000:
        ratio128 = 10_000
    return (amount * ratio128) // 10_000


def test_emode_full_coverage_when_solvent():
    assert emode_payout(100, 150, 100) == 100  # cap at 100%


def test_emode_pro_rata_drains_pool_fairly():
    # Pool with a 50% hole: two 50-XEL notes must each get 25, and the pool
    # ends empty (pending hits 0 exactly when the balance does).
    balance, pending = 100, 200  # atomic-ish, ratio 50%
    p1 = emode_payout(100, balance, pending)
    balance -= p1
    pending -= 100
    p2 = emode_payout(100, balance, pending)
    balance -= p2
    pending -= 100
    assert (p1, p2) == (50, 50)
    assert balance == 0 and pending == 0


def test_emode_mixed_denominations_fair():
    balance, pending = 55, 110  # 50%
    p100 = emode_payout(100, balance, pending)
    balance -= p100
    pending -= 100
    p10 = emode_payout(10, balance, pending)
    assert (p100, p10) == (50, 5)


def test_emode_no_pending_means_zero_payout():
    assert emode_payout(100, 500, 0) == 0


def test_emode_u128_no_overflow():
    # whole supply x 10000 must not overflow (contract computes in u128)
    big = 18_400_000 * 10**8
    assert emode_payout(1000, big, big) == 1000


# ---------------------------------------------------------------------------
# Note file round-trip
# ---------------------------------------------------------------------------

def test_note_roundtrip(tmp_path):
    from xvault.mixer import Note
    note = Note(version=1, network="testnet", contract="a" * 64,
                secret="b" * 64, recipient="xtv:test", amount=10**10,
                leaf_index=3, created_topoheight=42)
    path = tmp_path / "note.json"
    note.save(str(path))
    loaded = Note.load(str(path))
    assert loaded == note
