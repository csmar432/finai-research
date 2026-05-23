#!/usr/bin/env python3
"""
AI 路由核心
===========
外部 AI 模型调度层，以 Cursor（本地 Claude）为默认，外部 API 仅作补充。

NOTE: This module is used by ToolSelector as the external AI fallback.
It is NOT the primary agent entry point — use scripts/agent.py instead.
The primary ResearchSession uses ToolSelector (scripts/core/tool_selector.py),
which delegates to this module when MCP tools or script tools are unavailable
or when a direct LLM call is needed (e.g., for context compression, evaluation).

架构说明：
  ┌─────────────────────────────────────────────┐
  │               Cursor（核心，优先）              │
  │  ┌─────────────────────────────────────────┐ │
  │  │  TaskClassifier  → 自动识别任务类型        │ │
  │  │  ModelRouter     → 分配最佳外部模型        │ │
  │  │  LLMBridge       → 调用外部 API           │ │
  │  └─────────────────────────────────────────┘ │
  │                    ↓                          │
  │         脚本/批处理 → 外部 AI API             │
  │
  使用原则：
    - Cursor Agent 直接调用本地 Claude，无需外部 API
    - 脚本批处理（batch_sentiment / generate_code 等）→ 外部 API（B.AI / DeepSeek）
    - Cursor 无法访问时（如终端运行脚本）→ B.AI → DeepSeek → 报错
  │
  外部 AI 角色（按实测可用性）：
    B.AI 中转（需 VPN）：gpt-5.5（代码/翻译） / claude-sonnet-4.6 / gemini-3.1-pro
    DeepSeek 直连（无需 VPN）：deepseek-chat → deepseek-v4-flash


使用方法：
  from scripts.ai_router import AI, Task

  # 简单调用（自动路由）
  result = AI.chat("帮我分析一下茅台的财务数据")

  # 指定任务类型（精确路由）
  result = AI.chat("写一篇关于AI的英文论文", task=Task.PAPER_EN)

  # 直接指定模型
  result = AI.chat("解释这个Python代码", model="gpt5")
"""

import json
import os
import time
import re
import hashlib
import warnings
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import openai
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# ── 密钥加载策略 ──────────────────────────────────────────────
# 优先级：Keychain（macOS系统密钥库）> .env.local > 环境变量
# Keychain 完全不写入磁盘，安全性最高。

def _get_from_keychain(service: str, account: str) -> Optional[str]:
    """从 macOS Keychain 读取密钥。失败返回 None。"""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service,
             "-a", account, "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None

# 定义密钥服务名称和账户名映射
_KEYCHAIN_MAP = {
    "B_AI_API_KEY":       ("论文工作流", "B_AI_API_KEY"),
    "DEEPSEEK_API_KEY":   ("论文工作流", "DEEPSEEK_API_KEY"),
    "FRED_API_KEY":       ("论文工作流", "FRED_API_KEY"),
    "ZHIPU_API_KEY":      ("论文工作流", "ZHIPU_API_KEY"),
}

def _load_secrets():
    """优先从 Keychain 加载密钥，fallback 到 .env.local"""
    # 1. 先加载 .env.local（备用）
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env.local", override=False)

    # 2. 从 Keychain 覆盖（优先）
    for env_name, (service, account) in _KEYCHAIN_MAP.items():
        value = _get_from_keychain(service, account)
        if value:
            os.environ[env_name] = value

_load_secrets()


# ─── 配置路径 ────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent.parent / "config"


# ─── 任务类型枚举 ────────────────────────────────────────

class Task(Enum):
    """支持的任务类型，对应不同的 AI 模型分配策略。"""
    RESEARCH       = "research"        # 研究分析 → DeepSeek V3
    LITERATURE     = "literature"      # 文献检索 → DeepSeek V3
    CODE           = "code"            # 代码生成 → GPT-5.5（B.AI）
    CODE_ANALYSIS  = "code_analysis"  # 代码分析 → GPT-5.5（B.AI）
    DATA_ANALYSIS  = "data_analysis"  # 数据分析 → GPT-5.5（B.AI）
    REPORT_CN      = "report_cn"       # 中文研报 → DeepSeek
    PAPER_CN       = "paper_cn"        # 中文论文 → DeepSeek
    PAPER_EN       = "paper_en"        # 英文论文 → GPT-5.5（B.AI）
    TRANSLATION    = "translation"     # 翻译       → GPT-5.5（B.AI）
    MATH_REASONING = "math_reasoning"  # 数学推理 → Gemini-3.1-Pro（B.AI）
    SIMPLE_QA      = "simple_qa"       # 简单问答 → DeepSeek V3
    GENERAL        = "general"         # 通用对话 → DeepSeek V3


# ─── 模型定义 ────────────────────────────────────────────

@dataclass
class ModelConfig:
    """单个模型的配置。"""
    provider: str          # openai | anthropic | deepseek
    model: str             # 模型名
    api_key: str           # API key（可为空，脚本会自动从 llm_config.json 读取）
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120


@dataclass
class ModelPool:
    """模型池，存储所有可用模型。"""
    deepseek: Optional[ModelConfig] = None
    deepseek_reasoner: Optional[ModelConfig] = None
    gpt5: Optional[ModelConfig] = None
    gemini: Optional[ModelConfig] = None
    kimi: Optional[ModelConfig] = None


# ─── 任务 → 模型路由表 ──────────────────────────────────

TASK_ROUTING = {
    # DeepSeek — 速度快、成本低，适合检索和中文写作
    Task.RESEARCH:       "deepseek",
    Task.LITERATURE:     "deepseek",
    Task.SIMPLE_QA:      "deepseek",
    Task.REPORT_CN:      "deepseek",
    Task.PAPER_CN:       "deepseek",
    # GPT-5.5（B.AI）— 代码/英文写作/翻译/数据分析
    Task.CODE:           "gpt5",
    Task.CODE_ANALYSIS:  "gpt5",
    Task.DATA_ANALYSIS:  "gpt5",
    Task.PAPER_EN:       "gpt5",
    Task.TRANSLATION:    "gpt5",
    # Gemini-3.1-Pro（B.AI）— 数学推理
    Task.MATH_REASONING: "gemini",
    # 默认兜底
    Task.GENERAL:        "deepseek",
}


# ─── 缓存层 ──────────────────────────────────────────────

class CacheManager:
    """
    基于内容哈希的简单缓存，避免重复请求。
    缓存策略：相同问题 + 相同模型 → 直接返回缓存结果。

    支持 TTL 清理：超过 max_age_days 的缓存文件会被自动删除。
    """

    def __init__(self, cache_dir: str = ".cache/ai_router", max_age_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, dict] = {}
        self._cleanup(max_age_days)

    def _cleanup(self, max_age_days: int):
        """删除超过 max_age_days 的缓存文件"""
        if max_age_days <= 0:
            return
        import time
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
        if removed:
            warnings.warn(f"[CacheManager] 已清理 {removed} 个过期缓存文件（>{max_age_days}天）", stacklevel=2)

    def _hash(self, content: str, model: str) -> str:
        key = f"{model}:{content}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def get(self, content: str, model: str) -> Optional[str]:
        key = self._hash(content, model)
        if key in self._memory_cache:
            return self._memory_cache[key].get("response")
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                self._memory_cache[key] = cached
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
        self._memory_cache[key] = entry
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ─── 配置加载器 ──────────────────────────────────────────

def _resolve_env(value):
    """解析值：如果以 $ 开头，从环境变量读取。"""
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value


def load_llm_config() -> dict:
    """从 llm_config.json 加载配置，并解析环境变量引用（$VAR_NAME 格式）。"""
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

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)
    return _resolve_dict(raw)


def build_model_pool() -> ModelPool:
    """根据 llm_config.json 构建模型池。"""
    cfg = load_llm_config()
    pool = ModelPool()

    if "deepseek" in cfg:
        deepsec_cfg = cfg["deepseek"]
        pool.deepseek = ModelConfig(
            provider="deepseek",
            model=deepsec_cfg.get("model", "deepseek-chat"),
            api_key=deepsec_cfg.get("api_key", ""),
            base_url=deepsec_cfg.get("base_url"),
            max_tokens=deepsec_cfg.get("max_tokens", 8192),
            temperature=deepsec_cfg.get("temperature", 0.7),
        )
        pool.deepseek_reasoner = ModelConfig(
            provider="deepseek",
            model="deepseek-reasoner",
            api_key=deepsec_cfg.get("api_key", ""),
            base_url=deepsec_cfg.get("base_url"),
            max_tokens=8192,
            temperature=0.5,
        )

    if "openai" in cfg:
        openai_cfg = cfg["openai"]
        pool.gpt5 = ModelConfig(
            provider="openai",
            model=openai_cfg.get("model", "gpt-5.5"),
            api_key=openai_cfg.get("api_key", ""),
            base_url=openai_cfg.get("base_url"),
            max_tokens=openai_cfg.get("max_tokens", 8192),
            temperature=openai_cfg.get("temperature", 0.7),
        )

    if "gemini" in cfg:
        gemini_cfg = cfg["gemini"]
        pool.gemini = ModelConfig(
            provider="gemini",
            model=gemini_cfg.get("model", "gemini-3.1-pro"),
            api_key=gemini_cfg.get("api_key", ""),
            base_url=gemini_cfg.get("base_url", "https://api.b.ai/v1"),
            max_tokens=gemini_cfg.get("max_tokens", 8192),
            temperature=gemini_cfg.get("temperature", 0.7),
        )

    if "kimi" in cfg:
        kimi_cfg = cfg["kimi"]
        pool.kimi = ModelConfig(
            provider="kimi",
            model=kimi_cfg.get("model", "kimi-k2.5"),
            api_key=kimi_cfg.get("api_key", ""),
            base_url=kimi_cfg.get("base_url", "https://api.b.ai/v1"),
            max_tokens=kimi_cfg.get("max_tokens", 8192),
            temperature=kimi_cfg.get("temperature", 0.7),
        )

    return pool


# ─── 任务分类器 ──────────────────────────────────────────

class TaskClassifier:
    """
    根据用户输入自动判断任务类型。
    优先级：精确匹配关键词 > 正则模式匹配 > 默认通用。
    """

    KEYWORD_PATTERNS: dict[Task, list[str]] = {
        Task.RESEARCH: ["研究", "分析", "调研", "对比", "评估", "趋势", "前景"],
        Task.LITERATURE: ["文献", "论文检索", "搜论文", "查找文献", "检索", "找相关研究", "academic", "paper search"],
        Task.CODE: ["写代码", "python", "代码", "script", "function", "def ", "class ", "import "],
        Task.CODE_ANALYSIS: ["这段代码", "解释代码", "代码分析", "debug", "优化代码"],
        Task.DATA_ANALYSIS: ["数据分析", "数据处理", "统计", "回归", "可视化", "chart", "plot"],
        Task.REPORT_CN: ["研报", "行研", "行业报告", "研究报告中", "研报框架"],
        Task.PAPER_CN: ["写论文", "中文论文", "中文学术"],
        Task.PAPER_EN: ["write a paper", "英文论文", "english paper", "ACL", "ICML", "NeurIPS", "IEEE"],
        Task.TRANSLATION: ["翻译", "translate to", "中译英", "英译中"],
        Task.MATH_REASONING: ["证明", "推导", "数学", "计算", "math", "calculate"],
        Task.SIMPLE_QA: ["是什么", "什么是", "怎么用", "介绍一下"],
    }

    REGEX_PATTERNS: list[tuple[re.Pattern, Task]] = [
        # 独立模式：开头必须是"帮我分析"，后面跟财务关键词
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


# ─── LLM 桥接器 ─────────────────────────────────────────

class LLMBridge:
    """统一调用不同 AI 模型的接口。"""

    def __init__(self, pool: ModelPool):
        self.pool = pool
        self._clients: dict[str, openai.OpenAI] = {}
        self._init_clients()

    def _init_clients(self):
        """初始化各模型的客户端。"""
        # ── DeepSeek（直连，独立计费）────────────────────────
        if self.pool.deepseek and self.pool.deepseek.api_key:
            self._clients["deepseek"] = openai.OpenAI(
                api_key=self.pool.deepseek.api_key,
                base_url=self.pool.deepseek.base_url,
                timeout=120,
            )

        if self.pool.deepseek_reasoner and self.pool.deepseek_reasoner.api_key:
            self._clients["deepseek-reasoner"] = openai.OpenAI(
                api_key=self.pool.deepseek_reasoner.api_key,
                base_url=self.pool.deepseek_reasoner.base_url,
                timeout=300,
            )

        # ── GPT-5.5（B.AI 中转）────────────────────────────
        if self.pool.gpt5 and self.pool.gpt5.api_key:
            self._clients["gpt5"] = openai.OpenAI(
                api_key=self.pool.gpt5.api_key,
                base_url=self.pool.gpt5.base_url,
                timeout=120,
            )

        # ── Gemini-3.1-Pro（B.AI 中转）────────────────────
        if self.pool.gemini and self.pool.gemini.api_key:
            self._clients["gemini"] = openai.OpenAI(
                api_key=self.pool.gemini.api_key,
                base_url=self.pool.gemini.base_url,
                timeout=120,
            )

        # ── Kimi（B.AI 中转）───────────────────────────────
        if self.pool.kimi and self.pool.kimi.api_key:
            self._clients["kimi"] = openai.OpenAI(
                api_key=self.pool.kimi.api_key,
                base_url=self.pool.kimi.base_url,
                timeout=120,
            )

    def _get_client(self, model_key: str) -> Optional[openai.OpenAI]:
        """获取对应模型的客户端。"""
        if model_key in ("deepseek", "deepseek-v4-pro", "deepseek-v4-flash",
                         "deepseek-chat", "deepseek-reasoner"):
            return self._clients.get("deepseek")
        if model_key in ("gpt5", "gpt-5.5", "gpt-5.4-pro"):
            return self._clients.get("gpt5")
        if model_key in ("gemini", "gemini-3.1-pro", "gemini-3-flash"):
            return self._clients.get("gemini")
        if model_key in ("kimi", "kimi-k2.5"):
            return self._clients.get("kimi")
        return self._clients.get(model_key)

    def _get_model_name(self, model_key: str) -> str:
        """
        将内部 key 映射为实际 API 模型名。
        实测 deepseek-v4-pro / deepseek-v4-flash / deepseek-reasoner
        在直连模式下返回空内容，只用 deepseek-chat。
        """
        # DeepSeek 直连 — 只认 deepseek-chat
        if model_key in ("deepseek", "deepseek-v4-pro", "deepseek-v4-flash",
                         "deepseek-chat", "deepseek-reasoner"):
            # 优先用配置中的值，其次降级为实测可用的模型
            cfg_model = (self.pool.deepseek.model
                         if self.pool.deepseek else "")
            if cfg_model and cfg_model not in ("deepseek-v4-pro",
                                               "deepseek-v4-flash",
                                               "deepseek-reasoner", ""):
                return cfg_model
            return "deepseek-chat"
        if model_key in ("gpt5", "gpt-5.5", "gpt-5.4-pro"):
            return self.pool.gpt5.model if self.pool.gpt5 else "gpt-5.5"
        if model_key in ("gemini", "gemini-3.1-pro", "gemini-3-flash"):
            return self.pool.gemini.model if self.pool.gemini else "gemini-3.1-pro"
        if model_key in ("kimi", "kimi-k2.5"):
            return self.pool.kimi.model if self.pool.kimi else "kimi-k2.5"
        return model_key

    def call(self, model_key: str, messages: list[dict],
             system_prompt: Optional[str] = None,
             temperature: float = 0.7,
             max_tokens: int = 8192,
             timeout: int = 180) -> str:
        """
        统一调用接口（含超时控制和空内容检测）。

        Args:
            model_key: 模型标识 (deepseek | gpt5 | gemini | kimi)
            messages: 消息列表
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出 token
            timeout: 请求超时（秒），默认 180
        """
        client = self._get_client(model_key)
        if client is None:
            raise RuntimeError(
                f"模型 '{model_key}' 未配置或缺少 API Key。"
                f"请检查 config/llm_config.json"
            )

        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        model_name = self._get_model_name(model_key)

        resp = client.chat.completions.create(
            model=model_name,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = resp.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError(
                f"模型 '{model_name}' 返回了空内容。"
                f"请检查 API Key、模型名或网络连接。"
            )
        return content


# ─── AI 路由主类 ─────────────────────────────────────────

@dataclass
class AIResult:
    """AI 调用的结果封装。"""
    response: str
    model_used: str
    task_type: str
    latency_ms: float
    cached: bool = False


class AIRouter:
    """
    AI 路由主入口。
    组合任务分类、模型路由、API 调用、缓存管理。
    """

    def __init__(self, use_cache: bool = True):
        self._use_cache = use_cache
        self._pool = None
        self._bridge = None
        self._cache = None
        self._classifier = None
        self._available_models: dict[str, str] = {}
        self._initialized = False

    def _lazy_init(self):
        """延迟初始化，避免模块导入时就创建客户端。"""
        if self._initialized:
            return
        self._pool = build_model_pool()
        self._classifier = TaskClassifier()
        self._bridge = LLMBridge(self._pool)
        self._cache = CacheManager() if self._use_cache else None

        for key in ["deepseek", "gpt5", "gemini", "kimi"]:
            client = self._bridge._get_client(key)
            self._available_models[key] = "✅ 可用" if client else "❌ 未配置"
        if self._bridge._get_client("deepseek-reasoner"):
            self._available_models["deepseek-reasoner"] = "✅ 可用"
        else:
            self._available_models["deepseek-reasoner"] = "❌ 未配置"
        self._initialized = True

    @property
    def pool(self):
        self._lazy_init()
        return self._pool

    @property
    def bridge(self):
        self._lazy_init()
        return self._bridge

    @property
    def cache(self):
        self._lazy_init()
        return self._cache

    @property
    def classifier(self):
        self._lazy_init()
        return self._classifier

    def status(self) -> dict:
        """返回当前各模型的可用状态。"""
        self._lazy_init()
        return self._available_models.copy()

    def chat(self, user_input: str,
             task: Optional[Task] = None,
             model: Optional[str] = None,
             system_prompt: Optional[str] = None,
             temperature: float = 0.7,
             max_tokens: int = 8192) -> AIResult:
        """
        主入口方法。

        调用优先级：
          1. model 参数 → 强制使用指定模型
          2. task 参数 → 按任务类型路由
          3. 自动分类 → 根据内容判断

        容错策略：主模型失败时，自动 fallback 到备选模型。

        Args:
            user_input: 用户输入
            task: 强制指定任务类型（跳过自动分类）
            model: 强制指定模型（跳过路由）
            system_prompt: 额外系统提示词
            temperature: 生成温度
            max_tokens: 最大输出 token

        Returns:
            AIResult 对象，包含回复、模型、任务类型、耗时
        """
        start = time.time()

        # Step 1：确定任务类型
        actual_task = task if task else self.classifier.classify(user_input)

        # Step 2：确定使用哪个模型
        if model:
            model_key = model
        else:
            model_key = TASK_ROUTING.get(actual_task, "deepseek")

        # Step 3：检查缓存
        cached_response = None
        if self.cache:
            cached_response = self.cache.get(user_input, model_key)

        if cached_response:
            return AIResult(
                response=cached_response,
                model_used=model_key,
                task_type=actual_task.value,
                latency_ms=(time.time() - start) * 1000,
                cached=True,
            )

        # Step 4：调用 AI（含自动 fallback）
        messages = [{"role": "user", "content": user_input}]
        response = None
        fallback_tried = False

        try:
            response = self.bridge.call(
                model_key=model_key,
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as primary_err:
            # Fallback 策略：primary → deepseek → kimi → gemini
            fallbacks = {
                "gpt5":    ["deepseek", "kimi", "gemini"],
                "gemini":  ["deepseek", "kimi"],
                "kimi":    ["deepseek"],
                "deepseek": [],
            }
            fallback_keys = fallbacks.get(model_key, [])

            for fb_key in fallback_keys:
                try:
                    fb_client = self.bridge._get_client(fb_key)
                    if fb_client is None:
                        continue
                    response = self.bridge.call(
                        model_key=fb_key,
                        messages=messages,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    model_key = fb_key
                    fallback_tried = True
                    print(f"  ⚠ 主模型失败，已切换至 {fb_key}: {primary_err}")
                    break
                except Exception:
                    continue

            if response is None:
                raise RuntimeError(
                    f"所有模型均调用失败。原始错误（{model_key}）: {primary_err}"
                ) from primary_err

        # Step 5：写入缓存
        if self.cache:
            self.cache.set(user_input, model_key, response, actual_task.value)

        return AIResult(
            response=response,
            model_used=model_key,
            task_type=actual_task.value,
            latency_ms=(time.time() - start) * 1000,
            cached=False,
        )

    def clear_cache(self):
        """清空所有缓存。"""
        if self.cache:
            _ = self.cache  # 触发延迟初始化
            if self._cache:
                self._cache._memory_cache.clear()
                for f in self._cache.cache_dir.glob("*.json"):
                    f.unlink()


# ─── 便捷别名 ─────────────────────────────────────────────

AI = AIRouter(use_cache=True)


# ─── 演示与调试 ──────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("AI 路由核心 v1.0")
    print("=" * 60)

    router = AIRouter(use_cache=True)

    # 状态检查
    print("\n[模型状态]")
    for model, status in router.status().items():
        print(f"  {model:20s} {status}")

    # 自动分类测试
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
    ]
    for inp in test_inputs:
        task = router._classifier.classify(inp)
        model = TASK_ROUTING.get(task, "unknown")
        print(f"  [{task.value:15s}] {model:15s} | {inp}")

    # 实际调用测试（需要先配置 API Key）
    print("\n[实际调用测试]")
    test_call = router.chat(
        "用一句话解释什么是ROE（净资产收益率）",
        task=Task.SIMPLE_QA,
    )
    print(f"  模型: {test_call.model_used}")
    print(f"  任务: {test_call.task_type}")
    print(f"  缓存: {test_call.cached}")
    print(f"  耗时: {test_call.latency_ms:.0f}ms")
    print(f"  回复: {test_call.response[:200]}")
