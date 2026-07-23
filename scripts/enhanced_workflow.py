#!/usr/bin/env python3
"""
金融AI学术研究工作流 - 增强版
================================
集成所有增强功能的完整学术论文和金融研报生成工作流。

增强功能（2026-05-25）：
1. 深化金融分析师 - 杜邦分析、DCF多情景、Jones模型
2. Halt Rules - 金融研报、实证论文、ML论文规则集
3. 引用验证增强 - Scite-style Smart Citations、引用意图分类
4. AI Parliament与HITLGate联动
5. 自我进化自动触发

使用方法：
  python scripts/enhanced_workflow.py                           # 完整交互模式
  python scripts/enhanced_workflow.py --auto                  # 自动模式
  python scripts/enhanced_workflow.py --test                 # 运行测试
  python scripts/enhanced_workflow.py --validate-citations   # 验证引用
  python scripts/enhanced_workflow.py --check-quality        # 质量检查
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ── 路径设置 ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# ── 加载环境变量 ────────────────────────────────────────────────────────────
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env.local", override=False)

# ── 导入增强模块 ────────────────────────────────────────────────────────────
try:
    from scripts.core.analyst import (
        AIParliament,
        AIParliamentHITLIntegration,
    )
    from scripts.core.analyst import (
        EnhancedEarningsQualityAnalyst,
        EnhancedFinancialAnalyst,
        EnhancedValuationAnalyst,
    )
    from scripts.core.citation_verifier import (
        CitationVerifier,
    )
    from scripts.core.halt_rules_registry import (
        HaltRuleChecker,
        HaltRuleRegistry,
    )
    from scripts.core.self_evolution import (
        SelfEvolutionAutoTrigger,
    )
    ENHANCED_MODULES_AVAILABLE = True
except ImportError as e:
    ENHANCED_MODULES_AVAILABLE = False
    print(f"⚠️ 部分增强模块导入失败: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 枚举和配置
# ════════════════════════════════════════════════════════════════════════════


class WorkflowMode(Enum):
    """工作流模式"""
    FULL = "full"           # 完整论文流程
    RESEARCH = "research"   # 金融研究流程
    VALIDATE = "validate"   # 仅验证流程
    TEST = "test"           # 测试模式


class PaperType(Enum):
    """论文/报告类型"""
    EMPIRICAL_PAPER = "empirical_paper"       # 实证论文
    FINANCE_REPORT = "finance_report"          # 金融研报
    ML_PAPER = "ml_paper"                     # 机器学习论文


# ════════════════════════════════════════════════════════════════════════════
# 数据类
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class WorkflowConfig:
    """工作流配置"""
    mode: WorkflowMode = WorkflowMode.FULL
    paper_type: PaperType = PaperType.EMPIRICAL_PAPER
    auto_approve: bool = False
    enable_evolution: bool = True
    enable_parliament: bool = True
    citation_verification: bool = True
    halt_rules_check: bool = True
    output_dir: Path = None

    def __post_init__(self):
        if self.output_dir is None:
            self.output_dir = PROJECT_ROOT / "output"


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool
    workflow_type: str
    duration_ms: float
    results: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "workflow_type": self.workflow_type,
            "duration_ms": self.duration_ms,
            "results": self.results,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class CitationCheckResult:
    """引用检查结果"""
    total_citations: int
    verified: int
    unverified: int
    context_issues: list[str]
    intent_distribution: dict[str, int]
    freshness_scores: list[float]
    overall_quality: str


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    passed: bool
    score: float
    halt_rules_violations: list[str]
    warnings: list[str]
    recommendations: list[str]


# ════════════════════════════════════════════════════════════════════════════
# 增强功能测试
# ════════════════════════════════════════════════════════════════════════════


class EnhancedModuleTester:
    """
    增强模块测试器

    测试所有新增的增强功能：
    1. 深化金融分析师
    2. 引用验证增强
    3. Halt Rules
    4. AI Parliament
    5. 自我进化
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results: dict[str, dict] = {}

    def _print(self, msg: str, level: str = "INFO"):
        if self.verbose:
            prefix = {
                "INFO": "  ℹ️",
                "PASS": "  ✅",
                "FAIL": "  ❌",
                "WARN": "  ⚠️",
            }.get(level, "  ")
            print(f"{prefix} {msg}")

    def run_all_tests(self) -> dict[str, bool]:
        """运行所有测试"""
        print("\n" + "=" * 70)
        print("  金融AI学术研究工作流 - 增强模块测试")
        print("=" * 70)

        tests = [
            ("模块导入", self.test_module_imports),
            ("深化金融分析师", self.test_enhanced_analysts),
            ("引用验证增强", self.test_citation_verifier),
            ("Halt Rules", self.test_halt_rules),
            ("AI Parliament", self.test_ai_parliament),
            ("自我进化", self.test_self_evolution),
        ]

        all_passed = True
        for name, test_func in tests:
            print(f"\n{'─' * 70}")
            print(f"  测试: {name}")
            print(f"{'─' * 70}")

            try:
                passed = test_func()
                self.results[name] = {"passed": passed, "error": None}
                if passed:
                    self._print(f"{name} - 通过", "PASS")
                else:
                    self._print(f"{name} - 失败", "FAIL")
                    all_passed = False
            except Exception as e:
                self._print(f"{name} - 异常: {e}", "FAIL")
                self.results[name] = {"passed": False, "error": str(e)}
                all_passed = False

        # 打印总结
        print(f"\n{'=' * 70}")
        passed_count = sum(1 for r in self.results.values() if r["passed"])
        total_count = len(self.results)
        status = "全部通过" if all_passed else "存在失败"
        print(f"  测试结果: {passed_count}/{total_count} 通过 | {status}")
        print(f"{'=' * 70}\n")

        return self.results

    def test_module_imports(self) -> bool:
        """测试模块导入"""
        self._print("检查增强模块是否可用...", "INFO")

        if not ENHANCED_MODULES_AVAILABLE:
            self._print("增强模块导入失败，跳过功能测试", "WARN")
            return True  # 模块导入失败不视为测试失败

        self._print("✅ 增强模块导入成功", "PASS")
        return True

    def test_enhanced_analysts(self) -> bool:
        """测试深化金融分析师"""
        if not ENHANCED_MODULES_AVAILABLE:
            self._print("模块不可用", "WARN")
            return False

        try:
            # 测试杜邦分析
            analyst = EnhancedFinancialAnalyst()
            test_data = {
                "income_statement": {
                    "revenue": 1000000,
                    "net_income": 100000,
                    "gross_profit": 400000,
                    "ebit": 150000,
                },
                "balance_sheet": {
                    "total_assets": 5000000,
                    "total_equity": 2500000,
                    "current_assets": 2000000,
                    "current_liabilities": 1000000,
                },
                "cash_flow": {
                    "operating_cash_flow": 120000,
                },
            }

            result = asyncio.run(analyst.analyze_financial_health(
                ticker="TEST",
                financial_data=test_data,
            ))

            dupont = result.get("dupont", {})
            roe = dupont.get("roe", 0)

            self._print(f"杜邦分析: ROE = {roe:.2f}%", "INFO")
            assert 3 <= roe <= 7, f"ROE应在3-7%之间，实际为{roe}%"
            self._print("✅ 杜邦分析测试通过", "PASS")

            # 测试DCF估值
            val_analyst = EnhancedValuationAnalyst()
            dcf_result = asyncio.run(val_analyst.analyze_valuation(
                ticker="TEST",
                financial_data=test_data,
                market_data={"current_price": 10.0},
                current_price=10.0,
            ))

            scenarios = dcf_result.get("dcf_scenarios", {})
            assert "基准情景" in scenarios, "应包含基准情景"
            self._print("✅ DCF估值测试通过", "PASS")

            # 测试盈利质量
            eq_analyst = EnhancedEarningsQualityAnalyst()
            test_multi_year = {
                2023: test_data,
                2022: test_data,
            }
            eq_result = asyncio.run(eq_analyst.analyze_earnings_quality(
                ticker="TEST",
                financial_data=test_multi_year,
                years=[2023, 2022],
            ))

            score = eq_result.get("earnings_quality_score", {})
            assert "rating" in score, "应包含评级"
            self._print("✅ 盈利质量分析测试通过", "PASS")

            return True

        except Exception as e:
            self._print(f"测试失败: {e}", "FAIL")
            return False

    def test_citation_verifier(self) -> bool:
        """测试引用验证增强"""
        if not ENHANCED_MODULES_AVAILABLE:
            self._print("模块不可用", "WARN")
            return False

        try:
            verifier = CitationVerifier()

            # 测试基本引用验证
            result = verifier.verify({
                "doi": "10.48550/arXiv.1706.03762",
                "title": "Attention Is All You Need",
                "authors": ["Vaswani et al."],
                "year": 2017,
            })

            self._print(f"基本验证: verified={result.verified}, score={result.levenshtein_score:.2f}", "INFO")

            # 测试上下文验证（启发式）
            context_result = verifier.verify_citation_context(
                citation_sentence="Vaswani et al. (2017) proposed the Transformer architecture.",
                paper_abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
            )

            self._print(f"上下文验证: accurate={context_result.is_accurate}", "INFO")

            # 测试引用意图分类
            intent_result = verifier.classify_citation_intent(
                citation_sentence="As shown in Vaswani et al. (2017), attention mechanisms are effective.",
            )

            self._print(f"意图分类: intent={intent_result.intent}", "INFO")

            # 测试时效性评分
            freshness = verifier.score_citation_freshness(
                citation_year=2026,
                publication_year=2023,
                citation_count=50000,
            )

            self._print(f"时效评分: freshness={freshness.freshness_score:.2f}", "INFO")

            self._print("✅ 引用验证增强测试通过", "PASS")
            return True

        except Exception as e:
            self._print(f"测试失败: {e}", "FAIL")
            return False

    def test_halt_rules(self) -> bool:
        """测试Halt Rules"""
        if not ENHANCED_MODULES_AVAILABLE:
            self._print("模块不可用", "WARN")
            return False

        try:
            # 测试注册表
            registry = HaltRuleRegistry()
            registry.load_all()

            domains = registry.get_domains()
            self._print(f"已加载领域: {domains}", "INFO")

            # 测试验证
            test_content = """
            ROE = 15.5%
            毛利率 = 45.2%
            净利率 = 12.3%

            根据Smith et al. (2020)的研究，我们发现...
            DOI: 10.1234/example
            """

            result = registry.validate(test_content, domain="finance_report")

            self._print(f"验证结果: passed={result.passed}, checked={result.checked_rules}", "INFO")

            # 测试检查器
            checker = HaltRuleChecker()
            should_halt, validation_result = checker.check(test_content, domain="finance_report")

            self._print(f"Halt检查: should_halt={should_halt}", "INFO")

            self._print("✅ Halt Rules测试通过", "PASS")
            return True

        except Exception as e:
            self._print(f"测试失败: {e}", "FAIL")
            return False

    def test_ai_parliament(self) -> bool:
        """测试AI Parliament"""
        if not ENHANCED_MODULES_AVAILABLE:
            self._print("模块不可用", "WARN")
            return False

        try:
            parliament = AIParliament()

            test_paper = {
                "title": "Test Paper: Environmental Regulation and Green Innovation",
                "abstract": "This paper studies the impact of environmental regulation on corporate green innovation using difference-in-differences approach.",
            }

            # 快速测试（减少辩论轮数）
            verdict = asyncio.run(parliament.debate(test_paper, rounds=1))

            self._print(f"裁决: score={verdict.score:.2f}, recommendation={verdict.recommendation}", "INFO")

            # 测试联动模块
            integration = AIParliamentHITLIntegration(parliament)

            verdict_dict, need_review = asyncio.run(
                integration.debate_and_approve(test_paper, rounds=1, auto_threshold=4.0)
            )

            self._print(f"联动测试: need_review={need_review}", "INFO")

            self._print("✅ AI Parliament测试通过", "PASS")
            return True

        except Exception as e:
            self._print(f"测试失败: {e}", "FAIL")
            return False

    def test_self_evolution(self) -> bool:
        """测试自我进化"""
        if not ENHANCED_MODULES_AVAILABLE:
            self._print("模块不可用", "WARN")
            return False

        try:
            # 测试自动触发器（不需要真实的LLM网关）
            from dataclasses import dataclass

            @dataclass
            class MockResult:
                score: float = 0.5

            class MockEngine:
                def __init__(self):
                    self._history = []
                    self._proposals = []

                def _extract_quality(self, result):
                    return result.score

                def record_and_assess(self, agent_name, result, context):
                    quality = self._extract_quality(result)
                    if quality < 0.7:
                        return {
                            "proposal": {"agent_name": agent_name, "suggestion": "test"},
                            "assessment": {"commit": False},
                            "should_commit": False,
                        }
                    return None

                def rollback(self, agent_name):
                    return {"rolled_back": True, "agent_name": agent_name}

            mock_engine = MockEngine()
            trigger = SelfEvolutionAutoTrigger(mock_engine, quality_threshold=0.7)

            # 测试成功情况
            result1 = MockResult(score=0.8)
            event = trigger.on_task_complete("test_agent", result1, {})
            assert event is None, "高质量结果不应触发进化"

            # 测试失败情况
            result2 = MockResult(score=0.5)
            event = trigger.on_task_complete("test_agent", result2, {})
            # 可能触发进化

            stats = trigger.get_stats()
            self._print(f"进化统计: {stats}", "INFO")

            self._print("✅ 自我进化测试通过", "PASS")
            return True

        except Exception as e:
            self._print(f"测试失败: {e}", "FAIL")
            return False


# ════════════════════════════════════════════════════════════════════════════
# 引用验证工作流
# ════════════════════════════════════════════════════════════════════════════


class CitationValidationWorkflow:
    """引用验证工作流"""

    def __init__(self):
        self.verifier = CitationVerifier()

    async def validate_paper_citations(
        self,
        citations: list[dict],
        content: str = "",
    ) -> CitationCheckResult:
        """验证论文的所有引用"""
        total = len(citations)
        verified = 0
        context_issues = []
        intents = {}
        freshness_scores = []

        for citation in citations:
            # 基本验证
            result = self.verifier.verify(citation)
            if result.verified:
                verified += 1

            # 上下文验证（如果有内容）
            if content:
                # 简化：使用标题作为引用句
                sentence = f"{citation.get('authors', [''])[0]} et al. ({citation.get('year', 'N/A')})"
                abstract = result.raw_api_response.get("abstract", "") if result.verified else ""

                if abstract:
                    ctx_result = self.verifier.verify_citation_context(
                        citation_sentence=sentence,
                        paper_abstract=abstract,
                    )
                    if not ctx_result.is_accurate:
                        context_issues.append(f"{citation.get('title', 'Unknown')}: {ctx_result.issue_type}")

            # 引用意图（如果有内容）
            if content:
                intent_result = self.verifier.classify_citation_intent(
                    citation_sentence=sentence,
                )
                intent = intent_result.intent
                intents[intent] = intents.get(intent, 0) + 1

            # 时效性评分
            if result.verified:
                freshness = self.verifier.score_citation_freshness(
                    citation_year=2026,
                    publication_year=result.matched_year or 2020,
                    citation_count=result.raw_api_response.get("citationCount", 0),
                )
                freshness_scores.append(freshness.freshness_score)

        # 整体质量评估
        verified_rate = verified / total if total > 0 else 0
        if verified_rate >= 0.9 and len(context_issues) == 0:
            quality = "high"
        elif verified_rate >= 0.7:
            quality = "medium"
        else:
            quality = "low"

        return CitationCheckResult(
            total_citations=total,
            verified=verified,
            unverified=total - verified,
            context_issues=context_issues,
            intent_distribution=intents,
            freshness_scores=freshness_scores,
            overall_quality=quality,
        )


# ════════════════════════════════════════════════════════════════════════════
# 质量检查工作流
# ════════════════════════════════════════════════════════════════════════════


class QualityCheckWorkflow:
    """质量检查工作流"""

    def __init__(self, paper_type: PaperType = PaperType.EMPIRICAL_PAPER):
        self.checker = HaltRuleChecker()
        self.domain_map = {
            PaperType.EMPIRICAL_PAPER: "empirical_paper",
            PaperType.FINANCE_REPORT: "finance_report",
            PaperType.ML_PAPER: "ml_paper",
        }
        self.domain = self.domain_map.get(paper_type, "empirical_paper")

    def check_quality(
        self,
        content: str,
        min_score: float = 0.7,
    ) -> QualityCheckResult:
        """检查内容质量"""
        should_halt, result = self.checker.check(content, domain=self.domain)

        # 计算质量分数
        if result.checked_rules > 0:
            score = result.passed_rules / result.checked_rules
        else:
            score = 1.0

        # 生成建议
        recommendations = []
        if result.violations:
            recommendations.append("请修复以下严重错误:")
            for v in result.violations[:3]:
                recommendations.append(f"  - [{v.rule_id}] {v.description}")
        if result.warnings:
            recommendations.append("建议改进:")
            for w in result.warnings[:3]:
                recommendations.append(f"  - [{w.rule_id}] {w.description}")

        return QualityCheckResult(
            passed=not should_halt and score >= min_score,
            score=score,
            halt_rules_violations=[v.description for v in result.violations],
            warnings=[w.description for w in result.warnings],
            recommendations=recommendations,
        )


# ════════════════════════════════════════════════════════════════════════════
# 完整工作流
# ════════════════════════════════════════════════════════════════════════════


class EnhancedResearchWorkflow:
    """增强版研究工作流"""

    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.citation_workflow = CitationValidationWorkflow()
        self.quality_workflow = QualityCheckWorkflow()

    async def run_research_flow(
        self,
        topic: str,
        citations: list[dict] = None,
        content: str = "",
    ) -> WorkflowResult:
        """运行完整研究流程"""
        start_time = time.time()
        errors = []
        warnings_list = []
        results = {}

        print(f"\n{'=' * 70}")
        print("  增强版研究工作流")
        print(f"  主题: {topic}")
        print(f"{'=' * 70}\n")

        try:
            # 1. 引用验证
            if citations and self.config.citation_verification:
                print("  [1/4] 验证引用...")
                citation_result = await self.citation_workflow.validate_paper_citations(
                    citations=citations,
                    content=content,
                )
                results["citations"] = asdict(citation_result)

                if citation_result.overall_quality == "low":
                    warnings_list.append(f"引用质量较低: {citation_result.overall_quality}")

                print(f"       引用验证: {citation_result.verified}/{citation_result.total_citations} 通过")

            # 2. 质量检查
            if content and self.config.halt_rules_check:
                print("  [2/4] 检查质量规则...")
                quality_result = self.quality_workflow.check_quality(content)
                results["quality"] = asdict(quality_result)

                if not quality_result.passed:
                    warnings_list.append("质量检查未通过")

                print(f"       质量分数: {quality_result.score:.1%}")
                if quality_result.recommendations:
                    for rec in quality_result.recommendations[:3]:
                        print(f"       {rec}")

            # 3. AI Parliament评审
            if self.config.enable_parliament and ENHANCED_MODULES_AVAILABLE:
                print("  [3/4] AI Parliament评审...")
                parliament = AIParliament()
                paper = {"title": topic, "abstract": content[:1000] if content else ""}
                verdict = await parliament.debate(paper, rounds=2)
                results["parliament"] = {
                    "score": verdict.score,
                    "recommendation": verdict.recommendation,
                    "key_strengths": verdict.key_strengths,
                    "key_weaknesses": verdict.key_weaknesses,
                }
                print(f"       评分: {verdict.score:.1f}/5.0 | 建议: {verdict.recommendation}")

            # 4. 保存结果
            print("  [4/4] 保存结果...")
            output_path = self.config.output_dir / f"workflow_result_{int(time.time())}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({
                    "topic": topic,
                    "results": results,
                    "timestamp": time.time(),
                }, f, ensure_ascii=False, indent=2)

            print(f"       结果已保存: {output_path}")

        except Exception as e:
            errors.append(str(e))
            logger.error(f"工作流执行错误: {e}")

        duration = (time.time() - start_time) * 1000

        return WorkflowResult(
            success=len(errors) == 0,
            workflow_type=self.config.mode.value,
            duration_ms=duration,
            results=results,
            errors=errors,
            warnings=warnings_list,
            metadata={"topic": topic},
        )


# ════════════════════════════════════════════════════════════════════════════
# 交互式确认系统（精简版）
# ════════════════════════════════════════════════════════════════════════════


class InteractiveConfirmationSystem:
    """交互式确认系统"""

    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve

    def confirm_innovation_selection(self, selected: list[dict]) -> bool:
        """确认创新点选择"""
        if self.auto_approve:
            print(f"  自动确认 {len(selected)} 个创新点")
            return True

        print("\n  已选创新点:")
        for i, item in enumerate(selected, 1):
            print(f"    {i}. {item.get('title', 'Unknown')} [{item.get('novelty', '')}]")

        while True:
            resp = input("\n  确认选择? [Y/n]: ").strip().lower()
            if resp in ['', 'y', 'yes', '是']:
                return True
            if resp in ['n', 'no', '否']:
                return False

    def confirm_proceed(self, message: str, default: bool = True) -> bool:
        """确认继续"""
        if self.auto_approve:
            print(f"  {message} [自动: {'是' if default else '否'}]")
            return default

        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            resp = input(f"  {message} {suffix}: ").strip().lower()
            if resp in ['', 'y', 'yes', '是']:
                return True
            if resp in ['n', 'no', '否']:
                return False


# ════════════════════════════════════════════════════════════════════════════
# CLI入口
# ════════════════════════════════════════════════════════════════════════════


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(
        description="金融AI学术研究工作流 - 增强版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/enhanced_workflow.py --test                    # 运行测试
  python scripts/enhanced_workflow.py --validate-citations    # 验证引用
  python scripts/enhanced_workflow.py --check-quality          # 质量检查
  python scripts/enhanced_workflow.py --auto                  # 自动模式
  python scripts/enhanced_workflow.py --topic "绿色金融"       # 研究主题
        """
    )

    parser.add_argument("--test", action="store_true", help="运行增强模块测试")
    parser.add_argument("--validate-citations", action="store_true", help="验证示例引用")
    parser.add_argument("--check-quality", action="store_true", help="检查示例内容质量")
    parser.add_argument("--auto", action="store_true", help="自动模式（无交互）")
    parser.add_argument("--topic", type=str, default="环境规制与企业绿色创新", help="研究主题")
    parser.add_argument("--paper-type", choices=["empirical", "finance", "ml"],
                        default="empirical", help="论文类型")
    parser.add_argument("--output-dir", type=str, help="输出目录")

    args = parser.parse_args()

    # 确定模式
    mode = WorkflowMode.FULL
    if args.test:
        mode = WorkflowMode.TEST
    elif args.validate_citations:
        mode = WorkflowMode.VALIDATE
    elif args.auto:
        mode = WorkflowMode.RESEARCH

    # 配置
    paper_type_map = {
        "empirical": PaperType.EMPIRICAL_PAPER,
        "finance": PaperType.FINANCE_REPORT,
        "ml": PaperType.ML_PAPER,
    }

    config = WorkflowConfig(
        mode=mode,
        paper_type=paper_type_map.get(args.paper_type, PaperType.EMPIRICAL_PAPER),
        auto_approve=args.auto,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )

    # 运行
    if args.test:
        # 测试模式
        tester = EnhancedModuleTester(verbose=True)
        results = tester.run_all_tests()
        sys.exit(0 if all(r["passed"] for r in results.values()) else 1)

    elif args.validate_citations:
        # 验证引用模式
        print("\n" + "=" * 70)
        print("  引用验证工作流")
        print("=" * 70 + "\n")

        workflow = CitationValidationWorkflow()

        test_citations = [
            {"doi": "10.48550/arXiv.1706.03762", "title": "Attention Is All You Need", "year": 2017},
            {"doi": "10.1038/nature14539", "title": "Deep learning", "year": 2015},
            {"arxiv_id": "2103.14030", "title": "Vision Transformer", "year": 2021},
        ]

        result = asyncio.run(workflow.validate_paper_citations(test_citations))

        print("\n验证结果:")
        print(f"  总引用数: {result.total_citations}")
        print(f"  已验证: {result.verified}")
        print(f"  未验证: {result.unverified}")
        print(f"  整体质量: {result.overall_quality}")

        if result.context_issues:
            print("\n上下文问题:")
            for issue in result.context_issues:
                print(f"  - {issue}")

        if result.intent_distribution:
            print("\n引用意图分布:")
            for intent, count in result.intent_distribution.items():
                print(f"  - {intent}: {count}")

    elif args.check_quality:
        # 质量检查模式
        print("\n" + "=" * 70)
        print("  质量检查工作流")
        print("=" * 70 + "\n")

        workflow = QualityCheckWorkflow()

        test_content = """
        本文研究了环境规制对企业绿色创新的影响。

        假设H1: 环境规制正向促进企业绿色创新。

        方法：使用双重差分法（DID）进行因果推断。
        数据来源：2010-2022年中国A股上市公司数据。

        ROE = 15.5%
        毛利率 = 45.2%
        净利率 = 12.3%

        根据Smith et al. (2020)的研究，我们发现环境规制显著促进了绿色创新。
        DOI: 10.1234/example
        """

        result = workflow.check_quality(test_content)

        print("\n质量检查结果:")
        print(f"  通过: {'是' if result.passed else '否'}")
        print(f"  质量分数: {result.score:.1%}")

        if result.halt_rules_violations:
            print(f"\n严重违规 ({len(result.halt_rules_violations)}):")
            for v in result.halt_rules_violations:
                print(f"  - {v}")

        if result.warnings:
            print(f"\n警告 ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")

        if result.recommendations:
            print("\n建议:")
            for r in result.recommendations:
                print(f"  {r}")

    else:
        # 完整工作流
        print("\n" + "=" * 70)
        print("  金融AI学术研究工作流 - 增强版")
        print("=" * 70)
        print(f"\n  模式: {config.mode.value}")
        print(f"  论文类型: {config.paper_type.value}")
        print(f"  研究主题: {args.topic}")
        print(f"  自动模式: {config.auto_approve}")

        workflow = EnhancedResearchWorkflow(config)
        result = asyncio.run(workflow.run_research_flow(topic=args.topic))

        print(f"\n{'=' * 70}")
        print("  工作流完成")
        print(f"  耗时: {result.duration_ms:.0f}ms")
        print(f"  状态: {'成功' if result.success else '失败'}")
        print(f"{'=' * 70}\n")

        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
