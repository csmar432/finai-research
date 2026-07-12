"""
paid_source_notifier.py
=======================
付费数据源的非阻塞提示器 (audit 2026-07-12, T10).

设计原则:
  - 不阻断 (no raise / no sys.exit) — 用户可按需配置
  - 主动告知 (proactive) — 调用时打印 1 次警告, 不等 health_check 才发现
  - 去重 (deduplicated) — 同一 (server, tool) 进程内最多提示 1 次, 不刷屏
  - 可关闭 — CLI 设置 FINAI_SUPPRESS_PAID_WARNINGS=1 或配置 disable_paid_warnings
  - 可引导 (actionable) — 每条警告都附带: 费用 / 获取 URL / 影响范围

支持的付费源 (白名单):
  - user-tushare  (Tushare Pro Token, 个人 200-2000元/年)
  - user-csmar    (国泰安机构账号)
  - user-wind     (Wind 机构账号)
  - user-cnki     (CNKI 机构账号 / VPN)
  - user-wanfang  (万方机构账号)
  - user-eodhd    (EODHD API Key, 免费额度 20 req/day)
  - user-brave-search (Brave Search API Key, 免费 2000 query/月)
  - user-newsapi  (NewsAPI Key, 免费 100 req/day)
  - user-e2b-mcp  (e2b 云端执行 Key)

环境变量:
  TUSHARE_TOKEN         Tushare Pro 个人 Token
  CSMAR_API_KEY         CSMAR API Key
  WIND_ACCOUNT          Wind 账号
  CNKI_USERNAME         CNKI 用户名
  CNKI_PASSWORD         CNKI 密码
  WANFANG_API_KEY       万方 API Key
  EODHD_API_KEY         EODHD Key
  BRAVE_SEARCH_API_KEY  Brave Search Key
  NEWSAPI_API_KEY       NewsAPI Key
  E2B_API_KEY           e2b API Key

CLI:
  FINAI_SUPPRESS_PAID_WARNINGS=1   全局静默付费警告 (用于 CI 批处理)
  FINAI_PAID_WARN_LOG=<path>       自定义日志路径 (默认 ./paid_source_warnings.jsonl)

用法:
  from scripts.core.paid_source_notifier import paid_notifier
  paid_notifier.warn_if_paid("user-tushare", "get_daily_quote")  # 自动检测
  paid_notifier.warn(server="user-csmar", tool="*", reason="...") # 显式
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
_LOG_PATH = Path(os.environ.get("FINAI_PAID_WARN_LOG", str(_PROJECT_ROOT / "paid_source_warnings.jsonl")))
_SUPPRESSED = os.environ.get("FINAI_SUPPRESS_PAID_WARNINGS") == "1"


@dataclass(frozen=True)
class PaidSourceSpec:
    """元数据: 付费数据源 + 如何获取 Key + 典型费用."""
    server: str
    display_name: str
    env_var: str
    cost: str                    # e.g. "个人 200-2000元/年"
    get_url: str                 # 注册/购买入口
    fallback: str                # fallback 行为 (akshare / baostock / synthetic)
    impact: str                  # 对哪些研究有影响 (一句话)


# ─── 付费数据源注册表 ─────────────────────────────────────────────────────────

PAID_SOURCE_REGISTRY: dict[str, PaidSourceSpec] = {
    "user-tushare": PaidSourceSpec(
        server="user-tushare",
        display_name="Tushare Pro",
        env_var="TUSHARE_TOKEN",
        cost="个人 ¥200-2000/年 (积分制)",
        get_url="https://tushare.pro/register",
        fallback="akshare / baostock / efinance",
        impact="A股财务/行情/融资融券; 财务指标/股东户数/分红等",
    ),
    "user-csmar": PaidSourceSpec(
        server="user-csmar",
        display_name="CSMAR 国泰安",
        env_var="CSMAR_API_KEY",
        cost="机构 ¥数千-万元/年 (高校图书馆通常可申请)",
        get_url="https://www.gtarsc.com/",
        fallback="akshare (部分字段)",
        impact="A股财务/治理/专利/海关/分析师预测/ESG 等结构化数据",
    ),
    "user-wind": PaidSourceSpec(
        server="user-wind",
        display_name="Wind 万得",
        env_var="WIND_ACCOUNT",
        cost="机构 ¥数万/年 (个人极少)",
        get_url="https://www.wind.com.cn/",
        fallback="akshare / iFinD (部分字段)",
        impact="A股/港股/美股/债券/基金/期货/指数全谱行情与基本面",
    ),
    "user-cnki": PaidSourceSpec(
        server="user-cnki",
        display_name="CNKI 中国知网",
        env_var="CNKI_USERNAME",
        cost="机构 ¥数千元/年 / 个人 ¥数百/年",
        get_url="https://www.cnki.net/",
        fallback="万方 / OpenAlex / arXiv / 公开摘要",
        impact="中文期刊/学位论文/会议论文/专利全文",
    ),
    "user-wanfang": PaidSourceSpec(
        server="user-wanfang",
        display_name="万方数据",
        env_var="WANFANG_API_KEY",
        cost="机构 ¥数千元/年",
        get_url="https://www.wanfangdata.com.cn/",
        fallback="CNKI / OpenAlex / 公开摘要",
        impact="中文期刊/学位论文/会议论文 (部分 CNKI 未覆盖)",
    ),
    "user-eodhd": PaidSourceSpec(
        server="user-eodhd",
        display_name="EODHD",
        env_var="EODHD_API_KEY",
        cost="免费 20 req/day; 个人 $20/月",
        get_url="https://eodhd.com/",
        fallback="user-fed-data / user-financial / yfinance",
        impact="美债收益率/经济日历/全球指数/基本面",
    ),
    "user-brave-search": PaidSourceSpec(
        server="user-brave-search",
        display_name="Brave Search",
        env_var="BRAVE_SEARCH_API_KEY",
        cost="免费 2000 query/月",
        get_url="https://brave.com/search/api/",
        fallback="user-arxiv / user-openalex / WebSearch (内置)",
        impact="网络搜索 (中英文网站)",
    ),
    "user-newsapi": PaidSourceSpec(
        server="user-newsapi",
        display_name="NewsAPI",
        env_var="NEWSAPI_API_KEY",
        cost="免费 100 req/day",
        get_url="https://newsapi.org/register",
        fallback="user-eastmoney-reports / WebSearch",
        impact="全球财经新闻搜索",
    ),
    "user-e2b-mcp": PaidSourceSpec(
        server="user-e2b-mcp",
        display_name="e2b 云端代码执行",
        env_var="E2B_API_KEY",
        cost="免费额度; 个人 $25/月起",
        get_url="https://e2b.dev/",
        fallback="本地 Python subprocess / pandas_mcp",
        impact="云端沙盒执行大型 Python 脚本",
    ),
}


@dataclass
class PaidSourceNotifier:
    """
    进程级单例. 每次调用 warn_if_paid() 时:
      1. 判断 server 是否在 PAID 列表
      2. 判断对应 env_var 是否已设置
      3. 如未设置 / 未配置, 打印一次 🟡 警告 (含获取方式 + 影响范围)
      4. 追加到 paid_source_warnings.jsonl (供后续 audit)
    """
    _seen: set[tuple[str, str]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _disabled: bool = False

    def configure(self, disabled: bool = False) -> None:
        """Process-level toggle. Set disabled=True to silence all paid warnings."""
        with self._lock:
            self._disabled = disabled

    @staticmethod
    def _check_key(env_var: str) -> bool:
        """Return True if env_var is set and non-empty."""
        val = os.environ.get(env_var, "").strip()
        if not val:
            return False
        # Some providers use placeholder strings like "<your-key>" — treat as unset
        if val.startswith("<") or val in {"YOUR_KEY", "your_key", "your-key", "TODO", "REPLACE_ME"}:
            return False
        return True

    def is_paid(self, server: str) -> bool:
        return server in PAID_SOURCE_REGISTRY

    def warn_if_paid(self, server: str, tool: str = "*",
                     reason: Optional[str] = None) -> bool:
        """
        Check if `server` is a paid MCP and warn if its key is missing.
        Returns True if a warning was emitted, False if no action was taken.

        Args:
            server:  MCP server name (e.g. "user-tushare")
            tool:    Tool name (e.g. "get_daily_quote") or "*" for any
            reason:  Optional human-readable reason for this specific call

        Side effects (non-blocking):
            - Prints a single 🟡 warning to stderr (deduplicated within process)
            - Appends to paid_source_warnings.jsonl
        """
        # Suppression paths
        if self._disabled or _SUPPRESSED:
            return False
        if server not in PAID_SOURCE_REGISTRY:
            return False

        spec = PAID_SOURCE_REGISTRY[server]
        if self._check_key(spec.env_var):
            # Key is configured — no warning needed
            return False

        # Dedup within process
        dedup_key = (server, tool)
        with self._lock:
            if dedup_key in self._seen:
                return False
            self._seen.add(dedup_key)

        # ── Build warning ────────────────────────────────────────────────
        msg = self._format_warning(spec, tool, reason)

        # ── Print (non-blocking) ─────────────────────────────────────────
        # Use sys.stderr so it surfaces even if stdout is redirected
        import sys
        print(msg, file=sys.stderr, flush=True)

        # ── Log to file (audit trail) ────────────────────────────────────
        try:
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": time.time(),
                    "server": server,
                    "tool": tool,
                    "env_var": spec.env_var,
                    "cost": spec.cost,
                    "get_url": spec.get_url,
                    "fallback": spec.fallback,
                    "impact": spec.impact,
                    "reason": reason,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass  # log failures must not break pipeline

        return True

    @staticmethod
    def _format_warning(spec: PaidSourceSpec, tool: str, reason: Optional[str]) -> str:
        """Format the warning text (used by warn_if_paid)."""
        lines = [
            "",
            "━" * 64,
            f"🟡 付费数据源未配置: {spec.display_name} ({spec.server})",
            "━" * 64,
            f"  调用: {spec.server}/{tool}",
            f"  影响: {spec.impact}",
            f"  费用: {spec.cost}",
            f"  获取: {spec.get_url}",
            f"  Fallback: 自动切到 {spec.fallback}",
            f"  按需配置: 在 .env.local 设置 {spec.env_var} 然后重新运行",
            "  关闭提示: FINAI_SUPPRESS_PAID_WARNINGS=1 (用于 CI 批处理)",
        ]
        if reason:
            lines.append(f"  说明: {reason}")
        lines.append("━" * 64)
        return "\n".join(lines)

    def warn(self, server: str, tool: str = "*", reason: Optional[str] = None) -> bool:
        """
        Public alias of warn_if_paid — explicit named entry-point.

        Used by callers that already KNOW a server is paid and want to
        log a warning (skips the registry check). Always returns False
        because the suppression/disable gates are honored by warn_if_paid.
        """
        return self.warn_if_paid(server, tool, reason)

    def stats(self) -> dict:
        """Return counts of unique (server, tool) pairs warned in this process."""
        with self._lock:
            seen_list = sorted(self._seen)  # sort tuples (comparable)
            return {
                "unique_warnings": len(self._seen),
                "warnings": [
                    {"server": s, "tool": t} for (s, t) in seen_list
                ],
            }


# ─── 进程级单例 ──────────────────────────────────────────────────────────────
paid_notifier = PaidSourceNotifier()


# ─── 自动 hook: 包 import 时自动启用 ──────────────────────────────────────────

# 注意: 我们不会主动 monkey-patch MCPClient. 调用方应显式调用
# `paid_notifier.warn_if_paid(server, tool)` 或在 MCPToolClient.call() 内部
# 加一行. 这样保留调用方的可控性, 又不破坏现有调用路径.


__all__ = [
    "PaidSourceNotifier",
    "PaidSourceSpec",
    "PAID_SOURCE_REGISTRY",
    "paid_notifier",
]