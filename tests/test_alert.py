"""T69 — ALERT_WEBHOOK_URL: tắt / gửi / nuốt lỗi."""

import asyncio
import json
from unittest.mock import MagicMock

from app.core import alert
from app.core.config import settings


def test_send_alert_disabled_noop(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "")

    def _fail(*a, **k):
        raise AssertionError("Không được gọi urlopen khi alert tắt")

    monkeypatch.setattr(alert.urllib.request, "urlopen", _fail)
    asyncio.run(alert.send_alert("test"))  # không raise


def test_send_alert_posts_json(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "http://example.invalid/hook")
    captured: dict = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["method"] = req.get_method()
        return MagicMock(status=200)

    monkeypatch.setattr(alert.urllib.request, "urlopen", _fake_urlopen)
    asyncio.run(alert.send_alert("xin chào"))
    assert captured["url"] == "http://example.invalid/hook"
    assert captured["body"] == {"text": "xin chào"}
    assert captured["method"] == "POST"


def test_send_alert_swallows_errors(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "http://example.invalid/hook")

    def _raise(*a, **k):
        raise OSError("mạng lỗi")

    monkeypatch.setattr(alert.urllib.request, "urlopen", _raise)
    asyncio.run(alert.send_alert("test"))  # không raise
