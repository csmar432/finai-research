"""AssetPricingDirection: Factor models, ESG pricing and market efficiency.

Research focus:
    1. ESG factor and stock returns (Fama-French + ESG)
    2. Carbon risk and asset pricing
    3. Factor momentum and reversal strategies

Data strategy:
    - Primary: user-yfinance (US stocks)
    - Secondary: user-tushare (A-shares)
    - Last resort: ABORT
"""

from __future__ import annotations

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class AssetPricingDirection(BaseResearchDirection):
    """Asset pricing research direction."""

    name = "资产定价"
    slug = "asset_pricing"
    description = "因子模型、ESG定价、碳风险溢价研究"
    policy_events = []

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}

        yf_result = self._fetch_via_mcp(
            "yfinance", "get_ticker_info", {"symbol": "SPY"}
        )
        if yf_result:
            data["market"] = yf_result

        ts_result = self._fetch_via_mcp(
            "tushare", "get_index_data",
            {"ts_code": "000300.SH", "start_date": "20180101", "end_date": "20240101"}
        )
        if ts_result:
            data["index"] = ts_result

        if not data:
            self._require_data_source("asset_pricing", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        if "index" in data:
            return {"df": data.get("index", []), "description": "Index from Tushare"}
        return {"df": data.get("market", {}), "description": "Market data from yfinance"}

    def run_regressions(self, panel: dict) -> dict:
        """Run FF3/FF5 factor model regressions on panel data."""
        import pandas as pd

        from scripts.factor_models import FactorModelComparison

        df = panel.get("df")
        if df is None or (isinstance(df, (list, dict)) and len(df) == 0):
            return {"status": "no_data", "tables": {}}

        if isinstance(df, pd.DataFrame) and not df.empty:
            returns_cols = [c for c in df.columns if c.lower() not in
                           ["mkt", "smb", "hml", "rmw", "cma", "date", "year", "month"]]
            factor_cols = ["MKT", "SMB", "HML"]
            available_factors = [c for c in factor_cols if c in df.columns]

            if returns_cols and available_factors:
                try:
                    comparison = FactorModelComparison()
                    returns_df = df[returns_cols]
                    factors_df = df[available_factors]
                    comparison.compare(returns_df, factors_df)
                    tables = {"r2_comparison": comparison.get_r2_comparison().to_dict()}
                    if hasattr(comparison, "get_grs_comparison"):
                        tables["grs_comparison"] = comparison.get_grs_comparison().to_dict()
                    return {"status": "success", "tables": tables}
                except Exception as e:
                    return {"status": "error", "error": str(e), "tables": {}}

        return {"status": "pending", "tables": {}}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results as LaTeX/ASCII tables."""
        import pandas as pd
        tables = reg_results.get("tables", {})
        formatted = {}
        for name, data in tables.items():
            if isinstance(data, dict) and data:
                try:
                    df = pd.DataFrame(data).T
                    formatted[f"{name}_latex"] = df.to_latex()
                    formatted[f"{name}_markdown"] = df.to_markdown()
                except Exception:
                    pass
        return formatted if formatted else {}


get_registry().register(AssetPricingDirection())
