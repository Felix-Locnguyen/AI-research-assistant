"""Nghiên cứu: tạo truy vấn (T40), chạy pipeline tìm kiếm–lọc–tóm tắt, lưu bài (T46) và định dạng (T47)."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.database.models import Article
from app.database.repository import ArticleRepository
from app.research import collector, filter as research_filter, search, summarizer

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "research.md"

MAX_QUERIES = 3
MAX_ARTICLES = 5
FETCH_CONCURRENCY = 3

QUERY_SCHEMA = {"type": "array", "items": {"type": "string"}}


@dataclass
class ResearchOutcome:
    formatted: str
    articles: list[Article] = field(default_factory=list)


async def generate_queries(question: str, preferences: dict[str, str]) -> list[str]:
    """Tạo 2–3 truy vấn tìm kiếm từ câu hỏi + sở thích (T40)."""
    prefs = "; ".join(f"{key}: {value}" for key, value in preferences.items()) or "(không có)"
    contents = [{"role": "user", "parts": [{"text": f"Câu hỏi: {question}\nSở thích người dùng: {prefs}"}]}]
    try:
        response = await llm.generate(PROMPT_FILE.read_text(encoding="utf-8"), contents, response_schema=QUERY_SCHEMA)
        queries = [str(q).strip() for q in json.loads(response.text or "[]") if str(q).strip()]
    except Exception:
        logger.exception("Lỗi khi tạo truy vấn, dùng câu hỏi gốc")
        queries = []
    return (queries or [question])[:MAX_QUERIES]


async def _fetch_all(urls: list[str]) -> list[collector.FetchedArticle]:
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch(url: str) -> collector.FetchedArticle | None:
        async with semaphore:
            return await collector.fetch_article(url)

    results = await asyncio.gather(*(fetch(url) for url in urls))
    return [article for article in results if article is not None]


def _format(question: str, rows: list[tuple[Article, str | None]]) -> str:  # T47
    if not rows:
        return f"## Kết quả nghiên cứu\n\nMình chưa tìm được nguồn phù hợp cho: **{question}**."
    lines = [f"## Kết quả nghiên cứu: {question}", ""]
    for position, (article, summary) in enumerate(rows, start=1):
        date = f" — {article.published_at.date()}" if article.published_at else ""
        lines.append(f"### {position}. {article.title}")
        lines.append(f"- Nguồn: {article.source}{date}")
        lines.append(f"- Link: {article.url}")
        lines.append(f"- Tóm tắt: {summary or 'chưa có — xem link để đọc chi tiết'}")
        lines.append("")
    return "\n".join(lines).strip()


async def run_research(
    question: str,
    preferences: dict[str, str],
    user_id: int,
    session: AsyncSession,
    feeds: list[str] | None = None,
) -> ResearchOutcome:
    """Chạy toàn bộ pipeline nghiên cứu và trả về kết quả đã định dạng."""
    queries = await generate_queries(question, preferences)

    hits: list[search.SearchHit] = []
    for position, query in enumerate(queries):
        if position:
            await asyncio.sleep(1)   # nghỉ giữa các truy vấn để tránh rate-limit
        hits.extend(await search.web_search(query))
    if feeds:
        hits.extend(await collector.collect_rss(feeds, keywords=list(research_filter._tokens(question)) or None))

    hits = research_filter.dedupe(hits)                                   # T42
    hits = research_filter.filter_relevant(hits, question, preferences, MAX_ARTICLES)  # T43

    articles = research_filter.dedupe(await _fetch_all([hit.url for hit in hits]))  # T41 + T45, bỏ bản trùng sau khi trích xuất

    try:
        summaries = await summarizer.summarize(articles, question)        # T44
    except Exception:
        logger.exception("Lỗi khi tóm tắt, trả kết quả kèm link nhưng chưa có tóm tắt")
        summaries = None                                                  # khác {}: giữ mọi bài, thiếu tóm tắt

    article_repo = ArticleRepository(session)
    rows: list[tuple[Article, str | None]] = []
    for index, fetched in enumerate(articles):
        summary = summaries.get(index) if summaries is not None else None
        if summaries is not None and not summary:
            continue                                                      # summarizer đánh giá không liên quan
        article = await article_repo.add(                                 # T46
            title=fetched.title,
            url=fetched.url,
            source=fetched.source,
            published_at=fetched.published_at,
            summary=summary,
            user_id=user_id,
        )
        if summary and not article.summary:
            await article_repo.set_summary(article.id, summary)
        rows.append((article, summary))

    return ResearchOutcome(formatted=_format(question, rows), articles=[article for article, _ in rows])
