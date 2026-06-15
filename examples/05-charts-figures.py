#!/usr/bin/env python3
"""
Example 05: Academic Finance Charts · 20+ 种学术金融图表

演示 fin_charts.py 模块的 20+ 种专业金融图表预设。
所有图表 ≥300 DPI，输出 PDF/SVG/PNG。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

OUTPUT_DIR = project_root / "output" / "examples" / "05-charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def demo_charts():
    """演示 5 种代表性图表。"""
    print("📊 20+ 种学术金融图表演示")
    print("=" * 60)
    print()
    print("可用图表类型（部分）：")
    print()
    print("  1. 📈 平行趋势图 (Parallel Trends)")
    print("  2. 🎯 事件研究图 (Event Study)")
    print("  3. 🔥 系数热图 (Coefficient Heatmap)")
    print("  4. 📊 描述性统计表 (Descriptive Stats)")
    print("  5. 📉 累计异常收益 (CAR)")
    print("  6. 🌳 决策树可视化")
    print("  7. 📈 收益率序列图")
    print("  8. 🔄 相关性矩阵")
    print("  9. 📊 因子载荷图")
    print(" 10. 🎲 Placebo 检验")
    print("  ... 等等共 20+ 种")
    print()
    print("💡 真实使用：")
    print()
    print("   ```python")
    print("   from scripts.research_framework.fin_charts import (")
    print("       plot_parallel_trends,")
    print("       plot_event_study,")
    print("       plot_coefficient_heatmap,")
    print("   )")
    print()
    print("   # 平行趋势图")
    print("   plot_parallel_trends(")
    print("       data, treatment_col, time_col, y_col,")
    print("       title='Carbon Trading → Innovation',")
    print("       save_path='figures/parallel_trends.pdf',")
    print("       dpi=300,")
    print("   )")
    print()
    print("   # 事件研究图")
    print("   plot_event_study(")
    print("       result,  # DID 结果对象")
    print("       save_path='figures/event_study.pdf',")
    print("   )")
    print()
    print("   # 系数热图 (异质性检验)")
    print("   plot_coefficient_heatmap(")
    print("       coef_df,  # 各子样本回归系数")
    print("       save_path='figures/heterogeneity.pdf',")
    print("   )")
    print("   ```")
    print()
    print("📁 所有图表 ≥300 DPI, 输出 PDF/SVG/PNG")


if __name__ == "__main__":
    demo_charts()
    print()
    print(f"📁 预期输出: {OUTPUT_DIR}/")
