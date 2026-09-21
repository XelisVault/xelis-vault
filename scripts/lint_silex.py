#!/usr/bin/env python3
"""lint_silex.py — strict static linter for Silex (.slx) contracts.

Security-oriented linter encoding every dangerous pattern found by the
XelisVault v12 audit (worklog Tasks 1 / 2-a / 2-b). Runs on every push
(GitHub Actions job `silex-lint`) over contracts/ — legacy/ is excluded
because the 51 archived v12 contracts are known-broken by design.

Rules (id, severity):
  R1  BLOCKER  `let _ = transfer|transfer_contract|transfer_payload`
               — swallowed transfer failure (91 occurrences in v12)
  R2  BLOCKER  fire-and-forget transfer: the bool result is neither
               captured-then-required/asserted nor directly inside a
               require(...)/assert(...)
  R3  BLOCKER  rug switch: `execute_emergency_withdraw`-style entry, or any
               public function transferring the WHOLE contract balance
               (value of get_balance_for_asset) to a get_caller()-derived
               address
  R4  BLOCKER  unguarded `.expect(` / `.unwrap(` — panic on None = DoS
               (guarded = a require/is_some check on the same optional in
               the 3 preceding lines; constructor occurrences are deployment
               data -> INFO)
  R5  ERROR    68-hex-char literal (34 bytes) — XELIS Hash/Address are 32
               bytes (64 hex); wrong-padded address literal
  R6  ERROR    `unwrap_or(Hash::zero())` used as the safety fallback of a
               transfer destination/asset or a Contract::new target
  R7  WARNING  public entry (or store()-ing pub fn) with no access guard —
               potentially an unprotected admin entry (views without store
               are fine)
  R8  WARNING  while/for loop without an obvious static bound (bound is a
               runtime value — storage load, param, .len() — instead of a
               const/numeric comparison)
  R9  INFO     stale function-number comments: `// N.` (and `ID N:` /
               `(chunk N):` variants) that disagree with the real chunk
               index (declaration order) of the function they document
  R10 INFO     dead code: private `fn` whose name appears exactly once in
               the file (its own declaration) — never called
  R11 BLOCKER  deposit-params address leak: a public `deposit*` entry that
               takes an `Address` parameter — the recipient would be
               readable in plaintext invoke params at deposit time
               (PrivacyMixer V4 flaw, fixed in V5: deposits take ONLY a
               client-computed commitment hash)

Exit code: 0 if no BLOCKER/ERROR, 1 otherwise, 2 on tool error.

Usage:
  python3 scripts/lint_silex.py                       # lint contracts/ (CI mode)
  python3 scripts/lint_silex.py --contracts contracts # explicit
  python3 scripts/lint_silex.py --json reports/lint-report.json
  python3 scripts/lint_silex.py --scan-legacy legacy/contracts/privacy/PrivacyMixer.slx
                                                       # audit-validation mode:
                                                       # run all rules on known-bad
                                                       # v12 code (NOT used by CI)

Note on native functions: the linter only ever flags *usage patterns* of the
documented stdlib (transfer/transfer_contract/transfer_payload -> bool,
get_balance_for_asset/get_deposit_for_asset -> optional, get_caller ->
optional<Address>, Storage::new/load/store/delete, Contract::new/call,
require/assert/emit_event — see research/pages/features_smart-contracts_
standard-library.txt). Calling a native function is never a finding by
itself; only the dangerous audit patterns above are.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silex_parse import (  # noqa: E402
    SilexFile,
    SilexFunction,
    Call,
    find_calls,
    call_args,
    assigned_var_before,
    call_is_directly_in,
    _match_paren,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"

SEVERITY_ORDER = {"BLOCKER": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}

TRANSFER_FUNCS = ("transfer", "transfer_contract", "transfer_payload")
GUARD_FN_RE = re.compile(r"^(only_[a-z_]+|require_(owner|admin|auth|guardian)[a-z_]*|assert_(owner|admin|auth)[a-z_]*)$")


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    message: str
    snippet: str = ""


@dataclass
class Exemption:
    """A rule-7 exemption actually applied (printed for transparency)."""
    contract: str
    entry: str
    reason: str


# ---------------------------------------------------------------------------
# Rule 7 allowlist — public-by-design entries of the active protocol.
#
# These are entries that legitimately have NO access guard. Each one is a
# reviewed security decision, not a lint bypass: if the entry is renamed or
# its semantics change, the exemption stops applying and the linter flags it
# again (a stale allowlist entry is itself reported as INFO).
# ---------------------------------------------------------------------------
PUBLIC_BY_DESIGN: Dict[Tuple[str, str], str] = {
    ("PrivacyMixerV4", "withdraw"): (
        "payout is cryptographically authorized: the withdrawal recipient is "
        "bound into the note commitment and the Merkle proof against the "
        "archived roots IS the access guard (audit v12 fix for the "
        "plaintext-secret mixer)"
    ),
    ("PrivacyMixerV4", "raise_alarm"): (
        "permissionless circuit breaker by design: it can only pause the "
        "contract (a strictly safety-increasing write); unpause stays "
        "owner-only"
    ),
    ("PrivacyMixerV5", "release"): (
        "payout is cryptographically authorized and FRONT-RUN-PROOF: the "
        "recipient is recovered by recomputing the note commitment from the "
        "release params, so the caller can neither choose nor redirect the "
        "payout — the Merkle proof against the archived roots IS the access "
        "guard; the release caller only ever receives the capped bounty"
    ),
    ("PrivacyMixerV5", "release_many"): (
        "batched form of `release`: same cryptographic authorization, same "
        "front-run-proof payout binding, all-or-nothing semantics; the "
        "caller only ever receives the capped bounties"
    ),
    ("PrivacyMixerV5", "raise_alarm"): (
        "permissionless circuit breaker by design: it can only freeze NEW "
        "deposits (a strictly safety-increasing write; releases are never "
        "blockable); unpause stays owner-only"
    ),
    ("VaultLaunch", "sell"): (
        "exit path, public by design and NEVER blockable (not by pause, not "
        "by Untrusted status, not by a voting window): the payout goes ONLY "
        "to the caller and is bounded by the caller's OWN attached token "
        "deposit, which the entry consumes in full (whole-deposit semantics, "
        "v4) — the deposit IS the authorization (holders must always be "
        "able to exit)"
    ),
    ("VaultLaunch", "finalize_validation"): (
        "permissionless deadline executor: once a voting window has ended, "
        "anyone can trigger the outcome that the public tallies already "
        "determine (pass -> Asset::create + Bonding or direct-listing "
        "Graduated, fail -> Rejected/Untrusted); it moves no user funds (the "
        "v2 migration fee is taken from the project's own curve by "
        "graduate(), accounted in pending_fees; the asset creation fee is "
        "paid from the project's own earmarked budget with the unused part "
        "refunded to the creator), mints nothing to the caller, and cannot "
        "act before the deadline — the founder and the community both have "
        "natural incentives to call it"
    ),
    ("VaultLaunch", "migrate"): (
        "permissionless migration executor, public by design: the outcome "
        "is fully determined by the project's state — it can only send the "
        "project's OWN curve reserves and token inventory to the PINNED "
        "LaunchDEX contract (frozen after the first migration, D19) as a "
        "pool seed, with no destination, amount or caller choice anywhere; "
        "a 'malicious' migrator can only perform the migration the "
        "community is waiting for (anti-rug: the pool has no "
        "remove_liquidity at all)"
    ),
    ("VaultLaunch", "sync_trust_to_dex"): (
        "permissionless community keeper: it only mirrors the PUBLIC trust "
        "status (Untrusted flag) to the migrated pool's buys-pause on the "
        "pinned DEX — a strictly safety-increasing write on the buy side "
        "only (sells are never pausable, D4/D17); kept OUT of report/"
        "support on purpose so voters never need the contract-call "
        "permission (D17)"
    ),
    ("VaultLaunch", "claim_vote_deposit"): (
        "pull-refund of the caller's OWN locked deposit (D21): the storage "
        "key is v:{pid}:{round}:{caller} — it embeds the caller's address, "
        "so no voter can ever touch another voter's funds; the slot's "
        "recorded amount bounds the payout exactly, require(locked > 0) "
        "makes double claims impossible (the slot is zeroed but kept — the "
        "vote stays counted), and the round-closed check keeps deposits "
        "locked while the window is still open"
    ),
    ("LaunchDEX", "add_liquidity"): (
        "public donation entry by design: the caller attaches BOTH assets "
        "and receives back at most its OWN excess side (X7 — the pool's "
        "ratio is enforced, the excess is refunded, so the price can never "
        "be moved by a donation) — there is no remove_liquidity in the "
        "entire contract (permanent protocol-owned liquidity, X2), so the "
        "entry can only ever ADD value to the market at the market's own "
        "price; the attached deposits bound exactly what it can take"
    ),
}


# ---------------------------------------------------------------------------
# Per-function dataflow: which vars hold the caller / the whole balance?
# ---------------------------------------------------------------------------

ASSIGN_RE = re.compile(
    r"(?:let|var)\s+([A-Za-z_]\w*)\s*(?::[^=\n]*?)?\s*=(?!=)\s*([^\n;]+)|"
    r"(?<![\w.)(])([A-Za-z_]\w*)\s*(?::[^=\n]*?)?\s*=(?!=)(?<![<>!=])\s*([^\n;=]+)"
)


def _strip_calls(text: str) -> str:
    """Remove balanced (...) groups so top-level arithmetic is visible."""
    out: List[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


_ARITH_RE = re.compile(r"[+\-*/%<>]|[^<>=!]=(?!=)")


def _is_pure_method_chain(rhs: str) -> bool:
    """True if rhs is only `expr.method(...).method(...)` — no top-level
    arithmetic (so the value is the receiver, possibly unwrapped)."""
    return not _ARITH_RE.search(_strip_calls(rhs))


def tag_function_vars(sf: SilexFile, fn: SilexFunction) -> Tuple[Set[str], Set[str]]:
    """Return (caller_vars, balance_vars) for one function body.

    caller_vars  — transitive through pure method chains (.expect/.unwrap):
                   everything that IS the get_caller() address.
    balance_vars — direct only: assigned from `get_balance_for_asset(...)`
                   through pure method chains (.unwrap_or(0) etc.). Derived
                   arithmetic (pro-rata math, balances minus fees...) is
                   deliberately NOT tagged: rule 3 is about transferring the
                   TOTAL balance, not a value computed from it.
    """
    body = sf.masked[fn.body_start:fn.body_end]
    assigns: List[Tuple[str, str]] = []
    for m in ASSIGN_RE.finditer(body):
        var, rhs = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if var in ("if", "for", "while", "return"):
            continue
        assigns.append((var, rhs.strip()))

    caller_vars: Set[str] = set()
    balance_vars: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for var, rhs in assigns:
            if var in caller_vars:
                continue
            if "get_caller(" in rhs:
                caller_vars.add(var)
                changed = True
                continue
            # transitive: rhs is a pure method chain on a caller var
            if _is_pure_method_chain(rhs) and any(
                re.search(rf"\b{re.escape(v)}\b", rhs) for v in caller_vars
            ):
                caller_vars.add(var)
                changed = True
        for var, rhs in assigns:
            if var in balance_vars:
                continue
            if "get_balance_for_asset(" in rhs and _is_pure_method_chain(rhs):
                balance_vars.add(var)
                changed = True
    return caller_vars, balance_vars


# ---------------------------------------------------------------------------
# The lint engine
# ---------------------------------------------------------------------------

class SilexLinter:
    def __init__(self, sf: SilexFile, rel: str):
        self.sf = sf
        self.rel = rel
        self.findings: List[Finding] = []
        self.exemptions: List[Exemption] = []
        self._require_assert_spans: List[Call] = (
            find_calls(sf.masked, "require") + find_calls(sf.masked, "assert")
        )

    # -- helpers -----------------------------------------------------------

    def add(self, rule: str, severity: str, line: int, message: str) -> None:
        self.findings.append(Finding(
            rule=rule, severity=severity, file=self.rel, line=line,
            message=message, snippet=self.sf.line_text(line),
        ))

    def functions(self) -> List[SilexFunction]:
        return self.sf.functions

    def _transfer_calls_in(self, fn: SilexFunction) -> List[Call]:
        out: List[Call] = []
        for name in TRANSFER_FUNCS:
            for c in find_calls(self.sf.masked, name):
                if fn.body_start <= c.start <= fn.body_end:
                    out.append(c)
        return sorted(out, key=lambda c: c.start)

    def _guard_calls_in(self, fn: SilexFunction) -> List[str]:
        """Names of access-guard functions called inside fn's body."""
        private_names = {f.name for f in self.sf.functions if f.kind == "fn"}
        guards = set()
        for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\(", self.sf.masked[fn.body_start:fn.body_end]):
            name = m.group(1)
            if name in private_names and GUARD_FN_RE.match(name):
                guards.add(name)
        return sorted(guards)

    def _has_inline_auth(self, fn: SilexFunction, caller_vars: Set[str]) -> bool:
        """A require(...) that authorizes the caller (compares a
        get_caller()-derived value against something)."""
        for ra in self._require_assert_spans:
            if not (fn.body_start <= ra.start <= fn.body_end):
                continue
            text = self.sf.masked[ra.start:ra.end]
            if "get_caller(" in text:
                return True
            if ("==" in text or "!=" in text) and any(
                re.search(rf"\b{re.escape(v)}\b", text) for v in caller_vars
            ):
                return True
        return False

    # -- R1 + R2: transfer result handling ----------------------------------

    def check_transfers(self) -> None:
        for fn in self.functions():
            for call in self._transfer_calls_in(fn):
                line = self.sf.line_of_offset(call.start)
                var = assigned_var_before(self.sf.masked, call.start)
                if var == "_":
                    self.add(
                        "R1", "BLOCKER", line,
                        f"swallowed transfer failure: `let _ = {call.name}(...)` — "
                        f"the bool result is discarded, a failed transfer cannot "
                        f"revert the entry (audit v12: 91 occurrences)")
                    continue
                if call_is_directly_in(self.sf.masked, call, ("require", "assert")):
                    continue  # require(transfer(...)) / assert(transfer(...))
                if var is not None:
                    # checked iff the var is later passed to require/assert
                    # inside the same function
                    checked = False
                    for ra in self._require_assert_spans:
                        if ra.start > call.start and fn.body_start <= ra.start <= fn.body_end:
                            if re.search(rf"\b{re.escape(var)}\b",
                                         self.sf.masked[ra.start:ra.end]):
                                checked = True
                                break
                    if checked:
                        continue
                    self.add(
                        "R2", "BLOCKER", line,
                        f"fire-and-forget transfer: `{var}` captures the result of "
                        f"{call.name}(...) but is never passed to require/assert — "
                        f"strict policy: check transfers with require({var}, ...) so "
                        f"failure semantics are uniform (if-checks/early returns are "
                        f"not accepted)")
                else:
                    self.add(
                        "R2", "BLOCKER", line,
                        f"fire-and-forget transfer: result of {call.name}(...) is "
                        f"neither captured+checked nor inside require/assert")

    # -- R3: rug switch -----------------------------------------------------

    def check_rug_switch(self) -> None:
        for fn in self.functions():
            if not fn.is_public:
                continue
            # (a) by name — the 2-step emergency-withdraw rug switch audited
            #     ~15x across v12
            if fn.name.startswith("execute_emergency_withdraw"):
                self.add(
                    "R3", "BLOCKER", fn.decl_line,
                    f"rug-switch entry: `{fn.name}` — 2-step emergency withdraw "
                    f"sweeping contract funds to a single role (audit v12 critical "
                    f"pattern, replicated on ~15 contracts)")
            # (b) by shape: transfer(get_caller(), TOTAL balance, ...)
            caller_vars, balance_vars = tag_function_vars(self.sf, fn)
            for call in self._transfer_calls_in(fn):
                args = call_args(self.sf.masked, call)
                if len(args) < 2:
                    continue
                dest, amount = args[0].strip(), args[1].strip()
                dest_is_caller = (
                    dest in caller_vars
                    or "get_caller(" in dest
                    or any(re.search(rf"\b{re.escape(v)}\b", dest) for v in caller_vars)
                )
                amount_is_total_balance = (
                    amount in balance_vars or "get_balance_for_asset(" in amount
                )
                if dest_is_caller and amount_is_total_balance:
                    self.add(
                        "R3", "BLOCKER", self.sf.line_of_offset(call.start),
                        f"rug switch: `{call.name}({dest}, {amount}, ...)` transfers "
                        f"the ENTIRE contract balance (get_balance_for_asset) to "
                        f"get_caller()-derived address `{dest}` in `{fn.name}`")

    # -- R4: unguarded .expect / .unwrap ------------------------------------

    def check_expects(self) -> None:
        for m in re.finditer(r"\.(expect|unwrap)\s*\(", self.sf.masked):
            # `.unwrap_or(` must NOT match: next char after `unwrap` is `_`
            pos = m.start()
            fn = self.sf.function_at_offset(pos)
            line = self.sf.line_of_offset(pos)
            kind = m.group(1)

            # receiver: identifier or balanced (...) expression before the dot
            receiver = self._receiver_before(pos)
            var = None
            if receiver and re.fullmatch(r"[A-Za-z_]\w*", receiver):
                var = receiver

            # guard window: from the start of the 3rd line above, up to
            # this position, clamped to the enclosing function body
            win_start = self.sf.masked.rfind("\n", 0, pos) + 1
            for _ in range(3):
                prev_nl = self.sf.masked.rfind("\n", 0, win_start - 1)
                win_start = prev_nl + 1
            if fn is not None:
                win_start = max(win_start, fn.body_start)
            window = self.sf.masked[win_start:pos]

            guarded = False
            if var is not None:
                if re.search(rf"\b{re.escape(var)}\.(is_some|is_none)\s*\(", window):
                    guarded = True
            elif receiver:
                if re.search(re.escape(receiver) + r"\.(is_some|is_none)\s*\(", window):
                    guarded = True

            if guarded:
                continue
            where = fn.name if fn else "<top level>"
            if fn and fn.is_constructor:
                self.add(
                    "R4", "INFO", line,
                    f".{kind}() in constructor (deployment data, tolerated): "
                    f"{self._snippet_at(pos)}")
            else:
                self.add(
                    "R4", "BLOCKER", line,
                    f"unguarded .{kind}() on `{receiver or '?'}` in `{where}` — no "
                    f"require/is_some check on the optional in the 3 preceding "
                    f"lines; a None value panics and can brick the entry (DoS, "
                    f"audit v12: dangling MINER_LIST .expect)")

    def _receiver_before(self, dot_pos: int) -> Optional[str]:
        """Identifier or balanced-paren expression ending right before pos."""
        masked = self.sf.masked
        i = dot_pos - 1
        if i < 0:
            return None
        if masked[i] == ")":
            depth = 0
            j = i
            while j >= 0:
                if masked[j] == ")":
                    depth += 1
                elif masked[j] == "(":
                    depth -= 1
                    if depth == 0:
                        break
                j -= 1
            if j < 0:
                return None
            # include a preceding identifier (e.g. `Contract::new` or `s.load`)
            k = j - 1
            while k >= 0 and (masked[k].isalnum() or masked[k] in "_:"):
                k -= 1
            return masked[k + 1:i + 1]
        j = i
        while j >= 0 and (masked[j].isalnum() or masked[j] == "_"):
            j -= 1
        if j == i:
            return None
        return masked[j + 1:i + 1]

    def _snippet_at(self, pos: int) -> str:
        line = self.sf.line_of_offset(pos)
        return self.sf.line_text(line)

    # -- R5: 68-hex literals -------------------------------------------------

    def check_hex_literals(self) -> None:
        # string literals only (real code data, not comments)
        for (start, end, content) in self.sf.strings:
            for m in re.finditer(r"(?<![0-9a-fA-F])[0-9a-fA-F]{68}(?![0-9a-fA-F])", content):
                line = self.sf.line_of_offset(start + m.start())
                self.add(
                    "R5", "ERROR", line,
                    f"68-hex-char literal ({m.group(0)[:16]}…): 34 bytes instead of "
                    f"32 — XELIS Hash/Address are 64 hex chars; wrong-padded "
                    f"address literal (audit v12: Address::from_bytes panics in "
                    f"OracleGovernance propose_*)")

    # -- R6: Hash::zero() fallback used for transfers/calls -----------------

    def check_zero_fallback(self) -> None:
        for m in re.finditer(r"\.unwrap_or\s*\(\s*Hash::zero\s*\(\s*\)\s*\)", self.sf.masked):
            pos = m.start()
            line = self.sf.line_of_offset(pos)
            fn = self.sf.function_at_offset(pos)
            if fn is None:
                continue
            # var assigned from this fallback: the `.unwrap_or(Hash::zero())`
            # usually TERMINATES the RHS (`let v: Hash = s.load(K).unwrap…`),
            # so scan the line prefix for the last assignment starter
            line_begin = self.sf.masked.rfind("\n", 0, pos) + 1
            prefix = self.sf.masked[line_begin:pos]
            lets = re.findall(r"(?:let|var)\s+([A-Za-z_]\w*)\s*(?::[^=]*)?\s*=", prefix)
            var = lets[-1] if lets else None

            # dangerous sinks inside the same function: the three transfer
            # variants and Contract::new(...)
            body = self.sf.masked[fn.body_start:fn.body_end]
            rel_pos = pos - fn.body_start
            sinks: List[Tuple[int, int, str]] = []
            for name in TRANSFER_FUNCS:
                for c in find_calls(body, name):
                    sinks.append((c.start, c.end, f"{name}(...)"))
            for cm in re.finditer(r"Contract\s*::\s*new\s*\(", body):
                open_idx = body.find("(", cm.start())
                sinks.append((cm.start(), _match_paren(body, open_idx),
                              "Contract::new(...)"))

            usage = None
            if var:
                for (s, e, label) in sinks:
                    if re.search(rf"\b{re.escape(var)}\b", body[s:e]):
                        usage = label
                        break
            if usage is None:
                # the fallback expression itself sits inside a sink call
                for (s, e, label) in sinks:
                    if s <= rel_pos <= e:
                        usage = label
                        break
            if usage:
                self.add(
                    "R6", "ERROR", line,
                    f"unwrap_or(Hash::zero()) used as safety fallback of {usage}"
                    f"{' for `' + var + '`' if var else ''} — a zero hash is NOT a "
                    f"safe transfer destination/asset (audit v12: stake_relayer_bond "
                    f"bonding in XEL when VLT_ASSET was unset)")

    # -- R7: unguarded public entries that write ------------------------------

    def check_unguarded_entries(self) -> None:
        stem = self.sf.path.stem
        seen_allowlist: Set[str] = set()
        for fn in self.functions():
            if not fn.is_public:
                continue
            body = self.sf.masked[fn.body_start:fn.body_end]
            if not re.search(r"\bstore\s*\(", body):
                continue  # views / pure getters are fine (spec)
            key = (stem, fn.name)
            if key in PUBLIC_BY_DESIGN:
                reason = PUBLIC_BY_DESIGN[key]
                self.exemptions.append(Exemption(stem, fn.name, reason))
                seen_allowlist.add(fn.name)
                continue
            caller_vars, _ = tag_function_vars(self.sf, fn)
            if self._guard_calls_in(fn):
                continue  # funnelled through only_owner/only_admin/...
            if self._has_inline_auth(fn, caller_vars):
                continue  # require(caller == <stored value>) style
            if "get_deposit_for_asset(" in body:
                continue  # payable-style user entry: it collects the user's funds
            self.add(
                "R7", "WARNING", fn.decl_line,
                f"public `{fn.kind.replace('_', ' ')}` `{fn.name}` writes storage "
                f"with no access guard and no caller authorization — potentially "
                f"an unprotected admin entry (audit v12: update_channel_meta)")
        # stale allowlist entries keep the exemption list honest
        for (c_stem, entry), reason in PUBLIC_BY_DESIGN.items():
            if c_stem == stem and entry not in seen_allowlist \
                    and self.sf.function_by_name(entry) is None:
                self.add(
                    "R7", "INFO", 1,
                    f"stale PUBLIC_BY_DESIGN allowlist entry `{entry}` — function "
                    f"not found in this contract; remove it from lint_silex.py")

    # -- R8: unbounded loops ---------------------------------------------------

    def check_loops(self) -> None:
        consts = set(self.sf.consts.keys())
        for fn in self.functions():
            body = self.sf.masked[fn.body_start:fn.body_end]

            # C-style: for i: u32 = 0; i < BOUND; i += 1
            for m in re.finditer(
                    r"\bfor\s+(\w+)\s*:\s*\w+\s*=\s*[^;]+;\s*(.+?);", body):
                self._check_loop_bound(m.group(2), consts, fn,
                                       self.sf.line_of_offset(fn.body_start + m.start()),
                                       "for")
            # while COND
            for m in re.finditer(r"\bwhile\s+([^{]+)", body):
                self._check_loop_bound(m.group(1).strip(), consts, fn,
                                       self.sf.line_of_offset(fn.body_start + m.start()),
                                       "while")
            # for-in (future-proofing)
            for m in re.finditer(r"\bfor\s+\w+\s+in\s+([^{]+)", body):
                coll = m.group(1).strip()
                if ".load(" in coll:
                    self.add(
                        "R8", "WARNING",
                        self.sf.line_of_offset(fn.body_start + m.start()),
                        f"for-in loop iterates over storage-loaded collection "
                        f"`{coll}` with no static cap in `{fn.name}`")

    def _check_loop_bound(self, cond: str, consts: Set[str], fn: SilexFunction,
                          line: int, style: str) -> None:
        cond = cond.strip()
        m = re.match(r"^(\w+)\s*(<=|>=|<|>)\s*(.+)$", cond)
        if m:
            bound = m.group(3).strip()
            if bound in consts or re.fullmatch(r"\d+(u8|u16|u32|u64|u128)?", bound):
                return  # statically bounded
            self.add(
                "R8", "WARNING", line,
                f"{style} loop in `{fn.name}` is bounded by runtime value "
                f"`{bound}` (not a const/numeric) — no static iteration cap "
                f"(audit v12: storage-iterating loops)")
            return
        # non-comparison condition or unknown shape -> flag unless a const
        # appears in it
        if any(re.search(rf"\b{re.escape(c)}\b", cond) for c in consts):
            return
        self.add(
            "R8", "WARNING", line,
            f"{style} loop in `{fn.name}` has no obvious static bound "
            f"(condition `{cond[:60]}`)")

    # -- R9: stale function-number comments ------------------------------------

    NUMBERED_RE = re.compile(r"^\s*//\s*(\d+(?:\s*[/,-]\s*\d+)+|\d+)\s*\.(?=\s|\S)")
    ID_COMMENT_RE = re.compile(
        r"^\s*//.*?(?:\bID\s+(\d+)\s*:\s*(\w+)|\(?\bchunk\s+(\d+)\s*\)?\s*:\s*(\w+)|"
        r"\bENTRY\s+\d+\s*\(?\s*chunk\s+(\d+)\s*\)?\s*:\s*(\w+))")

    def _comment_block(self, lines: List[str], idx: int) -> Tuple[int, int]:
        """(first, last) line of the contiguous // comment block around idx."""
        is_comment = lambda t: t.lstrip().startswith("//")
        first = idx
        while first > 1 and is_comment(lines[first - 2]):
            first -= 1
        last = idx
        while last < len(lines) and is_comment(lines[last]):
            last += 1
        return (first, last)

    def _is_function_banner(self, lines: List[str], idx: int) -> bool:
        """True if the comment at idx sits in a comment block that directly
        precedes a function declaration (<= 5 lines gap). Doc lists in the
        big header (security model, usage guidance...) are NOT banners."""
        first, last = self._comment_block(lines, idx)
        nxt = self.sf.next_function_after_line(idx)
        if nxt is None:
            return False
        return last < nxt.decl_line and (nxt.decl_line - last) <= 5

    def check_stale_comments(self) -> None:
        lines = self.sf.src.splitlines()

        for idx, text in enumerate(lines, start=1):
            inside_fn = any(f.covers_line(idx) and f.decl_line < idx for f in self.sf.functions)
            if inside_fn:
                continue  # step-numbered comments inside bodies are not chunk ids
            if not text.lstrip().startswith("//"):
                continue
            if not self._is_function_banner(lines, idx):
                continue

            m = self.NUMBERED_RE.match(text)
            if m:
                # only unambiguous banners: exactly ONE numbered line in the
                # block (a block with several numbered lines cannot be
                # attributed reliably — skipped to avoid false positives)
                first, last = self._comment_block(lines, idx)
                numbered_in_block = [
                    l for l in range(first, last + 1)
                    if self.NUMBERED_RE.match(lines[l - 1])
                ]
                if len(numbered_in_block) != 1:
                    continue
                numbers = [int(x) for x in re.findall(r"\d+", m.group(1))]
                self._verify_number_comment(numbers, idx, text)
                continue
            m = self.ID_COMMENT_RE.match(text)
            if m:
                cid = next(g for g in (m.group(1), m.group(3), m.group(5)) if g)
                name = next(g for g in (m.group(2), m.group(4), m.group(6)) if g)
                fn = self.sf.function_by_name(name)
                if fn is None:
                    continue  # not a function we know (e.g. event name)
                actual = self.sf.chunk_index(fn)
                if actual != int(cid):
                    self.add(
                        "R9", "INFO", idx,
                        f"stale chunk-id comment: says `{name}` is chunk {cid} but "
                        f"declaration order makes it chunk {actual}")

    def _verify_number_comment(self, numbers: List[int], line: int, text: str) -> None:
        following: List[SilexFunction] = []
        for f in self.sf.functions:
            if f.decl_line > line:
                following.append(f)
        if not following:
            return
        for i, num in enumerate(numbers):
            if i >= len(following):
                break
            actual = self.sf.chunk_index(following[i])
            if num != actual:
                expected = "/".join(
                    str(self.sf.chunk_index(following[j]))
                    for j in range(min(len(numbers), len(following))))
                self.add(
                    "R9", "INFO", line,
                    f"stale function-number comment `{text.strip()[:60]}` — "
                    f"documents chunk {num} for `{following[i].name}` but its real "
                    f"chunk (declaration order) is {actual} "
                    f"(expected sequence: {expected})")
                return

    # -- R10: dead private functions -------------------------------------------

    def check_dead_code(self) -> None:
        for fn in self.sf.functions:
            if fn.kind != "fn":
                continue  # entries and pub fns are public API by definition
            uses = len(re.findall(rf"\b{re.escape(fn.name)}\b", self.sf.masked))
            if uses <= 1:
                self.add(
                    "R10", "INFO", fn.decl_line,
                    f"dead code: private fn `{fn.name}` is never called in this "
                    f"file (name occurs only at its declaration)")

    # -- run everything ----------------------------------------------------------

    def check_deposit_addr_leak(self) -> None:
        """R11 — a public deposit entry must never take an Address param.

        XELIS invoke parameters are public. A mixer deposit that names the
        payout recipient in its parameters leaks the depositor->recipient
        link at deposit time, defeating the whole purpose of the pool
        (the exact flaw shipped in PrivacyMixer V4). Deposits must carry
        ONLY a client-side commitment hash.
        """
        for fn in self.functions():
            if fn.kind != "entry" or not fn.name.startswith("deposit"):
                continue
            signature = self.sf.src[fn.decl_start:fn.body_start]
            if re.search(r"\bAddress\b", signature):
                self.add("R11-deposit-addr-leak", "BLOCKER", fn.decl_line,
                         f"entry `{fn.name}` takes an Address parameter: the "
                         f"recipient would leak in plaintext invoke params "
                         f"at deposit time (PrivacyMixer V4 flaw) — accept a "
                         f"client-computed commitment hash instead")

    def run(self) -> List[Finding]:
        self.check_transfers()
        self.check_rug_switch()
        self.check_expects()
        self.check_hex_literals()
        self.check_zero_fallback()
        self.check_unguarded_entries()
        self.check_loops()
        self.check_stale_comments()
        self.check_dead_code()
        self.check_deposit_addr_leak()
        self.findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.line, f.rule))
        return self.findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _severity_tag(sev: str) -> str:
    if sev == "BLOCKER":
        return "[BLOCKER]"
    if sev == "ERROR":
        return "[ERROR]  "
    if sev == "WARNING":
        return "[WARNING]"
    return "[INFO]   "


def print_report(results: List[dict], mode: str) -> None:
    print("=" * 78)
    print(f" Silex strict linter v{VERSION} — XelisVault CI  (mode: {mode})")
    print(" Patterns from the v12 security audit — BLOCKER/ERROR fail the build")
    print("=" * 78)

    total = {"BLOCKER": 0, "ERROR": 0, "WARNING": 0, "INFO": 0}
    for res in results:
        rel = res["rel"]
        lines = res["sf"].src.count("\n") + 1
        print(f"\n{rel}  ({lines} lines)")
        if not res["findings"] and not res["exemptions"]:
            print("  CLEAN — no findings")
        for f in res["findings"]:
            total[f.severity] += 1
            print(f"  {_severity_tag(f.severity)} {f.rule:<4} L{f.line:<5} {f.message}")
            if f.snippet:
                print(f"           | {f.snippet[:90]}")
        for ex in res["exemptions"]:
            print(f"  [EXEMPT] R7   {ex.entry}: public-by-design — {ex.reason}")

    print("\n" + "-" * 78)
    status = "PASS" if (total["BLOCKER"] == 0 and total["ERROR"] == 0) else "FAIL"
    print(f" Files: {len(results)}  |  BLOCKER: {total['BLOCKER']}  ERROR: {total['ERROR']}"
          f"  WARNING: {total['WARNING']}  INFO: {total['INFO']}")
    print(f" Result: {status}")
    print("=" * 78)


def build_json(results: List[dict], mode: str, exit_code: int) -> dict:
    findings = []
    exemptions = []
    total = {"BLOCKER": 0, "ERROR": 0, "WARNING": 0, "INFO": 0}
    for res in results:
        for f in res["findings"]:
            total[f.severity] += 1
            findings.append(asdict(f))
        for ex in res["exemptions"]:
            exemptions.append(asdict(ex))
    return {
        "tool": "lint_silex",
        "version": VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode": mode,
        "files_scanned": [res["rel"] for res in results],
        "findings": findings,
        "exemptions_applied": exemptions,
        "summary": {"counts": total, "result": "PASS" if exit_code == 0 else "FAIL"},
        "exit_code": exit_code,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def collect_slx(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*.slx")
                  if "legacy" not in p.relative_to(root).parts
                  and "superseded" not in p.relative_to(root).parts)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Strict Silex linter (XelisVault CI)")
    ap.add_argument("--contracts", type=Path, default=REPO_ROOT / "contracts",
                    help="directory to lint (default: <repo>/contracts; anything "
                         "under a legacy/ subdir is skipped)")
    ap.add_argument("--scan-legacy", type=Path, default=None, metavar="PATH",
                    help="VALIDATION MODE: run all rules on known-bad v12 code "
                         "(file or directory). Not used by CI — proves the linter "
                         "still catches the audited bugs.")
    ap.add_argument("--json", type=Path, default=None,
                    help="write the JSON report to this path")
    args = ap.parse_args(argv)

    if args.scan_legacy is not None:
        target = args.scan_legacy.resolve()
        if target.is_file():
            files = [target]
        else:
            files = sorted(target.rglob("*.slx"))
        base = target.parent if target.is_file() else target
        mode = "scan-legacy"
    else:
        base = args.contracts.resolve()
        if not base.is_dir():
            print(f"error: contracts directory not found: {base}", file=sys.stderr)
            return 2
        files = collect_slx(base)
        mode = "contracts"

    if not files:
        print(f"error: no .slx files found under {base}", file=sys.stderr)
        return 2

    results: List[dict] = []
    for path in files:
        sf = SilexFile.parse(path)
        rel = str(path.relative_to(base))
        linter = SilexLinter(sf, rel)
        findings = linter.run()
        results.append({"sf": sf, "rel": rel, "findings": findings,
                        "exemptions": linter.exemptions})

    print_report(results, mode)

    blockers = sum(1 for r in results for f in r["findings"]
                   if f.severity in ("BLOCKER", "ERROR"))
    exit_code = 0 if blockers == 0 else 1

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(build_json(results, mode, exit_code),
                                        indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
