"""Tests for scripts/audit_guard.py — defensive guards against audit
hallucinations and CI workflow bugs.

These tests live separately from the audit guard itself so the guard can
fail loudly during development without breaking test collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# scripts/ is not a package; import audit_guard as a standalone module.
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "audit_guard", ROOT / "scripts" / "audit_guard.py"
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_guard"] = _mod
_spec.loader.exec_module(_mod)

AuditCheck = _mod.AuditCheck
CHECKS = _mod.CHECKS


def test_audit_guard_has_check_13():
    """PR-4 added check 13 to prevent silent ci.yml parse failures (PR-3 and
    PR-4 both shipped YAML `name:` strings containing unquoted colons)."""
    ids = {c.id for c in CHECKS}
    assert 13 in ids, f"expected check 13 in {sorted(ids)}"


def test_check_13_describes_yaml_unquoted_colon_bug():
    """check 13's description must mention the bug class it's catching."""
    chk = next(c for c in CHECKS if c.id == 13)
    assert "colon" in chk.description.lower() or "yaml" in chk.description.lower()


def test_check_13_actually_runs_against_workspace():
    """Run check 13 — it must return a passed result against the current
    .github/workflows/*.yml files (no unquoted colon `name:` lines)."""
    fn = next(c for c in CHECKS if c.id == 13).run
    result = fn()
    assert result.passed, (
        f"check 13 failed: {result.actual} (expected {result.expected}); "
        f"evidence:\n" + "\n".join(result.evidence)
    )


def test_check_13_uses_pyyaml_for_validation():
    """Defense in depth: check 13 should not silently skip parsing."""
    import inspect

    fn = next(c for c in CHECKS if c.id == 13).run
    src = inspect.getsource(fn)
    assert "yaml.safe_load" in src or "yaml_load" in src


def test_check_13_detects_unquoted_name_with_colon(tmp_path: Path):
    """If we feed a fake workflow with an unquoted `name: a: b`, the heuristic
    should flag it.

    Note: This is a synthetic test that goes outside the standard check_13
    function (which is hardcoded to scan .github/). We replicate the logic
    inline so we can inject bad YAML.
    """

    fake_wf = tmp_path / "fake.yml"
    fake_wf.write_text(
        "- name: foo\n"
        "  uses: bar\n"
        "- name: bad: name with colon\n"   # unquoted colon = bug
        "  uses: bar\n"
    )

    # Replicate check_13's unquoted-colon scan.
    issues = []
    for i, line in enumerate(fake_wf.read_text().splitlines(), 1):
        s = line.lstrip()
        if not s.startswith("- name:") and not s.startswith("name:"):
            continue
        val = s.split("name:", 1)[1].lstrip()
        if val and not val.startswith(('"', "'")):
            if ":" in val:
                issues.append((i, s))

    assert len(issues) >= 1, "synthetic YAML with unquoted colon should be detected"
    assert any("bad: name" in s for _i, s in issues), (
        "should flag the specific bad line"
    )


def test_check_13_passes_well_quoted_yaml(tmp_path: Path):
    """`name: "foo: bar"` (quoted) must NOT be flagged."""
    fake_wf = tmp_path / "good.yml"
    fake_wf.write_text(
        '- name: "foo: bar"\n'
        "  uses: bar\n"
    )
    issues = []
    for i, line in enumerate(fake_wf.read_text().splitlines(), 1):
        s = line.lstrip()
        if not s.startswith("- name:") and not s.startswith("name:"):
            continue
        val = s.split("name:", 1)[1].lstrip()
        if val and not val.startswith(('"', "'")):
            if ":" in val:
                issues.append((i, s))
    assert issues == [], f"quoted name must not be flagged; got {issues}"


def test_audit_guard_has_check_14():
    ids = {c.id for c in CHECKS}
    assert 14 in ids, f"expected check 14 (diff-in-diff2 phantom dep) in {sorted(ids)}"


def test_audit_guard_has_check_15():
    ids = {c.id for c in CHECKS}
    assert 15 in ids, f"expected check 15 (PyPI deps existence) in {sorted(ids)}"


def test_check_14_passes_after_phantom_dep_removal():
    """After removing diff-in-diff2 from active install lines, check 14 should
    pass (it only counts uncommented install refs)."""
    fn = next(c for c in CHECKS if c.id == 14).run
    result = fn()
    assert result.passed, f"check 14 should pass: {result.actual}\n" + "\n".join(result.evidence)


def _is_pypi_reachable() -> bool:
    """Pre-flight check for PyPI connectivity using subprocess (avoids urllib hanging)."""
    import subprocess
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "4", "https://pypi.org/simple/"],
            capture_output=True, timeout=6,
        )
        return r.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(
    not _is_pypi_reachable(),
    reason="PyPI unreachable — test requires live network to check deps",
)
def test_check_15_handles_network_failure_gracefully():
    """Check 15: verify it gracefully handles a PyPI dep lookup.

    This test requires live network access to actually exercise the HTTP
    logic in check_15_pypi_deps_exist. When PyPI is unreachable it is
    skipped (not failed) via the skipif above.
    """
    fn = next(c for c in CHECKS if c.id == 15).run
    result = fn()
    assert result.passed, f"check 15 should pass: {result.actual}\n" + "\n".join(result.evidence)
