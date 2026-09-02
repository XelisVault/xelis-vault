#!/usr/bin/env python3
"""
Check deployment priority of all Silex contracts.
Returns exit code 0 if all contracts are properly tagged, 1 otherwise.

Usage:
    python3 scripts/check_deployment_priority.py
"""
import os
import re
import sys
from pathlib import Path

CONTRACTS_DIR = Path(__file__).parent.parent / "contracts"
PENDING_MARKER = "DEPLOYMENT STATUS: PENDING"
CORE_MARKER = "XELIS Vault v5.0"  # Core contracts have this version tag

def scan_contracts():
    """Scan all .slx files and classify them."""
    contracts = []
    for slx_file in sorted(CONTRACTS_DIR.rglob("*.slx")):
        rel_path = slx_file.relative_to(CONTRACTS_DIR.parent)
        try:
            content = slx_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  ERROR reading {rel_path}: {e}")
            continue

        is_pending = PENDING_MARKER in content
        is_core = not is_pending  # Everything not pending is core

        # Extract feature number if brainstorming
        feature_match = re.search(r'Brainstorming Feature #(\d+)', content)
        feature_num = int(feature_match.group(1)) if feature_match else None

        # Extract contract name
        name_match = re.search(r'//\s*(\w+\.slx)\s*—', content)
        name = name_match.group(1).replace('.slx', '') if name_match else slx_file.stem

        contracts.append({
            'path': str(rel_path),
            'name': name,
            'is_pending': is_pending,
            'is_core': is_core,
            'feature_num': feature_num,
        })
    return contracts

def main():
    print("=" * 70)
    print("XELIS Vault — Deployment Priority Check")
    print("=" * 70)
    print()

    contracts = scan_contracts()
    core = [c for c in contracts if c['is_core']]
    pending = [c for c in contracts if c['is_pending']]

    print(f"✅ CORE contracts (Phase 1 — deploy now): {len(core)}")
    for c in core:
        print(f"   - {c['path']}")
    print()

    print(f"⛔ PENDING contracts (Phase 5+ — do NOT deploy yet): {len(pending)}")
    for c in pending:
        feat = f" [Feature #{c['feature_num']}]" if c['feature_num'] else ""
        print(f"   - {c['path']}{feat}")
    print()

    print("=" * 70)
    print(f"TOTAL: {len(contracts)} contracts ({len(core)} core + {len(pending)} pending)")
    print()

    # Verify all pending contracts have the marker in the first 20 lines
    bad = []
    for c in pending:
        path = CONTRACTS_DIR.parent / c['path']
        lines = path.read_text(encoding='utf-8').split('\n')[:20]
        header = '\n'.join(lines)
        if PENDING_MARKER not in header:
            bad.append(c['path'])

    if bad:
        print("⚠️  WARNING: These pending contracts don't have the marker in their header:")
        for p in bad:
            print(f"   - {p}")
        print()
        print("The marker must be in the first 20 lines for auto-deployers to detect it.")
        sys.exit(1)
    else:
        print("✅ All pending contracts have the DEPLOYMENT STATUS marker in their header.")
        print("✅ Auto-deployers (Miya, etc.) can safely skip pending contracts.")
        sys.exit(0)

if __name__ == '__main__':
    main()
