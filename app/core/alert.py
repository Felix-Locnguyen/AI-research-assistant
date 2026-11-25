"""Gửi cảnh báo vận hành tới ALERT_WEBHOOK_URL (T69) — fire-and-forget, không chặn request."""

import asyncio
import json
import logging
import urllib.request

from app.core.config import settings

logger = logging.getLogger(__name__)

ALERT_TIMEOUT_SECONDS = 5


async def send_alert(message: str) -> None:
    """POST JSON {"text": message} nếu đã cấu hình ALERT_WEBHOOK_URL; lỗi → nuốt + log warning."""
    if not settings.alert_webhook_url:
        return

    def _post() -> None:
        req = urllib.request.Request(
            settings.alert_webhook_url,
            data=json.dumps({"text": message}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=ALERT_TIMEOUT_SECONDS)
        except Exception:
            logger.warning("Gửi alert thất bại")

    try:
        await asyncio.to_thread(_post)
    except Exception:
        logger.warning("Gửi alert thất bại")
