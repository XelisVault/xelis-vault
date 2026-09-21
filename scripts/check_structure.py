#!/usr/bin/env python3
"""check_structure.py — repository structure & hygiene gate (CI job `structure`).

Enforces the repository layout decided after the XelisVault audit (v13,
extended in v15 when VaultLaunch joined the mixer as the second active
contract):

  1. contracts/ contains ONLY .slx files, and only inside contracts/mixer/
     and contracts/launchpad/ (the active, self-contained contracts — one
     per product family; anything else needs a deliberate layout decision,
     not a stray file).
  2. No active script imports the archived legacy/ code. Reading legacy files
     as DATA (e.g. lint_silex.py --scan-legacy, explicitly a non-CI flag) is
     allowed; importing legacy Python modules would resurrect known-broken
     v12 tooling.
  3. No secrets in active files: GitHub PATs (github_pat_/ghp_), API keys
     (sk-…) or private keys (BEGIN … PRIVATE KEY). The patterns are precise
     (length-checked) so documentation mentions don't self-trigger.
  4. No binary blobs > 5 MB outside legacy/ (v13 removed 29 MB of .exe from
     git — keep it that way).

Exit code: 0 if everything is clean, 1 otherwise, 2 on tool error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_contracts_layout(repo: Path) -> List[str]:
    problems: List[str] = []
    contracts = repo / "contracts"
    if not contracts.is_dir():
        return [f"contracts/ directory missing under {repo}"]

    slx_files = sorted(contracts.rglob("*.slx"))
    all_files = sorted(p for p in contracts.rglob("*") if p.is_file())

    for p in all_files:
        if p.suffix != ".slx":
            problems.append(f"contracts/ must contain only .slx files — found {p.relative_to(repo)}")

    # Active contract families, one directory each (v18: mixer + launchpad + dex).
    # Adding a family is a deliberate layout decision: extend this tuple,
    # the CI workflow comment and docs/ARCHITECTURE.md in the same commit.
    active_families = ("mixer", "launchpad", "dex")
    for p in slx_files:
        parts = p.relative_to(contracts).parts
        # active contract: contracts/<family>/<Name>.slx (exactly one level)
        if len(parts) == 2 and parts[0] in active_families:
            continue
        # superseded archive: contracts/mixer/superseded/*.slx (banner-marked,
        # excluded from lint; kept for history + lint regression corpus)
        if len(parts) == 3 and parts[0] == "mixer" and parts[1] == "superseded":
            continue
        problems.append(
            f"active contract outside contracts/<{'|'.join(active_families)}/>/: "
            f"{p.relative_to(repo)} (each active contract lives in its own "
            f"family directory — stray files are not a layout decision)")

    for family in active_families:
        if not (contracts / family).is_dir() or not any(
                (contracts / family).glob("*.slx")):
            problems.append(f"contracts/{family}/ is empty — its active contract is missing")
    return problems


def check_no_legacy_imports(repo: Path) -> List[str]:
    problems: List[str] = []
    roots = [repo / "scripts", repo / "tests", repo / "sdk"]
    py_files: List[Path] = []
    for root in roots:
        if root.is_dir():
            py_files += sorted(root.rglob("*.py"))
    py_files += sorted(p for p in repo.glob("*.py"))  # root-level scripts

    import_re = re.compile(r"^\s*(?:import|from)\s+legacy\b", re.MULTILINE)
    syspath_re = re.compile(r"sys\.path\.(?:insert|append)\(\s*[^)\n]*\blegacy\b")
    for p in py_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        if import_re.search(text):
            problems.append(f"{p.relative_to(repo)} imports the legacy/ package — "
                            f"legacy v12 tooling is archived and known-broken")
        if syspath_re.search(text):
            problems.append(f"{p.relative_to(repo)} adds legacy/ to sys.path")
    return problems


# Precise secret patterns: length-checked so that prose/documentation mentions
# ("we grep for ghp_ and github_pat_") never trigger a false BLOCKER.
SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("GitHub fine-grained PAT (github_pat_…)",
     re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("GitHub classic PAT (ghp_…)",
     re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("API key (sk-…)",
     re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("private key block (BEGIN … PRIVATE KEY)",
     re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
]

SKIP_DIRS = {".git", "legacy", "reports", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_FILES = {Path(__file__).name}  # never self-scan the scanner's own regexes


def check_no_secrets(repo: Path) -> List[str]:
    problems: List[str] = []
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(repo).parts)
        if rel_parts & SKIP_DIRS:
            continue
        if p.name in SKIP_FILES:
            continue
        if p.stat().st_size > 1_000_000:
            # handled by the blob check instead
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:1024]:
            continue  # binary file
        text = raw.decode("utf-8", errors="replace")
        for label, rx in SECRET_PATTERNS:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(
                    f"SECRET FOUND [{label}] at {p.relative_to(repo)}:{line} — "
                    f"matches `{m.group(0)[:12]}…` (rotate the credential AND "
                    f"scrub git history before it was pushed)")
    return problems


def check_no_blobs(repo: Path) -> List[str]:
    problems: List[str] = []
    limit = 5 * 1024 * 1024
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(repo).parts)
        if rel_parts & SKIP_DIRS:
            continue
        size = p.stat().st_size
        if size > limit:
            problems.append(
                f"binary blob {p.relative_to(repo)} is {size/1024/1024:.1f} MB — "
                f"v13 removed the 29 MB of .exe from git; do not re-add blobs")
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Repository structure gate (XelisVault CI)")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT,
                    help="repository root (default: parent of scripts/)")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()

    print("=" * 78)
    print(f" Structure & hygiene gate v{VERSION} — XelisVault CI")
    print("=" * 78)

    sections = [
        ("contracts/ layout (only .slx under contracts/mixer|launchpad|dex/)", check_contracts_layout),
        ("no legacy/ imports in active scripts", check_no_legacy_imports),
        ("no secrets in active files", check_no_secrets),
        ("no binary blobs outside legacy/", check_no_blobs),
    ]
    failed = False
    for title, fn in sections:
        problems = fn(repo)
        status = "OK" if not problems else "FAIL"
        print(f"\n[{status}] {title}")
        for p in problems:
            failed = True
            print(f"       - {p}")

    print("\n" + "-" * 78)
    print(f" Result: {'PASS' if not failed else 'FAIL'}")
    print("=" * 78)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
