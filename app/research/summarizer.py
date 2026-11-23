"""Tóm tắt bài viết bằng LLM (T44)."""

import json
import logging
from pathlib import Path

from app.core import llm
from app.research.collector import FetchedArticle

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "summarizer.md"
ARTICLE_EXCERPT_CHARS = 3000

RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "summary": {"type": "string"},
            "relevant": {"type": "boolean"},
        },
        "required": ["index", "summary", "relevant"],
    },
}


def _load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


async def summarize(articles: list[FetchedArticle], question: str) -> dict[int, str]:
    """Tóm tắt hàng loạt bài viết; trả về {index: summary} chỉ cho bài liên quan."""
    if not articles:
        return {}

    blocks = []
    for index, article in enumerate(articles):
        blocks.append(f"[{index}] {article.title}\n{article.text[:ARTICLE_EXCERPT_CHARS]}")
    contents = [
        {
            "role": "user",
            "parts": [{"text": f"Câu hỏi của người dùng: {question}\n\nCác bài viết:\n\n" + "\n\n".join(blocks)}],
        }
    ]

    response = await llm.generate(_load_prompt(), contents, response_schema=RESPONSE_SCHEMA)
    try:
        items = json.loads(response.text or "[]")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Summarizer trả về JSON không hợp lệ: %r", response.text)
        return {}

    result: dict[int, str] = {}
    for item in items:
        if not item.get("relevant", True):
            continue
        index = item.get("index")
        summary = (item.get("summary") or "").strip()
        if isinstance(index, int) and 0 <= index < len(articles) and summary:
            result[index] = summary
    return result
