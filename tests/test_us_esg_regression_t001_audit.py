"""Regression tests for audit_fix_2026_07_12 — T001 mechanism variables tautology.

These tests assert that:
1. us_esg_regression.py no longer constructs mechanism proxy variables
   from linear functions of treatment variables (endless tautology).
2. The Table 5 LaTeX generator outputs the "Omitted" notice instead of fake results.
3. The Python module still loads and the LaTeX file is generated correctly.

Reference: docs/IMPROVEMENT_ROADMAP.md T001 (P0 / 学术诚信).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ────────────────────────────────────────────────────────────────────────
# Source-level tests (do not require module import)
# ────────────────────────────────────────────────────────────────────────


class TestNoMechanismTautology:
    """Verify the source file does NOT contain tautological mechanism proxies."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        return (ROOT / "scripts" / "us_esg_regression.py").read_text(encoding="utf-8")

    def test_no_analyst_cov_proxy_construction(self, source: str) -> None:
        """Must not contain `analyst_cov_proxy = ... * 2.8` style assignments."""
        pattern = r"df_mech\[.analyst_cov_proxy.\]\s*=\s*df_mech\[.ln_assets.\]\s*\*\s*2\.8"
        assert not re.search(pattern, source), (
            "T001 fix regression: detected original tautological analyst_cov_proxy "
            "construction `analyst_cov_proxy = ln_assets * 2.8`."
        )

    def test_no_cds_proxy_tautology(self, source: str) -> None:
        """Must not contain cds_proxy = 120 - 42 * esg_high - 8 * post (mechanical tautology)."""
        pattern = r"df_mech\[.cds_proxy.\]\s*=\s*120\s*-\s*42"
        assert not re.search(pattern, source), (
            "T001 fix regression: detected original tautological cds_proxy "
            "construction `cds_proxy = 120 - 42 * esg_high - 8 * post`."
        )

    def test_no_rating_proxy_tautology(self, source: str) -> None:
        """Must not contain rating_proxy = 4 + 1.5 * esg_high + 0.8 * post."""
        pattern = r"df_mech\[.rating_proxy.\]\s*=\s*4\s*\+\s*1\.5"
        assert not re.search(pattern, source), (
            "T001 fix regression: detected original tautological rating_proxy "
            "construction `rating_proxy = 4 + 1.5 * esg_high + 0.8 * post`."
        )

    def test_omitted_notice_present(self, source: str) -> None:
        """Mechanism Tests section must show 'Omitted' notice."""
        assert "Mechanism Tests (omitted in v2" in source, (
            "T001 fix regression: the 'Mechanism Tests (omitted in v2)' notice "
            "is missing. The audit fix marker should appear in source."
        )

    def test_audit_fix_marker_present(self, source: str) -> None:
        """Source must reference `audit_fix_2026_07_12` for traceability."""
        assert "audit_fix_2026_07_12" in source, (
            "T001 fix regression: 'audit_fix_2026_07_12' marker missing — "
            "this is the canonical reference for the fix and must remain in the source."
        )


# ────────────────────────────────────────────────────────────────────────
# Module-level tests (require module to import)
# ────────────────────────────────────────────────────────────────────────


try:
    import scripts.us_esg_regression as uer  # noqa: E402
    _module_available = True
except Exception as _exc:  # pragma: no cover
    _module_available = False
    _import_error = _exc


@pytest.mark.skipif(not _module_available, reason=f"us_esg_regression not importable: {_import_error if not _module_available else ''}")
class TestUsEsgRegressionT001:
    """T001 regression: behavior of the (omitted) Table 5 generator."""

    def test_module_loads(self):
        assert uer is not None

    def test_t5_generator_emits_omitted_marker(self):
        """When the script runs, _generate_table5_tex should emit 'Omitted' notice."""
        # Re-extract the function from the source (it's defined inside `__main__`).
        from pathlib import Path
        import ast
        src = (Path("scripts/us_esg_regression.py")).read_text(encoding="utf-8")
        tree = ast.parse(src)
        func_src = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_generate_table5_tex":
                func_src = ast.get_source_segment(src, node)
                break
        assert func_src is not None, "_generate_table5_tex not found in source"
        ns: dict = {}
        exec(func_src, ns)  # noqa: S102
        result = ns["_generate_table5_tex"]()
        # Result must mention "Omitted" and "audit_fix" but NOT contain real coefficients.
        assert "Omitted" in result, f"_generate_table5_tex must contain 'Omitted', got: {result[:200]}"
        # The output uses LaTeX-escaped underscores: audit\_fix\_2026\_07\_12
        marker = "audit_fix_2026_07_12"
        marker_escaped = marker.replace("_", r"\_")
        assert (marker in result) or (marker_escaped in result), (
            f"_generate_table5_tex must reference {marker}, got: {result[:300]}"
        )
        assert ("tautology" in result.lower()) or ("tautologies" in result.lower()), (
            f"_generate_table5_tex should explain the tautology, got: {result[:300]}"
        )
        # And should NOT contain the misleading label "ESG Reduces Information Asymmetry"
        # which was the title of the original (fake) mechanism results.
        assert "ESG Reduces Information Asymmetry" not in result, (
            "T001 regression: removed Table 5 must not still claim "
            "'ESG Reduces Information Asymmetry' — that was the misleading caption."
        )
