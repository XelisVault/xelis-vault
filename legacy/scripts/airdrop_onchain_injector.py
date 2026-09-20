#!/usr/bin/env python3
"""
airdrop_onchain_injector.py — Injecte les points du classement off-chain dans le
contrat AirdropTracker ON-CHAIN (testnet), puis surveille l'activité pour
force-qualifier les users dès qu'ils cumulent 7 jours d'activité on-chain.

Le contrat AirdropTracker (testnet) ne reçoit aucune activité des contrats core
(les record_* ne sont pas câblés). Pour rendre l'airdrop "live", on écrit nous-mêmes
les points du leaderboard off-chain (produit par airdrop_offchain_indexer.py) dans
le contrat via record_manual_attribution (entry 21, admin-only).

Deux phases :
  1. INJECTION initiale : injecte les points actuels du leaderboard par user/catégorie.
  2. DAEMON de surveillance : relit le leaderboard, injecte les DELTAS de points
     (nouveaux points non encore injectés) à chaque cycle, et quand un user atteint
     `days_active >= 7` ON-CHAIN (via l'activité réinjectée sur des jours distincts),
     appelle force_qualify_user (entry 58).

Le `days_active` du contrat est calculé par update_day_activity() avec le topo ACTUEL
(get_day = topo // BLOCKS_PER_DAY) : il ne PEUT PAS être rétroactif. Le seul moyen de
le faire monter est d'injecter des points sur des jours distincts. C'est pourquoi on
ré-injecte les nouveaux points à chaque cycle — chaque jour où un user a de l'activité,
son days_active on-chain augmente de 1. Dès qu'il atteint 7, on force-qualifie.

Catégories (AirdropTracker.slx) : 1=MINING 2=RELAYER 3=GOVERNANCE 4=CHAT
                                   5=LIQUIDITY 6=BOUNTY 7=COMMUNITY

Usage :
    python3 scripts/airdrop_onchain_injector.py --inject
    python3 scripts/airdrop_onchain_injector.py --inject --dry-run
    python3 scripts/airdrop_onchain_injector.py --daemon
    python3 scripts/airdrop_onchain_injector.py --sync-once      # injecte les deltas une fois
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protocol  # noqa: E402

TRACKER = protocol.CONTRACT_HASHES["AirdropTracker"]

# Chunk indexes compilés (source: docs/entry_chunk_ids.json -> AirdropTracker)
CH_RECORD_MANUAL = 21        # record_manual_attribution(user, cat:u8, pts:u64, reason)
CH_RECORD_BATCH = 54         # record_manual_attribution_batch(users[], cat, pts, reason)
CH_FORCE_QUALIFY = 58        # force_qualify_user(user, reason)
CH_RECORD_MAINNET = 22       # record_mainnet_address(addr)

# Catégories (consts AirdropTracker.slx)
CAT = {"MINING": 1, "RELAYER": 2, "GOVERNANCE": 3, "CHAT": 4,
       "LIQUIDITY": 5, "BOUNTY": 6, "COMMUNITY": 7}

# Index du struct UserPoints (source .slx lignes 177-192)
UP_DAYS_ACTIVE = 9
UP_QUALIFIED = 12

ADMIN = protocol.ADMIN
DEFAULT_LEADERBOARD = Path.home() / ".xelis-vault" / "airdrop" / "airdrop_leaderboard.json"
DEFAULT_STATE = Path.home() / ".xelis-vault" / "airdrop" / "airdrop_inject_state.json"

REASON = "offchain-indexer"


class Injector:
    def __init__(self, p: protocol.Protocol, leaderboard_path: Path, state_path: Path):
        self.p = p
        self.tracker = TRACKER
        self.lb_path = Path(leaderboard_path)
        self.state_path = Path(state_path)
        self.state = self._load_state()

    # ------------------------------------------------------------------ state
    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except Exception:
                pass
        return {"injected": {}, "force_qualified": []}  # {addr: {cat: pts}}

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2))

    # ------------------------------------------------------------------ load
    def load_leaderboard(self) -> dict:
        if not self.lb_path.exists():
            raise FileNotFoundError(f"leaderboard not found: {self.lb_path}")
        return json.loads(self.lb_path.read_text())

    @staticmethod
    def _addr_row(data: dict) -> dict:
        return {r["address"]: r for r in data.get("leaderboard", [])}

    # ------------------------------------------------------------- on-chain
    def user_points_struct(self, addr: str):
        """Lit le struct UserPoints on-chain (clé user_<addr>). Retourne tuple/list
        ou None si le user n'existe pas encore on-chain."""
        raw = self.p.daemon.read_key(self.tracker, "user_" + addr)
        return raw

    def days_active_onchain(self, addr: str) -> int:
        raw = self.user_points_struct(addr)
        if not raw:
            return 0
        return self._field(raw, UP_DAYS_ACTIVE)

    def qualified_onchain(self, addr: str) -> bool:
        raw = self.user_points_struct(addr)
        if not raw:
            return False
        return bool(self._field(raw, UP_QUALIFIED))

    @staticmethod
    def _field(raw, idx):
        if isinstance(raw, (list, tuple)):
            if idx < len(raw):
                return raw[idx]
            return 0
        if isinstance(raw, dict):
            keys = list(raw)
            if idx < len(keys):
                return raw[keys[idx]]
            return 0
        return 0

    def is_force_qualified(self, addr: str) -> bool:
        # FORCE_QUALIFIED_PREFIX = "fqual_" -> bool
        return bool(self.p.daemon.read_key(self.tracker, "fqual_" + addr) or False)

    # ------------------------------------------------------------- inject
    def inject_one(self, addr: str, cat: int, pts: int, reason: str) -> None:
        params = [protocol.val_addr(addr), protocol.val_u8(cat),
                  protocol.val_u64(pts), protocol.val_str(reason)]
        tx = self.p.invoke_hash(self.tracker, CH_RECORD_MANUAL, params,
                                max_gas=protocol.HEAVY_GAS)
        print(f"  + {addr[:14]}… cat={cat} pts={pts} tx={tx[:16]}")

    def deliver_delta(self, addr: str, row: dict, dry_run: bool, verbose: bool = True) -> int:
        """Injecte les points NON encore injectés pour chaque catégorie de `row`.
        Retourne le nombre d'appels faits."""
        injected = self.state["injected"].setdefault(addr, {})
        calls = 0
        cats = row.get("categories") or {}
        for cat_name, pts in cats.items():
            pts_i = int(round(float(pts)))
            if pts_i <= 0:
                continue
            if cat_name not in CAT:
                continue
            already = injected.get(cat_name, 0)
            if already >= pts_i:
                continue
            delta = pts_i - already
            if delta <= 0:
                continue
            if verbose:
                print(f"  [{cat_name}] delta {delta} (already {already}/{pts_i})")
            if not dry_run:
                # cap sécurité : record_manual_attribution exige pts <= mcap (50000)
                while delta > 0:
                    chunk = min(delta, 48000)
                    self.inject_one(addr, CAT[cat_name], chunk, REASON)
                    injected[cat_name] = injected.get(cat_name, 0) + chunk
                    delta -= chunk
                    calls += 1
            else:
                injected[cat_name] = pts_i
        if calls or verbose:
            pass
        return calls

    # ------------------------------------------------------------- qualify
    def maybe_force_qualify(self, addr: str, threshold: int, dry_run: bool, verbose: bool = True) -> bool:
        """Si le user a >= threshold jours d'activité on-chain (et points >= 1000)
        mais n'est pas (encore) force-qualifié, appelle force_qualify_user."""
        if self.qualified_onchain(addr):
            return False
        if self.is_force_qualified(addr):
            return False
        days = self.days_active_onchain(addr)
        if days < threshold:
            return False
        if verbose:
            print(f"  !! {addr[:14]}… days_active(nc)={days} >= {threshold} -> force_qualify")
        if not dry_run:
            params = [protocol.val_addr(addr), protocol.val_str(REASON)]
            tx = self.p.invoke_hash(self.tracker, CH_FORCE_QUALIFY, params,
                                    max_gas=protocol.INVOKE_GAS)
            print(f"  ++ FORCE QUALIFY {addr[:14]}… tx={tx[:16]}")
            if addr not in self.state["force_qualified"]:
                self.state["force_qualified"].append(addr)
        return True

    # ------------------------------------------------------------- flows
    def sync_once(self, dry_run: bool = False, threshold: int = 7, verbose: bool = True):
        """Une passe : injecte les deltas de tous les users du leaderboard, puis
        force-qualifie ceux qui ont >= threshold jours d'activité on-chain."""
        data = self.load_leaderboard()
        rows = self._addr_row(data)
        if verbose:
            print(f"[sync] leaderboard: {len(rows)} users")
        total_calls = 0
        for addr, row in rows.items():
            if addr == ADMIN:
                continue
            total_calls += self.deliver_delta(addr, row, dry_run, verbose)
        if verbose:
            print(f"[sync] injection: {total_calls} appels")
        if not dry_run:
            self._save_state()
        # force-qualify
        for addr in list(rows.keys()):
            if addr == ADMIN:
                continue
            self.maybe_force_qualify(addr, threshold, dry_run, verbose)
        if verbose:
            print("[sync] terminé")
        return total_calls

    def run_daemon(self, threshold: int = 7, poll: float = 60, dry_run: bool = False):
        print(f"[daemon] surveillance AirdropTracker on-chain (poll={poll}s, "
              f"force_qualify à {threshold} jours)")
        while True:
            t0 = time.time()
            try:
                self.sync_once(dry_run=dry_run, threshold=threshold, verbose=False)
            except Exception as e:
                print(f"[daemon] erreur: {e}")
            # affichage périodique condensé
            self._print_status()
            elapsed = time.time() - t0
            time.sleep(max(1, poll - elapsed))

    def _print_status(self):
        try:
            uc = self.p.daemon.read_key(self.tracker, "uc") or 0
            tp = self.p.daemon.read_key(self.tracker, "tp") or 0
            qc = self.p.daemon.read_key(self.tracker, "qc") or 0
            fq = len(self.state.get("force_qualified", []))
            print(f"[daemon] uc={uc} tp={tp} qc={qc} force_qualified={fq} "
                  f"({time.strftime('%H:%M:%S')})")
        except Exception as e:
            print(f"[daemon] status err: {e}")


def main():
    ap = argparse.ArgumentParser(description="Injecte les points airdrop off-chain "
                                             "dans AirdropTracker on-chain")
    ap.add_argument("--inject", action="store_true", help="Injection initiale + deltas (une passe)")
    ap.add_argument("--daemon", action="store_true", help="Mode continu (deltas + force_qualify)")
    ap.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer de txs")
    ap.add_argument("--leaderboard", default=str(DEFAULT_LEADERBOARD))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--threshold", type=int, default=7, help="Jours d'activité requis "
                                                             "(défaut 7)")
    ap.add_argument("--poll-interval", type=float, default=60.0)
    args = ap.parse_args()

    p = protocol.Protocol()
    inj = Injector(p, Path(args.leaderboard), Path(args.state))

    if args.dry_run:
        print("=== DRY RUN (aucune tx) ===")
    print("tracker:", TRACKER)
    print("admin  :", ADMIN)

    if args.daemon:
        inj.run_daemon(threshold=args.threshold, poll=args.poll_interval,
                       dry_run=args.dry_run)
    else:
        inj.sync_once(dry_run=args.dry_run, threshold=args.threshold)


if __name__ == "__main__":
    main()
