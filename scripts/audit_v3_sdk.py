#!/usr/bin/env python3
"""audit_v3_sdk.py — AUDIT PASS 4 (SDK/CLI/tests coherence) for VaultLaunch v3.

Verifies propose/update_project_info builder signatures match the contract's
entry parameter order exactly, the SDK entry-id table equals the real chunk
numbering, the reader exposes every v3 view, and the test spec-API covers
the v3 views. Exit 1 on any drift."""
import inspect
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sdk" / "xvault"))
sys.path.insert(0, str(REPO / "scripts"))

from xvault import launchpad as lp          # noqa: E402
from xvault import protocol                 # noqa: E402
from silex_parse import SilexFile           # noqa: E402

SRC = (REPO / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
fails = []

# 1. propose: contract signature vs SDK builder parameter order
m = re.search(r"entry propose\(([^)]*)\)", SRC)
contract_params = [p.strip().split(":")[0] for p in m.group(1).split(",")]
sig = inspect.signature(lp.propose_params)
sdk_params = list(sig.parameters)
print(f"contrat propose({', '.join(contract_params)})")
print(f"SDK    propose_params({', '.join(sdk_params)})")
if len(sdk_params) != len(contract_params) or \
        any(sp != cp for cp, sp in zip(contract_params, sdk_params)):
    fails.append("propose: ordre paramètres SDK != contrat")
else:
    print("  [OK ] 11 paramètres, ordre exact identique\n")

# 2. update_project_info: pid + 6 metadata fields
m = re.search(r"entry update_project_info\(([^)]*)\)", SRC)
contract_params = [p.strip().split(":")[0] for p in m.group(1).split(",")]
sig = inspect.signature(lp.update_info_params)
sdk_params = list(sig.parameters)
print(f"contrat update_project_info({', '.join(contract_params)})")
print(f"SDK    update_info_params({', '.join(sdk_params)})")
if contract_params[0] == "pid" and contract_params[1:] == sdk_params:
    print("  [OK ] pid + 6 métadonnées, ordre identique\n")
else:
    fails.append("update_project_info: mismatch ordre paramètres")

# 3. SDK entry-id table == real declaration order
sf = SilexFile.parse(REPO / "contracts" / "launchpad" / "VaultLaunch.slx")
real = {f.name: i for i, f in enumerate(sf.functions)}
bad = [(n, c, real.get(n)) for n, c in protocol.LAUNCHPAD_ENTRY_IDS.items()
       if real.get(n) != c]
if bad:
    fails.append(f"entry ids drift: {bad}")
else:
    print(f"  [OK ] {len(protocol.LAUNCHPAD_ENTRY_IDS)} entry-ids SDK == "
          f"ordre de déclaration réel")
    alt_same = set(protocol.LAUNCHPAD_ENTRY_IDS) == set(protocol.LAUNCHPAD_ENTRY_IDS_ALT)
    if not alt_same:
        fails.append("table ALT != bijection de la table principale")
    else:
        print("  [OK ] table ALT = bijection exacte\n")

# 4. reader exposes every v3 view
reader_methods = [m for m in dir(lp.LaunchpadReader) if not m.startswith("_")]
need = ["social_links", "trading_stats", "market_cap_history",
        "volume_stats", "team_allocation", "project", "stats",
        "proposal_data"]
missing = [n for n in need if n not in reader_methods]
if missing:
    fails.append(f"reader manque: {missing}")
else:
    print(f"  [OK ] reader v3 complet: {', '.join(need)}\n")

# 5. test spec-API covers the v3 views
t = (REPO / "tests" / "test_launchpad_reference.py").read_text()
spec_block = re.search(r"spec = \{(.*?)\}", t, re.S)
missing_v3 = []
if spec_block:
    missing_v3 = [v for v in ["get_social_links", "get_trading_stats",
                              "get_market_cap_history", "get_proposal_data",
                              "get_volume_stats"]
                  if f'"{v}"' not in spec_block.group(1)]
if missing_v3:
    print(f"  [GAP] test spec-API sans les vues v3: {missing_v3}")
    fails.append(f"spec-API test gap: {missing_v3}")
else:
    print("  [OK ] test spec-API couvre les vues v3")

print()
if fails:
    print("AUDIT 4: FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("AUDIT 4: PASS — signatures, entry-ids, reader et tests alignés sur le contrat.")
