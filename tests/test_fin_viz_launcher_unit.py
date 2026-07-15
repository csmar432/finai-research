"""Unit tests for scripts/fin-viz-launcher.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def fv():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    import importlib.util
    spec = importlib.util.spec_from_file_location('fv', 'scripts/fin-viz-launcher.py')
    import sys as s
    m = importlib.util.module_from_spec(spec)
    s.modules['fv'] = m
    spec.loader.exec_module(m)
    yield m
    if 'fv' in s.modules:
        del s.modules['fv']


class TestChartTypeRecommendation:
    def test_init(self, fv):
        rec = fv.ChartTypeRecommendation(
            name="event_study",
            name_cn="事件研究图",
            score=0.9,
            description="政策前后效应",
            examples=["DID事件研究"],
            best_for=["DID"],
            factory_method="custom",
            pipeline_query="绘制事件研究图",
        )
        assert rec.name == "event_study"
        assert rec.score == 0.9


class TestVizSession:
    def test_init(self, fv):
        sess = fv.VizSession(
            query="碳交易效应",
            recommended=None,
            selected="event_study",
            data_description="DID数据",
            target_journal="JF",
            output_path=None,
        )
        assert sess.query == "碳交易效应"
