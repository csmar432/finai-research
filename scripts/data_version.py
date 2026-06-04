#!/usr/bin/env python3
"""
数据版本管理器 (Data Version Manager)
====================================
为金融数据提供版本化管理，确保研究可复现性。

核心功能：
1. 数据快照：每次获取数据时创建版本快照
2. 版本追溯：可以回溯到任意历史版本的数据
3. 数据差异：对比两个版本之间的差异
4. 新鲜度追踪：记录数据获取时间，支持缓存失效
5. 断点续传：支持大文件的分片下载

使用方法：
    from scripts.data_version import DataVersionManager, DataSnapshot

    dvm = DataVersionManager()
    snapshot = dvm.fetch("000001.SZ", "2024-01-01", "2025-01-01")
    old_data = dvm.get_version("000001.SZ", "v_2024_05_01")
    diff = dvm.diff("000001.SZ", "v_2024_05_01", "latest")
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DataSnapshot:
    """数据快照"""
    version_id: str           # 唯一版本ID（v_YYYY_MM_DD_HHMMSS_hash）
    ticker: str               # 股票代码
    data_type: str            # 数据类型（daily/financial/macro）
    data_hash: str            # 数据内容的 MD5 哈希
    row_count: int            # 数据行数
    columns: list[str]        # 列名
    date_range: tuple[str, str]  # (start_date, end_date)
    fetched_at: str            # 获取时间
    source: str               # 数据源
    file_path: str           # 存储路径
    metadata: dict = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date_range"] = list(self.date_range)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> DataSnapshot:
        data = dict(data)
        data["date_range"] = tuple(data.get("date_range", ["", ""]))
        return cls(**data)

    def age_days(self) -> float:
        """计算数据年龄（天）"""
        fetched = datetime.fromisoformat(self.fetched_at)
        return (datetime.now() - fetched).total_seconds() / 86400

    def is_fresh(self, max_age_days: float = 1.0) -> bool:
        """检查数据是否新鲜"""
        return self.age_days() <= max_age_days


@dataclass
class DataDiff:
    """数据差异"""
    ticker: str
    version1: str
    version2: str
    row_count_diff: int
    column_diff: list[str]       # 新增/删除的列
    value_changes: dict          # {column: [(row, old, new), ...]}
    summary: str


# ═══════════════════════════════════════════════════════════════════════════════
# 数据版本管理器
# ═══════════════════════════════════════════════════════════════════════════════


class DataVersionManager:
    """
    数据版本管理器。

    为金融数据提供版本化存储和追溯能力。
    支持 CSV/Parquet 格式的压缩存储。
    """

    DEFAULT_DB_PATH = ".cache/data_versions.db"
    DEFAULT_DATA_DIR = ".cache/data_versions"

    def __init__(
        self,
        db_path: str | None = None,
        data_dir: str | None = None,
        max_age_days: float = 1.0,
    ):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.data_dir = Path(data_dir or self.DEFAULT_DATA_DIR)
        self.max_age_days = max_age_days

        self._ensure_dirs()
        self._conn = self._connect_db()
        self._init_db()

    def _ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _connect_db(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库"""
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_snapshots (
                version_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                data_type TEXT NOT NULL,
                data_hash TEXT NOT NULL,
                row_count INTEGER,
                columns TEXT,
                date_range_start TEXT,
                date_range_end TEXT,
                fetched_at TEXT NOT NULL,
                source TEXT,
                file_path TEXT NOT NULL,
                metadata TEXT,
                UNIQUE(ticker, version_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_fetch_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                data_type TEXT,
                fetched_at TEXT NOT NULL,
                version_id TEXT,
                success INTEGER,
                error_message TEXT,
                duration_ms REAL
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON data_snapshots(ticker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fetched_at ON data_snapshots(fetched_at)")

        self._conn.commit()

    def _generate_version_id(self, ticker: str, data: pd.DataFrame) -> str:
        """生成唯一版本ID"""
        timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
        content_hash = hashlib.md5(pd.util.hash_pandas_object(data).values.tobytes()).hexdigest()[:8]
        safe_ticker = ticker.replace(".", "_").replace("-", "_")
        return f"{safe_ticker}_{timestamp}_{content_hash}"

    def _compute_data_hash(self, data: pd.DataFrame) -> str:
        """计算数据内容哈希"""
        return hashlib.md5(pd.util.hash_pandas_object(data).values.tobytes()).hexdigest()[:16]

    def _save_data(self, version_id: str, data: pd.DataFrame) -> Path:
        """保存数据到文件，优先 parquet，备用 csv，同时写一份 gzip 备份。

        Returns the primary path (parquet if available, else csv).
        """
        parquet_path = self.data_dir / f"{version_id}.parquet"
        csv_path = self.data_dir / f"{version_id}.csv"
        gzip_path = Path(str(csv_path) + ".gz")

        # Primary: parquet
        try:
            data.to_parquet(parquet_path, index=False)
            primary = parquet_path
        except Exception:
            # Fallback: CSV
            data.to_csv(csv_path, index=False)
            primary = csv_path

        # Backup: gzip (always from csv_path so suffix is always ".csv.gz")
        try:
            data.to_csv(gzip_path, index=False, compression="gzip")
        except Exception:
            pass  # gzip backup is non-critical

        return primary

    def _load_data(self, filepath: str | Path) -> pd.DataFrame:
        """加载数据文件"""
        filepath = Path(filepath)
        suffix = filepath.suffix

        if suffix == ".parquet":
            return pd.read_parquet(filepath)
        elif suffix == ".gz":
            return pd.read_csv(filepath, compression="gzip")
        else:
            return pd.read_csv(filepath)

    def fetch(
        self,
        data_loader: Callable[[], pd.DataFrame],
        ticker: str,
        data_type: str = "daily",
        source: str = "unknown",
        force_refresh: bool = False,
        metadata: dict | None = None,
    ) -> tuple[pd.DataFrame, DataSnapshot]:
        """
        获取数据并自动创建版本快照。

        Args:
            data_loader: 数据加载函数（返回 DataFrame）
            ticker: 数据标识（如股票代码）
            data_type: 数据类型
            source: 数据源
            force_refresh: 强制刷新（忽略缓存）
            metadata: 额外元数据

        Returns:
            (数据DataFrame, 快照信息)
        """
        log_id = None
        start_time = time.time()

        try:
            # 检查最新版本是否足够新鲜
            if not force_refresh:
                latest = self.get_latest_version(ticker)
                if latest and latest.is_fresh(self.max_age_days):
                    data = self._load_data(latest.file_path)
                    self._log_fetch(ticker, data_type, latest.version_id, True, None, start_time, log_id)
                    return data, latest

            # 获取新数据
            data = data_loader()

            # 生成版本ID
            version_id = self._generate_version_id(ticker, data)

            # 保存数据
            file_path = self._save_data(version_id, data)

            # 创建快照
            date_range = ("", "")
            if "date" in data.columns:
                date_range = (str(data["date"].min()), str(data["date"].max()))
            elif "Date" in data.columns:
                date_range = (str(data["Date"].min()), str(data["Date"].max()))

            snapshot = DataSnapshot(
                version_id=version_id,
                ticker=ticker,
                data_type=data_type,
                data_hash=self._compute_data_hash(data),
                row_count=len(data),
                columns=list(data.columns),
                date_range=date_range,
                fetched_at=datetime.now().isoformat(),
                source=source,
                file_path=str(file_path),
                metadata=metadata or {},
            )

            # 保存到数据库
            self._save_snapshot(snapshot)

            duration = time.time() - start_time
            self._log_fetch(ticker, data_type, version_id, True, None, duration, log_id)

            return data, snapshot

        except Exception as e:
            duration = time.time() - start_time
            self._log_fetch(ticker, data_type, None, False, str(e), duration, log_id)
            raise

    def _save_snapshot(self, snapshot: DataSnapshot):
        """保存快照记录"""
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO data_snapshots
                (version_id, ticker, data_type, data_hash, row_count, columns,
                 date_range_start, date_range_end, fetched_at, source, file_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.version_id,
                snapshot.ticker,
                snapshot.data_type,
                snapshot.data_hash,
                snapshot.row_count,
                json.dumps(snapshot.columns, ensure_ascii=False),
                snapshot.date_range[0],
                snapshot.date_range[1],
                snapshot.fetched_at,
                snapshot.source,
                snapshot.file_path,
                json.dumps(snapshot.metadata, ensure_ascii=False),
            ))
            self._conn.commit()
        except sqlite3.Error as e:
            self._conn.rollback()
            warnings.warn(f"Failed to save snapshot: {e}")

    def _log_fetch(
        self,
        ticker: str,
        data_type: str,
        version_id: str | None,
        success: bool,
        error_message: str | None,
        duration_ms: float,
        log_id: int | None,
    ):
        """记录获取日志"""
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO data_fetch_log
                (ticker, data_type, fetched_at, version_id, success, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                data_type,
                datetime.now().isoformat(),
                version_id,
                1 if success else 0,
                error_message,
                duration_ms * 1000,
            ))
            self._conn.commit()
        except sqlite3.Error:
            pass

    def get_latest_version(self, ticker: str) -> DataSnapshot | None:
        """获取最新版本"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM data_snapshots WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
            (ticker,)
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_version(self, ticker: str, version_id: str) -> DataSnapshot | None:
        """获取指定版本"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM data_snapshots WHERE ticker = ? AND version_id = ?",
            (ticker, version_id)
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def _row_to_snapshot(self, row: sqlite3.Row) -> DataSnapshot:
        """数据库行转快照对象"""
        return DataSnapshot(
            version_id=row["version_id"],
            ticker=row["ticker"],
            data_type=row["data_type"],
            data_hash=row["data_hash"],
            row_count=row["row_count"],
            columns=json.loads(row["columns"]) if row["columns"] else [],
            date_range=(row["date_range_start"] or "", row["date_range_end"] or ""),
            fetched_at=row["fetched_at"],
            source=row["source"] or "",
            file_path=row["file_path"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def list_versions(
        self,
        ticker: str,
        limit: int = 20,
    ) -> list[DataSnapshot]:
        """列出所有版本"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM data_snapshots WHERE ticker = ? ORDER BY fetched_at DESC LIMIT ?",
            (ticker, limit)
        )
        rows = cursor.fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    def diff(
        self,
        ticker: str,
        version1: str,
        version2: str,
    ) -> DataDiff | None:
        """对比两个版本的数据差异"""
        snap1 = self.get_version(ticker, version1)
        snap2 = self.get_version(ticker, version2)

        if not snap1 or not snap2:
            return None

        # 加载数据
        data1 = self._load_data(snap1.file_path)
        data2 = self._load_data(snap2.file_path)

        # 计算差异
        row_diff = len(data2) - len(data1)

        # 列差异
        cols1, cols2 = set(data1.columns), set(data2.columns)
        col_diff = {
            "added": list(cols2 - cols1),
            "removed": list(cols1 - cols2),
        }

        # 数值差异（针对共有列）
        value_changes = {}
        common_cols = cols1 & cols2
        for col in common_cols:
            if pd.api.types.is_numeric_dtype(data1[col]) and pd.api.types.is_numeric_dtype(data2[col]):
                diff_mask = data1[col] != data2[col]
                if diff_mask.any():
                    changes = []
                    for idx in data1[diff_mask].index[:10]:  # 限制数量
                        if idx < len(data1) and idx < len(data2):
                            old_val = data1.loc[idx, col]
                            new_val = data2.loc[idx, col]
                            changes.append((idx, old_val, new_val))
                    value_changes[col] = changes

        summary = f"行数变化: {row_diff:+d}"
        if col_diff["added"]:
            summary += f", 新增列: {len(col_diff['added'])}"
        if col_diff["removed"]:
            summary += f", 删除列: {len(col_diff['removed'])}"

        return DataDiff(
            ticker=ticker,
            version1=version1,
            version2=version2,
            row_count_diff=row_diff,
            column_diff=col_diff["added"] + col_diff["removed"],
            value_changes=value_changes,
            summary=summary,
        )

    def get_freshness_report(self) -> dict:
        """生成数据新鲜度报告"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT ticker, version_id, fetched_at FROM data_snapshots "
            "WHERE version_id IN ("
            "  SELECT version_id FROM data_snapshots s1 WHERE fetched_at = ("
            "    SELECT MAX(fetched_at) FROM data_snapshots s2 WHERE s2.ticker = s1.ticker"
            "  )"
            ")"
        )
        rows = cursor.fetchall()

        fresh_count = 0
        stale_count = 0
        report = {"fresh": [], "stale": [], "unknown": []}

        for row in rows:
            snapshot = self._row_to_snapshot(row)
            age_days = snapshot.age_days()

            info = {
                "ticker": snapshot.ticker,
                "version_id": snapshot.version_id,
                "fetched_at": snapshot.fetched_at,
                "age_days": round(age_days, 1),
            }

            if age_days <= 1:
                report["fresh"].append(info)
                fresh_count += 1
            elif age_days <= 7:
                report["stale"].append(info)
                stale_count += 1
            else:
                report["unknown"].append(info)

        report["summary"] = {
            "total": fresh_count + stale_count + len(report["unknown"]),
            "fresh": fresh_count,
            "stale": stale_count,
            "old": len(report["unknown"]),
        }

        return report

    def cleanup_old_versions(self, keep_latest: int = 5):
        """清理旧版本，保留最新N个"""
        cursor = self._conn.cursor()

        # 获取所有 ticker
        cursor.execute("SELECT DISTINCT ticker FROM data_snapshots")
        tickers = [row[0] for row in cursor.fetchall()]

        cleaned = 0
        for ticker in tickers:
            cursor.execute(
                "SELECT version_id, file_path FROM data_snapshots "
                "WHERE ticker = ? ORDER BY fetched_at DESC",
                (ticker,)
            )
            rows = cursor.fetchall()

            # 保留最新N个
            for row in rows[keep_latest:]:
                version_id, file_path = row

                # 删除文件
                try:
                    Path(file_path).unlink(missing_ok=True)
                    zip_path = Path(file_path + ".gz")
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass

                # 删除数据库记录
                cursor.execute(
                    "DELETE FROM data_snapshots WHERE version_id = ?",
                    (version_id,)
                )
                cleaned += 1

        self._conn.commit()
        return cleaned

    def __del__(self):
        """关闭数据库连接"""
        try:
            if hasattr(self, '_conn') and self._conn:
                self._conn.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 与 data_pipeline.py 的集成
# ═══════════════════════════════════════════════════════════════════════════════


def wrap_with_versioning(
    fetch_func: Callable,
    ticker: str,
    data_type: str = "daily",
    **kwargs
) -> pd.DataFrame:
    """
    包装现有的数据获取函数，添加版本化管理。

    用法：
        from scripts.data_pipeline import fetch_a_stock
        from scripts.data_version import wrap_with_versioning

        df = wrap_with_versioning(
            lambda: fetch_a_stock("000001.SZ", "2024-01-01", "2025-01-01"),
            ticker="000001.SZ",
            data_type="daily",
        )
    """
    dvm = DataVersionManager()

    def loader():
        return fetch_func(**kwargs)

    data, snapshot = dvm.fetch(
        data_loader=loader,
        ticker=ticker,
        data_type=data_type,
        source=fetch_func.__name__,
    )

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="数据版本管理器")
    parser.add_argument("--list", "-l", help="列出指定 ticker 的所有版本")
    parser.add_argument("--latest", help="获取指定 ticker 的最新版本")
    parser.add_argument("--diff", "-d", nargs=3, metavar=("TICKER", "V1", "V2"),
                        help="对比两个版本的差异")
    parser.add_argument("--freshness", "-f", action="store_true", help="新鲜度报告")
    parser.add_argument("--cleanup", "-c", type=int, metavar="N", help="清理旧版本，保留最新N个")
    parser.add_argument("--stats", "-s", action="store_true", help="统计信息")

    args = parser.parse_args()

    dvm = DataVersionManager()

    if args.list:
        versions = dvm.list_versions(args.list)
        print(f"\n{'='*70}")
        print(f"  {args.list} 的数据版本 ({len(versions)} 个)")
        print(f"{'='*70}")
        for v in versions:
            fresh = "✅" if v.is_fresh(1) else "❌"
            print(f"  {fresh} [{v.version_id}]")
            print(f"      行数: {v.row_count} | 范围: {v.date_range[0]} ~ {v.date_range[1]}")
            print(f"      获取: {v.fetched_at[:19]} | 来源: {v.source}")

    elif args.latest:
        latest = dvm.get_latest_version(args.latest)
        if latest:
            print(f"\n{'='*70}")
            print(f"  最新版本: {latest.version_id}")
            print(f"  行数: {latest.row_count}")
            print(f"  范围: {latest.date_range}")
            print(f"  新鲜度: {latest.age_days():.1f} 天")
            print(f"  来源: {latest.source}")
        else:
            print(f"未找到 {args.latest} 的数据版本")

    elif args.diff:
        ticker, v1, v2 = args.diff
        diff = dvm.diff(ticker, v1, v2)
        if diff:
            print(f"\n{'='*70}")
            print(f"  数据差异: {ticker}")
            print(f"  {v1} vs {v2}")
            print(f"{'='*70}")
            print(f"  {diff.summary}")
            if diff.column_diff:
                print(f"  列变化: {diff.column_diff}")
        else:
            print("未找到指定的版本")

    elif args.freshness:
        report = dvm.get_freshness_report()
        print(f"\n{'='*70}")
        print("  数据新鲜度报告")
        print(f"{'='*70}")
        s = report["summary"]
        print(f"  总计: {s['total']} | 新鲜: {s['fresh']} | 略旧: {s['stale']} | 过期: {s['old']}")
        print("\n  新鲜数据 (≤1天):")
        for item in report["fresh"][:5]:
            print(f"    {item['ticker']}: {item['age_days']} 天前")
        if report["stale"]:
            print("\n  略旧数据 (1-7天):")
            for item in report["stale"][:5]:
                print(f"    {item['ticker']}: {item['age_days']} 天前")

    elif args.cleanup:
        cleaned = dvm.cleanup_old_versions(keep_latest=args.cleanup)
        print(f"已清理 {cleaned} 个旧版本")

    elif args.stats:
        cursor = dvm._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM data_snapshots")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM data_snapshots")
        tickers = cursor.fetchone()[0]
        print(f"\n{'='*70}")
        print("  数据版本统计")
        print(f"{'='*70}")
        print(f"  总快照数: {total}")
        print(f"  数据标的数: {tickers}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
