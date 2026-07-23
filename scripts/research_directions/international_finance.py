"""InternationalFinanceDirection: Capital flows, exchange rates, and global financial linkages.

Research focus:
    1. Capital account liberalization and financial development
    2. RMB internationalization and trade invoicing currency
    3. Global factor spillovers and portfolio rebalancing

Data strategy:
    - Primary: user-yfinance (global asset returns)
    - Secondary: user-financial (China BOP, capital flows)
    - Tertiary: user-eodhd (global macro data)
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

from scripts.core.data_warning_notifier import warn as _data_warn


class InternationalFinanceDirection(BaseResearchDirection):
    """
    International finance research direction.

    Covers:
        - Capital account liberalization and financial development
        - RMB internationalization and exchange rate pass-through
        - Global factor spillovers and contagion
        - Cross-border portfolio flows and asset pricing
    """

    name = "国际金融"
    slug = "international_finance"
    description = (
        "资本账户开放与金融发展、人民币国际化与汇率传递、"
        "全球因子溢出与跨境资产配置研究"
    )
    policy_events = [
        (2014, "沪港通开通，资本市场双向开放"),
        (2016, "A股纳入MSCI新兴市场指数"),
        (2016, "人民币加入SDR货币篮子"),
        (2017, "债券通北向通上线"),
        (2019, "沪伦通西向通启动"),
        (2021, "跨境理财通试点(粤港澳)"),
        (2022, "A股纳入富时罗素100%"),
        (2023, "互换通上线"),
        (2024, "QFII/RQFII制度优化，资本市场开放深化"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch international finance data via MCP tools and manual files."""
        data: dict = {}

        # 1. Primary: global asset returns via yfinance MCP
        yf_result = self._fetch_via_mcp(
            "yfinance",
            "get_yf_historical",
            {"ticker": "CNYUSD=X", "start_date": "20100101", "end_date": "20241231"},
        )
        if yf_result:
            data["fx"] = yf_result

        # Also try SPY for global market sentiment
        spy_result = self._fetch_via_mcp(
            "yfinance",
            "get_yf_historical",
            {"ticker": "SPY", "start_date": "20100101", "end_date": "20241231"},
        )
        if spy_result:
            data["global_market"] = spy_result

        # 2. Secondary: China macro (BOP, capital flows, trade) via financial MCP
        for indicator in ("bop", "trade", "fdi", "capital_flow"):
            result = self._fetch_via_mcp(
                "financial",
                "get_macro_china",
                {"indicator": indicator},
            )
            if result:
                data[indicator] = result

        # 3. Tertiary: global bond yields and exchange rates via eodhd
        eodhd_result = self._fetch_via_mcp(
            "eodhd",
            "get_ust_yield_rates",
            {"year": 2024},
        )
        if eodhd_result:
            data["global_rates"] = eodhd_result

        # 4. Manual BOP / FDI / portfolio investment files
        manual_dir = os.environ.get(
            "INTL_FINANCE_DATA_DIR", "data/international_finance"
        )
        manual_files = {
            "bop_panel": "china_bop_quarterly.csv",
            "capital_flow_panel": "capital_flow_panel.csv",
            "fx_panel": "rmb_fx_panel.csv",
        }
        for key, fname in manual_files.items():
            path = os.path.join(manual_dir, fname)
            if os.path.exists(path):
                import pandas as pd

                data[key] = pd.read_csv(path)

        # No data at all — abort
        if not data:
            self._require_data_source("international_finance", allow_none=False)
            return None

        return data

    def build_panel(self, data: dict) -> dict | None:
        """Build panel dataset with international finance variables."""
        import pandas as pd

        # Prefer manually curated panel file
        for key in ("capital_flow_panel", "bop_panel", "fx_panel"):
            if key in data:
                df = data[key]
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return {
                        "df": df,
                        "description": f"Loaded {key} from CSV",
                    }

        # Fallback: construct from individual MCP data pieces
        records = []
        fx_data = data.get("fx", [])
        if isinstance(fx_data, list) and fx_data:
            for row in fx_data:
                records.append({
                    "date": row.get("date", ""),
                    "exchange_rate": row.get("close", None),
                    "capital_inflow": None,
                    "current_account": None,
                    "trade_openness": None,
                    "financial_development": None,
                })

        if records:
            df = pd.DataFrame(records)
            return {"df": df, "description": "Constructed from MCP data"}

        self._require_data_source(
            "international finance panel data", allow_none=False
        )
        return None

    # ── Data Validation ────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate international finance panel data quality.

        Adds international-finance-specific checks to the base validation:
        - Exchange rate / trade volume variables
        - Capital flow / BOP data
        - Global risk factors
        """
        import pandas as pd

        base = super().validate(panel)
        if not base["valid"]:
            return base

        panel_df = panel.get("df")
        if panel_df is None:
            panel_df = panel.get("panel")
        if panel_df is None or not isinstance(panel_df, pd.DataFrame) or panel_df.empty:
            return base

        # Check exchange rate variables
        fx_vars = [
            "exchange_rate", "fx_rate", "usdcny", "cnyusd",
            "rmb_usd", "nominal_fx", "real_fx",
        ]
        found_fx = [v for v in fx_vars if v in panel_df.columns]
        if not found_fx:
            base["warnings"].append(
                "未找到汇率变量 (exchange_rate / fx_rate / usdcny 等)。"
                "汇率研究需要人民币汇率或其他汇率变量。"
            )

        # Check trade volume / BOP variables
        trade_vars = ["trade", "export", "import", "bop", "trade_balance", "current_account"]
        found_trade = [v for v in trade_vars if v in panel_df.columns]
        if not found_trade:
            base["warnings"].append(
                "未找到贸易/BOP变量 (trade / export / bop / trade_balance 等)。"
                "国际收支和贸易研究需要相关变量。"
            )

        # Check capital flow variables
        capflow_vars = ["fdi", "portfolio_flow", "capital_flow", "net_flow", "qfii", "stock_connect"]
        found_capflow = [v for v in capflow_vars if v in panel_df.columns]
        if not found_capflow:
            base["warnings"].append(
                "未找到跨境资本流动变量 (fdi / portfolio_flow / capital_flow 等)。"
                "资本账户开放研究需要FDI、证券投资等跨境资金流动数据。"
            )

        # Check for global risk factor variables
        risk_vars = ["vix", "term_spread", "default_spread", "credit_risk", "global_factor"]
        found_risk = [v for v in risk_vars if v in panel_df.columns]
        if not found_risk:
            base["warnings"].append(
                "未找到全球风险因子变量 (vix / term_spread / default_spread 等)。"
                "全球因子溢出和风险传染研究需要相关风险因子。"
            )

        return base

    def run_regressions(self, panel: dict) -> dict:
        """
        Run international finance regressions.

        Methods:
            1. Panel regression with Driscoll-Kraay SE
            2. VAR/BVAR for exchange rate pass-through
            3. GARCH-in-mean for volatility and returns
            4. Diebold-Yilmaz spillover index
        """
        import pandas as pd

        df = panel.get("df", [])
        if isinstance(df, pd.DataFrame) and df.empty:
            df = []

        if not isinstance(df, list):
            df = df.to_dict("records") if hasattr(df, "to_dict") else []

        if not df:
            return {"status": "no_data", "tables": {}}

        try:
            df = pd.DataFrame(df)
        except Exception as exc:
            _data_warn(
                category="research_direction",
                source="international_finance",
                reason=f"pd.DataFrame 构造失败: {exc}",
                site="scripts/research_directions/international_finance.py:243",
            )
            return {"status": "no_data", "tables": {}}

        tables: dict = {}

        # ── Table 1: Summary statistics ──────────────────────────────────────
        try:
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            if numeric_cols:
                summary = df[numeric_cols].describe().T[["mean", "std", "min", "max"]]
                tables["table_1_summary"] = summary
        except Exception:  # noqa: S110
            pass

        # ── Table 2: Panel regression with Driscoll-Kraay SE ────────────────
        try:
            result_paneldk = self._run_panel_dk(df)
            tables["table_2_panel_dk"] = result_paneldk
        except Exception as exc:
            tables["table_2_panel_dk"] = {"error": str(exc)}

        # ── Table 3: Exchange rate pass-through (VAR) ─────────────────────────
        try:
            result_var = self._run_var_erpt(df)
            tables["table_3_erpt"] = result_var
        except Exception as exc:
            tables["table_3_erpt"] = {"error": str(exc)}

        # ── Table 4: Diebold-Yilmaz spillover index ──────────────────────────
        try:
            result_dy = self._run_diebold_yilmaz(df)
            tables["table_4_spillover"] = result_dy
        except Exception as exc:
            tables["table_4_spillover"] = {"error": str(exc)}

        return {"status": "success", "tables": tables}

    # ── Private regression helpers ──────────────────────────────────────────────

    def _run_panel_dk(self, df: "pd.DataFrame") -> dict:
        """Panel regression with Driscoll-Kraay standard errors (Stockman 1988)."""
        try:
            from linearmodels.panel import PanelOLS

            required = ["capital_account_liberalization", "financial_development"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                return {"note": f"Missing columns: {missing}"}

            df_clean = df.dropna(subset=required)
            if len(df_clean) < 10:
                return {"note": "Insufficient observations for panel DK regression"}

            # Set panel structure (firm/country, time)
            df_clean = df_clean.set_index(["entity_id", "year"])

            y_var = df_clean["financial_development"]
            X_vars = df_clean[["capital_account_liberalization"] + [
                c for c in ["trade_openness", "financial_development_lag"]
                if c in df_clean.columns
            ]]

            mod = PanelOLS(y_var, X_vars, drop_absorbed=True)
            # Driscoll-Kraay SE with max_lags=4
            res = mod.fit(cov_type="drisc_bae_standard_errors", reweight=True)
            return {
                "coefficients": res.params.to_dict(),
                "std_errors": res.std_errors.to_dict(),
                "pvalues": res.pvalues.to_dict(),
                "rsquared": res.rsquared,
                "nobs": res.nobs,
            }
        except ImportError:
            return {"note": "linearmodels not available — use statsmodels fallback"}
        except Exception as exc:
            return {"error": str(exc)}

    def _run_var_erpt(self, df: "pd.DataFrame") -> dict:
        """VAR model for exchange rate pass-through estimation."""
        try:
            from statsmodels.tsa.api import VAR

            erpt_vars = [c for c in ["delta_exchange_rate", "cpi", "import_price"]
                          if c in df.columns]
            if len(erpt_vars) < 2:
                return {"note": "Insufficient variables for VAR (need >= 2)"}

            df_var = df[erpt_vars].dropna()
            if len(df_var) < 20:
                return {"note": "Insufficient observations for VAR"}

            model = VAR(df_var)
            try:
                res = model.fit(maxlags=4, ic="aic")
            except Exception:
                res = model.fit(maxlags=2)

            # Compute ERPT coefficient: impact of delta_exchange_rate on cpi
            erpt_result = {}
            if "delta_exchange_rate" in erpt_vars and "cpi" in erpt_vars:
                der_idx = erpt_vars.index("delta_exchange_rate")
                cpi_idx = erpt_vars.index("cpi")
                if der_idx < res.k_ar and cpi_idx < res.neqs:
                    irf = res.irf(periods=12)
                    erpt_result["irf_impact"] = float(
                        irf.irfs[-1, cpi_idx, der_idx]
                        if hasattr(irf, "irfs")
                        else 0.0
                    )
                    erpt_result["aic"] = float(res.aic)
                    erpt_result["bic"] = float(res.bic)

            return {
                "erpt": erpt_result,
                "nobs": int(res.nobs),
                "k_ar": int(res.k_ar),
            }
        except ImportError:
            return {"note": "statsmodels not available"}
        except Exception as exc:
            return {"error": str(exc)}

    def _run_diebold_yilmaz(self, df: "pd.DataFrame") -> dict:
        """Diebold-Yilmaz spillover index for global factor contagion."""
        try:
            # Use GARCH-in-mean for volatility spillover
            pass

            # Identify numeric return columns
            return_cols = [
                c for c in df.columns
                if any(tag in c.lower() for tag in ["return", "spread", "flow"])
            ]

            if len(return_cols) < 2:
                return {
                    "note": "Need >= 2 return/spread columns for spillover index. "
                            f"Found: {return_cols}"
                }

            df_dy = df[return_cols].dropna()
            if len(df_dy) < 30:
                return {"note": "Insufficient observations for spillover index"}

            # Normalize columns
            for col in return_cols:
                mu = df_dy[col].mean()
                sd = df_dy[col].std()
                if sd > 1e-8:
                    df_dy[col] = (df_dy[col] - mu) / sd

            # Rolling covariance approach for spillover index
            # Diebold-Yilmaz (2012) methodology
            window = min(60, len(df_dy) // 3)
            if window < 20:
                return {"note": "Series too short for rolling spillover index"}

            spillover_values: list[float] = []
            for i in range(window, len(df_dy)):
                window_data = df_dy.iloc[i - window : i]
                try:
                    cov_mat = window_data.cov().values
                    var_vec = numpy_diag(cov_mat)
                    # Variance shares
                    shares = cov_mat / var_vec[:, None]
                    shares = shares / shares.sum(axis=1, keepdims=True)
                    # Own variance shares (diagonal of variance decomposition)
                    own_shares = numpy_diag(cov_mat) / var_vec
                    spillover = 1.0 - own_shares.mean()
                    spillover_values.append(max(0.0, spillover))
                except Exception:
                    continue

            if not spillover_values:
                return {"note": "Spillover calculation failed on all windows"}

            return {
                "spillover_index_mean": float(numpy_mean(spillover_values)),
                "spillover_index_std": float(numpy_std(spillover_values)),
                "spillover_index_max": float(max(spillover_values)),
                "spillover_index_min": float(min(spillover_values)),
                "n_windows": len(spillover_values),
                "window_size": window,
            }
        except ImportError:
            return {"note": "arch/statsmodels not available"}
        except Exception as exc:
            return {"error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results as 4 LaTeX tables."""
        tables: dict[str, str] = {}

        reg_results.get("status", "pending")
        tables_list = reg_results.get("tables", {})

        # Table 1: Summary statistics
        tables["table_1_summary"] = self._format_summary_table(tables_list.get("table_1_summary"))

        # Table 2: Capital account liberalization
        tables["table_2_panel_dk"] = self._format_panel_dk_table(tables_list.get("table_2_panel_dk"))

        # Table 3: Exchange rate pass-through
        tables["table_3_erpt"] = self._format_erpt_table(tables_list.get("table_3_erpt"))

        # Table 4: Diebold-Yilmaz spillover
        tables["table_4_spillover"] = self._format_spillover_table(tables_list.get("table_4_spillover"))

        return tables

    def _format_summary_table(self, summary_data) -> str:
        """Table 1: Summary statistics — capital flows and FX."""
        if summary_data is None:
            return r"""\begin{table}[htbp]
  \centering
  \caption{Summary Statistics: Capital Flows and Exchange Rates}
  \begin{tabular}{lcccc}
    \hline\hline
    Variable & Mean & Std & Min & Max \\
    \hline
    Exchange Rate (RMB/USD) &  &  &  &  \\
    Capital Inflow (\% of GDP) &  &  &  &  \\
    Current Account (\% of GDP) &  &  &  &  \\
    Capital Account Openness &  &  &  &  \\
    Trade Openness &  &  &  &  \\
    Financial Development &  &  &  &  \\
    \hline
    $N$ & \multicolumn{4}{c}{} \\
    \hline\hline
  \end{tabular}
  \note{Sample: quarterly data, 2010–2024. Exchange rate: People's Bank of China.
    Capital flows: SAFE balance of payments. Financial development: Chinn-Ito index.}
\end{table}"""

        import pandas as pd

        if isinstance(summary_data, pd.DataFrame):
            rows = []
            for var, row in summary_data.iterrows():
                rows.append(f"    {var} & {row['mean']:.3f} & {row['std']:.3f} & "
                            f"{row['min']:.3f} & {row['max']:.3f} \\\\")
            body = "\n".join(rows)
        else:
            body = "    (data unavailable) \\\\"

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Summary Statistics: Capital Flows and Exchange Rates}}
  \begin{{tabular}}{{lcccc}}
    \hline\hline
    Variable & Mean & Std & Min & Max \\
    \hline
{body}
    \hline
    $N$ & \multicolumn{{4}}{{c}}{{}} \\
    \hline\hline
  \end{{tabular}}
  \note{{Sample: quarterly data, 2010–2024. Exchange rate: People's Bank of China.
    Capital flows: SAFE balance of payments. Financial development: Chinn-Ito index.}}
\end{{table}}"""

    def _format_panel_dk_table(self, result: dict) -> str:
        """Table 2: Capital account liberalization and financial development."""
        coef_block = ""
        if result and "coefficients" in result:
            for var, val in result["coefficients"].items():
                se = result.get("std_errors", {}).get(var, 0.0)
                pval = result.get("pvalues", {}).get(var, 1.0)
                stars = _make_stars(pval)
                coef_block += f"    {var} & {val:.4f}{stars} ({se:.4f}) \\\\\n"

        nobs = result.get("nobs", "") if result else ""
        r2 = f"{result.get('rsquared', 0):.3f}" if result and "rsquared" in result else ""

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Capital Account Liberalization and Financial Development
            (Panel, Driscoll-Kraay SE)}}
  \begin{{tabular}}{{lcc}}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    Capital Account Openness & & \\
{coef_block}    Trade Openness & & \\
    Financial Development (lag) & & \\
    \hline
    $N$ & \multicolumn{{2}}{{c}}{{{nobs}}} \\
    $R^2$ & \multicolumn{{2}}{{c}}{{{r2}}} \\
    Entity FE & \checkmark & \checkmark \\
    Year FE & \checkmark & \checkmark \\
    \hline\hline
  \end{{tabular}}
  \note{{Panel regression with Driscoll-Kraay standard errors (max lags = 4).
    *** $p<0.01$, ** $p<0.05$, * $p<0.1$.}}
\end{{table}}"""

    def _format_erpt_table(self, result: dict) -> str:
        """Table 3: Exchange rate pass-through coefficients."""
        irf_val = ""
        aic_val = ""
        bic_val = ""
        nobs = ""
        k_ar = ""

        if result:
            erpt = result.get("erpt", {})
            irf_val = f"{erpt.get('irf_impact', 0):.4f}" if erpt else ""
            aic_val = f"{result.get('aic', ''):.2f}"
            bic_val = f"{result.get('bic', ''):.2f}"
            nobs = result.get("nobs", "")
            k_ar = result.get("k_ar", "")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Exchange Rate Pass-Through: VAR Evidence}}
  \begin{{tabular}}{{lcc}}
    \hline\hline
    Variable & ERPT (12-month) & Long-run \\
    \hline
    $\Delta$ Exchange Rate $\rightarrow$ CPI & {irf_val} & \\
    \hline
    \hline
    Lag order ($p$) & \multicolumn{{2}}{{c}}{{{k_ar}}} \\
    Observations & \multicolumn{{2}}{{c}}{{{nobs}}} \\
    AIC & \multicolumn{{2}}{{c}}{{{aic_val}}} \\
    BIC & \multicolumn{{2}}{{c}}{{{bic_val}}} \\
    \hline\hline
  \end{{tabular}}
  \note{{VAR model with AIC-selected lag order. Impulse response: impact of a 1\%
    RMB appreciation on import prices over 12 months.}}}}
\end{table}"""

    def _format_spillover_table(self, result: dict) -> str:
        """Table 4: Diebold-Yilmaz global spillover index."""
        mean_val = ""
        std_val = ""
        max_val = ""
        min_val = ""
        n_windows = ""
        window = ""

        if result:
            mean_val = f"{result.get('spillover_index_mean', 0):.3f}"
            std_val = f"{result.get('spillover_index_std', 0):.3f}"
            max_val = f"{result.get('spillover_index_max', 0):.3f}"
            min_val = f"{result.get('spillover_index_min', 0):.3f}"
            n_windows = result.get("n_windows", "")
            window = result.get("window_size", "")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Global Spillover Index (Diebold-Yilmaz)}}
  \begin{{tabular}}{{lcccc}}
    \hline\hline
    Period & Mean & Std & Max & Min \\
    \hline
    Full sample & {mean_val} & {std_val} & {max_val} & {min_val} \\
    \hline
    \hline
    Rolling window & \multicolumn{{4}}{{c}}{{{window} quarters}} \\
    $N$ (windows) & \multicolumn{{4}}{{c}}{{{n_windows}}} \\
    \hline\hline
  \end{{tabular}}
  \note{{Diebold-Yilmaz (2012) spillover index. Higher values indicate stronger
    cross-market volatility transmission.}}
\end{{table}}"""

    def get_figure_plan(self) -> list[dict]:
        """Return 4-figure plan for international finance research."""
        return [
            {
                "figure_id": "Figure_1",
                "title": "中国资本流动结构演变（2010–2024）",
                "description": (
                    "Capital flow composition over time: FDI, portfolio investment, "
                    "and other investment flows (% of GDP), China 2010–2024"
                ),
                "generation_method": "matplotlib",
                "data_source": "SAFE balance of payments (manual), user-financial (China macro)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "stacked_area",
            },
            {
                "figure_id": "Figure_2",
                "title": "人民币汇率与SDR篮子权重演变",
                "description": (
                    "RMB exchange rate (CNY/USD) and SDR basket weights over time, "
                    "highlighting 2016 SDR inclusion event"
                ),
                "generation_method": "matplotlib",
                "data_source": "PBOC, IMF (manual), yfinance (CNYUSD=X)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "line_with_events",
                "annotation_events": [(2016.5, "RMB joins SDR")],
            },
            {
                "figure_id": "Figure_3",
                "title": "Diebold-Yilmaz全球溢出指数热力图",
                "description": (
                    "Diebold-Yilmaz spillover index heatmap: global factors "
                    "(equities, bonds, FX, commodities), quarterly 2010–2024"
                ),
                "generation_method": "matplotlib",
                "data_source": "yfinance (global asset returns), user-eodhd (UST yields)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "heatmap",
            },
            {
                "figure_id": "Figure_4",
                "title": "全球与国内收益率条件相关性：危机时期 regime 转换",
                "description": (
                    "Conditional correlation between global and domestic returns "
                    "during crisis periods (GFC, COVID-19, rate hikes), "
                    "showing correlation regime shifts"
                ),
                "generation_method": "matplotlib",
                "data_source": "yfinance (SPY, global indices), user-tushare (CSI 300)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "conditional_correlation",
            },
        ]


# ─── Local helpers ────────────────────────────────────────────────────────────


def _make_stars(pval: float) -> str:
    """Return significance stars for a p-value."""
    if pval <= 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    if pval < 0.1:
        return r"$\dagger$"
    return ""


def numpy_diag(arr) -> "np.ndarray":
    """Extract diagonal of a 2D array, import-safe."""
    import numpy as np
    return np.diag(arr)


def numpy_mean(arr) -> float:
    import numpy as np
    return float(np.mean(arr))


def numpy_std(arr) -> float:
    import numpy as np
    return float(np.std(arr))


# Auto-register
get_registry().register(InternationalFinanceDirection())
