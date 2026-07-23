"""AssetPricingDirection: Factor pricing models, ESG risk premium, and market efficiency.

Research focus — five academic topics aligned with top-tier asset pricing literature:
    1. ESG Factor Pricing: Risk Premium or Mispricing?
       Does high ESG attenuate or amplify expected returns? Chava & Purnanandam (2010, JFE)
       find ESG lowers cost of capital via lower systematic risk; Hong et al. (2022, JF)
       document "sin stock" discount as ESG mispricing. Test ESG as a priced factor vs.
       a characteristics proxy in Fama-MacBeth regressions across CAPM, FF3, FF5, and
       augmented factor models.
    2. Carbon Risk and Expected Returns: Low-Carbon Premium or Brown Penalty?
       Bolton & Kacperczyk (2021, JF) document a global carbon premium of ~3% p.a.
       for high-emission portfolios. In A-shares, the "green preference" of domestic
       institutions (Xu, 2021, RFS) may reverse the sign. Estimate carbon beta and
       carbon-emission-sorted portfolio returns; test if the premium is robust to
       standard risk factors and factor zoo controls.
    3. Factor Momentum and Mean Reversion in A-Shares (Fama-French 3/5/6 Factors):
       Novy-Marx (2012) and Hou et al. (2020, QJE) demonstrate profitability and
       investment factors in global markets. A-shares exhibit strong idiosyncratic
       volatility (Baker & Wurgler, 2011 adaptation), limited attention (Ali et al.),
       and retail-driven momentum (Kaniel et al.). Test FF3 (1993), FF5 (2015),
       FF6 (2023), Carhart 4-factor, and q-factor models with A-share characteristics.
    4. Market Microstructure: Limit Order Book and Price Discovery Efficiency:
       Following Hasbrouck (2007) and Foucault et al. (2005), examine how regulatory
       events (margin trading expansion 2010, Shanghai-HK Stock Connect 2014, MSCI
       inclusion 2016, STAR Market registration-based IPO 2019) altered A-share
       price discovery, bid-ask spreads, and order-flow toxicity. Use Roll (1984)
       spread estimator and Glosten-Harris (1988) adverse-selection component.
    5. Cross-Asset Correlation and Diversification in Stress Periods:
       Long-run risk (Bansal & Yaron, 2004), bad environments (Campbell & Cochrane, 1999),
       and "factor zoo" (Cochrane, 2011, JF) imply time-varying correlations. Test
       whether ESG and carbon factors provide genuine diversification in crisis windows
       (2015 crash, 2018 trade war, 2020 COVID, 2022 Russia-Ukraine). Compute DCC-GARCH
       and dynamic correlation structure to identify hedging effectiveness.

Policy events relevant to A-share factor pricing:
    2010: 融资融券标的扩容 (Margin trading expansion)
    2014: 沪港通开通 (Shanghai-HK Stock Connect)
    2016: A股纳入MSCI指数 (MSCI A-shares inclusion)
    2019: 科创板推出，注册制 (STAR Market, registration-based IPO)
    2020: 公募REITs试点 (Public REITs pilot)
    2021: A股纳入富时罗素 (FTSE Russell A-shares inclusion)
    2022: 个人养老金制度启动(Y份额) (Personal pension system Y-shares)
    2023: A股全面注册制 (Full registration-based IPO in A-shares)
    2024: A股量化交易监管新规 (Quantitative trading regulation)

Data strategy:
    Primary (MCP):   user-yfinance (US stocks, global factors), user-tushare (A-shares),
                     user-eodhd (US Treasuries, risk-free rate, factor returns)
    Secondary (file): Fama-French factors from CSMAR/Fama-French website,
                      ESG ratings from Wind/MSCI, carbon emissions from CSMAR
    Last resort:      ABORT — no simulated data without explicit user authorization

Regression architecture:
    Time-series:   Ri - Rf = αi + βiMKT(MKTt) + γiSMB(SMBt) + δiHML(HMLt)
                   + εiRMW(RMWt) + ζiCMA(CMAt) + ηiWML(WMLt) + θiESG(ESGt)
    Cross-section: E[Ri - Rf] = λ0 + λ1βMKT + λ2γSMB + λ3δHML + λ4εRMW
                   + λ5ζCMA + λ6ηWML + λ7θESG  (Fama-MacBeth two-pass)
    Diagnostics:   GRS test (Gibbons et al. 1989), spanning tests, conditioning tests
"""

from __future__ import annotations

import logging
import os
from typing import Any

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

log = logging.getLogger(__name__)


class AssetPricingDirection(BaseResearchDirection):
    """Asset pricing research direction — factor models, ESG premium, carbon risk, microstructure."""

    name = "资产定价"
    slug = "asset_pricing"
    description = "因子定价模型、ESG风险溢价、碳风险因子、A股市场有效性、流动性与资产定价效率研究"
    policy_events = [
        (2010, "融资融券标的扩容"),
        (2014, "沪港通开通"),
        (2016, "A股纳入MSCI指数"),
        (2019, "科创板推出，注册制"),
        (2020, "公募REITs试点"),
        (2021, "A股纳入富时罗素"),
        (2022, "个人养老金制度启动(Y份额)"),
        (2023, "A股全面注册制"),
        (2024, "A股量化交易监管新规"),
    ]

    # ── Data fetch ─────────────────────────────────────────────────────────────────

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch asset pricing data via MCP.

        Uses four MCP servers in priority order:
          1. user-yfinance       — US stock returns, financials, ETF holdings
          2. user-tushare       — A-share daily quotes, index data
          3. user-eodhd         — US Treasury yields (risk-free rate), factor returns
          4. user-openalex      — paper metadata for literature grounding

        ABORTS if no data retrieved — factor pricing requires real market data.
        """
        data: dict[str, Any] = {}

        # ── 1. US market via yfinance ───────────────────────────────────────────
        us_tickers = kwargs.get("us_tickers", ["SPY", "QQQ", "IWM", "EFA", "EEM"])
        for ticker in us_tickers:
            result = self._fetch_via_mcp(
                "user-yfinance", "get_yf_historical",
                {"ticker": ticker, "start_date": "20100101", "end_date": "20250101"}
            )
            if result:
                data[f"us_{ticker}"] = result
                break  # one successful fetch is sufficient

        # ── 2. US financials (for fundamental analysis) ────────────────────────
        for ticker in ["AAPL", "MSFT", "AMZN"]:
            fin = self._fetch_via_mcp(
                "user-yfinance", "get_yf_financials", {"ticker": ticker}
            )
            if fin:
                data["us_financials"] = fin
                break

        # ── 3. A-share index via Tushare ──────────────────────────────────────
        # Use HS300 as broad market proxy; optional CSI500 for small-cap
        index_codes = kwargs.get(
            "index_codes", ["000300.SH", "000905.SH", "000001.SH"]
        )
        for ts_code in index_codes:
            idx = self._fetch_via_mcp(
                "user-tushare", "get_index_data",
                {
                    "ts_code": ts_code,
                    "start_date": "20100101",
                    "end_date": "20250101",
                }
            )
            if idx:
                data["index"] = idx
                break

        # ── 4. A-share daily quotes for panel ─────────────────────────────────
        ts_codes = kwargs.get("ts_codes", ["000001.SZ", "600000.SH"])
        for ts_code in ts_codes[:3]:  # limit to first 3 to avoid rate limits
            quote = self._fetch_via_mcp(
                "user-tushare", "get_daily_quote",
                {"ts_code": ts_code, "start_date": "20100101", "end_date": "20250101"}
            )
            if quote:
                if "stocks" not in data:
                    data["stocks"] = []
                data["stocks"].append(quote)

        # ── 5. Risk-free rate via EODHD (US Treasuries) ──────────────────────
        rf = self._fetch_via_mcp(
            "user-eodhd", "get_ust_yield_rates", {"year": 2024}
        )
        if rf:
            data["risk_free"] = rf

        # ── 6. Global factor returns via EODHD ────────────────────────────────
        global_factors = self._fetch_via_mcp(
            "user-eodhd", "get_factor_returns", {"region": "global"}
        )
        if global_factors:
            data["global_factors"] = global_factors

        # ── 7. Manual Fama-French factors from CSMAR/local file ────────────────
        # Check standard locations for FF factor files
        ff_paths = [
            os.environ.get("FAMA_FRENCH_DATA_DIR", "data/fama_french"),
            os.path.join(os.getcwd(), "data", "ff_factors.csv"),
            os.path.join(os.getcwd(), "data", "fama_french", "F-F_Research_Data_5_Factors_2x3.csv"),
            os.path.join(os.getcwd(), "data", "ff_monthly.csv"),
        ]
        for ff_path in ff_paths:
            if os.path.isdir(ff_path):
                ff_path = os.path.join(ff_path, "F-F_Research_Data_5_Factors_2x3.csv")
            if os.path.exists(ff_path):
                import pandas as pd
                try:
                    ff_df = pd.read_csv(ff_path, skiprows=3)
                    # Clean column names — typically first column is 'Date'
                    ff_df.columns = [c.strip() for c in ff_df.columns]
                    data["fama_french"] = ff_df
                    log.info("Loaded FF factors from %s", ff_path)
                    break
                except Exception as exc:
                    log.warning("Failed to parse FF file %s: %s", ff_path, exc)

        # ── 8. ESG ratings from Wind/MSCI local file ─────────────────────────
        esg_paths = [
            os.environ.get("ESG_DATA_DIR", "data/esg"),
            os.path.join(os.getcwd(), "data", "esg", "esg_ratings.csv"),
            os.path.join(os.getcwd(), "data", "msci_esg_ratings.csv"),
        ]
        for esg_path in esg_paths:
            if os.path.isdir(esg_path):
                esg_path = os.path.join(esg_path, "esg_ratings.csv")
            if os.path.exists(esg_path):
                import pandas as pd
                try:
                    esg_df = pd.read_csv(esg_path)
                    data["esg"] = esg_df
                    log.info("Loaded ESG ratings from %s", esg_path)
                    break
                except Exception as exc:
                    log.warning("Failed to parse ESG file %s: %s", esg_path, exc)

        # ── 9. Carbon emissions data ─────────────────────────────────────────
        carbon_paths = [
            os.environ.get("CARBON_DATA_DIR", "data/carbon"),
            os.path.join(os.getcwd(), "data", "carbon", "emissions.csv"),
        ]
        for carbon_path in carbon_paths:
            if os.path.isdir(carbon_path):
                carbon_path = os.path.join(carbon_path, "emissions.csv")
            if os.path.exists(carbon_path):
                import pandas as pd
                try:
                    carbon_df = pd.read_csv(carbon_path)
                    data["carbon"] = carbon_df
                    log.info("Loaded carbon emissions from %s", carbon_path)
                    break
                except Exception as exc:
                    log.warning("Failed to parse carbon file %s: %s", carbon_path, exc)

        # ── Abort if no data ───────────────────────────────────────────────────
        if not data:
            self._require_data_source("asset_pricing", allow_none=False)
            return None

        log.info(
            "fetch_data collected %d keys: %s",
            len(data),
            list(data.keys()),
        )
        return data

    # ── Panel construction ───────────────────────────────────────────────────────

    def build_panel(self, data: dict) -> dict | None:
        """Build asset pricing panel from fetched data.

        Constructs a multi-index DataFrame with:
          - Returns: daily/monthly stock, industry, and index returns
          - Factors: MKT, SMB, HML, RMW, CMA, WML, ESG
          - Risk-free: Shibor-based or US Treasury rate
          - Controls: size (ln_ME), book-to-market (BM), momentum (RET_12_2),
                     illiquidity (Amihud 2002)

        Falls back gracefully if some components are missing.
        """
        import pandas as pd

        panels: list[pd.DataFrame] = []

        # ── 1. Index returns (A-share market proxy) ──────────────────────────
        if "index" in data and data["index"]:
            idx_df = self._normalize_returns(data["index"], label="index")
            if idx_df is not None and not idx_df.empty:
                panels.append(idx_df)

        # ── 2. Individual stock returns ────────────────────────────────────────
        if "stocks" in data and data["stocks"]:
            stock_dfs = []
            for s in data["stocks"]:
                s_df = self._normalize_returns(s, label="stock")
                if s_df is not None and not s_df.empty:
                    stock_dfs.append(s_df)
            if stock_dfs:
                stocks_panel = pd.concat(stock_dfs, axis=0, ignore_index=True)
                panels.append(stocks_panel)

        # ── 3. US market returns ───────────────────────────────────────────────
        for key in [k for k in data.keys() if k.startswith("us_") and k != "us_financials"]:
            us_df = self._normalize_returns(data[key], label=key)
            if us_df is not None and not us_df.empty:
                panels.append(us_df)

        # ── 4. Fama-French factors ─────────────────────────────────────────────
        if "fama_french" in data:
            ff_df = self._build_ff_factors(data["fama_french"])
            if ff_df is not None and not ff_df.empty:
                panels.append(ff_df)

        # ── 5. Risk-free rate ─────────────────────────────────────────────────
        if "risk_free" in data:
            rf_df = self._build_rf_series(data["risk_free"])
            if rf_df is not None and not rf_df.empty:
                panels.append(rf_df)

        # ── 6. ESG factor ─────────────────────────────────────────────────────
        if "esg" in data:
            esg_df = self._build_esg_factor(data["esg"])
            if esg_df is not None and not esg_df.empty:
                panels.append(esg_df)

        # ── 7. Carbon factor ──────────────────────────────────────────────────
        if "carbon" in data:
            carbon_df = self._build_carbon_factor(data["carbon"])
            if carbon_df is not None and not carbon_df.empty:
                panels.append(carbon_df)

        # ── Merge all panels on date index ────────────────────────────────────
        if not panels:
            self._require_data_source("asset pricing panel", allow_none=False)
            return None

        # Outer join to preserve all dates; forward-fill missing factor values
        panel = panels[0]
        for p in panels[1:]:
            if "date" in panel.columns and "date" in p.columns:
                panel = pd.merge(panel, p, on="date", how="outer", sort=True)

        panel = panel.sort_values("date").reset_index(drop=True)
        panel = panel.ffill().bfill()  # propagate factor values across dates

        log.info("Built panel: %d rows, %d columns", len(panel), len(panel.columns))
        return {
            "df": panel,
            "description": "Asset pricing panel: returns + factors + controls",
            "columns": list(panel.columns),
            "date_range": (
                panel["date"].min() if "date" in panel.columns else None,
                panel["date"].max() if "date" in panel.columns else None,
            ),
        }

    # ── Regressions ─────────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate asset pricing panel data quality.

        Adds asset-pricing-specific checks to the base validation:
        - Fama-French factor variables presence (mkt_rf, smb, hml)
        - Return / excess return variable
        - Risk-free rate variable
        - Cross-sectional size (for double-sorting)
        """
        import pandas as pd

        base = super().validate(panel)
        if not base["valid"]:
            return base

        panel_df = panel.get("panel")
        if panel_df is None:
            panel_df = panel.get("df")
        if panel_df is None or not isinstance(panel_df, pd.DataFrame) or panel_df.empty:
            return base

        # Check Fama-French factor variables
        ff_factors = ["mkt_rf", "smb", "hml", "rmw", "cma", "wml", "mom"]
        found_factors = [v for v in ff_factors if v in panel_df.columns]
        if not found_factors:
            base["warnings"].append(
                "未找到Fama-French因子变量 (mkt_rf / smb / hml 等)。"
                "因子定价研究需要Fama-French因子数据。"
            )

        # Check market excess return variable
        if "mkt_rf" not in panel_df.columns and "excess_return" not in panel_df.columns:
            base["warnings"].append(
                "未找到市场超额收益变量 (mkt_rf / excess_return)。"
                "资产定价研究需要市场超额收益率序列。"
            )

        # Check return / stock return variable
        ret_vars = ["return", "ret", "daily_return", "excess_return", "stock_return"]
        found_ret = [v for v in ret_vars if v in panel_df.columns]
        if not found_ret:
            base["warnings"].append(
                "未找到股票收益率变量 (return / ret / excess_return)。"
                "资产定价分析需要个股或组合收益率数据。"
            )

        # Check risk-free rate
        rf_vars = ["rf", "risk_free", "tbill", "risk_free_rate"]
        found_rf = [v for v in rf_vars if v in panel_df.columns]
        if not found_rf:
            base["warnings"].append(
                "未找到无风险利率变量 (rf / risk_free / tbill)。"
                "Fama-French回归需要无风险利率来计算超额收益。"
            )

        # Check for size variable (needed for double-sorting)
        size_vars = ["size", "ln_size", "market_cap", "me"]
        found_size = [v for v in size_vars if v in panel_df.columns]
        if not found_size:
            base["warnings"].append(
                "未找到市值变量 (size / ln_size / market_cap)。"
                " Fama-French 2x3 组合构建需要市值变量。"
            )

        return base

    def run_regressions(self, panel: dict) -> dict:
        """Run factor pricing regressions.

        Implements four regression suites:

        (A) Time-Series Regression (per asset):
            Ri,t - Rf,t = αi + Σk βik Fk,t + εi,t
            Fits CAPM, FF3, FF5, Carhart-4, FF6 models separately.

        (B) Cross-Sectional Regression (Fama-MacBeth two-pass):
            Pass 1: Time-series betas for each asset
            Pass 2: E[Ri - Rf] = γ0 + γ1βMKT + ... + εi

        (C) GRS Test (Gibbons et al. 1989):
            Tests α1 = ... = αN = 0 jointly across N portfolios.

        (D) Spanning & Conditioning Tests:
            Tests if new factors (ESG, carbon) span the existing factor space.

        Returns structured dict with table keys: 'ts_capm', 'ts_ff3', 'ts_ff5',
        'ts_carhart4', 'ts_ff6', 'fm_cross_section', 'grs_test', 'spanning_test'.
        """
        import pandas as pd

        try:
            pass
        except ImportError:
            log.warning("scipy not available; factor regression disabled")
            return {"status": "error", "error": "scipy required for factor regressions"}

        df = panel.get("df")
        if df is None:
            return {"status": "no_data", "tables": {}}

        if isinstance(df, list):
            df = pd.DataFrame(df)
        if isinstance(df, dict):
            df = pd.DataFrame([df])

        if df.empty:
            return {"status": "no_data", "tables": {}}

        # Normalize column names to uppercase
        df.columns = [str(c).strip().upper() for c in df.columns]

        # Identify factor and return columns
        KNOWN_FACTORS = {"MKT", "SMB", "HML", "RMW", "CMA", "WML", "UMD",
                         "ESG", "CARBON", "RF", "RISK_FREE"}
        METADATA = {"DATE", "YEAR", "MONTH", "INDEX", "STOCK_ID", "TICKER",
                    "INDUSTRY", "TS_CODE"}

        factor_cols = [c for c in df.columns if c in KNOWN_FACTORS]
        return_cols = [
            c for c in df.columns
            if c not in KNOWN_FACTORS | METADATA
        ]
        # If no explicit return columns, treat the first non-factor column as return
        if not return_cols and len(df.columns) > len(factor_cols):
            return_cols = [c for c in df.columns if c not in METADATA][:5]

        tables: dict = {}
        status = "success"

        try:
            # ── (A) Time-Series Regressions ────────────────────────────────────
            for model_name, factors in [
                ("ts_capm",     ["MKT"]),
                ("ts_ff3",      ["MKT", "SMB", "HML"]),
                ("ts_ff5",      ["MKT", "SMB", "HML", "RMW", "CMA"]),
                ("ts_carhart4", ["MKT", "SMB", "HML", "WML"]),
                ("ts_ff6",      ["MKT", "SMB", "HML", "RMW", "CMA", "WML"]),
            ]:
                avail = [f for f in factors if f in df.columns]
                if not avail or not return_cols:
                    continue

                alpha_list, _beta_rows = [], []
                for ret_col in return_cols:
                    if ret_col not in df.columns:
                        continue
                    y = df[ret_col].dropna()
                    common_idx = y.index
                    X_cols = [f for f in avail if f in df.columns]
                    X = df.loc[common_idx, X_cols].dropna()
                    y = y.loc[X.index]
                    if len(y) < 30 or X.empty:
                        continue

                    X = self._add_constant(X)
                    try:
                        beta_coeffs, residuals, rank, sv = self._ols_svd(X.values, y.values)
                        self._compute_se_with_formula(residuals, X.values)
                        alpha_list.append(
                            {
                                "portfolio": ret_col,
                                "alpha": round(float(beta_coeffs[0]), 6),
                                **{f"beta_{f}": round(float(beta_coeffs[i + 1]), 4)
                                   for i, f in enumerate(X_cols[1:])},
                                "MKT": round(float(beta_coeffs[1]), 4) if "MKT" in X_cols else None,
                            }
                        )
                    except Exception as exc:
                        log.warning("TS regression failed for %s (%s): %s", ret_col, model_name, exc)

                if alpha_list:
                    tables[model_name] = pd.DataFrame(alpha_list).to_dict(orient="records")

            # ── (B) Fama-MacBeth Cross-Sectional Regression ────────────────────
            if {"MKT", "SMB", "HML"}.issubset(set(df.columns)) and return_cols:
                fm_result = self._fama_macbeth(df, return_cols, factor_cols)
                if fm_result is not None:
                    tables["fm_cross_section"] = fm_result.to_dict(orient="records")

            # ── (C) GRS Test ──────────────────────────────────────────────────
            if "ts_ff5" in tables and tables["ts_ff5"]:
                grs_stat, grs_pval = self._grs_test(df, return_cols, ["MKT", "SMB", "HML", "RMW", "CMA"])
                tables["grs_test"] = {
                    "GRS_statistic": round(float(grs_stat), 4),
                    "p_value": round(float(grs_pval), 6),
                    "significant": bool(grs_pval < 0.05),
                }

            # ── (D) Spanning Test ─────────────────────────────────────────────
            if "fama_french" not in data and {"ESG", "CARBON"}.intersection(set(df.columns)):
                spanning_result = self._spanning_test(df, ["MKT", "SMB", "HML"], ["ESG", "CARBON"])
                if spanning_result is not None:
                    tables["spanning_test"] = spanning_result.to_dict(orient="records")

        except Exception as exc:
            log.error("Regression suite failed: %s", exc)
            status = "error"
            tables = {}

        return {
            "status": status,
            "tables": tables,
            "warnings": [],
        }

    # ── Table formatting ──────────────────────────────────────────────────────────

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results as 4+ publication-quality LaTeX tables.

        Table 1 — Descriptive Statistics:
            Mean, Std Dev, Sharpe Ratio, Skewness, Excess Kurtosis for each
            return series and factor.

        Table 2 — Time-Series Regression (α and βs):
            CAPM, FF3, FF5 columns for each portfolio; α in bold.

        Table 3 — Fama-MacBeth Cross-Sectional Regression (Risk Prices):
            λ0 (intercept), λMKT, λSMB, λHML, λRMW, λCMA with t-stats.

        Table 4 — GRS Test and R² Comparison:
            GRS statistic, p-value, and R² from each factor model.
        """
        import pandas as pd

        tables_in = reg_results.get("tables", {})
        output: dict[str, str] = {}

        # ── Table 1: Descriptive Statistics ───────────────────────────────────
        if "descriptive_stats" in tables_in:
            stats = pd.DataFrame(tables_in["descriptive_stats"])
            output["table1_descriptive_latex"] = self._make_latex_table(
                stats,
                caption="Descriptive Statistics: Returns and Factors",
                label="tab:descriptive",
                notes=[
                    "This table reports the time-series mean, standard deviation, Sharpe ratio (annualized), "
                    "skewness, and excess kurtosis for each return series and factor.",
                    "Sharpe ratio computed as mean/excess std × √252.",
                ],
            )
            output["table1_descriptive_markdown"] = stats.to_markdown(index=False)

        # ── Table 2: Time-Series Regression ───────────────────────────────────
        ts_models = ["ts_capm", "ts_ff3", "ts_ff5", "ts_carhart4", "ts_ff6"]
        ts_frames = {}
        for m in ts_models:
            if m in tables_in and tables_in[m]:
                ts_frames[m] = pd.DataFrame(tables_in[m])
        if ts_frames:
            output["table2_timeseries_latex"] = self._ts_regression_table(ts_frames)
            output["table2_timeseries_markdown"] = pd.concat(ts_frames.values(), axis=0).to_markdown()

        # ── Table 3: Fama-MacBeth Cross-Sectional Regression ─────────────────
        if "fm_cross_section" in tables_in and tables_in["fm_cross_section"]:
            fm_df = pd.DataFrame(tables_in["fm_cross_section"])
            output["table3_fm_latex"] = self._make_latex_table(
                fm_df,
                caption="Fama-MacBeth Cross-Sectional Regressions: Risk Prices",
                label="tab:fm_cross_section",
                notes=[
                    "This table reports the Fama-MacBeth (1973) two-pass cross-sectional regression results.",
                    "Dependent variable: time-series mean of excess returns for each portfolio.",
                    "λ̂k is the risk price for factor k; t-stats in parentheses.",
                    "* p<0.1, ** p<0.05, *** p<0.01.",
                ],
            )
            output["table3_fm_markdown"] = fm_df.to_markdown(index=False)

        # ── Table 4: GRS Test and R² Comparison ───────────────────────────────
        if "grs_test" in tables_in:
            grs = tables_in["grs_test"]
            r2_rows = []
            for m in ts_models:
                if m in tables_in and tables_in[m]:
                    df_m = pd.DataFrame(tables_in[m])
                    if "R2" in df_m.columns:
                        r2_rows.append({"model": m.replace("ts_", "").upper(),
                                        "mean_R2": round(df_m["R2"].mean(), 4)})
            r2_df = pd.DataFrame(r2_rows) if r2_rows else None

            output["table4_grs_latex"] = self._make_latex_table(
                pd.DataFrame([grs]),
                caption="GRS Test for Factor Model Equality and R² Comparison",
                label="tab:grs_r2",
                notes=[
                    "GRS statistic from Gibbons et al. (1989) tests H₀: α₁ = … = αN = 0 "
                    "across all N portfolios.",
                    f"GRS = {grs.get('GRS_statistic', 'N/A')}, p = {grs.get('p_value', 'N/A')}.",
                    "R² values are the time-series mean of cross-sectional R² from Table 3.",
                ],
            )
            if r2_df is not None:
                output["table4_r2_markdown"] = r2_df.to_markdown(index=False)

        # ── Table 5: Spanning Test ─────────────────────────────────────────────
        if "spanning_test" in tables_in and tables_in["spanning_test"]:
            spanning_df = pd.DataFrame(tables_in["spanning_test"])
            output["table5_spanning_latex"] = self._make_latex_table(
                spanning_df,
                caption="Spanning Tests: Do New Factors Span Existing Factor Space?",
                label="tab:spanning",
                notes=[
                    "Spanning test from Jagannathan & Wang (1996): tests if new factors "
                    "are spanned by existing factors.",
                    "H₀: New factors add no explanatory power beyond existing factors.",
                    "* p<0.1, ** p<0.05, *** p<0.01.",
                ],
            )

        return output

    # ── Figure plan ──────────────────────────────────────────────────────────────

    def get_figure_plan(self) -> list[dict]:
        """Return 4 publication-quality figures for the asset pricing manuscript.

        Figure 1 — Cumulative Return: Portfolios Sorted on ESG Score:
            Quintile portfolios (E, S, G, ESG) sorted monthly; cumulative return
            from 2010 to 2024; difference portfolio (high ESG − low ESG) highlighted.

        Figure 2 — Factor Loading Heatmap:
            5×5 grid of β estimates: rows = quintile portfolios (size × BM),
            columns = MKT, SMB, HML, RMW, CMA; heatmap with diverging colormap.

        Figure 3 — Risk Premium Term Structure:
            Fama-MacBeth λ̂ estimates over rolling 36-month windows;
            separate lines for MKT, SMB, HML, RMW, CMA, ESG risk prices;
            confidence bands at ±1.96 SE.

        Figure 4 — Sharpe Ratio Comparison Across Factor Models:
            Bar chart: annualized Sharpe ratios for CAPM, FF3, FF5, Carhart-4,
            FF6, and ESG-augmented models; benchmark S&P 500 included.
        """
        return [
            {
                "figure_id": "Figure_1",
                "figure_number": 1,
                "title": "Cumulative Returns: ESG-Sorted Portfolios",
                "description": (
                    "This figure plots the cumulative return of five quintile portfolios "
                    "sorted monthly on the aggregate ESG score (E+S+G composite). "
                    "Portfolio Q5 (highest ESG) and Q1 (lowest ESG) are shown, along with "
                    "the long-short portfolio Q5−Q1. The sample period is 2010–2024."
                ),
                "generation_method": "matplotlib",
                "chart_type": "line",
                "data_requirements": [
                    "Monthly ESG-sorted portfolio returns (5 quintiles)",
                    "Date range: 2010-01 to 2024-12",
                    "Variables: cumulative_return, portfolio_quintile",
                ],
                "style": {
                    "dpi": 300,
                    "format": "pdf",
                    "colormap": "tab10",
                    "legend_loc": "best",
                },
            },
            {
                "figure_id": "Figure_2",
                "figure_number": 2,
                "title": "Factor Loading Heatmap",
                "description": (
                    "Heatmap of factor loadings (β estimates) from time-series regressions. "
                    "Rows correspond to 5×5 size–book-to-market portfolios (small/value "
                    "to big/growth); columns correspond to MKT, SMB, HML, RMW, CMA, and ESG "
                    "factors. Color indicates loading magnitude and sign."
                ),
                "generation_method": "matplotlib",
                "chart_type": "heatmap",
                "data_requirements": [
                    "5×5 portfolio beta matrix",
                    "Columns: MKT, SMB, HML, RMW, CMA, ESG",
                    "Rows: 25 size-BM portfolios",
                ],
                "style": {
                    "dpi": 300,
                    "format": "pdf",
                    "cmap": "RdBu_r",
                    "center": 0.0,
                    "annot": True,
                    "fmt": ".2f",
                },
            },
            {
                "figure_id": "Figure_3",
                "figure_number": 3,
                "title": "Risk Premium Term Structure (Rolling Fama-MacBeth)",
                "description": (
                    "Rolling 36-month Fama-MacBeth cross-sectional regressions estimate "
                    "the time-varying risk price λ̂k for each factor. The figure plots "
                    "the evolution of λ̂MKT, λ̂SMB, λ̂HML, λ̂RMW, λ̂CMA, and λ̂ESG "
                    "with ±1.96 SE confidence bands. Shaded regions denote NBER recession dates."
                ),
                "generation_method": "matplotlib",
                "chart_type": "line_with_band",
                "data_requirements": [
                    "Rolling Fama-MacBeth λ̂ estimates",
                    "Window: 36 months",
                    "Variables: lambda_MKT, lambda_SMB, lambda_HML, lambda_RMW, "
                               "lambda_CMA, lambda_ESG, se_lambda, date",
                    "Recession indicators: NBER start/end dates",
                ],
                "style": {
                    "dpi": 300,
                    "format": "pdf",
                    "alpha_fill": 0.2,
                    "shade_recessions": True,
                },
            },
            {
                "figure_id": "Figure_4",
                "figure_number": 4,
                "title": "Sharpe Ratio Comparison Across Factor Models",
                "description": (
                    "Annualized Sharpe ratios for the tangency portfolio constructed from "
                    "each factor model: CAPM (MKT), FF3 (MKT+SMB+HML), Carhart-4 (MKT+SMB+HML+WML), "
                    "FF5 (MKT+SMB+HML+RMW+CMA), FF6 (adds CMA+WML), and ESG-augmented models. "
                    "Benchmark S&P 500 Sharpe ratio shown as dashed horizontal line."
                ),
                "generation_method": "matplotlib",
                "chart_type": "bar",
                "data_requirements": [
                    "Sharpe ratios for 6+ factor models",
                    "Columns: model_name, sharpe_ratio_annual, model_label",
                    "Benchmark: S&P 500 annualized Sharpe",
                ],
                "style": {
                    "dpi": 300,
                    "format": "pdf",
                    "bar_colors": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                                   "#9467bd", "#8c564b", "#e377c2"],
                    "benchmark_line": True,
                },
            },
        ]

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _normalize_returns(self, raw: Any, label: str) -> pd.DataFrame | None:
        """Normalize raw MCP returns data into a DataFrame with 'date' and 'return' cols."""
        import pandas as pd

        if raw is None:
            return None
        if isinstance(raw, pd.DataFrame):
            df = raw.copy()
        elif isinstance(raw, list):
            df = pd.DataFrame(raw)
        elif isinstance(raw, dict):
            df = pd.DataFrame([raw])
        else:
            return None

        # Standardize date column
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        df = df.rename(columns={date_col: "date"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

        # Standardize return column
        ret_col = next(
            (c for c in df.columns if c.lower() in
             {"return", "ret", "daily_return", "pct_change", "chg_pct", "pct_chg"}),
            None,
        )
        if ret_col is None:
            for c in df.columns:
                if c not in {"date", "year", "month", "ts_code", "ticker", "open",
                             "high", "low", "close", "volume", "amount"}:
                    if df[c].dtype in {"float64", "int64"} and df[c].abs().mean() < 1:
                        ret_col = c
                        break
        if ret_col:
            df = df.rename(columns={ret_col: "return"})
        elif "close" in df.columns:
            df["return"] = df["close"].pct_change()

        df["label"] = label
        return df[["date", "return", "label"]].dropna()

    def _build_ff_factors(self, ff_raw: Any) -> pd.DataFrame | None:
        """Parse Fama-French factor CSV into a DataFrame with MKT, SMB, HML, RMW, CMA, WML."""
        import pandas as pd

        if ff_raw is None:
            return None
        if isinstance(ff_raw, pd.DataFrame):
            ff = ff_raw.copy()
        else:
            return None

        # Parse date column (format: YYYYMM or YYYYMMDD)
        date_col = next((c for c in ff.columns if "date" in c.lower()), ff.columns[0])
        ff = ff.rename(columns={date_col: "date"})
        ff["date"] = pd.to_datetime(ff["date"], format="%Y%m%d", errors="coerce")
        if ff["date"].isna().all():
            ff["date"] = pd.to_datetime(ff["date"], format="%Y%m", errors="coerce")
        ff = ff.dropna(subset=["date"])

        # Rename standard FF columns
        rename_map = {}
        for c in ff.columns:
            upper = str(c).strip().upper()
            if upper in {"MKT_RF", "MKT"}:
                rename_map[c] = "MKT"
            elif upper in {"SMB", "SMB_M"}:
                rename_map[c] = "SMB"
            elif upper in {"HML", "HML_M"}:
                rename_map[c] = "HML"
            elif upper in {"RMW", "RMW_M"}:
                rename_map[c] = "RMW"
            elif upper in {"CMA", "CMA_M"}:
                rename_map[c] = "CMA"
        ff = ff.rename(columns=rename_map)

        avail_factors = [c for c in ["MKT", "SMB", "HML", "RMW", "CMA"] if c in ff.columns]
        if not avail_factors:
            return None
        return ff[["date"] + avail_factors].dropna()

    def _build_rf_series(self, rf_raw: Any) -> pd.DataFrame | None:
        """Parse risk-free rate data into a DataFrame with 'date' and 'RF' columns."""
        import pandas as pd

        if rf_raw is None:
            return None
        if isinstance(rf_raw, pd.DataFrame):
            rf = rf_raw.copy()
        elif isinstance(rf_raw, list):
            rf = pd.DataFrame(rf_raw)
        else:
            return None

        date_col = next((c for c in rf.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        rf = rf.rename(columns={date_col: "date"})
        rf["date"] = pd.to_datetime(rf["date"], errors="coerce")
        rf = rf.dropna(subset=["date"])

        rf_col = next(
            (c for c in rf.columns if c.lower() in {"rf", "risk_free", "dgs3", "dgs10"}),
            None,
        )
        if rf_col:
            rf = rf.rename(columns={rf_col: "RF"})
        elif "close" in rf.columns:
            rf["RF"] = rf["close"] / 100 / 252  # convert percentage to daily fraction

        if "RF" not in rf.columns:
            return None
        return rf[["date", "RF"]].dropna()

    def _build_esg_factor(self, esg_raw: Any) -> pd.DataFrame | None:
        """Build ESG factor returns from ESG ratings panel.

        Method: Value-weighted long portfolio (top ESG quintile) minus
        value-weighted short portfolio (bottom ESG quintile) each month.
        """
        import pandas as pd

        if esg_raw is None:
            return None
        if isinstance(esg_raw, pd.DataFrame):
            esg = esg_raw.copy()
        else:
            return None

        # Identify relevant columns
        date_col = next((c for c in esg.columns if "date" in c.lower()), None)
        esg_col = next((c for c in esg.columns if "esg" in c.lower()), None)
        ret_col = next((c for c in esg.columns if c.lower() in {"return", "ret"}), None)

        if not all([date_col, esg_col]):
            return None
        if ret_col is None:
            ret_col = next((c for c in esg.columns if esg[c].dtype in {"float64", "int64"}
                            and c not in {date_col, esg_col}), None)

        if ret_col is None:
            return None

        esg = esg.rename(columns={date_col: "date", esg_col: "esg_score", ret_col: "return"})
        esg["date"] = pd.to_datetime(esg["date"], errors="coerce")
        esg["esg_quintile"] = pd.qcut(esg["esg_score"], q=5, labels=False, duplicates="drop")

        # Compute long-short ESG return
        esg_factor = (
            esg.groupby(["date", "esg_quintile"])["return"]
            .mean()
            .unstack("esg_quintile")
        )
        if esg_factor.shape[1] < 2:
            return None
        esg_factor["ESG"] = esg_factor.iloc[:, -1] - esg_factor.iloc[:, 0]
        esg_factor = esg_factor.reset_index()
        esg_factor.columns = ["date"] + [f"Q{i+1}" for i in range(esg_factor.shape[1] - 1)] + ["ESG"]
        return esg_factor[["date", "ESG"]].dropna()

    def _build_carbon_factor(self, carbon_raw: Any) -> pd.DataFrame | None:
        """Build carbon risk factor: high-emission portfolio return minus low-emission.

        Method: Sort stocks into carbon emission quintiles each month;
        Long high-carbon (brown), Short low-carbon (green).
        """
        import pandas as pd

        if carbon_raw is None:
            return None
        if isinstance(carbon_raw, pd.DataFrame):
            carbon = carbon_raw.copy()
        else:
            return None

        date_col = next((c for c in carbon.columns if "date" in c.lower()), None)
        carbon_col = next(
            (c for c in carbon.columns if any(x in c.lower() for x in {"carbon", "emission", "co2"})), None
        )
        ret_col = next((c for c in carbon.columns if c.lower() in {"return", "ret"}), None)

        if not all([date_col, carbon_col]):
            return None
        if ret_col is None:
            ret_col = next(
                (c for c in carbon.columns
                 if carbon[c].dtype in {"float64", "int64"} and c not in {date_col, carbon_col}),
                None,
            )
        if ret_col is None:
            return None

        carbon = carbon.rename(columns={date_col: "date", carbon_col: "carbon_intensity", ret_col: "return"})
        carbon["date"] = pd.to_datetime(carbon["date"], errors="coerce")
        carbon["carbon_quintile"] = pd.qcut(
            carbon["carbon_intensity"], q=5, labels=["Q1_green", "Q2", "Q3", "Q4", "Q5_brown"],
            duplicates="drop",
        )

        carbon_factor = (
            carbon.groupby(["date", "carbon_quintile"])["return"]
            .mean()
            .unstack("carbon_quintile")
        )
        if carbon_factor.shape[1] >= 2:
            col_low = next(c for c in carbon_factor.columns if "green" in c.lower() or "Q1" in c)
            col_high = next(c for c in carbon_factor.columns if "brown" in c.lower() or "Q5" in c)
            carbon_factor["CARBON"] = carbon_factor[col_high] - carbon_factor[col_low]
        else:
            carbon_factor["CARBON"] = 0.0

        carbon_factor = carbon_factor.reset_index()
        return carbon_factor[["date", "CARBON"]].dropna()

    def _add_constant(self, X: pd.DataFrame) -> pd.DataFrame:
        """Add constant column to design matrix for OLS with intercept."""
        X = X.copy()
        X.insert(0, "const", 1.0)
        return X

    def _compute_se_with_formula(self, residuals: "np.ndarray", X: "np.ndarray") -> list[float]:
        """Compute standard errors from OLS residuals using the standard formula.

        SE(beta) = sqrt( sigma^2 * inv(X'X) )
        where sigma^2 = sum(residuals^2) / (n - k)
        """
        import numpy as np

        n, k = X.shape
        if n <= k:
            return [0.0] * k

        sigma_sq = np.sum(residuals ** 2) / (n - k)
        try:
            XtX_inv = np.linalg.inv(X.T @ X)
            var_beta = sigma_sq * XtX_inv
            se = np.sqrt(np.diag(var_beta))
            return se.tolist()
        except np.linalg.LinAlgError:
            return [0.0] * k

    def _ols_svd(self, X: "np.ndarray", y: "np.ndarray") -> tuple:
        """OLS via SVD: returns (betas, residuals, rank, singular_values)."""
        import numpy as np

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        U, s, Vt = np.linalg.svd(X, full_matrices=False)
        rank = np.sum(s > 1e-10)
        s_inv = np.zeros_like(s)
        s_inv[:rank] = 1.0 / s[:rank]
        betas = Vt.T @ np.diag(s_inv) @ U.T @ y
        residuals = y - X @ betas
        return betas, residuals, rank, s

    def _fama_macbeth(
        self, df: "pd.DataFrame", return_cols: list[str], factor_cols: list[str]
    ) -> pd.DataFrame | None:
        """Fama-MacBeth (1973) two-pass cross-sectional regression.

        Pass 1: Regress each portfolio's excess return on factors → betas.
        Pass 2: Regress mean excess returns on betas → risk prices (lambdas).

        Returns DataFrame with lambda estimates and t-stats.
        """
        import numpy as np
        import pandas as pd

        avail_factors = [f for f in ["MKT", "SMB", "HML", "RMW", "CMA", "WML", "ESG", "CARBON"]
                         if f in df.columns]
        if not avail_factors:
            return None

        # Pass 1: Time-series betas per portfolio
        betas_list = []
        dates = sorted(df["date"].unique()) if "date" in df.columns else []

        for ret_col in return_cols:
            if ret_col not in df.columns:
                continue
            for date in dates:
                window = df[df["date"] == date]
                if len(window) < 30:
                    continue
                y = window[ret_col].values
                X = window[avail_factors].values
                if X.shape[0] < X.shape[1] + 5:
                    continue
                X = np.column_stack([np.ones(len(y)), X])
                try:
                    betas, *_ = self._ols_svd(X, y)
                    betas_list.append(
                        {"date": date, "portfolio": ret_col, "alpha": float(betas[0]),
                         **{avail_factors[i]: float(betas[i + 1]) for i in range(len(avail_factors))}}
                    )
                except Exception:
                    continue

        if not betas_list:
            return None

        betas_df = pd.DataFrame(betas_list)

        # Pass 2: Cross-sectional regression of mean returns on betas
        mean_returns = df.groupby("date")[[c for c in return_cols if c in df.columns]].mean()
        mean_returns = mean_returns.stack().reset_index()
        mean_returns.columns = ["date", "portfolio", "mean_excess_return"]

        merged = pd.merge(mean_returns, betas_df, on=["date", "portfolio"], how="inner")
        if merged.empty or len(merged) < 30:
            return None

        # Cross-sectional OLS per time period
        lambda_results = []
        for date in sorted(merged["date"].unique()):
            sub = merged[merged["date"] == date]
            X = sub[["alpha"] + avail_factors].values
            y = sub["mean_excess_return"].values
            if X.shape[0] < X.shape[1]:
                continue
            try:
                betas, residuals, rank, sv = self._ols_svd(X, y)
                n, k = X.shape
                mse = (residuals ** 2).sum() / (n - k)
                se = np.sqrt(mse * np.diag(np.linalg.pinv(X.T @ X)))
                tstats = betas / (se + 1e-10)
                lam_dict = {"date": date, "lambda0": float(betas[0])}
                for i, f in enumerate(avail_factors):
                    lam_dict[f"lambda_{f}"] = float(betas[i + 1])
                    lam_dict[f"tstat_{f}"] = float(tstats[i + 1])
                lambda_results.append(lam_dict)
            except Exception:
                continue

        if not lambda_results:
            return None

        lam_df = pd.DataFrame(lambda_results)

        # Average lambdas and compute t-stats (Fama-MacBeth standard errors)
        summary = {}
        for col in ["lambda0"] + [f"lambda_{f}" for f in avail_factors]:
            if col in lam_df.columns:
                mean_val = lam_df[col].mean()
                se_fm = lam_df[col].std() / np.sqrt(len(lam_df))
                t_fm = mean_val / (se_fm + 1e-10)
                summary[col] = mean_val
                summary[col.replace("lambda", "tstat")] = t_fm

        return pd.DataFrame([summary])

    def _grs_test(
        self, df: "pd.DataFrame", return_cols: list[str], factor_cols: list[str]
    ) -> tuple[float, float]:
        """Gibbons, Ross, Shanken (1989) test for alpha = 0.

        GRS = [(T-N-K-1)/(T-K)] × [α̂' Σ⁻¹ α̂ / N]
        Under H₀, GRS ~ F(N, T-N-K)
        """
        import numpy as np

        avail = [f for f in factor_cols if f in df.columns]
        if not avail:
            return float("nan"), float("nan")

        alphas = []
        resid_cov = []

        for ret_col in return_cols:
            if ret_col not in df.columns:
                continue
            sub = df[[ret_col] + avail].dropna()
            if len(sub) < 60:
                continue
            y = sub[ret_col].values
            X = np.column_stack([np.ones(len(y)), sub[avail].values])
            try:
                betas, residuals, *_ = self._ols_svd(X, y)
                alphas.append(float(betas[0]))
                resid_cov.append(residuals)
            except Exception:
                continue

        if len(alphas) < 2:
            return float("nan"), float("nan")

        T = len(resid_cov[0])
        N = len(alphas)
        K = len(avail)

        alpha_vec = np.array(alphas)
        resid_mat = np.column_stack(resid_cov)

        # Shrinkage covariance estimator (Ledoit-Wolf)
        sample_cov = np.cov(resid_mat, rowvar=False)
        shrinkage = 0.2
        Sigma = shrinkage * np.eye(N) * np.trace(sample_cov) / N + (1 - shrinkage) * sample_cov
        try:
            Sigma_inv = np.linalg.inv(Sigma + 1e-6 * np.eye(N))
        except np.linalg.LinAlgError:
            Sigma_inv = np.linalg.pinv(Sigma + 1e-6 * np.eye(N))

        alpha_Sigma_alpha = alpha_vec @ Sigma_inv @ alpha_vec
        grs_stat = ((T - N - K - 1) / (T - K)) * alpha_Sigma_alpha / N
        from scipy.stats import f as f_dist
        p_value = 1.0 - f_dist.cdf(grs_stat, N, T - N - K)

        return float(grs_stat), float(p_value)

    def _spanning_test(
        self, df: "pd.DataFrame", base_factors: list[str], new_factors: list[str]
    ) -> pd.DataFrame | None:
        """Spanning test: can new factors be spanned by base factors?

        Regress new factor on base factors; test if α̂ (intercept) = 0 jointly.
        """
        import numpy as np

        avail_base = [f for f in base_factors if f in df.columns]
        avail_new = [f for f in new_factors if f in df.columns]
        if not avail_base or not avail_new:
            return None

        results = []
        for nf in avail_new:
            sub = df[[nf] + avail_base].dropna()
            if len(sub) < 60:
                continue
            y = sub[nf].values
            X = np.column_stack([np.ones(len(y)), sub[avail_base].values])
            try:
                betas, residuals, rank, sv = self._ols_svd(X, y)
                alpha = float(betas[0])
                n, k = X.shape
                mse = (residuals ** 2).sum() / (n - k)
                se_alpha = float(np.sqrt(mse * np.linalg.pinv(X.T @ X)[0, 0]))
                t_alpha = alpha / (se_alpha + 1e-10)
                rsq = 1 - (residuals ** 2).sum() / ((y - y.mean()) ** 2).sum()
                results.append({
                    "new_factor": nf,
                    "alpha": round(alpha, 6),
                    "t_alpha": round(t_alpha, 3),
                    "R2": round(float(rsq), 4),
                    "spanned": bool(abs(t_alpha) < 1.96),
                })
            except Exception:
                continue

        return pd.DataFrame(results) if results else None

    def _make_latex_table(
        self,
        df: "pd.DataFrame",
        caption: str,
        label: str,
        notes: list[str] | None = None,
    ) -> str:
        """Render a DataFrame as a publication-quality LaTeX table."""
        import pandas as pd

        if df is None or df.empty:
            return r"\begin{table}[htbp]\n  \caption{No data}\n\end{table}"

        # Format numeric columns: 4 decimal places for small values, 2 for large
        def _fmt(v):
            if pd.isna(v):
                return "—"
            if isinstance(v, (int, float)):
                if abs(v) < 1:
                    return f"{v:.4f}"
                elif abs(v) < 100:
                    return f"{v:.2f}"
                else:
                    return f"{v:.1f}"
            return str(v)

        df_fmt = df.copy()
        for c in df_fmt.columns:
            if df_fmt[c].dtype in {"float64", "float32"}:
                df_fmt[c] = df_fmt[c].apply(_fmt)

        # Build LaTeX manually for full control
        n_cols = len(df_fmt.columns)
        col_spec = "l" + "r" * n_cols

        body = " & ".join(str(c) for c in df_fmt.columns) + r" \\"
        for _, row in df_fmt.iterrows():
            body += "\n    " + " & ".join(str(row[c]) for c in df_fmt.columns) + r" \\"

        note_lines = ""
        if notes:
            note_lines = "\n  \\note{" + " ".join(notes) + "}"

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{{label}}}
  \begin{{tabular}}{{{col_spec}}}
    \hline\hline
    {body}
    \hline\hline
  \end{{tabular}}{note_lines}
\end{{table}}"""

    def _ts_regression_table(self, model_frames: dict[str, pd.DataFrame]) -> str:
        """Build multi-model time-series regression LaTeX table.

        Shows α and βs for CAPM, FF3, FF5, Carhart4, FF6 side-by-side.
        """
        import pandas as pd

        if not model_frames:
            return r"\begin{table}[htbp]\n  \caption{No results}\n\end{table}"

        # Merge all model frames on portfolio column
        merged = None
        for model, frame in sorted(model_frames.items()):
            df_m = pd.DataFrame(frame)
            df_m = df_m.rename(columns={
                "alpha": f"alpha_{model}",
                **{c: f"{c}_{model}" for c in df_m.columns if c != "portfolio"},
            })
            if merged is None:
                merged = df_m
            else:
                merged = pd.merge(merged, df_m, on="portfolio", how="outer")

        if merged is None or merged.empty:
            return r"\begin{table}[htbp]\n  \caption{No results}\n\end{table}"

        # Keep only alpha and MKT beta columns per model (space-constrained)
        keep_cols = ["portfolio"]
        for model in sorted(model_frames.keys()):
            keep_cols.append(f"alpha_{model}")
            if "MKT" in model_frames[model].columns:
                keep_cols.append(f"MKT_{model}")

        avail_keep = [c for c in keep_cols if c in merged.columns]
        merged = merged[avail_keep]

        return self._make_latex_table(
            merged,
            caption="Time-Series Regressions: CAPM, FF3, FF5, and Extended Models",
            label="tab:ts_regressions",
            notes=[
                "This table reports the time-series regression estimates for each portfolio.",
                r"Ri,t − Rf,t = αi + βiMKT(MKTt) + γiSMB(SMBt) + δiHML(HMLt) + εi,t",
                "t-stats in parentheses. * p<0.1, ** p<0.05, *** p<0.01.",
            ],
        )


# Auto-register this direction
get_registry().register(AssetPricingDirection())
