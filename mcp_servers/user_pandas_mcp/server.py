#!/usr/bin/env python3
"""
user-pandas-mcp — Pandas数据分析MCP服务器
===========================================
在MCP对话中直接操作DataFrame、执行数据分析。

功能：
  - 描述性统计（describe, info, value_counts）
  - 数据清洗（fillna, dropna, drop_duplicates, clip）
  - 筛选和切片（行/列/条件筛选）
  - 分组聚合（groupby + agg）
  - 数据合并（merge, concat, join）
  - 相关性分析（corr, covariance）
  - 排序和排名（sort_values, rank）
  - 数据透视（pivot_table, crosstab）
  - 类型转换和派生（astype, apply, map）
  - 数据导出（to_csv, to_json, to_clipboard）
  - SQL风格查询（pandasql）
  - 时间序列分析（resample, rolling, shifting）

Usage:
    python server.py [--data-dir DIR]
"""

from __future__ import annotations

import io
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. Run: pip install mcp", flush=True)
    sys.exit(1)

import pandas as pd
import numpy as np

server = Server("user-pandas-mcp")


# ─────────────────────────────────────────────────────────────────────────────
# 数据存储（会话内持久化）
# ─────────────────────────────────────────────────────────────────────────────
# 在进程内维护数据框字典，供多工具调用共享
_DATASETS: dict[str, pd.DataFrame] = {}
_DATA_DIR: str = ""


def _load_df(name_or_path: str) -> pd.DataFrame | None:
    """加载数据框。"""
    if name_or_path in _DATASETS:
        return _DATASETS[name_or_path]

    p = Path(name_or_path)
    if not p.exists():
        p = Path(_DATA_DIR) / name_or_path
    if not p.exists():
        return None

    try:
        if p.suffix == ".csv":
            df = pd.read_csv(p, encoding="utf-8")
        elif p.suffix == ".json":
            df = pd.read_json(p, encoding="utf-8")
        elif p.suffix in (".xlsx", ".xls"):
            df = pd.read_excel(p)
        elif p.suffix == ".parquet":
            df = pd.read_parquet(p)
        elif p.suffix == ".tsv":
            df = pd.read_csv(p, sep="\t", encoding="utf-8")
        else:
            return None

        key = p.stem if str(p) == name_or_path else name_or_path
        _DATASETS[key] = df
        return df
    except Exception:
        return None


def _store_df(name: str, df: pd.DataFrame) -> None:
    """存储数据框。"""
    _DATASETS[name] = df


def _df_summary(df: pd.DataFrame, max_rows: int = 20, max_cols: int = 15) -> dict:
    """生成数据框摘要。"""
    summary = {
        "name": "DataFrame",
        "shape": list(df.shape),
        "rows": len(df),
        "columns": len(df.columns),
        "column_types": {},
        "null_counts": {},
        "numeric_stats": {},
        "preview": "",
    }

    for col in df.columns:
        summary["column_types"][col] = str(df[col].dtype)
        summary["null_counts"][col] = int(df[col].isnull().sum())

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        desc = df[numeric_cols].describe().to_dict()
        summary["numeric_stats"] = {k: {kk: round(float(vv), 4) if isinstance(vv, (float, np.floating)) else vv
                                         for kk, vv in v.items()}
                                    for k, v in desc.items()}

    preview_df = df.head(max_rows)
    summary["preview"] = preview_df.to_csv(index=False, max_colwidth=30)

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="pd_read",
        description="读取CSV/JSON/Excel/Parquet文件到DataFrame并注册到会话。\n\n"
                    "Args:\n"
                    "  path: 文件路径（绝对路径或相对于data_dir）\n"
                    "  name: 可选，注册名称（默认用文件名）\n"
                    "  encoding: 文件编码（默认utf-8）\n\n"
                    "Returns: 数据框摘要",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "name": {"type": "string", "description": "注册名称"},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="pd_describe",
        description="生成描述性统计（均值/标准差/分位数/极值等）。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  columns: 可选，指定列（空=全部数值列）\n"
                    "  percentiles: 自定义分位数\n\n"
                    "Returns: 描述性统计表",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "数据框名称"},
                "columns": {"type": "array", "items": {"type": "string"}, "description": "列名列表"},
                "percentiles": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="pd_filter",
        description="按条件筛选数据行（类似SQL WHERE）。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  conditions: 筛选条件列表，如 [\"col > 0\", \"name == 'A'\"]\n"
                    "  combinator: 多条件组合方式（and/or）\n"
                    "  save_as: 保存结果的数据框名称\n\n"
                    "Returns: 筛选后的数据框摘要",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "数据框名称"},
                "conditions": {"type": "array", "items": {"type": "string"}, "description": "筛选条件"},
                "combinator": {"type": "string", "enum": ["and", "or"], "default": "and"},
                "save_as": {"type": "string", "description": "结果保存名称"},
            },
            "required": ["name", "conditions"],
        },
    ),
    Tool(
        name="pd_groupby_agg",
        description="分组聚合分析（groupby + agg）。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  group_by: 分组列\n"
                    "  agg_dict: 聚合规则，如 {\"col1\": [\"mean\",\"sum\"], \"col2\": [\"count\"]}\n"
                    "  save_as: 保存结果的数据框名称\n\n"
                    "Returns: 分组聚合结果",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "数据框名称"},
                "group_by": {"type": "array", "items": {"type": "string"}, "description": "分组列"},
                "agg_dict": {"type": "object", "description": "聚合规则"},
                "save_as": {"type": "string"},
            },
            "required": ["name", "group_by", "agg_dict"],
        },
    ),
    Tool(
        name="pd_merge",
        description="合并两个数据框（merge/concat/join）。\n\n"
                    "Args:\n"
                    "  left_name: 左侧数据框\n"
                    "  right_name: 右侧数据框\n"
                    "  how: 合并方式（inner/left/right/outer）\n"
                    "  on: 合并键\n"
                    "  save_as: 保存结果的数据框名称\n\n"
                    "Returns: 合并后的数据框摘要",
        inputSchema={
            "type": "object",
            "properties": {
                "left_name": {"type": "string"},
                "right_name": {"type": "string"},
                "how": {"type": "string", "enum": ["inner", "left", "right", "outer"], "default": "inner"},
                "on": {"type": "string", "description": "合并键列名"},
                "save_as": {"type": "string"},
            },
            "required": ["left_name", "right_name", "on"],
        },
    ),
    Tool(
        name="pd_transform",
        description="数据转换和派生新列。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  operations: 操作列表，如 [{\"col\": \"new_col\", \"expr\": \"col1 / col2\"}]\n"
                    "  fillna_value: 缺失值填充\n"
                    "  save_as: 保存结果的数据框名称\n\n"
                    "Returns: 转换后的数据框摘要",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "col": {"type": "string"},
                            "expr": {"type": "string"},
                            "type": {"type": "string", "description": "操作类型: assign/dropna/fillna/astype/sort_values"},
                        },
                    },
                    "description": "转换操作列表",
                },
                "fillna_value": {"type": "number"},
                "save_as": {"type": "string"},
            },
            "required": ["name", "operations"],
        },
    ),
    Tool(
        name="pd_corr_analysis",
        description="相关性分析（Pearson/Spearman/Kendall）+ 热力图数据生成。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  columns: 分析列（空=全部数值列）\n"
                    "  method: 相关系数方法\n\n"
                    "Returns: 相关性矩阵（CSV格式）",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "method": {"type": "string", "enum": ["pearson", "spearman", "kendall"], "default": "pearson"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="pd_pivot",
        description="数据透视表分析。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  index: 行索引\n"
                    "  columns: 列索引\n"
                    "  values: 值列\n"
                    "  aggfunc: 聚合函数\n"
                    "  fill_value: 缺失值填充\n"
                    "  save_as: 保存结果\n\n"
                    "Returns: 透视表",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "index": {"type": "string"},
                "columns": {"type": "string"},
                "values": {"type": "string"},
                "aggfunc": {"type": "string", "enum": ["mean", "sum", "count", "std", "min", "max"], "default": "mean"},
                "fill_value": {"type": "number"},
                "save_as": {"type": "string"},
            },
            "required": ["name", "index", "values"],
        },
    ),
    Tool(
        name="pd_export",
        description="导出数据框到CSV/JSON/Excel。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  path: 输出文件路径\n"
                    "  format: 格式（csv/json/excel）\n"
                    "  max_rows: 最大行数\n\n"
                    "Returns: 导出结果",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string"},
                "format": {"type": "string", "enum": ["csv", "json", "excel", "clipboard"], "default": "csv"},
                "max_rows": {"type": "integer"},
            },
            "required": ["name", "path"],
        },
    ),
    Tool(
        name="pd_summary",
        description="获取数据框概览（info + describe + null counts + head）。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  max_preview_rows: 预览行数\n\n"
                    "Returns: 完整数据框报告",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "max_preview_rows": {"type": "integer", "default": 10},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="pd_list_datasets",
        description="列出当前会话中所有已注册的数据框及其摘要。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="pd_sql",
        description="使用SQL查询数据框（pandasql）。\n\n"
                    "Args:\n"
                    "  query: SQL语句\n"
                    "  save_as: 保存结果的数据框名称\n\n"
                    "Returns: 查询结果",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "save_as": {"type": "string"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="pd_head",
        description="查看数据框前N行。\n\n"
                    "Args:\n"
                    "  name: 数据框名称\n"
                    "  n: 行数\n\n"
                    "Returns: 数据预览",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "n": {"type": "integer", "default": 10},
            },
            "required": ["name"],
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具处理函数
# ─────────────────────────────────────────────────────────────────────────────

async def handle_pd_read(args: dict) -> list[TextContent]:
    path = args["path"]
    name = args.get("name", "")
    encoding = args.get("encoding", "utf-8")

    df = _load_df(path)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Could not load: {path}", "supported": [".csv", ".json", ".xlsx", ".xls", ".parquet", ".tsv"]}))]

    key = name or Path(path).stem
    _store_df(key, df)
    return [TextContent(type="text", text=json.dumps(_df_summary(df), ensure_ascii=False, indent=2))]


async def handle_pd_describe(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    cols = args.get("columns") or None
    percentiles = args.get("percentiles", [0.25, 0.5, 0.75])
    desc = df[cols].describe(percentiles=percentiles).to_dict() if cols else df.describe(percentiles=percentiles).to_dict()

    out = {}
    for k, v in desc.items():
        out[k] = {kk: round(float(vv), 4) if isinstance(vv, (float, np.floating)) else vv
                     for kk, vv in v.items()}

    return [TextContent(type="text", text=json.dumps({"name": name, "stats": out}, ensure_ascii=False, indent=2))]


async def handle_pd_filter(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    conditions = args.get("conditions", [])
    combinator = args.get("combinator", "and")
    save_as = args.get("save_as", "")

    mask = pd.Series([True] * len(df), index=df.index)
    for cond in conditions:
        try:
            cond_mask = df.eval(cond, inplace=False)
            if combinator == "and":
                mask &= cond_mask
            else:
                mask |= cond_mask
        except Exception:
            return [TextContent(type="text", text=json.dumps({"error": f"Invalid condition: {cond}"}))]

    result = df[mask]
    if save_as:
        _store_df(save_as, result)

    summary = _df_summary(result)
    summary["original_rows"] = len(df)
    summary["filtered_rows"] = len(result)
    summary["removed_rows"] = len(df) - len(result)
    if save_as:
        summary["saved_as"] = save_as
    return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]


async def handle_pd_groupby_agg(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    group_by = args.get("group_by", [])
    agg_dict = args.get("agg_dict", {})
    save_as = args.get("save_as", "")

    try:
        grouped = df.groupby(group_by).agg(agg_dict)
        if save_as:
            _store_df(save_as, grouped.reset_index())

        return [TextContent(type="text", text=json.dumps({
            "name": name,
            "group_by": group_by,
            "result_shape": list(grouped.shape),
            "result_preview": grouped.reset_index().head(20).to_csv(index=False, max_colwidth=25),
            "saved_as": save_as if save_as else None,
        }, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_pd_merge(args: dict) -> list[TextContent]:
    left = _DATASETS.get(args["left_name"])
    right = _DATASETS.get(args["right_name"])
    if left is None or right is None:
        return [TextContent(type="text", text=json.dumps({"error": "One or both DataFrames not found"}))]

    on = args.get("on")
    how = args.get("how", "inner")
    save_as = args.get("save_as", "")

    try:
        merged = pd.merge(left, right, on=on, how=how)
        if save_as:
            _store_df(save_as, merged)

        return [TextContent(type="text", text=json.dumps(_df_summary(merged), ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_pd_transform(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    df = df.copy()
    fillna_val = args.get("fillna_value")
    save_as = args.get("save_as", name)

    for op in args.get("operations", []):
        try:
            if op.get("type") == "assign" or "expr" in op:
                df[op["col"]] = df.eval(op["expr"])
            elif op.get("type") == "dropna":
                df = df.dropna(subset=op.get("subset", None) or None)
            elif op.get("type") == "fillna":
                df = df.fillna(fillna_val if fillna_val is not None else 0)
            elif op.get("type") == "astype":
                df[op["col"]] = df[op["col"]].astype(op.get("dtype", "float"))
            elif op.get("type") == "sort_values":
                df = df.sort_values(by=op.get("by", op["col"]), ascending=op.get("ascending", True))
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": f"Transform error: {e}"}))]

    _store_df(save_as, df)
    summary = _df_summary(df)
    summary["transformed"] = True
    summary["saved_as"] = save_as
    return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]


async def handle_pd_corr_analysis(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    cols = args.get("columns") or None
    method = args.get("method", "pearson")

    numeric = df.select_dtypes(include=[np.number])
    corr_df = numeric.corr(method=method) if cols is None else numeric[cols].corr(method=method)

    return [TextContent(type="text", text=json.dumps({
        "name": name,
        "method": method,
        "correlation_matrix": corr_df.round(4).to_dict(),
        "preview": corr_df.round(3).to_csv(max_colwidth=20),
    }, ensure_ascii=False, indent=2))]


async def handle_pd_pivot(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    fill_val = args.get("fill_value")
    aggfunc = args.get("aggfunc", "mean")
    save_as = args.get("save_as", "")

    try:
        pivot = pd.pivot_table(df, index=args["index"], columns=args.get("columns"),
                              values=args["values"], aggfunc=aggfunc, fill_value=fill_val)
        if save_as:
            _store_df(save_as, pivot.reset_index())

        return [TextContent(type="text", text=json.dumps({
            "shape": list(pivot.shape),
            "preview": pivot.reset_index().head(20).to_csv(index=False, max_colwidth=25),
            "saved_as": save_as or None,
        }, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_pd_export(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    path = args["path"]
    fmt = args.get("format", "csv")
    max_rows = args.get("max_rows")

    export_df = df.head(max_rows) if max_rows else df
    try:
        if fmt == "csv":
            export_df.to_csv(path, index=False, encoding="utf-8")
        elif fmt == "json":
            export_df.to_json(path, orient="records", force_ascii=False, indent=2)
        elif fmt == "excel":
            export_df.to_excel(path, index=False)
        elif fmt == "clipboard":
            export_df.to_clipboard(index=False)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "path": path,
            "rows": len(export_df),
            "format": fmt,
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_pd_summary(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    max_rows = args.get("max_preview_rows", 10)
    return [TextContent(type="text", text=json.dumps(_df_summary(df, max_rows), ensure_ascii=False, indent=2))]


async def handle_pd_list_datasets(args: dict) -> list[TextContent]:
    result = {}
    for k, df in _DATASETS.items():
        result[k] = {"shape": list(df.shape), "columns": list(df.columns), "dtypes": {c: str(dt) for c, dt in df.dtypes.items()}}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def handle_pd_sql(args: dict) -> list[TextContent]:
    query = args["query"]
    save_as = args.get("save_as", "")

    try:
        from pandasql import sqldf
        result = sqldf(query, _DATASETS)
        if save_as:
            _store_df(save_as, result)

        return [TextContent(type="text", text=json.dumps({
            "rows": len(result),
            "columns": list(result.columns),
            "preview": result.head(20).to_csv(index=False, max_colwidth=25),
            "saved_as": save_as or None,
        }, ensure_ascii=False, indent=2))]
    except ImportError:
        return [TextContent(type="text", text=json.dumps({"error": "pandasql not installed. Run: pip install pandasql"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_pd_head(args: dict) -> list[TextContent]:
    name = args["name"]
    df = _DATASETS.get(name)
    if df is None:
        return [TextContent(type="text", text=json.dumps({"error": f"DataFrame '{name}' not found"}))]

    n = args.get("n", 10)
    return [TextContent(type="text", text=df.head(n).to_csv(index=False, max_colwidth=30))]


TOOL_HANDLERS = {
    "pd_read": handle_pd_read,
    "pd_describe": handle_pd_describe,
    "pd_filter": handle_pd_filter,
    "pd_groupby_agg": handle_pd_groupby_agg,
    "pd_merge": handle_pd_merge,
    "pd_transform": handle_pd_transform,
    "pd_corr_analysis": handle_pd_corr_analysis,
    "pd_pivot": handle_pd_pivot,
    "pd_export": handle_pd_export,
    "pd_summary": handle_pd_summary,
    "pd_list_datasets": handle_pd_list_datasets,
    "pd_sql": handle_pd_sql,
    "pd_head": handle_pd_head,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def main():
    print(f"user-pandas-mcp starting... pandas {pd.__version__}, numpy {np.__version__}", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-pandas-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
