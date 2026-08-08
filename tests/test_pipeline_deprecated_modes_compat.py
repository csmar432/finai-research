"""CLI soft-compat for deprecated research_framework.pipeline --mode aliases."""

from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest

from scripts.research_framework import pipeline as rf_pipeline


@pytest.mark.parametrize(
    "mode",
    ["data", "analysis", "draft", "lit-review", "novelty-check", "regression"],
)
def test_deprecated_modes_exit_2_with_redirect(mode, capsys):
    with patch.object(
        rf_pipeline,
        "_parse_args",
        return_value=type("A", (), {
            "mode": mode,
            "list_methods": False,
            "topic": "t",
            "draft_file": None,
        })(),
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rc = rf_pipeline._main_dispatch()
    assert rc == 2
    err = capsys.readouterr().err
    assert "Deprecated" in err or "Use:" in err
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_valid_design_mode_still_dispatches():
    with patch.object(
        rf_pipeline,
        "_parse_args",
        return_value=type("A", (), {
            "mode": "design",
            "list_methods": False,
            "topic": "t",
            "draft_file": None,
            "venue": "经济研究",
            "language": "zh",
            "output": "papers/tmp",
            "refined_design": None,
        })(),
    ), patch.object(rf_pipeline, "_run_design_mode", return_value=0) as design:
        rc = rf_pipeline._main_dispatch()
    assert rc == 0
    design.assert_called_once()


def test_deprecated_mode_keys_documented_in_choices():
    keys = set(rf_pipeline._DEPRECATED_MODE_REDIRECTS)
    assert {"data", "analysis", "draft", "lit-review", "novelty-check", "regression"} <= keys
