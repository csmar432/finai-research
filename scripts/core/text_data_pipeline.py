"""
text_data_pipeline.py — 金融文本数据管道

从多个来源获取金融文本数据：
1. 年报/半年报原文（巨潮资讯网）
2. 公司公告原文（巨潮资讯网）
3. 研报原文（东方财富/同花顺）
4. 电话会纪要（业绩说明会文字实录）
5. 政策文件全文
6. 新闻文章

文本处理：
- 情感分析（中文金融词汇）
- 语调分析（正面/负面/中性词）
- 关键信息披露提取
- 结构化数据提取（财务数字/日期/承诺）
"""

from __future__ import annotations

__all__ = [
    "TextSource",
    "TextRecord",
    "SentimentAnalyzer",
]

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
if TYPE_CHECKING:
    import requests

logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


class TextSource(str, Enum):
    """文本来源。"""
    ANNUAL_REPORT = "annual_report"           # 年报
    HALF_YEAR_REPORT = "half_year_report"   # 半年报
    QUARTERLY_REPORT = "quarterly_report"   # 季报
    PROSPECTUS = "prospectus"               # 招股说明书
    ANNOUNCEMENT = "announcement"           # 临时公告
    EARNINGS_CALL = "earnings_call"         # 业绩说明会
    RESEARCH_REPORT = "research_report"      # 研报
    POLICY_DOCUMENT = "policy_document"     # 政策文件
    NEWS = "news"                           # 新闻
    WEIBO = "weibo"                         # 社交媒体


@dataclass
class TextRecord:
    """单条文本记录。"""
    source_type: TextSource
    source_url: str | None
    title: str
    content: str
    publish_date: str | None
    company: str | None        # 公司名称
    ts_code: str | None       # A股代码
    word_count: int
    extracted_entities: dict = field(default_factory=dict)  # 提取的实体
    sentiment_scores: dict = field(default_factory=dict)   # 情感分数
    key_disclosures: list[str] = field(default_factory=list)  # 关键信息披露
    metadata: dict = field(default_factory=dict)


# ─── 情感词典 ────────────────────────────────────────────────────────────────

POSITIVE_WORDS = {
    # 财务表现
    "增长", "提升", "提高", "增长", "强劲", "稳健", "超预期",
    "创新高", "突破", "大幅增长", "显著增长", "快速增长",
    "扭亏为盈", "盈利", "利润增长", "营收增长", "市场份额提升",
    # 战略
    "战略布局", "转型升级", "深化改革", "高质量发展",
    "行业领先", "竞争优势", "核心竞争力", "护城河",
    # 合作
    "战略合作", "强强联合", "生态合作", "伙伴关系",
    # 研发
    "研发投入", "技术创新", "专利", "核心专利", "技术突破",
    # 运营
    "降本增效", "效率提升", "运营优化", "成本控制",
}

NEGATIVE_WORDS = {
    # 财务风险
    "亏损", "下降", "减少", "下滑", "放缓", "负增长",
    "不及预期", "低于预期", "风险", "不确定性",
    "债务风险", "流动性风险", "信用风险", "经营风险",
    "商誉减值", "资产减值", "计提减值", "亏损风险",
    # 经营问题
    "诉讼", "仲裁", "处罚", "监管", "整改",
    "竞争加剧", "价格战", "毛利率下降", "市场份额下滑",
    # 宏观风险
    "外部冲击", "贸易摩擦", "政策变化", "监管趋严",
    "行业下行", "需求疲软", "供给过剩",
    "技术迭代", "替代风险", "颠覆性风险",
}

UNCERTAINTY_WORDS = {
    "可能", "或将", "也许", "似乎", "预计", "预期",
    "计划", "拟", "将", "未来", "展望", "规划",
    "存在不确定性", "风险因素", "可能影响", "有待观察",
    "取决于", "视", "取决于", "依", "依据",
}

FINANCIAL_MENTIONS = {
    # 业绩承诺
    "业绩承诺", "对赌协议", "盈利预测", "业绩目标",
    # 并购
    "并购重组", "收购", "资产重组", "股权转让",
    "商誉", "溢价收购", "估值调整",
    # 融资
    "定增", "配股", "发债", "可转债", "再融资",
    "IPO", "上市", "科创板", "创业板",
    # 分红
    "分红", "派息", "送股", "转增", "现金分红",
    # 高管变动
    "辞职", "离任", "换届", "任命", "新任",
    "董事长", "总经理", "高管", "核心人员",
}


# ─── 情感分析器 ──────────────────────────────────────────────────────────────

class SentimentAnalyzer:
    """基于词典的金融文本情感分析器。"""

    def __init__(self):
        self.positive_set = set(POSITIVE_WORDS)
        self.negative_set = set(NEGATIVE_WORDS)
        self.uncertainty_set = set(UNCERTAINTY_WORDS)
        self.financial_set = set(FINANCIAL_MENTIONS)

    def analyze(self, text: str) -> dict:
        """分析文本情感。"""
        words = [w for w in re.findall(r"[\u4e00-\u9fff]+", text)]
        total = max(len(words), 1)

        pos_count = sum(1 for w in words for _ in self.positive_set if w in _)
        neg_count = sum(1 for w in words for _ in self.negative_set if w in _)
        unc_count = sum(1 for w in words for _ in self.uncertainty_set if w in _)
        fin_count = sum(1 for w in words for _ in self.financial_set if w in _)

        # 提取含关键词的句子
        pos_sentences = self._extract_sentences_with(text, self.positive_set)
        neg_sentences = self._extract_sentences_with(text, self.negative_set)
        unc_sentences = self._extract_sentences_with(text, self.uncertainty_set)
        fin_sentences = self._extract_sentences_with(text, self.financial_set)

        # 综合情感分数 [-1, 1]
        sentiment = (pos_count - neg_count) / total
        uncertainty_ratio = unc_count / total

        return {
            "sentiment_score": round(sentiment, 4),   # -1 到 1
            "sentiment_label": "positive" if sentiment > 0.05 else "negative" if sentiment < -0.05 else "neutral",
            "positive_ratio": round(pos_count / total, 4),
            "negative_ratio": round(neg_count / total, 4),
            "uncertainty_ratio": round(uncertainty_ratio, 4),
            "financial_density": round(fin_count / total, 4),
            "word_count": total,
            "positive_count": pos_count,
            "negative_count": neg_count,
            "uncertainty_count": unc_count,
            "positive_highlights": pos_sentences[:5],
            "negative_highlights": neg_sentences[:5],
            "uncertainty_highlights": unc_sentences[:5],
            "key_disclosure_highlights": fin_sentences[:5],
        }

    def _extract_sentences_with(self, text: str, word_set: set) -> list[str]:
        """提取包含关键词的句子。"""
        sentences = re.split(r"[。！？；]", text)
        matched = []
        for sent in sentences:
            for kw in word_set:
                if kw in sent:
                    matched.append(sent.strip()[:200])
                    break
        return matched


# ─── 文本提取器 ──────────────────────────────────────────────────────────────

class TextExtractor:
    """从各类来源提取结构化文本。"""

    def extract_financial_numbers(self, text: str) -> dict:
        """提取文本中的财务数字。"""
        patterns = {
            "营收": r"(?:营业收入|营收)[:：]?\s*([\d,，.]+)\s*(?:亿|万|元)?",
            "净利润": r"(?:净利润|归母净利润)[:：]?\s*([\d,，.+-]+)\s*(?:亿|万|元)?",
            "总资产": r"总资产[:：]?\s*([\d,，.]+)\s*(?:亿|万|元)?",
            "毛利率": r"毛利率[:：]?\s*([\d,，.]+)%",
            "ROE": r"ROE[:：]?\s*([\d,，.]+)%",
        }

        results = {}
        for name, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                results[name] = matches[0]

        return results

    def extract_dates(self, text: str) -> list[str]:
        """提取文本中的日期。"""
        patterns = [
            r"\d{4}年\d{1,2}月\d{1,2}日",
            r"\d{4}-\d{2}-\d{2}",
            r"\d{4}/\d{2}/\d{2}",
        ]
        dates = []
        for p in patterns:
            dates.extend(re.findall(p, text))
        return list(dict.fromkeys(dates))

    def extract_commitments(self, text: str) -> list[str]:
        """提取管理层承诺。"""
        patterns = [
            r"将[^\n。]{5,30}",
            r"承诺[^\n。]{5,50}",
            r"计划[^\n。]{5,50}",
            r"预计[^\n。]{5,50}",
            r"拟[^\n。]{5,50}",
            r"预计[^\n。]{5,30}",
        ]
        commitments = []
        for p in patterns:
            matches = re.findall(p, text)
            commitments.extend(matches)
        return commitments[:10]  # 最多10条

    def extract_key_metrics(self, text: str) -> dict:
        """提取关键财务指标（简化版）。"""
        metrics = {}

        # 增长率
        growth_patterns = [
            (r"(?:同比|YoY)[:：]?\s*([+-]?\d+\.?\d*)%", "yoy_growth"),
            (r"(?:环比|QoQ)[:：]?\s*([+-]?\d+\.?\d*)%", "qoq_growth"),
            (r"(?:同比增长|increase)[:：]?\s*([+-]?\d+\.?\d*)%", "yoy_growth"),
        ]
        for pattern, name in growth_patterns:
            m = re.search(pattern, text)
            if m:
                try:
                    metrics[name] = float(m.group(1))
                except ValueError:
                    pass

        return metrics


# ─── Web Scraper ────────────────────────────────────────────────────────────

class TextScraper:
    """网页文本抓取器。"""

    def __init__(self, session: "requests.Session | None" = None):
        self.session = session or (requests.Session() if _HAS_REQUESTS else None)
        if self.session is not None:
            self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def fetch_page(self, url: str, timeout: int = 15) -> str | None:
        """获取网页内容。"""
        if not self.session:
            return None
        try:
            r = self.session.get(url, timeout=timeout)
            r.raise_for_status()
            if _HAS_BS4:
                soup = BeautifulSoup(r.text, "html.parser")
                # 移除脚本和样式
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)
            return r.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def fetch_cninfo_annual_report(self, company_name: str, year: int) -> TextRecord | None:
        """从巨潮资讯网抓取年报。"""
        # 巨潮资讯年报搜索URL
        search_url = f"http://www.cninfo.com.cn/new/fulltextSearch/full?searchkey={company_name}+{year}年报&sdate=&edate=&isfulltext=false&sortName=nothing&stockCode=&pageNo=1&pageSize=5"
        if not self.session:
            return None
        try:
            r = self.session.get(search_url, timeout=10)
            data = r.json()
            announcements = data.get("announcements", [])
            if not announcements:
                return None

            # 找到年报
            for ann in announcements:
                if f"{year}" in ann.get("announcementTitle", "") and "年报" in ann.get("announcementTitle", ""):
                    return TextRecord(
                        source_type=TextSource.ANNUAL_REPORT,
                        source_url=f"http://www.cninfo.com.cn/new/disclosure/detail?announcementTime={ann.get('announcementTime', '')}",
                        title=ann.get("announcementTitle", ""),
                        content="[需下载PDF后解析]",  # 年报PDF需要单独处理
                        publish_date=ann.get("announcementTime", ""),
                        company=company_name,
                        ts_code=ann.get("secCode", ""),
                        word_count=0,
                        metadata={"cninfo_id": ann.get("announcementId", "")},
                    )
        except Exception as e:
            logger.warning(f"cninfo fetch failed: {e}")
        return None

    def fetch_policy_document(self, url: str) -> TextRecord | None:
        """抓取政策文件全文。"""
        content = self.fetch_page(url)
        if not content:
            return None

        # 简单提取正文
        lines = content.split("\n")
        body_lines = [l for l in lines if len(l) > 50][:500]
        body = "\n".join(body_lines)

        return TextRecord(
            source_type=TextSource.POLICY_DOCUMENT,
            source_url=url,
            title=url.split("/")[-1],
            content=body,
            publish_date=None,
            company=None,
            ts_code=None,
            word_count=len(body),
        )


# ─── 主管道 ────────────────────────────────────────────────────────────────

class TextDataPipeline:
    """金融文本数据管道——统一入口。

    Usage:
        pipeline = TextDataPipeline(cache_dir="data/text_cache/")
        record = pipeline.fetch_earnings_call("贵州茅台", "2024-03-28")
        print(f"情感: {record.sentiment_scores['sentiment_label']}")
        print(f"关键披露: {record.key_disclosures}")
    """

    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.sentiment = SentimentAnalyzer()
        self.extractor = TextExtractor()
        self.scraper = TextScraper()

    def _cache_key(self, source: TextSource, identifier: str) -> Path:
        if not self.cache_dir:
            return Path("/dev/null")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^\w]", "_", identifier)[:50]
        return self.cache_dir / f"{source.value}_{safe_id}.json"

    def _load_cache(self, key: Path) -> TextRecord | None:
        if not key.exists() or key == Path("/dev/null"):
            return None
        try:
            with open(key) as f:
                data = json.load(f)
                return TextRecord(**data)
        except Exception:
            return None

    def _save_cache(self, key: Path, record: TextRecord) -> None:
        if key == Path("/dev/null"):
            return
        try:
            data = {
                "source_type": record.source_type.value,
                "source_url": record.source_url,
                "title": record.title,
                "content": record.content,
                "publish_date": record.publish_date,
                "company": record.company,
                "ts_code": record.ts_code,
                "word_count": record.word_count,
                "extracted_entities": record.extracted_entities,
                "sentiment_scores": record.sentiment_scores,
                "key_disclosures": record.key_disclosures,
                "metadata": record.metadata,
            }
            with open(key, "w") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    def process_text(
        self,
        text: str,
        source_type: TextSource = TextSource.NEWS,
        metadata: dict | None = None,
    ) -> TextRecord:
        """处理一段文本（抓取后或直接传入）。"""
        # 情感分析
        sentiment = self.sentiment.analyze(text)

        # 实体提取
        entities: dict[str, Any] = {}
        numbers = self.extractor.extract_financial_numbers(text)
        if numbers:
            entities["financial_numbers"] = numbers
        dates = self.extractor.extract_dates(text)
        if dates:
            entities["dates"] = dates
        _commitments = self.extractor.extract_commitments(text)
        self.extractor.extract_key_metrics(text)

        # 关键词披露
        key_disclosures = sentiment.get("key_disclosure_highlights", [])
        key_disclosures.extend(_commitments[:3])

        return TextRecord(
            source_type=source_type,
            source_url=metadata.get("url") if metadata else None,
            title=metadata.get("title", "") if metadata else "",
            content=text,
            publish_date=metadata.get("publish_date") if metadata else None,
            company=metadata.get("company") if metadata else None,
            ts_code=metadata.get("ts_code") if metadata else None,
            word_count=len(text),
            extracted_entities=entities,
            sentiment_scores=sentiment,
            key_disclosures=list(dict.fromkeys(key_disclosures))[:10],
            metadata=metadata or {},
        )

    def fetch_and_process(
        self,
        url: str,
        source_type: TextSource,
        metadata: dict | None = None,
    ) -> TextRecord | None:
        """抓取URL并处理。"""
        cache_key = self._cache_key(source_type, url)
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        content = self.scraper.fetch_page(url)
        if not content:
            return None

        record = self.process_text(content, source_type, metadata)
        self._save_cache(cache_key, record)
        return record

    def batch_process_texts(
        self,
        texts: list[tuple[str, TextSource]],
    ) -> list[TextRecord]:
        """批量处理文本列表。"""
        records = []
        for text, source_type in texts:
            try:
                record = self.process_text(text, source_type)
                records.append(record)
            except Exception as e:
                logger.warning(f"Text processing failed: {e}")
        return records

    def generate_text_summary(self, records: list[TextRecord]) -> str:
        """生成文本集合摘要报告。"""
        if not records:
            return "无文本数据"

        avg_sentiment = sum(r.sentiment_scores.get("sentiment_score", 0) for r in records) / len(records)
        total_words = sum(r.word_count for r in records)

        lines = [
            "## 文本数据摘要",
            f"",
            f"文本数量: {len(records)} 篇",
            f"总字数: {total_words:,} 字",
            f"平均情感: {avg_sentiment:.3f} ({'偏正面' if avg_sentiment > 0.05 else '偏负面' if avg_sentiment < -0.05 else '中性'})",
            "",
            f"| 来源 | 篇数 | 平均情感 |",
            f"|------|------|----------|",
        ]

        by_source: dict[TextSource, list] = {}
        for r in records:
            by_source.setdefault(r.source_type, []).append(r)

        for source, recs in by_source.items():
            avg = sum(r.sentiment_scores.get("sentiment_score", 0) for r in recs) / len(recs)
            lines.append(f"| {source.value} | {len(recs)} | {avg:.3f} |")

        lines.append("")
        lines.append("## 关键信息披露")
        for r in records:
            if r.key_disclosures:
                lines.append(f"\n**{r.title}** ({r.publish_date or '未知日期'})")
                for d in r.key_disclosures[:3]:
                    lines.append(f"- {d}")

        return "\n".join(lines)
