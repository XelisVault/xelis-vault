"""
xvault.crypto — cryptographic reference for PrivacyMixer V5.

Byte-exact mirror of contracts/mixer/PrivacyMixerV5.slx:
  note_commitment = blake3("XVMIX5:NOTE:" || secret || recipient_bytes || amount_dec)
  node_hash       = blake3("XVMIX5:N:"    || left || right)
  zero chain      = z[0] = blake3("XVMIX5:Z:"), z[i] = node_hash(z[i-1], z[i-1])

recipient_bytes reproduces the Silex `Address::to_bytes()` syscall EXACTLY
(verified against xelis-blockchain source, Sep 2026 — see research notes):

  Address::to_bytes() = [mainnet: u8] + [public_key: 32 bytes] + [addr_type: u8]
    => 34 bytes for a Normal address (no opaque-id prefix: the Serializer
       trait's default to_bytes() calls write() directly)

  The address STRING is XELIS's custom Bech32 (separator ':' — not '1'):
    "xel:…"/"xet:…" = bech32(hrp, convert_bits(public_key || addr_type, 8->5))
  with the standard bech32 polymod checksum (see bech32.rs in
  xelis-blockchain/xelis_common/src/crypto/).

tests/test_mixer_reference.py asserts that this module reproduces the
contract's commitment formula, incremental Merkle insertion and proof
verification exactly.
"""
from __future__ import annotations

import secrets
from typing import List, Optional, Tuple

import blake3

NOTE_DOMAIN = b"XVMIX5:NOTE:"
NODE_DOMAIN = b"XVMIX5:N:"
ZERO_DOMAIN = b"XVMIX5:Z:"

TREE_DEPTH = 20
CAPACITY = 1 << TREE_DEPTH
ROOT_HISTORY = 64

# Atomic units (8 decimals): 10 / 100 / 1000 XEL
DENOMINATIONS = [1_000_000_000, 10_000_000_000, 100_000_000_000]

DEFAULT_FEE_BPS = 30
MAX_FEE_BPS = 100
DEFAULT_BOUNTY = 5_000_000        # 0.05 XEL
MAX_BOUNTY = 50_000_000           # 0.5 XEL

# Dead-drop window (topoheights; ~5s each since the V3 hard fork).
# MIN ~ 1 hour, MAX ~ 3 days. The depositor picks uniformly at random
# inside this window; the contract enforces the bounds on-chain.
MIN_DELAY_TOPO = 720
MAX_DELAY_TOPO = 51_840

# ---------------------------------------------------------------------------
# XELIS Bech32 (custom separator ':') — port of xelis_common/src/crypto/bech32.rs
# ---------------------------------------------------------------------------

BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_GENERATOR = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
BECH32_SEPARATOR = ":"

MAINNET_HRP = "xel"
TESTNET_HRP = "xet"


def _polymod(values: List[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i, item in enumerate(BECH32_GENERATOR):
            if (top >> i) & 1 == 1:
                chk ^= item
    return chk


def _hrp_expand(hrp: str) -> List[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _create_checksum(hrp: str, data: List[int]) -> List[int]:
    values = _hrp_expand(hrp) + list(data) + [0] * 6
    polymod = _polymod(values) ^ 1
    return [(polymod >> (5 * (5 - i))) & 31 for i in range(6)]


def _verify_checksum(hrp: str, data: List[int]) -> bool:
    return _polymod(_hrp_expand(hrp) + list(data)) == 1


def _convert_bits(data: List[int], from_bits: int, to_bits: int, pad: bool) -> List[int]:
    acc = 0
    bits = 0
    result: List[int] = []
    max_value = (1 << to_bits) - 1
    for value in data:
        if value >> from_bits:
            raise ValueError(f"invalid data range: {value} (from_bits={from_bits})")
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((acc >> bits) & max_value)
    if pad:
        if bits > 0:
            result.append((acc << (to_bits - bits)) & max_value)
    elif bits >= from_bits:
        raise ValueError("illegal zero padding")
    elif (acc << (to_bits - bits)) & max_value:
        raise ValueError("non-zero padding")
    return result


def bech32_encode(hrp: str, data: List[int]) -> str:
    if not hrp:
        raise ValueError("empty hrp")
    if hrp.upper() != hrp and hrp.lower() != hrp:
        raise ValueError("mixed case hrp")
    hrp = hrp.lower()
    combined = list(data) + _create_checksum(hrp, data)
    return hrp + BECH32_SEPARATOR + "".join(BECH32_CHARSET[v] for v in combined)


def bech32_decode(bech: str) -> Tuple[str, List[int]]:
    if len(bech) > 2048:
        raise ValueError("bech32 string too long")
    if bech.lower() != bech and bech.upper() != bech:
        raise ValueError("mixed case")
    bech = bech.lower()
    pos = bech.rfind(BECH32_SEPARATOR)
    if pos < 1 or pos + 7 > len(bech):
        raise ValueError("separator not found / invalid position")
    hrp = bech[:pos]
    try:
        data = [BECH32_CHARSET.index(c) for c in bech[pos + 1:]]
    except ValueError as e:
        raise ValueError(f"invalid bech32 character: {e}") from e
    if not _verify_checksum(hrp, data):
        raise ValueError("invalid bech32 checksum")
    return hrp, data[:-6]


# ---------------------------------------------------------------------------
# Address <-> bytes (EXACT mirror of Silex Address::to_bytes())
# ---------------------------------------------------------------------------

def address_to_bytes(address: str) -> bytes:
    """Silex `Address::to_bytes()` — 34 bytes for a Normal address:

        [mainnet(1)] [public_key(32)] [addr_type(1)]

    Raises on: bad checksum, wrong network prefix, integrated (Data)
    address type (the mixer only supports Normal addresses).
    """
    hrp, data5 = bech32_decode(address.strip())
    if hrp not in (MAINNET_HRP, TESTNET_HRP):
        raise ValueError(f"unknown address prefix '{hrp}:' "
                         f"(expected {MAINNET_HRP}: or {TESTNET_HRP}:)")
    payload = _convert_bits(data5, 5, 8, pad=False)
    if len(payload) != 33:
        raise ValueError(f"unexpected address payload: {len(payload)} bytes (want 33)")
    key = bytes(payload[:32])
    addr_type = payload[32]
    if addr_type != 0:
        raise ValueError("integrated (data) addresses are not supported — "
                         "use a normal address")
    mainnet = 1 if hrp == MAINNET_HRP else 0
    return bytes([mainnet]) + key + bytes([addr_type])


def address_from_bytes(raw: bytes, mainnet: bool) -> str:
    """Inverse of address_to_bytes (used by tests and tooling)."""
    if len(raw) != 34 or raw[33] != 0:
        raise ValueError("not a Normal address byte form (34 bytes, type 0)")
    key = raw[1:33]
    hrp = MAINNET_HRP if mainnet else TESTNET_HRP
    payload = list(key) + [0]
    data5 = _convert_bits(payload, 8, 5, pad=True)
    return bech32_encode(hrp, data5)


def address_network(address: str) -> str:
    """'mainnet' | 'testnet' from the hrp (after checksum validation)."""
    hrp, _ = bech32_decode(address.strip())
    if hrp == MAINNET_HRP:
        return "mainnet"
    if hrp == TESTNET_HRP:
        return "testnet"
    raise ValueError(f"unknown address prefix '{hrp}:'")


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def b3(data: bytes) -> bytes:
    return blake3.blake3(data).digest()


def note_commitment(secret: bytes, recipient_bytes: bytes, amount: int) -> bytes:
    """Contract: Hash::blake3(NOTE_DOMAIN + secret + recipient_bytes + amount_dec).

    `recipient_bytes` must be Silex Address::to_bytes() (see address_to_bytes()).
    """
    if len(secret) != 32:
        raise ValueError("secret must be 32 bytes")
    return b3(NOTE_DOMAIN + secret + recipient_bytes + str(amount).encode())


def note_commitment_for_address(secret: bytes, recipient: str, amount: int) -> bytes:
    """Convenience: compute the commitment from an address STRING.

    This is what the CLI calls at deposit time — the recipient and the
    secret NEVER leave the client; only this hash goes on-chain.
    """
    return note_commitment(secret, address_to_bytes(recipient), amount)


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


def generate_delay() -> int:
    """Uniform random delay in [MIN_DELAY_TOPO, MAX_DELAY_TOPO]
    (~1 hour .. ~3 days): the dead-drop payout window."""
    return secrets.randbelow(MAX_DELAY_TOPO - MIN_DELAY_TOPO + 1) + MIN_DELAY_TOPO


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
