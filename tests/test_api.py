"""T62 — API tests qua TestClient: /health + webhooks (KHÔNG chạy lifespan)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.core import config
from app.core import queue as job_queue
from app.core.queue import QueueFullError
from app.main import app


@pytest.fixture(autouse=True)
def _clean_queue():
    job_queue._reset_for_tests()
    yield
    job_queue._reset_for_tests()


@pytest.fixture
def client():
    # KHÔNG dùng context manager → lifespan/init_db/worker không chạy (D3)
    return TestClient(app)


@pytest.fixture
def dev_secrets(monkeypatch):
    """Ép mọi webhook secret về '' (dev mode) — deterministic kể cả khi .env có secret."""
    for attr in (
        "telegram_webhook_secret",
        "zalo_webhook_secret",
        "messenger_app_secret",
        "messenger_verify_token",
    ):
        monkeypatch.setattr(config.settings, attr, "")


def _queue_snapshot() -> list:
    items = []
    while True:
        try:
            items.append(job_queue._queue.get_nowait())
            job_queue._queue.task_done()
        except Exception:
            return items


# ── health ───────────────────────────────────────────────────

def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── telegram ─────────────────────────────────────────────────

def test_telegram_webhook_enqueues(client, dev_secrets):
    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "xin chào", "chat": {"id": 42}, "from": {"username": "alice"}}},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    items = _queue_snapshot()
    assert len(items) == 1
    assert items[0].channel == "telegram"
    assert items[0].user_id == "42"
    assert items[0].text == "xin chào"


def test_telegram_webhook_bad_secret_403(client, monkeypatch):
    monkeypatch.setattr(config.settings, "telegram_webhook_secret", "sec123")
    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "x", "chat": {"id": 1}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "sai"},
    )
    assert response.status_code == 403


def test_telegram_webhook_queue_full_503(client, dev_secrets, monkeypatch):
    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr("app.channels.telegram.enqueue", _full)
    response = client.post("/webhooks/telegram", json={"message": {"text": "x", "chat": {"id": 1}}})
    assert response.status_code == 503
    assert "Hàng đợi" in response.json()["detail"]


def test_telegram_non_text_update_200_no_enqueue(client, dev_secrets):
    response = client.post("/webhooks/telegram", json={"message": {"sticker": {}}})
    assert response.status_code == 200
    assert _queue_snapshot() == []


# ── zalo ─────────────────────────────────────────────────────

def test_zalo_webhook_enqueues(client, dev_secrets):
    payload = {
        "event_name": "user_send_text",
        "sender": {"id": 50123, "display_name": "Nguyễn A"},
        "message": {"text": "xin chào"},
    }
    response = client.post("/webhooks/zalo", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    items = _queue_snapshot()
    assert len(items) == 1
    assert items[0].channel == "zalo"
    assert items[0].user_id == "50123"  # int → str
    assert items[0].username == "Nguyễn A"


def test_zalo_webhook_bad_signature_403(client, monkeypatch):
    from tests.conftest import make_sig

    monkeypatch.setattr(config.settings, "zalo_webhook_secret", "sec")
    body = b'{"event_name":"user_send_text"}'
    response = client.post(
        "/webhooks/zalo",
        content=body,
        headers={"content-type": "application/json", "X-ZEvent-Signature": make_sig(body, "sai-sec")},
    )
    assert response.status_code == 403


def test_zalo_malformed_json_200_ok_false(client, dev_secrets):
    response = client.post(
        "/webhooks/zalo",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": False}
    assert _queue_snapshot() == []


def test_zalo_queue_full_503(client, dev_secrets, monkeypatch):
    def _full(msg):
        raise QueueFullError()

    monkeypatch.setattr("app.channels.zalo.enqueue", _full)
    payload = {"event_name": "user_send_text", "sender": {"id": 1}, "message": {"text": "x"}}
    response = client.post("/webhooks/zalo", json=payload)
    assert response.status_code == 503


# ── messenger ────────────────────────────────────────────────

def test_messenger_get_handshake_ok(client, monkeypatch):
    monkeypatch.setattr(config.settings, "messenger_verify_token", "vt123")
    response = client.get(
        "/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "vt123", "hub.challenge": "abc"},
    )
    assert response.status_code == 200
    assert response.content == b"abc"
    assert response.headers["content-type"].startswith("text/plain")


def test_messenger_get_handshake_bad_token_403(client, monkeypatch):
    monkeypatch.setattr(config.settings, "messenger_verify_token", "vt123")
    response = client.get(
        "/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "sai", "hub.challenge": "abc"},
    )
    assert response.status_code == 403


def test_messenger_get_handshake_empty_secret_403(client, dev_secrets):
    # token chưa cấu hình → strict, không dev-skip
    response = client.get(
        "/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "abc"},
    )
    assert response.status_code == 403


def test_messenger_post_enqueues(client, dev_secrets):
    payload = {"entry": [{"messaging": [{"sender": {"id": "99"}, "message": {"text": "hello"}}]}]}
    response = client.post("/webhooks/messenger", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    items = _queue_snapshot()
    assert len(items) == 1
    assert items[0].channel == "messenger"
    assert items[0].user_id == "99"
    assert items[0].username is None


def test_messenger_bad_signature_403(client, monkeypatch):
    from tests.conftest import make_sig

    monkeypatch.setattr(config.settings, "messenger_app_secret", "sec")
    body = b'{"entry":[]}'
    response = client.post(
        "/webhooks/messenger",
        content=body,
        headers={"content-type": "application/json", "X-Hub-Signature-256": make_sig(body, "sai")},
    )
    assert response.status_code == 403


def test_messenger_malformed_json_200_ok_false(client, dev_secrets):
    response = client.post(
        "/webhooks/messenger",
        content=b"broken",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": False}


def test_messenger_echo_skipped(client, dev_secrets):
    payload = {"entry": [{"messaging": [{"sender": {"id": "1"}, "message": {"is_echo": True, "text": "x"}}]}]}
    response = client.post("/webhooks/messenger", json=payload)
    assert response.status_code == 200
    assert _queue_snapshot() == []


# ── global exception handler ─────────────────────────────────

def test_unhandled_exception_returns_500(dev_secrets, monkeypatch):
    from app.channels import telegram

    monkeypatch.setattr(telegram, "process_update", AsyncMock(side_effect=RuntimeError("boom")))
    # raise_server_exceptions=False: ServerErrorMiddleware re-raise sau khi trả 500 (D4)
    c = TestClient(app, raise_server_exceptions=False)
    response = c.post("/webhooks/telegram", json={"message": {"text": "x", "chat": {"id": 1}}})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
