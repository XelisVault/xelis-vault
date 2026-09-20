"""
xvault.mixer — high-level PrivacyMixer V4 operations.

Note model, deposit/withdraw preparation, proof building from live contract
storage and protocol health checks. All functions are network-safe (reads via
DaemonClient); the CLI decides what to do with the prepared transactions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import crypto
from .protocol import (DaemonClient, MIXER_ENTRY_IDS, NETWORKS, RPCError,
                       val_addr, val_hash, val_str, val_u64, val_array)


# ---------------------------------------------------------------------------
# Storage keys (mirror of the contract)
# ---------------------------------------------------------------------------
K_LEAF_COUNT = "lc"
K_ROOT_COUNT = "rc"
K_PENDING = "pd"
K_FEES_OWED = "fo"
K_FEE_BPS = "fb"
K_PAUSED = "pz"
K_EMODE = "em"
K_NOTES_ISSUED = "ni"
K_NOTES_SPENT = "ns"
K_TOTAL_DEPOSITED = "td"
K_TOTAL_WITHDRAWN = "tw"

NODE_PREFIX = "nd:"
ZERO_PREFIX = "z:"
SPENT_PREFIX = "sp:"
ROOT_PREFIX = "rt:"


@dataclass
class Note:
    """A mixer note. The `secret` is a bearer instrument: whoever holds it AND
    controls `recipient` can withdraw. Store it encrypted, never in a repo."""
    version: int
    network: str
    contract: str
    secret: str            # hex, 32 bytes
    recipient: str         # xel:... / xtv:... address
    amount: int            # atomic units
    leaf_index: Optional[int] = None
    created_topoheight: Optional[int] = None

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))
        try:  # best-effort local hygiene
            Path(path).chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def load(path: str) -> "Note":
        return Note(**json.loads(Path(path).read_text()))


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

class MixerReader:
    def __init__(self, daemon: DaemonClient, contract: str):
        self.d = daemon
        self.c = contract

    def _read(self, key: str) -> Any:
        return self.d.read_key(self.c, key)

    def leaf_count(self) -> int:
        return int(self._read(K_LEAF_COUNT) or 0)

    def root_count(self) -> int:
        return int(self._read(K_ROOT_COUNT) or 0)

    def root(self) -> Optional[str]:
        rc = self.root_count()
        if rc == 0:
            return None
        return self._read(f"{ROOT_PREFIX}{rc - 1}")

    def pending(self) -> int:
        return int(self._read(K_PENDING) or 0)

    def fees_owed(self) -> int:
        return int(self._read(K_FEES_OWED) or 0)

    def fee_bps(self) -> int:
        return int(self._read(K_FEE_BPS) or crypto.DEFAULT_FEE_BPS)

    def paused(self) -> bool:
        return bool(self._read(K_PAUSED) or False)

    def emode(self) -> bool:
        return bool(self._read(K_EMODE) or False)

    def stats(self) -> Dict[str, int]:
        return {
            "notes_issued": int(self._read(K_NOTES_ISSUED) or 0),
            "notes_spent": int(self._read(K_NOTES_SPENT) or 0),
            "leaf_count": self.leaf_count(),
            "pending": self.pending(),
            "fees_owed": self.fees_owed(),
            "fee_bps": self.fee_bps(),
            "total_deposited": int(self._read(K_TOTAL_DEPOSITED) or 0),
            "total_withdrawn": int(self._read(K_TOTAL_WITHDRAWN) or 0),
        }

    def node(self, level: int, index: int) -> Optional[str]:
        return self._read(f"{NODE_PREFIX}{level}:{index}")

    def zero(self, level: int) -> Optional[str]:
        return self._read(f"{ZERO_PREFIX}{level}")

    def is_spent(self, index: int) -> bool:
        return bool(self._read(f"{SPENT_PREFIX}{index}") or False)

    def leaf(self, index: int) -> Optional[str]:
        return self.node(0, index)

    def siblings(self, leaf_index: int) -> List[str]:
        """Read the 20 Merkle siblings of a leaf position from live storage.
        Missing nodes (empty subtrees) resolve to the stored zero hashes."""
        siblings = []
        idx = leaf_index
        for level in range(crypto.TREE_DEPTH):
            pos = (idx ^ 1)
            sib = self.node(level, pos)
            if sib is None:
                z = self.zero(level)
                if z is None:
                    raise RPCError(f"missing zero hash z:{level} — contract "
                                   "uninitialized?")
                sib = z
            siblings.append(sib)
            idx //= 2
        return siblings

    def balance(self, xel_asset: str) -> int:
        return self.d.get_contract_balance(self.c, xel_asset)

    def health(self, xel_asset: str) -> Dict[str, Any]:
        """Circuit-breaker view: balance vs pending, fees, state flags."""
        s = self.stats()
        bal = self.balance(xel_asset)
        return {
            **s,
            "balance": bal,
            "solvent": bal >= s["pending"],
            "paused": self.paused(),
            "emode": self.emode(),
        }


# ---------------------------------------------------------------------------
# Writes (transaction preparation — signing/broadcast happens in the wallet)
# ---------------------------------------------------------------------------

def prepare_deposit(network: str, contract: str, amount: int,
                    recipient: str) -> Note:
    """Generate a fresh bearer note + the invoke parameters for deposit().
    The XEL deposit is attached to the transaction by the wallet."""
    if not crypto.is_denomination(amount):
        raise ValueError(
            f"amount must be exactly one of "
            f"{[crypto.fmt_xel(d) for d in crypto.DENOMINATIONS]}, got "
            f"{crypto.fmt_xel(amount)}")
    prefix = NETWORKS[network]["address_prefix"]
    if not recipient.startswith(f"{prefix}:"):
        raise ValueError(f"recipient must be a {prefix}: address on {network}")
    secret = crypto.generate_secret()
    return Note(
        version=1,
        network=network,
        contract=contract,
        secret=secret.hex(),
        recipient=recipient,
        amount=amount,
    )


def deposit_params(note: Note) -> List[dict]:
    """ValueCell parameters for the deposit invoke."""
    return [val_hash(note.secret), val_addr(note.recipient)]


def deposit_deposits(note: Note, xel_asset: str) -> Dict[str, int]:
    """Attached deposit map for the invoke: {xel_asset: amount}."""
    return {xel_asset: note.amount}


def withdraw_params(note: Note, reader: MixerReader) -> List[dict]:
    """ValueCell parameters for withdraw(secret, amount, leaf_index, siblings),
    with the proof built from LIVE contract storage. Also verifies locally
    that the proof lands on the current root (catches stale trees before
    spending gas)."""
    if note.leaf_index is None:
        raise ValueError("note has no leaf_index — was the deposit confirmed?")
    if reader.is_spent(note.leaf_index):
        raise ValueError(f"note {note.leaf_index} is already spent")

    siblings_hex = reader.siblings(note.leaf_index)
    siblings = [bytes.fromhex(h) for h in siblings_hex]

    # Local verification: the stored leaf must fold (with these siblings) to
    # the current root. Uses the stored leaf (the commitment) so no address
    # decoding is required.
    stored_leaf = reader.leaf(note.leaf_index)
    if stored_leaf is None:
        raise ValueError(f"leaf {note.leaf_index} not found on-chain")
    recomputed = crypto.verify_proof(bytes.fromhex(stored_leaf),
                                     note.leaf_index, siblings).hex()
    current_root = reader.root()
    if recomputed != current_root:
        raise ValueError(
            "local proof check failed: recomputed root "
            f"{recomputed[:16]}… != current root {str(current_root)[:16]}… "
            "(tree moved? retry in a moment)")

    return [
        val_hash(note.secret),
        val_u64(note.amount),
        val_u64(note.leaf_index),
        val_array([val_hash(h) for h in siblings_hex]),
    ]
