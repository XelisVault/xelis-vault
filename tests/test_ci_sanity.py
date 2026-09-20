"""CI sanity placeholder — guarantees the pytest job always has work.

The functional test-suite will be extended by the project lead; until then
this file keeps `pytest tests/` meaningful (a CI job that silently runs zero
tests is worse than no job). It pins the two structural facts the whole CI
depends on: the active contract exists and is a real, substantial file.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
V5 = REPO_ROOT / "contracts" / "mixer" / "PrivacyMixerV5.slx"


def test_active_contract_exists():
    """contracts/mixer/PrivacyMixerV5.slx must exist (the only active contract)."""
    assert V5.is_file(), f"missing active contract: {V5}"


def test_active_contract_is_substantial():
    """The mixer must be a real contract (>500 lines), not a stub."""
    assert V5.is_file(), f"missing active contract: {V5}"
    lines = V5.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 500, (
        f"PrivacyMixerV5.slx has only {len(lines)} lines — expected >500 "
        f"(a shrunk/stubbed mixer is a red flag)"
    )


def test_active_contract_documents_its_chunk_table():
    """The header must document the CHUNK TABLE (checked in depth by
    scripts/verify_chunk_ids.py — this is the cheap canary)."""
    assert V5.is_file(), f"missing active contract: {V5}"
    text = V5.read_text(encoding="utf-8")
    assert "CHUNK TABLE" in text, "PrivacyMixerV5.slx header must document its CHUNK TABLE"
