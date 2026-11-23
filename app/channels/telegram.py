import logging

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import IncomingMessage
from app.core.config import settings
from app.conversation.handler import handle_message
from app.database.connection import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"


async def send_text(chat_id: str, text: str) -> None:
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


async def process_update(update: dict, session: AsyncSession) -> None:
    message = update.get("message") or {}
    text = message.get("text")
    if not text:
        return  # bỏ qua sticker, ảnh, callback...

    chat_id = str(message["chat"]["id"])
    username = (message.get("from") or {}).get("username")
    incoming = IncomingMessage(channel="telegram", user_id=chat_id, username=username, text=text)

    reply = await handle_message(incoming, session)
    try:
        await send_text(chat_id, reply)
    except httpx.HTTPError:
        # trả 200 dù gửi lỗi để Telegram không retry làm lặp tin nhắn
        logger.exception("Failed to send reply to telegram chat %s", chat_id)


@router.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    update = await request.json()
    await process_update(update, session)
    return {"ok": True}