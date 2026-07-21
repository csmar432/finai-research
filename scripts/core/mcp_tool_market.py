"""
MCP Tool Marketplace Registry

Scans all MCP servers under mcp_servers/ and builds a searchable registry
with quality scores, categories, and metadata.
"""

from __future__ import annotations

__all__ = [
    "ToolMetadata",
    "MCPToolRegistry",
    "CATEGORY_RULES",
    "TAG_KEYWORDS",
    "get_default_registry",
]

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["tushare", "eastmoney", "csmar", "wind"], "financial"),
    (["fed_data", "wb_data", "oecd_data", "imf_data", "macro", "hubei_stats", "wuhan_stats",
      "province_stats", "bea_data", "macro_ceic"], "macro_data"),
    (["eodhd", "enhanced_finance", "yfinance"], "market_data"),
    (["arxiv", "nber_wp"], "academic"),
]

TAG_KEYWORDS: dict[str, list[str]] = {
    "financial": ["股票", "A股", "财报", "财务", "盈利", "营收", "ROE", "市值", "估值", "PE", "PB"],
    "macro_data": ["GDP", "CPI", "PPI", "PMI", "M2", "利率", "通胀", "就业", "宏观", "经济"],
    "market_data": ["行情", "价格", "收益率", "汇率", "期货", "大宗商品", "航运", "指数", "期权"],
    "academic": ["论文", "工作论文", "NBER", "arXiv", "文献", "研究"],
    "utility": ["文件", "LaTeX", "代码", "执行", "沙箱", "浏览器"],
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: dict
    mcp_server: str
    category: str
    quality_score: float
    is_mock: bool
    requires_api_key: bool
    tags: list[str] = field(default_factory=list)
    last_updated: str = ""
    example_params: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolMetadata":
        d["tags"] = d.get("tags", [])
        d["example_params"] = d.get("example_params")
        return cls(**d)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _extract_api_hints(schema: dict, description: str) -> bool:
    """Return True if the tool hints at real API usage (not purely mock)."""
    text = json.dumps(schema, ensure_ascii=False) + " " + description
    text_lower = text.lower()
    mock_signals = ["mock", "假数据", "演示数据", "示例数据", "fake", "dummy"]
    return not any(s in text_lower for s in mock_signals)


def _quality_score(name: str, description: str, schema: dict, mcp_server: str,
                   server_desc: str) -> tuple[float, bool]:
    """
    Score a tool 0.0–1.0 based on richness of metadata.
    Also returns whether it looks like a mock/demo server.
    """
    score = 0.0
    # Has description (not empty, not just whitespace/newlines)
    stripped = description.strip().replace("\\n", " ").replace("\n", " ").strip()
    if len(stripped) > 10:
        score += 0.2

    # Has input_schema with properties
    props = schema.get("properties", {})
    if isinstance(props, dict) and len(props) >= 1:
        score += 0.2

    # Real API hints (not mock)
    api_real = _extract_api_hints(schema, description)
    if api_real:
        score += 0.3

    # Server-level mock signal
    is_mock_server = any(
        kw in server_desc for kw in ["演示", "mock", "fake", "demo"]
    )

    # Has examples in description
    if "例如" in description or "e.g." in description.lower() or "example" in description.lower():
        score += 0.1

    return min(score, 1.0), is_mock_server


def _assign_category(mcp_server: str, description: str) -> str:
    """Auto-assign category from server name and description."""
    server_lower = mcp_server.lower()
    for keywords, category in CATEGORY_RULES:
        if any(kw in server_lower for kw in keywords):
            return category
    # Fallback: infer from description keywords
    for category, keywords in TAG_KEYWORDS.items():
        if any(kw in description for kw in keywords):
            return category
    return "utility"


def _build_tags(name: str, description: str, category: str) -> list[str]:
    """Derive searchable tags from name, description, and category."""
    tags: list[str] = [category]
    combined = (name + " " + description).lower()
    for cat, keywords in TAG_KEYWORDS.items():
        if cat == category:
            continue
        for kw in keywords:
            if kw.lower() in combined:
                tags.append(cat)
    # Extract meaningful word tokens
    tokens = re.findall(r"[a-zA-Z_]{3,}", name)
    tags.extend(tokens[:3])
    return list(dict.fromkeys(tags))  # deduplicate preserve order


# ---------------------------------------------------------------------------
# Main Registry
# ---------------------------------------------------------------------------

class MCPToolRegistry:
    """
    MCP Tool Marketplace Registry.

    Scans mcp_servers/user_*/ directories, reads SERVER_METADATA.json and
    tools/*.json files, and builds a searchable in-memory registry.
    """

    def __init__(self):
        self.tools: dict[str, ToolMetadata] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_tool(self, tool: ToolMetadata) -> None:
        key = f"{tool.mcp_server}:{tool.name}"
        self.tools[key] = tool

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        max_results: int = 10,
    ) -> list[ToolMetadata]:
        """
        Full-text search across name, description, and tags.
        Returns tools sorted by quality_score descending.
        """
        query_lower = query.lower()
        scored: list[tuple[float, ToolMetadata]] = []

        for tool in self.tools.values():
            if category and tool.category != category:
                continue
            q = query_lower
            name_hit = q in tool.name.lower()
            desc_hit = q in tool.description.lower()
            tag_hit = any(q in t.lower() for t in tool.tags)
            if not (name_hit or desc_hit or tag_hit):
                continue
            # Boost score for name/tag hits
            boost = 0.2 if name_hit else (0.1 if tag_hit else 0.0)
            scored.append((tool.quality_score + boost, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:max_results]]

    def get_by_server(self, server: str) -> list[ToolMetadata]:
        """Get all tools from a specific MCP server."""
        return [t for t in self.tools.values() if t.mcp_server == server]

    def get_by_category(self, category: str) -> list[ToolMetadata]:
        """Get all tools in a specific category."""
        return [t for t in self.tools.values() if t.category == category]

    def get_marketplace_report(self) -> dict:
        """Generate marketplace statistics as a dict."""
        total = len(self.tools)
        by_category: dict[str, int] = {}
        by_server: dict[str, int] = {}
        category_avg_quality: dict[str, float] = {}
        requires_key = 0
        mock_count = 0

        for tool in self.tools.values():
            by_category[tool.category] = by_category.get(tool.category, 0) + 1
            by_server[tool.mcp_server] = by_server.get(tool.mcp_server, 0) + 1
            if tool.requires_api_key:
                requires_key += 1
            if tool.is_mock:
                mock_count += 1
            if tool.category not in category_avg_quality:
                category_avg_quality[tool.category] = 0.0
            category_avg_quality[tool.category] += tool.quality_score

        for cat in category_avg_quality:
            count = by_category.get(cat, 1)
            category_avg_quality[cat] = round(category_avg_quality[cat] / count, 3)

        # Top 5 by quality
        top5 = sorted(self.tools.values(), key=lambda t: t.quality_score, reverse=True)[:5]
        top5_list = [
            {
                "server": t.mcp_server,
                "name": t.name,
                "score": round(t.quality_score, 3),
                "category": t.category,
                "description": t.description[:80],
            }
            for t in top5
        ]

        return {
            "total_tools": total,
            "total_servers": len(by_server),
            "by_category": dict(sorted(by_category.items())),
            "by_server": dict(sorted(by_server.items())),
            "category_avg_quality": dict(sorted(category_avg_quality.items())),
            "requires_api_key": requires_key,
            "mock_tools": mock_count,
            "top_5_by_quality": top5_list,
            "generated_at": datetime.now().isoformat(),
        }

    def to_json(self) -> dict:
        """Export registry as a JSON-serializable dict."""
        return {
            "generated_at": datetime.now().isoformat(),
            "total_tools": len(self.tools),
            "tools": {k: t.to_dict() for k, t in self.tools.items()},
        }

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    def from_directory(cls, base_path: str) -> "MCPToolRegistry":
        """
        Scan base_path (e.g. 'mcp_servers') and build the registry.

        Expected structure:
            {base_path}/
                user_{name}/
                    SERVER_METADATA.json
                    tools/
                        *.json
        """
        registry = cls()
        base = Path(base_path)

        if not base.exists():
            raise FileNotFoundError(f"Directory not found: {base_path}")

        today = date.today().isoformat()

        for server_dir in sorted(base.iterdir()):
            if not server_dir.is_dir() or not server_dir.name.startswith("user_"):
                continue

            mcp_server = server_dir.name  # e.g. "user-tushare"
            metadata_file = server_dir / "SERVER_METADATA.json"

            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, encoding="utf-8") as f:
                    server_meta = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            server_desc = server_meta.get("description", "")
            tools_dir = server_dir / "tools"

            # Load all tool JSON files
            tool_files: list[Path] = []
            if tools_dir.exists():
                tool_files = sorted(tools_dir.glob("*.json"))

            if not tool_files:
                continue

            for tool_file in tool_files:
                try:
                    with open(tool_file, encoding="utf-8") as f:
                        tool_json = json.load(f)
                except (json.JSONDecodeError, IOError):
                    continue

                name = tool_json.get("name", tool_file.stem)
                description = tool_json.get("description", "")
                schema = tool_json.get("inputSchema", {})

                quality, is_mock = _quality_score(
                    name, description, schema, mcp_server, server_desc
                )

                # requires_api_key: check server metadata
                legacy = server_meta.get("_legacy_capabilities", {})
                if isinstance(legacy, dict):
                    requires_key = legacy.get("requires_api_key", False)
                else:
                    requires_key = False

                category = _assign_category(mcp_server, description)
                tags = _build_tags(name, description, category)

                # Derive example params from schema properties
                example_params: Optional[dict] = None
                props = schema.get("properties", {})
                if isinstance(props, dict) and len(props) > 0:
                    example_params = {}
                    for pname, pval in list(props.items())[:3]:
                        ptype = pval.get("type", "string")
                        if ptype == "integer":
                            example_params[pname] = 2024
                        elif ptype == "number":
                            example_params[pname] = 1.0
                        elif ptype == "boolean":
                            example_params[pname] = True
                        else:
                            example_params[pname] = pval.get("description", "value") or "example"

                tool_meta = ToolMetadata(
                    name=name,
                    description=description,
                    input_schema=schema,
                    mcp_server=mcp_server,
                    category=category,
                    quality_score=round(quality, 3),
                    is_mock=is_mock,
                    requires_api_key=requires_key,
                    tags=tags,
                    last_updated=today,
                    example_params=example_params,
                )
                registry.register_tool(tool_meta)

        return registry

    # ------------------------------------------------------------------
    # Console output
    # ------------------------------------------------------------------

    def print_catalog(self, category: Optional[str] = None) -> None:
        """Print a formatted catalog to the console."""
        tools = (
            self.get_by_category(category) if category
            else list(self.tools.values())
        )

        title = f"MCP Tool Marketplace {'— ' + category.upper() if category else ''}"
        sep = "=" * 80
        print(f"\n{sep}")
        print(f"  {title}")
        print(sep)

        report = self.get_marketplace_report()
        print(f"\n  Total: {report['total_tools']} tools across {report['total_servers']} servers")
        print(f"  Mock tools: {report['mock_tools']}  |  Requires API key: {report['requires_api_key']}")

        print("\n  [ By Category ]")
        for cat, count in report["by_category"].items():
            avg_q = report["category_avg_quality"].get(cat, 0)
            bar = "█" * int(avg_q * 10) + "░" * (10 - int(avg_q * 10))
            print(f"    {cat:<18} {count:>4} tools   [{bar}] avg q={avg_q:.2f}")

        print("\n  [ By Server ]")
        for srv, count in report["by_server"].items():
            print(f"    {srv:<30} {count:>3} tools")

        print("\n  [ Top 5 by Quality Score ]")
        for i, item in enumerate(report["top_5_by_quality"], 1):
            print(f"    {i}. [{item['score']:.3f}] {item['server']}::{item['name']}")
            print(f"       → {item['description']}...")

        if tools:
            print(f"\n  [ Tool Listing — {len(tools)} tools ]")
            for tool in tools:
                badge = "MOCK" if tool.is_mock else ("KEY" if tool.requires_api_key else "FREE")
                print(
                    f"    [{tool.quality_score:.1f}] [{tool.category:<12}] [{badge:>4}] "
                    f"{tool.mcp_server}::{tool.name}"
                )
                if tool.description.strip():
                    desc_preview = tool.description.strip().replace("\n", " ")[:70]
                    print(f"         {desc_preview}")

        print(f"\n{sep}\n")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.tools)

    def __repr__(self) -> str:
        return f"MCPToolRegistry({len(self.tools)} tools)"


# ---------------------------------------------------------------------------
# Global default registry (lazy singleton)
# ---------------------------------------------------------------------------

_default_registry: MCPToolRegistry | None = None


def get_default_registry(base_path: str | None = None) -> MCPToolRegistry:
    """
    Get the global default MCPToolRegistry instance.

    On first call, scans the mcp_servers directory and builds the registry.
    Subsequent calls return the cached instance.

    Parameters
    ----------
    base_path : str | None
        Path to mcp_servers directory. Defaults to 'mcp_servers' relative to
        the directory containing this module.

    Returns
    -------
    MCPToolRegistry
        The shared registry instance.

    Raises
    ------
    FileNotFoundError
        If base_path does not exist.
    RuntimeError
        If called before the registry has been initialised and base_path is None.
    """
    global _default_registry  # noqa: PLW0603
    if _default_registry is not None:
        return _default_registry

    if base_path is None:
        base_path = str(Path(__file__).parent.parent.parent / "mcp_servers")

    if not Path(base_path).exists():
        raise RuntimeError(
            f"Default registry has not been built yet and mcp_servers "
            f"directory not found at '{base_path}'. "
            f"Call MCPToolRegistry.from_directory() explicitly."
        )

    _default_registry = MCPToolRegistry.from_directory(base_path)
    return _default_registry


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Tool Marketplace Registry")
    parser.add_argument(
        "--dir", "-d", default="mcp_servers",
        help="Path to mcp_servers directory (default: mcp_servers)"
    )
    parser.add_argument(
        "--category", "-c", default=None,
        help="Filter by category (financial, macro_data, market_data, academic, utility)"
    )
    parser.add_argument(
        "--search", "-s", default=None,
        help="Search query"
    )
    parser.add_argument(
        "--server", default=None,
        help="Show tools for a specific server (e.g. user-tushare)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Export full registry as JSON"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print marketplace statistics"
    )
    args = parser.parse_args()

    registry = MCPToolRegistry.from_directory(args.dir)

    if args.json:
        print(json.dumps(registry.to_json(), indent=2, ensure_ascii=False))
    elif args.report:
        report = registry.get_marketplace_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.search:
        results = registry.search(args.search, category=args.category)
        print(f"\nSearch: '{args.search}' — {len(results)} results\n")
        for t in results:
            print(f"  [{t.quality_score:.2f}] {t.mcp_server}::{t.name}")
            print(f"    {t.description[:80]}")
            print()
    elif args.server:
        tools = registry.get_by_server(args.server)
        print(f"\nServer: {args.server} — {len(tools)} tools\n")
        for t in tools:
            print(f"  [{t.quality_score:.2f}] {t.name}")
    else:
        registry.print_catalog(category=args.category)
