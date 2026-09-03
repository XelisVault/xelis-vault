#!/usr/bin/env python3
"""
 ============================================================================
  XELIS Vault — Onboarding Wizard (auto-configuration)
 ============================================================================
 Zero-config onboarding for xvault-miner:

   1. Wallet: detect a running wallet RPC, connect to it, or bootstrap a new
      one (download official xelis_wallet release binary when available,
      create/import wallet non-interactively, launch it in background).
      Seeds are generated LOCALLY with the exact Xelis mnemonic scheme
      (1626-word English list, 24 words + CRC32 checksum word) and shown once.
   2. Daemon: auto-detect local node, allow custom URL, or continue offline
      (degraded dashboard only).
   3. Contracts: loaded automatically from network/testnet.json bundled in
      the repository — the user never types contract addresses.

 Everything is saved to ~/.xelis-vault/config/config.json so subsequent
 launches skip straight to the dashboard.
 ============================================================================
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
import zlib
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent))
from tui import C, BANNER, clear, menu, text_input, confirm, info_box

VAULT_DIR = Path.home() / ".xelis-vault"
BIN_DIR = VAULT_DIR / "bin"
LOG_DIR = VAULT_DIR / "logs"
WALLETS_DIR = VAULT_DIR / "wallets"
WORDLIST_PATH = Path(__file__).parent / "xelis_wordlist_english.txt"

GITHUB_API = "https://api.github.com/repos/xelis-project/xelis-blockchain/releases/latest"

# Release asset names -> (platform.system(), platform.machine()) patterns
ASSET_MAP = {
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu.tar.gz",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu.tar.gz",
    ("Linux", "armv7l"): "armv7-unknown-linux-gnueabihf.tar.gz",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc.zip",
}

DEFAULT_DAEMONS = ["http://127.0.0.1:18081"]
PUBLIC_NODE = "https://testnet-node.xelis.io"


def _detached_kwargs() -> dict:
    """subprocess kwargs that keep a child wallet/miner alive after the parent
    (xvault) exits — essential on Windows.

    On POSIX we use start_new_session (new process group/session) so the child
    is not killed when the controlling terminal closes. On Windows we detach the
    child from the parent console and put it in its own process group so it does
    not receive CTRL_CLOSE_EVENT / CTRL_C_EVENT when the xvault console closes.

    stdin is always explicitly redirected to DEVNULL: with DETACHED_PROCESS on
    Windows there is no console to inherit stdin from, and letting Popen try to
    duplicate the parent's (invalid) stdin handle raises
    `OSError: [WinError 6] The handle is invalid` — this is what previously
    crashed the miner/wallet/relayer/tunnel right after launch (see miner.log).
    """
    import subprocess as _sp
    if platform.system() == "Windows":
        return {"creationflags": _sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP,
                "stdin": _sp.DEVNULL}
    return {"start_new_session": True, "stdin": _sp.DEVNULL}


# ---------------------------------------------------------------------------
# Xelis mnemonic scheme (identical to xelis_wallet/src/mnemonics)
# ---------------------------------------------------------------------------

def _load_wordlist() -> list:
    if not WORDLIST_PATH.exists():
        return []
    return [w.strip() for w in WORDLIST_PATH.read_text().splitlines() if w.strip()]


_CURVE25519_L = 2**252 + 27742317777372353535851937790883648493


def _random_valid_scalar() -> bytes:
    """Random canonical curve25519 scalar (what KeyPair::new() generates)."""
    while True:
        k = int.from_bytes(os.urandom(32), "little") % _CURVE25519_L
        if k > 0:
            return k.to_bytes(32, "little")


def generate_seed_phrase(wordlist: Optional[list] = None) -> list:
    """Random wallet -> 24 words + checksum word (English, Xelis scheme).

    Xelis mnemonics: 8 groups of 3 words encode 4 little-endian bytes each;
    the 25th word is a REPEAT of the word at position crc32(prefixes)%24.
    """
    W = wordlist or _load_wordlist()
    if len(W) != 1626:
        raise RuntimeError("english wordlist missing or invalid")
    N = len(W)
    key = _random_valid_scalar()
    words = []
    for i in range(0, 32, 4):
        val = int.from_bytes(key[i:i + 4], "little")
        a = val % N
        b = ((val // N) + a) % N
        c = ((val // N // N) + b) % N
        words += [W[a], W[b], W[c]]
    prefix = "".join(w[:3].lower() for w in words)
    words.append(words[zlib.crc32(prefix.encode()) % 24])
    return words


def validate_seed_phrase(phrase: str, wordlist: Optional[list] = None) -> bool:
    """Check words exist in list + sanity + optional checksum word (lenient)."""
    W = wordlist or _load_wordlist()
    if not W:
        return True  # cannot validate without list — accept
    S = set(W)
    words = phrase.lower().strip().replace("\n", " ").split()
    if len(words) not in (24, 25):
        return False
    if any(w not in S for w in words[:24]):
        return False
    N = len(W)
    for i in range(0, 24, 3):
        a, b, c = (W.index(w) for w in words[i:i + 3])
        val = a + N * (((N - a) + b) % N) + N * N * (((N - b) + c) % N)
        if val % N != a:
            return False
    if len(words) == 25:
        prefix = "".join(w[:3].lower() for w in words[:24])
        if words[24] != words[zlib.crc32(prefix.encode()) % 24]:
            return False
    return True


# ---------------------------------------------------------------------------
# Network config (contracts bundle)
# ---------------------------------------------------------------------------

def load_network_bundle() -> dict:
    for candidate in (Path(__file__).parent.parent / "network" / "testnet.json",
                      Path(__file__).parent / "network_testnet.json"):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except Exception:
                pass
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rpc_call(url: str, method: str, params=None, auth=None, timeout=5):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        payload["params"] = params
    r = requests.post(url.rstrip("/") + "/json_rpc" if not url.endswith("/json_rpc") else url,
                      json=payload, auth=auth, timeout=timeout)
    data = r.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"])[:120])
    return data.get("result")


def find_wallet_binary() -> Optional[str]:
    exe = "xelis_wallet.exe" if platform.system() == "Windows" else "xelis_wallet"
    candidates = [
        BIN_DIR / exe,
        Path.home() / ".xelis" / exe,
        Path.home() / "xelis" / exe,
        shutil.which("xelis_wallet"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def download_wallet_binary() -> Optional[str]:
    """Download official release binary (Linux/Windows). macOS unsupported."""
    system, machine = platform.system(), platform.machine()
    asset_suffix = ASSET_MAP.get((system, machine))
    print(f"\n  {C.DIM}Downloading the official xelis wallet…{C.RESET}")
    try:
        rel = requests.get(GITHUB_API, timeout=30).json()
        tag = rel.get("tag_name", "")
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        name = next((n for n in assets if n.endswith(asset_suffix)), None) if asset_suffix else None
        if not name:
            print(f"  {C.RED}No prebuilt binary for {system}/{machine}.{C.RESET}")
            return None
        url = assets[name]
        dest = BIN_DIR / name
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  {C.DIM}{name} ({tag})…{C.RESET}")
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = min(100, done * 100 // total)
                        print(f"\r  {C.CYAN}{pct}%{C.RESET}", end="", flush=True)
        print()
        if dest.suffix == ".zip":
            with zipfile.ZipFile(dest) as z:
                for member in z.infolist():
                    target = BIN_DIR / member.filename
                    if not str(target).startswith(str(BIN_DIR)):
                        raise ValueError(f"unsafe zip member: {member.filename}")
                z.extractall(BIN_DIR)
        else:
            with tarfile.open(dest) as t:
                for member in t.getmembers():
                    target = BIN_DIR / member.name
                    if not str(target).startswith(str(BIN_DIR)):
                        raise ValueError(f"unsafe tar member: {member.name}")
                t.extractall(BIN_DIR)
        dest.unlink(missing_ok=True)
        exe = BIN_DIR / ("xelis_wallet.exe" if system == "Windows" else "xelis_wallet")
        if exe.exists():
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return str(exe)
        # some archives nest a folder
        found = next(BIN_DIR.rglob("xelus_wallet*"), None) or next(
            (p for p in BIN_DIR.rglob("*xelis_wallet*") if p.is_file()), None)
        if found:
            found.chmod(found.stat().st_mode | stat.S_IEXEC)
            return str(found)
    except Exception as e:
        print(f"  {C.RED}Download error: {e}{C.RESET}")
    return None


def free_port(start: int = 18082, avoid=()) -> int:
    import socket
    used = set(avoid)
    port = start
    while port < start + 200:
        if port in used:
            port += 1
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            port += 1
        finally:
            try:
                s.close()
            except Exception:
                pass
    raise RuntimeError("no free port")


def launch_wallet(binary: str, network: str, daemon_url: str, password: str,
                  wallet_dir: Path, rpc_port: int, seed: Optional[str] = None,
                  rpc_user: str = "wallet", rpc_pass: str = "testpass") -> subprocess.Popen:
    wallet_dir.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_DIR / "wallet.log", "ab")
    cmd = [
        binary,
        "--network", network,
        "--daemon-address", daemon_url,
        "--password", password,
        "--wallet-path", str(wallet_dir),
        "--rpc-bind-address", f"127.0.0.1:{rpc_port}",
        "--rpc-username", rpc_user,
        "--rpc-password", rpc_pass,
        "--logs-path", str(LOG_DIR) + os.sep,
        "--disable-ascii-art",
    ]
    if seed:
        cmd += ["--seed", seed]
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                            **_detached_kwargs())
    return proc


def wait_for_wallet(url: str, auth, timeout_s: int = 90) -> Optional[str]:
    """Wait for the wallet RPC to become responsive.

    Uses a 1-second polling interval for fast detection of wallet readiness.
    Returns the wallet address on success, None on timeout.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            addr = rpc_call(url, "get_address", auth=auth, timeout=2)
            if isinstance(addr, dict):
                addr = addr.get("address")
            if addr:
                return addr
        except Exception:
            pass
        time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# Onboarding steps
# ---------------------------------------------------------------------------

def ensure_wallet(cfg) -> bool:
    """Returns True when cfg has a working wallet connection."""
    wurl = cfg.get("wallet_url", "http://127.0.0.1:18082")
    user, pwd = cfg.get("wallet_user", "wallet"), cfg.get("wallet_pass", "testpass")

    def _try(url, u, p):
        try:
            addr = rpc_call(url, "get_address", auth=(u, p), timeout=4)
            if isinstance(addr, dict):
                addr = addr.get("address")
            return addr
        except Exception:
            return None

    # already configured & reachable?
    addr = _try(wurl, user, pwd)
    if addr:
        cfg.data["miner_address"] = cfg.data.get("miner_address") or addr
        info_box("Wallet detected", [f"Connected to {wurl}", f"Address: {addr[:34]}…"])
        return True

    clear()
    print(BANNER)
    choice = menu("Welcome to XELIS Vault! Do you already have a running Xelis wallet?", [
        ("Yes — connect to it (RPC URL + credentials)", "connect"),
        ("No — set everything up for me automatically", "bootstrap"),
        ("Use a public daemon without a wallet (read-only)", "readonly"),
    ])
    if choice is None:
        return False

    if choice == "connect":
        while True:
            wurl = text_input("Wallet RPC URL", wurl)
            user = text_input("RPC username", user)
            pwd = text_input("RPC password", pwd, password=True)
            addr = _try(wurl, user, pwd)
            if addr:
                cfg.data.update({"wallet_url": wurl, "wallet_user": user,
                                 "wallet_pass": pwd, "miner_address": addr})
                cfg.save()
                info_box("Wallet connected ✓", [f"{wurl}", f"Address: {addr[:34]}…"])
                return True
            print(f"  {C.RED}Could not connect ({wurl}). Try again.{C.RESET}")
            if not confirm("Retry?", default_yes=True):
                return False

    if choice == "readonly":
        cfg.data["wallet_url"] = ""
        cfg.data["miner_address"] = ""
        cfg.save()
        return True

    # ---- full bootstrap ----------------------------------------------------
    binary = find_wallet_binary()
    if not binary:
        if platform.system() == "Darwin":
            print(f"\n  {C.YELLOW}macOS: no official prebuilt binary is published by Xelis.{C.RESET}")
            print(f"  {C.DIM}Building from source is required (~10 min):{C.RESET}")
            print(f"  {C.DIM}  git clone https://github.com/xelis-project/xelis-blockchain{C.RESET}")
            print(f"  {C.DIM}  cargo build --release -p xelis-wallet{C.RESET}")
            print(f"  {C.DIM}Then run xvault again.\n{C.RESET}")
            input("  Press Enter to exit... ")
            return False
        binary = download_wallet_binary()
        if not binary:
            input("  Press Enter to exit... ")
            return False
    print(f"  {C.GREEN}Wallet binary: {binary}{C.RESET}")

    network = menu("Select network:", [("Testnet (recommended to start)", "testnet"),
                                       ("Mainnet", "mainnet")]) or "testnet"
    # Default to the public node: a local daemon is NOT required.
    daemon_url = cfg.get("rpc_url") or (PUBLIC_NODE if network == "testnet" else DEFAULT_DAEMONS[0])

    mode = menu("Create or import a wallet?", [
        ("Create a NEW wallet (seed generated & shown once)", "create"),
        ("Import an existing seed (24/25 words)", "import"),
    ])
    if mode is None:
        return False

    seed = None
    password = "xvault-" + os.urandom(9).hex()
    if mode == "create":
        # CRITICAL: generate the phrase FIRST and pass it to the wallet so
        # the displayed backup controls the wallet actually created.
        try:
            seed = " ".join(generate_seed_phrase())
        except Exception as e:
            print(f"  {C.RED}Could not generate a seed locally ({e}).{C.RESET}")
            input("  Press Enter to exit... ")
            return False
    else:
        while True:
            phrase = text_input("Paste your seed (24/25 words)")
            if validate_seed_phrase(phrase):
                seed = phrase.strip()
                break
            print(f"  {C.RED}Invalid seed (unknown words / wrong length). Try again.{C.RESET}")

    rpc_port = free_port(int(wurl.split(":")[-1].split("/")[0]) if ":18" in wurl else 18082)
    wdir = WALLETS_DIR / f"xvault-{network}"
    print(f"\n  {C.DIM}Launching wallet (first sync may take a few minutes)...{C.RESET}")
    launch_wallet(binary, network, daemon_url, password, wdir, rpc_port, seed=seed)

    url = f"http://127.0.0.1:{rpc_port}"
    addr = wait_for_wallet(url, ("wallet", password), timeout_s=120)
    if not addr:
        print(f"  {C.RED}Wallet did not answer on {url}. Logs: ~/.xelis-vault/logs/wallet.log{C.RESET}")
        return False

    cfg.data.update({
        "wallet_url": url, "wallet_user": "wallet", "wallet_pass": password,
        "wallet_binary": binary, "wallet_network": network,
        "wallet_password": password, "wallet_path": str(wdir),
        "wallet_rpc_port": rpc_port, "miner_address": addr,
    })
    cfg.save()

    if mode == "create":
        phrase = seed.split()  # exactly the words passed to --seed above
        # Write the seed to a local (chmod 600) backup file as a safety net, so
        # the wallet is never left unrecoverable even if the terminal display
        # fails or the user closes the window mid-flow.
        backup_file = None
        try:
            (VAULT_DIR / "seed_backup").mkdir(parents=True, exist_ok=True)
            backup_file = VAULT_DIR / "seed_backup" / f"{network}-{addr[:12]}.seed.txt"
            backup_file.write_text("".join(f"{i+1:>2}. {w}\n" for i, w in enumerate(phrase)))
            backup_file.chmod(0o600)
        except Exception:
            backup_file = None

        def _show_seed():
            clear()
            print(BANNER)
            print(f"\n{C.GREEN}{C.BOLD}  WALLET CREATED!{C.RESET}")
            print(f"  Address: {C.BOLD}{addr}{C.RESET}\n")
            print(f"  {C.RED}{C.BOLD}╔══════════════════════════════════════════════════════════╗{C.RESET}")
            print(f"  {C.RED}{C.BOLD}║  BACK UP YOUR SEED — SHOWN ONLY ONCE!                     ║{C.RESET}")
            print(f"  {C.RED}{C.BOLD}║  Write it down on paper. Without it your funds are lost.  ║{C.RESET}")
            print(f"  {C.RED}{C.BOLD}╚══════════════════════════════════════════════════════════╝{C.RESET}\n")
            for i in range(0, 25, 5):
                row = phrase[i:i + 5]
                print("  " + "  ".join(f"{C.BOLD}{j+1:>2}.{C.RESET}{w:<12}" for j, w in
                                        zip(range(i, i + 5), row)))
            if backup_file:
                print(f"  {C.DIM}A backup copy was saved to:{C.RESET}")
                print(f"  {C.YELLOW}{backup_file}{C.RESET}")
            print()
            sys.stdout.flush()  # ensure the seed is written even on a slow/redirected console

        _show_seed()
        input("  Press Enter once you have written down all 25 words... ")
        _show_seed()
        # Confirm the user actually captured the seed: retry on mismatch so they
        # can never walk away with an unrecoverable wallet.
        while True:
            typed = text_input("Type word #13 to confirm you backed it up").strip().lower()
            if typed == phrase[12].lower():
                break
            print(f"  {C.YELLOW}That doesn't match word #13 shown above. Copy it exactly.{C.RESET}")
            _show_seed()
        info_box("Wallet ready", [
            f"Binary : {binary}",
            f"Folder : {wdir}",
            f"RPC    : {url}",
            "",
            f"Wallet file password: {password}",
            "(saved in local config)",
        ] + (["", f"Seed backup: {backup_file}"] if backup_file else []))
    else:
        info_box("Wallet imported ✓", [f"RPC: {url}", f"Address: {addr[:34]}…"])
    return True


def ensure_daemon(cfg) -> bool:
    """Pick the chain data source: public node first, then local daemon.

    The public node needs NO local daemon at all — every read used by the CLI
    (get_info / get_contract_data / get_balance / get_nonce) works remotely,
    so this is the default for new users.
    """
    candidates = []
    if cfg.get("rpc_url"):
        candidates.append(cfg.get("rpc_url"))
    candidates += [PUBLIC_NODE] + DEFAULT_DAEMONS

    for url in candidates:
        try:
            topo = rpc_call(url, "get_topoheight")
            cfg.data["rpc_url"] = url
            cfg.data["mode"] = "local" if "127.0.0.1" in url else "remote"
            cfg.save()
            info_box("Network connected ✓", [
                f"{url}",
                f"Topoheight: {topo}",
                "(public node — no local daemon needed)" if "127.0.0.1" not in url else "",
            ])
            return True
        except Exception:
            continue

    clear()
    print(BANNER)
    choice = menu("No Xelis node found. How do you want to continue?", [
        ("Enter a daemon URL", "custom"),
        ("Continue offline (degraded dashboard)", "offline"),
    ])
    if choice == "custom":
        url = text_input("Daemon RPC URL", DEFAULT_DAEMONS[0])
        try:
            rpc_call(url, "get_topoheight")
            cfg.data["rpc_url"] = url
            cfg.save()
            return True
        except Exception as e:
            print(f"  {C.RED}Unreachable: {e}{C.RESET}")
            time.sleep(2)
    elif choice == "offline":
        cfg.data.setdefault("rpc_url", DEFAULT_DAEMONS[0])
        cfg.save()
        return True
    return True


# ---------------------------------------------------------------------------
# Miner auto-configuration
# ---------------------------------------------------------------------------

def find_miner_binary() -> Optional[str]:
    exe = "xelis_miner.exe" if platform.system() == "Windows" else "xelis_miner"
    # Also check script directory and current working directory
    script_dir = Path(__file__).parent.parent.parent / "bin"
    cwd = Path.cwd() / "bin"
    candidates = [
        BIN_DIR / exe,
        script_dir / exe,
        cwd / exe,
        Path.cwd() / exe,
        Path.home() / ".xelis" / exe,
        Path.home() / "xelis" / exe,
        shutil.which("xelis_miner"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def download_miner_binary() -> Optional[str]:
    """Download official xelis_miner from the same release as the wallet."""
    system, machine = platform.system(), platform.machine()
    asset_suffix = ASSET_MAP.get((system, machine))
    if not asset_suffix:
        print(f"  {C.RED}No prebuilt binary for {system}/{machine}.{C.RESET}")
        return None
    print(f"\n  {C.DIM}Downloading the official xelis miner…{C.RESET}")
    try:
        rel = requests.get(GITHUB_API, timeout=30).json()
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        name = next((n for n in assets if n.endswith(asset_suffix)), None)
        if not name:
            return None
        dest = BIN_DIR / name
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        with requests.get(assets[name], stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    f.write(chunk)
        if dest.suffix == ".zip":
            with zipfile.ZipFile(dest) as z:
                for member in z.infolist():
                    target = BIN_DIR / member.filename
                    if not str(target).startswith(str(BIN_DIR)):
                        raise ValueError(f"unsafe zip member: {member.filename}")
                z.extractall(BIN_DIR)
        else:
            with tarfile.open(dest) as t:
                for member in t.getmembers():
                    target = BIN_DIR / member.name
                    if not str(target).startswith(str(BIN_DIR)):
                        raise ValueError(f"unsafe tar member: {member.name}")
                t.extractall(BIN_DIR)
        dest.unlink(missing_ok=True)
        exe = BIN_DIR / ("xelis_miner.exe" if system == "Windows" else "xelis_miner")
        if exe.exists():
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return str(exe)
        found = next((p for p in BIN_DIR.rglob("*xelis_miner*") if p.is_file()), None)
        if found:
            found.chmod(found.stat().st_mode | stat.S_IEXEC)
            return str(found)
    except Exception as e:
        print(f"  {C.RED}Download error: {e}{C.RESET}")
    return None


MINER_PID_FILE = VAULT_DIR / "miner.pid"


def miner_running() -> Optional[int]:
    try:
        pid = int(MINER_PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        MINER_PID_FILE.unlink(missing_ok=True)
        return None


def start_miner(cfg) -> tuple[bool, str]:
    """Launch xelis_miner against the configured daemon (local OR public node).

    The official node serves mining work over WebSocket, so remote mining
    works without any local daemon.
    """
    pid = miner_running()
    if pid:
        return True, f"miner already running (pid {pid})"

    binary = cfg.get("miner_binary") or find_miner_binary()
    if not binary:
        # Try to download on all platforms (including macOS)
        binary = download_miner_binary()
    if not binary:
        system = platform.system()
        exe = "xelis_miner.exe" if system == "Windows" else "xelis_miner"
        return False, (f"xelis_miner not found — download it from "
                       f"https://github.com/xelis-project/xelis-blockchain/releases "
                       f"and place it in {BIN_DIR}/{exe}, or run with --setup")
    cfg.data["miner_binary"] = binary

    addr = cfg.get("miner_address")
    if not addr:
        return False, "no wallet address configured yet"

    daemon = cfg.get("rpc_url") or PUBLIC_NODE
    threads = str(cfg.get("miner_threads") or max(1, (os.cpu_count() or 2) - 1))
    cfg.data["miner_threads"] = threads
    cfg.save()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_DIR / "miner.log", "ab")
    cmd = [binary, "--miner-address", addr, "--daemon-address",
           daemon.replace("http", "ws", 1) if daemon.startswith("http") else daemon,
           "-n", threads, "--disable-ascii-art"]
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                            **_detached_kwargs())
    MINER_PID_FILE.write_text(str(proc.pid))
    return True, f"miner started (pid {proc.pid}, {threads} thread(s), node: {daemon})"


def _terminate(pid: int, tree: bool = True) -> None:
    """Terminate a process, cross-platform.

    - Windows: taskkill /F /T (kills the whole process tree — required for
      cloudflared, which spawns worker children; a bare os.kill(SIGTERM)
      does not exist there and would leave orphans).
    - POSIX: SIGTERM, wait ~2s, then SIGKILL if still alive.
    """
    if platform.system() == "Windows":
        import subprocess as _sp
        cmd = ["taskkill", "/PID", str(pid), "/F"]
        if tree:
            cmd.append("/T")
        _sp.run(cmd, capture_output=True, timeout=15)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    import time as _t
    for _ in range(10):
        _t.sleep(0.2)
        try:
            os.kill(pid, 0)
        except OSError:
            return  # exited
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def stop_miner() -> tuple[bool, str]:
    pid = miner_running()
    if not pid:
        return False, "miner is not running"
    try:
        _terminate(pid)
        time.sleep(1)
        MINER_PID_FILE.unlink(missing_ok=True)
        return True, f"miner stopped (pid {pid})"
    except OSError as e:
        return False, f"could not stop pid {pid}: {e}"


def ensure_miner_configured(cfg) -> None:
    """Detect/download the miner once during onboarding; never blocks."""
    if not cfg.get("miner_binary"):
        b = find_miner_binary()
        if b:
            cfg.data["miner_binary"] = b
            cfg.data.setdefault(
                "miner_threads", max(1, (os.cpu_count() or 2) - 1))
            cfg.save()


# ---------------------------------------------------------------------------
# VaultChat relayer daemon management
# ---------------------------------------------------------------------------
RELAYER_DIR = VAULT_DIR / "relayer"
RELAYER_PID_FILE = RELAYER_DIR / "relayer.pid"
RELAYER_SCRIPT = Path(__file__).parent / "relayer_server.py"
RELAYER_DEFAULT_PORT = 18444


def relayer_running() -> Optional[int]:
    try:
        pid = int(RELAYER_PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        RELAYER_PID_FILE.unlink(missing_ok=True)
        return None


def relayer_health(cfg, port: Optional[int] = None, timeout: float = 1.0) -> bool:
    port = port or int(cfg.get("relayer_port") or RELAYER_DEFAULT_PORT)
    try:
        import urllib.request
        host = cfg.get("relayer_host") or "127.0.0.1"
        with urllib.request.urlopen(f"http://{host}:{port}/health",
                                    timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_relayer(cfg) -> tuple[bool, str]:
    """Launch the VaultChat relayer daemon (relayer_server.py) detached."""
    pid = relayer_running()
    if pid:
        return True, f"relayer already running (pid {pid})"
    if not RELAYER_SCRIPT.exists():
        return False, (f"relayer_server.py not found at {RELAYER_SCRIPT} — "
                       "re-sync your scripts to ~/.xelis-vault/src/scripts/")
    if not cfg.get("wallet_url"):
        return False, "no wallet configured — configure a wallet first"

    daemon = cfg.get("rpc_url") or PUBLIC_NODE
    wallet_user = cfg.get("wallet_user") or "wallet"
    wallet_pass = cfg.get("wallet_pass") or "testpass"
    port = int(cfg.get("relayer_port") or RELAYER_DEFAULT_PORT)
    host = cfg.get("relayer_host") or "127.0.0.1"

    RELAYER_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_DIR / "relayer.log", "ab")
    cmd = [sys.executable, str(RELAYER_SCRIPT),
           "--daemon-url", daemon,
           "--wallet-url", cfg.get("wallet_url", ""),
           "--wallet-user", wallet_user,
           "--wallet-pass", wallet_pass,
           "--host", host,
           "--port", str(port)]
    if not cfg.get("relayer_anchor", True):
        cmd.append("--no-anchor")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                            **_detached_kwargs())
    RELAYER_PID_FILE.write_text(str(proc.pid))
    print(f"  {C.DIM}relayer starting (pid {proc.pid}) — waiting for the "
          f"HTTP endpoint on {host}:{port}…{C.RESET}", flush=True)

    # health-check: wait up to ~12s for the HTTP endpoint to answer
    for _ in range(12):
        time.sleep(1)
        if relayer_health(cfg, port):
            return True, (f"relayer started (pid {proc.pid}) — endpoint "
                          f"http://{host}:{port}")
    return True, (f"relayer started (pid {proc.pid}) — HTTP endpoint not yet "
                  f"up on http://{host}:{port}; check ~/.xelis-vault/logs/relayer.log")


def stop_relayer() -> tuple[bool, str]:
    pid = relayer_running()
    if not pid:
        return False, "relayer is not running"
    try:
        _terminate(pid)
        time.sleep(1)
        RELAYER_PID_FILE.unlink(missing_ok=True)
        return True, f"relayer stopped (pid {pid})"
    except OSError as e:
        return False, f"could not stop pid {pid}: {e}"


# ---------------------------------------------------------------------------
# Free public exposure — Cloudflare quick tunnel (no account, *.trycloudflare.com)
# ---------------------------------------------------------------------------
TUNNEL_PID_FILE = RELAYER_DIR / "tunnel.pid"
TUNNEL_LOG = LOG_DIR / "relayer-tunnel.log"


def find_tunnel_binary() -> Optional[str]:
    # 1) our local copy
    local = BIN_DIR / ("cloudflared.exe" if platform.system() == "Windows" else "cloudflared")
    if local.exists():
        return str(local)
    # 2) Homebrew on macOS
    if platform.system() == "Darwin" and os.path.exists("/opt/homebrew/opt/cloudflared/bin/cloudflared"):
        return "/opt/homebrew/opt/cloudflared/bin/cloudflared"
    # 3) PATH
    return shutil.which("cloudflared") or shutil.which("cloudflared.exe")


def ensure_tunnel_binary() -> tuple[Optional[str], str]:
    """Return (binary_path, note). Tries an existing install, then installs
    cloudflared automatically (package manager, then direct download of the
    official prebuilt binary) so the tunnel works on macOS/Windows/Linux."""
    binary = find_tunnel_binary()
    if binary:
        return binary, "cloudflared already installed"
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    sys_ = platform.system()
    # ── package manager quick path ─────────────────────────────────────
    if sys_ == "Darwin" and shutil.which("brew"):
        r = subprocess.run(["brew", "install", "cloudflared"],
                           capture_output=True, text=True, timeout=300)
        binary = find_tunnel_binary()
        if binary:
            return binary, "cloudflared installed via Homebrew"
    if sys_ == "Windows":
        if shutil.which("winget"):
            subprocess.run(["winget", "install", "--id", "Cloudflare.cloudflared",
                            "--silent", "--accept-package-agreements",
                            "--accept-source-agreements"],
                           capture_output=True, text=True, timeout=300)
        elif shutil.which("choco"):
            subprocess.run(["choco", "install", "cloudflared", "-y"],
                           capture_output=True, text=True, timeout=300)
        binary = find_tunnel_binary()
        if binary:
            return binary, "cloudflared installed via package manager"
    # ── direct download of the official prebuilt binary ────────────────
    arch = platform.machine().lower()
    if sys_ == "Windows":
        suffix = "windows-amd64.exe" if "amd64" in arch or "x86_64" in arch else "windows-386.exe"
        dest = BIN_DIR / "cloudflared.exe"
    elif sys_ == "Darwin":
        suffix = "darwin-arm64.tgz" if "arm" in arch or "aarch64" in arch else "darwin-amd64.tgz"
        dest = BIN_DIR / "cloudflared"
    else:  # Linux
        suffix = "linux-amd64" if "amd64" in arch or "x86_64" in arch else "linux-arm64"
        dest = BIN_DIR / "cloudflared"
    url = (f"https://github.com/cloudflare/cloudflared/releases/latest/"
           f"download/cloudflared-{suffix}")
    try:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        if suffix.endswith(".tgz"):
            tmp = BIN_DIR / "cf.tgz"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
            import tarfile
            with tarfile.open(tmp, "r:gz") as tf:
                member = next(m for m in tf.getmembers() if m.isfile())
                blob = tf.extractfile(member).read()
            tmp.unlink(missing_ok=True)
            dest.write_bytes(blob)
        else:
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        if sys_ != "Windows":
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return str(dest), f"cloudflared downloaded to {dest}"
    except Exception as e:
        return None, f"cloudflared install failed: {e}"


def tunnel_running() -> Optional[int]:
    try:
        pid = int(TUNNEL_PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return None


def tunnel_url() -> str:
    """Return the last public URL from the tunnel log (trycloudflare.com).

    Reads only the tail of the log (it grows unboundedly while cloudflared
    runs), so repeated status checks stay instant no matter how long the
    tunnel has been up."""
    try:
        import re
        url = ""
        with open(TUNNEL_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 131_072))   # last 128 KB is plenty
            txt = f.read().decode("utf-8", "replace")
        # iterate all matches, keep the LAST one (most recent in the log)
        for m in re.finditer(r"https?://[a-z0-9-]+\.trycloudflare\.com/?", txt):
            url = m.group(0).rstrip("/")
        return url
    except Exception:
        return ""


def tunnel_healthy(url: str, timeout: float = 5.0, retries: int = 2) -> bool:
    """Quick HTTP HEAD/GET check that the public tunnel URL is reachable.

    Uses multiple attempts with short delays to handle transient network
    issues (common with Cloudflare's edge network propagation)."""
    if not url:
        return False
    for attempt in range(retries + 1):
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            if r.status_code < 400:
                return True
            # HEAD might be blocked, try GET
            r = requests.get(url, timeout=timeout, allow_redirects=True, stream=True)
            r.close()
            if r.status_code < 400:
                return True
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.0)  # brief pause before retry
    return False


def _tunnel_error_snippet(max_bytes: int = 65_536) -> str:
    """Return the last lines of the tunnel log for diagnostics.

    Reads only the tail (the log grows unboundedly while cloudflared runs),
    so this stays instant no matter how long the tunnel has been up."""
    try:
        with open(TUNNEL_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            txt = f.read().decode("utf-8", "replace")
        lines = txt.splitlines()
        return "\n".join(lines[-20:]) if lines else "(empty log)"
    except Exception:
        return "(no log)"


def start_tunnel(cfg) -> tuple[bool, str]:
    """Launch a free Cloudflare quick tunnel to the local relayer endpoint."""
    pid = tunnel_running()
    if pid:
        url = tunnel_url()
        healthy = tunnel_healthy(url) if url else False
        status = f"tunnel already running (pid {pid})"
        if url:
            status += f" — {url}" + (" ✓" if healthy else " ⚠ unreachable")
        return True, status
    binary, note = ensure_tunnel_binary()
    if not binary:
        return False, note
    port = int(cfg.get("relayer_port") or RELAYER_DEFAULT_PORT)
    host = cfg.get("relayer_host") or "127.0.0.1"
    RELAYER_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(TUNNEL_LOG, "ab")
    try:
        proc = subprocess.Popen(
            [binary, "tunnel", "--no-autoupdate", "--url",
             f"http://{host}:{port}"],
            stdout=log_file, stderr=log_file, **_detached_kwargs())
    except Exception as e:
        log_file.close()
        return False, f"failed to start cloudflared: {e}"
    TUNNEL_PID_FILE.write_text(str(proc.pid))
    log_file.close()
    print(f"  {C.DIM}tunnel starting (pid {proc.pid}) — waiting for the "
          f"public *.trycloudflare.com URL…{C.RESET}", flush=True)
    # poll for the public URL (up to ~25s)
    for _ in range(25):
        time.sleep(1)
        url = tunnel_url()
        if url:
            cfg_relayer_port(cfg, port)
            if tunnel_healthy(url):
                return True, (f"tunnel started (pid {proc.pid}) -> {url} ✓")
            return True, (f"tunnel started (pid {proc.pid}) -> {url} "
                          f"(URL found but not yet reachable, may need a few more seconds)")
    # URL not found — show last log lines for diagnostics
    tail = _tunnel_error_snippet()
    return True, (f"tunnel started (pid {proc.pid}) — URL not ready yet; "
                  f"see ~/.xelis-vault/logs/relayer-tunnel.log\n"
                  f"Last log lines:\n{tail}")


def cfg_relayer_port(cfg, port: int) -> None:
    try:
        cfg.data["relayer_port"] = port
        cfg.save()
    except Exception:
        pass


def stop_tunnel() -> tuple[bool, str]:
    pid = tunnel_running()
    if not pid:
        return False, "tunnel is not running"
    try:
        _terminate(pid)
        time.sleep(1)
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return True, f"tunnel stopped (pid {pid})"
    except OSError as e:
        return False, f"could not stop pid {pid}: {e}"


def relayer_tunnel_status(cfg) -> dict:
    """Combined status for the CLI panel: relayer pid, tunnel pid, public URL."""
    rpid = relayer_running()
    tpid = tunnel_running()
    return {
        "relayer_pid": rpid,
        "tunnel_pid": tpid,
        "url": tunnel_url() if tpid else "",
        "local_endpoint": f"{cfg.get('relayer_host') or '127.0.0.1'}:"
                          f"{int(cfg.get('relayer_port') or RELAYER_DEFAULT_PORT)}",
    }


def watchdog_tunnel(cfg, poll_interval: float = 60.0, stop_event: Optional[threading.Event] = None) -> dict:
    """Watchdog for tunnel + relayer + on-chain endpoint.

    Loop:
      1. ensure relayer + tunnel are running
      2. if tunnel URL changed -> update endpoint on-chain
      3. health check public URL
      4. sleep and repeat

    Pass a stop_event (threading.Event) to gracefully stop the watchdog.
    Returns last status dict.
    """
    last_url = ""
    last_status = {"ok": False, "message": "not started"}
    consecutive_failures = 0
    max_failures_before_restart = 3

    while True:
        # Check for stop signal
        if stop_event and stop_event.is_set():
            last_status["message"] = "watchdog stopped"
            break
        try:
            status = relayer_tunnel_status(cfg)
            tpid = status.get("tunnel_pid")
            url = status.get("url") or ""
            # 1) restart tunnel if dead
            if not tpid or not url:
                ok, msg = start_tunnel(cfg)
                status = relayer_tunnel_status(cfg)
                tpid = status.get("tunnel_pid")
                url = status.get("url") or ""
                last_status = {"ok": ok, "message": msg, "url": url}
                consecutive_failures = 0
            else:
                last_status = {"ok": True, "message": f"tunnel alive {url}", "url": url}
            # 2) auto-update on-chain if URL changed
            if url and url != last_url:
                try:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from cli_backend import Backend
                    b = Backend({
                        "rpc_url": cfg.get("rpc_url") or PUBLIC_NODE,
                        "wallet_url": cfg.get("wallet_url"),
                        "wallet_user": cfg.get("wallet_user") or "wallet",
                        "wallet_pass": cfg.get("wallet_pass") or "testpass",
                    })
                    res = b.chat_update_endpoint(url)
                    last_status["endpoint"] = "updated ✓" if res.ok else f"update failed: {res.reason}"
                    if res.ok:
                        last_url = url  # only update last_url on success
                except Exception as e:
                    last_status["endpoint"] = f"skipped: {e}"
            # 3) health check public URL
            if url:
                healthy = tunnel_healthy(url)
                last_status["healthy"] = healthy
                if not healthy:
                    consecutive_failures += 1
                    last_status["message"] += f" ⚠ public URL unreachable ({consecutive_failures}/{max_failures_before_restart})"
                    # If too many consecutive failures, restart tunnel
                    if consecutive_failures >= max_failures_before_restart:
                        last_status["message"] += " — restarting tunnel…"
                        stop_tunnel()
                        time.sleep(2)
                        consecutive_failures = 0
                else:
                    consecutive_failures = 0
        except Exception as e:
            last_status = {"ok": False, "message": f"watchdog error: {e}", "url": last_url}
        # Sleep in small increments to respond quickly to stop signal
        for _ in range(int(max(5, float(poll_interval)))):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)
    return last_status


def start_relayer_public(cfg) -> tuple[bool, str]:
    """One-shot: ensure relayer daemon + tunnel run, then sync the public URL
    on-chain via update_relayer_endpoint."""
    ok, msg = start_relayer(cfg)
    if not ok:
        return False, msg
    ok2, msg2 = start_tunnel(cfg)
    url = tunnel_url()
    if ok2:
        if not url:
            # start_tunnel already polls for ~25s; give it a short grace
            # period with visible feedback instead of a silent 15s block.
            for _ in range(8):
                time.sleep(1)
                url = tunnel_url()
                if url:
                    break
        if url:
            healthy = tunnel_healthy(url)
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from cli_backend import Backend
                b = Backend({
                    "rpc_url": cfg.get("rpc_url") or PUBLIC_NODE,
                    "wallet_url": cfg.get("wallet_url"),
                    "wallet_user": cfg.get("wallet_user") or "wallet",
                    "wallet_pass": cfg.get("wallet_pass") or "testpass",
                })
                res = b.chat_update_endpoint(url)
                status = "updated ✓" if res.ok else f"update failed: {res.reason}"
                health = "" if healthy else " ⚠ tunnel unreachable"
                return True, (f"relayer public: {url}{health} "
                              f"(endpoint on-chain {status})")
            except Exception as e:
                return True, f"relayer public: {url} (endpoint update skipped: {e})"
        return True, f"relayer running, tunnel URL not ready yet: {msg2}"
    return True, f"relayer running, tunnel failed: {msg2}"



def apply_bundled_contracts(cfg) -> bool:
    bundle = load_network_bundle()
    contracts = bundle.get("contracts", {})
    if contracts:
        merged = dict(cfg.contracts)
        merged.update({k: v for k, v in contracts.items() if v})
        cfg.data["contracts"] = merged
        if bundle.get("vlt_asset"):
            cfg.data.setdefault("vlt_asset", bundle["vlt_asset"])
        cfg.data.setdefault("network", bundle.get("network", "testnet"))
        cfg.save()
        info_box("Contracts loaded automatically ✓", [
            f"{k}: {v[:26]}…" for k, v in list(merged.items())[:4]
        ] + ["", f"(network bundle v{bundle.get('version', '?')} — no input required)"])
        return True
    return False


def run_onboarding(cfg) -> bool:
    """Full first-run experience. Returns True when config is usable."""
    ok_wallet = ensure_wallet(cfg)
    ok_daemon = ensure_daemon(cfg)
    ensure_miner_configured(cfg)
    ok_contracts = apply_bundled_contracts(cfg)

    if not ok_contracts:
        # Manual fallback (file has a hyphen in its name → importlib needed).
        try:
            from importlib import util as _ilu
            _spec = _ilu.spec_from_file_location(
                "xvault_miner_mod",
                Path(__file__).parent / "xvault-miner.py")
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.interactive_setup(cfg)
        except Exception:
            info_box("Warning", [
                "Network bundle not found and manual setup unavailable.",
                "Contract addresses may be incomplete.",
            ], color=C.YELLOW)

    services = menu("Which services should this node support?", [
        ("Oracle + Chat (recommended, max rewards)", "both"),
        ("Oracle only (price feed)", "oracle"),
        ("Chat only (message anchoring)", "chat"),
    ])
    if services:
        cfg.data["services"] = services
    endpoint = text_input("Public endpoint URL (optional, press Enter to skip)", "")
    cfg.data["miner_endpoint"] = endpoint
    cfg.save()

    lines = []
    lines.append("Setup complete!" if ok_wallet else
                 "Partial setup (no wallet).")
    lines.append("")
    lines.append(f"Wallet   : {'✓ ' + cfg.get('wallet_url') if ok_wallet else '—'}")
    lines.append(f"Daemon   : {cfg.get('rpc_url')}")
    lines.append(f"Address  : {(cfg.get('miner_address') or '—')[:34]}")
    lines.append(f"Contracts: {'✓ automatic' if ok_contracts else '✗ manual'}")
    info_box("Ready!", lines)
    return ok_wallet
