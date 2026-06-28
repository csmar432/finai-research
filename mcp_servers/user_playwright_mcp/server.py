#!/usr/bin/env python3
"""
user-playwright-mcp — 浏览器自动化MCP服务器
===========================================
动态网页数据抓取（JS渲染网站）、自动填表、页面截图。

适合抓取：
  - 东方财富（eastmoney.com）股票/基金/债券数据
  - 同花顺（10jqka.com.cn）金融数据
  - CSMAR / Wind 金融数据库
  - 其他需要JS渲染的动态网页

前置依赖：
  pip install playwright && playwright install chromium
  或: npx playwright install chromium

Usage:
    python server.py [--headless]
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import warnings
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. Run: pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-playwright-mcp")

# ─────────────────────────────────────────────────────────────────────────────
# Playwright 初始化（延迟导入，避免启动时卡住）
# ─────────────────────────────────────────────────────────────────────────────
_browser = None
_context = None
_playwright = None
_HEADLESS = True


def _get_browser():
    global _browser, _context, _playwright
    if _browser is None:
        try:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=_HEADLESS)
            _context = _browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
        except ImportError:
            raise ImportError("playwright not installed. Run: pip install playwright && playwright install chromium")
    return _browser, _context


def _close_browser():
    global _browser, _context, _playwright
    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None
        _context = None
    if _playwright:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


# ─────────────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="pw_navigate",
        description="导航到指定URL，等待页面加载完成。\n\n"
                    "Args:\n"
                    "  url: 目标URL\n"
                    "  wait_for: 等待元素选择器（可选）\n"
                    "  timeout: 超时秒数（默认30s）\n\n"
                    "Returns: 页面标题和当前URL",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
                "wait_for": {"type": "string", "description": "等待元素选择器"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="pw_screenshot",
        description="截取页面或元素截图。\n\n"
                    "Args:\n"
                    "  path: 输出图片路径\n"
                    "  selector: 可选，只截取指定元素\n"
                    "  full_page: 是否截取整页\n\n"
                    "Returns: 截图路径",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "输出路径（.png）"},
                "selector": {"type": "string", "description": "CSS选择器（截取元素而非整页）"},
                "full_page": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="pw_scrape_table",
        description="抓取HTML表格数据（东方财富/同花顺等金融网站的常用表格）。\n\n"
                    "Args:\n"
                    "  selector: 表格选择器（默认自动查找table）\n"
                    "  max_rows: 最大行数\n\n"
                    "Returns: 表格数据（CSV格式）",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS选择器", "default": "table"},
                "max_rows": {"type": "integer", "default": 100},
            },
        },
    ),
    Tool(
        name="pw_scrape_json",
        description="从页面提取JSON数据（从script标签、API响应或JSON-LD中提取）。\n\n"
                    "Args:\n"
                    "  pattern: JSON路径或键名模式（如 'data.records'）\n"
                    "  selector: 可选，只在特定元素内查找\n\n"
                    "Returns: 提取的JSON数据",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "JSON路径模式"},
                "selector": {"type": "string", "description": "CSS选择器"},
            },
            "required": ["pattern"],
        },
    ),
    Tool(
        name="pw_click",
        description="点击页面元素。\n\n"
                    "Args:\n"
                    "  selector: 元素选择器\n"
                    "  wait_after: 点击后等待秒数\n\n"
                    "Returns: 点击结果",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "wait_after": {"type": "number", "default": 1.0},
            },
            "required": ["selector"],
        },
    ),
    Tool(
        name="pw_fill_form",
        description="填写表单字段。\n\n"
                    "Args:\n"
                    "  fields: 字段字典，如 {\"input[name=q]\": \"搜索词\", \"#date\": \"2024-01-01\"}\n\n"
                    "Returns: 填写结果",
        inputSchema={
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "选择器 → 值 的映射",
                },
            },
            "required": ["fields"],
        },
    ),
    Tool(
        name="pw_evaluate_js",
        description="在页面上下文中执行JavaScript代码。\n\n"
                    "Args:\n"
                    "  code: JavaScript代码\n\n"
                    "Returns: 执行结果（序列化JSON）",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
    ),
    Tool(
        name="pw_wait",
        description="等待指定时间或条件。\n\n"
                    "Args:\n"
                    "  seconds: 等待秒数\n"
                    "  selector: 可选，等待元素出现\n\n"
                    "Returns: 等待结果",
        inputSchema={
            "type": "object",
            "properties": {
                "seconds": {"type": "number"},
                "selector": {"type": "string"},
            },
        },
    ),
    Tool(
        name="pw_download",
        description="等待并下载文件（触发下载后等待完成）。\n\n"
                    "Args:\n"
                    "  save_path: 保存路径\n"
                    "  trigger_selector: 触发下载的选择器\n"
                    "  timeout: 超时秒数\n\n"
                    "Returns: 下载文件路径",
        inputSchema={
            "type": "object",
            "properties": {
                "save_path": {"type": "string"},
                "trigger_selector": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["save_path"],
        },
    ),
    Tool(
        name="pw_get_html",
        description="获取页面或元素的HTML源码。\n\n"
                    "Args:\n"
                    "  selector: 可选，只获取指定元素的HTML\n\n"
                    "Returns: HTML源码",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "max_length": {"type": "integer", "default": 50000},
            },
        },
    ),
    Tool(
        name="pw_search_click",
        description="在搜索框输入关键词并点击搜索按钮（金融网站通用流程）。\n\n"
                    "Args:\n"
                    "  search_input_selector: 搜索框选择器\n"
                    "  search_button_selector: 搜索按钮选择器\n"
                    "  keyword: 搜索关键词\n"
                    "  wait_after: 点击后等待秒数\n\n"
                    "Returns: 操作结果",
        inputSchema={
            "type": "object",
            "properties": {
                "search_input_selector": {"type": "string", "default": "input[type=text], input[name=q], #searchInput"},
                "search_button_selector": {"type": "string", "default": "button[type=submit], .search-btn, input[type=button]"},
                "keyword": {"type": "string"},
                "wait_after": {"type": "number", "default": 2.0},
            },
            "required": ["keyword"],
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具处理函数
# ─────────────────────────────────────────────────────────────────────────────

_page = None


def _get_page():
    global _page
    browser, context = _get_browser()
    if _page is None:
        _page = context.new_page()
    return _page


async def handle_pw_navigate(args: dict) -> list[TextContent]:
    url = args["url"]
    wait_for = args.get("wait_for")
    timeout = args.get("timeout", 30)

    page = _get_page()
    try:
        page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        if wait_for:
            page.wait_for_selector(wait_for, timeout=timeout * 1000)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "url": page.url,
            "title": page.title(),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_screenshot(args: dict) -> list[TextContent]:
    path = args["path"]
    selector = args.get("selector")
    full_page = args.get("full_page", False)

    page = _get_page()
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    try:
        if selector:
            element = page.wait_for_selector(selector, timeout=5000)
            element.screenshot(path=path)
        else:
            page.screenshot(path=path, full_page=full_page)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "path": path,
            "size_kb": round(Path(path).stat().st_size / 1024, 1),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_scrape_table(args: dict) -> list[TextContent]:
    selector = args.get("selector", "table")
    max_rows = args.get("max_rows", 100)

    page = _get_page()
    try:
        table_element = page.wait_for_selector(selector, timeout=5000)
        headers = table_element.query_selector_all("thead th, thead td")
        header_texts = [h.inner_text().strip() for h in headers] if headers else []

        rows = table_element.query_selector_all("tbody tr")
        if not rows:
            rows = table_element.query_selector_all("tr")

        data_rows = []
        for row in rows[:max_rows]:
            cells = row.query_selector_all("td")
            if not cells:
                cells = row.query_selector_all("th")
            data_rows.append([c.inner_text().strip() for c in cells])

        if not header_texts and data_rows:
            header_texts = data_rows[0]
            data_rows = data_rows[1:]

        return [TextContent(type="text", text=json.dumps({
            "headers": header_texts,
            "rows": data_rows[:max_rows],
            "row_count": len(data_rows),
            "csv": "\n".join([",".join(h) for h in [header_texts] + data_rows]) if header_texts else "",
        }, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_scrape_json(args: dict) -> list[TextContent]:
    pattern = args["pattern"]
    selector = args.get("selector")

    page = _get_page()
    try:
        if selector:
            el = page.query_selector(selector)
            content = el.inner_text() if el else ""
        else:
            content = page.content()

        import re
        json_matches = re.findall(r'(?:window\.|var\s+)?(\w+)\s*=\s*(\[\{.*?\}\])', content[:50000], re.DOTALL)
        results = {}
        for key, val in json_matches:
            try:
                results[key] = json.loads(val)
            except Exception:
                pass

        return [TextContent(type="text", text=json.dumps({
            "pattern": pattern,
            "extracted": results,
            "source_length": len(content),
        }, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_click(args: dict) -> list[TextContent]:
    selector = args["selector"]
    wait_after = args.get("wait_after", 1.0)

    page = _get_page()
    try:
        page.click(selector, timeout=5000)
        page.wait_for_timeout(int(wait_after * 1000))
        return [TextContent(type="text", text=json.dumps({"success": True, "clicked": selector}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_fill_form(args: dict) -> list[TextContent]:
    fields = args["fields"]

    page = _get_page()
    try:
        for sel, val in fields.items():
            page.fill(sel, str(val), timeout=5000)
        return [TextContent(type="text", text=json.dumps({"success": True, "filled": list(fields.keys())}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_evaluate_js(args: dict) -> list[TextContent]:
    code = args["code"]

    page = _get_page()
    try:
        result = page.evaluate(code)
        return [TextContent(type="text", text=json.dumps({
            "result": result,
            "type": type(result).__name__,
        }, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_wait(args: dict) -> list[TextContent]:
    seconds = args.get("seconds", 1.0)
    selector = args.get("selector")

    page = _get_page()
    try:
        if selector:
            page.wait_for_selector(selector, timeout=int(seconds * 1000))
        else:
            page.wait_for_timeout(int(seconds * 1000))
        return [TextContent(type="text", text=json.dumps({"success": True, "waited": seconds}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_download(args: dict) -> list[TextContent]:
    save_path = args["save_path"]
    trigger_selector = args.get("trigger_selector")

    page = _get_page()
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with page.expect_download(timeout=(args.get("timeout", 30)) * 1000) as dl_info:
            if trigger_selector:
                page.click(trigger_selector, timeout=5000)
        dl = dl_info.value
        dl.save_as(save_path)
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "path": save_path,
            "size_kb": round(Path(save_path).stat().st_size / 1024, 1),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_get_html(args: dict) -> list[TextContent]:
    selector = args.get("selector")
    max_length = args.get("max_length", 50000)

    page = _get_page()
    try:
        if selector:
            el = page.query_selector(selector)
            html = el.inner_html() if el else ""
        else:
            html = page.content()

        return [TextContent(type="text", text=json.dumps({
            "html": html[:max_length],
            "truncated": len(html) > max_length,
            "total_length": len(html),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_pw_search_click(args: dict) -> list[TextContent]:
    input_sel = args.get("search_input_selector", "input[type=text], input[name=q], #searchInput")
    btn_sel = args.get("search_button_selector", "button[type=submit], .search-btn, input[type=button]")
    keyword = args["keyword"]
    wait_after = args.get("wait_after", 2.0)

    page = _get_page()
    try:
        el = page.wait_for_selector(input_sel, timeout=5000)
        el.fill(keyword)
        page.keyboard.press("Enter")
        page.wait_for_timeout(int(wait_after * 1000))
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "keyword": keyword,
            "url": page.url,
            "title": page.title(),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


TOOL_HANDLERS = {
    "pw_navigate": handle_pw_navigate,
    "pw_screenshot": handle_pw_screenshot,
    "pw_scrape_table": handle_pw_scrape_table,
    "pw_scrape_json": handle_pw_scrape_json,
    "pw_click": handle_pw_click,
    "pw_fill_form": handle_pw_fill_form,
    "pw_evaluate_js": handle_pw_evaluate_js,
    "pw_wait": handle_pw_wait,
    "pw_download": handle_pw_download,
    "pw_get_html": handle_pw_get_html,
    "pw_search_click": handle_pw_search_click,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def main():
    print("user-playwright-mcp starting... (use 'npx playwright install chromium' if not installed)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-playwright-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
