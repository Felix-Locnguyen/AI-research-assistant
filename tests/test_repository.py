"""Unit test [db] cho repository CRUD + scope theo user (T61)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.database.repository import (
    ArticleRepository,
    ConversationRepository,
    MemoryRepository,
    ReminderRepository,
    UserRepository,
)

NOW = datetime.now(UTC).replace(tzinfo=None)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=1)


async def _two_users(session):
    a = await UserRepository(session).get_or_create("telegram", "ua", "user_a")
    b = await UserRepository(session).get_or_create("telegram", "ub", "user_b")
    return a, b


# ── UserRepository ───────────────────────────────────────────

@pytest.mark.db
def test_user_get_or_create_idempotent(db_run):
    async def scenario(session):
        u1 = await UserRepository(session).get_or_create("telegram", "u1", "tester")
        u2 = await UserRepository(session).get_or_create("telegram", "u1", "khác")
        assert u1.id == u2.id
        # kênh khác → row khác
        u3 = await UserRepository(session).get_or_create("zalo", "u1")
        assert u3.id != u1.id
        assert u3.channel == "zalo"

    db_run(scenario)


@pytest.mark.db
def test_user_get_returns_none_missing(db_run):
    async def scenario(session):
        assert await UserRepository(session).get(99999) is None

    db_run(scenario)


@pytest.mark.db
def test_preferences_set_and_get(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = UserRepository(session)
        await repo.set_preference(user.id, "city", "HN")
        await repo.set_preference(user.id, "lang", "vi")
        prefs = await repo.get_preferences(user.id)
        assert prefs == {"city": "HN", "lang": "vi"}

        # overwrite không tạo bản ghi trùng
        await repo.set_preference(user.id, "city", "HCM")
        prefs = await repo.get_preferences(user.id)
        assert prefs == {"city": "HCM", "lang": "vi"}

    db_run(scenario)


# ── ConversationRepository ───────────────────────────────────

@pytest.mark.db
def test_conversation_get_or_create_reuses_latest(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ConversationRepository(session)
        c1 = await repo.get_or_create(user.id)
        c2 = await repo.get_or_create(user.id)
        assert c1.id == c2.id

    db_run(scenario)


@pytest.mark.db
def test_conversation_recent_messages_order_and_limit(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ConversationRepository(session)
        conv = await repo.get_or_create(user.id)
        for i in range(5):
            await repo.add_message(conv.id, "user", f"tin {i}")

        recent = await repo.recent_messages(conv.id, limit=3)
        # thứ tự tăng dần (reversed từ desc), giới hạn 3 tin cuối
        assert [m.content for m in recent] == ["tin 2", "tin 3", "tin 4"]

        all_msgs = await repo.recent_messages(conv.id, limit=20)
        assert len(all_msgs) == 5
        assert all_msgs[0].content == "tin 0"

    db_run(scenario)


# ── MemoryRepository ─────────────────────────────────────────

@pytest.mark.db
def test_memory_add_strips_and_truncates(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        memory = await repo.add(user.id, "  " + "a" * 600)
        assert memory.content == "a" * 500

    db_run(scenario)


@pytest.mark.db
def test_memory_add_empty_raises(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        with pytest.raises(ValueError, match="rỗng"):
            await MemoryRepository(session).add(user.id, "   ")

    db_run(scenario)


@pytest.mark.db
def test_memory_add_dedupe_same_content(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        m1 = await repo.add(user.id, "thích cà phê mỗi sáng")
        m2 = await repo.add(user.id, "thích cà phê mỗi sáng")  # trùng → trả lại row cũ
        assert m1.id == m2.id

        from sqlalchemy import func, select

        from app.database.models import Memory

        count = (
            await session.execute(
                select(func.count()).select_from(Memory).where(Memory.user_id == user.id)
            )
        ).scalar_one()
        assert count == 1

    db_run(scenario)


@pytest.mark.db
def test_memory_update_missing_raises(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        with pytest.raises(ValueError, match="Không tìm thấy ký ức"):
            await MemoryRepository(session).update(user.id, 999, "nội dung mới")

    db_run(scenario)


@pytest.mark.db
def test_memory_update_sets_content_and_expiry(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        m = await repo.add(user.id, "nội dung cũ")
        updated = await repo.update(user.id, m.id, "  nội dung mới  ", FUTURE)
        assert updated.content == "nội dung mới"
        assert updated.expires_at == FUTURE

        cleared = await repo.update(user.id, m.id, "không hạn", None)
        assert cleared.expires_at is None

    db_run(scenario)


@pytest.mark.db
def test_memory_delete_true_false(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        m = await repo.add(user.id, "sẽ bị xóa")
        assert await repo.delete(user.id, m.id) is True
        assert await repo.delete(user.id, m.id) is False
        assert await repo.get(user.id, m.id) is None

    db_run(scenario)


@pytest.mark.db
def test_memory_list_active_hides_expired(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        keep_none = await repo.add(user.id, "không có hạn")
        keep_future = await repo.add(user.id, "hạn còn xa", FUTURE)
        await repo.add(user.id, "đã hết hạn", PAST)

        active = await repo.list_active(user.id)
        active_ids = [m.id for m in active]
        assert keep_none.id in active_ids
        assert keep_future.id in active_ids
        assert len(active) == 2
        # id desc (mới hơn trước)
        assert active_ids == sorted(active_ids, reverse=True)

        limited = await repo.list_active(user.id, limit=1)
        assert len(limited) == 1

    db_run(scenario)


@pytest.mark.db
def test_memory_cleanup_expired_count(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = MemoryRepository(session)
        await repo.add(user.id, "hết hạn một", PAST)
        await repo.add(user.id, "hết hạn hai", PAST)
        await repo.add(user.id, "còn sống", FUTURE)

        removed = await repo.cleanup_expired()
        assert removed == 2
        remaining = await repo.list_active(user.id)
        assert [m.content for m in remaining] == ["còn sống"]

    db_run(scenario)


# ── ArticleRepository ────────────────────────────────────────

@pytest.mark.db
def test_article_add_url_dedupe(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ArticleRepository(session)
        a1 = await repo.add(title="Bài A", url="https://ex.com/a", user_id=user.id)
        a2 = await repo.add(title="Bài A khác tiêu đề", url="https://ex.com/a", user_id=user.id)
        assert a1.id == a2.id  # T42: URL trùng → không lưu lại

    db_run(scenario)


@pytest.mark.db
def test_article_set_summary_and_recent_for_user(db_run):
    async def scenario(session):
        a, b = await _two_users(session)
        repo = ArticleRepository(session)
        art_a = await repo.add(title="Của A", url="https://ex.com/1", user_id=a.id)
        await repo.add(title="Của B", url="https://ex.com/2", user_id=b.id)
        a_id = a.id  # capture trước (không expire_all — summary đã đúng trong session này)

        await repo.set_summary(art_a.id, "tóm tắt hay")
        recent_a = await repo.recent_for_user(a_id)
        assert len(recent_a) == 1
        assert recent_a[0].summary == "tóm tắt hay"

        # set_summary với id không tồn tại → im lặng
        await repo.set_summary(99999, "x")

    db_run(scenario)


# ── ReminderRepository ───────────────────────────────────────

@pytest.mark.db
def test_reminder_add_get_update_delete(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ReminderRepository(session)
        r = await repo.add(user.id, "họp", FUTURE)
        fetched = await repo.get(user.id, r.id)
        assert fetched.text == "họp"
        assert fetched.repeat == "none"
        assert fetched.is_done is False

        updated = await repo.update(user.id, r.id, text="họp mới", repeat="daily")
        assert updated.text == "họp mới"
        assert updated.repeat == "daily"

        assert await repo.delete(user.id, r.id) is True
        assert await repo.get(user.id, r.id) is None
        assert await repo.delete(user.id, r.id) is False

        with pytest.raises(ValueError, match="Không tìm thấy lời nhắc"):
            await repo.update(user.id, 999, text="x")

    db_run(scenario)


@pytest.mark.db
def test_reminder_list_for_user_excludes_done(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ReminderRepository(session)
        later = await repo.add(user.id, "sau", FUTURE + timedelta(days=1))
        first = await repo.add(user.id, "trước", FUTURE)
        done = await repo.add(user.id, "xong rồi", FUTURE - timedelta(days=1))
        # đánh dấu done thủ công
        done.is_done = True
        await session.commit()

        items = await repo.list_for_user(user.id)
        assert [i.id for i in items] == [first.id, later.id]  # remind_at asc, ẩn done

    db_run(scenario)


@pytest.mark.db
def test_reminder_list_due_filters_by_now(db_run):
    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1")
        repo = ReminderRepository(session)
        due_past = await repo.add(user.id, "đã đến hạn", PAST)
        await repo.add(user.id, "chưa đến", FUTURE)
        done = await repo.add(user.id, "đã xong", PAST)
        done.is_done = True
        await session.commit()

        due = await repo.list_due(NOW)
        assert [d.id for d in due] == [due_past.id]

    db_run(scenario)


# ── scope theo user ──────────────────────────────────────────

@pytest.mark.db
def test_repository_scoped_by_user(db_run):
    async def scenario(session):
        a, b = await _two_users(session)
        repo = MemoryRepository(session)
        m = await repo.add(a.id, "ký ức riêng của user a")

        # user b không thấy ký ức của a
        assert await repo.get(b.id, m.id) is None
        assert await repo.list_active(b.id) == []

        # update/delete theo user b không ảnh hưởng row của a
        assert await repo.delete(b.id, m.id) is False
        with pytest.raises(ValueError, match="Không tìm thấy"):
            await repo.update(b.id, m.id, "hack")

        reminder_repo = ReminderRepository(session)
        r = await reminder_repo.add(a.id, "nhắc của a", FUTURE)
        assert await reminder_repo.get(b.id, r.id) is None
        assert await reminder_repo.list_for_user(b.id) == []
        assert await reminder_repo.delete(b.id, r.id) is False

    db_run(scenario)
