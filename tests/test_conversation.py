"""Unit test cho conversation: context_builder, tools.execute, handler._reply/handle_message (T61)."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.conversation import context_builder, handler, tools
from app.memory import manager as memory_manager

# ═══════════════════ pure: context_builder ═══════════════════

def test_build_contents_role_mapping():
    history = [
        SimpleNamespace(role="user", content="xin chào"),
        SimpleNamespace(role="assistant", content="chào bạn"),
    ]
    out = context_builder.build_contents(history, "tiếp theo")
    assert out == [
        {"role": "user", "parts": [{"text": "xin chào"}]},
        {"role": "model", "parts": [{"text": "chào bạn"}]},
        {"role": "user", "parts": [{"text": "tiếp theo"}]},
    ]


def test_build_contents_empty_history():
    out = context_builder.build_contents([], "chỉ câu mới")
    assert out == [{"role": "user", "parts": [{"text": "chỉ câu mới"}]}]


def test_load_system_prompt_appends_context():
    base = context_builder.PROMPT_FILE.read_text(encoding="utf-8")
    assert context_builder.load_system_prompt({}, None) == base

    with_ctx = context_builder.load_system_prompt({"city": "HN"}, None)
    assert with_ctx.startswith(base)
    assert "## Sở thích người dùng đã lưu" in with_ctx
    assert "- city: HN" in with_ctx


# ═══════════════════ pure: tools helpers ═══════════════════

def test_expires_at_from_days_none():
    assert tools._expires_at_from_days(None) is None


def test_expires_at_from_days_positive():
    result = tools._expires_at_from_days(7)
    expected_min = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7, minutes=-2)
    expected_max = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7, minutes=2)
    assert result is not None
    assert expected_min <= result <= expected_max
    assert result.tzinfo is None  # naive-UTC theo convention


# ═══════════════════ pure: tools.execute ═══════════════════

def _call(name: str, **args):
    return SimpleNamespace(name=name, args=args)


def test_execute_unknown_tool():
    out = asyncio.run(tools.execute(_call("nope"), 1, MagicMock()))
    assert out == "Không tồn tại tool: nope"


def test_execute_save_user_preference(monkeypatch):
    set_pref = AsyncMock()
    monkeypatch.setattr(tools.UserRepository, "set_preference", set_pref)
    out = asyncio.run(
        tools.execute(_call("save_user_preference", key="city", value="HN"), 1, MagicMock())
    )
    assert out == "Đã lưu vào hồ sơ người dùng."
    set_pref.assert_awaited_once_with(1, "city", "HN")


def test_execute_save_memory_success(monkeypatch):
    save = AsyncMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(tools.MemoryManager, "save", save)
    out = asyncio.run(
        tools.execute(_call("save_memory", content="thích cà phê"), 1, MagicMock())
    )
    assert out == "Đã ghi nhớ (id=7)."


def test_execute_list_memories_empty(monkeypatch):
    monkeypatch.setattr(tools.MemoryManager, "list", AsyncMock(return_value=[]))
    out = asyncio.run(tools.execute(_call("list_memories"), 1, MagicMock()))
    assert out == "Chưa có ký ức nào được lưu."


def test_execute_list_memories_formats(monkeypatch):
    memories = [
        SimpleNamespace(id=1, content="thích cà phê", expires_at=None),
        SimpleNamespace(id=2, content="họp team", expires_at=datetime(2030, 1, 1)),
    ]
    monkeypatch.setattr(tools.MemoryManager, "list", AsyncMock(return_value=memories))
    out = asyncio.run(tools.execute(_call("list_memories"), 1, MagicMock()))
    assert "- id=1: thích cà phê" in out
    assert "- id=2: họp team" in out
    assert "hết hạn 2030-01-01" in out


def test_execute_update_memory_not_found(monkeypatch):
    monkeypatch.setattr(
        tools.MemoryManager, "update",
        AsyncMock(side_effect=ValueError("Không tìm thấy ký ức id=5.")),
    )
    out = asyncio.run(tools.execute(_call("update_memory", memory_id=5, content="mới"), 1, MagicMock()))
    assert out == "Không tìm thấy ký ức id=5."


def test_execute_delete_memory_bool(monkeypatch):
    monkeypatch.setattr(tools.MemoryManager, "delete", AsyncMock(return_value=True))
    assert asyncio.run(tools.execute(_call("delete_memory", memory_id=3), 1, MagicMock())) == "Đã xóa ký ức id=3."
    monkeypatch.setattr(tools.MemoryManager, "delete", AsyncMock(return_value=False))
    assert asyncio.run(tools.execute(_call("delete_memory", memory_id=9), 1, MagicMock())) == "Không tìm thấy ký ức id=9."


def test_execute_create_reminder_value_error(monkeypatch):
    monkeypatch.setattr(
        tools.reminder_service, "create_reminder",
        AsyncMock(side_effect=ValueError("Thời gian nhắc phải ở tương lai")),
    )
    out = asyncio.run(
        tools.execute(_call("create_reminder", text="họp", remind_at="2020-01-01T08:00:00"), 1, MagicMock())
    )
    assert out == "Thời gian nhắc phải ở tương lai"


def test_execute_list_reminders_empty(monkeypatch):
    monkeypatch.setattr(tools.reminder_service, "list_reminders", AsyncMock(return_value=[]))
    out = asyncio.run(tools.execute(_call("list_reminders"), 1, MagicMock()))
    assert out == "Chưa có lời nhắc nào."


def test_execute_research_returns_formatted(monkeypatch):
    outcome = SimpleNamespace(formatted="## Kết quả nghiên cứu\n\nok", articles=[])
    monkeypatch.setattr(tools, "run_research", AsyncMock(return_value=outcome))
    monkeypatch.setattr(tools.UserRepository, "get_preferences", AsyncMock(return_value={}))
    out = asyncio.run(tools.execute(_call("research", topic="python"), 1, MagicMock()))
    assert out.startswith("## Kết quả nghiên cứu")


# ═══════════════════ pure: handler._reply ═══════════════════

def _gen_response(function_calls=None, text=None, content=None):
    resp = MagicMock()
    resp.function_calls = function_calls or []
    resp.text = text
    resp.candidates = [MagicMock(content=content or MagicMock())]
    return resp


def test_reply_plain_text_no_tools(monkeypatch):
    resp = _gen_response(text="trả lời cuối")
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(return_value=resp))
    out = asyncio.run(handler._reply("sys", [{"role": "user", "parts": [{"text": "hi"}]}], 1, MagicMock()))
    assert out == "trả lời cuối"


def test_reply_tool_loop_then_text(monkeypatch):
    call = SimpleNamespace(name="save_user_preference", args={"key": "city", "value": "HN"})
    resp1 = _gen_response(function_calls=[call])
    resp2 = _gen_response(text="Đã lưu city.")
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(side_effect=[resp1, resp2]))
    exec_mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(handler.tools, "execute", exec_mock)

    out = asyncio.run(handler._reply("sys", [{"role": "user", "parts": [{"text": "hi"}]}], 1, MagicMock()))
    assert out == "Đã lưu city."
    exec_mock.assert_awaited_once()


def test_reply_max_rounds_fallback(monkeypatch):
    call = SimpleNamespace(name="list_memories", args={})
    always_call = _gen_response(function_calls=[call])
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(return_value=always_call))
    monkeypatch.setattr(handler.tools, "execute", AsyncMock(return_value="danh sách"))

    out = asyncio.run(handler._reply("sys", [{"role": "user", "parts": [{"text": "hi"}]}], 1, MagicMock()))
    assert out == "Xin lỗi, mình chưa xử lý được yêu cầu lần này."


# ═══════════════════ [db] handle_message ═══════════════════

@pytest.mark.db
def test_handle_message_persists_and_replies(db_run, monkeypatch):
    resp = _gen_response(text="Xin chào!")
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(return_value=resp))
    spawn = MagicMock()
    monkeypatch.setattr(handler.extractor, "spawn", spawn)

    async def scenario(session):
        from sqlalchemy import select

        from app.database.models import Message, User

        message = SimpleNamespace(channel="telegram", user_id="u1", username="tester", text="xin chào bạn")
        reply = await handler.handle_message(message, session)
        assert reply == "Xin chào!"

        user = (
            await session.execute(select(User).where(User.channel == "telegram", User.channel_user_id == "u1"))
        ).scalar_one()
        assert user is not None
        messages = (await session.execute(select(Message).order_by(Message.id))).scalars().all()
        assert [m.role for m in messages] == ["user", "assistant"]
        assert [m.content for m in messages] == ["xin chào bạn", "Xin chào!"]
        spawn.assert_called_once()

    db_run(scenario)


@pytest.mark.db
def test_handle_message_tool_round(db_run, monkeypatch):
    call = SimpleNamespace(name="save_user_preference", args={"key": "city", "value": "HN"})
    resp1 = _gen_response(function_calls=[call])
    resp2 = _gen_response(text="Đã lưu.")
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(side_effect=[resp1, resp2]))
    monkeypatch.setattr(handler.extractor, "spawn", MagicMock())

    async def scenario(session):
        from sqlalchemy import select

        from app.database.models import User
        from app.database.repository import UserRepository

        message = SimpleNamespace(channel="telegram", user_id="u1", username=None, text="tôi sống ở hà nội")
        reply = await handler.handle_message(message, session)
        assert reply == "Đã lưu."

        user = (
            await session.execute(select(User).where(User.channel == "telegram", User.channel_user_id == "u1"))
        ).scalar_one()
        prefs = await UserRepository(session).get_preferences(user.id)
        assert prefs.get("city") == "HN"

    db_run(scenario)


@pytest.mark.db
def test_handle_message_uses_preferences_in_prompt(db_run, monkeypatch):
    from app.database.repository import UserRepository

    captured: dict = {}

    def fake_load_system_prompt(preferences, memories=None):
        captured.update(preferences)
        return "sys"

    monkeypatch.setattr(handler, "load_system_prompt", fake_load_system_prompt)
    resp = _gen_response(text="ok")
    monkeypatch.setattr(handler.llm, "generate", AsyncMock(return_value=resp))
    monkeypatch.setattr(handler.extractor, "spawn", MagicMock())

    async def scenario(session):
        user = await UserRepository(session).get_or_create("telegram", "u1", "tester")
        await UserRepository(session).set_preference(user.id, "city", "Hà Nội")

        message = SimpleNamespace(channel="telegram", user_id="u1", username=None, text="hôm nay thế nào")
        await handler.handle_message(message, session)
        assert captured.get("city") == "Hà Nội"

    db_run(scenario)
