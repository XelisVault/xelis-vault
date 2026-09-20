"""
xvault.mixer — high-level PrivacyMixer V5 operations.

Dead-drop model:
  * deposit() receives ONLY a client-computed commitment + a random delay.
    The recipient address and the secret NEVER appear on-chain at deposit.
  * release() is PERMISSIONLESS: anyone can trigger the payout after the
    note's unlock topoheight. The payout ALWAYS goes to the address bound
    inside the commitment — a releaser cannot steal or redirect it.

Note model, deposit/release preparation, proof building from live contract
storage and protocol health checks. All functions are network-safe (reads
via DaemonClient); the CLI decides what to do with the prepared transactions.
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
K_BOUNTY = "bty"
K_PAUSED = "pz"
K_EMODE = "em"
K_NOTES_ISSUED = "ni"
K_NOTES_SPENT = "ns"
K_TOTAL_DEPOSITED = "td"
K_TOTAL_RELEASED = "tr"

NODE_PREFIX = "nd:"
ZERO_PREFIX = "z:"
SPENT_PREFIX = "sp:"
UNLOCK_PREFIX = "u:"
ROOT_PREFIX = "rt:"


@dataclass
class Note:
    """A V5 dead-drop note. The `secret` is a bearer instrument: whoever
    holds it can trigger the payout — but the funds ALWAYS land on
    `recipient` (bound inside the commitment). Store it encrypted."""
    version: int                 # note-file format version (2)
    network: str
    contract: str
    secret: str                  # hex, 32 bytes
    recipient: str               # xel:… / xet:… address
    amount: int                  # atomic units
    delay: int                   # topoheights chosen at deposit
    commitment: Optional[str] = None   # hex, 32 bytes (client-computed)
    leaf_index: Optional[int] = None
    unlock_topoheight: Optional[int] = None
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

    def bounty(self) -> int:
        return int(self._read(K_BOUNTY) or crypto.DEFAULT_BOUNTY)

    def paused(self) -> bool:
        return bool(self._read(K_PAUSED) or False)

    def emode(self) -> bool:
        return bool(self._read(K_EMODE) or False)

    def topoheight(self) -> int:
        return self.d.topoheight()

    def stats(self) -> Dict[str, int]:
        return {
            "notes_issued": int(self._read(K_NOTES_ISSUED) or 0),
            "notes_spent": int(self._read(K_NOTES_SPENT) or 0),
            "leaf_count": self.leaf_count(),
            "pending": self.pending(),
            "fees_owed": self.fees_owed(),
            "fee_bps": self.fee_bps(),
            "bounty": self.bounty(),
            "total_deposited": int(self._read(K_TOTAL_DEPOSITED) or 0),
            "total_released": int(self._read(K_TOTAL_RELEASED) or 0),
        }

    def node(self, level: int, index: int) -> Optional[str]:
        return self._read(f"{NODE_PREFIX}{level}:{index}")

    def zero(self, level: int) -> Optional[str]:
        return self._read(f"{ZERO_PREFIX}{level}")

    def is_spent(self, index: int) -> bool:
        return bool(self._read(f"{SPENT_PREFIX}{index}") or False)

    def unlock_topoheight(self, index: int) -> Optional[int]:
        v = self._read(f"{UNLOCK_PREFIX}{index}")
        return int(v) if v is not None else None

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
        """Circuit-breaker view: balance vs pending, fees, bounty, flags."""
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
                    recipient: str, delay: Optional[int] = None) -> Note:
    """Generate a fresh dead-drop note + the invoke parameters for deposit().

    * the commitment is computed CLIENT-SIDE (secret + recipient never leave
      this machine — only the hash goes on-chain);
    * the delay is drawn uniformly at random inside the dead-drop window
      (~1h..~3d) unless the caller passes an explicit value.
    The XEL deposit is attached to the transaction by the wallet.
    """
    if not crypto.is_denomination(amount):
        raise ValueError(
            f"amount must be exactly one of "
            f"{[crypto.fmt_xel(d) for d in crypto.DENOMINATIONS]}, got "
            f"{crypto.fmt_xel(amount)}")

    # Validate the recipient against the network (bech32 checksum + prefix).
    prefix = NETWORKS[network]["address_prefix"]
    if not recipient.startswith(f"{prefix}:"):
        raise ValueError(f"recipient must be a {prefix}: address on {network}")
    addr_net = crypto.address_network(recipient)
    if addr_net != network:
        raise ValueError(f"recipient is a {addr_net} address, not {network}")

    if delay is None:
        delay = crypto.generate_delay()
    if not (crypto.MIN_DELAY_TOPO <= delay <= crypto.MAX_DELAY_TOPO):
        raise ValueError(
            f"delay must be in [{crypto.MIN_DELAY_TOPO}, {crypto.MAX_DELAY_TOPO}] "
            f"topoheights (~1h..~3d at 5s), got {delay}")

    secret = crypto.generate_secret()
    commitment = crypto.note_commitment_for_address(secret, recipient, amount)
    return Note(
        version=2,
        network=network,
        contract=contract,
        secret=secret.hex(),
        recipient=recipient,
        amount=amount,
        delay=delay,
        commitment=commitment.hex(),
    )


def deposit_params(note: Note) -> List[dict]:
    """ValueCell parameters for deposit(commitment, delay)."""
    if not note.commitment:
        raise ValueError("note has no commitment — regenerate it")
    return [val_hash(note.commitment), val_u64(note.delay)]


def deposit_deposits(note: Note, xel_asset: str) -> Dict[str, int]:
    """Attached deposit map for the invoke: {xel_asset: amount}."""
    return {xel_asset: note.amount}


def release_params(note: Note, reader: MixerReader) -> List[dict]:
    """ValueCell parameters for release(recipient, secret, amount,
    leaf_index, siblings), with the proof built from LIVE contract storage.

    Verifies locally BEFORE spending gas:
      * the note is not spent;
      * the unlock topoheight has been reached;
      * the recomputed commitment matches the stored leaf;
      * the proof folds to the current root.
    """
    if note.leaf_index is None:
        raise ValueError("note has no leaf_index — was the deposit confirmed?")
    if reader.is_spent(note.leaf_index):
        raise ValueError(f"note {note.leaf_index} is already spent")

    unlock = reader.unlock_topoheight(note.leaf_index)
    if unlock is None:
        raise ValueError(f"leaf {note.leaf_index} has no unlock topoheight")
    topo = reader.topoheight()
    if topo < unlock:
        raise ValueError(
            f"note locked until topoheight {unlock} (now {topo}, "
            f"{unlock - topo} to go ≈ {(unlock - topo) * 5 / 3600:.1f}h)")

    # Recompute the commitment exactly like the contract will.
    commitment = crypto.note_commitment_for_address(
        bytes.fromhex(note.secret), note.recipient, note.amount)
    stored_leaf = reader.leaf(note.leaf_index)
    if stored_leaf is None:
        raise ValueError(f"leaf {note.leaf_index} not found on-chain")
    if commitment.hex() != stored_leaf:
        raise ValueError(
            "commitment mismatch: this note does not match the stored leaf "
            "(wrong note file, wrong contract, or wrong recipient)")

    siblings_hex = reader.siblings(note.leaf_index)
    siblings = [bytes.fromhex(h) for h in siblings_hex]
    recomputed = crypto.verify_proof(bytes.fromhex(stored_leaf),
                                     note.leaf_index, siblings).hex()
    current_root = reader.root()
    if recomputed != current_root:
        raise ValueError(
            "local proof check failed: recomputed root "
            f"{recomputed[:16]}… != current root {str(current_root)[:16]}… "
            "(tree moved? retry in a moment)")

    return [
        val_addr(note.recipient),
        val_hash(note.secret),
        val_u64(note.amount),
        val_u64(note.leaf_index),
        val_array([val_hash(h) for h in siblings_hex]),
    ]


def release_many_params(notes: List[Note], reader: MixerReader) -> List[dict]:
    """ValueCell parameters for release_many(...): flat siblings array
    (20 per note), all-or-nothing semantics on-chain."""
    if not notes:
        raise ValueError("no notes given")
    if len(notes) > 16:
        raise ValueError("batch cap is 16 notes per release_many")
    flat_siblings: List[str] = []
    for note in notes:
        params = release_params(note, reader)  # full verification per note
        flat_siblings.extend(params[4]["value"])
    return [
        val_array([val_addr(n.recipient) for n in notes]),
        val_array([val_hash(n.secret) for n in notes]),
        val_array([val_u64(n.amount) for n in notes]),
        val_array([val_u64(n.leaf_index) for n in notes]),
        val_array([val_hash(h) for h in flat_siblings]),
    ]
