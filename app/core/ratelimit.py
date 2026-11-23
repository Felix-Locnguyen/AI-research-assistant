"""Giới hạn tần suất gọi LLM và API ngoài (T60) — không dùng thư viện ngoài."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Hằng nút chỉnh ở đây (KHÔNG đưa vào config.py) — theo style llm.py / research.py
LLM_MAX_CONCURRENT = 1
LLM_MIN_INTERVAL_SECONDS = 0.2      # ≥0.2s giữa 2 lần gọi Gemini
SEARCH_MAX_CONCURRENT = 1
SEARCH_MIN_INTERVAL_SECONDS = 1.0   # ≥1s giữa 2 lần DDGS


class RateGate:
    """Semaphore + khoảng nghỉ tối thiểu giữa các lần acquire.

    Số đo khoảng nghỉ tại thời điểm acquire (dưới lock) rồi sleep NGOÀI lock
    để nhiều task không cùng "cướp" một slot thời gian (tránh stampede).
    """

    def __init__(self, max_concurrent: int, min_interval: float) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0  # time.monotonic()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self._sem.acquire()
        try:
            async with self._lock:
                now = time.monotonic()
                wait = max(0.0, self._next_allowed - now)
                # đặt lịch NGAY khi acquire để task sau không vượt mặt
                self._next_allowed = max(now, self._next_allowed) + self._min_interval
            if wait > 0:
                await asyncio.sleep(wait)
            yield
        finally:
            self._sem.release()


# Hai instance module-level — mọi caller dùng chung
LLM_GATE = RateGate(LLM_MAX_CONCURRENT, LLM_MIN_INTERVAL_SECONDS)
SEARCH_GATE = RateGate(SEARCH_MAX_CONCURRENT, SEARCH_MIN_INTERVAL_SECONDS)
