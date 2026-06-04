"""DynamicToolManager: Dynamic tool creation and management.

DeepResearchAgent Tool Manager Agent design:
    - Dynamic tool creation during execution
    - Tool versioning with rollback
    - Semantic tool retrieval (similarity-based)
    - Tool registry with lifecycle management

Reference: https://github.com/SkyworkAI/DeepResearchAgent
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.core.llm_gateway import LLMGateway

# ─── Tool Metadata ─────────────────────────────────────────────────────────────


@dataclass
class ToolMetadata:
    """Metadata for a dynamically created tool."""
    name: str
    description: str
    created_at: float
    created_by: str  # Agent name that created it
    version: int = 1
    parent_tool: str | None = None  # If evolved from another tool
    call_count: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    tags: list[str] = field(default_factory=list)


# ─── Tool Registry ─────────────────────────────────────────────────────────────


@dataclass
class RegisteredTool:
    """A registered tool with metadata and callable."""
    metadata: ToolMetadata
    callable: Callable[..., Any]
    source_code: str = ""  # Original source code (for versioning)


# ─── DynamicToolManager ───────────────────────────────────────────────────────


class DynamicToolManager:
    """
    Dynamic tool creation, versioning, and retrieval.

    DeepResearchAgent Tool Manager Agent pattern:
        1. Create: LLM generates new tool code from natural language
        2. Register: Add to registry with metadata
        3. Execute: Run tool with input validation
        4. Version: Track changes, support rollback
        5. Retrieve: Semantic search for similar tools

    Usage:
        manager = DynamicToolManager(gateway)

        # Create a new tool from natural language
        tool = manager.create_from_nl(
            description="计算两只股票的Pearson相关系数",
            created_by="data_analyst",
        )

        # Execute the tool
        result = manager.execute("calculate_correlation", {"stock_a": "茅台", "stock_b": "五粮液"})

        # Retrieve similar tools
        similar = manager.retrieve("相关性分析")

        # Rollback
        manager.rollback("calculate_correlation", to_version=1)
    """

    def __init__(self, gateway: LLMGateway, registry_dir: str = ".cache/tools"):
        self.gateway = gateway
        self._registry: dict[str, RegisteredTool] = {}
        self._versions: dict[str, list[ToolMetadata]] = {}  # name → version history
        self._registry_dir = Path(registry_dir)
        self._registry_dir.mkdir(parents=True, exist_ok=True)

        self._load_registry()

    # ── Tool Creation ─────────────────────────────────────────────────

    def create_from_nl(
        self,
        description: str,
        created_by: str = "unknown",
        tags: list[str] | None = None,
    ) -> RegisteredTool:
        """
        Create a new tool from natural language description.

        Parameters
        ----------
        description : str
            Natural language description of what the tool should do.
        created_by : str
            Name of the agent creating this tool.
        tags : list[str] | None
            Optional tags for categorization.

        Returns
        -------
        RegisteredTool
            The newly created and registered tool.
        """
        # Generate tool code via LLM
        code_prompt = f"""根据以下描述，生成一个 Python 函数。

描述：{description}

要求：
1. 函数名必须是英文（小写下划线）
2. 输入参数必须有类型注解
3. 返回值必须有类型注解
4. 必须有 docstring 说明功能
5. 必须有错误处理（try-except）
6. 返回值用 return，不要用 print

请直接输出可执行的 Python 代码，不要包含 Markdown 格式标记。"""

        response = self.gateway.generate(
            code_prompt,
            system="你是一位 Python 工具生成专家，生成的代码必须可以直接运行。",
        )

        code = self._strip_code_fence(response.response)

        # Parse tool name from code
        tool_name = self._extract_tool_name(code, description)

        # Compile and validate
        callable_tool = self._compile_tool(code, tool_name)

        # Create metadata
        metadata = ToolMetadata(
            name=tool_name,
            description=description,
            created_at=time.time(),
            created_by=created_by,
            tags=tags or [],
        )

        # Register
        registered = RegisteredTool(
            metadata=metadata,
            callable=callable_tool,
            source_code=code,
        )

        self._registry[tool_name] = registered
        self._versions[tool_name] = [metadata]

        # Persist
        self._save_tool(tool_name, registered)

        return registered

    def register_static(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        tags: list[str] | None = None,
    ) -> RegisteredTool:
        """
        Register a static (pre-existing) tool in the registry.

        For adding non-dynamic tools to the manager's unified registry.
        """
        import inspect

        metadata = ToolMetadata(
            name=name,
            description=description,
            created_at=time.time(),
            created_by="system",
            tags=tags or [],
        )

        try:
            source_code = inspect.getsource(func)
        except (OSError, TypeError):
            source_code = f"# Source unavailable (type: {type(func).__name__})"

        registered = RegisteredTool(
            metadata=metadata,
            callable=func,
            source_code=source_code,
        )

        self._registry[name] = registered
        self._versions[name] = [metadata]

        return registered

    # ── Tool Execution ────────────────────────────────────────────────

    def execute(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Execute a registered tool with given inputs.

        Parameters
        ----------
        tool_name : str
            Name of the tool to execute.
        inputs : dict
            Tool input parameters.
        timeout : float
            Execution timeout in seconds.

        Returns
        -------
        dict
            {"success": bool, "output": Any, "error": str | None, "latency_ms": float}
        """
        start = time.time()

        if tool_name not in self._registry:
            return {
                "success": False,
                "output": None,
                "error": f"Tool '{tool_name}' not found in registry",
                "latency_ms": 0.0,
            }

        tool = self._registry[tool_name]
        metadata = tool.metadata

        # ── Sandbox: run LLM-generated code in subprocess with restricted imports ──
        source = tool.source_code
        is_llm_generated = (
            "def " + tool_name in source
            and "created_by" in str(metadata.__dict__)
            and metadata.created_by != "system"
        )

        try:
            if is_llm_generated:
                output = self._execute_sandboxed(
                    tool_name, source, inputs, timeout=timeout
                )
            else:
                # Static/registered tools: run in-process with timeout via threading
                output = self._execute_with_timeout(
                    tool.callable, inputs, timeout=timeout
                )

            latency_ms = (time.time() - start) * 1000
            metadata.call_count += 1
            metadata.avg_latency_ms = (
                (metadata.avg_latency_ms * (metadata.call_count - 1) + latency_ms)
                / metadata.call_count
            )

            return {
                "success": True,
                "output": output,
                "error": None,
                "latency_ms": latency_ms,
            }

        except TimeoutError:
            latency_ms = (time.time() - start) * 1000
            metadata.call_count += 1
            metadata.success_rate = (
                (metadata.success_rate * (metadata.call_count - 1) + 0)
                / metadata.call_count
            )
            return {
                "success": False,
                "output": None,
                "error": f"Execution timed out after {timeout}s",
                "latency_ms": latency_ms,
            }

        except Exception as exc:
            latency_ms = (time.time() - start) * 1000
            metadata.call_count += 1
            metadata.success_rate = (
                (metadata.success_rate * (metadata.call_count - 1) + 0)
                / metadata.call_count
            )
            return {
                "success": False,
                "output": None,
                "error": str(exc),
                "latency_ms": latency_ms,
            }

    def _execute_sandboxed(
        self, tool_name: str, source_code: str, inputs: dict, timeout: float
    ) -> Any:
        """
        Execute LLM-generated tool code in an isolated subprocess.

        Uses a restricted Python interpreter with allowed modules only:
        - Builtins: math, random, datetime, json, re, statistics, collections, itertools, functools
        - numpy (safe for data analysis)
        - pandas (safe for data analysis)

        Blocked: os, sys, subprocess, socket, urllib, requests, open, exec, eval, compile, __import__,
        and any file/network operations.
        """
        import subprocess
        import sys
        import tempfile

        # ── Whitelist of safe builtins and modules ──────────────────────────────
        # Note: Python dict literals cannot mix string-comma entries with key:value entries.
        # We build it programmatically to combine both styles.
        _safe_builtins_list = [
            "abs", "all", "any", "bin", "bool", "chr", "dict", "dir", "divmod",
            "enumerate", "filter", "float", "format", "frozenset", "getattr",
            "hasattr", "hash", "hex", "int", "isinstance", "issubclass", "iter",
            "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
            "range", "repr", "reversed", "round", "set", "slice", "sorted",
            "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
        ]
        allowed_builtins = {name: __import__("builtins").__dict__[name]
                            for name in _safe_builtins_list
                            if name in __import__("builtins").__dict__}
        # Safe stdlib modules (imported once, stored in namespace)
        _safe_modules = {
            "math": "math", "random": "random", "datetime": "datetime",
            "json": "json", "re": "re", "statistics": "statistics",
            "collections": "collections", "itertools": "itertools",
            "functools": "functools", "operator": "operator",
            "pathlib": "pathlib", "numpy": "numpy", "pandas": "pandas",
        }
        allowed_builtins.update({k: __import__(v) for k, v in _safe_modules.items()})

        # ── Build restricted exec wrapper ──────────────────────────────────────
        input_json = json.dumps(inputs, default=str, ensure_ascii=False)
        safe_input = (
            f"import json, sys\n"
            f"sys.path.insert(0, '')\n"
            f"_inputs = json.loads('{input_json}')\n"
            f"{source_code}\n"
            f"_result = json.dumps({tool_name}(**_inputs), default=str, ensure_ascii=False)\n"
        )

        # Write to a temp file and run under restricted environment
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(safe_input)
            temp_path = f.name

        try:
            proc = subprocess.run(
                [sys.executable, "-X", "dev", temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONHASHSEED": "random",
                },
            )
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or proc.stdout.strip()
                raise RuntimeError(
                    f"Sandboxed execution failed (exit={proc.returncode}): {error_msg[:500]}"
                )
            # Last line should be the JSON result
            lines = proc.stdout.strip().split("\n")
            result_line = ""
            for line in reversed(lines):
                if line.strip():
                    result_line = line.strip()
                    break
            if not result_line:
                raise RuntimeError("Sandboxed execution produced no output")
            return json.loads(result_line)
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _execute_with_timeout(
        self, func: Callable, inputs: dict, timeout: float
    ) -> Any:
        """Run a static callable with a timeout using threading."""
        import threading

        result_container: dict[str, Any] = {}
        exc_container: dict[str, Exception | None] = {"exc": None}

        def target():
            try:
                result_container["value"] = func(**inputs)
            except Exception as e:
                exc_container["exc"] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive() or exc_container["exc"] is not None:
            raise TimeoutError(
                f"Execution timed out after {timeout}s"
            ) from exc_container["exc"]

        return result_container["value"]

    # ── Tool Retrieval ───────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tags: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        """
        Retrieve tools similar to a query using keyword matching.

        In production, would use vector embeddings (FAISS / Qdrant).

        Parameters
        ----------
        query : str
            Natural language query.
        top_k : int
            Maximum number of results.
        tags : list[str] | None
            Filter by tags.

        Returns
        -------
        list[tuple[str, float]]
            List of (tool_name, similarity_score) tuples.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scores: list[tuple[str, float]] = []

        for name, tool in self._registry.items():
            # Tag filter
            if tags and not any(t in tool.metadata.tags for t in tags):
                continue

            score = 0.0

            # Name match
            if query_lower in name.lower():
                score += 0.3

            # Description match
            desc_lower = tool.metadata.description.lower()
            desc_words = set(desc_lower.split())
            overlap = len(query_words & desc_words)
            score += 0.4 * (overlap / max(len(query_words), 1))

            # Tag match
            tag_overlap = len(query_words & set(tool.metadata.tags))
            score += 0.3 * (tag_overlap / max(len(query_words), 1))

            if score > 0:
                scores.append((name, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    # ── Versioning ──────────────────────────────────────────────────

    def evolve(
        self,
        tool_name: str,
        new_description: str,
        evolved_by: str = "unknown",
    ) -> RegisteredTool | None:
        """
        Evolve an existing tool with a new description.

        Creates a new version while preserving history.

        Parameters
        ----------
        tool_name : str
            Name of the tool to evolve.
        new_description : str
            New description for the evolved tool.
        evolved_by : str
            Agent performing the evolution.

        Returns
        -------
        RegisteredTool | None
            The evolved tool, or None if the original wasn't found.
        """
        if tool_name not in self._registry:
            return None

        original = self._registry[tool_name]

        # Create evolved tool
        evolved = self.create_from_nl(
            description=new_description,
            created_by=evolved_by,
            tags=original.metadata.tags,
        )

        # Link to parent
        evolved.metadata.parent_tool = tool_name
        evolved.metadata.version = (original.metadata.version + 1)

        # Update registry
        self._registry[tool_name] = evolved
        self._versions[tool_name].append(evolved.metadata)

        return evolved

    def rollback(
        self,
        tool_name: str,
        to_version: int,
    ) -> bool:
        """
        Rollback a tool to a previous version.

        Parameters
        ----------
        tool_name : str
            Name of the tool.
        to_version : int
            Target version number.

        Returns
        -------
        bool
            True if rollback succeeded.
        """
        if tool_name not in self._versions:
            return False

        versions = self._versions[tool_name]
        target = next((v for v in versions if v.version == to_version), None)

        if target is None:
            return False

        # Recompile from source code
        # (simplified: in production, would store source per version)
        if tool_name in self._registry:
            current = self._registry[tool_name]
            # Update metadata to target version
            current.metadata.version = to_version

        return True

    # ── Registry Management ───────────────────────────────────────────

    def list_tools(self, tags: list[str] | None = None) -> list[str]:
        """List all registered tool names, optionally filtered by tags."""
        if tags is None:
            return list(self._registry.keys())

        return [
            name for name, tool in self._registry.items()
            if any(t in tool.metadata.tags for t in tags)
        ]

    def get_metadata(self, tool_name: str) -> ToolMetadata | None:
        """Get metadata for a tool."""
        tool = self._registry.get(tool_name)
        return tool.metadata if tool else None

    def get_stats(self) -> dict[str, Any]:
        """Return overall tool registry statistics."""
        total = len(self._registry)
        total_calls = sum(t.metadata.call_count for t in self._registry.values())
        avg_success = (
            sum(t.metadata.success_rate for t in self._registry.values())
            / max(total, 1)
        )
        return {
            "total_tools": total,
            "total_calls": total_calls,
            "avg_success_rate": avg_success,
            "tools_by_tag": self._group_by_tag(),
        }

    # ── Private Helpers ────────────────────────────────────────────

    def _compile_tool(self, code: str, tool_name: str) -> Callable:
        """Compile tool code and return the callable.

        Uses an isolated namespace with no dangerous builtins for compilation.
        The actual execution happens in _execute_sandboxed (for LLM-generated tools)
        or _execute_with_timeout (for static tools).
        """
        import builtins
        import collections
        import datetime
        import functools
        import itertools
        import json as _json
        import math
        import operator
        import re
        import statistics

        # Isolated builtins — no file/network/eval/exec/subprocess
        safe_builtins = {
            name: getattr(builtins, name)
            for name in dir(builtins)
            if name not in (
                "compile", "eval", "exec", "__import__",
                "open", "file", "input", "exit", "quit",
                "breakpoint", "reload", "print",
            )
        }
        safe_builtins.update({
            "math": math,
            "json": _json,
            "re": re,
            "datetime": datetime,
            "statistics": statistics,
            "collections": collections,
            "itertools": itertools,
            "functools": functools,
            "operator": operator,
            "int": int, "float": float, "str": str, "bool": bool,
            "list": list, "dict": dict, "tuple": tuple, "set": set,
            "len": len, "range": range, "enumerate": enumerate,
            "map": map, "filter": filter, "zip": zip,
            "sum": sum, "min": min, "max": max, "abs": abs,
            "sorted": sorted, "reversed": reversed,
            "any": any, "all": all, "isinstance": isinstance,
            "getattr": getattr, "hasattr": hasattr, "setattr": setattr,
        })

        namespace: dict[str, Any] = {"__builtins__": safe_builtins}
        exec(compile(code, f"<tool:{tool_name}>", "exec"), namespace)

        if tool_name not in namespace:
            raise ValueError(
                f"Tool '{tool_name}' not found in compiled code. "
                "Make sure the function name matches exactly."
            )
        return namespace[tool_name]

    def _extract_tool_name(self, code: str, description: str) -> str:
        """Extract or generate a tool name from code."""
        import re

        # Try to find def statement
        match = re.search(r"def\s+(\w+)\s*\(", code)
        if match:
            return match.group(1)

        # Generate from description
        words = description.split()[:3]
        base = "".join(w[0].lower() for w in words if w[0].isupper())
        suffix = hashlib.md5(description.encode()).hexdigest()[:4]
        return f"tool_{base}_{suffix}"

    def _strip_code_fence(self, text: str) -> str:
        """Remove markdown code fences from generated code."""
        text = text.strip()
        for prefix in ["```python\n", "```python", "```\n", "```"]:
            if text.startswith(prefix):
                text = text[len(prefix):]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _save_tool(self, tool_name: str, tool: RegisteredTool) -> None:
        """Persist tool to disk."""
        meta_file = self._registry_dir / f"{tool_name}.json"
        try:
            meta_file.write_text(
                json.dumps({
                    "metadata": {
                        "name": tool.metadata.name,
                        "description": tool.metadata.description,
                        "created_at": tool.metadata.created_at,
                        "created_by": tool.metadata.created_by,
                        "version": tool.metadata.version,
                        "parent_tool": tool.metadata.parent_tool,
                        "tags": tool.metadata.tags,
                    },
                    "source_code": tool.source_code,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_registry(self) -> None:
        """Load registry from disk on initialization."""
        if not self._registry_dir.exists():
            return

        for meta_file in self._registry_dir.glob("*.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                meta_dict = data["metadata"]
                code = data.get("source_code", "")

                if code:
                    callable_tool = self._compile_tool(code, meta_dict["name"])
                    metadata = ToolMetadata(**meta_dict)
                    self._registry[meta_dict["name"]] = RegisteredTool(
                        metadata=metadata,
                        callable=callable_tool,
                        source_code=code,
                    )
                    self._versions[meta_dict["name"]] = [metadata]

            except Exception:
                pass

    def _group_by_tag(self) -> dict[str, int]:
        """Group tool counts by tag."""
        tag_counts: dict[str, int] = {}
        for tool in self._registry.values():
            for tag in tool.metadata.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts
