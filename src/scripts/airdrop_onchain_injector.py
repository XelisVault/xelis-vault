#!/usr/bin/env python3
"""
airdrop_onchain_injector.py — Injects off-chain leaderboard points into the
AirdropTracker contract ON-CHAIN (testnet), then monitors activity to
force-qualify users as soon as they accumulate 7 days of on-chain activity.

The AirdropTracker contract (testnet) does not receive activity from core contracts
(the record_* hooks are not wired). To make the airdrop "live", we write the
off-chain leaderboard points (produced by airdrop_offchain_indexer.py) into
the contract via record_manual_attribution (entry 21, admin-only).

Two phases:
  1. INITIAL injection: injects current leaderboard points per user/category.
  2. Monitoring daemon: re-reads the leaderboard, injects point DELTAS
     (new points not yet injected) each cycle, and when a user reaches
     `days_active >= 7` ON-CHAIN (via activity re-injected on distinct days),
     calls force_qualify_user (entry 58).

The contract's `days_active` is computed by update_day_activity() using the CURRENT
topo (get_day = topo // BLOCKS_PER_DAY): it CANNOT be retroactive. The only way to
increase it is to inject points on distinct days. That's why we
re-inject new points each cycle — each day a user has activity,
their on-chain days_active increases by 1. Once it reaches 7, we force-qualify.

Categories (AirdropTracker.slx): 1=MINING 2=RELAYER 3=GOVERNANCE 4=CHAT
                                    5=LIQUIDITY 6=BOUNTY 7=COMMUNITY

Usage:
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

# Compiled chunk indexes (source: docs/entry_chunk_ids.json -> AirdropTracker)
CH_RECORD_MANUAL = 21        # record_manual_attribution(user, cat:u8, pts:u64, reason)
CH_RECORD_BATCH = 54         # record_manual_attribution_batch(users[], cat, pts, reason)
CH_FORCE_QUALIFY = 58        # force_qualify_user(user, reason)
CH_RECORD_MAINNET = 22       # record_mainnet_address(addr)

# Categories (consts AirdropTracker.slx)
CAT = {"MINING": 1, "RELAYER": 2, "GOVERNANCE": 3, "CHAT": 4,
       "LIQUIDITY": 5, "BOUNTY": 6, "COMMUNITY": 7}

# UserPoints struct index (source .slx lines 177-192)
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
        """Reads the UserPoints struct on-chain (key user_<addr>). Returns tuple/list
        or None if the user does not exist on-chain yet."""
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
        """Injects points NOT yet injected for each category in `row`.
        Returns the number of calls made."""
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
                # safety cap: record_manual_attribution requires pts <= mcap (50000)
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
        """If the user has >= threshold days of on-chain activity (and points >= 1000)
        but is not yet force-qualified, calls force_qualify_user."""
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
        """One pass: injects deltas for all leaderboard users, then
        force-qualifies those with >= threshold days of on-chain activity."""
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
            print("[sync] done")
        return total_calls

    def run_daemon(self, threshold: int = 7, poll: float = 60, dry_run: bool = False):
        print(f"[daemon] monitoring AirdropTracker on-chain (poll={poll}s, "
              f"force_qualify at {threshold} days)")
        while True:
            t0 = time.time()
            try:
                self.sync_once(dry_run=dry_run, threshold=threshold, verbose=False)
            except Exception as e:
                print(f"[daemon] error: {e}")
            # compact periodic display
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
    ap.add_argument("--daemon", action="store_true", help="Continuous mode (deltas + force_qualify)")
    ap.add_argument("--dry-run", action="store_true", help="Show actions without sending txs")
    ap.add_argument("--leaderboard", default=str(DEFAULT_LEADERBOARD))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--threshold", type=int, default=7, help="Days of activity required "
                                                             "(default 7)")
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
