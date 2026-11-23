"""Kênh Zalo OA (T55).

Lưu ý: ZALO_OA_ACCESS_TOKEN hết hạn sau ~1 giờ — phải cập nhật thủ công trong .env,
không có luồng refresh token.
"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import IncomingMessage, verify_hmac_signature
from app.core.config import settings
from app.conversation.handler import handle_message
from app.database.connection import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

ZALO_API = "https://openapi.zalo.me/v3.0/oa"


async def send_text(user_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{ZALO_API}/message/cs",
            headers={"access_token": settings.zalo_oa_access_token},
            json={"recipient": {"user_id": user_id}, "message": {"text": text}},
        )
        response.raise_for_status()


async def process_webhook(payload: dict, session: AsyncSession) -> None:
    if payload.get("event_name") != "user_send_text":
        return  # bỏ qua các event khác (nhắn ảnh, follow, react...)
    message = payload.get("message") or {}
    text = message.get("text")
    if not text:
        return
    sender = payload.get("sender") or {}
    user_id = str(sender.get("id", "") or "")
    if not user_id:
        return
    username = sender.get("display_name")
    incoming = IncomingMessage(channel="zalo", user_id=user_id, username=username, text=text)

    reply = await handle_message(incoming, session)
    try:
        await send_text(user_id, reply)
    except httpx.HTTPError:
        # trả 200 dù gửi lỗi để Zalo không retry; ví dụ ngoài cửa sổ 48h CS sẽ rơi vào đây,
        # tick sau của scheduler sẽ thử lại
        logger.exception("Lỗi gửi trả lời qua Zalo cho user %s", user_id)


@router.post("/webhooks/zalo")
async def zalo_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    raw = await request.body()
    if not verify_hmac_signature(raw, request.headers.get("X-ZEvent-Signature"), settings.zalo_webhook_secret):
        raise HTTPException(status_code=403, detail="Chữ ký webhook Zalo không hợp lệ")
    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("Zalo webhook gửi body không phải JSON hợp lệ")
        return {"ok": False}
    await process_webhook(payload, session)
    return {"ok": True}
