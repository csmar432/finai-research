"""DigitalFinanceDirection: Fintech, digital finance and financial inclusion.

Research focus:
    1. Digital finance penetration and financial inclusion
    2. Fintech competition and bank performance
    3. E-commerce platforms and SME financing

Data strategy:
    - Primary: user-tushare (A-share financials)
    - Secondary: user-financial (macro indicators)
    - Tertiary: manual CSMAR data
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class DigitalFinanceDirection(BaseResearchDirection):
    """Digital finance research direction."""

    name = "数字金融"
    slug = "digital_finance"
    description = "数字金融普及、金融包容性、金融科技竞争研究"
    policy_events = [
        (2015, "国务院推进互联网+行动"),
        (2016, "G20数字普惠金融原则"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}

        ts_result = self._fetch_via_mcp(
            "tushare", "get_stock_basic", {"list_status": "L"}
        )
        if ts_result:
            data["stocks"] = ts_result

        manual_dir = os.environ.get("DIGITAL_FINANCE_DATA_DIR", "data/digital_finance")
        panel_path = os.path.join(manual_dir, "digital_finance_panel.csv")
        if os.path.exists(panel_path):
            import pandas as pd
            data["panel"] = pd.read_csv(panel_path)

        if not data:
            self._require_data_source("digital_finance", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        if "panel" in data:
            return {"df": data["panel"], "description": "Loaded from CSV"}
        if "stocks" not in data:
            self._require_data_source("A-share stock data", allow_none=False)
            return None
        return {"df": data.get("stocks", []), "description": "Panel from MCP"}

    def run_regressions(self, panel: dict) -> dict:
        try:
            from scripts.econometrics import OLSRegression
            df = panel.get("df", [])
            if not isinstance(df, list) or len(df) == 0:
                return {"status": "no_data", "tables": {}}
            import pandas as pd
            df = pd.DataFrame(df)
            reg = OLSRegression(df, y="y")
            results = reg.fit(formula="y ~ x1 + x2", cluster="firm_id")
            return {"status": "success", "tables": {"ols_main": results}}
        except Exception as exc:
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        tables = {}
        if reg_results.get("status") == "success":
            tables["ols_main"] = self._format_ols_table()
        return tables

    def _format_ols_table(self) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Digital Finance and Firm Performance}
  \begin{tabular}{lcc}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    Digital Finance Index & \\\\
    Controls & \\\\
    \hline
    $N$ & \\\\
    $R^2$ & \\\\
    \hline\hline
  \end{tabular}
  \note{Standard errors in parentheses, clustered at firm level.%
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.}
\end{table}"""

    def get_figure_plan(self) -> list[dict]:
        return [
            {"figure_id": "Figure_1", "description": "Digital finance index trend",
             "generation_method": "matplotlib"},
            {"figure_id": "Figure_2", "description": "Coefficient plot: heterogeneity",
             "generation_method": "matplotlib"},
        ]


get_registry().register(DigitalFinanceDirection())
