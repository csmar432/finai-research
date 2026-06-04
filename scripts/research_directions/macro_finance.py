"""MacroFinanceDirection: Monetary policy, banking and macroeconomics.

Research focus:
    1. Monetary policy transmission
    2. Bank performance and competition
    3. Macro-financial linkages

Data strategy:
    - Primary: user-financial (global macro via FRED)
    - Secondary: user-eodhd (macro indicators)
    - Tertiary: manual data
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class MacroFinanceDirection(BaseResearchDirection):
    """Macro-finance research direction."""

    name = "宏观金融"
    slug = "macro_finance"
    description = "货币政策传导、银行竞争、宏观金融关联研究"
    policy_events = [
        (2015, "利率市场化改革完成"),
        (2019, "LPR改革"),
        (2022, "美联储加息周期"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}

        # Try FRED data via financial MCP
        fred_result = self._fetch_via_mcp(
            "financial", "get_macro_usa", {"indicator": "FEDFUNDS"}
        )
        if fred_result:
            data["rates"] = fred_result

        china_result = self._fetch_via_mcp(
            "financial", "get_macro_china", {"indicator": "gdp"}
        )
        if china_result:
            data["china"] = china_result

        manual_dir = os.environ.get("MACRO_DATA_DIR", "data/macro_finance")
        panel_path = os.path.join(manual_dir, "macro_panel.csv")
        if os.path.exists(panel_path):
            import pandas as pd
            data["panel"] = pd.read_csv(panel_path)

        if not data:
            self._require_data_source("macro_finance", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        if "panel" in data:
            return {"df": data["panel"], "description": "Loaded from CSV"}
        return {"df": data.get("rates", {}), "description": "Macro data from FRED"}

    def run_regressions(self, panel: dict) -> dict:
        try:
            from scripts.econometrics import OLSRegression
            df = panel.get("df", [])
            if not isinstance(df, list) or len(df) == 0:
                return {"status": "no_data", "tables": {}}
            import pandas as pd
            df = pd.DataFrame(df)
            reg = OLSRegression(df, y="y")
            results = reg.fit(formula="y ~ mp_shock", cluster="bank_id")
            return {"status": "success", "tables": {"mp_transmission": results}}
        except Exception as exc:
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        tables = {}
        if reg_results.get("status") == "success":
            tables["mp_transmission"] = self._mp_table()
        return tables

    def _mp_table(self) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Monetary Policy Transmission}
  \begin{tabular}{lcc}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    MP Shock & \\\\
    Controls & \\\\
    \hline
    $N$ & \\\\
    $R^2$ & \\\\
    \hline\hline
  \end{tabular}
  \note{Standard errors in parentheses.%
    * $p<0.1$, ** $p<0.05$, *** $p<0.01$.}
\end{table}"""

    def get_figure_plan(self) -> list[dict]:
        return [
            {"figure_id": "Figure_1", "description": "Impulse response function",
             "generation_method": "matplotlib"},
        ]


get_registry().register(MacroFinanceDirection())
