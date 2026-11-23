import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.channels.base import IncomingMessage, verify_secret_token
from app.core.config import settings
from app.core.queue import QueueFullError, enqueue

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"


async def send_text(chat_id: str, text: str) -> None:
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


async def process_update(update: dict) -> None:
    message = update.get("message") or {}
    text = message.get("text")
    if not text:
        return  # bỏ qua sticker, ảnh, callback...

    chat_id = str(message["chat"]["id"])
    username = (message.get("from") or {}).get("username")
    incoming = IncomingMessage(channel="telegram", user_id=chat_id, username=username, text=text)
    enqueue(incoming)  # T58: worker sẽ handle + gửi reply


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    if not verify_secret_token(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token"),
        settings.telegram_webhook_secret,
    ):
        raise HTTPException(status_code=403, detail="Secret token webhook không hợp lệ")
    update = await request.json()
    try:
        await process_update(update)
    except QueueFullError:
        raise HTTPException(status_code=503, detail="Hàng đợi tin nhắn đầy, thử lại sau")
    return {"ok": True}
