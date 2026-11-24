"""Unit test thuần cho research: filter, collector parsers, summarizer, agents (T61)."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bs4 import BeautifulSoup

from app.research import collector, filter as research_filter, summarizer
from app.research.search import SearchHit


def _hit(title: str, url: str, snippet: str = "") -> SearchHit:
    return SearchHit(title=title, url=url, snippet=snippet)


# ── filter.canonical_url ─────────────────────────────────────

def test_canonical_url_strips_tracking_params():
    url = "HTTPS://Example.com/Post/?utm_source=x&utm_medium=y&fbclid=abc#frag"
    assert research_filter.canonical_url(url) == "https://example.com/Post"


def test_canonical_url_keeps_meaningful_query():
    url = "https://example.com/search?q=python&page=2"
    assert research_filter.canonical_url(url) == "https://example.com/search?q=python&page=2"


# ── filter.dedupe ────────────────────────────────────────────

def test_dedupe_by_canonical_url():
    a = _hit("Bài A", "https://ex.com/a?utm_source=rss")
    b = _hit("Bài B", "https://ex.com/a")
    assert research_filter.dedupe([a, b]) == [a]


def test_dedupe_by_similar_title():
    a = _hit("Tin tức công nghệ mới nhất hôm nay", "https://ex.com/1")
    b = _hit("Tin tức công nghệ mới nhất hôm nay", "https://ex.com/2")
    c = _hit("Thể thao bóng đá", "https://ex.com/3")
    kept = research_filter.dedupe([a, b, c])
    assert kept == [a, c]


# ── filter.score_relevance / filter_relevant ────────────────

def test_score_relevance_counts_tokens():
    prefs = {"interest": "python"}
    score = research_filter.score_relevance("Học python mỗi ngày", "python fastapi", prefs)
    # "python" khớp query + prefs (set gộp, đếm 1 lần), "fastapi" không có → 1
    assert score == 1


def test_filter_relevance_prefers_overlap():
    hits = [
        _hit("Python tips", "https://ex.com/1", "python rất hay"),
        _hit("Cooking", "https://ex.com/2", "nấu ăn"),
    ]
    result = research_filter.filter_relevant(hits, "python", None, limit=1)
    assert [h.url for h in result] == ["https://ex.com/1"]


def test_filter_relevance_fallback_when_no_overlap():
    # không hit nào khớp → pool = mọi scored (vẫn trả về, sort theo điểm 0)
    hits = [_hit("A", "https://ex.com/1"), _hit("B", "https://ex.com/2")]
    result = research_filter.filter_relevant(hits, "zzzzz", None, limit=5)
    assert len(result) == 2


def test_filter_relevance_respects_limit():
    hits = [_hit(f"T{i} python", f"https://ex.com/{i}", "python") for i in range(10)]
    result = research_filter.filter_relevant(hits, "python", None, limit=3)
    assert len(result) == 3


# ── collector parsers ────────────────────────────────────────

def test_parse_datetime_iso_and_zulu():
    assert collector._parse_datetime("2026-01-02T10:00:00Z") == datetime(2026, 1, 2, 10, 0, 0)
    aware = datetime(2026, 1, 2, 10, 0, 0)
    parsed = collector._parse_datetime(aware)
    assert parsed.tzinfo is None
    assert collector._parse_datetime("garbage") is None
    assert collector._parse_datetime("") is None
    assert collector._parse_datetime(None) is None


CANNED_HTML = """
<html><head>
<meta property="og:title" content="OG Title"/>
<meta property="article:published_time" content="2026-01-02T10:00:00Z"/>
<script>var x=1;</script>
</head><body><nav>menu</nav>
<article><h1>Real Title</h1><p>Nội dung bài viết dài hơn hai trăm ký tự để vượt ngưỡng
kiểm tra của collector. Lorem ipsum dolor sit amet consectetur adipiscing elit sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam quis
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p></article>
</body></html>
"""


def test_extract_text_prefers_h1_and_article():
    soup = BeautifulSoup(CANNED_HTML, "html.parser")
    title, text = collector._extract_text(soup)
    assert title == "Real Title"
    assert "menu" not in text        # nav bị bỏ
    assert "var x" not in text       # script bị bỏ
    assert "Nội dung bài viết" in text


def test_extract_text_falls_back_to_og_title():
    html = "<html><head><meta property='og:title' content='OG'/></head><body><p>x</p></body></html>"
    title, _ = collector._extract_text(BeautifulSoup(html, "html.parser"))
    assert title == "OG"


def test_extract_text_falls_back_to_title_tag():
    html = "<html><head><title>Title Tag</title></head><body><p>x</p></body></html>"
    title, _ = collector._extract_text(BeautifulSoup(html, "html.parser"))
    assert title == "Title Tag"


def test_extract_published_from_meta_or_time():
    soup = BeautifulSoup(CANNED_HTML, "html.parser")
    assert collector._extract_published(soup) == datetime(2026, 1, 2, 10, 0, 0)

    html = "<html><body><time datetime='2026-03-04T05:06:07'></time></body></html>"
    assert collector._extract_published(BeautifulSoup(html, "html.parser")) == datetime(2026, 3, 4, 5, 6, 7)

    assert collector._extract_published(BeautifulSoup("<html><body></body></html>", "html.parser")) is None


CANNED_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Tin A</title><link>https://ex.com/a</link><summary>Sa</summary></item>
<item><title>Tin B</title><link>https://ex.com/b</link></item>
<item><title>No link</title><summary>x</summary></item>
</channel></rss>"""


def test_parse_feed_parses_entries():
    hits = collector._parse_feed(CANNED_RSS, limit=5)
    # item không link bị bỏ qua (feedparser vẫn liệt kê 3 entry)
    assert [h.url for h in hits] == ["https://ex.com/a", "https://ex.com/b"]
    assert hits[0].title == "Tin A"
    assert hits[0].snippet == "Sa"
    assert hits[1].snippet == ""


def test_parse_feed_respects_limit():
    hits = collector._parse_feed(CANNED_RSS, limit=1)
    assert len(hits) == 1


def test_parse_feed_snippet_truncated_to_300():
    long_summary = "x" * 500
    rss = f"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>T</title><link>https://ex.com/l</link><summary>{long_summary}</summary></item>
    </channel></rss>"""
    hits = collector._parse_feed(rss, limit=5)
    assert len(hits[0].snippet) == 300


# ── summarizer ───────────────────────────────────────────────

def _article(i: int) -> collector.FetchedArticle:
    return collector.FetchedArticle(title=f"Bài {i}", url=f"https://ex.com/{i}", text="nội dung", source="ex.com", published_at=None)


def test_summarize_empty_articles_returns_empty(monkeypatch):
    gen = AsyncMock()
    monkeypatch.setattr(summarizer.llm, "generate", gen)
    assert asyncio.run(summarizer.summarize([], "q")) == {}
    gen.assert_not_awaited()


def test_summarize_valid_json_filters_irrelevant(monkeypatch):
    response = MagicMock()
    response.text = '[{"index":0,"summary":"Tốt","relevant":true},{"index":1,"summary":"X","relevant":false}]'
    monkeypatch.setattr(summarizer.llm, "generate", AsyncMock(return_value=response))
    result = asyncio.run(summarizer.summarize([_article(0), _article(1)], "q"))
    assert result == {0: "Tốt"}


def test_summarize_invalid_json_returns_empty(monkeypatch):
    response = MagicMock()
    response.text = "not json"
    monkeypatch.setattr(summarizer.llm, "generate", AsyncMock(return_value=response))
    assert asyncio.run(summarizer.summarize([_article(0)], "q")) == {}


# ── agents/research: generate_queries + _format ─────────────

def test_generate_queries_fallback_on_llm_error(monkeypatch):
    from app.agents import research as research_agent

    monkeypatch.setattr(research_agent.llm, "generate", AsyncMock(side_effect=RuntimeError("boom")))
    queries = asyncio.run(research_agent.generate_queries("hỏi gì đó", {}))
    assert queries == ["hỏi gì đó"]


def test_generate_queries_parses_and_caps(monkeypatch):
    from app.agents import research as research_agent

    response = MagicMock()
    response.text = '["q1", " q2 ", "q3", "q4", ""]'
    monkeypatch.setattr(research_agent.llm, "generate", AsyncMock(return_value=response))
    queries = asyncio.run(research_agent.generate_queries("câu hỏi", {}))
    assert queries == ["q1", "q2", "q3"]  # cap MAX_QUERIES=3, strip


def test_format_empty_rows():
    from app.agents import research as research_agent

    out = research_agent._format("câu hỏi", [])
    assert "## Kết quả nghiên cứu" in out
    assert "**câu hỏi**" in out


def test_format_rows_markdown():
    from app.agents import research as research_agent

    article = SimpleNamespace(
        title="Bài viết", url="https://ex.com/a", source="ex.com",
        published_at=datetime(2026, 1, 1),
    )
    out = research_agent._format("q", [(article, "Tóm tắt hay")])
    assert "### 1. Bài viết" in out
    assert "- Nguồn: ex.com — 2026-01-01" in out
    assert "- Link: https://ex.com/a" in out
    assert "- Tóm tắt: Tóm tắt hay" in out

    out_none = research_agent._format("q", [(article, None)])
    assert "chưa có — xem link" in out_none
