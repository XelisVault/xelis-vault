#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Relayer Daemon (relayer_daemon.py)
============================================================================
The software that runs a VaultChat relayer node.
Receives messages, stores on-chain, syncs P2P, manages plans.

Works on Linux, macOS, and Windows.
Arrow-key navigation (uses tui.py).
============================================================================
"""
from __future__ import annotations
import json, os, sys, time, threading, socket, hashlib, traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from tui import *

VAULT_DIR = Path.home() / ".xelis-vault"
CONFIG_PATH = VAULT_DIR / "config" / "relayer_config.json"
LOG_DIR = VAULT_DIR / "logs"
LOG_FILE = LOG_DIR / "relayer.log"
PENDING_DIR = VAULT_DIR / "chat" / "relayer_pending"

# ── Config ──────────────────────────────────────────────────────────────────
class Config:
    def __init__(self):
        self.data = {
            "rpc_url": "http://127.0.0.1:18081",
            "wallet_url": "http://127.0.0.1:18082",
            "wallet_user": "wallet",
            "wallet_pass": "testpass",
            "relayer_address": "",
            "listen_host": "0.0.0.0",
            "listen_port": 8080,
            "p2p_port": 9000,
            "batch_interval": 1000,
            "free_daily_limit": 100,
            "free_wallet_slots": 100,
            "vaultchat_contract": "",
            "miner_contract": "",
            "vlt_asset": "",
            "peers": [],
        }
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                stored = json.loads(CONFIG_PATH.read_text())
                for k in self.data:
                    if k in stored: self.data[k] = stored[k]
            except: pass

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.data, indent=2))

    def get(self, key, default=""):
        return self.data.get(key, default)

# ── XELIS Client ────────────────────────────────────────────────────────────
class XelisClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.auth = (cfg.get("wallet_user"), cfg.get("wallet_pass"))
        self.connected = False
        self.topoheight = 0
        self.balance = 0

    def rpc(self, method, params=None):
        try:
            r = self.session.post(self.cfg.get("rpc_url"), json={
                "jsonrpc": "2.0", "method": method, "params": params or [], "id": 1
            }, timeout=10)
            data = r.json()
            if not data.get("error"):
                self.connected = True
                return data.get("result")
            self.connected = False
            return None
        except:
            self.connected = False
            return None

    def wallet_rpc(self, method, params=None):
        try:
            r = self.session.post(self.cfg.get("wallet_url"), json={
                "jsonrpc": "2.0", "method": method, "params": params or [], "id": 1
            }, timeout=10)
            data = r.json()
            return data.get("result") if not data.get("error") else None
        except: return None

    def refresh(self):
        r = self.rpc("get_topoheight")
        self.topoheight = r if isinstance(r, int) else 0
        addr = self.cfg.get("relayer_address")
        if addr:
            b = self.wallet_rpc("get_balance", [addr, ""])
            self.balance = b.get("balance", 0) if isinstance(b, dict) else 0

    def invoke(self, contract, entry_id, params):
        """Submit a transaction to a contract."""
        try:
            r = self.session.post(self.cfg.get("wallet_url"), json={
                "jsonrpc": "2.0", "method": "invoke_contract",
                "params": [contract, entry_id, params], "id": 1
            }, timeout=30)
            data = r.json()
            return data.get("result") if not data.get("error") else None
        except: return None

# ── Logger ──────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line)

# ── Message Queue ───────────────────────────────────────────────────────────
class MessageQueue:
    def __init__(self):
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        self.messages = []
        self.load_pending()

    def load_pending(self):
        for f in PENDING_DIR.glob("*.json"):
            try:
                self.messages.append(json.loads(f.read_text()))
            except: pass

    def add(self, recipient, encrypted_blob, sender, timestamp):
        msg = {
            "recipient": recipient,
            "encrypted_blob": encrypted_blob,
            "sender": sender,
            "timestamp": timestamp,
            "queued_at": time.time(),
        }
        filename = PENDING_DIR / f"msg_{int(time.time() * 1000)}.json"
        filename.write_text(json.dumps(msg, indent=2))
        self.messages.append(msg)
        log(f"Message queued for {recipient[:16]}... ({len(self.messages)} pending)")

    def get_batch(self, max_count=100):
        return self.messages[:max_count]

    def clear_batch(self, count):
        self.messages = self.messages[count:]
        # Delete files
        files = sorted(PENDING_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime)
        for f in files[:count]:
            f.unlink()

# ── P2P Sync ────────────────────────────────────────────────────────────────
class P2PSync:
    def __init__(self, cfg):
        self.cfg = cfg
        self.peers = cfg.get("peers", [])
        self.socket = None

    def start_server(self, port):
        """Start listening for P2P connections from other relayers."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(("0.0.0.0", port))
            self.socket.listen(5)
            self.socket.settimeout(1)
            log(f"P2P server listening on port {port}")
        except Exception as e:
            log(f"P2P server failed: {e}", "ERROR")

    def accept_connections(self):
        """Accept incoming P2P connections (non-blocking)."""
        if not self.socket: return
        try:
            conn, addr = self.socket.accept()
            threading.Thread(target=self.handle_peer, args=(conn, addr), daemon=True).start()
        except socket.timeout: pass
        except Exception as e:
            log(f"P2P accept error: {e}", "ERROR")

    def handle_peer(self, conn, addr):
        """Handle a P2P connection from another relayer."""
        try:
            data = conn.recv(65536).decode()
            msg = json.loads(data)
            if msg.get("type") == "sync_request":
                # Send our message count
                response = json.dumps({"type": "sync_response", "count": len(self.peers)})
                conn.send(response.encode())
            elif msg.get("type") == "message":
                # Received a message from another relayer
                log(f"Received P2P message from {addr[0]}")
        except: pass
        finally:
            conn.close()

    def sync_with_peers(self):
        """Sync messages with all known peers."""
        for peer in self.peers:
            try:
                host = peer.get("address", "").split(":")[0]
                port = peer.get("p2p_port", 9000)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.send(json.dumps({"type": "sync_request"}).encode())
                response = sock.recv(65536).decode()
                data = json.loads(response)
                log(f"Synced with {host}: {data.get('count', 0)} messages")
                sock.close()
            except Exception as e:
                log(f"Sync failed with {peer.get('address', '?')}: {e}", "WARN")

# ── HTTP Server (for users to send messages) ───────────────────────────────
class HTTPServer:
    def __init__(self, cfg, queue, client):
        self.cfg = cfg
        self.queue = queue
        self.client = client
        self.socket = None

    def start(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.cfg.get("listen_host"), self.cfg.get("listen_port")))
            self.socket.listen(10)
            self.socket.settimeout(1)
            log(f"HTTP server listening on {self.cfg.get('listen_host')}:{self.cfg.get('listen_port')}")
        except Exception as e:
            log(f"HTTP server failed: {e}", "ERROR")

    def accept_connections(self):
        if not self.socket: return
        try:
            conn, addr = self.socket.accept()
            threading.Thread(target=self.handle_request, args=(conn, addr), daemon=True).start()
        except socket.timeout: pass
        except Exception as e:
            log(f"HTTP accept error: {e}", "ERROR")

    def handle_request(self, conn, addr):
        try:
            data = conn.recv(65536).decode()
            if "POST /send" in data:
                # Parse JSON body
                body = data.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in data else "{}"
                msg = json.loads(body)
                
                # Add to queue
                self.queue.add(
                    msg.get("recipient", ""),
                    msg.get("encrypted_blob", ""),
                    msg.get("sender", ""),
                    msg.get("timestamp", int(time.time()))
                )
                
                response = json.dumps({"status": "ok", "queued": len(self.queue.messages)})
                conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + response.encode())
            elif "GET /health" in data:
                response = json.dumps({
                    "status": "online",
                    "topoheight": self.client.topoheight,
                    "messages_queued": len(self.queue.messages),
                    "balance": self.client.balance
                })
                conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + response.encode())
            else:
                conn.send(b"HTTP/1.1 404 Not Found\r\n\r\n")
        except Exception as e:
            log(f"HTTP request error: {e}", "ERROR")
            try: conn.send(b"HTTP/1.1 500 Error\r\n\r\n")
            except: pass
        finally:
            conn.close()

# ── Batcher (stores messages on-chain) ─────────────────────────────────────
class Batcher:
    def __init__(self, cfg, client, queue):
        self.cfg = cfg
        self.client = client
        self.queue = queue
        self.last_batch = 0
        self.batch_count = 0

    def should_batch(self):
        now = self.client.topoheight
        interval = self.cfg.get("batch_interval")
        return now >= self.last_batch + interval and len(self.queue.messages) > 0

    def process_batch(self):
        if not self.should_batch(): return
        
        batch = self.queue.get_batch(100)
        if not batch: return

        log(f"Processing batch of {len(batch)} messages...")

        # Store each message on-chain
        for msg in batch:
            try:
                # Call VaultChat.store_message(recipient, encrypted_blob, timestamp)
                self.client.invoke(
                    self.cfg.get("vaultchat_contract"),
                    "store_message",  # Entry name (would be entry ID in production)
                    [msg["recipient"], msg["encrypted_blob"], msg["timestamp"]]
                )
                time.sleep(0.1)  # Rate limit
            except Exception as e:
                log(f"Failed to store message: {e}", "ERROR")
                break

        # Compute Merkle root and anchor
        merkle_root = self._compute_merkle(batch)
        try:
            self.client.invoke(
                self.cfg.get("vaultchat_contract"),
                "anchor_batch",
                [merkle_root, len(batch)]
            )
            self.batch_count += 1
            self.last_batch = self.client.topoheight
            self.queue.clear_batch(len(batch))
            log(f"Batch anchored: {len(batch)} messages, root={merkle_root[:16]}...")
        except Exception as e:
            log(f"Anchor failed: {e}", "ERROR")

    def _compute_merkle(self, messages):
        if not messages: return "0" * 64
        hashes = [hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest() for m in messages]
        while len(hashes) > 1:
            if len(hashes) % 2 != 0: hashes.append(hashes[-1])
            next_level = []
            for i in range(0, len(hashes), 2):
                next_level.append(hashlib.sha256((hashes[i] + hashes[i+1]).encode()).hexdigest())
            hashes = next_level
        return hashes[0]

# ── Dashboard ───────────────────────────────────────────────────────────────
def render_dashboard(cfg, client, queue, batcher, p2p, http_server):
    clear()
    now = datetime.now().strftime("%H:%M:%S")
    addr = cfg.get("relayer_address") or "(not set)"
    conn = f"{C.GREEN}CONNECTED{C.RESET}" if client.connected else f"{C.RED}OFFLINE{C.RESET}"

    print(f"{C.CYAN}{C.BOLD}  XELIS Vault — Relayer Daemon{C.RESET}")
    print(f"{C.GRAY}{'=' * 60}{C.RESET}")
    print(f"{C.DIM}  {now}  |  Topo: {client.topoheight}  |  {conn}  |  {addr[:20]}...{C.RESET}")
    print(f"{C.GRAY}{'=' * 60}{C.RESET}")

    # Status
    lines = [
        f"  Status:          {C.GREEN}RUNNING{C.RESET}",
        f"  HTTP Endpoint:   http://{cfg.get('listen_host')}:{cfg.get('listen_port')}",
        f"  P2P Port:        {cfg.get('p2p_port')}",
        f"  Batch interval:  {cfg.get('batch_interval')} blocks (~{cfg.get('batch_interval') * 5 // 60} min)",
        f"  Balance:         {client.balance / 1e8:.4f} XEL",
        f"  Batch count:     {batcher.batch_count}",
    ]
    print()
    print(box("RELAYER STATUS", lines, C.CYAN))

    # Queue
    q_lines = [
        f"  Pending messages:  {len(queue.messages)}",
        f"  Next batch in:     {max(0, cfg.get('batch_interval') - (client.topoheight - batcher.last_batch))} blocks",
    ]
    print()
    print(box("MESSAGE QUEUE", q_lines, C.YELLOW))

    # Network
    peer_lines = [
        f"  Known peers:  {len(cfg.get('peers'))}",
        f"  HTTP server:  {'Listening' if http_server.socket else 'Stopped'}",
        f"  P2P server:   {'Listening' if p2p.socket else 'Stopped'}",
    ]
    print()
    print(box("NETWORK", peer_lines, C.MAGENTA))

    print()
    print(f"{C.GRAY}{'=' * 60}{C.RESET}")
    print(f"{C.DIM}  q Quit  r Refresh  s Setup  p Peers{C.RESET}")

# ── Setup ───────────────────────────────────────────────────────────────────
def interactive_setup(cfg):
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}Relayer Setup{C.RESET}\n")
    print(f"  {C.GRAY}{'=' * 56}{C.RESET}\n")

    cfg.data["rpc_url"] = text_input("Daemon RPC URL", cfg.get("rpc_url"))
    cfg.data["wallet_url"] = text_input("Wallet RPC URL", cfg.get("wallet_url"))
    cfg.data["relayer_address"] = text_input("Your relayer XELIS address", cfg.get("relayer_address"))
    
    listen_host = menu("Listen address", [
        ("0.0.0.0 (all interfaces — recommended)", "0.0.0.0"),
        ("127.0.0.1 (localhost only — testing)", "127.0.0.1"),
    ])
    if listen_host: cfg.data["listen_host"] = listen_host
    
    cfg.data["listen_port"] = int(text_input("HTTP port", str(cfg.get("listen_port"))))
    cfg.data["p2p_port"] = int(text_input("P2P port", str(cfg.get("p2p_port"))))
    
    batch_choice = menu("Batch interval (how often to store on-chain)", [
        ("Fast: 100 blocks (~8 min, more gas)", "100"),
        ("Normal: 1000 blocks (~80 min, balanced)", "1000"),
        ("Slow: 20160 blocks (~1 week, cheapest)", "20160"),
    ])
    if batch_choice: cfg.data["batch_interval"] = int(batch_choice)
    
    cfg.data["free_daily_limit"] = int(text_input("Free messages per day per user", str(cfg.get("free_daily_limit"))))
    cfg.data["free_wallet_slots"] = int(text_input("Free slots per day (total users)", str(cfg.get("free_wallet_slots"))))
    
    cfg.data["vaultchat_contract"] = text_input("VaultChat contract hash", cfg.get("vaultchat_contract"))
    cfg.data["miner_contract"] = text_input("XelisVaultMiner contract hash", cfg.get("miner_contract"))
    cfg.data["vlt_asset"] = text_input("VLT asset hash", cfg.get("vlt_asset"))

    cfg.save()
    info_box("Setup Complete", [
        "Configuration saved!", "",
        f"HTTP: http://{cfg.get('listen_host')}:{cfg.get('listen_port')}",
        f"P2P:  port {cfg.get('p2p_port')}",
        f"Batch: every {cfg.get('batch_interval')} blocks",
        "",
        "Ready to start relaying.",
    ])

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="XELIS Vault Relayer Daemon")
    parser.add_argument("--rpc", help="Daemon RPC URL")
    parser.add_argument("--wallet-url", help="Wallet RPC URL")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup")
    parser.add_argument("-y", "--yes", action="store_true")
    args = parser.parse_args()

    cfg = Config()
    if args.rpc: cfg.data["rpc_url"] = args.rpc
    if args.wallet_url: cfg.data["wallet_url"] = args.wallet_url
    if args.setup:
        interactive_setup(cfg)
        return

    # Check if configured
    if not cfg.get("relayer_address") or not cfg.get("vaultchat_contract"):
        clear()
        print(BANNER)
        print(f"\n{C.YELLOW}{'=' * 60}{C.RESET}")
        print(f"{C.YELLOW}  !  RELAYER NOT CONFIGURED{C.RESET}")
        print(f"{C.YELLOW}{'=' * 60}{C.RESET}")
        print(f"\n{C.BOLD}The relayer daemon needs configuration.{C.RESET}")
        print(f"Run: xvault-relayer --setup\n")
        return

    client = XelisClient(cfg)
    queue = MessageQueue()
    batcher = Batcher(cfg, client, queue)
    p2p = P2PSync(cfg)
    http_server = HTTPServer(cfg, queue, client)

    # Start servers
    p2p.start_server(cfg.get("p2p_port"))
    http_server.start()

    client.refresh()

    running = [True]
    def on_signal(sig, frame): running[0] = False
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    log("Relayer daemon started")
    last_refresh = time.time()
    last_sync = time.time()

    hide_cursor()
    try:
        while running[0]:
            # Render dashboard
            render_dashboard(cfg, client, queue, batcher, p2p, http_server)

            # Accept connections
            http_server.accept_connections()
            p2p.accept_connections()

            # Refresh data every 5 seconds
            now = time.time()
            if now - last_refresh > 5:
                client.refresh()
                last_refresh = now

            # Process batch if needed
            batcher.process_batch()

            # Sync with peers every 60 seconds
            if now - last_sync > 60 and cfg.get("peers"):
                p2p.sync_with_peers()
                last_sync = now

            # Check for key press (non-blocking, 1s timeout)
            key = read_key_timeout(1)
            if key in ("Q", "CTRL_C", "CTRL_D"):
                break
            elif key == "S":
                show_cursor()
                interactive_setup(cfg)
                client = XelisClient(cfg)
                queue = MessageQueue()
                batcher = Batcher(cfg, client, queue)
                p2p = P2PSync(cfg)
                http_server = HTTPServer(cfg, queue, client)
                p2p.start_server(cfg.get("p2p_port"))
                http_server.start()
                hide_cursor()
            elif key == "P":
                # Show peers
                peers = cfg.get("peers", [])
                lines = [f"  {p.get('address', '?')}:{p.get('p2p_port', 9000)}" for p in peers]
                if not lines: lines = ["  (no peers configured)"]
                info_box("P2P Peers", lines)
    finally:
        show_cursor()
        clear()
        log("Relayer daemon stopped")
        print(f"\n{C.CYAN}{C.BOLD}  Relayer stopped. Goodbye!{C.RESET}\n")

if __name__ == "__main__":
    main()
