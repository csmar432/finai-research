#!/usr/bin/env python3
"""
scripts/fetch_provincial_stats.py
=================================
全国各省科技创新数据自动填充管道。

数据获取优先级（对应 acquisition_routes）：
  Tier 1 — MCP（需配置）
    • province-stats     → 读取本地 national_province_data_2026.json（已有数据时）
    • user-wb-data        → World Bank API（无需Key）
    • user-financial       → akshare 中国宏观（无需Key）
    • user-brave-search   → 各省公报关键词检索（需Key）
    • user-fetch          → 直接抓取各省统计局/科技厅官网

  Tier 2 — Web Search & Fetch（无需Key）
    • 搜索各省"2024年统计公报"获取公报URL
    • 直接 fetch 公报URL提取关键指标

  Tier 3 — Manual（用户提供）
    • 手动录入（用于无API的指标：数字经济、AI算力等）

用法：
    python scripts/fetch_provincial_stats.py --help
    python scripts/fetch_provincial_stats.py --province 湖北
    python scripts/fetch_provincial_stats.py --all --mcp
    python scripts/fetch_provincial_stats.py --rankings --export-xlsx
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_log = logging.getLogger("fetch_provincial_stats")

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.research_framework.data_fetcher import (
    DataSource,
    ProvenanceTracker,
    call_mcp_tool,
)

# ─── Constants ──────────────────────────────────────────────────────────────────

DATA_FILE = SCRIPT_DIR / "data" / "national_province_data_2026.json"
OUTPUT_XLSX = SCRIPT_DIR / "data" / "national_province_data_2026.xlsx"
PROVENANCE_FILE = SCRIPT_DIR / "data" / "provenance_provincial.json"

ALL_31_PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古",
    "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南",
    "广东", "广西", "海南",
    "重庆", "四川", "贵州", "云南", "西藏",
    "陕西", "甘肃", "青海", "宁夏", "新疆",
]

CAT_IDS = ["ECON", "EDU", "PLAT", "RD", "ENT", "TECH", "IND", "AI", "FIN"]

# Province name variations for search
PROVINCE_ALIASES = {
    "内蒙古": ["内蒙古", "内蒙"],
    "西藏": ["西藏", "西藏自治区"],
    "宁夏": ["宁夏", "宁夏回族自治区"],
    "新疆": ["新疆", "新疆维吾尔自治区"],
    "广西": ["广西", "广西壮族自治区"],
    "黑龙江": ["黑龙江", "黑龙江省"],
}

# Official statistics bureau URLs per province
PROVINCE_BULLETIN_URLS = {
    # 直接可访问的统计公报页面（优先官方gov.cn，支持hongheiku.com镜像）
    "北京": "https://www.beijing.gov.cn/hdjl_8611/ztzl_8614/tjsj/tjgb/2025/",
    "天津": "https://stats.tj.gov.cn/tjgb/zkgb/",
    "河北": "https://www.hestj.gov.cn/hdjl/tjgb/",
    "山西": "https://tjgb.hongheiku.com/sjtjgb/58259.html",
    "内蒙古": "https://m.kszhsy.com/tjsj/tjsj/tjgb/202504/t20250402_2692478.html",
    "辽宁": "https://tjj.ln.gov.cn/tjj/tjsj/sjfb/sqzx/2025011821363976950/index.shtml",
    "吉林": "https://tjgb.hongheiku.com/sjtjgb/57522.html",
    "黑龙江": "https://www.hlj.gov.cn/hlj/c108419/202504/c00_31866784.shtml",
    "上海": "https://tjj.sh.gov.cn/tjgb/2025/index.htm",
    "江苏": "https://stats.jiangsu.gov.cn/sjfb/tjgb/",
    "浙江": "https://tjj.zj.gov.cn/col/col1525/index.html",
    "安徽": "https://tjj.ah.gov.cn/ss/fq/tjsj/tjgb/index.html",
    "福建": "https://tjj.fujian.gov.cn/tjgb/zkgb/",
    "江西": "https://www.jxstj.gov.cn/tjsj/tjgb/",
    "山东": "https://stats.sd.gov.cn/tjgb/",
    "河南": "https://tjj.henan.gov.cn/tjgb/",
    "湖北": "https://stats.hb.cnpc.com.cn/tjj/2025/",
    "湖南": "https://tjj.hunan.gov.cn/tjsj/tjgb/",
    "广东": "https://stats.gd.gov.cn/tjsj/",
    "广西": "http://tjj.gxzf.gov.cn/tjsj/tjgb/qqgb/",
    "海南": "https://stats.hainan.gov.cn/tjsj/",
    "重庆": "https://tjj.cq.gov.cn/tjsj/tjgb/",
    "四川": "https://tjj.sc.gov.cn/scstjj/c105567/2025/",
    "贵州": "https://stjj.guizhou.gov.cn/tjsj/tjfbyjd/202503/t20250322_87236410.html",
    "云南": "https://www.yn.gov.cn/sjfb/tjgb/202504/t20250408_311279.html",
    "西藏": "https://www.xizang.gov.cn/xxgk/ztzl_8613/tjsj_8619/",
    "陕西": "https://tjj.shaanxi.gov.cn/tjsj/tjgb/",
    "甘肃": "https://tjj.gansu.gov.cn/tjj/c107471/tjgb.shtml",
    "青海": "https://tjj.qinghai.gov.cn/tjsj/tjgb/",
    "宁夏": "https://nx.gov.cn/tjsj/tjgb/",
    "新疆": "https://tjj.xinjiang.gov.cn/tjj/tjsj/tjgb/",
}


# ─── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class IndicatorValue:
    """单一年份指标值。"""
    value: Any
    unit: str
    source: str
    data_type: str = "A"  # A=真实, B=MCP可补充, C=手动录入
    year: str | None = None
    note: str = ""


@dataclass
class ProvinceResult:
    province: str
    verification: str = "empty"
    data: dict = field(default_factory=dict)  # cat_id -> {indicator_id -> IndicatorValue}
    time_series: dict = field(default_factory=dict)  # indicator_id -> {year -> value}
    errors: list = field(default_factory=list)
    fetched_via: str = "none"


# ─── MCP helpers ────────────────────────────────────────────────────────────────

def mcp_get_province_summary() -> dict | None:
    """调用 MCP get_all_provinces_summary 获取当前数据状态。"""
    try:
        result = call_mcp_tool("province-stats", "get_all_provinces_summary", {})
        if result:
            data = result.get("data", {}) if isinstance(result, dict) else result
            if isinstance(data, dict) and "provinces" in data:
                return data
            return data if isinstance(data, dict) else None
        return None
    except Exception as e:
        _log.warning(f"MCP get_all_provinces_summary failed: {e}")
        return None


def mcp_get_indicator(province: str, indicator: str, year: str = "") -> dict | None:
    """调用 MCP get_province_indicator 获取单一指标。"""
    args = {"province": province, "indicator": indicator}
    if year:
        args["year"] = year
    try:
        result = call_mcp_tool("province-stats", "get_province_indicator", args)
        if result:
            return result.get("data", result) if isinstance(result, dict) else None
        return None
    except Exception as e:
        _log.debug(f"MCP {province}/{indicator}: {e}")
        return None


def mcp_get_timeseries(province: str, indicator: str) -> dict | None:
    """调用 MCP get_province_timeseries 获取序列数据。"""
    try:
        result = call_mcp_tool("province-stats", "get_province_timeseries", {
            "province": province, "indicator": indicator
        })
        if result:
            return result.get("data", result) if isinstance(result, dict) else None
        return None
    except Exception as e:
        _log.debug(f"MCP ts {province}/{indicator}: {e}")
        return None


def mcp_get_rankings(table: str) -> dict | None:
    """调用 MCP get_province_rankings 获取排名表。"""
    try:
        result = call_mcp_tool("province-stats", "get_province_rankings", {"table": table})
        if result:
            return result.get("data", result) if isinstance(result, dict) else None
        return None
    except Exception as e:
        _log.debug(f"MCP rankings {table}: {e}")
        return None


# ─── Web search / fetch helpers ───────────────────────────────────────────────

def web_search_province_bulletin(province: str, year: int = 2024) -> dict | None:
    """
    使用 Brave Search 搜索各省统计公报URL。
    返回 {"url": str, "title": str} 或 None。
    """
    aliases = PROVINCE_ALIASES.get(province, [province])
    name = aliases[0]
    query = f"{name}省 {year}年 国民经济和社会发展统计公报 site:gov.cn"
    try:
        result = call_mcp_tool("user-brave-search", "brave-search", {
            "query": query, "count": 3, "source": "web"
        })
        if not result:
            return None
        items = result.get("web", result.get("results", []))
        for item in items:
            url = item.get("url", "")
            title = item.get("title", "")
            if url and any(kw in url for kw in ["gov.cn", "stats.gov.cn", "tjj."]):
                return {"url": url, "title": title}
        if items:
            return {"url": items[0].get("url"), "title": items[0].get("title")}
        return None
    except Exception as e:
        _log.debug(f"Brave search failed for {province}: {e}")
        return None


def fetch_bulletin_content(url: str) -> str | None:
    """
    使用 curl 抓取公报页面（macOS 系统级证书支持）。
    降级：subprocess → requests → urllib。
    """
    import subprocess

    # Try curl first (macOS system-level SSL certs)
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "20",
             "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             "-H", "Accept: text/html,application/xhtml+xml",
             url],
            capture_output=True, text=True, timeout=25,
        )
        text = r.stdout
        if text and len(text) > 100:
            return text
    except Exception as e:
        _log.debug(f"curl failed for {url}: {e}")

    # Fallback: requests — 先尝试 SSL 验证，失败后降级
    try:
        import requests
        try:
            # 优先使用 SSL 验证（安全）
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=15, verify=True, allow_redirects=True,
            )
        except Exception as ssl_err:
            # SSL 验证失败时降级（省级政府网站常有证书问题）
            _log.debug(f"SSL verification failed, retrying without: {ssl_err}")
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=15, verify=False, allow_redirects=True,
            )
        if resp.status_code == 200 and len(resp.text) > 100:
            return resp.text
    except Exception as e:
        _log.debug(f"requests failed for {url}: {e}")

    # Fallback: urllib — 先尝试 SSL，失败后降级
    try:
        import ssl
        import urllib.request
        # 优先使用系统 CA 证书
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = resp.read()
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            return raw.decode(charset, errors="replace")
    except ssl.SSLCertVerificationError:
        # 证书验证失败时降级（省级政府网站常有证书问题）
        _log.debug(f"SSL verification failed, retrying without: {url}")
        try:
            ctx_insecure = ssl.create_default_context()
            ctx_insecure.check_hostname = False
            ctx_insecure.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=15, context=ctx_insecure) as resp2:
                raw = resp2.read()
                charset = "utf-8"
                ct = resp2.headers.get("Content-Type", "")
                if "charset=" in ct:
                    charset = ct.split("charset=")[-1].split(";")[0].strip()
                return raw.decode(charset, errors="replace")
        except Exception:
            pass
    except Exception as e:
        _log.debug(f"urllib failed for {url}: {e}")

    return None


# ─── Content parsing helpers ──────────────────────────────────────────────────

def extract_value_from_text(
    text: str,
    patterns: list[str],
    target_unit: str = "亿",
) -> tuple[Any, str] | None:
    """
    从文本中提取数值。

    Args:
        text: 公报文本内容
        patterns: 正则表达式列表，按优先级排列
        target_unit: 目标单位（"亿" | "万" | "%" | None）。默认"亿"。
                    万→亿转换仅在 target_unit="亿" 且源数据为万时发生。

    Returns:
        (提取的数值, 匹配到的模式) 或 None
    """
    for pattern in patterns:
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            continue
        matched = m.group(0)
        nums = re.findall(r"[\d,]+\.?\d*", matched)
        if not nums:
            continue
        raw = nums[0].replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        # Unit conversion: only convert 万→亿 when target is 亿
        if target_unit == "亿":
            if "万亿" in matched or "万亿元" in matched:
                value *= 10000
            elif "亿" in matched and "万" not in matched:
                pass  # already in 亿
            elif "万" in matched:
                value /= 10000  # 万 → 亿
        # For target_unit="万", "家", "%" etc.: no conversion needed
        return value, matched[:80]
    return None


# Key indicator extraction patterns (GB/T 4754 industry standard)
INDICATOR_PATTERNS: dict[str, dict] = {
    "ECON": {
        "GDP": {
            "unit": "亿元",
            "patterns": [
                r"GDP[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"地区生产总值[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"实现地区生产总值[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"完成地区生产总值[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
            ]
        },
        "GDP增速": {
            "unit": "%",
            "patterns": [
                r"GDP[^\d]{0,20}([+-]?[\d,]+\.?\d*)\s*%",
                r"地区生产总值[^\d]{0,20}([+-]?[\d,]+\.?\d*)\s*%",
                r"同比增长[^\d]{0,20}([+-]?[\d,]+\.?\d*)\s*%",
                r"比上年增长[^\d]{0,20}([+-]?[\d,]+\.?\d*)\s*%",
            ]
        },
    },
    "RD": {
        "R&D经费": {
            "unit": "亿元",
            "patterns": [
                r"R&D[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"研发经费[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"研究与试验发展[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
            ]
        },
        "R&D强度": {
            "unit": "%",
            "patterns": [
                r"R&D[^\d]{0,20}([\d,]+\.?\d*)\s*%",
                r"研发投入强度[^\d]{0,20}([\d,]+\.?\d*)\s*%",
                r"R&D经费占GDP[^\d]{0,20}([\d,]+\.?\d*)\s*%",
            ]
        },
    },
    "ENT": {
        "高新技术企业": {
            "unit": "家",
            "patterns": [
                r"高新技术[^\d]{0,20}([\d,]+)\s*[家家]",
                r"高新技术企业[^\d]{0,20}([\d,]+)\s*[家家]",
            ]
        },
    },
    "TECH": {
        "技术合同成交额": {
            "unit": "亿元",
            "patterns": [
                r"技术合同[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"技术合同成交额[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
                r"技术合同登记[^\d]{0,20}([\d,]+\.?\d*)\s*[亿]",
            ]
        },
    },
    "EDU": {
        "高校数量": {
            "unit": "所",
            "patterns": [
                r"普通高校[^\d]{0,20}([\d,]+)\s*[所座个]",
                r"高等教育[^\d]{0,20}([\d,]+)\s*[所座个]",
            ]
        },
        "本专科在校生": {
            "unit": "万人",
            "patterns": [
                r"普通本专科[^\d]{0,20}([\d,]+\.?\d*)\s*[万人]",
                r"高等教育[^\d]{0,20}([\d,]+\.?\d*)\s*万人",
            ]
        },
        "研究生在学": {
            "unit": "万人",
            "patterns": [
                r"在学研究生[^\d]{0,20}([\d,]+\.?\d*)\s*[万人]",
                r"研究生(?!教育|招生)[^\d]{0,20}([\d,]+\.?\d*)\s*[万人]",
            ]
        },
    },
}


# ─── Core fetching pipeline ────────────────────────────────────────────────────

class ProvincialStatsFetcher:
    """
    各省科技创新数据填充器。

    工作流：
      1. load_skeleton()     — 加载现有骨架
      2. fetch_province()     — 获取单省数据
      3. fetch_all()         — 并行获取全部31省
      4. update_json()       — 写回 national_province_data_2026.json
      5. export_xlsx()       — 导出 Excel
      6. save_provenance()   — 保存数据溯源
    """

    def __init__(
        self,
        data_file: Path = DATA_FILE,
        output_xlsx: Path = OUTPUT_XLSX,
        use_mcp: bool = True,
        use_web: bool = True,
        delay_ms: int = 500,
    ):
        self.data_file = data_file
        self.output_xlsx = output_xlsx
        self.use_mcp = use_mcp
        self.use_web = use_web
        self.delay_ms = delay_ms

        self.data: dict | None = None
        self.provenance = ProvenanceTracker()

    # ── Step 1: Load ─────────────────────────────────────────────────────────

    def load_skeleton(self) -> dict:
        """加载现有骨架（骨架必须已存在）。"""
        if not self.data_file.exists():
            raise FileNotFoundError(
                f"骨架文件不存在: {self.data_file}\n"
                "请先确认 data/national_province_data_2026.json 骨架已创建。"
            )
        with open(self.data_file, encoding="utf-8") as f:
            self.data = json.load(f)
        provinces = list(self.data.get("provinces", {}).keys())
        _log.info(f"骨架加载完成：{len(provinces)} 省，文件大小 {self.data_file.stat().st_size/1024:.1f} KB")
        return self.data

    # ── Step 2: Fetch single province ─────────────────────────────────────────

    def fetch_province(
        self,
        province: str,
        indicators: list[str] | None = None,
        year: str = "2024",
    ) -> ProvinceResult:
        """
        获取单省数据（Tier1 Web抓取 → Tier2 MCP查询）。

        注意：骨架为空时 MCP 返回"未收录"，应优先使用 Web 抓取各省公报。
        MCP 适合查询已有数据的省。

        Args:
            province: 省名
            indicators: 要获取的指标列表（默认全量）
            year: 数据年份

        Returns:
            ProvinceResult，包含 data / time_series / errors
        """
        result = ProvinceResult(province=province, fetched_via="none")
        province_data = self.data["provinces"].get(province, {})
        cats = province_data.get("data", {})

        # Check if data already exists via MCP
        has_existing = any(cat_data for cat_data in cats.values())

        if indicators is None:
            indicators = list(INDICATOR_PATTERNS.keys())

        # ── Try MCP first ONLY if data already exists ──────────────────
        if self.use_mcp and has_existing:
            for cat_id in indicators:
                for ind_id in INDICATOR_PATTERNS.get(cat_id, {}):
                    mcp_result = mcp_get_indicator(province, ind_id, year)
                    if mcp_result and mcp_result.get("data"):
                        result.data.setdefault(cat_id, {})[ind_id] = IndicatorValue(
                            value=mcp_result["data"].get("value"),
                            unit=INDICATOR_PATTERNS[cat_id][ind_id]["unit"],
                            source=f"MCP:province-stats ({datetime.now().date()})",
                            data_type="A",
                            year=year,
                        )
                        self.provenance.record(
                            f"{province}.{cat_id}.{ind_id}",
                            DataSource.MCP_USER,
                            f"get_province_indicator/{ind_id}"
                        )
                    time.sleep(self.delay_ms / 1000)
            if result.data:
                result.fetched_via = "mcp"

        # ── Web fetch (primary data acquisition method) ───────────────
        if self.use_web and result.fetched_via == "none":
            bulletin_url = PROVINCE_BULLETIN_URLS.get(province)
            if not bulletin_url:
                search_result = web_search_province_bulletin(province, int(year))
                if search_result:
                    bulletin_url = search_result["url"]
                    _log.info(f"  Search ✓ {province}: {bulletin_url[:60]}")

            if bulletin_url:
                text = fetch_bulletin_content(bulletin_url)
                if text:
                    _log.info(f"  Fetch ✓ {province}: {len(text)} chars")
                    result.fetched_via = "web"

                    for cat_id, ind_map in INDICATOR_PATTERNS.items():
                        for ind_id, ind_def in ind_map.items():
                            extracted = extract_value_from_text(
                                text, ind_def["patterns"], target_unit=ind_def["unit"]
                            )
                            if extracted:
                                value, matched = extracted
                                result.data.setdefault(cat_id, {})[ind_id] = IndicatorValue(
                                    value=value,
                                    unit=ind_def["unit"],
                                    source=f"各省统计公报 (fetch: {bulletin_url[:60]})",
                                    data_type="A",
                                    year=year,
                                    note=matched.strip(),
                                )
                                self.provenance.record(
                                    f"{province}.{cat_id}.{ind_id}",
                                    DataSource.MANUAL,
                                    f"web_fetch:{bulletin_url[:40]}"
                                )
                                _log.info(f"  Extract ✓ {province}/{ind_id}: {value} {ind_def['unit']}")
                else:
                    result.errors.append(f"Failed to fetch bulletin for {province}")
            else:
                result.errors.append(f"No bulletin URL found for {province}")

        result.verification = "partial" if result.data else "empty"
        return result

    # ── Step 3: Batch fetch all provinces ────────────────────────────────────

    def fetch_all(
        self,
        provinces: list[str] | None = None,
        year: str = "2024",
        concurrent: int = 5,
    ) -> dict[str, ProvinceResult]:
        """
        并行获取多个省的数据。

        Args:
            provinces: 省名列表（默认全部31省）
            year: 数据年份
            concurrent: 并发数上限（建议≤5，避免触发反爬）

        Returns:
            {province_name: ProvinceResult}
        """
        if provinces is None:
            provinces = ALL_31_PROVINCES

        _log.info(f"\n开始获取 {len(provinces)} 省数据（并发上限={concurrent}）...")

        results: dict[str, ProvinceResult] = {}
        for i, prov in enumerate(provinces, 1):
            _log.info(f"[{i}/{len(provinces)}] 获取 {prov} ...")
            try:
                r = self.fetch_province(prov, year=year)
                results[prov] = r
                count = sum(len(cat) for cat in r.data.values())
                _log.info(f"  → {prov}: {count} 个指标, verification={r.verification}")
            except Exception as e:
                _log.error(f"  ✗ {prov} failed: {e}")
                results[prov] = ProvinceResult(province=prov, errors=[str(e)])
            time.sleep(self.delay_ms / 1000)

        # Summary
        verified = sum(1 for r in results.values() if r.verification == "partial")
        _log.info(f"\n完成：{len(results)} 省 | partial={verified} | empty={len(results)-verified}")

        return results

    # ── Step 4: Update JSON ────────────────────────────────────────────────

    def update_json(self, results: dict[str, ProvinceResult]) -> None:
        """
        将 ProvinceResult 写回 national_province_data_2026.json。

        对每个省：
          - 用新数据填充 provinces.<name>.data
          - 更新 verification 状态
          - 从 data 重建 ranking_tables
        """
        for prov, res in results.items():
            if prov not in self.data["provinces"]:
                _log.warning(f"Province {prov} not in skeleton, skipping")
                continue

            prov_data = self.data["provinces"][prov]
            prov_data["verification"] = res.verification

            for cat_id, indicators in res.data.items():
                if cat_id not in prov_data["data"]:
                    prov_data["data"][cat_id] = {}
                for ind_id, iv in indicators.items():
                    prov_data["data"][cat_id][ind_id] = {
                        "value": iv.value,
                        "unit": iv.unit,
                        "source": iv.source,
                        "data_type": iv.data_type,
                        "year": iv.year,
                        "note": iv.note,
                    }

            # Track categories that have data
            cats_with_data = [cat for cat, inds in prov_data["data"].items() if inds]
            prov_data["categories"] = cats_with_data

        # Rebuild ranking tables from all province data
        self._rebuild_rankings()

        # Write back
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        _log.info(f"JSON 已更新：{self.data_file} ({self.data_file.stat().st_size/1024:.1f} KB)")

    def _rebuild_rankings(self) -> None:
        """从 provinces 数据重建 ranking_tables。"""
        ranking_map: dict[str, list[tuple]] = {
            "GDP_2024": [],
            "RD经费_2024": [],
            "RD强度_2024": [],
            "高新技术企业_2024": [],
            "技术合同_2024": [],
        }
        field_map: dict[str, tuple[str, str]] = {
            "GDP_2024": ("ECON", "GDP"),
            "RD经费_2024": ("RD", "R&D经费"),
            "RD强度_2024": ("RD", "R&D强度"),
            "高新技术企业_2024": ("ENT", "高新技术企业"),
            "技术合同_2024": ("TECH", "技术合同成交额"),
        }

        for prov, prov_data in self.data["provinces"].items():
            cats = prov_data.get("data", {})
            for table, (cat_id, ind_id) in field_map.items():
                ind_data = cats.get(cat_id, {}).get(ind_id)
                if ind_data and ind_data.get("value") is not None:
                    ranking_map[table].append((prov, ind_data.get("value", 0), ind_data.get("source", "")))

        # Sort and update tables
        for table, rows in ranking_map.items():
            rows_sorted = sorted(rows, key=lambda x: x[1], reverse=True)
            if table in self.data["ranking_tables"]:
                headers = self.data["ranking_tables"][table].get("headers", [])
                self.data["ranking_tables"][table]["data"] = [
                    [rank + 1, prov, val, src]
                    for rank, (prov, val, src) in enumerate(rows_sorted)
                ]

    # ── Step 5: Export Excel ───────────────────────────────────────────────

    def export_xlsx(self) -> None:
        """导出 national_province_data_2026.xlsx。"""
        try:
            import pandas as pd
        except ImportError:
            _log.warning("pandas 未安装，跳过 Excel 导出")
            return

        rows = []
        for prov, prov_data in self.data["provinces"].items():
            for cat_id, indicators in prov_data.get("data", {}).items():
                for ind_id, ind_data in indicators.items():
                    if isinstance(ind_data, dict):
                        rows.append({
                            "省份": prov,
                            "类别": cat_id,
                            "指标": ind_id,
                            "数值": ind_data.get("value"),
                            "单位": ind_data.get("unit", ""),
                            "年份": ind_data.get("year", ""),
                            "数据来源": ind_data.get("source", ""),
                            "数据类型": ind_data.get("data_type", "A"),
                            "核查状态": prov_data.get("verification", "unknown"),
                        })

        if not rows:
            _log.warning("无数据可导出，跳过 xlsx")
            return

        df = pd.DataFrame(rows)
        self.output_xlsx.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(self.output_xlsx, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="数据总表", index=False)
            # Summary sheet
            summary = pd.DataFrame([
                {"省份": prov, "核查状态": pdata.get("verification", "?"),
                 "数据类别数": len([c for c in pdata.get("data", {}).values() if c]),
                 "指标总数": sum(len(v) for v in pdata.get("data", {}).values())}
                for prov, pdata in self.data["provinces"].items()
            ])
            summary.to_excel(writer, sheet_name="省情总览", index=False)

        _log.info(f"Excel 已导出：{self.output_xlsx}（{len(rows)} 行）")

    # ── Step 6: Save provenance ─────────────────────────────────────────────

    def save_provenance(self, filepath: Path = PROVENANCE_FILE) -> None:
        """保存数据溯源记录。"""
        summary = self.provenance.summary()
        records = {k: {"source": v.source.value, "detail": v.source_detail, "is_sim": v.is_simulated}
                   for k, v in self.provenance._records.items()}
        output = {"summary": summary, "records": records, "saved_at": datetime.now(timezone.utc).isoformat()}
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        _log.info(f"溯源记录已保存：{filepath}")

    # ── Full pipeline ────────────────────────────────────────────────────────

    def run(
        self,
        provinces: list[str] | None = None,
        year: str = "2024",
        fetch: bool = True,
        export: bool = True,
        provenance: bool = True,
    ) -> dict[str, ProvinceResult]:
        """
        完整数据填充流程。

        Steps: load_skeleton → fetch_provinces → update_json → export_xlsx → save_provenance
        """
        self.load_skeleton()

        results: dict[str, ProvinceResult] = {}
        if fetch:
            results = self.fetch_all(provinces, year)
            self.update_json(results)

        if export and self.data:
            self.export_xlsx()

        if provenance:
            self.save_provenance()

        return results


# ─── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="全国各省科技创新数据自动填充管道",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--province", type=str, default=None,
                        help="只获取指定省（如：湖北）")
    parser.add_argument("--all", action="store_true",
                        help="获取全部31省")
    parser.add_argument("--year", type=str, default="2024",
                        help="数据年份（默认2024）")
    parser.add_argument("--mcp", action="store_true",
                        help="仅使用MCP获取（跳过Web）")
    parser.add_argument("--web", action="store_true",
                        help="仅使用Web获取")
    parser.add_argument("--rankings", action="store_true",
                        help="仅重建排名表（不重新获取数据）")
    parser.add_argument("--export-xlsx", action="store_true",
                        help="导出Excel")
    parser.add_argument("--provenance", action="store_true",
                        help="保存数据溯源")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅加载骨架，不获取数据")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    fetcher = ProvincialStatsFetcher(use_mcp=not args.web, use_web=not args.mcp)

    if args.dry_run:
        fetcher.load_skeleton()
        provinces = list(fetcher.data["provinces"].keys())
        _log.info(f"骨架验证：{len(provinces)} 省")
        for prov in provinces[:5]:
            pdata = fetcher.data["provinces"][prov]
            cats = list(pdata.get("data", {}).keys())
            _log.info(f"  {prov}: {cats}")
        return

    if args.rankings:
        fetcher.load_skeleton()
        fetcher._rebuild_rankings()
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(fetcher.data, f, indent=2, ensure_ascii=False)
        _log.info("排名表已重建")
        return

    provinces = None
    if args.province:
        provinces = [args.province]
    elif args.all:
        provinces = None  # all

    results = fetcher.run(
        provinces=provinces,
        year=args.year,
        fetch=True,
        export=args.export_xlsx,
        provenance=args.provenance,
    )

    # Print summary
    if results:
        print("\n" + "=" * 60)
        print("获取结果摘要：")
        for prov, res in results.items():
            count = sum(len(cat) for cat in res.data.values())
            status = "✅" if res.verification == "partial" else "❌"
            print(f"  {status} {prov}: {count}指标 | {res.fetched_via} | {res.verification}")


if __name__ == "__main__":
    main()
