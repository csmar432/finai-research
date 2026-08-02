"""Tests for _auto_generate_arch_diagrams() integration in agent_pipeline.

C2: 验证 --auto-arch flag 的 best-effort 行为:
  - 默认关闭 (auto_arch_diagrams=False)
  - 开启后调用 _auto_generate_arch_diagrams 生成图
  - graphviz 不可用时静默 fallback
  - 失败时不阻塞流水线
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── AgentPipelineConfig 字段 ───────────────────────────────────────────────


class TestConfigField:
    def test_auto_arch_diagrams_field_exists(self):
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig()
        assert hasattr(config, "auto_arch_diagrams")
        assert config.auto_arch_diagrams is False, "默认应关闭 (opt-in)"

    def test_auto_arch_diagrams_can_be_enabled(self):
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=True)
        assert config.auto_arch_diagrams is True


# ── _auto_generate_arch_diagrams 方法存在性 ──────────────────────────────


class TestMethodSignature:
    def test_method_exists(self):
        from scripts.agent_pipeline import AgentPipeline
        assert hasattr(AgentPipeline, "_auto_generate_arch_diagrams")

    def test_method_callable(self):
        from scripts.agent_pipeline import AgentPipeline
        import inspect
        sig = inspect.signature(AgentPipeline._auto_generate_arch_diagrams)
        params = list(sig.parameters.keys())
        # 必须有 self, topic, outline, output_dir
        assert "self" in params
        assert "topic" in params
        assert "outline" in params
        assert "output_dir" in params

    def test_method_returns_list(self):
        """返回值应是 Path 列表"""
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=False)
        pipeline = AgentPipeline(config=config)
        # 默认关闭时, 调用直接返回空列表
        result = pipeline._auto_generate_arch_diagrams()
        assert isinstance(result, list)


# ── 默认行为: 开关关闭时跳过 ───────────────────────────────────────────────


class TestDefaultOffBehavior:
    def test_skipped_when_disabled(self, tmp_path):
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=False)
        pipeline = AgentPipeline(config=config)
        result = pipeline._auto_generate_arch_diagrams(
            topic="test",
            output_dir=tmp_path,
        )
        assert result == [], "默认关闭时应返回空列表"


# ── 开启行为: 调用 arch_diagram_demos ──────────────────────────────────────


@pytest.mark.skipif(
    not Path("/opt/homebrew/bin/dot").exists()
    and not Path("/usr/bin/dot").exists()
    and not Path("/usr/local/bin/dot").exists(),
    reason="graphviz not available",
)
class TestEnabledBehavior:
    def test_generates_diagrams_when_enabled(self, tmp_path):
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=True)
        pipeline = AgentPipeline(config=config)
        result = pipeline._auto_generate_arch_diagrams(
            topic="数字金融与企业创新",
            output_dir=tmp_path,
        )
        # 至少应该生成若干图 (最多 5)
        assert len(result) > 0
        for p in result:
            assert isinstance(p, Path)
            assert p.exists()

    def test_output_dir_contains_arch_diagrams(self, tmp_path):
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=True)
        pipeline = AgentPipeline(config=config)
        pipeline._auto_generate_arch_diagrams(
            topic="test_topic",
            output_dir=tmp_path,
        )
        arch_dir = tmp_path / "arch_diagrams"
        assert arch_dir.exists()
        assert arch_dir.is_dir()
        pngs = list(arch_dir.glob("*.png"))
        assert len(pngs) > 0


# ── Best-effort 验证: 失败不抛异常 ─────────────────────────────────────────


class TestBestEffortBehavior:
    def test_import_failure_silent(self, tmp_path):
        """arch_diagram_demos import 失败时静默返回空列表"""
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=True)
        pipeline = AgentPipeline(config=config)

        with patch.dict("sys.modules", {
            "scripts.research_framework.arch_diagram_demos": None,
        }):
            # 即使 import 失败也不抛异常
            try:
                result = pipeline._auto_generate_arch_diagrams(
                    topic="test",
                    output_dir=tmp_path,
                )
                # 如果到了这里,说明已经优雅处理
                assert isinstance(result, list)
            except Exception as ex:
                pytest.fail(f"应该是 best-effort 不抛异常, 但抛了: {ex}")

    def test_partial_failure_does_not_block(self, tmp_path):
        """部分 demo 失败不阻塞其他生成"""
        from scripts.agent_pipeline import AgentPipeline
        from scripts.agent_pipeline import AgentPipelineConfig
        config = AgentPipelineConfig(auto_arch_diagrams=True)
        pipeline = AgentPipeline(config=config)

        # 模拟某个 demo 抛异常, 但其他仍能成功
        original_func = None
        try:
            from scripts.research_framework.arch_diagram_demos import (
                demo_arch_finresearch_gv,
            )
            original_func = demo_arch_finresearch_gv

            # 让第一个 demo 失败
            def fail_then_ok(*args, **kwargs):
                raise RuntimeError("simulated failure")

            with patch(
                "scripts.research_framework.arch_diagram_demos.demo_arch_finresearch_gv",
                side_effect=fail_then_ok,
            ):
                result = pipeline._auto_generate_arch_diagrams(
                    topic="test",
                    output_dir=tmp_path,
                )
                # 部分失败仍能返回 (其他 4 个 demo 可能成功)
                # 至少应该不抛异常
                assert isinstance(result, list)
        except ImportError:
            # graphviz / arch_diagram_demos 未安装, 跳过
            pytest.skip("arch_diagram_demos not importable")


# ── AgentPipelineResult 字段 ───────────────────────────────────────────────


class TestResultField:
    def test_arch_diagram_paths_field_exists(self):
        from scripts.agent_pipeline import AgentPipelineResult
        # dataclass 应有 arch_diagram_paths 字段
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AgentPipelineResult)}
        assert "arch_diagram_paths" in fields

    def test_arch_diagram_paths_default_empty(self):
        from scripts.agent_pipeline import AgentPipelineResult, AgentPipelineConfig
        result = AgentPipelineResult(
            config=AgentPipelineConfig(),
        )
        assert result.arch_diagram_paths == []
