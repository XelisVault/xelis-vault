import json, os, subprocess, time, requests

L = "http://127.0.0.1:18081/json_rpc"
O = "https://testnet-node.xelis.io/json_rpc"
LOG = "/tmp/sync_monitor.log"
DAEMON_DIR = "/Users/adrien/xelis"

def log(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def info(url):
    try:
        return requests.post(url, json={"jsonrpc": "2.0", "method": "get_info", "id": 1}, timeout=20).json().get("result")
    except Exception:
        return None

def kill_daemon():
    try:
        out = subprocess.run(["lsof", "-ti", ":18081"], capture_output=True, text=True).stdout.split()
        for pid in out:
            subprocess.run(["kill", pid])
        time.sleep(4)
    except Exception as e:
        log(f"kill err: {e}")

def start_daemon():
    subprocess.Popen(
        ["./xelis_daemon", "--network", "testnet",
         "--dir-path", f"{DAEMON_DIR}/data/", "--logs-path", f"{DAEMON_DIR}/logs/",
         "--rpc-bind-address", "127.0.0.1:18081",
         "--priority-nodes", "74.208.251.149:2125",
         "--allow-fast-sync"],
        cwd=DAEMON_DIR,
        stdout=open("/tmp/daemon_fastsync.log", "ab"),
        stderr=subprocess.STDOUT)

def full_reset(reason):
    log(f"RESET: {reason}")
    kill_daemon()
    subprocess.run(["rm", "-rf", f"{DAEMON_DIR}/data/testnet"])
    time.sleep(2)
    start_daemon()
    log("daemon relance en fast-sync (DB vierge)")

log("monitor demarre")
last_progress = time.time()
last_reset = 0
prev_local = -1
consecutive_bad = 0

while True:
    lo, of = info(L), info(O)
    now = time.time()

    if of is None:
        log("officiel injoignable — attente")
        consecutive_bad += 1
    elif lo is None:
        log("local pas pret")
        consecutive_bad += 1
    else:
        lt, ot = lo["topoheight"], of["topoheight"]
        lh, oh = lo["top_block_hash"], of["top_block_hash"]
        if lt == ot and lh == oh:
            if consecutive_bad >= 3 or prev_local != lt:
                log(f"SYNCHRONISE ✓ topo={lt:,} hash={lh[:16]}")
            consecutive_bad = 0
            last_progress = now
        elif lt > ot:
            # on est DEVANT l'officiel (normal si leur node stalle et qu'on mine):
            # verifier que le bloc commun au topo officiel est identique
            try:
                b = requests.post(O, json={"jsonrpc": "2.0", "method": "get_block_at_topoheight",
                                           "params": {"topoheight": ot}, "id": 1}, timeout=15).json().get("result")
                lb = requests.post(L, json={"jsonrpc": "2.0", "method": "get_block_at_topoheight",
                                            "params": {"topoheight": ot}, "id": 1}, timeout=15).json().get("result")
                if b and lb and b["hash"] == lb["hash"]:
                    consecutive_bad = 0
                    last_progress = now
                    if prev_local != lt:
                        log(f"AHEAD (on mine devant node gelé): local {lt:,} vs off {ot:,} — ancêtre commun OK")
                else:
                    consecutive_bad += 1
                    log(f"FORK réel @topo {ot}: hashes différents ({consecutive_bad})")
            except Exception:
                log("check ancêtre commun échoué")
        else:  # lt < ot : en retard / en cours de sync
            if lt > prev_local:
                last_progress = now
                if lt // 10000 != (prev_local // 10000 if prev_local >= 0 else -1):
                    log(f"sync en cours: {lt:,}/{ot:,} ({lt/max(ot,1)*100:.1f}%)")
                consecutive_bad = max(0, consecutive_bad - 1)
            else:
                stuck_min = (now - last_progress) / 60
                if stuck_min > 25:
                    consecutive_bad += 1
                    log(f"stalle {stuck_min:.0f} min @topo {lt:,} ({consecutive_bad})")
            if ot - lt < 5000 and lt > 0:
                # proche du tip: comparer les hashes pour detecter un fork
                try:
                    b = requests.post(O, json={"jsonrpc": "2.0", "method": "get_block_at_topoheight",
                                               "params": {"topoheight": lt}, "id": 1}, timeout=15).json().get("result")
                    lb = requests.post(L, json={"jsonrpc": "2.0", "method": "get_block_at_topoheight",
                                                "params": {"topoheight": lt}, "id": 1}, timeout=15).json().get("result")
                    if b and lb and b["hash"] != lb["hash"]:
                        consecutive_bad += 1
                        log(f"FORK detecte au topo {lt}: hashes differents ({consecutive_bad})")
                    elif b and lb:
                        consecutive_bad = 0
                except Exception:
                    pass
        prev_local = lt

    if consecutive_bad >= 4 and now - last_reset > 1200:
        full_reset(f"{consecutive_bad} controles anormaux consecutifs")
        last_reset = now
        consecutive_bad = 0
        prev_local = -1
        last_progress = time.time()

    time.sleep(60)
