#!/usr/bin/env python3
"""
============================================================================
 tx_ledger.py — local, structured transaction history for the CLI
============================================================================
 The on-chain AirdropTracker is empty (contracts do not record_*), so the
 CLI keeps its OWN append-only ledger of every transaction the user performs.
 Each entry carries rich metadata (screen, contract, entry, amounts, topo,
 timestamp, tx hash) which can be exported as CSV or a clean Discord block
 and analyzed manually.

 Storage: ~/.xelis-vault/tx_history.json   (sidecar to the CLI config)
 Uses only the Python standard library — safe for xvault and xvault-miner.
============================================================================
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path

LEDGER_DIR = Path.home() / ".xelis-vault"
LEDGER_PATH = LEDGER_DIR / "tx_history.json"
LEDGER_VERSION = 1
MAX_ENTRIES = 5000           # cap to keep the file small


def _defaults():
    return {"version": LEDGER_VERSION, "wallet": "", "created_utc": "",
            "entries": []}


def _load() -> dict:
    if not LEDGER_PATH.exists():
        return _defaults()
    try:
        d = json.loads(LEDGER_PATH.read_text())
        if not isinstance(d, dict) or "entries" not in d:
            return _defaults()
        return d
    except Exception:
        return _defaults()


def _save(d: dict) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(tmp, LEDGER_PATH)
    try:
        os.chmod(LEDGER_PATH, 0o600)
    except Exception:
        pass


def record(wallet: str, tx_hash: str, *, screen: str = "", contract: str = "",
           entry: str = "", action: str = "", description: str = "",
           topo: int | None = None,
           amounts: list | None = None) -> dict:
    """Append one confirmed transaction to the ledger. Idempotent by tx_hash."""
    tx_hash = (tx_hash or "").lower()
    if not tx_hash:
        return _defaults()
    d = _load()
    # de-dup: skip already-recorded hash
    for e in d["entries"]:
        if e.get("tx_hash") == tx_hash:
            return d
    now = time.time()
    seq = (d["entries"][-1]["seq"] + 1) if d["entries"] else 1
    entry_rec = {
        "seq": seq,
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "epoch": int(now),
        "tx_hash": tx_hash,
        "screen": screen or "",
        "contract": contract or "",
        "entry": entry or "",
        "action": action or "",
        "description": description or "",
        "topo": topo,
        "amounts": amounts or [],
    }
    d["entries"].append(entry_rec)
    if not d.get("wallet"):
        d["wallet"] = wallet
        d["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    if len(d["entries"]) > MAX_ENTRIES:
        d["entries"] = d["entries"][-MAX_ENTRIES:]
    _save(d)
    return d


def all_entries(wallet: str = "", limit: int | None = None) -> list:
    d = _load()
    ents = d["entries"]
    if wallet and d.get("wallet") and d["wallet"] != wallet:
        ents = [e for e in ents if e.get("wallet") == wallet]
    if limit is not None:
        ents = ents[-limit:]
    return ents


def stats() -> dict:
    d = _load()
    ents = d["entries"]
    return {
        "wallet": d.get("wallet", ""),
        "count": len(ents),
        "created_utc": d.get("created_utc", ""),
        "first_seq": ents[0]["seq"] if ents else None,
        "last_seq": ents[-1]["seq"] if ents else None,
        "last_ts": ents[-1]["ts_utc"] if ents else None,
    }


def to_csv(wallet: str = "") -> str:
    """Rows optimized for spreadsheet analysis, one column per field."""
    fields = ["seq", "ts_utc", "tx_hash", "contract", "entry", "action",
              "topo", "description", "amounts", "screen"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for e in all_entries(wallet):
        row = {k: (e.get(k) if e.get(k) is not None else "") for k in fields}
        if row["amounts"]:
            try:
                row["amounts"] = ";".join(
                    f"{a.get('asset','')}={a.get('display', a.get('atomic',''))}"
                    for a in row["amounts"] if isinstance(a, dict))
            except Exception:
                row["amounts"] = str(row["amounts"])
        w.writerow(row)
    return buf.getvalue()


def to_discord_block(wallet: str = "") -> str:
    """A compiler-friendly block for Discord.

    ```tsv
    seq  ts_utc               tx_hash(64)                          action               topo
    1    2026-08-29T19:05:00Z  abc123...                            PSM.redeem           166556
    ```
    One row per tx, tab-separated, so the analyst can paste straight into a
    sheet/Discord and process every transaction hash in bulk.
    """
    lines = ["```tsv", "seq\tts_utc\ttx_hash\tcontract.entry\taction\ttopo"]
    for e in all_entries(wallet):
        ce = (f"{e.get('contract','')}.{e.get('entry','')}").strip(".")
        lines.append("\t".join([
            str(e.get("seq", "")),
            str(e.get("ts_utc", "")),
            str(e.get("tx_hash", "")),
            ce,
            str(e.get("action", "")),
            str(e.get("topo", "") or ""),
        ]))
    lines.append("```")
    return "\n".join(lines)


def dump_json(wallet: str = "") -> str:
    """Full structured JSON of the ledger (deduplicated, plain)."""
    d = _load()
    ents = all_entries(wallet)
    out = {k: v for k, v in d.items() if k != "entries"}
    out["entries"] = ents
    return json.dumps(out, indent=2)
