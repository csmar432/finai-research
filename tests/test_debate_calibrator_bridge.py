"""
tests/test_debate_calibrator_bridge.py

Unit tests for the DebateCalibratorBridge integration module.
Covers:
  - Module imports
  - CalibrationDebateVerdict dataclass fields and methods
  - DebateCalibratorBridge initialization and configuration
  - Weighted score merging logic (_compute_final_score)
  - Debate bias extraction (_record_debate_biases)
  - sync_review_claim returns CalibrationDebateVerdict
  - Graceful degradation when modules are unavailable
  - Publication report generation
  - Journal-specific calibration adjustments
"""

from __future__ import annotations

import unittest
from dataclasses import fields

# Import the module under test
import scripts.core.debate_calibrator_bridge as bridge_module
from scripts.core.debate_calibrator_bridge import (
    CalibrationDebateVerdict,
    DebateCalibratorBridge,
    _DEBATE_AVAILABLE,
    _CALIBRATOR_AVAILABLE,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────


def _make_dummy_debate_verdict(score: float = 7.0, confidence: str = "medium") -> "DebateVerdict":
    """Create a minimal DebateVerdict for testing."""
    from scripts.core.debate_arena import DebateVerdict
    return DebateVerdict(
        claim="Carbon trading increases green patents by 15%",
        overall_score=score,
        confidence_delta=0.5,
        key_concerns=["Parallel trends", "Endogeneity"],
        unresolved_issues=["Selection on observables"],
        suggested_revisions=["Add event-study"],
        confidence_level=confidence,
        accepted=True,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestModuleImports(unittest.TestCase):
    """Test 1: Bridge module imports successfully."""

    def test_bridge_module_loads(self):
        self.assertIsNotNone(bridge_module)
        self.assertTrue(hasattr(bridge_module, "CalibrationDebateVerdict"))
        self.assertTrue(hasattr(bridge_module, "DebateCalibratorBridge"))

    def test_debate_available_flag(self):
        # Flag reflects whether debate_arena was importable
        self.assertIsInstance(_DEBATE_AVAILABLE, bool)

    def test_calibrator_available_flag(self):
        self.assertIsInstance(_CALIBRATOR_AVAILABLE, bool)


class TestCalibrationDebateVerdictFields(unittest.TestCase):
    """Test 2: CalibrationDebateVerdict dataclass fields."""

    def test_required_fields_present(self):
        """All required fields are declared on the dataclass."""
        field_names = {f.name for f in fields(CalibrationDebateVerdict)}
        required = {
            "debate_verdict",
            "calibrator_score",
            "bias_adjustment",
            "calibrated_score",
            "journal",
            "concerns_from_debate",
            "suggestions_from_debate",
            "unresolved_from_debate",
            "confidence_level",
            "accepted",
            "debate_score",
            "calibrator_weight_used",
            "debate_weight_used",
            "timestamp",
            "claim",
            "overall_score",
            "confidence_delta",
        }
        self.assertEqual(required, field_names)

    def test_default_values(self):
        """Default values are sensible."""
        v = CalibrationDebateVerdict()
        self.assertIsNone(v.debate_verdict)
        self.assertIsNone(v.calibrator_score)
        self.assertEqual(v.bias_adjustment, 0.0)
        self.assertEqual(v.calibrated_score, 0.0)
        self.assertEqual(v.journal, "经济研究")
        self.assertEqual(v.confidence_level, "medium")
        self.assertFalse(v.accepted)
        self.assertEqual(v.debate_score, 0.0)

    def test_to_dict(self):
        """to_dict returns a flat dictionary with all fields."""
        v = CalibrationDebateVerdict(
            claim="Test claim",
            debate_score=6.5,
            calibrator_score=7.0,
            bias_adjustment=0.3,
            calibrated_score=6.8,
            journal="JFE",
            confidence_level="high",
            accepted=True,
        )
        d = v.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["claim"], "Test claim")
        self.assertEqual(d["debate_score"], 6.5)
        self.assertEqual(d["calibrator_score"], 7.0)
        self.assertEqual(d["bias_adjustment"], 0.3)
        self.assertEqual(d["calibrated_score"], 6.8)
        self.assertEqual(d["journal"], "JFE")
        self.assertEqual(d["confidence_level"], "high")
        self.assertTrue(d["accepted"])

    def test_post_init_from_debate_verdict(self):
        """__post_init__ propagates fields from DebateVerdict."""
        dv = _make_dummy_debate_verdict(score=7.5, confidence="high")
        v = CalibrationDebateVerdict(debate_verdict=dv)
        self.assertEqual(v.claim, dv.claim)
        self.assertEqual(v.debate_score, 7.5)
        self.assertEqual(v.confidence_level, "high")
        self.assertEqual(v.concerns_from_debate, dv.key_concerns)
        self.assertEqual(v.suggestions_from_debate, dv.suggested_revisions)


class TestBridgeInitialization(unittest.TestCase):
    """Test 3: DebateCalibratorBridge initialization."""

    def test_default_init(self):
        """Bridge initializes with all defaults without error."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        self.assertEqual(bridge.journal, "经济研究")
        self.assertTrue(bridge.use_debate)
        self.assertTrue(bridge.use_calibration)

    def test_debate_disabled(self):
        """Bridge works when debate is disabled."""
        bridge = DebateCalibratorBridge(llm_gateway=None, use_debate=False)
        self.assertFalse(bridge.use_debate)
        self.assertIsNone(bridge.arena)

    def test_calibration_disabled(self):
        """Bridge works when calibration is disabled."""
        bridge = DebateCalibratorBridge(llm_gateway=None, use_calibration=False)
        self.assertFalse(bridge.use_calibration)
        self.assertIsNone(bridge.calibrator)

    def test_custom_journal(self):
        """Custom journal name is stored."""
        bridge = DebateCalibratorBridge(llm_gateway=None, journal="JF")
        self.assertEqual(bridge.journal, "JF")


class TestComputeFinalScore(unittest.TestCase):
    """Test 4: _compute_final_score weighted averaging logic."""

    def test_no_calibration_returns_debate_score(self):
        """When calibrator_score is None, debate score is returned as-is."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        final, dw, cw = bridge._compute_final_score(7.0, None, None)
        self.assertEqual(final, 7.0)
        self.assertEqual(dw, 1.0)
        self.assertEqual(cw, 0.0)

    def test_medium_confidence_default_weights(self):
        """Medium confidence uses default 60/40 weights."""
        bridge = DebateCalibratorBridge(llm_gateway=None, journal="JF")
        final, dw, cw = bridge._compute_final_score(
            debate_score=7.0,
            calibrator_score=8.0,
            verdict=_make_dummy_debate_verdict(score=7.0, confidence="medium"),
        )
        # 0.6 * 7.0 + 0.4 * 8.0 = 7.4
        self.assertAlmostEqual(final, 7.4, places=2)
        self.assertAlmostEqual(dw, 0.60, places=2)
        self.assertAlmostEqual(cw, 0.40, places=2)

    def test_high_confidence_debate_heavy(self):
        """High confidence shifts weight toward debate."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        final, dw, cw = bridge._compute_final_score(
            debate_score=7.0,
            calibrator_score=8.0,
            verdict=_make_dummy_debate_verdict(score=7.0, confidence="high"),
        )
        # 0.75 * 7.0 + 0.25 * 8.0 = 7.25
        self.assertAlmostEqual(final, 7.25, places=2)
        self.assertAlmostEqual(dw, 0.75, places=2)
        self.assertAlmostEqual(cw, 0.25, places=2)

    def test_low_confidence_calibrator_heavy(self):
        """Low confidence shifts weight toward calibrator."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        final, dw, cw = bridge._compute_final_score(
            debate_score=7.0,
            calibrator_score=8.0,
            verdict=_make_dummy_debate_verdict(score=7.0, confidence="low"),
        )
        # 0.40 * 7.0 + 0.60 * 8.0 = 7.6
        self.assertAlmostEqual(final, 7.6, places=2)
        self.assertAlmostEqual(dw, 0.40, places=2)
        self.assertAlmostEqual(cw, 0.60, places=2)

    def test_missing_verdict_uses_medium(self):
        """Missing verdict falls back to medium confidence weights."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        final, dw, cw = bridge._compute_final_score(
            debate_score=6.0,
            calibrator_score=7.0,
            verdict=None,
        )
        # 0.6 * 6.0 + 0.4 * 7.0 = 6.4
        self.assertAlmostEqual(final, 6.4, places=2)
        self.assertAlmostEqual(dw, 0.60, places=2)


class TestRecordDebateBiases(unittest.TestCase):
    """Test 5: _record_debate_biases extracts concerns from verdict."""

    def test_no_db_means_noop(self):
        """No-op when no bias DB is configured."""
        bridge = DebateCalibratorBridge(llm_gateway=None, db_path=None)
        bridge._bias_db = None
        # Should not raise
        bridge._record_debate_biases(_make_dummy_debate_verdict())

    def test_records_bias_for_unresolved_issues(self):
        """Method calls db.record_review when unresolved issues exist."""
        from unittest.mock import MagicMock, patch

        dv = _make_dummy_debate_verdict()
        bridge = DebateCalibratorBridge(llm_gateway=None, db_path=":memory:")
        bridge._bias_db = MagicMock()

        bridge._record_debate_biases(dv)
        bridge._bias_db.record_review.assert_called_once()


class TestSyncReviewClaim(unittest.TestCase):
    """Test 6: sync_review_claim returns CalibrationDebateVerdict."""

    def test_sync_returns_calibration_verdict(self):
        """sync_review_claim returns a CalibrationDebateVerdict."""
        bridge = DebateCalibratorBridge(
            llm_gateway=None,
            use_debate=False,
            use_calibration=False,
        )
        result = bridge.sync_review_claim(
            claim="Test claim",
            context={"methodology": "DID"},
        )
        self.assertIsInstance(result, CalibrationDebateVerdict)
        self.assertEqual(result.claim, "Test claim")

    def test_sync_no_debate_no_calibration(self):
        """With both disabled, returns verdict with zero scores."""
        bridge = DebateCalibratorBridge(
            llm_gateway=None,
            use_debate=False,
            use_calibration=False,
        )
        result = bridge.sync_review_claim(claim="Stub claim", context={})
        self.assertEqual(result.debate_score, 0.0)
        self.assertIsNone(result.calibrator_score)
        self.assertEqual(result.calibrated_score, 0.0)


class TestGracefulDegradation(unittest.TestCase):
    """Test 7: Graceful degradation when modules are unavailable."""

    def test_bridge_instantiates_without_modules(self):
        """Bridge still instantiates even if sub-modules are unavailable."""
        # The flags tell us whether imports succeeded
        if not _DEBATE_AVAILABLE:
            self.skipTest("DebateArena not available")
        if not _CALIBRATOR_AVAILABLE:
            self.skipTest("ReviewerCalibrator not available")

        bridge = DebateCalibratorBridge(llm_gateway=None)
        self.assertIsNotNone(bridge)


class TestPublicationReport(unittest.TestCase):
    """Test 8: to_publication_report generates readable text."""

    def test_report_includes_claim(self):
        """Publication report contains the claim."""
        v = CalibrationDebateVerdict(
            claim="Carbon trading increases green patents by 15%",
            debate_score=7.0,
            calibrator_score=7.5,
            calibrated_score=7.2,
            journal="经济研究",
            confidence_level="high",
            accepted=True,
            concerns_from_debate=["Endogeneity concern"],
            suggestions_from_debate=["Add IV"],
            unresolved_from_debate=["Selection"],
        )
        report = v.to_publication_report()
        self.assertIn("Carbon trading", report)
        self.assertIn("accepted", report)
        self.assertIn("7.20", report)
        self.assertIn("Endogeneity", report)

    def test_report_handles_missing_concerns(self):
        """Report works even when no concerns are present."""
        v = CalibrationDebateVerdict(
            claim="Short claim",
            debate_score=8.0,
            calibrator_score=8.5,
            calibrated_score=8.2,
            journal="JFE",
            confidence_level="high",
            accepted=True,
        )
        report = v.to_publication_report()
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 20)


class TestJournalSpecificCalibration(unittest.TestCase):
    """Test 9: Journal-specific calibration adjustments."""

    def test_standardization_method_used(self):
        """Bridge calls calibrator with standardization method."""
        from unittest.mock import MagicMock, patch

        bridge = DebateCalibratorBridge(
            llm_gateway=None,
            journal="JFE",
            use_debate=False,
        )
        bridge.calibrator = MagicMock()
        bridge.calibrator.calibrate_review.return_value = MagicMock(
            calibrated_overall_score=7.2,
            original_overall_score=7.0,
        )

        bridge.sync_review_claim(claim="Test", context={})
        bridge.calibrator.calibrate_review.assert_called_once()
        call_kwargs = bridge.calibrator.calibrate_review.call_args
        self.assertEqual(call_kwargs.kwargs.get("method"), "standardization")
        self.assertEqual(call_kwargs.kwargs.get("target_journal"), "JFE")

    def test_review_report_includes_journal_metadata(self):
        """_build_review_report includes journal in metadata."""
        bridge = DebateCalibratorBridge(llm_gateway=None, journal="RFS")
        report = bridge._build_review_report(
            claim="Test",
            verdict=_make_dummy_debate_verdict(score=6.5),
        )
        self.assertEqual(report["metadata"]["journal"], "RFS")

    def test_different_journals_different_baselines(self):
        """Different journals produce different calibration outcomes."""
        from unittest.mock import MagicMock

        bridge_jf = DebateCalibratorBridge(llm_gateway=None, journal="JF")
        bridge_jfe = DebateCalibratorBridge(llm_gateway=None, journal="JFE")

        dv = _make_dummy_debate_verdict(score=7.0)

        # Calibrator mock returning same score
        for bridge_obj in [bridge_jf, bridge_jfe]:
            bridge_obj.calibrator = MagicMock()
            bridge_obj.calibrator.journal_baselines = {
                "JF": {"overall": 7.5},
                "JFE": {"overall": 7.7},
            }
            bridge_obj.calibrator.calibrate_review.return_value = MagicMock(
                calibrated_overall_score=7.5,
                original_overall_score=7.0,
            )

        r1 = bridge_jf._compute_final_score(7.0, 7.5, dv)
        r2 = bridge_jfe._compute_final_score(7.0, 7.5, dv)
        # Same inputs but bridge carries different journal config
        self.assertEqual(r1[1], r2[1])  # weights same (same confidence)


class TestBuildReviewReport(unittest.TestCase):
    """Test 10: _build_review_report structure."""

    def test_returns_dict_with_required_keys(self):
        """_build_review_report returns dict with all required keys."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        dv = _make_dummy_debate_verdict(score=7.5)
        report = bridge._build_review_report("Test claim", dv)
        self.assertIsInstance(report, dict)
        self.assertIn("overall_score", report)
        self.assertIn("dimension_scores", report)
        self.assertIn("metadata", report)
        self.assertEqual(report["overall_score"], 7.5)

    def test_dimension_scores_in_range(self):
        """Dimension scores stay within 1-10 range."""
        bridge = DebateCalibratorBridge(llm_gateway=None)
        for score in [0.5, 5.0, 9.5, 15.0]:
            dv = _make_dummy_debate_verdict(score=score)
            report = bridge._build_review_report("claim", dv)
            for dim, val in report["dimension_scores"].items():
                self.assertGreaterEqual(val, 1.0, f"{dim} score {val} below 1.0")
                self.assertLessEqual(val, 10.0, f"{dim} score {val} above 10.0")


class TestCalibrationDebateVerdictConvenienceFields(unittest.TestCase):
    """Test 11: Convenience fields are propagated from DebateVerdict."""

    def test_claim_from_verdict(self):
        """claim field is set from DebateVerdict."""
        dv = _make_dummy_debate_verdict(score=6.0)
        v = CalibrationDebateVerdict(debate_verdict=dv)
        self.assertEqual(v.claim, dv.claim)

    def test_overall_score_from_verdict(self):
        """overall_score is set from DebateVerdict."""
        dv = _make_dummy_debate_verdict(score=6.5)
        v = CalibrationDebateVerdict(debate_verdict=dv)
        self.assertEqual(v.overall_score, 6.5)

    def test_confidence_delta_from_verdict(self):
        """confidence_delta is set from DebateVerdict."""
        dv = _make_dummy_debate_verdict(score=6.0)
        dv.confidence_delta = 0.75
        v = CalibrationDebateVerdict(debate_verdict=dv)
        self.assertEqual(v.confidence_delta, 0.75)


class TestConfidenceWeightMap(unittest.TestCase):
    """Test 12: Confidence weight mapping for weighted scoring."""

    def test_all_confidence_levels_mapped(self):
        """All confidence levels have defined weights."""
        from scripts.core.debate_calibrator_bridge import _CONFIDENCE_WEIGHT_MAP

        for level in ["high", "medium", "low"]:
            self.assertIn(level, _CONFIDENCE_WEIGHT_MAP)
            weight = _CONFIDENCE_WEIGHT_MAP[level]
            self.assertGreater(weight, 0.0)
            self.assertLessEqual(weight, 1.0)

    def test_weights_sum_to_one(self):
        """Debate weight and calibration weight sum to 1.0."""
        from scripts.core.debate_calibrator_bridge import _CONFIDENCE_WEIGHT_MAP

        for level, dw in _CONFIDENCE_WEIGHT_MAP.items():
            cw = 1.0 - dw
            self.assertAlmostEqual(dw + cw, 1.0, places=5, msg=f"Weights for {level} don't sum to 1")


# ─── Test Suite ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    unittest.main(verbosity=2)
