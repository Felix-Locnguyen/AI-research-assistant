"""Tìm kiếm web (T38) — dùng DuckDuckGo qua thư viện ddgs, không cần API key."""

import asyncio
import logging
from dataclasses import dataclass

from ddgs import DDGS
from ddgs.exceptions import DDGSException

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
SNIPPET_LENGTH = 300
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def _search_sync(query: str, max_results: int) -> list[SearchHit]:
    hits = []
    for item in DDGS().text(query, max_results=max_results):
        url = item.get("href", "")
        if not url:
            continue
        hits.append(
            SearchHit(
                title=(item.get("title") or "").strip(),
                url=url,
                snippet=(item.get("body") or "").strip()[:SNIPPET_LENGTH],
            )
        )
    return hits


async def web_search(query: str, max_results: int = MAX_RESULTS) -> list[SearchHit]:
    """Tìm kiếm web, trả về danh sách kết quả (title/url/snippet). Có thử lại khi bị rate-limit."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await asyncio.to_thread(_search_sync, query, max_results)
        except DDGSException as exc:
            logger.info("Không có kết quả tìm kiếm cho %r (lần %s): %s", query, attempt + 1, exc)
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        except Exception:
            logger.exception("Lỗi khi tìm kiếm: %s", query)
            return []
    return []
