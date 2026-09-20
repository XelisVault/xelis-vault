"""Linter rule regression tests — pins the detection power of the CI itself.

The founder's requirement is "zero false negatives on the audited patterns,
zero blocking false positives on the mixer". The mixer side is checked by
running the real linter on contracts/mixer/PrivacyMixerV4.slx (it must stay
free of BLOCKER/ERROR/WARNING). This file pins the other side: a synthetic
contract containing ONE instance of every audited dangerous pattern must
trigger the matching rule, and the linter must exit non-zero.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINTER = REPO_ROOT / "scripts" / "lint_silex.py"
V4 = REPO_ROOT / "contracts" / "mixer" / "PrivacyMixerV4.slx"

BAD_CONTRACT = """\
// Bad.slx — synthetic contract covering every audit pattern
// CHUNK TABLE (test)
// 0 constructor  1 deposit  2 sweep
const MAX: u64 = 10

hook constructor() -> u64 {
    let s: Storage = Storage::new()
    return 0
}

// 9. deposit — number deliberately wrong (deposit is chunk 1)
entry deposit(to: Address) -> u64 {
    let s: Storage = Storage::new()
    let bal: u64 = get_balance_for_asset(get_xelis_asset()).unwrap_or(0)
    let caller: Address = get_caller().expect("err")
    s.store("k", 1u64)
    let _ = transfer(to, 100, get_xelis_asset())
    transfer(caller, bal, get_xelis_asset())
    let ok: bool = transfer(to, 5, get_xelis_asset())
    let vlt: Hash = s.load("vlt").unwrap_or(Hash::zero())
    let ok2: bool = transfer(to, 7, vlt)
    require(ok2, "txfail")
    let zero: Hash = Hash::blake3(bytes::from_hex("00000000000000000000000000000000000000000000000000000000000000000000"))
    let i: u64 = 0
    while i < s.load("n").unwrap_or(0) {
        i += 1
    }
    return 0
}

entry sweep() -> u64 {
    let s: Storage = Storage::new()
    s.store("swept", true)
    return 0
}

fn never_called() -> u64 {
    return 42
}
"""


def run_linter(target: Path):
    proc = subprocess.run(
        [sys.executable, str(LINTER), "--contracts", str(target)],
        capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


class TestLinterCatchesAuditPatterns(unittest.TestCase):
    """One instance of every audited pattern -> the matching rule fires."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "Bad.slx").write_text(BAD_CONTRACT, encoding="utf-8")
        self.code, self.out = run_linter(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exit_code_nonzero(self):
        self.assertEqual(self.code, 1, "BLOCKER/ERROR findings must exit 1")

    def test_all_ten_rules_fire(self):
        for rule in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10"]:
            self.assertIn(rule, self.out, f"rule {rule} did not fire on its pattern")

    def test_severities(self):
        # audited patterns are BLOCKER/ERROR, structural ones WARNING/INFO
        for rule, sev in [("R1", "BLOCKER"), ("R2", "BLOCKER"), ("R3", "BLOCKER"),
                          ("R4", "BLOCKER"), ("R5", "ERROR"), ("R6", "ERROR"),
                          ("R7", "WARNING"), ("R8", "WARNING"),
                          ("R9", "INFO"), ("R10", "INFO")]:
            self.assertIn(f"[{sev}", self.out, f"{rule} must be {sev}")


class TestMixerV4StaysClean(unittest.TestCase):
    """The active contract must never gain a blocking/warning finding."""

    def test_v4_has_no_blocker_error_or_warning(self):
        self.assertTrue(V4.is_file(), "contracts/mixer/PrivacyMixerV4.slx missing")
        code, out = run_linter(V4.parent.parent)
        self.assertEqual(code, 0, f"linter must pass on V4:\n{out}")
        for line in out.splitlines():
            self.assertNotIn("[BLOCKER]", line)
            self.assertNotIn("[ERROR]", line)
            self.assertNotIn("[WARNING]", line)


if __name__ == "__main__":
    unittest.main()
