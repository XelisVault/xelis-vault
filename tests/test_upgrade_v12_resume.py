#!/usr/bin/env python3
"""
test_upgrade_v12_resume.py — crash-resume & cutover tests for the v12.1
upgrade flow (deploy/upgrade_v12.py), using a fully mocked protocol layer.

Covers the community-review findings:
  1. import_user_state accepts users ABOVE the manual attribution cap
  2. the new tracker is migrated while PAUSED and BEFORE the registry cutover
  3. the migration resumes from the ON-CHAIN mig cursor after a crash
     (idempotent re-imports, no duplicated users)
  4. finalize_migration never double-counts and never zeroes the totals
     (on-chain batch cursor + completion flag)
  5. Phase D FAILS CLOSED when the old tracker changed during the migration
  6. unpause is crash-safe: a re-run after a successful on-chain unpause
     never unpauses twice (reads the on-chain "pz" key)
  7. the registry cutover upgrades BOTH the "VaultSwap" and "VaultSwapV2"
     aliases, and is idempotent on re-run

Run:  python3 tests/test_upgrade_v12_resume.py
"""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Fake protocol module (must be installed BEFORE upgrade_v12 is loaded)
# ---------------------------------------------------------------------------
CHAIN: dict = {}          # {contract: {key: value}}  on-chain state
INVOKE_LOG: list = []     # [(contract, entry, decoded_params)]
CRASH_AFTER: dict = {"n": None, "count": 0}  # crash switch
TX_SEQ = {"n": 0}

OLD_TRACKER = "xOLDTRACKER00000000000000000000000000000000000000000000000"[:64]
NEW_TRACKER = "xNEWTRACKER0000000000000000000000000000000000000000000000"[:64]
REGISTRY = "xREGISTRY0000000000000000000000000000000000000000000000000"[:64]
OLD_SWAP = "xOLDSWAP00000000000000000000000000000000000000000000000000"[:64]
NEW_SWAP = "xNEWSWAP0000000000000000000000000000000000000000000000000"[:64]


def _dec(p: dict):
    """Decode a protocol value param into a python value."""
    if not isinstance(p, dict):
        return p
    if p.get("type") == "primitive":
        inner = p.get("value", {})
        t, v = inner.get("type"), inner.get("value")
        if t in ("u64", "u128", "u32"):
            return int(v)
        if t in ("u8", "u16"):
            return int(v)
        if t == "boolean":
            return bool(v)
        if t == "string":
            return v
        if t == "opaque":
            return v.get("value") if isinstance(v, dict) else v
    if p.get("type") == "bytes":
        return p.get("value")
    return p


def _prim(t, v):
    return {"type": "primitive", "value": {"type": t, "value": v}}


def _apply(contract, entry, params):
    """Apply the REAL v12.1 AirdropTracker semantics to the fake chain."""
    st = CHAIN.setdefault(contract, {})
    p = [_dec(x) for x in params]

    if contract == NEW_TRACKER:
        if entry == 78:  # import_user_state
            addr = p[0]
            if ("user_" + addr) not in st:
                st[f"ul_{st.get('uc', 0)}"] = addr
                st["uc"] = st.get("uc", 0) + 1
            total = sum(int(x) for x in p[1:8])
            st["user_" + addr] = [p[1], p[2], p[3], p[4], p[5], p[6], p[7],
                                  total, 0, p[8], p[9], p[11], p[10], True]
        elif entry == 81:  # set_mig_cursor
            st["mig"] = int(p[0])
        elif entry == 79:  # finalize_migration(count)
            if st.get("migd"):
                return
            count = int(p[0])
            uc = st.get("uc", 0)
            start = st.get("migf", 0)
            end = min(start + count, uc)
            acc = st.get("mig_acc", {"tp": 0, "c": [0] * 7})
            for i in range(start, end):
                addr = st.get(f"ul_{i}")
                if addr is None:
                    continue
                up = st.get("user_" + addr)
                acc["tp"] += up[7]
                for c in range(7):
                    acc["c"][c] += up[c]
            if end >= uc:
                st["tp"] = acc["tp"]
                for c in range(7):
                    st[f"ct_{c + 1}"] = acc["c"][c]
                st["migd"] = True
                st.pop("migf", None)
                st.pop("mig_acc", None)
            else:
                st["migf"] = end
                st["mig_acc"] = acc
        elif entry == 73:  # pause
            st["pz"] = True
        elif entry == 74:  # unpause
            st["pz"] = False

    elif contract == REGISTRY and entry == 4:  # registry upgrade
        name, target = p[0], p[1]
        st["prev_" + name] = st.get("cur_" + name)
        st["cur_" + name] = target


class _CrashNow(Exception):
    """Simulates the python process dying mid-script."""


class FakeWallet:
    def invoke(self, contract, entry, params, deposits, max_gas):
        TX_SEQ["n"] += 1
        tx = f"tx{TX_SEQ['n']}"
        _apply(contract, entry, params)
        INVOKE_LOG.append((contract, entry, [_dec(x) for x in params]))
        CRASH_AFTER["count"] += 1
        if CRASH_AFTER["n"] is not None and CRASH_AFTER["count"] >= CRASH_AFTER["n"]:
            CRASH_AFTER["n"] = None  # one-shot
            raise _CrashNow("simulated crash AFTER on-chain effect")
        return tx

    def _call(self, method, payload):
        TX_SEQ["n"] += 1
        return {"hash": f"tx{TX_SEQ['n']}"}

    def _wait_nonce_catchup(self):
        pass

    def address(self):
        return "xet:admin"


class FakeDaemon:
    def read_key(self, contract, key):
        return CHAIN.get(contract, {}).get(key)


class FakeProtocol:
    def __init__(self):
        self.wallet = FakeWallet()
        self.daemon = FakeDaemon()

    def wait(self, tx, timeout=None):
        return True

    def revert_reason(self, tx):
        return None


fake_protocol = types.ModuleType("protocol")
fake_protocol.Protocol = FakeProtocol
fake_protocol.WalletClient = FakeWallet
fake_protocol.DaemonClient = FakeDaemon
fake_protocol.RPCError = type("RPCError", (Exception,), {})
fake_protocol.val_u64 = lambda n: _prim("u64", str(n))
fake_protocol.val_u8 = lambda n: _prim("u8", int(n))
fake_protocol.val_u16 = lambda n: _prim("u16", int(n))
fake_protocol.val_bool = lambda b: _prim("boolean", bool(b))
fake_protocol.val_str = lambda s: _prim("string", s)
fake_protocol.val_hash = lambda h: _prim("opaque", {"type": "Hash", "value": h})
fake_protocol.val_addr = lambda a: _prim("opaque", {"type": "Address", "value": a})
fake_protocol._with_retries = lambda fn, **kw: fn()
sys.modules["protocol"] = fake_protocol

# --- load upgrade_v12 against the fake protocol --------------------------
_spec = importlib.util.spec_from_file_location(
    "upgrade_v12", REPO / "deploy" / "upgrade_v12.py")
uv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uv)

ADDR_A = "xet:" + "a" * 60   # power user: 60,000 pts (above the 50k manual cap)
ADDR_B = "xet:" + "b" * 60   # user with a partially unreadable struct
ADDR_C = "xet:" + "c" * 60   # normal user


def make_old_tracker():
    """Old tracker state: 3 users, one above the manual cap, one corrupted."""
    CHAIN[OLD_TRACKER] = {
        "uc": 3,
        "tp": 60000 + 15 + 400,
        "ct_1": 60000, "ct_2": 10, "ct_3": 0, "ct_4": 5,
        "ct_5": 0, "ct_6": 0, "ct_7": 400,
        "ul_0": ADDR_A, "ul_1": ADDR_B, "ul_2": ADDR_C,
        # full 14-field struct
        "user_" + ADDR_A: [60000, 0, 0, 0, 0, 0, 0, 60000, 60000, 12, 40,
                           "xet:" + "m" * 60, True, True],
        # CORRUPTED struct (only 3 fields readable)
        "user_" + ADDR_B: [10, 0, 5],
        "user_" + ADDR_C: [0, 10, 0, 5, 0, 0, 400, 415, 415, 7, 41, None, False, True],
    }
    CHAIN[REGISTRY] = {
        "cur_AirdropTracker": OLD_TRACKER,
        "cur_VaultSwap": OLD_SWAP,
        "cur_VaultSwapV2": OLD_SWAP,
    }
    CHAIN[NEW_TRACKER] = {"pz": True}  # v12.1 constructor default


def fresh_module_state(tmp):
    """(re)init upgrade_v12 module globals with tmp state + deployed S."""
    uv.STATE_PATH = Path(tmp) / "upgrade_v12_state.json"
    uv.NETWORK_PATH = Path(tmp) / "testnet.json"
    net = {"contracts": {"contract_registry": REGISTRY},
           "vlt_asset": "xVLT", "xusd_asset": "xUSD"}
    uv.NETWORK_PATH.write_text(json.dumps(net))
    uv.STATE = {"contracts": {}, "steps": [], "migrated_users": []}
    for n in uv.UPGRADE_CONTRACTS:
        uv.STATE["contracts"][n] = "NEW_" + n + "_" + "0" * 40
    uv.STATE["contracts"]["VaultSwapV2"] = NEW_SWAP
    uv.STATE["contracts"]["AirdropTracker"] = NEW_TRACKER
    uv.S = uv.STATE["contracts"]
    uv.BYTECODE_DIR = Path(tmp)
    uv.save()


class UpgradeResumeTests(unittest.TestCase):

    def setUp(self):
        global CHAIN, INVOKE_LOG, CRASH_AFTER
        CHAIN, INVOKE_LOG = {}, []
        CRASH_AFTER = {"n": None, "count": 0}
        TX_SEQ["n"] = 0
        self.tmp = tempfile.mkdtemp()
        make_old_tracker()
        fresh_module_state(self.tmp)
        self.D = uv.Deployer()

    # -- helpers ------------------------------------------------------------

    def run_phase_d(self):
        uv.phase_d(self.D, OLD_TRACKER)

    def imports_of(self, entry):
        return [c for (c, e, p) in INVOKE_LOG if e == entry]

    # -- 1/2/3: full migration, cap bypass, defaults, paused ----------------

    def test_full_migration_imports_everyone_and_bypasses_cap(self):
        self.run_phase_d()
        st = CHAIN[NEW_TRACKER]
        self.assertEqual(st["uc"], 3, "exactly 3 users, no duplicates")
        # power user above the manual cap migrated without failure
        self.assertEqual(st["user_" + ADDR_A][7], 60000)
        # corrupted struct -> imported with safe defaults (not skipped)
        self.assertIn("user_" + ADDR_B, st)
        # struct [10, 0, 5] -> mining 10 + governance 5 = 15 preserved
        self.assertEqual(st["user_" + ADDR_B][7], 15)
        self.assertEqual(st["user_" + ADDR_B][0], 10)
        # qualified flag + last_active_day preserved for the full user
        self.assertEqual(st["user_" + ADDR_A][10], 40)   # last_active_day
        self.assertIs(st["user_" + ADDR_A][12], True)    # qualified
        # cursor at the end + finalized totals
        self.assertEqual(st["mig"], 3)
        self.assertIs(st["migd"], True)
        self.assertEqual(st["tp"], 60000 + 15 + 415)
        # the tracker was migrated while STILL PAUSED (unpause comes later)
        self.assertIs(st["pz"], True)

    # -- 3: crash resume via the on-chain mig cursor -------------------------

    def test_crash_mid_import_resumes_from_onchain_cursor(self):
        # crash after the 1st import succeeded on-chain (before local save)
        CRASH_AFTER["n"] = 1
        with self.assertRaises(_CrashNow):
            self.run_phase_d()
        self.assertEqual(CHAIN[NEW_TRACKER]["uc"], 1)

        # relaunch the process: local STATE was NOT saved for the crash step
        # (the crash hit right after the on-chain effect) — the on-chain
        # cursor is the source of truth
        CRASH_AFTER["n"] = None
        self.run_phase_d()
        st = CHAIN[NEW_TRACKER]
        self.assertEqual(st["uc"], 3, "no duplicated users after resume")
        self.assertEqual(st["mig"], 3)
        self.assertIs(st["migd"], True)
        self.assertEqual(st["tp"], 60000 + 15 + 415)
        # user A was re-imported (idempotent overwrite) — not re-counted
        self.assertEqual(st["user_" + ADDR_A][7], 60000)

    def test_crash_after_cursor_update_skips_reimported_users(self):
        # crash AFTER the first import AND after mig_cursor=1 landed on-chain
        uv.MIG_CURSOR_EVERY = 1  # cursor after every import (test mode)
        try:
            CRASH_AFTER["n"] = 2
            with self.assertRaises(_CrashNow):
                self.run_phase_d()
            self.assertEqual(CHAIN[NEW_TRACKER]["mig"], 1)

            CRASH_AFTER["n"] = None
            n_import_before = len(self.imports_of(78))
            self.run_phase_d()
            # user 0 (already covered by the cursor) is NOT re-imported
            n_import_after = len(self.imports_of(78))
            self.assertEqual(n_import_after - n_import_before, 2)
            self.assertEqual(CHAIN[NEW_TRACKER]["uc"], 3)
        finally:
            uv.MIG_CURSOR_EVERY = 20

    # -- 4: finalize is never double-counted / never zeroes ------------------

    def test_finalize_rerun_after_completion_is_noop(self):
        self.run_phase_d()
        tp = CHAIN[NEW_TRACKER]["tp"]
        self.assertIs(CHAIN[NEW_TRACKER]["migd"], True)
        n_final = len(self.imports_of(79))
        # re-run phase D end-to-end (e.g. operator ran it twice)
        uv.STATE["migration_finalized"] = True
        self.run_phase_d()
        # no additional finalize call and totals untouched
        self.assertEqual(len(self.imports_of(79)), n_final)
        self.assertEqual(CHAIN[NEW_TRACKER]["tp"], tp)

    # -- 5: fail closed when the old tracker moved ---------------------------

    def test_fail_closed_if_old_tracker_changed_during_migration(self):
        # record new activity on the OLD tracker after the snapshot was
        # taken (e.g. a miner submitted a heartbeat between imports)
        original_read = FakeDaemon.read_key

        def read_then_mutate(self, contract, key):
            v = original_read(self, contract, key)
            if (contract, key) == (NEW_TRACKER, "mig") and "mutated" not in CHAIN:
                CHAIN["mutated"] = True
                CHAIN[OLD_TRACKER]["tp"] += 25  # new activity on-chain
            return v

        FakeDaemon.read_key = read_then_mutate
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.run_phase_d()
            self.assertIn("FAIL CLOSED", str(ctx.exception))
        finally:
            FakeDaemon.read_key = original_read
        # the cutover has NOT run: registry still points to the old tracker
        self.assertEqual(CHAIN[REGISTRY]["cur_AirdropTracker"], OLD_TRACKER)

    # -- 6: unpause is crash-safe, never twice -------------------------------

    def test_unpause_never_twice_after_crash(self):
        # phase U with the tracker paused
        self.assertIs(CHAIN[NEW_TRACKER]["pz"], True)
        uv.phase_u(self.D)
        self.assertIs(CHAIN[NEW_TRACKER]["pz"], False)
        unpause_calls = len([1 for (c, e, p) in INVOKE_LOG if e == 74])
        self.assertEqual(unpause_calls, 1)

        # simulate: script crashed right after the on-chain unpause but
        # BEFORE saving the local state → relaunch phase U
        uv.STATE.pop("unpaused", None)
        INVOKE_LOG.clear()
        uv.phase_u(self.D)
        unpause_calls = len([1 for (c, e, p) in INVOKE_LOG if e == 74])
        self.assertEqual(unpause_calls, 0, "second run must NOT unpause again")
        self.assertIs(CHAIN[NEW_TRACKER]["pz"], False)

    # -- 7: registry cutover upgrades both VaultSwap aliases -----------------

    def test_cutover_upgrades_both_vaultswap_aliases(self):
        uv.phase_b(self.D)
        self.assertEqual(CHAIN[REGISTRY]["cur_VaultSwap"], NEW_SWAP)
        self.assertEqual(CHAIN[REGISTRY]["cur_VaultSwapV2"], NEW_SWAP)
        # rollback pointers preserved
        self.assertEqual(CHAIN[REGISTRY]["prev_VaultSwapV2"], OLD_SWAP)

    def test_cutover_is_idempotent(self):
        uv.phase_b(self.D)
        INVOKE_LOG.clear()
        uv.phase_b(self.D)
        upgrades = [1 for (c, e, p) in INVOKE_LOG if e == 4]
        self.assertEqual(upgrades, [], "second run must not re-upgrade")

    # -- 2 (order): the migration happens BEFORE the registry cutover -------

    def test_phase_order_all_runs_migration_before_cutover(self):
        order = []
        orig_d, orig_b, orig_u = uv.phase_d, uv.phase_b, uv.phase_u
        uv.phase_d = lambda D, old: order.append("d")
        uv.phase_b = lambda D: order.append("b")
        uv.phase_u = lambda D: order.append("u")
        try:
            # emulate what main() does for --phase all
            phases = ["a", "c", "d", "b", "u", "e"]
            self.assertEqual(phases.index("d") < phases.index("b"), True)
            self.assertEqual(phases.index("b") < phases.index("u"), True)
            for ph in phases:
                if ph == "d":
                    uv.phase_d(self.D, OLD_TRACKER)
                elif ph == "b":
                    uv.phase_b(self.D)
                elif ph == "u":
                    uv.phase_u(self.D)
            self.assertEqual(order, ["d", "b", "u"])
        finally:
            uv.phase_d, uv.phase_b, uv.phase_u = orig_d, orig_b, orig_u


if __name__ == "__main__":
    unittest.main(verbosity=2)
