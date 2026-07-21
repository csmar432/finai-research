"""
数据源预检查模块
论文-研报工作流 · FinResearch Agent

【设计原则】
1. 所有实证脚本必须在运行任何数据获取代码前调用 DataSourceChecker
2. 模拟数据必须经用户明确授权才可使用，禁止静默fallback
3. 每个数据缺口必须有明确的用户交互确认
4. 所有检查结果必须向用户展示并等待确认

【用法】
    from scripts.data_source_checker import DataSourceChecker, DataRequirement

    # 定义研究需要的数据
    requirements = [
        DataRequirement(
            name="A股财务数据",
            description="资产负债率、ROA、规模等公司财务指标",
            sources=["tushare", "wind", "csmar"],
            required=True,
            user_facing_name="A股财务数据（资产负债率/ROA等）"
        ),
        DataRequirement(
            name="海关进出口数据",
            description="上市公司对美出口明细（含HS编码）用于构建关税暴露强度",
            sources=["csmar_customs"],
            required=True,
            user_facing_name="上市公司海关进出口明细（HS编码）"
        ),
        ...
    ]

    checker = DataSourceChecker(requirements)
    result = checker.run()

    if result.requires_synthetic_data:
        # 【硬中断】必须用户授权
        print(result.authorization_request_message)
        user_response = ask_user授权()
        if not user_response.authorized:
            sys.exit(0)  # 停止，不使用模拟数据
        # 继续使用模拟数据...
    else:
        # 有真实数据可用，继续...
        pass
"""

from __future__ import annotations

import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd

# ── ANSI Colors ────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ── 数据源枚举 ────────────────────────────────────────────────────────────────

class DataSource(str, Enum):
    # MCP数据源（无需API Key）
    TUSHARE = "tushare"              # A股行情/财务/融资融券（需Token）
    WIND = "wind"                    # Wind金融终端
    CSMAR = "csmar"                 # CSMAR数据库（需机构账号）
    CSMAR_CUSTOMS = "csmar_customs" # CSMAR海关数据（需机构账号）
    AKSHARE = "akshare"             # akshare（无需Key，部分功能免费）
    EASTMONEY = "eastmoney"         # 东方财富（无需Key）

    # MCP服务（已验证可用）
    USER_FINANCIAL = "user-financial"  # 全球宏观数据（WB API + akshare）
    USER_EODHD = "user-eodhd"        # 美债收益率/经济日历（需Key）
    USER_FED = "user-fed-data"        # 美联储数据
    USER_WB = "user-wb-data"         # 世界银行数据
    USER_IMF = "user-imf-data"        # IMF数据
    USER_OECD = "user-oecd-data"      # OECD数据
    USER_EASTMONEY_REPORTS = "user-eastmoney-reports"  # 研报/新闻

    # 外部数据文件
    LOCAL_CSV = "local_csv"
    LOCAL_EXCEL = "local_excel"

    # 模拟数据
    SYNTHETIC = "synthetic"


@dataclass
class DataRequirement:
    """单一数据需求定义"""
    name: str                      # 内部名称（如 "tariff_exposure"）
    user_facing_name: str           # 用户可见名称（如 "关税暴露强度"）
    description: str               # 对用户说明此数据用途
    sources: list[str]              # 可用数据源列表
    required: bool = True          # 是否必须（有真实数据才能继续）
    min_quality: str = "real"      # "real" = 必须真实数据 | "demo" = 可用演示数据 | "any" = 无所谓


@dataclass
class SourceCheckResult:
    """单一数据源检查结果"""
    source: str
    status: str          # "available" | "requires_auth" | "requires_key" | "requires_purchase" | "unavailable" | "not_tested"
    message: str          # 用户可见的状态说明
    details: str = ""      # 技术细节
    url: str = ""         # 获取途径URL


@dataclass
class UserDataFile:
    """data/ 目录下扫描到的单个文件"""
    path: str
    name: str
    size_bytes: int
    file_type: str  # "csv" | "xlsx" | "xls" | "json"
    detected_columns: list[str] = field(default_factory=list)
    suggested_use: str = ""


@dataclass
class UserDataScanResult:
    """scan_user_data_dir() 的扫描结果"""
    found_files: list[UserDataFile] = field(default_factory=list)
    files_by_category: dict[str, list[UserDataFile]] = field(default_factory=dict)
    total_files: int = 0
    total_size_mb: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    """完整检查结果"""
    # 各数据源检查结果
    source_results: dict[str, SourceCheckResult]

    # 真实数据可用情况
    available_sources: list[str]      # 可立即使用的数据源
    partial_sources: list[str]          # 部分可用（有缺口）的数据源
    unavailable_sources: list[str]      # 完全不可用的数据源

    # 是否必须询问用户
    requires_user_query: bool
    requires_synthetic_data: bool       # 是否需要用户授权才能使用模拟数据

    # 给用户展示的消息
    summary_message: str
    authorization_request_message: str  # 如果需要模拟数据授权，展示给用户的请求消息
    next_steps_message: str             # 用户可采取的行动

    # 技术报告
    tech_report: str                   # 详细技术信息（供开发者debug）

    # P3: 细粒度授权结果
    partial_auth_results: dict[str, bool] = field(default_factory=dict)  # var_name -> authorized


def _probe_url(url: str, timeout: int = 8) -> tuple[bool, str]:
    """探测URL是否可访问"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FinResearch-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"连接失败: {e.reason}"
    except Exception as e:
        return False, str(e)[:60]


def _read_env(path: Path) -> dict[str, str]:
    """读取.env文件"""
    env = {}
    if not path.exists():
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ── 核心检查器 ────────────────────────────────────────────────────────────────

class DataSourceChecker:
    """
    数据源预检查器

    使用流程：
    1. 实例化时传入研究需要的数据需求列表
    2. 调用 run() 执行检查
    3. 检查结果包含：
       - 每个数据源的状态
       - 是否需要用户授权使用模拟数据
       - 给用户展示的完整报告
    4. 调用 should_stop() 判断是否应该停止（用户未授权模拟数据时）

    【强制规范】
    - 模拟数据 = 下下策，必须用户明确授权
    - 没有真实数据时，必须停下来让用户选择：
      (1) 补充数据后再继续
      (2) 授权使用演示数据（但不发表）
      (3) 更换研究方向
    - 禁止静默fallback到模拟数据
    """

    # 数据源元信息表（URL/获取方式）
    SOURCE_META: dict[str, dict] = {
        "tushare": {
            "name": "Tushare Pro",
            "get_url": "https://tushare.pro/register",
            "env_var": "TUSHARE_TOKEN",
            "description": "A股财务/行情/融资融券",
            "cost": "免费注册有积分额度",
        },
        "csmar": {
            "name": "CSMAR国泰安",
            "get_url": "https://www.gtadata.com",
            "env_var": "CSMAR_API_KEY",
            "description": "A股财务/公司治理/海关数据",
            "cost": "需机构账号（高校图书馆通常有）",
        },
        "csmar_customs": {
            "name": "CSMAR海关数据",
            "get_url": "https://www.gtadata.com",
            "env_var": "CSMAR_API_KEY",
            "description": "上市公司进出口明细（HS编码）",
            "cost": "需CSMAR完整版机构账号",
        },
        "wind": {
            "name": "Wind万得",
            "get_url": "https://www.wind.com.cn",
            "env_var": "",
            "description": "A股财务/宏观数据（机构用户）",
            "cost": "商业付费（学校可能有授权）",
        },
        "akshare": {
            "name": "akshare",
            "get_url": "https://akshare.akfamily.net",
            "env_var": "",
            "description": "免费金融数据（部分接口可用）",
            "cost": "免费",
        },
        "user-financial": {
            "name": "MCP: user-financial",
            "get_url": "无需配置，直接使用",
            "env_var": "",
            "description": "中国宏观GDP/CPI/M2（akshare接口）",
            "cost": "免费，无需Key",
        },
        "user-eodhd": {
            "name": "MCP: user-eodhd",
            "get_url": "https://eodhd.com",
            "env_var": "EODHD_API_KEY",
            "description": "美债收益率/经济日历",
            "cost": "免费Key可用",
        },
        "user-wb-data": {
            "name": "MCP: user-wb-data",
            "get_url": "无需配置，直接使用",
            "env_var": "",
            "description": "世界银行GDP/人口/贸易数据",
            "cost": "免费，World Bank API",
        },
        "user-fed-data": {
            "name": "MCP: user-fed-data",
            "get_url": "无需配置，直接使用",
            "env_var": "",
            "description": "美联储/FOMC数据",
            "cost": "免费",
        },
        "user-imf-data": {
            "name": "MCP: user-imf-data",
            "get_url": "无需配置，直接使用",
            "env_var": "",
            "description": "IMF全球经济数据",
            "cost": "免费",
        },
        "local_csv": {
            "name": "本地CSV文件",
            "get_url": "将文件放入 data/ 目录",
            "env_var": "",
            "description": "用户提供的数据文件",
            "cost": "免费",
        },
    }

    def __init__(self, requirements: list[DataRequirement]):
        self.requirements = requirements
        self._results: Optional[CheckResult] = None

    # ── 单数据源检查 ──────────────────────────────────────────────────────────

    def _check_single_source(self, source_id: str) -> SourceCheckResult:
        """检查单个数据源的可用性"""

        # 读取环境变量
        root = Path(__file__).parent.parent
        env_local = _read_env(root / ".env.local")
        env = _read_env(root / ".env")
        all_env = {**env, **env_local}

        # 已知数据源元信息
        if source_id in self.SOURCE_META:
            meta = self.SOURCE_META[source_id]
            env_var = meta.get("env_var", "")
            key = all_env.get(env_var, "").strip() if env_var else ""

            # 1. Tushare：需要Token
            if source_id == "tushare":
                if key:
                    ok, msg = _probe_url("https://api.tushare.pro", timeout=6)
                    if ok:
                        return SourceCheckResult(
                            source=source_id, status="available",
                            message=f"Tushare Pro API 可用（Token已配置）",
                            details=f"Token: {key[:4]}***",
                            url=meta["get_url"]
                        )
                    else:
                        return SourceCheckResult(
                            source=source_id, status="requires_auth",
                            message=f"Tushare Token已配置但API无法访问: {msg}",
                            details=f"Token: {key[:4]}*** | 网络问题: {msg}",
                            url=meta["get_url"]
                        )
                else:
                    return SourceCheckResult(
                        source=source_id, status="requires_key",
                        message=f"需要配置 TUSHARE_TOKEN 才能获取A股财务数据",
                        details=f"Tushare Pro: {meta['description']} | {meta['cost']}",
                        url=meta["get_url"]
                    )

            # 2. CSMAR海关数据：需要机构账号
            elif source_id == "csmar_customs":
                if key:
                    return SourceCheckResult(
                        source=source_id, status="requires_purchase",
                        message=f"CSMAR海关数据需要机构账号（Token≠数据权限）",
                        details="CSMAR API Key不等于海关数据库访问权限，通常需要高校图书馆VPN或购买",
                        url=meta["get_url"]
                    )
                else:
                    return SourceCheckResult(
                        source=source_id, status="requires_key",
                        message=f"需要CSMAR机构账号才能访问海关进出口数据",
                        details="CSMAR海关数据通常仅通过高校图书馆VPN访问，需联系学校图书馆",
                        url=meta["get_url"]
                    )

            # 3. CSMAR通用：需要账号
            elif source_id == "csmar":
                if key:
                    return SourceCheckResult(
                        source=source_id, status="requires_purchase",
                        message=f"CSMAR需要机构账号（API Key≠机构权限）",
                        details="请确认所在机构已购买CSMAR数据库",
                        url=meta["get_url"]
                    )
                else:
                    return SourceCheckResult(
                        source=source_id, status="requires_key",
                        message=f"需要CSMAR_API_KEY",
                        details=f"注册: {meta['get_url']}",
                        url=meta["get_url"]
                    )

            # 4. Wind：商业付费
            elif source_id == "wind":
                return SourceCheckResult(
                    source=source_id, status="requires_purchase",
                    message=f"Wind万得需商业授权（学校可能有）",
                    details=meta["description"],
                    url=meta["get_url"]
                )

            # 5. akshare：免费但不稳定
            elif source_id == "akshare":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message=f"akshare可用（免费，无需Key，但部分接口可能不稳定）",
                    details="建议作为辅助数据源，主要数据仍需Tushare/CSMAR",
                    url=meta["get_url"]
                )

            # 6. user-financial（MCP）
            elif source_id == "user-financial":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message=f"MCP user-financial 可用（akshare接口，无需Key）",
                    details="可获取中国GDP/CPI/M2等宏观指标",
                    url=meta["get_url"]
                )

            # 7. user-wb-data（MCP）
            elif source_id == "user-wb-data":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message=f"MCP user-wb-data 可用（World Bank API，无需Key）",
                    details="覆盖全球所有国家GDP/人口/贸易数据",
                    url=meta["get_url"]
                )

            # 8. user-eodhd
            elif source_id == "user-eodhd":
                if key:
                    return SourceCheckResult(
                        source=source_id, status="available",
                        message=f"MCP user-eodhd 可用（EODHD API Key已配置）",
                        details=f"Token: {key[:4]}***",
                        url=meta["get_url"]
                    )
                else:
                    return SourceCheckResult(
                        source=source_id, status="requires_key",
                        message=f"MCP user-eodhd 需要EODHD_API_KEY",
                        details="免费注册获取Key: https://eodhd.com",
                        url=meta["get_url"]
                    )

            # 9. user-fed-data（MCP）
            elif source_id == "user-fed-data":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message=f"MCP user-fed-data 可用（无需Key）",
                    details=meta["description"],
                    url=meta["get_url"]
                )

            # 10. user-imf-data（MCP）
            elif source_id == "user-imf-data":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message=f"MCP user-imf-data 可用（无需Key）",
                    details=meta["description"],
                    url=meta["get_url"]
                )

            # 11. 本地文件
            elif source_id in ("local_csv", "local_excel"):
                data_dir = root / "data"
                if data_dir.exists() and any(data_dir.iterdir()):
                    files = [f.name for f in data_dir.iterdir() if f.is_file()]
                    return SourceCheckResult(
                        source=source_id, status="available",
                        message=f"本地数据文件: {', '.join(files[:5])}",
                        details=f"data/ 目录存在",
                        url=""
                    )
                else:
                    return SourceCheckResult(
                        source=source_id, status="unavailable",
                        message=f"data/ 目录为空或不存在",
                        details="请将CSV/Excel文件放入 data/ 目录",
                        url=""
                    )

            # 12. 模拟数据
            elif source_id == "synthetic":
                return SourceCheckResult(
                    source=source_id, status="available",
                    message="模拟数据可用（需用户授权）",
                    details="仅用于演示流程，不能用于发表",
                    url=""
                )

        # 未知数据源
        return SourceCheckResult(
            source=source_id, status="not_tested",
            message=f"数据源 '{source_id}' 未知，无法检查",
            details="请检查 SOURCE_META 表是否包含此数据源",
            url=""
        )

    # ── 完整检查 ──────────────────────────────────────────────────────────────

    def run(self) -> CheckResult:
        """执行完整数据源检查"""
        results: dict[str, SourceCheckResult] = {}

        for req in self.requirements:
            for src in req.sources:
                if src not in results:
                    results[src] = self._check_single_source(src)

        # 分类
        available = []
        partial = []
        unavailable = []

        for src_id, result in results.items():
            if result.status == "available":
                available.append(src_id)
            elif result.status in ("requires_key", "requires_purchase", "requires_auth"):
                unavailable.append(src_id)
            elif result.status == "not_tested":
                unavailable.append(src_id)

        # 判断是否需要询问用户
        # 如果有任何 required=True 的需求没有可用数据源，则需要用户授权
        required_without_data = []
        for req in self.requirements:
            if not req.required:
                continue
            has_available = False
            for src in req.sources:
                src_result = results.get(src)
                if src_result and src_result.status == "available":
                    has_available = True
                    break
            if not has_available:
                required_without_data.append(req)

        requires_synthetic = len(required_without_data) > 0

        # 生成报告
        summary_parts = []
        if available:
            summary_parts.append(f"✅ 可用数据源: {', '.join(available)}")
        if unavailable:
            summary_parts.append(f"❌ 不可用数据源: {', '.join(unavailable)}")

        summary_msg = " | ".join(summary_parts) if summary_parts else "无数据源信息"

        # 授权请求消息（如果需要）
        auth_msg = ""
        if requires_synthetic:
            [req.user_facing_name for req in required_without_data]
            auth_msg = (
                f"\n{'='*60}\n"
                f"🔴 数据缺口 — 无法继续\n"
                f"{'='*60}\n\n"
                f"研究需要以下数据，但当前没有可用来源：\n\n"
            )
            for req in required_without_data:
                auth_msg += f"  • {req.user_facing_name}\n"
                auth_msg += f"    用途: {req.description}\n"
                for src in req.sources:
                    if src in results:
                        r = results[src]
                        auth_msg += f"    状态: {r.message}\n"
                        if r.url:
                            auth_msg += f"    获取: {r.url}\n"
                auth_msg += "\n"

            auth_msg += (
                f"{'='*60}\n"
                f"下一步（请选择）：\n\n"
                f"  (1) 补充数据后再继续\n"
                f"      → 配置 Tushare Token / 联系学校图书馆申请CSMAR账号\n"
                f"      → 将数据文件放入 data/ 目录\n\n"
                f"  (2) 授权使用演示数据\n"
                f"      → 仅用于演示完整研究流程\n"
                f"      → 论文不能发表，需后续替换为真实数据\n\n"
                f"  (3) 更换研究方向\n"
                f"      → 选择数据更易获取的研究主题\n\n"
                f"{'='*60}\n"
            )

        # 技术报告
        tech = "数据源检查技术报告:\n"
        for src_id, r in results.items():
            tech += f"  {src_id}: [{r.status}] {r.message}\n"
            if r.details:
                tech += f"    详情: {r.details}\n"

        self._results = CheckResult(
            source_results=results,
            available_sources=available,
            partial_sources=partial,
            unavailable_sources=unavailable,
            requires_user_query=requires_synthetic,
            requires_synthetic_data=requires_synthetic,
            summary_message=summary_msg,
            authorization_request_message=auth_msg,
            next_steps_message="见上方授权请求消息",
            tech_report=tech,
        )
        return self._results

    def print_report(self) -> None:
        """打印完整报告给用户"""
        if self._results is None:
            self.run()

        r = self._results

        print()
        print(c("═" * 60, CYAN))
        title = "  数据源预检查报告  "
        print(c("║", CYAN) + c(title.center(54), CYAN) + c(" ║", CYAN))
        print(c("═" * 60, CYAN))
        print()

        # 按状态分组显示
        available_srcs = [(k, v) for k, v in r.source_results.items() if v.status == "available"]
        unavailable_srcs = [(k, v) for k, v in r.source_results.items() if v.status != "available"]

        if available_srcs:
            print(c("✅ 可用数据源:", GREEN))
            for src_id, res in available_srcs:
                print(f"  • {src_id}: {res.message}")
            print()

        if unavailable_srcs:
            print(c("❌ 不可用/需配置的数据源:", RED))
            for src_id, res in unavailable_srcs:
                status_icon = {
                    "requires_key": "🔑 需要API Key",
                    "requires_purchase": "💰 需机构账号",
                    "requires_auth": "🔐 需要认证",
                    "unavailable": "❌ 不可用",
                    "not_tested": "⚠️ 未测试",
                }.get(res.status, res.status)
                print(f"  {status_icon} {src_id}")
                print(f"     {res.message}")
                if res.details:
                    print(f"     详情: {res.details}")
                if res.url:
                    print(f"     获取: {res.url}")
            print()

        # 如果需要授权，打印授权请求
        if r.requires_synthetic_data:
            print(c("═" * 60, YELLOW))
            print(c(r.authorization_request_message, YELLOW))
            print()

        print(f"{c('─'*60, CYAN)}")
        print(f"技术详情（供debug）:")
        print(f"  可用: {r.available_sources}")
        print(f"  不可用: {r.unavailable_sources}")
        print(f"  需要授权模拟数据: {r.requires_synthetic_data}")
        print()

    def should_stop_for_synthetic(self) -> bool:
        """
        判断是否应该停止（当需要模拟数据但用户未授权时返回True）
        调用方必须检查此返回值，为True时必须中断流程
        """
        if self._results is None:
            self.run()
        return self._results.requires_synthetic_data

    # ── P2: 用户数据目录自动扫描 ─────────────────────────────────────────────

    def scan_user_data_dir(
        self,
        idea_keywords: list[str] | None = None,
    ) -> UserDataScanResult:
        """
        P2: 自动扫描 data/ 目录，识别与研究相关的用户数据文件。

        Args:
            idea_keywords: 可选的研究关键词列表，用于过滤相关文件。

        Returns:
            UserDataScanResult，包含所有扫描到的文件、分类和建议。
        """
        import json

        result = UserDataScanResult()
        data_dir = Path(__file__).parent.parent / "data"

        if not data_dir.exists():
            print(c("⚠ data/ 目录不存在", YELLOW))
            return result

        keywords = set(k.lower() for k in (idea_keywords or []))

        # Scan all subdirectories
        for subdir in data_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith((".", "__", "processed")):
                continue

            category = subdir.name
            files_in_category: list[UserDataFile] = []

            for item in subdir.iterdir():
                if not item.is_file():
                    continue

                ext = item.suffix.lower()
                if ext not in (".csv", ".xlsx", ".xls", ".json"):
                    continue

                size_bytes = item.stat().st_size
                result.total_size_mb += size_bytes / (1024 * 1024)

                # Read headers (first 3 rows for Excel)
                try:
                    if ext == ".csv":
                        df_peek = pd.read_csv(item, nrows=3, encoding="utf-8-sig")
                    elif ext in (".xlsx", ".xls"):
                        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
                        df_peek = pd.read_excel(item, engine=engine, nrows=3)
                    elif ext == ".json":
                        with open(item, encoding="utf-8") as f:
                            json_data = json.load(f)
                        if isinstance(json_data, list) and len(json_data) > 0:
                            df_peek = pd.DataFrame(json_data[:3])
                        else:
                            df_peek = pd.DataFrame()
                    else:
                        df_peek = pd.DataFrame()

                    detected_cols = [str(c) for c in df_peek.columns]
                except Exception as exc:
                    detected_cols = []
                    print(f"  读取 {item.name} 头失败: {exc}")

                # Determine suggested use based on column names and keywords
                suggested_use = self._suggest_file_use(detected_cols, keywords)

                udf = UserDataFile(
                    path=str(item),
                    name=item.name,
                    size_bytes=size_bytes,
                    file_type=ext.lstrip("."),
                    detected_columns=detected_cols,
                    suggested_use=suggested_use,
                )
                files_in_category.append(udf)
                result.found_files.append(udf)

            if files_in_category:
                result.files_by_category[category] = files_in_category

        result.total_files = len(result.found_files)

        # Generate recommendations
        result.recommendations = self._generate_file_recommendations(
            result.found_files, keywords
        )

        # Print formatted report
        self._print_scan_report(result, idea_keywords)
        return result

    def _suggest_file_use(self, columns: list[str], keywords: set[str]) -> str:
        """根据列名推断文件的可能用途"""
        col_text = " ".join(c.lower() for c in columns)

        use_map = [
            (["tariff", "customs", "export", "import", "hs"], "海关进出口/关税数据"),
            (["roa", "roe", "leverage", "debt", "asset", "财务"], "A股财务数据"),
            (["patent", "rd", "innovation", "绿色"], "创新/专利数据"),
            (["esg", "carbon", "emission", "绿色"], "ESG/碳排放数据"),
            (["macro", "gdp", "cpi", "m2", "inflation"], "宏观数据"),
            (["news", "sentiment", "analyst"], "舆情/分析师数据"),
            (["fund", "nav", "flow", "基金"], "基金数据"),
            (["bond", "yield", "repo", "债券"], "债券数据"),
            (["option", "volatility", "期权"], "期权数据"),
        ]

        for keywords_group, label in use_map:
            if any(kw in col_text for kw in keywords_group):
                return label

        if keywords:
            for kw in keywords:
                if kw.lower() in col_text:
                    return f"可能相关（关键词: {kw}）"

        return "通用数据文件"

    def _generate_file_recommendations(
        self, files: list[UserDataFile], keywords: set[str]
    ) -> list[str]:
        """生成文件使用建议"""
        recommendations: list[str] = []

        if not files:
            recommendations.append("data/ 目录为空，请将CSV/Excel文件放入对应的子目录")
            return recommendations

        # Group by suggested_use
        by_use: dict[str, list[UserDataFile]] = {}
        for f in files:
            use = f.suggested_use or "通用"
            by_use.setdefault(use, []).append(f)

        for use, file_list in by_use.items():
            names = [f.name for f in file_list]
            recommendations.append(f"  • {use}: {', '.join(names)}")

        return recommendations

    def _print_scan_report(
        self, result: UserDataScanResult, keywords: list[str] | None
    ) -> None:
        """打印用户数据扫描报告"""
        print()
        print(c("═" * 60, CYAN))
        title = "  用户数据文件扫描报告  "
        print(c("║", CYAN) + c(title.center(54), CYAN) + c(" ║", CYAN))
        print(c("═" * 60, CYAN))
        print()

        print(f"  📁 总文件数: {result.total_files}")
        print(f"  💾 总大小: {result.total_size_mb:.2f} MB")
        if keywords:
            print(f"  🔍 过滤关键词: {', '.join(keywords)}")
        print()

        if not result.found_files:
            print(c("  ⚠ 未发现任何数据文件", YELLOW))
            print("  提示: 将 CSV/Excel 文件放入 data/ 的子目录中")
            print()
            return

        # By category
        for category, files in result.files_by_category.items():
            print(c(f"  📂 {category}/", CYAN))
            for f in files:
                size_kb = f.size_bytes / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
                print(f"    📄 {f.name} ({size_str}) [{f.file_type}]")
                if f.detected_columns:
                    n_cols = len(f.detected_columns)
                    sample = ", ".join(f.detected_columns[:5])
                    suffix = "..." if n_cols > 5 else ""
                    print(f"       列({n_cols}): {sample}{suffix}")
                if f.suggested_use:
                    print(f"       用途: {f.suggested_use}")
            print()

        # Recommendations
        if result.recommendations:
            print(c("  💡 文件使用建议:", GREEN))
            for rec in result.recommendations:
                print(rec)
            print()

        print(c("─" * 60, CYAN))
        print()

    # ── P3: 细粒度授权模式 ───────────────────────────────────────────────────

    def run_partial_auth(self) -> CheckResult:
        """
        P3: 细粒度授权模式。

        - 已有真实数据的变量 → 直接标记为可用
        - 缺失数据的变量 → 列出清单，等待用户逐个授权

        Returns:
            CheckResult with partial_auth_results populated.
        """
        if self._results is None:
            self.run()

        partial_results: dict[str, bool] = {}
        # Initialize all requirement variables as not authorized
        for req in self.requirements:
            partial_results[req.name] = False

        # For each requirement, check if it has available sources
        for req in self.requirements:
            has_available = False
            for src in req.sources:
                src_result = self._results.source_results.get(src)
                if src_result and src_result.status == "available":
                    has_available = True
                    break
            if has_available:
                partial_results[req.name] = True

        # Update CheckResult
        self._results.partial_auth_results = partial_results

        # Print partial auth report
        self._print_partial_auth_report()
        return self._results

    def _print_partial_auth_report(self) -> None:
        """打印细粒度授权报告"""
        if self._results is None:
            return

        print()
        print(c("═" * 60, CYAN))
        print(c("  细粒度授权报告", CYAN))
        print(c("═" * 60, CYAN))
        print()

        authorized = [
            name for name, ok in self._results.partial_auth_results.items() if ok
        ]
        unauthorized = [
            name for name, ok in self._results.partial_auth_results.items() if not ok
        ]

        if authorized:
            print(c(f"  ✅ 已授权 (真实数据可用): {len(authorized)}个", GREEN))
            for name in authorized:
                req = next((r for r in self.requirements if r.name == name), None)
                label = req.user_facing_name if req else name
                print(f"     • {label}")
            print()

        if unauthorized:
            print(c(f"  ⚠ 需授权模拟数据: {len(unauthorized)}个", YELLOW))
            for name in unauthorized:
                req = next((r for r in self.requirements if r.name == name), None)
                label = req.user_facing_name if req else name
                desc = req.description if req else ""
                print(f"     • {label}")
                if desc:
                    print(f"       用途: {desc}")
            print()
            print("  提示: 使用 checker.authorize_variable('{name}') 逐个授权")
            print()

        print(c("─" * 60, CYAN))
        print()

    def authorize_variable(self, var_name: str) -> bool:
        """
        授权指定变量使用模拟数据。

        Args:
            var_name: 变量名（对应 DataRequirement.name）。

        Returns:
            True if authorized, False if variable not found.
        """
        if self._results is None:
            self.run()

        if var_name not in self._results.partial_auth_results:
            print(c(f"⚠ 未知的变量名: {var_name}", RED))
            return False

        self._results.partial_auth_results[var_name] = True
        print(c(f"✅ 已授权模拟数据: {var_name}", GREEN))

        # Check if all are now authorized
        if all(self._results.partial_auth_results.values()):
            self._results.requires_synthetic_data = False
            print(c("  所有变量已授权，可以继续", GREEN))
        return True

    def get_missing_variables(self) -> list[str]:
        """
        返回仍缺少数据的变量列表。

        Returns:
            所有 partial_auth_results 中值为 False 的变量名列表。
        """
        if self._results is None:
            self.run()
        return [
            name for name, ok in self._results.partial_auth_results.items()
            if not ok
        ]


# ── 便捷函数 ────────────────────────────────────────────────────────────────

def check_and_confirm(requirements: list[DataRequirement]) -> CheckResult:
    """
    一行调用：检查数据源并返回结果
    调用方必须检查 result.requires_synthetic_data
    若为True，必须向用户展示 authorization_request_message 并等待授权
    """
    checker = DataSourceChecker(requirements)
    result = checker.run()
    checker.print_report()
    return result


# ── 关税研究专用预设 ──────────────────────────────────────────────────────

TARIFF_RESEARCH_REQUIREMENTS: list[DataRequirement] = [
    DataRequirement(
        name="financial_data",
        user_facing_name="A股财务数据",
        description="资产负债率（Lev）、ROA、规模（Size）等公司财务指标，用于构建资本结构调整速度模型",
        sources=["tushare", "wind", "csmar", "akshare"],
        required=True,
        min_quality="real",
    ),
    DataRequirement(
        name="customs_data",
        user_facing_name="上市公司海关进出口明细（HS编码）",
        description="上市公司出口美国产品明细（含HS8位码），用于计算企业关税暴露强度（Tariff_Exp）",
        sources=["csmar_customs"],
        required=True,
        min_quality="real",
    ),
    DataRequirement(
        name="tariff_list",
        user_facing_name="USTR 301关税清单",
        description="2018-2019年四批301关税清单（HS8位码+税率），用于匹配企业出口产品",
        sources=["web_scrape"],
        required=True,
        min_quality="real",
    ),
    DataRequirement(
        name="macro_data",
        user_facing_name="中国宏观数据（GDP/CPI/M2）",
        description="GDP增速、CPI、M2增速等，作为控制变量",
        sources=["user-financial", "akshare"],
        required=False,
        min_quality="real",
    ),
]
