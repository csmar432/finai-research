"""CorporateFinanceDirection: Capital structure, M&A and corporate governance.

Research focus:
    1. Capital structure adjustment speed
    2. M&A performance and governance effects
    3. ESG and corporate financial decisions

Data strategy:
    - Primary: user-tushare (A-share financials)
    - Secondary: user-financial (macro)
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class CorporateFinanceDirection(BaseResearchDirection):
    """Corporate finance research direction."""

    name = "公司金融"
    slug = "corporate_finance"
    description = "资本结构、并购绩效、公司治理研究"
    policy_events = [
        (2015, "并购重组市场化改革"),
        (2020, "注册制改革"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}

        ts_result = self._fetch_via_mcp(
            "tushare", "get_financial_report",
            {"ts_code": kwargs.get("ts_code", "000001.SZ"), "start_date": "20180101"}
        )
        if ts_result:
            data["financials"] = ts_result

        manual_dir = os.environ.get("CORP_FINANCE_DATA_DIR", "data/corp_finance")
        panel_path = os.path.join(manual_dir, "corp_finance_panel.csv")
        if os.path.exists(panel_path):
            import pandas as pd
            data["panel"] = pd.read_csv(panel_path)

        if not data:
            self._require_data_source("corporate_finance", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        if "panel" in data:
            return {"df": data["panel"], "description": "Loaded from CSV"}
        if "financials" in data:
            return {"df": data.get("financials", []), "description": "From Tushare"}
        self._require_data_source("financial data", allow_none=False)
        return None

    def run_regressions(self, panel: dict) -> dict:
        try:
            from scripts.econometrics import OLSRegression
            df = panel.get("df", [])
            if not isinstance(df, list) or len(df) == 0:
                return {"status": "no_data", "tables": {}}
            import pandas as pd
            df = pd.DataFrame(df)
            reg = OLSRegression(df, y="lev")
            results = reg.fit(formula="lev ~ esg + size + roe + tangibility", cluster="firm_id")
            return {"status": "success", "tables": {"capital_structure": results}}
        except Exception as exc:
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        tables = {}
        if reg_results.get("status") == "success":
            tables["capital_structure"] = self._cs_table()
        return tables

    def _cs_table(self) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Capital Structure and ESG}
  \begin{tabular}{lcc}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    ESG & \\\\
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
            {"figure_id": "Figure_1", "description": "Capital structure trend by ESG group",
             "generation_method": "matplotlib"},
        ]


get_registry().register(CorporateFinanceDirection())
