"""SafeCodeExecutor: Secure code execution sandbox for the research agent pipeline.

This module provides a safe code execution environment for running user-provided
Python code in the PaperOrchestra pipeline, with AST-based security checks and
resource limits.

Features:
1. AST-based security validation (block dangerous imports/builtins/patterns)
2. Configurable resource limits (timeout, memory, CPU, output size)
3. Multiple execution modes (restricted, subprocess, docker)
4. Safe execution context with whitelisted packages
5. Chart capture (matplotlib → base64 PNG)
6. Integration with PlottingAgent/agent_pipeline

Usage:
    from scripts.core.sandbox import SafeCodeExecutor

    executor = SafeCodeExecutor(timeout=60, max_memory_mb=512)
    result = executor.execute("import numpy as np; print(np.mean([1,2,3]))")
    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")
"""

from __future__ import annotations

__all__ = [
    "ExecutionMode",
    "ExecutionResult",
    "ValidationResult",
    "_safe_savefig",
    "main",
]

import ast
import base64
import builtins
import io
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_MEMORY_MB = 512
DEFAULT_MAX_CPU_PERCENT = 80
DEFAULT_MAX_OUTPUT_CHARS = 50000

# Whitelisted imports for scientific computing
ALLOWED_IMPORTS: set[str] = {
    "numpy", "pandas", "matplotlib", "scipy", "statsmodels",
    "sklearn", "seaborn", "plotly", "itertools", "functools",
    "collections", "re", "json", "math", "datetime", "typing",
    "warnings", "copy", "abc", "numbers", "fractions",
    "decimal", "pprint", "operator", "io", "os"  # limited os.path only
}

# Dangerous imports to block
BLOCKED_IMPORTS: set[str] = {
    "os", "subprocess", "socket", "urllib", "requests", "httpx",
    "ftplib", "telnetlib", "telnet", "smtplib", "poplib", "imaplib",
    "nntplib", "xmlrpc", "xmlrpclib", "multiprocessing", "concurrent",
    "threading", "asyncio", "aiohttp", "asyncpg", "redis",
    "pymongo", "mysql", "sqlite3", "psycopg", "pymemcache",
    "ctypes", "cffi", "cython",
    "shutil", "glob", "pathlib",  # filesystem ops
    "pickle", "marshal", "struct",
    "gc", "sys", "builtins",
    "signal", "atexit", "exit", "quit",
    "exec", "eval", "compile", "input",
    "open", "file", "webbrowser", "cgi", "wsgiref",
    "code", "codeop", "dis", "inspect",
    "sysconfig", "platform", "platformdirs",
    "tempfile", "shelve",
}

# Dangerous builtins to block
BLOCKED_BUILTINS: set[str] = {
    "eval", "exec", "compile", "__import__",
    "reload", "breakpoint", "exit", "quit", "license",
    "help", "dir", "vars", "object",
    "memoryview", "classmethod", "staticmethod",
    "super", "property", "issubclass", "isinstance",
    "__build_class__", "__loader__", "__spec__",
    "__import_submodules__", "__package__",
    "input",  # block input() to prevent interactive blocking
}

# Allowed builtins (subset of safe builtins)
ALLOWED_BUILTINS: set[str] = {
    "len", "range", "str", "int", "float", "list", "dict",
    "tuple", "set", "bool", "sum", "min", "max", "sorted",
    "enumerate", "zip", "map", "filter", "round", "abs",
    "any", "all", "isinstance", "issubclass", "type",
    "hasattr", "getattr", "setattr", "delattr",
    "repr", "hash", "id", "format", "chr", "ord",
    "slice", "complex", "bin", "hex", "oct",
    "frozenset", "bytearray", "bytes", "memoryview",
    "print",  # allowed via safe_print wrapper
}

# ─── Enums ────────────────────────────────────────────────────────────────────


class ExecutionMode(Enum):
    """Execution mode for the sandbox."""
    RESTRICTED = "restricted"   # AST-validated exec() in subprocess
    SUBPROCESS = "subprocess"   # Full subprocess with ulimit/resource limits
    DOCKER = "docker"           # Docker container execution (if available)


# ─── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Result of a safe code execution."""
    success: bool
    stdout: str
    stderr: str
    charts: list[str] = field(default_factory=list)  # base64-encoded PNG images
    execution_time_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "charts": self.charts,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
        }


@dataclass
class ValidationResult:
    """Result of code validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── AST Validators ──────────────────────────────────────────────────────────


class SecurityValidator(ast.NodeVisitor):
    """AST-based security checker for Python code."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name.split(".")[0]
            if name in BLOCKED_IMPORTS:
                self.errors.append(f"Blocked import: '{name}'")
            elif name not in ALLOWED_IMPORTS:
                self.warnings.append(f"Unknown import: '{name}' (allowed by default)")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            name = node.module.split(".")[0]
            if name in BLOCKED_IMPORTS:
                self.errors.append(f"Blocked import: 'from {node.module}'")
            elif name not in ALLOWED_IMPORTS:
                self.warnings.append(f"Unknown import: 'from {node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("eval", "exec", "compile", "__import__", "open",
                          "reload", "breakpoint", "exit", "quit", "input"):
            self.errors.append(f"Dangerous function call: '{func_name}'")

        if func_name == "getattr" and len(node.args) >= 3:
            self.warnings.append("getattr with default may access restricted attrs")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "os":
            dangerous_os_attrs = {"system", "popen", "spawn", "execl",
                                  "execv", "fork", "kill", "chmod",
                                  "chown", "remove", "unlink", "rmdir",
                                  "rename", "mkdir", "makedirs"}
            if node.attr in dangerous_os_attrs:
                self.errors.append(f"Dangerous os attribute: 'os.{node.attr}'")

        if isinstance(node.value, ast.Name) and node.value.id == "subprocess":
            dangerous_subprocess = {"run", "Popen", "call", "check_call",
                                     "check_output", "DEVNULL", "STDOUT"}
            if node.attr in dangerous_subprocess:
                self.errors.append(f"Dangerous subprocess call: 'subprocess.{node.attr}'")

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in BLOCKED_BUILTINS and node.id != "print":
            self.errors.append(f"Blocked builtin: '{node.id}'")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
            self.errors.append("Access to __builtins__ is blocked")
        self.generic_visit(node)


class PatternValidator:
    """Regex-based pattern validator for additional security checks."""

    DANGEROUS_PATTERNS: list[tuple[str, str]] = [
        (r"__import__\s*\(", "Dynamic import detected"),
        (r"exec\s*\(", "exec() detected"),
        (r"eval\s*\(", "eval() detected"),
        (r"compile\s*\(", "compile() detected"),
        (r"open\s*\([^)]*[\"'][rwa][\"']", "File open() detected"),
        (r"getattr\s*\([^,]+,[^,]+,[^)]+\)", "getattr with default may access restricted attrs"),
        (r"setattr\s*\([^,]+,[^,]+,[^)]+\)", "setattr on arbitrary objects"),
        (r"hasattr\s*\([^,]+,", "hasattr on dynamic attributes"),
        (r"import\s+os\s*;", "os import detected"),
        (r"import\s+subprocess\s*;", "subprocess import detected"),
        (r"import\s+socket\s*;", "socket import detected"),
        (r"import\s+requests\s*;", "requests import detected"),
        (r"import\s+urllib\s*;", "urllib import detected"),
        (r"from\s+os\s+import", "os module access detected"),
        (r"from\s+subprocess\s+import", "subprocess module access detected"),
        (r"subprocess\.run", "subprocess.run detected"),
        (r"subprocess\.Popen", "subprocess.Popen detected"),
        (r"socket\.socket", "socket creation detected"),
        (r"os\.system", "os.system detected"),
        (r"os\.popen", "os.popen detected"),
        (r"os\.chmod", "os.chmod detected"),
        (r"os\.chown", "os.chown detected"),
        (r"os\.remove", "os.remove detected"),
        (r"os\.unlink", "os.unlink detected"),
        (r"os\.rename", "os.rename detected"),
        (r"sys\.exit", "sys.exit detected"),
        (r"exit\s*\(", "exit() detected"),
        (r"quit\s*\(", "quit() detected"),
        (r"signal\.signal", "signal handler modification detected"),
        (r"resource\.setrlimit", "resource limit modification detected"),
    ]

    def validate(self, code: str) -> list[str]:
        errors = []
        for pattern, message in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                errors.append(message)
        return errors


# ─── Safe Code Executor ───────────────────────────────────────────────────────


class SafeCodeExecutor:
    """
    Secure code execution sandbox for the research agent pipeline.

    Provides AST-based security validation, resource limits, and safe execution
    context for running user-provided Python code.

    Args:
        timeout: Maximum execution time in seconds (default: 60)
        max_memory_mb: Maximum memory usage in MB (default: 512)
        max_cpu_percent: Maximum CPU usage percentage (default: 80)
        max_output_chars: Maximum stdout/stderr characters (default: 50000)
        mode: Execution mode (default: RESTRICTED)
        allowed_imports: Custom set of allowed imports (optional)
        blocked_builtins: Custom set of blocked builtins (optional)
        output_dir: Directory to save generated charts (optional)

    Example:
        executor = SafeCodeExecutor(timeout=30, max_memory_mb=256)
        result = executor.execute('''
            import numpy as np
            import matplotlib.pyplot as plt
            x = np.linspace(0, 10, 100)
            plt.plot(x, np.sin(x))
            plt.savefig("sin_wave.png")
        ''')
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        max_cpu_percent: int = DEFAULT_MAX_CPU_PERCENT,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        mode: ExecutionMode = ExecutionMode.RESTRICTED,
        allowed_imports: set[str] | None = None,
        blocked_builtins: set[str] | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent
        self.max_output_chars = max_output_chars
        self.mode = mode
        self.allowed_imports = allowed_imports or ALLOWED_IMPORTS
        self.blocked_builtins = blocked_builtins or BLOCKED_BUILTINS
        self.output_dir = Path(output_dir) if output_dir else Path("data/charts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._ast_validator = SecurityValidator()
        self._pattern_validator = PatternValidator()

    def validate(self, code: str) -> ValidationResult:
        """
        Validate code before execution.

        Args:
            code: Python code string to validate

        Returns:
            ValidationResult with valid status and list of errors/warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Step 1: AST parsing
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ValidationResult(
                valid=False,
                errors=[f"Syntax error: {e.msg} at line {e.lineno}, col {e.offset}"],
            )
        except ValueError as e:
            return ValidationResult(
                valid=False,
                errors=[f"AST parsing error: {str(e)}"],
            )

        # Step 2: AST-based security check
        visitor = SecurityValidator()
        visitor.visit(tree)
        errors.extend(visitor.errors)
        warnings.extend(visitor.warnings)

        # Step 3: Pattern-based security check
        pattern_errors = self._pattern_validator.validate(code)
        errors.extend(pattern_errors)

        # Step 4: Check for dangerous string patterns in code
        dangerous_strings = [
            (r"rm\s+-rf", "Command 'rm -rf' detected"),
            (r"chmod\s+777", "Dangerous chmod 777 detected"),
            (r"curl.*\|.*sh", "Pipe to shell detected"),
            (r"wget.*\|.*sh", "Pipe to shell detected"),
            (r"nc\s+-e", "Netcat reverse shell pattern detected"),
            (r"bash\s+-i", "Interactive bash shell detected"),
            (r"python.*-c.*import", "Inline python import detected"),
        ]
        for pattern, msg in dangerous_strings:
            if re.search(pattern, code, re.IGNORECASE):
                errors.append(msg)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(self, code: str, context: dict[str, Any] | None = None) -> ExecutionResult:
        """
        Execute code safely and return result.

        Args:
            code: Python code string to execute
            context: Optional context dict to inject into execution namespace

        Returns:
            ExecutionResult with stdout, stderr, charts, timing, and error info
        """
        start_time = time.time()

        # Step 1: Validate code
        validation = self.validate(code)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        # Step 2: Execute based on mode
        if self.mode == ExecutionMode.RESTRICTED:
            return self._execute_restricted(code, context, start_time)
        elif self.mode == ExecutionMode.SUBPROCESS:
            return self._execute_subprocess(code, context, start_time)
        elif self.mode == ExecutionMode.DOCKER:
            return self._execute_docker(code, context, start_time)
        else:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Unknown execution mode: {self.mode}",
            )

    def _execute_restricted(
        self,
        code: str,
        context: dict[str, Any] | None,
        start_time: float,
    ) -> ExecutionResult:
        """Execute code using restricted Python (AST-validated exec())."""
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        charts: list[str] = []

        # Set current charts ref for capture
        self._current_charts = charts

        # Build safe globals with pre-loaded packages
        safe_globals: dict[str, Any] = {
            "__name__": "__sandbox__",
            "__builtins__": self._get_safe_builtins(),
            "__doc__": None,
            "__package__": None,
        }

        # Pre-load allowed packages to avoid import issues
        for pkg in ["numpy", "pandas", "matplotlib", "scipy", "sklearn", "seaborn", "plotly"]:
            try:
                safe_globals[pkg] = __import__(pkg)
            except ImportError:
                pass  # Package not available

        # Build safe locals
        safe_locals: dict[str, Any] = {}

        # Inject context
        if context:
            safe_locals.update(context)

        try:
            # Execute with timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._exec_wrapper,
                    code,
                    safe_globals,
                    safe_locals,
                    stdout_buffer,
                    stderr_buffer,
                )
                try:
                    future.result(timeout=self.timeout)
                except FuturesTimeoutError:
                    return ExecutionResult(
                        success=False,
                        stdout=self._truncate(stdout_buffer.getvalue()),
                        stderr=self._truncate(stderr_buffer.getvalue() + "\nExecution timeout"),
                        charts=charts,
                        execution_time_ms=(time.time() - start_time) * 1000,
                        error=f"Execution timeout after {self.timeout}s",
                    )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout=self._truncate(stdout_buffer.getvalue()),
                stderr=self._truncate(stderr_buffer.getvalue()),
                charts=charts,
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Execution error: {str(e)}",
            )

        execution_time_ms = (time.time() - start_time) * 1000
        stderr_output = stderr_buffer.getvalue()

        if "Error" in stderr_output or "Traceback" in stderr_output:
            return ExecutionResult(
                success=False,
                stdout=self._truncate(stdout_buffer.getvalue()),
                stderr=self._truncate(stderr_output),
                charts=charts,
                execution_time_ms=execution_time_ms,
                error=f"Runtime error: {stderr_output[:500]}",
            )

        return ExecutionResult(
            success=True,
            stdout=self._truncate(stdout_buffer.getvalue()),
            stderr=self._truncate(stderr_output),
            charts=charts,
            execution_time_ms=execution_time_ms,
            error=None,
        )

    def _exec_wrapper(
        self,
        code: str,
        safe_globals: dict[str, Any],
        safe_locals: dict[str, Any],
        stdout_buffer: io.StringIO,
        stderr_buffer: io.StringIO,
    ) -> None:
        """Wrapper for exec with stdout/stderr capture."""
        # Redirect stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_buffer
        sys.stderr = stderr_buffer

        try:
            # Setup safe matplotlib with chart capture
            self._setup_safe_matplotlib_with_capture()

            # Execute code
            exec(code, safe_globals, safe_locals)  # noqa: S102
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def _setup_safe_matplotlib(self) -> None:
        """Setup matplotlib with safe Agg backend."""
        try:
            import matplotlib
            matplotlib.use("Agg")
        except Exception:
            pass

    def _setup_safe_matplotlib_with_capture(self) -> None:
        """Setup matplotlib with Agg backend and chart capture."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import base64
            import io as io_module

            import matplotlib.pyplot as plt

            # Reference to the charts list in outer scope
            charts_ref = getattr(self, '_current_charts', [])

            # Store original savefig
            original_savefig = plt.savefig

            def safe_savefig(*args: Any, **kwargs: Any) -> Any:
                """Capture chart as base64 PNG."""
                buf = io_module.BytesIO()
                # Capture to buffer with fixed settings
                kwargs_copy = dict(kwargs)
                kwargs_copy.pop("format", None)
                kwargs_copy.pop("dpi", None)
                kwargs_copy.pop("bbox_inches", None)
                result = original_savefig(buf, format="png", bbox_inches="tight", dpi=100, **kwargs_copy)
                buf.seek(0)
                charts_ref.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
                buf.close()
                return result

            plt.savefig = safe_savefig
        except ImportError:
            pass

    def _get_safe_builtins(self) -> dict[str, Any]:
        """Get safe builtins dict."""
        safe = {}
        for name in ALLOWED_BUILTINS:
            try:
                safe[name] = getattr(builtins, name)
            except AttributeError:
                pass

        # Add safe print
        def safe_print(*args: Any, **kwargs: Any) -> None:
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            file = kwargs.get("file", sys.stdout)
            if file == sys.stdout or file is None:
                print(*args, sep=sep, end=end, file=file)
        safe["print"] = safe_print

        # Add safe import that only allows pre-approved packages
        _ALLOWED_IMPORT_PACKAGES = frozenset({
            "numpy", "pandas", "matplotlib", "scipy", "sklearn",
            "seaborn", "plotly", "statsmodels", "dateutil", "tqdm",
        })

        def _safe_import(name: str, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            """Restricted import — only pre-approved packages allowed."""
            root = name.split(".")[0]
            if root not in _ALLOWED_IMPORT_PACKAGES:
                raise ImportError(
                    f"Sandbox restricts imports to {_ALLOWED_IMPORT_PACKAGES}; "
                    f"'{root}' is not allowed. "
                    f"Use pre-loaded packages: numpy, pandas, matplotlib, scipy, etc."
                )
            return builtins.__import__(name, globals_dict, locals_dict, fromlist, level)

        safe["__import__"] = _safe_import

        return safe

    def _execute_subprocess(
        self,
        code: str,
        context: dict[str, Any] | None,
        start_time: float,
    ) -> ExecutionResult:
        """Execute code in a subprocess with resource limits."""
        io.StringIO()
        io.StringIO()
        charts: list[str] = []

        # Prepare wrapper script
        wrapper_code = self._build_subprocess_wrapper(code, context)

        # Write code to temp file (using os.O_EXCL to prevent symlink attacks)
        temp_dir = self.output_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        import os, stat
        fd, temp_path = os.mkstemp(suffix=".py", dir=str(temp_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                tf.write(wrapper_code)
            os.chmod(temp_path, stat.S_IRUSR)  # readable only by owner
        except Exception:
            os.close(fd)
            raise
        temp_file = Path(temp_path)

        try:
            # Build resource limit command
            max_memory_kb = self.max_memory_mb * 1024
            max_open_files = 100

            # Determine shell command
            if sys.platform == "darwin":
                # macOS doesn't have ulimit, use Python resource module in subprocess
                cmd = [
                    sys.executable,
                    "-c",
                    f"""
import resource
import sys
# Set memory limit
resource.setrlimit(resource.RLIMIT_AS, ({max_memory_kb * 1024}, {max_memory_kb * 1024 * 2}))
resource.setrlimit(resource.RLIMIT_NOFILE, ({max_open_files}, max_open_files))
resource.setrlimit(resource.RLIMIT_CPU, ({self.timeout}, {self.timeout + 10}))
# Run the script
exec(open('{temp_file}').read())
"""
                ]
            else:
                # Linux - use ulimit
                cmd = [
                    "/bin/bash", "-c",
                    f"ulimit -v {max_memory_kb} && ulimit -t {self.timeout} && "
                    f"ulimit -n {max_open_files} && {sys.executable} {temp_file}"
                ]

            # Execute with timeout
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.output_dir),
            )

            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return ExecutionResult(
                    success=False,
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr + f"\nExecution timeout after {self.timeout}s"),
                    charts=charts,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=f"Execution timeout after {self.timeout}s",
                )

            # Load captured charts
            chart_file = self.output_dir / "temp" / "charts.json"
            if chart_file.exists():
                try:
                    import json as json_module
                    charts = json_module.loads(chart_file.read_text())
                except Exception:
                    pass
                chart_file.unlink(missing_ok=True)

            execution_time_ms = (time.time() - start_time) * 1000

            # Check exit code
            if process.returncode != 0:
                return ExecutionResult(
                    success=False,
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr),
                    charts=charts,
                    execution_time_ms=execution_time_ms,
                    error=f"Subprocess exited with code {process.returncode}: {stderr[:500]}",
                )

            return ExecutionResult(
                success=True,
                stdout=self._truncate(stdout),
                stderr=self._truncate(stderr),
                charts=charts,
                execution_time_ms=execution_time_ms,
                error=None,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                charts=charts,
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Subprocess execution error: {str(e)}",
            )
        finally:
            temp_file.unlink(missing_ok=True)

    def _build_subprocess_wrapper(
        self,
        code: str,
        context: dict[str, Any] | None,
    ) -> str:
        """Build subprocess wrapper script with chart capture."""
        context_str = json.dumps(context or {}, default=str) if context else "{}"
        output_dir = str(self.output_dir / "temp")

        return f'''
import sys
import io
import json
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Capture stdout/stderr
stdout_capture = io.StringIO()
stderr_capture = io.StringIO()
sys.stdout = stdout_capture
sys.stderr = stderr_capture

# Context
context = json.loads('{context_str}')

# Setup chart capture
charts = []
_original_savefig = plt.savefig
def _safe_savefig(*args, **kwargs):
    buf = io.BytesIO()
    kwargs["format"] = "png"
    _original_savefig(buf, *args, **kwargs)
    charts.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
    buf.close()
    return _safe_savefig
plt.savefig = _safe_savefig

# Execute user code
{code}

# Restore stdout/stderr and print
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print(stdout_capture.getvalue(), end="")
print(stderr_capture.getvalue(), end="", file=sys.stderr)

# Save charts
if charts:
    with open("{output_dir}/charts.json", "w") as f:
        json.dump(charts, f)
'''

    def _execute_docker(
        self,
        code: str,
        context: dict[str, Any] | None,
        start_time: float,
    ) -> ExecutionResult:
        """Execute code in a Docker container (if available)."""
        # Check if docker is available
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr="",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error="Docker is not available",
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                execution_time_ms=(time.time() - start_time) * 1000,
                error="Docker is not installed or not accessible",
            )

        io.StringIO()
        io.StringIO()
        charts: list[str] = []

        # Prepare code file
        temp_dir = self.output_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        code_file = temp_dir / "sandbox_code.py"
        context_file = temp_dir / "sandbox_context.json"

        wrapper_code = self._build_docker_wrapper(code)
        code_file.write_text(wrapper_code, encoding="utf-8")
        if context:
            context_file.write_text(json.dumps(context, default=str), encoding="utf-8")

        try:
            # Build docker command
            container_name = f"sandbox_{int(time.time() * 1000)}"
            docker_cmd = [
                "docker", "run",
                "--rm",
                "--name", container_name,
                "--network", "none",  # Disable network
                "--memory", f"{self.max_memory_mb}m",
                "--cpus", str(self.max_cpu_percent / 100),
                "-v", f"{temp_dir}:/code",
                "-w", "/code",
                "python:3.11-slim",
                "python", "sandbox_code.py",
            ]

            # Execute
            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = process.communicate(timeout=self.timeout + 10)
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                stdout, stderr = process.communicate()
                return ExecutionResult(
                    success=False,
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr + f"\nExecution timeout after {self.timeout}s"),
                    charts=charts,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=f"Execution timeout after {self.timeout}s",
                )

            # Load charts
            chart_file = temp_dir / "charts.json"
            if chart_file.exists():
                charts = json.loads(chart_file.read_text())
                chart_file.unlink()

            execution_time_ms = (time.time() - start_time) * 1000

            if process.returncode != 0:
                return ExecutionResult(
                    success=False,
                    stdout=self._truncate(stdout),
                    stderr=self._truncate(stderr),
                    charts=charts,
                    execution_time_ms=execution_time_ms,
                    error=f"Docker execution failed: {stderr[:500]}",
                )

            return ExecutionResult(
                success=True,
                stdout=self._truncate(stdout),
                stderr=self._truncate(stderr),
                charts=charts,
                execution_time_ms=execution_time_ms,
                error=None,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                charts=charts,
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Docker execution error: {str(e)}",
            )
        finally:
            code_file.unlink(missing_ok=True)
            context_file.unlink(missing_ok=True)

    def _build_docker_wrapper(self, code: str) -> str:
        """Build Docker wrapper script."""
        output_dir = "/code"
        return f'''
import sys
import io
import json
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Capture stdout/stderr
stdout_capture = io.StringIO()
stderr_capture = io.StringIO()
sys.stdout = stdout_capture
sys.stderr = stderr_capture

# Load context
try:
    with open("{output_dir}/sandbox_context.json") as f:
        context = json.load(f)
except FileNotFoundError:
    context = {{}}

# Setup chart capture
charts = []
_original_savefig = plt.savefig
def _safe_savefig(*args, **kwargs):
    buf = io.BytesIO()
    kwargs["format"] = "png"
    _original_savefig(buf, *args, **kwargs)
    charts.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
    buf.close()
    return _safe_savefig
plt.savefig = _safe_savefig

# Execute user code
{code}

# Restore stdout/stderr and print
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print(stdout_capture.getvalue(), end="")
print(stderr_capture.getvalue(), end="", file=sys.stderr)

# Save charts
if charts:
    with open("{output_dir}/charts.json", "w") as f:
        json.dump(charts, f)
'''

    def _truncate(self, text: str) -> str:
        """Truncate output to max characters."""
        if len(text) > self.max_output_chars:
            return text[:self.max_output_chars] + f"\n... (truncated, total {len(text)} chars)"
        return text

    # ─── Convenience Methods ─────────────────────────────────────────────────

    def safe_execute(self, code: str, **kwargs: Any) -> ExecutionResult:
        """
        Convenience method matching PlottingAgent integration interface.

        Args:
            code: Python code string to execute
            **kwargs: Additional context to inject

        Returns:
            ExecutionResult
        """
        return self.execute(code, context=kwargs if kwargs else None)

    def save_charts(self, result: ExecutionResult, prefix: str = "chart") -> list[str]:
        """
        Save generated charts to files.

        Args:
            result: ExecutionResult containing charts
            prefix: Filename prefix for saved charts

        Returns:
            List of saved file paths
        """
        saved_paths = []
        for i, chart_b64 in enumerate(result.charts):
            filename = f"{prefix}_{i + 1}.png"
            filepath = self.output_dir / filename
            try:
                chart_data = base64.b64decode(chart_b64)
                filepath.write_bytes(chart_data)
                saved_paths.append(str(filepath))
            except Exception:
                pass  # Skip failed saves
        return saved_paths


# ─── Import for json module in subprocess wrapper ──────────────────────────────
import json

# ─── CLI Interface ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI for testing the sandbox."""
    import argparse

    parser = argparse.ArgumentParser(description="SafeCodeExecutor CLI")
    parser.add_argument("code", help="Python code to execute")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument("--memory", type=int, default=512, help="Max memory in MB")
    parser.add_argument("--mode", choices=["restricted", "subprocess", "docker"],
                        default="restricted", help="Execution mode")

    args = parser.parse_args()

    executor = SafeCodeExecutor(
        timeout=args.timeout,
        max_memory_mb=args.memory,
        mode=ExecutionMode(args.mode),
    )

    result = executor.execute(args.code)

    print(f"Success: {result.success}")
    print(f"Execution time: {result.execution_time_ms:.2f}ms")
    print(f"\nStdout:\n{result.stdout}")
    print(f"\nStderr:\n{result.stderr}")
    if result.charts:
        print(f"\nCharts: {len(result.charts)} generated")
    if result.error:
        print(f"\nError: {result.error}")


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════════════════
# E2B / Multi-Tier Sandbox Integration
# ═══════════════════════════════════════════════════════════════════════════════════════


def create_sandbox_runner(
    tier: str = "local",
    api_key: str | None = None,
    **kwargs,
):
    """
    工厂函数：根据隔离级别创建合适的 sandbox runner。

    Parameters
    ----------
    tier : str
        隔离级别：
          - "local"      — SafeCodeExecutor RESTRICTED 模式
          - "subprocess" — SafeCodeExecutor SUBPROCESS 模式
          - "docker"    — SafeCodeExecutor DOCKER 模式
          - "microvm"   — E2B microVM（有 api_key 时）
    api_key : str | None
        E2B API Key（用于 microvm 模式）。
    **kwargs
        传递给 runner 的其他参数。

    Usage
    -----
        # 本地进程隔离（无 E2B）
        runner = create_sandbox_runner("subprocess", timeout=60)

        # E2B microVM（有 API key 时）
        runner = create_sandbox_runner("microvm", api_key="e2b_...")
    """
    from scripts.core.sandbox import SafeCodeExecutor, ExecutionMode

    mode_map = {
        "local": ExecutionMode.RESTRICTED,
        "subprocess": ExecutionMode.SUBPROCESS,
        "docker": ExecutionMode.DOCKER,
    }

    if tier == "microvm":
        # E2B microVM 模式（有 API key）
        try:
            from scripts.core.sandbox_runner import E2BRunner
            e2b_api = api_key or __import__("os").get("E2B_API_KEY")
            if e2b_api:
                return E2BRunner(
                    api_key=e2b_api,
                    **kwargs,
                )
        except Exception:
            pass
        # 降级到 subprocess
        return SafeCodeExecutor(mode=ExecutionMode.SUBPROCESS, **kwargs)

    mode = mode_map.get(tier, ExecutionMode.RESTRICTED)
    return SafeCodeExecutor(mode=mode, **kwargs)
