"""T63 — Integration: webhook → queue → worker → reply + shape HTTP outbound (mock cả 3 kênh)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.channels import messenger, telegram, zalo
from app.core import config
from app.core import queue as job_queue
from app.main import app


@pytest.fixture(autouse=True)
def _clean_queue():
    job_queue._reset_for_tests()
    yield
    job_queue._reset_for_tests()


@pytest.fixture
def client():
    return TestClient(app)  # no lifespan


@pytest.fixture
def dev_secrets(monkeypatch):
    for attr in ("telegram_webhook_secret", "zalo_webhook_secret",
                 "messenger_app_secret", "messenger_verify_token"):
        monkeypatch.setattr(config.settings, attr, "")


def _run_worker_until_idle():
    async def scenario():
        task = asyncio.create_task(job_queue.worker())
        try:
            await asyncio.wait_for(job_queue._queue.join(), timeout=2)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return asyncio.run(scenario())


def _patch_httpx_client(monkeypatch, handler):
    """Thay httpx.AsyncClient bằng factory gắn MockTransport — trả client THẬT."""
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# ═══════════════════ A. Inbound E2E ═══════════════════

def _prepare_reply_mocks(monkeypatch, reply: str):
    handle = AsyncMock(return_value=reply)
    send = AsyncMock()
    monkeypatch.setattr(job_queue, "handle_message", handle)
    monkeypatch.setattr(job_queue, "send_text", send)
    return handle, send


def test_telegram_webhook_to_send_text(client, dev_secrets, monkeypatch):
    handle, send = _prepare_reply_mocks(monkeypatch, "Xin chào")

    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "hi", "chat": {"id": 42}, "from": {"username": "a"}}},
    )
    assert response.status_code == 200
    assert job_queue._queue.qsize() == 1

    _run_worker_until_idle()

    handle.assert_awaited_once()
    incoming = handle.await_args.args[0]
    assert (incoming.channel, incoming.user_id, incoming.text) == ("telegram", "42", "hi")
    send.assert_awaited_once_with("telegram", "42", "Xin chào")


def test_zalo_webhook_to_send_text(client, dev_secrets, monkeypatch):
    handle, send = _prepare_reply_mocks(monkeypatch, "Chào bạn")

    payload = {
        "event_name": "user_send_text",
        "sender": {"id": 50123, "display_name": "A"},
        "message": {"text": "xin chào"},
    }
    response = client.post("/webhooks/zalo", json=payload)
    assert response.status_code == 200

    _run_worker_until_idle()

    incoming = handle.await_args.args[0]
    assert (incoming.channel, incoming.user_id) == ("zalo", "50123")
    send.assert_awaited_once_with("zalo", "50123", "Chào bạn")


def test_messenger_webhook_to_send_text(client, dev_secrets, monkeypatch):
    handle, send = _prepare_reply_mocks(monkeypatch, "OK")

    payload = {"entry": [{"messaging": [{"sender": {"id": "77"}, "message": {"text": "hello"}}]}]}
    response = client.post("/webhooks/messenger", json=payload)
    assert response.status_code == 200

    _run_worker_until_idle()

    incoming = handle.await_args.args[0]
    assert (incoming.channel, incoming.user_id, incoming.username) == ("messenger", "77", None)
    send.assert_awaited_once_with("messenger", "77", "OK")


# ═══════════════════ B. Outbound HTTP shape ═══════════════════

def test_telegram_send_text_request_shape(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(config.settings, "telegram_bot_token", "TOK")
    _patch_httpx_client(monkeypatch, handler)

    asyncio.run(telegram.send_text("99", "xin"))

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.telegram.org/botTOK/sendMessage"
    assert captured["json"] == {"chat_id": "99", "text": "xin"}


def test_telegram_send_text_raises_on_http_error(monkeypatch):
    _patch_httpx_client(monkeypatch, lambda request: httpx.Response(500, json={"ok": False}))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(telegram.send_text("99", "xin"))


def test_zalo_send_text_request_shape(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"error": 0})

    monkeypatch.setattr(config.settings, "zalo_oa_access_token", "ZTOKEN")
    _patch_httpx_client(monkeypatch, handler)

    asyncio.run(zalo.send_text("50123", "nhắc bạn"))

    assert captured["url"] == "https://openapi.zalo.me/v3.0/oa/message/cs"
    assert captured["headers"]["access_token"] == "ZTOKEN"
    assert captured["json"] == {
        "recipient": {"user_id": "50123"},
        "message": {"text": "nhắc bạn"},
    }


def test_messenger_send_text_response_mode(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message_id": "m1"})

    monkeypatch.setattr(config.settings, "messenger_page_access_token", "PTOKEN")
    _patch_httpx_client(monkeypatch, handler)

    asyncio.run(messenger.send_text("77", "trả lời"))

    assert captured["url"] == "https://graph.facebook.com/v19.0/me/messages?access_token=PTOKEN"
    body = captured["json"]
    assert body["messaging_type"] == "RESPONSE"
    assert "tag" not in body
    assert body["recipient"] == {"id": "77"}
    assert body["message"] == {"text": "trả lời"}


def test_messenger_send_text_message_tag_proactive(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message_id": "m1"})

    monkeypatch.setattr(config.settings, "messenger_page_access_token", "PTOKEN")
    monkeypatch.setattr(config.settings, "messenger_tag", "ACCOUNT_UPDATE")
    _patch_httpx_client(monkeypatch, handler)

    asyncio.run(messenger.send_text("77", "lời nhắc", proactive=True))

    body = captured["json"]
    assert body["messaging_type"] == "MESSAGE_TAG"
    assert body["tag"] == "ACCOUNT_UPDATE"
