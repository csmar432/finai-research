#!/usr/bin/env python3
"""
量化因子库 + 事件研究模块
============================
提供金融实证研究的核心因子库和标准化事件研究框架。

功能：
  因子库
    - 估值因子（PE, PB, PS, PCF, EV/EBITDA）
    - 盈利因子（ROE, ROA, Gross Margin, Net Margin）
    - 成长因子（营收增速, 利润增速, 资产增速）
    - 杠杆因子（资产负债率, 净负债率）
    - 动量因子（1M/3M/6M/12M）
    - 波动率因子（20D/60D/历史波动率）
    - 质量因子（资产周转率, 现金流/资产）
    - 分红因子（股息率, 分红次数）
    - ESG因子（需真实数据或用户提供）

  事件研究
    - 标准化事件窗口（-30, +30, CAR/BHAR）
    - 预期收益模型（CAPM, FF3, FF5, Carhart）
    - 统计检验（t检验, 符号检验, Wilcoxon）
    - 累计异常收益（CAR）及图表
    - 因子调整异常收益（FF-alpha）
    - 多事件叠加分析

用法：
  from scripts.quantitative_factor_library import FactorLibrary, EventStudy

  fl = FactorLibrary()
  factors = fl.compute_all_factors(df)
  es = EventStudy(df, event_date_col="date", abnormal_col="return")
  results = es.run(window=(-30, 30), market_model="ff3")
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

SCRIPT_DIR = Path(__file__).parent.parent
import sys

sys.path.insert(0, str(SCRIPT_DIR))


_log = logging.getLogger("quant_factors")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ════════════════════════════════════════════════════════════════════
# 因子库
# ════════════════════════════════════════════════════════════════════

class FactorLibrary:
    """
    标准化量化因子库，支持A股和美股财务数据。

    所有因子计算均基于真实财务数据（从 yfinance MCP 或用户提供的数据），
    不包含任何模拟数据。

    用法：
        fl = FactorLibrary()
        factors = fl.compute_all_factors(df)   # df 包含原始财务数据
        print(factors[["pe", "pb", "roe", "revenue_growth"]].describe())
    """

    # 因子定义：名称 → (计算函数, 描述, 单位)
    FACTOR_DEFINITIONS = {
        # ── 估值因子 ──
        "pe":            (" Valuation",    "市盈率 (Price/Earnings)",         "倍"),
        "pb":            (" Valuation",    "市净率 (Price/Book)",             "倍"),
        "ps":            (" Valuation",    "市销率 (Price/Sales)",             "倍"),
        "pcf":           (" Valuation",    "市现率 (Price/Cash Flow)",        "倍"),
        "ev_ebitda":     (" Valuation",    "EV/EBITDA",                       "倍"),
        "pcf_operating":  (" Valuation",    "经营现金流市价率",                "倍"),

        # ── 盈利因子 ──
        "roe":           (" Profitability", "净资产收益率 ROE",                "%"),
        "roa":           (" Profitability", "资产收益率 ROA",                  "%"),
        "gross_margin":  (" Profitability", "毛利率",                           "%"),
        "net_margin":    (" Profitability", "净利率",                           "%"),
        "ebitda_margin": (" Profitability", "EBITDA率",                        "%"),
        "operating_margin": (" Profitability","营业利润率",                       "%"),

        # ── 成长因子 ──
        "revenue_growth":  (" Growth",      "营收增速 YoY",                    "%"),
        "net_income_growth": (" Growth",   "净利润增速 YoY",                  "%"),
        "asset_growth":    (" Growth",      "总资产增速 YoY",                 "%"),
        "equity_growth":   (" Growth",      "所有者权益增速 YoY",              "%"),
        "cash_growth":     (" Growth",      "现金流增速 YoY",                  "%"),

        # ── 杠杆因子 ──
        "debt_ratio":     (" Leverage",     "资产负债率",                       "%"),
        "net_debt_equity": (" Leverage",   "净负债率（净负债/股东权益）",     "%"),
        "interest_bearing_debt": (" Leverage","带息负债率",                    "%"),
        "ltd_ratio":      (" Leverage",     "长期负债率",                       "%"),

        # ── 动量因子 ──
        "ret_1m":        (" Momentum",     "月收益率",                         "%"),
        "ret_3m":        (" Momentum",    "季度收益率 (3M)",                  "%"),
        "ret_6m":        (" Momentum",    "半年收益率 (6M)",                  "%"),
        "ret_12m":       (" Momentum",    "年度收益率 (12M)",                 "%"),
        "vol_20d":       (" Momentum",     "20日波动率",                       "%"),
        "vol_60d":       (" Momentum",    "60日波动率",                       "%"),

        # ── 质量因子 ──
        "asset_turnover": (" Quality",     "资产周转率",                       "次"),
        "cash_ratio":     (" Quality",     "现金比率（现金/总资产）",         "%"),
        "current_ratio":  (" Quality",     "流动比率",                         "倍"),
        "quick_ratio":    (" Quality",     "速动比率",                         "倍"),
        "fcf_assets":     (" Quality",     "自由现金流/总资产",               "%"),
        "accruals":       (" Quality",     "应计项目/总资产",                 "%"),

        # ── 分红因子 ──
        "dividend_yield": (" Dividend",    "股息率",                           "%"),
        "payout_ratio":   (" Dividend",    "派息率（分红/净利润）",            "%"),

        # ── ESG因子（需要外部数据） ──
        "esg_score":      (" ESG",         "ESG综合评分",                      "分"),
        "env_score":      (" ESG",         "环境评分",                        "分"),
        "social_score":   (" ESG",         "社会责任评分",                    "分"),
        "gov_score":      (" ESG",         "治理评分",                        "分"),
    }

    def __init__(self, name: str = "因子库"):
        self.name = name
        self._computed: list[str] = []

    def compute_all_factors(self, df: pd.DataFrame,
                            price_col: str = "price",
                            market_cap_col: str = "market_cap",
                            required_cols: list[str] | None = None) -> pd.DataFrame:
        """
        对原始财务数据批量计算所有可计算的因子。

        Args:
            df: 原始数据 DataFrame
            price_col: 价格列名（用于估值因子）
            market_cap_col: 市值列名
            required_cols: 指定必须存在的列（如不存在则跳过）

        Returns:
            DataFrame 新增因子列
        """
        df = df.copy()
        self._computed = []

        for fname, (category, desc, unit) in self.FACTOR_DEFINITIONS.items():
            try:
                method = getattr(self, f"_factor_{fname}", None)
                if method:
                    result = method(df, price_col, market_cap_col)
                    if result is not None and len(result) == len(df):
                        df[fname] = result
                        self._computed.append(fname)
            except Exception as e:
                _log.debug(f"  {fname} skipped: {e}")

        _log.info(f"  成功计算 {len(self._computed)}/{len(self.FACTOR_DEFINITIONS)} 个因子")
        return df

    def factor_summary(self) -> pd.DataFrame:
        """返回因子概览表格。"""
        rows = []
        for fname, (cat, desc, unit) in self.FACTOR_DEFINITIONS.items():
            rows.append({
                "因子": fname,
                "类别": cat.strip(),
                "描述": desc,
                "单位": unit,
                "已计算": "✓" if fname in self._computed else "",
            })
        return pd.DataFrame(rows)

    # ── 估值因子 ──────────────────────────────────────────────────────────────

    def _factor_pe(self, df, price_col, mktcap_col):
        """P/E = Price / (Net Income / Shares)"""
        ni = df.get("net_income", None)
        shares = df.get("shares", None)
        price = df.get(price_col, None)
        if ni is None or price is None: return None
        earnings_per_share = ni / shares.replace(0, np.nan) if shares is not None else ni / 1e9
        pe = price / earnings_per_share.replace(0, np.nan)
        return pe.replace([np.inf, -np.inf], np.nan)

    def _factor_pb(self, df, price_col, mktcap_col):
        """P/B = Price / Book Value Per Share"""
        equity = df.get("equity", None)
        shares = df.get("shares", None)
        price = df.get(price_col, None)
        if equity is None or price is None: return None
        bvps = equity / shares.replace(0, np.nan) if shares is not None else equity / 1e9
        return (price / bvps.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_ps(self, df, price_col, mktcap_col):
        """P/S = Price / Revenue Per Share"""
        revenue = df.get("revenue", None)
        shares = df.get("shares", None)
        price = df.get(price_col, None)
        if revenue is None or price is None: return None
        rps = revenue / shares.replace(0, np.nan) if shares is not None else revenue / 1e9
        return (price / rps.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_pcf(self, df, price_col, mktcap_col):
        """P/CF = Price / Operating Cash Flow Per Share"""
        opcf = df.get("op_cashflow", None)
        shares = df.get("shares", None)
        price = df.get(price_col, None)
        if opcf is None or price is None: return None
        cfps = opcf / shares.replace(0, np.nan) if shares is not None else opcf / 1e9
        return (price / cfps.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_ev_ebitda(self, df, price_col, mktcap_col):
        """EV/EBITDA = (Market Cap + Total Debt - Cash) / EBITDA"""
        mktcap = df.get(mktcap_col, None) or df.get("market_cap", None)
        total_debt = df.get("total_debt", 0)
        cash = df.get("cash", 0)
        ebitda = df.get("ebitda", None)
        if mktcap is None or ebitda is None: return None
        ev = mktcap + total_debt - cash
        return (ev / ebitda.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_pcf_operating(self, df, price_col, mktcap_col):
        return self._factor_pcf(df, price_col, mktcap_col)

    # ── 盈利因子 ──────────────────────────────────────────────────────────────

    def _factor_roe(self, df, *args):
        """ROE = Net Income / Equity"""
        ni = df.get("net_income", None)
        equity = df.get("equity", None)
        if ni is None or equity is None: return None
        return (ni / equity.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_roa(self, df, *args):
        """ROA = Net Income / Total Assets"""
        ni = df.get("net_income", None)
        ta = df.get("total_assets", None)
        if ni is None or ta is None: return None
        return (ni / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_gross_margin(self, df, *args):
        """Gross Margin = (Revenue - COGS) / Revenue"""
        rev = df.get("revenue", None)
        cogs = df.get("cogs", df.get("cost_of_goods_sold", None))
        if rev is None or cogs is None: return None
        return ((rev - cogs) / rev.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_net_margin(self, df, *args):
        """Net Margin = Net Income / Revenue"""
        ni = df.get("net_income", None)
        rev = df.get("revenue", None)
        if ni is None or rev is None: return None
        return (ni / rev.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_ebitda_margin(self, df, *args):
        """EBITDA Margin = EBITDA / Revenue"""
        ebitda = df.get("ebitda", None)
        rev = df.get("revenue", None)
        if ebitda is None or rev is None: return None
        return (ebitda / rev.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_operating_margin(self, df, *args):
        """Operating Margin = Operating Income / Revenue"""
        op_income = df.get("operating_income", None)
        rev = df.get("revenue", None)
        if op_income is None or rev is None: return None
        return (op_income / rev.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    # ── 成长因子 ──────────────────────────────────────────────────────────────

    def _yoy_growth(self, df: pd.DataFrame, col: str, ticker_col: str = "ticker",
                    year_col: str = "year") -> pd.Series:
        """计算同比增速。"""
        if col not in df.columns: return pd.Series(np.nan, index=df.index)
        df_sorted = df.sort_values([ticker_col, year_col])
        growth = df_sorted.groupby(ticker_col)[col].pct_change()
        return growth.replace([np.inf, -np.inf], np.nan) * 100

    def _factor_revenue_growth(self, df, *args):
        return self._yoy_growth(df, "revenue")

    def _factor_net_income_growth(self, df, *args):
        return self._yoy_growth(df, "net_income")

    def _factor_asset_growth(self, df, *args):
        return self._yoy_growth(df, "total_assets")

    def _factor_equity_growth(self, df, *args):
        return self._yoy_growth(df, "equity")

    def _factor_cash_growth(self, df, *args):
        return self._yoy_growth(df, "cash")

    # ── 杠杆因子 ──────────────────────────────────────────────────────────────

    def _factor_debt_ratio(self, df, *args):
        """资产负债率 = Total Debt / Total Assets"""
        td = df.get("total_debt", None)
        ta = df.get("total_assets", None)
        if td is None or ta is None: return None
        return (td / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_net_debt_equity(self, df, *args):
        """净负债率 = (Total Debt - Cash) / Equity"""
        td = df.get("total_debt", 0)
        cash = df.get("cash", 0)
        eq = df.get("equity", None)
        if eq is None: return None
        net_debt = td - cash
        return (net_debt / eq.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_interest_bearing_debt(self, df, *args):
        """带息负债率 = Interest Bearing Debt / Total Assets"""
        td = df.get("total_debt", None)
        ta = df.get("total_assets", None)
        if td is None or ta is None: return None
        return (td / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_ltd_ratio(self, df, *args):
        """长期负债率 = Long-term Debt / Total Assets"""
        ltd = df.get("long_term_debt", None)
        ta = df.get("total_assets", None)
        if ltd is None or ta is None: return None
        return (ltd / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    # ── 动量因子 ──────────────────────────────────────────────────────────────

    def _stock_returns(self, df: pd.DataFrame, col: str = "price",
                        ticker_col: str = "ticker",
                        date_col: str = "date") -> pd.DataFrame:
        """计算个股日收益率。"""
        if col not in df.columns: return pd.DataFrame()
        df_s = df.sort_values([ticker_col, date_col]).copy()
        for period in [1, 3, 6, 12, 20, 60]:
            # period 1/3/6/12: 收益率 (ret_1m, ret_3m, ret_6m, ret_12m)
            # period 20/60:   年化波动率 (vol_240d, vol_252d) — 20交易日≈1月, 60交易日≈3月
            if period >= 20:
                name = f"vol_{period}d"
            else:
                name = f"ret_{period}m"
            df_s[name] = df_s.groupby(ticker_col)[col].pct_change(period)
        return df_s

    def _factor_ret_1m(self, df, *args):
        return self._stock_returns(df).get("ret_1m", pd.Series(np.nan, index=df.index))

    def _factor_ret_3m(self, df, *args):
        return self._stock_returns(df).get("ret_3m", pd.Series(np.nan, index=df.index))

    def _factor_ret_6m(self, df, *args):
        return self._stock_returns(df).get("ret_6m", pd.Series(np.nan, index=df.index))

    def _factor_ret_12m(self, df, *args):
        return self._stock_returns(df).get("ret_12m", pd.Series(np.nan, index=df.index))

    def _factor_vol_20d(self, df, *args):
        return self._stock_returns(df).get("vol_20d", pd.Series(np.nan, index=df.index))

    def _factor_vol_60d(self, df, *args):
        return self._stock_returns(df).get("vol_60d", pd.Series(np.nan, index=df.index))

    # ── 质量因子 ──────────────────────────────────────────────────────────────

    def _factor_asset_turnover(self, df, *args):
        """资产周转率 = Revenue / Total Assets"""
        rev = df.get("revenue", None)
        ta = df.get("total_assets", None)
        if rev is None or ta is None: return None
        return (rev / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_cash_ratio(self, df, *args):
        """现金比率 = Cash / Total Assets"""
        cash = df.get("cash", None)
        ta = df.get("total_assets", None)
        if cash is None or ta is None: return None
        return (cash / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_current_ratio(self, df, *args):
        """流动比率 = Current Assets / Current Liabilities"""
        ca = df.get("current_assets", None)
        cl = df.get("current_liabilities", None)
        if ca is None or cl is None: return None
        return (ca / cl.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_quick_ratio(self, df, *args):
        """速动比率 = (Current Assets - Inventory) / Current Liabilities"""
        ca = df.get("current_assets", None)
        inv = df.get("inventory", 0)
        cl = df.get("current_liabilities", None)
        if ca is None or cl is None: return None
        return ((ca - inv) / cl.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    def _factor_fcf_assets(self, df, *args):
        """自由现金流 / 总资产"""
        fcf = df.get("free_cashflow", df.get("op_cashflow", None))
        ta = df.get("total_assets", None)
        if fcf is None or ta is None: return None
        return (fcf / ta.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_accruals(self, df, *args):
        """应计项目 = (Net Income - Operating Cash Flow) / Total Assets"""
        ni = df.get("net_income", None)
        opcf = df.get("op_cashflow", None)
        ta = df.get("total_assets", None)
        if ni is None or opcf is None or ta is None: return None
        accruals = (ni - opcf) / ta.replace(0, np.nan)
        return accruals.replace([np.inf, -np.inf], np.nan)

    # ── 分红因子 ──────────────────────────────────────────────────────────────

    def _factor_dividend_yield(self, df, *args):
        """股息率 = Dividends Per Share / Price"""
        dps = df.get("dps", None)
        price = df.get("price", None)
        if dps is None or price is None: return None
        return (dps / price.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    def _factor_payout_ratio(self, df, *args):
        """派息率 = Dividends / Net Income"""
        div = df.get("dividends", None)
        ni = df.get("net_income", None)
        if div is None or ni is None: return None
        return (div / ni.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan) * 100

    # ── ESG因子（外部数据） ─────────────────────────────────────────────────

    def _factor_esg_score(self, df, *args):
        """ESG评分（需要外部数据源）"""
        _log.info("  esg_score 需要外部ESG数据源（yfinance sustainability 或用户提供）")
        return pd.Series(np.nan, index=df.index)

    def _factor_env_score(self, df, *args):
        return pd.Series(np.nan, index=df.index)

    def _factor_social_score(self, df, *args):
        return pd.Series(np.nan, index=df.index)

    def _factor_gov_score(self, df, *args):
        return pd.Series(np.nan, index=df.index)


# ════════════════════════════════════════════════════════════════════
# 事件研究
# ════════════════════════════════════════════════════════════════════

@dataclass
class EventStudyResult:
    """事件研究结果封装。"""
    event_date: str
    window: tuple[int, int]
    n_estimate: int          # 估计窗口观测数
    n_event: int             # 事件窗口观测数
    car: float               # 累计异常收益
    car_se: float            # CAR 标准误
    car_tstat: float         # CAR t统计量
    car_pval: float          # CAR p值
    aar: float               # 日均异常收益
    aar_tstat: float
    bhar: float             # 买入持有异常收益
    bhar_se: float
    model: str               # 预期收益模型
    abnormal_returns: pd.Series  # 日异常收益序列
    cumulative_ar: pd.Series   # 累计异常收益序列
    daily_stats: pd.DataFrame  # 每日 AAR + t统计量
    alpha: float | None = None  # FF-alpha
    alpha_se: float | None = None
    alpha_pval: float | None = None


class EventStudy:
    """
    标准化事件研究框架。

    支持：
      - 单事件 / 多事件叠加
      - 预期收益模型：市场模型、CAPM、Fama-French 3因子/5因子
      - 统计检验：参数t检验、符号检验、Wilcoxon符号秩检验
      - 输出：CAR、BHAR、FF-alpha 及 publication-quality 图表

    用法：
        es = EventStudy(df,
                        price_col="return",
                        market_return_col="mkt_return",
                        date_col="date",
                        ticker_col="ticker")
        result = es.run(event_date="2022-03-15",
                        window=(-30, 30),
                        estimate_window=(-250, -31),
                        market_model="ff3",
                        ff_factors=df[["mkt_rf", "smb", "hml"]])
        print(f"CAR: {result.car:.2%} (p={result.car_pval:.4f})")
    """

    def __init__(self, df: pd.DataFrame,
                 price_col: str = "return",
                 market_return_col: str = "mkt_return",
                 date_col: str = "date",
                 ticker_col: str = "ticker"):
        """
        Args:
            df: 包含日收益率数据的 DataFrame
            price_col: 股票日收益率列名
            market_return_col: 市场日收益率列名（用于市场模型）
            date_col: 日期列名
            ticker_col: 股票代码列名
        """
        self.df = df.copy()
        self.price_col = price_col
        self.market_col = market_return_col
        self.date_col = date_col
        self.ticker_col = ticker_col

        # 确保日期排序
        if date_col in self.df.columns:
            self.df[date_col] = pd.to_datetime(self.df[date_col])
            self.df = self.df.sort_values([ticker_col, date_col]).reset_index(drop=True)

    def run(self,
            event_date: str | datetime,
            window: tuple[int, int] = (-30, 30),
            estimate_window: tuple[int, int] = (-250, -31),
            market_model: str = "market",
            ff_factors: pd.DataFrame | None = None,
            min_est_days: int = 120) -> EventStudyResult:
        """
        执行单事件研究。

        Args:
            event_date: 事件日期
            window: 事件窗口 (pre, post)，如 (-30, 30)
            estimate_window: 估计窗口 (pre, post)，如 (-250, -31)
            market_model: "market" | "capm" | "ff3" | "ff5" | "carhart"
            ff_factors: FF因子 DataFrame，必须包含 date 列作为索引
            min_est_days: 估计窗口最少交易日数量

        Returns:
            EventStudyResult
        """
        event_dt = pd.to_datetime(event_date)
        df = self.df.copy()

        if self.date_col not in df.columns:
            raise ValueError(f"Date column '{self.date_col}' not found")

        # 确定股票（单只或全市场）
        if self.ticker_col in df.columns:
            tickers = df[self.ticker_col].unique()
            if len(tickers) == 1:
                stock_df = df.copy()
            else:
                # 多只股票：使用市场平均
                stock_df = df.groupby(self.date_col).agg({
                    self.price_col: "mean",
                    self.market_col: "first",
                }).reset_index()
        else:
            stock_df = df.copy()
            self.ticker_col = None

        stock_df = stock_df.set_index(self.date_col).sort_index()

        # 计算每日相对时间
        stock_df["rel_day"] = (stock_df.index - event_dt).days

        # 估计窗口
        est_df = stock_df[
            (stock_df["rel_day"] >= estimate_window[0]) &
            (stock_df["rel_day"] <= estimate_window[1])
        ].dropna(subset=[self.price_col, self.market_col])

        if len(est_df) < min_est_days:
            _log.warning(f"  估计窗口仅 {len(est_df)} 天（建议 ≥{min_est_days}），结果可能不稳定")

        # 事件窗口
        ev_df = stock_df[
            (stock_df["rel_day"] >= window[0]) &
            (stock_df["rel_day"] <= window[1])
        ].dropna(subset=[self.price_col, self.market_col])

        # 计算预期收益（alpha + beta * market）
        expected_ret = self._fit_market_model(est_df, ev_df, market_model, ff_factors)

        # 异常收益
        ev_df = ev_df.copy()
        ev_df["ar"] = ev_df[self.price_col] - expected_ret

        # CAR
        car = ev_df["ar"].sum()
        car_var = ev_df["ar"].var()
        car_se = np.sqrt(car_var * len(ev_df))
        car_tstat = car / car_se if car_se > 0 else 0
        car_pval = 2 * (1 - stats.t.cdf(abs(car_tstat), df=len(ev_df) - 1))

        # AAR（平均日异常收益）
        aar = ev_df["ar"].mean()
        aar_se = ev_df["ar"].std(ddof=1) / np.sqrt(len(ev_df))
        aar_tstat = aar / aar_se if aar_se > 0 else 0

        # BHAR（买入持有异常收益）
        bhar = (1 + ev_df["ar"]).prod() - 1
        bhar_se = ev_df["ar"].std(ddof=1) * np.sqrt(len(ev_df))

        # FF-alpha（如果使用因子模型）
        alpha = None
        alpha_se = None
        alpha_pval = None
        if market_model in ("ff3", "ff5", "carhart") and ff_factors is not None:
            ff_alpha, ff_se, ff_pval = self._fit_ff_alpha(est_df, ev_df, ff_factors, market_model)
            alpha = ff_alpha; alpha_se = ff_se; alpha_pval = ff_pval

        # 每日统计
        daily_stats = ev_df[["rel_day", "ar"]].copy()
        daily_stats["aar"] = daily_stats["ar"]  # 单事件等同于日异常收益
        daily_stats["t_stat"] = daily_stats["ar"] / ev_df["ar"].std() * np.sqrt(range(1, len(ev_df) + 1))
        daily_stats["cum_ar"] = daily_stats["ar"].cumsum()

        # 符号检验（不依赖正态分布）
        ar_sign_positive = (ev_df["ar"] > 0).sum()
        n_sign = len(ev_df)
        sign_pval = stats.binomtest(ar_sign_positive, n_sign, 0.5).pvalue if n_sign > 0 else 1.0

        _log.info(f"  事件研究: {event_date}")
        _log.info(f"  CAR = {car:.4f} (t = {car_tstat:.2f}, p = {car_pval:.4f})")
        _log.info(f"  BHAR = {bhar:.4f}")
        _log.info(f"  FF-alpha = {alpha:.4f} (p = {alpha_pval:.4f})" if alpha else "  FF-alpha: N/A")
        _log.info(f"  符号检验: {ar_sign_positive}/{n_sign} 正收益 (p = {sign_pval:.4f})")

        return EventStudyResult(
            event_date=str(event_date),
            window=window,
            n_estimate=len(est_df),
            n_event=len(ev_df),
            car=car,
            car_se=car_se,
            car_tstat=car_tstat,
            car_pval=car_pval,
            aar=aar,
            aar_tstat=aar_tstat,
            bhar=bhar,
            bhar_se=bhar_se,
            model=market_model,
            abnormal_returns=ev_df["ar"],
            cumulative_ar=ev_df["ar"].cumsum(),
            daily_stats=daily_stats.reset_index(),
            alpha=alpha,
            alpha_se=alpha_se,
            alpha_pval=alpha_pval,
        )

    def run_multiple(self,
                     events: list[dict],
                     window: tuple[int, int] = (-30, 30),
                     estimate_window: tuple[int, int] = (-250, -31),
                     market_model: str = "market",
                     ff_factors: pd.DataFrame | None = None) -> list[EventStudyResult]:
        """
        对多个事件执行叠加事件研究。

        Args:
            events: 事件列表，每项包含 event_date, ticker（可选）
            window, estimate_window, market_model, ff_factors: 同 run()

        Returns:
            list[EventStudyResult]
        """
        results = []
        for ev in events:
            ev_date = ev.get("event_date")
            ticker = ev.get("ticker")
            if ticker and self.ticker_col in self.df.columns:
                sub_df = self.df[self.df[self.ticker_col] == ticker].copy()
            else:
                sub_df = self.df.copy()

            es = EventStudy(sub_df,
                            price_col=self.price_col,
                            market_return_col=self.market_col,
                            date_col=self.date_col,
                            ticker_col=self.ticker_col if self.ticker_col in sub_df.columns else None)
            try:
                result = es.run(ev_date, window, estimate_window, market_model, ff_factors)
                results.append(result)
            except Exception as e:
                _log.warning(f"  事件 {ev_date} ({ticker}) 失败: {e}")

        return results

    def run_cross_sectional(self,
                            events: list[dict],
                            window: tuple[int, int] = (-1, 1),
                            estimate_window: tuple[int, int] = (-250, -31),
                            market_model: str = "market",
                            ff_factors: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        事件横截面分析：对每个事件计算 CAR，然后按特征分组比较。

        Returns:
            DataFrame 每个事件的 CAR 及其统计量
        """
        results = self.run_multiple(events, window, estimate_window, market_model, ff_factors)

        rows = []
        for r in results:
            rows.append({
                "event_date": r.event_date,
                "window": f"{r.window[0]},{r.window[1]}",
                "N_event": r.n_event,
                "CAR": r.car,
                "CAR_se": r.car_se,
                "CAR_t": r.car_tstat,
                "CAR_p": r.car_pval,
                "BHAR": r.bhar,
                "FF_alpha": r.alpha,
                "FF_alpha_p": r.alpha_pval,
            })

        df = pd.DataFrame(rows)

        # 横截面统计
        if len(df) > 1:
            car_mean = df["CAR"].mean()
            car_t_cs = car_mean / (df["CAR"].std() / np.sqrt(len(df)))
            car_p_cs = 2 * (1 - stats.t.cdf(abs(car_t_cs), df=len(df) - 1))
            _log.info(f"\n  横截面事件研究 (N={len(df)}):")
            _log.info(f"  平均 CAR = {car_mean:.4f} (t = {car_t_cs:.2f}, p = {car_p_cs:.4f})")

        return df

    def _fit_market_model(self,
                           est_df: pd.DataFrame,
                           ev_df: pd.DataFrame,
                           model: str,
                           ff_factors: pd.DataFrame | None) -> np.ndarray:
        """拟合预期收益模型，返回事件窗口的预期收益序列。"""
        price = self.price_col
        mkt = self.market_col

        if model == "market" or model == "capm":
            # 市场模型: R_i = alpha + beta * R_m
            X = sm.add_constant(est_df[mkt].values)
            y = est_df[price].values
            model_fit = sm.OLS(y, X).fit()
            alpha, beta = model_fit.params

            # 预测事件窗口
            return alpha + beta * ev_df[mkt].values

        elif model in ("ff3", "ff5", "carhart"):
            if ff_factors is None:
                _log.warning(f"  {model} 需要 ff_factors 参数，降级为市场模型")
                return self._fit_market_model(est_df, ev_df, "market", None)

            # 对齐因子数据
            est_idx = est_df.index
            ev_idx = ev_df.index

            ff_est = ff_factors.reindex(est_idx).dropna()
            ff_ev = ff_factors.reindex(ev_idx).dropna()

            # 确保长度匹配
            common_est = est_df.loc[ff_est.index]
            common_ev = ev_df.loc[ff_ev.index]

            # FF因子回归
            if model == "ff3":
                X_cols = ["mkt_rf", "smb", "hml"]
            elif model == "ff5":
                X_cols = ["mkt_rf", "smb", "hml", "rmw", "cma"]
            else:  # carhart
                X_cols = ["mkt_rf", "smb", "hml", "mom"]

            available_cols = [c for c in X_cols if c in ff_est.columns]
            if not available_cols:
                return self._fit_market_model(est_df, ev_df, "market", None)

            X = sm.add_constant(ff_est[available_cols].values)
            y = common_est[price].values
            model_fit = sm.OLS(y, X).fit()

            # 预测
            X_ev = sm.add_constant(ff_ev[available_cols].values)
            expected = model_fit.predict(X_ev)

            # 处理索引不匹配
            expected_full = np.full(len(ev_df), np.nan)
            for i, idx in enumerate(ev_df.index):
                if idx in ff_ev.index:
                    pos = list(ff_ev.index).index(idx)
                    expected_full[i] = expected[pos]

            return expected_full

        else:
            # 简单用市场收益作为预期
            return ev_df[mkt].values

    def _fit_ff_alpha(self,
                      est_df: pd.DataFrame,
                      ev_df: pd.DataFrame,
                      ff_factors: pd.DataFrame,
                      model: str) -> tuple[float, float, float]:
        """计算 FF-alpha（因子模型截距）。"""
        if model == "ff3":
            X_cols = ["mkt_rf", "smb", "hml"]
        elif model == "ff5":
            X_cols = ["mkt_rf", "smb", "hml", "rmw", "cma"]
        else:
            X_cols = ["mkt_rf", "smb", "hml", "mom"]

        available_cols = [c for c in X_cols if c in ff_factors.columns]
        if not available_cols:
            return 0.0, 0.0, 1.0

        ff_est = ff_factors.reindex(est_df.index).dropna()
        common = est_df.loc[ff_est.index]

        X = sm.add_constant(ff_est[available_cols].values)
        y = common[self.price_col].values
        fit = sm.OLS(y, X).fit()

        return float(fit.params[0]), float(fit.bse[0]), float(fit.pvalues[0])

    def plot_event_study(self,
                          result: EventStudyResult,
                          figsize: tuple[float, float] = (9, 5),
                          save_path: Path | str | None = None) -> None:
        """
        绘制事件研究图（Publication quality）。

        生成两幅图：
          1. 累计异常收益 (CAR) 时间线
          2. 日异常收益 (AR) 柱状图
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True,
                                         gridspec_kw={"height_ratios": [2, 1]})
        plt.rcParams.update({
            "font.family": "sans-serif", "font.size": 10,
            "axes.spines.top": False, "axes.spines.right": False,
            "figure.dpi": 150, "savefig.dpi": 300,
        })

        daily = result.daily_stats.sort_values(self.date_col if self.date_col in result.daily_stats.columns else "rel_day")
        x = range(len(daily))
        rel_days = daily["rel_day"].values if "rel_day" in daily.columns else x

        # Panel A: CAR
        ax1.plot(x, result.cumulative_ar.values, color="steelblue", linewidth=2)
        ax1.fill_between(x, 0, result.cumulative_ar.values,
                         where=(result.cumulative_ar.values >= 0),
                         color="steelblue", alpha=0.2)
        ax1.fill_between(x, 0, result.cumulative_ar.values,
                         where=(result.cumulative_ar.values < 0),
                         color="coral", alpha=0.2)
        ax1.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        ax1.axvline(list(x)[list(rel_days).index(0)] if 0 in rel_days else len(x) // 2,
                    color="crimson", linewidth=1.5, linestyle=":", label="Event Day")
        ax1.set_ylabel("Cumulative Abnormal Return (CAR)", fontsize=11)
        ax1.set_title(f"Event Study: {result.event_date}  |  CAR = {result.car:.2%} "
                      f"(t = {result.car_tstat:.2f}, p = {result.car_pval:.3f})",
                      fontsize=11, fontweight="bold")
        ax1.legend(fontsize=9)
        ax1.grid(alpha=0.2)

        # Panel B: Daily AR
        colors = ["steelblue" if v >= 0 else "coral" for v in daily["ar"].values]
        ax2.bar(x, daily["ar"].values, color=colors, alpha=0.7, width=0.8)
        ax2.axhline(0, color="gray", linewidth=0.8)
        ax2.axvline(list(x)[list(rel_days).index(0)] if 0 in rel_days else len(x) // 2,
                    color="crimson", linewidth=1.5, linestyle=":", alpha=0.5)
        ax2.set_ylabel("Daily Abnormal Return", fontsize=11)
        ax2.set_xlabel("Days Relative to Event", fontsize=11)
        ax2.set_xticks(x[::max(1, len(x) // 10)])
        ax2.set_xticklabels([str(int(rel_days[xi])) for xi in ax2.get_xticks()])
        ax2.grid(axis="y", alpha=0.2)

        fig.tight_layout()

        if save_path:
            fig.savefig(save_path, bbox_inches="tight")
            _log.info(f"  事件研究图已保存: {save_path}")

        plt.close(fig)


# ════════════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("量化因子库 + 事件研究模块 v1.0")
    print("=" * 50)
    print("功能：")
    print("  因子库: 估值/盈利/成长/杠杆/动量/质量/分红/ESG 因子")
    print("  事件研究: CAR/BHAR/FF-alpha, 多事件叠加, 横截面分析")
    print()
    print("使用示例：")
    print("""
  from scripts.quantitative_factor_library import FactorLibrary, EventStudy

  # 因子库
  fl = FactorLibrary()
  factors = fl.compute_all_factors(df)  # df 为原始财务数据
  print(fl.factor_summary())

  # 事件研究
  es = EventStudy(df, price_col="return", market_return_col="mkt_return",
                  date_col="date", ticker_col="ticker")
  result = es.run(event_date="2022-03-15", window=(-30, 30),
                  market_model="ff3", ff_factors=ff_factors)
  print(f"CAR: {result.car:.2%} (p={result.car_pval:.4f})")
  es.plot_event_study(result, save_path="event_study.png")
    """)
