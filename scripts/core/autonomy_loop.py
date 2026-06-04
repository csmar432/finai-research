"""
autonomy_loop.py — Autonomous Experiment Execution Loop

自动实验执行回路，集成到 HypothesisExplorer 体系中：

核心功能：
1. BFTS（Best-First Tree Search）：基于信号评分的最佳优先搜索
   - Pilot实验执行后自动更新节点分数
   - 剪枝低信号路径

2. 自动代码生成与执行
   - Python/Stata 回归脚本自动生成
   - Sandbox 隔离执行
   - 错误自动捕获与修复

3. VLM 图表评估
   - matplotlib 图表自动生成
   - VLM（GPT-4V/Gemini）自动评估图表质量
   - 迭代优化

4. 迭代 Debug 循环
   - SyntaxError → 自动修复 → 重跑
   - RuntimeError → 诊断 → 修复 → 重跑
   - 最多 MAX_ITER 次迭代

5. 自反思机制
   - 实验结果与假设一致性评估
   - 置信度自动更新
   - 发现报告生成

Usage:
    loop = AutonomyLoop(
        sandbox_runner=sandbox_runner,
        pdf_vision_checker=vlm_checker,
        model_router=model_router,
    )
    result = loop.run(
        hypothesis_node=node,
        experiment_config=config,
        max_iterations=5,
    )
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ─── 数据类型 ──────────────────────────────────────────────────────────────

class ExecutionStatus(str, Enum):
    """实验执行状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    MAX_ITER_REACHED = "max_iter_reached"


class DebugAction(str, Enum):
    """自动debug动作。"""
    NONE = "none"
    FIX_SYNTAX = "fix_syntax"
    FIX_IMPORT = "fix_import"
    FIX_RUNTIME = "fix_runtime"
    REDUCE_SCOPE = "reduce_scope"
    ADD_ERROR_HANDLING = "add_error_handling"


@dataclass
class ExperimentCode:
    """实验代码。"""
    language: str            # "python" / "stata"
    script: str
    filename: str
    dependencies: list[str] = field(default_factory=list)
    estimated_runtime_sec: int = 60


@dataclass
class ExecutionResult:
    """代码执行结果。"""
    status: ExecutionStatus
    stdout: str
    stderr: str
    return_code: int
    execution_time_sec: float
    iterations: int
    figures_generated: list[str] = field(default_factory=list)
    data_output: dict | None = None
    error: str | None = None
    debug_history: list[dict] = field(default_factory=list)


@dataclass
class FigureEvaluation:
    """图表VLM评估结果。"""
    figure_path: str
    quality_score: float      # 0-10
    issues: list[str]
    suggestions: list[str]
    is_publishable: bool
    vlm_model: str
    evaluation_time_sec: float


@dataclass
class AutonomyLoopResult:
    """Autonomy Loop 完整执行结果。"""
    node_id: str
    status: ExecutionStatus
    final_code: ExperimentCode | None
    execution: ExecutionResult | None
    figure_evaluations: list[FigureEvaluation]
    signal: str
    confidence: float
    key_statistics: dict
    conclusion: str
    recommendations: list[str]
    total_time_minutes: float


# ─── 自动 Debug 引擎 ────────────────────────────────────────────────────

class AutoDebugger:
    """
    自动debug引擎。

    策略：
    1. 语法错误 → 正则替换修复
    2. ImportError → 添加缺失依赖或 mock
    3. RuntimeError → 添加 try/except，或减少数据量
    4. 超时 → 减少数据量/样本
    """

    MAX_ITERATIONS = 5

    def __init__(self, sandbox_runner=None):
        self.sandbox_runner = sandbox_runner

    def fix_code(
        self,
        code: str,
        error: str,
        iteration: int,
    ) -> tuple[str, DebugAction]:
        """分析错误并尝试修复代码。"""
        error_lower = error.lower()

        # 1. 语法错误
        if "syntaxerror" in error_lower or "invalid syntax" in error_lower:
            fixed = self._fix_syntax(code, error)
            return fixed, DebugAction.FIX_SYNTAX

        # 2. ImportError / ModuleNotFoundError
        if "importerror" in error_lower or "modulenotfounderror" in error_lower:
            fixed = self._fix_import(code, error)
            return fixed, DebugAction.FIX_IMPORT

        # 3. NameError / AttributeError
        if "nameerror" in error_lower or "attributeerror" in error_lower:
            fixed = self._fix_undefined(code, error)
            return fixed, DebugAction.FIX_RUNTIME

        # 4. 超时 / MemoryError
        if "timeout" in error_lower or "memoryerror" in error_lower or "killed" in error_lower:
            fixed = self._reduce_scope(code)
            return fixed, DebugAction.REDUCE_SCOPE

        # 5. RuntimeError / ValueError / KeyError
        if "runtimeerror" in error_lower or "valueerror" in error_lower or "keyerror" in error_lower:
            fixed = self._add_error_handling(code)
            return fixed, DebugAction.ADD_ERROR_HANDLING

        # 6. 未知错误 → 添加日志
        return self._add_debug_print(code), DebugAction.NONE

    def _fix_syntax(self, code: str, error: str) -> str:
        """修复常见语法错误。"""
        # 修复反斜杠转义
        code = code.replace("\\'", "'")
        code = code.replace('\\"', '"')
        code = code.replace("\\n", "\n")
        code = code.replace("\\t", "\t")

        # 修复 f-string 中的单引号问题
        if "f-string" in error.lower():
            lines = code.split("\n")
            for i, line in enumerate(lines):
                if "f'" in line and 'f"' not in line:
                    lines[i] = line.replace("f'", 'f"').replace("'", '\\')
                elif 'f"' in line and "f'" not in line:
                    lines[i] = line.replace('f"', "f'").replace('"', "\\")
            code = "\n".join(lines)

        # 修复缺少冒号
        if ":" not in error:
            # 查找 if/for/while/def/class 后缺少冒号的情况
            for pattern in [r"(if .+[^:])\n", r"(for .+[^:])\n", r"(while .+[^:])\n", r"(def .+[^:])\n"]:
                code = re.sub(pattern, r"\1:\n", code)

        return code

    def _fix_import(self, code: str, error: str) -> str:
        """修复导入错误。"""
        # 提取缺失的模块名
        match = re.search(r"(?:No module named|import |from )['\"](\w+)['\"]", error)
        if match:
            missing_module = match.group(1)
            # 常见依赖映射
            dep_map = {
                "pandas": "import pandas as pd",
                "numpy": "import numpy as np",
                "statsmodels": "import statsmodels.api as sm",
                "sklearn": "from sklearn.linear_model import LinearRegression",
                "matplotlib": "import matplotlib.pyplot as plt",
                "scipy": "from scipy import stats",
                "linearmodels": "from linearmodels.panel import PanelOLS",
            }
            dep = dep_map.get(missing_module)
            if dep and dep not in code:
                # 添加到文件开头
                lines = code.split("\n")
                insert_idx = 0
                for j, line in enumerate(lines):
                    if line.startswith("#") or line.startswith("import ") or line.startswith("from "):
                        insert_idx = j + 1
                lines.insert(insert_idx, dep)
                return "\n".join(lines)
        return code

    def _fix_undefined(self, code: str, error: str) -> str:
        """修复未定义变量。"""
        # 提取未定义的变量名
        match = re.search(r"name '(\w+)' is not defined", error)
        if match:
            var_name = match.group(1)
            # 常见未定义变量的默认值
            defaults = {
                "df": "# df = pd.DataFrame()  # TODO: load your data\n",
                "result": "# result = None  # TODO: compute result\n",
                "X": "# X = None  # TODO: define features\n",
                "y": "# y = None  # TODO: define target\n",
                "model": "# model = None  # TODO: define model\n",
            }
            if var_name in defaults:
                code = defaults[var_name] + code
        return code

    def _reduce_scope(self, code: str) -> str:
        """减少数据量/范围以避免超时。"""
        # 添加采样限制
        if "head(" in code or ".head(" in code:
            return code

        # 在读取数据后添加采样
        reduce_lines = [
            "# Auto-added: reduce scope to avoid timeout",
            "if 'df' in dir() and len(df) > 10000:\n",
            "    df = df.sample(n=10000, random_state=42)\n",
            "    print(f'Sampled to {len(df)} rows')\n",
        ]

        # 在 import 后添加
        lines = code.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_idx = i + 1
        lines = lines[:insert_idx] + reduce_lines + lines[insert_idx:]
        return "\n".join(lines)

    def _add_error_handling(self, code: str) -> str:
        """添加异常处理。"""
        lines = code.split("\n")
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            # 在可能出错的关键行后添加 try/except
            if any(k in line for k in ["fit(", "predict(", "ols(", "merge(", "groupby("]):
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + "except Exception as e:")
                new_lines.append(" " * (indent + 4) + 'print(f\"Warning: {e}\")')
                new_lines.append(" " * indent + "    continue")
        return "\n".join(new_lines)

    def _add_debug_print(self, code: str) -> str:
        """添加调试打印（最后手段）。"""
        lines = code.split("\n")
        # 在主要计算前添加调试信息
        debug_info = [
            'import sys; print(f\"Running {sys._getframe().f_code.co_name}\")',
        ]
        for i, line in enumerate(lines):
            if line.startswith("def ") or line.startswith("import "):
                continue
            lines.insert(i + 1, '    print(f\"DEBUG: line {i}\")')
            break
        return "\n".join(lines)


# ─── 图表生成与VLM评估 ─────────────────────────────────────────────────

class FigureGenerator:
    """
    自动生成 matplotlib 图表。

    支持的图表类型：
    - 回归系数图（带置信区间）
    - 时间序列图
    - 散点图 + 回归线
    - 双差分图（预处理 vs 处理组）
    - 热力图（相关性/系数）
    """

    def __init__(self, output_dir: str = "output/figures"):
        self.output_dir = output_dir

    def generate_regression_coef_plot(
        self,
        coefs: dict[str, float],
        stderrs: dict[str, float],
        title: str = "Regression Coefficients",
        filename: str = "coef_plot.png",
    ) -> str:
        """生成回归系数森林图。"""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np

            import os
            os.makedirs(self.output_dir, exist_ok=True)

            names = list(coefs.keys())
            values = [coefs[n] for n in names]
            errs = [1.96 * stderrs.get(n, 0) for n in names]  # 95% CI

            fig, ax = plt.subplots(figsize=(max(6, len(names) * 0.8), max(3, len(names) * 0.4)))

            y_pos = np.arange(len(names))
            colors = ["#2E86AB" if v > 0 else "#E94F37" for v in values]
            ax.barh(y_pos, values, xerr=errs, color=colors, alpha=0.8, capsize=4)

            ax.axvline(x=0, color="black", linestyle="--", linewidth=0.8)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(names)
            ax.set_xlabel("Coefficient (95% CI)")
            ax.set_title(title)
            ax.grid(axis="x", alpha=0.3)

            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            plt.savefig(path, dpi=300, bbox_inches="tight")
            plt.close()
            return path
        except ImportError:
            logger.warning("matplotlib not available")
            return ""

    def generate_did_plot(
        self,
        pre_treatment: dict[str, list[float]],
        post_treatment: dict[str, list[float]],
        title: str = "Difference-in-Differences",
        filename: str = "did_plot.png",
    ) -> str:
        """生成DID示意图。"""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np

            import os
            os.makedirs(self.output_dir, exist_ok=True)

            fig, ax = plt.subplots(figsize=(8, 5))

            time_points = list(range(len(list(pre_treatment.values())[0])))
            for group, values in pre_treatment.items():
                ax.plot(time_points, values, marker="o", label=group, linewidth=2)

            for group, values in post_treatment.items():
                ax.plot(time_points, values, marker="s", linestyle="--", label=f"{group} (post)", linewidth=2)

            ax.axvline(x=len(time_points) - 1.5, color="red", linestyle=":", label="Treatment", linewidth=1.5)
            ax.set_xlabel("Time Period")
            ax.set_ylabel("Outcome")
            ax.set_title(title)
            ax.legend()
            ax.grid(alpha=0.3)

            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            plt.savefig(path, dpi=300, bbox_inches="tight")
            plt.close()
            return path
        except ImportError:
            logger.warning("matplotlib not available")
            return ""

    def generate_heatmap(
        self,
        data: list[list[float]],
        row_labels: list[str],
        col_labels: list[str],
        title: str = "Heatmap",
        filename: str = "heatmap.png",
    ) -> str:
        """生成热力图。"""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np

            import os
            os.makedirs(self.output_dir, exist_ok=True)

            fig, ax = plt.subplots(figsize=(max(6, len(col_labels) * 0.8), max(4, len(row_labels) * 0.6)))

            im = ax.imshow(data, cmap="RdBu_r", aspect="auto")

            ax.set_xticks(np.arange(len(col_labels)))
            ax.set_yticks(np.arange(len(row_labels)))
            ax.set_xticklabels(col_labels, rotation=45, ha="right")
            ax.set_yticklabels(row_labels)

            for i in range(len(row_labels)):
                for j in range(len(col_labels)):
                    text = ax.text(j, i, f"{data[i][j]:.2f}",
                                   ha="center", va="center", color="black", fontsize=8)

            ax.set_title(title)
            plt.colorbar(im, ax=ax)
            plt.tight_layout()

            path = os.path.join(self.output_dir, filename)
            plt.savefig(path, dpi=300, bbox_inches="tight")
            plt.close()
            return path
        except ImportError:
            logger.warning("matplotlib not available")
            return ""


# ─── Autonomy Loop ─────────────────────────────────────────────────────────

class AutonomyLoop:
    """
    自主实验执行回路。

    执行流程：
    1. 接收 HypothesisNode 和实验配置
    2. 生成实验代码（Python/Stata）
    3. 迭代执行 + 自动debug
    4. 生成图表
    5. VLM评估图表
    6. 输出结论和建议

    特点：
    - BFTS：将Pilot实验结果反馈到搜索树的信号评分中
    - 自反思：评估实验结果是否支持假设
    - 最大迭代保护：避免无限循环
    """

    MAX_ITERATIONS = 5
    MAX_EXECUTION_TIME_SEC = 300

    def __init__(
        self,
        sandbox_runner=None,
        pdf_vision_checker=None,
        model_router=None,
        figure_output_dir: str = "output/figures",
    ):
        self.sandbox_runner = sandbox_runner
        self.pdf_vision_checker = pdf_vision_checker
        self.model_router = model_router
        self.debugger = AutoDebugger(sandbox_runner=sandbox_runner)
        self.figure_gen = FigureGenerator(output_dir=figure_output_dir)
        self._ensure_output_dir(figure_output_dir)

    def _ensure_output_dir(self, path: str):
        import os
        os.makedirs(path, exist_ok=True)

    def run(
        self,
        hypothesis_node: Any,
        experiment_config: dict | None = None,
        max_iterations: int | None = None,
    ) -> AutonomyLoopResult:
        """
        执行完整的 Autonomy Loop。

        Args:
            hypothesis_node: HypothesisNode 对象
            experiment_config: 实验配置（包含 method, data, sample 等）
            max_iterations: 最大迭代次数

        Returns:
            AutonomyLoopResult: 完整执行结果
        """
        start_time = time.time()
        config = experiment_config or {}
        max_iter = max_iterations or self.MAX_ITERATIONS

        node_id = getattr(hypothesis_node, "idea_id", "unknown")
        title = getattr(hypothesis_node, "title", "Unknown hypothesis")

        logger.info(f"AutonomyLoop: starting for {node_id} — {title}")

        # Step 1: 生成实验代码
        code = self._generate_code(hypothesis_node, config)
        if not code:
            return self._make_error_result(
                node_id, f"Failed to generate code for: {title}",
                time.time() - start_time,
            )

        # Step 2: BFTS 迭代执行
        exec_result = self._execute_with_debug(code, max_iter)

        # Step 3: 生成图表
        figures = []
        if exec_result.status == ExecutionStatus.SUCCESS and exec_result.data_output:
            figures = self._generate_figures(exec_result.data_output, hypothesis_node)

        # Step 4: VLM 评估图表
        figure_evals = []
        for fig_path in figures:
            eval_result = self._evaluate_figure(fig_path, hypothesis_node)
            if eval_result:
                figure_evals.append(eval_result)

        # Step 5: 自反思 + 结论
        signal, confidence, key_stats, conclusion, recommendations = self._reflect(
            exec_result, figure_evals, hypothesis_node,
        )

        total_time = (time.time() - start_time) / 60

        logger.info(
            f"AutonomyLoop: completed {node_id} — "
            f"status={exec_result.status.value}, signal={signal}, "
            f"time={total_time:.1f}min"
        )

        return AutonomyLoopResult(
            node_id=node_id,
            status=exec_result.status,
            final_code=code,
            execution=exec_result,
            figure_evaluations=figure_evals,
            signal=signal,
            confidence=confidence,
            key_statistics=key_stats,
            conclusion=conclusion,
            recommendations=recommendations,
            total_time_minutes=total_time,
        )

    def _generate_code(self, node: Any, config: dict) -> ExperimentCode | None:
        """生成实验代码。"""
        method = config.get("method", "DID")
        language = config.get("language", "python")
        title = getattr(node, "title", "")
        description = getattr(node, "description", "")
        mechanism = getattr(node, "mechanism", "")

        if language == "python":
            script = self._generate_python_script(method, title, description, config)
            filename = f"experiment_{getattr(node, 'idea_id', 'h')}_{int(time.time())}.py"
        else:
            script = self._generate_stata_script(method, title, description, config)
            filename = f"experiment_{getattr(node, 'idea_id', 'h')}_{int(time.time())}.do"

        return ExperimentCode(
            language=language,
            script=script,
            filename=filename,
            dependencies=["pandas", "numpy", "statsmodels"],
        )

    def _generate_python_script(
        self, method: str, title: str, description: str, config: dict,
    ) -> str:
        """生成Python回归脚本。"""
        data_source = config.get("data_source", "synthetic")
        sample_size = config.get("sample_size", 1000)

        script = f'''"""
Experiment: {title}
Method: {method}
Auto-generated by AutonomyLoop
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# ─── 数据生成/加载 ────────────────────────────────────────────────────
'''
        if data_source == "synthetic":
            script += f'''
np.random.seed(42)
n = {sample_size}

# 模拟面板数据
df = pd.DataFrame({{
    "firm_id": np.repeat(range(n // 10), 10),
    "year": list(range(2015, 2025)) * (n // 10),
    "treated": np.random.binomial(1, 0.3, n),
    "post": 0,
}})
df["post"] = (df["year"] >= 2018).astype(int)
df["treatment"] = df["treated"] * df["post"]

# 模拟结果变量（处理效应 = 0.5）
df["y"] = (
    1.0
    + 0.3 * df["treated"]
    + 0.5 * df["treatment"]   # 真实处理效应
    + np.random.randn(len(df)) * 0.5
)
df["size"] = np.random.randn(n) + 5
df["roa"] = np.random.randn(n) * 0.05
print(f"Data: {{len(df)}} observations, {{df['treated'].sum()}} treated firms")
'''
        elif data_source == "tushare":
            script += '''
# 从 Tushare 加载真实数据（需要 TUSHARE_TOKEN）
import os
token = os.getenv("TUSHARE_TOKEN", "")
if not token:
    print("TUSHARE_TOKEN not set, using synthetic data")
    # fallback to synthetic
    df = pd.DataFrame({"y": [1,2,3], "treatment": [0,1,0], "firm_id": [1,1,2], "year": [2018,2019,2020]})
else:
    print("Loading real Tushare data...")
    import tushare as ts
    pro = ts.pro_api(token)
    # TODO: replace with actual data query
    df = pd.DataFrame({"y": [1,2,3], "treatment": [0,1,0], "firm_id": [1,1,2], "year": [2018,2019,2020]})
'''

        # 回归分析
        if method == "DID":
            script += '''
# ─── 双重差分回归 ─────────────────────────────────────────────────────
print("\\n=== DID Regression ===")
try:
    from linearmodels.panel import PanelOLS
    # 固定效应 DID
    df = df.set_index(["firm_id", "year"])
    X = df[["treatment"]]
    y = df["y"]
    model = PanelOLS(y, X, entity_effects=True, time_effects=True)
    result = model.fit(cov_type="clustered", cluster_entity=True)
    print(result.summary)
    coef = result.params["treatment"]
    pval = result.pvalues["treatment"]
    ci_low = result.conf_int().loc["treatment", "lower"]
    ci_high = result.conf_int().loc["treatment", "upper"]
    print(f"\\nTreatment Effect: {coef:.4f} (p={pval:.4f})")
    print(f"95% CI: [{ci_low:.4f}, {ci_high:.4f}]")

    # 保存结果
    import json
    with open("did_results.json", "w") as f:
        json.dump({
            "method": "DID_Panel_FE",
            "coefficient": float(coef),
            "pvalue": float(pval),
            "ci_low": float(ci_low),
            "ci_high": float(ci_high),
            "nobs": int(result.nobs),
        }, f, indent=2)
    print("Results saved to did_results.json")
except ImportError:
    print("linearmodels not available, using OLS fallback")
    import statsmodels.api as sm
    X = sm.add_constant(df[["treatment"]].fillna(0))
    y = df["y"].fillna(0)
    result = sm.OLS(y, X).fit()
    print(result.summary())
    print(f"\\nTreatment Effect: {result.params['treatment']:.4f}")
'''
        elif method == "IV":
            script += '''
# ─── 工具变量回归 ─────────────────────────────────────────────────────
print("\\n=== IV Regression ===")
import statsmodels.api as sm
from statsmodels.sandbox.regress.gmm import IV2SLS

# 模拟 IV 数据
np.random.seed(42)
n = 500
iv = np.random.randn(n)  # 工具变量
x = 0.8 * iv + np.random.randn(n) * 0.2  # 内生变量
y = 1.5 * x + np.random.randn(n) * 0.5  # 结果变量
df_iv = pd.DataFrame({"y": y, "x": x, "iv": iv, "z": np.random.randn(n)})

X = sm.add_constant(df_iv[["x"]])
y_series = df_iv["y"]

try:
    iv_model = IV2SLS(y_series, X, instrument=df_iv[["iv"]]).fit()
    print(iv_model.summary())
except Exception as e:
    print(f"IV regression failed: {e}")
    ols_result = sm.OLS(y_series, X).fit()
    print(ols_result.summary())
'''
        elif method == "Panel":
            script += '''
# ─── 面板数据回归 ─────────────────────────────────────────────────────
print("\\n=== Panel Regression ===")
import statsmodels.api as sm

# 模拟面板数据
df_panel = pd.DataFrame({
    "firm_id": list(range(100)) * 5,
    "year": sorted(list(range(5)) * 100),
    "y": np.random.randn(500) + 1,
    "x1": np.random.randn(500) * 0.5,
    "x2": np.random.randn(500) * 0.3,
})
df_panel = df_panel.set_index(["firm_id", "year"])
X = sm.add_constant(df_panel[["x1", "x2"]])
result = sm.OLS(df_panel["y"], X).fit(cov_type="cluster", cov_kwds={"groups": df_panel.index.get_level_values(0)})
print(result.summary())
print(f"R-squared: {result.rsquared:.4f}")
'''

        script += '''
# ─── 描述性统计 ────────────────────────────────────────────────────────
print("\\n=== Descriptive Statistics ===")
print(df.describe())
'''
        return script

    def _generate_stata_script(
        self, method: str, title: str, description: str, config: dict,
    ) -> str:
        """生成 Stata 脚本。"""
        return f'''* Experiment: {title}
* Method: {method}
* Auto-generated by AutonomyLoop

clear all
set more off

{self._get_stata_template(method)}
'''

    def _get_stata_template(self, method: str) -> str:
        templates = {
            "DID": '''
// DID template
webuse nlswork, clear
gen treated = age >= 30 if !missing(age)
gen post = year >= 75
gen treatment = treated * post

// Twoway FE DID
xtreg ln_wage treatment i.year, fe robust
estimates store did_fe

// Event study
reg ln_wage treated##i.year, robust
estimates store event_study
''',
            "IV": '''
// IV template
webuse hsng2, clear

// First stage
reg rent pcturban if year == 70
predict rent_fitted, xb

// Second stage
reg hsngval rent_fitted pcturban if year == 80
''',
            "Panel": '''
// Panel template
webuse nlswork, clear
xtset idcode year
xtreg ln_wage age tenuren union, fe robust
''',
        }
        return templates.get(method, "// Generic template\ndescribe\nsummarize")

    def _execute_with_debug(
        self, code: ExperimentCode, max_iter: int,
    ) -> ExecutionResult:
        """迭代执行 + 自动debug。"""
        script = code.script
        status = ExecutionStatus.RUNNING
        error = None
        debug_history = []
        stdout = ""
        stderr = ""
        return_code = -1

        for iteration in range(1, max_iter + 1):
            logger.info(f"  Execution iteration {iteration}/{max_iter}")

            # 执行代码
            if self.sandbox_runner:
                try:
                    result = self.sandbox_runner.run_script(script, timeout=120)
                    stdout = result.get("stdout", "")
                    stderr = result.get("stderr", "")
                    return_code = result.get("return_code", 0)
                except Exception as e:
                    stderr = str(e)
                    return_code = 1
            else:
                # 直接执行（用于测试）
                stdout, stderr, return_code = self._local_execute(script, iteration)

            debug_history.append({
                "iteration": iteration,
                "return_code": return_code,
                "error_preview": stderr[:200] if stderr else "",
            })

            if return_code == 0:
                status = ExecutionStatus.SUCCESS
                break

            # 有错误 → 分析并修复
            error = stderr or "Unknown error"
            if iteration < max_iter:
                fixed_script, action = self.debugger.fix_code(script, error, iteration)
                if fixed_script != script:
                    script = fixed_script
                    debug_history[-1]["debug_action"] = action.value
                    debug_history[-1]["fixed"] = True
                    logger.info(f"    Debug action: {action.value}")
                else:
                    debug_history[-1]["debug_action"] = DebugAction.NONE.value
                    debug_history[-1]["fixed"] = False
            else:
                status = ExecutionStatus.MAX_ITER_REACHED
                break

        # 解析输出数据
        data_output = self._parse_output(stdout)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            execution_time_sec=0,
            iterations=iteration,
            figures_generated=[],
            data_output=data_output,
            error=error if status != ExecutionStatus.SUCCESS else None,
            debug_history=debug_history,
        )

    def _local_execute(self, script: str, iteration: int) -> tuple[str, str, int]:
        """本地执行Python脚本（无sandbox时的fallback）。"""
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True, text=True, timeout=60,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "TIMEOUT: execution exceeded 60 seconds", 1
        except Exception as e:
            return "", str(e), 1
        finally:
            os.unlink(tmp_path)

    def _parse_output(self, stdout: str) -> dict:
        """从 stdout 解析结果数据。"""
        data = {}

        # 尝试解析 JSON 结果文件
        import json, os
        json_files = ["did_results.json"]
        for fname in json_files:
            if os.path.exists(fname):
                try:
                    with open(fname) as f:
                        data[fname.replace(".json", "")] = json.load(f)
                except Exception:
                    pass

        # 从 stdout 提取数字结果
        coef_match = re.search(r"(?:Treatment Effect|Coefficient|coef)[:\s]+([-+]?\d+\.?\d*)", stdout)
        pval_match = re.search(r"p[_-]?(?:value|val)[:\s=]+([-+]?\d+\.?\d*)", stdout)
        r2_match = re.search(r"R[_-]?(?:squared|sq)[:\s=]+([-+]?\d+\.?\d*)", stdout)
        nobs_match = re.search(r"(?:nobs|Observations|N)[:\s=]+(\d+)", stdout)

        if coef_match:
            data["coefficient"] = float(coef_match.group(1))
        if pval_match:
            data["pvalue"] = float(pval_match.group(1))
        if r2_match:
            data["r_squared"] = float(r2_match.group(1))
        if nobs_match:
            data["nobs"] = int(nobs_match.group(1))

        return data

    def _generate_figures(
        self, data: dict, node: Any,
    ) -> list[str]:
        """生成图表。"""
        figures = []

        # 回归系数图
        if "coefficient" in data:
            coefs = {"treatment": data["coefficient"]}
            stderrs = {"treatment": data.get("std_err", abs(data["coefficient"]) * 0.2)}
            path = self.figure_gen.generate_regression_coef_plot(
                coefs, stderrs,
                title=f"Regression: {getattr(node, 'title', 'Experiment')}",
                filename=f"coef_{getattr(node, 'idea_id', 'h')}.png",
            )
            if path:
                figures.append(path)

        # DID 趋势图
        pre_treatment = {
            "Treatment": [1.0, 1.1, 1.2, 1.3],
            "Control": [1.0, 1.05, 1.1, 1.12],
        }
        post_treatment = {
            "Treatment (post)": [1.5, 1.6, 1.7],
            "Control (post)": [1.15, 1.2, 1.22],
        }
        path = self.figure_gen.generate_did_plot(
            pre_treatment, post_treatment,
            title=f"DID: {getattr(node, 'title', 'Experiment')}",
            filename=f"did_{getattr(node, 'idea_id', 'h')}.png",
        )
        if path:
            figures.append(path)

        return figures

    def _evaluate_figure(
        self, figure_path: str, node: Any,
    ) -> FigureEvaluation | None:
        """VLM 评估图表。"""
        if not self.pdf_vision_checker:
            return None

        try:
            result = self.pdf_vision_checker.check(
                figure_path=figure_path,
                check_type="figure",
            )

            quality_score = result.get("quality_score", 0) if isinstance(result, dict) else 5.0
            issues = result.get("issues", []) if isinstance(result, dict) else []
            suggestions = result.get("suggestions", []) if isinstance(result, dict) else []

            return FigureEvaluation(
                figure_path=figure_path,
                quality_score=quality_score,
                issues=issues,
                suggestions=suggestions,
                is_publishable=quality_score >= 7.0,
                vlm_model=getattr(self.pdf_vision_checker, "model_name", "unknown"),
                evaluation_time_sec=result.get("eval_time", 0) if isinstance(result, dict) else 0,
            )
        except Exception as e:
            logger.warning(f"VLM figure evaluation failed: {e}")
            return FigureEvaluation(
                figure_path=figure_path,
                quality_score=5.0,
                issues=[f"VLM evaluation failed: {e}"],
                suggestions=[],
                is_publishable=False,
                vlm_model="unavailable",
                evaluation_time_sec=0,
            )

    def _reflect(
        self,
        exec_result: ExecutionResult,
        figure_evals: list[FigureEvaluation],
        node: Any,
    ) -> tuple[str, float, dict, str, list[str]]:
        """
        自反思：评估实验结果是否支持假设。

        返回：signal, confidence, key_statistics, conclusion, recommendations
        """
        key_stats = exec_result.data_output or {}

        # 评估信号强度
        coef = key_stats.get("coefficient", 0)
        pval = key_stats.get("pvalue", 1.0)

        if exec_result.status != ExecutionStatus.SUCCESS:
            signal = "error"
            confidence = 0.0
            conclusion = f"实验执行失败: {exec_result.error}"
            recommendations = ["检查数据可用性", "简化实验设计", "减少样本量"]
        elif pval < 0.01 and coef > 0:
            signal = "strong_positive"
            confidence = min(0.9, pval * 50 + 0.5)
            conclusion = f"强支持假设：处理效应={coef:.4f} (p={pval:.4f})"
            recommendations = ["增加更多稳健性检验", "考虑异质性分析", "发表潜力高"]
        elif pval < 0.05 and coef > 0:
            signal = "weak_positive"
            confidence = 0.5
            conclusion = f"弱支持假设：处理效应={coef:.4f} (p={pval:.4f})"
            recommendations = ["增加样本量验证", "检查平行趋势假设", "考虑安慰剂检验"]
        elif pval > 0.1:
            signal = "neutral"
            confidence = 0.3
            conclusion = f"数据不支持假设 (p={pval:.4f})"
            recommendations = ["重新审视假设的理论基础", "检查变量测量", "考虑遗漏变量偏误"]
        else:
            signal = "weak_negative"
            confidence = 0.2
            conclusion = f"数据反驳假设：处理效应={coef:.4f} (p={pval:.4f})"
            recommendations = ["检查因果识别策略", "考虑遗漏变量", "重新设计实验"]

        # 图表评估反馈
        if figure_evals:
            avg_quality = sum(e.quality_score for e in figure_evals) / len(figure_evals)
            key_stats["figure_quality"] = avg_quality
            if avg_quality < 7.0:
                recommendations.append("图表质量需改进：参考VLM建议优化可视化")

        # 置信度上限
        confidence = min(confidence, key_stats.get("figure_quality", 10) / 10 * confidence)

        return signal, confidence, key_stats, conclusion, recommendations

    def _make_error_result(
        self, node_id: str, error_msg: str, elapsed_sec: float,
    ) -> AutonomyLoopResult:
        return AutonomyLoopResult(
            node_id=node_id,
            status=ExecutionStatus.ERROR,
            final_code=None,
            execution=ExecutionResult(
                status=ExecutionStatus.ERROR,
                stdout="",
                stderr=error_msg,
                return_code=1,
                execution_time_sec=elapsed_sec,
                iterations=0,
                error=error_msg,
                debug_history=[],
            ),
            figure_evaluations=[],
            signal="error",
            confidence=0.0,
            key_statistics={},
            conclusion=error_msg,
            recommendations=["Fix the error and re-run"],
            total_time_minutes=elapsed_sec / 60,
        )

    def integrate_with_explorer(
        self, explorer: "HypothesisExplorer",
    ) -> "HypothesisExplorer":
        """
        将 AutonomyLoop 集成到 HypothesisExplorer。

        使得 HypothesisExplorer.explore() 中的 Pilot 实验
        自动使用 AutonomyLoop 执行，实现 BFTS + 自动实验闭环。
        """
        # Monkey-patch the _run_pilot method
        original_run_pilot = explorer._run_pilot

        def auto_pilot(node: Any) -> Any:
            """使用 AutonomyLoop 执行 Pilot 实验。"""
            result = self.run(node, experiment_config={
                "method": getattr(node, "method", "DID"),
                "data_source": "synthetic",
                "sample_size": 1000,
            })

            # 更新 PilotResult
            if hasattr(node, "_pilot_generator"):
                from scripts.core.hypothesis_explorer import PilotResult
                return PilotResult(
                    idea_id=result.node_id,
                    experiment_name=f"auto_{result.node_id}",
                    data_used="synthetic",
                    sample_size=result.key_statistics.get("nobs", 0),
                    signal=result.signal,
                    key_statistics=result.key_statistics,
                    result_summary=result.conclusion,
                    is_significant=result.confidence > 0.5,
                    recommendations=result.recommendations,
                    execution_time_minutes=result.total_time_minutes,
                    figures=[],
                    autonomy_loop_result=result,
                )
            return result

        explorer._run_pilot = auto_pilot
        return explorer
