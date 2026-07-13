"""Regression tests for P0-A: _main_dispatch (audit_fix_2026_07_12).

Bug: previous `_main_dispatch` only dispatched `design`/`review` modes,
so the default `--mode full` silently fell through and returned None
(implicit exit code 0, but did nothing useful).

These tests assert the dispatcher routes correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestMainDispatch:
    """P0-A regression: _main_dispatch must route by mode."""

    def _setup_args(self, mode: str, list_methods: bool = False):
        """Patch _parse_args to return a controlled args object."""
        from scripts.research_framework import pipeline as pl
        args = MagicMock()
        args.mode = mode
        args.list_methods = list_methods
        return patch.object(pl, "_parse_args", return_value=args)

    def test_full_mode_dispatches_to_full_pipeline(self):
        """Default mode 'full' must call _run_full_pipeline, not return None."""
        from scripts.research_framework import pipeline as pl

        with self._setup_args("full"):
            with patch.object(pl, "_run_full_pipeline") as mock_full:
                mock_full.return_value = 0
                rc = pl._main_dispatch()
                assert rc == 0, f"_main_dispatch for mode=full must return 0, got {rc}"
                assert mock_full.called, "_run_full_pipeline must be called for mode=full"

    def test_design_mode_dispatches_to_design(self):
        from scripts.research_framework import pipeline as pl

        with self._setup_args("design"):
            with patch.object(pl, "_run_design_mode") as mock_design:
                mock_design.return_value = 0
                rc = pl._main_dispatch()
                assert rc == 0
                assert mock_design.called

    def test_review_mode_dispatches_to_review(self):
        from scripts.research_framework import pipeline as pl

        with self._setup_args("review"):
            with patch.object(pl, "_run_review_mode") as mock_review:
                mock_review.return_value = 0
                rc = pl._main_dispatch()
                assert rc == 0
                assert mock_review.called

    def test_unknown_mode_returns_error_code(self):
        """Unknown mode must return non-zero (not None)."""
        from scripts.research_framework import pipeline as pl

        with self._setup_args("garbage"):
            rc = pl._main_dispatch()
            assert rc == 1, (
                f"_main_dispatch for invalid mode must return 1, got {rc!r} "
                "(P0-A bug: previous implementation returned None which prints no error)"
            )

    def test_main_alias_points_to_full_pipeline(self):
        """`main = _run_full_pipeline` alias for `python pipeline.py`."""
        from scripts.research_framework import pipeline
        assert pipeline.main is pipeline._run_full_pipeline, (
            "P0-A: `main` alias must point to _run_full_pipeline so that "
            "`python pipeline.py` works without --mode flag."
        )
