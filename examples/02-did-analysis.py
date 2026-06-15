#!/usr/bin/env python3
"""
Example 02: Callaway-Sant'Anna DID Analysis · 现代 DID 实证

演示如何用 modern_did.py 模块跑现代双重差分 (DID)。
C-S (QJE 2021) 是当前 DID 识别策略的 gold standard。

数据：模拟（生产环境请用真实面板数据）
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.research_framework.modern_did import callaway_santanna
from scripts.research_framework.fin_charts import plot_did_event_study

OUTPUT_DIR = project_root / "output" / "examples" / "02-did"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("📊 Callaway-Sant'Anna DID 演示")
    print("=" * 60)

    # 1. 模拟面板数据 (200 个企业，10 年)
    np.random.seed(42)
    n_units = 200
    n_periods = 10
    treat_period = 7  # 第 7 期开始处理

    df = pd.DataFrame({
        "unit_id": np.repeat(np.arange(n_units), n_periods),
        "period": np.tile(np.arange(n_periods), n_units),
        "treated": (np.repeat(np.arange(n_units), n_periods) < 100).astype(int),
    })

    # DGP: 处理效应 = 0.5 (在 treat_period 之后)
    df["Y"] = (
        df["period"]
        + 0.3 * np.random.randn(len(df))
        + 0.5 * df["treated"] * (df["period"] >= treat_period)
    )

    print(f"  单元数: {n_units}, 期数: {n_periods}")
    print(f"  处理组: 100 个企业, 处理期: t ≥ {treat_period}")
    print()

    # 2. 跑 C-S DID
    print("🔄 跑 Callaway-Sant'Anna DID...")
    result = callaway_santanna(
        data=df,
        yname="Y",
        tname="period",
        idname="unit_id",
        gname="treated",
        # 控制变量、单位权重等
    )

    print(f"  ATT (平均处理效应): {result.att:.4f}")
    print(f"  标准误: {result.se:.4f}")
    print(f"  95% CI: [{result.ci_low:.4f}, {result.ci_high:.4f}]")
    print()

    # 3. 事件研究图
    print("📈 生成事件研究图...")
    fig_path = OUTPUT_DIR / "event_study.png"
    plot_did_event_study(
        result,
        title="Carbon Trading → Innovation: Event Study",
        save_path=str(fig_path),
    )
    print(f"  ✅ {fig_path}")

    print("\n🎉 演示完成！")
    print(f"📁 输出: {OUTPUT_DIR}")
