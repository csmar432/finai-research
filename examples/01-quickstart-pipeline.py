#!/usr/bin/env python3
"""
Example 01: Quickstart Pipeline · 5 行代码跑完整研究流水线

演示如何用最少的代码，从一个研究主题跑到论文草稿。

依赖：
    - DEEPSEEK_API_KEY (在 .env.local 或环境变量中)
    - pip install -e .  (安装项目依赖)

使用：
    python examples/01-quickstart-pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

OUTPUT_DIR = project_root / "output" / "examples" / "01-quickstart"


if __name__ == "__main__":
    # 1. 健康检查
    print("\uD83D\uDD0D 系统健康检查...")
    try:
        from scripts.health_check import run_health_check
        run_health_check()
    except Exception as e:
        print(f"\u26A0\uFE0F 健康检查失败: {e}\uFF08\u7EE7\u7EED\uFF09")

    # 2. 配置研究主题
    topic = "\u78B3\u6398\u653E\u6743\u4EA4\u6613\u653F\u7B56\u5BF9\u4F01\u4E1A\u7EFF\u8272\u521B\u65B0\u7684\u5F15\u54CD"
    venue = "\u7ECF\u6D4E\u7814\u7A76"

    print(f"\n\uD83D\uDE80 \u542F\u52A8\u7814\u7A76: {topic}")
    print(f"\uD83D\uDCC4 \u76EE\u6807\u671F\u520A: {venue}")
    print(f"\uD83D\uDCC1 \u8F93\u51FA\u76EE\u5F55: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 3. 初始化流水线
    config = AgentPipelineConfig(
        topic=topic,
        venue=venue,
        output_dir=OUTPUT_DIR,
        visualize=True,
        auto_dashboard=False,
    )
    pipeline = AgentPipeline(config=config)

    # 4. 跑流水线
    try:
        print("\n\uD83D\uDE80 \u5F00\u59CB\u8FD0\u884C...")
        result = pipeline.run(topic=topic)

        if result.success:
            print(f"\n\u2705 \u6D41\u6C34\u7EBF\u5B8C\u6210\uFF01")
            print(f"\u23F1 \u603B\u65F6\u957F: {result.total_latency_ms / 1000:.1f}s")
            if result.outline:
                print(f"\uD83D\uDCCB \u5927\u7EB2\u5B58\u50A8: {len(str(result.outline))} \u5B57\u7B49")
            if result.visualization_path:
                print(f"\uD83D\uDCCA \u53EF\u89C6\u5316: {result.visualization_path}")
            print(f"\uD83D\uDCC4 \u8BBA\u6587\u9636\u6BB5:")
            for stage in ["outline", "literature", "plotting", "writing", "refinement"]:
                data = getattr(result, stage, None)
                if data:
                    preview = str(data)[:80].replace("\n", " ")
                    print(f"    \u2713 {stage}: {preview}")
            if result.did_chart_paths:
                print(f"\uD83D\uDCC8 DID \u56FE\u8868: {len(result.did_chart_paths)} \u5F20")
        else:
            print(f"\n\u274C \u6D41\u6C34\u7EBF\u5931\u8D25: {result.errors or ['\u672A\u77E5\u9519\u8BEF']}")
            sys.exit(1)

    except Exception as e:
        print(f"\n\uD83D\uDCA5 \u6D41\u6C34\u7EBF\u5F02\u5E38: {e}")
        print("\uD83D\uDCA1 \u63D0\u793A: \u786E\u8BA4\u5DF2\u914D\u7F6E DEEPSEEK_API_KEY")
        sys.exit(1)
