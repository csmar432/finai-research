"""GreenFinanceDirection: Green credit policy and ESG research direction.

Research focus:
    1. Green credit guidance policy effects (DID)
    2. ESG and financing constraints (cross-sectional)
    3. Green bond issuance and cost of capital

Data strategy:
    - Primary: user-tushare (A-share financials, requires TUSHARE_TOKEN)
    - Secondary: user-financial (macro indicators)
    - Tertiary: Published benchmarks (CSMAR, Wind)
    - Last resort: ABORT with clear error (never silently mock)
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class GreenFinanceDirection(BaseResearchDirection):
    """
    Green finance research direction.

    Covers:
        - Green credit policy event studies (China, 2012银监会指引)
        - ESG investment and financing constraints
        - Carbon trading and corporate performance
    """

    name = "绿色金融"
    slug = "green_finance"
    description = "绿色信贷政策效应、ESG与融资约束、绿色债券研究"
    policy_events = [(2012, "银监会绿色信贷指引")]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch data from MCP tools."""
        data: dict = {}

        # 1. Try Tushare for A-share financials
        ts_result = self._fetch_via_mcp(
            "tushare", "get_stock_basic",
            {"list_status": "L"}
        )
        if ts_result:
            data["stocks"] = ts_result

        # 2. Try financial MCP for macro data
        macro_result = self._fetch_via_mcp(
            "financial", "get_macro_china",
            {"indicator": "gdp"}
        )
        if macro_result:
            data["macro"] = macro_result

        # 3. Check for manual data files
        manual_dir = os.environ.get("GREEN_FINANCE_DATA_DIR", "data/green_finance")
        panel_path = os.path.join(manual_dir, "green_credit_panel.csv")
        if os.path.exists(panel_path):
            import pandas as pd
            data["panel"] = pd.read_csv(panel_path)

        # No data at all — abort
        if not data:
            self._require_data_source("green_finance", allow_none=False)
            return None

        return data

    def build_panel(self, data: dict) -> dict | None:
        """Build panel dataset from fetched data."""
        if "panel" in data:
            return {"df": data["panel"], "description": "Loaded from CSV"}

        if "stocks" not in data:
            self._require_data_source("A-share stock data", allow_none=False)
            return None

        return {
            "df": data.get("stocks", []),
            "description": "Panel constructed from MCP data",
        }

    def run_regressions(self, panel: dict) -> dict:
        """Run DID regressions."""
        try:
            from scripts.econometrics import DIDRegression
            df = panel.get("df", [])
            if not isinstance(df, list) or len(df) == 0:
                return {"status": "no_data", "tables": {}}
            import pandas as pd
            df = pd.DataFrame(df)
            did = DIDRegression(
                data=df,
                y="y",
                treatment="treat",
                post="post",
                treated_groups=["treated_bank_001", "treated_bank_002"],
                post_period="2012",
            )
            results = did.fit(cluster="firm_id")
            return {"status": "success", "tables": {"did_main": results}}
        except ImportError:
            return {
                "status": "import_error",
                "tables": {},
                "error": "statsmodels not available"
            }
        except Exception as exc:
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results as LaTeX."""
        tables = {}
        if reg_results.get("status") == "success":
            tables["did_main"] = self._format_did_table(reg_results)
        return tables

    def _format_did_table(self, results: dict) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Green Credit Policy Effect (DID)}
  \begin{tabular}{lcc}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    DID & \\\\
    Controls & \\\\
    \hline
    $N$ & \\\\
    $R^2$ & \\\\
    Firm FE & \checkmark & \checkmark \\
    Year FE & \checkmark & \checkmark \\
    \hline
    \hline
  \end{tabular}
  \note{Standard errors in parentheses, clustered at firm level.%
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.}
\end{table}"""

    def get_figure_plan(self) -> list[dict]:
        return [
            {
                "figure_id": "Figure_1",
                "description": "Event study: Green credit policy effect over time",
                "generation_method": "matplotlib",
            },
            {
                "figure_id": "Figure_2",
                "description": "Coefficient plot: Heterogeneity analysis",
                "generation_method": "matplotlib",
            },
        ]


# Auto-register
get_registry().register(GreenFinanceDirection())
