"""DigitalFinanceDirection: Fintech, digital finance and financial inclusion.

Research focus:
    1. Digital finance penetration and financial inclusion
    2. Fintech competition and bank performance
    3. E-commerce platforms and SME financing

Data strategy:
    - Primary: user-tushare (A-share financials)
    - Secondary: user-financial (macro indicators)
    - Tertiary: Published benchmarks (CSMAR, Wind)
    - Last resort: ABORT
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

_log = logging.getLogger(__name__)


def _safe_fmt(v: Any, decimals: int = 4) -> str:
    """Safely format a numeric value for LaTeX tables.

    Args:
        v: Value to format (may be None or non-numeric).
        decimals: Number of decimal places.

    Returns:
        Formatted string, or "--" if value is None/invalid.
    """
    if v is None:
        return "--"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return "--"


MCP_TUSHARE = "user-tushare"
MCP_FINANCIAL = "user-financial"
MCP_YFINANCE = "user-yfinance"

DEFAULT_DFI_DIR = os.environ.get(
    "PKU_DFI_DATA_DIR", "data/digital_finance"
)
DEFAULT_CSMAR_DIR = os.environ.get(
    "CSMAR_DATA_DIR", "data/csmar"
)


class DigitalFinanceDataError(Exception):
    """Raised when no data source is available for digital finance research."""


class DigitalFinanceDirection(BaseResearchDirection):
    """数字金融与金融包容性、Fintech竞争对企业绩效的影响研究。

    研究设计采用北京大学数字普惠金融指数作为核心处理变量，以双重差分
    (DID)和面板回归为主要识别策略，考察数字金融发展对企业融资、绩效
    和金融包容性的多维影响。

    Attributes:
        name: Display name for this research direction.
        slug: URL-safe identifier.
        description: One-line Chinese description.
        policy_events: Chronological list of major digital finance policy events.
    """

    name = "数字金融"
    slug = "digital_finance"
    description = (
        "数字普惠金融、Fintech竞争与金融包容性对企业绩效的影响研究"
    )

    policy_events = [
        (2013, "余额宝上线，互联网理财元年"),
        (2015, "国务院《互联网+行动指导意见》发布"),
        (2016, "G20数字普惠金融高级原则"),
        (2017, "央行金融科技委员会成立"),
        (2019, "央行金融科技发展规划(2019-2021)"),
        (2021, "央行金融科技发展规划(2022-2025)"),
        (2022, "数据要素市场化配置改革启动"),
        (2023, "生成式AI管理办法征求意见"),
    ]

    def fetch_data(self, topic: str) -> pd.DataFrame:
        """Fetch data for digital finance research.

        Args:
            topic: Research topic or keyword.

        Returns:
            DataFrame with columns: year, province, dfi_index, firm_id,
            roa, lev, size, age, tangibility, etc.

        Raises:
            DigitalFinanceDataError: If no data source is available.
        """
        _log.info("Fetching digital finance data for topic: %s", topic)

        data = self._try_tushare()
        if data is not None and len(data) > 0:
            _log.info("Successfully fetched data from Tushare: %d rows", len(data))
            return data

        data = self._try_financial_mcp()
        if data is not None and len(data) > 0:
            _log.info("Successfully fetched data from financial MCP: %d rows", len(data))
            return data

        data = self._try_csv_files()
        if data is not None and len(data) > 0:
            _log.info("Successfully loaded data from CSV: %d rows", len(data))
            return data

        raise DigitalFinanceDataError(
            "No data source available for digital finance research. "
            "Tried: user-tushare, user-financial, CSV files. "
            "Please configure at least one data source or provide manual data."
        )

    def _try_tushare(self) -> pd.DataFrame | None:
        """Try to fetch data via Tushare MCP."""
        try:
            from scripts.core.dynamic_tools import get_mcp_tool

            tool = get_mcp_tool(MCP_TUSHARE, "get_financial_report")
            if tool is None:
                return None

            result = tool(
                ts_code="000001.SZ",
                report_type="balance",
                start_date="20130101",
                end_date="20231231",
            )
            if result and isinstance(result, list) and len(result) > 0:
                df = pd.DataFrame(result)
                df["data_source"] = "tushare"
                return df
        except Exception as e:
            _log.warning("Tushare fetch failed: %s", e)
        return None

    def _try_financial_mcp(self) -> pd.DataFrame | None:
        """Try to fetch macro data via financial MCP."""
        try:
            from scripts.core.dynamic_tools import get_mcp_tool

            tool = get_mcp_tool(MCP_FINANCIAL, "get_macro_china")
            if tool is None:
                return None

            result = tool(indicator="dfi_index")
            if result and isinstance(result, list) and len(result) > 0:
                df = pd.DataFrame(result)
                df["data_source"] = "financial_mcp"
                return df
        except Exception as e:
            _log.warning("Financial MCP fetch failed: %s", e)
        return None

    def _try_csv_files(self) -> pd.DataFrame | None:
        """Try to load data from CSV files."""
        csv_path = os.path.join(DEFAULT_DFI_DIR, "dfi_panel.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df["data_source"] = "csv"
            return df

        csmar_path = os.path.join(DEFAULT_CSMAR_DIR, "digital_finance.csv")
        if os.path.exists(csmar_path):
            df = pd.read_csv(csmar_path)
            df["data_source"] = "csmar_csv"
            return df
        return None

    def build_panel(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build balanced panel with DFI index and firm outcomes.

        Args:
            data: Raw data from fetch_data.

        Returns:
            Panel DataFrame with columns:
                - year: int
                - province: str
                - firm_id: str
                - dfi_index: float (digital financial inclusion index)
                - roa: float (return on assets)
                - lev: float (leverage ratio)
                - size: float (firm size, log)
                - age: int (firm age)
                - tangibility: float
                - roe: float (return on equity)
                - asset_turn: float (asset turnover)
        """
        _log.info("Building panel from data with shape: %s", data.shape)

        panel = self._extract_dfi_index(data)
        panel = self._extract_firm_outcomes(panel, data)
        panel = self._add_control_variables(panel)

        panel = panel.dropna(subset=["dfi_index", "roa"])
        _log.info(
            "Panel built successfully: %d observations, %d firms, %d years",
            len(panel),
            panel["firm_id"].nunique() if "firm_id" in panel.columns else 0,
            panel["year"].nunique() if "year" in panel.columns else 0,
        )
        return panel

    def _extract_dfi_index(self, data: pd.DataFrame) -> pd.DataFrame:
        """Extract DFI index from data.

        Raises:
            DigitalFinanceDataError: If DFI column is not found in data.
        """
        dfi_columns = ["dfi_index", "dfi", "digital_finance_index", "普惠金融指数"]
        for col in dfi_columns:
            if col in data.columns:
                panel = data.copy()
                panel["dfi_index"] = pd.to_numeric(panel[col], errors="coerce")
                return panel

        # C2 修复: 不再静默生成伪随机 DFI 数据，改为显式报错
        raise DigitalFinanceDataError(
            "DFI (digital financial inclusion) index column not found in data. "
            "Expected one of: dfi_index, dfi, digital_finance_index, 普惠金融指数. "
            f"Available columns: {list(data.columns)}. "
            "Please provide DFI data from PKU DFI index files, CSMAR, or configure "
            "PKU_DFI_DATA_DIR environment variable pointing to your DFI CSV files."
        )

    def _extract_firm_outcomes(
        self,
        panel: pd.DataFrame,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Extract firm outcome variables.

        Raises:
            DigitalFinanceDataError: If required outcome variables cannot be extracted.
        """
        outcome_cols = ["roa", "ROA", "return_on_assets"]
        roa_col = None
        for col in outcome_cols:
            if col in data.columns:
                roa_col = col
                break

        if roa_col:
            panel["roa"] = pd.to_numeric(data[roa_col], errors="coerce")
        else:
            raise DigitalFinanceDataError(
                "ROA (return on assets) not found in data. "
                "Cannot generate fake financial outcomes. "
                f"Available columns: {list(data.columns)}. "
                "Please provide data with ROA column or use a different data source."
            )

        lev_col = None
        lev_candidates = ["lev", "LEV", "leverage", "资产负债率"]
        for col in lev_candidates:
            if col in data.columns:
                lev_col = col
                break
        if lev_col:
            panel["lev"] = pd.to_numeric(data[lev_col], errors="coerce")
        else:
            raise DigitalFinanceDataError(
                "Leverage ratio not found in data. "
                "Cannot generate fake leverage data. "
                f"Available columns: {list(data.columns)}. "
                "Please provide data with leverage column or use a different data source."
            )

        return panel

    def _add_control_variables(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Add control variables to panel.

        Raises:
            DigitalFinanceDataError: If required control variables cannot be derived.
        """
        if "size" not in panel.columns:
            raise DigitalFinanceDataError(
                "Firm size (size) not found in panel. "
                "Cannot generate fake size data. "
                "Please provide data with firm size column."
            )

        if "age" not in panel.columns:
            raise DigitalFinanceDataError(
                "Firm age not found in panel. "
                "Cannot generate fake age data. "
                "Please provide data with firm age column."
            )

        if "tangibility" not in panel.columns:
            raise DigitalFinanceDataError(
                "Tangibility not found in panel. "
                "Cannot generate fake tangibility data. "
                "Please provide data with tangibility column."
            )

        if "roe" not in panel.columns:
            raise DigitalFinanceDataError(
                "ROE not found in panel. "
                "Cannot generate fake ROE data. "
                "Please provide data with ROE column."
            )

        if "asset_turn" not in panel.columns:
            raise DigitalFinanceDataError(
                "Asset turnover not found in panel. "
                "Cannot generate fake asset turnover data. "
                "Please provide data with asset_turn column."
            )

        if "year" not in panel.columns:
            raise DigitalFinanceDataError(
                "Year not found in panel. "
                "Cannot determine time dimension. "
                "Please provide data with year column."
            )

        if "firm_id" not in panel.columns:
            raise DigitalFinanceDataError(
                "Firm ID not found in panel. "
                "Cannot identify individual firms. "
                "Please provide data with firm_id column."
            )

        if "province" not in panel.columns:
            raise DigitalFinanceDataError(
                "Province not found in panel. "
                "Cannot determine regional dimension. "
                "Please provide data with province column."
            )

        return panel

    # ── Data Validation ────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate digital finance panel data quality.

        Adds digital-finance-specific checks to the base validation:
        - DFI (digital financial inclusion) index column presence
        - Required outcome/control variables
        - Panel balance for FE estimation
        """
        import pandas as pd

        base = super().validate(panel)
        if not base["valid"]:
            return base

        panel_df = panel
        if not isinstance(panel_df, pd.DataFrame):
            panel_df = panel.get("panel")
        if panel_df is None:
            panel_df = panel.get("df")
        if panel_df is None or not isinstance(panel_df, pd.DataFrame) or panel_df.empty:
            return base

        # Check DFI index presence
        dfi_candidates = ["dfi_index", "dfi", "digital_finance_index", "普惠金融指数"]
        found_dfi = [v for v in dfi_candidates if v in panel_df.columns]
        if not found_dfi:
            base["warnings"].append(
                "未找到数字普惠金融指数列。"
                "期望: dfi_index / dfi / digital_finance_index。"
                "DFI指数是数字金融研究的核心处理变量。"
            )

        # Check required outcome variables
        required = ["roa"]
        for var in required:
            if var in panel_df.columns:
                miss = panel_df[var].isna().mean()
                if miss > 0.3:
                    base["warnings"].append(f"{var}: {miss:.0%} 缺失率较高 (>30%)")

        # Check leverage ratio presence
        lev_candidates = ["lev", "leverage", "LEV"]
        if not any(v in panel_df.columns for v in lev_candidates):
            base["warnings"].append(
                "未找到资产负债率变量 (lev / leverage)。"
                "杠杆率是公司金融控制变量的核心组成部分。"
            )

        return base

    def run_regressions(
        self,
        panel: pd.DataFrame,
    ) -> dict[str, Any]:
        """Run fixed-effects panel regressions.

        Args:
            panel: Balanced panel from build_panel.

        Returns:
            Dictionary with regression results:
                - main_results: list of regression dicts
                - heterogeneity_results: dict by subgroup
                - robustness_results: dict of robustness checks
        """
        if panel is None or (hasattr(panel, '__len__') and len(panel) == 0):
            _log.warning("Empty panel provided to run_regressions")
            return {
                "status": "pending",
                "tables": {},
                "note": "Panel data not available - cannot run regressions"
            }

        if "dfi_index" not in panel.columns or "roa" not in panel.columns:
            _log.warning("Required columns (dfi_index, roa) missing from panel")
            return {
                "status": "pending",
                "tables": {},
                "note": "Required columns missing from panel data"
            }

        _log.info("Running panel regressions on %d observations", len(panel))

        try:
            has_linearmodels = True
        except ImportError:
            has_linearmodels = False
            _log.warning("linearmodels not available, using OLS fallback")

        results = {}

        main_reg = self._run_main_regression(panel, has_linearmodels)
        results["main_results"] = main_reg

        results["heterogeneity_results"] = self._run_heterogeneity(panel, has_linearmodels)

        results["robustness_results"] = self._run_robustness(panel, has_linearmodels)

        results["status"] = "ok"
        return results

    def _run_main_regression(
        self,
        panel: pd.DataFrame,
        use_linearmodels: bool,
    ) -> list[dict[str, Any]]:
        """Run main FE regression with DFI index.

        Three specifications:
            (1) DFI Index only
            (2) DFI Index + firm controls (size, age, lev)
            (3) DFI Index + firm controls + firm fixed effects

        Raises:
            DigitalFinanceDataError: If required columns are missing.
        """
        if "dfi_index" not in panel.columns or "roa" not in panel.columns:
            raise DigitalFinanceDataError(
                "Required columns (dfi_index, roa) not found in panel. "
                "Cannot run regression with missing outcome or treatment variables."
            )

        specifications = [
            ("(1)", ["dfi_index"], [], False, False),
            ("(2)", ["dfi_index"], ["size", "age", "lev"], True, False),
            ("(3)", ["dfi_index"], ["size", "age", "lev"], True, True),
        ]

        results = []
        for spec_id, y_vars, x_vars, with_controls, with_fe in specifications:
            try:
                if use_linearmodels:
                    from linearmodels.panel import PanelOLS

                    panel_clean = panel.dropna(
                        subset=y_vars + x_vars + ["firm_id", "year"]
                    )
                    if len(panel_clean) < 10:
                        _log.warning(
                            "[DigitalFinance] Spec %s: insufficient observations (%d)",
                            spec_id, len(panel_clean),
                        )
                        continue

                    panel_clean = panel_clean.set_index(["firm_id", "year"])
                    y = panel_clean[y_vars[0]]
                    X = panel_clean[x_vars]

                    if with_fe:
                        mod = PanelOLS(y, X, entity_effects=True, time_effects=False)
                    else:
                        mod = PanelOLS(y, X, entity_effects=False)

                    res = mod.fit(cov_type="clustered", cluster_entity=True)

                    coef = float(res.params.iloc[0]) if len(res.params) > 0 else None
                    se = float(res.std_errors.iloc[0]) if len(res.std_errors) > 0 else None
                    t_stat = float(res.tstats.iloc[0]) if len(res.tstats) > 0 else None
                    p_value = float(res.pvalues.iloc[0]) if len(res.pvalues) > 0 else None
                    r_squared = float(res.rsquared) if hasattr(res, "rsquared") else None
                else:
                    import statsmodels.api as sm

                    panel_clean = panel.dropna(subset=y_vars + x_vars + ["firm_id"])
                    if len(panel_clean) < 10:
                        _log.warning(
                            "[DigitalFinance] Spec %s: insufficient observations (%d)",
                            spec_id, len(panel_clean),
                        )
                        continue

                    y = panel_clean[y_vars[0]]
                    X = panel_clean[x_vars]
                    X = sm.add_constant(X)
                    mod = sm.OLS(y, X)
                    res = mod.fit(cov_type="cluster", cov_kwds={"groups": panel_clean["firm_id"]})

                    coef = float(res.params.iloc[1]) if len(res.params) > 1 else None
                    se = float(res.bse.iloc[1]) if len(res.bse) > 1 else None
                    t_stat = float(res.tvalues.iloc[1]) if len(res.tvalues) > 1 else None
                    p_value = float(res.pvalues.iloc[1]) if len(res.pvalues) > 1 else None
                    r_squared = float(res.rsquared) if hasattr(res, "rsquared") else None

                results.append({
                    "spec": spec_id,
                    "coefficient": coef,
                    "std_error": se,
                    "t_stat": t_stat,
                    "p_value": p_value,
                    "n_obs": len(panel_clean),
                    "r_squared": r_squared,
                    "with_controls": with_controls,
                    "with_fixed_effects": with_fe,
                })
                _log.info(
                    "[DigitalFinance] Spec %s: coef=%.4f, se=%.4f, p=%.4f, N=%d",
                    spec_id, coef, se, p_value, len(panel_clean),
                )
            except Exception as exc:
                _log.warning("[DigitalFinance] Regression spec %s failed: %s", spec_id, exc)
                results.append({
                    "spec": spec_id,
                    "coefficient": None,
                    "std_error": None,
                    "t_stat": None,
                    "p_value": None,
                    "n_obs": 0,
                    "r_squared": None,
                    "with_controls": with_controls,
                    "with_fixed_effects": with_fe,
                    "error": str(exc),
                })

        return results

    def _run_heterogeneity(
        self,
        panel: pd.DataFrame,
        use_linearmodels: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        """Run heterogeneity analysis by firm size and region.

        Splits:
            - by_size: Large (size >= median) vs Small (size < median)
            - by_region: East vs Central/West (based on province column)

        Logs warnings via _log.warning on regression failures.
        Returns empty dict if linearmodels is not available.
        """
        if not use_linearmodels:
            _log.warning("linearmodels not available, skipping heterogeneity analysis")
            return {}

        het_results: dict[str, list[dict[str, Any]]] = {}

        # ── 1. By firm size ─────────────────────────────────────────────────
        if "size" not in panel.columns:
            _log.warning(
                "[DigitalFinance] Heterogeneity by size: 'size' column missing, skipping"
            )
        else:
            size_median = panel["size"].median()
            group_large = panel[panel["size"] >= size_median].copy()
            group_small = panel[panel["size"] < size_median].copy()

            size_groups: list[tuple[str, pd.DataFrame]] = [
                (f"Large (≥{size_median:.2f})", group_large),
                (f"Small (<{size_median:.2f})", group_small),
            ]

            size_results: list[dict[str, Any]] = []
            for group_label, sub_panel in size_groups:
                if len(sub_panel) < 20:
                    _log.warning(
                        "[DigitalFinance] Size group '%s': only %d obs, skipping",
                        group_label, len(sub_panel),
                    )
                    continue
                try:
                    coef, se, t_stat, pval, n_obs, r2 = self._ols_regression(
                        sub_panel, y_var="roa", x_vars=["dfi_index"], with_fe=True
                    )
                    size_results.append({
                        "group": group_label,
                        "coefficient": coef,
                        "std_error": se,
                        "t_stat": t_stat,
                        "p_value": pval,
                        "n_obs": n_obs,
                        "r_squared": r2,
                    })
                    _log.info(
                        "[DigitalFinance] Size %s: coef=%.4f, se=%.4f, p=%.4f, N=%d",
                        group_label, coef, se, pval, n_obs,
                    )
                except Exception as exc:
                    _log.warning(
                        "[DigitalFinance] Size group '%s' regression failed: %s",
                        group_label, exc,
                    )
            het_results["by_size"] = size_results

        # ── 2. By region ────────────────────────────────────────────────────
        if "province" not in panel.columns:
            _log.warning(
                "[DigitalFinance] Heterogeneity by region: 'province' column missing, skipping"
            )
        else:
            east_keywords = ["北京", "天津", "河北", "上海", "江苏", "浙江", "福建", "山东", "广东", "海南", "辽宁"]
            panel_copy = panel.copy()
            panel_copy["_is_east"] = panel_copy["province"].apply(
                lambda p: any(kw in str(p) for kw in east_keywords)
            )
            group_east = panel_copy[panel_copy["_is_east"]]
            group_other = panel_copy[~panel_copy["_is_east"]]

            region_groups: list[tuple[str, pd.DataFrame]] = [
                ("East", group_east),
                ("Central/West", group_other),
            ]

            region_results: list[dict[str, Any]] = []
            for group_label, sub_panel in region_groups:
                if len(sub_panel) < 20:
                    _log.warning(
                        "[DigitalFinance] Region group '%s': only %d obs, skipping",
                        group_label, len(sub_panel),
                    )
                    continue
                try:
                    coef, se, t_stat, pval, n_obs, r2 = self._ols_regression(
                        sub_panel, y_var="roa", x_vars=["dfi_index"], with_fe=True
                    )
                    region_results.append({
                        "group": group_label,
                        "coefficient": coef,
                        "std_error": se,
                        "t_stat": t_stat,
                        "p_value": pval,
                        "n_obs": n_obs,
                        "r_squared": r2,
                    })
                    _log.info(
                        "[DigitalFinance] Region %s: coef=%.4f, se=%.4f, p=%.4f, N=%d",
                        group_label, coef, se, pval, n_obs,
                    )
                except Exception as exc:
                    _log.warning(
                        "[DigitalFinance] Region group '%s' regression failed: %s",
                        group_label, exc,
                    )
            het_results["by_region"] = region_results

        return het_results

    def _run_robustness(
        self,
        panel: pd.DataFrame,
        use_linearmodels: bool,
    ) -> dict[str, dict[str, Any]]:
        """Run robustness checks.

        Three checks:
            1. alternative_dfi: replace dependent variable with ROE instead of ROA
            2. exclude_top_bottom: winsorize at 1% / 99% before regression
            3. lagged_dfi: use L1 (lagged) DFI index

        Logs warnings via _log.warning on regression failures.
        Returns empty dict if linearmodels is not available.
        """
        if not use_linearmodels:
            _log.warning("linearmodels not available, skipping robustness checks")
            return {}

        robustness_checks: dict[str, dict[str, Any]] = {}

        # ── 1. Alternative dependent variable (ROE instead of ROA) ─────────────
        if "roe" not in panel.columns:
            _log.warning(
                "[DigitalFinance] Robustness (ROE): 'roe' not available, skipping"
            )
            robustness_checks["alternative_dfi"] = {
                "coefficient": None, "std_error": None,
                "t_stat": None, "p_value": None,
                "note": "ROE not available in panel",
            }
        else:
            try:
                coef, se, t_stat, pval, n_obs, r2 = self._ols_regression(
                    panel, y_var="roe", x_vars=["dfi_index"], with_fe=True
                )
                robustness_checks["alternative_dfi"] = {
                    "coefficient": coef,
                    "std_error": se,
                    "t_stat": t_stat,
                    "p_value": pval,
                }
                _log.info(
                    "[DigitalFinance] Robustness (ROE): coef=%.4f, se=%.4f, p=%.4f, N=%d",
                    coef, se, pval, n_obs,
                )
            except Exception as exc:
                _log.warning("[DigitalFinance] Robustness (ROE) failed: %s", exc)
                robustness_checks["alternative_dfi"] = {
                    "coefficient": None, "std_error": None,
                    "t_stat": None, "p_value": None,
                    "error": str(exc),
                }

        # ── 2. Winsorize at 1% / 99% ──────────────────────────────────────────
        try:
            panel_winsor = self._winsorize_panel(panel, level=0.01)
            if len(panel_winsor) < 20:
                _log.warning(
                    "[DigitalFinance] Robustness (winsorize): insufficient obs after winsorize (%d)",
                    len(panel_winsor),
                )
                robustness_checks["exclude_top_bottom"] = {
                    "coefficient": None, "std_error": None,
                    "t_stat": None, "p_value": None,
                    "note": "Insufficient observations after winsorize",
                }
            else:
                coef, se, t_stat, pval, n_obs, r2 = self._ols_regression(
                    panel_winsor, y_var="roa", x_vars=["dfi_index"], with_fe=True
                )
                robustness_checks["exclude_top_bottom"] = {
                    "coefficient": coef,
                    "std_error": se,
                    "t_stat": t_stat,
                    "p_value": pval,
                }
                _log.info(
                    "[DigitalFinance] Robustness (winsorize): coef=%.4f, se=%.4f, p=%.4f, N=%d",
                    coef, se, pval, n_obs,
                )
        except Exception as exc:
            _log.warning("[DigitalFinance] Robustness (winsorize) failed: %s", exc)
            robustness_checks["exclude_top_bottom"] = {
                "coefficient": None, "std_error": None,
                "t_stat": None, "p_value": None,
                "error": str(exc),
            }

        # ── 3. Lagged DFI index (L1) ──────────────────────────────────────────
        if "dfi_index" not in panel.columns or "firm_id" not in panel.columns or "year" not in panel.columns:
            _log.warning(
                "[DigitalFinance] Robustness (lagged DFI): required index columns missing, skipping"
            )
            robustness_checks["lagged_dfi"] = {
                "coefficient": None, "std_error": None,
                "t_stat": None, "p_value": None,
                "note": "Required columns for lag missing",
            }
        else:
            try:
                panel_lag = panel.sort_values(["firm_id", "year"]).copy()
                panel_lag["dfi_lag"] = panel_lag.groupby("firm_id")["dfi_index"].shift(1)
                panel_lag = panel_lag.dropna(subset=["dfi_lag", "roa"])
                if len(panel_lag) < 20:
                    _log.warning(
                        "[DigitalFinance] Robustness (lagged DFI): only %d obs, skipping",
                        len(panel_lag),
                    )
                    robustness_checks["lagged_dfi"] = {
                        "coefficient": None, "std_error": None,
                        "t_stat": None, "p_value": None,
                        "note": f"Insufficient observations ({len(panel_lag)}) after lag",
                    }
                else:
                    coef, se, t_stat, pval, n_obs, r2 = self._ols_regression(
                        panel_lag, y_var="roa", x_vars=["dfi_lag"], with_fe=True
                    )
                    robustness_checks["lagged_dfi"] = {
                        "coefficient": coef,
                        "std_error": se,
                        "t_stat": t_stat,
                        "p_value": pval,
                    }
                    _log.info(
                        "[DigitalFinance] Robustness (lagged DFI): coef=%.4f, se=%.4f, p=%.4f, N=%d",
                        coef, se, pval, n_obs,
                    )
            except Exception as exc:
                _log.warning("[DigitalFinance] Robustness (lagged DFI) failed: %s", exc)
                robustness_checks["lagged_dfi"] = {
                    "coefficient": None, "std_error": None,
                    "t_stat": None, "p_value": None,
                    "error": str(exc),
                }

        return robustness_checks

    # ── Internal regression helper ───────────────────────────────────────────

    def _ols_regression(
        self,
        panel: pd.DataFrame,
        y_var: str,
        x_vars: list[str],
        with_fe: bool = False,
    ) -> tuple[float | None, float | None, float | None, float | None, int, float | None]:
        """Run OLS/PanelOLS regression and return extracted results.

        Args:
            panel: Panel DataFrame.
            y_var: Name of dependent variable column.
            x_vars: List of independent variable column names.
            with_fe: If True, use PanelOLS with entity effects; else plain OLS.

        Returns:
            Tuple of (coefficient, std_error, t_stat, p_value, n_obs, r_squared).
            Coefficient/std_error/t_stat/p_value refer to the FIRST x_vars element.

        Raises:
            RuntimeError: If regression fitting fails.
        """
        from linearmodels.panel import PanelOLS
        import statsmodels.api as sm

        panel_clean = panel.dropna(subset=[y_var] + x_vars)
        if len(panel_clean) < 5:
            raise RuntimeError(f"Insufficient observations: {len(panel_clean)}")

        if with_fe and "firm_id" in panel_clean.columns and "year" in panel_clean.columns:
            panel_clean = panel_clean.set_index(["firm_id", "year"])
            y = panel_clean[y_var]
            X = panel_clean[x_vars]
            mod = PanelOLS(y, X, entity_effects=True, time_effects=False)
            res = mod.fit(cov_type="clustered", cluster_entity=True)
            idx = 0
        else:
            y = panel_clean[y_var]
            X = panel_clean[x_vars]
            X = sm.add_constant(X)
            mod = sm.OLS(y, X)
            if "firm_id" in panel_clean.columns:
                res = mod.fit(cov_type="cluster", cov_kwds={"groups": panel_clean["firm_id"]})
            else:
                res = mod.fit()
            idx = 1  # skip const

        coef = float(res.params.iloc[idx]) if len(res.params) > idx else None
        se = float(res.std_errors.iloc[idx]) if len(res.std_errors) > idx else None
        t_stat = float(res.tstats.iloc[idx]) if len(res.tstats) > idx else None
        p_value = float(res.pvalues.iloc[idx]) if len(res.pvalues) > idx else None
        r_squared = float(res.rsquared) if hasattr(res, "rsquared") else None
        n_obs = len(panel_clean)

        return coef, se, t_stat, p_value, n_obs, r_squared

    def _winsorize_panel(
        self,
        panel: pd.DataFrame,
        level: float = 0.01,
    ) -> pd.DataFrame:
        """Winsorize numeric columns at the given percentile level.

        Args:
            panel: Input DataFrame.
            level: Winsorization level (default 1% = 0.01). Values at
                ``level`` and ``1 - level`` percentiles are clipped.

        Returns:
            New DataFrame with winsorized numeric columns.
        """
        result = panel.copy()
        numeric_cols = result.select_dtypes(include=["float64", "float32", "int64"]).columns
        for col in numeric_cols:
            lower = result[col].quantile(level)
            upper = result[col].quantile(1 - level)
            result[col] = result[col].clip(lower=lower, upper=upper)
        return result

    def format_tables(self, reg_results: dict[str, Any]) -> dict[str, str]:
        """Format regression results into LaTeX tables.

        Args:
            reg_results: Results from run_regressions.

        Returns:
            Dictionary mapping table names to LaTeX strings.
        """
        tables = {}

        tables["main_table"] = self._format_main_table(reg_results.get("main_results", []))
        tables["heterogeneity_table"] = self._format_heterogeneity_table(
            reg_results.get("heterogeneity_results", {})
        )
        tables["robustness_table"] = self._format_robustness_table(
            reg_results.get("robustness_results", {})
        )

        return tables

    def _format_main_table(self, main_results: list[dict[str, Any]]) -> str:
        """Format main regression results table."""
        tbl = "\\begin{table}[htbp]\n"
        tbl += "  \\centering\n"
        tbl += "  \\caption{Digital Finance and Firm Performance}\n"
        tbl += "  \\label{tab:digital_finance_main}\n"
        tbl += "  \\begin{tabular}{l" + "c" * len(main_results) + "}\n"
        tbl += "    \\hline\n"
        tbl += "    \\hline\n"
        tbl += "    Variable & " + " & ".join([r["spec"] for r in main_results]) + " \\\\\n"
        tbl += "    \\hline\n"
        tbl += "    DFI Index & " + " & ".join([_safe_fmt(r["coefficient"]) for r in main_results]) + " \\\\\n"
        tbl += "                & (" + ") & (".join([_safe_fmt(r["t_stat"], decimals=2) for r in main_results]) + ") \\\\\n"
        tbl += "    \\hline\n"
        tbl += "    Firm Controls & " + " & ".join(["Yes" if r["with_controls"] else "No" for r in main_results]) + " \\\\\n"
        tbl += "    Firm FE & " + " & ".join(["Yes" if r["with_fixed_effects"] else "No" for r in main_results]) + " \\\\\n"
        tbl += "    Year FE & Yes & Yes & Yes \\\\\n"
        tbl += "    \\hline\n"
        tbl += "    $N$ & " + " & ".join([f"{r['n_obs']}" for r in main_results]) + " \\\\\n"
        tbl += "    $R^2$ & " + " & ".join([_safe_fmt(r["r_squared"], decimals=3) for r in main_results]) + " \\\\\n"
        tbl += "    \\hline\n"
        tbl += "    \\hline\n"
        tbl += "  \\end{tabular}\n"
        tbl += "\\end{table}"
        return tbl

    def _format_heterogeneity_table(
        self,
        het_results: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Format heterogeneity analysis table."""
        tbl = "\\begin{table}[htbp]\n"
        tbl += "  \\centering\n"
        tbl += "  \\caption{Heterogeneity Analysis}\n"
        tbl += "  \\label{tab:digital_finance_het}\n"
        tbl += "  \\begin{tabular}{lcc}\n"
        tbl += "    \\hline\n"
        tbl += "    \\hline\n"
        tbl += "    Variable & (1) & (2) \\\\\n"
        tbl += "    \\hline\n"

        for group_name, groups in het_results.items():
            display_name = group_name.replace("_", " ").title()
            tbl += "    \\textit{" + display_name + "} & & \\\\\n"
            for g in groups:
                tbl += "    " + g["group"] + " & " + _safe_fmt(g["coefficient"]) + " & " + "(" + _safe_fmt(g["t_stat"], decimals=2) + ") \\\\\n"

        tbl += "    \\hline\n"
        tbl += "    Controls & Yes & Yes \\\\\n"
        tbl += "    Fixed Effects & Yes & Yes \\\\\n"
        tbl += "    \\hline\n"
        tbl += "  \\end{tabular}\n"
        tbl += "\\end{table}"
        return tbl

    def _format_robustness_table(
        self,
        robust_results: dict[str, dict[str, Any]],
    ) -> str:
        """Format robustness checks table."""
        tbl = "\\begin{table}[htbp]\n"
        tbl += "  \\centering\n"
        tbl += "  \\caption{Robustness Checks}\n"
        tbl += "  \\label{tab:digital_finance_robust}\n"
        tbl += "  \\begin{tabular}{lcc}\n"
        tbl += "    \\hline\n"
        tbl += "    \\hline\n"
        tbl += "    Robustness Check & Coefficient & $t$-stat \\\\\n"
        tbl += "    \\hline\n"

        check_names = {
            "alternative_dfi": "Alternative DFI Index",
            "exclude_top_bottom": "Exclude Top/Bottom 1\\%",
            "lagged_dfi": "Lagged DFI (L1)",
        }

        for check_id, result in robust_results.items():
            display_name = check_names.get(check_id, check_id)
            tbl += "    " + display_name + " & " + _safe_fmt(result["coefficient"]) + " & " + "(" + _safe_fmt(result["t_stat"], decimals=2) + ") \\\\\n"

        tbl += "    \\hline\n"
        tbl += "    Controls & Yes & \\\\\n"
        tbl += "    Fixed Effects & Yes & \\\\\n"
        tbl += "    \\hline\n"
        tbl += "  \\end{tabular}\n"
        tbl += "\\end{table}"
        return tbl

    def get_figure_plan(self) -> list[dict[str, Any]]:
        """Get plan for figures to generate.

        Returns:
            List of figure specification dictionaries.
        """
        figures = [
            {
                "figure_id": "fig_dfi_trend",
                "title": "Digital Finance Index Trend by Province",
                "generation_method": "matplotlib",
                "chart_type": "line",
                "description": "Time series of DFI index by province, 2013-2023",
                "variables": ["year", "dfi_index", "province"],
                "output_format": "pdf",
            },
            {
                "figure_id": "fig_scatter_dfi_roa",
                "title": "DFI Index and Firm ROA Scatter Plot",
                "generation_method": "matplotlib",
                "chart_type": "scatter",
                "description": "Scatter plot with regression line showing relationship between DFI and ROA",
                "variables": ["dfi_index", "roa"],
                "output_format": "pdf",
            },
            {
                "figure_id": "fig_event_study",
                "title": "Event Study: DFI Expansion and Firm Performance",
                "type": "event_study",
                "description": "Event study plot showing pre/post treatment effects around DFI expansion",
                "variables": ["event_time", "coefficient", "ci_lower", "ci_upper"],
                "output_format": "pdf",
            },
            {
                "figure_id": "fig_heterogeneity",
                "title": "Heterogeneous Effects by Firm Size and Region",
                "type": "bar",
                "description": "Coefficient plot showing differential effects across subgroups",
                "variables": ["group", "coefficient", "conf_int"],
                "output_format": "pdf",
            },
        ]
        return figures


get_registry().register(DigitalFinanceDirection())
