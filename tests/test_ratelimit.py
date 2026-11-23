import asyncio
import time
from contextlib import asynccontextmanager

from app.core.ratelimit import RateGate


def test_min_interval_enforced():
    gate = RateGate(max_concurrent=1, min_interval=0.1)

    async def scenario():
        start = time.monotonic()
        async with gate.acquire():
            pass
        async with gate.acquire():
            pass
        return time.monotonic() - start

    elapsed = asyncio.run(scenario())
    assert elapsed >= 0.09  # bound rộng chống flaky


def test_max_concurrent_blocks():
    gate = RateGate(max_concurrent=1, min_interval=0)

    async def scenario():
        entered = asyncio.Event()

        async def holder():
            async with gate.acquire():
                entered.set()
                await asyncio.sleep(0.2)

        async def contender() -> bool:
            async with gate.acquire():
                return True

        holder_task = asyncio.create_task(holder())
        await entered.wait()
        contender_task = asyncio.create_task(contender())
        await asyncio.sleep(0.05)
        assert not contender_task.done()  # đang bị semaphore chặn
        await holder_task
        assert await asyncio.wait_for(contender_task, timeout=1) is True

    asyncio.run(scenario())


def test_gate_released_on_exception():
    gate = RateGate(max_concurrent=1, min_interval=0)

    async def scenario():
        try:
            async with gate.acquire():
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        async with gate.acquire():  # phải qua được ngay
            pass

    asyncio.run(scenario())


class RecordingGate:
    def __init__(self):
        self.entered = 0

    @asynccontextmanager
    async def acquire(self):
        self.entered += 1
        yield


def test_llm_generate_acquires_gate(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.core import llm

    gate = RecordingGate()
    monkeypatch.setattr(llm, "LLM_GATE", gate)

    response = MagicMock()
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    result = asyncio.run(llm.generate("s", [{"role": "user", "parts": [{"text": "hi"}]}]))
    assert result is response
    assert gate.entered == 1


def test_search_gate_wraps_call(monkeypatch):
    from app.research import search

    gate = RecordingGate()
    monkeypatch.setattr(search, "SEARCH_GATE", gate)
    monkeypatch.setattr(search, "_search_sync", lambda q, m: [])

    hits = asyncio.run(search.web_search("q"))
    assert hits == []
    assert gate.entered == 1
