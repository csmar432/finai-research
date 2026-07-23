"""
Unit tests for scripts/agent_pipeline.py — dataclasses and helper functions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))



class TestInteractionResultDataclass:
    """Test InteractionResult dataclass."""

    def test_interaction_result_defaults(self):
        from scripts.agent_pipeline import InteractionResult

        result = InteractionResult()
        assert result.needs_input is False
        assert result.action_needed == "proceed"
        assert result.questions == []
        assert result.limitations == []
        assert result.api_keys_to_add == []
        assert result.fix_steps == []
        assert result.llm_available is True

    def test_interaction_result_with_api_key_issues(self):
        from scripts.agent_pipeline import InteractionResult

        result = InteractionResult(
            needs_input=True,
            action_needed="ask_api_key",
            questions=["Please set TUSHARE_TOKEN"],
            limitations=["Tushare A股数据"],
            api_keys_to_add=[{"name": "TUSHARE_TOKEN", "url": "https://tushare.pro/register"}],
            fix_steps=["1. Register at tushare.pro", "2. Copy token to .env.local"],
            llm_available=True,
        )
        assert result.needs_input is True
        assert result.action_needed == "ask_api_key"
        assert "Tushare" in result.limitations[0]
        assert len(result.api_keys_to_add) == 1
        assert result.llm_available is True

    def test_interaction_result_llm_unavailable(self):
        from scripts.agent_pipeline import InteractionResult

        result = InteractionResult(
            needs_input=True,
            action_needed="ask_llm_confirm",
            limitations=["LLM不可用"],
            llm_available=False,
        )
        assert result.llm_available is False
        assert result.action_needed == "ask_llm_confirm"


class TestPipelineConfigurationError:
    """Test PipelineConfigurationError exception."""

    def test_error_init(self):
        from scripts.agent_pipeline import PipelineConfigurationError

        err = PipelineConfigurationError("Health check failed")
        assert str(err) == "Health check failed"
        assert err.message == "Health check failed"
        assert err.details == {}

    def test_error_with_details(self):
        from scripts.agent_pipeline import PipelineConfigurationError

        err = PipelineConfigurationError(
            "Missing API keys",
            details={"missing": ["TUSHARE_TOKEN"], "found": []},
        )
        assert err.message == "Missing API keys"
        assert err.details["missing"] == ["TUSHARE_TOKEN"]


class TestStatusMappings:
    """Test module-level status/label mapping constants."""

    def test_status_cn_mapping(self):
        from scripts.agent_pipeline import _STATUS_CN

        assert isinstance(_STATUS_CN, dict)
        assert _STATUS_CN["running"] == "运行中"
        assert _STATUS_CN["success"] == "已完成"
        assert _STATUS_CN["error"] == "执行失败"

    def test_label_cn_mapping(self):
        from scripts.agent_pipeline import _LABEL_CN

        assert isinstance(_LABEL_CN, dict)
        assert _LABEL_CN["outline"] == "大纲设计"
        assert _LABEL_CN["literature"] == "文献综述"
        assert _LABEL_CN["writing"] == "论文写作"
        assert _LABEL_CN["refinement"] == "修改润色"

    def test_stage_color_mapping(self):
        from scripts.agent_pipeline import _STAGE_COLOR

        assert isinstance(_STAGE_COLOR, dict)
        for key, color in _STAGE_COLOR.items():
            assert color.startswith("#") or color is None
            if color:
                assert len(color) == 7  # #RRGGBB

    def test_gate_state_cn_mapping(self):
        from scripts.agent_pipeline import _GATE_STATE_CN

        assert isinstance(_GATE_STATE_CN, dict)
        assert _GATE_STATE_CN["pending"] == "待审批"
        assert _GATE_STATE_CN["approved"] == "已通过"
        assert _GATE_STATE_CN["rejected"] == "已拒绝"


class TestBuildCanvasBanner:
    """Test _build_canvas_banner helper."""

    def test_build_canvas_banner_basic(self):
        from scripts.agent_pipeline import _build_canvas_banner

        banner = _build_canvas_banner("Pipeline complete")
        assert isinstance(banner, str)
        assert "Pipeline complete" in banner
        assert "╔" in banner
        assert "╚" in banner

    def test_build_canvas_banner_with_detail(self):
        from scripts.agent_pipeline import _build_canvas_banner

        banner = _build_canvas_banner("Running", detail="Step 3/5")
        assert "Running" in banner
        assert "Step 3/5" in banner


class TestGetCanvasUrl:
    """Test _get_canvas_url helper."""

    def test_get_canvas_url_returns_str(self):
        from scripts.agent_pipeline import _get_canvas_url

        url = _get_canvas_url()
        assert isinstance(url, str)
        assert len(url) > 0


class TestBuildWfPayload:
    """Test _build_wf_payload helper."""

    def test_build_wf_payload_basic(self):
        from scripts.agent_pipeline import _build_wf_payload

        payload = _build_wf_payload(
            steps=[],
            stage_results={},
            topic="碳排放权交易与绿色创新",
        )
        assert isinstance(payload, dict)
        assert "nodes" in payload
        assert "edges" in payload
        assert "meta" in payload
        assert payload["nodes"][0]["id"] == "input"
        assert "用户请求" in payload["nodes"][0]["label"]

    def test_build_wf_payload_input_preview(self):
        from scripts.agent_pipeline import _build_wf_payload

        payload = _build_wf_payload(
            steps=[],
            stage_results={},
            topic="测试研究主题",
        )
        input_node = payload["nodes"][0]
        assert input_node["input_preview"] == "测试研究主题"


class TestModuleLevelConstants:
    """Test other module-level constants."""

    def test_project_root_defined(self):
        from scripts.agent_pipeline import PROJECT_ROOT

        assert isinstance(PROJECT_ROOT, Path)
        assert PROJECT_ROOT.exists()

    def test_report_gen_available_flag(self):
        from scripts.agent_pipeline import _REPORT_GEN_AVAILABLE

        assert isinstance(_REPORT_GEN_AVAILABLE, bool)

    def test_lg_bridge_available_flag(self):
        from scripts.agent_pipeline import _LG_BRIDGE_AVAILABLE

        assert isinstance(_LG_BRIDGE_AVAILABLE, bool)
