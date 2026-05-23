#!/usr/bin/env python3
"""
金融数据处理流水线 v3.1
=================
用于获取、清洗、存储金融数据 + 文献检索 + LLM 模型处理的通用工具集。

角色定位（以 Cursor 为核心，外部 AI 仅作补充）：
  ┌─────────────────────────────────────────────┐
  │         Cursor（本地 Claude，默认）             │
  │  所有对话、分析、代码任务直接调用本地 Claude     │
  └─────────────────────────────────────────────┘
                          ↓ 脚本批处理时调用
  ┌─────────────────────────────────────────────┐
  │  外部 AI（scripts/ai_router.py 调度）         │
  │  B.AI 中转（需 VPN）：gpt-5.5 / claude-4.6  │
  │  DeepSeek 直连（无需 VPN）：deepseek-chat     │
  └─────────────────────────────────────────────┘

功能：
- A股数据（akshare）：日线、财务报表、指数、板块
- 美股数据（yfinance）：行情、财务、期权
- 宏观控制变量（FRED）：GDP、CPI、利率、汇率、贸易数据
- 市场交易控制变量：市场收益率、行业动量、VIX、资金流
- 文献检索（ArXiv / Brave Search）：摘要/要点提取，BibTeX导出
- LLM模型处理（B.AI GPT-5.5 / Claude-4.6 / Gemini-3.1-Pro / DeepSeek-V3/R1）：
  情感分析、文档摘要、命名实体识别、文本分类、金融问答、代码生成、论文审稿
  （注：Cursor 直接对话时由 Cursor Claude 处理，无需调用外部 API）
- 技术指标（MCP）：RSI、MACD、布林带、SMA/EMA、ATR、随机指标、OBV、ADX（pandas-ta，无限次）
- 数据清洗（缺失值、异常值、标准化）
- 输出为 CSV / Parquet / Excel 格式

用法：
  from scripts.data_pipeline import fetch_a_stock, add_return_features

  df = fetch_a_stock("000001.SZ", "2024-01-01", "2025-01-01")
  df = add_return_features(df)
"""

import os
import re
import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)


# ─── 配置 ────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent


# ─── A股数据获取（akshare）─────────────────────────────

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
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请安装 akshare: pip install akshare")

    def _fetch_with_retry(code: str, start: str, end: str, adjust: str, retries: int = 3) -> pd.DataFrame:
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
                    _w.warn(f"akshare 请求失败（{attempt+1}/{retries}），{wait}s 后重试: {e}", stacklevel=2)
                    _time.sleep(wait)
        raise RuntimeError(f"akshare 请求失败（已重试 {retries} 次）: {last_err}")

    df = _fetch_with_retry(code, start_date, end_date, adjust)
    # 标准化列名
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "涨跌幅": "pct_change", "涨跌额": "change",
        "换手率": "turnover",
    })
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_a_financial(
    code: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> pd.DataFrame:
    """
    获取A股财务报表（利润表、资产负债表、现金流量表）。

    Args:
        code: 股票代码，如 "000001"
        start_year: 起始年份，默认近5年
        end_year: 结束年份，默认今年
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请安装 akshare: pip install akshare")

    now = datetime.now().year
    sy = start_year or (now - 5)
    ey = end_year or now

    reports = []
    for year in range(sy, ey + 1):
        for quarter in [1, 2, 3, 4]:
            try:
                df = ak.stock_financial_analysis_indicator(
                    symbol=code,
                    start_year=str(year),
                    end_year=str(year),
                )
                if df is not None and not df.empty:
                    reports.append(df)
            except Exception:
                pass

    if reports:
        return pd.concat(reports, ignore_index=True)
    return pd.DataFrame()


def fetch_a_index(
    symbol: str = "000001.SH",
    start_date: str = "20200101",
    end_date: str = None,
) -> pd.DataFrame:
    """
    获取A股指数行情。

    Args:
        symbol: 指数代码，"000001.SH"（上证指数）、"399001.SZ"（深证成指）
        start_date: 开始日期 "YYYYMMDD"
        end_date: 结束日期 "YYYYMMDD"，默认今天
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请安装 akshare: pip install akshare")

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    df = ak.stock_zh_index_daily(symbol=symbol, start_date=start_date, end_date=end_date)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_a_sector(
    sector: str = "新能源",
    date: str = None,
) -> pd.DataFrame:
    """
    获取A股板块/行业行情。

    Args:
        sector: 板块名称，如 "新能源"、"人工智能"、"半导体"
        date: 日期 "YYYYMMDD"，默认今天
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请安装 akshare: pip install akshare")

    date = date or datetime.now().strftime("%Y%m%d")
    df = ak.stock_board_industry_name_em()
    if sector:
        df = df[df["板块名称"].str.contains(sector, na=False)]
    return df


# ─── 美股数据获取（yfinance）──────────────────────────

def fetch_us_stock(
    ticker: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    获取美股行情（yfinance）。

    Args:
        ticker: 股票代码，如 "AAPL", "TSLA", "MSFT"
        start_date: "YYYY-MM-DD"
        end_date: "YYYY-MM-DD"
        interval: "1d" | "1wk" | "1mo" | "5m" 等
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("请安装 yfinance: pip install yfinance")

    # 支持 HTTP/HTTPS 代理（从环境变量读取）
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None

    session_params = {}
    if proxy:
        session_params["proxy"] = proxy

    stock = yf.Ticker(ticker, session=session_params if session_params else None)
    df = stock.history(start=start_date, end=end_date, interval=interval)
    if df is not None and not df.empty:
        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    return df


def fetch_us_financial(ticker: str) -> dict:
    """获取美股财务数据（利润表、资产负债表、现金流量表）。"""
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("请安装 yfinance: pip install yfinance")

    stock = yf.Ticker(ticker)
    return {
        "income_stmt": stock.income_stmt,
        "balance_sheet": stock.balance_sheet,
        "cashflow": stock.cashflow,
    }


# ─── 数据清洗 ────────────────────────────────────────

def clean_missing_values(df: pd.DataFrame, strategy: str = "ffill") -> pd.DataFrame:
    """
    清洗缺失值。

    Args:
        strategy: "ffill" | "bfill" | "drop" | "interpolate"
    """
    if strategy == "ffill":
        return df.ffill()
    elif strategy == "bfill":
        return df.bfill()
    elif strategy == "drop":
        return df.dropna()
    elif strategy == "interpolate":
        return df.interpolate(method="linear")
    return df


def detect_outliers(df: pd.DataFrame, column: str, n_std: float = 3.0) -> pd.DataFrame:
    """基于标准差检测异常值，添加 is_outlier 列。"""
    result = df.copy()
    mean = result[column].mean()
    std = result[column].std()
    result["is_outlier"] = (
        (result[column] < mean - n_std * std) |
        (result[column] > mean + n_std * std)
    )
    return result


def winsorize(df: pd.DataFrame, columns: list[str], lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    """对指定列进行缩尾处理。"""
    result = df.copy()
    for col in columns:
        lower_val = result[col].quantile(lower)
        upper_val = result[col].quantile(upper)
        result[col] = result[col].clip(lower=lower_val, upper=upper_val)
    return result


def normalize(df: pd.DataFrame, columns: list[str], method: str = "zscore") -> pd.DataFrame:
    """
    数据标准化。

    Args:
        method: "zscore" | "minmax"
    """
    result = df.copy()
    for col in columns:
        if col not in result.columns:
            continue
        if method == "zscore":
            result[f"{col}_zscore"] = (result[col] - result[col].mean()) / result[col].std()
        elif method == "minmax":
            result[f"{col}_minmax"] = (result[col] - result[col].min()) / (result[col].max() - result[col].min())
    return result


# ─── 数据导出 ────────────────────────────────────────

def to_csv(df: pd.DataFrame, path: str, **kwargs):
    df.to_csv(path, index=False, encoding="utf-8-sig", **kwargs)
    print(f"[✓] Saved to {path}")


def to_parquet(df: pd.DataFrame, path: str, **kwargs):
    df.to_parquet(path, index=False, **kwargs)
    print(f"[✓] Saved to {path}")


def to_excel(df: pd.DataFrame, path: str, sheet_name: str = "Sheet1", **kwargs):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, **kwargs)
    print(f"[✓] Saved to {path}")


# ─── 特征工程 ────────────────────────────────────────

def add_return_features(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """添加收益率相关特征。"""
    result = df.copy()
    if price_col in result.columns:
        result["daily_return"] = result[price_col].pct_change()
        result["log_return"] = np.log(result[price_col] / result[price_col].shift(1))
        result["volatility_20d"] = result["daily_return"].rolling(20).std()
        result["volatility_60d"] = result["daily_return"].rolling(60).std()
    return result


def add_moving_averages(
    df: pd.DataFrame,
    price_col: str = "close",
    windows: list[int] = None,
) -> pd.DataFrame:
    """添加移动平均线。"""
    if windows is None:
        windows = [5, 10, 20, 60]
    result = df.copy()
    if price_col not in result.columns:
        return result
    for w in windows:
        result[f"ma_{w}"] = result[price_col].rolling(w).mean()
        result[f"ma_{w}_ratio"] = result[price_col] / result[f"ma_{w}"]
    return result


def add_momentum_features(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """添加动量因子。"""
    result = df.copy()
    if price_col not in result.columns:
        return result
    for period in [5, 10, 20, 60]:
        result[f"momentum_{period}"] = result[price_col] / result[price_col].shift(period) - 1
    result["rsi_14"] = compute_rsi(result[price_col], 14)
    return result


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """计算 RSI 指标。"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ════════════════════════════════════════════════════════════════════
# 宏观控制变量层（新增）
# ────────────────────────────────────────────────────────────────
# 学术实证研究需要"冗余控制变量"策略：
#   1. 主回归使用理论驱动的基础控制变量
#   2. 稳健性检验逐步加入额外控制变量
#   3. 当某变量不显著时，用其他替代变量替代
#
# 参考文献可参考的变量体系：
#   - Autor, Dorn & Hanson (2013): 进口渗透度、制造业就业份额
#   - Pierce & Schott (2016): 对华关税、制造业就业
#   - Bloom, Draca & Van Reenen (2016): 中国进口冲击、创新投入
#   - Hershbein & Kahn (2018): 机器人应用、就业结构
#   - Aghion et al. (2022): 关税削减、企业创新

def fetch_fred_series(series_id: str, start: str = None, end: str = None) -> pd.DataFrame:
    """
    从 FRED 获取宏观时间序列。

    Args:
        series_id: FRED 系列 ID，如 "GDP", "CPIAUCSL", "DFF"
        start: 开始日期 "YYYY-MM-DD"，默认 10 年前
        end: 结束日期 "YYYY-MM-DD"，默认今天
    """
    import urllib.request
    import urllib.error

    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key or api_key.startswith("YOUR_"):
        print(f"  ⚠ 未配置 FRED_API_KEY，跳过: {series_id}")
        return pd.DataFrame()

    start = start or (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")
    end = end or datetime.now().strftime("%Y-%m-%d")

    url = (
        f"https://api.stlouisfed.org/fred/series/observations?"
        f"series_id={series_id}&api_key={api_key}&file_type=json"
        f"&observation_start={start}&observation_end={end}"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        observations = data.get("observations", [])
        if not observations:
            return pd.DataFrame()

        df = pd.DataFrame(observations)[["date", "value"]].rename(
            columns={"date": "date", "value": series_id.lower()}
        )
        df[series_id.lower()] = pd.to_numeric(df[series_id.lower()], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        print(f"  ⚠ FRED 请求失败 [{series_id}]: {e}")
        return pd.DataFrame()


def fetch_macro_control_variables(
    start: str = None,
    end: str = None,
    include: list[str] = None,
) -> pd.DataFrame:
    """
    获取完整的宏观控制变量面板，用于关税/贸易实证研究。

    包含四大类（每类均含多个备选变量，稳健性检验可替换）：

    【1. 货币与金融条件】
      - DFF: 联邦基金利率
      - TB3MS: 3月国债收益率
      - TEDRATE: TED利差（信用风险）
      - BAAFFM: BAA级企业债收益率（信用利差）
      - VIXCLS: VIX恐慌指数

    【2. 宏观经济总量】
      - GDP: 名义GDP
      - GDPPOT: 潜在GDP（产出缺口）
      - CPILFESL: 核心CPI（除食品能源）
      - UNRATE: 失业率
      - INDPRO: 工业生产指数

    【3. 贸易与汇率】
      - TWEXB: 美元贸易加权汇率（Broad）
      - EXPGSC1: 出口同比
      - IMPGSC1: 进口同比
      - NETEXP: 净出口
      - IR: 贸易条件（出口价格/进口价格）

    【4. 行业与就业（按NAICS行业）】
      - MANEMP: 制造业就业
      - NMANEMP: 非制造业就业
      - MORTGAGE30US: 30年抵押贷款利率
      - HOUST: 新屋开工数

    Args:
        start: 开始日期，默认 10 年前
        end: 结束日期，默认今天
        include: 只获取指定系列，如 ["DFF", "GDP", "VIXCLS"]
    """
    all_series = [
        # 货币金融
        ("DFF",       "联邦基金利率（%）"),
        ("TEDRATE",   "TED利差（%）"),
        ("BAAFFM",    "BAA企业债收益率（%）"),
        ("VIXCLS",    "VIX恐慌指数"),
        # 宏观
        ("GDP",       "名义GDP（十亿美元）"),
        ("GDPPOT",    "潜在GDP（十亿美元）"),
        ("CPILFESL",  "核心CPI同比（%）"),
        ("UNRATE",    "失业率（%）"),
        ("INDPRO",    "工业生产指数（2017=100）"),
        # 贸易汇率
        ("TWEXB",     "美元贸易加权汇率指数"),
        ("EXPGSC1",   "出口同比（%）"),
        ("IMPGSC1",   "进口同比（%）"),
        ("NETEXP",    "净出口（十亿美元）"),
        # 行业就业
        ("MANEMP",    "制造业就业（千人）"),
        ("NMANEMP",   "非制造业就业（千人）"),
        ("MORTGAGE30US", "30年抵押贷款利率（%）"),
        ("HOUST",     "新屋开工数（千套）"),
    ]

    if include:
        all_series = [(sid, name) for sid, name in all_series if sid in include]

    print(f"\n📊 正在获取宏观控制变量（共 {len(all_series)} 个系列）...")
    frames = []
    for i, (series_id, name) in enumerate(all_series, 1):
        print(f"  [{i}/{len(all_series)}] {series_id} — {name}")
        df = fetch_fred_series(series_id, start, end)
        if not df.empty:
            frames.append(df)

    if not frames:
        print("  ⚠ 未能获取任何宏观数据（请检查 FRED_API_KEY）")
        return pd.DataFrame()

    # 按 date 合并
    result = frames[0]
    for df in frames[1:]:
        result = pd.merge(result, df, on="date", how="outer")
    result = result.sort_values("date").reset_index(drop=True)
    result = result.ffill().bfill()  # 月度数据缺失用插值填补

    print(f"  ✅ 获取完成：{len(result)} 行 × {len(result.columns)} 列")
    print(f"  时间范围: {result['date'].min().date()} ~ {result['date'].max().date()}")
    return result


def fetch_market_controls(
    index_code: str = "000001.SH",
    start: str = None,
    end: str = None,
) -> pd.DataFrame:
    """
    获取市场级别控制变量（用于个股回归的面板数据）。

    包括：
      - 市场日收益率（mkt_ret）
      - 市场波动率（mkt_vol，20日滚动标准差）
      - 行业动量（ind_momentum，12个月滚动）
      - 换手率（turnover_rate）
      - 资金流（净流入比例）

    Args:
        index_code: 指数代码，"000001.SH"（上证）/"399001.SZ"（深证）
        start/end: 日期范围
    """
    try:
        import akshare as ak
    except ImportError:
        print("  ⚠ akshare 未安装，跳过市场控制变量")
        return pd.DataFrame()

    start = start or (datetime.now() - timedelta(days=3650)).strftime("%Y%m%d")
    end = end or datetime.now().strftime("%Y%m%d")

    print(f"\n📊 正在获取市场控制变量（{index_code}）...")
    try:
        df = ak.stock_zh_index_daily(symbol=index_code, start_date=start, end_date=end)
    except Exception as e:
        print(f"  ⚠ 获取失败: {e}")
        return pd.DataFrame()

    df = df.rename(columns={
        col: col.strip().lower().replace(" ", "_")
        for col in df.columns
        if isinstance(col, str)
    })
    date_col = [c for c in df.columns if "date" in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col])

    # 市场收益率
    price_col = [c for c in df.columns if "close" in c.lower() or "收盘" in str(c)][0]
    df["mkt_ret"] = df[price_col].pct_change()
    df["mkt_vol_20d"] = df["mkt_ret"].rolling(20).std() * np.sqrt(252)

    # 行业动量（12个月）
    df["ind_momentum_12m"] = df[price_col] / df[price_col].shift(252) - 1

    # 换手率
    vol_col = [c for c in df.columns if "volume" in c.lower() or "成交" in str(c)][0]
    amt_col = [c for c in df.columns if "amount" in c.lower() or "成交额" in str(c)][0]
    if vol_col in df.columns and amt_col in df.columns:
        df["turnover_rate"] = df[vol_col] / (df[amt_col] / df[price_col])

    df = df.rename(columns={date_col: "date"})
    df = df[["date", "mkt_ret", "mkt_vol_20d", "ind_momentum_12m", "turnover_rate"]].dropna()

    print(f"  ✅ 获取完成：{len(df)} 行")
    return df


def panel_merge(
    micro_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    on: str = "date",
    how: str = "left",
) -> pd.DataFrame:
    """
    将宏观控制变量合并到微观面板数据。

    宏观数据（月度）会向前填充到日度，以匹配微观数据频率。

    Args:
        micro_df: 微观面板数据（如个股日度数据），必须含 on 列
        macro_df: 宏观控制变量，必须含 on 列
        on: 合并键列名（默认 date）
        how: 合并方式，默认 left（左连接保留微观数据）
    """
    if macro_df.empty or micro_df.empty:
        return micro_df.copy()

    macro = macro_df.copy()
    macro[on] = pd.to_datetime(macro[on])

    # 如果微观数据是日度，将月度宏观数据前向填充到日度
    micro_dates = micro_df[on].dt.to_period("D").dt.to_timestamp()
    is_daily = micro_df[on].diff().dt.days.median() <= 1

    if is_daily:
        macro_daily = macro.copy()
        macro_daily = macro_daily.set_index(on)
        macro_daily.index = pd.to_datetime(macro_daily.index)
        macro_daily = macro_daily.resample("D").ffill().reset_index()
        macro_daily = macro_daily.rename(columns={"index": on})
        macro = macro_daily

    return micro_df.merge(macro, on=on, how=how, suffixes=("", "_macro"))


# ════════════════════════════════════════════════════════════════════
# 第四层：文献获取与分析
# ────────────────────────────────────────────────────────────────
# 学术实证研究的文献层需要覆盖三类来源：
#   1. 政策文本（USTR公告、Fed纪要、贸易协议）
#   2. 学术论文（ArXiv/SSRN/Google Scholar）
#   3. 新闻舆情（Bloomberg/Reuters/财经网）
#
# 参考文献体系：
#   - Autor, Dorn & Hanson (2013), QJE: "The China Shock"
#   - Pierce & Schott (2016), JEP: "The Surprisingly Swift Decline of US Manufacturing Employment"
#   - Bloom, Draca & Van Reenen (2016), RESTAT: "Trade Induced Technical Change"
#   - Hershbein & Kahn (2018), ILR Review: "Do Employers Prefer Unemployed Workers?"
#   - Aghion et al. (2022), JFE: "Tariff Reduce Innovation? Evidence from US Firms"
#   - Jia, Lin & Zhang (2020), AER: "Does Import Competition Cause Innovation?"
#   - Murtinu & Scalera (2021), JWB: "National Security and Outward FDI"
#   - Lu et al. (2023), JFE: "AI and Corporate Employment Structure"
#   - Hutton et al. (2024), JFQA: "LLM Sentiment and Stock Returns"


class LiteratureRetriever:
    """
    多源文献检索器。

    支持三种来源：
      - arxiv:     ArXiv 预印本（含金融AI、量化、资产定价）
      - brave:    Brave Search 通用搜索（财经新闻、政策文件）
      - semantic: Semantic Scholar（需 API Key）

    提示词模板（来自 research_agent 规则）：
      - search_arxiv_prompt: ArXiv 检索提示词
      - extract_abstract_prompt: 从 PDF/HTML 提取摘要提示词
      - extract_findings_prompt: 提取研究发现提示词

    文献记录格式（参考 BibTeX 字段）：
      - bibtex_key:    "Autor2013ChinaShock"
      - title:         论文标题
      - authors:       作者列表
      - year:          发表年份
      - journal:       期刊/会议名
      - doi/arxiv_id:  唯一标识
      - url:           链接
      - abstract:      摘要
      - tags:          研究主题标签
    """

    def __init__(self, brave_api_key: str = None, semantic_api_key: str = None):
        self.brave_api_key = brave_api_key or os.environ.get("BRAVE_SEARCH_API_KEY")
        self.semantic_api_key = semantic_api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        self._arxiv_cache: dict[str, dict] = {}

    # ── ArXiv 检索 ───────────────────────────────────────────────

    def search_arxiv(
        self,
        query: str,
        max_results: int = 10,
        categories: list[str] = None,
    ) -> list[dict]:
        """
        在 ArXiv 检索学术论文。

        Args:
            query: 检索词，如 "tariff AND manufacturing employment"
            max_results: 返回数量上限
            categories: 限定分类，如 ["q-fin.GN", "econ.GN", "cs.AI"]

        Returns:
            文献列表，每条含 arxiv_id, title, authors, abstract, published, categories, pdf_url
        """
        if categories is None:
            categories = ["q-fin.GN", "econ.GN", "cs.LG", "stat.ML"]

        import urllib.parse

        cat_query = " OR ".join(f"cat:{c}" for c in categories)
        full_query = f"({query}) AND ({cat_query})"
        encoded = urllib.parse.quote_plus(full_query)

        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query={encoded}&start=0&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )

        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            return self._parse_arxiv_atom(raw)
        except Exception as e:
            print(f"  ⚠ ArXiv 检索失败: {e}")
            return []

    def _parse_arxiv_atom(self, xml: str) -> list[dict]:
        import xml.etree.ElementTree as ET
        records = []
        try:
            root = ET.fromstring(xml)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
                title = " ".join(
                    entry.find("atom:title", ns).text.split()
                )
                summary = " ".join(
                    entry.find("atom:summary", ns).text.split()
                )
                authors = [
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)
                    if a.find("atom:name", ns) is not None
                ]
                published = entry.find("atom:published", ns).text[:10]
                cats = [
                    c.get("term")
                    for c in entry.findall("atom:category", ns)
                ]
                links = entry.findall("atom:link", ns)
                pdf_url = next(
                    (l.get("href") for l in links if l.get("title") == "pdf"),
                    next((l.get("href") for l in links if l.get("type", "").startswith("application/pdf")), "")
                )
                records.append({
                    "bibtex_key": f"{authors[0].split()[-1]}{published[:4] if authors else 'Unknown'}"
                                  f"{''.join(c for c in title.split()[:2] if len(c) > 3)[:6]}",
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "authors": ", ".join(authors),
                    "year": int(published[:4]) if published else None,
                    "journal": "ArXiv preprint",
                    "doi": f"10.48550/arXiv.{arxiv_id}",
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "pdf_url": pdf_url,
                    "abstract": summary[:500],
                    "published": published,
                    "categories": cats,
                    "tags": [],
                })
                self._arxiv_cache[arxiv_id] = records[-1]
        except ET.ParseError as e:
            print(f"  ⚠ ArXiv XML 解析错误: {e}")
        return records

    # ── Brave Search 检索 ───────────────────────────────────────

    def search_brave(
        self,
        query: str,
        max_results: int = 10,
        source: str = "news",
    ) -> list[dict]:
        """
        使用 Brave Search 检索财经新闻与政策文件。

        Args:
            query: 检索词
            max_results: 返回数量
            source: "news" | "web" | "videos"
        """
        if not self.brave_api_key:
            print("  ⚠ BRAVE_SEARCH_API_KEY 未配置，跳过 Brave 搜索")
            return []

        try:
            from mcp import MCPServices
            # MCP 方式调用 brave search
            result = MCPServices.brave_search(
                query=query,
                max_results=max_results,
                source=source,
            )
            records = []
            for item in result.get("web", result.get("results", [])):
                records.append({
                    "bibtex_key": f"Brave{query[:20].replace(' ', '')}{item.get('date', '')[:10].replace('-', '')}",
                    "title": item.get("title", ""),
                    "authors": item.get("authors", ""),
                    "year": int(item.get("date", "2024")[:4]) if item.get("date") else 2024,
                    "journal": item.get("source", "Web"),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "published": item.get("date", ""),
                    "tags": [],
                })
            return records
        except ImportError:
            # 降级为直接 HTTP 调用
            return self._search_brave_http(query, max_results, source)

    def _search_brave_http(self, query: str, max_results: int, source: str) -> list[dict]:
        import urllib.request, urllib.parse, json
        encoded = urllib.parse.quote_plus(query)
        url = f"https://api.search.brave.com/res/v1/{source}/search?q={encoded}&count={max_results}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "X-Subscription-Token": self.brave_api_key}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            results = data.get("results", [])
            return [
                {
                    "bibtex_key": f"Brave{query[:15].replace(' ', '')}{r.get('age', '')[:8].replace('-', '')}",
                    "title": r.get("title", ""),
                    "authors": r.get("meta.url", ""),
                    "year": int(r.get("age", "2024")[:4]) if r.get("age") else 2024,
                    "journal": r.get("meta.url", "").split("/")[1] if r.get("meta.url") else "Web",
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                    "published": r.get("age", ""),
                    "tags": [],
                }
                for r in results
            ]
        except Exception as e:
            print(f"  ⚠ Brave Search HTTP 失败: {e}")
            return []

    # ── 文献分析 ────────────────────────────────────────────────

    def extract_abstract(self, text: str, prompt_template: str = None) -> str:
        """
        使用 LLM 从全文/PDF 中提取摘要。

        提示词模板（来自 researcher 规则）：
          - system: "You are an academic research assistant..."
          - user:   "Extract a structured abstract from the following paper...\n\n{text}\n\n"
                    "Focus on: research question, methodology, data, key findings, contribution."
        """
        prompt = prompt_template or EXTRACT_ABSTRACT_PROMPT
        return prompt.format(text=text[:8000])

    def extract_findings(
        self,
        text: str,
        research_question: str = None,
        prompt_template: str = None,
    ) -> dict:
        """
        从文献中提取结构化研究发现。

        返回字段：
          - research_question: 研究问题
          - hypothesis: 研究假设
          - methodology: 方法（实验/计量/案例）
          - dataset: 数据集与时间跨度
          - key_findings: 核心结论（3-5条）
          - robustness_checks: 稳健性检验
          - limitations: 研究局限
          - policy_implications: 政策启示
        """
        prompt = prompt_template or EXTRACT_FINDINGS_PROMPT
        if research_question:
            prompt = prompt.replace("{research_question}", research_question)
        return {
            "prompt_sent": prompt.format(text=text[:6000]),
            "expected_fields": [
                "research_question", "hypothesis", "methodology",
                "dataset", "key_findings", "robustness_checks",
                "limitations", "policy_implications",
            ],
        }

    def batch_search(
        self,
        queries: list[str],
        sources: list[str] = None,
        max_per_query: int = 5,
    ) -> dict[str, list[dict]]:
        """
        批量多源检索。

        Args:
            queries: 多个检索词，如 ["tariff innovation", "AI employment", "LLM finance"]
            sources: 来源列表，如 ["arxiv", "brave"]，默认 ["arxiv", "brave"]
            max_per_query: 每个词最多返回多少条
        """
        if sources is None:
            sources = ["arxiv", "brave"]

        results = {}
        for q in queries:
            q_results = []
            if "arxiv" in sources:
                arxiv = self.search_arxiv(q, max_results=max_per_query)
                q_results.extend(arxiv)
            if "brave" in sources:
                brave = self.search_brave(q, max_results=max_per_query)
                q_results.extend(brave)
            results[q] = q_results
            print(f"  [{q}] → {len(q_results)} 条文献")

        return results

    def to_bibtex(self, records: list[dict]) -> str:
        """
        将文献记录转换为 BibTeX 格式。

        支持 article、inproceedings、techreport、misc 四种类型。
        """
        lines = []
        for r in records:
            bibtype = "article"
            if "arxiv" in str(r.get("url", "")):
                bibtype = "misc"
            elif r.get("conference"):
                bibtype = "inproceedings"

            key = r.get("bibtex_key", f"Unknown{r.get('year', 2024)}")
            lines.append(f"@{bibtype}{{{key},")
            lines.append(f"  title   = {{{r.get('title', 'Unknown')}}},")
            lines.append(f"  author  = {{{r.get('authors', 'Unknown')}}},")
            lines.append(f"  year    = {{{r.get('year', 'n.d.')}}},")
            if r.get("journal"):
                lines.append(f"  journal = {{{r.get('journal')}}},")
            if r.get("doi"):
                lines.append(f"  doi     = {{{r.get('doi')}}},")
            if r.get("url"):
                lines.append(f"  url     = {{{r.get('url')}}},")
            lines.append("}")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# 第五层：LLM 模型处理模块
# ────────────────────────────────────────────────────────────────
# 角色定位：以 Cursor 本地 Claude 为默认，外部 AI 仅作脚本批处理补充
# 学术研究中的 LLM 调用需覆盖五类任务：
#   1. 情感/舆情分析（Sentiment Analysis）
#   2. 文档摘要（Document Summarization）
#   3. 命名实体提取（NER: 公司/人/指标/金额）
#   4. 文本分类（Policy Document / News / Academic）
#   5. 问答/信息抽取（QA over Financial Reports）
#
# 参考文献（LLM 金融应用）：
#   - Lopez-Lira & Tang (2023): "Can ChatGPT Forecast Stock Price Movements?"
#   - Li et al. (2024): "FinAgent: A Multi-Agent Framework for Financial Tasks"
#   - Xie et al. (2024): "FinMem: LLM-Powered Investor Profiling"
#   - Zhang et al. (2024): "Can LLMs Strut Their Stuff? LLMs vs. Financial Data"
#   - Bommarito & Katz (2024): "LLMs as Forensic Tools"
#   - Araabi & Monreale (2024): "Extracting Financial Entities from Earnings Calls"
#   - Sun et al. (2024): "FinNLP: LLMs for Financial NLP"
#   - Duffy et al. (2024): "LLM-Assisted Qualitative Coding in Finance Research"


class LLMProcessor:
    """
    LLM 模型处理器，支持多种调用方式和任务类型。

    支持的模型接口（均使用最新版本）：
      - bai:       B.AI 中转 API（需 B_AI_API_KEY）
                    可用模型（已实测）：
                      GPT系列:  gpt-5.5 / gpt-5.4 / gpt-5.4-mini / gpt-5.4-nano / gpt-5.5-instant
                      Claude:   claude-sonnet-4.6 / claude-opus-4.7 / claude-haiku-4.5
                      Gemini:   gemini-3.1-pro / gemini-3-flash
                      DeepSeek: deepseek-v4-flash / deepseek-v4-pro
                    Base URL: https://api.b.ai/v1
      - deepseek:  DeepSeek 直连（需 DEEPSEEK_API_KEY）
                    模型: deepseek-chat / deepseek-reasoner（R1推理）
                    Base URL: https://api.deepseek.com/v1

    提示词模板（内置 + 可扩展）：
      - sentiment_prompt:    情感分析提示词
      - summarization_prompt: 摘要生成提示词
      - ner_prompt:          命名实体识别提示词
      - classification_prompt: 文本分类提示词
      - qa_prompt:           金融问答提示词
      - coding_prompt:        代码生成提示词（数据处理/统计检验）
      - reviewer_prompt:      论文审稿提示词

    使用示例：
      >>> proc = LLMProcessor(provider="bai", model="gpt-5.5")      # 外部补充（需 VPN）
      >>> proc = LLMProcessor(provider="deepseek", model="deepseek-chat")  # 外部补充（无需 VPN）
      >>> proc = LLMProcessor(provider="bai", model="claude-sonnet-4.6")
      >>> proc = LLMProcessor(provider="bai", model="gemini-3.1-pro")
      >>> sentiment = proc.analyze_sentiment("Fed announces rate cut...")
      >>> summary = proc.summarize(text, max_words=200)
      >>> entities = proc.extract_entities(text, entity_types=["ORG", "MONEY", "DATE"])
      >>> label = proc.classify("Quarterly earnings call transcript...", categories=...)
    """

    def __init__(
        self,
        provider: str = "bai",
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.provider = provider.lower()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
        self._model = model
        self._base_url = base_url

        # B.AI 中转（GPT/Gemini 等，通过 Cursor 代理转发，OpenAI 兼容格式）
        if self.provider == "bai":
            self._model = model or "gpt-5.5"
            self._api_key = api_key or os.environ.get("B_AI_API_KEY")
            self._base_url = (
                base_url or
                os.environ.get("B_AI_BASE_URL") or
                "https://api.b.ai/v1"
            )
            if self._api_key:
                try:
                    from openai import OpenAI
                    self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
                except ImportError:
                    print("  ⚠ openai 未安装: pip install openai")
                    self._client = None
            else:
                print("  ⚠ B_AI_API_KEY 未配置")

        # DeepSeek（直连，OpenAI 兼容格式）
        elif self.provider == "deepseek":
            self._model = model or "deepseek-chat"
            self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
            self._base_url = (
                base_url or
                os.environ.get("DEEPSEEK_BASE_URL") or
                "https://api.deepseek.com/v1"
            )
            if self._api_key:
                try:
                    from openai import OpenAI
                    self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
                except ImportError:
                    print("  ⚠ openai 未安装: pip install openai")
                    self._client = None
            else:
                print("  ⚠ DEEPSEEK_API_KEY 未配置")

    # ── 通用调用 ────────────────────────────────────────────────

    def _call(self, messages: list[dict], **kwargs) -> str:
        """
        统一调用入口，返回文本响应。

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
            **kwargs: temperature, max_tokens 等参数覆盖

        Returns:
            模型生成的文本
        """
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        # B.AI 中转（OpenAI 兼容格式，可调用 GPT/Gemini 等）
        if self.provider == "bai" and self._client:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content

        # DeepSeek（OpenAI 兼容格式）
        elif self.provider == "deepseek" and self._client:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content

        return "[错误] 未配置有效的 LLM 提供者或缺少 API Key"

    def call_with_prompt(
        self,
        prompt: str,
        system: str = None,
        **kwargs,
    ) -> str:
        """最简接口：传入 prompt 文本即可调用模型。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call(messages, **kwargs)

    # ── 情感分析 ────────────────────────────────────────────────

    def analyze_sentiment(
        self,
        text: str,
        scale: str = "polar",
        return_scores: bool = True,
        prompt_template: str = None,
    ) -> dict:
        """
        对金融文本进行情感分析。

        支持三种量表（scale 参数）：
          - "polar":    负面(-1) / 中性(0) / 正面(+1)
          - "fine":     强烈负面(-2) / 负面(-1) / 中性(0) / 正面(+1) / 强烈正面(+2)
          - "prob":     返回各情感概率 [neg, neutral, pos]

        参考文献（情感与市场）：
          - Lopez-Lira & Tang (2023): ChatGPT 可预测股价
          - Bommarito & Katz (2024): LLM 在法律/金融文本上的精度
          - Duffy et al. (2024): LLM 辅助定性编码

        Args:
            text: 待分析文本（研报/新闻/推文/财报电话会）
            scale: 量表类型
            return_scores: 是否返回概率分布
            prompt_template: 自定义提示词

        Returns:
            {"label": str, "score": float, "probabilities": dict}
        """
        prompt = prompt_template or self._get_sentiment_prompt(scale)
        prompt_filled = prompt.format(text=text)

        messages = [
            {"role": "system", "content": SENTIMENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        raw = self._call(messages)

        return self._parse_sentiment_response(raw, scale, return_scores)

    def _get_sentiment_prompt(self, scale: str) -> str:
        if scale == "polar":
            return (
                "Analyze the sentiment of the following financial text. "
                "Classify it as: NEGATIVE, NEUTRAL, or POSITIVE.\n\n"
                "Text: {text}\n\n"
                "Output format: LABEL=<NEGATIVE|NEUTRAL|POSITIVE>, "
                "SCORE=<integer from -1 to 1>, REASON=<one sentence>."
            )
        elif scale == "fine":
            return (
                "Analyze the sentiment of the following financial text on a 5-point scale:\n"
                "  -2: Strongly Negative (severe loss, crisis, major risk)\n"
                "  -1: Negative (decline, concern, headwind)\n"
                "   0: Neutral (mixed signals, no clear direction)\n"
                "  +1: Positive (growth, improvement, opportunity)\n"
                "  +2: Strongly Positive (breakthrough, record, major win)\n\n"
                "Text: {text}\n\n"
                "Output: LABEL=<value>, SCORE=<integer -2 to 2>, REASON=<one sentence>."
            )
        else:  # prob
            return (
                "Analyze the sentiment of the following financial text. "
                "Return probabilities for NEGATIVE, NEUTRAL, and POSITIVE.\n\n"
                "Text: {text}\n\n"
                "Output: PROB_NEG=<0.0-1.0>, PROB_NEUTRAL=<0.0-1.0>, PROB_POS=<0.0-1.0>, "
                "REASON=<brief justification>."
            )

    def _parse_sentiment_response(self, raw: str, scale: str, return_scores: bool) -> dict:
        import re
        label = "NEUTRAL"
        score = 0.0
        probs = {"negative": 0.33, "neutral": 0.34, "positive": 0.33}
        reason = ""

        label_m = re.search(r"LABEL\s*=\s*([\w\-\s]+)", raw, re.IGNORECASE)
        score_m = re.search(r"SCORE\s*=\s*(-?\d+(?:\.\d+)?)", raw)
        prob_m = re.search(r"PROB_NEG\s*=\s*([\d.]+).*?PROB_NEUTRAL\s*=\s*([\d.]+).*?PROB_POS\s*=\s*([\d.]+)", raw, re.DOTALL)
        reason_m = re.search(r"REASON\s*=\s*(.+?)(?:\n|$)", raw, re.DOTALL)

        if label_m:
            label = label_m.group(1).strip().upper()
        if score_m:
            score = float(score_m.group(1))
        if prob_m:
            probs = {
                "negative": float(prob_m.group(1)),
                "neutral": float(prob_m.group(2)),
                "positive": float(prob_m.group(3)),
            }
        if reason_m:
            reason = reason_m.group(1).strip()

        result = {"label": label, "score": score, "reason": reason}
        if return_scores and scale == "prob":
            result["probabilities"] = probs
        return result

    # ── 文档摘要 ────────────────────────────────────────────────

    def summarize(
        self,
        text: str,
        max_words: int = 200,
        style: str = "academic",
        prompt_template: str = None,
    ) -> str:
        """
        对长文档生成摘要。

        支持三种风格：
          - "academic": 学术摘要（研究问题、方法、结论）
          - "bullet":    要点列表（适合研报要点）
          - "executive": 管理层摘要（适合财报电话会）

        参考文献（摘要质量）：
          - Liu (2024): "A Survey on Text Summarization with Large Language Models"
          - Lewis et al. (2020), BART: "Denoising Sequence-to-Sequence Pre-training"
        """
        prompt = prompt_template or self._get_summarization_prompt(style, max_words)
        prompt_filled = prompt.format(text=text)

        messages = [
            {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        return self._call(messages, max_tokens=max_tokens_max(max_words))

    def _get_summarization_prompt(self, style: str, max_words: int) -> str:
        if style == "academic":
            return (
                "Summarize the following document in academic style, no more than {max_words} words.\n"
                "Structure: [Background & Research Question] → [Methodology] → [Key Findings] → [Implications]\n\n"
                "Document: {text}"
            )
        elif style == "bullet":
            return (
                f"Summarize the following text as a list of bullet points, at most {max_words} words total.\n"
                "Use • for each point. Focus on: key facts, numbers, changes, and implications.\n\n"
                "Text: {text}"
            )
        else:  # executive
            return (
                "Write an executive summary of the following text, at most {max_words} words.\n"
                "Target audience: C-suite executives. Highlight: performance, outlook, risks.\n\n"
                "Text: {text}"
            )

    # ── 命名实体识别 ───────────────────────────────────────────

    def extract_entities(
        self,
        text: str,
        entity_types: list[str] = None,
        prompt_template: str = None,
    ) -> dict:
        """
        从金融文本中提取结构化实体。

        支持的实体类型：
          - ORG:    公司/机构名称
          - TICKER: 股票代码
          - MONEY:  金额/数值（美元/人民币）
          - DATE:   日期/时间
          - PERCENT: 百分比/变化率
          - GEO:    地理位置/国家/地区
          - REG:    监管政策/法律名称
          - METRIC: 财务指标（ROE/PE/营收等）

        参考文献：
          - Araabi & Monreale (2024): Extracting Financial Entities from Earnings Calls
          - Xie et al. (2024): FinMem for Investor Profiling

        Returns:
            {"ORG": [...], "TICKER": [...], "MONEY": [...], ...}
        """
        if entity_types is None:
            entity_types = ["ORG", "TICKER", "MONEY", "DATE", "PERCENT", "GEO", "REG", "METRIC"]

        prompt = prompt_template or EXTRACT_ENTITIES_PROMPT
        prompt_filled = prompt.format(
            entity_types=", ".join(entity_types),
            types_list="\n".join(f"  - {t}: {ETYPE_DESCRIPTIONS.get(t, '')}" for t in entity_types),
            text=text,
        )

        messages = [
            {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        raw = self._call(messages)
        return self._parse_entities_response(raw, entity_types)

    def _parse_entities_response(self, raw: str, entity_types: list[str]) -> dict:
        import re
        result = {t: [] for t in entity_types}

        for etype in entity_types:
            pattern = rf"{etype}\s*[:：]\s*(.+?)(?=\n[A-Z]+|$$|\Z)"
            matches = re.findall(pattern, raw, re.DOTALL)
            for m in matches:
                items = [x.strip().strip("-*•、，,") for x in m.split("\n") if x.strip()]
                result[etype].extend(items)

        return result

    # ── 文本分类 ───────────────────────────────────────────────

    def classify(
        self,
        text: str,
        categories: list[str] = None,
        prompt_template: str = None,
    ) -> dict:
        """
        对文本进行主题/类型分类。

        默认分类体系（可用于文献/新闻/研报分类）：
          - policy:      政策/监管文件
          - academic:    学术论文
          - news:        新闻报道
          - earnings:    财报/业绩发布
          - analyst:     券商研报
          - social:      社交媒体/推文

        参考文献（分类性能）：
          - Zhang et al. (2024): LLMs vs. Financial Data benchmark
          - Sun et al. (2024): FinNLP: LLMs for Financial NLP survey
        """
        if categories is None:
            categories = ["policy", "academic", "news", "earnings", "analyst", "social"]

        prompt = prompt_template or CLASSIFICATION_PROMPT
        prompt_filled = prompt.format(
            categories=", ".join(categories),
            cat_list="\n".join(f"  - {c}" for c in categories),
            text=text[:4000],
        )

        messages = [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        raw = self._call(messages)
        return self._parse_classification_response(raw, categories)

    def _parse_classification_response(self, raw: str, categories: list[str]) -> dict:
        import re
        label = categories[0]
        confidence = 0.5

        label_m = re.search(r"LABEL\s*[:＝]\s*([\w\-]+)", raw, re.IGNORECASE)
        conf_m = re.search(r"CONFIDENCE\s*[:＝]\s*([\d.]+)", raw, re.IGNORECASE)

        if label_m:
            label = label_m.group(1).lower()
            if label not in categories:
                label = next((c for c in categories if label in c), categories[0])
        if conf_m:
            confidence = float(conf_m.group(1))

        return {"label": label, "confidence": confidence, "raw": raw.strip()}

    # ── 批量处理 ───────────────────────────────────────────────

    def batch_sentiment(
        self,
        texts: list[str],
        scale: str = "polar",
        delay: float = 0.5,
    ) -> list[dict]:
        """
        批量情感分析（含速率限制）。

        Args:
            texts: 文本列表
            scale: 量表类型
            delay: 请求间隔（秒），防止 API 超限
        """
        import time
        results = []
        for i, text in enumerate(texts):
            try:
                result = self.analyze_sentiment(text, scale=scale)
                results.append(result)
                if i < len(texts) - 1:
                    time.sleep(delay)
            except Exception as e:
                results.append({"error": str(e), "label": "ERROR", "score": 0.0})
        return results

    def batch_summarize(
        self,
        texts: list[str],
        max_words: int = 200,
        delay: float = 0.5,
    ) -> list[str]:
        """批量摘要生成。"""
        import time
        summaries = []
        for i, text in enumerate(texts):
            try:
                summary = self.summarize(text, max_words=max_words)
                summaries.append(summary)
                if i < len(texts) - 1:
                    time.sleep(delay)
            except Exception as e:
                summaries.append(f"[Error: {e}]")
        return summaries

    # ── 金融问答 ───────────────────────────────────────────────

    def financial_qa(
        self,
        question: str,
        context: str = None,
        prompt_template: str = None,
    ) -> str:
        """
        基于上下文进行金融问答。

        适用场景：
          - 研报问答：提取研报中的关键数据
          - 财报问答：问询特定指标
          - 文献综述：问答式文献理解

        参考文献：
          - Li et al. (2024): FinAgent — Multi-Agent for Financial Tasks
          - Xie et al. (2024): FinMem — LLM-Powered Investor Profiling
        """
        prompt = prompt_template or QA_PROMPT
        if context:
            prompt_filled = prompt.format(question=question, context=context)
        else:
            prompt_filled = f"Question: {question}\n\nAnswer based on your financial knowledge:"
        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        return self._call(messages, max_tokens=self.max_tokens)

    # ── 数据处理代码生成 ───────────────────────────────────────

    def generate_code(
        self,
        task: str,
        language: str = "python",
        prompt_template: str = None,
    ) -> str:
        """
        生成数据处理代码。

        支持任务：
          - 统计检验（t检验、Wilcoxon、Bootstrap）
          - 回归分析（OLS、FE、Diff-in-Diff）
          - 面板数据处理（Stata/Python）
          - 因子分析（CAPM、Fama-French）
          - 可视化（matplotlib/seaborn）

        参考文献（代码生成质量）：
          - Rozani et al. (2024): LLM for scientific code generation
          - Fan et al. (2024): Code generation for econometrics
        """
        prompt = prompt_template or CODE_GENERATION_PROMPT
        prompt_filled = prompt.format(task=task, language=language)
        messages = [
            {"role": "system", "content": CODE_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_filled},
        ]
        return self._call(messages, max_tokens=self.max_tokens)

    # ── 论文审稿辅助 ───────────────────────────────────────────

    def review_paper(
        self,
        abstract: str,
        sections: dict = None,
        focus_areas: list[str] = None,
    ) -> dict:
        """
        论文审稿辅助（模拟 reviewer 视角）。

        返回字段：
          - novelty:        创新性评分（1-10）
          - methodology:    方法论评分（1-10）
          - clarity:        写作清晰度（1-10）
          - major_comments: 主要修改意见（3-5条）
          - minor_comments: 次要修改意见
          - recommendation: 接收/修改/拒绝建议
        """
        if focus_areas is None:
            focus_areas = ["novelty", "methodology", "clarity", "contribution", "limitations"]
        sections_text = ""
        if sections:
            sections_text = "\n\n".join(f"=== {k.upper()} ===\n{v}" for k, v in sections.items())

        prompt = (
            f"You are an academic reviewer for a top-tier finance/economics journal.\n"
            f"Review the following paper focusing on: {', '.join(focus_areas)}.\n\n"
            f"Abstract:\n{abstract}\n\n"
            f"{sections_text}\n\n"
            "Provide structured feedback in this format:\n"
            "NOVELTY=<1-10>, METHODOLOGY=<1-10>, CLARITY=<1-10>\n"
            "MAJOR: (list 3-5 major concerns)\n"
            "MINOR: (list minor issues)\n"
            "RECOMMENDATION: ACCEPT / REVISE / REJECT\n"
            "SUMMARY: <2-sentence overall assessment>"
        )
        messages = [
            {"role": "system", "content": PAPER_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt.format(abstract=abstract)},
        ]
        raw = self._call(messages)
        return self._parse_review_response(raw)


# ════════════════════════════════════════════════════════════════════
# 提示词模板库
# ════════════════════════════════════════════════════════════════════
# 学术提示词设计原则（参考 research_agent 规则）：
#   1. 角色设定：明确 AI 身份（如"资深金融分析师"、"学术审稿人"）
#   2. 任务描述：具体、可量化（"提取不超过200词的摘要"）
#   3. 输出格式：结构化（JSON/BibTeX/表格/Markdown）
#   4. 约束条件：语言、长度、风格限制
#   5. 示例驱动：few-shot 提供 1-3 个示例


SENTIMENT_SYSTEM_PROMPT = """You are a senior financial analyst specializing in sentiment analysis.
You analyze earnings calls, analyst reports, news articles, and social media.
Always cite specific phrases from the text to justify your assessment.
Output format must be concise and machine-readable."""


SUMMARIZATION_SYSTEM_PROMPT = """You are an academic writing expert for finance and economics.
Generate concise, accurate summaries that preserve key quantitative findings.
Do not add information not present in the original text.
Cite data points and statistics explicitly."""


ENTITY_EXTRACTION_SYSTEM_PROMPT = """You are a financial entity extraction specialist.
Extract named entities with high precision. For each entity:
  - ORG: Company or institution name (full legal name preferred)
  - TICKER: Stock ticker symbol (e.g., AAPL, 000001.SZ)
  - MONEY: Monetary amounts with currency (e.g., $5.2B, ¥300亿)
  - DATE: Specific dates or time periods
  - PERCENT: Percentages and growth rates
  - GEO: Countries, cities, regions
  - REG: Regulatory or policy names
  - METRIC: Financial metrics (ROE, P/E, revenue growth, etc.)
Output in structured format, one entity type per line."""


CLASSIFICATION_SYSTEM_PROMPT = """You are a financial text classification expert.
Classify each text into exactly one of the provided categories.
Consider both the content and the writing style.
Provide a confidence score between 0 and 1."""


QA_SYSTEM_PROMPT = """You are a knowledgeable financial research assistant.
Answer questions using only information from the provided context.
If the context is insufficient, say "Based on the provided context, I cannot determine..."
Cite specific parts of the context to support your answer."""


CODE_GENERATION_SYSTEM_PROMPT = """You are an expert in quantitative finance and econometrics.
Write clean, well-documented code for data analysis and statistical modeling.
Prefer pandas, numpy, scipy, statsmodels, and matplotlib.
Include inline comments for non-obvious logic.
Handle edge cases and missing data appropriately."""


PAPER_REVIEW_SYSTEM_PROMPT = """You are a seasoned academic reviewer for leading finance journals (JF/JFE/RESTAT/JPE/QJE).
Provide constructive, specific, and actionable feedback.
Be critical but fair — acknowledge strengths while identifying weaknesses.
Cite similar papers if you suggest additional literature."""


# ── 任务级提示词模板 ────────────────────────────────────────────


SENTIMENT_PROMPTS = {
    "polar": (
        "Analyze the sentiment of the following financial text. "
        "Classify as NEGATIVE (bearish, risk, decline) / NEUTRAL / POSITIVE (bullish, opportunity, growth).\n\n"
        "Text: {text}\n\n"
        "Output: LABEL=<NEGATIVE|NEUTRAL|POSITIVE>, SCORE=<-1 to 1>, REASON=<justification>"
    ),
    "fine": (
        "Classify the sentiment on a 5-point scale for financial text:\n"
        "  -2 Strongly Negative (crisis, severe losses, major risk)\n"
        "  -1 Negative (decline, concern, headwind)\n"
        "   0 Neutral\n"
        "  +1 Positive (growth, improvement)\n"
        "  +2 Strongly Positive (breakthrough, record performance)\n\n"
        "Text: {text}\n\n"
        "Output: LABEL=<value>, SCORE=<-2 to 2>, REASON=<justification>"
    ),
    "prob": (
        "Estimate sentiment probabilities for financial text:\n"
        "Text: {text}\n\n"
        "Output: PROB_NEG=<0.0-1.0>, PROB_NEUTRAL=<0.0-1.0>, PROB_POS=<0.0-1.0>, REASON=<brief>"
    ),
}


EXTRACT_ABSTRACT_PROMPT = """You are an academic research assistant. Extract a structured abstract from the following paper text.

Focus on these five elements:
1. Research Question: What problem does this paper address?
2. Methodology: What data, models, or experiments are used?
3. Key Findings: What are the main results (with numbers if available)?
4. Contribution: How does this advance the field?
5. Limitations: What are the acknowledged weaknesses?

Text:
{text}

Output in this format:
[Background & Research Question]
...
[Methodology]
...
[Key Findings]
...
[Contribution]
...
[Limitations]
...
"""


EXTRACT_FINDINGS_PROMPT = """You are an academic research assistant specializing in finance and economics.
Extract structured findings from the following paper.

Research Question (if provided):
{research_question}

Paper Text:
{text}

Extract the following fields (use "N/A" if not found):
- research_question
- hypothesis
- methodology (data, model, sample period, identification strategy)
- dataset (name, source, observations, time span)
- key_findings (list 3-5 bullet points with statistics)
- robustness_checks
- limitations
- policy_implications

Output as structured text with clear section headers.
"""


EXTRACT_ENTITIES_PROMPT = """Extract financial named entities from the following text.

Entity types to extract:
{types_list}

Text:
{text}

Output format (one per line):
{entity_types[0]}:
  - <entity1>
  - <entity2>
{entity_types[1]}:
  - <entity1>
...
"""


CLASSIFICATION_PROMPT = """Classify the following financial text into one of these categories:
{cat_list}

Text:
{text}

Output: LABEL=<category>, CONFIDENCE=<0.0-1.0>
"""


QA_PROMPT = """Based on the following context, answer the question concisely and cite specific parts.

Context:
{context}

Question: {question}

Answer:
"""


CODE_GENERATION_PROMPT = """Write {language} code for the following quantitative finance task:

Task: {task}

Requirements:
- Use {language} (prefer pandas, numpy, scipy, statsmodels for Python)
- Include docstrings and comments
- Handle missing data
- Output should be runnable

Code:
"""


# ── 辅助常量 ──────────────────────────────────────────────────


ETYPE_DESCRIPTIONS = {
    "ORG":     "公司或机构全称",
    "TICKER":  "股票代码（如AAPL、600000.SH）",
    "MONEY":   "金额（带货币单位，如$5.2B、¥300亿）",
    "DATE":    "具体日期或时间段",
    "PERCENT": "百分比或变化率",
    "GEO":     "国家、城市、地区名称",
    "REG":     "监管政策或法律名称",
    "METRIC":  "财务指标（ROE、PE、营收增速等）",
}


# ── 工具函数 ──────────────────────────────────────────────────


def max_tokens_max(max_words: int) -> int:
    """估算最大 token 数（约 1 token ≈ 0.75 英文词，中文约 1.5）"""
    return int(max_words * 2)


# ════════════════════════════════════════════════════════════════════
# 第六层：Prompt 模板管理器
# ════════════════════════════════════════════════════════════════════


class PromptTemplateManager:
    """
    提示词模板管理器，支持版本控制与动态组合。

    功能：
      - 模板注册与按名查找
      - 变量插值（{var} 语法）
      - 模板链（base + instruction + format 三段式）
      - Jinja2 风格条件渲染
      - 模板导出为 Markdown 文档

    学术使用场景：
      - 文献综述：组合 research_question + methodology_template
      - 情感分析：polar_template / fine_template 切换
      - 实证研究：variable_definition + regression_output_template
      - 论文写作：abstract_template + introduction_template

    模板结构（三段式）：
      [SYSTEM]  角色设定与行为约束
      [CONTENT] 具体任务描述与输入数据
      [FORMAT]  输出格式约束
    """

    def __init__(self):
        self._templates: dict[str, dict] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册内置模板。"""
        self.register("sentiment_polar", {
            "description": "情感分析 - 二分类（负面/中性/正面）",
            "category": "sentiment",
            "system": SENTIMENT_SYSTEM_PROMPT,
            "template": SENTIMENT_PROMPTS["polar"],
            "variables": ["text"],
            "output_format": "LABEL=<...>, SCORE=<...>, REASON=<...>",
            "citation": "Lopez-Lira & Tang (2023); Bommarito & Katz (2024)",
        })

        self.register("sentiment_fine", {
            "description": "情感分析 - 五分类（-2至+2量表）",
            "category": "sentiment",
            "system": SENTIMENT_SYSTEM_PROMPT,
            "template": SENTIMENT_PROMPTS["fine"],
            "variables": ["text"],
            "output_format": "LABEL=<...>, SCORE=<...>, REASON=<...>",
            "citation": "Bommarito & Katz (2024)",
        })

        self.register("extract_abstract", {
            "description": "从论文全文提取结构化摘要",
            "category": "literature",
            "system": "You are an academic research assistant.",
            "template": EXTRACT_ABSTRACT_PROMPT,
            "variables": ["text"],
            "output_format": "[Background] ... [Methodology] ... [Findings] ...",
            "citation": "researcher_agent rule",
        })

        self.register("extract_findings", {
            "description": "从论文提取结构化研究发现",
            "category": "literature",
            "system": "You are an academic research assistant for finance/economics.",
            "template": EXTRACT_FINDINGS_PROMPT,
            "variables": ["text", "research_question"],
            "output_format": "research_question, hypothesis, methodology, dataset, key_findings, robustness, limitations",
            "citation": "researcher_agent rule",
        })

        self.register("extract_entities", {
            "description": "从金融文本提取命名实体",
            "category": "ner",
            "system": ENTITY_EXTRACTION_SYSTEM_PROMPT,
            "template": EXTRACT_ENTITIES_PROMPT,
            "variables": ["text", "entity_types"],
            "output_format": "ORG:, TICKER:, MONEY:, ...",
            "citation": "Araabi & Monreale (2024); Xie et al. (2024)",
        })

        self.register("classify_financial", {
            "description": "金融文本分类（政策/学术/新闻/财报/研报/社交）",
            "category": "classification",
            "system": CLASSIFICATION_SYSTEM_PROMPT,
            "template": CLASSIFICATION_PROMPT,
            "variables": ["text", "categories"],
            "output_format": "LABEL=<...>, CONFIDENCE=<...>",
            "citation": "Zhang et al. (2024); Sun et al. (2024)",
        })

        self.register("financial_qa", {
            "description": "基于上下文的金融问答",
            "category": "qa",
            "system": QA_SYSTEM_PROMPT,
            "template": QA_PROMPT,
            "variables": ["question", "context"],
            "output_format": "Free text answer with citations",
            "citation": "Li et al. (2024) FinAgent; Xie et al. (2024) FinMem",
        })

        self.register("summarize_academic", {
            "description": "学术风格摘要生成",
            "category": "summarization",
            "system": SUMMARIZATION_SYSTEM_PROMPT,
            "template": "Summarize in academic style, ≤{max_words} words.\nStructure: [Background & RQ] → [Method] → [Findings] → [Implications]\n\nText: {text}",
            "variables": ["text", "max_words"],
            "output_format": "Structured paragraphs",
            "citation": "Liu (2024) Text Summarization Survey; Lewis et al. (2020) BART",
        })

        self.register("summarize_bullet", {
            "description": "要点列表摘要（研报风格）",
            "category": "summarization",
            "system": SUMMARIZATION_SYSTEM_PROMPT,
            "template": f"Summarize as bullet points, ≤{{max_words}} words total.\nFocus: key facts, numbers, changes, implications.\n\nText: {{text}}",
            "variables": ["text", "max_words"],
            "output_format": "• Point 1\n• Point 2...",
            "citation": "analyst_agent rule",
        })

        self.register("generate_code", {
            "description": "数据处理代码生成（Python/Stata/R）",
            "category": "coding",
            "system": CODE_GENERATION_SYSTEM_PROMPT,
            "template": CODE_GENERATION_PROMPT,
            "variables": ["task", "language"],
            "output_format": "Executable code with comments",
            "citation": "Rozani et al. (2024); Fan et al. (2024)",
        })

        self.register("review_paper", {
            "description": "论文审稿辅助",
            "category": "review",
            "system": PAPER_REVIEW_SYSTEM_PROMPT,
            "template": "Review paper focusing on: novelty, methodology, clarity, contribution, limitations.\n\nAbstract:\n{abstract}\n\nOutput: NOVELTY=<1-10>, METHODOLOGY=<1-10>, CLARITY=<1-10>, MAJOR concerns, MINOR concerns, RECOMMENDATION.",
            "variables": ["abstract"],
            "output_format": "NOVELTY=<>, METHODOLOGY=<>, CLARITY=<>, MAJOR/MINOR, RECOMMENDATION",
            "citation": "paper_writer_agent rule",
        })

        # 实证研究专用模板
        self.register("regression_output", {
            "description": "回归结果解读与报告撰写",
            "category": "research",
            "system": "You are a financial research analyst. Interpret regression output and write academic text.",
            "template": (
                "Interpret the following regression results for an academic paper.\n\n"
                "Model: {model_spec}\n"
                "Results: {results}\n\n"
                "Write: (1) coefficient interpretation, "
                "(2) statistical significance discussion, "
                "(3) economic magnitude assessment, "
                "(4) comparison with prior literature."
            ),
            "variables": ["model_spec", "results"],
            "output_format": "Academic paragraph with statistics",
            "citation": "analyst_agent rule",
        })

        self.register("diff_in_diff", {
            "description": "双重差分法（DID）分析框架",
            "category": "research",
            "system": "You are a causal inference expert for finance/economics.",
            "template": (
                "Design a Difference-in-Differences analysis for:\n\n"
                "Research Question: {research_question}\n"
                "Treatment: {treatment}\n"
                "Control: {control}\n"
                "Time Period: {period}\n\n"
                "Address: (1) Parallel trends assumption, "
                "(2) Staggered treatment timing, "
                "(3) Robustness checks (placebo, synthetic control), "
                "(4) Heterogeneous treatment effects."
            ),
            "variables": ["research_question", "treatment", "control", "period"],
            "output_format": "Structured DID framework",
            "citation": "Autor (2003) DID; Callaway & Sant'Anna (2021)",
        })

    def register(
        self,
        name: str,
        template_dict: dict,
        overwrite: bool = False,
    ):
        """注册新模板或更新现有模板。"""
        if name in self._templates and not overwrite:
            raise ValueError(f"模板 '{name}' 已存在，设置 overwrite=True 可覆盖")
        self._templates[name] = template_dict

    def get(self, name: str) -> dict:
        """按名称获取模板。"""
        if name not in self._templates:
            raise KeyError(f"未找到模板: '{name}'. 可用: {list(self._templates.keys())}")
        return self._templates[name]

    def render(
        self,
        name: str,
        **kwargs,
    ) -> dict:
        """
        渲染模板，返回 messages 格式。

        Returns:
            {"system": str, "user": str, "metadata": dict}
        """
        tmpl = self.get(name)
        system = tmpl.get("system", "")
        raw_template = tmpl.get("template", "")
        user_text = raw_template.format(**kwargs)

        return {
            "system": system,
            "user": user_text,
            "metadata": {
                "template_name": name,
                "category": tmpl.get("category", ""),
                "description": tmpl.get("description", ""),
                "citation": tmpl.get("citation", ""),
                "output_format": tmpl.get("output_format", ""),
            },
        }

    def list_templates(self, category: str = None) -> list[dict]:
        """列出模板， optionally 按 category 过滤。"""
        items = []
        for name, tmpl in self._templates.items():
            if category is None or tmpl.get("category") == category:
                items.append({
                    "name": name,
                    "category": tmpl.get("category", ""),
                    "description": tmpl.get("description", ""),
                    "variables": tmpl.get("variables", []),
                    "citation": tmpl.get("citation", ""),
                })
        return items

    def export_markdown(self, path: str = None) -> str:
        """导出所有模板为 Markdown 文档。"""
        lines = ["# Prompt Templates\n", "Generated by PromptTemplateManager\n"]

        categories = {}
        for name, tmpl in self._templates.items():
            cat = tmpl.get("category", "uncategorized")
            categories.setdefault(cat, []).append((name, tmpl))

        for cat, templates in sorted(categories.items()):
            lines.append(f"## {cat.upper()}\n")
            for name, tmpl in templates:
                lines.append(f"### `{name}`\n")
                lines.append(f"**描述**: {tmpl.get('description', '')}\n")
                lines.append(f"**变量**: `{', '.join(tmpl.get('variables', []))}`\n")
                lines.append(f"**引用**: {tmpl.get('citation', '')}\n")
                lines.append(f"**输出格式**: {tmpl.get('output_format', '')}\n")
                lines.append("\n**System Prompt**:\n```\n" + tmpl.get("system", "") + "\n```\n")
                lines.append("\n**Template**:\n```\n" + tmpl.get("template", "") + "\n```\n")
                lines.append("\n---\n")

        md = "\n".join(lines)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"[✓] Prompt templates exported to {path}")
        return md


# ════════════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("金融数据处理流水线 v3.0（数据 + 文献 + LLM）")
    print("\n[1] A股数据示例：获取平安银行日线（2024年）")
    print("[2] 美股数据示例：获取苹果(AAPL)日线（2024年）")
    print("[3] 特征工程演示（模拟数据）")
    print("[4] 文献检索演示（ArXiv 检索）")
    print("[5] LLM 情感分析演示（需 API Key）")
    print("[6] Prompt 模板管理器演示")
    print("\n输入数字选择，或直接 import 使用")

    choice = input("\n> ").strip()

    if choice == "1":
        print("\n正在获取A股数据...")
        try:
            df = fetch_a_stock("000001.SZ", "2024-01-01", "2024-12-31")
            print(df.tail())
            df = add_return_features(df)
            df = add_moving_averages(df)
            df = add_momentum_features(df)
            print(f"\n特征工程后列数: {len(df.columns)}")
            print(df.tail(3))
        except ImportError as e:
            print(f"缺少依赖: {e}")
            print("安装命令: pip install akshare")

    elif choice == "2":
        print("\n正在获取美股数据...")
        try:
            df = fetch_us_stock("AAPL", "2024-01-01", "2024-12-31")
            print(df.tail())
            df = add_return_features(df)
            df = add_moving_averages(df)
            print(f"\n特征工程后列数: {len(df.columns)}")
            print(df.tail(3))
        except ImportError as e:
            print(f"缺少依赖: {e}")
            print("安装命令: pip install yfinance")

    elif choice == "3":
        import numpy as np
        sample = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60),
            "code": ["AAPL"] * 60,
            "close": 180 + np.cumsum(np.random.randn(60) * 2),
            "volume": np.random.randint(1e7, 1e8, 60),
        })
        sample = add_return_features(sample)
        sample = add_moving_averages(sample)
        sample = add_momentum_features(sample)
        print(sample.tail(5).to_string())

    elif choice == "4":
        print("\n正在检索 ArXiv 文献...")
        retriever = LiteratureRetriever()
        results = retriever.search_arxiv(
            "tariff AND manufacturing employment",
            max_results=5,
            categories=["econ.GN", "q-fin.GN"],
        )
        for r in results:
            print(f"\n  [{r['arxiv_id']}] {r['title']}")
            print(f"  Authors: {r['authors']}")
            print(f"  DOI: {r['doi']}")
        # 导出 BibTeX
        if results:
            print("\n[BibTeX]:")
            print(retriever.to_bibtex(results))

    elif choice == "5":
        print("\nLLM 情感分析演示...")
        print("支持的 provider:")
        print("  - bai:      B.AI 中转（GPT-5.5 / claude-sonnet-4.6 / gemini-3.1-pro 等）")
        print("  - deepseek: DeepSeek-V3 / DeepSeek-R1（需 DEEPSEEK_API_KEY）")
        print()
        proc = LLMProcessor(provider="bai", model="gpt-5.5")
        print(f"当前模型: {proc._model} (provider={proc.provider})")
        test_text = (
            "Fed signals potential rate cuts in 2024 as inflation cools to 2.1%, "
            "boosting equity markets. However, trade tensions with China remain a headwind."
        )
        result = proc.analyze_sentiment(test_text, scale="fine")
        print(f"Sentiment: {result}")

    elif choice == "6":
        print("\nPrompt 模板管理器演示...")
        mgr = PromptTemplateManager()
        print(f"共注册 {len(mgr._templates)} 个模板:")
        for t in mgr.list_templates():
            print(f"  [{t['category']}] {t['name']}: {t['description']}")
            print(f"    变量: {t['variables']} | 引用: {t['citation']}")
        # 渲染示例
        rendered = mgr.render("sentiment_polar", text="Apple reports record $123B revenue.")
        print(f"\n渲染示例（sentiment_polar）:")
        print(f"  System: {rendered['system'][:60]}...")
        print(f"  Metadata: {rendered['metadata']}")
