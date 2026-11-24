"""Unit test cho core.llm: _is_transient, _get_client, retry loop (T61)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.core import llm


class FakeAPIError(Exception):
    def __init__(self, code: int, msg: str = "api error"):
        super().__init__(msg)
        self.code = code


def _fake_client(outcomes: list):
    """Client giả: mỗi lần gọi lấy outcome kế tiếp (Exception → raise, còn lại trả về)."""
    client = MagicMock()
    index = {"n": 0}

    async def _gen(**kwargs):
        i = index["n"]
        index["n"] += 1
        outcome = outcomes[i]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client.aio.models.generate_content = _gen
    client.call_count = lambda: index["n"]
    return client


# ── _is_transient ────────────────────────────────────────────

def test_is_transient_runtime_error_false():
    # RuntimeError = lỗi cấu hình (thiếu key) — retry vô ích
    assert llm._is_transient(RuntimeError("config")) is False


def test_is_transient_known_codes():
    assert llm._is_transient(FakeAPIError(503)) is True
    assert llm._is_transient(FakeAPIError(400)) is False
    assert llm._is_transient(FakeAPIError(429)) is False  # quota: retry tốn thêm quota


def test_is_transient_unknown_exception_true():
    assert llm._is_transient(Exception("network")) is True


# ── _get_client ──────────────────────────────────────────────

def test_get_client_raises_without_key(monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", "")
    monkeypatch.setattr(llm, "_client", None)
    with pytest.raises(RuntimeError, match="Thiếu GEMINI_API_KEY"):
        llm._get_client()


# ── generate retry loop ──────────────────────────────────────

def test_generate_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    response = MagicMock()
    client = _fake_client([FakeAPIError(503), response])
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    out = asyncio.run(llm.generate("sys", [{"role": "user", "parts": [{"text": "hi"}]}]))
    assert out is response
    assert client.call_count() == 2


def test_generate_no_retry_on_non_transient(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    client = _fake_client([RuntimeError("config")])
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    with pytest.raises(RuntimeError, match="config"):
        asyncio.run(llm.generate("sys", []))
    assert client.call_count() == 1


def test_generate_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    client = _fake_client([FakeAPIError(503)] * llm.MAX_RETRIES)
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    with pytest.raises(FakeAPIError):
        asyncio.run(llm.generate("sys", []))
    assert client.call_count() == llm.MAX_RETRIES


def test_generate_acquires_gate(monkeypatch):
    """Gate bọc quanh call API (EPIC 09 — đã khôi phục trong EPIC 10 Step 0)."""
    from contextlib import asynccontextmanager

    class RecordingGate:
        def __init__(self):
            self.entered = 0

        @asynccontextmanager
        async def acquire(self):
            self.entered += 1
            yield

    gate = RecordingGate()
    monkeypatch.setattr(llm, "LLM_GATE", gate)
    client = _fake_client([MagicMock()])
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    asyncio.run(llm.generate("sys", []))
    assert gate.entered == 1
    assert client.call_count() == 1
