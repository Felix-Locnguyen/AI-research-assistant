"""Job nền kiểm tra lời nhắc đến hạn và gửi thông báo (T50)."""

import asyncio
import logging
from datetime import UTC, datetime

from app.database.connection import SessionLocal
from app.database.repository import ReminderRepository
from app.reminders import notifier, service

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 60


async def run_once() -> None:
    """Quét một lượt: gửi lời nhắc đến hạn rồi đánh dấu / dời lịch lặp."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with SessionLocal() as session:
        due = await ReminderRepository(session).list_due(now)
        for reminder in due:
            sent = await notifier.notify(session, reminder.user_id, reminder)
            if not sent:
                continue                      # giữ nguyên để tick sau thử lại
            await service.mark_fired(session, reminder)
            logger.info("Đã nhắc reminder id=%s (repeat=%s)", reminder.id, reminder.repeat)


async def run_loop() -> None:
    while True:
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
        try:
            await run_once()
        except Exception:
            logger.exception("Lỗi khi quét lời nhắc đến hạn")
