"""
想法-数据交叉验证器 (Idea-Data Cross-Validator)
论文-研报工作流 · FinResearch Agent

【设计原则】
1. 想法生成时即检查数据可行性——不等到阶段5才发现无数据
2. 每个想法附带"数据可行性报告"，标注所需数据及获取路径
3. 数据不可行的想法要么被过滤，要么进入"待授权"状态
4. 用户在想法阶段即可决定：补充数据 / 授权模拟 / 更换主题

【工作流程】
  生成8-12个想法
       ↓
  每个想法 → 推断所需数据 → 检查数据可用性
       ↓
  ┌─ 数据可行 → 进入推荐名单
  ├─ 数据不可行 + 用户可补充 → 标记"需补充数据" → 引导用户配置
  └─ 数据不可行 + 无替代方案 → 标记"数据稀缺" → 用户决定：授权模拟 or 放弃

【用法】
    from scripts.idea_data_checker import IdeaDataValidator, IdeaDataRequirement

    # 定义候选想法
    ideas = [
        {
            "id": "idea_1",
            "title": "关税冲击与资本结构调整速度",
            "description": "利用DID分析2018年关税冲击对企业资本结构调整速度的影响",
            "keywords": ["tariff", "capital structure", "DID", "A-share"],
        },
        ...
    ]

    validator = IdeaDataValidator(ideas)
    result = validator.validate_all()

    for idea_result in result.idea_results:
        print(f"{idea_result.idea['title']}: {idea_result.feasibility.value}")
        if idea_result.feasibility == Feasibility.DATA_GAP:
            for action in idea_result.actions:
                print(f"  需补充: {action}")
"""

from __future__ import annotations

import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# Bootstrap sys.path so `python scripts/idea_data_checker.py` works
# without requiring `pip install -e .` first.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── ANSI Colors ────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ── 数据可行性枚举 ──────────────────────────────────────────────────────────

class Feasibility(str, Enum):
    AVAILABLE = "available"           # 真实数据可用
    PARTIALLY_AVAILABLE = "partial"  # 部分可用（某些变量缺失）
    DATA_GAP = "data_gap"            # 数据缺口（无可用来源）
    REQUIRES_AUTH = "auth_needed"    # 需要用户授权（模拟数据）


# ── 数据缺口原因 ──────────────────────────────────────────────────────────

class GapReason(str, Enum):
    REQUIRES_COMMERCIAL_DB = "requires_commercial_db"   # 需商业数据库
    REQUIRES_INSTITUTION = "requires_institution"       # 需机构账号
    REQUIRES_API_KEY = "requires_api_key"               # 需配置API Key
    DATA_NOT_DIGITIZED = "not_digitized"               # 数据未数字化
    NO_PUBLIC_SOURCE = "no_public_source"              # 无公开来源
    USER_AUTHORIZATION = "user_authorization"          # 需用户授权模拟


# ── 核心数据需求定义 ──────────────────────────────────────────────────────

@dataclass
class IdeaDataRequirement:
    """单个想法所需的数据需求"""
    data_type: str              # "financial_panel" | "customs_trade" | "macro_indicator" | ...
    description: str             # 对用户说明
    required_variables: list[str]  # 必须包含的变量
    time_frequency: str         # "daily" | "monthly" | "yearly"
    time_range: str             # "2010-2024" 等
    sample_scope: str           # "A股全样本" | "创业板" | "出口美国企业" 等
    data_sources_candidates: list[str]  # 可能的来源列表
    priority: int = 1          # 1=必须，2=重要但可替代，3=可选


@dataclass
class DataSourceAvailability:
    """某个数据需求的可用性检查结果"""
    data_type: str
    feasibility: Feasibility
    gap_reason: Optional[GapReason]
    available_sources: list[str]       # 可立即使用的数据源
    unavailable_sources: list[str]      # 不可用的数据源
    what_is_missing: str               # 缺失的具体内容
    how_to_get: str                   # 如何获取（用户可见）
    how_to_get_url: str               # 获取地址
    how_to_get_cost: str              # 成本/限制
    can_use_synthetic: bool           # 能否用模拟数据（作为最后手段）


@dataclass
class IdeaValidationResult:
    """单个想法的数据可行性验证结果"""
    idea: dict                       # 原始想法字典
    data_requirements: list[IdeaDataRequirement]  # 推断出的数据需求
    availability_results: list[DataSourceAvailability]  # 每个需求的可用性
    feasibility: Feasibility         # 综合可行性
    feasibility_score: float         # 0.0-1.0，1.0=完全可行
    gaps: list[str]                  # 所有数据缺口描述
    actions: list[str]               # 用户需要采取的行动
    recommendation: str              # 对用户的建议


@dataclass
class ValidationReport:
    """完整验证报告"""
    total_ideas: int
    available_count: int             # 数据可行的想法数
    partial_count: int              # 部分可行的想法数
    gap_count: int                  # 数据缺口的想泗数
    auth_needed_count: int          # 需要授权的想法数

    idea_results: list[IdeaValidationResult]

    # 汇总
    feasible_ideas: list[dict]       # 可立即推进的想法
    partial_ideas: list[dict]       # 部分可行的想法
    gap_ideas: list[dict]           # 有数据缺口的想泗

    # 批量操作建议
    batch_actions: list[str]         # 一次性获取数据的建议

    # 给用户的下一步选项
    user_options: list[str]


# ── 研究主题 → 数据需求的映射 ─────────────────────────────────────────────

# 关键词映射表：检测到特定关键词时，自动推断所需数据
_KEYWORD_TO_DATA_PATTERNS: list[dict] = [
    {
        # 关税/贸易相关
        "keywords": ["关税", "tariff", "中美贸", "301条款", "出口", "进口", "贸易战",
                     "customs", "trade", "export", "import", "HS code"],
        "data_types": ["financial_panel", "customs_trade", "tariff_exposure", "macro_indicator"],
        "financial_panel_needed": True,
        "critical_gap": "customs_trade",
        "gap_explanation": "上市公司进出口明细（HS8位码）用于计算企业关税暴露强度",
        "gap_sources": ["csmar_customs", "customs_bureau"],
        "gap_how_to_get": "CSMAR海关数据库（通过学校图书馆VPN）或向海关总署申请数据授权",
        "gap_how_to_url": "https://www.gtadata.com",
        "gap_how_to_cost": "需CSMAR机构账号（高校图书馆通常有VPN访问权限）",
        "can_synthetic": False,
        "feasibility_if_gap": Feasibility.DATA_GAP,
    },
    {
        # 资本结构相关
        "keywords": ["资本结构", "capital structure", "资产负债", "leverage", "融资",
                     "debt", "equity", "financing"],
        "data_types": ["financial_panel"],
        "financial_panel_needed": True,
        "critical_gap": None,
        "gap_explanation": "",
        "gap_sources": [],
        "gap_how_to_get": "",
        "gap_how_to_url": "",
        "gap_how_to_cost": "",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
    {
        # ESG/绿色金融相关
        "keywords": ["ESG", "绿色", "green", "碳排放", "carbon", "环境", "environmental",
                     "社会责任", "公司治理", "减排", "climate"],
        "data_types": ["financial_panel", "esg_rating", "carbon_emission", "macro_indicator"],
        "financial_panel_needed": True,
        "critical_gap": "esg_rating",
        "gap_explanation": "ESG评级数据（商道融绿、华证、中证等）",
        "gap_sources": ["wind_esg", "third_party_esg"],
        "gap_how_to_get": "Wind ESG数据库（学校可能有授权）或第三方ESG数据商",
        "gap_how_to_url": "https://www.wind.com.cn",
        "gap_how_to_cost": "Wind商业授权（学校图书馆可能有）",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
    {
        # 货币政策/宏观相关
        "keywords": ["货币", "monetary", "宏观", "macro", "GDP", "CPI", "M2", "利率",
                     "interest rate", "央行", "FOMC", "汇率", "exchange rate"],
        "data_types": ["macro_indicator"],
        "financial_panel_needed": False,
        "critical_gap": None,
        "gap_explanation": "",
        "gap_sources": [],
        "gap_how_to_get": "",
        "gap_how_to_url": "",
        "gap_how_to_cost": "",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.AVAILABLE,  # 宏观数据通常免费
    },
    {
        # 专利/创新相关
        "keywords": ["专利", "patent", "创新", "innovation", "研发", "R&D",
                     "全要素生产率", "TFP", "技术进步"],
        "data_types": ["financial_panel", "patent_data"],
        "financial_panel_needed": True,
        "critical_gap": "patent_data",
        "gap_explanation": "企业专利申请/授权数据（CNRDS或国家知识产权局）",
        "gap_sources": ["cnrds", "sipo"],
        "gap_how_to_get": "CNRDS数据库（学校可能有）或国家知识产权局公开数据",
        "gap_how_to_url": "https://www.cnrds.com",
        "gap_how_to_cost": "CNRDS机构账号",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
    {
        # 融资融券/市场情绪相关
        "keywords": ["融资融券", "margin", "卖空", "short selling", "市场情绪", "market sentiment",
                     "投资者", "散户", "institutional investor"],
        "data_types": ["financial_panel", "margin_data", "market_data"],
        "financial_panel_needed": True,
        "critical_gap": "margin_data",
        "gap_explanation": "融资融券余额数据",
        "gap_sources": ["tushare_margin"],
        "gap_how_to_get": "Tushare Pro（需注册积分）或Wind",
        "gap_how_to_url": "https://tushare.pro",
        "gap_how_to_cost": "Tushare注册有免费积分额度",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
    {
        # 公司治理/高管相关
        "keywords": ["公司治理", "corporate governance", "高管", "executive", "薪酬",
                     "股权激励", "stock option", "董事会", "board"],
        "data_types": ["financial_panel", "governance_data"],
        "financial_panel_needed": True,
        "critical_gap": "governance_data",
        "gap_explanation": "公司治理数据（董事会结构、高管薪酬、股权结构等）",
        "gap_sources": ["csmar_governance", "wind"],
        "gap_how_to_get": "CSMAR或Wind数据库",
        "gap_how_to_url": "https://www.gtadata.com",
        "gap_how_to_cost": "需机构账号",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
    {
        # 因子/资产定价相关
        "keywords": ["因子", "factor", "定价", "pricing", "收益", "return", "异常",
                     "anomaly", "动量", "momentum", "价值", "value"],
        "data_types": ["market_data", "financial_panel", "factor_data"],
        "financial_panel_needed": False,  # 可只做股票收益率
        "critical_gap": None,
        "gap_explanation": "",
        "gap_sources": [],
        "gap_how_to_get": "",
        "gap_how_to_url": "",
        "gap_how_to_cost": "",
        "can_synthetic": True,
        "feasibility_if_gap": Feasibility.PARTIALLY_AVAILABLE,
    },
]


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _read_env(path: Path) -> dict[str, str]:
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


def _probe_url(url: str, timeout: int = 6) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FinResearch-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"连接失败"
    except Exception as e:
        return False, str(e)[:60]


def _match_keywords(idea_keywords: list[str], pattern_keywords: list[str]) -> int:
    """返回匹配的关键词数量"""
    idea_text = " ".join(k.lower() for k in idea_keywords)
    score = 0
    for kw in pattern_keywords:
        if kw.lower() in idea_text:
            score += 1
    return score


# ── 核心验证器 ──────────────────────────────────────────────────────────────

class IdeaDataValidator:
    """
    想法-数据交叉验证器

    【核心流程】
    1. 对每个想法，扫描关键词，匹配数据需求模式
    2. 对每个推断出的数据需求，检查真实可用性
    3. 汇总每个想法的综合可行性
    4. 生成报告，列出可行想法、缺口想法及对应行动

    【关键原则】
    - 数据缺口的想法不进"推荐名单"（除非用户明确授权模拟）
    - 每个缺口想法必须附带"如何获取"的明确路径
    - 用户在想法阶段即可决定下一步（补充数据/授权模拟/更换）
    """

    def __init__(self, ideas: list[dict]):
        """
        Args:
            ideas: 想法字典列表，每个字典应包含：
                   - title: 想法标题
                   - description: 想法描述
                   - keywords: 关键词列表（自动从标题/描述提取）
                   - 其他任意字段
        """
        self.ideas = ideas
        self._env: Optional[dict[str, str]] = None

    @property
    def env(self) -> dict[str, str]:
        if self._env is None:
            root = Path(__file__).parent.parent
            self._env = {**_read_env(root / ".env"), **_read_env(root / ".env.local")}
        return self._env

    def _match_pattern(self, idea: dict) -> list[dict]:
        """将想法的关键词与已知模式匹配"""
        keywords = idea.get("keywords", [])
        # 自动从标题和描述提取更多关键词
        extra = re.findall(r"[\w]{3,}", idea.get("title", "") + " " + idea.get("description", ""))
        all_keywords = keywords + extra

        matched = []
        for pattern in _KEYWORD_TO_DATA_PATTERNS:
            score = _match_keywords(all_keywords, pattern["keywords"])
            if score > 0:
                matched.append((score, pattern))
        # 按匹配分数排序
        matched.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in matched]

    def _check_data_availability(self, pattern: dict) -> DataSourceAvailability:
        """检查某个数据需求模式的真实可用性"""
        data_type = pattern["data_types"][0] if pattern["data_types"] else "unknown"
        gap_sources = pattern.get("gap_sources", [])
        gap_reason: Optional[GapReason] = None

        available_srcs: list[str] = []
        unavailable_srcs: list[str] = []

        # 检查商业数据库
        for src in gap_sources:
            if src == "csmar_customs":
                csmar_key = self.env.get("CSMAR_API_KEY", "").strip()
                if csmar_key:
                    # 有key≠有数据权限
                    unavailable_srcs.append(f"{src} (API Key已配置但需机构数据权限)")
                    gap_reason = GapReason.REQUIRES_INSTITUTION
                else:
                    unavailable_srcs.append(f"{src} (需CSMAR机构账号)")
                    gap_reason = GapReason.REQUIRES_INSTITUTION
            elif src == "tushare":
                tushare_key = self.env.get("TUSHARE_TOKEN", "").strip()
                if tushare_key:
                    ok, msg = _probe_url("https://api.tushare.pro", timeout=6)
                    if ok:
                        available_srcs.append(f"{src} (API可用)")
                    else:
                        unavailable_srcs.append(f"{src} (API Key已配置但网络不通)")
                        gap_reason = GapReason.REQUIRES_API_KEY
                else:
                    unavailable_srcs.append(f"{src} (需注册Tushare Pro获取Token)")
                    gap_reason = GapReason.REQUIRES_API_KEY
            elif src == "tushare_margin":
                tushare_key = self.env.get("TUSHARE_TOKEN", "").strip()
                if tushare_key:
                    available_srcs.append(f"{src} (通过Tushare)")
                else:
                    unavailable_srcs.append(f"{src} (需Tushare Pro Token)")
                    gap_reason = GapReason.REQUIRES_API_KEY
            elif src in ("wind", "csmar", "csmar_governance", "cnrds"):
                unavailable_srcs.append(f"{src} (需商业数据库授权)")
                gap_reason = GapReason.REQUIRES_COMMERCIAL_DB
            else:
                unavailable_srcs.append(f"{src} (需手动获取)")

        # 通用免费数据源检查
        if pattern.get("financial_panel_needed"):
            tushare_key = self.env.get("TUSHARE_TOKEN", "").strip()
            if tushare_key:
                available_srcs.append("tushare (财务数据)")
            # akshare 是免费备选
            available_srcs.append("akshare (免费备选)")

        if "macro_indicator" in pattern["data_types"]:
            # 宏观数据免费
            available_srcs.append("MCP user-financial (World Bank + akshare, 免费)")

        # 决定可行性
        has_critical_gap = bool(pattern.get("critical_gap"))
        can_use_synthetic = pattern.get("can_synthetic", True)
        feasibility = Feasibility.DATA_GAP

        if has_critical_gap:
            if gap_reason in (GapReason.REQUIRES_INSTITUTION, GapReason.REQUIRES_COMMERCIAL_DB):
                if available_srcs:
                    feasibility = Feasibility.PARTIALLY_AVAILABLE
                else:
                    feasibility = Feasibility.DATA_GAP
            elif gap_reason == GapReason.REQUIRES_API_KEY:
                if available_srcs:
                    feasibility = Feasibility.AVAILABLE
                else:
                    feasibility = Feasibility.DATA_GAP
        elif available_srcs:
            feasibility = Feasibility.AVAILABLE
        elif can_use_synthetic:
            feasibility = Feasibility.REQUIRES_AUTH
        else:
            feasibility = Feasibility.DATA_GAP

        return DataSourceAvailability(
            data_type=data_type,
            feasibility=feasibility,
            gap_reason=gap_reason,
            available_sources=available_srcs,
            unavailable_sources=unavailable_srcs,
            what_is_missing=pattern.get("gap_explanation", ""),
            how_to_get=pattern.get("gap_how_to_get", ""),
            how_to_get_url=pattern.get("gap_how_to_url", ""),
            how_to_get_cost=pattern.get("gap_how_to_cost", ""),
            can_use_synthetic=can_use_synthetic,
        )

    def _infer_data_requirements(self, idea: dict, patterns: list[dict]) -> list[IdeaDataRequirement]:
        """从匹配的模式推断想法所需的数据"""
        requirements: list[IdeaDataRequirement] = []

        for pattern in patterns:
            req = IdeaDataRequirement(
                data_type=pattern["data_types"][0] if pattern["data_types"] else "unknown",
                description=f"基于关键词推断的数据需求",
                required_variables=self._variables_for_type(pattern["data_types"][0] if pattern["data_types"] else "unknown"),
                time_frequency="yearly",
                time_range="2010-2023",
                sample_scope="A股上市公司",
                data_sources_candidates=pattern.get("gap_sources", []),
                priority=1 if pattern.get("critical_gap") else 2,
            )
            requirements.append(req)

        return requirements

    def _variables_for_type(self, data_type: str) -> list[str]:
        """返回特定数据类型需要的变量"""
        var_map = {
            "financial_panel": ["资产负债率", "ROA", "ROE", "规模", "年龄", "所有制"],
            "customs_trade": ["出口额", "HS编码", "目的地", "产品类别"],
            "tariff_exposure": ["关税税率", "HS8位码", "暴露强度"],
            "macro_indicator": ["GDP增速", "CPI", "M2", "利率"],
            "esg_rating": ["ESG综合得分", "E分数", "S分数", "G分数"],
            "patent_data": ["专利申请数", "专利授权数", "研发投入"],
            "margin_data": ["融资余额", "融券余额", "融资买入额"],
            "governance_data": ["董事会规模", "独立董事比例", "高管薪酬"],
            "market_data": ["日收益率", "换手率", "市值", "账面市值比"],
            "factor_data": ["动量因子", "价值因子", "规模因子", "盈利因子"],
        }
        return var_map.get(data_type, ["基础财务指标"])

    def validate_all(self) -> ValidationReport:
        """对所有想法执行数据可行性验证"""
        all_results: list[IdeaValidationResult] = []

        for idea in self.ideas:
            # 匹配数据需求模式
            patterns = self._match_pattern(idea)

            if not patterns:
                # 没有匹配到任何已知模式，假设需要财务面板数据
                patterns = [_KEYWORD_TO_DATA_PATTERNS[1]]  # 默认用资本结构模式

            # 检查每个模式的可用性
            availabilities: list[DataSourceAvailability] = []
            for pattern in patterns:
                avail = self._check_data_availability(pattern)
                availabilities.append(avail)

            # 综合判断可行性
            worst_feasibility = Feasibility.AVAILABLE
            feasibility_score = 1.0
            gaps: list[str] = []
            actions: list[str] = []

            for avail in availabilities:
                if avail.feasibility == Feasibility.DATA_GAP:
                    worst_feasibility = Feasibility.DATA_GAP
                    feasibility_score = min(feasibility_score, 0.0)
                    if avail.what_is_missing:
                        gaps.append(avail.what_is_missing)
                    if avail.how_to_get:
                        actions.append(f"获取{avail.data_type}: {avail.how_to_get} ({avail.how_to_get_cost})")
                    if avail.how_to_get_url:
                        actions.append(f"  网址: {avail.how_to_get_url}")
                elif avail.feasibility == Feasibility.REQUIRES_AUTH:
                    if worst_feasibility != Feasibility.DATA_GAP:
                        worst_feasibility = Feasibility.REQUIRES_AUTH
                    feasibility_score = min(feasibility_score, 0.3)
                    gaps.append(f"需要授权使用模拟{avail.data_type}数据")
                    actions.append(f"授权模拟数据: {avail.how_to_get or '联系导师/获取商业数据'}")
                elif avail.feasibility == Feasibility.PARTIALLY_AVAILABLE:
                    if worst_feasibility == Feasibility.AVAILABLE:
                        worst_feasibility = Feasibility.PARTIALLY_AVAILABLE
                    feasibility_score = min(feasibility_score, 0.6)
                    gaps.append(f"部分数据可用: {', '.join(avail.available_sources)}")
                    if avail.unavailable_sources:
                        gaps.append(f"缺失: {', '.join(avail.unavailable_sources)}")
                        actions.append(f"补充{avail.data_type}: {avail.how_to_get} ({avail.how_to_get_cost})")

            # 生成建议
            if worst_feasibility == Feasibility.AVAILABLE:
                recommendation = "✅ 数据可行，可立即推进"
            elif worst_feasibility == Feasibility.PARTIALLY_AVAILABLE:
                recommendation = "⚠️ 部分数据缺失，可推进但需补充"
            elif worst_feasibility == Feasibility.DATA_GAP:
                recommendation = "❌ 数据缺口严重，建议补充数据后再推进"
            else:
                recommendation = "🔐 需要用户授权使用模拟数据"

            result = IdeaValidationResult(
                idea=idea,
                data_requirements=self._infer_data_requirements(idea, patterns),
                availability_results=availabilities,
                feasibility=worst_feasibility,
                feasibility_score=feasibility_score,
                gaps=gaps,
                actions=actions,
                recommendation=recommendation,
            )
            all_results.append(result)

        # 分类
        feasible = [r for r in all_results if r.feasibility == Feasibility.AVAILABLE]
        partial = [r for r in all_results if r.feasibility == Feasibility.PARTIALLY_AVAILABLE]
        gaps = [r for r in all_results if r.feasibility == Feasibility.DATA_GAP]
        auth_needed = [r for r in all_results if r.feasibility == Feasibility.REQUIRES_AUTH]

        # 批量操作建议
        batch_actions: list[str] = []
        all_gap_types: set[str] = set()
        for r in all_results:
            for avail in r.availability_results:
                if avail.feasibility in (Feasibility.DATA_GAP, Feasibility.REQUIRES_AUTH):
                    if avail.data_type and avail.how_to_get:
                        all_gap_types.add(avail.data_type)

        if all_gap_types:
            batch_actions.append(f"优先解决以下数据缺口: {', '.join(all_gap_types)}")

        # 用户选项
        user_options = []
        if gaps or auth_needed:
            user_options.extend([
                "(1) 补充数据——获取API Key或联系学校图书馆",
                "(2) 授权模拟——仅用演示流程，结果不能发表",
                "(3) 更换主题——选择数据更易获取的研究方向",
            ])
        else:
            user_options = [
                "(1) 选择可行想法继续推进",
                "(2) 对部分可行想法补充数据后再推进",
            ]

        return ValidationReport(
            total_ideas=len(all_results),
            available_count=len(feasible),
            partial_count=len(partial),
            gap_count=len(gaps),
            auth_needed_count=len(auth_needed),
            idea_results=all_results,
            feasible_ideas=feasible,
            partial_ideas=partial,
            gap_ideas=gaps,
            batch_actions=batch_actions,
            user_options=user_options,
        )

    def print_report(self, report: ValidationReport) -> None:
        """打印完整验证报告给用户"""
        print()
        print(c("═" * 70, CYAN))
        title = "  想法-数据可行性验证报告  "
        print(c("║", CYAN) + c(title.center(64), CYAN) + c(" ║", CYAN))
        print(c("═" * 70, CYAN))
        print()

        # 汇总统计
        print(f"  {c('验证结果统计:', BOLD)}")
        print(f"    ✅ 数据可行:       {report.available_count} 个想法")
        print(f"    ⚠️  部分可行:     {report.partial_count} 个想法")
        print(f"    ❌ 数据缺口:      {report.gap_count} 个想法")
        print(f"    🔐 需授权模拟:    {report.auth_needed_count} 个想法")
        print()

        # 按可行性分组展示
        # 1. 可行想法
        if report.feasible_ideas:
            print(c(f"  ━━ ✅ 数据可行的想法 ({len(report.feasible_ideas)}个) ━━", GREEN))
            for i, r in enumerate(report.feasible_ideas, 1):
                idea = r.idea
                print(f"  {i}. {c(idea.get('title', '未命名'), BOLD)}")
                print(f"     评分: {r.feasibility_score:.1f}/1.0 | {r.recommendation}")
                if r.availability_results:
                    avail_srcs = []
                    for a in r.availability_results:
                        avail_srcs.extend(a.available_sources)
                    if avail_srcs:
                        print(f"     数据: {', '.join(avail_srcs[:3])}")
                print()

        # 2. 部分可行想法
        if report.partial_ideas:
            print(c(f"  ━━ ⚠️  部分可行的想法 ({len(report.partial_ideas)}个) ━━", YELLOW))
            for i, r in enumerate(report.partial_ideas, 1):
                idea = r.idea
                print(f"  {i}. {c(idea.get('title', '未命名'), BOLD)}")
                print(f"     评分: {r.feasibility_score:.1f}/1.0 | {r.recommendation}")
                for gap in r.gaps:
                    print(f"     ⚡ {gap}")
                print()

        # 3. 数据缺口想法
        if report.gap_ideas:
            print(c(f"  ━━ ❌ 数据缺口的想法 ({len(report.gap_ideas)}个) ━━", RED))
            print(f"  {c('这些想法当前无法推进，需要先补充数据。', YELLOW)}")
            print()
            for i, r in enumerate(report.gap_ideas, 1):
                idea = r.idea
                print(f"  {i}. {c(idea.get('title', '未命名'), BOLD)}")
                print(f"     评分: {r.feasibility_score:.1f}/1.0")
                for avail in r.availability_results:
                    if avail.what_is_missing:
                        print(f"     缺失数据: {avail.what_is_missing}")
                    if avail.how_to_get:
                        print(f"     获取途径: {avail.how_to_get}")
                    if avail.how_to_get_cost:
                        print(f"     成本/限制: {avail.how_to_get_cost}")
                    if avail.how_to_get_url:
                        print(f"     网址: {avail.how_to_get_url}")
                print()

        print(c("─" * 70, CYAN))

        # 批量操作建议
        if report.batch_actions:
            print(f"  {c('批量数据行动建议:', BOLD)}")
            for action in report.batch_actions:
                print(f"    • {action}")
            print()

        # 用户选项
        print(f"  {c('下一步（请选择）:', BOLD)}")
        for opt in report.user_options:
            print(f"    {opt}")
        print()

        print(c("═" * 70, CYAN))
        print()

    def validate_single(self, idea: dict) -> IdeaValidationResult:
        """验证单个想法的数据可行性"""
        patterns = self._match_pattern(idea)
        if not patterns:
            patterns = [_KEYWORD_TO_DATA_PATTERNS[1]]

        availabilities = [self._check_data_availability(p) for p in patterns]
        requirements = self._infer_data_requirements(idea, patterns)

        # 综合判断
        worst = Feasibility.AVAILABLE
        score = 1.0
        gaps: list[str] = []
        actions: list[str] = []

        for avail in availabilities:
            if avail.feasibility == Feasibility.DATA_GAP:
                worst = Feasibility.DATA_GAP
                score = 0.0
                if avail.what_is_missing:
                    gaps.append(avail.what_is_missing)
                if avail.how_to_get:
                    actions.append(f"获取{avail.data_type}: {avail.how_to_get}")
            elif avail.feasibility == Feasibility.REQUIRES_AUTH:
                if worst == Feasibility.AVAILABLE:
                    worst = Feasibility.REQUIRES_AUTH
                score = min(score, 0.3)
            elif avail.feasibility == Feasibility.PARTIALLY_AVAILABLE:
                if worst == Feasibility.AVAILABLE:
                    worst = Feasibility.PARTIALLY_AVAILABLE
                score = min(score, 0.6)
                gaps.append(f"部分数据缺失: {', '.join(avail.unavailable_sources)}")

        rec = {
            Feasibility.AVAILABLE: "✅ 数据可行，可立即推进",
            Feasibility.PARTIALLY_AVAILABLE: "⚠️ 部分数据缺失，可推进但需补充",
            Feasibility.DATA_GAP: "❌ 数据缺口严重，建议补充数据",
            Feasibility.REQUIRES_AUTH: "🔐 需要用户授权使用模拟数据",
        }[worst]

        return IdeaValidationResult(
            idea=idea,
            data_requirements=requirements,
            availability_results=availabilities,
            feasibility=worst,
            feasibility_score=score,
            gaps=gaps,
            actions=actions,
            recommendation=rec,
        )


def quick_check(ideas: list[dict]) -> ValidationReport:
    """
    一行调用：对所有想法进行数据可行性验证并打印报告。
    用于想法生成后立即检查，而非等待阶段5。
    """
    validator = IdeaDataValidator(ideas)
    report = validator.validate_all()
    validator.print_report(report)
    return report


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="idea_data_checker.py",
        description="想法-数据交叉验证：检查研究想法所需数据的可用性。",
    )
    parser.add_argument(
        "--ideas-file", "-f",
        required=True,
        help="想法文件路径（JSON 或 YAML），或包含 YAML/JSON 想法列表的文件",
    )
    parser.add_argument(
        "--format", "-F",
        default="auto",
        choices=["auto", "json", "yaml"],
        help="文件格式（默认: auto — 根据扩展名自动推断）",
    )
    parser.add_argument(
        "--output", "-o",
        help="将报告写入指定文件（JSON 格式）",
    )
    parser.add_argument(
        "--summary-only", "-s",
        action="store_true",
        help="仅显示汇总，不打印详细分析",
    )
    args = parser.parse_args()

    # 读取想法文件
    path = Path(args.ideas_file)
    if not path.exists():
        print(f"Error: 文件不存在: {args.ideas_file}", file=sys.stderr)
        sys.exit(1)

    raw = path.read_text(encoding="utf-8")
    ideas: list[dict]

    if args.format == "json" or (args.format == "auto" and path.suffix in (".json",)):
        data = json.loads(raw)
        if isinstance(data, dict) and "ideas" in data:
            ideas = data["ideas"]
        elif isinstance(data, list):
            ideas = data
        else:
            print("Error: JSON 文件必须包含 'ideas' 数组或顶级数组", file=sys.stderr)
            sys.exit(1)
    else:
        import yaml
        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            ideas = data.get("ideas", [data])
        elif isinstance(data, list):
            ideas = data
        else:
            print("Error: 无法解析文件内容", file=sys.stderr)
            sys.exit(1)

    if not ideas:
        print("Error: 想法列表为空", file=sys.stderr)
        sys.exit(1)

    # 运行验证
    validator = IdeaDataValidator(ideas)
    report = validator.validate_all()

    if not args.summary_only:
        validator.print_report(report)

    # 输出汇总
    print()
    total = len(report.idea_results)
    feasible = sum(1 for r in report.idea_results if r.feasibility == Feasibility.AVAILABLE)
    partial = sum(1 for r in report.idea_results if r.feasibility == Feasibility.PARTIALLY_AVAILABLE)
    gap = sum(1 for r in report.idea_results if r.feasibility == Feasibility.DATA_GAP)
    auth = sum(1 for r in report.idea_results if r.feasibility == Feasibility.REQUIRES_AUTH)

    print(f"汇总: {total} 个想法 | ✅可行={feasible} ⚠️部分={partial} ❌缺口={gap} 🔐需授权={auth}")

    # 写入输出文件
    if args.output:
        out = {
            "summary": {
                "total": total, "feasible": feasible,
                "partial": partial, "gap": gap, "requires_auth": auth,
            },
            "timestamp": datetime.now().isoformat(),
            "file": str(path),
        }
        Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"报告已写入: {args.output}")

    # 退出码：0=全部可行, 1=部分/需授权, 2=全部不可行
    sys.exit(0 if gap == 0 else (1 if feasible + partial > 0 else 2))

