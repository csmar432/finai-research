#!/usr/bin/env python3
"""
论文-研报工作流 · 首次运行配置向导

功能：
1. 检测当前配置状态（.env / .env.local）
2. 交互式询问研究方向
3. 根据方向推荐相关 API Keys / MCP Servers
4. 引导用户选择性配置
5. 保存到 .env.local
6. 生成状态报告

用法：
    python scripts/setup_wizard.py --guided      # 引导模式
    python scripts/setup_wizard.py --status      # 状态检查
    python scripts/setup_wizard.py --direction a_share  # 快速配置
    python scripts/setup_wizard.py --validate     # 验证配置
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# =============================================================================
# ANSI Color Codes
# =============================================================================

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def red(text: str) -> str:
    return colorize(text, RED)


def green(text: str) -> str:
    return colorize(text, GREEN)


def yellow(text: str) -> str:
    return colorize(text, YELLOW)


def blue(text: str) -> str:
    return colorize(text, BLUE)


def cyan(text: str) -> str:
    return colorize(text, CYAN)


def dim(text: str) -> str:
    return colorize(text, DIM)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ConfigStatus:
    """单个配置项的当前状态"""
    var_name: str
    is_set: bool
    is_sensitive: bool
    current_value: Optional[str]  # 脱敏显示
    priority: str  # "must" | "should" | "nice"
    description: str
    for_directions: list[str]
    placeholder: str = ""


@dataclass
class DirectionConfig:
    """研究方向推荐配置"""
    direction: str
    label: str
    description: str
    required: list[str]
    recommended: list[str]
    nice: list[str]
    mcp_servers: list[str]


@dataclass
class MCPStatus:
    """MCP 服务器状态"""
    server_id: str
    name: str
    installed: bool
    enabled: bool
    needs_api_key: bool
    api_key_var: str
    description: str
    for_directions: list[str]
    needs_optional_dep: str = ""  # e.g. "sandbox" 或 "browser"，空=无额外依赖


# =============================================================================
# 配置项定义
# =============================================================================

ALL_CONFIGS: list[ConfigStatus] = [
    ConfigStatus(
        var_name="DEEPSEEK_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="must",
        description="DeepSeek API Key（中文LLM，核心必需）",
        for_directions=["a_share", "macro", "empirical_paper", "quantitative", "financial_report"],
        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="RELAY_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="should",
        description="B.AI 中转 API Key（GPT/Claude 英文模型）",
        for_directions=["empirical_paper", "financial_report", "a_share"],
        placeholder="ba-xxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="TUSHARE_TOKEN",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="should",
        description="Tushare Pro API Key（A股行情/财务数据）",
        for_directions=["a_share", "quantitative", "empirical_paper", "financial_report"],
        placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="EODHD_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="nice",
        description="EODHD API Key（全球宏观/国债收益率/经济日历）",
        for_directions=["macro", "quantitative", "empirical_paper"],
        placeholder="xxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="BRAVE_SEARCH_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="should",
        description="Brave Search API Key（网络搜索文献/新闻）",
        for_directions=["macro", "empirical_paper", "financial_report"],
        placeholder="BSAxxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="FRED_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="nice",
        description="FRED API Key（美联储经济数据）",
        for_directions=["macro", "quantitative"],
        placeholder="xxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="ZHIPU_API_KEY",
        is_set=False,
        is_sensitive=True,
        current_value=None,
        priority="nice",
        description="智谱 GLM API Key（结构化输出）",
        for_directions=["a_share", "macro", "empirical_paper", "quantitative", "financial_report"],
        placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ),
    ConfigStatus(
        var_name="OLLAMA_ENABLED",
        is_set=False,
        is_sensitive=False,
        current_value="false",
        priority="nice",
        description="Ollama 本地模型（离线兜底）",
        for_directions=["empirical_paper", "quantitative"],
        placeholder="true / false"
    ),
]

# =============================================================================
# 研究方向定义
# =============================================================================

DIRECTION_REQUIREMENTS: dict[str, DirectionConfig] = {
    "a_share": DirectionConfig(
        direction="a_share",
        label="A股研究（上市公司分析）",
        description="需要 Tushare Pro 账号获取 A 股行情、财务、融资融券数据",
        required=["DEEPSEEK_API_KEY"],
        recommended=["TUSHARE_TOKEN", "RELAY_API_KEY"],
        nice=["BRAVE_SEARCH_API_KEY", "OLLAMA_ENABLED"],
        mcp_servers=["user-tushare", "user-eastmoney-reports", "user-eastmoney-fund", "user-eastmoney-bond", "user-enhanced-finance"]
    ),
    "macro": DirectionConfig(
        direction="macro",
        label="宏观经济研究",
        description="需要 Tushare 宏观数据 + 东方财富研报 + 全球宏观数据库",
        required=["DEEPSEEK_API_KEY"],
        recommended=["BRAVE_SEARCH_API_KEY", "EODHD_API_KEY"],
        nice=["FRED_API_KEY", "RELAY_API_KEY"],
        mcp_servers=["user-wb-data", "user-imf-data", "user-oecd-data", "user-fed-data", "user-financial", "user-enhanced-finance"]
    ),
    "empirical_paper": DirectionConfig(
        direction="empirical_paper",
        label="实证学术论文",
        description="需要 A 股数据做实证分析 + 网络搜索找文献",
        required=["DEEPSEEK_API_KEY"],
        recommended=["TUSHARE_TOKEN", "BRAVE_SEARCH_API_KEY"],
        nice=["RELAY_API_KEY", "OLLAMA_ENABLED"],
        mcp_servers=["user-tushare", "user-wb-data", "user-financial", "user-bea-data", "user-eastmoney-reports"]
    ),
    "quantitative": DirectionConfig(
        direction="quantitative",
        label="量化投资研究",
        description="需要 Tushare 高频行情 + EODHD 全球市场数据",
        required=["DEEPSEEK_API_KEY", "TUSHARE_TOKEN"],
        recommended=["EODHD_API_KEY"],
        nice=["OLLAMA_ENABLED"],
        mcp_servers=["user-tushare", "user-eodhd", "user-enhanced-finance", "user-e2b-mcp"]
    ),
    "financial_report": DirectionConfig(
        direction="financial_report",
        label="金融研究报告撰写",
        description="完整研报流程：数据获取 + 深度分析 + 研报撰写",
        required=["DEEPSEEK_API_KEY"],
        recommended=["RELAY_API_KEY", "TUSHARE_TOKEN", "BRAVE_SEARCH_API_KEY"],
        nice=[],
        mcp_servers=["user-tushare", "user-eastmoney-reports", "user-financial", "user-wb-data"]
    ),
}

# =============================================================================
# MCP 服务器定义
# =============================================================================

MCP_SERVERS: dict[str, MCPStatus] = {
    "user-tushare": MCPStatus(
        server_id="user-tushare",
        name="Tushare A股数据",
        installed=True,
        enabled=False,
        needs_api_key=True,
        api_key_var="TUSHARE_TOKEN",
        description="A股行情、财务、融资融券、指数数据",
        for_directions=["a_share", "quantitative", "empirical_paper", "financial_report"]
    ),
    "user-eastmoney-reports": MCPStatus(
        server_id="user-eastmoney-reports",
        name="东方财富研报",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="研报、新闻、概念板块、分析师排名",
        for_directions=["a_share", "empirical_paper", "financial_report"]
    ),
    "user-eastmoney-fund": MCPStatus(
        server_id="user-eastmoney-fund",
        name="东方财富基金数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="基金净值、持仓、资金流向",
        for_directions=["a_share", "financial_report"]
    ),
    "user-eastmoney-bond": MCPStatus(
        server_id="user-eastmoney-bond",
        name="东方财富债券数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="债券行情、收益率曲线",
        for_directions=["a_share", "macro"]
    ),
    "user-eastmoney-option": MCPStatus(
        server_id="user-eastmoney-option",
        name="东方财富期权数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="期权链、Greeks、波动率曲面",
        for_directions=["quantitative"]
    ),
    "user-wb-data": MCPStatus(
        server_id="user-wb-data",
        name="世界银行数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="全球GDP、人口、贸易、债务指标",
        for_directions=["macro", "empirical_paper"]
    ),
    "user-imf-data": MCPStatus(
        server_id="user-imf-data",
        name="IMF数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="IMF世界经济展望、国际收支",
        for_directions=["macro"]
    ),
    "user-oecd-data": MCPStatus(
        server_id="user-oecd-data",
        name="OECD数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="OECD成员国经济指标",
        for_directions=["macro"]
    ),
    "user-fed-data": MCPStatus(
        server_id="user-fed-data",
        name="美联储数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="FOMC会议纪要、褐皮书、收益率曲线",
        for_directions=["macro"]
    ),
    "user-financial": MCPStatus(
        server_id="user-financial",
        name="全球宏观数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="中国/日本/英国/欧元区宏观指标",
        for_directions=["macro", "empirical_paper", "financial_report"]
    ),
    "user-enhanced-finance": MCPStatus(
        server_id="user-enhanced-finance",
        name="增强金融数据",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="外汇、大宗商品、航运指数",
        for_directions=["macro", "a_share", "quantitative"]
    ),
    "user-eodhd": MCPStatus(
        server_id="user-eodhd",
        name="EODHD全球市场",
        installed=True,
        enabled=False,
        needs_api_key=True,
        api_key_var="EODHD_API_KEY",
        description="国债收益率、经济日历、美股数据",
        for_directions=["macro", "quantitative"]
    ),
    "user-e2b-mcp": MCPStatus(
        server_id="user-e2b-mcp",
        name="E2B代码执行",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="云端Python代码执行与沙箱",
        for_directions=["quantitative"],
        needs_optional_dep="sandbox",
    ),
    "user-bea-data": MCPStatus(
        server_id="user-bea-data",
        name="美国经济分析局",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="美国GDP、NIPA、行业数据",
        for_directions=["macro", "empirical_paper"]
    ),
    "user-csmar": MCPStatus(
        server_id="user-csmar",
        name="CSMAR金融数据库",
        installed=True,
        enabled=False,
        needs_api_key=True,
        api_key_var="CSMAR_API_KEY",
        description="中国金融市场与会计研究数据库",
        for_directions=["empirical_paper"]
    ),
    "user-latex-mcp": MCPStatus(
        server_id="user-latex-mcp",
        name="LaTeX排版工具",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="LaTeX编译、公式渲染、参考文献检查",
        for_directions=["empirical_paper", "financial_report"]
    ),
    "user-playwright-mcp": MCPStatus(
        server_id="user-playwright-mcp",
        name="浏览器自动化",
        installed=True,
        enabled=False,
        needs_api_key=False,
        api_key_var="",
        description="网页抓取、表单交互、动态内容渲染",
        for_directions=["empirical_paper"],
        needs_optional_dep="browser",
    ),
}


# =============================================================================
# Utility Functions
# =============================================================================

def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.resolve()


def get_env_file() -> Path:
    """获取 .env 文件路径"""
    return get_project_root() / ".env"


def get_env_local_file() -> Path:
    """获取 .env.local 文件路径"""
    return get_project_root() / ".env.local"


def mask_sensitive(value: str) -> str:
    """脱敏显示敏感值"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def read_env_file(path: Path) -> dict[str, str]:
    """读取 .env 文件，返回键值对字典"""
    env_vars = {}
    if not path.exists():
        return env_vars

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def write_env_file(path: Path, env_vars: dict[str, str], comments: dict[str, str] = None) -> None:
    """写入 .env 文件"""
    lines = []
    comments = comments or {}

    # 写入文件头
    lines.append("# =============================================================================")
    lines.append(f"# 论文-研报工作流 · 环境变量配置")
    lines.append(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("# =============================================================================")
    lines.append("")

    # 按类别分组
    categories = {
        "AI模型API Keys": ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "RELAY_API_KEY", "RELAY_BASE_URL", "ZHIPU_API_KEY"],
        "金融数据API Keys": ["TUSHARE_TOKEN", "EODHD_API_KEY", "FRED_API_KEY"],
        "可选API Keys": ["BRAVE_SEARCH_API_KEY", "ALPHA_VANTAGE_API_KEY", "TIINGO_API_KEY", "NEWSAPI_KEY"],
        "Ollama本地模型": ["OLLAMA_ENABLED", "OLLAMA_BASE_URL", "OLLAMA_MODEL"],
    }

    for category, keys in categories.items():
        lines.append(f"# ── {category} ──")
        for key in keys:
            if key in env_vars:
                value = env_vars[key]
                if comments.get(key):
                    lines.append(f"# {comments[key]}")
                lines.append(f"{key}={value}")
            elif key in comments:
                lines.append(f"# {comments[key]}")
                lines.append(f"# {key}=")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# =============================================================================
# Status Detection
# =============================================================================

def detect_config_status() -> dict[str, ConfigStatus]:
    """检测当前所有配置项的状态"""
    # Alias for backward compatibility
    return get_current_status()


def get_current_status() -> dict[str, ConfigStatus]:
    """检测当前所有配置项的状态"""
    env_local = read_env_file(get_env_local_file())
    env = read_env_file(get_env_file())

    # 合并环境变量（.env.local 优先）
    all_env = {**env, **env_local}

    status_map = {}
    for config in ALL_CONFIGS:
        # TUSHARE_TOKEN backward compatibility: also check TUSHARE_API_KEY
        if config.var_name == "TUSHARE_TOKEN":
            value = all_env.get("TUSHARE_TOKEN") or all_env.get("TUSHARE_API_KEY")
        else:
            value = all_env.get(config.var_name)
        is_set = bool(value and value.strip())

        # 创建状态副本
        status = ConfigStatus(
            var_name=config.var_name,
            is_set=is_set,
            is_sensitive=config.is_sensitive,
            current_value=mask_sensitive(value) if is_set and config.is_sensitive else (value if is_set else None),
            priority=config.priority,
            description=config.description,
            for_directions=config.for_directions,
            placeholder=config.placeholder
        )
        status_map[config.var_name] = status

    return status_map


def detect_mcp_status() -> dict[str, MCPStatus]:
    """检测当前 MCP 服务器状态"""
    mcp_servers_dir = get_project_root() / "mcp_servers"

    for server_id, status in MCP_SERVERS.items():
        server_dir = mcp_servers_dir / server_id
        # 目录存在即视为已安装
        status.installed = server_dir.exists() and (server_dir / "server.py").exists()
        # 假设未启用（需在 Cursor 设置中手动开启）
        status.enabled = False

    return MCP_SERVERS


# =============================================================================
# Print Functions
# =============================================================================

def print_banner(title: str) -> None:
    """打印标题横幅"""
    width = 70
    print()
    print(bold(cyan("═" * width)))
    print(bold(cyan("║")) + bold(f" {title}").center(width - 4) + bold(cyan(" ║")))
    print(bold(cyan("═" * width)))
    print()


def print_section(title: str) -> None:
    """打印分节标题"""
    print()
    print(bold(yellow(f"━━━ {title} ━━━")))
    print()


def print_status_table(status_map: dict[str, ConfigStatus], direction: Optional[str] = None) -> None:
    """打印配置状态表格"""
    # 过滤方向相关的配置
    if direction:
        filtered = {k: v for k, v in status_map.items() if direction in v.for_directions}
    else:
        filtered = status_map

    # 按优先级排序
    priority_order = {"must": 0, "should": 1, "nice": 2}
    sorted_status = sorted(filtered.values(), key=lambda x: (priority_order.get(x.priority, 3), x.var_name))

    print(f"{'配置项':<25} {'状态':<10} {'当前值':<20} {'说明'}")
    print("-" * 100)

    for status in sorted_status:
        if status.is_set:
            icon = green("✅ 已配置")
            value_display = cyan(status.current_value or "已设置")
        elif status.var_name in ["OLLAMA_ENABLED"]:
            # 非敏感配置
            icon = yellow("⚠️ 待配置")
            value_display = dim(f"[{status.current_value or 'false'}]")
        else:
            icon = red("❌ 未配置")
            value_display = dim("[未设置]")

        # 优先级标记
        priority_icon = ""
        if status.priority == "must":
            priority_icon = red("●")
        elif status.priority == "should":
            priority_icon = yellow("○")
        else:
            priority_icon = dim("·")

        print(f"{priority_icon} {status.var_name:<23} {icon:<12} {value_display:<20} {status.description}")

    print()


def print_mcp_status_table(mcp_map: dict[str, MCPStatus], direction: Optional[str] = None) -> None:
    """打印 MCP 服务器状态表格"""
    if direction:
        filtered = {k: v for k, v in mcp_map.items() if direction in v.for_directions}
    else:
        filtered = mcp_map

    print(f"{'MCP服务器':<30} {'状态':<15} {'说明'}")
    print("-" * 80)

    for server_id, status in filtered.items():
        if status.enabled:
            icon = green("✅ 已启用")
        elif status.installed:
            icon = yellow("⚠️ 待启用")
        else:
            icon = red("❌ 未安装")

        api_key_hint = ""
        if status.needs_api_key and status.api_key_var:
            api_key_hint = f" (需 {status.api_key_var})"

        dep_hint = ""
        if status.enabled and status.needs_optional_dep:
            dep_hint = f"  ⚠️  需额外依赖: pip install -e \".[{status.needs_optional_dep}]\""

        print(f"{status.name:<28} {icon:<15} {status.description}{api_key_hint}{dep_hint}")

    print()


# =============================================================================
# Interactive Functions
# =============================================================================

def prompt_yes_no(question: str, default: bool = False) -> bool:
    """交互式确认"""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        response = input(bold(cyan(question)) + suffix).strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print(dim("请输入 y 或 n"))


def prompt_choice(question: str, choices: list[str], default: int = 0) -> int:
    """交互式选择（返回索引）"""
    print(bold(cyan(question)))
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    while True:
        try:
            response = input(bold("请选择 (默认1): ")).strip()
            if not response:
                return default
            idx = int(response) - 1
            if 0 <= idx < len(choices):
                return idx
            print(dim(f"请输入 1-{len(choices)}"))
        except ValueError:
            print(dim("请输入数字"))


def prompt_api_key(var_name: str, status: ConfigStatus, required: bool = True) -> Optional[str]:
    """交互式输入 API Key"""
    print()
    print(bold(f"━━━ {status.description} ━━━"))
    print(f"变量名: {cyan(var_name)}")

    if status.is_set:
        print(f"当前值: {cyan(status.current_value)}")
        if prompt_yes_no("是否重新输入？", default=False):
            pass
        else:
            print(dim("保留当前值"))
            return None

    if required:
        print(dim(f"示例: {status.placeholder}"))
        while True:
            value = input(bold("请输入 API Key: ")).strip()
            if value:
                return value
            print(red("不能为空，请重新输入"))
    else:
        value = input(bold(f"请输入 API Key（直接回车跳过）: ")).strip()
        return value if value else None


def select_research_direction() -> str:
    """交互式选择研究方向"""
    print_banner("研究方向选择")

    print("请选择您的主要研究领域：")
    print()

    directions = list(DIRECTION_REQUIREMENTS.items())
    for i, (key, config) in enumerate(directions, 1):
        print(f"  {i}. {bold(config.label)}")
        print(f"     {dim(config.description)}")
        print()

    while True:
        try:
            response = input(bold(cyan("请输入序号 (1-5): "))).strip()
            idx = int(response) - 1
            if 0 <= idx < len(directions):
                selected_key = directions[idx][0]
                print()
                print(green(f"已选择: {DIRECTION_REQUIREMENTS[selected_key].label}"))
                return selected_key
            print(dim(f"请输入 1-{len(directions)}"))
        except ValueError:
            print(dim("请输入数字"))


# =============================================================================
# Main Setup Functions
# =============================================================================

def guided_setup(direction: Optional[str] = None) -> dict[str, str]:
    """引导式配置流程"""
    # 1. 选择研究方向
    if not direction:
        direction = select_research_direction()

    rec = DIRECTION_REQUIREMENTS[direction]
    print_banner(f"开始配置：{rec.label}")

    # 2. 检测当前状态
    status_map = detect_config_status()
    mcp_map = detect_mcp_status()

    # 3. 显示当前状态
    print_section("当前配置状态")
    print_status_table(status_map, direction)

    # 4. 收集需要配置的值
    results = {}

    # 必需配置
    if rec.required:
        print_section("必需配置")
        print(yellow("以下配置为研究所必需，请务必填写："))
        for var_name in rec.required:
            if var_name in status_map:
                value = prompt_api_key(var_name, status_map[var_name], required=True)
                if value:
                    results[var_name] = value

    # 推荐配置
    if rec.recommended:
        print_section("推荐配置")
        print(yellow("以下配置可提升研究效率，建议配置（可跳过）："))
        for var_name in rec.recommended:
            if var_name in status_map:
                value = prompt_api_key(var_name, status_map[var_name], required=False)
                if value:
                    results[var_name] = value

    # 可选配置
    if rec.nice:
        print_section("可选增强")
        print(dim("以下为可选配置，根据需要添加："))
        for var_name in rec.nice:
            if var_name in status_map:
                value = prompt_api_key(var_name, status_map[var_name], required=False)
                if value:
                    results[var_name] = value

    # 5. MCP 服务器状态
    print_section("MCP 数据服务器")
    print(f"根据研究方向「{rec.label}」，推荐以下 MCP 服务器：")
    print_mcp_status_table(mcp_map, direction)

    print(yellow("提示：请在 Cursor 设置中启用相关 MCP 服务器。"))

    # 6. 保存配置
    print_section("保存配置")
    if results:
        if prompt_yes_no("是否保存配置到 .env.local？", default=True):
            save_configs(results)
            print(green("✅ 配置已保存到 .env.local"))
    else:
        print(dim("未收集到新的配置，跳过保存"))

    return results


def status_check() -> None:
    """状态检查模式"""
    print_banner("配置状态检查")

    status_map = detect_config_status()
    mcp_map = detect_mcp_status()

    print_section("API Keys 配置状态")
    print_status_table(status_map)

    print_section("MCP 服务器状态")
    print_mcp_status_table(mcp_map)

    # 汇总
    must_missing = [s for s in status_map.values() if not s.is_set and s.priority == "must"]
    should_missing = [s for s in status_map.values() if not s.is_set and s.priority == "should"]

    if not must_missing and not should_missing:
        print(green("✅ 所有必需配置已完成"))
    else:
        if must_missing:
            print(red(f"❌ 缺少 {len(must_missing)} 个必需配置："))
            for s in must_missing:
                print(f"  - {s.var_name}: {s.description}")
        if should_missing:
            print(yellow(f"⚠️ 缺少 {len(should_missing)} 个推荐配置："))
            for s in should_missing:
                print(f"  - {s.var_name}: {s.description}")


def quick_setup(direction: str, configs: dict[str, str]) -> None:
    """快速配置模式"""
    if direction not in DIRECTION_REQUIREMENTS:
        print(red(f"未知研究方向: {direction}"))
        print(f"可用方向: {', '.join(DIRECTION_REQUIREMENTS.keys())}")
        sys.exit(1)

    rec = DIRECTION_REQUIREMENTS[direction]
    print_banner(f"快速配置：{rec.label}")

    # 保存配置
    if configs:
        save_configs(configs)
        print(green(f"✅ 已保存 {len(configs)} 项配置"))
    else:
        print(yellow("未提供配置项"))


def validate_configs() -> bool:
    """验证配置有效性"""
    print_banner("配置验证")

    status_map = detect_config_status()
    valid = True

    # 检查必需配置
    for config in status_map.values():
        if config.priority == "must" and not config.is_set:
            print(red(f"❌ 必需配置缺失: {config.var_name}"))
            valid = False

    if valid:
        print(green("✅ 所有必需配置已设置"))

    return valid


# =============================================================================
# File Operations
# =============================================================================

def save_configs(configs: dict[str, str]) -> None:
    """保存配置到 .env.local"""
    env_local_path = get_env_local_file()

    # 读取现有配置
    existing = read_env_file(env_local_path)

    # 合并配置
    existing.update(configs)

    # 生成注释
    comments = {
        "DEEPSEEK_API_KEY": "DeepSeek 直连（中文LLM推荐）",
        "RELAY_API_KEY": "B.AI 中转（GPT/Claude英文模型）",
        "TUSHARE_TOKEN": "Tushare Pro A股数据",
        "EODHD_API_KEY": "EODHD全球宏观数据",
        "BRAVE_SEARCH_API_KEY": "Brave Search网络搜索",
        "FRED_API_KEY": "美联储经济数据",
        "ZHIPU_API_KEY": "智谱GLM（结构化输出）",
        "OLLAMA_ENABLED": "Ollama本地模型兜底",
    }

    # 写入文件
    write_env_file(env_local_path, existing, comments)


def generate_env_template(direction: Optional[str] = None) -> str:
    """生成 .env.local 模板内容"""
    lines = []
    lines.append("# =============================================================================")
    lines.append("# 论文-研报工作流 · 环境变量配置")
    lines.append(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("# =============================================================================")
    lines.append("")

    if direction and direction in DIRECTION_REQUIREMENTS:
        rec = DIRECTION_REQUIREMENTS[direction]
        lines.append(f"# 研究方向: {rec.label}")
        lines.append("")

    lines.append("# ─── AI 模型 API Keys ───")
    lines.append("")
    lines.append("# DeepSeek 直连（中文LLM，核心必需）")
    lines.append("DEEPSEEK_API_KEY=your_deepseek_key_here")
    lines.append("")
    lines.append("# B.AI 中转（GPT/Claude英文模型）")
    lines.append("RELAY_API_KEY=your_relay_key_here")
    lines.append("")
    lines.append("# ─── 金融数据 API Keys ───")
    lines.append("")
    lines.append("# Tushare Pro A股数据")
    lines.append("TUSHARE_TOKEN=your_tushare_key_here")
    lines.append("")
    lines.append("# EODHD 全球宏观数据")
    lines.append("EODHD_API_KEY=your_eodhd_key_here")
    lines.append("")
    lines.append("# ─── 可选 API Keys ───")
    lines.append("")
    lines.append("# Brave Search 网络搜索")
    lines.append("BRAVE_SEARCH_API_KEY=your_brave_key_here")
    lines.append("")
    lines.append("# Ollama 本地模型（离线兜底）")
    lines.append("OLLAMA_ENABLED=false")

    return "\n".join(lines)


# =============================================================================
# Orchestrator Integration
# =============================================================================

def check_and_guide_setup(topic: Optional[str] = None) -> dict:
    """由 AgentOrchestrator 调用：
    1. 检测当前配置
    2. 若有关键缺失，生成引导提示
    3. 返回状态字典
    """
    status_map = detect_config_status()

    # 找出缺失的必需和推荐配置
    missing_critical = [
        s for s in status_map.values()
        if not s.is_set and s.priority in ("must", "should")
    ]

    if not missing_critical:
        return {
            "needs_setup": False,
            "missing": [],
            "guidance": green("✅ 所有必需配置已完成")
        }

    # 生成引导提示
    missing_names = [s.var_name for s in missing_critical]

    guidance_lines = [
        yellow("⚠️ 检测到配置缺失，需要完成首次设置"),
        "",
        "缺失的配置项：",
    ]
    for s in missing_critical:
        priority_label = red("必需") if s.priority == "must" else yellow("推荐")
        guidance_lines.append(f"  • {s.var_name} [{priority_label}]: {s.description}")

    guidance_lines.extend([
        "",
        dim("运行以下命令启动配置向导："),
        dim("  python scripts/setup_wizard.py --guided"),
    ])

    return {
        "needs_setup": True,
        "missing": missing_names,
        "critical_count": len([s for s in missing_critical if s.priority == "must"]),
        "recommended_count": len([s for s in missing_critical if s.priority == "should"]),
        "guidance": "\n".join(guidance_lines)
    }


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="论文-研报工作流 · 配置向导",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  python scripts/setup_wizard.py --guided           # 引导模式
  python scripts/setup_wizard.py --status          # 状态检查
  python scripts/setup_wizard.py --direction a_share --key DEEPSEEK_API_KEY=xxx  # 快速配置
  python scripts/setup_wizard.py --validate        # 验证配置
  python scripts/setup_wizard.py --template        # 生成模板
        """
    )

    parser.add_argument("--guided", action="store_true", help="引导式配置")
    parser.add_argument("--status", action="store_true", help="显示配置状态")
    parser.add_argument("--direction", "-d", type=str, help="研究方向 (a_share/macro/empirical_paper/quantitative/financial_report)")
    parser.add_argument("--key", "-k", action="append", type=str, help="快速配置键值对 (KEY=value)")
    parser.add_argument("--validate", action="store_true", help="验证配置")
    parser.add_argument("--template", action="store_true", help="生成配置模板")

    args = parser.parse_args()

    # 解析快速配置
    configs = {}
    if args.key:
        for kv in args.key:
            if "=" in kv:
                k, v = kv.split("=", 1)
                configs[k.strip()] = v.strip()

    # 根据参数选择模式
    if args.status:
        status_check()
    elif args.validate:
        validate_configs()
    elif args.template:
        print(generate_env_template(args.direction))
    elif args.direction and configs:
        quick_setup(args.direction, configs)
    elif args.guided or args.direction:
        guided_setup(args.direction)
    else:
        # 默认显示状态
        status_check()
        print()
        print(dim("运行 --guided 进入引导模式，或 --help 查看更多选项"))


if __name__ == "__main__":
    main()
