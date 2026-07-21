"""DID Audit Guard — intercept mock data before DID estimation (PR5, Audit 2026-06-27).

解决问题 #6：DID 是否完备，是否欺诈调用模拟数据。

核心机制：
  - 在所有 DID 入口函数中强制调用 assert_real_data()
  - 检测 DataFrame 中的 mock sentinel 列（_synthetic, _mock, __MOCK__）
  - 检查 provenance_id 是否存在（由 provenance.py 注入）
  - 拦截时抛出 MockDataError，禁止悄悄使用模拟数据运行 DID

支持模块：
  - modern_did.py: ModernDiD.fit() / did_2x2() / cs() / sa() / gb() / dcdh()
  - rdd.py: RDDesign.run() / plot_rdd()
  - iv_panel.py: IVPanel.fit()
  - synthetic_did.py: SyntheticDiDEngine.estimate()

使用：
  # 自动织入（在 DID 函数入口调用）
  from scripts.core.did_audit_guard import assert_real_data, DID_AUDIT_ENABLED

  def did_2x2(df, ...):
      assert_real_data(df, "did_2x2")   # 抛 MockDataError 若为 mock
      ...

  # 手动检查
  python scripts/core/did_audit_guard.py --check-data ./data/panel.csv

  # 关闭审计（仅测试用）
  DID_AUDIT_ENABLED = False
"""

from __future__ import annotations

__all__ = [
    "MockDataError",
    "assert_real_data",
    "DID_AUDIT_ENABLED",
    "DID_AUDIT_CONFIG",
]

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# ─── Configuration ──────────────────────────────────────────────────────────────


# 全局开关：生产环境默认开启，测试时关闭
DID_AUDIT_ENABLED = os.getenv("DID_AUDIT_ENABLED", "true").lower() not in (
    "false", "0", "no", "off"
)

# sentinel 列名（来自各个 mock 数据生成器）
_MOCK_SENTINEL_COLUMNS = [
    "_synthetic",      # universal_data_fetcher.py / akshare fallback
    "_mock",           # demo_research_report.py
    "__MOCK__",       # data_fetcher.py
    "_mock_reason",   # demo_research_report.py
    "_sim",           # 通用模拟标记
    "data_source",    # green_credit_data.py（值为 "MOCK_DATA(DEMO)"）
]

# provenance 列名（来自 provenance.py）
_PROVENANCE_COLUMNS = [
    "provenance_id",
    "_provenance_id",
    "data_provenance",
]

# 若存在以下列且值为 mock 相关值，则认为数据不真实
_DATA_SOURCE_MOCK_VALUES = [
    "mock", "synthetic", "sim", "demo", "MOCK_DATA", "SYNTHETIC",
    "fake", "dummy",
]


# ─── Exception ────────────────────────────────────────────────────────────────


class MockDataError(Exception):
    """检测到使用模拟数据时抛出（禁止在正式 DID 分析中使用）。"""
    pass


# ─── Audit Result ──────────────────────────────────────────────────────────────


@dataclass
class DataAuditResult:
    """数据审计结果。"""
    is_real: bool
    method: str                    # 检测方法
    reason: str                   # 判断原因
    sentinel_columns: list[str]     # 检测到的 mock sentinel 列
    provenance_found: bool         # 是否找到 provenance 列
    data_source_values: list[str]   # data_source 列中的 mock 值
    recommendations: list[str]     # 建议


# ─── Core Functions ───────────────────────────────────────────────────────────


def assert_real_data(
    df: pd.DataFrame,
    context: str = "did",
    raise_on_mock: bool = True,
) -> DataAuditResult:
    """断言 DataFrame 为真实数据，非 mock。

    Args:
        df: 待检查的数据帧
        context: 上下文描述（用于错误信息）
        raise_on_mock: 为 True 时，若检测到 mock 数据则抛 MockDataError

    Returns:
        DataAuditResult: 审计结果

    Raises:
        MockDataError: 当 raise_on_mock=True 且检测到 mock 数据时
    """
    if not DID_AUDIT_ENABLED:
        return DataAuditResult(
            is_real=True,
            method="disabled",
            reason="DID_AUDIT_ENABLED=False，审计已关闭",
            sentinel_columns=[],
            provenance_found=False,
            data_source_values=[],
            recommendations=[],
        )

    result = _audit_dataframe(df, context)

    if raise_on_mock and not result.is_real:
        detail_parts = [
            f"❌ DID 审计拦截：{context} 使用了模拟数据",
            f"   原因: {result.reason}",
        ]
        if result.sentinel_columns:
            detail_parts.append(f"   检测到 sentinel 列: {result.sentinel_columns}")
        if result.data_source_values:
            detail_parts.append(f"   mock 值: {result.data_source_values}")
        detail_parts.append("")
        detail_parts.append("   解决方案：")
        detail_parts.append("   ① 使用真实数据文件（从 Tushare/akshare/CSMAR 获取）")
        detail_parts.append("   ② 在 REFINED_DESIGN.md 中更新数据源配置")
        detail_parts.append("   ③ 若仅用于演示：DID_AUDIT_ENABLED=false python your_script.py")
        detail_parts.append("")
        detail_parts.append("   禁止行为：")
        detail_parts.append("   🚫 不能将模拟数据的结果用于正式论文")
        raise MockDataError("\n".join(detail_parts))

    return result


def _audit_dataframe(df: pd.DataFrame, context: str) -> DataAuditResult:
    """执行数据帧审计。"""
    sentinel_columns: list[str] = []
    provenance_found = False
    mock_source_values: list[str] = []

    # 1. 检查 sentinel 列
    for col in df.columns:
        col_lower = str(col).lower()
        for sentinel in _MOCK_SENTINEL_COLUMNS:
            if sentinel in col_lower:
                sentinel_columns.append(str(col))
                break

    # 2. 检查 data_source 列的值
    for col in df.columns:
        col_lower = str(col).lower()
        if "data_source" in col_lower or "source" in col_lower:
            unique_vals = df[col].dropna().astype(str).unique()
            for val in unique_vals:
                val_lower = val.lower()
                for mock_val in _DATA_SOURCE_MOCK_VALUES:
                    if mock_val in val_lower:
                        mock_source_values.append(val)
                        break

    # 3. 检查 provenance 列是否存在
    for col in df.columns:
        if any(proven_col in str(col).lower() for proven_col in _PROVENANCE_COLUMNS):
            provenance_found = True
            break

    # 4. 综合判断
    is_real = len(sentinel_columns) == 0 and len(mock_source_values) == 0

    # 若有 provenance 列 → 优先认定为真实（provenance 溯源过）
    if provenance_found and len(sentinel_columns) == 0 and len(mock_source_values) == 0:
        is_real = True

    # 5. 生成建议
    recommendations = []
    if sentinel_columns:
        recommendations.append(f"移除 mock sentinel 列: {sentinel_columns}")
    if mock_source_values:
        recommendations.append(f"替换 data_source 列中的 mock 值: {set(mock_source_values)}")
    if not provenance_found:
        recommendations.append("建议在数据获取后注入 provenance_id（from scripts.core.provenance import record_transform）")

    reason_parts = []
    if sentinel_columns:
        reason_parts.append(f"发现 {len(sentinel_columns)} 个 sentinel 列")
    if mock_source_values:
        reason_parts.append(f"data_source 列含 mock 值: {set(mock_source_values)}")
    if provenance_found:
        reason_parts.append("存在 provenance_id（认为是真实数据）")
    if is_real:
        reason_parts.append("未检测到任何 mock 标记")

    return DataAuditResult(
        is_real=is_real,
        method="sentinel_check",
        reason="; ".join(reason_parts) if reason_parts else "未知",
        sentinel_columns=sentinel_columns,
        provenance_found=provenance_found,
        data_source_values=list(set(mock_source_values)),
        recommendations=recommendations,
    )


def audit_file(path: str | Path) -> DataAuditResult:
    """对 CSV/Parquet 文件执行审计（不抛异常）。"""
    path = Path(path)
    if not path.exists():
        return DataAuditResult(
            is_real=False,
            method="file_check",
            reason=f"文件不存在: {path}",
            sentinel_columns=[],
            provenance_found=False,
            data_source_values=[],
            recommendations=[f"创建文件或检查路径: {path}"],
        )

    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, nrows=1000)  # 只读前1000行加速
        elif path.suffix.lower() in (".parquet", ".pq"):
            df = pd.read_parquet(path)  # parquet 不支持 nrows
        else:
            return DataAuditResult(
                is_real=False,
                method="file_check",
                reason=f"不支持的文件格式: {path.suffix}",
                sentinel_columns=[],
                provenance_found=False,
                data_source_values=[],
                recommendations=["仅支持 CSV / Parquet 文件"],
            )
    except Exception as e:
        return DataAuditResult(
            is_real=False,
            method="file_check",
            reason=f"读取失败: {e}",
            sentinel_columns=[],
            provenance_found=False,
            data_source_values=[],
            recommendations=["检查文件是否损坏"],
        )

    return _audit_dataframe(df, str(path))


# ─── Decorator ───────────────────────────────────────────────────────────────


def audit_did_call(func):
    """装饰器：自动在 DID 函数入口执行 mock 数据审计。"""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 尝试从参数中提取 DataFrame
        # 第一个参数通常是 df
        df = None
        if args and isinstance(args[0], pd.DataFrame):
            df = args[0]
        # 或从 kwargs 中找
        if df is None:
            df = kwargs.get("df")

        if df is not None and DID_AUDIT_ENABLED:
            result = assert_real_data(df, context=func.__name__, raise_on_mock=True)
            # 记录审计日志
            _log = __import__("logging").getLogger("did_audit")
            if result.is_real:
                _log.info("✅ DID audit pass: %s", func.__name__)
            else:
                _log.error("❌ DID audit FAIL: %s — %s", func.__name__, result.reason)
                # MockDataError 已在 assert_real_data 中抛出

        return func(*args, **kwargs)

    return wrapper


# ─── Integration: DID methods ──────────────────────────────────────────────────


def install_audit_guard_into_modern_did() -> bool:
    """将审计守卫织入 ModernDiDEngine 类的入口方法。

    使用方法（在脚本启动时调用一次）：
        from scripts.core.did_audit_guard import install_audit_guard_into_modern_did
        install_audit_guard_into_modern_did()

    效果：所有 ModernDiDEngine 实例在创建时
          自动执行 assert_real_data(self.df)。

    Returns:
        True: 织入成功
        False: 织入失败（modern_did.py 未找到或 ModernDiDEngine 不存在）
    """
    try:
        from scripts.research_framework.modern_did import ModernDiDEngine
    except ImportError as exc:
        _log = __import__("logging").getLogger("did_audit")
        _log.warning(
            "modern_did.py 未找到，ModernDiDEngine DID 审计未织入: %s", exc
        )
        return False

    if not hasattr(ModernDiDEngine, "__init__"):
        return False

    _original_init = ModernDiDEngine.__init__

    def audited_init(self, df: pd.DataFrame, *args, **kwargs):
        # 在 __init__ 时拦截 mock 数据（df 必传）
        if df is not None and DID_AUDIT_ENABLED:
            result = assert_real_data(df, context="ModernDiDEngine.__init__")
            if not result.is_real:
                raise MockDataError(
                    f"ModernDiDEngine.__init__ 拒绝使用 mock 数据：{result.reason}\n"
                    f"sentinel 列: {result.sentinel_columns}\n"
                    f"recommendations: {result.recommendations}"
                )
        return _original_init(self, df, *args, **kwargs)

    ModernDiDEngine.__init__ = audited_init
    __import__("logging").getLogger("did_audit").info(
        "✅ DID 审计守卫已织入 ModernDiDEngine.__init__()"
    )
    return True


def install_audit_guard_into_rdd() -> bool:
    """将审计守卫织入 RDDEngine.__init__()（RDD 主类）。"""
    try:
        from scripts.research_framework.rdd import RDDEngine
    except ImportError as exc:
        __import__("logging").getLogger("did_audit").warning(
            "rdd.py 未找到，RDDEngine 审计未织入: %s", exc
        )
        return False

    if not hasattr(RDDEngine, "__init__"):
        return False

    _original_init = RDDEngine.__init__

    def audited_init(self, *args, **kwargs):
        # RDDEngine 的 __init__ 通常接收 df 作为第一个参数
        df = None
        if args and isinstance(args[0], pd.DataFrame):
            df = args[0]
        # audit-2026-07-05 PR-7F: avoid `df or ...` which calls DataFrame.__bool__
        if df is None:
            df = kwargs.get("df")
        if df is not None and DID_AUDIT_ENABLED:
            result = assert_real_data(df, context="RDDEngine.__init__")
            if not result.is_real:
                raise MockDataError(
                    f"RDDEngine.__init__ 拒绝使用 mock 数据：{result.reason}\n"
                    f"recommendations: {result.recommendations}"
                )
        return _original_init(self, *args, **kwargs)

    RDDEngine.__init__ = audited_init
    __import__("logging").getLogger("did_audit").info(
        "✅ DID 审计守卫已织入 RDDEngine.__init__()"
    )
    return True


def install_audit_guard_into_iv_panel() -> bool:
    """将审计守卫织入 IVPanel 类（如果存在）。"""
    try:
        from scripts.research_framework.iv_panel import IVPanel
    except ImportError as exc:
        __import__("logging").getLogger("did_audit").warning(
            "iv_panel.py 未找到，IVPanel DID 审计未织入: %s", exc
        )
        return False

    if not hasattr(IVPanel, "__init__"):
        return False

    _original_init = IVPanel.__init__

    def audited_init(self, *args, **kwargs):
        # IVPanel 通常接收 df 作为第一个参数
        df = None
        if args and isinstance(args[0], pd.DataFrame):
            df = args[0]
        # audit-2026-07-05 PR-7F: avoid `df or ...` which calls DataFrame.__bool__
        # and raises ValueError on pandas 3.0+. Use explicit None check.
        if df is None:
            df = kwargs.get("df")
        if df is not None and DID_AUDIT_ENABLED:
            result = assert_real_data(df, context="IVPanel.__init__")
            if not result.is_real:
                raise MockDataError(
                    f"IVPanel.__init__ 拒绝使用 mock 数据：{result.reason}"
                )
        return _original_init(self, *args, **kwargs)

    IVPanel.__init__ = audited_init
    __import__("logging").getLogger("did_audit").info(
        "✅ DID 审计守卫已织入 IVPanel.__init__()"
    )
    return True


def install_all_audit_guards() -> dict[str, bool]:
    """一键安装所有 DID 审计守卫。

    Returns:
        每个守卫的安装状态: {"modern_did": True, "rdd": True, "iv_panel": False}
    """
    return {
        "modern_did": install_audit_guard_into_modern_did(),
        "rdd": install_audit_guard_into_rdd(),
        "iv_panel": install_audit_guard_into_iv_panel(),
    }


def install_audit_guard_into_rdd() -> bool:
    """将审计守卫织入 RDDEngine.__init__()（RDD 主类）。"""
    try:
        from scripts.research_framework.rdd import RDDEngine
    except ImportError as exc:
        __import__("logging").getLogger("did_audit").warning(
            "rdd.py 未找到，RDDEngine 审计未织入: %s", exc
        )
        return False

    if not hasattr(RDDEngine, "__init__"):
        return False

    _original_init = RDDEngine.__init__

    def audited_init(self, *args, **kwargs):
        # RDDEngine 的 __init__ 通常接收 df 作为第一个参数
        df = None
        if args and isinstance(args[0], pd.DataFrame):
            df = args[0]
        # audit-2026-07-05 PR-7F: avoid `df or ...` which calls DataFrame.__bool__
        if df is None:
            df = kwargs.get("df")
        if df is not None and DID_AUDIT_ENABLED:
            result = assert_real_data(df, context="RDDEngine.__init__")
            if not result.is_real:
                raise MockDataError(
                    f"RDDEngine.__init__ 拒绝使用 mock 数据：{result.reason}\n"
                    f"recommendations: {result.recommendations}"
                )
        return _original_init(self, *args, **kwargs)

    RDDEngine.__init__ = audited_init
    __import__("logging").getLogger("did_audit").info(
        "✅ DID 审计守卫已织入 RDDEngine.__init__()"
    )
    return True


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DID 审计守卫 — 检测数据是否为 mock")
    parser.add_argument("--check-data", metavar="PATH",
                       help="检查 CSV/Parquet 文件是否为真实数据")
    parser.add_argument("--check-df", metavar="JSON",
                       help="检查内嵌 DataFrame JSON（用于测试）")
    parser.add_argument("--disable", action="store_true",
                       help="禁用 DID 审计（仅用于测试）")
    args = parser.parse_args()

    if args.disable:
        global DID_AUDIT_ENABLED
        DID_AUDIT_ENABLED = False
        print("✅ DID 审计已禁用（仅本次运行）")
        return

    if args.check_data:
        result = audit_file(args.check_data)
        print(f"\n🔍 数据审计 | {args.check_data}")
        print(f"   结果: {'✅ 真实数据' if result.is_real else '❌ Mock 数据'}")
        print(f"   方法: {result.method}")
        print(f"   原因: {result.reason}")
        if result.sentinel_columns:
            print(f"   sentinel 列: {result.sentinel_columns}")
        if result.data_source_values:
            print(f"   mock 值: {result.data_source_values}")
        if result.provenance_found:
            print(f"   provenance: ✅ 存在")
        if result.recommendations:
            print(f"   建议:")
            for rec in result.recommendations:
                print(f"     • {rec}")
        print()
        raise SystemExit(0 if result.is_real else 1)

    # 无参数：运行所有已知数据文件检查
    data_dir = Path("data")
    csv_files = list(data_dir.rglob("*.csv")) + list(data_dir.rglob("*.parquet"))
    print(f"\n🔍 扫描数据目录 | {data_dir} ({len(csv_files)} 个文件)")
    if not csv_files:
        print("   未找到数据文件")
        return

    real_count = 0
    for f in csv_files:
        result = audit_file(f)
        status = "✅" if result.is_real else "❌"
        print(f"   {status} {f.relative_to(data_dir)}")
        if result.is_real:
            real_count += 1

    print(f"\n   真实数据: {real_count}/{len(csv_files)}")


if __name__ == "__main__":
    main()
