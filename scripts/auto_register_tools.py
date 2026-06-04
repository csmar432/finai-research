#!/usr/bin/env python3
"""
为 tool_selector.py 的 TOOL_REGISTRY_BASE 补全缺失的逻辑工具注册。

TOOL_REGISTRY_BASE 使用"逻辑工具名"（如 tushare, province_indicator），
MCP_TOOL_SERVER_MAP 中每个条目就是一对：逻辑名 → (实际MCP工具, 服务器名)。
本脚本从 MAP 提取所有逻辑工具名，补充到 REGISTRY_BASE 中。
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent  # 工作区根目录

# ── 逻辑名 → task_types 推断规则 ─────────────────────────────────────────────
TOOL_TYPE_RULES = [
    (["province", "timeseries", "rankings", "summary"], ["DATA_FETCH", "ANALYSIS"]),
    (["research_report", "stock_news", "analyst"], ["DATA_FETCH", "LITERATURE"]),
    (["financial", "margin", "index", "calendar", "stock_basic",
      "daily_quote", "concept", "fund_nav", "fund_holdings", "fund_flow",
      "fund_performance", "bond", "repo", "forex", "commodity", "crypto",
      "shipping", "futures", "stock_index", "credit_spread", "futures"], ["DATA_FETCH"]),
    (["option_chain", "option_greeks", "option_vol"], ["DATA_FETCH"]),
    (["fed", "fomc", "beige", "interest_rate"], ["DATA_FETCH"]),
    (["wb_", "imf_", "oecd_", "macro_", "gdp", "cpi", "ppi", "pmi", "m2",
      "fdi", "retail", "population", "inflation", "unemployment", "trade",
      "industry", "consumer", "bop", "ifs", "weo", "employment", "tfp",
      "education_panel", "tech_panel", "rd_panel", "industry_panel",
      "nsti_report", "nipa", "gdi"], ["DATA_FETCH"]),
    (["nber", "paper_detail"], ["LITERATURE"]),
    (["fs_", "latex", "pd_", "pw_", "e2b_", "compile", "bibtex",
      "scaffold", "count_words", "render", "diff", "latex_diff",
      "latex_check", "latex_compile", "latex_to_pdf", "latex_render",
      "latex_scaffold"], ["CODE"]),
    (["navigate", "screenshot", "scrape_table", "scrape_json", "click",
      "fill_form", "download", "get_html", "search_click"], ["CODE"]),
    (["bea_", "csmar_", "enhanced_"], ["DATA_FETCH"]),
    (["nbs_fallback"], ["DATA_FETCH"]),
    (["wind"], ["DATA_FETCH"]),
]

# 已有描述（从现有 TOOL_REGISTRY_BASE 中提取）
DESCRIPTIONS = {
    "arxiv": "ArXiv学术论文检索和下载",
    "brave_search": "财经新闻、政策文件网络检索",
    "fetch": "网页正文抓取",
    "context7": "官方API文档查询",
    "financial": "宏观经济、行情、crypto（yfinance/FRED）",
    "finviz_sec": "美股筛选、90+基本面、SEC文件",
    "eastmoney_reports": "东方财富研报",
    "tushare": "A股日线、财务、指数、概念板块数据（Tushare Pro）",
    "fetch_a_stock": "A股日线数据（akshare）",
    "econometrics_regression": "OLS/DID回归（statsmodels）",
    "report_generator": "研报生成+可视化图表",
    "dashboard": "Streamlit监控仪表盘",
    "province_indicator": "查询指定省份单一指标（GDP/R&D经费/高新技术企业等）",
    "province_timeseries": "获取指定省份指标的多年面板序列",
    "province_rankings": "获取全国各省排名表（GDP/R&D经费/高新技术企业排名）",
    "province_summary": "获取所有收录省份的概览信息（含核查状态、数据覆盖范围）",
}

def infer_task_types(name: str) -> list[str]:
    for patterns, types in TOOL_TYPE_RULES:
        for p in patterns:
            if p in name:
                return types
    return ["DATA_FETCH"]

def make_description(name: str) -> str:
    """从名称推断描述"""
    if name.startswith("fs_"):
        return f"文件系统操作: {name.replace('fs_', '')}"
    if name.startswith("latex"):
        return f"LaTeX工具: {name.replace('latex_', '')}"
    if name.startswith("pd_"):
        return f"数据分析: {name.replace('pd_', '')}"
    if name.startswith("pw_"):
        return f"浏览器自动化: {name.replace('pw_', '')}"
    if name.startswith("e2b_"):
        return f"云端代码执行: {name.replace('e2b_', '')}"
    if name.startswith("get_"):
        parts = name.replace("_", " ").split()
        return f"获取{name.replace('get_', '').replace('_', ' ')}数据"
    return name

def main():
    content = Path("scripts/core/tool_selector.py").read_text()

    # 已有注册
    existing = set(re.findall(r'TOOL_REGISTRY_BASE\["([^"]+)"\]', content))
    print(f"已有注册: {len(existing)} 个")

    # 从 MCP_TOOL_SERVER_MAP 提取所有逻辑工具名
    map_match = re.search(r'MCP_TOOL_SERVER_MAP.*?=\s*\{(.*?)\n    \}', content, re.DOTALL)
    if not map_match:
        print("错误：找不到 MCP_TOOL_SERVER_MAP")
        return

    map_text = map_match.group(1)
    # Format: "logical_name": ("actual_mcp_tool", "server_name"),
    map_entries = re.findall(r'"([^"]+)":\s*\("([^"]+)",\s*"([^"]+)"', map_text)
    logical_names = sorted(set(e[0] for e in map_entries))
    print(f"MCP_TOOL_SERVER_MAP 逻辑工具名: {len(logical_names)} 个")

    # 新增
    missing = [n for n in logical_names if n not in existing]
    print(f"缺失注册: {len(missing)} 个")

    new_entries = []
    for name in missing:
        task_types = infer_task_types(name)
        task_types_str = ", ".join(f"TaskType.{t}" for t in task_types)
        desc = DESCRIPTIONS.get(name, make_description(name))[:120]

        entry = f'''
        cls.TOOL_REGISTRY_BASE["{name}"] = ToolCapability(
            name="{name}",
            task_types=[{task_types_str}],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="{desc}",
            callable=None,
        )'''
        new_entries.append(entry)

    if not new_entries:
        print("\n无需修改。")
        return

    # 插入到 _registry_initialized = True 之前
    insert_marker = "cls._registry_initialized = True"
    pos = content.rfind(insert_marker)
    new_content = content[:pos] + "\n".join(new_entries) + "\n        " + content[pos:]

    out = Path("scripts/core/tool_selector.py.new")
    out.write_text(new_content)

    print(f"\n生成 {out}")
    print(f"新增 {len(new_entries)} 个工具注册")

    # 语法检查
    venv_python = ROOT / ".venv" / "bin" / "python"
    result = subprocess.run(
        [str(venv_python), "-m", "py_compile", str(out)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ 语法检查通过")
    else:
        print(f"❌ 语法错误:\n{result.stderr[:500]}")

    print("\n应用修改: mv scripts/core/tool_selector.py.new scripts/core/tool_selector.py")


if __name__ == "__main__":
    main()
