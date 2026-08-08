"""Official empirics explore + no-silent-demo regressions."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _tiny_did_panel() -> pd.DataFrame:
    rows = []
    for u in range(20):
        treat = int(u < 10)
        for y in (2018, 2019, 2020, 2021):
            post = int(y >= 2020)
            rows.append(
                {
                    "ticker": f"F{u:02d}",
                    "year": y,
                    "roa": 0.05 + 0.02 * treat * post + 0.001 * u,
                    "lev": 0.3,
                    "size": 21.0,
                    "tangibility": 0.2,
                    "mb": 1.5,
                    "cash_ratio": 0.1,
                    "esg_high": treat,
                    "post": post,
                    "did": treat * post,
                    "sector": "tech" if u % 2 == 0 else "mfg",
                }
            )
    return pd.DataFrame(rows)


def test_load_panel_redundant_from_path(tmp_path: Path):
    from scripts.core.empirical_explore import load_panel_redundant

    p = tmp_path / "green_patent_panel.csv"
    df = _tiny_did_panel()
    df.to_csv(p, index=False)
    res = load_panel_redundant(panel_path=p, topic="绿色专利")
    assert res.ok
    assert res.source == "path"
    assert len(res.df) == len(df)


def test_load_panel_redundant_from_empirical_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.core.empirical_explore import load_panel_redundant

    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "firm_绿色专利.csv").write_text(
        _tiny_did_panel().to_csv(index=False), encoding="utf-8"
    )
    res = load_panel_redundant(topic="企业级绿色专利 DID")
    assert res.ok
    assert res.source == "local_empirical"


def test_explore_did_suite_standard_succeeds_baseline():
    from scripts.core.empirical_explore import explore_did_suite
    from scripts.research_framework.modern_did import ModernDiDEngine

    engine = ModernDiDEngine(
        df=_tiny_did_panel(),
        y_var="roa",
        treat_var="did",
        time_var="post",
        unit_var="ticker",
        x_vars=["lev", "size"],
        cluster_var="sector",
    )
    report = explore_did_suite(engine, level="standard", cluster_var="sector")
    assert "did_2x2" in report.succeeded
    assert "did_2x2" in report.results
    # Missing sa/dCdH must not be claimed
    assert "sa" not in report.succeeded


def test_enhanced_pipeline_refuses_silent_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.research_framework.enhanced_pipeline import EnhancedPipeline

    # Explicit empty root must not fall through to repo data/sample demos
    empty = tmp_path / "empty_root"
    empty.mkdir()
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(empty))
    with patch(
        "scripts.research_framework.data_fetcher.CachedDataFetcher"
    ) as mock_cls:
        mock_cls.return_value.fetch_with_fallback.return_value = None
        pipe = EnhancedPipeline(
            topic="ESG test",
            output_dir=tmp_path / "out",
            allow_demo=False,
            explore=False,
            enable_hitl=False,
            enable_validation_gates=False,
            enable_latex_lint=False,
            enable_latex_diff=False,
            enable_pdf_vision=False,
            enable_sandbox=False,
        )
        df = pipe.step1_load_data()
    assert df.empty
    assert pipe.ctx.step_results["step1"]["status"] == "error"


def test_env_root_does_not_fall_through_to_repo_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.core.empirical_data_root import resolve_empirical_data_root

    missing = tmp_path / "no_such_root"
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(missing))
    root = resolve_empirical_data_root()
    assert root.source == "env"
    assert not root.available
    assert root.path == missing.resolve()


def test_enhanced_pipeline_local_panel_and_explore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.research_framework.enhanced_pipeline import EnhancedPipeline

    panel = tmp_path / "panel.csv"
    _tiny_did_panel().to_csv(panel, index=False)
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path / "unused"))

    pipe = EnhancedPipeline(
        topic="ESG financing",
        output_dir=tmp_path / "out2",
        panel_path=panel,
        explore=True,
        allow_demo=False,
        enable_hitl=False,
        enable_validation_gates=False,
        enable_latex_lint=False,
        enable_latex_diff=False,
        enable_pdf_vision=False,
        enable_sandbox=False,
    )
    df = pipe.step1_load_data()
    assert not df.empty
    assert pipe.ctx.step_results["step1"]["status"] == "ok"
    results = pipe.step2_modern_did()
    assert "did_2x2" in results
    assert pipe.ctx.step_results["step2"].get("explore_level") == "explore"


def test_entity_list_no_silent_known_fallback():
    from scripts.universal_data_fetcher import (
        SyntheticDataForbiddenError,
        UniversalDataFetcher,
    )

    fetcher = UniversalDataFetcher()
    with patch.object(fetcher, "fetch") as mock_fetch:
        mock_fetch.return_value = MagicMock(data=None)
        with pytest.raises(SyntheticDataForbiddenError):
            fetcher.fetch_entity_list_events(allow_synthetic=False)
        df = fetcher.fetch_entity_list_events(allow_synthetic=True)
        assert not df.empty
        assert "_synthetic" in df.columns
