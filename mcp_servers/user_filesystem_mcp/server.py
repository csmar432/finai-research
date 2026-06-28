#!/usr/bin/env python3
"""
user-filesystem-mcp — 文件系统增强MCP服务器
============================================
高级文件操作：批量读写、通配符搜索、文件差异比较、文件监控。

功能：
  - glob/wildcard 文件搜索（支持复杂模式）
  - 批量读取/写入文件
  - 文件差异比较（diff）
  - 文件树生成（类似tree命令）
  - 全文搜索（grep，支持正则）
  - 文件统计（大小、行数、修改时间）
  - 批量重命名/移动
  - 软链接管理

Usage:
    python server.py [--root DIR]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import warnings
from pathlib import Path

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

server = Server("user-filesystem-mcp")

_ROOT_DIR = os.environ.get("FS_ROOT", str(_PROJECT_ROOT))


def _norm(p: str) -> Path:
    """规范化路径，在root内"""
    path = Path(p).expanduser().resolve()
    if not str(path).startswith(_ROOT_DIR):
        return Path(_ROOT_DIR) / Path(p).name
    return path


def _read_file(p: Path, max_kb: int = 500, encoding: str = "utf-8") -> dict:
    """读取文件内容（限制大小）。"""
    if not p.exists():
        return {"error": f"Not found: {p}"}
    size_kb = p.stat().st_size / 1024
    if size_kb > max_kb:
        return {"error": f"File too large: {size_kb:.1f}KB > {max_kb}KB", "size_kb": round(size_kb, 1)}
    try:
        content = p.read_text(encoding=encoding)
        lines = content.splitlines()
        return {
            "path": str(p),
            "size_kb": round(size_kb, 1),
            "lines": len(lines),
            "content": content[:100000],
            "truncated": len(content) > 100000,
        }
    except UnicodeDecodeError:
        try:
            content = p.read_text(encoding="latin-1")
            return {"path": str(p), "size_kb": round(size_kb, 1), "encoding": "latin-1", "content": content[:100000]}
        except Exception as e:
            return {"error": str(e)}


def _file_tree(d: Path, max_depth: int = 3, current_depth: int = 0) -> list[dict]:
    """生成文件树。"""
    items = []
    if current_depth >= max_depth:
        return items
    try:
        for item in sorted(d.iterdir()):
            rel = item.relative_to(d)
            if "/." in str(rel) or item.name.startswith("."):
                continue
            stat = item.stat()
            items.append({
                "name": item.name,
                "path": str(item.relative_to(d.parent) if d.parent != d else item.name),
                "type": "dir" if item.is_dir() else "file",
                "size_kb": round(stat.st_size / 1024, 1) if item.is_file() else 0,
                "modified": stat.st_mtime,
            })
            if item.is_dir():
                items.extend(_file_tree(item, max_depth, current_depth + 1))
    except PermissionError:
        pass
    return items


def _grep_content(p: Path, pattern: str, regex: bool = False, case_insensitive: bool = True) -> list[dict]:
    """在文件中搜索内容。"""
    results = []
    try:
        flags = re.IGNORECASE if case_insensitive else 0
        prog = re.compile(pattern, flags) if regex else None
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if regex:
                if prog.search(line):
                    results.append({"line": i, "content": line.strip(), "match": pattern})
            else:
                if pattern.lower() in line.lower():
                    idx = line.lower().index(pattern.lower())
                    results.append({"line": i, "content": line.strip(), "context": line[max(0,idx-20):idx+len(pattern)+20]})
            if len(results) >= 200:
                break
    except Exception:
        pass
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="fs_glob",
        description="通配符文件搜索（类似find但更强大）。\n\n"
                    "Args:\n"
                    "  pattern: 搜索模式，如 **/*.py, **/*.tex, **/*.csv\n"
                    "  root: 搜索根目录（默认项目根目录）\n"
                    "  max_results: 最大返回数\n\n"
                    "Returns: 匹配文件列表",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "root": {"type": "string"},
                "max_results": {"type": "integer", "default": 100},
            },
            "required": ["pattern"],
        },
    ),
    Tool(
        name="fs_read",
        description="读取一个或多个文件内容。\n\n"
                    "Args:\n"
                    "  paths: 文件路径列表\n"
                    "  max_kb: 单文件最大KB\n"
                    "  encoding: 编码\n\n"
                    "Returns: 文件内容",
        inputSchema={
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "max_kb": {"type": "integer", "default": 500},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["paths"],
        },
    ),
    Tool(
        name="fs_write",
        description="写入文件内容（可批量）。\n\n"
                    "Args:\n"
                    "  files: 文件字典，如 {\"path/to/file.txt\": \"content\"}\n\n"
                    "Returns: 写入结果",
        inputSchema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "object",
                    "description": "path → content 映射",
                },
            },
            "required": ["files"],
        },
    ),
    Tool(
        name="fs_tree",
        description="生成目录树结构（类似tree命令）。\n\n"
                    "Args:\n"
                    "  root: 目录路径\n"
                    "  max_depth: 最大深度\n\n"
                    "Returns: 树形结构列表",
        inputSchema={
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "max_depth": {"type": "integer", "default": 3},
            },
        },
    ),
    Tool(
        name="fs_grep",
        description="在文件中搜索文本（grep）。\n\n"
                    "Args:\n"
                    "  pattern: 搜索关键词\n"
                    "  root: 搜索根目录\n"
                    "  file_pattern: 文件模式，如 *.py, *.md\n"
                    "  regex: 是否正则表达式\n"
                    "  case_insensitive: 大小写不敏感\n"
                    "  max_results: 最大匹配数\n\n"
                    "Returns: 匹配结果（含行号和上下文）",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "root": {"type": "string"},
                "file_pattern": {"type": "string"},
                "regex": {"type": "boolean", "default": False},
                "case_insensitive": {"type": "boolean", "default": True},
                "max_results": {"type": "integer", "default": 200},
            },
            "required": ["pattern"],
        },
    ),
    Tool(
        name="fs_diff",
        description="比较两个文件差异。\n\n"
                    "Args:\n"
                    "  old_file: 旧文件\n"
                    "  new_file: 新文件\n\n"
                    "Returns: 差异列表",
        inputSchema={
            "type": "object",
            "properties": {
                "old_file": {"type": "string"},
                "new_file": {"type": "string"},
            },
            "required": ["old_file", "new_file"],
        },
    ),
    Tool(
        name="fs_stats",
        description="获取文件/目录统计信息（大小/行数/修改时间）。\n\n"
                    "Args:\n"
                    "  paths: 路径列表\n\n"
                    "Returns: 统计信息",
        inputSchema={
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["paths"],
        },
    ),
    Tool(
        name="fs_batch_rename",
        description="批量重命名文件（支持替换模式）。\n\n"
                    "Args:\n"
                    "  directory: 目录\n"
                    "  pattern: 匹配模式（支持*）\n"
                    "  replace: 替换为\n"
                    "  dry_run: 只预览不执行\n\n"
                    "Returns: 重命名结果",
        inputSchema={
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "pattern": {"type": "string"},
                "replace": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["directory", "pattern", "replace"],
        },
    ),
    Tool(
        name="fs_watch",
        description="监控目录变化（新增/修改/删除文件）。\n\n"
                    "Args:\n"
                    "  directory: 监控目录\n"
                    "  duration_seconds: 监控时长\n"
                    "  pattern: 只监控匹配模式的文件\n\n"
                    "Returns: 变化事件列表",
        inputSchema={
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "duration_seconds": {"type": "integer", "default": 5},
                "pattern": {"type": "string"},
            },
            "required": ["directory"],
        },
    ),
    Tool(
        name="fs_hash",
        description="计算文件哈希值（MD5/SHA256）。\n\n"
                    "Args:\n"
                    "  path: 文件路径\n"
                    "  algorithm: 算法（md5/sha256）\n\n"
                    "Returns: 哈希值",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "algorithm": {"type": "string", "enum": ["md5", "sha256"], "default": "md5"},
            },
            "required": ["path"],
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具处理函数
# ─────────────────────────────────────────────────────────────────────────────

async def handle_fs_glob(args: dict) -> list[TextContent]:
    pattern = args["pattern"]
    root = args.get("root", _ROOT_DIR)
    max_results = args.get("max_results", 100)

    root_path = Path(root)
    if not root_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Root not found: {root}"}))]

    results = []
    for p in root_path.glob(pattern):
        if "/." in str(p) or p.name.startswith("."):
            continue
        results.append(str(p))
        if len(results) >= max_results:
            break

    return [TextContent(type="text", text=json.dumps({
        "pattern": pattern,
        "root": str(root_path),
        "total_matches": len(results),
        "files": results,
    }, ensure_ascii=False, indent=2))]


async def handle_fs_read(args: dict) -> list[TextContent]:
    paths = args["paths"]
    max_kb = args.get("max_kb", 500)
    encoding = args.get("encoding", "utf-8")

    results = {}
    for p_str in paths:
        p = _norm(p_str)
        results[p_str] = _read_file(p, max_kb, encoding)

    return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]


async def handle_fs_write(args: dict) -> list[TextContent]:
    files = args["files"]
    written = []
    errors = []

    for p_str, content in files.items():
        p = _norm(p_str)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(str(p))
        except Exception as e:
            errors.append({"path": p_str, "error": str(e)})

    return [TextContent(type="text", text=json.dumps({
        "written": written,
        "errors": errors,
        "total": len(files),
    }, ensure_ascii=False, indent=2))]


async def handle_fs_tree(args: dict) -> list[TextContent]:
    root = args.get("root", _ROOT_DIR)
    max_depth = args.get("max_depth", 3)

    root_path = Path(root)
    if not root_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {root}"}))]

    tree = _file_tree(root_path, max_depth)
    return [TextContent(type="text", text=json.dumps({
        "root": str(root_path),
        "total_items": len(tree),
        "tree": tree,
        "markdown": _tree_to_markdown(tree, root_path),
    }, ensure_ascii=False, indent=2))]


def _tree_to_markdown(items: list[dict], root: Path) -> str:
    """转换为markdown树"""
    lines = [f"📁 {root.name}/"]
    for item in items:
        indent = "  " * (item["path"].count(os.sep) - 1)
        icon = "📁" if item["type"] == "dir" else "📄"
        size = f" ({item['size_kb']}KB)" if item["size_kb"] else ""
        lines.append(f"{indent}{icon} {item['name']}{size}")
    return "\n".join(lines)


async def handle_fs_grep(args: dict) -> list[TextContent]:
    pattern = args["pattern"]
    root = args.get("root", _ROOT_DIR)
    file_pattern = args.get("file_pattern", "*")
    regex = args.get("regex", False)
    case_insensitive = args.get("case_insensitive", True)
    max_results = args.get("max_results", 200)

    root_path = Path(root)
    all_results = []
    files_searched = 0

    for p in root_path.glob(f"**/{file_pattern}"):
        if "/." in str(p) or p.name.startswith(".") or p.is_dir():
            continue
        files_searched += 1
        matches = _grep_content(p, pattern, regex, case_insensitive)
        for m in matches:
            all_results.append({"file": str(p.relative_to(root_path)), **m})
        if len(all_results) >= max_results:
            break

    return [TextContent(type="text", text=json.dumps({
        "pattern": pattern,
        "root": str(root_path),
        "files_searched": files_searched,
        "total_matches": len(all_results),
        "results": all_results,
    }, ensure_ascii=False, indent=2))]


async def handle_fs_diff(args: dict) -> list[TextContent]:
    old_path = _norm(args["old_file"])
    new_path = _norm(args["new_file"])

    if not old_path.exists() or not new_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": "One or both files not found"}))]

    try:
        import difflib
        old_lines = old_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        new_lines = new_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(old_path), tofile=str(new_path), lineterm=""))

        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        return [TextContent(type="text", text=json.dumps({
            "old_file": str(old_path),
            "new_file": str(new_path),
            "old_lines": len(old_lines),
            "new_lines": len(new_lines),
            "lines_added": added,
            "lines_removed": removed,
            "diff": "\n".join(diff[:100]),
            "truncated": len(diff) > 100,
        }, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_fs_stats(args: dict) -> list[TextContent]:
    paths = args["paths"]
    results = []

    for p_str in paths:
        p = Path(p_str)
        if p.is_dir():
            total_size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and "/." not in str(f))
            total_files = sum(1 for f in p.rglob("*") if f.is_file() and "/." not in str(f))
            results.append({
                "path": str(p),
                "type": "directory",
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "total_files": total_files,
            })
        elif p.is_file():
            stat = p.stat()
            results.append({
                "path": str(p),
                "type": "file",
                "size_kb": round(stat.st_size / 1024, 1),
                "lines": len(p.read_text(errors="ignore").splitlines()),
                "modified": stat.st_mtime,
            })

    return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]


async def handle_fs_batch_rename(args: dict) -> list[TextContent]:
    directory = args["directory"]
    pattern = args["pattern"]
    replace = args["replace"]
    dry_run = args.get("dry_run", True)

    dir_path = Path(directory)
    if not dir_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {directory}"}))]

    changes = []
    for p in dir_path.glob(pattern):
        if p.is_dir():
            continue
        new_name = p.name.replace(pattern.replace("*", ""), replace) if "*" in pattern else re.sub(pattern, replace, p.name)
        new_path = p.parent / new_name
        changes.append({"old": str(p), "new": str(new_path)})
        if not dry_run:
            p.rename(new_path)

    return [TextContent(type="text", text=json.dumps({
        "directory": str(dir_path),
        "dry_run": dry_run,
        "total_changes": len(changes),
        "changes": changes[:50],
    }, ensure_ascii=False, indent=2))]


async def handle_fs_watch(args: dict) -> list[TextContent]:
    import time
    directory = args["directory"]
    duration = args.get("duration_seconds", 5)
    file_pattern = args.get("pattern", "*")

    dir_path = Path(directory)
    if not dir_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {directory}"}))]

    initial = {str(p): p.stat().st_mtime for p in dir_path.rglob(file_pattern) if p.is_file()}
    time.sleep(duration)
    final = {str(p): p.stat().st_mtime for p in dir_path.rglob(file_pattern) if p.is_file()}

    events = []
    for path, mtime in final.items():
        if path not in initial:
            events.append({"type": "created", "path": path})
        elif mtime > initial[path]:
            events.append({"type": "modified", "path": path})
    for path in initial:
        if path not in final:
            events.append({"type": "deleted", "path": path})

    return [TextContent(type="text", text=json.dumps({
        "directory": str(dir_path),
        "duration_seconds": duration,
        "events": events,
        "total_events": len(events),
    }, ensure_ascii=False, indent=2))]


async def handle_fs_hash(args: dict) -> list[TextContent]:
    path = _norm(args["path"])
    algo = args.get("algorithm", "md5")

    if not path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {path}"}))]

    try:
        if algo == "md5":
            h = hashlib.md5()
        else:
            h = hashlib.sha256()

        h.update(path.read_bytes())
        return [TextContent(type="text", text=json.dumps({
            "path": str(path),
            "algorithm": algo,
            "hash": h.hexdigest(),
            "size_kb": round(path.stat().st_size / 1024, 1),
        }, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "fs_glob": handle_fs_glob,
    "fs_read": handle_fs_read,
    "fs_write": handle_fs_write,
    "fs_tree": handle_fs_tree,
    "fs_grep": handle_fs_grep,
    "fs_diff": handle_fs_diff,
    "fs_stats": handle_fs_stats,
    "fs_batch_rename": handle_fs_batch_rename,
    "fs_watch": handle_fs_watch,
    "fs_hash": handle_fs_hash,
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
    print(f"user-filesystem-mcp starting... root={_ROOT_DIR}", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-filesystem-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
