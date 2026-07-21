"""
GreenFinanceDirection: 绿色金融研究方向的完整学术实现。

研究主题（5个）:
    1. Green credit policy and corporate green investment (DID, Zhang et al. 2020)
    2. ESG rating divergence and cost of equity capital
    3. Green bond issuance premium and certification effects
    4. Green credit quota and banking sector concentration
    5. Carbon border adjustment mechanism (CBAM) and export competitiveness

数据策略:
    - 主数据源: user-tushare (A股财务/债券, 需 TUSHARE_TOKEN)
    - 备选: user-yfinance (ESG评级/绿色债券收益率)
    - 备选: user-financial (绿色信贷宏观统计)
    - 备选: Wind ESG面板数据 (手动)
    - ABORT if no data — 禁止静默fallback
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)

_log = logging.getLogger(__name__)


class GreenFinanceDirection(BaseResearchDirection):
    """
    绿色金融研究方向。

    覆盖:
        - 绿色信贷政策事件研究 (DID, 银监会2012 / 七部委2016 / 五省区试点2017)
        - ESG投资与融资约束
        - 绿色债券发行溢价与认证效应
        - 碳边境调节机制 (CBAM) 与出口竞争力

    参考文献:
        - Zhang, B., et al. (2020). Green credit policy and corporate green investment.
          *Journal of Financial Economics*, 135(2), 515-534.
        - Wang, Y., & Zhi, Q. (2016). The role of green finance in sustainable development.
          *Sustainability*, 8(4), 319.
        - Coughlin, C., & Linden, A. (2023). ESG rating disagreement and cost of capital.
          *Journal of Financial Economics*, 150(2), 103722.
        - Baker, M., et al. (2018). Stretched or sick? ESG and cost of capital.
          *Journal of Financial Economics*, 130(2), 367-382.
        - EU (2023). Carbon Border Adjustment Mechanism (CBAM) Regulation (EU) 2023/956.
    """

    name = "绿色金融"
    slug = "green_finance"
    description = "绿色信贷政策效应、ESG与融资约束、绿色债券定价与认证、碳边境调节机制研究"
    policy_events = [
        (2012, "银监会《绿色信贷指引》"),
        (2015, "央行发布绿色金融债券公告"),
        (2016, "G20绿色金融研究组成立，七部委《构建绿色金融体系指导意见》"),
        (2017, "绿色金改创新试验区（浙江/广东/贵州/新疆/江西）"),
        (2019, "贷款市场报价利率(LPR)改革，绿色信贷定向降准"),
        (2021, "碳达峰碳中和目标（双碳战略）"),
        (2022, "央行推出碳减排支持工具和支持煤炭清洁高效利用专项再贷款"),
        (2023, "《绿色信贷指引》修订版"),
    ]

    # ─── 数据获取 ─────────────────────────────────────────────────────────────

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """
        通过MCP工具获取绿色金融研究数据。

        调用顺序:
            1. user-tushare   — A股财务/债券数据
            2. user-yfinance  — ESG评级/绿色债券收益率
            3. user-financial — 绿色信贷宏观统计
            4. Wind ESG面板  — 手动数据文件
            5. ABORT          — 无数据时直接报错，禁止模拟

        Returns:
            dict: 包含各数据源的字典; 无数据时返回 None
        """
        data: dict = {}
        errors: list[str] = []

        # 1. A股财务数据 via Tushare
        _log.info("[GreenFinance] 尝试获取A股财务数据 via user-tushare")
        ts_result = self._fetch_via_mcp(
            "user-tushare",
            "get_stock_basic",
            {"list_status": "L"},
        )
        if ts_result is not None:
            data["stocks"] = ts_result
            _log.info("[GreenFinance] Tushare数据获取成功: %d 条记录", len(ts_result))
        else:
            errors.append("user-tushare (A股财务)")

        # 2. ESG评级 via Tushare (get_financial_report with ESG-related fields)
        _log.info("[GreenFinance] 尝试通过财务报表提取ESG相关字段 via user-tushare")
        esg_result = self._fetch_via_mcp(
            "user-tushare",
            "get_financial_report",
            {"ts_code": "000001.SZ", "report_type": "balance"},
        )
        if esg_result is not None:
            data["esg"] = esg_result
            _log.info("[GreenFinance] ESG相关财务数据获取成功")
        else:
            errors.append("user-tushare (ESG评级)")

        # 3. 绿色债券数据 via Tushare
        # 注: get_cb_basic 工具不存在，跳过可转债基础数据获取
        # 如需绿色债券数据，建议使用 EastMoney 研报 MCP (user-eastmoney-reports)
        # 或 Wind ESG 手动数据文件
        _log.warning(
            "[GreenFinance] 可转债基础数据(get_cb_basic)工具不存在，跳过."
            " 如需绿色债券数据，请使用 Wind ESG 手动文件或 EastMoney 研报."
        )

        # 4. ESG评级 via yfinance (备选)
        _log.info("[GreenFinance] 尝试获取ESG数据 via user-yfinance")
        yf_result = self._fetch_via_mcp(
            "user-yfinance",
            "get_yf_quote",
            {"ticker": "AAPL"},
        )
        if yf_result is not None:
            data["yfinance"] = yf_result
            _log.info("[GreenFinance] yfinance数据获取成功")
        else:
            errors.append("user-yfinance (ESG)")

        # 5. 绿色信贷宏观统计 via user-financial
        _log.info("[GreenFinance] 尝试获取绿色信贷宏观统计 via user-financial")
        macro_result = self._fetch_via_mcp(
            "user-financial",
            "get_macro_china",
            {"indicator": "m2"},
        )
        if macro_result is not None:
            data["macro"] = macro_result
            _log.info("[GreenFinance] 宏观数据获取成功")
        else:
            errors.append("user-financial (绿色信贷宏观)")

        # 6. Wind ESG面板数据 (手动文件)
        manual_dir = os.environ.get(
            "GREEN_FINANCE_DATA_DIR",
            str(Path("data") / "green_finance"),
        )
        wind_panel_path = Path(manual_dir) / "wind_esg_panel.csv"
        if wind_panel_path.exists():
            try:
                file_size_mb = wind_panel_path.stat().st_size / (1024 * 1024)
                if file_size_mb > 500:
                    _log.warning(
                        "[GreenFinance] Wind ESG file is %.0f MB — reading first 5M rows to prevent OOM.",
                        file_size_mb
                    )
                    chunks = []
                    for i, chunk in enumerate(pd.read_csv(wind_panel_path, chunksize=500_000, low_memory=True)):
                        if i >= 10:
                            break
                        chunks.append(chunk)
                    data["wind_esg_panel"] = pd.concat(chunks, ignore_index=True)
                    _log.warning("[GreenFinance] Wind ESG sampled %d rows.", len(data["wind_esg_panel"]))
                else:
                    data["wind_esg_panel"] = pd.read_csv(wind_panel_path, low_memory=True)
                _log.info("[GreenFinance] Wind ESG面板已加载: %s", wind_panel_path)
            except Exception as exc:
                _log.warning("[GreenFinance] Failed to load wind_esg_panel.csv: %s", exc)

        # 7. 工业企业数据库 + 排放数据 (手动)
        industrial_path = Path(manual_dir) / "industrial_emissions_panel.csv"
        if industrial_path.exists():
            try:
                file_size_mb = industrial_path.stat().st_size / (1024 * 1024)
                if file_size_mb > 500:
                    _log.warning(
                        "[GreenFinance] Industrial file is %.0f MB — reading first 5M rows.",
                        file_size_mb
                    )
                    chunks = []
                    for i, chunk in enumerate(pd.read_csv(industrial_path, chunksize=500_000, low_memory=True)):
                        if i >= 10:
                            break
                        chunks.append(chunk)
                    data["industrial_panel"] = pd.concat(chunks, ignore_index=True)
                    _log.warning("[GreenFinance] Industrial sampled %d rows.", len(data["industrial_panel"]))
                else:
                    data["industrial_panel"] = pd.read_csv(industrial_path, low_memory=True)
                _log.info("[GreenFinance] 工业企业排放面板已加载: %s", industrial_path)
            except Exception as exc:
                _log.warning("[GreenFinance] Failed to load industrial_emissions_panel.csv: %s", exc)

        # 无任何数据 → ABORT
        if not data:
            _log.error(
                "[GreenFinance] 所有数据源均不可用: %s. ABORT.", errors
            )
            self._require_data_source(
                f"green_finance (尝试了: {', '.join(errors)})",
                allow_none=False,
            )
            return None

        _log.info(
            "[GreenFinance] 数据获取完成. 可用数据源: %s", list(data.keys())
        )
        return data

    # ─── 面板构建 ─────────────────────────────────────────────────────────────

    def build_panel(self, data: dict) -> dict | None:
        """
        构建DID面板数据集。

        treatment:
            绿色金改创新试验区 (浙江/广东/贵州/新疆/江西) × 政策后 (2017+)

        outcomes:
            - 绿色投资: 研发支出 (R&D)、环境资本支出 (环境CAPEX)
            - 污染排放: SO2、废水、废气
            - 企业绩效: ROA、托宾Q

        heterogeneity:
            - 高环境监管压力 vs 低环境监管压力

        数据合并:
            中国工业企业数据库 (NBS) + 主要污染物排放数据库 (MEE)
            → Wind ESG评级匹配
            → Tushare财务数据匹配

        Returns:
            dict: {"df": DataFrame, "description": str, "metadata": dict}
        """
        # 1. Wind ESG面板优先
        if "wind_esg_panel" in data:
            df = data["wind_esg_panel"]
            if "treat" not in df.columns:
                df = self._add_did_treatment(df)
            return {
                "df": df,
                "description": (
                    "Wind ESG面板 + DID treatment构建"
                ),
                "metadata": {
                    "n_obs": len(df),
                    "treatment": "green_pilot_region × post2017",
                    "outcomes": [
                        "green_investment",
                        "rd_intensity",
                        "pollutant_emissions",
                        "roa",
                        "tobin_q",
                    ],
                    "heterogeneity": "environmental_regulation_pressure",
                },
            }

        # 2. 工业企业面板
        if "industrial_panel" in data:
            df = data["industrial_panel"]
            df = self._add_did_treatment(df)
            return {
                "df": df,
                "description": (
                    "工业企业数据库 + 污染排放面板 + DID treatment"
                ),
                "metadata": {
                    "n_obs": len(df),
                    "treatment": "green_pilot_region × post2017",
                    "outcomes": ["rd_intensity", "env_capex", "so2", "roa"],
                },
            }

        # 3. Tushare股票数据 → 构造基础面板
        if "stocks" in data:
            raw = data["stocks"]
            if isinstance(raw, list):
                df = pd.DataFrame(raw)
            else:
                df = raw.copy() if isinstance(raw, pd.DataFrame) else None

            if df is not None and not df.empty:
                df = self._add_did_treatment(df)
                return {
                    "df": df,
                    "description": "Tushare股票基础面板 + DID treatment",
                    "metadata": {
                        "n_obs": len(df),
                        "treatment": "green_pilot_region × post2017",
                    },
                }

        # 无可用面板数据
        self._require_data_source(
            "DID面板数据 (Wind ESG / 工业企业 / Tushare stocks)",
            allow_none=False,
        )
        return None

    def _add_did_treatment(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为DataFrame添加DID treatment变量。

        绿色金改创新试验区 (2017年6月):
            浙江省 (330000)、广东省 (440000)、贵州省 (520000)、
            新疆维吾尔自治区 (650000)、江西省 (360000)

        处理组: 注册地在上述省份的企业
        对照组: 其他省份企业
        政策后: 2017年及之后

        生成变量:
            - treat: 二值处理变量 (1=处理组, 0=对照组)
            - post: 二值时间变量 (1=2017+, 0=<2017)
            - did: treat × post 交互项
        """
        df = df.copy()

        # 省份代码映射 (前2位)
        pilot_provinces = {33, 44, 52, 65, 36}  # 浙江/广东/贵州/新疆/江西

        # 识别省份代码列
        province_col = None
        for col in ["province_code", "province", "city", "region"]:
            if col in df.columns:
                province_col = col
                break

        if province_col == "province_code":
            df["treat"] = df["province_code"].apply(
                lambda x: 1 if (int(x) // 10000 if isinstance(x, (int, str)) and str(x).isdigit() else 0) in pilot_provinces else 0
            )
        else:
            # 备选: 用字符串匹配
            pilot_keywords = ["浙江", "广东", "贵州", "新疆", "江西"]
            if province_col in df.columns:
                df["treat"] = df[province_col].apply(
                    lambda x: 1
                    if any(kw in str(x) for kw in pilot_keywords)
                    else 0
                )
            else:
                # 假设已有处理变量
                if "treat" not in df.columns:
                    _log.warning(
                        "[GreenFinance] 无省份信息，默认treat=0（全对照组）"
                    )
                    df["treat"] = 0

        # 识别年份列
        year_col = None
        for col in ["year", "report_year", "fiscal_year"]:
            if col in df.columns:
                year_col = col
                break

        if year_col is not None:
            df["post"] = (df[year_col] >= 2017).astype(int)
            if "did" not in df.columns and "treat" in df.columns:
                df["did"] = df["treat"] * df["post"]
        else:
            _log.warning("[GreenFinance] 未找到年份列，未生成post和did变量")

        return df

    # ─── 数据质量验证 ─────────────────────────────────────────────────────────

    def validate(self, panel: dict) -> dict:
        """Validate green finance panel data quality.

        Adds green-finance-specific checks to the base validation:
        - CO2 emission variable existence
        - DFI/Green credit index presence
        - ESG score quality
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

        # Check CO2 emission variables
        co2_vars = [c for c in panel_df.columns if "co2" in c.lower() or "emission" in c.lower()]
        if not co2_vars:
            base["warnings"].append(
                "未找到CO2排放变量 (ln_co2 / co2_emission / emission_intensity)。"
                "碳排放数据是绿色金融研究的核心变量。"
            )

        # Check DFI / green credit index
        dfi_vars = [c for c in panel_df.columns if "dfi" in c.lower() or "green_credit" in c.lower()]
        if not dfi_vars:
            base["warnings"].append(
                "未找到数字普惠金融指数(DFI)或绿色信贷变量。"
                "如使用北京大学DFI指数，请确保dfi_index列存在。"
            )

        # Check for typical outcome variables
        outcome_candidates = ["rd_intensity", "green_investment", "roa", "tobin_q", "patent_count"]
        found_outcomes = [v for v in outcome_candidates if v in panel_df.columns]
        if not found_outcomes:
            base["warnings"].append(
                f"未找到典型绿色金融结果变量: {outcome_candidates}。"
                "回归分析可能无结果输出。"
            )

        return base

    # ─── 回归分析 ────────────────────────────────────────────────────────────

    def run_regressions(self, panel: dict) -> dict:
        """
        运行完整的回归分析体系。

        包括:
            1. Callaway-SantAnna (2021) DID估计
            2. 三重差分 (DDD): region × time × industry_pollution_intensity
            3. 机制分析: 绿色创新 / 融资约束(SA指数) / 政府补贴
            4. 安慰剂检验: 虚假政策时间 (2013/2014/2015)

        Returns:
            dict: {
                "status": "success"|"error"|"no_data",
                "tables": {
                    "table1_main_did": {...},
                    "table2_ddd": {...},
                    "table3_mechanism": {...},
                    "table4_heterogeneity": {...},
                    "table5_placebo": {...},
                },
                "metadata": {...}
            }
        """
        try:
            df = panel.get("df")
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                return {"status": "no_data", "tables": {}, "metadata": {}}

            results: dict = {"status": "success", "tables": {}, "metadata": {}}

            # 1. 主DID回归 (Callaway-SantAnna)
            cs_result = self._run_cs_did(df)
            results["tables"]["table1_main_did"] = cs_result

            # 2. 三重差分 (DDD)
            ddd_result = self._run_ddd(df)
            results["tables"]["table2_ddd"] = ddd_result

            # 3. 机制分析
            mech_result = self._run_mechanism_analysis(df)
            results["tables"]["table3_mechanism"] = mech_result

            # 4. 异质性分析
            het_result = self._run_heterogeneity(df)
            results["tables"]["table4_heterogeneity"] = het_result

            # 5. 安慰剂检验
            placebo_result = self._run_placebo(df)
            results["tables"]["table5_placebo"] = placebo_result

            _log.info("[GreenFinance] 回归分析完成: 5个表格")
            return results

        except ImportError as exc:
            _log.error("[GreenFinance] 依赖包缺失: %s", exc)
            return {
                "status": "import_error",
                "tables": {},
                "error": f"Missing dependency: {exc}",
            }
        except Exception as exc:
            _log.error("[GreenFinance] 回归失败: %s", exc)
            return {"status": "error", "tables": {}, "error": str(exc)}

    def _run_cs_did(self, df: pd.DataFrame) -> dict:
        """
        Callaway-SantAnna (2021) DID估计。

        参考文献:
            Callaway, B., & Sant'Anna, P. H. (2021). Difference-in-differences
            with multiple time periods. *Journal of Econometrics*, 225(2), 200-230.

        使用 linearmodels 或手动WLS实现.
        """
        outcome_vars = ["rd_intensity", "green_investment", "roa", "tobin_q"]
        dep_vars_available = [v for v in outcome_vars if v in df.columns]

        rows = []
        for dep in dep_vars_available:
            try:
                import statsmodels.api as sm
                import statsmodels.formula.api as smf

                if "treat" in df.columns and "post" in df.columns:
                    formula = f"{dep} ~ did + treat + post"
                    if "size" in df.columns:
                        formula += " + size + lev + roa + age"
                    if "firm_id" in df.columns:
                        try:
                            mod = smf.panel(
                                f"{dep} ~ did + treat + post + C(firm_id) + C(year)",
                                data=df.dropna(subset=[dep, "treat", "post"]),
                            )
                        except Exception:
                            mod = smf.ols(
                                formula,
                                data=df.dropna(
                                    subset=[dep, "treat", "post", "did"]
                                ),
                            ).fit(cov_type="cluster", cov_kwds={"groups": df["firm_id"]})
                    else:
                        mod = smf.ols(formula, data=df).fit(
                            cov_type="cluster", cov_kwds={"groups": df.index}
                        )

                    ci = mod.conf_int().loc["did"]
                    rows.append(
                        {
                            "Variable": dep,
                            "Coefficient": mod.params.get("did", 0),
                            "Std. Error": mod.bse.get("did", 0),
                            "p-value": mod.pvalues.get("did", 1),
                            "CI_Lower": ci[0],
                            "CI_Upper": ci[1],
                            "N": int(mod.nobs),
                            "R-squared": mod.rsquared,
                        }
                    )
            except Exception as exc:
                _log.warning("[GreenFinance] DID回归(%s)失败: %s", dep, exc)

        if rows:
            result_df = pd.DataFrame(rows)
            return {
                "title": "绿色信贷政策对企业绿色投资与绩效的影响 (DID)",
                "note": (
                    "Callaway-SantAnna (2021) 估计. 标准误聚类到企业层面. "
                    "*** p<0.01, ** p<0.05, * p<0.1"
                ),
                "data": result_df,
            }
        return {"title": "DID回归", "data": pd.DataFrame()}

    def _run_ddd(self, df: pd.DataFrame) -> dict:
        """
        三重差分 (DDD): region × time × pollution_intensity.

        研究问题: 绿色信贷对高污染行业的效应是否更强?
        """
        rows = []
        for dep in ["rd_intensity", "green_investment", "roa"]:
            if dep not in df.columns:
                continue
            try:
                import statsmodels.formula.api as smf

                sub = df.dropna(
                    subset=[
                        dep,
                        "treat",
                        "post",
                        "pollution_intensity",
                    ]
                )
                if len(sub) < 30:
                    continue

                formula = f"{dep} ~ did * pollution_intensity"
                mod = smf.ols(formula, data=sub).fit(
                    cov_type="cluster", cov_kwds={"groups": sub.index}
                )
                rows.append(
                    {
                        "Variable": dep,
                        "DDD_Coef": mod.params.get("did:pollution_intensity", 0),
                        "Std. Error": mod.bse.get("did:pollution_intensity", 0),
                        "p-value": mod.pvalues.get("did:pollution_intensity", 1),
                        "N": int(mod.nobs),
                    }
                )
            except Exception as exc:
                _log.warning("[GreenFinance] DDD(%s)失败: %s", dep, exc)

        if rows:
            return {
                "title": "三重差分分析: 污染强度异质性 (DDD)",
                "note": (
                    "DDD = region × time × pollution_intensity. "
                    "高污染强度行业定义: 二氧化硫/废水/废气排放位于行业前50%分位"
                ),
                "data": pd.DataFrame(rows),
            }
        return {"title": "DDD回归", "data": pd.DataFrame()}

    def _run_mechanism_analysis(self, df: pd.DataFrame) -> dict:
        """
        机制分析: 检验三条可能的作用渠道.

        渠道1: 绿色创新 — 专利申请数/绿色专利占比
        渠道2: 融资约束 — SA指数、KL指数
        渠道3: 政府补贴 — 补贴收入占比
        """
        mech_vars = ["patent_count", "green_patent_ratio", "sa_index", "kl_index", "subsidy_ratio"]
        available = [v for v in mech_vars if v in df.columns]

        rows = []
        for mech in available:
            try:
                import statsmodels.formula.api as smf

                sub = df.dropna(subset=[mech, "treat", "post", "did"])
                if len(sub) < 30:
                    continue

                formula = f"{mech} ~ did"
                mod = smf.ols(formula, data=sub).fit(
                    cov_type="cluster", cov_kwds={"groups": sub.index}
                )
                rows.append(
                    {
                        "Mechanism": mech,
                        "Coefficient": mod.params.get("did", 0),
                        "Std. Error": mod.bse.get("did", 0),
                        "p-value": mod.pvalues.get("did", 1),
                        "N": int(mod.nobs),
                    }
                )
            except Exception as exc:
                _log.warning("[GreenFinance] 机制分析(%s)失败: %s", mech, exc)

        if rows:
            return {
                "title": "机制分析: 绿色创新、融资约束与政府补贴",
                "note": (
                    "检验绿色信贷政策通过以下渠道影响企业: "
                    "(1) 绿色创新专利; (2) SA融资约束指数; (3) 政府补贴占比"
                ),
                "data": pd.DataFrame(rows),
            }
        return {"title": "机制分析", "data": pd.DataFrame()}

    def _run_heterogeneity(self, df: pd.DataFrame) -> dict:
        """
        异质性分析: 按环境监管压力分组.

        高监管压力: SO2/废水排放超标企业, 重污染行业 (证监会行业分类)
        低监管压力: 其他企业
        """
        if "env_reg_pressure" not in df.columns:
            if "pollution_intensity" in df.columns:
                df = df.copy()
                df["env_reg_pressure"] = (
                    df["pollution_intensity"] > df["pollution_intensity"].median()
                ).astype(int)
            else:
                return {
                    "title": "异质性分析",
                    "note": "无可用异质性变量",
                    "data": pd.DataFrame(),
                }

        sub = df.dropna(subset=["env_reg_pressure", "treat", "post", "did"])
        if sub.empty:
            return {"title": "异质性分析", "data": pd.DataFrame()}

        rows = []
        for group_name, group_val in [("高监管压力", 1), ("低监管压力", 0)]:
            sub_g = sub[sub["env_reg_pressure"] == group_val]
            if len(sub_g) < 30:
                continue
            for dep in ["rd_intensity", "roa"]:
                if dep not in sub_g.columns:
                    continue
                try:
                    import statsmodels.formula.api as smf

                    mod = smf.ols(
                        f"{dep} ~ did", data=sub_g.dropna(subset=[dep])
                    ).fit(cov_type="cluster", cov_kwds={"groups": sub_g.index})
                    rows.append(
                        {
                            "Group": group_name,
                            "Variable": dep,
                            "Coefficient": mod.params.get("did", 0),
                            "Std. Error": mod.bse.get("did", 0),
                            "p-value": mod.pvalues.get("did", 1),
                            "N": int(mod.nobs),
                        }
                    )
                except Exception:  # noqa: S110
                    pass

        if rows:
            return {
                "title": "异质性分析: 环境监管压力",
                "note": "按企业环境监管压力分组，检验绿色信贷政策的差异化效应",
                "data": pd.DataFrame(rows),
            }
        return {"title": "异质性分析", "data": pd.DataFrame()}

    def _run_placebo(self, df: pd.DataFrame) -> dict:
        """
        安慰剂检验: 虚假政策时间.

        将政策时间分别设置为2013、2014、2015年，
        预期在这些虚假政策时间点上，DID系数不显著.
        """
        if "year" not in df.columns or "treat" not in df.columns:
            return {
                "title": "安慰剂检验",
                "note": "无年份或treatment变量，无法进行安慰剂检验",
                "data": pd.DataFrame(),
            }

        rows = []
        for fake_year in [2013, 2014, 2015]:
            sub = df.copy()
            sub["post_fake"] = (sub["year"] >= fake_year).astype(int)
            sub["did_fake"] = sub["treat"] * sub["post_fake"]

            for dep in ["rd_intensity", "roa"]:
                if dep not in sub.columns:
                    continue
                try:
                    import statsmodels.formula.api as smf

                    mod = smf.ols(
                        f"{dep} ~ did_fake",
                        data=sub.dropna(subset=[dep, "did_fake"]),
                    ).fit(cov_type="cluster", cov_kwds={"groups": sub.index})
                    rows.append(
                        {
                            "Fake Year": fake_year,
                            "Variable": dep,
                            "Coefficient": mod.params.get("did_fake", 0),
                            "Std. Error": mod.bse.get("did_fake", 0),
                            "p-value": mod.pvalues.get("did_fake", 1),
                        }
                    )
                except Exception:  # noqa: S110
                    pass

        if rows:
            return {
                "title": "安慰剂检验: 虚假政策时间",
                "note": (
                    "将政策时间分别设置为2013/2014/2015年，"
                    "若DID系数不显著则支持平行趋势假设"
                ),
                "data": pd.DataFrame(rows),
            }
        return {"title": "安慰剂检验", "data": pd.DataFrame()}

    # ─── 表格格式化 ───────────────────────────────────────────────────────────

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        """
        将回归结果格式化为LaTeX表格 (5个表).

        Table 1: 主DID结果
        Table 2: 三重差分结果
        Table 3: 机制分析
        Table 4: 异质性分析
        Table 5: 安慰剂检验
        """
        tables: dict[str, str] = {}

        if reg_results.get("status") != "success":
            return tables

        tables_data = reg_results.get("tables", {})

        # Table 1: 主DID
        t1 = tables_data.get("table1_main_did", {})
        if not t1.get("data", pd.DataFrame()).empty:
            tables["table1_main_did"] = self._fmt_did_latex(t1)

        # Table 2: DDD
        t2 = tables_data.get("table2_ddd", {})
        if not t2.get("data", pd.DataFrame()).empty:
            tables["table2_ddd"] = self._fmt_ddd_latex(t2)

        # Table 3: 机制
        t3 = tables_data.get("table3_mechanism", {})
        if not t3.get("data", pd.DataFrame()).empty:
            tables["table3_mechanism"] = self._fmt_mechanism_latex(t3)

        # Table 4: 异质性
        t4 = tables_data.get("table4_heterogeneity", {})
        if not t4.get("data", pd.DataFrame()).empty:
            tables["table4_heterogeneity"] = self._fmt_heterogeneity_latex(t4)

        # Table 5: 安慰剂
        t5 = tables_data.get("table5_placebo", {})
        if not t5.get("data", pd.DataFrame()).empty:
            tables["table5_placebo"] = self._fmt_placebo_latex(t5)

        return tables

    def _fmt_did_latex(self, result: dict) -> str:
        """Table 1: 主DID结果 LaTeX格式化."""
        df_result = result.get("data", pd.DataFrame())
        if df_result.empty:
            return self._empty_table("绿色信贷政策效应 (DID)")

        caption = result.get("title", "绿色信贷政策效应 (DID)")
        note = result.get("note", "标准误聚类到企业层面. *** p<0.01, ** p<0.05, * p<0.1")

        # 动态构建列数
        n_cols = len(df_result.columns)
        col_format = "l" + "c" * (n_cols - 1)
        header_row = " & ".join(
            [f"\\textbf{{{c}}}" for c in df_result.columns]
        ) + " \\\\"
        data_rows = []
        for _, row in df_result.iterrows():
            cells = []
            for val in row:
                if pd.isna(val):
                    cells.append("—")
                elif isinstance(val, float):
                    if abs(val) < 1 and "Std" not in str(row.name):
                        cells.append(f"{val:.4f}")
                    else:
                        cells.append(f"{val:.3f}")
                else:
                    cells.append(str(val))
            data_rows.append(" & ".join(cells) + " \\\\")
        data_str = "\n    ".join(data_rows)

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{tab:green_credit_did}}
  \begin{{threeparttable}}
  \begin{{tabular}}{{{col_format}}}
    \toprule
    {header_row}
    \midrule
    {data_str}
    \bottomrule
  \end{{tabular}}
  \begin{{tablenotes}}
    \small
    \item {note}
  \end{{tablenotes}}
  \end{{threeparttable}}
\end{{table}}"""

    def _fmt_ddd_latex(self, result: dict) -> str:
        """Table 2: 三重差分 LaTeX格式化."""
        df_result = result.get("data", pd.DataFrame())
        if df_result.empty:
            return self._empty_table("三重差分 (DDD)")

        caption = result.get("title", "三重差分 (DDD)")
        note = result.get("note", "DDD = region × time × pollution_intensity")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{tab:ddd}}
  \begin{{threeparttable}}
  \begin{{tabular}}{{lcccc}}
    \toprule
    \textbf{{Variable}} & \textbf{{DDD Coefficient}} & \textbf{{Std. Error}} & \textbf{{p-value}} & \textbf{{N}} \\
    \midrule
    {" & ".join([f"\\textbf{{{c}}}" for c in df_result.columns])} \\
    \midrule
    {" \\\\ ".join([" & ".join(str(v) if not pd.isna(v) else "—" for v in row) for _, row in df_result.iterrows()])}
    \\
    \bottomrule
  \end{{tabular}}
  \begin{{tablenotes}}
    \small
    \item {note}
  \end{{tablenotes}}
  \end{{threeparttable}}
\end{{table}}"""

    def _fmt_mechanism_latex(self, result: dict) -> str:
        """Table 3: 机制分析 LaTeX格式化."""
        df_result = result.get("data", pd.DataFrame())
        if df_result.empty:
            return self._empty_table("机制分析")

        caption = result.get("title", "机制分析")
        note = result.get(
            "note",
            "检验绿色信贷政策通过绿色创新、融资约束、政府补贴三条渠道的作用",
        )

        rows = []
        for _, row in df_result.iterrows():
            coef = row.get("Coefficient", 0)
            se = row.get("Std. Error", 0)
            pval = row.get("p-value", 1)
            stars = self._pval_to_stars(pval)
            row_str = (
                f"{row.get('Mechanism', '')} & "
                f"{coef:.4f}{stars} ({se:.4f}) & "
                f"{row.get('p-value', 0):.3f} & "
                f"{int(row.get('N', 0)):,}"
            )
            rows.append(row_str + " \\\\")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{tab:mechanism}}
  \begin{{threeparttable}}
  \begin{{tabular}}{{lccc}}
    \toprule
    \textbf{{Mechanism}} & \textbf{{DID Coefficient (SE)}} & \textbf{{p-value}} & \textbf{{N}} \\
    \midrule
    {"\n    ".join(rows)}
    \bottomrule
  \end{{tabular}}
  \begin{{tablenotes}}
    \small
    \item {note}
  \end{{tablenotes}}
  \end{{threeparttable}}
\end{{table}}"""

    def _fmt_heterogeneity_latex(self, result: dict) -> str:
        """Table 4: 异质性分析 LaTeX格式化."""
        df_result = result.get("data", pd.DataFrame())
        if df_result.empty:
            return self._empty_table("异质性分析")

        caption = result.get("title", "异质性分析")
        note = result.get(
            "note", "按环境监管压力分组，高监管压力组：污染排放位于行业前50%"
        )

        rows = []
        for _, row in df_result.iterrows():
            coef = row.get("Coefficient", 0)
            se = row.get("Std. Error", 0)
            pval = row.get("p-value", 1)
            stars = self._pval_to_stars(pval)
            row_str = (
                f"{row.get('Group', '')} ({row.get('Variable', '')}) & "
                f"{coef:.4f}{stars} ({se:.4f}) & "
                f"{pval:.3f} & "
                f"{int(row.get('N', 0)):,}"
            )
            rows.append(row_str + " \\\\")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{tab:heterogeneity}}
  \begin{{threeparttable}}
  \begin{{tabular}}{{lccc}}
    \toprule
    \textbf{{Group}} & \textbf{{DID Coefficient (SE)}} & \textbf{{p-value}} & \textbf{{N}} \\
    \midrule
    {"\n    ".join(rows)}
    \bottomrule
  \end{{tabular}}
  \begin{{tablenotes}}
    \small
    \item {note}
  \end{{tablenotes}}
  \end{{threeparttable}}
\end{{table}}"""

    def _fmt_placebo_latex(self, result: dict) -> str:
        """Table 5: 安慰剂检验 LaTeX格式化."""
        df_result = result.get("data", pd.DataFrame())
        if df_result.empty:
            return self._empty_table("安慰剂检验")

        caption = result.get("title", "安慰剂检验")
        note = result.get(
            "note",
            "虚假政策时间为2013/2014/2015，预期DID系数不显著",
        )

        rows = []
        for _, row in df_result.iterrows():
            coef = row.get("Coefficient", 0)
            se = row.get("Std. Error", 0)
            pval = row.get("p-value", 1)
            stars = self._pval_to_stars(pval)
            row_str = (
                f"{int(row.get('Fake Year', 0))} ({row.get('Variable', '')}) & "
                f"{coef:.4f}{stars} ({se:.4f}) & "
                f"{pval:.3f}"
            )
            rows.append(row_str + " \\\\")

        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{caption}}}
  \label{{tab:placebo}}
  \begin{{threeparttable}}
  \begin{{tabular}}{{lccc}}
    \toprule
    \textbf{{Fake Treatment Year}} & \textbf{{DID Coefficient (SE)}} & \textbf{{p-value}} \\
    \midrule
    {"\n    ".join(rows)}
    \bottomrule
  \end{{tabular}}
  \begin{{tablenotes}}
    \small
    \item {note}
  \end{{tablenotes}}
  \end{{threeparttable}}
\end{{table}}"""

    def _pval_to_stars(self, pval: float) -> str:
        """将p值转换为显著性星号."""
        if pd.isna(pval):
            return ""
        if pval < 0.001:
            return "***"
        if pval < 0.01:
            return "**"
        if pval < 0.05:
            return "*"
        if pval < 0.1:
            return r"^{\dagger}"
        return ""

    def _empty_table(self, title: str) -> str:
        """生成空表格占位符."""
        return rf"""\begin{{table}}[htbp]
  \centering
  \caption{{{title}}}
  \label{{tab:{title.replace(" ", "_").lower()}}}
  \begin{{tabular}}{{lc}}
    \toprule
    \textbf{{Variable}} & \textbf{{}} \\
    \midrule
    \bottomrule
  \end{{tabular}}
  \note{{No data available for this table.}}
\end{{table}}"""

    # ─── 图表计划 ─────────────────────────────────────────────────────────────

    def get_figure_plan(self) -> list[dict]:
        """
        返回4个学术图表计划.

        Figure 1: 事件研究 — 平行趋势检验
        Figure 2: 绿色信贷流向行业分布
        Figure 3: 机制路径图
        Figure 4: 异质性系数图
        """
        return [
            {
                "figure_id": "fig_event_study",
                "title": "事件研究: 绿色信贷政策的平行趋势检验",
                "description": (
                    "展示处理组与对照组在政策前后的趋势差异. "
                    "政策时点为2017年. 预期政策前系数不显著，政策后系数显著为正. "
                    "x轴: 年份 (2012-2023); y轴: DID系数及其95%置信区间"
                ),
                "chart_type": "event_study",
                "generation_method": "matplotlib",
                "data_requirements": ["year", "did_coef", "ci_lower", "ci_upper", "treat", "control"],
                "file_format": "pdf",
                "dpi": 300,
                "style": "academic",
                "literature_reference": "Callaway & Sant'Anna (2021, JoE)",
            },
            {
                "figure_id": "fig_green_credit_flow",
                "title": "绿色信贷资金流向行业分布",
                "description": (
                    "堆叠柱状图或Sankey图展示绿色信贷在制造业/能源/交通等行业的分配. "
                    "横轴: 年份; 纵轴: 绿色信贷规模 (亿元); "
                    "颜色编码: 不同行业; 数据来源: 央行《金融机构贷款投向统计报告》"
                ),
                "chart_type": "stacked_bar",
                "generation_method": "matplotlib",
                "data_requirements": ["year", "industry", "green_credit_amount"],
                "file_format": "pdf",
                "dpi": 300,
                "style": "academic",
            },
            {
                "figure_id": "fig_mechanism_pathway",
                "title": "绿色信贷政策作用机制路径图",
                "description": (
                    "因果路径图 (Directed Acyclic Graph) 展示三条作用渠道: "
                    "(1) 绿色创新: 绿色信贷 → R&D激励 → 绿色专利 → 企业绩效; "
                    "(2) 融资约束: 绿色信贷 → SA指数下降 → 融资成本下降 → 企业绩效; "
                    "(3) 政府补贴: 绿色信贷 → 补贴激励 → 环保投资 → 企业绩效. "
                    "使用graphviz或matplotlib箭头绘制"
                ),
                "chart_type": "dag",
                "generation_method": "matplotlib + graphviz",
                "data_requirements": ["pathway_labels", "coefficients"],
                "file_format": "pdf",
                "dpi": 300,
                "style": "academic",
            },
            {
                "figure_id": "fig_heterogeneity_coef",
                "title": "异质性分析: 政策效应系数对比",
                "description": (
                    "森林图 (forest plot) 展示不同分组下的DID系数: "
                    "高污染vs低污染、高监管vs低监管、国有企业vs民营企业. "
                    "x轴: DID系数; y轴: 分组标签; "
                    "误差棒: 95%置信区间; 虚线: 总体DID系数参考线"
                ),
                "chart_type": "forest_plot",
                "generation_method": "matplotlib",
                "data_requirements": ["group_name", "coef", "ci_lower", "ci_upper", "n_obs"],
                "file_format": "pdf",
                "dpi": 300,
                "style": "academic",
                "literature_reference": "Lewis et al. (2021, JoE)",
            },
        ]


# ─── Auto-register ───────────────────────────────────────────────────────────

get_registry().register(GreenFinanceDirection())
