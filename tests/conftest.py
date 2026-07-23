"""
pytest 配置：fixtures、mock LLM gateway、临时目录
"""
import sys
from pathlib import Path

# 确保 scripts/ 在 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock


# ─── NumPy _NoValue singleton unification (pytest-cov workaround) ────────────
# pytest-cov's tracer can inject its own _NoValueType sentinel into numpy
# internals; the compiled C code in numpy.core._methods does an identity
# check `initial is _NoValue` and raises:
#   TypeError: float() argument must be a string or a real number,
#              not '_NoValueType'
# We unify the sentinel at import time so that any module referencing
# numpy's _NoValue gets numpy's own canonical object.
try:
    _NUMPY_NO_VALUE = np._NoValue  # canonical singleton
    for _mod_name in list(sys.modules):
        _mod = sys.modules.get(_mod_name)
        if _mod is None:
            continue
        try:
            _cur = getattr(_mod, "_NoValue", None)
            if _cur is not None and _cur is not _NUMPY_NO_VALUE:
                _mod._NoValue = _NUMPY_NO_VALUE  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            continue
    del _mod_name, _mod, _cur
except Exception:
    pass


# ─── pandas.util._decorators.deprecate_kwarg compatibility shim ─────────────
# audit-2026-07-05 PR-7F: pandas 3.0+ changed deprecate_kwarg() signature.
# statsmodels 0.14.x calls it positionally with (old_arg, new_arg), but
# pandas now uses keyword args only. Importing statsmodels.tsa.stattools
# (transitively pulled by linearmodels → statsmodels.api) raises:
#   TypeError: deprecate_kwarg() missing 1 required positional argument
# This breaks scripts.research_framework.iv_panel and ~25 tests in
# tests/test_iv_panel.py. Patch the decorator to a no-op stub.
try:
    import pandas.util._decorators as _pd_dec

    class _StubDeprecateKwarg:
        """No-op drop-in for pandas.util._decorators.deprecate_kwarg."""

        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, func):
            return func

    _pd_dec.deprecate_kwarg = _StubDeprecateKwarg
    del _pd_dec, _StubDeprecateKwarg
except Exception:
    pass


# ─── Shared mock fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_gateway():
    """Mock LLM Gateway（无真实API调用）。"""
    gateway = MagicMock()
    gateway.generate.return_value = MagicMock(
        response="Mock LLM response",
        model_used="mock",
        input_tokens=100,
        output_tokens=50,
        latency_ms=500,
    )
    gateway.call_mcp_tool.return_value = {"data": "mock_mcp_result"}
    return gateway


@pytest.fixture
def mock_memory():
    """Mock ResearchMemory（无SQLite写入）。"""
    from scripts.core.memory import ResearchMemory
    memory = MagicMock(spec=ResearchMemory)
    memory.add.return_value = True
    memory.get_context.return_value = []
    return memory


@pytest.fixture
def temp_output_dir(tmp_path):
    """临时输出目录。"""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def sample_financial_data():
    """样本财务数据（用于测试分析师）。"""
    return {
        "income_statement": {
            "revenue": 1000,
            "net_income": 100,
            "gross_profit": 300,
            "operating_income": 150,
            "ebit": 160,
            "interest_expense": 10,
            "income_tax": 30,
            "pretax_income": 130,
        },
        "balance_sheet": {
            "total_assets": 5000,
            "total_equity": 2500,
            "total_liabilities": 2500,
            "current_assets": 2000,
            "current_liabilities": 1000,
            "cash": 500,
            "accounts_receivable": 300,
            "fixed_assets": 1500,
        },
        "cash_flow": {
            "operating_cash_flow": 120,
            "capex": 50,
            "net_cash_flow": 70,
        },
    }


@pytest.fixture
def sample_empirical_content():
    """样本实证论文内容（用于测试 halt rules）。"""
    return """本研究考察碳排放权交易对企业绿色创新的影响。
研究问题：碳排放权交易政策能否促进企业绿色创新？
假设H1：碳排放权交易对企业绿色专利申请数量有正向影响。
假设H2：碳排放权对企业绿色创新效率有正向影响。
方法：使用双重差分法（DID），处理组为企业获得的碳排放权配额。
数据来源：CSMAR、国泰安数据库。样本时间范围：2015-2022年。
最终样本量：3082个企业-年份观测值。
被解释变量：绿色专利申请数量（ln_gti）。
核心解释变量：Treat × Post（DID交互项）。
控制变量：企业规模、资产负债率、ROA、资本密集度。
固定效应：企业固定效应、年份固定效应。
标准误：双向聚类（企业×年份）。
稳健性检验：(1)替换被解释变量为绿色专利授权数量。
稳健性检验：(2)调整样本范围，排除重污染行业。
预期：稳健性检验结果应与基准回归方向一致。
异质性分析（按企业规模分组）：大型企业受影响更显著。
R²: 0.35, N: 3082, ***: p<0.01, **: p<0.05, *: p<0.1"""


@pytest.fixture
def mock_llm_response():
    """Mock LLM response JSON for ReviewResult parsing tests."""
    return """{
        "overall_score": 8.0,
        "overall_recommendation": "Accept",
        "scores": {
            "methodology_rigor": {"score": 8, "max": 10, "justification": "DID design is sound"},
            "novelty": {"score": 7, "max": 10, "justification": "Interesting research question"},
            "clarity": {"score": 8, "max": 10, "justification": "Well structured"},
            "reproducibility": {"score": 7, "max": 10, "justification": "Most details provided"},
            "impact": {"score": 8, "max": 10, "justification": "Relevant to the field"}
        },
        "confidence": 0.85,
        "summary": "Strong paper with sound methodology"
    }"""


# ─── Mock DataFrame Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def mock_panel_df():
    """
    Mock panel DataFrame for regression/DID tests.
    n=50 units, n=20 periods, treatment at middle period (period 10).
    """
    np.random.seed(42)
    n_units = 50
    n_periods = 20
    treated_period = 10

    data = []
    for unit_id in range(n_units):
        is_treated = unit_id >= 40  # last 10 units are treated
        for period in range(1, n_periods + 1):
            treat_var = 1 if is_treated and period >= treated_period else 0
            # Synthetic outcome with unit + time effects
            base = 10 + 0.3 * period + np.random.normal(0, 0.5)
            treatment_effect = 1.5 * treat_var if is_treated else 0
            y = base + treatment_effect + np.random.normal(0, 0.2)
            data.append({
                "firm_id": f"firm_{unit_id:03d}",
                "year": 2000 + period,
                "roa": y,
                "lev": np.random.uniform(0.2, 0.8),
                "size": np.random.uniform(18, 22),
                "tangibility": np.random.uniform(0.1, 0.5),
                "roa_lag": base + np.random.normal(0, 0.2) if period > 1 else np.nan,
                "did": treat_var,
                "post": 1 if period >= treated_period else 0,
                "treat": 1 if is_treated else 0,
                "industry": f"ind_{unit_id % 5}",
            })
    return pd.DataFrame(data)


@pytest.fixture
def mock_did_df():
    """
    Simple 2x2 DID DataFrame for testing.
    """
    np.random.seed(42)
    data = {
        "firm_id": [],
        "year": [],
        "roa": [],
        "did": [],
        "post": [],
        "treat": [],
        "ln_assets": [],
        "roa_lag": [],
        "industry": [],
    }
    for firm_id in range(100):
        is_treated = firm_id >= 50
        for year in [2018, 2019, 2020, 2021]:
            data["firm_id"].append(f"firm_{firm_id}")
            data["year"].append(year)
            data["post"].append(1 if year >= 2020 else 0)
            data["treat"].append(1 if is_treated else 0)
            data["did"].append(1 if is_treated and year >= 2020 else 0)
            base = 0.05 + 0.01 * (year - 2018) + np.random.normal(0, 0.01)
            treatment_effect = 0.02 if is_treated and year >= 2020 else 0
            data["roa"].append(base + treatment_effect)
            data["ln_assets"].append(np.log(1e8 + firm_id * 1e6 + np.random.randn() * 1e7))
            data["roa_lag"].append(base - 0.01 + np.random.normal(0, 0.01))
            data["industry"].append(f"ind_{firm_id % 5}")
    return pd.DataFrame(data)


@pytest.fixture
def mock_rdd_df():
    """
    Mock RDD DataFrame: running variable score, outcome y, treatment assignment.
    """
    np.random.seed(42)
    n = 500
    x = np.random.uniform(-1, 1, n)  # running variable
    cutoff = 0.0

    # True treatment effect at cutoff
    treatment_effect = 0.5
    noise = np.random.normal(0, 0.1, n)
    y = 2 + treatment_effect * (x >= cutoff) + 3 * x + noise

    df = pd.DataFrame({
        "score": x,
        "outcome": y,
        "treated": (x >= cutoff).astype(int),
        "firm_id": [f"firm_{i}" for i in range(n)],
    })
    return df


@pytest.fixture
def mock_sc_df():
    """
    Mock data for Synthetic Control: 1 treated unit + 49 donors, 20 periods.
    Treatment at period 10.
    """
    np.random.seed(42)
    n_periods = 20
    n_donors = 49
    treatment_time = 10

    records = []

    # Treated unit (unit_id = 0)
    for t in range(n_periods):
        y = 10 + 0.5 * t + (3 if t >= treatment_time else 0) + np.random.normal(0, 0.3)
        records.append({
            "unit": "treated_california",
            "year": 2000 + t,
            "gdp_per_capita": y,
            "is_treated": 1 if t >= treatment_time else 0,
        })

    # Donor units (control states)
    for uid in range(1, n_donors + 1):
        base = np.random.uniform(8, 12)
        trend = np.random.uniform(0.3, 0.7)
        for t in range(n_periods):
            y = base + trend * t + np.random.normal(0, 0.3)
            records.append({
                "unit": f"state_{uid:03d}",
                "year": 2000 + t,
                "gdp_per_capita": y,
                "is_treated": 0,
            })

    return pd.DataFrame(records)


@pytest.fixture
def mock_time_series_df():
    """Mock time series DataFrame for general tests."""
    np.random.seed(42)
    n = 100
    return pd.DataFrame({
        "date": pd.date_range("2015-01-01", periods=n, freq="M"),
        "value": np.cumsum(np.random.randn(n)) + 100,
        "group": np.random.choice(["A", "B", "C"], n),
    })


# ─── Latex fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def valid_latex_tex(tmp_path):
    """A minimal valid LaTeX file with all cross-refs intact."""
    content = r"""\documentclass{article}
\begin{document}
\section{Intro}\label{sec:intro}
See Figure~\ref{fig:main} and Table~\ref{tab:desc}.

\begin{figure}
  \centering
  \caption{Main Result}\label{fig:main}
\end{figure}

\begin{table}
  \caption{Descriptive Statistics}\label{tab:desc}
\end{table}

\bibliography{refs}
\end{document}
"""
    p = tmp_path / "valid.tex"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def broken_latex_tex(tmp_path):
    """A LaTeX file with several intentional errors."""
    content = r"""\documentclass{article}
\begin{document}
\section{Test}\label{sec:test}
See Equation~\ref{eq:missing} and Figure~\ref{fig:fake}.

\begin{figure}
  % missing caption and label
\end{figure}

\begin{table}
  \caption{Data}\label{tab:data}
\end{table}

\begin{tabular}{ccc}
  a & b \\
  x & y & z \\
\end{tabular}

\bibliographystyle{plain}
\end{document}
"""
    p = tmp_path / "broken.tex"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def math_latex_tex(tmp_path):
    """LaTeX file with math mode issues."""
    content = r"""\documentclass{article}
\begin{document}
Inline $math with missing closer.

Display math:
$$
y = \alpha + \beta x + \epsilon
$$
\end{document}
"""
    p = tmp_path / "math.tex"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def refs_bib(tmp_path):
    """A .bib file for citation tests."""
    bib = r"""@article{Author2020,
  author = {Author, A.},
  title = {A Study},
  journal = {Journal},
  year = {2020},
}
"""
    p = tmp_path / "refs.bib"
    p.write_text(bib, encoding="utf-8")
    return p
