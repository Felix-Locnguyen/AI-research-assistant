import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.channels import base, messenger, zalo
from app.core import config
from tests.conftest import FakeRequest


def test_dispatcher_telegram(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.channels.telegram.send_text", send)
    asyncio.run(base.send_text("telegram", "u", "x"))
    send.assert_awaited_once_with("u", "x")


def test_dispatcher_zalo(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.channels.zalo.send_text", send)
    asyncio.run(base.send_text("zalo", "u", "x"))
    send.assert_awaited_once_with("u", "x")


def test_dispatcher_messenger_proactive(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.channels.messenger.send_text", send)
    asyncio.run(base.send_text("messenger", "u", "x", proactive=True))
    send.assert_awaited_once_with("u", "x", proactive=True)


def test_dispatcher_unknown_channel():
    with pytest.raises(ValueError, match="Kênh không hỗ trợ"):
        asyncio.run(base.send_text("kakao", "u", "x"))


def test_notifier_uses_dispatcher(monkeypatch):
    """T54 acceptance: notifier gọi dispatcher với kênh của user + proactive=True."""
    from app.reminders import notifier, service
    from app.database import repository

    user = SimpleNamespace(channel="zalo", channel_user_id="u1")
    get = AsyncMock(return_value=user)
    monkeypatch.setattr(repository.UserRepository, "get", get)
    monkeypatch.setattr(service, "user_tz", AsyncMock(return_value=ZoneInfo("Asia/Ho_Chi_Minh")))
    send = AsyncMock()
    monkeypatch.setattr(notifier, "send_text", send)

    reminder = SimpleNamespace(text="họp", remind_at=datetime(2030, 1, 1, 8, 0), repeat="none")
    ok = asyncio.run(notifier.notify(MagicMock(), 1, reminder))

    assert ok is True
    send.assert_awaited_once()
    args, kwargs = send.await_args
    assert args[0] == "zalo"
    assert args[1] == "u1"
    assert kwargs.get("proactive") is True
    assert "họp" in args[2]


def test_zalo_webhook_bad_signature(monkeypatch):
    monkeypatch.setattr(config.settings, "zalo_webhook_secret", "sec")
    body = b'{"event_name":"user_send_text"}'
    req = FakeRequest(body, {"X-ZEvent-Signature": "sha256=" + "0" * 64})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zalo.zalo_webhook(req))
    assert exc.value.status_code == 403


def test_zalo_webhook_queue_full_503(monkeypatch):
    from app.core.queue import QueueFullError

    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr(zalo, "enqueue", _full)
    monkeypatch.setattr(config.settings, "zalo_webhook_secret", "")  # dev mode: bỏ qua chữ ký
    body = b'{"event_name":"user_send_text","sender":{"id":"1"},"message":{"text":"x"}}'
    req = FakeRequest(body, {})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(zalo.zalo_webhook(req))
    assert exc.value.status_code == 503


def test_telegram_webhook_queue_full_503(monkeypatch):
    from app.channels import telegram
    from app.core.queue import QueueFullError

    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr(telegram, "enqueue", _full)
    monkeypatch.setattr(config.settings, "telegram_webhook_secret", "")  # dev mode
    body = b'{"message":{"text":"hi","chat":{"id":1}}}'
    req = FakeRequest(body, {})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(telegram.telegram_webhook(req))
    assert exc.value.status_code == 503


def test_messenger_webhook_queue_full_503(monkeypatch):
    from app.core.queue import QueueFullError

    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr(messenger, "enqueue", _full)
    monkeypatch.setattr(config.settings, "messenger_app_secret", "")  # dev mode
    body = b'{"entry":[{"messaging":[{"sender":{"id":"1"},"message":{"text":"x"}}]}]}'
    req = FakeRequest(body, {})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(messenger.messenger_webhook(req))
    assert exc.value.status_code == 503


def test_messenger_verify_handshake(monkeypatch):
    monkeypatch.setattr(config.settings, "messenger_verify_token", "vt123")
    ok = asyncio.run(
        messenger.messenger_verify(hub_mode="subscribe", hub_verify_token="vt123", hub_challenge="abc123")
    )
    assert ok.body == b"abc123"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            messenger.messenger_verify(hub_mode="subscribe", hub_verify_token="sai", hub_challenge="abc123")
        )
    assert exc.value.status_code == 403
