import asyncio
from unittest.mock import MagicMock

from app.channels import messenger, telegram, zalo
from app.core.queue import QueueFullError


def _run(coro):
    return asyncio.run(coro)


def test_telegram_text_update(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(telegram, "enqueue", enq)

    update = {"message": {"text": "hi", "chat": {"id": 123}, "from": {"username": "alice"}}}
    _run(telegram.process_update(update))

    enq.assert_called_once()
    incoming = enq.call_args.args[0]
    assert incoming.channel == "telegram"
    assert incoming.user_id == "123"
    assert incoming.username == "alice"
    assert incoming.text == "hi"


def test_telegram_sticker_ignored(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(telegram, "enqueue", enq)

    _run(telegram.process_update({"message": {"sticker": {}}}))
    enq.assert_not_called()


def test_zalo_user_send_text(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(zalo, "enqueue", enq)

    payload = {
        "event_name": "user_send_text",
        "app_id": "1",
        "sender": {"id": 50123, "display_name": "Nguyễn A"},
        "message": {"text": "xin chào"},
        "timestamp": 1,
    }
    _run(zalo.process_webhook(payload))

    enq.assert_called_once()
    incoming = enq.call_args.args[0]
    assert incoming.channel == "zalo"
    assert incoming.user_id == "50123"  # id số trong JSON → str
    assert incoming.username == "Nguyễn A"
    assert incoming.text == "xin chào"


def test_zalo_non_text_event_ignored(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(zalo, "enqueue", enq)

    _run(zalo.process_webhook({"event_name": "user_send_image", "sender": {"id": 1}}))
    _run(zalo.process_webhook({"event_name": "user_send_text", "sender": {"id": 1}, "message": {}}))
    enq.assert_not_called()


def test_messenger_mixed_events(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(messenger, "enqueue", enq)

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
    _run(messenger.process_webhook(payload))

    enq.assert_called_once()
    incoming = enq.call_args.args[0]
    assert incoming.channel == "messenger"
    assert incoming.user_id == "3"
    assert incoming.username is None
    assert incoming.text == "hello"


def test_messenger_empty_entry(monkeypatch):
    enq = MagicMock()
    monkeypatch.setattr(messenger, "enqueue", enq)

    _run(messenger.process_webhook({"entry": []}))
    _run(messenger.process_webhook({}))
    enq.assert_not_called()


def test_telegram_queue_full_propagates(monkeypatch):
    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr(telegram, "enqueue", _full)
    update = {"message": {"text": "hi", "chat": {"id": 1}, "from": {}}}
    try:
        _run(telegram.process_update(update))
    except QueueFullError:
        pass
    else:
        raise AssertionError("QueueFullError phải lan ra từ process_update")
