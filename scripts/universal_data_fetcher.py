"""
universal_data_fetcher.py
========================
经济金融研究统一数据获取模块。

【设计原则】
每个数据需求都有4层fallback，确保任何情况下都能获取数据或明确标记为模拟：

  Layer 1: MCP调用（Cursor MCP Tool，通过CallMcpTool）
  Layer 2: Python CLI库（akshare/yfinance/baostock，直接pip安装）
  Layer 3: 原始HTTP请求（requests/urllib，无需特殊库）
  Layer 4: 标记为_synthetic（不可用时明确标记）

【关税研究数据需求】
  - A股财务数据: Tushare → akshare → baostock → efinance
  - 专利数据:        CNRDS → USPTO公开数据 → 文本代理
  - 实体清单事件:    BIS官网 → 手动整理 → 代理指标
  - 宏观数据:        MCP(user-financial) → akshare → WorldBank API

【用法】
  from scripts.universal_data_fetcher import UniversalDataFetcher

  fetcher = UniversalDataFetcher()
  result = fetcher.fetch("a_stock_financial", ts_code="000001.SZ", years=[2015,2025])
  print(result.data)      # DataFrame或None
  print(result.source)   # "tushare" / "akshare" / "baostock" / "SYNTHETIC"
  print(result.provenance) # "MCP→CLI→HTTP→synthetic"
"""

from __future__ import annotations

import json
import logging
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

# 修复 yfinance 在某些环境下的 SSL/TLS 问题（必须在 yfinance 导入前设置）
import os as _os
_os.environ.setdefault("YFINANCE_USE_CURL_CFFI", "false")
_os.environ.setdefault("HTTPX_DISABLE_CURL", "true")

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("universal_fetcher")

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT))

# ─── 数据来源枚举 ───────────────────────────────────────────────────────────────

class DataSource(str, Enum):
    MCP = "mcp"              # MCP服务器
    CLI_AKSHARE = "cli_akshare"    # akshare Python库
    CLI_BAOSTOCK = "cli_baostock"  # baostock Python库
    CLI_YFINANCE = "cli_yfinance"  # yfinance Python库
    HTTP_DIRECT = "http_direct"    # 直接HTTP请求
    SYNTHETIC = "synthetic"      # 模拟数据（需用户授权）

    @property
    def tier(self) -> int:
        tier_map = {
            DataSource.MCP: 1,
            DataSource.CLI_AKSHARE: 2,
            DataSource.CLI_BAOSTOCK: 2,
            DataSource.CLI_YFINANCE: 2,
            DataSource.HTTP_DIRECT: 3,
            DataSource.SYNTHETIC: 4,
        }
        return tier_map.get(self, 99)

    @property
    def is_available(self) -> bool:
        return self != DataSource.SYNTHETIC


@dataclass
class DataResult:
    """数据获取结果"""
    data: Any              # DataFrame/dict 或 None
    source: DataSource      # 最终数据来源
    provenance: str        # 完整调用链，如 "MCP→akshare→synthetic"
    available: bool        # 是否成功获取
    error: str = ""       # 最后一次错误信息
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def is_synthetic(self) -> bool:
        """是否使用了模拟数据（任何上游 synthetic 都算）"""
        return self.source == DataSource.SYNTHETIC or "synthetic" in (self.provenance or "")


class SyntheticDataForbiddenError(RuntimeError):
    """Raised when fetch() would fall back to synthetic data without
    explicit opt-in. Serious empirical work MUST NOT silently get fake
    numbers. Callers must pass `allow_synthetic=True` to override.

    This replaces the v1 behavior of returning synthetic data
    transparently with a `_synthetic` column — which was easy to
    overlook in pandas columns during a regression.
    """


# ─── 已知制裁事件（初始数据，可后续从BIS官网更新）───────────────────────────────

KNOWN_ENTITY_LIST: list[dict] = [
    # 格式: {company, stock_code, bis_name, sanction_date, sanction_year, cohort, product_scope}
    {"company": "中兴通讯", "stock_code": "000063.SZ", "bis_name": "Zhongxing Telecom",
     "sanction_date": "2018-04-16", "sanction_year": 2018, "cohort": "2018_zte", "product_scope": "电信设备"},
    {"company": "海康威视", "stock_code": "002415.SZ", "bis_name": "Hangzhou Hikvision",
     "sanction_date": "2019-05-22", "sanction_year": 2019, "cohort": "2019_huawei", "product_scope": "监控设备"},
    {"company": "大华股份", "stock_code": "002236.SZ", "bis_name": "Dahua Technology",
     "sanction_date": "2019-05-22", "sanction_year": 2019, "cohort": "2019_huawei", "product_scope": "监控设备"},
    {"company": "中芯国际", "stock_code": "688981.SH", "bis_name": "SMIC",
     "sanction_date": "2020-12-18", "sanction_year": 2020, "cohort": "2020_smic", "product_scope": "半导体制造"},
    {"company": "长江存储", "stock_code": "688072.SH", "bis_name": "YMTC",
     "sanction_date": "2022-12-15", "sanction_year": 2022, "cohort": "2022_chip_ban", "product_scope": "NAND闪存"},
    {"company": "北方华创", "stock_code": "002371.SZ", "bis_name": "Naura Technology",
     "sanction_date": "2024-12-02", "sanction_year": 2024, "cohort": "2024_dec_140", "product_scope": "半导体设备"},
    {"company": "中微公司", "stock_code": "688012.SH", "bis_name": "AMEC",
     "sanction_date": "2024-12-02", "sanction_year": 2024, "cohort": "2024_dec_140", "product_scope": "刻蚀设备"},
    {"company": "华大九天", "stock_code": "301269.SZ", "bis_name": "Empyrean Technology",
     "sanction_date": "2024-12-02", "sanction_year": 2024, "cohort": "2024_dec_140", "product_scope": "EDA软件"},
    {"company": "拓荆科技", "stock_code": "688072.SH", "bis_name": "Piotech",
     "sanction_date": "2024-12-02", "sanction_year": 2024, "cohort": "2024_dec_140", "product_scope": "薄膜沉积设备"},
]


# ─── 数据获取器基类 ────────────────────────────────────────────────────────────

class DataFetcher:
    """单个数据类型的获取器基类

    v2 行为（更严格）：
    - 默认 `try_mcp()` 抛 NotImplementedError 而非返回 False。
      调用方 fetch() 会捕获并记录到 provenance，但不再"成功 fallback
      到 None"，而是显示 "no mcp impl"。
    - 默认 `synthetic()` 抛 SyntheticDataForbiddenError。
      fetch() 在所有层失败时，**默认**抛 SyntheticDataForbiddenError，
      必须显式 `allow_synthetic=True` 才返回模拟数据。
    - 子类按需重写 try_mcp / try_akshare / try_baostock / try_yfinance
      / try_http / synthetic 之一或多个。
    """

    def __init__(self, name: str):
        self.name = name
        self._provenance: list[str] = []

    def try_mcp(self, *args, **kwargs) -> tuple[bool, Any, str]:
        """Layer 1: 尝试MCP调用。子类应该重写此方法。

        v2 行为：基类默认抛 NotImplementedError（而不是静默返回 False），
        让"未实现"在 fetch 流程中显式可见。
        """
        raise NotImplementedError(
            f"{type(self).__name__}.try_mcp is not implemented. "
            "MCP server bindings are only available inside Cursor/MCP "
            "runtime; standalone scripts that need real data should "
            "override try_akshare / try_yfinance / try_http instead."
        )

    def try_cli(self, *args, **kwargs) -> tuple[bool, Any, str]:
        """Layer 2: 尝试CLI库调用（基类泛型）"""
        return False, None, "CLI not implemented for this fetcher"

    def try_http(self, *args, **kwargs) -> tuple[bool, Any, str]:
        """Layer 3: 尝试直接HTTP请求"""
        return False, None, "HTTP fallback not implemented"

    def synthetic(self, *args, **kwargs) -> Any:
        """Layer 4: 生成模拟数据。子类应该重写此方法。

        v2 行为：基类默认抛 SyntheticDataForbiddenError，迫使调用方
        显式 opt-in。
        """
        raise SyntheticDataForbiddenError(
            f"{type(self).__name__}.synthetic is not implemented. "
            "Refusing to return fake data. Pass allow_synthetic=True "
            "to fetch() if you really want simulation output."
        )

    def fetch(self, *args, allow_synthetic: bool = False, **kwargs) -> DataResult:
        """按顺序尝试所有层，返回最终结果。

        Args:
            *args, **kwargs: forwarded to try_mcp / try_akshare / ...
            allow_synthetic: 默认 False。如果所有层都失败且该值为
                False，抛 SyntheticDataForbiddenError。仅在你**明确**
                想要模拟数据用于演示/测试时设为 True。严肃实证研究
                **永远不要** 设为 True。
        """
        provenance = []

        # Layer 1: MCP
        try:
            ok, data, err = self.try_mcp(*args, **kwargs)
            if ok and data is not None:
                provenance.append("mcp")
                return DataResult(data=data, source=DataSource.MCP,
                               provenance="→".join(provenance), available=True)
            provenance.append(f"mcp_miss:{err[:30] if err else 'no_impl'}")
        except NotImplementedError as e:
            provenance.append("mcp_no_impl")
        except Exception as e:
            provenance.append(f"mcp_err:{str(e)[:30]}")

        # Layer 2: CLI — only call methods that actually exist on this instance
        cli_methods = [
            (DataSource.CLI_AKSHARE, "try_akshare"),
            (DataSource.CLI_BAOSTOCK, "try_baostock"),
            (DataSource.CLI_YFINANCE, "try_yfinance"),
        ]
        for cls_source, method_name in cli_methods:
            if not hasattr(self, method_name):
                continue
            cli_fn = getattr(self, method_name)
            try:
                ok, data, err = cli_fn(*args, **kwargs)
                if ok and data is not None:
                    provenance.append(cls_source.value)
                    return DataResult(data=data, source=cls_source,
                                   provenance="→".join(provenance), available=True)
            except Exception as e:
                provenance.append(f"{cls_source.value}_err:{str(e)[:20]}")

        # Layer 3: HTTP
        try:
            ok, data, err = self.try_http(*args, **kwargs)
            if ok and data is not None:
                provenance.append("http")
                return DataResult(data=data, source=DataSource.HTTP_DIRECT,
                               provenance="→".join(provenance), available=True)
            provenance.append(f"http_miss:{err[:30] if err else 'no_impl'}")
        except NotImplementedError as e:
            provenance.append("http_no_impl")
        except Exception as e:
            provenance.append(f"http_err:{str(e)[:20]}")

        # Layer 4: Synthetic — opt-in only
        if not allow_synthetic:
            raise SyntheticDataForbiddenError(
                f"{type(self).__name__}.fetch exhausted all real-data layers "
                f"(provenance: {'→'.join(provenance)}). "
                "Refusing to fall back to synthetic data. "
                "If you want simulation output, pass allow_synthetic=True."
            )

        try:
            data = self.synthetic(*args, **kwargs)
            provenance.append("synthetic")
            return DataResult(
                data=data,
                source=DataSource.SYNTHETIC,
                provenance="→".join(provenance),
                available=False,
                error=f"All layers exhausted. Synthetic data generated (opt-in). {provenance[-1] if provenance else ''}"
            )
        except SyntheticDataForbiddenError:
            raise
        except Exception as e:
            provenance.append("synthetic_err")
            raise SyntheticDataForbiddenError(
                f"{type(self).__name__}.fetch all real-data layers failed "
                f"and synthetic layer also failed: {e}"
            )


# ─── A股财务数据获取器 ────────────────────────────────────────────────────────

class AStockFinancialFetcher(DataFetcher):
    """A股财务数据获取器"""

    def try_mcp(self, ts_code: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 1: MCP Tushare"""
        # 注意：MCP调用需要在Cursor中通过CallMcpTool执行
        # 这里检查环境变量是否有token，但不实际调用MCP
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
        load_dotenv(_PROJECT_ROOT / ".env.local", override=True)
        import os
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        if not token:
            return False, None, "TUSHARE_TOKEN not set"
        # MCP不可在脚本层直接调用，返回False让fallback生效
        return False, None, "MCP requires CallMcpTool in Cursor context"

    def try_akshare(self, stock: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 2a: akshare"""
        try:
            import akshare as ak
            # 尝试获取财务指标
            code = stock.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2015", end_year="2025")
            if df is not None and not df.empty:
                df["stock_code"] = stock
                return True, df, ""
        except Exception as e:
            pass

        # 尝试全市场财务摘要
        try:
            import akshare as ak
            df = ak.stock_financial_abstract(symbol="全部")
            if df is not None and not df.empty:
                return True, df, ""
        except Exception as e:
            return False, None, str(e)
        return False, None, "akshare returned empty data"

    def try_baostock(self, stock: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 2b: baostock"""
        try:
            import baostock as bs
            bs.login()
            code_bs = stock.replace(".SH", "sh.").replace(".SZ", "sz.").replace(".BJ", "bj.")
            rs = bs.query_profit_sheet_data(code_bs, start_date="2015-01-01", end_date="2025-12-31")
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            bs.logout()
            if rows:
                df = pd.DataFrame(rows, columns=rs.fields)
                df["stock_code"] = stock
                return True, df, ""
        except Exception as e:
            return False, None, str(e)
        return False, None, "baostock returned empty data"

    def try_yfinance(self, ticker: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 2c: yfinance（适用于美股、港股和中概股 ADR）

        注：YFINANCE_USE_CURL_CFFI=false 在模块顶部设置（解决 SSL 不兼容问题）。
        """
        if not ticker:
            return False, None, "no ticker"
        # 常见 A股→ADR / 美股 / 港股映射
        ticker_map = {
            "000001.SZ": "000001.SZ",
            "600519.SH": "600519.SS",
            "0700.HK": "0700.HK",
            "9988.HK": "BABA",
            "9618.HK": "JD",
            "3690.HK": "MTQ",
            "PDD": "PDD",
            "BIDU": "BIDU",
            "BABA": "BABA",
            "TCEHY": "TCEHY",
            "NVDA": "NVDA",
            "AAPL": "AAPL",
            "MSFT": "MSFT",
            "GOOGL": "GOOGL",
            "AMZN": "AMZN",
            "TSLA": "TSLA",
            "SPY": "SPY",
            "QQQ": "QQQ",
        }
        mapped = ticker_map.get(ticker, ticker)
        try:
            import yfinance as _yf
            t = _yf.Ticker(mapped)
            # 优先 .info（最稳定），fallback 到 financials
            try:
                info = t.info
                if info and isinstance(info, dict) and info.get("symbol"):
                    return True, info, ""
            except Exception:
                pass
            try:
                financials = t.financials
                if financials is not None and hasattr(financials, "empty") and not financials.empty:
                    return True, financials, ""
            except Exception:
                pass
            return False, None, f"yfinance returned no data for {mapped}"
        except Exception as e:
            return False, None, str(e)

    def try_http(self, stock: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 3: 直接HTTP请求到东方财富"""
        try:
            import requests
            code_num = stock.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
            exchange = "sh" if stock.endswith(".SH") else "sz"
            url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={1 if exchange=='sh' else 0}.{code_num}&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=20150101&end=20251231"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and data["data"].get("klines"):
                    return True, data, ""
        except Exception as e:
            return False, None, str(e)
        return False, None, "HTTP fallback failed"


# ─── 宏观数据获取器 ────────────────────────────────────────────────────────────

class MacroDataFetcher(DataFetcher):
    """宏观数据获取器"""

    def try_akshare(self, indicator: str = "gdp", **kwargs) -> tuple[bool, Any, str]:
        """Layer 2: akshare宏观数据"""
        try:
            import akshare as ak
            func_map = {
                "gdp": ak.macro_china_gdp,
                "cpi": ak.macro_china_cpi,
                "ppi": ak.macro_china_ppi,
                "m2": ak.macro_china_m2,
                "pmi": ak.macro_china_pmi,
                "lpr": ak.macro_china_lpr,
                "shibor": ak.macro_china_shibor,
                "fdi": ak.macro_china_fdi,
                "trade": ak.macro_china_trade,
                "fx": ak.macro_china_fx_reserves,
            }
            func = func_map.get(indicator.lower())
            if func:
                df = func()
                if df is not None and not df.empty:
                    return True, df, ""
        except Exception as e:
            return False, None, str(e)
        return False, None, f"akshare macro:{indicator} failed"

    def try_http(self, indicator: str = "gdp", **kwargs) -> tuple[bool, Any, str]:
        """Layer 3: World Bank API (HTTPS) with fallback to requests"""
        import time

        indicator_codes = {
            "gdp": "NY.GDP.MKTP.CD", "gdp_growth": "NY.GDP.MKTP.KD.ZG",
            "cpi": "FP.CPI.TOTL.ZG", "m2": "FM.LBL.NGMA.GD.ZS",
            "ppi": "FP.CPI.TOTL.ZG", "unemployment": "SL.UEM.TOTL.ZS",
            "population": "SP.POP.TOTL", "trade": "NE.EXP.GNFS.ZS",
        }
        code = indicator_codes.get(indicator.lower(), "NY.GDP.MKTP.CD")

        # Attempt 1: urllib with HTTPS
        for attempt in range(2):
            try:
                url = (f"https://api.worldbank.org/v2/country/CN/indicator/{code}"
                       f"?format=json&per_page=100")
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "FinResearch-Agent/1.0", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                    if not raw:
                        continue
                    data = json.loads(raw)
                if isinstance(data, list) and len(data) > 1 and data[1]:
                    records = data[1]
                    df = pd.DataFrame([{"year": r["date"], "value": r["value"]} for r in records])
                    return True, df, ""
            except Exception:
                if attempt == 0:
                    time.sleep(1)
                    continue
                break

        # Attempt 2: requests library (more robust HTTP client)
        try:
            import requests as _req
            url = (f"https://api.worldbank.org/v2/country/CN/indicator/{code}"
                   f"?format=json&per_page=100")
            r = _req.get(url, headers={"User-Agent": "FinResearch-Agent/1.0"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1 and data[1]:
                    records = data[1]
                    df = pd.DataFrame([{"year": rec["date"], "value": rec["value"]} for rec in records])
                    return True, df, ""
        except Exception as e:
            pass

        return False, None, f"World Bank API failed for indicator={indicator}"


# ─── 实体清单事件数据获取器 ──────────────────────────────────────────────────

class EntityListFetcher(DataFetcher):
    """实体清单事件数据获取器"""

    def try_http(self, **kwargs) -> tuple[bool, Any, str]:
        """Layer 3: BIS Entity List官网"""
        try:
            import requests
            # BIS Entity List JSON格式
            url = "https://www.bis.doc.gov/entity-list/downloads/current.csv"
            resp = requests.get(url, timeout=15, headers={"User-Agent": "FinResearch-Agent/1.0"})
            if resp.status_code == 200:
                from io import StringIO
                df = pd.read_csv(StringIO(resp.text))
                return True, df, ""
        except Exception as e:
            pass

        # 备用：Federal Register RSS
        try:
            url = "https://www.federalregister.gov/api/v1/documents.rss?conditions[agency_id]=13&conditions[doc_types][]=RULE&conditions[signing_date][gte]=2018-01-01"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return True, {"source": "federal_register_rss", "content": resp.text[:5000]}, ""
        except Exception:
            pass
        return False, None, "BIS Entity List download failed"

    def synthetic(self, **kwargs) -> pd.DataFrame:
        """Layer 4: 使用已知事件数据"""
        df = pd.DataFrame(KNOWN_ENTITY_LIST)
        df["_synthetic"] = True
        log.warning("Entity List data is SYNTHETIC (known events only). "
                    "For complete data, manually download from: https://www.bis.doc.gov/entity-list")
        return df


# ─── 专利数据获取器 ───────────────────────────────────────────────────────────

class PatentDataFetcher(DataFetcher):
    """专利数据获取器（使用CNRDS或替代方案）"""

    def try_akshare(self, stock: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 2: akshare无直接专利数据，尝试年报文本"""
        # akshare没有直接的专利接口，返回失败
        return False, None, "akshare has no patent API"

    def try_http(self, company_name: str = "", **kwargs) -> tuple[bool, Any, str]:
        """Layer 3: CNIPA国家知识产权局公开接口"""
        try:
            import requests
            # CNIPA专利检索接口
            search_url = "http://cpquery.cponline.cnipa.gov.cn/searchs/search-word.jsp"
            params = {"searchkey": company_name, "page": 1, "num": 50}
            resp = requests.post(search_url, data=params, timeout=15)
            if resp.status_code == 200:
                return True, {"source": "cnipa", "content": resp.text[:5000]}, ""
        except Exception:
            pass

        # USPTO公开专利检索
        try:
            import urllib.request
            encoded = urllib.parse.quote(company_name)
            url = f"https://api.patentsview.org/patents/query?q={{\"_or\":[{{\"assignee_first_name\":\"{company_name}\"}}]}}&o={{\"page\":1,\"per_page\":25}}"
            req = urllib.request.Request(url, headers={"User-Agent": "FinResearch-Agent/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            if data.get("patents"):
                return True, data, ""
        except Exception:
            pass
        return False, None, "CNIPA and USPTO patent APIs failed"

    def synthetic(self, stock: str = "", **kwargs) -> pd.DataFrame:
        """Layer 4: 生成专利模拟数据（基于R&D强度代理）

        v2: 该方法只在 fetch(allow_synthetic=True) 时才会被调用。
        之前是静默 fallback → 真实问题（用户把 np.random 数据
        当真实数据用）。现在需要显式 opt-in。
        """
        import numpy as np
        np.random.seed(42)
        years = list(range(2015, 2026))
        n = len(years)
        is_sanctioned = stock in ["000063.SZ", "002415.SZ", "002236.SZ", "688981.SH", "688072.SH"]

        # 简化模拟：制裁后企业专利申请数略有变化
        patent_base = np.random.randint(10, 100, n)
        if is_sanctioned:
            # 制裁后专利变化（基于文献：可能增加也可能减少）
            patent_qty = patent_base.copy()
            for i, year in enumerate(years):
                if year >= 2019:
                    patent_qty[i] = int(patent_qty[i] * np.random.uniform(0.85, 1.2))
        else:
            patent_qty = patent_base

        df = pd.DataFrame({
            "stock_code": [stock] * n,
            "year": years,
            "patent_apply": patent_qty,
            "inv_patent_apply": [max(1, int(p * np.random.uniform(0.4, 0.8))) for p in patent_qty],
            "rd_expense_sim": [np.random.uniform(500, 5000) * 1e6] * n,
            "_synthetic": True,
            "_note": "SYNTHETIC patent data. For real data, use CNRDS or CNIPA."
        })
        log.warning(f"Patent data for {stock} is SYNTHETIC. "
                    "Use CNRDS (via school library VPN) or CNIPA for real data.")
        return df


# ─── 统一数据获取器 ──────────────────────────────────────────────────────────

class UniversalDataFetcher:
    """
    统一数据获取器
    所有数据需求通过统一的接口访问，自动尝试四层fallback。
    """

    def __init__(self):
        self._fetchers: dict[str, DataFetcher] = {
            "a_stock_financial": AStockFinancialFetcher("a_stock_financial"),
            "macro": MacroDataFetcher("macro"),
            "entity_list": EntityListFetcher("entity_list"),
            "patent": PatentDataFetcher("patent"),
        }
        self._results: list[DataResult] = []

    def fetch(self, data_type: str, **kwargs) -> DataResult:
        """获取指定类型的数据"""
        fetcher = self._fetchers.get(data_type)
        if not fetcher:
            return DataResult(
                data=None, source=DataSource.SYNTHETIC,
                provenance="", available=False,
                error=f"Unknown data type: {data_type}"
            )

        result = fetcher.fetch(**kwargs)
        self._results.append(result)

        # 记录provenance
        status = "✅" if result.available else "⚠️"
        log.info(f"{status} {data_type} | source={result.source.value} | provenance={result.provenance}")
        if result.error and not result.available:
            log.warning(f"  {result.error}")

        return result

    def diagnose(self, data_type: str = "a_stock_financial") -> dict:
        """运行数据源可用性诊断。

        Args:
            data_type: 要诊断的数据类型。
                       可选: "a_stock_financial" / "macro" / "entity_list" / "patent"
                       或 "all"（诊断全部类型）。

        Returns:
            诊断报告字典，含每层的可用性状态。
        """
        import traceback as _tb

        if data_type == "all":
            types = list(self._fetchers.keys())
        else:
            types = [data_type]

        report = {
            "timestamp": datetime.now().isoformat(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "data_types": {},
            "summary": {"available": 0, "failed": 0, "total": len(types)},
        }

        for dtype in types:
            layer_report: dict[str, Any] = {"status": "unknown", "error": None, "available": False}
            try:
                result = self.fetch(dtype)
                layer_report["status"] = result.source.value
                layer_report["available"] = result.available
                layer_report["provenance"] = result.provenance
                if result.error:
                    layer_report["error"] = str(result.error)[:200]
                if result.available:
                    report["summary"]["available"] += 1
                else:
                    report["summary"]["failed"] += 1
            except Exception as e:
                layer_report["status"] = "exception"
                layer_report["error"] = str(e)[:200]
                layer_report["traceback"] = _tb.format_exc()[-500:]
                report["summary"]["failed"] += 1

            report["data_types"][dtype] = layer_report

        return report

    def fetch_a_stock_panel(
        self,
        stock_codes: list[str],
        years: list[int],
        variables: list[str] | None = None,
        allow_synthetic: bool = False,
    ) -> pd.DataFrame:
        """批量获取A股面板数据（支持四层fallback）

        v2: 默认禁止静默合成数据。如果所有股票都拿不到真实数据，
        抛 SyntheticDataForbiddenError。设 allow_synthetic=True 才会
        退到 numpy.random 的合成面板。
        """
        all_rows = []

        for code in stock_codes:
            for year in years:
                try:
                    result = self.fetch("a_stock_financial", stock=code, year=year)
                except SyntheticDataForbiddenError:
                    # 真实数据不可用，停止尝试后续 stock
                    if not allow_synthetic:
                        raise
                    # allow_synthetic=True 时直接落到下面的合成面板逻辑
                    break
                if result.data is not None and isinstance(result.data, pd.DataFrame):
                    if "_synthetic" not in result.data.columns:
                        result.data["stock_code"] = code
                        result.data["year"] = year
                        all_rows.append(result.data)

        if all_rows:
            return pd.concat(all_rows, ignore_index=True)

        if not allow_synthetic:
            raise SyntheticDataForbiddenError(
                f"fetch_a_stock_panel could not get any real data for "
                f"{len(stock_codes)} stocks × {len(years)} years. "
                "Pass allow_synthetic=True to fall back to a numpy.random panel."
            )

        log.warning("No real data fetched for any stock. Generating SYNTHETIC panel "
                    "(allow_synthetic=True).")
        import numpy as np
        np.random.seed(42)
        panel_rows = []
        for code in stock_codes:
            for year in years:
                panel_rows.append({
                    "stock_code": code, "year": year,
                    "rd_ratio": np.random.uniform(2, 15),
                    "roa": np.random.uniform(0.02, 0.15),
                    "lev": np.random.uniform(0.3, 0.7),
                    "size": np.random.uniform(20, 25),
                    "_synthetic": True,
                })
        return pd.DataFrame(panel_rows)

        df = pd.concat(all_rows, ignore_index=True)
        df["_source"] = result.source.value
        df["_timestamp"] = datetime.now().isoformat()
        return df

    def fetch_entity_list_events(self) -> pd.DataFrame:
        """获取实体清单事件数据"""
        result = self.fetch("entity_list")
        if result.data is not None and isinstance(result.data, pd.DataFrame):
            return result.data
        return pd.DataFrame(KNOWN_ENTITY_LIST)

    def fetch_macro_panel(
        self, indicators: list[str], start_year: int = 2015, end_year: int = 2025
    ) -> pd.DataFrame:
        """获取宏观数据面板"""
        all_dfs = []
        for indicator in indicators:
            result = self.fetch("macro", indicator=indicator)
            if result.data is not None and isinstance(result.data, pd.DataFrame):
                result.data["indicator"] = indicator
                result.data["_source"] = result.source.value
                all_dfs.append(result.data)

        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        return pd.DataFrame()

    def get_provenance_report(self) -> dict:
        """生成数据溯源报告"""
        return {
            "total_requests": len(self._results),
            "available": sum(1 for r in self._results if r.available),
            "synthetic": sum(1 for r in self._results if not r.available),
            "by_source": {
                s.value: sum(1 for r in self._results if r.source == s)
                for s in DataSource
            },
            "details": [
                {"type": r.source.value, "provenance": r.provenance,
                 "available": r.available, "error": r.error}
                for r in self._results
            ],
        }


# ─────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────
def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="universal_data_fetcher.py",
        description=(
            "Universal data fetcher with 4-layer fallback (MCP → CLI lib → HTTP → synthetic). "
            "Run a single data fetch or a self-diagnostic to see which sources are available."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diag = sub.add_parser("diagnose", help="Run source-availability diagnostic")
    p_diag.add_argument(
        "--data-type", default="a_stock_financial",
        help="Data type to diagnose (default: a_stock_financial)",
    )

    p_fetch = sub.add_parser("fetch", help="Fetch a single dataset")
    p_fetch.add_argument("--data-type", required=True,
                         help="e.g. a_stock_financial / us_stock_financial / macro_china_gdp")
    p_fetch.add_argument("--ts-code", default=None, help="Tushare-style code, e.g. 000001.SZ")
    p_fetch.add_argument("--ticker", default=None, help="yfinance-style ticker, e.g. AAPL")
    p_fetch.add_argument("--indicator", default=None, help="Macro indicator key")
    p_fetch.add_argument("--start-year", type=int, default=2015)
    p_fetch.add_argument("--end-year", type=int, default=2025)
    p_fetch.add_argument(
        "--sources", default="mcp,cli,http,synthetic",
        help="Comma-separated fallback order (default: mcp,cli,http,synthetic)",
    )
    p_fetch.add_argument("--output-json", default=None, help="Path to write the result as JSON")

    args = parser.parse_args()

    # NOTE: UniversalDataFetcher.__init__ does NOT accept a sources argument.
    # The sources parameter is only used by the 'fetch' subcommand.
    fetcher = UniversalDataFetcher()

    if args.cmd == "diagnose":
        report = fetcher.diagnose(data_type=args.data_type)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.cmd == "fetch":
        kwargs: dict[str, Any] = {"start_year": args.start_year, "end_year": args.end_year}
        if args.ts_code:
            kwargs["ts_code"] = args.ts_code
        if args.ticker:
            kwargs["ticker"] = args.ticker
        if args.indicator:
            kwargs["indicator"] = args.indicator
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        result = fetcher.fetch(args.data_type, **kwargs)
        summary = {
            "source": result.source.value,
            "provenance": result.provenance,
            "available": result.available,
            "error": result.error,
            "row_count": 0 if result.data is None else len(result.data),
        }
        if args.output_json:
            Path(args.output_json).write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if result.available else 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_cli())
