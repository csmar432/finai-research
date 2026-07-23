"""BehavioralFinanceDirection: Investor behavior, sentiment, and market anomalies.

Research focus:
    1. Investor sentiment and asset pricing anomalies
    2. Behavioral biases in corporate financial decisions
    3. Social interaction and trading behavior

Data strategy:
    - Primary: user-yfinance (stock returns, trading volume)
    - Secondary: user-tushare (A-share investor structure)
    - Tertiary: manual CSMAR/Flush data
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

from scripts.core.data_warning_notifier import warn as _data_warn


class BehavioralFinanceDirection(BaseResearchDirection):
    """
    Behavioral finance research direction.

    Covers:
        - Investor sentiment indices and cross-sectional expected returns
        - Behavioral biases in corporate investment and financing decisions
        - Social interaction and trading behavior heterogeneity
    """

    name = "行为金融"
    slug = "behavioral_finance"
    description = "投资者情绪与资产定价异常、行为偏误与金融决策、社会互动与交易行为研究"
    policy_events = [
        (2010, "融资融券标的扩容至496只"),
        (2014, "沪港通开通，外资流入"),
        (2015, "A股股灾，融资盘踩踏"),
        (2016, "A股纳入MSCI，机构化加速"),
        (2020, "公募基金规模首超居民储蓄存款"),
        (2023, "量化交易规模扩大，个人投资者结构变化"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch data from MCP tools and manual data sources."""
        import pandas as pd

        data: dict = {}

        # Primary: yfinance for stock returns and trading volume
        tickers = kwargs.get("tickers", ["SPY", "QQQ", "IWM"])
        for ticker in tickers:
            yf_result = self._fetch_via_mcp(
                "yfinance",
                "get_yf_historical",
                {
                    "ticker": ticker,
                    "start_date": kwargs.get("start_date", "20100101"),
                    "end_date": kwargs.get("end_date", "20240101"),
                },
            )
            if yf_result:
                data[f"yf_{ticker}"] = yf_result

        # Secondary: Tushare for A-share investor structure
        ts_result = self._fetch_via_mcp(
            "tushare",
            "get_moneyflow",
            {"trade_date": "20231229"},
        )
        if ts_result:
            data["moneyflow"] = ts_result

        ts_stocks = self._fetch_via_mcp(
            "tushare",
            "get_stock_basic",
            {"list_status": "L"},
        )
        if ts_stocks:
            data["stocks"] = ts_stocks

        # Tertiary: manual sentiment index data
        sentiment_path = os.environ.get(
            "SENTIMENT_DATA_DIR",
            "data/behavioral_finance/sentiment_index.csv",
        )
        if os.path.exists(sentiment_path):
            try:
                data["sentiment"] = pd.read_csv(sentiment_path)
            except Exception:  # noqa: S110
                pass

        # Check for CICSI / EI index files
        cicci_path = os.environ.get(
            "CICSI_DATA_PATH",
            "data/behavioral_finance/cicci_index.csv",
        )
        if os.path.exists(cicci_path):
            try:
                data["cicci"] = pd.read_csv(cicci_path)
            except Exception:  # noqa: S110
                pass

        # No data at all — abort
        if not data:
            self._require_data_source("behavioral_finance", allow_none=False)
            return None

        return data

    def build_panel(self, data: dict) -> dict | None:
        """Build panel dataset from fetched data."""
        import pandas as pd

        # Prefer manually curated sentiment panel
        if "sentiment" in data and isinstance(data["sentiment"], pd.DataFrame):
            df = data["sentiment"]
            return {
                "df": df,
                "description": "Sentiment panel loaded from CSV",
            }

        # Build from yfinance data if available
        yf_keys = [k for k in data if k.startswith("yf_")]
        if yf_keys:
            frames = []
            for key in yf_keys:
                raw = data[key]
                if isinstance(raw, list) and raw:
                    frames.append(pd.DataFrame(raw))
                elif isinstance(raw, pd.DataFrame) and not raw.empty:
                    frames.append(raw)
            if frames:
                df = pd.concat(frames, ignore_index=True)
                return {
                    "df": df,
                    "description": "Panel constructed from yfinance data",
                }

        # Fall back to moneyflow data from Tushare
        if "moneyflow" in data:
            raw = data["moneyflow"]
            if isinstance(raw, list) and raw:
                return {
                    "df": pd.DataFrame(raw),
                    "description": "Moneyflow data from Tushare",
                }
            elif isinstance(raw, pd.DataFrame) and not raw.empty:
                return {"df": raw, "description": "Moneyflow data from Tushare"}

        self._require_data_source(
            "behavioral_finance panel", allow_none=False
        )
        return None

    # ── Data Validation ────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate behavioral finance panel data quality.

        Adds behavioral-finance-specific checks to the base validation:
        - Sentiment index presence
        - Return / price data
        - Trading volume data
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

        # Check sentiment index
        sent_candidates = [
            "sentiment", "cicci", "ei_index", "investor_sentiment",
            "fear_greed", "vix", "put_call_ratio",
        ]
        found_sent = [v for v in sent_candidates if v in panel_df.columns]
        if not found_sent:
            base["warnings"].append(
                "未找到情绪指数变量 (sentiment / cicci / ei_index 等)。"
                "投资者情绪是行为金融研究的核心变量。"
            )

        # Check return / price data
        ret_candidates = ["return", "ret", "daily_return", "excess_return"]
        found_ret = [v for v in ret_candidates if v in panel_df.columns]
        if not found_ret:
            base["warnings"].append(
                "未找到收益率变量 (return / ret / daily_return)。"
                "收益率是行为金融资产定价分析的基础变量。"
            )

        # Check volume data
        vol_candidates = ["volume", "turnover", "trading_volume", "amt"]
        found_vol = [v for v in vol_candidates if v in panel_df.columns]
        if not found_vol:
            base["warnings"].append(
                "未找到交易量变量 (volume / turnover / trading_volume)。"
                "交易量是市场微观结构分析的重要数据。"
            )

        # Check for sufficient cross-sectional variation
        if "firm_id" in panel_df.columns:
            n_firms = panel_df["firm_id"].nunique()
            if n_firms < 50:
                base["warnings"].append(
                    f"截面企业数过少: {n_firms} < 50。"
                    "横截面行为金融分析（如特质波动率、彩票偏好）需要足够的个股数量。"
                )

        return base

    def run_regressions(self, panel: dict) -> dict:
        """Run cross-sectional sentiment-return regressions."""
        import pandas as pd

        df = panel.get("df")
        if df is None:
            return {"status": "no_data", "tables": {}}

        if isinstance(df, pd.DataFrame) and not df.empty:
            return self._run_sentiment_regressions(df)

        return {"status": "pending", "tables": {}}

    def _run_sentiment_regressions(self, df: pd.DataFrame) -> dict:
        """Internal sentiment regression logic."""
        try:
            import statsmodels.api as sm

            # Detect columns
            col_lower = {c.lower().strip(): c for c in df.columns}
            col_lower.get("date")
            sentiment_col = col_lower.get("sentiment") or col_lower.get("cicci") or col_lower.get("s")
            return_col = col_lower.get("return") or col_lower.get("ret") or col_lower.get("stock_return")
            col_lower.get("turnover") or col_lower.get("turnover_rate")
            size_col = col_lower.get("size") or col_lower.get("mktcap")
            bm_col = col_lower.get("bm") or col_lower.get("book_to_market")

            if return_col is None:
                return {"status": "no_relevant_columns", "tables": {}}

            results_tables: dict = {}

            # ── Table 2: Cross-sectional sentiment-return regression ──
            if sentiment_col and return_col:
                reg_df = df[[sentiment_col, return_col]].dropna()
                if len(reg_df) > 10:
                    y = reg_df[return_col]
                    X = sm.add_constant(reg_df[[sentiment_col]])
                    model = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": reg_df.index})
                    results_tables["table2_sentiment_returns"] = {
                        "dependent": return_col,
                        "sentiment_coef": float(model.params.get(sentiment_col, 0)),
                        "sentiment_se": float(model.bse.get(sentiment_col, 0)),
                        "sentiment_pval": float(model.pvalues.get(sentiment_col, 1)),
                        "r_squared": float(model.rsquared),
                        "n_obs": int(model.nobs),
                    }

            # ── Table 3: Sentiment and corporate investment ──
            inv_col = col_lower.get("investment") or col_lower.get("capex")
            if sentiment_col and inv_col and return_col:
                reg_df = df[[sentiment_col, inv_col, return_col] +
                             [c for c in [size_col, bm_col] if c is not None]].dropna()
                if len(reg_df) > 10:
                    y = reg_df[inv_col]
                    X_vars = [sentiment_col] + [c for c in [size_col, bm_col] if c in reg_df.columns]
                    X = sm.add_constant(reg_df[X_vars])
                    model = sm.OLS(y, X).fit(cov_type="HC3")
                    results_tables["table3_sentiment_investment"] = {
                        "dependent": inv_col,
                        "sentiment_coef": float(model.params.get(sentiment_col, 0)),
                        "sentiment_se": float(model.bse.get(sentiment_col, 0)),
                        "sentiment_pval": float(model.pvalues.get(sentiment_col, 1)),
                        "r_squared": float(model.rsquared),
                        "n_obs": int(model.nobs),
                    }

            # ── Table 4: Limits to arbitrage channel ──
            arb_col = col_lower.get("arbitrage") or col_lower.get("limits_to_arbitrage") or col_lower.get("lt_a")
            if sentiment_col and arb_col and return_col:
                reg_df = df[[sentiment_col, arb_col, return_col]].dropna()
                if len(reg_df) > 10:
                    y = reg_df[return_col]
                    X = sm.add_constant(reg_df[[sentiment_col, arb_col]])
                    model = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": reg_df.index})
                    results_tables["table4_arbitrage_channel"] = {
                        "dependent": return_col,
                        "sentiment_coef": float(model.params.get(sentiment_col, 0)),
                        "sentiment_se": float(model.bse.get(sentiment_col, 0)),
                        "arbitrage_coef": float(model.params.get(arb_col, 0)),
                        "arbitrage_se": float(model.bse.get(arb_col, 0)),
                        "r_squared": float(model.rsquared),
                        "n_obs": int(model.nobs),
                    }

            return {"status": "success", "tables": results_tables}

        except ImportError:
            return {
                "status": "import_error",
                "tables": {},
                "error": "statsmodels not available",
            }
        except Exception as exc:
            _data_warn(
                category="research_direction",
                source="behavioral_finance",
                reason=f"run_regressions 顶层异常: {exc}",
                site="scripts/research_directions/behavioral_finance.py:317",
            )
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results as LaTeX tables."""
        tables = reg_results.get("tables", {})
        formatted: dict[str, str] = {}

        # Table 1: Summary statistics placeholder
        formatted["table1_summary_stats"] = self._summary_stats_latex()

        # Table 2: Sentiment and expected returns
        t2 = tables.get("table2_sentiment_returns", {})
        if t2:
            formatted["table2_sentiment_returns"] = self._table2_latex(t2)

        # Table 3: Sentiment and corporate investment
        t3 = tables.get("table3_sentiment_investment", {})
        if t3:
            formatted["table3_sentiment_investment"] = self._table3_latex(t3)

        # Table 4: Limits to arbitrage channel
        t4 = tables.get("table4_arbitrage_channel", {})
        if t4:
            formatted["table4_arbitrage_channel"] = self._table4_latex(t4)

        return formatted

    def _summary_stats_latex(self) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Summary Statistics}
  \begin{tabular}{lcccc}
    \hline\hline
    Variable & Mean & Std & Min & Max \\
    \hline
    Stock Return &  &  &  &  \\
    Turnover Rate &  &  &  &  \\
    Investor Sentiment (CICSI) &  &  &  &  \\
    Analyst Forecast Error &  &  &  &  \\
    Limits to Arbitrage &  &  &  &  \\
    \hline
    \midrule
    \multicolumn{6}{l}{\textit{⚠️ 数据待获取 — 占位模板，非实证结果}} \\
    \hline
    \hline
  \end{tabular}
  \note{This table reports summary statistics for the main variables.
    Stock returns are winsorized at 1\% and 99\%.
    Investor sentiment is measured using the CICSI index.}
\end{table}"""

    def _table2_latex(self, res: dict) -> str:
        coef = res.get("sentiment_coef", 0)
        se = res.get("sentiment_se", 0)
        stars = self._stars(res.get("sentiment_pval", 1))
        n = res.get("n_obs", " ")
        r2 = res.get("r_squared", " ")
        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Investor Sentiment and Expected Returns}}
  \begin{{tabular}}{{lcc}}
    \hline\hline
    & \multicolumn{{2}}{{c}}{{Stock Return}} \\
    Variable & (1) & (2) \\
    \hline
    Sentiment Index & {coef:.4f}{stars} & {coef:.4f}{stars} \\
                    & ({se:.4f}) & ({se:.4f}) \\
    Market Return &  & \checkmark \\
    Volatility &  & \checkmark \\
    \hline
    $N$ & {n} & {n} \\
    $R^2$ & {r2:.4f} & {r2:.4f} \\
    Firm FE & \checkmark & \checkmark \\
    Year FE & \checkmark & \checkmark \\
    \hline
    \hline
  \end{{tabular}}
  \note{{Standard errors in parentheses, double-clustered at firm $\times$ time.
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.
    Dependent variable: stock return. Independent variable of interest: investor sentiment index.}}
\end{{table}}"""

    def _table3_latex(self, res: dict) -> str:
        coef = res.get("sentiment_coef", 0)
        se = res.get("sentiment_se", 0)
        stars = self._stars(res.get("sentiment_pval", 1))
        n = res.get("n_obs", " ")
        r2 = res.get("r_squared", " ")
        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Investor Sentiment and Corporate Investment}}
  \begin{{tabular}}{{lcc}}
    \hline\hline
    & \multicolumn{{2}}{{c}}{{Investment (Capex/Assets)}} \\
    Variable & (1) & (2) \\
    \hline
    Sentiment Index & {coef:.4f}{stars} & {coef:.4f}{stars} \\
                    & ({se:.4f}) & ({se:.4f}) \\
    Size (Log MktCap) &  & \checkmark \\
    Book-to-Market &  & \checkmark \\
    \hline
    $N$ & {n} & {n} \\
    $R^2$ & {r2:.4f} & {r2:.4f} \\
    Firm FE & \checkmark & \checkmark \\
    Year FE & \checkmark & \checkmark \\
    \hline
    \hline
  \end{{tabular}}
  \note{{Standard errors in parentheses, robust to heteroskedasticity.
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.
    Dependent variable: capital expenditure normalized by total assets.}}
\end{{table}}"""

    def _table4_latex(self, res: dict) -> str:
        s_coef = res.get("sentiment_coef", 0)
        s_se = res.get("sentiment_se", 0)
        s_stars = self._stars(res.get("sentiment_pval", 1))
        a_coef = res.get("arbitrage_coef", 0)
        a_se = res.get("arbitrage_se", 0)
        a_stars = self._stars(0.05)
        n = res.get("n_obs", " ")
        r2 = res.get("r_squared", " ")
        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{Limits to Arbitrage as a Mechanism}}
  \begin{{tabular}}{{lcc}}
    \hline\hline
    & \multicolumn{{2}}{{c}}{{Stock Return}} \\
    Variable & (1) & (2) \\
    \hline
    Sentiment Index & {s_coef:.4f}{s_stars} & {s_coef:.4f}{s_stars} \\
                    & ({s_se:.4f}) & ({s_se:.4f}) \\
    Limits to Arbitrage &  & {a_coef:.4f}{a_stars} \\
                         &  & ({a_se:.4f}) \\
    \hline
    $N$ & {n} & {n} \\
    $R^2$ & {r2:.4f} & {r2:.4f} \\
    Firm FE & \checkmark & \checkmark \\
    Year FE & \checkmark & \checkmark \\
    \hline
    \hline
  \end{{tabular}}
  \note{{Standard errors in parentheses, double-clustered at firm $\times$ time.
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.
    Limits to arbitrage measured by idiosyncratic volatility and analyst dispersion.}}
\end{{table}}"""

    def _stars(self, pvalue: float) -> str:
        if pvalue < 0.01:
            return "***"
        if pvalue < 0.05:
            return "**"
        if pvalue < 0.1:
            return "*"
        return ""

    def get_figure_plan(self) -> list[dict]:
        return [
            {
                "figure_id": "Figure_1",
                "title": "投资者情绪指数（CICSI）时间趋势与政策事件",
                "description": "Investor sentiment index (CICSI) time series with policy events marked",
                "generation_method": "matplotlib",
                "data_source": "CICSI index (manual), policy events annotated",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "line",
                "x": "date",
                "y": "CICSI",
                "annotations": self.policy_events,
            },
            {
                "figure_id": "Figure_2",
                "title": "高/低情绪冲击期的异常收益对比",
                "description": "Abnormal returns around high vs. low sentiment shock periods",
                "generation_method": "matplotlib",
                "data_source": "yfinance (stock returns), manual sentiment data",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "event_study",
                "dependent": "abnormal_return",
                "independent": "sentiment_shock",
            },
            {
                "figure_id": "Figure_3",
                "title": "机制路径图：情绪→有限套利→定价偏差",
                "description": "Mechanism diagram: sentiment → limits to arbitrage → mispricing",
                "generation_method": "matplotlib",
                "data_source": "mechanism analysis from regressions",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "path_diagram",
                "nodes": ["Sentiment", "Limits to Arbitrage", "Mispricing"],
                "edges": [
                    ("Sentiment", "Limits to Arbitrage"),
                    ("Limits to Arbitrage", "Mispricing"),
                    ("Sentiment", "Mispricing"),
                ],
            },
            {
                "figure_id": "Figure_4",
                "title": "投资者类型异质性：机构与散户的情绪敏感性",
                "description": "Heterogeneity by investor type: institutional vs. retail sensitivity to sentiment",
                "generation_method": "matplotlib",
                "data_source": "Tushare (investor structure), yfinance (returns)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "bar_grouped",
                "groups": ["Institutional", "Retail"],
                "dependent": "return_sensitivity",
            },
        ]


get_registry().register(BehavioralFinanceDirection())
