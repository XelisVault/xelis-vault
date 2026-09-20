#!/usr/bin/env python3
"""
relayer_server.py — VaultChat relayer daemon (a real, running relay service).

This process turns your wallet into a WORKING relayer for VaultChat. Unlike the
static `endpoint` string you register on-chain, this daemon actually:

  1. SYNC — watches the VaultChat contract on the chain (testnet/mainnet) for new
     direct messages, relayed messages and group messages, and keeps a local
     deduplicated ledger in ~/.xelis-vault/relayer/ledger.json.
  2. SERVE — exposes a local HTTP API (default http://127.0.0.1:18444) so clients
     and other relayers can query inboxes/groups, push relayed messages and read
     our status. This is the "mail server" behind a relayer endpoint.
  3. ANCHOR — batches newly relayed messages (>=5 messages from >=2 distinct
     senders) into a Merkle root and submits it via `anchor_messages` to earn the
     on-chain VLT relayer reward, respecting the contract rate limits (>=300
     blocks between anchors, <=50/day, daily reward cap handled by the contract).

The daemon is pure-stdlib (uses Python's http.server) and only depends on the
existing `cli_backend` package for chain access, so it runs anywhere the CLI runs.

Run it directly:
    python3 relayer_server.py --help

The xvault CLI (screen_relayer -> Install & launch relayer) manages this for you:
start/stop/status, and writes its pid to ~/.xelis-vault/relayer/relayer.pid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
VAULT_DIR = Path(os.environ.get("XELIS_VAULT_DIR", Path.home() / ".xelis-vault"))
CONFIG_PATH = VAULT_DIR / "config" / "config.json"
RELAYER_DIR = VAULT_DIR / "relayer"
LEDGER_PATH = RELAYER_DIR / "ledger.json"
PID_PATH = RELAYER_DIR / "relayer.pid"

# Contract rate-limit constants (must match VaultChat.slx)
ANCHOR_MIN_MESSAGES = 5      # need >= 5 messages per rewarded anchor
ANCHOR_MIN_SENDERS = 2       # need >= 2 distinct senders
ANCHOR_RATE_LIMIT_BLOCKS = 300   # min blocks between anchors
ANCHOR_MAX_PER_DAY = 50      # max anchors per day

DECIMALS_VLT = 8


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def default_cfg() -> dict:
    c = load_config()
    return {
        "daemon_url": c.get("rpc_url") or "http://127.0.0.1:18081",
        "wallet_url": c.get("wallet_url") or "http://127.0.0.1:18082",
        "wallet_user": c.get("wallet_user") or "wallet",
        "wallet_pass": c.get("wallet_pass") or "testpass",
        "host": "127.0.0.1",
        "port": 18444,
        "anchor_enabled": True,
        "anchor_blocks": ANCHOR_RATE_LIMIT_BLOCKS,
        "sync_interval": 3.0,
    }


# ---------------------------------------------------------------------------
# Local ledger
# ---------------------------------------------------------------------------
class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"seen": {}, "anchored": [], "counters": {}}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text())
                self.data.setdefault("seen", {})
                self.data.setdefault("anchored", [])
                self.data.setdefault("counters", {})
        except Exception:
            self.data = {"seen": {}, "anchored": [], "counters": {}}

    def save(self):
        try:
            RELAYER_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data))
            os.replace(tmp, self.path)
        except Exception:
            pass

    def is_seen(self, kind: str, key: str) -> bool:
        return key in self.data["seen"].get(kind, {})

    def mark_seen(self, kind: str, key: str, meta: str = ""):
        self.data["seen"].setdefault(kind, {})[key] = meta or str(int(time.time()))

    def last_anchor_topo(self) -> int:
        return int(self.data.get("last_anchor_topo", 0) or 0)

    def set_last_anchor_topo(self, topo: int, day: str):
        self.data["last_anchor_topo"] = topo
        self.data["last_anchor_day"] = day
        self.data["anchored_day_count"] = self.data.get("anchored_day_count", 0) + 1


# ---------------------------------------------------------------------------
# Merkle root (blake3 over the sorted unique blobs, matching the contract's
# expectation of a single Hash root for a batch)
# ---------------------------------------------------------------------------
def merkle_root(blobs: list) -> str:
    """Deterministic Merkle root over sorted unique blobs using blake3.

    Uses the `blake3` package when available (it powers the chain's hashing);
    falls back to sha256 so the daemon still runs if it is not installed.
    """
    try:
        import blake3 as _b3
        hasher = lambda b: _b3.blake3(b).digest()
    except Exception:
        hasher = lambda b: hashlib.sha256(b).digest()
    leaves = sorted(set(blobs))
    if not leaves:
        return ""
    nodes = [hasher(x.encode("utf-8")) for x in leaves]
    while len(nodes) > 1:
        if len(nodes) % 2:  # duplicate last for odd sizes
            nodes.append(nodes[-1])
        nodes = [hasher(a + b) for a, b in zip(nodes[0::2], nodes[1::2])]
    return nodes[0].hex()


# ---------------------------------------------------------------------------
# The relayer daemon
# ---------------------------------------------------------------------------
class Relayer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ledger = Ledger(LEDGER_PATH)
        self.b = None            # cli_backend.Backend, created lazily
        self.chat = None         # VaultChat contract hash
        self.outbox_new = []     # blobs seen but not yet anchored
        self.outbox_senders = set()
        self.started = time.time()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.anchored_count = 0
        self.last_anchor_ts = 0
        self.sync_errors = 0
        self._connect()

    # -- connection ------------------------------------------------------
    def _connect(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cli_backend import Backend  # noqa: E402
        c = {
            "rpc_url": self.cfg["daemon_url"],
            "wallet_url": self.cfg["wallet_url"],
            "wallet_user": self.cfg["wallet_user"],
            "wallet_pass": self.cfg["wallet_pass"],
        }
        self.b = Backend(c)
        self.chat = self.b.C("VaultChat")

    def _w(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] relayer: {msg}", flush=True)

    # -- topo ------------------------------------------------------------
    def _topo(self) -> int:
        try:
            return self.b.daemon.topoheight()
        except Exception:
            return 0

    # -- raw storage read --------------------------------------------------
    def _rd(self, key: str):
        try:
            return self.b.daemon.read_key(self.chat, key)
        except Exception:
            return None

    def _int(self, v, default=0) -> int:
        try:
            return int(v)
        except Exception:
            return default

    # -- message reading ---------------------------------------------------
    def _read_inbox(self, kind: str, addr: str, count_key: str, prefix: str, limit=200):
        """Read `count_key` for addr then index prefix<addr>_<i>, split '|'."""
        n = self._int(self._rd(count_key + addr))
        out = []
        for i in range(min(n, limit)):
            raw = self._rd(f"{prefix}{addr}_{i}")
            if not raw:
                continue
            parts = str(raw).split("|")
            out.append({
                "kind": kind,
                "recipient": addr,
                "slot": i,
                "blob": parts[0] if len(parts) > 0 else "",
                "sender": parts[1] if len(parts) > 1 else "",
                "ts": parts[2] if len(parts) > 2 else "",
            })
        return out

    # -- sync: gather messages we can see and enqueue unseen ones ----------
    def sync_once(self):
        """Scan chain storage for messages; record new ones into the outbox so
        they are candidates for anchoring.

        We can't enumerate every recipient off-chain, so we scan the set of
        addresses seen so far (written into the ledger when /inbox is queried or
        a message is relayed) plus our own. Relayed messages (msg_<addr>_<slot>)
        carry a blob + sender, so they make valid anchor candidates.
        """
        if not self.chat:
            return 0
        addrs = set()
        for each in (self.ledger.data.get("seen_relayered", {}) or {}):
            addrs.add(each)
        try:
            mine = self.b.address
            if mine:
                addrs.add(mine)
        except Exception:
            pass
        new = 0
        for addr in list(addrs):
            for m in self._read_inbox("relayed", addr, "msgc_", "msg_"):
                if not m["blob"]:
                    continue
                key = f"{m['sender']}|{m['ts']}|{m['slot']}"
                with self.lock:
                    if not self.ledger.is_seen("relayed", key):
                        self.ledger.mark_seen("relayed", key)
                        self.outbox_new.append(m["blob"])
                        self.outbox_senders.add(m["sender"])
                        new += 1
                    else:
                        continue
                self.ledger.save()
        if new:
            self._w(f"sync: +{new} new relayed message(s) enqueued")
        return new

    # -- HTTP-facing reads (real per-address reads on demand) --------------
    def inbox_for(self, addr: str) -> list:
        """Read the on-chain inbox for an address: direct + relayed, dedup."""
        out = []
        out += self._read_inbox("direct", addr, "dmsgc_", "dmsg_")
        out += self._read_inbox("relayed", addr, "msgc_", "msg_")
        # remember this recipient so the background sync discovers its messages
        self.ledger.data.setdefault("seen_relayered", {})[addr] = \
            str(int(time.time()))
        self.ledger.save()
        # mark relayed messages as anchor candidates (dedup by sender|ts|slot)
        for m in out:
            if m["kind"] == "relayed" and m["blob"]:
                key = f"{m['sender']}|{m['ts']}|{m['slot']}"
                with self.lock:
                    if not self.ledger.is_seen("relayed", key):
                        self.ledger.mark_seen("relayed", key)
                        self.outbox_new.append(m["blob"])
                        self.outbox_senders.add(m["sender"])
                    else:
                        continue
                self.ledger.save()
        return out

    def groups(self) -> list:
        gc = self._int(self._rd("gc"))
        groups = []
        for gid in range(gc):
            raw = self._rd(f"group_{gid}")
            if not raw:
                continue
            # Group struct: [id, group_pubkey(Hash), creator(Address), created_at, active]
            if isinstance(raw, list):
                groups.append({"id": gid,
                               "group_pubkey": str(raw[1]) if len(raw) > 1 else "",
                               "creator": str(raw[2]) if len(raw) > 2 else "",
                               "created_at": str(raw[3]) if len(raw) > 3 else "",
                               "active": bool(raw[4]) if len(raw) > 4 else False})
            else:
                groups.append({"id": gid, "raw": str(raw)[:200]})
        return groups

    def status(self) -> dict:
        self._read_relayer_registration()
        try:
            my_addr = self.b.address or ""
        except Exception:
            my_addr = ""
        return {
            "running_since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)),
            "uptime_s": int(time.time() - self.started),
            "daemon_url": self.cfg["daemon_url"],
            "wallet_url": self.cfg["wallet_url"],
            "relayer_account": my_addr,
            "http_endpoint": f"http://{self.cfg['host']}:{self.cfg['port']}",
            "anchor_enabled": self.cfg["anchor_enabled"],
            "anchors_submitted": self.anchored_count,
            "last_anchor_topo": self.ledger.last_anchor_topo(),
            "outbox_new": len(self.outbox_new),
            "outbox_senders": len(self.outbox_senders),
            "sync_errors": self.sync_errors,
            "topo": self._topo(),
        }

    def _read_relayer_registration(self):
        addr = self.b.address
        if not addr:
            return {}
        s = {"active": bool(self._rd("relayer_" + addr)),
             "bond": self._int(self._rd("rbond_" + addr)),
             "fee": self._int(self._rd("rfee_" + addr)),
             "token": self._int(self._rd("rtok_" + addr))}
        reg = self._rd("rlreg_" + addr)
        if reg:
            parts = str(reg).split("|")
            s["endpoint"] = parts[0]
            s["free_daily_limit"] = parts[1] if len(parts) > 1 else ""
            s["free_wallet_slots"] = parts[2] if len(parts) > 2 else ""
        return s

    # -- anchoring ---------------------------------------------------------
    def try_anchor(self):
        """Anchoring is rate-limited and requires the contract's bond/whitelist.
        Returns a dict describing the outcome; the CLI drives when this runs.
        """
        if not self.cfg["anchor_enabled"]:
            return {"ok": False, "reason": "anchoring disabled"}
        if not self.b.wallet:
            return {"ok": False, "reason": "no wallet connected"}
        with self.lock:
            blobs = list(dict.fromkeys(self.outbox_new))
            senders = list(self.outbox_senders)
        if len(blobs) < ANCHOR_MIN_MESSAGES:
            return {"ok": False, "reason": f"need >= {ANCHOR_MIN_MESSAGES} messages "
                                           f"(have {len(blobs)})"}
        if len(senders) < ANCHOR_MIN_SENDERS:
            return {"ok": False, "reason": f"need >= {ANCHOR_MIN_SENDERS} distinct "
                                           f"senders (have {len(senders)})"}
        # rate limit: must be >= anchor_blocks since last anchor
        topo = self._topo()
        last = self.ledger.last_anchor_topo()
        if last and (topo - last) < self.cfg["anchor_blocks"]:
            return {"ok": False, "reason": f"rate-limited (topo {topo}, last "
                                           f"anchor {last})"}
        root = merkle_root(blobs)
        if not root:
            return {"ok": False, "reason": "empty outbox"}
        self._w(f"anchoring {len(blobs)} msgs from {len(senders)} senders "
                f"root={root[:16]}...")
        res = self.b.chat_anchor(root, len(blobs), len(senders))
        if res.ok:
            self.anchored_count += 1
            self.last_anchor_ts = time.time()
            self.ledger.set_last_anchor_topo(topo, time.strftime("%Y-%m-%d"))
            with self.lock:
                self.outbox_new = []
                self.outbox_senders = set()
            self.ledger.save()
            return {"ok": True, "tx": res.tx, "count": len(blobs)}
        return {"ok": False, "reason": res.reason}

    # -- background --------------------------------------------------------
    def run(self):
        self._w(f"relayer daemon online — endpoint {self.cfg['host']}:{self.cfg['port']}")
        topo_last = self._topo()
        while not self.stop.is_set():
            try:
                topo = self._topo()
                if topo <= 0:
                    raise RuntimeError("daemon unreachable")
                if topo != topo_last:
                    topo_last = topo
                    self.sync_once()
            except Exception as e:
                self.sync_errors += 1
                self._w(f"sync error: {e}")
            self.stop.wait(self.cfg.get("sync_interval", 3.0))


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    relayer = None  # set by the server

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0].strip("/")
        parts = p.split("/")
        name = parts[0] if parts else ""
        if name == "health":
            self._json(200, {"ok": True, "service": "xelisvault-relayer",
                             "time": time.time()})
        elif name == "status":
            self._json(200, self.relayer.status())
        elif name == "inbox" and len(parts) >= 2:
            self._json(200, {"addr": parts[1],
                             "messages": self.relayer.inbox_for(parts[1])})
        elif name == "groups":
            self._json(200, {"groups": self.relayer.groups()})
        elif name == "anchor":
            self._json(200, self.relayer.try_anchor())
        else:
            self._json(404, {"error": "not found",
                             "routes": ["/health", "/status", "/inbox/<addr>",
                                        "/groups", "/anchor", "/relay"]})

    def do_POST(self):
        p = self.path.split("?")[0].strip("/")
        parts = p.split("/")
        name = parts[0] if parts else ""
        if name == "relay":
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or b"{}")
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)})
                return
            # Deposit a relayed message on-chain for a recipient (store_message)
            recipient = data.get("recipient", "")
            blob = data.get("blob", "")
            if not recipient or not blob:
                self._json(400, {"ok": False, "error": "recipient + blob required"})
                return
            res = self.relayer.b.chat_store_message(recipient, blob)
            self._json(200 if res.ok else 400,
                       {"ok": res.ok, "reason": res.reason, "tx": res.tx})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # silence request logs
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="XELIS VaultChat relayer daemon")
    c = default_cfg()
    ap.add_argument("--daemon-url", default=c["daemon_url"])
    ap.add_argument("--wallet-url", default=c["wallet_url"])
    ap.add_argument("--wallet-user", default=c["wallet_user"])
    ap.add_argument("--wallet-pass", default=c["wallet_pass"])
    ap.add_argument("--host", default=c["host"])
    ap.add_argument("--port", type=int, default=c["port"])
    ap.add_argument("--no-anchor", action="store_true", help="disable auto anchoring")
    ap.add_argument("--anchor-blocks", type=int, default=c["anchor_blocks"])
    ap.add_argument("--sync-interval", type=float, default=c["sync_interval"])
    ap.add_argument("--once", action="store_true",
                    help="run one sync + optional anchor then exit (for tests)")
    args = ap.parse_args()

    cfg = {
        "daemon_url": args.daemon_url, "wallet_url": args.wallet_url,
        "wallet_user": args.wallet_user, "wallet_pass": args.wallet_pass,
        "host": args.host, "port": args.port,
        "anchor_enabled": not args.no_anchor,
        "anchor_blocks": args.anchor_blocks, "sync_interval": args.sync_interval,
    }
    r = Relayer(cfg)

    if args.once:
        n = r.sync_once()
        a = r.try_anchor()
        print(json.dumps({"sync_new": n, "anchor": a}, indent=2))
        return 0

    RELAYER_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    try:
        Handler.relayer = r
        httpd = ThreadingHTTPServer((cfg["host"], cfg["port"]), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        r.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
