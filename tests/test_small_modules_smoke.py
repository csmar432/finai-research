"""Smoke tests for small utility modules that were 0% covered.

P3 2026-06-29: Covers 8 small scripts/ modules with <50 statements each that
had zero test coverage. These are utility/data-constant files that other
modules depend on but were never directly tested.

Modules covered:
- scripts/exceptions.py (8 stmts): Exception class hierarchy
- scripts/logging_config.py (22): Logging setup with file rotation
- scripts/gen_social_preview.py (26): Social preview image generation
- scripts/research_framework/china_carbon_events.py (29): Carbon ETS panel builder
- scripts/research_framework/china_policy_events.py (29): 7 China policy events
- scripts/journal_templates_multilang.py (33): Japanese/German journal templates
- scripts/plot_utils.py (33): Plotting utilities (CJK font fallback)
- scripts/verify_metadata.py (34): MCP server metadata verification
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pytest


# ────────────────────────────────────────────────────────────────────────────
# 1. scripts/exceptions.py
# ────────────────────────────────────────────────────────────────────────────


class TestExceptions:
    """Verify all 8 WorkflowError subclasses are importable and instantiable."""

    def test_workflow_error_base(self):
        from scripts.exceptions import WorkflowError

        err = WorkflowError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_subclass_hierarchy(self):
        from scripts.exceptions import (
            WorkflowError,
            DataFetchError,
            LLMError,
            ValidationError,
            CacheError,
            DataSourceError,
            CitationError,
            EmbeddingError,
        )

        # All must inherit from WorkflowError (transitively from Exception).
        for cls in [
            DataFetchError,
            LLMError,
            ValidationError,
            CacheError,
            DataSourceError,
            CitationError,
            EmbeddingError,
        ]:
            assert issubclass(cls, WorkflowError)
            assert issubclass(cls, Exception)

    @pytest.mark.parametrize(
        "cls_name,msg",
        [
            ("DataFetchError", "fetch failed"),
            ("LLMError", "API timeout"),
            ("ValidationError", "missing field"),
            ("CacheError", "disk full"),
            ("DataSourceError", "no source available"),
            ("CitationError", "DOI not found"),
            ("EmbeddingError", "model unavailable"),
        ],
    )
    def test_subclass_constructible(self, cls_name, msg):
        from scripts import exceptions

        cls = getattr(exceptions, cls_name)
        err = cls(msg)
        assert str(err) == msg
        # Must be catchable as WorkflowError.
        try:
            raise cls(msg)
        except exceptions.WorkflowError as e:
            assert str(e) == msg


# ────────────────────────────────────────────────────────────────────────────
# 2. scripts/logging_config.py
# ────────────────────────────────────────────────────────────────────────────


class TestLoggingConfig:
    """Verify logging setup creates the expected handlers and formatters."""

    def test_setup_logging_returns_logger(self, tmp_path):
        from scripts.logging_config import setup_logging

        log_dir = str(tmp_path / "logs")
        logger = setup_logging(log_dir=log_dir, console=False)
        assert isinstance(logger, logging.Logger)
        assert logger.name == "finai"

    def test_setup_logging_creates_log_dir(self, tmp_path):
        from scripts.logging_config import setup_logging

        log_dir = str(tmp_path / "logs")
        setup_logging(log_dir=log_dir, console=False)
        assert Path(log_dir).exists()

    def test_setup_logging_creates_log_file(self, tmp_path):
        from scripts.logging_config import setup_logging

        log_dir = str(tmp_path / "logs")
        logger = setup_logging(log_dir=log_dir, console=False)
        logger.info("test message")
        log_file = Path(log_dir) / "workflow.log"
        assert log_file.exists()
        # Force a flush by getting handlers.
        for h in logger.handlers:
            h.flush()

    def test_get_logger_returns_child(self):
        from scripts.logging_config import get_logger

        logger = get_logger("data_pipeline")
        assert logger.name == "finai.data_pipeline"
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_with_console(self, tmp_path):
        from scripts.logging_config import setup_logging

        log_dir = str(tmp_path / "logs")
        logger = setup_logging(log_dir=log_dir, console=True)
        # At least 2 handlers: file + console.
        assert len(logger.handlers) >= 2


# ────────────────────────────────────────────────────────────────────────────
# 3. scripts/research_framework/china_carbon_events.py
# ────────────────────────────────────────────────────────────────────────────


class TestChinaCarbonEvents:
    """Verify carbon ETS panel builder and constants."""

    def test_national_ets_constants(self):
        from scripts.research_framework.china_carbon_events import CHINA_NATIONAL_ETS

        assert CHINA_NATIONAL_ETS["launch_date"] == date(2021, 7, 16)
        assert CHINA_NATIONAL_ETS["scope"] == "Power generation (发电行业) only in Phase 1"
        assert CHINA_NATIONAL_ETS["covered_emissions_pct"] == 40.0

    def test_pilot_ets_dataframe(self):
        from scripts.research_framework.china_carbon_events import CHINA_PILOT_ETS

        assert isinstance(CHINA_PILOT_ETS, pd.DataFrame)
        assert len(CHINA_PILOT_ETS) == 7
        # Shenzhen was first.
        shenzhen = CHINA_PILOT_ETS[CHINA_PILOT_ETS["city"] == "深圳"]
        assert shenzhen["launch_date"].iloc[0] == date(2013, 6, 18)

    def test_eu_ets_phases(self):
        from scripts.research_framework.china_carbon_events import EU_ETS_PHASES

        assert isinstance(EU_ETS_PHASES, pd.DataFrame)
        phases = EU_ETS_PHASES["phase"].tolist()
        assert phases == [1, 2, 3, 4]

    def test_build_carbon_ets_panel_national(self):
        from scripts.research_framework.china_carbon_events import build_carbon_ets_panel

        firm_panel = pd.DataFrame({
            "firm_id": ["A", "B"],
            "province_code": [110000, 440000],
            "year": [2020, 2021],
        })
        df = build_carbon_ets_panel(firm_panel)
        # National: all provinces treated.
        assert df["is_treated"].sum() == 2
        # Year 2021 >= treatment_year (default 2021).
        assert df.loc[df["year"] == 2021, "post"].iloc[0] == 1
        # DID column added.
        assert "did" in df.columns

    def test_build_carbon_ets_panel_pilots(self):
        from scripts.research_framework.china_carbon_events import (
            build_carbon_ets_panel,
            CarbonETSConfig,
            CHINA_PILOT_ETS,
        )

        # Pick one pilot province and one non-pilot.
        pilot_code = CHINA_PILOT_ETS["province_code"].iloc[0]
        non_pilot = 990000  # HK-style code, not a pilot.

        firm_panel = pd.DataFrame({
            "firm_id": ["A", "B"],
            "province_code": [pilot_code, non_pilot],
            "year": [2020, 2020],
        })
        config = CarbonETSConfig(use_pilots=True, treatment_year=2020)
        df = build_carbon_ets_panel(firm_panel, config=config)
        # Pilot firm treated, non-pilot not.
        pilot_treated = df.loc[df["province_code"] == pilot_code, "is_treated"].iloc[0]
        non_pilot_treated = df.loc[df["province_code"] == non_pilot, "is_treated"].iloc[0]
        assert pilot_treated == 1
        assert non_pilot_treated == 0

    def test_carbon_ets_regression_template(self):
        from scripts.research_framework.china_carbon_events import (
            carbon_ets_regression_template,
        )

        template = carbon_ets_regression_template()
        assert isinstance(template, str)
        assert "CallawaySantAnnaDID" in template
        assert "robustness" in template.lower()


# ────────────────────────────────────────────────────────────────────────────
# 4. scripts/research_framework/china_policy_events.py
# ────────────────────────────────────────────────────────────────────────────


class TestChinaPolicyEvents:
    """Verify the 7 China policy events registry."""

    def test_list_events_returns_dataframe(self):
        from scripts.research_framework.china_policy_events import list_events

        events = list_events()
        assert isinstance(events, pd.DataFrame)
        # 7 pre-built events.
        assert len(events) == 7

    def test_get_event_returns_correct_event(self):
        from scripts.research_framework.china_policy_events import (
            get_event,
            ALL_EVENTS,
        )

        for short_name in ALL_EVENTS:
            event = get_event(short_name)
            assert event.english_name  # non-empty

    def test_get_event_raises_on_unknown(self):
        from scripts.research_framework.china_policy_events import get_event

        with pytest.raises(KeyError, match="Unknown event"):
            get_event("nonexistent_event_xyz")

    def test_event_required_fields(self):
        from scripts.research_framework.china_policy_events import ALL_EVENTS

        for short_name, event in ALL_EVENTS.items():
            # All required fields populated.
            assert event.name
            assert event.english_name
            assert isinstance(event.launch_date, date)
            # scope is a free-form description string.
            assert isinstance(event.scope, str) and event.scope
            assert isinstance(event.treated_provinces, list)
            assert isinstance(event.treated_industries, list)
            assert event.expected_effect
            assert isinstance(event.example_papers, list)
            assert isinstance(event.data_sources, list)


# ────────────────────────────────────────────────────────────────────────────
# 5. scripts/journal_templates_multilang.py
# ────────────────────────────────────────────────────────────────────────────


class TestJournalTemplatesMultilang:
    """Verify Japanese/German journal template registry."""

    def test_templates_dict_populated(self):
        from scripts.journal_templates_multilang import TEMPLATES, list_templates

        assert isinstance(TEMPLATES, dict)
        assert len(TEMPLATES) > 0
        # list_templates returns same keys.
        assert list_templates() == list(TEMPLATES.keys())

    def test_get_template_jpe_via_alias(self):
        from scripts.journal_templates_multilang import get_template, TEMPLATES

        t = get_template("jer")  # alias for JER
        assert t is not None
        assert t.short_name in TEMPLATES

    def test_get_template_zwist_via_alias(self):
        from scripts.journal_templates_multilang import get_template, TEMPLATES

        t = get_template("zwist")
        assert t is not None
        assert t.short_name in TEMPLATES

    def test_get_by_language_japanese(self):
        from scripts.journal_templates_multilang import (
            get_by_language,
            TEMPLATES,
        )

        ja_templates = get_by_language("japanese")
        assert len(ja_templates) > 0
        assert all(k in TEMPLATES for k in ja_templates)

    def test_get_by_language_german(self):
        from scripts.journal_templates_multilang import (
            get_by_language,
            TEMPLATES,
        )

        de_templates = get_by_language("german")
        assert len(de_templates) > 0
        assert all(k in TEMPLATES for k in de_templates)

    def test_get_all_templates(self):
        from scripts.journal_templates_multilang import get_all_templates, TEMPLATES

        all_t = get_all_templates()
        # Returns a copy.
        assert all_t == TEMPLATES
        assert all_t is not TEMPLATES

    def test_get_template_returns_none_for_unknown(self):
        from scripts.journal_templates_multilang import get_template

        assert get_template("nonexistent_xyz") is None


# ────────────────────────────────────────────────────────────────────────────
# 6. scripts/plot_utils.py (CJK font fallback)
# ────────────────────────────────────────────────────────────────────────────


class TestPlotUtilsCJK:
    """Verify CJK font detection doesn't crash on any platform."""

    def test_import(self):
        from scripts import plot_utils

        assert hasattr(plot_utils, "_find_cjk_font")

    def test_find_cjk_font_returns_none_or_str(self):
        from scripts.plot_utils import _find_cjk_font

        # Should not crash; returns None or a font name string.
        result = _find_cjk_font()
        assert result is None or isinstance(result, str)


# ────────────────────────────────────────────────────────────────────────────
# 7. scripts/verify_metadata.py (MCP server metadata check)
# ────────────────────────────────────────────────────────────────────────────


class TestVerifyMetadata:
    """Verify MCP server metadata check runs without error.

    Imports the module which executes its top-level verification at import
    time. We mock stdout to keep test output clean and assert no exceptions
    are raised.
    """

    def test_module_imports_without_error(self, capsys, tmp_path, monkeypatch):
        # The module imports and runs verification. We can't easily mock
        # everything, but we can verify it doesn't raise on basic load.
        import scripts.verify_metadata as vm

        # Module-level constants exist.
        assert hasattr(vm, "base")
        assert vm.base.exists()
        # Re-running the verification logic should not crash.
        # Call the part that iterates servers — but it requires the real base.
        # Just call print() to verify stdout is captured.

    def test_module_executes_verification(self, capsys):
        # Importing the module runs its top-level check.
        import importlib
        import scripts.verify_metadata as vm

        importlib.reload(vm)
        captured = capsys.readouterr()
        # Should print either "All N SERVER_METADATA.json ..." or "ISSUE:" lines.
        assert captured.out  # non-empty output


# ────────────────────────────────────────────────────────────────────────────
# 8. scripts/gen_social_preview.py
# ────────────────────────────────────────────────────────────────────────────


class TestGenSocialPreview:
    """Verify social preview generator imports cleanly."""

    def test_module_imports(self):
        # Just import to ensure no top-level errors.
        from scripts import gen_social_preview

        assert hasattr(gen_social_preview, "__file__")


# ────────────────────────────────────────────────────────────────────────────
# Smoke test for checkpoint.py (covered by test_platform_lock.py)
# ────────────────────────────────────────────────────────────────────────────


class TestCheckpointSmoke:
    """Re-affirm checkpoint module imports cleanly with all platform helpers."""

    def test_checkpoint_imports(self):
        from scripts.core import checkpoint

        assert hasattr(checkpoint, "_file_lock_acquire")
        assert hasattr(checkpoint, "_file_lock_release")
        assert hasattr(checkpoint, "CheckpointManager")
