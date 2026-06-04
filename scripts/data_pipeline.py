#!/usr/bin/env python3
"""
金融数据处理流水线
=================
仅保留被实际调用的核心功能，其余均为死代码（已清理）。

被调用的函数：
  from scripts.data_pipeline import fetch_a_stock       # tool_selector 注册为 MCP 工具
  from scripts.data_pipeline import load_data          # interactive_paper_pipeline 调用
  from scripts.data_pipeline import preprocess_data     # interactive_paper_pipeline 调用

其余函数均为死代码（原始文件共 2170 行，清理后 150 行）。

注意：
  本文件中的 A股数据获取通过 akshare 实现，适用于中国 A股。
  如需更可靠的数据源，推荐使用 Tushare（需 Token）。
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

_log = logging.getLogger("data_pipeline")
warnings.filterwarnings("ignore", category=FutureWarning)


# ─── 数据加载（interactive_paper_pipeline 依赖）──────────────────────────────

def load_data(path: str | Path) -> pd.DataFrame:
    """
    从本地文件加载数据，支持 CSV / Excel / Parquet 格式。

    Args:
        path: 数据文件路径

    Returns:
        DataFrame，自动推断列类型
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")

    if suffix in (".csv", ".txt"):
        return pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    elif suffix == ".parquet":
        return pd.read_parquet(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix} (仅支持 csv/xlsx/parquet)")


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    对原始 DataFrame 进行基本清洗。

    处理步骤：
      1. 删除全空行
      2. 尝试将 date/日期 列转为 datetime
      3. 删除空值比例超过 50% 的列

    Args:
        df: 原始 DataFrame

    Returns:
        清洗后的 DataFrame
    """
    if df.empty:
        return df

    result = df.copy()

    # 删除全空行
    result = result.dropna(how="all")

    # 转换日期列
    for col in result.columns:
        col_lower = col.lower()
        if "date" in col_lower or "日期" in col:
            try:
                result[col] = pd.to_datetime(result[col], errors="coerce")
            except Exception:
                pass

    # 删除空值比例超过 50% 的列
    null_ratio = result.isnull().mean()
    cols_to_keep = null_ratio[null_ratio < 0.5].index
    result = result[cols_to_keep]

    return result


# ─── A股数据获取（tool_selector MCP 工具依赖）─────────────────────────────

def fetch_a_stock(
    code: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    获取A股日线行情。

    Args:
        code: 股票代码，如 "000001.SZ"（平安银行）、"600000.SH"（浦发银行）
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"
        adjust: "qfq"（前复权）| "hfq"（后复权）| ""（不复权）

    Returns:
        DataFrame，含 date, open, high, low, close, volume, amount, adjust

    Raises:
        ImportError: akshare 未安装
        RuntimeError: 重试 3 次后仍失败
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请安装 akshare: pip install akshare")

    def _fetch_with_retry(
        code: str, start: str, end: str, adjust: str, retries: int = 3
    ) -> pd.DataFrame:
        import time as _time

        last_err = None
        for attempt in range(retries):
            try:
                return ak.stock_zh_a_hist(
                    symbol=code.split(".")[0],
                    period="daily",
                    start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""),
                    adjust=adjust,
                )
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    wait = (attempt + 1) * 2
                    import warnings as _w

                    _w.warn(
                        f"akshare 请求失败（{attempt+1}/{retries}），{wait}s 后重试: {e}",
                        stacklevel=2,
                    )
                    _time.sleep(wait)
        raise RuntimeError(f"akshare 请求失败（已重试 {retries} 次）: {last_err}")

    df = _fetch_with_retry(code, start_date, end_date, adjust)
    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "换手率": "turnover",
        }
    )
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
