#!/usr/bin/env python3
"""
Example 01: Quickstart Pipeline · 5 行代码跑完整研究流水线

演示如何用最少的代码，从一个研究主题跑到 LaTeX 论文。
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.agent_pipeline import run_research_pipeline

OUTPUT_DIR = project_root / "output" / "examples" / "01-quickstart"

if __name__ == "__main__":
    # 1. 健康检查
    print("🔍 系统健康检查...")
    try:
        from scripts.health_check import run_health_check
        run_health_check()
    except Exception as e:
        print(f"⚠️  健康检查失败: {e}（继续）")

    # 2. 启动研究
    topic = "碳排放权交易政策对企业绿色创新的影响"
    print(f"\n🚀 启动研究: {topic}")
    print(f"📁 输出目录: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 3. 跑流水线
    try:
        result = run_research_pipeline(
            topic=topic,
            target_journal="经济研究",
            output_dir=str(OUTPUT_DIR),
            max_iterations=3,
        )

        print(f"\n✅ 论文生成完成！")
        print(f"📄 LaTeX 文件: {result.get('manuscript_path', 'N/A')}")
        print(f"📊 图表数量: {result.get('figure_count', 0)}")
        print(f"📚 引用数: {result.get('citation_count', 0)}")
    except Exception as e:
        print(f"\n❌ 流水线失败: {e}")
        print("💡 提示: 确认已配置 DEEPSEEK_API_KEY")
        sys.exit(1)
