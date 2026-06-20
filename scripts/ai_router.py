#!/usr/bin/env python3
"""
AI 路由核心 v2.0
=================
多模型全备选路由引擎。

架构原则：
  1. 每个任务类型有最优模型优先级列表
  2. 所有模型互为备选（DeepSeek / GPT / Gemini / Claude / Kimi / Qwen / MiniMax / 本地）
  3. 按优先级尝试直到成功，保证最高可用性
  4. 任务类型覆盖：研究/写作/代码/数据/翻译/推理/金融/文献

模型层（2026年5月最新）：
  DeepSeek V4 Flash  — 快速通用，中文最优，1M context
  DeepSeek V4 Pro   — 深度推理，编程最强，1.6T/49B，1M context
  DeepSeek R1       — 数学/复杂推理
  GPT-5.5          — 英文写作/翻译（Relay中转）
  Claude Sonnet 4.7— 英文复杂分析（Relay中转）
  Claude Opus 4.7  — 顶级推理（Relay中转）
  Gemini 3.5-Flash— 快速推理/数学（Relay中转）
  Kimi K2.5        — 长文档分析（Relay中转）
  Qwen 3.6-35B    — 编程/多语言（Relay中转，廉价）
  GLM-5.1         — 结构化输出（Relay中转）
  MiniMax M2.5    — 工作流自动化（Relay中转）
  本地（Ollama）   — 无网络时最后兜底

使用示例：
  from scripts.ai_router import AI, Task

  # 自动路由（最优模型）
  result = AI.chat("分析茅台财务数据", task=Task.DATA_ANALYSIS)

  # 指定模型
  result = AI.chat("写英文摘要", model="claude-sonnet")

  # 查看状态
  print(AI.status())
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Bootstrap sys.path so `python scripts/ai_router.py` works
# without requiring `pip install -e .` first.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import openai
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

_log = logging.getLogger("ai_router")


# ═══════════════════════════════════════════════════════════════════════
# LLM 调用结果
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LLMCallResult:
    """OllamaProvider 专用结果封装（兼容 AIRouter.AIResult）。"""
    content: str
    model: str
    provider: str
    latency_ms: float
    tokens_used: int = 0
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# 密钥加载（macOS Keychain 优先）
# ═══════════════════════════════════════════════════════════════════════

def _get_from_keychain(service: str, account: str) -> str | None:
    """从 macOS Keychain 读取密钥。"""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service,
             "-a", account, "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:  # noqa: S110
        pass
    return None


_KEYCHAIN_MAP = {
    "DEEPSEEK_API_KEY":  ("论文工作流", "DEEPSEEK_API_KEY"),
    "RELAY_API_KEY":     ("论文工作流", "RELAY_API_KEY"),
    "GEMINI_API_KEY":    ("论文工作流", "GEMINI_API_KEY"),
    "KIMI_API_KEY":     ("论文工作流", "KIMI_API_KEY"),
    "ZHIPU_API_KEY":    ("论文工作流", "ZHIPU_API_KEY"),
    "FRED_API_KEY":      ("论文工作流", "FRED_API_KEY"),
    "OPENAI_API_KEY":    ("论文工作流", "OPENAI_API_KEY"),
}


def _load_secrets():
    """优先从 Keychain 加载密钥，fallback 到 .env.local"""
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env.local", override=False)

    for env_name, (service, account) in _KEYCHAIN_MAP.items():
        value = _get_from_keychain(service, account)
        if value:
            os.environ[env_name] = value


_load_secrets()


# ═══════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════

CONFIG_DIR = Path(__file__).parent.parent / "config"


# ═══════════════════════════════════════════════════════════════════════
# 任务类型
# ═══════════════════════════════════════════════════════════════════════

class Task(Enum):
    """支持的任务类型。"""
    GENERAL        = "general"         # 通用对话
    RESEARCH      = "research"        # 研究分析
    CODE          = "code"            # 代码生成
    CODE_ANALYSIS = "code_analysis"   # 代码分析
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    MATH_REASONING= "math_reasoning" # 数学推理
    PAPER_CN      = "paper_cn"        # 中文论文
    PAPER_EN      = "paper_en"        # 英文论文
    REPORT_CN     = "report_cn"       # 中文研报
    TRANSLATION   = "translation"     # 翻译
    LITERATURE    = "literature"      # 文献检索
    FINANCIAL_DATA= "financial_data"   # 金融数据解读
    SENTIMENT     = "sentiment"       # 情感分析
    SIMPLE_QA     = "simple_qa"       # 简单问答


# ═══════════════════════════════════════════════════════════════════════
# 模型标识
# ═══════════════════════════════════════════════════════════════════════

class ModelKey(Enum):
    """所有可用模型的唯一标识。pool.get(key) 通过 key.value 查找 ModelPool 属性名。"""
    # ── DeepSeek 直连 ─────────────────────────────────────────
    DEEPSEEK_FLASH         = "deepseek_flash"          # V4 Flash：快速通用
    DEEPSEEK_PRO           = "deepseek_pro"            # V4 Pro：深度推理
    DEEPSEEK_R1            = "deepseek_r1"             # R1：数学推理
    # ── Relay — GPT 系列 ─────────────────────────────────────
    GPT_4O                 = "gpt_5_4_mini"                 # GPT-5.4-Mini：英文写作/翻译
    GPT_5_5_MINI           = "gpt_5_5_mini"           # GPT-5.5-Instant：快速廉价
    # ── Relay — Claude 系列 ──────────────────────────────────
    CLAUDE_OPUS            = "claude_opus"             # Claude 3 Opus：顶级推理
    CLAUDE_SONNET          = "claude_sonnet"           # Claude 3.5 Sonnet：英文分析
    # ── Relay — DeepSeek ────────────────────────────
    DEEPSEEK_V4_PRO_RELAY  = "deepseek_v4_pro_relay"  # DeepSeek-V4-Pro via Relay
    # ── Relay — Gemini（暂禁用） ───────────────────
    GEMINI_20_FLASH        = "gemini_20_flash"        # Gemini 2.0-Flash（暂禁用）
    # ── Relay — 其他 ─────────────────────────────────────────
    KIMI                   = "kimi"                   # Kimi K2.5：长文档
    QWEN                   = "qwen"                   # Qwen 2.5-14B：编程/多语言
    GLM                    = "glm"                    # GLM-5.1：结构化输出
    MINIMAX                = "minimax"                # MiniMax M2.5：工作流
    # ── 本地模型 ───────────────────────────────────────────────
    LOCAL_OLLAMA           = "local_ollama"           # Ollama 本地模型


# ═══════════════════════════════════════════════════════════════════════
# 模型配置
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ModelConfig:
    """单个模型配置。"""
    provider: str           # deepseek | openai | gemini | local
    model_id: str          # API模型名
    api_key: str
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.7
    timeout: int = 120
    # 元信息
    display_name: str = ""       # 显示名
    strength: str = ""           # 主要优势
    context_window: int = 128_000 # 上下文窗口


@dataclass
class ModelPool:
    """所有模型的配置池。"""
    # DeepSeek 直连
    deepseek_flash:          ModelConfig | None = None
    deepseek_pro:            ModelConfig | None = None
    deepseek_r1:             ModelConfig | None = None
    # Relay — GPT
    gpt_5_4_mini:                 ModelConfig | None = None
    gpt_5_5_mini:            ModelConfig | None = None
    # Relay — Claude
    claude_opus:             ModelConfig | None = None
    claude_sonnet:            ModelConfig | None = None
    # Relay — DeepSeek
    deepseek_v4_pro_relay:   ModelConfig | None = None  # DeepSeek-V4-Pro via Relay
    # Relay — Gemini（暂禁用）
    gemini_20_flash:         ModelConfig | None = None
    # Relay — 其他
    kimi:                    ModelConfig | None = None
    qwen:                    ModelConfig | None = None
    glm:                     ModelConfig | None = None
    minimax:                 ModelConfig | None = None
    # 本地
    local_ollama:            ModelConfig | None = None

    def get(self, key: ModelKey) -> ModelConfig | None:
        return getattr(self, key.value, None)

    def available_models(self) -> list[ModelKey]:
        """返回所有配置了的模型。"""
        return [k for k in ModelKey if self.get(k) is not None]


# ═══════════════════════════════════════════════════════════════════════
# 任务 → 模型优先级路由表
# ═══════════════════════════════════════════════════════════════════════

# 每个任务的最优模型优先级列表（第一个可用模型被使用）
_TASK_ROUTING: dict[Task, list[ModelKey]] = {
    # ── 通用 ─────────────────────────────────────────────────
    Task.GENERAL: [
        ModelKey.DEEPSEEK_FLASH,   # 速度快，中文好
        ModelKey.GPT_5_5_MINI,           # 英文强
        ModelKey.CLAUDE_SONNET,    # 分析强
        ModelKey.GEMINI_20_FLASH,  # 快速
    ],

    # ── 研究/分析 ─────────────────────────────────────────────
    Task.RESEARCH: [
        ModelKey.DEEPSEEK_FLASH,   # 中文研究分析
        ModelKey.CLAUDE_OPUS,      # 顶级分析
        ModelKey.DEEPSEEK_PRO,     # 深度推理
        ModelKey.GPT_4O,      # 英文分析
    ],

    # ── 代码 ─────────────────────────────────────────────────
    Task.CODE: [
        ModelKey.DEEPSEEK_FLASH,   # 速度快，代码能力强
        ModelKey.QWEN,             # Qwen编程强，廉价
        ModelKey.DEEPSEEK_PRO,     # 深度编程
        ModelKey.CLAUDE_OPUS,      # 顶级编程
    ],

    Task.CODE_ANALYSIS: [
        ModelKey.DEEPSEEK_PRO,    # 深度代码分析
        ModelKey.CLAUDE_OPUS,      # 顶级分析
        ModelKey.DEEPSEEK_FLASH,
        ModelKey.QWEN,
    ],

    # ── 数据分析 ───────────────────────────────────────────────
    Task.DATA_ANALYSIS: [
        ModelKey.DEEPSEEK_PRO,     # 深度推理分析
        ModelKey.DEEPSEEK_R1,      # 推理专用
        ModelKey.CLAUDE_OPUS,      # 顶级分析
        ModelKey.GPT_4O,
    ],

    # ── 数学推理 ───────────────────────────────────────────────
    Task.MATH_REASONING: [
        ModelKey.DEEPSEEK_R1,      # 数学专用
        ModelKey.DEEPSEEK_PRO,     # 通用推理
        ModelKey.GEMINI_20_FLASH,  # 快速推理
        ModelKey.CLAUDE_OPUS,      # 顶级推理
    ],

    # ── 写作 ─────────────────────────────────────────────────
    Task.PAPER_CN: [
        ModelKey.DEEPSEEK_FLASH,   # 中文写作最优
        ModelKey.DEEPSEEK_PRO,     # 深度写作
        ModelKey.CLAUDE_SONNET,    # 英文思维可辅助
    ],

    Task.PAPER_EN: [
        ModelKey.GPT_4O,      # 英文论文最强
        ModelKey.CLAUDE_OPUS,     # 顶级英文
        ModelKey.GPT_5_5_MINI,          # 英文写作
        ModelKey.DEEPSEEK_FLASH,  # 备用
    ],

    Task.REPORT_CN: [
        ModelKey.DEEPSEEK_FLASH,   # 中文研报
        ModelKey.DEEPSEEK_PRO,
    ],

    # ── 翻译 ─────────────────────────────────────────────────
    Task.TRANSLATION: [
        ModelKey.GPT_4O,      # 翻译最强
        ModelKey.CLAUDE_SONNET,   # 精确翻译
        ModelKey.DEEPSEEK_FLASH,  # 中文辅助
        ModelKey.MINIMAX,         # 工作流翻译
    ],

    # ── 文献 ─────────────────────────────────────────────────
    Task.LITERATURE: [
        ModelKey.DEEPSEEK_FLASH,   # 文献检索中文
        ModelKey.GPT_5_5_MINI,          # 英文文献分析
        ModelKey.GEMINI_20_FLASH,  # 快速检索
    ],

    # ── 金融数据 ──────────────────────────────────────────────
    Task.FINANCIAL_DATA: [
        ModelKey.DEEPSEEK_PRO,    # 金融分析深度
        ModelKey.DEEPSEEK_FLASH,  # 快速解读
        ModelKey.GPT_5_5_MINI,
        ModelKey.CLAUDE_SONNET,
    ],

    # ── 情感分析 ──────────────────────────────────────────────
    Task.SENTIMENT: [
        ModelKey.DEEPSEEK_FLASH,   # 快速情感分析
        ModelKey.GPT_5_5_MINI,          # 英文情感
        ModelKey.GLM,             # 结构化情感
        ModelKey.MINIMAX,
    ],

    # ── 简单问答 ─────────────────────────────────────────────
    Task.SIMPLE_QA: [
        ModelKey.DEEPSEEK_FLASH,   # 快速直接
        ModelKey.GEMINI_20_FLASH,  # 极快
        ModelKey.MINIMAX,         # 廉价
        ModelKey.QWEN,
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# Ollama 本地模型 Provider
# ═══════════════════════════════════════════════════════════════════════

class OllamaProvider:
    """Ollama 本地模型 Provider，支持自动数据脱敏和离线降级。"""

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        sanitize_data: bool | None = None,
    ):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        timeout_env = os.getenv("OLLAMA_TIMEOUT")
        self.timeout = timeout if timeout is not None else (
            float(timeout_env) if timeout_env else 120.0
        )
        sanitize_env = os.getenv("OLLAMA_SANITIZE_DATA")
        if sanitize_data is not None:
            self.sanitize_data = sanitize_data
        elif sanitize_env is not None:
            self.sanitize_data = sanitize_env.lower() == "true"
        else:
            self.sanitize_data = True
        self._client = None

    def _get_client(self):
        """Lazy-load httpx client."""
        if self._client is None:
            import httpx
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def is_available(self) -> bool:
        """检查 Ollama 服务是否可用。"""
        try:
            client = self._get_client()
            resp = client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """列出可用的 Ollama 模型。"""
        try:
            client = self._get_client()
            resp = client.get("/api/tags")
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
            return []
        except Exception:
            return []

    def chat(self, messages: list[dict], **kwargs) -> LLMCallResult:
        """发送聊天请求到 Ollama。"""
        import httpx

        sanitized = self._sanitize_messages(messages) if self.sanitize_data else messages

        payload = {
            "model": self.model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in sanitized],
            "stream": False,
        }
        options = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if options:
            payload["options"] = options

        try:
            client = self._get_client()
            resp = client.post("/api/chat", json=payload)
            if resp.status_code != 200:
                return LLMCallResult(
                    content=f"[Ollama Error: HTTP {resp.status_code}]",
                    model=self.model,
                    provider="ollama",
                    latency_ms=resp.elapsed.total_seconds() * 1000,
                    tokens_used=0,
                    error=f"HTTP {resp.status_code}",
                )

            data = resp.json()
            content = data.get("message", {}).get("content", "")
            prompt_tokens = sum(len(m["content"]) // 4 for m in sanitized)
            completion_tokens = len(content) // 4

            return LLMCallResult(
                content=content,
                model=self.model,
                provider="ollama",
                latency_ms=resp.elapsed.total_seconds() * 1000,
                tokens_used=prompt_tokens + completion_tokens,
            )
        except httpx.ConnectError:
            return LLMCallResult(
                content=f"[Ollama Connection Error: Server not running at {self.base_url}]",
                model=self.model,
                provider="ollama",
                latency_ms=0,
                tokens_used=0,
                error="connection_failed",
            )
        except Exception as e:
            return LLMCallResult(
                content=f"[Ollama Error: {e}]",
                model=self.model,
                provider="ollama",
                latency_ms=0,
                tokens_used=0,
                error=str(e),
            )

    def _sanitize_messages(self, messages: list[dict]) -> list[dict]:
        """移除敏感数据，防止本地模型意外记录敏感信息。"""
        sanitized = []
        for msg in messages:
            content = msg.get("content", "")
            content = re.sub(
                r'api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-]{20,}',
                "[REDACTED API KEY]",
                content,
            )
            # apiKey: KEYVALUE (unquoted, greedy up to whitespace)
            content = re.sub(
                r"apiKey:\s*\S{20,}",
                "apiKey: [REDACTED API KEY]",
                content,
            )
            content = re.sub(
                r"Bearer\s+[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
                "[REDACTED TOKEN]",
                content,
            )
            content = re.sub(r"/[^\"\'\n]+", "[FILE PATH]", content)
            content = re.sub(
                r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP ADDRESS]", content
            )
            sanitized.append({**msg, "content": content})
        return sanitized


# ═══════════════════════════════════════════════════════════════════════
# 缓存层
# ═══════════════════════════════════════════════════════════════════════

class CacheManager:
    """基于内容哈希的简单缓存。"""

    def __init__(self, cache_dir: str = ".cache/ai_router", max_age_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict] = {}
        self._cleanup(max_age_days)

    def _cleanup(self, max_age_days: int):
        if max_age_days <= 0:
            return
        cutoff = time.time() - max_age_days * 86400
        for f in self.cache_dir.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass

    def _hash(self, content: str, model: str) -> str:
        return hashlib.sha256(f"{model}:{content}".encode()).hexdigest()[:16]

    def get(self, content: str, model: str) -> str | None:
        key = self._hash(content, model)
        if key in self._memory:
            return self._memory[key].get("response")
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                self._memory[key] = cached
                return cached.get("response")
            except Exception:
                return None
        return None

    def set(self, content: str, model: str, response: str, task: str):
        key = self._hash(content, model)
        entry = {
            "content_hash": key,
            "model": model,
            "task": task,
            "response": response,
            "timestamp": time.time(),
        }
        self._memory[key] = entry
        cache_file = self.cache_dir / f"{key}.json"
        try:
            cache_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
        except Exception:  # noqa: S110
            pass


# ═══════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════

def _resolve_env(value):
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value


def load_llm_config() -> dict:
    config_path = CONFIG_DIR / "llm_config.json"
    if not config_path.exists():
        return {}

    def _resolve_dict(d: dict) -> dict:
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = _resolve_dict(v)
            elif isinstance(v, str) and v.startswith("$"):
                result[k] = os.environ.get(v[1:], "")
            else:
                result[k] = v
        return result

    return _resolve_dict(json.loads(config_path.read_text(encoding="utf-8")))


def build_model_pool() -> ModelPool:
    """
    根据 llm_config.json 构建完整模型池。

    每个模型从对应配置节读取 model_id（来自 _model_ids 映射表），支持
    DeepSeek / Relay(OpenAI兼容) / Gemini / 本地。
    不再硬编码 model_id 字符串，确保配置与代码严格同步。
    """
    cfg = load_llm_config()
    pool = ModelPool()

    # ── model_id 映射表（统一来源） ─────────────────────────────────────────
    # pool 属性名 → API model_id
    _ids: dict[str, str] = cfg.get("_model_ids", {})
    _get_id = lambda key, default: _ids.get(key, default)

    # ── DeepSeek 直连 ──────────────────────────────────────
    if "deepseek" in cfg:
        ds = cfg["deepseek"]
        defaults = ds.get("defaults", {})
        ds_key = ds.get("api_key", "")

        if ds_key and not ds_key.startswith("YOUR_"):
            # model_id 从 _model_ids 读取（默认为 deepseek-v4-flash）
            pool.deepseek_flash = ModelConfig(
                provider="deepseek",
                model_id=_get_id("deepseek_flash", "deepseek-v4-flash"),
                api_key=ds.get("api_key", ""),
                base_url=ds.get("base_url"),
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="DeepSeek V4 Flash",
                strength="快速通用，中文最优，1M context",
                context_window=1_000_000,
            )
            pool.deepseek_pro = ModelConfig(
                provider="deepseek",
                model_id=_get_id("deepseek_pro", "deepseek-v4-pro"),
                api_key=ds.get("api_key", ""),
                base_url=ds.get("base_url"),
                max_tokens=16384,
                temperature=0.5,
                timeout=300,
                display_name="DeepSeek V4 Pro",
                strength="深度推理，编程最强，1.6T/49B",
                context_window=1_000_000,
            )
            pool.deepseek_r1 = ModelConfig(
                provider="deepseek",
                model_id=_get_id("deepseek_r1", "deepseek-r1"),
                api_key=ds.get("api_key", ""),
                base_url=ds.get("base_url"),
                max_tokens=16384,
                temperature=0.6,
                timeout=300,
                display_name="DeepSeek R1",
                strength="数学/复杂推理专用",
                context_window=1_000_000,
            )

    # ── Relay 中转 API (Relay — 2026-05-29 实测验证) ──────────────
    if "relay" in cfg:
        relay = cfg["relay"]
        relay_key = relay.get("api_key", os.environ.get("RELAY_API_KEY", ""))
        relay_url = relay.get("base_url", "https://api.b.ai/v1")
        defaults = relay.get("defaults", {})

        if relay_key and not relay_key.startswith("YOUR_"):
            # GPT-5.4-Mini — ✅ 实测可用
            pool.gpt_5_4_mini = ModelConfig(
                provider="openai",
                model_id=_get_id("gpt_5_4_mini", "gpt-4o"),
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="GPT-5.4-Mini (via Relay)",
                strength="英文写作/翻译，✅实测可用",
                context_window=128_000,
            )
            # GPT-5.5-Instant — ✅ 实测可用
            pool.gpt_5_5_mini = ModelConfig(
                provider="openai",
                model_id=_get_id("gpt_5_5_mini", "gpt-4o-mini"),
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="GPT-5.5-Instant (via Relay)",
                strength="快速英文，✅实测可用",
                context_window=128_000,
            )
            # Claude Sonnet 4.6 — ✅ 实测可用
            pool.claude_sonnet = ModelConfig(
                provider="openai",
                model_id=_get_id("claude_sonnet", "claude-sonnet-4-20250514"),
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="Claude Sonnet 4.6 (via Relay)",
                strength="英文分析/翻译，✅实测可用",
                context_window=200_000,
            )
            # Claude Opus 4.7 — ✅ 实测可用
            pool.claude_opus = ModelConfig(
                provider="openai",
                model_id=_get_id("claude_opus", "claude-opus-3-20240229"),
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=0.5,
                timeout=180,
                display_name="Claude Opus 4.7 (via Relay)",
                strength="顶级推理，✅实测可用",
                context_window=200_000,
            )
            # DeepSeek-V4-Pro via Relay — ✅ 实测可用
            # 【修复】旧版误用 gemini_25_flash 变量名，现改为 deepseek_v4_pro_relay
            pool.deepseek_v4_pro_relay = ModelConfig(
                provider="openai",
                model_id=_get_id("deepseek_v4_pro_relay", "deepseek-v4-pro"),
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=180,
                display_name="DeepSeek-V4-Pro (via Relay)",
                strength="深度推理，✅实测可用",
                context_window=1_000_000,
            )
            # GLM-5.1 — model_id 从 _model_ids["glm"] 读取（relay.models 的值是 description 而非 model_id）
            glm_id = _get_id("glm", "glm-4")
            pool.glm = ModelConfig(
                provider="openai",
                model_id=glm_id,
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="GLM-5.1 (via Relay)",
                strength="结构化输出",
                context_window=128_000,
            )
            # Gemini — ❌ 返回空内容，禁用（保留 slot 供将来启用）
            # pool.gemini_20_flash = ModelConfig(
            #     provider="openai", model_id=_get_id("gemini_20_flash", "gemini-3.5-flash"),
            #     api_key=relay_key, base_url=relay_url, ...
            # )
            # Kimi K2.5 — model_id 从 _model_ids["kimi"] 读取（relay.models 的值是 description 而非 model_id）
            kimi_id = _get_id("kimi", "kimi")
            pool.kimi = ModelConfig(
                provider="openai",
                model_id=kimi_id,
                api_key=relay_key, base_url=relay_url,
                max_tokens=defaults.get("max_tokens", 8192),
                temperature=defaults.get("temperature", 0.7),
                timeout=120,
                display_name="Kimi K2.5 (via Relay)",
                strength="长文档分析",
                context_window=200_000,
            )

    # ── 本地 Ollama（无 API Key，固定配置） ───────────────────────────────
    # model_id 从 _model_ids["local_ollama"] 读取
    pool.local_ollama = ModelConfig(
        provider="openai",
        model_id=_get_id("local_ollama", "llama3.3"),
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        max_tokens=4096,
        temperature=0.7,
        timeout=60,
        display_name="Ollama 本地",
        strength="无网络时最后兜底，完全免费",
        context_window=128_000,
    )

    return pool


# ═══════════════════════════════════════════════════════════════════════
# LLM 桥接器
# ═══════════════════════════════════════════════════════════════════════

class LLMBridge:
    """统一调用所有模型。"""

    def __init__(self, pool: ModelPool):
        self.pool = pool
        self._clients: dict[ModelKey, openai.OpenAI] = {}
        self._init_clients()

    def _init_clients(self):
        """为所有配置了的模型初始化客户端。"""
        for key in ModelKey:
            cfg = self.pool.get(key)
            if cfg and cfg.api_key:
                try:
                    self._clients[key] = openai.OpenAI(
                        api_key=cfg.api_key,
                        base_url=cfg.base_url,
                        timeout=cfg.timeout,
                    )
                except Exception as exc:
                    _log.warning(
                        "[ModelPool._init_clients] OpenAI client init failed for %s: %s — "
                        "model will be unavailable",
                        key.name if hasattr(key, 'name') else key, exc
                    )

    def _get_client(self, key: ModelKey) -> openai.OpenAI | None:
        """获取对应模型的客户端。"""
        # 兼容旧别名
        legacy_map = {
            # DeepSeek
            "deepseek_flash": ModelKey.DEEPSEEK_FLASH,
            "deepseek_pro": ModelKey.DEEPSEEK_PRO,
            "deepseek_r1": ModelKey.DEEPSEEK_R1,
            "deepseek": ModelKey.DEEPSEEK_FLASH,
            "deepseek-chat": ModelKey.DEEPSEEK_FLASH,
            "deepseek-reasoner": ModelKey.DEEPSEEK_R1,
            # GPT
            "gpt5": ModelKey.GPT_4O,
            "gpt-4o": ModelKey.GPT_5_5_MINI,
            # Gemini（暂禁用）
            "gemini": ModelKey.GEMINI_20_FLASH,
            # 旧 gemini_25_flash 实际是 DeepSeek-V4-Pro via relay
            "gemini_25_flash": ModelKey.DEEPSEEK_V4_PRO_RELAY,
            # 其他
            "kimi": ModelKey.KIMI,
            # 旧 model_id 别名
            "gemini-3.5-flash": ModelKey.GEMINI_20_FLASH,
            "claude-sonnet": ModelKey.CLAUDE_SONNET,
            "claude-opus-4": ModelKey.CLAUDE_OPUS,
            "gpt-4o": ModelKey.GPT_4O,
            "gpt-4o-mini": ModelKey.GPT_5_5_MINI,
        }
        if isinstance(key, str):
            key = legacy_map.get(key, ModelKey(key))

        return self._clients.get(key)

    def _get_model_name(self, key: ModelKey) -> str:
        cfg = self.pool.get(key)
        if cfg:
            return cfg.model_id
        return key.value

    def call(
        self,
        model_key: ModelKey | str,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        """
        统一调用接口。

        Args:
            model_key: 模型标识
            messages: 消息列表
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出 token

        Returns:
            模型回复文本

        Raises:
            RuntimeError: 所有模型均调用失败
        """
        # 解析模型键
        if isinstance(model_key, str):
            legacy_map = {
                "deepseek_flash": ModelKey.DEEPSEEK_FLASH,
                "deepseek_pro": ModelKey.DEEPSEEK_PRO,
                "deepseek_r1": ModelKey.DEEPSEEK_R1,
                "gpt5": ModelKey.GPT_4O,
                "gemini": ModelKey.GEMINI_20_FLASH,
                "kimi": ModelKey.KIMI,
                "deepseek": ModelKey.DEEPSEEK_FLASH,
                "deepseek-chat": ModelKey.DEEPSEEK_FLASH,
                "deepseek-reasoner": ModelKey.DEEPSEEK_R1,
                "gpt-4o": ModelKey.GPT_5_5_MINI,
                # "gemini-3.5-flash": ModelKey.GEMINI_20_FLASH,  # Relay returns empty, disabled
                "claude-sonnet": ModelKey.CLAUDE_SONNET,
                "claude-opus": ModelKey.CLAUDE_OPUS,
                "claude-sonnet": ModelKey.CLAUDE_SONNET,
                "claude-opus": ModelKey.CLAUDE_OPUS,
                "local_ollama": ModelKey.LOCAL_OLLAMA,
            }
            resolved_key = legacy_map.get(model_key)
            if resolved_key is None:
                try:
                    resolved_key = ModelKey(model_key)
                except ValueError:
                    raise RuntimeError(f"未知模型标识: {model_key}")
            model_key = resolved_key

        client = self._get_client(model_key)
        if client is None:
            raise RuntimeError(
                f"模型 {model_key.value} 未配置或缺少 API Key。"
                f"请检查 config/llm_config.json"
            )

        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        model_name = self._get_model_name(model_key)

        # 部分模型不支持 temperature 参数（如 Claude Opus 4.7 via Relay）
        _no_temp_models = {"claude-opus-3-20240229", "claude-sonnet-4-20250514"}
        create_kwargs = {"model": model_name, "messages": all_messages, "max_tokens": max_tokens}
        if model_name not in _no_temp_models:
            create_kwargs["temperature"] = temperature

        resp = client.chat.completions.create(**create_kwargs)

        content = resp.choices[0].message.content
        if not content or not content.strip():
            # gemini-3.5-flash 等模型可能首次返回空，重试一次
            resp2 = client.chat.completions.create(**create_kwargs)
            content = resp2.choices[0].message.content
            if not content or not content.strip():
                raise RuntimeError(f"模型 {model_name} 返回了空内容")
        return content

    def supports_streaming(self, model_key: ModelKey | str) -> bool:
        """Check if a model supports streaming."""
        try:
            client = self._get_client(model_key)
            return client is not None
        except Exception:
            return False

    def stream(
        self,
        model_key: ModelKey | str,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ):
        """
        Stream response chunks from the model using token-by-token iteration.

        Args:
            model_key: Model identifier
            messages: Message list
            system_prompt: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum output tokens

        Yields:
            str: Text chunks as they arrive from the model

        Raises:
            RuntimeError: If streaming is not supported or call fails
        """
        if isinstance(model_key, str):
            legacy_map = {
                "deepseek_flash": ModelKey.DEEPSEEK_FLASH,
                "deepseek_pro": ModelKey.DEEPSEEK_PRO,
                "deepseek_r1": ModelKey.DEEPSEEK_R1,
                "gpt5": ModelKey.GPT_4O,
                "gemini": ModelKey.GEMINI_20_FLASH,
                "kimi": ModelKey.KIMI,
                "deepseek": ModelKey.DEEPSEEK_FLASH,
                "deepseek-chat": ModelKey.DEEPSEEK_FLASH,
                "deepseek-reasoner": ModelKey.DEEPSEEK_R1,
                "gpt-4o": ModelKey.GPT_5_5_MINI,
                # "gemini-3.5-flash": ModelKey.GEMINI_20_FLASH,  # Relay returns empty, disabled
                "claude-sonnet": ModelKey.CLAUDE_SONNET,
                "claude-opus": ModelKey.CLAUDE_OPUS,
                "claude-sonnet": ModelKey.CLAUDE_SONNET,
                "claude-opus": ModelKey.CLAUDE_OPUS,
                "local_ollama": ModelKey.LOCAL_OLLAMA,
            }
            resolved_key = legacy_map.get(model_key)
            if resolved_key is None:
                try:
                    resolved_key = ModelKey(model_key)
                except ValueError:
                    raise RuntimeError(f"Unknown model identifier: {model_key}")
            model_key = resolved_key

        client = self._get_client(model_key)
        if client is None:
            raise RuntimeError(
                f"Model {model_key.value} not configured or missing API Key."
            )

        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        model_name = self._get_model_name(model_key)

        try:
            stream_resp = client.chat.completions.create(
                model=model_name,
                messages=all_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as exc:
            raise RuntimeError(f"Streaming failed for {model_name}: {exc}") from exc



# ═══════════════════════════════════════════════════════════════════════
# 任务分类器
# ═══════════════════════════════════════════════════════════════════════

class TaskClassifier:
    """
    根据用户输入自动判断任务类型。
    优先级：精确匹配关键词 > 正则模式匹配 > 默认通用。
    """

    KEYWORD_PATTERNS: dict[Task, list[str]] = {
        Task.RESEARCH: ["研究", "分析", "调研", "对比", "评估", "趋势", "前景"],
        Task.LITERATURE: ["文献", "论文检索", "搜论文", "查找文献", "academic", "paper search"],
        Task.CODE: ["写代码", "python", "代码", "script", "function", "def ", "class ", "import "],
        Task.CODE_ANALYSIS: ["这段代码", "解释代码", "代码分析", "debug", "优化代码"],
        Task.DATA_ANALYSIS: ["数据分析", "数据处理", "统计", "回归", "可视化", "chart", "plot"],
        Task.MATH_REASONING: ["证明", "推导", "数学", "计算", "math", "calculate"],
        Task.PAPER_CN: ["写论文", "中文论文", "中文学术"],
        Task.PAPER_EN: ["write a paper", "英文论文", "english paper", "ACL", "ICML", "NeurIPS", "IEEE"],
        Task.REPORT_CN: ["研报", "行研", "行业报告", "研究报告中", "研报框架"],
        Task.TRANSLATION: ["翻译", "translate to", "中译英", "英译中"],
        Task.FINANCIAL_DATA: ["财务数据", "营收", "利润", "ROE", "估值", "股价", "EPS"],
        Task.SENTIMENT: ["情感分析", "sentiment", "情绪"],
        Task.SIMPLE_QA: ["是什么", "什么是", "怎么用", "介绍一下"],
    }

    REGEX_PATTERNS: list[tuple[re.Pattern, Task]] = [
        (re.compile(r"帮我分析.*(?:财务|营收|利润|ROE|估值|股价)"), Task.DATA_ANALYSIS),
        (re.compile(r"写.*(?:代码|python|javascript|script)"), Task.CODE),
        (re.compile(r"解释.*代码|这段代码.*作用|debug"), Task.CODE_ANALYSIS),
        (re.compile(r"写.*(?:论文|paper).*英文|英.*(?:论文|paper)", re.I), Task.PAPER_EN),
        (re.compile(r"翻译.*(?:中.*英|英.*中)", re.I), Task.TRANSLATION),
        (re.compile(r"证明.*(?:数学|公式)|推导.*(?:数学|公式)", re.I), Task.MATH_REASONING),
        (re.compile(r"搜.*(?:文献|论文)|找.*(?:文献|论文)|(?:文献|论文).*检索"), Task.LITERATURE),
        (re.compile(r"生成.*(?:研报|行研|行业.*报告)"), Task.REPORT_CN),
    ]

    def classify(self, user_input: str) -> Task:
        """根据输入内容自动分类任务。"""
        # 优先级1：正则精确匹配
        for pattern, task in self.REGEX_PATTERNS:
            if pattern.search(user_input):
                return task

        # 优先级2：关键词匹配（多命中取最匹配）
        scores: dict[Task, int] = {}
        for task, keywords in self.KEYWORD_PATTERNS.items():
            score = sum(1 for kw in keywords if kw.lower() in user_input.lower())
            if score > 0:
                scores[task] = score

        if scores:
            return max(scores, key=scores.get)

        # 优先级3：长度启发式
        if len(user_input) < 50:
            return Task.SIMPLE_QA

        return Task.GENERAL


# ═══════════════════════════════════════════════════════════════════════
# AI 结果封装
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AIResult:
    """AI 调用的结果封装。"""
    response: str
    model_used: str           # 模型显示名
    model_key: str           # 模型标识
    task_type: str
    latency_ms: float
    cached: bool = False
    fallback_tried: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# AI 路由主类
# ═══════════════════════════════════════════════════════════════════════

class AIRouter:
    """
    多模型全备选路由主入口。

    核心逻辑：
      1. 确定任务类型（手动指定 / 自动分类）
      2. 获取该任务的模型优先级列表
      3. 按优先级尝试调用，直到成功
      4. 记录使用了哪个模型作为最终结果
    """

    def __init__(self, use_cache: bool = True):
        self._use_cache = use_cache
        self._pool: ModelPool | None = None
        self._bridge: LLMBridge | None = None
        self._cache: CacheManager | None = None
        self._classifier: TaskClassifier | None = None
        self._ollama: OllamaProvider | None = None
        self._initialized = False
        self._available: dict[str, str] = {}

    def _lazy_init(self):
        if self._initialized:
            return
        self._pool = build_model_pool()
        self._classifier = TaskClassifier()
        self._bridge = LLMBridge(self._pool)
        self._cache = CacheManager() if self._use_cache else None

        # Ollama Provider（仅当显式启用时）
        if os.getenv("OLLAMA_ENABLED", "false").lower() == "true":
            self._ollama = OllamaProvider()

        # 检查各模型可用状态
        for key in ModelKey:
            cfg = self._pool.get(key)
            if cfg:
                client = self._bridge._get_client(key)
                self._available[key.value] = (
                    f"✅ {cfg.display_name}" if client else "❌ 未配置"
                )
            else:
                self._available[key.value] = "❌ 未安装"

        self._initialized = True

    @property
    def pool(self) -> ModelPool:
        self._lazy_init()
        return self._pool

    @property
    def bridge(self) -> LLMBridge:
        self._lazy_init()
        return self._bridge

    @property
    def cache(self) -> CacheManager | None:
        self._lazy_init()
        return self._cache

    @property
    def classifier(self) -> TaskClassifier:
        self._lazy_init()
        return self._classifier

    @property
    def ollama(self) -> OllamaProvider | None:
        self._lazy_init()
        return self._ollama

    def status(self) -> dict[str, str]:
        """返回当前各模型的可用状态。"""
        self._lazy_init()
        return self._available.copy()

    def chat(
        self,
        user_input: str,
        task: Task | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AIResult:
        """
        主入口方法。

        调用优先级：
          1. model 参数 → 强制使用指定模型（无备选，仅一次调用）
          2. task 参数 → 按任务类型路由（按优先级列表尝试备选）
          3. 自动分类 → 根据内容判断任务类型

        Args:
            user_input: 用户输入
            task: 强制指定任务类型
            model: 强制指定模型（绕过路由）
            system_prompt: 额外系统提示词
            temperature: 生成温度
            max_tokens: 最大输出 token

        Returns:
            AIResult 对象
        """
        start = time.time()
        self._lazy_init()

        # Step 1：确定任务类型
        actual_task = task if task else self.classifier.classify(user_input)

        # Step 2：获取模型优先级列表
        if model:
            # 强制指定模型：直接调用，不走备选链
            model_key_str = model
            primary_keys: list[ModelKey | str] = [model]
        else:
            # 按任务路由
            model_keys = _TASK_ROUTING.get(actual_task, [ModelKey.DEEPSEEK_FLASH])
            # 过滤掉未配置的模型
            primary_keys = [
                k for k in model_keys
                if self._bridge._get_client(k) is not None
            ]
            # 如果过滤后为空，加入本地兜底
            if not primary_keys:
                primary_keys = [ModelKey.LOCAL_OLLAMA]

            # 始终在末尾追加本地兜底
            if ModelKey.LOCAL_OLLAMA not in primary_keys:
                primary_keys.append(ModelKey.LOCAL_OLLAMA)

            model_key_str = primary_keys[0].value if isinstance(primary_keys[0], ModelKey) else primary_keys[0]

        # Step 3：检查缓存
        cached_response = None
        if self.cache:
            cached_response = self.cache.get(user_input, model_key_str)

        if cached_response:
            return AIResult(
                response=cached_response,
                model_used=model_key_str,
                model_key=model_key_str,
                task_type=actual_task.value,
                latency_ms=(time.time() - start) * 1000,
                cached=True,
            )

        # Step 4：按优先级尝试调用（第一个成功即返回）
        messages = [{"role": "user", "content": user_input}]
        fallback_tried: list[str] = []
        last_error: Exception = None

        for mk in primary_keys:
            mk_str = mk.value if isinstance(mk, ModelKey) else mk
            fallback_tried.append(mk_str)

            try:
                response = self.bridge.call(
                    model_key=mk,
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # 成功：写入缓存并返回
                if self.cache:
                    self.cache.set(user_input, mk_str, response, actual_task.value)

                # 获取模型显示名
                cfg = self._pool.get(mk) if isinstance(mk, ModelKey) else None
                display_name = cfg.display_name if cfg else mk_str

                return AIResult(
                    response=response,
                    model_used=display_name,
                    model_key=mk_str,
                    task_type=actual_task.value,
                    latency_ms=(time.time() - start) * 1000,
                    cached=False,
                    fallback_tried=fallback_tried,
                )

            except Exception as exc:
                last_error = exc
                continue  # 尝试下一个模型

        # 最后尝试 Ollama Provider（如果启用）
        if self._ollama is not None:
            messages = [{"role": "user", "content": user_input}]
            result = self._ollama.chat(messages, temperature=temperature, max_tokens=max_tokens)
            if not result.error:
                return AIResult(
                    response=result.content,
                    model_used=f"Ollama ({self._ollama.model})",
                    model_key="ollama",
                    task_type=actual_task.value,
                    latency_ms=(time.time() - start) * 1000,
                    cached=False,
                    fallback_tried=fallback_tried + ["ollama"],
                )

        # 全部失败
        tried_str = " → ".join(fallback_tried)
        raise RuntimeError(
            f"所有模型均调用失败（尝试顺序：{tried_str}）。"
            f"最后错误：{last_error}"
        ) from last_error

    def clear_cache(self):
        """清空所有缓存。"""
        if self.cache:
            self.cache._memory.clear()
            for f in self.cache.cache_dir.glob("*.json"):
                try:
                    f.unlink()
                except OSError:
                    pass


# ═══════════════════════════════════════════════════════════════════════
# 便捷别名
# ═══════════════════════════════════════════════════════════════════════

AI = AIRouter(use_cache=True)


# ═══════════════════════════════════════════════════════════════════════
# 演示与调试
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  AI 路由核心 v2.0 — 多模型全备选")
    print("=" * 65)

    router = AIRouter(use_cache=True)

    # 状态检查
    print("\n[模型状态]")
    for key, status in router.status().items():
        print(f"  {key:25s} {status}")

    # 任务分类测试
    print("\n[任务分类测试]")
    test_inputs = [
        "帮我分析一下茅台2024年的财务数据",
        "写一段Python代码读取CSV文件",
        "写一篇关于深度学习在金融领域应用的英文论文",
        "翻译一下这段英文摘要",
        "什么是PEG估值法？",
        "帮我搜一下强化学习在量化交易中的文献",
        "生成一份光伏行业的研究报告框架",
        "证明傅里叶变换的逆定理",
        "用DID分析关税对出口的影响",
    ]
    for inp in test_inputs:
        task = router.classifier.classify(inp)
        keys = _TASK_ROUTING.get(task, [])
        primary = keys[0].value if keys else "unknown"
        print(f"  [{task.value:20s}] {primary:25s} | {inp[:35]}")

    # 实际调用测试
    print("\n[实际调用测试 — 简单问答]")
    try:
        test_call = router.chat(
            "用一句话解释什么是ROE（净资产收益率）",
            task=Task.SIMPLE_QA,
        )
        print(f"  模型: {test_call.model_used}")
        print(f"  任务: {test_call.task_type}")
        print(f"  缓存: {test_call.cached}")
        print(f"  耗时: {test_call.latency_ms/1000:.1f}s")
        if test_call.fallback_tried:
            print(f"  备选链: {' → '.join(test_call.fallback_tried)}")
        print(f"  回复: {test_call.response[:200]}")
    except Exception as e:
        print(f"  调用失败: {e}")
