"""Tests for scripts/audit_guard.py — defensive guards against audit
hallucinations and CI workflow bugs.

These tests live separately from the audit guard itself so the guard can
fail loudly during development without breaking test collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
    import yaml

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
