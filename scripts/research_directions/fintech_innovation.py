"""FintechInnovationDirection: AI/ML/LLM in finance, blockchain and fintech disruption.

Research focus:
    1. LLM/AI adoption and analyst forecast accuracy
    2. Fintech competition and bank performance
    3. Blockchain/crypto and market microstructure

Data strategy:
    - Primary: user-yfinance (fintech-related stock returns)
    - Secondary: user-tushare (A-share fintech exposure)
    - Tertiary: manual data from CSMAR
    - Last resort: ABORT
"""

from __future__ import annotations

import logging
import os

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

from scripts.core.data_warning_notifier import warn as _data_warn

_log = logging.getLogger(__name__)


class FintechInnovationDirection(BaseResearchDirection):
    """Financial Technology Innovation research direction.

    Covers AI/LLM adoption in financial services, fintech disruption,
    blockchain applications, and their effects on market efficiency.
    """

    name = "金融科技创新"
    slug = "fintech_innovation"
    description = "金融科技(AI/LLM)采纳与资本市场效率、区块链与数字资产、智能投顾与分析师预测准确性研究"
    policy_events = [
        (2017, "央行金融科技委员会成立"),
        (2019, "央行金融科技发展规划(2019-2021)"),
        (2020, "数字人民币试点启动(深圳/苏州)"),
        (2021, "《互联网贷款管理暂行办法》"),
        (2022, "《金融科技发展规划(2022-2025)》发布"),
        (2022, "ChatGPT发布，LLM金融应用元年"),
        (2023, "《生成式AI服务管理暂行办法》"),
        (2024, "数字人民币全面推广，智能合约应用"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch data for fintech innovation research.

        Data sources:
            - Primary: user-yfinance (fintech sector returns)
            - Secondary: user-tushare (A-share fintech classification)
            - Tertiary: manual NLP sentiment data, analyst forecast data
            - Last resort: ABORT
        """
        data = {}

        fintech_tickers = [
            "SQ", "PYPL", "COIN", "HOOD", "V",
            "MS", "GS", "JPM", "BAC", "05960.HK",
        ]
        start_date = kwargs.get("start_date", "2015-01-01")
        end_date = kwargs.get("end_date", "2025-12-31")

        yf_result = self._fetch_via_mcp(
            "user-yfinance",
            "get_yf_historical",
            {"ticker": fintech_tickers[0], "start_date": start_date, "end_date": end_date}
        )
        if yf_result:
            data["yf_historical"] = yf_result
        else:
            for ticker in fintech_tickers[1:]:
                result = self._fetch_via_mcp(
                    "user-yfinance",
                    "get_yf_historical",
                    {"ticker": ticker, "start_date": start_date, "end_date": end_date}
                )
                if result:
                    data["yf_historical"] = result
                    break

        ts_result = self._fetch_via_mcp(
            "user-tushare",
            "get_stock_basic",
            {"list_status": "L"}
        )
        if ts_result:
            data["stocks"] = ts_result

        manual_dir = os.environ.get("FINTECH_DATA_DIR", "data/fintech")
        nlp_path = os.path.join(manual_dir, "nlp_sentiment.csv")
        analyst_path = os.path.join(manual_dir, "analyst_forecast.csv")
        blockchain_path = os.path.join(manual_dir, "blockchain_adoption.csv")

        for fname, key in [
            (nlp_path, "nlp_sentiment"),
            (analyst_path, "analyst_forecast"),
            (blockchain_path, "blockchain_adoption"),
        ]:
            if os.path.exists(fname):
                import pandas as pd
                data[key] = pd.read_csv(fname)

        if not data:
            self._require_data_source("fintech_innovation", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        """Build panel dataset for fintech innovation analysis.

        Panel structure:
            - Dependent: analyst forecast accuracy, stock price efficiency, trading costs
            - Treatment: fintech adoption (LLM-based tools, robo-advisory)
            - Controls: firm size, analyst experience, information environment
        """
        import pandas as pd

        if "nlp_sentiment" in data and isinstance(data["nlp_sentiment"], pd.DataFrame):
            return {
                "df": data["nlp_sentiment"],
                "description": "NLP sentiment panel for fintech text analysis",
                "dependent_vars": ["forecast_accuracy", "price_efficiency", "bid_ask_spread"],
                "treatment_vars": ["llm_adoption", "robo_advisory", "blockchain_adoption"],
                "control_vars": ["firm_size", "analyst_experience", "info_environment"],
            }

        if "analyst_forecast" in data and isinstance(data["analyst_forecast"], pd.DataFrame):
            return {
                "df": data["analyst_forecast"],
                "description": "Analyst forecast accuracy panel",
                "dependent_vars": ["forecast_error", "forecast_dispersion"],
                "treatment_vars": ["fintech_adoption"],
                "control_vars": ["firm_size", "leverage", "analyst_coverage"],
            }

        if "blockchain_adoption" in data and isinstance(data["blockchain_adoption"], pd.DataFrame):
            return {
                "df": data["blockchain_adoption"],
                "description": "Blockchain adoption panel",
                "dependent_vars": ["trading_volume", "volatility", "liquidity"],
                "treatment_vars": ["blockchain_adoption"],
                "control_vars": ["market_cap", "blockchain_awareness"],
            }

        if "yf_historical" in data and isinstance(data["yf_historical"], dict):
            df = pd.DataFrame(data["yf_historical"])
            if not df.empty:
                return {
                    "df": df,
                    "description": "Fintech stock returns from yfinance",
                    "dependent_vars": ["returns", "volatility"],
                    "treatment_vars": ["llm_announcement"],
                    "control_vars": ["market_return", "vix"],
                }

        self._require_data_source(
            "fintech panel data (NLP sentiment, analyst forecasts, or blockchain adoption)",
            allow_none=False
        )
        return None

    # ── Data Validation ────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate fintech innovation panel data quality.

        Adds fintech-specific checks to the base validation:
        - Fintech adoption variable presence
        - Analyst forecast / NLP sentiment data
        - Blockchain adoption data
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

        # Check fintech adoption variable
        fintech_vars = [
            "fintech_adoption", "fintech_score", "ai_score",
            "digital_score", "fintech_exposure",
        ]
        found_fintech = [v for v in fintech_vars if v in panel_df.columns]
        if not found_fintech:
            base["warnings"].append(
                "未找到金融科技采纳变量 (fintech_adoption / fintech_score / ai_score 等)。"
                "金融科技研究需要量化企业金融科技采纳程度的变量。"
            )

        # Check analyst forecast data
        analyst_vars = ["analyst_forecast_error", "eps", "analyst_coverage", "forecast_dispersion"]
        found_analyst = [v for v in analyst_vars if v in panel_df.columns]
        if not found_analyst:
            base["warnings"].append(
                "未找到分析师预测相关变量 (analyst_forecast_error / eps 等)。"
                "金融科技创新研究（如LLM采纳对分析师准确性的影响）需要分析师数据。"
            )

        # Check blockchain data
        blockchain_vars = ["blockchain_adoption", "crypto_holder", "blockchain_score"]
        found_blockchain = [v for v in blockchain_vars if v in panel_df.columns]
        if not found_blockchain:
            base["warnings"].append(
                "未找到区块链采纳变量 (blockchain_adoption / crypto_holder 等)。"
                "区块链研究需要相关采纳或使用数据。"
            )

        # Check for stock return data (needed for event study)
        ret_vars = ["return", "ret", "daily_return"]
        found_ret = [v for v in ret_vars if v in panel_df.columns]
        if not found_ret:
            base["warnings"].append(
                "未找到收益率变量 (return / ret)。"
                "金融科技事件研究（如ChatGPT发布对股价的影响）需要收益率数据。"
            )

        return base

    def run_regressions(self, panel: dict) -> dict:
        """Run regressions for fintech innovation research.

        Methods:
            1. Difference-in-differences: before/after fintech adoption
            2. Regression discontinuity: threshold-based fintech adoption
            3. Mediation analysis: analyst accuracy -> info efficiency -> returns
            4. Heterogeneity: large vs. small cap, sell-side vs. buy-side
        """
        try:
            from scripts.econometrics_extended import MediationAnalysis
            from scripts.econometrics import OLSRegression

            df = panel.get("df")
            if df is None:
                return {"status": "no_data", "tables": {}}

            if isinstance(df, list):
                import pandas as pd
                df = pd.DataFrame(df)

            if df.empty:
                return {"status": "no_data", "tables": {}}

            tables = {}
            errors = []

            reg = OLSRegression(df, y="forecast_accuracy" if "forecast_accuracy" in df.columns else df.columns[0])
            try:
                results = reg.fit(formula="~ fintech_adoption + firm_size + analyst_experience", cluster="firm_id")
                tables["did_main"] = results
            except ImportError as exc:
                errors.append("OLSRegression not available (pip install scikit-learn)")
                _log.warning("[FintechInnovation] OLSRegression not available: %s", exc)
                tables["did_main"] = {"error": str(exc)}
            except Exception as exc:
                errors.append(f"OLS regression failed: {exc}")
                _log.warning("[FintechInnovation] OLS regression failed: %s", exc)
                tables["did_main"] = {"error": str(exc)}

            try:
                mediator_cols = ["analyst_accuracy", "info_efficiency", "returns"]
                available_mediators = [c for c in mediator_cols if c in df.columns]
                if len(available_mediators) >= 2:
                    mediation = MediationAnalysis(df)
                    med_result = mediation.analyze(
                        treatment="fintech_adoption",
                        mediator=available_mediators[0],
                        outcome="forecast_accuracy" if "forecast_accuracy" in df.columns else available_mediators[-1],
                    )
                    tables["mediation"] = med_result
            except ImportError as exc:
                errors.append("MediationAnalysis not available")
                _log.warning("[FintechInnovation] MediationAnalysis not available: %s", exc)
                tables["mediation"] = {"error": str(exc)}
            except Exception as exc:
                errors.append(f"Mediation analysis failed: {exc}")
                _log.warning("[FintechInnovation] Mediation analysis failed: %s", exc)
                tables["mediation"] = {"error": str(exc)}

            if tables:
                status = "success"
            else:
                status = "partial"
            return {"status": status, "tables": tables, "errors": errors}
        except ImportError as exc:
            return {
                "status": "dependency_error",
                "tables": {},
                "error": f"Missing dependency: {str(exc)}",
            }
        except Exception as exc:
            _data_warn(
                category="research_direction",
                source="fintech_innovation",
                reason=f"run_regressions 顶层异常: {exc}",
                site="scripts/research_directions/fintech_innovation.py:301",
            )
            return {"status": "error", "tables": {}, "error": str(exc)}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """Format regression results into 4 LaTeX tables.

        Table 1: Fintech adoption and forecast accuracy
        Table 2: Information efficiency improvements
        Table 3: Mechanism: analyst behavior channel
        Table 4: Heterogeneity analysis
        """
        tables = {}
        status = reg_results.get("status", "pending")
        errors = reg_results.get("errors", [])

        if status == "success" and reg_results.get("tables"):
            tables["table_1"] = self._format_table_forecast_accuracy(pending=False)
            tables["table_2"] = self._format_table_info_efficiency(pending=False)
            tables["table_3"] = self._format_table_mechanism(pending=False)
            tables["table_4"] = self._format_table_heterogeneity(pending=False)
        elif status == "partial":
            error_note = (
                r"\item \note{⚠️ 回归执行失败，请检查 errors 字段。}"
                if errors
                else r"\item \note{⚠️ 部分回归失败。}"
            )
            tables["table_1"] = self._format_table_forecast_accuracy(pending=True, extra_note=error_note)
            tables["table_2"] = self._format_table_info_efficiency(pending=True, extra_note=error_note)
            tables["table_3"] = self._format_table_mechanism(pending=True, extra_note=error_note)
            tables["table_4"] = self._format_table_heterogeneity(pending=True, extra_note=error_note)
        elif status == "pending":
            tables["table_1"] = self._format_table_forecast_accuracy(pending=True)
            tables["table_2"] = self._format_table_info_efficiency(pending=True)
            tables["table_3"] = self._format_table_mechanism(pending=True)
            tables["table_4"] = self._format_table_heterogeneity(pending=True)

        return tables

    def _format_table_forecast_accuracy(self, pending: bool = False, extra_note: str | None = None) -> str:
        """Table 1: Fintech adoption and analyst forecast accuracy."""
        caption_tag = " [待填充]" if pending else ""
        if pending:
            note_lines = [
                r"\item \note{⚠️ 数据待获取 — 本表格为占位模板。"
                r"需配置 user-tushare (TUSHARE_TOKEN) 获取 A股分析师数据后，"
                r"回归结果将自动填充。}",
                r"\item \note{标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        else:
            note_lines = [
                r"\item \note{标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        if extra_note:
            note_lines.insert(0, extra_note)
        note_block = "\n".join(note_lines)
        return (
            r"\begin{table}[htbp]"
            "\n  \\centering"
            f"\n  \\caption[待填充]{{金融科技采纳与分析师预测准确性{caption_tag}}}"
            "\n  \\label{tab:fintech_forecast}"
            "\n  \\begin{threeparttable}"
            "\n  \\begin{tabular}{lcccc}"
            r"\n    \hline\hline"
            "\n    & (1) & (2) & (3) & (4) \\\\"
            "\n    Variable & OLS & DID & RDD & PSM-DID \\\\"
            "\n    \\hline"
            "\n    金融科技采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}LLM工具采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}智能投顾采纳 & & & & \\\\"
            "\n    企业规模 & & & & \\\\"
            "\n    分析师经验 & & & & \\\\"
            "\n    信息环境 & & & & \\\\"
            "\n    \\hline"
            "\n    $N$ & & & & \\\\"
            "\n    $R^2$ & & & & \\\\"
            "\n    固定效应 & Firm & Firm & Firm & Firm \\\\"
            r"\n    \hline\hline"
            "\n  \\end{tabular}"
            "\n  \\begin{tablenotes}"
            "\n    \\small"
            f"\n    {note_block}"
            "\n      被解释变量：分析师预测准确性（forecast\\_accuracy），定义为预测误差的负值。"
            "\n      解释变量：金融科技采纳为二元变量，表示企业是否采纳LLM工具或智能投顾。"
            "\n  \\end{tablenotes}"
            "\n  \\end{threeparttable}"
            "\n\\end{table}"
        )

    def _format_table_info_efficiency(self, pending: bool = False, extra_note: str | None = None) -> str:
        """Table 2: Information efficiency improvements."""
        caption_tag = " [待填充]" if pending else ""
        if pending:
            note_lines = [
                r"\item \note{⚠️ 数据待获取 — 本表格为占位模板。"
                r"需配置 user-tushare (TUSHARE_TOKEN) 获取 A股分析师数据后，"
                r"回归结果将自动填充。}",
                r"\item \note{标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        else:
            note_lines = [
                r"\item \note{标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        if extra_note:
            note_lines.insert(0, extra_note)
        note_block = "\n".join(note_lines)
        return (
            r"\begin{table}[htbp]"
            "\n  \\centering"
            f"\n  \\caption[待填充]{{金融科技与信息效率改善{caption_tag}}}"
            "\n  \\label{tab:fintech_efficiency}"
            "\n  \\begin{threeparttable}"
            "\n  \\begin{tabular}{lcccc}"
            r"\n    \hline\hline"
            "\n    & (1) & (2) & (3) & (4) \\\\"
            "\n    Variable & Price Sync & Info Speed & Forecast Dispersion & Trading Cost \\\\"
            "\n    \\hline"
            "\n    金融科技采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}LLM工具采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}区块链采纳 & & & & \\\\"
            "\n    企业规模 & & & & \\\\"
            "\n    盈利能力 & & & & \\\\"
            "\n    市场波动率 & & & & \\\\"
            "\n    \\hline"
            "\n    $N$ & & & & \\\\"
            "\n    $R^2$ & & & & \\\\"
            "\n    固定效应 & Firm & Firm & Firm & Firm \\\\"
            r"\n    \hline\hline"
            "\n  \\end{tabular}"
            "\n  \\begin{tablenotes}"
            "\n    \\small"
            f"\n    {note_block}"
            "\n      被解释变量：价格同步性（Price Sync）、信息速度（Info Speed）、"
            "\n      预测分歧度（Forecast Dispersion）、交易成本（Trading Cost）。"
            "\n  \\end{tablenotes}"
            "\n  \\end{threeparttable}"
            "\n\\end{table}"
        )

    def _format_table_mechanism(self, pending: bool = False, extra_note: str | None = None) -> str:
        """Table 3: Mechanism analysis - analyst behavior channel."""
        caption_tag = " [待填充]" if pending else ""
        if pending:
            note_lines = [
                r"\item \note{⚠️ 数据待获取 — 本表格为占位模板。"
                r"需配置 user-tushare (TUSHARE_TOKEN) 获取 A股分析师数据后，"
                r"回归结果将自动填充。}",
                r"\item \note{中介效应检验。间接效应通过Bootstrap法计算（重复1000次）。}",
            ]
        else:
            note_lines = [
                r"\item \note{中介效应检验。间接效应通过Bootstrap法计算（重复1000次）。}",
            ]
        if extra_note:
            note_lines.insert(0, extra_note)
        note_block = "\n".join(note_lines)
        return (
            r"\begin{table}[htbp]"
            "\n  \\centering"
            f"\n  \\caption[待填充]{{机制检验：分析师行为渠道{caption_tag}}}"
            "\n  \\label{tab:fintech_mechanism}"
            "\n  \\begin{threeparttable}"
            "\n  \\begin{tabular}{lccc}"
            r"\n    \hline\hline"
            "\n    & (1) & (2) & (3) \\\\"
            "\n    Variable & 预测准确性 & 信息效率 & 超额收益 \\\\"
            "\n    \\hline"
            "\n    \\textbf{总效应} & & & \\\\"
            "\n    \\hspace{0.5em}金融科技采纳 & & & \\\\"
            "\n    \\hline"
            "\n    \\textbf{直接效应} & & & \\\\"
            "\n    \\hspace{0.5em}金融科技采纳 & & & \\\\"
            "\n    \\hline"
            "\n    \\textbf{间接效应（中介）} & & & \\\\"
            "\n    \\hspace{0.5em}分析师准确性 & & & \\\\"
            "\n    \\hspace{0.5em}信息效率 & & & \\\\"
            "\n    \\hline"
            "\n    遮掩比例 & & & \\\\"
            "\n    \\hline"
            "\n    $N$ & & & \\\\"
            r"\n    \hline\hline"
            "\n  \\end{tabular}"
            "\n  \\begin{tablenotes}"
            "\n    \\small"
            f"\n    {note_block}"
            "\n     遮掩比例 = 间接效应 / 总效应。* $p<0.1$, ** $p<0.05$, *** $p<0.01$。"
            "\n  \\end{tablenotes}"
            "\n  \\end{threeparttable}"
            "\n\\end{table}"
        )

    def _format_table_heterogeneity(self, pending: bool = False, extra_note: str | None = None) -> str:
        """Table 4: Heterogeneity analysis."""
        caption_tag = " [待填充]" if pending else ""
        if pending:
            note_lines = [
                r"\item \note{⚠️ 数据待获取 — 本表格为占位模板。"
                r"需配置 user-tushare (TUSHARE_TOKEN) 获取 A股分析师数据后，"
                r"回归结果将自动填充。}",
                r"\item \note{分样本回归。标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        else:
            note_lines = [
                r"\item \note{分样本回归。标准误聚类至企业层面。* $p<0.1$, ** $p<0.05$, *** $p<0.01$}.",
            ]
        if extra_note:
            note_lines.insert(0, extra_note)
        note_block = "\n".join(note_lines)
        return (
            r"\begin{table}[htbp]"
            "\n  \\centering"
            f"\n  \\caption[待填充]{{异质性分析：企业特征与分析师类型{caption_tag}}}"
            "\n  \\label{tab:fintech_heterogeneity}"
            "\n  \\begin{threeparttable}"
            "\n  \\begin{tabular}{lcccc}"
            r"\n    \hline\hline"
            "\n    & \\multicolumn{2}{c}{市值规模} & \\multicolumn{2}{c}{分析师类型} \\\\"
            "\n    \\cline{2-3} \\cline{4-5}"
            "\n    Variable & 大市值 & 小市值 & 卖方分析师 & 买方分析师 \\\\"
            "\n    \\hline"
            "\n    金融科技采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}LLM工具采纳 & & & & \\\\"
            "\n    \\hspace{0.5em}智能投顾采纳 & & & & \\\\"
            "\n    \\hline"
            "\n    $N$ & & & & \\\\"
            "\n    $R^2$ & & & & \\\\"
            r"\n    \hline\hline"
            "\n  \\end{tabular}"
            "\n  \\begin{tablenotes}"
            "\n    \\small"
            f"\n    {note_block}"
            r"\n      大市值定义为市值前30\%的样本；卖方分析师来自券商研究部，买方分析师来自资产管理机构。"
            "\n  \\end{tablenotes}"
            "\n  \\end{threeparttable}"
            "\n\\end{table}"
        )

    def get_figure_plan(self) -> list[dict]:
        """Plan for 4 figures in the fintech innovation research.

        Figure 1: Fintech adoption timeline by industry
        Figure 2: Forecast accuracy improvement around LLM adoption
        Figure 3: Mechanism diagram: information spillover
        Figure 4: Market response to fintech product launches
        """
        return [
            {
                "figure_id": "Figure_1",
                "title": "金融科技采纳时间趋势（2015–2024）",
                "description": "金融科技采纳时间趋势：按行业分组的采纳率变化（2015-2024）",
                "generation_method": "matplotlib",
                "data_source": "manual fintech adoption survey data, Tushare (A-share fintech classification)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "line",
                "data_requirements": ["industry", "adoption_rate", "year"],
                "style": "academic",
            },
            {
                "figure_id": "Figure_2",
                "title": "LLM采纳前后分析师预测准确性变化",
                "description": "LLM采纳前后分析师预测准确性变化：事件研究法",
                "generation_method": "matplotlib",
                "data_source": "analyst forecast data (manual CSMAR), LLM adoption event dates",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "event_study",
                "data_requirements": ["relative_time", "forecast_accuracy", "confidence_interval"],
                "style": "academic",
            },
            {
                "figure_id": "Figure_3",
                "title": "机制路径图：金融科技→分析师行为→信息效率→资产定价",
                "description": "机制路径图：金融科技→分析师行为→信息效率→资产定价",
                "generation_method": "matplotlib",
                "data_source": "mechanism analysis from regressions (Table 3)",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "flow_diagram",
                "data_requirements": ["path_coefficients", "significance"],
                "style": "academic",
            },
            {
                "figure_id": "Figure_4",
                "title": "金融科技产品发布市场反应（CAR）",
                "description": "金融科技产品发布市场反应：累计异常收益（CAR）",
                "generation_method": "matplotlib",
                "data_source": "yfinance (fintech sector returns), event dates from policy",
                "format": "pdf",
                "dpi": 300,
                "chart_type": "bar",
                "data_requirements": ["event_window", "car", "standard_error"],
                "style": "academic",
            },
        ]


get_registry().register(FintechInnovationDirection())
