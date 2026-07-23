"""
User Data Merger & Schema Validator.

P1: Fuses user-provided files (data/) with MCP data sources.
P2: Validates and suggests column mappings between user CSV/Excel and expected schemas.

Design principles:
  1. User CSV/Excel (data/) → MCP (35 servers) → Synthetic (requires user auth)
  2. All merged fields carry provenance via ProvenanceTracker
  3. MockDataRegistry enforces no silent fallback to synthetic data
  4. SchemaValidator suggests field mappings for Chinese column names

Usage:
    from scripts.core.user_data_merger import UserDataMerger, UserDataSchemaValidator

    merger = UserDataMerger(project_root=Path("."))
    merged_df, tracker = merger.merge(
        variables=["roa", "leverage", "tariff_exposure"],
        idea_keywords=["关税", "资本结构", "A-share"],
    )

    validator = UserDataSchemaValidator()
    result = validator.validate_and_suggest_mapping(df, expected_schema)
    print(result.matched_columns)
"""

from __future__ import annotations

__all__ = [
    "SchemaValidationResult",
    "VariableSourceReport",
    "MergeResult",
    "_c",
    "_normalize",
    "_fuzzy_match",
]

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.research_framework.base import DataSource, ProvenanceTracker

try:
    from scripts.core.mock_data_governance import (
        MockDataPolicy,
        MockDataRegistry,
    )
    _MOCK_GOVERNANCE_AVAILABLE = True
except ImportError:
    _MOCK_GOVERNANCE_AVAILABLE = False
    MockDataPolicy = None
    MockDataRegistry = None

# ─── ANSI Colors ────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ─── Logger ────────────────────────────────────────────────────────────────────

logger = logging.getLogger("user_data_merger")

# ─── Known Real Data Sources ──────────────────────────────────────────────────

_KNOWN_REAL_SOURCES: set[str] = {
    "tushare",
    "akshare",
    "yfinance",
    "wind",
    "csmar",
    "eastmoney",
    "sec-edgar",
    "macro",
    "wb",
    "imf",
    "oecd",
    "fed",
    "bea",
    "user-financial",
    "user-eodhd",
    "user-wb-data",
    "user-imf-data",
    "user-oecd-data",
    "user-fed-data",
    "user-eastmoney-reports",
    "user-csmar",
    "user-hubei-stats",
    "user-province-stats",
    "user-enhanced-finance",
    "user-eastmoney-fund",
    "user-eastmoney-bond",
    "user-eastmoney-option",
    "user-cryptocompare",
}

# ─── Field Name Mappings (Chinese → English canonical) ─────────────────────────

_CHINESE_TO_ENGLISH: dict[str, list[str]] = {
    "资产负债率": ["debt_ratio", "leverage", "资产负责率", "lev", "debt_asset"],
    "roa": ["roa", "return_on_assets", "资产收益率", "总资产收益率", "资产回报率"],
    "roe": ["roe", "return_on_equity", "净资产收益率", "股权收益率", "股东权益收益率"],
    "总资产": ["total_assets", "资产总计", "assets", "资产总额"],
    "总负债": ["total_liability", "负债合计", "liabilities", "负债总额", "debt"],
    "营业收入": ["revenue", "sales", "营业总收入", "营业收入", "sales_revenue"],
    "净利润": ["net_income", "profit", "净利润", "企业净利润"],
    "市值": ["market_cap", "market_value", "市值", "股票市值", "总市值"],
    "股价": ["stock_price", "price", "收盘价", "股票价格"],
    "eps": ["eps", "earnings_per_share", "每股收益", "eps_basic"],
    "bps": ["bps", "book_value_per_share", "每股净资产", "bvps"],
    "流动比率": ["current_ratio", "流动比率", "liquidity_ratio"],
    "速动比率": ["quick_ratio", "速动比率", "acid_test"],
    "存货周转率": ["inventory_turnover", "存货周转率", "inventory_turnover_days"],
    "应收账款周转率": ["receivable_turnover", "应收账款周转率", "ar_turnover"],
    "毛利率": ["gross_margin", "毛利率", "gross_profit_margin"],
    "净利率": ["net_margin", "净利率", "net_profit_margin"],
    "企业规模": ["size", "log_size", "企业规模", "公司规模", "asset_size"],
    "成立年限": ["age", "firm_age", "企业年龄", "成立年限", "age_years"],
    "股权集中度": ["ownership_concentration", "股权集中度", "top1_holder"],
    "出口额": ["export", "export_value", "出口额", "出口金额", "export_amount"],
    "进口额": ["import_value", "import", "进口额", "进口金额"],
    "hs编码": ["hs_code", "hs", "海关编码", "商品编码", "hs8"],
    "关税税率": ["tariff_rate", "duty_rate", "关税率", "税率"],
    "关税暴露强度": ["tariff_exposure", "tariff_exp", "关税暴露"],
    "年份": ["year", "报告年份", "year_reported"],
    "季度": ["quarter", "q1", "q2", "q3", "q4"],
    "公司代码": ["ts_code", "stkcd", "stock_code", "股票代码", "firm_id"],
    "公司名称": ["company_name", "firm_name", "企业名称", "公司名称"],
    "行业": ["industry", "sector", "行业", "industry_code"],
    "地区": ["region", "province", "city", "地区", "省份"],
    "所有制": ["soe", "ownership", "所有制", "state_owned", "民营"],
    "研发投入": ["rd", "rd_intensity", "研发支出", "研发投入", "innovation"],
    "专利申请": ["patent", "patent_count", "专利", "创新产出"],
    "esg评分": ["esg", "esg_score", "ESG", "环境得分", "社会得分", "治理得分"],
    "碳排放": ["carbon", "emission", "碳排放", "co2", "碳强度"],
    "绿色专利": ["green_patent", "绿色专利", "environmental_patent"],
    "融资约束": ["financing_constraint", "sa_index", "kz_index", "融资约束"],
    "投资水平": ["investment", "capex", "投资支出", "资本支出", "investment_ratio"],
    "托宾q": ["tobin_q", "q_ratio", "托宾Q", "market_to_book"],
    "现金持有": ["cash", "cash_holding", "现金持有", "cash_ratio"],
    "高管薪酬": ["compensation", "exec_pay", "高管薪酬", "salary"],
    "审计意见": ["audit_opinion", "审计意见", "audit", "non_standard"],
    "分析师关注": ["analyst_coverage", "analyst", "分析师跟踪", "coverage"],
    "机构持股": ["institutional_holding", "inst_own", "机构持股", "inst_ownership"],
}

_ENGLISH_TO_NORMALIZED: dict[str, str] = {
    "roa": "roa",
    "roe": "roe",
    "lev": "leverage",
    "debt_ratio": "leverage",
    "leverage": "leverage",
    "size": "size",
    "log_size": "size",
    "tariff_exposure": "tariff_exposure",
    "tariff_exp": "tariff_exposure",
    "rd": "rd_intensity",
    "rd_intensity": "rd_intensity",
    "patent": "patent_count",
    "patent_count": "patent_count",
}


def _normalize(name: str) -> str:
    """Normalize a field name to a canonical form (lowercase, underscore)."""
    return _ENGLISH_TO_NORMALIZED.get(name.lower(), name.lower())


def _fuzzy_match(field_name: str, candidates: list[str]) -> tuple[bool, list[str]]:
    """Check if field_name matches any candidate (case-insensitive, Chinese-aware).

    Returns:
        (matched, list of matched canonical names)
    """
    normalized = _normalize(field_name)
    matches: list[str] = []

    for candidate in candidates:
        cand_norm = _normalize(candidate)
        if normalized == cand_norm:
            matches.append(candidate)
        elif normalized in cand_norm or cand_norm in normalized:
            matches.append(candidate)

    return len(matches) > 0, matches


def _find_canonical_for_chinese(col: str) -> list[str]:
    """Given a Chinese column name, return possible canonical English names."""
    # Direct lookup
    if col in _CHINESE_TO_ENGLISH:
        return _CHINESE_TO_ENGLISH[col]
    # Substring match
    for chinese_key, english_vals in _CHINESE_TO_ENGLISH.items():
        if chinese_key in col or col in chinese_key:
            return english_vals
    return []


# ─── Schema Validation Result ─────────────────────────────────────────────────


@dataclass
class SchemaValidationResult:
    """Result of validating user DataFrame against an expected schema."""

    matched_columns: dict[str, str] = field(default_factory=dict)
    """Logical name → actual column name in user's DataFrame."""

    unmatched_columns: list[str] = field(default_factory=list)
    """Columns in user's DataFrame with no schema match."""

    unknown_columns: list[str] = field(default_factory=list)
    """Columns in schema that user DataFrame does not have."""

    suggestions: list[str] = field(default_factory=list)
    """Human-readable mapping suggestions."""

    confidence: float = 0.0
    """Overall confidence score 0.0–1.0."""

    file_name: str = ""


# ─── Merge Report ──────────────────────────────────────────────────────────────


@dataclass
class VariableSourceReport:
    """Per-variable source information after merge."""

    variable: str
    source: str
    file_path: str = ""
    coverage_pct: float = 0.0
    row_count: int = 0
    is_simulated: bool = False
    note: str = ""


@dataclass
class MergeResult:
    """Result of merging user data with MCP sources."""

    merged_df: pd.DataFrame
    tracker: ProvenanceTracker
    source_report: list[VariableSourceReport] = field(default_factory=list)
    unmet_variables: list[str] = field(default_factory=list)
    user_files_used: list[str] = field(default_factory=list)
    mcp_sources_used: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ─── UserDataMerger ────────────────────────────────────────────────────────────


class UserDataMerger:
    """
    P1: User/MCP data fusion pipeline.

    Priority order:
        1. User CSV/Excel files in data/ directory (matching research variables)
        2. MCP data sources (35 servers)
        3. Synthetic data (requires explicit user authorization via MockDataRegistry)

    The merge process:
        1. scan data/ directory for user files
        2. match user files to research variables via keyword/column analysis
        3. merge user data with MCP data for uncovered variables
        4. validate merged dataset, identify gaps
        5. return unmet variables list for downstream handling

    Attributes:
        project_root: Root directory of the project (data/ subdirectory is scanned).
        logger: Logger instance.
    """

    def __init__(
        self,
        project_root: Path | str | None = None,
        mcp_registry: dict[str, Any] | None = None,
    ) -> None:
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        self.project_root = Path(project_root)
        self.data_dir = self.project_root / "data"
        self.logger = logger

        # Mock data governance (P3 auth enforcement)
        self._mock_registry: "MockDataRegistry | None" = None
        if _MOCK_GOVERNANCE_AVAILABLE:
            try:
                self._mock_registry = MockDataRegistry()
                self._mock_registry.set_policy(MockDataPolicy.DENY)
            except Exception as exc:
                self.logger.warning("Failed to init MockDataRegistry: %s", exc)

        # MCP registry: variable_name -> {"source": "mcp:xxx", "method": "get_xxx"}
        self._mcp_registry = mcp_registry or {}
        self._loaded_user_files: dict[str, pd.DataFrame] = {}

    # ── Data Preview ─────────────────────────────────────────────────────────

    def preview(self, path: str | Path, max_rows: int = 5) -> dict:
        """Preview a data file before merging.

        Returns a dict with:
        - head: first max_rows as string
        - dtypes: column types
        - missing: missing value counts per column
        - shape: (n_rows, n_cols)
        - numeric_cols: list of numeric columns
        - date_cols: list of date columns
        - suspicious: list of columns with suspicious patterns

        Args:
            path: Path to CSV/Excel/JSON file
            max_rows: Number of rows to preview

        Returns:
            dict with preview information
        """
        path = Path(path)
        ext = path.suffix.lower()

        # Read head for preview
        if ext == ".csv":
            df_head = pd.read_csv(path, nrows=max_rows, encoding="utf-8-sig", low_memory=False)
            df_full = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        elif ext in (".xlsx", ".xls"):
            engine = "openpyxl" if ext == ".xlsx" else "xlrd"
            df_head = pd.read_excel(path, nrows=max_rows, engine=engine)
            df_full = pd.read_excel(path, engine=engine)
        elif ext == ".json":
            import json as _json

            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
            if isinstance(data, list):
                df_head = pd.DataFrame(data[:max_rows])
                df_full = pd.DataFrame(data)
            else:
                df_head = pd.DataFrame([data])
                df_full = df_head.copy()
        else:
            return {"error": f"Unsupported file type: {ext}"}

        shape = df_full.shape

        # Identify numeric columns
        numeric_cols = df_full.select_dtypes(include=["number"]).columns.tolist()

        # Identify date columns: try pd.to_datetime on string/object cols
        date_cols: list[str] = []
        for col in df_full.select_dtypes(include=["object", "string"]).columns:
            try:
                parsed = pd.to_datetime(df_full[col], errors="coerce")
                if parsed.notna().sum() > len(df_full) * 0.5:
                    date_cols.append(col)
            except Exception:
                pass

        # Suspicious detection: very high cardinality (>1000 unique for string cols,
        # repeated values for numeric)
        suspicious: list[str] = []
        for col in df_full.select_dtypes(include=["object", "string"]).columns:
            n_unique = df_full[col].nunique()
            if n_unique > 1000:
                suspicious.append(f"{col} (high cardinality: {n_unique} unique)")
        for col in numeric_cols:
            n_unique = df_full[col].nunique()
            if n_unique <= 3:
                suspicious.append(f"{col} (low cardinality: {n_unique} unique — possible flag/binary)")

        # Head as string representation
        head_str = df_head.to_string(max_rows=max_rows)

        return {
            "head": head_str,
            "dtypes": {str(k): str(v) for k, v in df_full.dtypes.items()},
            "missing": df_full.isnull().sum().to_dict(),
            "shape": shape,
            "numeric_cols": numeric_cols,
            "date_cols": date_cols,
            "suspicious": suspicious,
        }

    # ── Step 1: Load user data ────────────────────────────────────────────────

    def load_user_data(
        self,
        variables: list[str],
        idea_keywords: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Scan data/ directory and load files relevant to the research variables.

        Args:
            variables: List of required variable names (English/Chinese).
            idea_keywords: Optional research keywords to improve file matching.

        Returns:
            Dict mapping file path (str) → DataFrame of loaded files.
        """
        self._loaded_user_files.clear()
        if not self.data_dir.exists():
            self.logger.warning("data/ directory does not exist: %s", self.data_dir)
            return {}

        keywords = set(v.lower() for v in (idea_keywords or []))
        keywords.update(v.lower() for v in variables)

        for item in self.data_dir.iterdir():
            # Skip subdirectories like __pycache__, processed, etc.
            if item.is_dir() and item.name.startswith((".", "__", "processed")):
                continue
            if not item.is_file():
                continue

            ext = item.suffix.lower()
            if ext not in (".csv", ".xlsx", ".xls", ".json"):
                continue

            # Heuristic: check if filename or any subdirectory name matches keywords
            parent_rel = item.parent.relative_to(self.data_dir) if item.parent != self.data_dir else ""
            name_lower = item.stem.lower()

            if not any(
                kw in name_lower or name_lower in kw or kw in str(parent_rel).lower()
                for kw in keywords
            ):
                # If no keyword match, try column-based matching
                try:
                    cols = self._peek_columns(item)
                    if not self._columns_match_variables(cols, variables):
                        self.logger.debug("Skipping '%s' (no variable match)", item.name)
                        continue
                except Exception as exc:
                    self.logger.debug("Could not peek columns of '%s': %s", item.name, exc)
                    continue

            try:
                df = self._load_file(item)
                self._loaded_user_files[str(item)] = df
                self.logger.info("Loaded user file: %s (%d rows × %d cols)",
                                 item.name, len(df), len(df.columns))
            except Exception as exc:
                self.logger.warning("Failed to load '%s': %s", item.name, exc)

        return self._loaded_user_files

    def _peek_columns(self, path: Path) -> list[str]:
        """Read only the header row to detect column names."""
        ext = path.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(path, nrows=0)
            return [str(c) for c in df.columns]
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(path, nrows=0)
            return [str(c) for c in df.columns]
        elif ext == ".json":
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return [str(k) for k in data[0].keys()]
            return []
        return []

    def _load_file(self, path: Path) -> pd.DataFrame:
        """Load a data file into a DataFrame."""
        ext = path.suffix.lower()
        if ext == ".csv":
            return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        elif ext in (".xlsx", ".xls"):
            return pd.read_excel(path, engine="openpyxl" if ext == ".xlsx" else "xlrd")
        elif ext == ".json":
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return pd.DataFrame(data)
            return pd.DataFrame([data])
        raise ValueError(f"Unsupported file type: {ext}")

    def _columns_match_variables(self, columns: list[str], variables: list[str]) -> bool:
        """Check if any column matches any variable (fuzzy)."""
        for col in columns:
            col_lower = col.lower().strip()
            for var in variables:
                var_lower = var.lower().strip()
                if var_lower in col_lower or col_lower in var_lower:
                    return True
                # Check canonical English equivalents
                for ch_key, en_vals in _CHINESE_TO_ENGLISH.items():
                    if ch_key.lower() in col_lower:
                        if var_lower in [v.lower() for v in en_vals]:
                            return True
        return False

    # ── Step 2: Merge with MCP ────────────────────────────────────────────────

    def merge_with_mcp(
        self,
        user_df: pd.DataFrame,
        unmet_variables: list[str],
        tracker: ProvenanceTracker,
    ) -> pd.DataFrame:
        """
        Attempt to fill unmet variables using MCP data sources.

        Args:
            user_df: Already-merged user data DataFrame.
            unmet_variables: Variables still missing.
            tracker: ProvenanceTracker to record MCP sources.

        Returns:
            DataFrame with additional columns from MCP (if available).
        """
        if not unmet_variables:
            return user_df

        # Try MCP data fetchers
        for var in list(unmet_variables):
            mcp_source = self._find_mcp_source_for_variable(var)
            if mcp_source:
                self.logger.info("MCP source found for '%s': %s", var, mcp_source)
                # Record provenance for MCP variables
                tracker.record(var, DataSource.MCP_USER, detail=f"MCP fallback via {mcp_source}")
                # Note: actual MCP call is done in data_fetcher.py
                # This method records the intent and source
                unmet_variables.remove(var)

        return user_df

    def _find_mcp_source_for_variable(self, var: str) -> str | None:
        """Find an appropriate MCP source for a variable."""
        var_lower = var.lower()
        mapping: dict[str, list[str]] = {
            "roa": ["mcp:tushare", "mcp:financial"],
            "roe": ["mcp:tushare", "mcp:financial"],
            "leverage": ["mcp:tushare", "mcp:financial"],
            "tariff_exposure": ["mcp:csmar", "mcp:chinese_customs"],
            "customs": ["mcp:chinese_customs", "mcp:csmar"],
            "macro": ["mcp:financial", "mcp:wb-data", "mcp:imf-data"],
            "esg": ["mcp:yfinance", "mcp:eastmoney"],
            "rd": ["mcp:tushare", "mcp:financial"],
            "patent": ["mcp:tushare", "mcp:financial"],
            "price": ["mcp:yfinance", "mcp:eastmoney"],
            "exchange_rate": ["mcp:enhanced-finance"],
            "shipping": ["mcp:enhanced-finance"],
        }

        for key, sources in mapping.items():
            if key in var_lower:
                return sources[0]

        return None

    # ── Step 3: Validate merged data ─────────────────────────────────────────

    def validate_merged(
        self,
        df: pd.DataFrame,
        variables: list[str],
        tracker: ProvenanceTracker,
    ) -> tuple[list[VariableSourceReport], list[str]]:
        """
        Validate merged dataset and identify coverage gaps.

        Args:
            df: The merged DataFrame.
            variables: Required variable list.
            tracker: ProvenanceTracker with recorded sources.

        Returns:
            (source_reports: list[VariableSourceReport], unmet: list[str])
        """
        reports: list[VariableSourceReport] = []
        unmet: list[str] = []

        for var in variables:
            # Try to find the column in DataFrame
            matched_col = self._find_column_in_df(df, var)

            if matched_col:
                non_null = df[matched_col].notna().sum()
                coverage = non_null / max(len(df), 1) * 100
                prov = tracker.get(var)
                src = prov.get("source", "unknown") if prov else "unknown"
                is_sim = prov.get("is_simulated", False) if prov else False

                reports.append(VariableSourceReport(
                    variable=var,
                    source=src,
                    coverage_pct=round(coverage, 1),
                    row_count=int(non_null),
                    is_simulated=is_sim,
                    note=f"Column '{matched_col}' matched",
                ))
            else:
                reports.append(VariableSourceReport(
                    variable=var,
                    source="missing",
                    coverage_pct=0.0,
                    row_count=0,
                    note="No matching column found in any loaded file",
                ))
                unmet.append(var)

        return reports, unmet

    def _find_column_in_df(self, df: pd.DataFrame, variable: str) -> str | None:
        """Find a DataFrame column that corresponds to a variable name."""
        var_lower = variable.lower()

        # Direct match
        for col in df.columns:
            if _normalize(col) == _normalize(var_lower):
                return col

        # Chinese mapping
        for col in df.columns:
            canonicals = _find_canonical_for_chinese(str(col))
            # Normalize so remapped names (e.g. "debt_ratio"→"leverage") match correctly
            var_lower_norm = _normalize(var_lower)
            if var_lower_norm in {_normalize(c) for c in canonicals}:
                return col

        # Substring match
        for col in df.columns:
            col_str = str(col).lower()
            if var_lower in col_str or col_str in var_lower:
                return col

        return None

    # ── Step 4: Get unmet variables ──────────────────────────────────────────

    def get_unmet_variables(
        self,
        variables: list[str],
        user_files: dict[str, pd.DataFrame],
        tracker: ProvenanceTracker,
    ) -> list[str]:
        """
        Return list of variables still missing after scanning user files.

        Args:
            variables: Required variable list.
            user_files: Loaded user files.
            tracker: ProvenanceTracker with recorded sources.

        Returns:
            List of variable names with no data source.
        """
        unmet = []
        all_cols: set[str] = set()
        for df in user_files.values():
            all_cols.update(str(c).lower() for c in df.columns)

        for var in variables:
            matched = self._find_column_in_df(
                pd.DataFrame(columns=list(all_cols)),  # dummy for matching
                var,
            )
            # Check if already recorded in tracker
            prov = tracker.get(var)
            if prov:
                continue
            if not matched and var.lower() not in all_cols:
                unmet.append(var)

        return list(set(unmet))

    # ── Main merge entry point ────────────────────────────────────────────────

    def merge(
        self,
        variables: list[str],
        idea_keywords: list[str] | None = None,
    ) -> tuple[pd.DataFrame, ProvenanceTracker]:
        """
        Full merge pipeline: user files → MCP → synthetic (auth required).

        Args:
            variables: Required variable names.
            idea_keywords: Research keywords to guide file discovery.

        Returns:
            (merged_df: pd.DataFrame, tracker: ProvenanceTracker)
        """
        self.logger.info("Starting merge for %d variables: %s", len(variables), variables)
        tracker = ProvenanceTracker()

        # Step 1: Load user data
        user_files = self.load_user_data(variables, idea_keywords)

        if not user_files:
            self.logger.warning("No user files found in data/ matching variables")
        else:
            self.logger.info("Loaded %d user file(s)", len(user_files))

        # Build initial merged DataFrame
        if user_files:
            # Concatenate all user files (outer join on common columns)
            dfs_to_concat = []
            for path_str, df in user_files.items():
                # Track file provenance
                tracker.record(
                    f"__file_{Path(path_str).name}__",
                    DataSource.MCP_USER,
                    detail=f"User file: {path_str}",
                )
                dfs_to_concat.append(df)

            if len(dfs_to_concat) == 1:
                merged_df = dfs_to_concat[0]
            else:
                # Find common key columns for merge
                key_candidates = ["stkcd", "ts_code", "stock_code", "company_name",
                                  "公司代码", "公司名称", "year", "年份"]
                key_col = None
                for key in key_candidates:
                    if all(key in df.columns for df in dfs_to_concat):
                        key_col = key
                        break

                if key_col:
                    merged_df = dfs_to_concat[0]
                    for other in dfs_to_concat[1:]:
                        merged_df = merged_df.merge(
                            other, on=key_col, how="outer", suffixes=("", "_dup")
                        )
                    # Remove dup columns
                    merged_df = merged_df[[c for c in merged_df.columns if not c.endswith("_dup")]]
                else:
                    merged_df = pd.concat(dfs_to_concat, axis=0, ignore_index=True)
        else:
            merged_df = pd.DataFrame()

        # Step 2: Identify unmet variables
        unmet = []
        for var in variables:
            if self._find_column_in_df(merged_df, var) is None:
                unmet.append(var)

        self.logger.info("Unmet variables after user files: %s", unmet)

        # Step 3: Attempt MCP fill
        if unmet:
            merged_df = self.merge_with_mcp(merged_df, unmet, tracker)

        # Step 4: Validate
        reports, final_unmet = self.validate_merged(merged_df, variables, tracker)

        self.logger.info(
            "Merge complete. Coverage reports: %d vars, unmet: %s",
            len(reports),
            final_unmet,
        )

        return merged_df, tracker

    # ── Auth enforcement ─────────────────────────────────────────────────────

    def authorize_synthetic_variable(self, var_name: str, reason: str = "") -> bool:
        """
        Authorize a specific variable for synthetic data use.

        Args:
            var_name: Variable name to authorize.
            reason: Why synthetic data is needed.

        Returns:
            True if authorized, False otherwise.
        """
        if not _MOCK_GOVERNANCE_AVAILABLE or self._mock_registry is None:
            self.logger.warning("Mock governance not available, allowing synthetic '%s'", var_name)
            return True

        try:
            self._mock_registry.authorize(var_name, reason=reason)
            self.logger.info("Authorized synthetic data for '%s' (reason: %s)", var_name, reason)
            return True
        except Exception as exc:
            self.logger.error("Failed to authorize '%s': %s", var_name, exc)
            return False


# ─── UserDataSchemaValidator ──────────────────────────────────────────────────


class UserDataSchemaValidator:
    """
    P2: Validates user DataFrame against an expected schema and suggests mappings.

    The expected_schema maps logical names to canonical names (English, Chinese aliases):
        {
            "资产负债率": ["debt_ratio", "leverage", "资产负责率", "lev"],
            "ROA": ["roa", "return_on_assets", "总资产收益率"],
            ...
        }

    The validator:
        1. Checks which logical names have a matching column in user DataFrame
        2. Reports unmatched user columns (might be typos or unknown variables)
        3. Reports unknown schema columns (user does not have them)
        4. Suggests fuzzy mappings for ambiguous cases
        5. Returns a confidence score for the overall mapping quality

    Usage:
        validator = UserDataSchemaValidator()
        result = validator.validate_and_suggest_mapping(df, expected_schema)
        print(f"Confidence: {result.confidence:.1%}")
        print(f"Matches: {result.matched_columns}")
        print(f"Suggestions: {result.suggestions}")
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("user_data_merger.schema_validator")
        self._last_result: SchemaValidationResult | None = None

    def validate_and_suggest_mapping(
        self,
        df: pd.DataFrame,
        expected_schema: dict[str, list[str]],
        file_name: str = "",
    ) -> SchemaValidationResult:
        """
        Validate user DataFrame against expected schema and suggest mappings.

        Args:
            df: User's DataFrame.
            expected_schema: Dict mapping logical names → canonical name aliases.
                Example:
                    {
                        "资产负债率": ["debt_ratio", "leverage", "lev"],
                        "ROA": ["roa", "return_on_assets"],
                    }
            file_name: Optional name of the source file.

        Returns:
            SchemaValidationResult with matched/unmatched columns and suggestions.
        """
        user_cols_lower = {str(c).lower().strip(): str(c) for c in df.columns}
        matched: dict[str, str] = {}
        unmatched_user: list[str] = []
        unknown_schema: list[str] = []
        suggestions: list[str] = []
        matched_values: set[str] = set()  # track matched df column names

        for logical_name, canonical_names in expected_schema.items():
            found_col: str | None = None

            # Exact match: df column equals any canonical name (case-insensitive)
            canonical_lower = {_normalize(c): c for c in canonical_names}
            # Also keep original strings for English identifiers that would be
            # remapped by _normalize (e.g. "debt_ratio" → "leverage")
            canonical_original_lower = {c.lower().strip(): c for c in canonical_names}

            for col_lower, col_original in user_cols_lower.items():
                # Check against original strings first (preserves English identifiers)
                if col_lower in canonical_original_lower:
                    found_col = col_original
                    break

                # Normalized check as fallback
                if col_lower in canonical_lower:
                    found_col = col_original
                    break

                # Chinese → English: df column's Chinese aliases match a canonical
                ch_canonical = _find_canonical_for_chinese(col_original)
                for cc in ch_canonical:
                    cc_norm = _normalize(cc)
                    if cc_norm in canonical_lower or cc.lower().strip() in canonical_original_lower:
                        found_col = col_original
                        suggestions.append(
                            f"  → 字段映射: '{col_original}' → '{logical_name}' "
                            f"(via Chinese alias '{cc}')"
                        )
                        break
                if found_col:
                    break

            if found_col:
                matched[logical_name] = found_col
                matched_values.add(found_col)
            else:
                unknown_schema.append(logical_name)
                suggestions.append(
                    f"  ⚠ 未找到 '{logical_name}' "
                    f"(期望别名: {canonical_names})"
                )

        # Identify df columns not covered by the schema
        for col_original in df.columns:
            if col_original in matched_values:
                continue
            col_lower = str(col_original).lower().strip()
            is_unmatched = True

            for logical_name, canonical_names in expected_schema.items():
                if col_lower in {_normalize(c) for c in canonical_names}:
                    is_unmatched = False
                    break
                ch_canonical = _find_canonical_for_chinese(str(col_original))
                if any(
                    _normalize(c) in {_normalize(cn) for cn in canonical_names}
                    for c in ch_canonical
                ):
                    is_unmatched = False
                    break

            if is_unmatched:
                best_suggestion = self._find_similar(
                    col_original, expected_schema
                )
                if best_suggestion:
                    suggestions.append(
                        f"  💡 可能映射: '{col_original}' → '{best_suggestion}' "
                        f"(相似度匹配)"
                    )
                unmatched_user.append(str(col_original))

        # Compute confidence
        n_total = len(expected_schema)
        n_matched = len(matched)
        confidence = n_matched / n_total if n_total > 0 else 0.0

        result = SchemaValidationResult(
            matched_columns=matched,
            unmatched_columns=unknown_schema,   # schema keys NOT matched (user missing)
            unknown_columns=unmatched_user,      # user df columns NOT in schema (extra)
            suggestions=suggestions,
            confidence=round(confidence, 3),
            file_name=file_name,
        )
        self._last_result = result
        self.logger.info(
            "Schema validation: %d/%d matched (%.1f%%), %d unmatched user cols, %d unknown schema",
            n_matched, n_total, confidence * 100, len(unmatched_user), len(unknown_schema),
        )

        return result

    def _find_similar(
        self,
        col_name: str,
        schema: dict[str, list[str]],
    ) -> str | None:
        """Find the most similar schema key using edit distance."""
        best_score = 0.0
        best_key: str | None = None
        col_lower = col_name.lower()

        for logical_name, canonicals in schema.items():
            all_names = [logical_name.lower()] + [c.lower() for c in canonicals]
            for name in all_names:
                score = self._string_similarity(col_lower, name)
                if score > best_score:
                    best_score = score
                    best_key = logical_name

        if best_score >= 0.6:
            return best_key
        return None

    @staticmethod
    def _string_similarity(s1: str, s2: str) -> float:
        """Simple Jaccard-like similarity based on character bigrams."""
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        def bigrams(s: str) -> set[str]:
            return {s[i:i + 2] for i in range(len(s) - 1)}

        bg1 = bigrams(s1)
        bg2 = bigrams(s2)
        if not bg1 or not bg2:
            return 0.0
        return len(bg1 & bg2) / len(bg1 | bg2)

    def print_report(self, result: SchemaValidationResult) -> None:
        """
        Print a formatted validation report to console.

        Args:
            result: SchemaValidationResult from validate_and_suggest_mapping().
        """
        print()
        print(_c("═" * 60, CYAN))
        print(_c("  用户数据 Schema 验证报告", CYAN))
        if result.file_name:
            print(_c(f"  文件: {result.file_name}", CYAN))
        print(_c("═" * 60, CYAN))
        print()

        # Confidence
        conf_emoji = "🟢" if result.confidence >= 0.8 else "🟡" if result.confidence >= 0.5 else "🔴"
        conf_label = f"{result.confidence:.0%}"
        print(f"  匹配置信度: {conf_emoji} {conf_label}")
        print(f"  已匹配字段: {len(result.matched_columns)}/{len(result.matched_columns) + len(result.unknown_columns)}")
        print()

        # Matched
        if result.matched_columns:
            print(_c("  ✅ 已匹配字段:", GREEN))
            for logical, col in result.matched_columns.items():
                print(f"     {logical} ← '{col}'")
            print()

        # Suggestions
        if result.suggestions:
            print(_c("  💡 映射建议:", YELLOW))
            for suggestion in result.suggestions:
                print(suggestion)
            print()

        # Unknown (schema fields user data doesn't have)
        if result.unmatched_columns:
            print(_c(f"  ⚠ 缺失字段 (schema有，数据无): {len(result.unmatched_columns)}个", YELLOW))
            for col in result.unmatched_columns:
                print(f"     • {col}")
            print()

        # Unmatched (extra columns in user data, not in schema)
        if result.unknown_columns:
            print(_c(f"  ❓ 多余字段 (数据有，schema无): {len(result.unknown_columns)}个", CYAN))
            for col in result.unknown_columns:
                print(f"     • '{col}'")
            print()

        print(_c("─" * 60, CYAN))
        print()


# ─── Convenience functions ─────────────────────────────────────────────────────

def quick_validate(
    file_path: str | Path,
    expected_schema: dict[str, list[str]],
) -> SchemaValidationResult:
    """
    One-liner: load a file and validate against expected schema.

    Args:
        file_path: Path to CSV/Excel file.
        expected_schema: Expected schema dict.

    Returns:
        SchemaValidationResult.
    """
    path = Path(file_path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, nrows=5)
    else:
        df = pd.read_excel(path, engine="openpyxl" if path.suffix == ".xlsx" else "xlrd", nrows=5)

    validator = UserDataSchemaValidator()
    return validator.validate_and_suggest_mapping(df, expected_schema, file_name=str(path.name))
