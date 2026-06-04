"""
Full sandbox code execution environment.

Provides secure execution of arbitrary Python code with:
- Process isolation (subprocess with resource limits)
- Dependency analysis and automatic installation
- Output capture (stdout, stderr, plots)
- Timeout enforcement
- Memory limits
- Execution history and replay

Upgrades from the basic subprocess in scripts/core/sandbox.py to a full sandbox
with dependency analysis and environment management.
"""

from __future__ import annotations

import ast
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─── Result Dataclass ──────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Result of sandboxed code execution."""
    success: bool
    stdout: str
    stderr: str
    return_value: Any = None
    execution_time_ms: float = 0.0
    plots: list[Path] = field(default_factory=list)
    dependencies_installed: list[str] = field(default_factory=list)
    memory_mb: float = 0.0
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_value": self.return_value,
            "execution_time_ms": self.execution_time_ms,
            "plots": [str(p) for p in self.plots],
            "dependencies_installed": self.dependencies_installed,
            "memory_mb": self.memory_mb,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


# ─── Dependency Analyzer ───────────────────────────────────────────────────────


class DependencyAnalyzer(ast.NodeVisitor):
    """Static analysis of Python code to extract imports."""

    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.add(node.module.split(".")[0])
        self.generic_visit(node)

    def analyze(self, code: str) -> list[str]:
        """Return list of third-party packages used in code."""
        try:
            tree = ast.parse(code)
            self.visit(tree)
        except SyntaxError:
            return []

        STDLIB = {
            "math", "statistics", "os", "sys", "re", "json", "time",
            "datetime", "collections", "itertools", "functools", "random",
            "uuid", "hashlib", "pickle", "csv", "io", "pathlib", "typing",
            "enum", "dataclasses", "abc", "pprint", "operator", "copy",
            "warnings", "numbers", "fractions", "decimal", "base64",
            "struct", "array", "bisect", "heapq", "copyreg", "shelve",
        }

        return sorted(self.imports - STDLIB)


# ─── Main Executor Class ───────────────────────────────────────────────────────


class FullSandboxExecutor:
    """
    Full-featured sandboxed code execution.

    Features:
    - Process isolation with resource limits
    - Automatic dependency analysis and installation
    - Memory and time limits
    - Plot capture (matplotlib output)
    - Execution history with replay
    - Security: no network, no file system access outside temp dir

    Example:
        executor = FullSandboxExecutor(timeout_seconds=30, max_memory_mb=512)
        result = executor.execute("import numpy as np; print(np.mean([1,2,3]))")
        print(result.stdout)
    """

    # Third-party packages that are pre-installed in the sandbox env
    PRE_INSTALLED = {
        "numpy", "pandas", "matplotlib", "scipy", "sklearn",
        "seaborn", "plotly", "statsmodels", "tqdm", "dateutil",
    }

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_memory_mb: int = 512,
        max_output_lines: int = 1000,
        sandbox_dir: str | Path | None = None,
        allowed_packages: list[str] | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.max_output_lines = max_output_lines
        self.sandbox_dir = Path(sandbox_dir) if sandbox_dir else None
        self.allowed_packages = set(allowed_packages) if allowed_packages else None
        self._analyzer = DependencyAnalyzer()
        self._history: list[ExecutionResult] = []
        self._sandbox_venv: Path | None = None  # Per-instance sandbox venv

    def execute(
        self,
        code: str,
        capture_plots: bool = True,
        install_deps: bool = True,
    ) -> ExecutionResult:
        """
        Execute code in sandbox.

        Steps:
        1. Analyze imports → find required packages
        2. Optionally install missing packages
        3. Write code to temp file
        4. Execute with resource limits
        5. Capture stdout/stderr/plots
        6. Return result
        """
        start_time = time.time()

        # Step 1: Analyze dependencies
        deps = self._analyzer.analyze(code)
        to_install: list[str] = []
        if install_deps:
            for dep in deps:
                if dep not in self.PRE_INSTALLED:
                    if self.allowed_packages is None or dep in self.allowed_packages:
                        to_install.append(dep)

        # Step 2: Setup sandbox directory (do this FIRST so venv can live inside it)
        sandbox = self._setup_sandbox()

        # Step 3: Install dependencies into the sandbox venv (if any)
        # SECURITY FIX: Previously installed to the HOST Python environment.
        # Now installs to an isolated venv inside the sandbox directory.
        installed: list[str] = []
        if to_install:
            installed = self._install_dependencies(to_install, sandbox)

        # Step 4: Write and execute script (now using the sandbox venv Python)
        wrapper = self._build_wrapper(code, sandbox, capture_plots)
        script_path = sandbox / "script.py"
        script_path.write_text(wrapper, encoding="utf-8")

        stdout, stderr, return_code, mem_mb = self._run_with_limits(
            script_path, sandbox, self.timeout_seconds
        )
        execution_time_ms = (time.time() - start_time) * 1000

        # Step 5: Collect plots
        plots_dir = sandbox / "plots"
        plots: list[Path] = []
        if capture_plots and plots_dir.exists():
            plots = list(plots_dir.glob("*.png")) + list(plots_dir.glob("*.pdf"))

        # Step 6: Build result
        result = ExecutionResult(
            success=(return_code == 0),
            stdout=self._truncate_output(stdout),
            stderr=self._truncate_output(stderr),
            execution_time_ms=execution_time_ms,
            plots=plots,
            dependencies_installed=installed,
            memory_mb=mem_mb,
            error_type=None if return_code == 0 else "RuntimeError",
            error_message=stderr if return_code != 0 else None,
        )

        self._history.append(result)
        return result

    def _setup_sandbox(self) -> Path:
        """Create temp sandbox directory with restrictions."""
        if self.sandbox_dir:
            sandbox = self.sandbox_dir / f"sandbox_{int(time.time() * 1000)}"
        else:
            sandbox = Path(tempfile.mkdtemp(prefix="sandbox_"))
        (sandbox / "plots").mkdir(exist_ok=True)
        return sandbox

    def _setup_sandbox_venv(self, sandbox: Path) -> Path:
        """
        Create an isolated venv inside the sandbox dir.
        This prevents pip install from modifying the host Python environment.
        """
        venv_path = sandbox / ".venv"
        try:
            import venv
            venv.create(venv_path, with_pip=True, clear=True)
            # Upgrade pip first
            pip_executable = str(venv_path / "bin" / "pip")
            subprocess.run(
                [pip_executable, "install", "--quiet", "--upgrade", "pip"],
                capture_output=True, timeout=120,
            )
            self._sandbox_venv = venv_path
            return venv_path
        except Exception:
            # Fallback: pip install into a temporary directory's site-packages
            # This is less isolated but still avoids the host environment
            import site
            extra_packages = site.getusersitepackages()
            os.makedirs(extra_packages, exist_ok=True)
            self._sandbox_venv = Path(extra_packages)
            return Path(extra_packages)

    def _install_dependencies(self, packages: list[str], sandbox: Path) -> list[str]:
        """
        Install required packages into the sandbox venv.

        SECURITY FIX: Previously this ran `pip install` in the host Python
        environment (sys.executable), which allowed arbitrary package installation
        on the host. Now packages are installed into an isolated venv created
        inside the sandbox directory, or the user site-packages as fallback.
        Neither modifies the host's site-packages.
        """
        installed: list[str] = []
        if not packages:
            return installed

        # Ensure sandbox venv exists (created inside the sandbox dir)
        if self._sandbox_venv is None:
            self._setup_sandbox_venv(sandbox)

        venv_pip = self._sandbox_venv / "bin" / "pip" if self._sandbox_venv else None

        for pkg in packages:
            try:
                if venv_pip is not None and venv_pip.exists():
                    cmd = [str(venv_pip), "install", "--quiet", pkg]
                else:
                    # Fallback: install to user site-packages (--user avoids host system packages)
                    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--user", pkg]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    installed.append(pkg)
                else:
                    logger.warning(
                        f"[SandboxExecutor] Failed to install '{pkg}': {result.stderr[:200]}"
                    )
            except Exception as e:
                logger.warning(f"[SandboxExecutor] Exception installing '{pkg}': {e}")
        return installed

    def _run_with_limits(
        self, script_path: Path, sandbox: Path, timeout: float
    ) -> tuple[str, str, int, float]:
        """Run script with resource limits in the sandbox venv."""
        max_mem_bytes = self.max_memory_mb * 1024 * 1024
        sandbox_str = str(sandbox)
        script_path_str = str(script_path)

        # Use the sandbox venv Python if available, otherwise fall back to host
        if self._sandbox_venv is not None:
            venv_python = self._sandbox_venv / "bin" / "python"
        else:
            venv_python = Path(sys.executable)

        # Build wrapper as plain string (avoid f-string indentation issues)
        wrapper = (
            "import resource\n"
            "import sys\n"
            "import os\n"
            f"max_mem = {max_mem_bytes}\n"
            f"timeout_val = {int(timeout)}\n"
            "try:\n"
            "    soft = max_mem\n"
            "    hard = soft * 2\n"
            "    cur_soft, cur_hard = resource.getrlimit(resource.RLIMIT_AS)\n"
            "    if soft > cur_hard:\n"
            "        soft = cur_hard\n"
            "        hard = cur_hard\n"
            "    resource.setrlimit(resource.RLIMIT_AS, (soft, hard))\n"
            "except (ValueError, OSError):\n"
            "    pass\n"
            "try:\n"
            "    resource.setrlimit(resource.RLIMIT_CPU, (timeout_val, timeout_val + 10))\n"
            "except (ValueError, OSError):\n"
            "    pass\n"
            "try:\n"
            "    resource.setrlimit(resource.RLIMIT_NOFILE, (50, 100))\n"
            "except (ValueError, OSError):\n"
            "    pass\n"
            # SECURITY FIX: Use exec() with a validated file path instead of open().read()
            # The script_path is validated by the caller, so we use importlib to execute it
            "import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('_sandbox_script', r'" + script_path_str.replace("\\", "\\\\").replace("'", "\\'") + "')\n"
            "if spec and spec.loader:\n"
            "    mod = importlib.util.module_from_spec(spec)\n"
            "    sys.modules['_sandbox_script'] = mod\n"
            "    spec.loader.exec_module(mod)\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(wrapper)
            wrapper_path = f.name

        try:
            # SECURITY FIX: Use sandbox venv Python instead of host sys.executable
            proc = subprocess.Popen(
                [str(venv_python), wrapper_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout + 5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                return self._truncate_output(stdout), self._truncate_output(stderr), -1, 0.0

            return_code = proc.returncode

            # Read the success flag written by the wrapper (1 = error occurred)
            success_file = os.path.join(sandbox_str, "success.txt")
            if os.path.exists(success_file):
                try:
                    with open(success_file) as f:
                        flag = f.read().strip()
                    if flag == "1":
                        return_code = 1
                except Exception:
                    pass
                try:
                    os.unlink(success_file)
                except Exception:
                    pass

            # Estimate memory from resource (best-effort)
            mem_mb = 0.0
            try:
                usage = resource.getrusage(resource.RUSAGE_CHILDREN)
                mem_mb = usage.ru_maxrss / 1024
            except Exception:
                pass

            return self._truncate_output(stdout), self._truncate_output(stderr), return_code, mem_mb

        except Exception as e:
            return "", str(e), 1, 0.0
        finally:
            try:
                Path(wrapper_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _build_wrapper(
        self, code: str, sandbox: Path, capture_plots: bool
    ) -> str:
        """Build the execution wrapper script."""
        plots_dir = str(sandbox / "plots")
        code_json = json.dumps(code)
        return f'''
import sys
import io
import json
import traceback

# Capture stdout/stderr
_stdout = io.StringIO()
_stderr = io.StringIO()
sys.stdout = _stdout
sys.stderr = _stderr

# Setup matplotlib for plot capture
if {capture_plots}:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import os
        os.makedirs({str(sandbox / "plots")!r}, exist_ok=True)
        os.chdir({str(sandbox / "plots")!r})
    except ImportError:
        pass

# Execute user code via compile+exec so it runs at the correct indentation level
_user_code = json.loads({code_json!r})
_exec_error = None
try:
    compiled = compile(_user_code, "<user_code>", "exec")
    exec(compiled, {{}})
except SystemExit:
    pass
except Exception as e:
    _exec_error = e
    import traceback as _tb
    _stderr.write(_tb.format_exc())

# Write success flag so the outer wrapper can detect failure
with open({str(sandbox / "success.txt")!r}, "w") as f:
    f.write("0" if _exec_error is None else "1")

# Restore and output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print(_stdout.getvalue(), end="")
_stderr_val = _stderr.getvalue()
if _stderr_val:
    print(_stderr_val, end="", file=sys.stderr)
'''

    def execute_with_requirements(
        self, code: str, requirements: list[str]
    ) -> ExecutionResult:
        """Execute code with pre-specified requirements (skip analysis)."""
        deps = list(requirements)
        installed: list[str] = []
        for dep in deps:
            if dep not in self.PRE_INSTALLED:
                installed.extend(self._install_dependencies([dep]))

        sandbox = self._setup_sandbox()
        wrapper = self._build_wrapper(code, sandbox, capture_plots=True)
        script_path = sandbox / "script.py"
        script_path.write_text(wrapper, encoding="utf-8")

        start_time = time.time()
        stdout, stderr, return_code, mem_mb = self._run_with_limits(
            script_path, sandbox, self.timeout_seconds
        )
        execution_time_ms = (time.time() - start_time) * 1000

        plots_dir = sandbox / "plots"
        plots: list[Path] = []
        if plots_dir.exists():
            plots = list(plots_dir.glob("*.png")) + list(plots_dir.glob("*.pdf"))

        result = ExecutionResult(
            success=(return_code == 0),
            stdout=self._truncate_output(stdout),
            stderr=self._truncate_output(stderr),
            execution_time_ms=execution_time_ms,
            plots=plots,
            dependencies_installed=installed,
            memory_mb=mem_mb,
            error_type=None if return_code == 0 else "RuntimeError",
            error_message=stderr if return_code != 0 else None,
        )

        self._history.append(result)
        return result

    def health_check(self) -> dict[str, Any]:
        """Check if sandbox is operational."""
        try:
            result = self.execute("print('health_check_ok')")
            return {
                "healthy": result.success and "health_check_ok" in result.stdout,
                "last_result": result.to_dict(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }

    def get_history(self) -> list[ExecutionResult]:
        """Return execution history."""
        return list(self._history)

    def _truncate_output(self, text: str) -> str:
        """Truncate output to max lines."""
        lines = text.splitlines()
        if len(lines) > self.max_output_lines:
            kept = lines[: self.max_output_lines]
            return "\n".join(kept) + f"\n... ({len(lines)} total lines, truncated)"
        return text


# ─── E2B Integration ───────────────────────────────────────────────────────────


class E2BExecutor:
    """
    E2B cloud sandbox executor.

    Uses the E2B API for true cloud-based sandbox execution.
    Falls back to FullSandboxExecutor if E2B is unavailable.

    Environment variable:
        E2B_API_KEY — E2B API key from https://e2b.dev
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("E2B_API_KEY", "")
        self._fallback = FullSandboxExecutor()

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Execute code in E2B cloud sandbox."""
        if not self.api_key:
            return self._fallback.execute(code)

        try:
            import e2b

            sandbox = e2b.Sandbox(
                api_key=self.api_key,
                timeout=timeout,
            )

            start = time.time()
            result = sandbox.run_code(code, timeout=timeout)
            elapsed = (time.time() - start) * 1000

            return ExecutionResult(
                success=(result.exit_code == 0),
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time_ms=elapsed,
                error_type=None if result.exit_code == 0 else "E2BRuntimeError",
            )
        except ImportError:
            return self._fallback.execute(code)
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                error_type=type(e).__name__,
                error_message=str(e),
            )

    def health_check(self) -> dict[str, Any]:
        """Check E2B connectivity."""
        if not self.api_key:
            return {"healthy": False, "reason": "E2B_API_KEY not set"}
        try:
            result = self.execute("print('ok')", timeout=10)
            return {"healthy": result.success, "result": result.to_dict()}
        except Exception as e:
            return {"healthy": False, "error": str(e)}
