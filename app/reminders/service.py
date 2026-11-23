"""Nghiệp vụ lời nhắc: CRUD (T48), đổi múi giờ (T53) và tính lần lặp kế tiếp (T52)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Reminder
from app.database.repository import ReminderRepository, UserRepository

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
REPEATS = {"none", "daily", "weekly"}


async def user_tz(session: AsyncSession, user_id: int) -> ZoneInfo:
    """Múi giờ của user (preferences key 'timezone'), mặc định giờ Việt Nam."""
    preferences = await UserRepository(session).get_preferences(user_id)
    name = preferences.get("timezone", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def parse_remind_at(raw: str, tz: ZoneInfo) -> datetime:
    """Đổi chuỗi ISO thành naive-UTC: ISO naive hiểu theo `tz`, ISO có offset thì đổi về UTC."""
    try:
        parsed = datetime.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValueError(f"Không hiểu định dạng thời gian: {raw!r}. Dùng ISO 8601, ví dụ 2026-01-01T08:00:00.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC).replace(tzinfo=None)


def format_reminder(reminder: Reminder, tz: ZoneInfo) -> str:
    local = reminder.remind_at.replace(tzinfo=UTC).astimezone(tz)
    suffix = " (lặp lại)" if reminder.repeat != "none" else ""
    return f"id={reminder.id}: {reminder.text} — {local.strftime('%H:%M %d/%m/%Y')} (giờ {tz.key}){suffix}"


def next_occurrence(remind_at: datetime, repeat: str, now: datetime) -> datetime | None:
    """Lần lặp kế tiếp trong tương lai (bỏ qua các lần đã lỡ khi server downtime)."""
    if repeat == "none":
        return None
    delta = timedelta(days=1 if repeat == "daily" else 7)
    next_at = remind_at
    while next_at <= now:
        next_at += delta
    return next_at


async def create_reminder(
    session: AsyncSession, user_id: int, text: str, remind_at_raw: str, repeat: str = "none"
) -> Reminder:
    text = (text or "").strip()
    if not text:
        raise ValueError("Nội dung lời nhắc rỗng")
    if repeat not in REPEATS:
        raise ValueError(f"Kiểu lặp không hợp lệ: {repeat!r}. Dùng none/daily/weekly.")
    tz = await user_tz(session, user_id)
    remind_at = parse_remind_at(remind_at_raw, tz)
    if remind_at <= datetime.now(UTC).replace(tzinfo=None):
        raise ValueError("Thời gian nhắc phải ở tương lai")
    return await ReminderRepository(session).add(user_id, text, remind_at, repeat)


async def list_reminders(session: AsyncSession, user_id: int) -> list[Reminder]:
    return await ReminderRepository(session).list_for_user(user_id)


async def update_reminder(
    session: AsyncSession,
    user_id: int,
    reminder_id: int,
    text: str | None = None,
    remind_at_raw: str | None = None,
    repeat: str | None = None,
) -> Reminder:
    remind_at = None
    if remind_at_raw is not None:
        tz = await user_tz(session, user_id)
        remind_at = parse_remind_at(remind_at_raw, tz)
        if remind_at <= datetime.now(UTC).replace(tzinfo=None):
            raise ValueError("Thời gian nhắc phải ở tương lai")
    if repeat is not None and repeat not in REPEATS:
        raise ValueError(f"Kiểu lặp không hợp lệ: {repeat!r}. Dùng none/daily/weekly.")
    return await ReminderRepository(session).update(user_id, reminder_id, text, remind_at, repeat)


async def delete_reminder(session: AsyncSession, user_id: int, reminder_id: int) -> bool:
    return await ReminderRepository(session).delete(user_id, reminder_id)


async def mark_fired(session: AsyncSession, reminder: Reminder) -> None:
    """Đánh dấu đã nhắc xong: xong hẳn nếu repeat=none, ngược lại dời tới lần kế tiếp."""
    now = datetime.now(UTC).replace(tzinfo=None)
    if reminder.repeat == "none":
        reminder.is_done = True
    else:
        reminder.remind_at = next_occurrence(reminder.remind_at, reminder.repeat, now)
    await session.commit()
