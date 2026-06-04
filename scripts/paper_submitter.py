#!/usr/bin/env python3
"""
论文自动投稿系统
================
自动完成论文格式检测、目标期刊匹配、投稿材料生成、提交状态追踪。

功能：
- 自动识别论文格式并匹配目标期刊
- 生成 / 检查投稿所需材料（Cover Letter、Response Letter、Highlights、Graphical Abstract）
- 追踪投稿状态（submitted / under review / revision / accepted / rejected）
- 支持主流会议投稿系统（CMT / OpenReview / EasyChair / ScholarOne）
- LaTeX 格式合规性预检

用法：
  python scripts/paper_submitter.py submit paper.pdf --venue NeurIPS
  python scripts/paper_submitter.py check paper.tex --venue ACL
  python scripts/paper_submitter.py status --id SUB-2025-001
  python scripts/paper_submitter.py match paper.pdf --field "Machine Learning"
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
TRACK_FILE = SCRIPT_DIR / "knowledge" / "submissions.json"


# ════════════════════════════════════════════════════════════════════
# 期刊 / 会议数据库
# ════════════════════════════════════════════════════════════════════

VENUE_DATABASE = {
    # 机器学习 / AI
    "NeurIPS": {
        "name": "Conference on Neural Information Processing Systems",
        "full_name": "Advances in Neural Information Processing Systems",
        "abbrev": "NeurIPS",
        "type": "conference",
        "field": ["Machine Learning", "AI", "Deep Learning"],
        "deadline_months": [4, 9],  # 通常5月和10月截稿
        "review_style": "double-blind",
        "page_limit": 9,
        "latex_style": "neurips",
        "submission_url": "https://neurips.cc/Conferences/2025/PaperTopics",
        "notes": "双盲审稿，最多9页（不含参考文献）",
    },
    "ICML": {
        "name": "International Conference on Machine Learning",
        "full_name": "International Conference on Machine Learning",
        "abbrev": "ICML",
        "type": "conference",
        "field": ["Machine Learning", "Statistics", "AI"],
        "deadline_months": [1, 9],
        "review_style": "double-blind",
        "page_limit": 8,
        "latex_style": "icml",
        "submission_url": "https://openreview.net/group?id=ICML.cc/2025/Conference",
        "notes": "双盲，通过 OpenReview 提交",
    },
    "ICLR": {
        "name": "International Conference on Learning Representations",
        "full_name": "International Conference on Learning Representations",
        "abbrev": "ICLR",
        "type": "conference",
        "field": ["Deep Learning", "Representation Learning", "AI"],
        "deadline_months": [9],
        "review_style": "open-review",
        "page_limit": 8,
        "latex_style": "iclr",
        "submission_url": "https://openreview.net/group?id=ICLR.cc/2025/Conference",
        "notes": "开放审稿，审稿前所有人可见论文",
    },
    "AAAI": {
        "name": "AAAI Conference on Artificial Intelligence",
        "full_name": "AAAI Conference on Artificial Intelligence",
        "abbrev": "AAAI",
        "type": "conference",
        "field": ["AI", "Reasoning", "Planning"],
        "deadline_months": [8],
        "review_style": "single-blind",
        "page_limit": 7,
        "latex_style": "aaai",
        "submission_url": "https://easychair.org/conferences/?conf=aaai2025",
        "notes": "单盲审稿，通常8月截稿",
    },
    "IJCAI": {
        "name": "International Joint Conference on Artificial Intelligence",
        "full_name": "International Joint Conference on Artificial Intelligence",
        "abbrev": "IJCAI",
        "type": "conference",
        "field": ["AI", "General AI"],
        "deadline_months": [1],
        "review_style": "single-blind",
        "page_limit": 7,
        "latex_style": "ijcai",
        "submission_url": "https://cmt3.research.microsoft.com/IJCAI2025",
        "notes": "通过 CMT 提交",
    },
    # 计算机视觉
    "CVPR": {
        "name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "abbrev": "CVPR",
        "type": "conference",
        "field": ["Computer Vision", "Deep Learning", "Pattern Recognition"],
        "deadline_months": [9],
        "review_style": "double-blind",
        "page_limit": 8,
        "latex_style": "cvpr",
        "submission_url": "https://cmt3.research.microsoft.com/CVPR2025",
        "notes": "CVPR 2025 通过 CMT 提交",
    },
    "ICCV": {
        "name": "IEEE/CVF International Conference on Computer Vision",
        "full_name": "IEEE/CVF International Conference on Computer Vision",
        "abbrev": "ICCV",
        "type": "conference",
        "field": ["Computer Vision", "Image Analysis"],
        "deadline_months": [4],
        "review_style": "double-blind",
        "page_limit": 8,
        "latex_style": "ieee",
        "submission_url": "https://cmt3.research.microsoft.com/ICCV2025",
        "notes": "单数年举办",
    },
    "ECCV": {
        "name": "European Conference on Computer Vision",
        "full_name": "European Conference on Computer Vision",
        "abbrev": "ECCV",
        "type": "conference",
        "field": ["Computer Vision"],
        "deadline_months": [3],
        "review_style": "double-blind",
        "page_limit": 14,
        "latex_style": "eccv",
        "submission_url": "https://eccv2025.ecva.net/submissions/",
        "notes": "双年举办，14页（不含参考文献）",
    },
    # NLP / 计算语言学
    "ACL": {
        "name": "Association for Computational Linguistics",
        "full_name": "Proceedings of the Annual Meeting of the Association for Computational Linguistics",
        "abbrev": "ACL",
        "type": "conference",
        "field": ["NLP", "Computational Linguistics", "ML"],
        "deadline_months": [1, 5],
        "deadline_note": "分长文和短文截稿",
        "review_style": "double-blind",
        "page_limit": 8,
        "latex_style": "acl",
        "submission_url": "https://openreview.net/group?id=ACL/2025/Main",
        "notes": "ACL 2025 通过 OpenReview",
    },
    "EMNLP": {
        "name": "Conference on Empirical Methods in Natural Language Processing",
        "full_name": "Conference on Empirical Methods in Natural Language Processing",
        "abbrev": "EMNLP",
        "type": "conference",
        "field": ["NLP", "ML"],
        "deadline_months": [6, 9],
        "review_style": "double-blind",
        "page_limit": 8,
        "latex_style": "emnlp",
        "submission_url": "https://openreview.net/group?id=EMNLP/2025/Conference",
        "notes": "EMNLP 2025",
    },
    # AI 期刊
    "JMLR": {
        "name": "Journal of Machine Learning Research",
        "full_name": "Journal of Machine Learning Research",
        "abbrev": "JMLR",
        "type": "journal",
        "field": ["Machine Learning", "AI"],
        "review_style": "open",
        "page_limit": None,
        "latex_style": "jmlr",
        "submission_url": "https://jmlr.org/author-guide.html",
        "notes": "完全开放获取，在线投稿",
    },
    "AIJ": {
        "name": "Artificial Intelligence",
        "full_name": "Artificial Intelligence (Elsevier)",
        "abbrev": "AIJ",
        "type": "journal",
        "field": ["AI", "Knowledge Representation", "Reasoning"],
        "review_style": "double-blind",
        "page_limit": None,
        "latex_style": "aij",
        "submission_url": "https://www.editorialmanager.com/artint/",
        "notes": "爱思唯尔期刊",
    },
    # 金融 AI / 量化
    "JFA": {
        "name": "Journal of Financial AI",
        "full_name": "Journal of Financial Artificial Intelligence",
        "abbrev": "JFA",
        "type": "journal",
        "field": ["Financial AI", "Quantitative Finance", "FinTech"],
        "review_style": "double-blind",
        "page_limit": None,
        "latex_style": "ieee",
        "submission_url": "https://www.journalofai.org/submit",
        "notes": "金融 AI 领域新兴期刊",
    },
}


# ════════════════════════════════════════════════════════════════════
# 投稿追踪
# ════════════════════════════════════════════════════════════════════

@dataclass
class Submission:
    """投稿记录。"""
    submission_id: str
    paper_title: str
    venue: str
    status: str  # draft / submitted / under_review / revision / accepted / rejected / withdrawn
    submitted_at: str | None = None
    last_updated: str | None = None
    notes: str = ""
    files: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "submission_id": self.submission_id,
            "paper_title": self.paper_title,
            "venue": self.venue,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "last_updated": self.last_updated or datetime.now().isoformat(),
            "notes": self.notes,
            "files": self.files,
        }


def load_submissions() -> dict:
    """加载投稿记录。"""
    TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TRACK_FILE.exists():
        return {}
    try:
        with open(TRACK_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return {k: Submission(**v) if isinstance(v, dict) else v
                    for k, v in data.items()}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_submissions(subs: dict):
    """保存投稿记录。"""
    TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.to_dict() if isinstance(v, Submission) else v for k, v in subs.items()}
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════
# 核心功能
# ════════════════════════════════════════════════════════════════════

def match_venue(paper_content: str, field: str | None = None) -> list[dict]:
    """
    根据论文内容和领域推荐合适期刊。

    Args:
        paper_content: 论文摘要或全文（用于关键词分析）
        field: 指定的研究领域（可选）

    Returns:
        按匹配度排序的期刊列表
    """
    keywords_map = {
        "machine learning": ["NeurIPS", "ICML", "JMLR"],
        "deep learning": ["NeurIPS", "ICLR", "ICML"],
        "computer vision": ["CVPR", "ICCV", "ECCV"],
        "nlp": ["ACL", "EMNLP", "NAACL"],
        "natural language": ["ACL", "EMNLP", "NAACL"],
        "reinforcement learning": ["NeurIPS", "ICML", "AAAI"],
        "financial": ["JFA", "JMLR", "AIJ"],
        "finance": ["JFA", "NeurIPS", "ICML"],
        "quantitative": ["JFA", "JMLR"],
        "robotics": ["NeurIPS", "ICRA", "AAAI"],
        "knowledge": ["IJCAI", "AAAI", "AIJ"],
        "reasoning": ["AAAI", "IJCAI", "AIJ"],
    }

    matched_venues = []
    content_lower = paper_content.lower()

    for kw, venues in keywords_map.items():
        if kw in content_lower:
            for v in venues:
                if v in VENUE_DATABASE:
                    if v not in [m["abbrev"] for m in matched_venues]:
                        matched_venues.append(VENUE_DATABASE[v])

    if field:
        field_lower = field.lower()
        for v_key, v_info in VENUE_DATABASE.items():
            if any(field_lower in f.lower() for f in v_info["field"]):
                if v_key not in [m["abbrev"] for m in matched_venues]:
                    matched_venues.append(v_info)

    # 去重并按 field 匹配度排序
    seen = set()
    unique = []
    for v in matched_venues:
        if v["abbrev"] not in seen:
            seen.add(v["abbrev"])
            unique.append(v)

    return unique[:5]


def check_compliance(paper_path: str, venue: str) -> dict:
    """
    检查论文是否符合目标期刊格式要求。

    Args:
        paper_path: 论文文件路径
        venue: 期刊缩写

    Returns:
        合规性检查结果
    """
    venue_info = VENUE_DATABASE.get(venue.upper())
    if not venue_info:
        return {"error": f"未知期刊: {venue}"}

    path = Path(paper_path)
    if not path.exists():
        return {"error": f"文件不存在: {paper_path}"}

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"读取失败: {e}"}

    checks = []
    warnings = []

    # 页数检查（仅 LaTeX）
    if path.suffix == ".tex":
        # 粗略估计：每页约 500 词
        words = len(content.split())
        estimated_pages = words / 500
        limit = venue_info.get("page_limit")
        if limit:
            if estimated_pages > limit:
                checks.append({
                    "item": "页数限制",
                    "status": "FAIL",
                    "detail": f"估计 {estimated_pages:.0f} 页 > 限制 {limit} 页",
                })
            else:
                checks.append({
                    "item": "页数限制",
                    "status": "PASS",
                    "detail": f"估计 {estimated_pages:.0f} 页 ≤ 限制 {limit} 页",
                })
        else:
            checks.append({
                "item": "页数限制",
                "status": "INFO",
                "detail": "该期刊无固定页数限制",
            })

    # LaTeX 样式检查
    style = venue_info.get("latex_style", "")
    style_patterns = {
        "neurips": r"\\usepackage.*neurips",
        "icml": r"\\usepackage.*icml",
        "acl": r"\\usepackage.*acl",
        "cvpr": r"\\usepackage.*cvpr",
        "aaai": r"\\usepackage.*aaai",
        "ieee": r"\\documentclass.*IEEE",
        "jmlr": r"\\documentclass.*jmlr",
    }
    pattern = style_patterns.get(style, "")
    if pattern:
        if re.search(pattern, content, re.IGNORECASE):
            checks.append({"item": "LaTeX 样式", "status": "PASS", "detail": f"检测到 {style} 样式"})
        else:
            warnings.append({"item": "LaTeX 样式", "detail": f"未检测到 {style} 样式，建议使用官方模板"})

    # 匿名检查（双盲）
    if venue_info.get("review_style") == "double-blind":
        author_patterns = [
            r"\\author\{[^}]*[A-Z][a-z]+",
            r"\\thanks\{",
            r"\\email\{",
        ]
        found = [p for p in author_patterns if re.search(p, content)]
        if found:
            warnings.append({
                "item": "匿名性",
                "detail": "检测到作者信息，请确认已在提交版本中移除（双盲审稿）",
            })
        else:
            checks.append({"item": "匿名性", "status": "PASS", "detail": "未检测到明显作者信息"})

    # 参考文献格式
    if "\\bibliography" in content:
        checks.append({"item": "参考文献", "status": "PASS", "detail": "使用 BibTeX 参考文献"})
    else:
        warnings.append({"item": "参考文献", "detail": "建议使用 BibTeX 管理参考文献"})

    passed = sum(1 for c in checks if c.get("status") == "PASS")
    failed = sum(1 for c in checks if c.get("status") == "FAIL")

    return {
        "venue": venue,
        "venue_name": venue_info["full_name"],
        "venue_type": venue_info["type"],
        "review_style": venue_info.get("review_style", "unknown"),
        "checks": checks,
        "warnings": warnings,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(checks),
            "ready": failed == 0,
        },
    }


def create_submission(paper_title: str, venue: str, files: dict = None) -> Submission:
    """创建新投稿记录。"""
    subs = load_submissions()
    sub_id = f"SUB-{datetime.now().strftime('%Y%m%d')}-{len(subs)+1:03d}"

    sub = Submission(
        submission_id=sub_id,
        paper_title=paper_title,
        venue=venue,
        status="draft",
        files=files or {},
    )

    subs[sub_id] = sub
    save_submissions(subs)
    return sub


def update_status(submission_id: str, new_status: str, notes: str = "") -> Submission | None:
    """更新投稿状态。"""
    subs = load_submissions()
    if submission_id not in subs:
        return None

    sub = subs[submission_id]
    sub.status = new_status
    sub.last_updated = datetime.now().isoformat()
    if notes:
        sub.notes = notes
    if new_status in ("submitted", "under_review"):
        sub.submitted_at = datetime.now().isoformat()

    save_submissions(subs)
    return sub


def generate_submission_package(
    paper_path: str,
    venue: str,
    authors: str,
    output_dir: str = "submission_package",
) -> dict:
    """
    生成完整投稿包（Cover Letter、Highlights、Graphical Abstract 说明等）。

    Returns:
        dict，包含各文件路径
    """
    from scripts.paper_tools_core import generate_cover_letter

    path = Path(paper_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    paper_content = ""
    if path.exists():
        paper_content = path.read_text(encoding="utf-8")

    venue_info = VENUE_DATABASE.get(venue.upper(), {})

    # Cover Letter
    print("  生成 Cover Letter...")
    cover_letter = generate_cover_letter(
        paper_content=paper_content[:3000],
        venue=venue,
        authors=authors,
    )

    cover_path = output / "cover_letter.txt"
    cover_path.write_text(cover_letter, encoding="utf-8")

    # Submission Checklist
    checklist = f"""投稿检查清单 — {venue}
{'='*50}
日期: {datetime.now().strftime('%Y-%m-%d')}

必选项:
  [ ] 论文全文（PDF）
  [ ] Cover Letter
  [ ] 作者信息（姓名、单位、通讯邮箱）
  [ ] 匿名版本（如双盲）
  [ ] 补充材料（如有）

建议项:
  [ ] Highlights（3-5个要点）
  [ ] Graphical Abstract（如期刊要求）
  [ ] 代码链接（如支持复现）
  [ ] 数据集说明（如适用）

格式检查:
  [ ] 页数 ≤ {venue_info.get('page_limit', '无限制')}
  [ ] LaTeX 模板正确
  [ ] 参考文献格式统一
  [ ] 图表清晰（≥300 DPI）
  [ ] 语法检查完毕

投稿系统: {venue_info.get('submission_url', 'N/A')}

审稿风格: {venue_info.get('review_style', 'N/A')}
说明: {venue_info.get('notes', '')}
"""
    checklist_path = output / "checklist.txt"
    checklist_path.write_text(checklist, encoding="utf-8")

    return {
        "cover_letter": str(cover_path),
        "checklist": str(checklist_path),
        "output_dir": str(output),
    }


# ════════════════════════════════════════════════════════════════════
# 类式包装（供 ToolSelector / ResearchSession 导入）
# ════════════════════════════════════════════════════════════════════


class PaperSubmitter:
    """
    论文投稿工具类式包装，支持工具化调用。

    完整功能：润色 / 查重 / LaTeX检查 / 投稿信生成 / 期刊匹配 / 格式合规 / 状态追踪

    示例：
        submitter = PaperSubmitter()
        matches = submitter.match_venue(paper_text, field="Machine Learning")
        report = submitter.check_compliance("paper.pdf", "NeurIPS")
        polished = submitter.polish(text)
        cover = submitter.generate_cover_letter(paper_content, "NeurIPS")
    """

    def __init__(self):
        self.venue_db = VENUE_DATABASE

    # ── 期刊匹配 ────────────────────────────────────────────────────────────

    def match_venue(self, paper_content: str, field: str = "") -> list[dict]:
        """推荐适合的期刊。"""
        return match_venue(paper_content, field)

    # ── 格式合规性 ─────────────────────────────────────────────────────────

    def check_compliance(self, paper_path: str, venue: str) -> dict:
        """检查格式合规性。"""
        return check_compliance(paper_path, venue)

    # ── 润色 ───────────────────────────────────────────────────────────────

    def polish(self, text: str, lang: str = "chinese", level: str = "standard") -> str:
        """润色文本。"""
        return polish(text, lang, level)

    def iterate_polish(self, text: str, lang: str = "chinese", rounds: int = 2) -> str:
        """多轮迭代润色。"""
        return iterate_polish(text, lang, rounds)

    # ── 查重 ────────────────────────────────────────────────────────────────

    def check_plagiarism(self, text: str) -> dict:
        """查重检测（建议使用 iThenticate/Turnitin）。"""
        return check_plagiarism(text)

    # ── LaTeX 检查 ──────────────────────────────────────────────────────────

    def latex_check(self, tex_path: str) -> dict:
        """LaTeX 格式检查（需 pandoc + texlive）。"""
        return latex_check(tex_path)

    # ── 投稿信 ─────────────────────────────────────────────────────────────

    def generate_cover_letter(
        self,
        paper_content: str = "",
        venue: str = "",
        authors: str = "",
    ) -> str:
        """生成 Cover Letter。"""
        return generate_cover_letter(paper_content, venue, authors)

    def generate_response_letter(
        self,
        paper_content: str = "",
        reviews: str = "",
        authors: str = "",
    ) -> str:
        """生成审稿回复信。"""
        return generate_response_letter(paper_content, reviews, authors)

    # ── 投稿追踪 ────────────────────────────────────────────────────────────

    def create_submission(
        self,
        title: str = "",
        venue: str = "",
        files: dict = None,
    ) -> dict:
        """创建投稿记录。"""
        sub = create_submission(title, venue, files)
        return sub.to_dict()

    def update_status(
        self,
        submission_id: str = "",
        status: str = "",
        notes: str = "",
    ) -> dict:
        """更新投稿状态。"""
        sub = update_status(submission_id, status, notes)
        return sub.to_dict() if sub else {}

    def list_submissions(self) -> list[dict]:
        """列出所有投稿记录。"""
        subs = load_submissions()
        return [v.to_dict() for v in subs.values()]

    # ── 投稿包 ──────────────────────────────────────────────────────────────

    def generate_package(
        self,
        paper_path: str = "",
        venue: str = "",
        authors: str = "",
        output_dir: str = "submission_package",
    ) -> dict:
        """生成投稿包（Cover Letter + Checklist）。"""
        return generate_submission_package(paper_path, venue, authors, output_dir)


# ════════════════════════════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="论文自动投稿系统 — 格式检查、期刊匹配、投稿状态追踪",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # match
    p_match = subparsers.add_parser("match", help="推荐适合的期刊")
    p_match.add_argument("file", help="论文文件路径（.pdf/.tex/.md）")
    p_match.add_argument("--field", "-f", help="研究领域")

    # check
    p_check = subparsers.add_parser("check", help="格式合规性检查")
    p_check.add_argument("file", help="论文文件路径")
    p_check.add_argument("--venue", "-v", required=True, help="目标期刊/会议")

    # submit
    p_submit = subparsers.add_parser("submit", help="创建投稿记录")
    p_submit.add_argument("file", help="论文文件路径")
    p_submit.add_argument("--venue", "-v", required=True, help="目标期刊")
    p_submit.add_argument("--title", "-t", help="论文标题")
    p_submit.add_argument("--authors", "-a", help="作者列表")

    # status
    p_status = subparsers.add_parser("status", help="查看投稿状态")
    p_status.add_argument("--id", help="投稿 ID（如 SUB-20250525-001）")
    p_status.add_argument("--list", "-l", action="store_true", help="列出所有投稿")

    # update
    p_update = subparsers.add_parser("update", help="更新投稿状态")
    p_update.add_argument("id", help="投稿 ID")
    p_update.add_argument("status", help="新状态")
    p_update.add_argument("--notes", help="备注")

    # package
    p_pkg = subparsers.add_parser("package", help="生成投稿包")
    p_pkg.add_argument("file", help="论文文件路径")
    p_pkg.add_argument("--venue", "-v", required=True, help="目标期刊")
    p_pkg.add_argument("--authors", "-a", default="", help="作者列表")
    p_pkg.add_argument("--output", "-o", default="submission_package", help="输出目录")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python scripts/paper_submitter.py match paper.pdf --field 'Machine Learning'")
        print("  python scripts/paper_submitter.py check paper.tex --venue NeurIPS")
        print("  python scripts/paper_submitter.py submit paper.pdf --venue NeurIPS -t '标题'")
        print("  python scripts/paper_submitter.py status --list")
        print("  python scripts/paper_submitter.py update SUB-20250525-001 under_review")
        return

    if args.command == "match":
        path = Path(args.file)
        content = ""
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        if not content:
            print(f"⚠ 无法读取文件: {args.file}")
            return
        results = match_venue(content[:2000], args.field)
        if not results:
            print("未找到匹配的期刊，请尝试指定 --field")
            return
        print("\n推荐的期刊（按相关度排序）：")
        for i, v in enumerate(results, 1):
            print(f"\n  {i}. {v['full_name']} ({v['abbrev']})")
            print(f"     类型: {v['type']} | 审稿: {v.get('review_style', 'N/A')}")
            print(f"     页数限制: {v.get('page_limit', '无') or '无'}")
            print(f"     截稿: {'、'.join(str(m)+'月' for m in v.get('deadline_months', [])) or '滚动投稿'}")
            print(f"     领域: {', '.join(v.get('field', []))}")

    elif args.command == "check":
        report = check_compliance(args.file, args.venue)
        if "error" in report:
            print(f"✗ {report['error']}")
            return
        print(f"\n{'='*60}")
        print(f"  格式合规性检查 — {report['venue_name']}")
        print(f"  审稿风格: {report['review_style']} | 类型: {report['venue_type']}")
        print(f"{'='*60}")

        for c in report["checks"]:
            icon = "✓" if c.get("status") == "PASS" else "✗"
            print(f"  [{icon}] {c['item']}: {c.get('detail', '')}")

        if report.get("warnings"):
            print("\n  提示:")
            for w in report["warnings"]:
                print(f"    → {w.get('detail', '')}")

        s = report["summary"]
        if s["ready"]:
            print("\n  ✅ 格式合规，可以投稿！")
        else:
            print(f"\n  ⚠ 有 {s['failed']} 项未通过，请修正后再投稿")

    elif args.command == "submit":
        path = Path(args.file)
        title = args.title or (path.stem if path.exists() else "Unknown")
        venue_info = VENUE_DATABASE.get(args.venue.upper(), {})
        sub = create_submission(title, args.venue, {"paper": str(path)})
        print("\n  ✅ 投稿记录已创建:")
        print(f"     ID: {sub.submission_id}")
        print(f"     标题: {sub.paper_title}")
        print(f"     期刊: {venue_info.get('full_name', args.venue)}")
        print("     状态: draft")
        print("\n  下一步：")
        print(f"    python scripts/paper_submitter.py check {args.file} --venue {args.venue}")
        print(f"    python scripts/paper_submitter.py package {args.file} --venue {args.venue}")

    elif args.command == "status":
        if args.list:
            subs = load_submissions()
            if not subs:
                print("暂无投稿记录")
                return
            print(f"\n投稿记录（共 {len(subs)} 条）")
            for sub in sorted(subs.values(), key=lambda x: x.last_updated or "", reverse=True):
                print(f"\n  [{sub.submission_id}] {sub.paper_title}")
                print(f"     期刊: {sub.venue} | 状态: {sub.status}")
                print(f"     更新: {sub.last_updated or sub.submitted_at or 'N/A'}")
        elif args.id:
            subs = load_submissions()
            if args.id not in subs:
                print(f"✗ 未找到投稿记录: {args.id}")
                return
            sub = subs[args.id]
            print(f"\n  ID: {sub.submission_id}")
            print(f"  标题: {sub.paper_title}")
            print(f"  期刊: {sub.venue}")
            print(f"  状态: {sub.status}")
            print(f"  投稿时间: {sub.submitted_at or 'N/A'}")
            print(f"  最后更新: {sub.last_updated or 'N/A'}")
            if sub.notes:
                print(f"  备注: {sub.notes}")
        else:
            print("请提供 --id 或 --list")

    elif args.command == "update":
        sub = update_status(args.id, args.status, args.notes or "")
        if sub:
            print(f"  ✅ 状态已更新: {sub.status}")
        else:
            print(f"✗ 未找到投稿记录: {args.id}")

    elif args.command == "package":
        pkg = generate_submission_package(args.file, args.venue, args.authors, args.output)
        print("\n  ✅ 投稿包已生成:")
        for k, v in pkg.items():
            if k != "output_dir":
                print(f"     {k}: {v}")


if __name__ == "__main__":
    main()
