"""Gửi thông báo lời nhắc qua kênh của người dùng (T51)."""

import logging
from datetime import UTC

import httpx

from app.channels.base import send_text
from app.database.models import Reminder
from app.database.repository import UserRepository
from app.reminders import service

logger = logging.getLogger(__name__)


def _message(reminder: Reminder, tz) -> str:
    local = reminder.remind_at.replace(tzinfo=UTC).astimezone(tz)
    lines = [
        f"🔔 Nhắc nhở: {reminder.text}",
        f"Thời gian: {local.strftime('%H:%M %d/%m/%Y')} (giờ {tz.key})",
    ]
    if reminder.repeat == "daily":
        lines.append("Lặp lại: hằng ngày")
    elif reminder.repeat == "weekly":
        lines.append("Lặp lại: hằng tuần")
    return "\n".join(lines)


async def notify(session, user_id: int, reminder: Reminder) -> bool:
    """Gửi tin nhắc; True nếu gửi thành công (tick sau sẽ thử lại nếu thất bại)."""
    user = await UserRepository(session).get(user_id)
    if user is None:
        logger.warning("Không tìm thấy user id=%s để gửi lời nhắc", user_id)
        return False

    tz = await service.user_tz(session, user_id)
    text = _message(reminder, tz)

    # Zalo ngoài cửa sổ 48h CS bị từ chối → tick sau scheduler thử lại
    try:
        await send_text(user.channel, user.channel_user_id, text, proactive=True)
        return True
    except ValueError:
        logger.warning("Kênh %s chưa hỗ trợ gửi thông báo (user %s)", user.channel, user_id)
        return False
    except httpx.HTTPError:
        logger.exception("Lỗi gửi lời nhắc qua %s cho user %s", user.channel, user_id)
        return False
