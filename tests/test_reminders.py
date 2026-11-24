"""Unit test cho reminders: parse/format/next_occurrence (thuần) + service/scheduler [db] (T61)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.reminders import notifier, scheduler, service

VN = ZoneInfo("Asia/Ho_Chi_Minh")

# ═══════════════════ pure: service time functions ═══════════════════

def test_parse_remind_at_naive_local_to_utc():
    # 08:00 giờ VN (UTC+7) → 01:00 UTC, naive
    result = service.parse_remind_at("2026-01-01T08:00:00", VN)
    assert result == datetime(2026, 1, 1, 1, 0, 0)
    assert result.tzinfo is None


def test_parse_remind_at_offset_preserved():
    assert service.parse_remind_at("2026-01-01T08:00:00+00:00", VN) == datetime(2026, 1, 1, 8, 0, 0)
    assert service.parse_remind_at("2026-01-01T08:00:00Z", VN) == datetime(2026, 1, 1, 8, 0, 0)
    # offset +07:00 → giữ nguyên 08:00 khi convert sang UTC... 08:00+07:00 = 01:00 UTC
    assert service.parse_remind_at("2026-01-01T08:00:00+07:00", VN) == datetime(2026, 1, 1, 1, 0, 0)


def test_parse_remind_at_invalid_raises():
    with pytest.raises(ValueError, match="ISO 8601"):
        service.parse_remind_at("không phải ngày", VN)
    with pytest.raises(ValueError, match="ISO 8601"):
        service.parse_remind_at("", VN)


def test_format_reminder_includes_tz_and_repeat():
    reminder = SimpleNamespace(id=3, text="họp team", remind_at=datetime(2026, 1, 1, 1, 0, 0), repeat="daily")
    out = service.format_reminder(reminder, VN)
    # 01:00 UTC → 08:00 VN
    assert out == "id=3: họp team — 08:00 01/01/2026 (giờ Asia/Ho_Chi_Minh) (lặp lại)"

    once = SimpleNamespace(id=4, text="mua sữa", remind_at=datetime(2026, 1, 1, 1, 0, 0), repeat="none")
    out_once = service.format_reminder(once, VN)
    assert "(lặp lại)" not in out_once


def test_next_occurrence_none_repeat():
    now = datetime(2026, 1, 1)
    assert service.next_occurrence(datetime(2025, 12, 31), "none", now) is None


def test_next_occurrence_daily_catchup():
    now = datetime(2026, 1, 10, 12, 0, 0)
    remind_at = datetime(2026, 1, 7, 8, 0, 0)  # đã lỡ 3 lần
    result = service.next_occurrence(remind_at, "daily", now)
    assert result == datetime(2026, 1, 11, 8, 0, 0)  # lần kế tiếp sau now, cùng giờ
    assert result > now


def test_next_occurrence_weekly_catchup():
    now = datetime(2026, 1, 20)
    remind_at = datetime(2026, 1, 1, 8, 0, 0)
    result = service.next_occurrence(remind_at, "weekly", now)
    assert result == datetime(2026, 1, 22, 8, 0, 0)  # 1/1 + 3 tuần = 22/1 (14 + 7)
    assert result > now


# ═══════════════════ pure: notifier message ═══════════════════

def test_notifier_message_daily_weekly():
    reminder = SimpleNamespace(text="họp", remind_at=datetime(2026, 1, 1, 1, 0, 0), repeat="daily")
    out = notifier._message(reminder, VN)
    assert "🔔 Nhắc nhở: họp" in out
    assert "Thời gian: 08:00 01/01/2026 (giờ Asia/Ho_Chi_Minh)" in out
    assert "Lặp lại: hằng ngày" in out

    weekly = SimpleNamespace(text="họp", remind_at=datetime(2026, 1, 1, 1, 0, 0), repeat="weekly")
    assert "Lặp lại: hằng tuần" in notifier._message(weekly, VN)

    once = SimpleNamespace(text="họp", remind_at=datetime(2026, 1, 1, 1, 0, 0), repeat="none")
    assert "Lặp lại" not in notifier._message(once, VN)


# ═══════════════════ [db] service + scheduler ═══════════════════

@pytest.mark.db
def test_create_reminder_success(db_run):
    from datetime import UTC

    from app.database.repository import UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        reminder = await service.create_reminder(session, user.id, "họp sprint", future, "none")
        assert reminder.id is not None
        assert reminder.remind_at.tzinfo is None  # naive-UTC
        assert reminder.text == "họp sprint"
        assert reminder.repeat == "none"

    db_run(scenario)


@pytest.mark.db
def test_create_reminder_empty_text(db_run):
    from app.database.repository import UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        with pytest.raises(ValueError, match="rỗng"):
            await service.create_reminder(session, user.id, "   ", future)

    db_run(scenario)


@pytest.mark.db
def test_create_reminder_bad_repeat(db_run):
    from app.database.repository import UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        with pytest.raises(ValueError, match="Kiểu lặp"):
            await service.create_reminder(session, user.id, "họp", future, "yearly")

    db_run(scenario)


@pytest.mark.db
def test_create_reminder_past_time(db_run):
    from app.database.repository import UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        with pytest.raises(ValueError, match="tương lai"):
            await service.create_reminder(session, user.id, "họp", "2020-01-01T08:00:00")

    db_run(scenario)


@pytest.mark.db
def test_user_tz_invalid_falls_back(db_run):
    from app.database.repository import UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        # chưa set → mặc định VN
        assert (await service.user_tz(session, user.id)).key == "Asia/Ho_Chi_Minh"

        await UserRepository(session).set_preference(user.id, "timezone", "Not/AZone")
        assert (await service.user_tz(session, user.id)).key == "Asia/Ho_Chi_Minh"

        await UserRepository(session).set_preference(user.id, "timezone", "UTC")
        assert (await service.user_tz(session, user.id)).key == "UTC"

    db_run(scenario)


@pytest.mark.db
def test_mark_fired_none_sets_done(db_run):
    from app.database.repository import ReminderRepository, UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        reminder = await ReminderRepository(session).add(user.id, "việc", datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1))
        await service.mark_fired(session, reminder)
        assert reminder.is_done is True

    db_run(scenario)


@pytest.mark.db
def test_mark_fired_daily_rolls_forward(db_run):
    from app.database.repository import ReminderRepository, UserRepository

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        reminder = await ReminderRepository(session).add(user.id, "việc", past, "daily")
        await service.mark_fired(session, reminder)
        now = datetime.now(UTC).replace(tzinfo=None)
        assert reminder.is_done is False
        assert reminder.remind_at > now
        assert reminder.remind_at.time() == past.time()  # giữ nguyên giờ trong ngày

    db_run(scenario)


@pytest.mark.db
def test_scheduler_run_once_sends_and_marks(db_run, monkeypatch):
    from app.database.repository import ReminderRepository, UserRepository

    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler.notifier, "notify", notify)

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        due = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        reminder = await ReminderRepository(session).add(user.id, "đến hạn", due)
        user_id, reminder_id = user.id, reminder.id  # capture trước khi expire

        await scheduler.run_once()  # dùng SessionLocal nội bộ (NullPool, cùng loop)

        notify.assert_awaited_once()
        # run_once ghi bằng session khác + expire_on_commit=False → bỏ cache trước khi đọc lại
        session.expire_all()
        refreshed = await ReminderRepository(session).get(user_id, reminder_id)
        assert refreshed.is_done is True

    db_run(scenario)


@pytest.mark.db
def test_scheduler_run_once_skips_failed_send(db_run, monkeypatch):
    from app.database.repository import ReminderRepository, UserRepository

    notify = AsyncMock(return_value=False)  # gửi thất bại → tick sau thử lại
    monkeypatch.setattr(scheduler.notifier, "notify", notify)

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        due = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        reminder = await ReminderRepository(session).add(user.id, "đến hạn", due)
        user_id, reminder_id = user.id, reminder.id

        await scheduler.run_once()

        notify.assert_awaited_once()
        session.expire_all()
        refreshed = await ReminderRepository(session).get(user_id, reminder_id)
        assert refreshed.is_done is False

    db_run(scenario)
