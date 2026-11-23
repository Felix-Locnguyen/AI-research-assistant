import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.channels import messenger, telegram, zalo


def _run(coro):
    return asyncio.run(coro)


def test_telegram_text_update(monkeypatch):
    handle = AsyncMock(return_value="đã nhận")
    send = AsyncMock()
    monkeypatch.setattr(telegram, "handle_message", handle)
    monkeypatch.setattr(telegram, "send_text", send)

    update = {"message": {"text": "hi", "chat": {"id": 123}, "from": {"username": "alice"}}}
    _run(telegram.process_update(update, MagicMock()))

    handle.assert_awaited_once()
    incoming = handle.await_args.args[0]
    assert incoming.channel == "telegram"
    assert incoming.user_id == "123"
    assert incoming.username == "alice"
    assert incoming.text == "hi"
    send.assert_awaited_once_with("123", "đã nhận")


def test_telegram_sticker_ignored(monkeypatch):
    handle = AsyncMock(return_value="x")
    monkeypatch.setattr(telegram, "handle_message", handle)

    _run(telegram.process_update({"message": {"sticker": {}}}, MagicMock()))
    handle.assert_not_awaited()


def test_zalo_user_send_text(monkeypatch):
    handle = AsyncMock(return_value="xin chào bạn")
    send = AsyncMock()
    monkeypatch.setattr(zalo, "handle_message", handle)
    monkeypatch.setattr(zalo, "send_text", send)

    payload = {
        "event_name": "user_send_text",
        "app_id": "1",
        "sender": {"id": 50123, "display_name": "Nguyễn A"},
        "message": {"text": "xin chào"},
        "timestamp": 1,
    }
    _run(zalo.process_webhook(payload, MagicMock()))

    handle.assert_awaited_once()
    incoming = handle.await_args.args[0]
    assert incoming.channel == "zalo"
    assert incoming.user_id == "50123"  # id số trong JSON → str
    assert incoming.username == "Nguyễn A"
    assert incoming.text == "xin chào"
    send.assert_awaited_once_with("50123", "xin chào bạn")


def test_zalo_non_text_event_ignored(monkeypatch):
    handle = AsyncMock(return_value="x")
    monkeypatch.setattr(zalo, "handle_message", handle)

    _run(zalo.process_webhook({"event_name": "user_send_image", "sender": {"id": 1}}, MagicMock()))
    _run(zalo.process_webhook({"event_name": "user_send_text", "sender": {"id": 1}, "message": {}}, MagicMock()))
    handle.assert_not_awaited()


def test_messenger_mixed_events(monkeypatch):
    handle = AsyncMock(return_value="trả lời")
    send = AsyncMock()
    monkeypatch.setattr(messenger, "handle_message", handle)
    monkeypatch.setattr(messenger, "send_text", send)

    payload = {
        "entry": [
            {
                "messaging": [
                    {"sender": {"id": "1"}, "message": {"is_echo": True, "text": "echo"}},
                    {"sender": {"id": "2"}, "message": {"attachments": [{"type": "image"}]}},
                    {"sender": {"id": "3"}, "message": {"text": "hello"}},
                ]
            }
        ]
    }
    _run(messenger.process_webhook(payload, MagicMock()))

    handle.assert_awaited_once()
    incoming = handle.await_args.args[0]
    assert incoming.channel == "messenger"
    assert incoming.user_id == "3"
    assert incoming.username is None
    assert incoming.text == "hello"
    send.assert_awaited_once_with("3", "trả lời")


def test_messenger_empty_entry(monkeypatch):
    handle = AsyncMock(return_value="x")
    monkeypatch.setattr(messenger, "handle_message", handle)

    _run(messenger.process_webhook({"entry": []}, MagicMock()))
    _run(messenger.process_webhook({}, MagicMock()))
    handle.assert_not_awaited()
