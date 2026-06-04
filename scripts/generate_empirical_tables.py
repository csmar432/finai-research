#!/usr/bin/env python3
"""
实证表格生成器
==============
整合 tariff_research_pipeline.py 的数据 + econometrics.py 的回归引擎，
生成可直接嵌入论文的规范 Markdown 表格。

设计原则：
  1. 真实数据：读取 tariff_research 的处理后数据
  2. 真实回归：调用 OLSRegression / DIDRegression 执行统计推断
  3. 真实表格：由 RegressionTable.to_markdown() 程序化输出
  4. AI 写作层只负责文字描述，不生成任何数字

输出文件（写入 tariff_research/results/tables/）：
  - descriptive_stats.md        描述性统计
  - core_regression.md          核心基准回归（关税暴露 → 专利/R&D）
  - did_regression.md           双重差分（政策净效应）
  - heterogeneity.md             异质性分析（行业/规模）
  - mediation.md                中介效应（R&D 在关税→创新中的角色）
  - robustness.md               稳健性检验（缩尾/子样本/Bootstrap）

使用方法：
  python scripts/generate_empirical_tables.py           # 生成所有表格
  python scripts/generate_empirical_tables.py --regression core  # 仅核心回归
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "tariff_research"))

from scripts.econometrics import (
    DIDRegression,
    OLSRegression,
    RegressionTable,
    descriptive_stats,
    table_to_markdown,
    winsorize_all,
)

# ════════════════════════════════════════════════════════════════════
# 数据加载
# ════════════════════════════════════════════════════════════════════

def load_tariff_data() -> dict[str, pd.DataFrame]:
    """
    加载 tariff_research 处理后的面板数据。
    如果不存在，则使用模拟数据（用于演示）。
    """
    base = SCRIPT_DIR / "tariff_research" / "data" / "processed"
    results_dir = SCRIPT_DIR / "tariff_research" / "results" / "tables"
    results_dir.mkdir(parents=True, exist_ok=True)

    data = {}

    # 尝试加载真实数据
    files = {
        "panel": base / "tariff_panel_data.csv",
        "did": base / "did_panel_data.csv",
    }

    for name, path in files.items():
        if path.exists():
            df = pd.read_csv(path)
            # 尝试解析日期列
            for col in ["year", "date", "time"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
            data[name] = df
            print(f"  加载 {name}: {len(df)} 行")

    # 如果没有真实数据，生成模拟面板数据
    if not data:
        print("  未找到真实面板数据，生成模拟数据（演示用）")
        data["panel"] = _generate_mock_panel(seed=42)
        data["did"] = _generate_mock_did(seed=42)

    return data, results_dir


def _generate_mock_panel(seed: int = 42) -> pd.DataFrame:
    """生成模拟关税面板数据，用于演示表格生成功能"""
    np.random.seed(seed)
    n_firms = 300
    n_years = 9  # 2016-2024
    firms = [f"firm_{i:04d}" for i in range(n_firms)]
    years = list(range(2016, 2025))
    industries = ["制造业", "服务业", "信息技术", "化工业", "医药业"]

    records = []
    for firm in firms:
        industry = np.random.choice(industries)
        size = np.random.choice(["大型", "中型", "小型"], p=[0.3, 0.4, 0.3])
        base_tariff = np.random.uniform(3.0, 8.0)
        base_rd = np.random.uniform(0.05, 0.25)
        base_patent = np.random.randint(10, 500)

        for year in years:
            # 2018年贸易战后，关税显著上升
            post_2018 = 1 if year >= 2018 else 0
            tariff = base_tariff + post_2018 * np.random.uniform(10, 18)
            tariff_x_export = tariff * np.random.uniform(0.3, 0.9)

            # 创新指标：关税越高，专利产出越低（熊彼特效应）
            innovation_effect = -0.04 * post_2018 * (tariff / 10)
            rd_intensity = base_rd + 0.01 * post_2018 + np.random.normal(0, 0.02)
            rd_intensity = max(0.01, min(rd_intensity, 0.80))

            patent_growth = base_patent * (
                1 + innovation_effect + np.random.normal(0, 0.15)
            )
            patent_growth = max(1, patent_growth)

            # 宏观控制变量
            gdp_growth = np.random.uniform(0.02, 0.08) - post_2018 * 0.01
            cpi = 100 + year * 2 + np.random.normal(0, 5)

            records.append({
                "firm": firm,
                "industry": industry,
                "size": size,
                "year": year,
                "post": post_2018,
                "tariff": tariff,
                "tariff_x_export": tariff_x_export,
                "ln_patent": np.log(patent_growth + 1),
                "rd_intensity": rd_intensity,
                "ln_sales": np.random.uniform(8, 12),
                "leverage": np.random.uniform(0.1, 0.7),
                "roa": np.random.uniform(-0.05, 0.20),
                "gdp_growth": gdp_growth,
                "cpi": cpi,
                "export_ratio": np.random.uniform(0, 0.8),
            })

    df = pd.DataFrame(records)
    print(f"  模拟面板: {len(df)} 行 ({n_firms} 企业 × {n_years} 年)")
    return df


def _generate_mock_did(seed: int = 42) -> pd.DataFrame:
    """生成模拟 DID 面板数据"""
    np.random.seed(seed)
    treated_firms = [f"T_{i:04d}" for i in range(150)]
    control_firms = [f"C_{i:04d}" for i in range(150)]
    years = list(range(2014, 2025))

    records = []
    for firm in treated_firms:
        for year in years:
            post = 1 if year >= 2018 else 0
            effect = -0.035 * post + np.random.normal(0, 0.02)
            records.append({
                "firm": firm, "year": year, "treated": 1, "post": post,
                "employment": 100 * np.exp(0.02 * (year - 2014) + effect),
                "ln_sales": 10 + 0.08 * (year - 2014) + effect * 0.5 + np.random.normal(0, 0.1),
                "rd_intensity": 0.12 + 0.01 * post + np.random.normal(0, 0.02),
                "industry": np.random.choice(["制造业", "服务业"]),
            })
    for firm in control_firms:
        for year in years:
            records.append({
                "firm": firm, "year": year, "treated": 0, "post": 0,
                "employment": 100 * np.exp(0.02 * (year - 2014) + np.random.normal(0, 0.01)),
                "ln_sales": 10 + 0.08 * (year - 2014) + np.random.normal(0, 0.1),
                "rd_intensity": 0.10 + np.random.normal(0, 0.02),
                "industry": np.random.choice(["制造业", "服务业"]),
            })

    df = pd.DataFrame(records)
    print(f"  模拟DID: {len(df)} 行")
    return df


# ════════════════════════════════════════════════════════════════════
# 表格生成函数
# ════════════════════════════════════════════════════════════════════

def generate_descriptive_stats(df: pd.DataFrame, out_dir: Path) -> str:
    """描述性统计"""
    var_map = {
        "ln_patent": "ln(专利产出+1)",
        "rd_intensity": "R&D强度",
        "tariff": "关税税率（%）",
        "ln_sales": "ln(营业收入)",
        "leverage": "资产负债率",
        "roa": "资产收益率",
        "gdp_growth": "GDP增速",
        "export_ratio": "出口占比",
        "employment": "就业人数",
    }

    avail = [v for v in var_map if v in df.columns]
    labels = [var_map[v] for v in avail]

    desc = descriptive_stats(df, avail)
    md = table_to_markdown(desc, precision=4)

    # 替换变量名为中文标签
    for v, l in zip(avail, labels):
        md = md.replace("| " + v + " |", "| " + l + " |")

    out_path = out_dir / "descriptive_stats.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [1/6] 描述性统计 → {out_path.name}")
    return md


def generate_core_regression(df: pd.DataFrame, out_dir: Path) -> str:
    """核心基准回归：关税暴露对创新指标的影响"""
    results = RegressionTable(name="核心基准回归")

    if "ln_patent" in df.columns and "tariff" in df.columns:
        # 模型 1：仅关税
        m1 = OLSRegression(df, y="ln_patent")
        m1.fit("ln_patent ~ tariff", name="基准(1)")
        results.models.append(m1.result.models[0])
        results.coefs.append(m1.result.coefs[0])

        # 模型 2：加入企业控制变量
        m2 = OLSRegression(df, y="ln_patent")
        m2.fit("ln_patent ~ tariff + ln_sales + leverage + roa + gdp_growth", name="基准(2)")
        results.models.append(m2.result.models[0])
        results.coefs.append(m2.result.coefs[0])

        # 模型 3：加入时间固定效应
        if "year" in df.columns:
            m3 = OLSRegression(df, y="ln_patent")
            m3.fit("ln_patent ~ tariff + ln_sales + leverage + roa + C(year)", name="基准(3)")
            results.models.append(m3.result.models[0])
            results.coefs.append(m3.result.coefs[0])

        # 模型 4：聚类标准误（行业）
        if "industry" in df.columns:
            m4 = OLSRegression(df, y="ln_patent")
            m4.fit("ln_patent ~ tariff + ln_sales + leverage + roa + C(year)",
                   cluster="industry", name="基准(4)")
            results.models.append(m4.result.models[0])
            results.coefs.append(m4.result.coefs[0])

    if "rd_intensity" in df.columns and "tariff" in df.columns:
        m5 = OLSRegression(df, y="rd_intensity")
        m5.fit("rd_intensity ~ tariff + ln_sales + leverage", cluster="industry" if "industry" in df.columns else "", name="R&D(5)")
        results.models.append(m5.result.models[0])
        results.coefs.append(m5.result.coefs[0])

    md = table_to_markdown(results, precision=4)

    # 变量名中文映射
    rename = {
        "ln_patent": "ln(专利产出)", "rd_intensity": "R&D强度",
        "tariff": "关税税率", "ln_sales": "ln(营业收入)",
        "leverage": "资产负债率", "roa": "ROA",
        "gdp_growth": "GDP增速", "post": "政策后",
    }
    for en, cn in rename.items():
        md = md.replace("| " + en + " |", "| " + cn + " |")

    out_path = out_dir / "core_regression.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [2/6] 核心回归 → {out_path.name}")
    return md


def generate_did_regression(df: pd.DataFrame, out_dir: Path) -> str:
    """DID 双重差分分析"""
    results = RegressionTable(name="DID分析")

    if all(c in df.columns for c in ["employment", "treated", "post"]):
        # 标准 DID
        did = DIDRegression(df, y="employment",
                          treatment="treated", post="post",
                          unit="firm", time="year")
        did.fit(name="DID(1)")
        results.models.append(did.result.models[0])
        results.coefs.append(did.result.coefs[0])

        # 加入控制变量
        did2 = DIDRegression(df, y="employment",
                           treatment="treated", post="post",
                           unit="firm", time="year")
        did2.fit(controls=["ln_sales", "rd_intensity"], cluster="industry" if "industry" in df.columns else "",
                 name="DID(2)")
        results.models.append(did2.result.models[0])
        results.coefs.append(did2.result.coefs[0])

    if "ln_sales" in df.columns and "treated" in df.columns and "post" in df.columns:
        did3 = DIDRegression(df, y="ln_sales",
                           treatment="treated", post="post",
                           unit="firm", time="year")
        did3.fit(controls=["rd_intensity"], name="DID(3)")
        results.models.append(did3.result.models[0])
        results.coefs.append(did3.result.coefs[0])

    md = table_to_markdown(results, precision=4)
    rename = {"employment": "就业人数", "ln_sales": "ln(营业收入)",
              "rd_intensity": "R&D强度", "did": "DID交互项",
              "treated": "处理组", "post": "政策后"}
    for en, cn in rename.items():
        md = md.replace("| " + en + " |", "| " + cn + " |")

    out_path = out_dir / "did_regression.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [3/6] DID分析 → {out_path.name}")
    return md


def generate_heterogeneity(df: pd.DataFrame, out_dir: Path) -> str:
    """异质性分析：按行业/规模分组回归"""
    results = RegressionTable(name="异质性分析")

    if "industry" in df.columns and "ln_patent" in df.columns:
        for ind in df["industry"].unique():
            sub = df[df["industry"] == ind]
            if len(sub) > 30:
                m = OLSRegression(sub, y="ln_patent")
                m.fit("ln_patent ~ tariff + ln_sales + leverage",
                     name="行业=" + ind)
                results.models.append(m.result.models[0])
                results.coefs.append(m.result.coefs[0])

    if "size" in df.columns and "ln_patent" in df.columns:
        for sz in df["size"].unique():
            sub = df[df["size"] == sz]
            if len(sub) > 30:
                m = OLSRegression(sub, y="ln_patent")
                m.fit("ln_patent ~ tariff + ln_sales + leverage",
                     name="规模=" + sz)
                results.models.append(m.result.models[0])
                results.coefs.append(m.result.coefs[0])

    md = table_to_markdown(results, precision=4)
    rename = {"ln_patent": "ln(专利)", "tariff": "关税税率",
              "ln_sales": "ln(营收)", "leverage": "杠杆率"}
    for en, cn in rename.items():
        md = md.replace("| " + en + " |", "| " + cn + " |")

    out_path = out_dir / "heterogeneity.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [4/6] 异质性分析 → {out_path.name}")
    return md


def generate_mediation(df: pd.DataFrame, out_dir: Path) -> str:
    """中介效应：R&D 在关税→创新之间的中介作用"""
    results = RegressionTable(name="中介效应")

    if all(c in df.columns for c in ["ln_patent", "rd_intensity", "tariff"]):
        # 第一步：关税 → R&D强度
        m1 = OLSRegression(df, y="rd_intensity")
        m1.fit("rd_intensity ~ tariff + ln_sales", name="Step1(关税→R&D)")
        results.models.append(m1.result.models[0])
        results.coefs.append(m1.result.coefs[0])

        # 第二步：关税 + R&D → 专利
        m2 = OLSRegression(df, y="ln_patent")
        m2.fit("ln_patent ~ tariff + rd_intensity + ln_sales", name="Step2(中介)")
        results.models.append(m2.result.models[0])
        results.coefs.append(m2.result.coefs[0])

        # 第三步：仅R&D → 专利（间接路径）
        m3 = OLSRegression(df, y="ln_patent")
        m3.fit("ln_patent ~ rd_intensity + ln_sales", name="Step3(间接)")
        results.models.append(m3.result.models[0])
        results.coefs.append(m3.result.coefs[0])

    md = table_to_markdown(results, precision=4)
    rename = {"ln_patent": "ln(专利)", "rd_intensity": "R&D强度",
              "tariff": "关税税率", "ln_sales": "ln(营收)"}
    for en, cn in rename.items():
        md = md.replace("| " + en + " |", "| " + cn + " |")

    out_path = out_dir / "mediation.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [5/6] 中介效应 → {out_path.name}")
    return md


def generate_robustness(df: pd.DataFrame, out_dir: Path) -> str:
    """稳健性检验"""
    results = RegressionTable(name="稳健性检验")

    if "ln_patent" not in df.columns or "tariff" not in df.columns:
        out_path = out_dir / "robustness.md"
        out_path.write_text("# 稳健性检验\n\n（数据不足，跳过）", encoding="utf-8")
        return ""

    # 基准模型
    base = OLSRegression(df, y="ln_patent")
    base.fit("ln_patent ~ tariff + ln_sales + leverage + C(year)",
             cluster="industry" if "industry" in df.columns else "", name="基准回归")
    results.models.append(base.result.models[0])
    results.coefs.append(base.result.coefs[0])

    # 缩尾 1%
    df_w = winsorize_all(df, ["ln_patent", "tariff", "ln_sales"], 0.01, 0.99)
    m1 = OLSRegression(df_w, y="ln_patent")
    m1.fit("ln_patent ~ tariff + ln_sales + leverage + C(year)",
           cluster="industry" if "industry" in df.columns else "", name="缩尾1%")
    results.models.append(m1.result.models[0])
    results.coefs.append(m1.result.coefs[0])

    # 剔除金融危机年份（2018-2019）
    if "year" in df.columns:
        df_sub = df[df["year"] >= 2020]
        if len(df_sub) > 50:
            m2 = OLSRegression(df_sub, y="ln_patent")
            m2.fit("ln_patent ~ tariff + ln_sales + leverage + C(year)",
                   name="剔除2018-19")
            results.models.append(m2.result.models[0])
            results.coefs.append(m2.result.coefs[0])

    md = table_to_markdown(results, precision=4)
    rename = {"ln_patent": "ln(专利)", "tariff": "关税税率",
              "ln_sales": "ln(营收)", "leverage": "杠杆率"}
    for en, cn in rename.items():
        md = md.replace("| " + en + " |", "| " + cn + " |")

    out_path = out_dir / "robustness.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  [6/6] 稳健性检验 → {out_path.name}")
    return md


# ════════════════════════════════════════════════════════════════════
# 主函数
# ════════════════════════════════════════════════════════════════════

def generate_all_tables() -> dict[str, str]:
    """生成所有实证表格，返回 {name: markdown} 字典"""
    print("\n" + "=" * 60)
    print("  实证表格生成器 v1.0")
    print("  " + "=" * 60)

    data, out_dir = load_tariff_data()

    tables = {}
    panel = data.get("panel")
    did_data = data.get("did")

    if panel is not None:
        tables["descriptive_md"] = generate_descriptive_stats(panel, out_dir)
        tables["core_findings_md"] = generate_core_regression(panel, out_dir)
        tables["heterogeneity_md"] = generate_heterogeneity(panel, out_dir)
        tables["mediation_md"] = generate_mediation(panel, out_dir)
        tables["robustness_md"] = generate_robustness(panel, out_dir)

    if did_data is not None:
        tables["did_summary_md"] = generate_did_regression(did_data, out_dir)

    print("\n  全部表格生成完毕！")
    return tables


def load_tables_from_files() -> dict[str, str]:
    """从已保存的 .md 文件加载表格（供 paper_full_pipeline.py 调用）"""
    out_dir = SCRIPT_DIR / "tariff_research" / "results" / "tables"
    mapping = {
        "descriptive_md": "descriptive_stats.md",
        "core_findings_md": "core_regression.md",
        "did_summary_md": "did_regression.md",
        "heterogeneity_md": "heterogeneity.md",
        "mediation_md": "mediation.md",
        "robustness_md": "robustness.md",
    }

    tables = {}
    for key, fname in mapping.items():
        path = out_dir / fname
        if path.exists():
            tables[key] = path.read_text(encoding="utf-8")
        else:
            tables[key] = ""
    return tables


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="实证表格生成器")
    parser.add_argument("--regression", choices=["core", "did", "heterogeneity",
                        "mediation", "robustness", "descriptive"],
                       help="仅生成指定类型的表格")
    args = parser.parse_args()

    tables = generate_all_tables()

    if args and args.regression:
        key = args.regression + "_md"
        if key in tables:
            print("\n" + tables[key])
