"""Hàng đợi xử lý tin nhắn nền (T58) + retry/dead-letter (T59).

Thiết kế đã chốt:
- In-memory only (asyncio.Queue): KHÔNG có bảng jobs, mất queue khi restart
  (trade-off có chủ đích — platform webhook redeliver khi 503).
- SINGLE worker: giữ FIFO và thứ tự hội thoại per-user. Hai worker có thể
  đan xen read-modify-write lịch sử của cùng user. Muốn tăng throughput sau này:
  cần per-user lock / partition — ngoài phạm vi EPIC 09.
- handle_message thành công thì KHÔNG bao giờ chạy lại (tránh lặp lượt hội thoại);
  lỗi sau handle → chỉ retry phần gửi.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

from app.channels.base import IncomingMessage, send_text
from app.conversation.handler import handle_message
from app.database.connection import SessionLocal

logger = logging.getLogger(__name__)

QUEUE_MAXSIZE = 1000          # tin chờ tối đa trước khi webhook trả 503
MAX_ATTEMPTS = 3              # số lần thử cho mỗi phase (handle / send)
RETRY_BACKOFF_SECONDS = 1     # 1s, 2s, 4s — ngủ NGAY trong worker (cũng là rate-limit tự nhiên)
DEAD_LETTER_LIMIT = 50        # giữ tối đa N bản ghi dead-letter gần nhất


class QueueFullError(Exception):
    """Hàng đợi đã đầy — webhook nên trả 503 để platform redeliver."""


@dataclass(frozen=True)
class DeadLetter:
    channel: str
    user_id: str
    text_snippet: str
    phase: str          # "handle" | "send"
    attempts: int
    error: str
    failed_at: datetime # naive-UTC


_queue: asyncio.Queue[IncomingMessage] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
_dead_letters: deque[DeadLetter] = deque(maxlen=DEAD_LETTER_LIMIT)


def enqueue(message: IncomingMessage) -> None:
    """Đưa tin vào hàng đợi (non-blocking). Ném QueueFullError khi đầy."""
    try:
        _queue.put_nowait(message)
    except asyncio.QueueFull:
        logger.warning(
            "Hàng đợi đầy (%s) — từ chối tin từ %s/%s",
            _queue.maxsize, message.channel, message.user_id,
        )
        raise QueueFullError("Hàng đợi tin nhắn đầy") from None


def _is_rate_limited(exc: BaseException) -> bool:
    """429 = quota Gemini: retry chỉ tốn thêm quota (đồng nhất triết lý llm.py:16)."""
    return getattr(exc, "code", None) == 429


async def _retry(phase: str, message: IncomingMessage, op) -> object:
    """Chạy op tối đa MAX_ATTEMPTS lần; 429 → dừng ngay; hết → ném exception cuối."""
    last_exc: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await op()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_exc = exc
            if _is_rate_limited(exc):
                logger.error(
                    "Bị rate-limit (429) ở phase %s, không retry — %s/%s: %s",
                    phase, message.channel, message.user_id, exc,
                )
                break
            if attempt < MAX_ATTEMPTS:
                wait = RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
                logger.warning(
                    "Phase %s thất bại (lần %s/%s), thử lại sau %ss — %s/%s: %s",
                    phase, attempt, MAX_ATTEMPTS, wait,
                    message.channel, message.user_id, exc,
                )
                await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def _handle_phase(message: IncomingMessage) -> str:
    async def op() -> str:
        async with SessionLocal() as session:
            return await handle_message(message, session)

    return await _retry("handle", message, op)  # type: ignore[return-value]


async def _send_phase(message: IncomingMessage, reply: str) -> None:
    async def op() -> None:
        # proactive=False (mặc định) → Messenger dùng RESPONSE cho trả lời
        await send_text(message.channel, message.user_id, reply)

    await _retry("send", message, op)


def _dead_letter(message: IncomingMessage, phase: str, attempts: int, exc: BaseException) -> None:
    entry = DeadLetter(
        channel=message.channel,
        user_id=message.user_id,
        text_snippet=message.text[:80],
        phase=phase,
        attempts=attempts,
        error=f"{type(exc).__name__}: {exc}",
        failed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    _dead_letters.append(entry)
    logger.error(
        "DEAD-LETTER phase=%s kênh=%s user=%s attempts=%s text=%r error=%s",
        entry.phase, entry.channel, entry.user_id, entry.attempts,
        entry.text_snippet, entry.error,
    )


async def _process_job(message: IncomingMessage) -> None:
    logger.info("Xử lý tin nhắn từ %s/%s: %r", message.channel, message.user_id, message.text[:60])
    try:
        reply = await _handle_phase(message)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _dead_letter(message, phase="handle", attempts=MAX_ATTEMPTS, exc=exc)
        return
    try:
        await _send_phase(message, reply)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # handle đã persist lịch sử — CHỈ dead-letter phần gửi, không chạy lại handle
        _dead_letter(message, phase="send", attempts=MAX_ATTEMPTS, exc=exc)


async def worker() -> None:
    """Vòng lặp worker vô hạn: lấy job → xử lý → task_done. Huỷ khi lifespan shutdown."""
    logger.info("Worker hàng đợi tin nhắn đã khởi động (maxsize=%s)", _queue.maxsize)
    while True:
        message = await _queue.get()
        try:
            await _process_job(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            # lưới an toàn cuối cùng — _process_job đã nuốt lỗi xử lý rồi
            logger.exception("Lỗi không ngờ khi xử lý job từ %s/%s", message.channel, message.user_id)
        finally:
            _queue.task_done()


def _reset_for_tests(maxsize: int = QUEUE_MAXSIZE) -> None:
    """Đưa queue + dead-letter về rỗng — CHỈ dùng trong test."""
    global _queue
    _queue = asyncio.Queue(maxsize=maxsize)
    _dead_letters.clear()
