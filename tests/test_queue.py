import asyncio
from unittest.mock import AsyncMock

import pytest

from app.channels.base import IncomingMessage
from app.core import queue as job_queue
from app.core.queue import MAX_ATTEMPTS, QueueFullError


@pytest.fixture(autouse=True)
def _clean_queue():
    job_queue._reset_for_tests()
    yield
    job_queue._reset_for_tests()


def _msg(text: str = "xin chào", user_id: str = "u1") -> IncomingMessage:
    return IncomingMessage(channel="telegram", user_id=user_id, username=None, text=text)


def _run_worker_until_idle():
    async def scenario():
        task = asyncio.create_task(job_queue.worker())
        try:
            await asyncio.wait_for(job_queue._queue.join(), timeout=2)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return asyncio.run(scenario())


def test_enqueue_and_worker_processes(monkeypatch):
    handle = AsyncMock(return_value="ok")
    send = AsyncMock()
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    job_queue.enqueue(_msg())
    _run_worker_until_idle()

    handle.assert_awaited_once()
    incoming = handle.await_args.args[0]
    assert incoming.channel == "telegram"
    assert incoming.user_id == "u1"
    assert incoming.text == "xin chào"
    send.assert_awaited_once_with("telegram", "u1", "ok")


def test_fifo_order(monkeypatch):
    seen: list[str] = []

    async def fake_handle(message, session):
        seen.append(message.text)
        return "r"

    monkeypatch.setattr(job_queue, "handle_message", fake_handle)
    monkeypatch.setattr(job_queue, "send_text", AsyncMock())

    for text in ("a", "b", "c"):
        job_queue.enqueue(_msg(text=text))
    _run_worker_until_idle()

    assert seen == ["a", "b", "c"]


def test_handle_failure_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    handle = AsyncMock(side_effect=[RuntimeError("x"), RuntimeError("x"), "ok"])
    send = AsyncMock()
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    job_queue.enqueue(_msg())
    _run_worker_until_idle()

    assert handle.await_count == 3
    send.assert_awaited_once_with("telegram", "u1", "ok")
    assert len(job_queue._dead_letters) == 0


def test_handle_persistent_failure_dead_letter(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    handle = AsyncMock(side_effect=RuntimeError("boom"))
    send = AsyncMock()
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    with caplog.at_level(logging.ERROR):
        job_queue.enqueue(_msg())
        _run_worker_until_idle()

    assert handle.await_count == MAX_ATTEMPTS
    send.assert_not_awaited()
    assert len(job_queue._dead_letters) == 1
    entry = job_queue._dead_letters[0]
    assert entry.phase == "handle"
    assert entry.attempts == MAX_ATTEMPTS
    assert any("DEAD-LETTER" in record.message for record in caplog.records)


def test_429_immediate_dead_letter_no_retry(monkeypatch):
    class RateLimited(Exception):
        code = 429

    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    handle = AsyncMock(side_effect=RateLimited("quota"))
    send = AsyncMock()
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    job_queue.enqueue(_msg())
    _run_worker_until_idle()

    assert handle.await_count == 1  # 429 → không retry
    send.assert_not_awaited()
    assert len(job_queue._dead_letters) == 1
    assert job_queue._dead_letters[0].phase == "handle"


def test_send_failure_handle_not_rerun(monkeypatch):
    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    handle = AsyncMock(return_value="ok")
    send = AsyncMock(side_effect=RuntimeError("net"))
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    job_queue.enqueue(_msg())
    _run_worker_until_idle()

    handle.assert_awaited_once()  # KHÔNG chạy lại handle
    assert send.await_count == MAX_ATTEMPTS
    assert len(job_queue._dead_letters) == 1
    assert job_queue._dead_letters[0].phase == "send"


def test_send_failure_then_success(monkeypatch):
    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    handle = AsyncMock(return_value="ok")
    send = AsyncMock(side_effect=[RuntimeError("net"), RuntimeError("net"), None])
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)

    job_queue.enqueue(_msg())
    _run_worker_until_idle()

    handle.assert_awaited_once()
    assert send.await_count == 3
    assert len(job_queue._dead_letters) == 0


def test_queue_full_raises():
    job_queue._reset_for_tests(maxsize=2)
    job_queue.enqueue(_msg(text="1"))
    job_queue.enqueue(_msg(text="2"))
    with pytest.raises(QueueFullError):
        job_queue.enqueue(_msg(text="3"))


def test_worker_task_done_on_failure(monkeypatch):
    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(job_queue, "handle_message", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(job_queue, "send_text", AsyncMock())

    job_queue.enqueue(_msg())
    _run_worker_until_idle()  # join chỉ trả về khi task_done đã chạy (unfinished == 0)


def test_reset_for_tests_clears_state():
    job_queue.enqueue(_msg())
    job_queue._dead_letters.append(
        job_queue.DeadLetter("telegram", "u1", "x", "handle", 3, "err", None)
    )
    job_queue._reset_for_tests()
    assert job_queue._queue.qsize() == 0
    assert len(job_queue._dead_letters) == 0


def test_stats_after_enqueue():
    assert job_queue.stats() == {"pending": 0, "dead_letters": 0}
    job_queue.enqueue(_msg())
    assert job_queue.stats() == {"pending": 1, "dead_letters": 0}


def test_stats_after_dead_letter(monkeypatch):
    monkeypatch.setattr(job_queue, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(job_queue, "handle_message", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(job_queue, "send_text", AsyncMock())
    job_queue.enqueue(_msg())
    _run_worker_until_idle()
    assert job_queue.stats() == {"pending": 0, "dead_letters": 1}
