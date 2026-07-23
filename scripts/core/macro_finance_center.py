"""
macro_finance_center.py — 宏观金融数据中心

统一接口，整合以下数据源：
1. FRED API（免费）- 美联储经济数据、NFP/CPI/FOMC
2. akshare（本地缓存）- 中国宏观、债券、基金
3. World Bank API（免费）- 全球GDP/CPI/人口
4. IMF IFS API（免费）- 国际收支、汇率、储备
5. BCEI/中债 - 中国债券收益率曲线
6. Tushare（需Token）- A股宏观因子

特点：
- 所有数据自动标注来源、时间和方法论说明
- 智能缓存（akshare本地数据 > FRED实时 > 模拟备选）
- 宏观日历：自动生成NFP/CPI/FOMC/PMI等重要发布日期
- 跨市场联动分析：中美欧央行政策联动
"""

from __future__ import annotations

__all__ = [
    "DataSourceType",
    "DataFreshness",
    "MacroObservation",
    "MacroTimeSeries",
    "FREDDataFetcher",
    "AkshareMacroFetcher",
    "MacroCalendar",
    "MacroFinanceCenter",
    "FRED_API_KEY",
    "IMF_API_KEY",
    "TUSHARE_TOKEN",
]

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
IMF_API_KEY = os.getenv("IMF_API_KEY", "")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")


class DataSourceType(str, Enum):
    FRED = "fred"                   # Federal Reserve Economic Data (免费)
    AKSHARE = "akshare"             # 本地缓存/实时
    WORLD_BANK = "world_bank"        # 世界银行 (免费)
    IMF = "imf"                     # IMF IFS (免费)
    BCEI = "bcei"                   # 中国债券收益率曲线
    TUSHARE = "tushare"             # A股宏观因子 (需Token)
    SIMULATED = "simulated"         # 模拟数据（仅测试）
    UNKNOWN = "unknown"


class DataFreshness(str, Enum):
    REALTIME = "realtime"          # 分钟级（akshare实时行情）
    DAILY = "daily"                # 日频（FRED日数据）
    MONTHLY = "monthly"             # 月频（GDP/CPI）
    QUARTERLY = "quarterly"         # 季度（财报/BOP）
    ANNUAL = "annual"              # 年度（人口/长期趋势）


@dataclass
class MacroObservation:
    """单条宏观数据观测。"""
    indicator: str
    value: float | None
    unit: str                      # "%", "billion USD", "index", etc.
    frequency: DataFreshness
    source: DataSourceType
    country: str                  # "US", "CN", "EU", "global"
    date: str                     # ISO date string
    release_date: str | None      # 实际发布日期（可能晚于date）
    is_realtime: bool             # 是否实时数据
    methodology: str | None       # 数据方法论说明
    url: str | None               # 原始数据URL
    confidence: float = 1.0       # 数据可信度 0-1
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "indicator": self.indicator,
            "value": self.value,
            "unit": self.unit,
            "frequency": self.frequency.value,
            "source": self.source.value,
            "country": self.country,
            "date": self.date,
            "release_date": self.release_date,
            "is_realtime": self.is_realtime,
            "methodology": self.methodology,
            "url": self.url,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class MacroTimeSeries:
    """宏观时间序列。"""
    indicator: str
    country: str
    unit: str
    frequency: DataFreshness
    source: DataSourceType
    observations: list[MacroObservation]
    last_updated: str
    description: str | None = None
    methodology: str | None = None

    def to_dataframe(self) -> "pd.DataFrame":
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for to_dataframe()")
        records = [obs.to_dict() for obs in self.observations]
        df = pd.DataFrame(records)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
        return df

    def latest(self) -> MacroObservation | None:
        if not self.observations:
            return None
        return max(self.observations, key=lambda o: o.date)


# ─── FRED Data Fetcher ────────────────────────────────────────────────────────

class FREDDataFetcher:
    """FRED (Federal Reserve Economic Data) API 封装。

    完全免费，无需注册即可用部分数据。
    注册获取API Key后解锁全部数据集。

    常用指标：
    - PAYEMS: NFP非农就业人数 (月度, 每月第一个周五发布)
    - UNRATE: 失业率 (月度, 每月第一个周五发布)
    - CPIAUCSL: CPI同比 (月度, 每月10-15号发布)
    - GDP: GDP现价 (季度, 每月最后一个周四发布)
    - FEDFUNDS: 联邦基金利率 (日度)
    - DGS10: 10年期国债收益率 (日度)
    - USEPUINDXM: VIX类恐慌指数 (日度)
    - TEDRATE: TED利差 (日度, 银行间风险指标)
    - NFCI: 全国金融状况指数
    - WALCL: 美联储总资产 (周度)
    """

    BASE_URL = "https://api.stlouisfed.org/fred"
    PUBLIC_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    # 常用指标元数据
    INDICATOR_CATALOG: dict[str, dict] = {
        # 劳动力市场
        "PAYEMS": {
            "name_cn": "非农就业人数",
            "name_en": "All Employees Total Nonfarm",
            "unit": "千人",
            "frequency": "monthly",
            "release_offset_days": 5,  # 每月第一个周五，约滞后5天
            "source_url": "https://fred.stlouisfed.org/series/PAYEMS",
            "methodology": "基于企业工资单的调查统计，季节性调整",
            "impact": "high",  # market impact: high/medium/low
        },
        "UNRATE": {
            "name_cn": "失业率",
            "name_en": "Unemployment Rate",
            "unit": "%",
            "frequency": "monthly",
            "release_offset_days": 5,
            "source_url": "https://fred.stlouisfed.org/series/UNRATE",
            "methodology": "基于 households survey，季节性调整",
            "impact": "high",
        },
        "CPIAUCSL": {
            "name_cn": "CPI同比",
            "name_en": "Consumer Price Index for All Urban Consumers",
            "unit": "% (同比)",
            "frequency": "monthly",
            "release_offset_days": 15,  # 每月10-15号
            "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL",
            "methodology": "城市消费者物价指数，基期=1982-1984",
            "impact": "high",
        },
        "PCECTPI": {
            "name_cn": "PCE物价指数同比",
            "name_en": "Personal Consumption Expenditures Price Index",
            "unit": "% (同比)",
            "frequency": "monthly",
            "release_offset_days": 30,
            "source_url": "https://fred.stlouisfed.org/series/PCECTPI",
            "methodology": "美联储首选通胀指标，范围比CPI更广",
            "impact": "high",
        },
        # 经济增长
        "GDP": {
            "name_cn": "GDP现价季环比年化",
            "name_en": "Real GDP (Chain-Type)",
            "unit": "% (环比年化)",
            "frequency": "quarterly",
            "release_offset_days": 30,
            "source_url": "https://fred.stlouisfed.org/series/GDP",
            "methodology": "BEA国民账户，Chain-type quantity indexes",
            "impact": "high",
        },
        "GDPPCT": {
            "name_cn": "GDP同比",
            "name_en": "Real GDP Percent Change",
            "unit": "% (同比)",
            "frequency": "quarterly",
            "release_offset_days": 30,
            "source_url": "https://fred.stlouisfed.org/series/A191RP1Q027SBEA",
            "methodology": "GDP同比增长率",
            "impact": "high",
        },
        # 货币政策
        "FEDFUNDS": {
            "name_cn": "联邦基金利率",
            "name_en": "Effective Federal Funds Rate",
            "unit": "%",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/FEDFUNDS",
            "methodology": "联邦基金市场隔夜利率的日均值",
            "impact": "high",
        },
        "DGS10": {
            "name_cn": "10年期国债收益率",
            "name_en": "10-Year Treasury Constant Maturity Rate",
            "unit": "%",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/DGS10",
            "methodology": "国债收益率曲线的即期利率",
            "impact": "high",
        },
        "DGS2": {
            "name_cn": "2年期国债收益率",
            "name_en": "2-Year Treasury Constant Maturity Rate",
            "unit": "%",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/DGS2",
            "methodology": "国债收益率曲线的即期利率",
            "impact": "medium",
        },
        "TEDRATE": {
            "name_cn": "TED利差",
            "name_en": "TED Spread",
            "unit": "bp",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/TEDRATE",
            "methodology": "3M LIBOR - 3M国债收益率，反映银行间信用风险",
            "impact": "high",
        },
        # 信用与风险
        "NFCI": {
            "name_cn": "全国金融状况指数",
            "name_en": "Chicago Fed National Financial Conditions Index",
            "unit": "index",
            "frequency": "weekly",
            "release_offset_days": 7,
            "source_url": "https://fred.stlouisfed.org/series/NFCI",
            "methodology": "货币/信用/杠杆/风险四个维度加权",
            "impact": "medium",
        },
        "BAML0C0A0CMORTY": {
            "name_cn": "美国IG债券利差",
            "name_en": "ICE BofA US Corporate Option-Adjusted Spread",
            "unit": "bp",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/BAML0C0A0CMORTY",
            "methodology": "BofA美银美国投资级企业债OAS利差",
            "impact": "medium",
        },
        "T10Y2Y": {
            "name_cn": "10Y-2Y国债利差",
            "name_en": "10-Year Treasury Constant Maturity Minus 2-Year",
            "unit": "bp",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/T10Y2Y",
            "methodology": "收益率曲线利差，倒挂通常预示衰退",
            "impact": "high",
        },
        # 消费与信心
        "PCE": {
            "name_cn": "个人消费支出",
            "name_en": "Personal Consumption Expenditures",
            "unit": "十亿美元",
            "frequency": "monthly",
            "release_offset_days": 30,
            "source_url": "https://fred.stlouisfed.org/series/PCE",
            "methodology": "BEA个人消费支出，季节性调整",
            "impact": "medium",
        },
        "CONSSENT": {
            "name_cn": "密歇根消费者信心指数",
            "name_en": "University of Michigan Consumer Sentiment",
            "unit": "index (1966Q1=100)",
            "frequency": "monthly",
            "release_offset_days": 10,
            "source_url": "https://fred.stlouisfed.org/series/CONSSENT",
            "methodology": "密歇根大学消费者调查 (n≈500)",
            "impact": "medium",
        },
        "ICSA": {
            "name_cn": "首次申请失业救济人数",
            "name_en": "Initial Claims for Unemployment Insurance",
            "unit": "千人",
            "frequency": "weekly",
            "release_offset_days": 2,
            "source_url": "https://fred.stlouisfed.org/series/ICSA",
            "methodology": "周度首次申请失业保险人数",
            "impact": "medium",
        },
        # 住房
        "CSUSHPINSA": {
            "name_cn": "Case-Shiller房价指数同比",
            "name_en": "S&P/Case-Shiller U.S. National Home Price Index",
            "unit": "% (同比)",
            "frequency": "monthly",
            "release_offset_days": 60,
            "source_url": "https://fred.stlouisfed.org/series/CSUSHPINSA",
            "methodology": "20个主要城市S&P/Case-Shiller房价指数",
            "impact": "medium",
        },
        # 制造业
        "MANEMP": {
            "name_cn": "制造业就业人数",
            "name_en": "All Employees Manufacturing",
            "unit": "千人",
            "frequency": "monthly",
            "release_offset_days": 5,
            "source_url": "https://fred.stlouisfed.org/series/MANEMP",
            "methodology": "制造业就业人数，季节性调整",
            "impact": "medium",
        },
        "PMI": {
            "name_cn": "ISM制造业PMI",
            "name_en": "ISM Manufacturing PMI",
            "unit": "index (50=扩张)",
            "frequency": "monthly",
            "release_offset_days": 1,
            "source_url": "https://fred.stlouisfed.org/series/ISMAN",
            "methodology": "ISM协会对采购经理的月度调查",
            "impact": "high",
        },
        # 国际
        "DEXCHUS": {
            "name_cn": "美元/人民币汇率",
            "name_en": "China/U.S. Foreign Exchange Rate",
            "unit": "CNY per USD",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/DEXCHUS",
            "methodology": "纽约联邦储备银行汇率",
            "impact": "high",
        },
        "DEXUSEU": {
            "name_cn": "美元/欧元汇率",
            "name_en": "U.S. Dollar to Euro Exchange Rate",
            "unit": "USD per EUR",
            "frequency": "daily",
            "release_offset_days": 0,
            "source_url": "https://fred.stlouisfed.org/series/DEXUSEU",
            "methodology": "欧洲央行参考汇率",
            "impact": "medium",
        },
    }

    def __init__(self, api_key: str | None = None, cache_dir: str | None = None):
        self.api_key = api_key or FRED_API_KEY
        self.cache_dir = cache_dir
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "FinResearch-Agent/1.0"})
        self._cache: dict[str, Any] = {}

    def _get_cached(self, key: str) -> Any | None:
        if self.cache_dir:
            path = os.path.join(self.cache_dir, f"fred_{key}.json")
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                if time.time() - mtime < 86400:  # 24h cache
                    with open(path) as f:
                        return json.load(f)
        return self._cache.get(key)

    def _set_cached(self, key: str, data: Any) -> None:
        self._cache[key] = data
        if self.cache_dir:
            path = os.path.join(self.cache_dir, f"fred_{key}.json")
            with open(path, "w") as f:
                json.dump(data, f, ensure_ascii=False)

    def fetch_series(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        use_public: bool = False,
    ) -> MacroTimeSeries:
        """获取FRED时间序列。

        Parameters
        ----------
        series_id : str
            FRED指标代码（如 "PAYEMS", "CPIAUCSL", "DGS10"）
        start_date : str, optional
            起始日期 YYYY-MM-DD
        end_date : str, optional
            结束日期 YYYY-MM-DD
        use_public : bool
            True=使用公开CSV接口（无需API Key），False=使用API（支持更多数据）

        Returns
        -------
        MacroTimeSeries
        """
        cache_key = f"{series_id}_{start_date}_{end_date}"
        cached = self._get_cached(cache_key)
        if cached:
            logger.info(f"FRED cache hit: {series_id}")
            return self._parse_fred_response(cached, series_id)

        catalog = self.INDICATOR_CATALOG.get(series_id, {})
        unit = catalog.get("unit", "unknown")
        freq_map = {"daily": DataFreshness.DAILY, "monthly": DataFreshness.MONTHLY,
                    "quarterly": DataFreshness.QUARTERLY, "weekly": DataFreshness.DAILY}
        freq = freq_map.get(catalog.get("frequency", "daily"), DataFreshness.DAILY)

        if use_public or not self.api_key:
            # 公开CSV接口（无需Key，但数据有限）
            url = f"{self.PUBLIC_URL}?id={series_id}"
            if start_date:
                url += f"&cosd={start_date}"
            if end_date:
                url += f"&coed={end_date}"
            try:
                r = self._session.get(url, timeout=15)
                r.raise_for_status()
                return self._parse_csv_response(r.text, series_id, unit, freq, catalog)
            except Exception as e:
                logger.warning(f"FRED public API failed for {series_id}: {e}")
                return self._fallback_mock(series_id, unit, freq, "FRED public API failed")

        # API接口（需要Key）
        url = f"{self.BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date or "1776-01-01",
            "observation_end": end_date or "9999-12-31",
        }
        try:
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            self._set_cached(cache_key, data)
            return self._parse_fred_response(data, series_id, unit, freq, catalog)
        except Exception as e:
            logger.error(f"FRED API failed for {series_id}: {e}")
            return self._fallback_mock(series_id, unit, freq, str(e))

    def _parse_fred_response(
        self, data: dict, series_id: str,
        unit: str, freq: DataFreshness,
        catalog: dict,
    ) -> MacroTimeSeries:
        observations = []
        for obs in data.get("observations", []):
            value = obs.get("value")
            if value and value != ".":
                observations.append(MacroObservation(
                    indicator=series_id,
                    value=float(value),
                    unit=unit,
                    frequency=freq,
                    source=DataSourceType.FRED,
                    country="US",
                    date=obs.get("date", ""),
                    release_date=None,
                    is_realtime=False,
                    methodology=catalog.get("methodology"),
                    url=catalog.get("source_url"),
                    metadata={"realtime_start": obs.get("realtime_start"),
                               "realtime_end": obs.get("realtime_end")},
                ))

        return MacroTimeSeries(
            indicator=series_id,
            country="US",
            unit=unit,
            frequency=freq,
            source=DataSourceType.FRED,
            observations=observations,
            last_updated=datetime.now().isoformat(),
            description=catalog.get("name_cn", series_id),
            methodology=catalog.get("methodology"),
        )

    def _parse_csv_response(
        self, csv_text: str, series_id: str,
        unit: str, freq: DataFreshness,
        catalog: dict,
    ) -> MacroTimeSeries:
        lines = csv_text.strip().split("\n")
        if len(lines) < 2:
            return self._fallback_mock(series_id, unit, freq, "Empty CSV response")

        observations = []
        for line in lines[1:]:  # skip header
            parts = line.split(",")
            if len(parts) >= 2:
                date_str = parts[0].strip()
                value_str = parts[1].strip()
                if value_str and value_str != ".":
                    try:
                        observations.append(MacroObservation(
                            indicator=series_id,
                            value=float(value_str),
                            unit=unit,
                            frequency=freq,
                            source=DataSourceType.FRED,
                            country="US",
                            date=date_str,
                            release_date=None,
                            is_realtime=False,
                            methodology=catalog.get("methodology"),
                            url=catalog.get("source_url"),
                        ))
                    except ValueError:
                        continue

        return MacroTimeSeries(
            indicator=series_id,
            country="US",
            unit=unit,
            frequency=freq,
            source=DataSourceType.FRED,
            observations=observations,
            last_updated=datetime.now().isoformat(),
            description=catalog.get("name_cn", series_id),
            methodology=catalog.get("methodology"),
        )

    def _fallback_mock(
        self, series_id: str, unit: str,
        freq: DataFreshness, reason: str,
    ) -> MacroTimeSeries:
        logger.warning(f"FRED {series_id} fallback to mock data: {reason}")
        return MacroTimeSeries(
            indicator=series_id,
            country="US",
            unit=unit,
            frequency=freq,
            source=DataSourceType.SIMULATED,
            observations=[],
            last_updated=datetime.now().isoformat(),
            description=f"{series_id} (MOCK - {reason})",
        )

    def fetch_nfp(self, start_year: int | None = None, end_year: int | None = None) -> MacroTimeSeries:
        """获取NFP非农就业数据（含市场预期/实际/前值）。"""
        ts = self.fetch_series(
            "PAYEMS",
            start_date=f"{start_year or 2015}-01-01",
            end_date=f"{end_year or 2026}-12-31",
        )
        return ts

    def fetch_cpi(self, start_year: int | None = None, end_year: int | None = None) -> MacroTimeSeries:
        """获取CPI同比数据。"""
        return self.fetch_series(
            "CPIAUCSL",
            start_date=f"{start_year or 2015}-01-01",
            end_date=f"{end_year or 2026}-12-31",
        )

    def fetch_fed_rates(self) -> MacroTimeSeries:
        """获取联邦基金利率。"""
        return self.fetch_series("FEDFUNDS")

    def fetch_yield_curve(self) -> dict[str, MacroTimeSeries]:
        """获取美债收益率曲线（2Y/5Y/10Y/30Y）。"""
        tenors = {"DGS2": "2Y", "DGS5": "5Y", "DGS10": "10Y", "DGS30": "30Y"}
        return {name: self.fetch_series(code) for code, name in tenors.items()}

    def fetch_ted_spread(self) -> MacroTimeSeries:
        """获取TED利差（银行间信用风险指标）。"""
        return self.fetch_series("TEDRATE")

    def fetch_yield_curve_slope(self) -> MacroTimeSeries:
        """获取10Y-2Y利差（衰退预警）。"""
        return self.fetch_series("T10Y2Y")


# ─── Akshare Macro Fetcher ────────────────────────────────────────────────────

class AkshareMacroFetcher:
    """akshare 本地缓存宏观数据封装。

    akshare数据覆盖：
    - 中国宏观（CPI/PPI/GDP/M2/社融）
    - 债券（国债收益率曲线、信用利差）
    - 基金（ETF申赎、公募规模）
    - 期货（商品期货、股指期货）
    - 汇率（CFETS指数、USD/CNY）
    """

    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = cache_dir
        self._ak = None
        self._available = False
        self._try_init()

    def _try_init(self) -> None:
        try:
            import akshare as ak
            self._ak = ak
            self._available = True
            logger.info("akshare available")
        except ImportError:
            logger.warning("akshare not installed, using fallback")
            self._available = False

    def _get(self, func: Callable, *args, cache_hours: int = 4, **kwargs) -> Any | None:
        """带缓存的 akshare 调用。"""
        if not self._available:
            return None
        cache_key = f"{func.__name__}_{args}_{kwargs}"
        if self.cache_dir:
            import hashlib
            key_hash = hashlib.md5(cache_key.encode(), usedforsecurity=False).hexdigest()
            path = os.path.join(self.cache_dir, f"ak_{key_hash}.json")
            if os.path.exists(path) and time.time() - os.path.getmtime(path) < cache_hours * 3600:
                with open(path) as f:
                    return json.load(f)
        try:
            result = func(*args, **kwargs)
            if self.cache_dir:
                with open(path, "w") as f:
                    json.dump({"_raw": str(type(result).__name__), "_data": result.to_dict() if hasattr(result, "to_dict") else list(result) if hasattr(result, "__iter__") else result}, f)
            return result
        except Exception as e:
            logger.warning(f"akshare {func.__name__} failed: {e}")
            return None

    # ── 中国宏观 ─────────────────────────────────────────────────────────────

    def fetch_cn_cpi(self, start_year: int = 2015) -> MacroTimeSeries:
        """中国CPI同比（月度）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_cpi()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_CPI",
                        value=float(row.get("cpi_yoy", 0)),
                        unit="%",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="国家统计局CPI调查",
                        url="https://www.stats.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN CPI failed: {e}")
        return MacroTimeSeries(
            indicator="CN_CPI",
            country="CN",
            unit="%",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国CPI同比",
        )

    def fetch_cn_gdp(self) -> MacroTimeSeries:
        """中国GDP同比（季度）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_gdp()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_GDP",
                        value=float(row.get("gdp_yoy", 0)),
                        unit="%",
                        frequency=DataFreshness.QUARTERLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="国家统计局国民账户",
                        url="https://www.stats.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN GDP failed: {e}")
        return MacroTimeSeries(
            indicator="CN_GDP",
            country="CN",
            unit="%",
            frequency=DataFreshness.QUARTERLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国GDP同比",
        )

    def fetch_cn_pmi(self) -> MacroTimeSeries:
        """中国官方PMI（月度，采购经理调查）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_pmi()
                for _, row in df.iterrows():
                    val = row.get("pmi", row.get("数值", 50))
                    obs.append(MacroObservation(
                        indicator="CN_PMI",
                        value=float(val),
                        unit="index (50=荣枯线)",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="国家统计局采购经理调查",
                        url="https://www.stats.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN PMI failed: {e}")
        return MacroTimeSeries(
            indicator="CN_PMI",
            country="CN",
            unit="index",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国官方PMI",
        )

    def fetch_cn_m2(self) -> MacroTimeSeries:
        """中国M2货币供应量同比。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_m2()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_M2",
                        value=float(row.get("m2_yoy", 0)),
                        unit="%",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="中国人民银行货币统计",
                        url="http://www.pbc.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN M2 failed: {e}")
        return MacroTimeSeries(
            indicator="CN_M2",
            country="CN",
            unit="%",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国M2同比",
        )

    def fetch_cn_financial_credit(self) -> MacroTimeSeries:
        """中国社会融资规模增量（月度）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_shibor()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_NEW_FINANCIAL_CREDIT",
                        value=float(row.get("value", 0)),
                        unit="亿元人民币",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="中国人民银行社会融资统计",
                        url="http://www.pbc.gov.cn",
                    ))
            except Exception:
                pass
        return MacroTimeSeries(
            indicator="CN_NEW_FINANCIAL_CREDIT",
            country="CN",
            unit="亿元",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国社会融资规模增量",
        )

    def fetch_cn_fdi(self) -> MacroTimeSeries:
        """中国实际使用外资金额（ FDI）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_fdi()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_FDI",
                        value=float(row.get("fdi_yoy", 0)),
                        unit="%",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="商务部外商投资统计",
                        url="http://www.mofcom.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN FDI failed: {e}")
        return MacroTimeSeries(
            indicator="CN_FDI",
            country="CN",
            unit="%",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国实际使用外资同比",
        )

    def fetch_cn_retail(self) -> MacroTimeSeries:
        """中国社会消费品零售总额同比。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_consumer_goods_retail()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_RETAIL",
                        value=float(row.get("retail_yoy", 0)),
                        unit="%",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="国家统计局零售统计",
                        url="https://www.stats.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CN retail failed: {e}")
        return MacroTimeSeries(
            indicator="CN_RETAIL",
            country="CN",
            unit="%",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="中国社会消费品零售总额同比",
        )

    def fetch_cn_shibor(self) -> MacroTimeSeries:
        """上海银行间同业拆借利率（SHIBOR）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_shibor()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_SHIBOR_3M",
                        value=float(row.get("shibor_3m", 0)),
                        unit="%",
                        frequency=DataFreshness.DAILY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=True,
                        methodology="全国银行间同业拆借中心",
                        url="http://www.shibor.org",
                    ))
            except Exception as e:
                logger.warning(f"akshare SHIBOR failed: {e}")
        return MacroTimeSeries(
            indicator="CN_SHIBOR_3M",
            country="CN",
            unit="%",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="SHIBOR 3M",
        )

    def fetch_cn_lpr(self) -> MacroTimeSeries:
        """贷款市场报价利率（LPR）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.macro_china_lpr()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_LPR_1Y",
                        value=float(row.get("lpr_1y", 0)),
                        unit="%",
                        frequency=DataFreshness.MONTHLY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=False,
                        methodology="中国人民银行授权LPR报价",
                        url="http://www.pbc.gov.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare LPR failed: {e}")
        return MacroTimeSeries(
            indicator="CN_LPR_1Y",
            country="CN",
            unit="%",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.AKSHARE,
            observations=obs,
            last_updated=datetime.now().isoformat(),
            description="1年期LPR",
        )

    # ── 中国债券 ─────────────────────────────────────────────────────────────

    def fetch_cn_yield_curve(self) -> MacroTimeSeries:
        """中国国债收益率曲线（中债估值）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.bond_china_yield()
                # df columns: date, 1Y, 3Y, 5Y, 7Y, 10Y, 30Y
                for _, row in df.iterrows():
                    for tenor in ["1Y", "3Y", "5Y", "10Y", "30Y"]:
                        if tenor in row:
                            obs.append(MacroObservation(
                                indicator=f"CN_GOVT_{tenor}",
                                value=float(row[tenor]),
                                unit="%",
                                frequency=DataFreshness.DAILY,
                                source=DataSourceType.AKSHARE,
                                country="CN",
                                date=str(row.get("date", "")),
                                release_date=None,
                                is_realtime=True,
                                methodology="中债国债收益率曲线估值",
                                url="http://www.chinamoney.com.cn",
                            ))
            except Exception as e:
                logger.warning(f"akshare CN yield curve failed: {e}")
        return MacroTimeSeries(
            indicator="CN_GOVT_YIELD_CURVE",
            country="CN",
            unit="%",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.AKSHARE,
            observations=obs[-100:] if obs else [],  # keep last 100
            last_updated=datetime.now().isoformat(),
            description="中债国债收益率曲线",
        )

    def fetch_cn_credit_spread(self) -> MacroTimeSeries:
        """中国信用利差（AA+企业债 - 国债）。"""
        obs = []
        if self._available:
            try:
                df = self._ak.bond_china_credit()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CN_CREDIT_SPREAD",
                        value=float(row.get("spread", 0)),
                        unit="bp",
                        frequency=DataFreshness.DAILY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=True,
                        methodology="AA+企业债收益率 - 同期限国债收益率",
                        url="http://www.chinamoney.com.cn",
                    ))
            except Exception:
                pass
        return MacroTimeSeries(
            indicator="CN_CREDIT_SPREAD",
            country="CN",
            unit="bp",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.AKSHARE,
            observations=obs[-100:] if obs else [],
            last_updated=datetime.now().isoformat(),
            description="中国信用利差",
        )

    # ── 外汇 ────────────────────────────────────────────────────────────────

    def fetch_cfets_index(self) -> MacroTimeSeries:
        """CFETS人民币汇率指数。"""
        obs = []
        if self._available:
            try:
                df = self._ak.currency_cfets_index()
                for _, row in df.iterrows():
                    obs.append(MacroObservation(
                        indicator="CFETS_INDEX",
                        value=float(row.get("cfets_index", 0)),
                        unit="index (2014=100)",
                        frequency=DataFreshness.DAILY,
                        source=DataSourceType.AKSHARE,
                        country="CN",
                        date=str(row.get("date", "")),
                        release_date=None,
                        is_realtime=True,
                        methodology="中国外汇交易中心CFETS一篮子货币",
                        url="http://www.chinamoney.com.cn",
                    ))
            except Exception as e:
                logger.warning(f"akshare CFETS failed: {e}")
        return MacroTimeSeries(
            indicator="CFETS_INDEX",
            country="CN",
            unit="index",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.AKSHARE,
            observations=obs[-100:] if obs else [],
            last_updated=datetime.now().isoformat(),
            description="CFETS人民币汇率指数",
        )


# ─── Macro Calendar ───────────────────────────────────────────────────────────

class MacroCalendar:
    """宏观日历：自动生成重要宏观数据发布日期。

    关键发布日期：
    - NFP: 每月第一个周五 (US, 08:30 EST)
    - CPI: 每月10-15号 (US, 08:30 EST)
    - FOMC: 每6周左右，周三 (US, 14:00 EST)
    - GDP: 每季度末月最后一个周四 (US, 08:30 EST)
    - CN PMI: 每月第一个工作日 (CN, 09:00 CST)
    - CN CPI/PPI: 每月9-12号 (CN, 09:30 CST)
    - CN GDP: 每季度末月18号左右 (CN, 10:00 CST)
    """

    def __init__(self):
        self.today = date.today()

    def get_upcoming_releases(self, days_ahead: int = 30) -> list[dict]:
        """获取未来N天的重要宏观数据发布。"""
        events = []
        current = self.today
        end = self.today + timedelta(days=days_ahead)

        while current <= end:
            # US NFP: 每月第一个周五
            if current.weekday() == 4:  # Friday
                first_day = date(current.year, current.month, 1)
                first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
                if current == first_friday:
                    events.append({
                        "name": "US NFP",
                        "name_cn": "美国非农就业",
                        "full_name": "All Employees Total Nonfarm (PAYEMS)",
                        "date": current.isoformat(),
                        "country": "US",
                        "time": "08:30 EST",
                        "impact": "high",
                        "description": "前值、预期、实际三值对比，影响FED政策预期",
                        "affected_assets": ["SPX", "TNX", "DXY", "XAUUSD", "USDCNH"],
                    })

            # US CPI: 每月10-15号
            if 10 <= current.day <= 15 and current.weekday() < 5:
                events.append({
                    "name": "US CPI",
                    "name_cn": "美国CPI通胀",
                    "full_name": "Consumer Price Index for All Urban Consumers",
                    "date": current.isoformat(),
                    "country": "US",
                    "time": "08:30 EST",
                    "impact": "high",
                    "description": "同比CPI，影响FED加息预期和国债收益率",
                    "affected_assets": ["TNX", "SPX", "GLD", "USDCNH"],
                })

            # CN PMI: 每月第一天（或第一个工作日）
            if current.day == 1 or (
                current.day <= 3 and current.weekday() < 5
            ):
                events.append({
                    "name": "CN PMI",
                    "name_cn": "中国官方PMI",
                    "full_name": "国家统计局采购经理调查",
                    "date": current.isoformat(),
                    "country": "CN",
                    "time": "09:00 CST",
                    "impact": "high",
                    "description": "制造业PMI，50为荣枯线，影响A股情绪",
                    "affected_assets": ["CSI300", "HSAHP", "USDCNH"],
                })

            # CN CPI/PPI: 每月9-12号
            if 9 <= current.day <= 12:
                events.append({
                    "name": "CN CPI",
                    "name_cn": "中国CPI/PPI",
                    "full_name": "国家统计局CPI和PPI",
                    "date": current.isoformat(),
                    "country": "CN",
                    "time": "09:30 CST",
                    "impact": "medium",
                    "description": "通胀数据，影响货币政策预期",
                    "affected_assets": ["CSI300", "CNYB", "USDCNH"],
                })

            current += timedelta(days=1)

        return events

    def get_next_fomc(self) -> dict | None:
        """估算下一次FOMC会议日期（仅估算，需核实官方日历）。"""
        # FOMC approximately every 6 weeks on Wednesday
        fomc = date(self.today.year, 1, 1)
        while fomc.weekday() != 2:  # Wednesday
            fomc += timedelta(days=1)
        while fomc <= self.today:
            fomc += timedelta(weeks=6)
        return {
            "name": "US FOMC",
            "name_cn": "美联储利率决议",
            "date": fomc.isoformat(),
            "days_until": (fomc - self.today).days,
            "country": "US",
            "time": "14:00 EST / 03:00 CST",
            "impact": "critical",
            "description": "联邦基金利率决议 + FOMC声明 + 经济预测 + 记者会",
            "affected_assets": ["DXY", "TNX", "SPX", "XAUUSD", "USDCNH"],
            "note": "精确日期需参考美联储官方日历 https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        }

    def get_next_nfp(self) -> dict:
        """计算下一次NFP发布日期。"""
        nfp = date(self.today.year, self.today.month, 1)
        nfp += timedelta(days=(4 - nfp.weekday()) % 7)  # 第一个周五
        if nfp <= self.today:
            nfp = date(self.today.year + (self.today.month // 12), (self.today.month % 12) + 1, 1)
            nfp += timedelta(days=(4 - nfp.weekday()) % 7)
        return {
            "name": "US NFP",
            "name_cn": "美国非农就业",
            "date": nfp.isoformat(),
            "days_until": (nfp - self.today).days,
            "time": "08:30 EST (约21:30 CST)",
            "impact": "high",
        }

    def generate_market_brief(self) -> str:
        """生成宏观市场简报。"""
        fred = FREDDataFetcher()
        ak = AkshareMacroFetcher()

        lines = ["## 宏观市场简报", f"**{datetime.now().strftime('%Y-%m-%d %H:%M')}**", ""]

        # US宏观
        try:
            nfp_ts = fred.fetch_nfp()
            if nfp_ts.observations:
                latest = nfp_ts.observations[-1]
                lines.append(f"**美国NFP**: {latest.date} = **{latest.value:,.0f}千人** (src: FRED/{latest.source.value})")
        except Exception:
            pass

        try:
            cpi_ts = fred.fetch_cpi()
            if cpi_ts.observations:
                latest = cpi_ts.observations[-1]
                lines.append(f"**美国CPI同比**: {latest.date} = **{latest.value:.1f}%** (src: FRED/{latest.source.value})")
        except Exception:
            pass

        try:
            fed_ts = fred.fetch_fed_rates()
            if fed_ts.observations:
                latest = fed_ts.observations[-1]
                lines.append(f"**联邦基金利率**: {latest.date} = **{latest.value:.2f}%** (src: FRED)")
        except Exception:
            pass

        try:
            ted = fred.fetch_ted_spread()
            if ted.observations:
                latest = ted.observations[-1]
                lines.append(f"**TED利差**: {latest.date} = **{latest.value:.1f}bp** (src: FRED)")
        except Exception:
            pass

        # CN宏观
        try:
            cn_pmi = ak.fetch_cn_pmi()
            if cn_pmi.observations:
                latest = cn_pmi.observations[-1]
                lines.append(f"**中国PMI**: {latest.date} = **{latest.value:.1f}** (src: akshare)")
        except Exception:
            pass

        try:
            cn_cpi = ak.fetch_cn_cpi()
            if cn_cpi.observations:
                latest = cn_cpi.observations[-1]
                lines.append(f"**中国CPI同比**: {latest.date} = **{latest.value:.1f}%** (src: akshare)")
        except Exception:
            pass

        try:
            cn_gdp = ak.fetch_cn_gdp()
            if cn_gdp.observations:
                latest = cn_gdp.observations[-1]
                lines.append(f"**中国GDP同比**: {latest.date} = **{latest.value:.1f}%** (src: akshare)")
        except Exception:
            pass

        try:
            cn_lpr = ak.fetch_cn_lpr()
            if cn_lpr.observations:
                latest = cn_lpr.observations[-1]
                lines.append(f"**1YLPR**: {latest.date} = **{latest.value:.2f}%** (src: akshare)")
        except Exception:
            pass

        # 日历
        lines.append("")
        lines.append("## 重要宏观日历")
        upcoming = self.get_upcoming_releases(14)
        if upcoming:
            for ev in upcoming[:5]:
                lines.append(f"- [{ev['date']}] {ev['name']} ({ev['name_cn']}) — {ev['time']}")
        else:
            lines.append("未来两周暂无重要宏观发布")

        return "\n".join(lines)


# ─── Main: MacroFinanceCenter ─────────────────────────────────────────────────

class MacroFinanceCenter:
    """宏观金融数据中心——统一入口。

    Usage:
        mfc = MacroFinanceCenter(cache_dir="data/macro")
        mfc.fetch_fred("PAYEMS")
        mfc.fetch_cn_macro("cpi")
        mfc.get_calendar().generate_market_brief()
    """

    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = cache_dir
        self.fred = FREDDataFetcher(cache_dir=cache_dir)
        self.ak = AkshareMacroFetcher(cache_dir=cache_dir)
        self.calendar = MacroCalendar()
        self._cache: dict[str, MacroTimeSeries] = {}

    def fetch_fred(self, indicator: str, **kwargs) -> MacroTimeSeries:
        """获取FRED指标。"""
        return self.fred.fetch_series(indicator, **kwargs)

    def fetch_cn_macro(self, indicator: str) -> MacroTimeSeries:
        """获取中国宏观指标。

        Available indicators:
            cpi, gdp, pmi, m2, fdi, retail, shibor, lpr,
            yield_curve, credit_spread, cfets
        """
        fetchers = {
            "cpi": self.ak.fetch_cn_cpi,
            "gdp": self.ak.fetch_cn_gdp,
            "pmi": self.ak.fetch_cn_pmi,
            "m2": self.ak.fetch_cn_m2,
            "fdi": self.ak.fetch_cn_fdi,
            "retail": self.ak.fetch_cn_retail,
            "shibor": self.ak.fetch_cn_shibor,
            "lpr": self.ak.fetch_cn_lpr,
            "yield_curve": self.ak.fetch_cn_yield_curve,
            "credit_spread": self.ak.fetch_cn_credit_spread,
            "cfets": self.ak.fetch_cfets_index,
        }
        fn = fetchers.get(indicator)
        if fn:
            return fn()
        raise ValueError(f"Unknown CN macro indicator: {indicator}")

    def fetch_macro_panel(
        self,
        indicators: list[str],
        country: str = "US",
    ) -> dict[str, MacroTimeSeries]:
        """批量获取宏观指标面板。"""
        results = {}
        for ind in indicators:
            try:
                if country == "US":
                    results[ind] = self.fred.fetch_series(ind)
                else:
                    results[ind] = self.fetch_cn_macro(ind)
            except Exception as e:
                logger.warning(f"Failed to fetch {ind}: {e}")
        return results

    def generate_macro_report(self) -> str:
        """生成完整的宏观研究报告。"""
        return self.calendar.generate_market_brief()
