#!/usr/bin/env python3
"""
实验追踪系统 (Experiment Tracker)
================================
对实证分析实验进行全面追踪和可复现性保障。

核心功能：
1. 完整记录每次实验的配置（随机种子、数据集版本、参数）
2. 程序化计算实验结果（不依赖AI生成数字）
3. 交叉验证论文中的数值声明
4. 生成标准化的结果表格
5. 支持实验版本化

设计原则：
- 所有数值结果由程序化计算，不依赖AI生成
- 每个实验有唯一ID，支持版本追溯
- 自动关联 Git commit，确保代码可复现

使用方法：
    from scripts.experiment_tracker import ExperimentTracker, ExperimentRecord

    tracker = ExperimentTracker()
    tracker.log(ExperimentRecord(...))
    result = tracker.verify_claims(paper_text)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ExperimentConfig:
    """实验配置"""
    random_seed: int = 42
    dataset_version: str = ""
    dataset_source: str = ""
    data_time_range: str = ""
    model_params: dict = field(default_factory=dict)
    hyperparams: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExperimentResult:
    """实验结果"""
    metric_name: str              # 指标名（如 "roe_mean", "sharpe_ratio"）
    value: float                  # 数值
    std: float | None = None   # 标准差
    p_value: float | None = None  # p值
    ci_lower: float | None = None  # 置信区间下界
    ci_upper: float | None = None  # 置信区间上界
    sample_size: int = 0          # 样本量
    note: str = ""                 # 备注

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExperimentArtifact:
    """实验产物"""
    artifact_type: str   # table / figure / model / data
    path: str           # 文件路径
    description: str     # 描述
    format: str = ""    # 格式（png/csv/tex等）

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExperimentRecord:
    """
    完整的实验记录。
    包含配置、结果、产物，可追溯、可复现。
    """
    experiment_id: str
    session_id: str
    hypothesis: str              # 实验对应的假设
    title: str                   # 实验标题
    description: str              # 实验描述
    config: ExperimentConfig
    results: list[ExperimentResult]  # 结果列表
    artifacts: list[ExperimentArtifact]  # 产物列表
    parent_experiment_id: str = ""  # 父实验ID（用于消融实验）
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=datetime.now().isoformat)
    git_commit: str = ""
    status: str = "pending"       # pending / running / completed / failed

    def to_dict(self) -> dict:
        return asdict(self)

    def get_primary_metric(self) -> ExperimentResult | None:
        """获取主要指标（第一个结果）"""
        return self.results[0] if self.results else None

    def get_metric(self, name: str) -> ExperimentResult | None:
        """根据名称获取指标"""
        for r in self.results:
            if r.metric_name == name:
                return r
        return None

    def to_summary(self) -> str:
        """生成实验摘要"""
        lines = [
            f"**实验**: {self.title}",
            f"**ID**: `{self.experiment_id}`",
            f"**假设**: {self.hypothesis}",
            f"**时间**: {self.timestamp}",
            f"**状态**: {self.status}",
            "**结果**:",
        ]
        for r in self.results:
            val_str = f"{r.value:.4f}"
            if r.std is not None:
                val_str += f" ± {r.std:.4f}"
            if r.p_value is not None:
                sig = ""
                if r.p_value < 0.001:
                    sig = "***"
                elif r.p_value < 0.01:
                    sig = "**"
                elif r.p_value < 0.05:
                    sig = "*"
                val_str += f" {sig}"
            lines.append(f"  - {r.metric_name}: {val_str}")

        if self.artifacts:
            lines.append(f"**产物**: {len(self.artifacts)} 个文件")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 实验追踪器
# ═══════════════════════════════════════════════════════════════════════════════


class ExperimentTracker:
    """
    实验追踪器。
    提供完整的实验记录、结果验证和版本管理功能。
    """

    _write_lock = threading.Lock()
    DEFAULT_DB_PATH = ".cache/experiments.db"

    def __init__(self, db_path: str | None = None, session_id: str = "default"):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.session_id = session_id
        self._ensure_db_dir()
        self._conn = self._connect_db()
        self._init_db()

    def _ensure_db_dir(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _connect_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表"""
        cursor = self._conn.cursor()

        # 实验记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                session_id TEXT,
                title TEXT,
                description TEXT,
                hypothesis TEXT,
                config TEXT,
                results TEXT,
                artifacts TEXT,
                parent_experiment_id TEXT,
                tags TEXT,
                timestamp REAL,
                git_commit TEXT,
                status TEXT,
                UNIQUE(experiment_id)
            )
        """)

        # 论文声明表（用于交叉验证）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_claims (
                claim_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                claim_text TEXT,
                extracted_value REAL,
                metric_name TEXT,
                verification_status TEXT,
                verified_at REAL,
                FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
            )
        """)

        # 实验版本表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiment_versions (
                version_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                version_number INTEGER,
                config_snapshot TEXT,
                created_at REAL,
                FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_session ON experiments(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_timestamp ON experiments(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_exp ON paper_claims(experiment_id)")

        with self._write_lock:
            self._conn.commit()

    def _generate_id(self, title: str) -> str:
        """生成唯一的实验ID"""
        raw = f"{title}{datetime.now().isoformat()}{time.time()}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _get_git_commit(self) -> str:
        """获取当前 Git commit"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=Path(__file__).parent.parent
            )
            if result.returncode == 0:
                return result.stdout.strip()[:8]
        except Exception:
            pass
        return "unknown"

    def log(self, record: ExperimentRecord) -> str:
        """
        记录一个实验。

        Args:
            record: 实验记录

        Returns:
            实验ID
        """
        if not record.experiment_id:
            record.experiment_id = self._generate_id(record.title)

        if not record.git_commit:
            record.git_commit = self._get_git_commit()

        cursor = self._conn.cursor()
        try:
            with self._write_lock:
                cursor.execute("""
                    INSERT OR REPLACE INTO experiments
                    (experiment_id, session_id, title, description, hypothesis,
                     config, results, artifacts, parent_experiment_id, tags,
                     timestamp, git_commit, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.experiment_id,
                    record.session_id,
                    record.title,
                    record.description,
                    record.hypothesis,
                    json.dumps(record.config.to_dict() if hasattr(record.config, 'to_dict') else record.config, ensure_ascii=False),
                    json.dumps([r.to_dict() if hasattr(r, 'to_dict') else r for r in record.results], ensure_ascii=False),
                    json.dumps([a.to_dict() if hasattr(a, 'to_dict') else a for a in record.artifacts], ensure_ascii=False),
                    record.parent_experiment_id,
                    json.dumps(record.tags, ensure_ascii=False),
                    time.time(),
                    record.git_commit,
                    record.status,
                ))
                self._conn.commit()
        except sqlite3.Error as e:
            with self._write_lock:
                self._conn.rollback()
            warnings.warn(f"Failed to log experiment: {e}")

        return record.experiment_id

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        """根据ID获取实验记录"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_record(row)

    def _row_to_record(self, row: sqlite3.Row) -> ExperimentRecord:
        """将数据库行转换为 ExperimentRecord"""
        config = json.loads(row["config"]) if row["config"] else {}
        config_obj = ExperimentConfig(**config) if config else ExperimentConfig()

        results = json.loads(row["results"]) if row["results"] else []
        result_objs = [ExperimentResult(**r) for r in results]

        artifacts = json.loads(row["artifacts"]) if row["artifacts"] else []
        artifact_objs = [ExperimentArtifact(**a) for a in artifacts]

        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            session_id=row["session_id"],
            title=row["title"],
            description=row["description"],
            hypothesis=row["hypothesis"],
            config=config_obj,
            results=result_objs,
            artifacts=artifact_objs,
            parent_experiment_id=row["parent_experiment_id"] or "",
            tags=json.loads(row["tags"]) if row["tags"] else [],
            timestamp=row["timestamp"] if isinstance(row["timestamp"], str) else datetime.fromtimestamp(row["timestamp"]).isoformat(),
            git_commit=row["git_commit"],
            status=row["status"],
        )

    def list_experiments(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[ExperimentRecord]:
        """列出实验记录"""
        cursor = self._conn.cursor()

        query = "SELECT * FROM experiments"
        params = []

        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [self._row_to_record(row) for row in rows]

    def update_status(self, experiment_id: str, status: str):
        """更新实验状态"""
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE experiments SET status = ? WHERE experiment_id = ?",
                (status, experiment_id)
            )
            self._conn.commit()

    def add_artifact(
        self,
        experiment_id: str,
        artifact: ExperimentArtifact,
    ):
        """为实验添加产物"""
        record = self.get(experiment_id)
        if not record:
            return

        record.artifacts.append(artifact)
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE experiments SET artifacts = ? WHERE experiment_id = ?",
                (json.dumps([a.to_dict() if hasattr(a, 'to_dict') else a for a in record.artifacts], ensure_ascii=False), experiment_id)
            )
            self._conn.commit()

    # ═══════════════════════════════════════════════════════════════════════
    # 论文数值声明交叉验证
    # ═══════════════════════════════════════════════════════════════════════

    def extract_claims_from_text(self, text: str) -> list[dict]:
        """
        从论文文本中提取数值声明。

        匹配模式：
        - 指标名: 数值（如 "ROE 为 25.3%"）
        - 数值 + 指标（如 "提升了 15.2%"）
        - 带括号的统计量（如 "25.3 (3.2)"）
        """
        claims = []

        # 数值 + 百分比提升模式
        patterns = [
            # "提升了 X%"
            (r"提升了\s*([-+]?\d+\.?\d*)\s*%", "提升百分比", "increase"),
            # "从 X 增加到 Y"
            (r"从\s*([-+]?\d+\.?\d*)\s*增?加到\s*([-+]?\d+\.?\d*)", "增加量", "increase"),
            # "准确率为 X%"
            (r"(准确率?|ROE|PE|PB|收益率?|收益?|Sharpe|R²|AUC|F1)\s*[为是为]?\s*([-+]?\d+\.?\d*)\s*%?", "指标值", "value"),
            # "p < 0.05"
            (r"p\s*[<>=]\s*0\.?(\d+)", "p值", "pvalue"),
            # "25.3 (3.2)" 格式
            (r"([-+]?\d+\.?\d*)\s*\(([-]?\d+\.?\d*)\)", "均值(标准误)", "mean_se"),
        ]

        for pattern, metric_type, claim_type in patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                if len(groups) >= 1:
                    value_str = groups[0]
                    try:
                        value = float(value_str)
                        claims.append({
                            "raw_text": match.group(0),
                            "value": value,
                            "metric_type": metric_type,
                            "claim_type": claim_type,
                            "position": match.start(),
                        })
                    except ValueError:
                        continue

        return claims

    def verify_claims(
        self,
        experiment_id: str,
        paper_text: str,
    ) -> list[dict]:
        """
        验证论文中的数值声明是否与实验记录一致。

        Args:
            experiment_id: 实验ID
            paper_text: 论文文本

        Returns:
            验证结果列表
        """
        record = self.get(experiment_id)
        if not record:
            return [{"status": "error", "message": f"实验 {experiment_id} 不存在"}]

        claims = self.extract_claims_from_text(paper_text)
        results = []

        for claim in claims:
            verified = False
            message = ""
            expected_value = None

            # 与实验结果对比
            for result in record.results:
                # 简单匹配：检查数值是否接近
                if result.value is not None:
                    diff = abs(claim["value"] - result.value)
                    if diff < 0.01:  # 误差容忍
                        verified = True
                        expected_value = result.value
                        break
                    elif diff < abs(result.value) * 0.05:  # 5% 相对误差
                        verified = True
                        expected_value = result.value
                        message = f"数值接近（差异 {diff:.4f}）"
                        break

            if verified:
                status = "verified"
            else:
                status = "unverified"
                message = "未找到匹配的实验结果"

            verification = {
                "status": status,
                "raw_text": claim["raw_text"],
                "extracted_value": claim["value"],
                "expected_value": expected_value,
                "message": message,
                "metric_type": claim["metric_type"],
            }

            # 记录到数据库
            self._log_claim(experiment_id, verification)
            results.append(verification)

        return results

    def _log_claim(
        self,
        experiment_id: str,
        verification: dict,
    ):
        """记录验证结果到数据库"""
        claim_id = hashlib.md5(
            f"{experiment_id}{verification['raw_text']}{time.time()}".encode()
        ).hexdigest()[:12]

        with self._write_lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO paper_claims
                    (claim_id, experiment_id, claim_text, extracted_value,
                     metric_name, verification_status, verified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    claim_id,
                    experiment_id,
                    verification["raw_text"],
                    verification["extracted_value"],
                    verification.get("metric_type", ""),
                    verification["status"],
                    time.time(),
                ))
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()

    # ═══════════════════════════════════════════════════════════════════════
    # 结果表格生成
    # ═══════════════════════════════════════════════════════════════════════

    def generate_results_table(
        self,
        experiment_ids: list[str],
        format: str = "markdown",
    ) -> str:
        """
        生成标准化的实验结果表格。

        Args:
            experiment_ids: 实验ID列表
            format: 输出格式（markdown / latex / json）

        Returns:
            格式化后的表格字符串
        """
        records = [self.get(eid) for eid in experiment_ids if self.get(eid)]
        if not records:
            return ""

        if format == "json":
            return json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2)

        # Markdown / LaTeX 表格
        lines = []
        if format == "markdown":
            lines.append("| 实验 | 指标 | 均值 | 标准误 | p值 | 样本量 | 状态 |")
            lines.append("|------|------|------|--------|-----|--------|------|")
        elif format == "latex":
            lines.append(r"\begin{table}[htbp]")
            lines.append(r"\centering")
            lines.append(r"\caption{实验结果}")
            lines.append(r"\begin{tabular}{lrrrrr}")
            lines.append(r"\toprule")
            lines.append("实验 & 指标 & 均值 & 标准误 & p值 & 样本量 \\")
            lines.append(r"\midrule")

        for record in records:
            for result in record.results:
                if format == "markdown":
                    val_str = f"{result.value:.4f}"
                    std_str = f"({result.std:.4f})" if result.std is not None else "-"
                    p_str = f"{result.p_value:.4f}" if result.p_value is not None else "-"
                    n_str = f"{result.sample_size:,}" if result.sample_size else "-"

                    # 显著性标记
                    sig = ""
                    if result.p_value is not None:
                        if result.p_value < 0.001:
                            sig = "***"
                        elif result.p_value < 0.01:
                            sig = "**"
                        elif result.p_value < 0.05:
                            sig = "*"

                    lines.append(
                        f"| {record.title[:15]} | {result.metric_name} | "
                        f"{val_str}{sig} | {std_str} | {p_str} | {n_str} | "
                        f"{record.status} |"
                    )
                elif format == "latex":
                    val_str = f"${result.value:.4f}$"
                    std_str = f"$({result.std:.4f})$" if result.std is not None else "-"
                    p_str = f"${result.p_value:.4f}$" if result.p_value is not None else "-"
                    n_str = f"{result.sample_size:,}" if result.sample_size else "-"

                    sig = ""
                    if result.p_value is not None:
                        if result.p_value < 0.001:
                            sig = "$^{***}$"
                        elif result.p_value < 0.01:
                            sig = "$^{**}$"
                        elif result.p_value < 0.05:
                            sig = "$^{*}$"

                    lines.append(
                        f"{record.title[:15]} & {result.metric_name} & "
                        f"{val_str}{sig} & {std_str} & {p_str} & {n_str} \\\\"
                    )

        if format == "markdown":
            lines.append("")
        elif format == "latex":
            lines.append(r"\bottomrule")
            lines.append(r"\end{tabular}")
            lines.append(r"\end{table}")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════
    # 消融实验支持
    # ═══════════════════════════════════════════════════════════════════════

    def log_ablation(
        self,
        parent_id: str,
        component_name: str,
        component_value: str,
        results: list[ExperimentResult],
        config: ExperimentConfig | None = None,
    ) -> str:
        """
        记录消融实验。

        Args:
            parent_id: 父实验ID
            component_name: 被消融的组件名
            component_value: 组件值（如 "removed" / "modified"）
            results: 消融后的结果
            config: 配置

        Returns:
            新实验ID
        """
        parent = self.get(parent_id)
        if not parent:
            raise ValueError(f"父实验 {parent_id} 不存在")

        ablation_record = ExperimentRecord(
            experiment_id=self._generate_id(f"ablation_{parent.title}"),
            session_id=parent.session_id,
            title=f"{parent.title} - {component_name}: {component_value}",
            description=f"消融实验: {component_name}",
            hypothesis=parent.hypothesis,
            config=config or parent.config,
            results=results,
            artifacts=[],
            parent_experiment_id=parent_id,
            tags=["ablation", component_name],
            git_commit=self._get_git_commit(),
            status="completed",
        )

        return self.log(ablation_record)

    def compare_ablation(
        self,
        parent_id: str,
    ) -> list[dict]:
        """
        比较父实验与所有消融实验。

        Returns:
            比较结果列表
        """
        parent = self.get(parent_id)
        if not parent:
            return []

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM experiments WHERE parent_experiment_id = ? ORDER BY timestamp",
            (parent_id,)
        )
        rows = cursor.fetchall()

        comparisons = []
        for row in rows:
            ablation = self._row_to_record(row)
            for parent_result in parent.results:
                ablation_result = ablation.get_metric(parent_result.metric_name)
                if ablation_result:
                    diff = ablation_result.value - parent_result.value
                    diff_pct = (diff / parent_result.value * 100) if parent_result.value != 0 else 0

                    comparisons.append({
                        "parent_metric": parent_result.metric_name,
                        "parent_value": parent_result.value,
                        "ablation_title": ablation.title,
                        "ablation_value": ablation_result.value,
                        "difference": diff,
                        "difference_pct": diff_pct,
                        "contribution": "正向" if diff > 0 else "负向",
                    })

        return comparisons

    # ═══════════════════════════════════════════════════════════════════════
    # 实验版本化
    # ═══════════════════════════════════════════════════════════════════════

    def create_version(self, experiment_id: str) -> str:
        """创建实验配置的版本快照"""
        record = self.get(experiment_id)
        if not record:
            raise ValueError(f"实验 {experiment_id} 不存在")

        cursor = self._conn.cursor()

        # 获取当前最大版本号
        cursor.execute(
            "SELECT MAX(version_number) FROM experiment_versions WHERE experiment_id = ?",
            (experiment_id,)
        )
        max_version = cursor.fetchone()[0] or 0
        new_version = max_version + 1

        version_id = f"{experiment_id}_v{new_version}"

        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO experiment_versions
                (version_id, experiment_id, version_number, config_snapshot, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                version_id,
                experiment_id,
                new_version,
                json.dumps(record.config.to_dict() if hasattr(record.config, 'to_dict') else record.config, ensure_ascii=False),
                time.time(),
            ))
            self._conn.commit()

        return version_id

    def list_versions(self, experiment_id: str) -> list[dict]:
        """列出实验的所有版本"""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM experiment_versions WHERE experiment_id = ? ORDER BY version_number DESC",
            (experiment_id,)
        )
        rows = cursor.fetchall()

        return [
            {
                "version_id": row["version_id"],
                "version_number": row["version_number"],
                "created_at": datetime.fromtimestamp(row["created_at"]).isoformat(),
            }
            for row in rows
        ]

    # ═══════════════════════════════════════════════════════════════════════
    # 统计摘要
    # ═══════════════════════════════════════════════════════════════════════

    def summary(self, session_id: str | None = None) -> dict:
        """生成实验统计摘要"""
        cursor = self._conn.cursor()

        if session_id:
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE session_id = ?", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM experiments")
        total = cursor.fetchone()[0] or 0

        if session_id:
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE session_id = ? AND status = 'completed'", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE status = 'completed'")
        completed = cursor.fetchone()[0] or 0

        if session_id:
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE session_id = ? AND parent_experiment_id != ''", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM experiments WHERE parent_experiment_id != ''")
        ablations = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM paper_claims WHERE verification_status = 'verified'")
        verified_claims = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM paper_claims")
        total_claims = cursor.fetchone()[0] or 0

        return {
            "total_experiments": total,
            "completed_experiments": completed,
            "ablation_experiments": ablations,
            "verified_claims": verified_claims,
            "total_claims": total_claims,
            "verification_rate": verified_claims / total_claims if total_claims > 0 else 0,
        }

    def __del__(self):
        """关闭数据库连接"""
        try:
            if hasattr(self, '_conn') and self._conn:
                self._conn.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="实验追踪系统")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有实验")
    parser.add_argument("--get", "-g", help="获取指定实验")
    parser.add_argument("--summary", "-s", action="store_true", help="实验统计摘要")
    parser.add_argument("--verify", "-v", help="验证论文数值声明")
    parser.add_argument("--table", "-t", help="生成结果表格（传入实验ID，逗号分隔）")
    parser.add_argument("--format", "-f", choices=["markdown", "latex", "json"], default="markdown", help="表格格式")

    args = parser.parse_args()

    tracker = ExperimentTracker()

    if args.list:
        experiments = tracker.list_experiments()
        print(f"\n{'='*70}")
        print(f"  实验记录 ({len(experiments)} 个)")
        print(f"{'='*70}")
        for exp in experiments[:20]:
            print(f"\n{exp.to_summary()}")

    elif args.get:
        record = tracker.get(args.get)
        if record:
            print(f"\n{'='*70}")
            print(record.to_summary())
        else:
            print(f"实验 {args.get} 不存在")

    elif args.summary:
        summary = tracker.summary()
        print(f"\n{'='*70}")
        print("  实验统计")
        print(f"{'='*70}")
        print(f"  总实验数: {summary['total_experiments']}")
        print(f"  已完成: {summary['completed_experiments']}")
        print(f"  消融实验: {summary['ablation_experiments']}")
        print(f"  已验证声明: {summary['verified_claims']}/{summary['total_claims']}")
        print(f"  验证率: {summary['verification_rate']:.1%}")

    elif args.verify:
        paper_text = Path(args.verify).read_text(encoding="utf-8") if Path(args.verify).exists() else args.verify
        experiments = tracker.list_experiments(limit=1)
        if experiments:
            results = tracker.verify_claims(experiments[0].experiment_id, paper_text)
            print(f"\n{'='*70}")
            print("  数值声明验证")
            print(f"{'='*70}")
            for r in results:
                status_icon = "✅" if r["status"] == "verified" else "❌"
                print(f"  {status_icon} {r['raw_text']}")
                print(f"      提取值: {r['extracted_value']}")
                if r['expected_value'] is not None:
                    print(f"      期望值: {r['expected_value']}")
                print(f"      {r['message']}")

    elif args.table:
        exp_ids = [e.strip() for e in args.table.split(",")]
        table = tracker.generate_results_table(exp_ids, format=args.format)
        print(table)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
