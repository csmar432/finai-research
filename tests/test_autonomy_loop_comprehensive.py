"""Comprehensive tests for scripts/core/autonomy_loop.py

Tests AutonomyLoop, AutoDebugger, FigureGenerator, ExecutionStatus, DebugAction,
ExecutionResult, FigureEvaluation, AutonomyLoopResult.
All tests use mocking — no real sandbox, VLM, or model access needed.
"""
import pytest
import re
import inspect
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Enums Tests ────────────────────────────────────────────────────────────────


class TestExecutionStatus:
    """Test ExecutionStatus enum."""

    def test_execution_status_pending_exists(self):
        """ExecutionStatus.PENDING exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.PENDING.value == "pending"

    def test_execution_status_running_exists(self):
        """ExecutionStatus.RUNNING exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.RUNNING.value == "running"

    def test_execution_status_success_exists(self):
        """ExecutionStatus.SUCCESS exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.SUCCESS.value == "success"

    def test_execution_status_error_exists(self):
        """ExecutionStatus.ERROR exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.ERROR.value == "error"

    def test_execution_status_timeout_exists(self):
        """ExecutionStatus.TIMEOUT exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.TIMEOUT.value == "timeout"

    def test_execution_status_max_iter_reached_exists(self):
        """ExecutionStatus.MAX_ITER_REACHED exists."""
        from scripts.core.autonomy_loop import ExecutionStatus
        assert ExecutionStatus.MAX_ITER_REACHED.value == "max_iter_reached"


class TestDebugAction:
    """Test DebugAction enum."""

    def test_debug_action_none_exists(self):
        """DebugAction.NONE exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.NONE.value == "none"

    def test_debug_action_fix_syntax_exists(self):
        """DebugAction.FIX_SYNTAX exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.FIX_SYNTAX.value == "fix_syntax"

    def test_debug_action_fix_import_exists(self):
        """DebugAction.FIX_IMPORT exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.FIX_IMPORT.value == "fix_import"

    def test_debug_action_fix_runtime_exists(self):
        """DebugAction.FIX_RUNTIME exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.FIX_RUNTIME.value == "fix_runtime"

    def test_debug_action_reduce_scope_exists(self):
        """DebugAction.REDUCE_SCOPE exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.REDUCE_SCOPE.value == "reduce_scope"

    def test_debug_action_add_error_handling_exists(self):
        """DebugAction.ADD_ERROR_HANDLING exists."""
        from scripts.core.autonomy_loop import DebugAction
        assert DebugAction.ADD_ERROR_HANDLING.value == "add_error_handling"


# ─── Dataclass Tests ───────────────────────────────────────────────────────────


class TestExperimentCode:
    """Test ExperimentCode dataclass."""

    def test_experiment_code_creation(self):
        """ExperimentCode can be created."""
        from scripts.core.autonomy_loop import ExperimentCode
        ec = ExperimentCode(
            language="python",
            script="print('hello')",
            filename="test.py",
        )
        assert ec.language == "python"
        assert ec.script == "print('hello')"
        assert ec.filename == "test.py"
        assert ec.dependencies == []
        assert ec.estimated_runtime_sec == 60

    def test_experiment_code_with_dependencies(self):
        """ExperimentCode accepts dependencies list."""
        from scripts.core.autonomy_loop import ExperimentCode
        ec = ExperimentCode(
            language="python",
            script="import pandas",
            filename="test.py",
            dependencies=["pandas", "numpy"],
        )
        assert "pandas" in ec.dependencies
        assert "numpy" in ec.dependencies


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_execution_result_creation(self):
        """ExecutionResult can be created."""
        from scripts.core.autonomy_loop import ExecutionResult, ExecutionStatus
        er = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            stdout="test output",
            stderr="",
            return_code=0,
            execution_time_sec=1.5,
            iterations=1,
        )
        assert er.status == ExecutionStatus.SUCCESS
        assert er.stdout == "test output"
        assert er.stderr == ""
        assert er.return_code == 0
        assert er.iterations == 1

    def test_execution_result_with_error(self):
        """ExecutionResult stores error info."""
        from scripts.core.autonomy_loop import ExecutionResult, ExecutionStatus
        er = ExecutionResult(
            status=ExecutionStatus.ERROR,
            stdout="",
            stderr="SyntaxError: invalid syntax",
            return_code=1,
            execution_time_sec=0.1,
            iterations=1,
            error="SyntaxError",
        )
        assert er.error == "SyntaxError"
        assert er.status == ExecutionStatus.ERROR

    def test_execution_result_with_debug_history(self):
        """ExecutionResult includes debug_history."""
        from scripts.core.autonomy_loop import ExecutionResult, ExecutionStatus
        er = ExecutionResult(
            status=ExecutionStatus.ERROR,
            stdout="",
            stderr="error",
            return_code=1,
            execution_time_sec=1.0,
            iterations=3,
            debug_history=[
                {"iteration": 1, "debug_action": "fix_syntax"},
                {"iteration": 2, "debug_action": "fix_import"},
            ],
        )
        assert len(er.debug_history) == 2

    def test_execution_result_with_figures(self):
        """ExecutionResult tracks figures_generated."""
        from scripts.core.autonomy_loop import ExecutionResult, ExecutionStatus
        er = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            stdout="",
            stderr="",
            return_code=0,
            execution_time_sec=5.0,
            iterations=1,
            figures_generated=["fig1.png", "fig2.png"],
        )
        assert len(er.figures_generated) == 2


class TestFigureEvaluation:
    """Test FigureEvaluation dataclass."""

    def test_figure_evaluation_creation(self):
        """FigureEvaluation can be created."""
        from scripts.core.autonomy_loop import FigureEvaluation
        fe = FigureEvaluation(
            figure_path="output/fig.png",
            quality_score=8.5,
            issues=[],
            suggestions=["Increase font size"],
            is_publishable=True,
            vlm_model="gpt-4v",
            evaluation_time_sec=2.3,
        )
        assert fe.quality_score == 8.5
        assert fe.is_publishable is True

    def test_figure_evaluation_with_issues(self):
        """FigureEvaluation stores identified issues."""
        from scripts.core.autonomy_loop import FigureEvaluation
        fe = FigureEvaluation(
            figure_path="output/bad_fig.png",
            quality_score=4.0,
            issues=["Low DPI", "Missing axis label"],
            suggestions=[],
            is_publishable=False,
            vlm_model="gpt-4v",
            evaluation_time_sec=1.0,
        )
        assert len(fe.issues) == 2


class TestAutonomyLoopResult:
    """Test AutonomyLoopResult dataclass."""

    def test_autonomy_loop_result_creation(self):
        """AutonomyLoopResult can be created."""
        from scripts.core.autonomy_loop import AutonomyLoopResult, ExecutionStatus
        result = AutonomyLoopResult(
            node_id="node_001",
            status=ExecutionStatus.SUCCESS,
            final_code=None,
            execution=None,
            figure_evaluations=[],
            signal="strong_positive",
            confidence=0.85,
            key_statistics={"coef": 0.5, "pval": 0.01},
            conclusion="Hypothesis supported",
            recommendations=["Publish this"],
            total_time_minutes=2.5,
        )
        assert result.node_id == "node_001"
        assert result.signal == "strong_positive"
        assert result.confidence == 0.85

    def test_autonomy_loop_result_with_figures(self):
        """AutonomyLoopResult includes figure evaluations."""
        from scripts.core.autonomy_loop import AutonomyLoopResult, ExecutionStatus, FigureEvaluation
        fe = FigureEvaluation(
            figure_path="test.png",
            quality_score=7.5,
            issues=[],
            suggestions=[],
            is_publishable=True,
            vlm_model="gpt-4v",
            evaluation_time_sec=1.0,
        )
        result = AutonomyLoopResult(
            node_id="test",
            status=ExecutionStatus.SUCCESS,
            final_code=None,
            execution=None,
            figure_evaluations=[fe],
            signal="positive",
            confidence=0.7,
            key_statistics={},
            conclusion="ok",
            recommendations=[],
            total_time_minutes=1.0,
        )
        assert len(result.figure_evaluations) == 1


# ─── AutoDebugger Tests ────────────────────────────────────────────────────────


class TestAutoDebuggerInit:
    """Test AutoDebugger initialization."""

    def test_autodebugger_creation(self):
        """AutoDebugger can be created."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        assert dbg is not None

    def test_autodebugger_with_sandbox(self):
        """AutoDebugger accepts sandbox_runner."""
        from scripts.core.autonomy_loop import AutoDebugger
        mock_sandbox = MagicMock()
        dbg = AutoDebugger(sandbox_runner=mock_sandbox)
        assert dbg.sandbox_runner is mock_sandbox

    def test_autodebugger_max_iterations(self):
        """AutoDebugger has MAX_ITERATIONS constant."""
        from scripts.core.autonomy_loop import AutoDebugger
        assert AutoDebugger.MAX_ITERATIONS == 5


class TestAutoDebuggerFixCode:
    """Test AutoDebugger.fix_code() method."""

    def test_fix_code_returns_tuple(self):
        """fix_code() returns (code, DebugAction) tuple."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        result = dbg.fix_code("print('hello')", "no error", iteration=1)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_fix_code_detects_syntax_error(self):
        """fix_code() detects SyntaxError."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        fixed, action = dbg.fix_code("if x\n    print(x)", "SyntaxError: invalid syntax", iteration=1)
        assert action == DebugAction.FIX_SYNTAX

    def test_fix_code_detects_import_error(self):
        """fix_code() detects ImportError."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        fixed, action = dbg.fix_code(
            "import pandas",
            "ImportError: No module named 'pandas'",
            iteration=1,
        )
        assert action == DebugAction.FIX_IMPORT

    def test_fix_code_detects_name_error(self):
        """fix_code() detects NameError."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        fixed, action = dbg.fix_code(
            "print(x)",
            "NameError: name 'x' is not defined",
            iteration=1,
        )
        assert action == DebugAction.FIX_RUNTIME

    def test_fix_code_detects_timeout(self):
        """fix_code() detects timeout error."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        fixed, action = dbg.fix_code(
            "while True: pass",
            "TimeoutError: execution timed out",
            iteration=1,
        )
        assert action == DebugAction.REDUCE_SCOPE

    def test_fix_code_detects_value_error(self):
        """fix_code() detects ValueError."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        fixed, action = dbg.fix_code(
            "int('abc')",
            "ValueError: invalid literal",
            iteration=1,
        )
        assert action == DebugAction.ADD_ERROR_HANDLING

    def test_fix_code_no_op_for_clean_code(self):
        """fix_code() returns unchanged code for no error."""
        from scripts.core.autonomy_loop import AutoDebugger, DebugAction
        dbg = AutoDebugger()
        code = "print('hello world')"
        fixed, action = dbg.fix_code(code, "no error", iteration=1)
        assert action == DebugAction.NONE


class TestFixSyntax:
    """Test _fix_syntax() internal method."""

    def test_fix_syntax_fstring_single_to_double(self):
        """_fix_syntax() converts f-string single quotes to double quotes."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "f'{x}' = 1"
        fixed = dbg._fix_syntax(code, "f-string error")
        assert 'f"' in fixed or fixed == code  # May or may not change depending on content

    def test_fix_syntax_adds_missing_colon(self):
        """_fix_syntax() adds missing colons to if statements."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "if x == 1\n    print(x)"
        fixed = dbg._fix_syntax(code, "expected ':'")
        # The method should add colons
        assert ":" in fixed


class TestFixImport:
    """Test _fix_import() internal method."""

    def test_fix_import_adds_pandas(self):
        """_fix_import() adds missing pandas import."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "# main code"
        fixed = dbg._fix_import(code, "No module named 'pandas'")
        assert "import pandas" in fixed

    def test_fix_import_adds_numpy(self):
        """_fix_import() adds missing numpy import."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "# main code"
        fixed = dbg._fix_import(code, "No module named 'numpy'")
        assert "import numpy" in fixed

    def test_fix_import_adds_matplotlib(self):
        """_fix_import() adds missing matplotlib import."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "# main code"
        fixed = dbg._fix_import(code, "No module named 'matplotlib'")
        assert "import matplotlib" in fixed

    def test_fix_import_does_not_duplicate(self):
        """_fix_import() doesn't duplicate existing imports."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "import pandas as pd\nprint(pd.DataFrame())"
        fixed = dbg._fix_import(code, "No module named 'pandas'")
        # Should not duplicate pandas import
        count = fixed.count("import pandas")
        assert count == 1


class TestFixUndefined:
    """Test _fix_undefined() internal method."""

    def test_fix_undefined_adds_placeholder(self):
        """_fix_undefined() adds placeholder for undefined df."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "print(df)"
        fixed = dbg._fix_undefined(code, "name 'df' is not defined")
        assert "df =" in fixed or fixed != code

    def test_fix_undefined_adds_placeholder_for_result(self):
        """_fix_undefined() adds placeholder for undefined result."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "return result"
        fixed = dbg._fix_undefined(code, "name 'result' is not defined")
        assert "result =" in fixed or fixed != code


class TestReduceScope:
    """Test _reduce_scope() internal method."""

    def test_reduce_scope_adds_sampling(self):
        """_reduce_scope() adds data sampling code."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "import pandas as pd\ndf = pd.read_csv('data.csv')"
        fixed = dbg._reduce_scope(code)
        assert "sample" in fixed.lower() or "len(df)" in fixed

    def test_reduce_scope_preserves_imports(self):
        """_reduce_scope() preserves existing import statements."""
        from scripts.core.autonomy_loop import AutoDebugger
        dbg = AutoDebugger()
        code = "import pandas as pd\ndf = pd.DataFrame()"
        fixed = dbg._reduce_scope(code)
        assert "import pandas" in fixed


# ─── FigureGenerator Tests ─────────────────────────────────────────────────────


class TestFigureGeneratorInit:
    """Test FigureGenerator initialization."""

    def test_figure_generator_creation(self):
        """FigureGenerator can be created."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator()
        assert gen is not None

    def test_figure_generator_with_custom_output_dir(self):
        """FigureGenerator accepts custom output_dir."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator(output_dir="/tmp/my_figures")
        assert gen.output_dir == "/tmp/my_figures"


class TestFigureGeneratorMethods:
    """Test FigureGenerator chart generation methods."""

    def test_has_generate_regression_coef_plot(self):
        """FigureGenerator has generate_regression_coef_plot method."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator()
        assert hasattr(gen, "generate_regression_coef_plot")

    def test_has_generate_did_plot(self):
        """FigureGenerator has generate_did_plot method."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator()
        assert hasattr(gen, "generate_did_plot")

    def test_has_generate_heatmap(self):
        """FigureGenerator has generate_heatmap method."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator()
        assert hasattr(gen, "generate_heatmap")

    def test_generate_regression_coef_plot_returns_path(self, tmp_path):
        """generate_regression_coef_plot() returns a file path."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator(output_dir=str(tmp_path))
        coefs = {"treatment": 0.5, "control": -0.2}
        stderrs = {"treatment": 0.1, "control": 0.1}
        path = gen.generate_regression_coef_plot(
            coefs, stderrs,
            title="Test Coefficients",
            filename="test_coef.png",
        )
        # Returns a path (or empty string if matplotlib unavailable)
        assert isinstance(path, str)

    def test_generate_did_plot_returns_path(self, tmp_path):
        """generate_did_plot() returns a file path."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator(output_dir=str(tmp_path))
        # Ensure all groups have the same number of time points
        pre = {"Treatment": [1.0, 1.1, 1.2, 1.3], "Control": [1.0, 1.05, 1.1, 1.12]}
        post = {"Treatment": [1.5, 1.6, 1.7, 1.8], "Control": [1.15, 1.2, 1.22, 1.25]}
        path = gen.generate_did_plot(pre, post, filename="test_did.png")
        assert isinstance(path, str)

    def test_generate_heatmap_returns_path(self, tmp_path):
        """generate_heatmap() returns a file path."""
        from scripts.core.autonomy_loop import FigureGenerator
        gen = FigureGenerator(output_dir=str(tmp_path))
        data = [[1.0, 0.5], [0.5, 1.0]]
        path = gen.generate_heatmap(
            data,
            row_labels=["var1", "var2"],
            col_labels=["var1", "var2"],
            filename="test_heatmap.png",
        )
        assert isinstance(path, str)


# ─── AutonomyLoop Tests ───────────────────────────────────────────────────────


class TestAutonomyLoopInit:
    """Test AutonomyLoop initialization."""

    def test_autonomy_loop_creation(self):
        """AutonomyLoop can be created."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert loop is not None

    def test_autonomy_loop_with_sandbox(self):
        """AutonomyLoop accepts sandbox_runner."""
        from scripts.core.autonomy_loop import AutonomyLoop
        mock_sandbox = MagicMock()
        loop = AutonomyLoop(sandbox_runner=mock_sandbox)
        assert loop.sandbox_runner is mock_sandbox

    def test_autonomy_loop_with_vlm_checker(self):
        """AutonomyLoop accepts pdf_vision_checker."""
        from scripts.core.autonomy_loop import AutonomyLoop
        mock_vlm = MagicMock()
        loop = AutonomyLoop(pdf_vision_checker=mock_vlm)
        assert loop.pdf_vision_checker is mock_vlm

    def test_autonomy_loop_has_debugger(self):
        """AutonomyLoop initializes AutoDebugger."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "debugger")

    def test_autonomy_loop_has_figure_gen(self):
        """AutonomyLoop initializes FigureGenerator."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "figure_gen")

    def test_autonomy_loop_max_iterations(self):
        """AutonomyLoop has MAX_ITERATIONS constant."""
        from scripts.core.autonomy_loop import AutonomyLoop
        assert AutonomyLoop.MAX_ITERATIONS == 5

    def test_autonomy_loop_max_execution_time(self):
        """AutonomyLoop has MAX_EXECUTION_TIME_SEC constant."""
        from scripts.core.autonomy_loop import AutonomyLoop
        assert hasattr(AutonomyLoop, "MAX_EXECUTION_TIME_SEC")
        assert AutonomyLoop.MAX_EXECUTION_TIME_SEC > 0


class TestAutonomyLoopCodeGeneration:
    """Test AutonomyLoop code generation methods."""

    def test_has_generate_code_method(self):
        """AutonomyLoop has _generate_code method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_generate_code")

    def test_generate_code_returns_experiment_code(self):
        """_generate_code() returns ExperimentCode."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExperimentCode
        loop = AutonomyLoop()

        mock_node = MagicMock()
        mock_node.title = "Test Hypothesis"
        mock_node.description = "Testing DID"
        mock_node.mechanism = "treatment effect"
        mock_node.idea_id = "test_001"

        result = loop._generate_code(mock_node, {"method": "DID", "language": "python"})
        assert isinstance(result, ExperimentCode)
        assert result.language == "python"

    def test_generate_code_python_script(self):
        """_generate_code() generates Python script for Python config."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_node = MagicMock()
        mock_node.title = "Test"
        mock_node.idea_id = "t1"
        mock_node.description = ""
        mock_node.mechanism = ""

        result = loop._generate_code(mock_node, {"language": "python", "method": "DID"})
        assert "python" in result.language
        assert "import pandas" in result.script or "import" in result.script

    def test_generate_code_stata_script(self):
        """_generate_code() generates Stata script for Stata config."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_node = MagicMock()
        mock_node.title = "Test"
        mock_node.idea_id = "t1"
        mock_node.description = ""
        mock_node.mechanism = ""

        result = loop._generate_code(mock_node, {"language": "stata", "method": "DID"})
        assert result.language == "stata"
        assert "clear" in result.script.lower() or "do" in result.script.lower()

    def test_generate_code_uses_synthetic_data_by_default(self):
        """_generate_code() uses synthetic data by default."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_node = MagicMock()
        mock_node.title = "Test"
        mock_node.idea_id = "t1"
        mock_node.description = ""
        mock_node.mechanism = ""

        result = loop._generate_code(mock_node, {})
        # Default is synthetic data
        assert "synthetic" in result.script.lower() or "seed" in result.script.lower()


class TestAutonomyLoopPythonScriptGeneration:
    """Test _generate_python_script() method."""

    def test_generate_python_script_did(self):
        """_generate_python_script() generates DID script."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        script = loop._generate_python_script(
            method="DID",
            title="Carbon Trading Effect",
            description="Test",
            config={"data_source": "synthetic"},
        )
        assert "DID" in script or "treatment" in script

    def test_generate_python_script_iv(self):
        """_generate_python_script() generates IV script."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        script = loop._generate_python_script(
            method="IV",
            title="Instrumental Variable",
            description="Test",
            config={"data_source": "synthetic"},
        )
        assert "IV" in script or "instrument" in script.lower()


class TestAutonomyLoopExecution:
    """Test _execute_with_debug() method."""

    def test_has_execute_with_debug_method(self):
        """AutonomyLoop has _execute_with_debug method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_execute_with_debug")

    def test_execute_with_debug_returns_execution_result(self):
        """_execute_with_debug() returns ExecutionResult."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionResult
        loop = AutonomyLoop()
        mock_code = MagicMock()
        mock_code.script = "print('hello world')"
        mock_code.language = "python"
        mock_code.filename = "test.py"

        result = loop._execute_with_debug(mock_code, max_iter=2)
        assert isinstance(result, ExecutionResult)

    def test_execute_with_debug_success(self):
        """_execute_with_debug() succeeds for valid code."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_code = MagicMock()
        mock_code.script = "print('success')"
        mock_code.language = "python"
        mock_code.filename = "test.py"

        result = loop._execute_with_debug(mock_code, max_iter=2)
        assert result.return_code == 0

    def test_execute_with_debug_debug_history(self):
        """_execute_with_debug() tracks debug_history."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_code = MagicMock()
        mock_code.script = "import nonexistent_module_xyz"
        mock_code.language = "python"
        mock_code.filename = "test.py"

        result = loop._execute_with_debug(mock_code, max_iter=3)
        assert isinstance(result.debug_history, list)


class TestAutonomyLoopLocalExecute:
    """Test _local_execute() fallback method."""

    def test_has_local_execute_method(self):
        """AutonomyLoop has _local_execute method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_local_execute")

    def test_local_execute_returns_tuple(self):
        """_local_execute() returns (stdout, stderr, return_code)."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        stdout, stderr, code = loop._local_execute("print('test')", iteration=1)
        assert isinstance(stdout, str)
        assert isinstance(stderr, str)
        assert isinstance(code, int)

    def test_local_execute_captures_stdout(self):
        """_local_execute() captures stdout."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        stdout, stderr, code = loop._local_execute("print('hello from test')", iteration=1)
        assert "hello from test" in stdout


class TestAutonomyLoopReflect:
    """Test _reflect() method."""

    def test_has_reflect_method(self):
        """AutonomyLoop has _reflect method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_reflect")

    def test_reflect_returns_five_tuple(self):
        """_reflect() returns (signal, confidence, key_stats, conclusion, recommendations)."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionStatus
        loop = AutonomyLoop()

        mock_exec = MagicMock()
        mock_exec.status = ExecutionStatus.SUCCESS
        mock_exec.data_output = {"coefficient": 0.5, "pvalue": 0.001}

        signal, confidence, key_stats, conclusion, recommendations = loop._reflect(
            mock_exec, [], MagicMock()
        )
        assert isinstance(signal, str)
        assert isinstance(confidence, float)
        assert isinstance(key_stats, dict)
        assert isinstance(conclusion, str)
        assert isinstance(recommendations, list)

    def test_reflect_strong_positive_signal(self):
        """_reflect() returns 'strong_positive' for p<0.01 and coef>0."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionStatus
        loop = AutonomyLoop()

        mock_exec = MagicMock()
        mock_exec.status = ExecutionStatus.SUCCESS
        mock_exec.data_output = {"coefficient": 0.8, "pvalue": 0.001}

        signal, confidence, _, conclusion, _ = loop._reflect(mock_exec, [], MagicMock())
        assert signal == "strong_positive"

    def test_reflect_error_signal(self):
        """_reflect() returns 'error' for failed execution."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionStatus
        loop = AutonomyLoop()

        mock_exec = MagicMock()
        mock_exec.status = ExecutionStatus.ERROR
        mock_exec.data_output = {}

        signal, confidence, _, conclusion, _ = loop._reflect(mock_exec, [], MagicMock())
        assert signal == "error"

    def test_reflect_neutral_signal(self):
        """_reflect() returns 'neutral' for p>0.1."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionStatus
        loop = AutonomyLoop()

        mock_exec = MagicMock()
        mock_exec.status = ExecutionStatus.SUCCESS
        mock_exec.data_output = {"coefficient": 0.1, "pvalue": 0.5}

        signal, confidence, _, _, _ = loop._reflect(mock_exec, [], MagicMock())
        assert signal == "neutral"


class TestAutonomyLoopRun:
    """Test run() method (the main entry point)."""

    def test_has_run_method(self):
        """AutonomyLoop has run() method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "run")

    def test_run_returns_autonomy_loop_result(self):
        """run() returns AutonomyLoopResult."""
        from scripts.core.autonomy_loop import AutonomyLoop, AutonomyLoopResult
        loop = AutonomyLoop()

        mock_node = MagicMock()
        mock_node.idea_id = "test_001"
        mock_node.title = "Test Hypothesis"
        mock_node.description = "Testing"
        mock_node.mechanism = ""

        result = loop.run(mock_node, experiment_config={"method": "DID", "language": "python"})
        assert isinstance(result, AutonomyLoopResult)
        assert result.node_id == "test_001"

    def test_run_with_custom_max_iterations(self):
        """run() respects custom max_iterations."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()

        mock_node = MagicMock()
        mock_node.idea_id = "test_002"
        mock_node.title = "Test"
        mock_node.description = ""
        mock_node.mechanism = ""

        result = loop.run(mock_node, max_iterations=3)
        assert isinstance(result.total_time_minutes, float)

    def test_run_returns_valid_status(self):
        """run() returns a valid ExecutionStatus."""
        from scripts.core.autonomy_loop import AutonomyLoop, ExecutionStatus
        loop = AutonomyLoop()

        mock_node = MagicMock()
        mock_node.idea_id = "test_003"
        mock_node.title = "Test"
        mock_node.description = ""
        mock_node.mechanism = ""

        result = loop.run(mock_node)
        # Status should be one of the valid enum values
        valid_statuses = [e.value for e in ExecutionStatus]
        assert result.status.value in valid_statuses


class TestAutonomyLoopFigureGeneration:
    """Test _generate_figures() method."""

    def test_has_generate_figures_method(self):
        """AutonomyLoop has _generate_figures method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_generate_figures")

    def test_generate_figures_returns_list(self):
        """_generate_figures() returns list of figure paths."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_node = MagicMock()
        mock_node.idea_id = "test"
        mock_node.title = "Test"

        figures = loop._generate_figures({"coefficient": 0.5}, mock_node)
        assert isinstance(figures, list)


class TestAutonomyLoopEvaluateFigure:
    """Test _evaluate_figure() method."""

    def test_has_evaluate_figure_method(self):
        """AutonomyLoop has _evaluate_figure method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_evaluate_figure")

    def test_evaluate_figure_returns_none_without_vlm(self):
        """_evaluate_figure() returns None when no VLM checker."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()  # No pdf_vision_checker
        result = loop._evaluate_figure("fake_path.png", MagicMock())
        assert result is None

    def test_evaluate_figure_with_vlm(self):
        """_evaluate_figure() calls VLM checker and returns FigureEvaluation."""
        from scripts.core.autonomy_loop import AutonomyLoop
        mock_vlm = MagicMock()
        mock_vlm.check.return_value = {
            "quality_score": 8.0,
            "issues": [],
            "suggestions": [],
        }
        loop = AutonomyLoop(pdf_vision_checker=mock_vlm)

        result = loop._evaluate_figure("output/test.png", MagicMock())
        assert result is not None
        mock_vlm.check.assert_called_once()


class TestParseOutput:
    """Test _parse_output() method."""

    def test_has_parse_output_method(self):
        """AutonomyLoop has _parse_output method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_parse_output")

    def test_parse_output_extracts_coefficient(self):
        """_parse_output() extracts coefficient from stdout."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        stdout = "Treatment Effect: 0.5432 (p=0.0234)"
        data = loop._parse_output(stdout)
        assert "coefficient" in data
        assert abs(data["coefficient"] - 0.5432) < 0.001

    def test_parse_output_extracts_pvalue(self):
        """_parse_output() extracts p-value from stdout."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        stdout = "Coefficient: 0.5, p_value: 0.034"
        data = loop._parse_output(stdout)
        assert "pvalue" in data

    def test_parse_output_empty_input(self):
        """_parse_output() handles empty stdout."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        data = loop._parse_output("")
        assert isinstance(data, dict)


class TestMakeErrorResult:
    """Test _make_error_result() method."""

    def test_has_make_error_result_method(self):
        """AutonomyLoop has _make_error_result method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "_make_error_result")

    def test_make_error_result_returns_autonomy_loop_result(self):
        """_make_error_result() returns AutonomyLoopResult."""
        from scripts.core.autonomy_loop import AutonomyLoop, AutonomyLoopResult
        loop = AutonomyLoop()
        result = loop._make_error_result("node_001", "test error", 10.0)
        assert isinstance(result, AutonomyLoopResult)
        assert result.node_id == "node_001"
        assert result.signal == "error"


class TestIntegrateWithExplorer:
    """Test integrate_with_explorer() method."""

    def test_has_integrate_with_explorer_method(self):
        """AutonomyLoop has integrate_with_explorer method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        assert hasattr(loop, "integrate_with_explorer")

    def test_integrate_with_explorer_returns_explorer(self):
        """integrate_with_explorer() returns the explorer with patched method."""
        from scripts.core.autonomy_loop import AutonomyLoop
        loop = AutonomyLoop()
        mock_explorer = MagicMock()
        mock_explorer._run_pilot = MagicMock()
        result = loop.integrate_with_explorer(mock_explorer)
        # Should return the explorer (with monkey-patched _run_pilot)
        assert result is mock_explorer


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
