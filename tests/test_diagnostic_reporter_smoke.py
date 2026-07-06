"""tests/test_diagnostic_reporter_smoke.py — Smoke tests for scripts/research_framework/diagnostic_reporter.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.diagnostic_reporter import (
        DiagnosticDecision,
        DiagnosticCheck,
        DiagnosticReport,
        DiagnosticReporter,
    )
except Exception as _exc:
    pytest.skip(f"diagnostic_reporter not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert DiagnosticReporter is not None
        assert DiagnosticDecision is not None

    def test_decision_values(self):
        assert DiagnosticDecision.PASS.value == "PASS"
        assert DiagnosticDecision.WARN.value == "WARN"
        assert DiagnosticDecision.FAIL.value == "FAIL"


class TestDiagnosticCheck:
    def test_instantiate(self):
        c = DiagnosticCheck(
            name="vif_size",
            name_zh="VIF检验-规模",
            category="A",
            decision=DiagnosticDecision.PASS,
            value=2.5,
            threshold="<5",
            pval=0.5,
        )
        assert c.name == "vif_size"
        assert c.decision == DiagnosticDecision.PASS

    def test_to_dict(self):
        c = DiagnosticCheck(
            name="x", name_zh="X", category="A",
            decision=DiagnosticDecision.WARN, value=1.0, threshold="<5",
        )
        d = c.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == "WARN"


class TestDiagnosticReport:
    def _make_checks(self, n_pass=1, n_warn=0, n_fail=0):
        checks = []
        for i in range(n_pass):
            checks.append(DiagnosticCheck(
                name=f"pass_{i}", name_zh=f"通过{i}", category="A",
                decision=DiagnosticDecision.PASS, value=1.0, threshold="<5",
            ))
        for i in range(n_warn):
            checks.append(DiagnosticCheck(
                name=f"warn_{i}", name_zh=f"警告{i}", category="A",
                decision=DiagnosticDecision.WARN, value=7.0, threshold="5-10",
            ))
        for i in range(n_fail):
            checks.append(DiagnosticCheck(
                name=f"fail_{i}", name_zh=f"失败{i}", category="A",
                decision=DiagnosticDecision.FAIL, value=15.0, threshold=">10",
            ))
        return checks

    def test_empty_overall_pass(self):
        report = DiagnosticReport()
        assert report.overall == DiagnosticDecision.PASS
        assert report.n_pass == 0

    def test_overall_warn(self):
        report = DiagnosticReport(checks=self._make_checks(n_warn=1))
        assert report.overall == DiagnosticDecision.WARN
        assert report.n_warn == 1

    def test_overall_fail(self):
        report = DiagnosticReport(checks=self._make_checks(n_pass=2, n_fail=1))
        assert report.overall == DiagnosticDecision.FAIL
        assert report.n_pass == 2
        assert report.n_fail == 1

    def test_to_dataframe(self):
        report = DiagnosticReport(checks=self._make_checks(n_pass=2, n_warn=1))
        df = report.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_summary_text(self):
        report = DiagnosticReport(checks=self._make_checks(n_pass=1))
        txt = report.summary_text()
        assert "诊断报告" in txt
        assert "PASS" in txt


class TestDiagnosticReporter:
    def test_builder_pattern(self):
        rep = DiagnosticReporter(model_name="test_model")
        rep.add_check(
            name="vif_x", name_zh="X", category="A",
            value=2.5, threshold="<5",
        )
        report = rep.generate()
        assert len(report.checks) == 1
        assert report.metadata["model"] == "test_model"

    def test_add_vif(self):
        rep = DiagnosticReporter()
        rep.add_vif({"size": 2.5, "leverage": 7.5, "roa": 15.0})
        report = rep.generate()
        assert len(report.checks) == 3
        # leverage (7.5) → WARN, roa (15.0) → FAIL
        assert report.checks[0].decision == DiagnosticDecision.PASS
        assert report.checks[1].decision == DiagnosticDecision.WARN
        assert report.checks[2].decision == DiagnosticDecision.FAIL

    def test_add_parallel_trends_pass(self):
        rep = DiagnosticReporter()
        rep.add_parallel_trends(f_stat=1.5, pval=0.3)
        report = rep.generate()
        assert report.checks[0].decision == DiagnosticDecision.PASS

    def test_add_parallel_trends_fail(self):
        rep = DiagnosticReporter()
        rep.add_parallel_trends(f_stat=10.0, pval=0.001)
        report = rep.generate()
        assert report.checks[0].decision == DiagnosticDecision.FAIL
