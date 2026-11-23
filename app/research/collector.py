"""Thu thập nội dung: lấy bài viết từ URL (T41/T45) và nguồn RSS (T39)."""

import asyncio
import calendar
import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.research.search import SearchHit

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 15
MAX_ARTICLE_CHARS = 8000
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


@dataclass
class FetchedArticle:
    title: str
    url: str
    text: str
    source: str | None
    published_at: datetime | None


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _extract_published(soup: BeautifulSoup) -> datetime | None:
    for attr in ("article:published_time", "datePublished", "og:published_time", "date"):
        tag = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
        if tag and tag.get("content"):
            parsed = _parse_datetime(tag["content"])
            if parsed:
                return parsed
    time_tag = soup.find("time", attrs={"datetime": True})
    return _parse_datetime(time_tag["datetime"]) if time_tag else None


def _extract_text(soup: BeautifulSoup) -> tuple[str, str]:
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript"]):
        tag.decompose()
    title = ""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    else:
        og = soup.find("meta", attrs={"property": "og:title"})
        title = (og.get("content") if og else "") or (soup.title.get_text(strip=True) if soup.title else "")
    body = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(body.get_text(separator=" ").split())
    return title.strip(), text[:MAX_ARTICLE_CHARS]


async def fetch_article(url: str) -> FetchedArticle | None:
    """Tải một URL, kiểm tra truy cập được (T45) và trích xuất title/nội dung/ngày đăng (T41)."""
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(url)
    except Exception:
        logger.warning("Không tải được %s", url)
        return None
    if response.status_code != 200:                     # T45: nguồn phải truy cập được
        logger.info("Bỏ qua %s (HTTP %s)", url, response.status_code)
        return None

    soup = BeautifulSoup(response.text, "lxml")
    title, text = _extract_text(soup)
    if not title or len(text) < 200:                    # quá ít nội dung -> không phải bài viết
        return None
    return FetchedArticle(
        title=title,
        url=str(response.url),
        text=text,
        source=urlparse(str(response.url)).netloc,
        published_at=_extract_published(soup),
    )


def _parse_feed(feed_text: str, limit: int) -> list[SearchHit]:
    parsed = feedparser.parse(feed_text)
    hits = []
    for entry in parsed.entries[:limit]:
        link = entry.get("link", "")
        if not link:
            continue
        published = None
        if entry.get("published_parsed"):
            published = datetime.utcfromtimestamp(calendar.timegm(entry["published_parsed"]))
        hits.append(
            SearchHit(
                title=(entry.get("title") or "").strip(),
                url=link,
                snippet=(entry.get("summary") or "").strip()[:300],
            )
        )
    return hits


async def collect_rss(feed_urls: list[str], keywords: list[str] | None = None, limit_per_feed: int = 5) -> list[SearchHit]:
    """Lấy bài mới từ các nguồn RSS (T39); lọc theo keywords nếu có."""
    hits: list[SearchHit] = []
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        for feed_url in feed_urls:
            try:
                response = await client.get(feed_url)
                if response.status_code != 200:
                    continue
                feed_hits = await asyncio.to_thread(_parse_feed, response.text, limit_per_feed)
            except Exception:
                logger.warning("Lỗi khi đọc feed %s", feed_url)
                continue
            if keywords:
                lowered = [word.lower() for word in keywords]
                feed_hits = [
                    hit for hit in feed_hits
                    if any(word in (hit.title + " " + hit.snippet).lower() for word in lowered)
                ]
            hits.extend(feed_hits)
    return hits
