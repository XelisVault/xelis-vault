#!/usr/bin/env python3
"""
XELIS Vault v11.5 — Full clean redeployment orchestrator.

Follows docs/DEPLOYMENT_GUIDE.md phase order (Phase 9 Insurance SKIPPED).
Resumable: state saved to docs/deployment_state.json after EVERY step.
Usage: python3 deploy_v12.py --phase N [--only step_name]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from protocol import (  # noqa: E402
    Protocol, WalletClient, DaemonClient, RPCError,
    val_u64, val_u128, val_u8, val_bool, val_str, val_hash, val_addr, parse_cell,
    ZERO_HASH, ADMIN,
)

BYTECODE_DIR = Path("/tmp")
STATE_PATH = REPO / "docs" / "deployment_state.json"
XEL = ZERO_HASH
TEN_XEL = 1_000_000_000          # 10 XEL @8dp — create_asset deposit
VLT_500K = 50_000_000_000_000    # 500k VLT @8dp

S = {}  # live state: name -> hash


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"contracts": {}, "assets": {}, "steps_done": [], "log": []}


STATE = load_state()


def save():
    STATE_PATH.write_text(json.dumps(STATE, indent=2))


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    STATE["log"].append(line)
    save()


class Deployer:
    def __init__(self):
        self.p = Protocol()
        self.w: WalletClient = self.p.wallet
        self.d: DaemonClient = self.p.daemon

    # -- low level ----------------------------------------------------------
    def deploy(self, name: str, max_gas: int = 1_000_000) -> str:
        """Deploy compiled module; contract hash == tx hash. Resumable."""
        if name in S:
            log(f"SKIP deploy {name} (déjà déployé: {S[name][:16]}…)")
            return S[name]
        hexfile = BYTECODE_DIR / f"deploy_{name}.hex"
        module = hexfile.read_text().strip()
        self.w._wait_nonce_catchup()

        def _build():
            payload = {
                "deploy_contract": {"contract": module,
                                    "invoke": {"max_gas": max_gas}},
                "fee": {"fixed": 100_000_000},
                "broadcast": True,
            }
            r = self.w._call("build_transaction", payload)
            h = r.get("hash") if isinstance(r, dict) else None
            if not h:
                raise RPCError(f"deploy {name}: no hash: {r}")
            return h
        from protocol import _with_retries
        tx = _with_retries(_build)
        self.p.wait(tx, timeout=180)
        rev = self.p.revert_reason(tx)
        if rev:
            raise RuntimeError(f"deploy {name} REVERTED: {rev}")
        S[name] = tx
        STATE["contracts"][name] = tx
        save()
        log(f"DEPLOY {name} -> {tx}")
        return tx

    def invoke(self, contract: str, entry: int, params=None, deposits=None,
               max_gas=5_000_000, label=""):
        key = f"{label}@{contract[:12]}"
        if key in STATE.get("steps", []):
            log(f"SKIP {label} (déjà fait)")
            return None
        tx = self.w.invoke(contract, entry, params or [], deposits or {},
                           max_gas=max_gas)
        self.p.wait(tx, timeout=180)
        rev = self.p.revert_reason(tx)
        if rev:
            raise RuntimeError(f"{label or entry} REVERTED: {rev}")
        log(f"OK {label} (chunk {entry}) -> {tx[:20]}…")
        STATE.setdefault("steps", []).append(key)
        save()
        return tx

    def read(self, contract: str, key: str):
        return self.d.read_key(contract, key)

    def register(self, reg_hash: str, name: str, target: str):
        # ContractRegistry.register(name, hash): chunk 3 per map. Idempotent.
        cur = self.read(reg_hash, f"cur_{name}")
        if cur == target:
            log(f'SKIP register "{name}" (déjà = {target[:16]}…)')
            return
        self.invoke(reg_hash, 3, [val_str(name), val_hash(target)],
                    label=f'register "{name}"')

    def set_minter(self, xusd: str, who: str, allowed: bool = True):
        self.invoke(xusd, 18, [val_hash(who), val_bool(allowed)],
                    label=f"xUSD.set_minter({who[:12]}…,{allowed})")

    def set_burner(self, xusd: str, who: str, allowed: bool = True):
        self.invoke(xusd, 19, [val_hash(who), val_bool(allowed)],
                    label=f"xUSD.set_burner({who[:12]}…,{allowed})")


# ---------------------------------------------------------------------------
# Phase implementations (guide order, Phase 9 skipped)
# ---------------------------------------------------------------------------

def phase1(D: Deployer):
    log("=== PHASE 1: Infrastructure ===")
    reg = D.deploy("ContractRegistry")
    comp = D.deploy("ComplianceModule")
    # ComplianceModule.set_registry — chunk from map
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())
    cid = next(c for c, i in cmap["ComplianceModule"].items()
               if i["name"] == "set_registry")
    D.invoke(comp, int(cid), [val_hash(reg)], label="Compliance.set_registry")
    STATE["assets"]["REGISTRY"] = reg
    save()


def phase2(D: Deployer):
    log("=== PHASE 2: Token Layer ===")
    reg = S["ContractRegistry"]
    # VLTToken
    vlt = D.deploy("VLTToken")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    tx = D.invoke(vlt, cid("VLTToken", "create_asset"), [],
                  deposits={XEL: {"amount": TEN_XEL}},
                  max_gas=5_000_000, label="VLT.create_asset")
    asset = extract_new_asset(vlt)
    STATE["assets"]["VLT"] = asset
    save()
    log(f"VLT ASSET = {asset}")
    D.invoke(vlt, cid("VLTToken", "set_registry"), [val_hash(reg)],
             label="VLT.set_registry")
    D.register(reg, "VLTToken", vlt)
    # xUSD
    xusd = D.deploy("xUSD")
    tx = D.invoke(xusd, cid("xUSD", "create_asset"), [],
                  deposits={XEL: {"amount": TEN_XEL}},
                  max_gas=5_000_000, label="xUSD.create_asset")
    xasset = extract_new_asset(xusd)
    STATE["assets"]["XUSD"] = xasset
    save()
    log(f"xUSD ASSET = {xasset}")
    D.invoke(xusd, cid("xUSD", "set_registry"), [val_hash(reg)],
             label="xUSD.set_registry")
    D.register(reg, "xUSD", xusd)
    # FaucetContract
    fau = D.deploy("FaucetContract")
    D.invoke(fau, cid("FaucetContract", "set_registry"), [val_hash(reg)],
             label="Faucet.set_registry")
    D.register(reg, "FaucetContract", fau)


def phase3(D: Deployer):
    log("=== PHASE 3: Mining & Oracle ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, vlt = S["ContractRegistry"], STATE["assets"]["VLT"]
    vltc = S["VLTToken"]
    miner = D.deploy("XelisVaultMiner")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_vlt_contract", val_hash(vltc)),
                    ("set_vlt_asset", val_hash(vlt)),
                    ("set_treasury", val_addr(ADMIN))]:
        D.invoke(miner, cid("XelisVaultMiner", fn), [arg], label=f"Miner.{fn}")
    D.register(reg, "XelisVaultMiner", miner)
    # StakedOracle
    oracle = D.deploy("StakedOracle")
    D.invoke(oracle, cid("StakedOracle", "set_registry"), [val_hash(reg)],
             label="Oracle.set_registry")
    D.invoke(oracle, cid("StakedOracle", "set_miner_contract"),
             [val_hash(miner)], label="Oracle.set_miner_contract")
    D.invoke(oracle, cid("StakedOracle", "add_feed_entry"),
             [val_str("XEL/USD"), val_hash(XEL), val_u8(8),
              val_u64(1), val_u64(100_000_000_000)],
             label="Oracle.add_feed_entry(XEL/USD)")
    D.register(reg, "StakedOracle", oracle)
    # v12.1: le Miner minte les récompenses via VLT.mint_to (chunk 4) —
    # il DOIT être minter, sinon submit_price → aggregate → notminter
    D.invoke(vltc, cid("VLTToken", "set_minter"), [val_hash(miner), val_bool(True)],
             label="VLT.set_minter(miner)")
    D.invoke(miner, cid("XelisVaultMiner", "register_service"),
             [val_u8(1), val_hash(oracle)],
             max_gas=10_000_000, label="Miner.register_service(oracle,1)")
    # MinerPool
    mp = D.deploy("MinerPool")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_miner_contract", val_hash(miner)),
                    ("set_vlt_asset", val_hash(vlt))]:
        D.invoke(mp, cid("MinerPool", fn), [arg], label=f"MinerPool.{fn}")
    D.register(reg, "MinerPool", mp)


def phase4(D: Deployer):
    log("=== PHASE 4: Core Lending ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg = S["ContractRegistry"]
    xusd, xasset = S["xUSD"], STATE["assets"]["XUSD"]
    oracle = S["StakedOracle"]
    admin_addr = ADMIN
    # IRM
    irm = D.deploy("InterestRateModel")
    D.invoke(irm, cid("InterestRateModel", "set_rates"),
             [val_u64(50), val_u64(1000), val_u64(5000), val_u64(8000)],
             label="IRM.set_rates")
    D.register(reg, "InterestRateModel", irm)
    # VaultEngineV3
    ve = D.deploy("VaultEngineV3")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_xusd_contract", val_hash(xusd)),
                    ("set_xusd_asset", val_hash(xasset)),
                    ("set_treasury", val_addr(admin_addr))]:
        D.invoke(ve, cid("VaultEngineV3", fn), [arg], label=f"VE.{fn}")
    D.register(reg, "VaultEngine", ve)
    D.register(reg, "VaultEngineV3", ve)   # alias pour allow-list FeeDistributor
    D.set_minter(xusd, ve)
    D.set_burner(xusd, ve)
    # SavingsRate
    sav = D.deploy("SavingsRate")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_xusd_contract", val_hash(xusd)),
                    ("set_xusd_asset", val_hash(xasset)),
                    ("set_treasury", val_addr(admin_addr))]:
        D.invoke(sav, cid("SavingsRate", fn), [arg], label=f"Savings.{fn}")
    D.set_minter(xusd, sav)
    D.register(reg, "SavingsRate", sav)
    # FlashCallback + FlashLoan
    cb = D.deploy("FlashCallback")
    fl = D.deploy("FlashLoan")
    D.invoke(fl, cid("FlashLoan", "set_registry"), [val_hash(reg)],
             label="FL.set_registry")
    D.invoke(fl, cid("FlashLoan", "set_treasury"), [val_addr(admin_addr)],
             label="FL.set_treasury")
    D.invoke(fl, cid("FlashLoan", "verify_callback"), [val_hash(cb)],
             label="FL.verify_callback(CB)")
    D.invoke(cb, cid("FlashCallback", "set_flash_loan"), [val_hash(fl)],
             label="CB.set_flash_loan")
    D.register(reg, "FlashLoan", fl)
    D.register(reg, "FlashCallback", cb)


def phase5(D: Deployer):
    log("=== PHASE 5: AMM ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg = S["ContractRegistry"]
    xusd, xasset = S["xUSD"], STATE["assets"]["XUSD"]
    oracle = S["StakedOracle"]
    admin_addr = ADMIN
    vs = D.deploy("VaultSwapV2")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_xusd_contract", val_hash(xusd)),
                    ("set_xusd_asset", val_hash(xasset)),
                    ("set_treasury", val_addr(admin_addr)),
                    ("set_oracle", val_hash(oracle))]:
        D.invoke(vs, cid("VaultSwapV2", fn), [arg], label=f"VS.{fn}")
    D.set_minter(xusd, vs)
    D.set_burner(xusd, vs)
    psm = D.deploy("PSM")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_xusd_contract", val_hash(xusd)),
                    ("set_xusd_asset", val_hash(xasset)),
                    ("set_treasury", val_addr(admin_addr)),
                    ("set_oracle", val_hash(oracle))]:
        D.invoke(psm, cid("PSM", fn), [arg], label=f"PSM.{fn}")
    D.set_minter(xusd, psm)
    D.set_burner(xusd, psm)
    # F-10: VaultSwap délègue à PSM
    D.invoke(vs, cid("VaultSwapV2", "set_psm_contract"), [val_hash(psm)],
             label="VS.set_psm_contract")
    D.register(reg, "VaultSwapV2", vs)
    D.register(reg, "VaultSwap", vs)       # alias compat tooling
    D.register(reg, "PSM", psm)


def phase6(D: Deployer):
    log("=== PHASE 6: Lending Markets ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, oracle, irm = S["ContractRegistry"], S["StakedOracle"], S["InterestRateModel"]
    admin_addr = ADMIN
    lm = D.deploy("LendingMarket")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_oracle", val_hash(oracle)),
                    ("set_treasury", val_addr(admin_addr))]:
        D.invoke(lm, cid("LendingMarket", fn), [arg], label=f"LM.{fn}")
    D.register(reg, "LendingMarket", lm)
    pl = D.deploy("PeerLoan")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_oracle", val_hash(oracle)),
                    ("set_treasury", val_addr(admin_addr))]:
        D.invoke(pl, cid("PeerLoan", fn), [arg], label=f"PL.{fn}")
    D.register(reg, "PeerLoan", pl)
    sp = D.deploy("SyndicatePool")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_oracle", val_hash(oracle)),
                    ("set_treasury", val_addr(admin_addr))]:
        D.invoke(sp, cid("SyndicatePool", fn), [arg], label=f"SP.{fn}")
    D.register(reg, "SyndicatePool", sp)


def phase7(D: Deployer):
    log("=== PHASE 7: Auctions & Privacy ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg = S["ContractRegistry"]
    au = D.deploy("SealedBidAuction")
    D.invoke(au, cid("SealedBidAuction", "set_registry"), [val_hash(reg)],
             label="Auction.set_registry")
    D.register(reg, "SealedBidAuction", au)
    mx = D.deploy("PrivacyMixer")
    D.invoke(mx, cid("PrivacyMixer", "set_registry"), [val_hash(reg)],
             label="Mixer.set_registry")
    D.register(reg, "PrivacyMixer", mx)


def phase8(D: Deployer):
    log("=== PHASE 8: Tokenization & Treasury ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, vlt, comp = S["ContractRegistry"], STATE["assets"]["VLT"], S["ComplianceModule"]
    admin_addr = ADMIN
    av = D.deploy("AssetVault")
    D.invoke(av, cid("AssetVault", "set_registry"), [val_hash(reg)],
             label="AV.set_registry")
    D.invoke(av, cid("AssetVault", "set_compliance"), [val_hash(comp)],
             label="AV.set_compliance")
    D.register(reg, "AssetVault", av)
    tv = D.deploy("TreasuryVault")
    D.register(reg, "TreasuryVault", tv)
    rs = D.deploy("RevenueShare")
    D.invoke(rs, cid("RevenueShare", "set_registry"), [val_hash(reg)],
             label="RS.set_registry")
    D.invoke(rs, cid("RevenueShare", "set_share_token"), [val_hash(vlt)],
             label="RS.set_share_token(VLT)")
    D.register(reg, "RevenueShare", rs)
    pay = D.deploy("Payroll")
    D.invoke(pay, cid("Payroll", "set_registry"), [val_hash(reg)],
             label="Payroll.set_registry")
    D.invoke(pay, cid("Payroll", "set_treasury"), [val_addr(admin_addr)],
             label="Payroll.set_treasury")
    D.register(reg, "Payroll", pay)


def phase10(D: Deployer):
    log("=== PHASE 10: Governance ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, vlt = S["ContractRegistry"], STATE["assets"]["VLT"]
    vltc, oracle = S["VLTToken"], S["StakedOracle"]
    gv = D.deploy("GovernanceVault")
    for fn, arg in [("set_registry", val_hash(reg)),
                    ("set_vlt_contract", val_hash(vltc)),
                    ("set_vlt_asset", val_hash(vlt))]:
        D.invoke(gv, cid("GovernanceVault", fn), [arg], label=f"GV.{fn}")
    D.register(reg, "GovernanceVault", gv)
    tl = D.deploy("Timelock")
    D.register(reg, "Timelock", tl)
    gm = D.deploy("GuardianMultisig")
    D.invoke(gm, cid("GuardianMultisig", "set_timelock"), [val_hash(tl)],
             label="GM.set_timelock")
    D.register(reg, "GuardianMultisig", gm)
    gov = D.deploy("Governor")
    D.invoke(gov, cid("Governor", "set_governance_vault"), [val_hash(gv)],
             label="Gov.set_governance_vault")
    D.invoke(gov, cid("Governor", "set_timelock"), [val_hash(tl)],
             label="Gov.set_timelock")
    D.register(reg, "Governor", gov)
    og = D.deploy("OracleGovernance")
    for fn, arg in [("set_governance_vault", val_hash(gv)),
                    ("set_oracle", val_hash(oracle)),
                    ("set_timelock", val_hash(tl))]:
        D.invoke(og, cid("OracleGovernance", fn), [arg], label=f"OG.{fn}")
    D.register(reg, "OracleGovernance", og)
    # cross-wiring Timelock <-> Governor/Guardian
    D.invoke(tl, cid("Timelock", "set_governor"), [val_hash(gov)],
             label="TL.set_governor")
    D.invoke(tl, cid("Timelock", "set_guardian_contract"), [val_hash(gm)],
             label="TL.set_guardian_contract")


def phase11(D: Deployer):
    log("=== PHASE 11: Chat ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, miner = S["ContractRegistry"], S["XelisVaultMiner"]
    vltc, vlt_asset = S["VLTToken"], STATE["assets"]["VLT"]
    chat = D.deploy("VaultChat")
    # v11.6: set_registry/set_vlt_contract inexistants sur VaultChat —
    # seul set_vlt_asset (chunk 96) existe et est requis pour le bond.
    D.invoke(chat, cid("VaultChat", "set_vlt_asset"), [val_hash(vlt_asset)],
             label="Chat.set_vlt_asset")
    # F-13: le relayer doit d'abord staker un bond >= 50 VLT
    BOND = 5_000_000_000  # 50 VLT @8dp
    D.invoke(S["VLTToken"], cid("VLTToken", "mint_to_entry"),
             [val_addr(ADMIN), val_u64(100_000_000_000)],  # 1000 VLT pour l'admin
             label="VLT.mint_to_entry(admin,1000)")
    D.invoke(chat, cid("VaultChat", "stake_relayer_bond"), [val_u64(BOND)],
             deposits={vlt_asset: {"amount": BOND}},
             label="Chat.stake_relayer_bond(50)")
    D.invoke(chat, cid("VaultChat", "set_relayer"), [val_addr(ADMIN), val_bool(True)],
             label="Chat.set_relayer(admin)")
    D.register(reg, "VaultChat", chat)
    D.invoke(miner, cid("XelisVaultMiner", "register_service"),
             [val_u8(2), val_hash(chat)],
             max_gas=10_000_000, label="Miner.register_service(chat,2)")


def phase12(D: Deployer):
    log("=== PHASE 12: Founder & Fees ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, vlt = S["ContractRegistry"], STATE["assets"]["VLT"]
    vltc, miner, tv = S["VLTToken"], S["XelisVaultMiner"], S["TreasuryVault"]
    for inst, regname in [("FounderVesting4y", "FounderVesting4y"),
                          ("FounderVesting10y", "FounderVesting10y")]:
        # instances distinctes: hash déjà connu => ne JAMAIS passer par le cache
        if inst in STATE["contracts"]:
            fv = STATE["contracts"][inst]
            log(f"SKIP deploy {inst} (déjà déployé: {fv[:16]}…)")
        else:
            fv = D.deploy("FounderVesting")
            STATE["contracts"][inst] = fv
            save()
        D.invoke(fv, cid("FounderVesting", "set_founder"), [val_addr(ADMIN)],
                 label=f"{regname}.set_founder")
        D.invoke(fv, cid("FounderVesting", "set_vlt_contract"), [val_hash(vltc)],
                 label=f"{regname}.set_vlt_contract")
        D.invoke(fv, cid("FounderVesting", "set_vlt_asset"), [val_hash(vlt)],
                 label=f"{regname}.set_vlt_asset")
        # fund 500k VLT via invoke deposit
        D.invoke(fv, cid("FounderVesting", "get_version"), [],
                 deposits={vlt: {"amount": VLT_500K}},
                 label=f"{regname}.fund 500k VLT")
        D.register(reg, regname, fv)
    fd = D.deploy("FeeDistributor")
    for fn, arg in [("set_founder", val_addr(ADMIN)),
                    ("set_treasury", val_hash(tv)),
                    ("set_vlt_contract", val_hash(vltc)),
                    ("set_vlt_asset", val_hash(vlt)),
                    ("set_registry", val_hash(reg))]:
        D.invoke(fd, cid("FeeDistributor", fn), [arg], label=f"FD.{fn}")
    D.register(reg, "FeeDistributor", fd)
    md = D.deploy("MinerDelegation")
    for fn, arg in [("set_vlt_asset", val_hash(vlt)),
                    ("set_miner_contract_hash", val_hash(miner)),
                    ("set_registry", val_hash(reg))]:
        D.invoke(md, cid("MinerDelegation", fn), [arg], label=f"MD.{fn}")
    D.register(reg, "MinerDelegation", md)
    # Guide 12.4: wiring bidirectionnel de la délégation
    D.invoke(miner, cid("XelisVaultMiner", "set_delegation_contract"),
             [val_hash(md)], label="Miner.set_delegation_contract")
    D.invoke(S["StakedOracle"], cid("StakedOracle", "set_delegation_contract"),
             [val_hash(md)], label="Oracle.set_delegation_contract")


def phase13(D: Deployer):
    log("=== PHASE 13: Airdrop ===")
    import json as _j
    cmap = _j.loads((REPO / "docs" / "entry_chunk_ids.json").read_text())

    def cid(c, fn):
        return int(next(k for k, v in cmap[c].items() if v["name"] == fn))

    reg, vltc = S["ContractRegistry"], S["VLTToken"]
    at = D.deploy("AirdropTracker")
    D.invoke(at, cid("AirdropTracker", "set_registry"), [val_hash(reg)],
             label="AT.set_registry")
    D.invoke(at, cid("AirdropTracker", "set_vlt_contract"), [val_hash(vltc)],
             label="AT.set_vlt_contract")
    recorders = ["XelisVaultMiner", "StakedOracle", "VaultChat", "Governor",
                 "VaultEngineV3", "VaultSwapV2", "PSM"]
    for n in recorders:
        D.invoke(at, cid("AirdropTracker", "set_authorized_recorder"),
                 [val_hash(S[n]), val_bool(True)],
                 label=f"AT.recorder({n})")
    D.register(reg, "AirdropTracker", at)


def extract_new_asset(contract_hash: str) -> str:
    """Read the created asset id from contract storage key 'ah'."""
    D = DaemonClient()
    for _ in range(10):
        v = D.read_key(contract_hash, "ah")
        if isinstance(v, str) and len(v) == 64:
            return v
        time.sleep(3)
    raise RuntimeError(f"asset hash ('ah') not found on {contract_hash}")


PHASES = {1: phase1, 2: phase2, 3: phase3, 4: phase4, 5: phase5, 6: phase6,
          7: phase7, 8: phase8, 10: phase10, 11: phase11, 12: phase12,
          13: phase13}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, required=True)
    args = ap.parse_args()
    global S
    S = STATE["contracts"]
    D = Deployer()
    fn = PHASES[args.phase]
    fn(D)
    log(f"=== PHASE {args.phase} COMPLETE ===")


if __name__ == "__main__":
    main()
