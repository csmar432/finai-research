"""Unit tests for scripts/core/debate_calibrator_bridge.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def dcb():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import debate_calibrator_bridge as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, dcb):
        for name in ["CalibrationDebateVerdict", "DebateCalibratorBridge", "_DEBATE_AVAILABLE", "_CALIBRATOR_AVAILABLE"]:
            assert hasattr(dcb, name), f"Missing export: {name}"


class TestModuleFlags:
    def test_debate_available_flag_is_bool(self, dcb):
        assert isinstance(dcb._DEBATE_AVAILABLE, bool)

    def test_calibrator_available_flag_is_bool(self, dcb):
        assert isinstance(dcb._CALIBRATOR_AVAILABLE, bool)


class TestCalibrationDebateVerdict:
    def test_default_init(self, dcb):
        v = dcb.CalibrationDebateVerdict()
        assert v.debate_verdict is None
        assert v.calibrator_score is None
        assert v.bias_adjustment == 0.0
        assert v.calibrated_score == 0.0
        assert v.journal == "经济研究"
        assert v.concerns_from_debate == []
        assert v.suggestions_from_debate == []
        assert v.unresolved_from_debate == []
        assert v.confidence_level == "medium"
        assert v.accepted is False
        assert v.debate_score == 0.0
        assert v.calibrator_weight_used == 0.40
        assert v.debate_weight_used == 0.60
        assert v.claim == ""
        assert v.overall_score == 0.0

    def test_init_with_kwargs(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="Test claim",
            journal="JF",
            confidence_level="high",
            accepted=True,
            calibrated_score=7.5,
            debate_score=8.0,
        )
        assert v.claim == "Test claim"
        assert v.journal == "JF"
        assert v.confidence_level == "high"
        assert v.accepted is True
        assert v.calibrated_score == 7.5
        assert v.debate_score == 8.0

    def test_to_dict_returns_dict(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="Test", journal="经济研究",
            confidence_level="high", accepted=True,
            calibrated_score=7.5, debate_score=8.0,
        )
        d = v.to_dict()
        assert isinstance(d, dict)
        assert d["claim"] == "Test"
        assert d["journal"] == "经济研究"
        assert d["confidence_level"] == "high"
        assert d["accepted"] is True
        assert d["calibrated_score"] == 7.5
        assert d["debate_score"] == 8.0
        assert "concerns_from_debate" in d
        assert "suggestions_from_debate" in d
        assert "unresolved_from_debate" in d
        assert "timestamp" in d

    def test_to_publication_report_short_claim(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="短 claim", journal="经济研究",
            confidence_level="medium", accepted=False,
            calibrated_score=5.0, debate_score=5.0,
        )
        report = v.to_publication_report()
        assert isinstance(report, str)
        assert "短 claim" in report
        assert "经济研究" in report
        assert "not recommended" in report or "accepted" in report

    def test_to_publication_report_long_claim_truncates(self, dcb):
        long_claim = "x" * 200
        v = dcb.CalibrationDebateVerdict(
            claim=long_claim, journal="JF",
            confidence_level="low", accepted=False,
            calibrated_score=3.0, debate_score=3.0,
        )
        report = v.to_publication_report()
        # Long claim should be truncated with "..."
        assert "..." in report
        # The full 200-char claim should NOT be present
        assert long_claim not in report

    def test_to_publication_report_with_bias_adjustment(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="test", journal="JF",
            confidence_level="medium", accepted=True,
            calibrated_score=7.0, debate_score=6.5,
            bias_adjustment=0.5,
        )
        report = v.to_publication_report()
        assert "Calibration adjustment" in report
        assert "upward" in report  # positive adjustment

    def test_to_publication_report_with_negative_bias(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="test", journal="经济研究",
            confidence_level="medium", accepted=False,
            calibrated_score=4.0, debate_score=5.0,
            bias_adjustment=-1.0,
        )
        report = v.to_publication_report()
        assert "downward" in report

    def test_to_publication_report_with_concerns(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="test", journal="JF",
            confidence_level="medium", accepted=False,
            calibrated_score=4.0, debate_score=4.0,
            concerns_from_debate=["平行趋势假设不可检验", "内生性问题", "样本选择偏差"],
        )
        report = v.to_publication_report()
        assert "Key methodological concerns" in report

    def test_to_publication_report_with_suggestions(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="test", journal="JF",
            confidence_level="medium", accepted=False,
            calibrated_score=4.0, debate_score=4.0,
            suggestions_from_debate=["增加工具变量", "改变控制变量集合"],
        )
        report = v.to_publication_report()
        assert "Recommended revisions" in report

    def test_to_publication_report_with_unresolved(self, dcb):
        v = dcb.CalibrationDebateVerdict(
            claim="test", journal="JF",
            confidence_level="low", accepted=False,
            calibrated_score=3.0, debate_score=3.0,
            unresolved_from_debate=["异质性未检验", "样本期过短"],
        )
        report = v.to_publication_report()
        assert "2 unresolved" in report or "unresolved issue" in report

    def test_fmt_helper(self, dcb):
        v = dcb.CalibrationDebateVerdict()
        assert v._fmt(None) == "N/A"
        assert v._fmt(3.14159) == "3.14"

    def test_timestamp_default(self, dcb):
        v = dcb.CalibrationDebateVerdict()
        assert v.timestamp > 0


class TestDebateCalibratorBridge:
    def test_init_disabled(self, dcb):
        bridge = dcb.DebateCalibratorBridge(
            llm_gateway=None,
            journal="JF",
            use_debate=False,
            use_calibration=False,
        )
        assert bridge.llm_gateway is None
        assert bridge.journal == "JF"
        assert bridge.use_debate is False
        assert bridge.use_calibration is False
        assert bridge.arena is None
        assert bridge.calibrator is None
        assert bridge._bias_db is None

    def test_init_default(self, dcb):
        bridge = dcb.DebateCalibratorBridge(llm_gateway=None, journal="经济研究")
        assert bridge.journal == "经济研究"

    def test_init_db_path_none(self, dcb):
        bridge = dcb.DebateCalibratorBridge(
            llm_gateway=None,
            use_debate=False,
            use_calibration=False,
            db_path=None,
        )
        assert bridge._bias_db is None


class TestConfidenceWeightMap:
    def test_weight_map_exists(self, dcb):
        assert isinstance(dcb._CONFIDENCE_WEIGHT_MAP, dict)
        assert dcb._CONFIDENCE_WEIGHT_MAP["high"] == 0.75
        assert dcb._CONFIDENCE_WEIGHT_MAP["medium"] == 0.60
        assert dcb._CONFIDENCE_WEIGHT_MAP["low"] == 0.40

    def test_base_weights(self, dcb):
        assert dcb._BASE_DEBATE_WEIGHT == 0.60
        assert dcb._BASE_CALIBRATION_WEIGHT == 0.40
        # Sum should be 1
        assert abs(dcb._BASE_DEBATE_WEIGHT + dcb._BASE_CALIBRATION_WEIGHT - 1.0) < 1e-9


class TestBridgeInternalMethods:
    def test_compute_final_score_no_calibrator(self, dcb):
        # When calibrator is None, return debate_score directly with weight 1.0
        bridge = dcb.DebateCalibratorBridge(
            llm_gateway=None, use_debate=False, use_calibration=False
        )
        score, dw, cw = bridge._compute_final_score(7.0, None, None)
        assert score == 7.0
        assert dw == 1.0
        assert cw == 0.0

    def test_build_review_report_no_verdict(self, dcb):
        bridge = dcb.DebateCalibratorBridge(
            llm_gateway=None, use_debate=False, use_calibration=False,
            journal="经济研究",
        )
        r = bridge._build_review_report("test claim", None)
        assert isinstance(r, dict)
        assert r["claim"] == "test claim"
        assert r["overall_score"] == 5.0  # default score when no verdict
        assert "dimension_scores" in r
        assert r["metadata"]["journal"] == "经济研究"
        assert r["metadata"]["source"] == "debate_arena"
        # review_id should be a string with "debate_" prefix
        assert r["review_id"].startswith("debate_")
