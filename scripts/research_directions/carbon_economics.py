"""CarbonEconomicsDirection: Carbon trading, climate risk and green innovation.

Research focus:
    1. Carbon trading pilot effects on firm emissions
    2. Climate risk and corporate investment
    3. Green innovation incentives under carbon pricing

Data strategy:
    - Primary: manual CSMAR / Wind data
    - Secondary: user-financial (macro)
    - Last resort: ABORT
"""

from __future__ import annotations

import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class CarbonEconomicsDirection(BaseResearchDirection):
    """Carbon economics research direction."""

    name = "碳经济学"
    slug = "carbon_economics"
    description = "碳交易试点效应、气候风险、绿色创新激励研究"
    policy_events = [
        (2011, "发改委碳交易试点启动"),
        (2013, "北京/上海/深圳碳交易启动"),
        (2017, "全国碳交易市场启动"),
        (2021, "全国碳市场正式上线"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}

        macro_result = self._fetch_via_mcp(
            "financial", "get_macro_china", {"indicator": "gdp"}
        )
        if macro_result:
            data["macro"] = macro_result

        manual_dir = os.environ.get("CARBON_DATA_DIR", "data/carbon")
        panel_path = os.path.join(manual_dir, "carbon_panel.csv")
        if os.path.exists(panel_path):
            import pandas as pd
            data["panel"] = pd.read_csv(panel_path)

        if not data:
            self._require_data_source("carbon_economics", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        if "panel" in data:
            return {"df": data["panel"], "description": "Loaded from CSV"}
        self._require_data_source("carbon panel data", allow_none=False)
        return None

    def run_regressions(self, panel: dict) -> dict:
        try:
            from scripts.econometrics import DIDRegression
            df = panel.get("df", [])
            if not isinstance(df, list) or len(df) == 0:
                return {"status": "no_data", "tables": {}}
            import pandas as pd
            df = pd.DataFrame(df)
            did = DIDRegression(
                data=df,
                y="emissions",
                treatment="treat",
                post="post",
                treated_groups=["treated_firm_001", "treated_firm_002"],
                post_period="2017",
            )
            results = did.fit(cluster="firm_id")
            return {"status": "success", "tables": {"carbon_did": results}}
        except Exception as exc:
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        tables = {}
        if reg_results.get("status") == "success":
            tables["carbon_did"] = self._carbon_did_table()
        return tables

    def _carbon_did_table(self) -> str:
        return r"""\begin{table}[htbp]
  \centering
  \caption{Carbon Trading and Firm Emissions (DID)}
  \begin{tabular}{lcc}
    \hline\hline
    Variable & (1) & (2) \\
    \hline
    DID & \\\\
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
            {"figure_id": "Figure_1", "description": "Carbon price trend",
             "generation_method": "matplotlib"},
            {"figure_id": "Figure_2", "description": "Event study: emissions around carbon trading",
             "generation_method": "matplotlib"},
        ]


get_registry().register(CarbonEconomicsDirection())
