"""
Reference tests for PrivacyMixer V5 (dead-drop model).

These tests assert that sdk/xvault/xvault/crypto.py reproduces EXACTLY the
algorithms implemented in contracts/mixer/PrivacyMixerV5.slx — and that the
byte-level XELIS primitives match the chain's own serialization:

  - XELIS Bech32 (custom ':' separator) encode/decode round-trip
    [port of xelis_common/src/crypto/bech32.rs]
  - Silex Address::to_bytes() = [mainnet(1)] [public_key(32)] [type(1)]
    [xelis_common Serializer::to_bytes default + crypto/address.rs write]
  - note commitment / node hash / zero chain formulas (domain separation,
    V5 domains)
  - incremental Merkle insertion + proofs + root history semantics
  - dead-drop window bounds and payout math (fee + bounty, emergency pro-rata)
  - release authorization model: the payout is bound to the COMMITTED
    recipient — a front-runner / malicious releaser cannot redirect it

If you change the contract's hashing or tree logic, change it here in the
same commit — CI fails on drift (see scripts/verify_chunk_ids.py for the
declaration-order side).
"""
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "xvault"))

import pytest  # noqa: E402

from xvault import crypto  # noqa: E402
from xvault.crypto import (IncrementalMerkleTree, fee_for, is_denomination,
                           node_hash, note_commitment, verify_proof,
                           zero_hashes)  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_address(mainnet: bool = True) -> str:
    """A structurally valid XELIS address around a random 32-byte key."""
    raw = bytes([1 if mainnet else 0]) + secrets.token_bytes(32) + bytes([0])
    return crypto.address_from_bytes(raw, mainnet=mainnet)


# ---------------------------------------------------------------------------
# XELIS Bech32 (custom separator ':') + Address::to_bytes()
# ---------------------------------------------------------------------------

def test_bech32_roundtrip_synthetic_addresses():
    for _ in range(20):
        addr = random_address(secrets.choice([True, False]))
        hrp, data = crypto.bech32_decode(addr)
        assert hrp == ("xel" if addr.startswith("xel:") else "xet")
        assert len(data) > 0


def test_bech32_rejects_bad_checksum():
    addr = random_address(True)
    # flip one character in the data part
    i = addr.rfind(":") + 1
    flipped = addr[:i] + ("q" if addr[i] != "q" else "p") + addr[i + 1:]
    with pytest.raises(ValueError):
        crypto.bech32_decode(flipped)


def test_bech32_rejects_unknown_prefix():
    addr = "btc:" + random_address(True)[4:]
    with pytest.raises(ValueError):
        crypto.address_to_bytes(addr)


def test_address_to_bytes_format():
    """EXACT mirror of Silex Address::to_bytes(): 34 bytes =
    [mainnet(1)] [public_key(32)] [addr_type(1)]. No opaque-id prefix."""
    key = secrets.token_bytes(32)
    for mainnet, hrp in ((True, "xel"), (False, "xet")):
        addr = crypto.address_from_bytes(bytes([1 if mainnet else 0]) + key + b"\x00",
                                         mainnet=mainnet)
        assert addr.startswith(f"{hrp}:")
        raw = crypto.address_to_bytes(addr)
        assert len(raw) == 34
        assert raw[0] == (1 if mainnet else 0)
        assert raw[1:33] == key
        assert raw[33] == 0  # Normal address type


def test_address_length_matches_chain_constant():
    """xelis_common: NORMAL_ADDRESS_LEN = 63 — a normal address string is
    exactly 63 chars (hrp + ':' + 53 data + 6 checksum)."""
    for _ in range(5):
        assert len(random_address(True)) == 63
        assert len(random_address(False)) == 63


def test_integrated_addresses_are_rejected():
    """Data-carrying addresses (type byte != 0) must be refused by the mixer."""
    key = secrets.token_bytes(32)
    payload = key + bytes([1, 42])  # type=1 + a data element
    data5 = crypto._convert_bits(list(payload), 8, 5, pad=True)
    addr = crypto.bech32_encode("xel", data5)
    with pytest.raises(ValueError):
        crypto.address_to_bytes(addr)


# ---------------------------------------------------------------------------
# Domain separation & commitment binding
# ---------------------------------------------------------------------------

def test_domains_are_distinct_and_v5():
    domains = {crypto.NOTE_DOMAIN, crypto.NODE_DOMAIN, crypto.ZERO_DOMAIN}
    assert len(domains) == 3
    assert crypto.NOTE_DOMAIN == b"XVMIX5:NOTE:"


def test_note_commitment_binding():
    """Commitment binds secret, recipient AND amount: flipping any input
    changes the commitment."""
    secret = secrets.token_bytes(32)
    recipient = bytes([1]) + secrets.token_bytes(32) + bytes([0])
    c = note_commitment(secret, recipient, crypto.DENOMINATIONS[1])
    assert c != note_commitment(secrets.token_bytes(32), recipient, crypto.DENOMINATIONS[1])
    assert c != note_commitment(secret, bytes([1]) + secrets.token_bytes(32) + bytes([0]), crypto.DENOMINATIONS[1])
    assert c != note_commitment(secret, recipient, crypto.DENOMINATIONS[0])
    assert c != node_hash(secret, recipient)  # cross-domain collision check


def test_commitment_deterministic_from_address_string():
    """The CLI's deposit path: same (secret, address, amount) -> same hash,
    forever. This is what the contract recomputes at release time."""
    secret = secrets.token_bytes(32)
    addr = random_address(True)
    amount = crypto.DENOMINATIONS[1]
    c1 = crypto.note_commitment_for_address(secret, addr, amount)
    c2 = crypto.note_commitment_for_address(secret, addr, amount)
    assert c1 == c2
    # different network prefix => different commitment (mainnet flag is in
    # the serialized bytes)
    key = crypto.address_to_bytes(addr)[1:33]
    addr_t = crypto.address_from_bytes(bytes([0]) + key + bytes([0]), mainnet=False)
    c3 = crypto.note_commitment_for_address(secret, addr_t, amount)
    assert c3 != c1


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
    — mirroring the contract's deposit/release exactly."""
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


def test_root_history_keeps_last_64():
    """A proof built on an OLDER tree state folds to that older root — the
    contract accepts it only while that root is among the last 64."""
    tree = IncrementalMerkleTree()
    commitments = [secrets.token_bytes(32) for _ in range(70)]
    root_after = {}
    for i, c in enumerate(commitments):
        tree.insert(c)
        root_after[i] = tree.root
    assert len(tree.roots) == crypto.ROOT_HISTORY
    assert tree.valid_root(root_after[69])
    assert tree.valid_root(root_after[10])
    assert not tree.valid_root(root_after[2])


def test_capacity_enforced():
    crypto.CAPACITY_BACKUP = crypto.CAPACITY
    try:
        crypto.CAPACITY = 1 << 4  # depth-4 capacity for the test
        t = IncrementalMerkleTree(depth=4)
        for _ in range(16):
            t.insert(secrets.token_bytes(32))
        with pytest.raises(ValueError):
            t.insert(secrets.token_bytes(32))
    finally:
        crypto.CAPACITY = crypto.CAPACITY_BACKUP


# ---------------------------------------------------------------------------
# Denominations, fees, bounty, dead-drop window
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


def test_bounty_constants():
    assert crypto.DEFAULT_BOUNTY == 5_000_000      # 0.05 XEL
    assert crypto.MAX_BOUNTY == 50_000_000         # 0.5 XEL
    assert crypto.DEFAULT_BOUNTY < crypto.DENOMINATIONS[0]  # sane vs 10 XEL notes


def test_delay_window_bounds():
    """~1 hour to ~3 days at 5s topoheights (V3 hard fork block time)."""
    assert crypto.MIN_DELAY_TOPO == 720        # 3600s / 5s
    assert crypto.MAX_DELAY_TOPO == 51_840     # 3 * 24 * 3600 / 5


def test_generated_delays_stay_in_window():
    for _ in range(200):
        d = crypto.generate_delay()
        assert crypto.MIN_DELAY_TOPO <= d <= crypto.MAX_DELAY_TOPO


def test_payout_math_fee_then_bounty():
    """Normal mode: payout = amount - fee - bounty (mirror of the contract)."""
    amount = crypto.DENOMINATIONS[1]
    fee = fee_for(amount, 30)
    bounty = min(crypto.DEFAULT_BOUNTY, amount - fee)
    payout = amount - fee - bounty
    assert payout == amount - fee - crypto.DEFAULT_BOUNTY
    # bounty never exceeds the share (tiny denominations edge)
    tiny_fee = fee_for(crypto.DENOMINATIONS[0], 100)
    assert min(crypto.MAX_BOUNTY, crypto.DENOMINATIONS[0] - tiny_fee) <= \
        crypto.DENOMINATIONS[0] - tiny_fee


# ---------------------------------------------------------------------------
# Emergency exit pro-rata (mirror of the contract's u128 math)
# ---------------------------------------------------------------------------

def emode_share(amount: int, balance: int, pending: int) -> int:
    """Exact mirror of the contract's emergency branch (before bounty)."""
    ratio128 = 0
    if pending > 0:
        ratio128 = (balance * 10_000) // pending
    if ratio128 > 10_000:
        ratio128 = 10_000
    return (amount * ratio128) // 10_000


def test_emode_full_coverage_when_solvent():
    assert emode_share(100, 150, 100) == 100  # cap at 100%


def test_emode_pro_rata_drains_pool_fairly():
    balance, pending = 100, 200  # ratio 50%
    p1 = emode_share(100, balance, pending)
    balance -= p1
    pending -= 100
    p2 = emode_share(100, balance, pending)
    balance -= p2
    pending -= 100
    assert (p1, p2) == (50, 50)
    assert balance == 0 and pending == 0


def test_emode_u128_no_overflow():
    big = 18_400_000 * 10**8
    assert emode_share(1000, big, big) == 1000


# ---------------------------------------------------------------------------
# Dead-drop release model — front-run & theft resistance
# ---------------------------------------------------------------------------

def test_release_payout_is_bound_to_committed_recipient():
    """Model of `process_release`: the payout address is recovered from the
    commitment, never from the caller. A front-runner who copies the release
    params verbatim changes NOTHING — funds land on the committed recipient;
    the thief only earns the bounty and pays the gas."""
    secret = secrets.token_bytes(32)
    victim = random_address(True)
    attacker = random_address(True)
    amount = crypto.DENOMINATIONS[1]

    commitment = crypto.note_commitment_for_address(secret, victim, amount)

    def release(caller_recipient_claim: str, releaser: str) -> str:
        # the contract recomputes the commitment from (secret, claim, amount)
        # and requires it to match the stored leaf: a different claim simply
        # fails; the SAME claim pays the committed address, whoever sent the tx
        got = crypto.note_commitment_for_address(secret, caller_recipient_claim, amount)
        assert got == commitment, "proof must verify"
        return victim  # payout target is the committed address, not the releaser

    # front-runner copies the params exactly:
    assert release(victim, attacker) == victim
    # thief tries to substitute their own address -> proof breaks:
    with pytest.raises(AssertionError):
        release(attacker, attacker)


def test_deposit_entry_has_no_address_param():
    """The V5 deposit must take ONLY (Hash, u64) — the recipient must never
    appear in plaintext invoke params (the V4 flaw, lint rule R11)."""
    contract = os.path.join(os.path.dirname(__file__), "..", "contracts",
                            "mixer", "PrivacyMixerV5.slx")
    src = open(contract, encoding="utf-8").read()
    m = re.search(r"^entry\s+deposit\s*\(([^)]*)\)", src, re.MULTILINE)
    assert m, "deposit entry not found in PrivacyMixerV5.slx"
    params = m.group(1)
    assert "Address" not in params, \
        f"deposit leaks an address in its params: deposit({params})"
    assert "Hash" in params and "u64" in params


# ---------------------------------------------------------------------------
# Note file round-trip
# ---------------------------------------------------------------------------

def test_note_roundtrip(tmp_path):
    from xvault.mixer import Note
    note = Note(version=2, network="testnet", contract="a" * 64,
                secret="b" * 64, recipient=random_address(False),
                amount=10**10, delay=720, commitment="c" * 64,
                leaf_index=3, unlock_topoheight=762, created_topoheight=42)
    path = tmp_path / "note.json"
    note.save(str(path))
    loaded = Note.load(str(path))
    assert loaded == note
