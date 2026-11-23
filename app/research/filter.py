"""Lọc kết quả nghiên cứu: phát hiện trùng lặp (T42) và xếp độ liên quan (T43)."""

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.research.search import SearchHit

MIN_TOKEN_LENGTH = 3
TITLE_SIMILARITY_THRESHOLD = 0.9
DROP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def canonical_url(url: str) -> str:
    """Chuẩn hóa URL để so trùng: bỏ fragment, tham số theo dõi, dấu / cuối."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in DROP_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _tokens(text: str) -> set[str]:
    return {word.lower() for word in _TOKEN_RE.findall(text or "") if len(word) >= MIN_TOKEN_LENGTH}


def dedupe(items: list) -> list:
    """Bỏ kết quả trùng URL (sau chuẩn hóa) hoặc tiêu đề gần giống nhau (T42).

    Nhận mọi object có `.title` và `.url` (SearchHit, FetchedArticle...).
    """
    kept: list = []
    seen_urls: set[str] = set()
    for item in items:
        url = canonical_url(item.url)
        if url in seen_urls:
            continue
        if any(SequenceMatcher(None, item.title.lower(), other.title.lower()).ratio() >= TITLE_SIMILARITY_THRESHOLD for other in kept):
            continue
        seen_urls.add(url)
        kept.append(item)
    return kept


def score_relevance(text: str, query: str, preferences: dict[str, str] | None = None) -> int:
    """Điểm = số token của câu hỏi/sở thích xuất hiện trong nội dung."""
    wanted = _tokens(query) | _tokens(" ".join((preferences or {}).values()))
    content = (text or "").lower()
    return sum(1 for token in wanted if token in content)


def filter_relevant(
    hits: list[SearchHit],
    query: str,
    preferences: dict[str, str] | None = None,
    limit: int = 5,
) -> list[SearchHit]:
    """Giữ các kết quả liên quan nhất tới câu hỏi + sở thích người dùng (T43)."""
    scored = [(score_relevance(f"{hit.title} {hit.snippet}", query, preferences), hit) for hit in hits]
    with_overlap = [item for item in scored if item[0] > 0]
    pool = with_overlap if len(with_overlap) >= limit else scored
    pool.sort(key=lambda item: item[0], reverse=True)
    return [hit for _, hit in pool[:limit]]
