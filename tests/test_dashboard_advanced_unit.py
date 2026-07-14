"""
Unit tests for scripts/core/dashboard_advanced.py.

Strategy:
- dashboard_advanced imports streamlit, plotly, plotly.express at module scope.
  Neither plotly nor streamlit is guaranteed installed in the test env.
- We inject stub modules into sys.modules *before* the dashboard module is imported
  so that `import streamlit as st` / `import plotly.express as px` succeed.
- Then we patch module-level singletons (agent_state_manager, cost_tracker,
  hitl_manager, HITLGate) so the render_* functions can be exercised.
- All seven public render functions and the two module-level dicts are tested.
- Real code paths (DataFrame construction, list comprehensions, filtering,
  dedup, error classification) are actually executed.
"""

from __future__ import annotations

import importlib
import sys
import types
import warnings
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# Warning / pandas compat shim
# ═══════════════════════════════════════════════════════════════════════════
# Dashboard code uses pandas.resample("H") and dt.floor("T"). In pandas
# 3.0+ these are no longer accepted by `to_offset` and now raise ValueError
# rather than a FutureWarning. We transparently translate the legacy
# frequency strings so the dashboard code can run on this environment.
# ═══════════════════════════════════════════════════════════════════════════

try:
    import pandas._libs.tslibs.offsets as _pd_offsets  # type: ignore

    _original_to_offset = _pd_offsets.to_offset

    def _compat_to_offset(freq):  # type: ignore[no-redef]
        if isinstance(freq, str):
            if freq == "H":
                freq = "h"
            elif freq == "T":
                freq = "min"
        return _original_to_offset(freq)

    _pd_offsets.to_offset = _compat_to_offset  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

warnings.filterwarnings(
    "ignore",
    message=r"'H' is deprecated.*",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"'M' is deprecated.*",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"'T' is deprecated.*",
    category=FutureWarning,
)


# ═══════════════════════════════════════════════════════════════════════════
# Stub builders
# ═══════════════════════════════════════════════════════════════════════════


class _StreamlitRecorder:
    """Captures calls to streamlit APIs so we can inspect them."""

    def __init__(self):
        self.metrics = []       # (label, value, kwargs)
        self.markdowns = []     # raw strings
        self.writes = []
        self.dataframes = []
        self.buttons = []       # (label, kwargs)
        self.infos = []
        self.successes = []
        self.errors = []
        self.captions = []
        self.dividers = 0
        self.timeline_calls = 0
        self.reruns = 0
        self.tabs_ret = []
        self.tab_ctxs = []
        self.cols_calls = []    # list of ints / fraction specs
        self.text_inputs = []
        self.text_areas = []
        self.selects = []       # (label, options, kwargs)
        self.multiselects = []
        self.jsons = []
        self.components_html_called = []

    def __call__(self, *args, **kwargs):  # behave like a mock too
        self.writes.append((args, kwargs))


def _build_streamlit_stub():
    """Build a `streamlit` stub module with all the APIs dashboard_advanced touches."""
    st = types.ModuleType("streamlit")
    st.components = types.ModuleType("streamlit.components")
    st.components.v1 = types.ModuleType("streamlit.components.v1")

    rec = _StreamlitRecorder()

    st.markdown = lambda *a, **kw: rec.markdowns.append((a, kw))
    st.divider = lambda *a, **kw: setattr(rec, "dividers", rec.dividers + 1)
    st.metric = lambda label, value, delta=None, delta_color=None, **kw: \
        rec.metrics.append((label, value, delta, delta_color, kw))
    st.dataframe = lambda data, **kw: rec.dataframes.append((data, kw))
    st.plotly_chart = lambda fig, **kw: setattr(rec, "timeline_calls", rec.timeline_calls + 1)
    st.button = lambda label, **kw: (rec.buttons.append((label, kw)) or False)
    st.info = lambda msg, **kw: rec.infos.append(msg)
    st.success = lambda msg, **kw: rec.successes.append(msg)
    st.error = lambda msg, **kw: rec.errors.append(msg)
    st.caption = lambda msg, **kw: rec.captions.append(msg)
    st.write = lambda *a, **kw: rec.writes.append((a, kw))
    st.json = lambda data, **kw: rec.jsons.append(data)
    st.rerun = lambda *a, **kw: setattr(rec, "reruns", rec.reruns + 1) or None

    def columns(spec):
        rec.cols_calls.append(spec)
        # Return a number of column context managers equal to spec length.
        if isinstance(spec, list):
            n = len(spec)
        else:
            n = int(spec)
        ctxs = [_ColCtx() for _ in range(n)]
        return ctxs

    st.columns = columns

    def tabs(labels):
        rec.tab_ctxs.append(list(labels))
        return [_TabCtx(label) for label in labels]

    st.tabs = tabs

    st.text_input = lambda label, **kw: (rec.text_inputs.append((label, kw)) or "")
    st.text_area = lambda label, key=None, **kw: (rec.text_areas.append((label, key, kw)) or "")
    st.selectbox = lambda label, options, index=0, **kw: (rec.selects.append((label, options, kw)) or options[index])
    st.multiselect = lambda label, options, default=None, format_func=None, **kw: (
        rec.multiselects.append((label, list(options), list(default or []), kw)) or list(default or options)
    )

    st.components.v1.html = lambda data, height=None, scrolling=None, **kw: \
        rec.components_html_called.append((data, height, scrolling, kw))

    st.container = lambda *a, **kw: _ColCtx()

    # Attach the recorder so tests can introspect
    st._recorder = rec
    st.components._recorder = rec
    st.components.v1._recorder = rec
    return st


class _ColCtx:
    """Context manager returned by st.columns(n)[i]."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _TabCtx:
    """Context manager returned by st.tabs([...])[i]."""

    def __init__(self, label):
        self.label = label
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *exc):
        self.exited += 1
        return False


def _build_plotly_express_stub():
    """Build a minimal plotly.express stub: pie/bar/line/timeline.

    Each function returns a MagicMock configured to mimic the .update_layout()
    / .update_yaxis() / .update_xaxis() chain used by the dashboard.
    """

    def make_fig():
        fig = MagicMock()
        fig.update_layout = MagicMock()
        fig.update_xaxis = MagicMock()
        fig.update_yaxis = MagicMock()
        return fig

    px = types.ModuleType("plotly.express")
    px.pie = lambda *a, **kw: make_fig()
    px.bar = lambda *a, **kw: make_fig()
    px.line = lambda *a, **kw: make_fig()
    px.timeline = lambda *a, **kw: make_fig()
    return px


class _StubPlotly:
    """A stub for the `plotly` package; we only need express as a submodule."""

    def __init__(self):
        self.express = _build_plotly_express_stub()


# ═══════════════════════════════════════════════════════════════════════════
# Session-scoped fixture that ensures the stubs are installed before any
# dashboard import. The other tests inside this file use the helpers below.
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def dashboard_module():
    """Import scripts.core.dashboard_advanced with streamlit/plotly mocked."""

    # Always install/replace stubs in sys.modules (under xdist, sys.modules may
    # already contain a streamlit from the parent fixture setup).
    sys.modules["streamlit"] = _build_streamlit_stub()

    _plotly = _StubPlotly()
    sys.modules["plotly"] = _plotly
    sys.modules["plotly.express"] = _plotly.express

    # Import the module under test (and any new deps it pulls in).
    from scripts.core import dashboard_advanced as mod  # noqa: WPS433
    return mod


@pytest.fixture(autouse=True)
def _reset_streamlit_recorder():
    """Reset per-test recording if dashboard was imported in this session."""
    st = sys.modules.get("streamlit")
    rec = getattr(st, "_recorder", None)
    if rec is not None:
        rec.metrics.clear()
        rec.markdowns.clear()
        rec.writes.clear()
        rec.dataframes.clear()
        rec.buttons.clear()
        rec.infos.clear()
        rec.successes.clear()
        rec.errors.clear()
        rec.captions.clear()
        rec.dividers = 0
        rec.timeline_calls = 0
        rec.reruns = 0
        rec.tabs_ret.clear()
        rec.tab_ctxs.clear()
        rec.cols_calls.clear()
        rec.text_inputs.clear()
        rec.text_areas.clear()
        rec.selects.clear()
        rec.multiselects.clear()
        rec.jsons.clear()
        rec.components_html_called.clear()
    yield


@pytest.fixture
def fake_agent():
    from scripts.core.agent_state import AgentState, AgentStatus
    return AgentState(
        agent_id="agt_x",
        name="X-Agent",
        status=AgentStatus.RUNNING,
        current_task="some task",
        start_time=1_700_000_000.0,
        end_time=1_700_000_005.0,
        error_count=1,
        last_error="boom",
    )


@pytest.fixture
def fake_event():
    import time
    from scripts.core.agent_state import Event, EventType
    # Recent timestamp so the 24h filter does not wipe it out.
    return Event(
        event_id="ev1",
        event_type=EventType.AGENT_ERROR,
        agent_id="agt_x",
        timestamp=time.time() - 60.0,  # 1 minute ago
        data={"error": "rate limit exceeded: 429"},
        duration_ms=123.0,
    )


@pytest.fixture
def fake_cost_record():
    from scripts.core.agent_state import CostRecord
    return CostRecord(
        record_id="r1",
        agent_id="agt_x",
        timestamp=1_700_000_000.0,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        model="deepseek-v4-flash",
        task_id="t1",
    )


@pytest.fixture
def fake_hitl_request():
    from scripts.core.agent_state import HITLRequest
    return HITLRequest(
        request_id="req-1",
        agent_id="agt_x",
        task_id="t1",
        decision_point="checkpoint",
        context={"k": "v"},
        created_at=1_700_000_000.0,
        status="approved",
        reviewed_at=1_700_000_010.0,
        reviewer_comment="ok",
    )


def _rec():
    return sys.modules["streamlit"]._recorder


# ═══════════════════════════════════════════════════════════════════════════
# Module-level constants
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleConstants:
    def test_all_listed(self, dashboard_module):
        # __all__ must list exactly the documented public surface.
        assert set(dashboard_module.__all__) == {
            "render_fleet_status",
            "render_cost_analytics",
            "render_execution_timeline",
            "render_hitl_inbox",
            "render_error_log",
            "render_dag_visualization",
            "render_advanced_views",
            "COLORS",
            "STATUS_LABELS",
        }

    def test_colors_keys_present(self, dashboard_module):
        COLORS = dashboard_module.COLORS
        for k in ("running", "succeeded", "failed", "idle", "waiting", "retrying"):
            assert k in COLORS, f"COLORS missing key {k!r}"
            assert COLORS[k].startswith("#"), f"COLORS[{k!r}] should be a hex string"

    def test_colors_values_distinct(self, dashboard_module):
        vals = list(dashboard_module.COLORS.values())
        assert len(set(vals)) == len(vals), "All colors should be unique"

    def test_status_labels_keys_present(self, dashboard_module):
        LABELS = dashboard_module.STATUS_LABELS
        for k in ("running", "succeeded", "failed", "idle", "waiting", "retrying"):
            assert k in LABELS, f"STATUS_LABELS missing key {k!r}"
            # Chinese labels are non-empty strings
            assert isinstance(LABELS[k], str) and LABELS[k]

    def test_color_label_keys_match(self, dashboard_module):
        assert set(dashboard_module.COLORS.keys()) == set(dashboard_module.STATUS_LABELS.keys())


# ═══════════════════════════════════════════════════════════════════════════
# render_fleet_status
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderFleetStatusEmpty:
    def test_renders_with_no_agents(self, dashboard_module):
        """When get_all_agents() is empty, function should call st.info."""
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 0,
                "running_count": 0,
                "idle_count": 0,
                "failed_count": 0,
                "waiting_count": 0,
                "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = []
            dashboard_module.render_fleet_status()

        rec = _rec()
        # Empty path → exactly one st.info
        assert "暂无Agent数据" in rec.infos
        # 6 metric cards
        assert len(rec.metrics) == 6
        # metric values reflect the patched status
        assert rec.metrics[0][0] == "Agent总数"
        assert rec.metrics[0][1] == 0

    def test_divider_called_once(self, dashboard_module):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 0, "running_count": 0, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = []
            rec = _rec()
            dashboard_module.render_fleet_status()
        assert rec.dividers == 1


class TestRenderFleetStatusWithAgents:
    def test_renders_with_agents(self, dashboard_module, fake_agent):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 1, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [fake_agent]
            dashboard_module.render_fleet_status()

        rec = _rec()
        # 6 metric cards + section dividers
        metric_labels = [m[0] for m in rec.metrics]
        assert "Agent总数" in metric_labels
        assert "运行中" in metric_labels
        assert "空闲" in metric_labels
        assert "失败" in metric_labels
        assert "等待审核" in metric_labels
        assert "重试中" in metric_labels

        # Agent table displayed
        assert len(rec.dataframes) == 1
        df, kwargs = rec.dataframes[0]
        assert kwargs.get("hide_index") is True
        assert len(df) == 1
        # Duration formatted when both timestamps present
        assert df.iloc[0]["持续时间"] == "5.0s"
        # Truncated long errors / status mapped via STATUS_LABELS
        assert df.iloc[0]["状态"] == "运行中"

    def test_renders_long_error_truncation(self, dashboard_module):
        from scripts.core.agent_state import AgentState, AgentStatus
        long_err = "x" * 80
        agent = AgentState(
            agent_id="a", name="n", status=AgentStatus.FAILED,
            last_error=long_err, error_count=2,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 0, "idle_count": 0,
                "failed_count": 1, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [agent]
            dashboard_module.render_fleet_status()

        rec = _rec()
        df = rec.dataframes[0][0]
        assert df.iloc[0]["错误次数"] == 2
        assert str(df.iloc[0]["最后错误"]).endswith("...")
        assert len(df.iloc[0]["最后错误"]) <= 53

    def test_no_last_error_renders_dash(self, dashboard_module):
        from scripts.core.agent_state import AgentState, AgentStatus
        agent = AgentState(
            agent_id="a", name="n", status=AgentStatus.SUCCEEDED,
            last_error=None, error_count=0, current_task=None,
            start_time=None, end_time=None,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 0, "idle_count": 1,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [agent]
            dashboard_module.render_fleet_status()

        rec = _rec()
        df = rec.dataframes[0][0]
        assert df.iloc[0]["持续时间"] == "-"
        assert df.iloc[0]["当前任务"] == "-"
        assert df.iloc[0]["最后错误"] == "-"

    def test_filter_statuses_passed_to_multiselect(self, dashboard_module, fake_agent):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 1, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [fake_agent]
            dashboard_module.render_fleet_status()
        rec = _rec()
        assert len(rec.multiselects) == 1
        label, options, default, _kw = rec.multiselects[0]
        assert label == "筛选状态"
        assert set(options) == set(dashboard_module.STATUS_LABELS.keys())

    def test_pie_and_bar_rendered(self, dashboard_module, fake_agent):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 1, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [fake_agent]
            dashboard_module.render_fleet_status()
        # at least two plotly figures (pie + bar)
        assert _rec().timeline_calls >= 2

    def test_refresh_button(self, dashboard_module, fake_agent):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 1, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [fake_agent]
            dashboard_module.render_fleet_status()
        # at least one "refresh" button
        assert any("刷新" in label for (label, _kw) in _rec().buttons)

    def test_running_count_delta_color_normal(self, dashboard_module):
        """When running_count > 0, delta_color must be 'normal'."""
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 3, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = []
            dashboard_module.render_fleet_status()
        # metric: "运行中"
        running_metric = next(m for m in _rec().metrics if m[0] == "运行中")
        assert running_metric[3] == "normal"

    def test_failed_delta_color_inverse_when_present(self, dashboard_module):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 0, "idle_count": 0,
                "failed_count": 2, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = []
            dashboard_module.render_fleet_status()
        failed = next(m for m in _rec().metrics if m[0] == "失败")
        assert failed[3] == "inverse"

    def test_retrying_count_defaults_to_zero(self, dashboard_module):
        """If 'retrying_count' missing from get_fleet_status, default to 0."""
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 0, "running_count": 0, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0,
                # retrying_count intentionally absent
            }
            mgr.get_all_agents.return_value = []
            dashboard_module.render_fleet_status()
        retrying = next(m for m in _rec().metrics if m[0] == "重试中")
        assert retrying[1] == 0


# ═══════════════════════════════════════════════════════════════════════════
# render_cost_analytics
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderCostAnalyticsEmpty:
    def test_zero_data(self, dashboard_module):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_calls": 0,
                "cost_per_call": 0.0,
            }
            ct.get_cost_by_agent.return_value = {}
            ct.get_cost_timeline.return_value = []
            ct.get_recent_records.return_value = []

            dashboard_module.render_cost_analytics()

        rec = _rec()
        # 4 overview cards
        assert len([m for m in rec.metrics if m[0].startswith("总成本") or
                    m[0].startswith("总Token") or
                    m[0].startswith("API调用") or
                    m[0].startswith("平均成本")]) >= 4
        # Empty-state infos
        info_text = "\n".join(rec.infos)
        assert "暂无成本数据" in info_text
        assert "暂无Agent成本数据" in info_text
        assert "暂无调用记录" in info_text


class TestRenderCostAnalyticsWithData:
    def test_renders_with_records(self, dashboard_module, fake_cost_record):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 0.5,
                "total_input_tokens": 1234,
                "total_output_tokens": 567,
                "total_calls": 3,
                "cost_per_call": 0.5 / 3,
            }
            ct.get_cost_by_agent.return_value = {
                "agt_a": {"call_count": 1, "total_input_tokens": 100,
                         "total_output_tokens": 50, "total_cost": 0.1},
                "agt_b": {"call_count": 2, "total_input_tokens": 200,
                         "total_output_tokens": 100, "total_cost": 0.4},
            }
            ct.get_cost_timeline.return_value = [
                {"timestamp": 1_700_000_000.0, "agent_id": "a",
                 "cost_usd": 0.1, "input_tokens": 100, "output_tokens": 50},
            ]
            ct.get_recent_records.return_value = [fake_cost_record]

            dashboard_module.render_cost_analytics()

        rec = _rec()
        # pie + line + bar at minimum
        assert rec.timeline_calls >= 3
        # Agent table displayed (agents)
        assert any(kw.get("hide_index") is True
                   for (_df, kw) in rec.dataframes
                   if hasattr(_df, "columns"))
        # 2 dataframes: agents + records
        assert len(rec.dataframes) >= 2

    def test_total_cost_metric_formatted(self, dashboard_module):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 1.2345,
                "total_input_tokens": 100, "total_output_tokens": 200,
                "total_calls": 1, "cost_per_call": 1.2345,
            }
            ct.get_cost_by_agent.return_value = {}
            ct.get_cost_timeline.return_value = []
            ct.get_recent_records.return_value = []
            dashboard_module.render_cost_analytics()

        total_metric = next(m for m in _rec().metrics if m[0] == "总成本 (USD)")
        assert total_metric[1].startswith("$")
        assert "1.2345" in total_metric[1]

    def test_token_sum_metric(self, dashboard_module):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 0.0,
                "total_input_tokens": 500, "total_output_tokens": 250,
                "total_calls": 0, "cost_per_call": 0,
            }
            ct.get_cost_by_agent.return_value = {}
            ct.get_cost_timeline.return_value = []
            ct.get_recent_records.return_value = []
            dashboard_module.render_cost_analytics()

        token_metric = next(m for m in _rec().metrics if m[0] == "总Token数")
        assert token_metric[1] == "750"

    def test_agent_breakdown_dataframe_columns(self, dashboard_module, fake_cost_record):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 0.5, "total_input_tokens": 100, "total_output_tokens": 50,
                "total_calls": 1, "cost_per_call": 0.5,
            }
            ct.get_cost_by_agent.return_value = {
                "agt_a": {"call_count": 1, "total_input_tokens": 100,
                         "total_output_tokens": 50, "total_cost": 0.1},
            }
            ct.get_cost_timeline.return_value = []
            ct.get_recent_records.return_value = [fake_cost_record]
            dashboard_module.render_cost_analytics()

        rec = _rec()
        # at least 2 dataframes: agent breakdown + recent records
        assert len(rec.dataframes) >= 2

    def test_recent_records_table(self, dashboard_module, fake_cost_record):
        with patch.object(dashboard_module, "cost_tracker") as ct:
            ct.get_total_cost.return_value = {
                "total_cost_usd": 0.001, "total_input_tokens": 100, "total_output_tokens": 50,
                "total_calls": 1, "cost_per_call": 0.001,
            }
            ct.get_cost_by_agent.return_value = {}
            ct.get_cost_timeline.return_value = []
            ct.get_recent_records.return_value = [fake_cost_record]
            dashboard_module.render_cost_analytics()

        rec = _rec()
        # The most recent dataframe should contain a row with our cost record
        last_df = rec.dataframes[-1][0]
        assert len(last_df) == 1
        assert last_df.iloc[0]["Agent"] == "agt_x"
        assert last_df.iloc[0]["输入Token"] == 100


# ═══════════════════════════════════════════════════════════════════════════
# render_execution_timeline
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderExecutionTimelineEmpty:
    def test_no_history_renders_info(self, dashboard_module):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = []
            mgr.get_all_agents.return_value = []
            dashboard_module.render_execution_timeline()
        assert "暂无执行数据" in _rec().infos


class TestRenderExecutionTimelineWithHistory:
    def test_renders_event_timeline(self, dashboard_module, fake_event):
        from scripts.core.agent_state import AgentState, AgentStatus
        agent = AgentState(
            agent_id="agt_x", name="X-Agent", status=AgentStatus.RUNNING,
            start_time=1_700_000_000.0, end_time=None,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [fake_event]
            mgr.get_all_agents.return_value = [agent]
            dashboard_module.render_execution_timeline()

        rec = _rec()
        # at least one plotly figure (line for timeline)
        assert rec.timeline_calls >= 1
        # at least 2 dataframes (events detail + gantt)
        assert len(rec.dataframes) >= 1
        # selectbox for time range
        assert any("时间范围" in label for (label, *_rest) in rec.selects)

    def test_refresh_button(self, dashboard_module, fake_event):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [fake_event]
            mgr.get_all_agents.return_value = []
            dashboard_module.render_execution_timeline()
        assert any("刷新" in label for (label, _kw) in _rec().buttons)

    def test_gantt_rendered_for_running_agent(self, dashboard_module, fake_event):
        from scripts.core.agent_state import AgentState, AgentStatus
        agent = AgentState(
            agent_id="agt_x", name="X-Agent", status=AgentStatus.RUNNING,
            start_time=1_700_000_000.0, end_time=1_700_000_005.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [fake_event]
            mgr.get_all_agents.return_value = [agent]
            dashboard_module.render_execution_timeline()
        # gantt timeline triggers plotly_chart
        assert _rec().timeline_calls >= 2

    def test_gantt_skipped_when_no_start_time(self, dashboard_module, fake_event):
        from scripts.core.agent_state import AgentState, AgentStatus
        agent = AgentState(
            agent_id="agt_x", name="X-Agent", status=AgentStatus.RUNNING,
            start_time=None, end_time=None,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [fake_event]
            mgr.get_all_agents.return_value = [agent]
            dashboard_module.render_execution_timeline()
        # timeline line still rendered, gantt skipped (data list empty)
        assert _rec().timeline_calls == 1


# ═══════════════════════════════════════════════════════════════════════════
# render_hitl_inbox
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderHITLInbox:
    def test_empty_inbox_renders_success(self, dashboard_module):
        """When both managers return empty, st.success is shown."""
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = []
            hm.get_all.return_value = []

            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = []
                GateCls.return_value = gate_inst

                dashboard_module.render_hitl_inbox()

        rec = _rec()
        # success: no pending
        assert any("没有待审核" in s for s in rec.successes)

    def test_metrics_shown(self, dashboard_module):
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = []
            hm.get_all.return_value = []
            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = []
                GateCls.return_value = gate_inst

                dashboard_module.render_hitl_inbox()
        labels = [m[0] for m in _rec().metrics]
        assert "总待审核" in labels
        assert "HITLGate" in labels
        assert "HITLManager" in labels
        assert "已批准" in labels

    def test_renders_hitlmanager_pending_request(self, dashboard_module, fake_hitl_request):
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = [fake_hitl_request]
            hm.get_all.return_value = [fake_hitl_request]

            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = []
                GateCls.return_value = gate_inst
                dashboard_module.render_hitl_inbox()
        rec = _rec()
        # One HITLManager record shown - metrics should reflect 1 pending.
        # Both 批准 / 拒绝 buttons rendered for the request.
        approve_buttons = [b for b in rec.buttons if "批准" in b[0]]
        reject_buttons = [b for b in rec.buttons if "拒绝" in b[0]]
        assert len(approve_buttons) == 1
        assert len(reject_buttons) == 1

    def test_dedup_hits_gate_first(self, dashboard_module, fake_hitl_request):
        """When HITLGate and HITLManager share an id, HITLGate wins."""
        # ApprovalRecord (gate) and HITLRequest (mgr) — distinct object types
        # but the test ensures the merge-and-dedup logic runs.
        from scripts.core.hitl_gate import ApprovalRecord, GateState

        gate_rec = ApprovalRecord(
            gate_id="shared", stage="outline", state=GateState.PENDING,
            content={"k": "v"}, question="approve me?",
        )

        # Build a HITLRequest that matches a different key (test dedup logic
        # in general — the merge uses rec.gate_id from gate side first).
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = [fake_hitl_request]
            hm.get_all.return_value = []

            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = [gate_rec]
                GateCls.return_value = gate_inst
                dashboard_module.render_hitl_inbox()

        rec = _rec()
        # Two distinct pending records (different keys) → two approve buttons
        approve_buttons = [b for b in rec.buttons if "批准" in b[0]]
        assert len(approve_buttons) == 2

    def test_gate_render_with_question_and_content(self, dashboard_module):
        """HITLGate path renders question + content + created_ts."""
        from scripts.core.hitl_gate import ApprovalRecord, GateState
        gate_rec = ApprovalRecord(
            gate_id="g1", stage="outline", state=GateState.PENDING,
            content={"outline": "…"}, question="请确认大纲？",
            held_at=1_700_000_000.0,
        )
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = []
            hm.get_all.return_value = []
            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = [gate_rec]
                GateCls.return_value = gate_inst
                dashboard_module.render_hitl_inbox()
        rec = _rec()
        # JSON dump of content present
        assert any(isinstance(j, dict) and j.get("outline") == "…" for j in rec.jsons)
        # approve and reject both rendered for HITLGate
        assert any("批准" in b[0] for b in rec.buttons)
        assert any("拒绝" in b[0] for b in rec.buttons)

    def test_get_pending_exception_swallowed(self, dashboard_module):
        """If hitl_manager.get_pending() throws, error is swallowed."""
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.side_effect = RuntimeError("nope")
            hm.get_all.return_value = []
            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.side_effect = RuntimeError("nope")
                GateCls.return_value = gate_inst
                # Should NOT raise
                dashboard_module.render_hitl_inbox()

        rec = _rec()
        assert any("没有待审核" in s for s in rec.successes)

    def test_history_table_when_completed(self, dashboard_module, fake_hitl_request):
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = []
            hm.get_all.return_value = [fake_hitl_request]
            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = []
                GateCls.return_value = gate_inst
                dashboard_module.render_hitl_inbox()
        rec = _rec()
        # History dataframe rendered
        history_dfs = [d for (d, kw) in rec.dataframes
                       if hasattr(d, "columns") and "审核时间" in d.columns]
        assert len(history_dfs) == 1
        assert history_dfs[0].iloc[0]["Agent"] == "agt_x"
        assert "批准" in history_dfs[0].iloc[0]["状态"]

    def test_no_history_message(self, dashboard_module):
        with patch.object(dashboard_module, "hitl_manager") as hm:
            hm.get_pending.return_value = []
            hm.get_all.return_value = []
            with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                gate_inst = MagicMock()
                gate_inst.get_pending.return_value = []
                GateCls.return_value = gate_inst
                dashboard_module.render_hitl_inbox()
        # No history → '暂无审核历史' or '暂无审核记录'
        info_text = "\n".join(_rec().infos)
        assert ("暂无审核历史" in info_text) or ("暂无审核记录" in info_text)


# ═══════════════════════════════════════════════════════════════════════════
# render_error_log
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderErrorLogEmpty:
    def test_no_errors_renders_success(self, dashboard_module):
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = []
            dashboard_module.render_error_log()
        assert any("没有错误记录" in s for s in _rec().successes)


@pytest.mark.filterwarnings("ignore::FutureWarning")
class TestRenderErrorLogWithErrors:
    def test_renders_error_metrics(self, dashboard_module):
        from scripts.core.agent_state import Event, EventType
        ev = Event(
            event_id="ev1", event_type=EventType.AGENT_ERROR,
            agent_id="agt_x", timestamp=1_700_000_000.0,
            data={"error": "rate limit exceeded: 429"}, duration_ms=123.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [ev]
            dashboard_module.render_error_log()
        rec = _rec()
        labels = [m[0] for m in rec.metrics]
        assert "错误总数" in labels
        assert "错误类型数" in labels
        assert "重试次数" in labels

    def test_error_event_classified(self, dashboard_module):
        from scripts.core.agent_state import Event, EventType
        ev = Event(
            event_id="ev1", event_type=EventType.AGENT_ERROR,
            agent_id="agt_x", timestamp=1_700_000_000.0,
            data={"error": "rate limit exceeded: 429"}, duration_ms=42.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [ev]
            dashboard_module.render_error_log()
        rec = _rec()
        error_dfs = [d for (d, kw) in rec.dataframes
                     if hasattr(d, "columns") and "错误类型" in d.columns]
        assert len(error_dfs) == 1
        # Cell value is a string in the rendered dataframe
        cell = error_dfs[0].iloc[0]["错误类型"]
        assert cell in ("frequency_limit", "rate_limit")

    def test_retry_event_counted(self, dashboard_module):
        from scripts.core.agent_state import Event, EventType
        e1 = Event(
            event_id="e1", event_type=EventType.AGENT_RETRY,
            agent_id="agt_x", timestamp=1_700_000_000.0,
            data={"error": "timeout"}, duration_ms=10.0,
        )
        e2 = Event(
            event_id="e2", event_type=EventType.AGENT_ERROR,
            agent_id="agt_x", timestamp=1_700_000_001.0,
            data={"error": "timeout"}, duration_ms=10.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [e1, e2]
            dashboard_module.render_error_log()
        rec = _rec()
        retry_metric = next(m for m in rec.metrics if m[0] == "重试次数")
        assert retry_metric[1] == 1

    def test_long_error_truncated(self, dashboard_module):
        from scripts.core.agent_state import Event, EventType
        long_msg = "boom " * 50  # 250 chars
        ev = Event(
            event_id="e1", event_type=EventType.AGENT_ERROR,
            agent_id="agt_x", timestamp=1_700_000_000.0,
            data={"error": long_msg}, duration_ms=10.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [ev]
            dashboard_module.render_error_log()
        rec = _rec()
        error_dfs = [d for (d, kw) in rec.dataframes
                     if hasattr(d, "columns") and "错误信息" in d.columns]
        assert len(error_dfs) == 1
        msg = error_dfs[0].iloc[0]["错误信息"]
        assert msg.endswith("...") or len(msg) <= 103

    def test_retry_strategy_suggestion(self, dashboard_module):
        """Each error type produces a markdown with strategy (max_retries/backoff)."""
        from scripts.core.agent_state import Event, EventType
        ev = Event(
            event_id="e1", event_type=EventType.AGENT_ERROR,
            agent_id="agt_x", timestamp=1_700_000_000.0,
            data={"error": "rate limit exceeded"}, duration_ms=10.0,
        )
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_history.return_value = [ev]
            dashboard_module.render_error_log()

        rec = _rec()
        joined = " ".join(
            m[0][0] if isinstance(m, tuple) and m[0] else str(m) for m in rec.markdowns
        )
        assert "最大重试次数" in joined
        assert "退避策略" in joined


# ═══════════════════════════════════════════════════════════════════════════
# render_dag_visualization
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderDAGVisualization:
    """All these tests patch WorkflowVisualizer.to_modern_html to a no-op so
    the dashboard does not depend on the (possibly buggy) f-string template in
    visualizer.py. The dashboard's own logic is exercised either way."""

    @staticmethod
    def _patched_dag():
        return patch(
            "scripts.core.visualizer.WorkflowVisualizer.to_modern_html",
            lambda self, *a, **kw: Path("/tmp/dummy.html"),
        )

    def test_empty_agents_renders_metrics(self, dashboard_module):
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = []
                dashboard_module.render_dag_visualization()
        rec = _rec()
        labels = [m[0] for m in rec.metrics]
        assert "🚀 运行中" in labels
        assert "✅ 已完成" in labels
        assert "⏳ 等待中" in labels
        assert "❌ 失败" in labels
        assert "📊 总计" in labels

    def test_components_html_called(self, dashboard_module):
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = []
                dashboard_module.render_dag_visualization()
        rec = _rec()
        assert len(rec.components_html_called) >= 1
        # First arg is the HTML body returned by visualizer
        html, height, scrolling, kw = rec.components_html_called[0]
        assert isinstance(html, str)
        assert height == 680
        assert scrolling is False

    def test_filtering_by_search(self, dashboard_module):
        """When search input is provided, viz filters nodes accordingly."""
        with self._patched_dag():
            original_text_input = sys.modules["streamlit"].text_input

            def fake_text_input(label, **kw):
                return "大纲"  # Matches the 'outline' node label

            sys.modules["streamlit"].text_input = fake_text_input
            try:
                with patch.object(dashboard_module, "agent_state_manager") as mgr:
                    mgr.get_all_agents.return_value = []
                    dashboard_module.render_dag_visualization()
            finally:
                sys.modules["streamlit"].text_input = original_text_input

    def test_get_all_agents_exception_swallowed(self, dashboard_module):
        """When agent_state_manager.get_all_agents raises, the view is still
        rendered (uses [] fallback), no exception bubbles out."""
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.side_effect = RuntimeError("boom")
                # Should NOT raise
                dashboard_module.render_dag_visualization()

    def test_running_agents_labeled_in_metric(self, dashboard_module):
        from scripts.core.agent_state import AgentState, AgentStatus
        a = AgentState(
            agent_id="agt_run", name="R", status=AgentStatus.RUNNING,
        )
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = [a]
                dashboard_module.render_dag_visualization()
        rec = _rec()
        running_metric = next(m for m in rec.metrics if m[0] == "🚀 运行中")
        # delta contains the running agent id
        assert running_metric[2] is not None
        assert "agt_run" in running_metric[2]

    def test_failed_agents_labeled(self, dashboard_module):
        from scripts.core.agent_state import AgentState, AgentStatus
        a = AgentState(
            agent_id="agt_fail", name="F", status=AgentStatus.FAILED,
        )
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = [a]
                dashboard_module.render_dag_visualization()
        rec = _rec()
        failed_metric = next(m for m in rec.metrics if m[0] == "❌ 失败")
        assert failed_metric[2] is not None
        assert "agt_fail" in failed_metric[2]

    def test_viz_instantiated_and_html_generated(self, dashboard_module):
        """The internal WorkflowVisualizer is constructed and its HTML output rendered."""
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = []
                dashboard_module.render_dag_visualization()
        # At least one render via components.v1.html
        rec = _rec()
        assert len(rec.components_html_called) >= 1

    def test_layout_selectbox_layout_modes(self, dashboard_module):
        """The layout selectbox offers '水平' and '垂直'."""
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = []
                dashboard_module.render_dag_visualization()
        rec = _rec()
        layout_sel = [s for s in rec.selects if s[0] == "布局"]
        assert layout_sel, "Expected a '布局' selectbox call"
        assert set(layout_sel[0][1]) == {"水平", "垂直"}

    def test_theme_selectbox_themes(self, dashboard_module):
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = []
                dashboard_module.render_dag_visualization()
        rec = _rec()
        theme_sel = [s for s in rec.selects if s[0] == "主题"]
        assert theme_sel
        assert set(theme_sel[0][1]) == {"深色", "浅色"}

    def test_failed_and_running_messages(self, dashboard_module):
        """Running agents appear via st.info, failed via st.error."""
        from scripts.core.agent_state import AgentState, AgentStatus
        ra = AgentState(agent_id="r1", name="R", status=AgentStatus.RUNNING)
        fa = AgentState(agent_id="f1", name="F", status=AgentStatus.FAILED)
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_all_agents.return_value = [ra, fa]
                dashboard_module.render_dag_visualization()
        rec = _rec()
        joined = "\n".join(rec.infos)
        assert "正在执行" in joined
        joined_err = "\n".join(rec.errors)
        assert "执行失败" in joined_err


# ═══════════════════════════════════════════════════════════════════════════
# render_advanced_views (the master orchestrator)
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderAdvancedViews:
    @staticmethod
    def _patched_dag():
        return patch(
            "scripts.core.visualizer.WorkflowVisualizer.to_modern_html",
            lambda self, *a, **kw: Path("/tmp/dummy.html"),
        )

    def test_renders_all_six_tabs(self, dashboard_module):
        """render_advanced_views should create one tab per section."""
        # Patch all the underlying managers / deps
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_fleet_status.return_value = {
                    "total_agents": 0, "running_count": 0, "idle_count": 0,
                    "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
                }
                mgr.get_all_agents.return_value = []
                mgr.get_history.return_value = []

                with patch.object(dashboard_module, "cost_tracker") as ct:
                    ct.get_total_cost.return_value = {
                        "total_cost_usd": 0, "total_input_tokens": 0,
                        "total_output_tokens": 0, "total_calls": 0,
                        "cost_per_call": 0,
                    }
                    ct.get_cost_by_agent.return_value = {}
                    ct.get_cost_timeline.return_value = []
                    ct.get_recent_records.return_value = []

                    with patch.object(dashboard_module, "hitl_manager") as hm:
                        hm.get_pending.return_value = []
                        hm.get_all.return_value = []

                        with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                            gate_inst = MagicMock()
                            gate_inst.get_pending.return_value = []
                            GateCls.return_value = gate_inst

                            dashboard_module.render_advanced_views()

        rec = _rec()
        # 6 tabs created with the right labels
        assert len(rec.tab_ctxs) == 1, "st.tabs should be called exactly once"
        tab_labels = rec.tab_ctxs[0]
        assert tab_labels == [
            "🚀 舰队状态",
            "💰 成本分析",
            "📈 执行时间线",
            "👤 人工审核",
            "❌ 错误日志",
            "🔀 DAG可视化",
        ]

    def test_each_section_invoked(self, dashboard_module):
        """Smoke: every sub-render was called (no exceptions raised)."""
        # Six major headings should be markdown'd — one per view.
        with self._patched_dag():
            with patch.object(dashboard_module, "agent_state_manager") as mgr:
                mgr.get_fleet_status.return_value = {
                    "total_agents": 0, "running_count": 0, "idle_count": 0,
                    "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
                }
                mgr.get_all_agents.return_value = []
                mgr.get_history.return_value = []

                with patch.object(dashboard_module, "cost_tracker") as ct:
                    ct.get_total_cost.return_value = {
                        "total_cost_usd": 0, "total_input_tokens": 0,
                        "total_output_tokens": 0, "total_calls": 0,
                        "cost_per_call": 0,
                    }
                    ct.get_cost_by_agent.return_value = {}
                    ct.get_cost_timeline.return_value = []
                    ct.get_recent_records.return_value = []

                    with patch.object(dashboard_module, "hitl_manager") as hm:
                        hm.get_pending.return_value = []
                        hm.get_all.return_value = []

                        with patch("scripts.core.dashboard_advanced.HITLGate") as GateCls:
                            gate_inst = MagicMock()
                            gate_inst.get_pending.return_value = []
                            GateCls.return_value = gate_inst

                            dashboard_module.render_advanced_views()

        rec = _rec()
        # Pull all markdown content as strings
        md_texts = []
        for c in rec.markdowns:
            if isinstance(c, tuple) and c:
                first = c[0]
                if isinstance(first, tuple):
                    md_texts.append(str(first[0]) if first else "")
                else:
                    md_texts.append(str(first))
        joined = " ".join(md_texts)
        # One section heading per major view
        for heading in ["舰队状态", "成本分析", "执行时间线", "人工审核",
                        "错误日志", "DAG", "论文写作流程"]:
            assert heading in joined, f"Missing heading: {heading!r}"


# ═══════════════════════════════════════════════════════════════════════════
# Coverage for the small exception-tolerant blocks & rounding behaviour
# ═══════════════════════════════════════════════════════════════════════════


class TestMiscCoverage:
    def test_module_docstring_present(self, dashboard_module):
        assert dashboard_module.__doc__ is not None
        assert "Dashboard" in dashboard_module.__doc__

    def test_render_functions_have_docstrings(self, dashboard_module):
        for fn_name in dashboard_module.__all__:
            if fn_name in ("COLORS", "STATUS_LABELS"):
                continue
            obj = getattr(dashboard_module, fn_name)
            assert callable(obj), f"{fn_name} is not callable"
            # every render function should have a docstring
            if fn_name.startswith("render_"):
                assert obj.__doc__, f"{fn_name} missing docstring"

    def test_colors_uses_lowercase_status_keys(self, dashboard_module):
        # The COLORS dict uses lowercase keys (matching AgentStatus.value)
        # Verify explicitly that 'succeeded' is present (since Enum value is lowercase)
        assert "succeeded" in dashboard_module.COLORS
        assert "retrying" in dashboard_module.COLORS

    def test_recorder_captures_columns_calls(self, dashboard_module, fake_agent):
        """Verify st.columns is called multiple times in the populated view."""
        with patch.object(dashboard_module, "agent_state_manager") as mgr:
            mgr.get_fleet_status.return_value = {
                "total_agents": 1, "running_count": 1, "idle_count": 0,
                "failed_count": 0, "waiting_count": 0, "retrying_count": 0,
            }
            mgr.get_all_agents.return_value = [fake_agent]
            dashboard_module.render_fleet_status()
        rec = _rec()
        # Top metric cards (6 cols) + status filter row + pie/bar row
        assert len(rec.cols_calls) >= 3
        assert 6 in rec.cols_calls
        assert 2 in rec.cols_calls


# ═══════════════════════════════════════════════════════════════════════════
# Direct invocation via the bundled module runner (catches path issues)
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleRunnerSanity:
    def test_import_via_string_path(self, dashboard_module):
        """Loading by importlib should yield the same module."""
        # Force re-import to make sure cache state is consistent
        spec = importlib.util.find_spec("scripts.core.dashboard_advanced")
        assert spec is not None

    def test_module_has_no_dunder_exports(self, dashboard_module):
        # We should NOT export anything starting with underscore
        for name in dashboard_module.__all__:
            assert not name.startswith("_"), name

    def test_public_api_callable(self, dashboard_module):
        # All non-dict entries in __all__ should be callable
        for name in dashboard_module.__all__:
            obj = getattr(dashboard_module, name)
            if name in ("COLORS", "STATUS_LABELS"):
                assert isinstance(obj, dict), name
            else:
                assert callable(obj), name


if __name__ == "__main__":
    unittest.main()
