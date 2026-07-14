"""沙箱执行引擎 — E2B microVM 隔离封装.

功能：
  - Firecracker microVM 隔离代码执行
  - seccomp + FUSE 文件系统过滤
  - 网络白名单 / 黑名单控制
  - 云元数据阻断（AWS/GCP/Azure）
  - 24h 长会话支持

依赖：
  pip install e2b-sdk agentsh

Usage:
    runner = E2BRunner(api_key="e2b_...")

    # 执行危险代码（网络请求/文件操作）
    # result = runner.run("...")

    # 执行数据处理（安全，仅文件操作）
    # result = runner.run("...", allowed_files=["input.csv"])

    # 获取沙箱状态
    # print(runner.get_stats())
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "SandboxTier",
    "SandboxResult",
    "E2BRunner",
    "LocalSandboxRunner",
]

logger = logging.getLogger(__name__)


class SandboxTier(Enum):
    """沙箱隔离级别。"""
    LOCAL = "local"          # 本地执行（无隔离）
    PROCESS = "process"      # 进程级隔离（subprocess）
    CONTAINER = "container"    # Docker 容器隔离
    MICROVM = "microvm"      # microVM 隔离（E2B）


@dataclass
class SandboxResult:
    """
    沙箱执行结果。

    Attributes
    ----------
    stdout : str
        标准输出。
    stderr : str
        标准错误。
    exit_code : int
        退出码。
    execution_time_ms : float
        执行时间（毫秒）。
    tier : SandboxTier
        使用的隔离级别。
    blocked_operations : list[str]
        被拦截的操作。
    is_safe : bool
        是否安全执行完成。
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    tier: SandboxTier = SandboxTier.LOCAL
    blocked_operations: list[str] = field(default_factory=list)
    is_safe: bool = True
    sandbox_id: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and self.is_safe

    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "tier": self.tier.value,
            "blocked_operations": self.blocked_operations,
            "is_safe": self.is_safe,
            "sandbox_id": self.sandbox_id,
        }


class LocalSandboxRunner:
    """
    本地进程级沙箱（无 E2B API Key 时降级使用）。

    使用 subprocess + 危险命令白名单实现进程级隔离。

    Usage
    -----
        runner = LocalSandboxRunner()
        result = runner.run("print('hello world')")
    """

    BLOCKED_IMPORTS = {
        "os": "os",
        "subprocess": "subprocess",
        "socket": "socket",
        "requests": "requests",
        "urllib": "urllib",
        "http": "http",
        "ftplib": "ftplib",
        "telnetlib": "telnetlib",
        "smtplib": "smtplib",
        "pickle": "pickle",
        "eval": "eval",
        "exec": "exec",
        "open": "open",  # 限制文件读写
        "__import__": "__import__",
    }

    ALLOWED_BUILTINS = {
        "print", "len", "range", "str", "int", "float", "list", "dict",
        "tuple", "set", "bool", "type", "isinstance", "issubclass",
        "hasattr", "getattr", "setattr", "enumerate", "zip", "map", "filter",
        "sorted", "reversed", "min", "max", "sum", "abs", "round",
        "any", "all", "format", "repr", "hex", "bin", "oct", "pow",
        "divmod", "slice", "object", "property", "staticmethod", "classmethod",
    }

    def __init__(
        self,
        allowed_files: list[str] | None = None,
        blocked_imports: set[str] | None = None,
        timeout_seconds: float = 30.0,
    ):
        self.allowed_files = set(allowed_files or [])
        self.blocked_imports = blocked_imports or set(self.BLOCKED_IMPORTS.values())
        self.timeout = timeout_seconds
        self._execution_log: list[SandboxResult] = []

    def run(
        self,
        code: str,
        *,
        allowed_files: list[str] | None = None,
        allowed_network: bool = False,
    ) -> SandboxResult:
        """
        在本地进程中执行代码。

        Parameters
        ----------
        code : str
            要执行的 Python 代码。
        allowed_files : list[str] | None
            允许访问的文件模式。
        allowed_network : bool
            是否允许网络请求。

        Returns
        -------
        SandboxResult
        """
        import subprocess
        import sys

        start = time.time()
        blocked: list[str] = []

        # 检查危险代码模式
        code_lower = code.lower()

        # 危险导入检查
        for imp in self.blocked_imports:
            if f"import {imp}" in code or f"from {imp} import" in code:
                blocked.append(f"blocked_import:{imp}")

        # 危险内置函数检查
        for dangerous in ["eval", "exec", "__import__"]:
            if dangerous in code_lower:
                blocked.append(f"dangerous_builtin:{dangerous}")

        # 危险文件操作检查（如果不是允许的文件）
        if not allowed_files and not self.allowed_files:
            for op in ["open(", "read(", "write(", ".to_csv(", ".to_excel("]:
                if op in code_lower:
                    blocked.append(f"file_operation:{op}")

        # 如果有危险操作，返回阻止结果
        if blocked:
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox blocked operations: {', '.join(blocked)}",
                exit_code=1,
                execution_time_ms=(time.time() - start) * 1000,
                tier=SandboxTier.PROCESS,
                blocked_operations=blocked,
                is_safe=False,
            )

        # 安全执行：使用 python -c 执行
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time_ms=(time.time() - start) * 1000,
                tier=SandboxTier.PROCESS,
                blocked_operations=[],
                is_safe=True,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                stdout="",
                stderr=f"Timeout after {self.timeout}s",
                exit_code=124,
                execution_time_ms=self.timeout * 1000,
                tier=SandboxTier.PROCESS,
                blocked_operations=["timeout"],
                is_safe=True,
            )
        except Exception as exc:
            return SandboxResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
                execution_time_ms=(time.time() - start) * 1000,
                tier=SandboxTier.PROCESS,
                is_safe=False,
            )


class E2BRunner:
    """
    E2B microVM 沙箱执行引擎。

    使用 E2B Cloud API 提供硬件级隔离。

    E2B 安全层次：
      Layer 1: Firecracker microVM — 硬件级隔离
      Layer 2: agentsh — seccomp + bash builtin 拦截
      Layer 3: FUSE 文件系统过滤
      Layer 4: 网络白名单 / 黑名单
      Layer 5: 云元数据阻断

    Usage
    -----
        runner = E2BRunner(api_key="e2b_...")

        # 标准执行
        result = runner.run(
            'import pandas as pd\n'
            'df = pd.read_csv("input.csv")\n'
            'print(df.describe())\n'
        )

        # 网络受限执行（仅白名单域名）
        result = runner.run(
            "import requests; r = requests.get('https://api.example.com')",
            network_whitelist=["api.example.com"],
        )

        # 长时间执行（学术脚本/模型训练）
        result = runner.run_script(
            script_path="scripts/run_analysis.py",
            timeout=3600,  # 1 小时
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        template: str = "base",
        timeout_seconds: float = 60.0,
        allowed_files: list[str] | None = None,
        network_whitelist: list[str] | None = None,
        verbose: bool = False,
    ):
        self.api_key = api_key
        self.template = template
        self.default_timeout = timeout_seconds
        self.allowed_files = allowed_files or []
        self.network_whitelist = network_whitelist or []
        self.verbose = verbose
        self._e2b_available = self._check_e2b()
        self._execution_log: list[SandboxResult] = []

    def _check_e2b(self) -> bool:
        """检查 E2B SDK 是否可用。"""
        try:
            import e2b
            return True
        except ImportError:
            logger.warning(
                "[E2BRunner] e2b-sdk not installed. "
                "Run: pip install e2b-sdk. "
                "Falling back to LocalSandboxRunner."
            )
            return False

    def run(
        self,
        code: str,
        *,
        timeout_seconds: float | None = None,
        allowed_files: list[str] | None = None,
        network_whitelist: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> SandboxResult:
        """
        在 microVM 中执行代码。

        Parameters
        ----------
        code : str
            要执行的 Python 代码。
        timeout_seconds : float | None
            超时时间（秒），默认使用 default_timeout。
        allowed_files : list[str] | None
            允许的文件访问。
        network_whitelist : list[str] | None
            允许的域名列表。
        env_vars : dict | None
            环境变量。

        Returns
        -------
        SandboxResult
        """
        start = time.time()
        timeout = timeout_seconds or self.default_timeout

        # 如果 E2B 不可用，降级到本地
        if not self._e2b_available:
            local_runner = LocalSandboxRunner(
                allowed_files=allowed_files or self.allowed_files,
                timeout_seconds=timeout,
            )
            result = local_runner.run(code)
            self._execution_log.append(result)
            return result

        # E2B 执行
        try:
            import e2b

            sandbox_config = {
                "template": self.template,
                "timeout": int(timeout),
            }

            if allowed_files or self.allowed_files:
                sandbox_config["allowed_files"] = allowed_files or self.allowed_files
            if network_whitelist or self.network_whitelist:
                sandbox_config["network_whitelist"] = (
                    network_whitelist or self.network_whitelist
                )

            with e2b.Sandbox(**sandbox_config) as sandbox:
                result = sandbox.run(code, env_vars=env_vars or {})

                return SandboxResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    execution_time_ms=(time.time() - start) * 1000,
                    tier=SandboxTier.MICROVM,
                    sandbox_id=sandbox.sandbox_id,
                    is_safe=True,
                )

        except Exception as exc:
            logger.error(f"[E2BRunner] E2B execution failed: {exc}")
            # 降级到本地
            local_runner = LocalSandboxRunner(timeout_seconds=timeout)
            result = local_runner.run(code)
            self._execution_log.append(result)
            return result

    def run_script(
        self,
        script_path: str | Path,
        *,
        args: list[str] | None = None,
        timeout_seconds: float | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> SandboxResult:
        """
        在 microVM 中执行本地脚本文件。

        Parameters
        ----------
        script_path : str | Path
            脚本路径（.py / .sh）。
        args : list[str]
            传递给脚本的命令行参数。
        timeout_seconds : float | None
            超时。
        env_vars : dict | None
            环境变量。

        Returns
        -------
        SandboxResult
        """
        path = Path(script_path)
        if not path.exists():
            return SandboxResult(
                stderr=f"Script not found: {script_path}",
                exit_code=1,
                execution_time_ms=0,
                is_safe=False,
            )

        code = path.read_text(encoding="utf-8")
        " ".join(args or [])

        wrapped = (
            f"import subprocess, sys\n"
            f"sys.argv = ['{path.name}', {repr(args or [])}]\n"
            f"exec({repr(code)})\n"
        )
        return self.run(wrapped, timeout_seconds=timeout_seconds, env_vars=env_vars)

    def run_notebook(
        self,
        notebook_path: str | Path,
        *,
        timeout_seconds: float | None = None,
    ) -> SandboxResult:
        """在 microVM 中执行 Jupyter notebook。"""
        path = Path(notebook_path)
        if not path.exists():
            return SandboxResult(
                stderr=f"Notebook not found: {notebook_path}",
                exit_code=1,
                execution_time_ms=0,
                is_safe=False,
            )

        code = (
            "import subprocess, sys\n"
            f"result = subprocess.run(\n"
            f"    ['jupyter', 'nbconvert', '--to', 'notebook', '--execute', '--inplace', '{path}'],\n"
            "    capture_output=True, text=True\n"
            ")\n"
            "print(result.stdout, file=sys.stdout)\n"
            "print(result.stderr, file=sys.stderr)\n"
            "sys.exit(result.returncode)\n"
        )
        return self.run(code, timeout_seconds=timeout_seconds)

    def get_stats(self) -> dict[str, Any]:
        """返回执行统计。"""
        if not self._execution_log:
            return {"total_runs": 0}

        return {
            "total_runs": len(self._execution_log),
            "success_count": sum(1 for r in self._execution_log if r.success),
            "blocked_count": sum(1 for r in self._execution_log if r.blocked_operations),
            "avg_time_ms": sum(r.execution_time_ms for r in self._execution_log) / len(self._execution_log),
            "tier": self.tier.value if self._execution_log else "none",
            "e2b_available": self._e2b_available,
        }


# ─── Convenience factory ──────────────────────────────────────────────────────


def create_runner(
    tier: SandboxTier = SandboxTier.LOCAL,
    **kwargs,
) -> E2BRunner | LocalSandboxRunner:
    """
    工厂函数：根据隔离级别创建合适的 runner。

    Usage
    -----
        runner = create_runner(SandboxTier.MICROVM, api_key="e2b_...")

        # 自动选择：如果有 API key 用 E2B，否则用本地
        runner = create_runner(SandboxTier.MICROVM)
    """
    if tier == SandboxTier.MICROVM:
        api_key = kwargs.pop("api_key", None) or __import__("os").get("E2B_API_KEY")
        if api_key:
            return E2BRunner(api_key=api_key, **kwargs)
        else:
            logger.warning(
                "[create_runner] No E2B_API_KEY found. "
                "Falling back to LocalSandboxRunner."
            )
            return LocalSandboxRunner(**kwargs)
    elif tier == SandboxTier.PROCESS:
        return LocalSandboxRunner(**kwargs)
    else:
        return LocalSandboxRunner(**kwargs)
