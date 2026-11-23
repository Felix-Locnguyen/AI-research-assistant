"""Truy xuất ký ức liên quan tới câu hỏi hiện tại (T35).

Không dùng embedding: lấy pool ký ức còn hạn từ SQL rồi xếp hạng trong Python
theo số token khớp, đồng hạng thì mới hơn đứng trước.
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory
from app.database.repository import MemoryRepository

POOL_SIZE = 100
MIN_TOKEN_LENGTH = 3
STOPWORDS = {
    "tôi", "mình", "bạn", "là", "của", "cho", "và", "ở", "có", "được", "các",
    "những", "này", "đó", "với", "từ", "về", "khi", "như", "một", "hay", "hay",
}

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    words = _TOKEN_RE.findall(text.lower())
    return {
        word
        for word in words
        if len(word) >= MIN_TOKEN_LENGTH and word not in STOPWORDS
    }


async def retrieve(
    session: AsyncSession, user_id: int, query: str, limit: int = 20
) -> list[Memory]:
    """Trả về tối đa `limit` ký ức liên quan nhất tới `query` (khớp token + mới hơn trước)."""
    pool = await MemoryRepository(session).list_active(user_id, POOL_SIZE)
    query_tokens = _tokens(query or "")

    def score(memory: Memory) -> tuple[int, int]:
        content = memory.content.lower()
        hits = sum(1 for token in query_tokens if token in content)
        return (hits, memory.id)

    ranked = sorted(pool, key=score, reverse=True)
    return ranked[:limit]
