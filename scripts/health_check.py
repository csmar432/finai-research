#!/usr/bin/env python3
r"""
health_check.py — 论文-研报工作流 · 系统健康检查 v2.0

【v2.0 改进】
1. LLM 真实验证 — 实际调用模型 API（发送一个简单 prompt），确认 key 真正有效
2. MCP 真实验证 — 启动服务器进程，发送 stdin/stdout 握手包，验证响应
3. 网络真实探测 — 对关键外部服务（DeepSeek/FRED/WorldBank）发起 HEAD 请求
4. 分级验证模式 — --check（基础） / --verify（深度，耗时长但更可靠）

用法：
  python scripts/health_check.py              # 交互模式（基础检查）
  python scripts/health_check.py --json       # JSON 输出
  python scripts/health_check.py --compact    # 紧凑摘要
  python scripts/health_check.py --verify     # 深度验证（LLM真实调用+MCP服务器ping）
  python scripts/health_check.py --verify --json  # 深度验证+JSON

在 Python 中导入：
  from scripts.health_check import run_diagnostic, DiagnosticResult
  result = run_diagnostic(verify=False)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# ── Load .env before any other module reads environment variables ─────────────
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    load_dotenv(_PROJECT_ROOT / ".env.local", override=True)
except ImportError:
    import logging as _dotenv_log
    _dotenv_log.warning(
        "python-dotenv not installed; .env files will not be auto-loaded. "
        "Install it with: pip install python-dotenv"
    )

# ── Add project root to path so 'from scripts.xxx' works ────────────────────
sys.path.insert(0, str(_PROJECT_ROOT))

# ── ANSI Color Codes ────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def green(t: str) -> str:
    return _c(t, GREEN)


def red(t: str) -> str:
    return _c(t, RED)


def yellow(t: str) -> str:
    return _c(t, YELLOW)


def cyan(t: str) -> str:
    return _c(t, CYAN)


def bold(t: str) -> str:
    return _c(t, BOLD)


def dim(t: str) -> str:
    return _c(t, DIM)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


class ProblemCategory(str, Enum):
    NETWORK = "network"
    API_KEY = "api_key"
    DEPENDENCY = "dependency"
    MCP = "mcp"
    DATA_SOURCE = "data_source"
    OK = "ok"


@dataclass
class ProblemItem:
    category: ProblemCategory
    name: str
    name_zh: str
    message: str
    fix_steps: list[str]
    severity: str = "high"
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiagnosticResult:
    timestamp: str
    platform: str
    llm_available: bool
    llm_status: str
    mcp_enabled_count: int
    mcp_verified_count: int
    problem_counts: dict[str, int]
    problems: list[ProblemItem]
    system_ready: bool
    recommendations: list[str]
    verify_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "platform": self.platform,
            "llm_available": self.llm_available,
            "llm_status": self.llm_status,
            "mcp_enabled_count": self.mcp_enabled_count,
            "mcp_verified_count": self.mcp_verified_count,
            "problem_counts": self.problem_counts,
            "system_ready": self.system_ready,
            "recommendations": self.recommendations,
            "verify_mode": self.verify_mode,
            "problems": [p.to_dict() for p in self.problems],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Platform Detection
# ─────────────────────────────────────────────────────────────────────────────


def _detect_platform() -> str:
    env_str = (
        os.environ.get("CURSOR", "") +
        os.environ.get("CURSOR_SESSION_ID", "") +
        os.environ.get("VSCODE_RESOLVING_ENVIRONMENT", "") +
        os.environ.get("CLAUDE_CODE", "") +
        os.environ.get("AGENT_ID", "") +
        os.environ.get("CODALANG_AGENT", "")
    )
    env_lower = env_str.lower()
    if "cursor" in env_lower:
        return "cursor"
    if "claude_code" in env_lower or "claude_desktop" in env_lower:
        return "claude_code"
    if "codex" in env_lower or "cody" in env_lower:
        return "codex"
    if "vscode" in env_lower:
        return "vscode"
    try:
        import psutil
        for p in psutil.Process().parents():
            name = p.name().lower()
            if "cursor" in name:
                return "cursor"
            if "claude" in name:
                return "claude_code"
    except Exception:
        import logging
        logging.getLogger("health_check").debug("Platform detection via psutil failed, falling back to unknown")
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Env File Reading
# ─────────────────────────────────────────────────────────────────────────────


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


def _mask(s: str) -> str:
    if not s or len(s) <= 6:
        return "*" * len(s) if s else ""
    return f"{s[:4]}{'*' * max(0, len(s) - 8)}{s[-4:]}"


# exported so external callers can reference the same root
def _project_root() -> Path:
    return _PROJECT_ROOT


# ─────────────────────────────────────────────────────────────────────────────
# Network Probe
# ─────────────────────────────────────────────────────────────────────────────

def _probe_url(url: str, timeout: int = 6) -> tuple[bool, str]:
    """对指定 URL 发起 GET 请求，返回 (success, message)。

    - HTTP 401/403 → 认证问题（不返回 False，表示网络可达）
    - 其他 HTTP 错误码 → 网络问题（返回 False）
    - 连接失败 → 网络问题（返回 False）
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "FinResearch-Agent/2.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # 认证问题 ≠ 网络问题，网络可达
            return True, f"HTTP {e.code} (网络可达，需认证)"
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"连接失败: {e.reason}"
    except Exception as e:
        return False, str(e)[:60]


# ─────────────────────────────────────────────────────────────────────────────
# LLM Real Verification
# ─────────────────────────────────────────────────────────────────────────────


def _llm_chat_completion(url: str, api_key: str, model: str,
                          timeout: int = 15) -> tuple[bool, str]:
    """真正调用 chat/completions API，返回 (success, message)。

    目的：验证 API Key 是否有效（能建立连接、认证通过、模型可调用）。
    不要求响应内容匹配特定字符串，只要不是错误即可。
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly one word: hello."}],
        "max_tokens": 20,
        "temperature": 0,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "FinResearch-Agent/2.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                result = json.loads(body)
            except json.JSONDecodeError as e:
                return False, f"JSON decode error: {e}"
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            # 只要拿到有效 JSON 响应就算成功（不要求特定内容）
            return True, f"API 正常 (model={model}, response_len={len(content)})"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        err_detail = ""
        try:
            err_obj = json.loads(body)
            err_detail = err_obj.get("error", {}).get("message", "") or err_obj.get("message", "")
        except Exception:
            err_detail = body[:120].strip()
        if not err_detail:
            err_detail = f"(HTTP {e.code}, body: {body[:80].strip() or 'empty'})"
        return False, err_detail or f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"连接失败: {e.reason}"
    except Exception as e:
        return False, str(e)[:80]


def _check_llm(verify: bool = False) -> tuple[bool, str, list[ProblemItem]]:
    """检查 LLM 是否可用且真正有效。verify=True 时实际调用模型 API。"""
    root = _project_root()
    env_local = _read_env(root / ".env.local")
    env = _read_env(root / ".env")
    all_env = {**env, **env_local}

    ds_key = all_env.get("DEEPSEEK_API_KEY", "").strip()
    relay_key = all_env.get("RELAY_API_KEY", "").strip()
    ds_url = all_env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    relay_url = all_env.get("RELAY_BASE_URL", "https://api.b.ai").strip()

    available: list[str] = []
    problems: list[ProblemItem] = []

    # ── DeepSeek ───────────────────────────────────────────────────────────
    if ds_key:
        ok, msg = _probe_url(ds_url.rstrip("/") + "/v1/models", timeout=6)
        if not ok:
            problems.append(ProblemItem(
                category=ProblemCategory.NETWORK,
                name="DEEPSEEK_API_KEY",
                name_zh="DeepSeek API",
                message=f"无法连接到 DeepSeek API（{msg}）",
                fix_steps=[
                    "1. 确认网络可以访问 https://api.deepseek.com",
                    "2. 如果使用代理，检查 HTTP_PROXY / HTTPS_PROXY 环境变量",
                    "3. DeepSeek 在中国大陆可直接访问，无需 VPN",
                ],
                severity="high",
            ))
        else:
            if verify:
                deepseek_models = ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner"]
                success = False
                last_msg = ""
                for model in deepseek_models:
                    ok2, msg2 = _llm_chat_completion(
                        ds_url.rstrip("/") + "/v1/chat/completions",
                        ds_key, model, timeout=15,
                    )
                    last_msg = msg2
                    if ok2:
                        available.append(f"DeepSeek ({_mask(ds_key)}) ✅ [{model}]")
                        success = True
                        break
                if not success:
                    problems.append(ProblemItem(
                        category=ProblemCategory.API_KEY,
                        name="DEEPSEEK_API_KEY",
                        name_zh="DeepSeek API Key",
                        message=f"DeepSeek Key 无效: {last_msg}",
                        fix_steps=[
                            "1. 访问 https://platform.deepseek.com 登录账号",
                            "2. 在 API Keys 页面创建新 Key",
                            f"3. 当前 Key: {_mask(ds_key)}",
                            "4. 替换 .env 中的 DEEPSEEK_API_KEY",
                            "5. 重启 Cursor / Claude Code",
                        ],
                        severity="high",
                    ))
            else:
                available.append(f"DeepSeek ({_mask(ds_key)}) ⚠️基础检查")
    else:
        problems.append(ProblemItem(
            category=ProblemCategory.API_KEY,
            name="DEEPSEEK_API_KEY",
            name_zh="DeepSeek API Key",
            message="DeepSeek API Key 未配置",
            fix_steps=[
                "1. 访问 https://platform.deepseek.com 注册账号",
                "2. 在 API Keys 页面创建新 Key（免费额度充足）",
                "3. 将 Key 填入 .env: DEEPSEEK_API_KEY=sk-xxxx",
                "4. 保存后重启 Cursor / Claude Code",
            ],
            severity="high",
        ))

    # ── Relay 中转 ─────────────────────────────────────────────────────
    if relay_key:
        # 探测多个可能的模型，找到任何一个返回 200 即说明 key 有效
        relay_models = [
            "deepseek-v4-flash", "deepseek-v4-pro",
            "gpt-4o-mini", "gpt-4o",
            "deepseek-chat",
        ]
        if verify:
            success = False
            last_msg = ""
            for model in relay_models:
                ok, msg = _llm_chat_completion(
                    relay_url.rstrip("/") + "/v1/chat/completions",
                    relay_key, model, timeout=15,
                )
                last_msg = msg
                if ok:  # HTTP 200 即 key 有效，不要求内容
                    available.append(f"Relay 中转 ({_mask(relay_key)}) ✅ [{model}]")
                    success = True
                    break
            if not success:
                problems.append(ProblemItem(
                    category=ProblemCategory.API_KEY,
                    name="RELAY_API_KEY",
                    name_zh="Relay 中转 API Key",
                    message=f"Relay 中转 Key 无法调用任何模型: {last_msg}",
                    fix_steps=[
                        "1. 访问中转服务确认 Key 有效",
                        "2. 确认 Key 所在账号已开通对应模型通道",
                        f"3. 当前 Key: {_mask(relay_key)}",
                    ],
                    severity="medium",
                ))
        else:
            ok, msg = _probe_url(relay_url.rstrip("/"), timeout=6)
            if ok:
                available.append(f"Relay 中转 ({_mask(relay_key)}) ⚠️基础检查")
            else:
                problems.append(ProblemItem(
                    category=ProblemCategory.NETWORK,
                    name="RELAY_API_KEY",
                    name_zh="Relay 中转 API",
                    message=f"无法连接到 Relay 中转（{msg}）",
                    fix_steps=[f"1. 检查网络是否可访问 {relay_url}"],
                    severity="medium",
                ))

    # ── 汇总 ────────────────────────────────────────────────────────────
    if available:
        status = "，".join(available)
        return True, f"✅ LLM 可用: {status}", problems

    if ds_key and any(p.category == ProblemCategory.NETWORK for p in problems):
        return False, "❌ LLM 不可用（网络问题）", problems

    return False, "❌ 没有可用的 LLM", problems


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Check
# ─────────────────────────────────────────────────────────────────────────────


def _check_dependencies() -> tuple[list[ProblemItem], list[str]]:
    critical_deps = [
        ("requests", "requests", "HTTP 请求"),
        ("numpy", "numpy", "数值计算"),
        ("pandas", "pandas", "数据处理"),
        ("scipy", "scipy", "科学计算"),
        ("matplotlib", "matplotlib", "图表绘制"),
        ("seaborn", "seaborn", "统计图表"),
        ("statsmodels", "statsmodels", "计量经济"),
    ]
    recommended_deps = [
        ("sklearn", "sklearn", "机器学习"),
        ("dotenv", "dotenv", "环境变量"),
        ("openpyxl", "openpyxl", "Excel 读取"),
    ]

    problems: list[ProblemItem] = []
    ok_list: list[str] = []

    for label, imp, zh in critical_deps + recommended_deps:
        try:
            mod = importlib.import_module(imp)
            v = getattr(mod, "__version__", "installed")
            ok_list.append(f"{label} {v}")
        except ImportError:
            is_critical = any(d[0] == label for d in critical_deps)
            severity = "high" if is_critical else "medium"
            install_hint = {
                "sklearn": "pip install scikit-learn",
                "dotenv": "pip install python-dotenv",
                "openpyxl": "pip install openpyxl",
                "requests": "pip install requests",
                "numpy": "pip install numpy",
                "pandas": "pip install pandas",
                "scipy": "pip install scipy",
                "matplotlib": "pip install matplotlib",
                "seaborn": "pip install seaborn",
                "statsmodels": "pip install statsmodels",
            }.get(imp, f"pip install {imp}")
            problems.append(ProblemItem(
                category=ProblemCategory.DEPENDENCY,
                name=imp,
                name_zh=zh,
                message=f"{zh}（{label}）未安装",
                fix_steps=[
                    f"运行: {install_hint}",
                    "或在项目根目录运行: pip install -r requirements.txt",
                    f"验证安装: python -c \"import {imp}\"",
                ],
                severity=severity,
            ))

    return problems, ok_list


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server Check
# ─────────────────────────────────────────────────────────────────────────────

_DIR_TO_ID: dict[str, str] = {
    "user_enhanced_finance": "enhanced-finance",
    "user_eastmoney_reports": "eastmoney-reports",
    "user_eastmoney_fund": "eastmoney-fund",
    "user_eastmoney_bond": "eastmoney-bond",
    "user_eastmoney_option": "eastmoney-option",
    "user_wb_data": "wb-data",
    "user_imf_data": "imf-data",
    "user_oecd_data": "oecd-data",
    "user_fed_data": "fed-data",
    "user_financial": "financial",
    "user_eodhd": "eodhd",
    "user_tushare": "tushare",
    "user_csmar": "csmar",
    "user_bea_data": "bea-data",
    "user_wind": "wind",
    "user_latex_mcp": "latex-mcp",
    "user_playwright_mcp": "playwright-mcp",
    "user_e2b_mcp": "e2b-mcp",
    "user_pandas_mcp": "pandas-mcp",
    "user_filesystem_mcp": "filesystem-mcp",
    "user_nber_wp": "nber-wp",
    "user_context7": "context7",
    "user_openalex": "openalex",
    "user_macro_ceic": "macro-ceic",
    "user_macro_datas": "macro-datas",
    "user_macro_stats": "macro-stats",
    "user_province_stats": "province-stats",
    "user_hubei_stats": "hubei-stats",
    "user_wuhan_stats": "wuhan-stats",
}

_MCP_API_KEYS: dict[str, str] = {
    "tushare": "TUSHARE_TOKEN",
    "eodhd": "EODHD_API_KEY",
    "csmar": "CSMAR_API_KEY",
}

# 网络连通性探测的目标（用于 MCP 深度验证）
_MCP_NETWORK_TARGETS: dict[str, str] = {
    "fed-data": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF",
    "financial": "https://api.worldbank.org/v2/country/all?format=json&per_page=1",
    "wb-data": "https://api.worldbank.org/v2/country/all?format=json&per_page=1",
    "eodhd": "https://eodhd.com/financial-api/calendar/",
    "enhanced-finance": "https://api.exchangerate-api.com/v4/latest/USD",
    "tushare": "https://api.tushare.pro",
}


def _verify_mcp_server_stdio(server_path: Path, timeout: int = 8) -> tuple[bool, str]:
    """启动 MCP 服务器，发送 JSON-RPC initialize + ping，验证响应。

    Returns (success, message)
    """
    if not server_path.exists():
        return False, "server.py 不存在"

    env = os.environ.copy()
    root = _project_root()
    for env_path in [root / ".env", root / ".env.local"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    # P0 修复 2026-06-28: 用 sys.executable（健康检查自身 Python），
    # 而不是 shutil.which("python3")（可能是 homebrew python3，缺 mcp 等依赖）
    python_path = sys.executable

    try:
        proc = subprocess.Popen(
            [python_path, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(root),
        )

        initialize_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "health-check", "version": "2.0"},
            },
        }
        ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}

        init_data = json.dumps(initialize_req).encode("utf-8") + b"\n"
        ping_data = json.dumps(ping_req).encode("utf-8") + b"\n"

        proc.stdin.write(init_data)
        proc.stdin.flush()

        start = time.time()
        output_lines = []

        while time.time() - start < timeout:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    stderr = proc.stderr.read(500).decode("utf-8", errors="replace")
                    # 检查 stderr 中的常见错误
                    if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
                        missing = next(
                            (l.strip() for l in stderr.splitlines() if "ModuleNotFoundError" in l),
                            stderr[:100],
                        )
                        return False, f"依赖缺失: {missing}"
                    if "SyntaxError" in stderr:
                        return False, f"语法错误: {stderr[:100]}"
                    return False, f"进程退出 (exit={proc.returncode}): {stderr[:80]}"
                time.sleep(0.1)
                continue
            output_lines.append(line)
            try:
                resp = json.loads(line)
                if resp.get("id") == 1:
                    proc.stdin.write(ping_data)
                    proc.stdin.flush()
                elif resp.get("id") == 2 or resp.get("result") is not None:
                    proc.terminate()
                    proc.wait(timeout=2)
                    return True, "握手成功"
            except (json.JSONDecodeError, KeyError):
                continue

        proc.terminate()
        proc.wait(timeout=2)
        raw_output = b"".join(output_lines).decode("utf-8", errors="replace")[:200]
        return False, f"超时 (收到 {len(output_lines)} 行): {raw_output}"

    except Exception as e:
        # Bug fix: `proc` is undefined if Popen itself threw (e.g. FileNotFoundError).
        # Check locals before attempting terminate.
        _proc = locals().get("proc")
        if _proc is not None:
            try:
                _proc.terminate()
            except Exception:
                pass
        return False, str(e)[:80]


def _check_mcp(verify: bool = False) -> tuple[int, int, list[ProblemItem], list[str]]:
    """检查 MCP 服务器状态。verify=True 时对关键服务器做 stdio 握手验证。"""
    root = _project_root()

    # 读取 Cursor MCP 配置
    cursor_mcp = Path.home() / ".cursor" / "mcp.json"
    enabled_ids: set[str] = set()
    if cursor_mcp.exists():
        try:
            with open(cursor_mcp, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and "mcpServers" in raw:
                enabled_ids = set(raw["mcpServers"].keys())
            elif isinstance(raw, dict):
                enabled_ids = set(raw.keys())
        except (json.JSONDecodeError, OSError) as e:
            import logging as _mcp_log
            _mcp_log.warning(f"Malformed MCP config {cursor_mcp}: {e} — skipping MCP server detection")

    # 扫描本地 mcp_servers 目录
    servers_dir = root / "mcp_servers"
    local_servers: dict[str, tuple[str, Path]] = {}
    if servers_dir.exists():
        for d in servers_dir.iterdir():
            if d.is_dir() and (d / "server.py").exists():
                mcp_id = _DIR_TO_ID.get(d.name, d.name)
                local_servers[mcp_id] = (d.name, d / "server.py")

    env_local = _read_env(root / ".env.local")
    env = _read_env(root / ".env")
    all_env = {**env, **env_local}

    problems: list[ProblemItem] = []
    ok_list: list[str] = []
    verified_count = 0
    network_probed: dict[str, tuple[bool, str]] = {}

    # 优先网络探测（轻量，可并发）
    if verify:
        def probe_one(name_url: tuple[str, str]) -> tuple[str, bool, str]:
            url = name_url[1]
            ok, msg = _probe_url(url, timeout=6)
            return name_url[0], ok, msg

        targets = {k: v for k, v in _MCP_NETWORK_TARGETS.items() if k in enabled_ids}
        if targets:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futures = {ex.submit(probe_one, (k, v)): k for k, v in targets.items()}
                for f in concurrent.futures.as_completed(futures, timeout=12):
                    try:
                        name, ok, msg = f.result()
                        network_probed[name] = (ok, msg)
                    except Exception as e:
                        name = futures[f]
                        network_probed[name] = (False, str(e)[:40])

    # 网络问题汇总
    network_failures = {k: v for k, v in network_probed.items() if not v[0]}
    if network_failures:
        names = ", ".join(network_failures.keys())
        msgs = "; ".join(f"{k}({v[1]})" for k, v in network_failures.items())
        problems.append(ProblemItem(
            category=ProblemCategory.NETWORK,
            name="mcp_network",
            name_zh="MCP 网络问题",
            message=f"以下 MCP 的外部数据源无法访问: {msgs}",
            fix_steps=[
                "1. 检查网络连接",
                "2. 如果使用代理，确保 HTTPS_PROXY 设置正确",
                "3. 部分数据源（如 Tushare Pro）需要额外认证",
            ],
            severity="medium",
        ))

    # MCP 服务器 stdio 握手验证（verify 模式，只测关键服务器）
    if verify:
        critical_for_verify = ["fed-data", "financial", "wb-data", "eodhd"]
        for mcp_id in critical_for_verify:
            if mcp_id not in enabled_ids or mcp_id not in local_servers:
                continue
            dir_name, server_path = local_servers[mcp_id]
            ok, msg = _verify_mcp_server_stdio(server_path, timeout=8)
            if ok:
                ok_list.append(f"{mcp_id} ✅ 握手成功")
                verified_count += 1
            else:
                problems.append(ProblemItem(
                    category=ProblemCategory.MCP,
                    name=f"mcp_{mcp_id}",
                    name_zh=f"MCP 服务器 {mcp_id}",
                    message=f"stdio 握手验证失败: {msg}",
                    fix_steps=[
                        f"1. 手动测试: python {server_path}",
                        "2. 检查依赖: pip install mcp",
                        "3. 检查 server.py 是否有语法错误",
                    ],
                    severity="medium",
                ))

    # 基础配置检查（总是执行）
    missing_key_mcp_ids: list[str] = []
    disabled_critical: list[str] = []

    critical_mcp_meta = {
        "wb-data": "世界银行（GDP/人口/贸易）",
        "financial": "全球宏观（中国/日本/欧元区）",
        "eastmoney-reports": "东方财富研报与新闻",
        "enhanced-finance": "外汇/航运/大宗商品",
        "fed-data": "美联储/FOMC 数据",
    }

    for mcp_id in sorted(local_servers.keys()):
        is_enabled = mcp_id in enabled_ids
        api_key_var = _MCP_API_KEYS.get(mcp_id)
        has_api_key = api_key_var and all_env.get(api_key_var, "").strip()

        if is_enabled:
            if api_key_var and not has_api_key:
                missing_key_mcp_ids.append(mcp_id)
            else:
                if not verify or mcp_id not in critical_for_verify:
                    ok_list.append(f"{mcp_id} ✅")
        else:
            if mcp_id in critical_mcp_meta:
                disabled_critical.append(mcp_id)

    if missing_key_mcp_ids:
        missing = ", ".join(missing_key_mcp_ids)
        problems.append(ProblemItem(
            category=ProblemCategory.API_KEY,
            name="mcp_missing_api_keys",
            name_zh="MCP 缺少 API Key",
            message=f"以下 MCP 已启用但缺少必要的 API Key: {missing}",
            fix_steps=[
                "请在 .env 中添加相应 Key：",
                "  TUSHARE_TOKEN → https://tushare.pro/register",
                "  EODHD_API_KEY → https://eodhd.com",
                "  CSMAR_API_KEY → https://www.gtadata.com（需机构账号）",
            ],
            severity="medium",
        ))

    if disabled_critical:
        disabled = ", ".join(disabled_critical)
        problems.append(ProblemItem(
            category=ProblemCategory.MCP,
            name="mcp_disabled",
            name_zh="MCP 服务器未启用",
            message=f"以下关键 MCP 服务器已安装但未启用: {disabled}",
            fix_steps=[
                "1. 打开 Cursor 设置（Cmd+,）",
                '2. 搜索 "MCP" 或 "Model Context Protocol"',
                "3. 点击 \"MCP Servers\"",
                f"4. 找到并启用: {disabled}",
                "5. 启用后重启 Cursor",
            ],
            severity="low",
        ))

    return len(enabled_ids), verified_count, problems, ok_list


# ─────────────────────────────────────────────────────────────────────────────
# Platform-specific Fix Instructions
# ─────────────────────────────────────────────────────────────────────────────


def _platform_fixes(platform: str) -> dict[str, str]:
    if platform == "cursor":
        return {
            "env_hint": "编辑项目根目录下的 .env 文件",
            "restart_hint": "启用 MCP 后需要重启 Cursor",
        }
    elif platform == "claude_code":
        return {
            "env_hint": "编辑项目根目录下的 .env 文件",
            "restart_hint": "重启 Claude Code",
        }
    elif platform == "codex":
        return {
            "env_hint": "编辑项目根目录下的 .env 文件",
            "restart_hint": "重新加载窗口（Cmd+Shift+P → Reload Window）",
        }
    else:
        return {
            "env_hint": "编辑项目根目录下的 .env 文件",
            "restart_hint": "重启 IDE",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Diagnostic
# ─────────────────────────────────────────────────────────────────────────────


def run_diagnostic(verify: bool = False) -> DiagnosticResult:
    """运行完整诊断。verify=True 时执行深度验证（耗时更长）。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    platform = _detect_platform()
    pf = _platform_fixes(platform)

    all_problems: list[ProblemItem] = []

    # 1. LLM 检查
    llm_available, llm_status, llm_problems = _check_llm(verify=verify)
    all_problems.extend(llm_problems)

    # 2. 依赖检查
    dep_problems, dep_ok = _check_dependencies()
    all_problems.extend(dep_problems)

    # 3. MCP 检查
    mcp_count, mcp_verified, mcp_problems, mcp_ok = _check_mcp(verify=verify)
    all_problems.extend(mcp_problems)

    # 3b. 数据源可用性检查
    from scripts.data_source_checker import (
        DataSourceChecker, DataRequirement,
        TARIFF_RESEARCH_REQUIREMENTS,
    )
    ds_checker = DataSourceChecker(TARIFF_RESEARCH_REQUIREMENTS)
    ds_result = ds_checker.run()

    # 将数据源问题转换为ProblemItem
    for src_id, src_result in ds_result.source_results.items():
        if src_result.status in ("requires_key", "requires_purchase", "requires_auth", "unavailable"):
            meta = DataSourceChecker.SOURCE_META.get(src_id, {})
            severity = "high" if src_id in ("csmar_customs", "tushare") else "medium"
            all_problems.append(ProblemItem(
                category=ProblemCategory.DATA_SOURCE,
                name=f"data_source_{src_id}",
                name_zh=f"数据源: {src_id}",
                message=src_result.message,
                fix_steps=[
                    f"来源: {meta.get('description', src_id)}",
                    f"获取: {src_result.url or meta.get('get_url', '请自行获取')}",
                    f"成本: {meta.get('cost', '未知')}",
                ] if src_result.status != "unavailable" else [src_result.details or "请将数据文件放入 data/ 目录"],
                severity=severity,
            ))

    # 4. 统计
    counts: dict[str, int] = {"network": 0, "api_key": 0, "dependency": 0, "mcp": 0, "data_source": 0}
    for p in all_problems:
        cat_val = p.category.value if isinstance(p.category, ProblemCategory) else p.category
        counts[cat_val] = counts.get(cat_val, 0) + 1

    # 5. 平台相关问题更新
    for p in all_problems:
        steps_text = " ".join(p.fix_steps).lower()
        if p.category == ProblemCategory.API_KEY and "env" in steps_text:
            p.fix_steps = [
                f"【{pf['env_hint']}】",
                *[s for s in p.fix_steps if "env" not in s.lower() and ".env" not in s],
                f"【{pf['restart_hint']}】",
            ]

    # 6. 系统就绪判定
    system_ready = (
        llm_available and
        not any(
            p.category == ProblemCategory.DEPENDENCY and p.severity == "high"
            for p in all_problems
        )
    )

    # 7. 建议
    recs: list[str] = []
    if not llm_available:
        high_sev = [p for p in all_problems if p.severity == "high"]
        if high_sev:
            recs.append(f"🔴 优先处理 {len(high_sev)} 个高优先级问题")
    if all_problems:
        recs.append("📋 问题已分类列示，每类都有明确修复步骤")
    if counts.get("dependency", 0) > 0:
        recs.append("📦 依赖: pip install scikit-learn python-dotenv openpyxl")
    if counts.get("api_key", 0) > 0:
        recs.append("🔑 配置 Key 后重启 IDE 使配置生效")
    if counts.get("data_source", 0) > 0:
        recs.append("📊 数据源缺失：关税研究需要CSMAR海关数据+Tushare，请先确认数据来源")
    if verify:
        recs.append("✅ 深度验证已完成（MCP stdio 握手 + LLM 真实调用）")
    else:
        recs.append("💡 使用 --verify 模式可进行深度验证（LLM 真实调用 + MCP 服务器握手）")

    return DiagnosticResult(
        timestamp=timestamp,
        platform=platform,
        llm_available=llm_available,
        llm_status=llm_status,
        mcp_enabled_count=mcp_count,
        mcp_verified_count=mcp_verified,
        problem_counts=counts,
        problems=all_problems,
        system_ready=system_ready,
        recommendations=recs,
        verify_mode=verify,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output Formatters
# ─────────────────────────────────────────────────────────────────────────────


def _group_by_category(problems: list[ProblemItem]) -> dict[ProblemCategory, list[ProblemItem]]:
    groups: dict[ProblemCategory, list[ProblemItem]] = {}
    for p in problems:
        cat = p.category if isinstance(p.category, ProblemCategory) else ProblemCategory(p.category)
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(p)
    return groups


_CAT_LABELS: dict[ProblemCategory, str] = {
    ProblemCategory.NETWORK: "🌐 网络问题",
    ProblemCategory.API_KEY: "🔑 API Key 问题",
    ProblemCategory.DEPENDENCY: "📦 依赖问题",
    ProblemCategory.MCP: "🖥️  MCP 配置",
    ProblemCategory.DATA_SOURCE: "📊 数据源问题",
    ProblemCategory.OK: "✅ 无问题",
}


def print_diagnostic(result: DiagnosticResult, compact: bool = False) -> None:
    width = 72
    problems = result.problems
    platform = result.platform

    platform_labels = {
        "cursor": "Cursor",
        "claude_code": "Claude Code",
        "codex": "VS Code / Codex",
        "vscode": "VS Code",
        "unknown": "未知平台",
    }
    plat_label = platform_labels.get(platform, platform)

    print()
    print(bold(cyan("═" * width)))
    print(bold(cyan("║")) + f"{' 系统诊断报告 v2.0 '.center(width - 4)}".center(width - 4) + bold(cyan(" ║")))
    print(bold(cyan("║")) + f"{' 论文-研报工作流 · FinResearch Agent '.center(width - 4)}".center(width - 4) + bold(cyan(" ║")))
    print(bold(cyan("═" * width)))
    print()
    print(f"  时间:    {dim(result.timestamp)}")
    print(f"  平台:    {cyan(plat_label)}")
    if result.verify_mode:
        print(f"  模式:    {yellow('深度验证 (--verify)')}")
    else:
        print(f"  模式:    {dim('基础检查')}")
    print(f"  MCP:     {cyan(f'{result.mcp_enabled_count} 个已启用')}" + (f" | {green(f'{result.mcp_verified_count} 个已验证')} " if result.mcp_verified_count > 0 else ""))
    print(f"  LLM:     {result.llm_status}")
    print()

    if not problems:
        print(bold(green("  ✅ 系统完全就绪，所有工具正常工作")))
        print()
        print("  可以直接开始研究工作。")
        print()
        print(bold(cyan("═" * width)))
        print()
        return

    groups = _group_by_category(problems)

    if compact:
        print(bold("  问题清单（按类别）:"))
        print()
        for cat, items in groups.items():
            icon = _CAT_LABELS.get(cat, cat.value)
            print(f"  {icon} × {len(items)}")
            for item in items:
                sev_icon = red("●") if item.severity == "high" else yellow("○")
                print(f"    {sev_icon} {item.name_zh}: {item.message[:50]}")
        print()
        return

    for cat, items in groups.items():
        cat_label = _CAT_LABELS.get(cat, cat.value)
        print(bold(yellow(f"  ┄┄┄ {cat_label} ┄┄┄")))
        for item in items:
            sev_icon = red("🔴 高") if item.severity == "high" else yellow("🟡 中") if item.severity == "medium" else dim("⚪ 低")
            print()
            print(f"    {sev_icon} {bold(item.name_zh)}")
            print(f"       {item.message}")
            for step in item.fix_steps:
                if step.startswith("【"):
                    print(f"       {bold(step)}")
                elif step.startswith("1.") or step.startswith("运行:"):
                    print(f"       {step}")
                else:
                    print(f"       {dim(step)}")
        print()

    if result.recommendations:
        print(bold(yellow("  ┄┄┄ 行动建议 ┄┄┄")))
        for rec in result.recommendations:
            print(f"  {rec}")
        print()

    print(bold(cyan("─" * width)))
    if result.system_ready:
        print(f"  {green('✅ 系统就绪')}，可以开始研究工作。")
        print(f"  {dim('（LLM 可用，核心依赖已安装）')}")
    else:
        reasons = []
        if not result.llm_available:
            reasons.append("LLM 不可用")
        if any(p.category == ProblemCategory.DEPENDENCY and p.severity == "high" for p in problems):
            reasons.append("核心依赖缺失")
        reasons_str = "，".join(reasons) if reasons else "部分工具有问题"
        print(f"  {yellow('⚠️  系统部分就绪')}，{reasons_str}。")
        print(f"  {dim('按上述步骤修复问题后即可开始研究')}")
    print()
    print(bold(cyan("═" * width)))
    print()
    print(dim(f"  基础检查: python scripts/health_check.py"))
    print(dim(f"  深度验证: python scripts/health_check.py --verify"))
    print(dim(f"  JSON 输出: python scripts/health_check.py --json 或 --verify --json"))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="论文-研报工作流 · 系统诊断 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/health_check.py              # 彩色完整报告（基础检查）
  python scripts/health_check.py --json       # JSON 输出（基础）
  python scripts/health_check.py --compact    # 紧凑摘要
  python scripts/health_check.py --verify     # 深度验证（MCP握手+LLM真实调用）
  python scripts/health_check.py --verify --json  # 深度验证+JSON
        """,
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--compact", action="store_true", help="紧凑摘要")
    parser.add_argument("--verify", action="store_true", help="深度验证（LLM 真实调用 + MCP stdio 握手，耗时约 30 秒）")
    args = parser.parse_args()

    result = run_diagnostic(verify=args.verify)

    if args.json:
        print(result.to_json())
    else:
        print_diagnostic(result, compact=args.compact)


if __name__ == "__main__":
    main()
