"""Unit test thuần cho memory: validate, context markdown, retriever, extractor (T61)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory import extractor, manager, retriever


# ── manager.validate_content ─────────────────────────────────

def test_validate_content_strips_and_truncates():
    long = "  " + "a" * 600 + "  "
    result = manager.validate_content(long)
    assert result == "a" * 500  # strip rồi [:500]


def test_validate_content_empty_raises():
    with pytest.raises(ValueError, match="rỗng"):
        manager.validate_content("")
    with pytest.raises(ValueError, match="rỗng"):
        manager.validate_content("   ")


def test_validate_content_too_short_raises():
    with pytest.raises(ValueError, match="quá ngắn"):
        manager.validate_content("ngắn")


def test_validate_content_no_letters_raises():
    with pytest.raises(ValueError, match="chữ cái"):
        manager.validate_content("1234567890 !!!")  # ≥10 ký tự nhưng không có chữ cái


def test_validate_content_accepts_vietnamese():
    assert manager.validate_content("Tôi thích cà phê buổi sáng") == "Tôi thích cà phê buổi sáng"


# ── manager.build_context_markdown ───────────────────────────

def test_build_context_markdown_empty():
    assert manager.build_context_markdown({}, None) == ""
    assert manager.build_context_markdown({}, []) == ""


def test_build_context_markdown_prefs_and_memories():
    memories = [SimpleNamespace(content="Thích Python"), SimpleNamespace(content="Sống ở Hà Nội")]
    out = manager.build_context_markdown({"city": "HN"}, memories)
    assert out.startswith("\n\n")
    assert "## Sở thích người dùng đã lưu" in out
    assert "- city: HN" in out
    assert "## Ký ức đã lưu" in out
    assert "- Thích Python" in out
    assert "- Sống ở Hà Nội" in out


def test_build_context_markdown_prefs_only():
    out = manager.build_context_markdown({"lang": "vi"}, None)
    assert "## Sở thích" in out
    assert "## Ký ức" not in out


# ── retriever ────────────────────────────────────────────────

def test_tokens_filters_stopwords_and_short():
    tokens = retriever._tokens("tôi là dev python")
    assert "tôi" not in tokens   # stopword
    assert "là" not in tokens    # stopword
    assert "dev" in tokens
    assert "python" in tokens


def test_retrieve_ranks_by_hits_then_id(monkeypatch):
    pool = [
        SimpleNamespace(id=1, content="thích python và fastapi"),
        SimpleNamespace(id=2, content="python là ngôn ngữ"),
        SimpleNamespace(id=3, content="kafka streaming"),
    ]
    monkeypatch.setattr(retriever.MemoryRepository, "list_active", AsyncMock(return_value=pool))
    result = asyncio.run(retriever.retrieve(MagicMock(), 1, "python fastapi"))
    # id=2: 1 hit python; id=1: 2 hits (python, fastapi) → cao hơn; id=3: 0 hit nhưng vẫn trả (limit)
    assert [m.id for m in result] == [1, 2, 3]


def test_retrieve_tie_breaks_by_id_desc(monkeypatch):
    pool = [
        SimpleNamespace(id=1, content="yêu thích cà phê"),
        SimpleNamespace(id=5, content="yêu thích trà"),
    ]
    monkeypatch.setattr(retriever.MemoryRepository, "list_active", AsyncMock(return_value=pool))
    result = asyncio.run(retriever.retrieve(MagicMock(), 1, "yêu thích"))
    assert [m.id for m in result] == [5, 1]  # đồng hạng → id lớn hơn trước


def test_retrieve_respects_limit(monkeypatch):
    pool = [SimpleNamespace(id=i, content=f"mục {i}") for i in range(1, 31)]
    monkeypatch.setattr(retriever.MemoryRepository, "list_active", AsyncMock(return_value=pool))
    result = asyncio.run(retriever.retrieve(MagicMock(), 1, "mục", limit=5))
    assert len(result) == 5


# ── extractor ────────────────────────────────────────────────

def test_should_extract_boundaries():
    assert extractor.should_extract("a" * 14) is False
    assert extractor.should_extract("a" * 15) is True
    assert extractor.should_extract("/helpDoingSomething") is False
    assert extractor.should_extract("") is False
    assert extractor.should_extract("   ") is False


def test_extract_invalid_json_swallows(monkeypatch):
    response = MagicMock()
    response.text = "{oops"
    monkeypatch.setattr(extractor.llm, "generate", AsyncMock(return_value=response))
    # không mở session, không raise
    asyncio.run(extractor.extract(1, "đủ mười lăm ký tự ạ", "trả lời"))


def test_extract_empty_json_returns(monkeypatch):
    response = MagicMock()
    response.text = "[]"
    gen = AsyncMock(return_value=response)
    monkeypatch.setattr(extractor.llm, "generate", gen)
    asyncio.run(extractor.extract(1, "đủ mười lăm ký tự ạ", "trả lời"))
    gen.assert_awaited_once()


def test_extract_skips_short_text(monkeypatch):
    gen = AsyncMock()
    monkeypatch.setattr(extractor.llm, "generate", gen)
    asyncio.run(extractor.extract(1, "ngắn", "trả lời"))
    gen.assert_not_awaited()


def test_extract_saves_valid_items(monkeypatch):
    response = MagicMock()
    response.text = '[{"content": "Thích uống cà phê mỗi sáng", "expires_in_days": 30}]'
    monkeypatch.setattr(extractor.llm, "generate", AsyncMock(return_value=response))
    saved = []

    class FakeManager:
        def __init__(self, session):
            pass

        async def save(self, user_id, content, expires_at=None):
            saved.append((user_id, content, expires_at is not None))
            return SimpleNamespace(id=1)

    monkeypatch.setattr(extractor, "MemoryManager", FakeManager)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(extractor, "SessionLocal", lambda: FakeSession())
    asyncio.run(extractor.extract(7, "Tôi thích uống cà phê mỗi sáng", "ok"))
    assert saved == [(7, "Thích uống cà phê mỗi sáng", True)]


def test_extract_invalid_item_skipped(monkeypatch):
    response = MagicMock()
    response.text = '[{"content": "rỗng"}]'
    monkeypatch.setattr(extractor.llm, "generate", AsyncMock(return_value=response))

    class FakeManager:
        def __init__(self, session):
            pass

        async def save(self, user_id, content, expires_at=None):
            # giả lập validate của manager
            raise ValueError("Nội dung ký ức quá ngắn")

    monkeypatch.setattr(extractor, "MemoryManager", FakeManager)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(extractor, "SessionLocal", lambda: FakeSession())
    asyncio.run(extractor.extract(1, "đủ mười lăm ký tự ạ", "ok"))  # không raise


def test_spawn_creates_and_clears_task(monkeypatch):
    async def fake_extract(user_id, user_text, assistant_text):
        return None

    monkeypatch.setattr(extractor, "extract", fake_extract)

    async def scenario():
        extractor.spawn(1, "đủ mười lăm ký tự ạ", "trả lời")
        assert len(extractor._pending_tasks) == 1
        await asyncio.gather(*extractor._pending_tasks)
        await asyncio.sleep(0)  # chạy done callback
        assert len(extractor._pending_tasks) == 0

    asyncio.run(scenario())
