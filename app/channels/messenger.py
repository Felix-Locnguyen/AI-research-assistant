"""Kênh Facebook Messenger (T56). Gửi chủ động (lời nhắc) dùng MESSAGE_TAG ngoài cửa sổ 24h."""

import hmac
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.channels.base import IncomingMessage, verify_hmac_signature
from app.core.config import settings
from app.core.queue import QueueFullError, enqueue

logger = logging.getLogger(__name__)
router = APIRouter()

GRAPH_API = "https://graph.facebook.com/v19.0"


async def send_text(user_id: str, text: str, proactive: bool = False) -> None:
    # RESPONSE cho trả lời trong cửa sổ 24h; MESSAGE_TAG cho gửi chủ động (lời nhắc)
    body: dict = {
        "recipient": {"id": user_id},
        "messaging_type": "MESSAGE_TAG" if proactive else "RESPONSE",
        "message": {"text": text},
    }
    if proactive:
        body["tag"] = settings.messenger_tag
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{GRAPH_API}/me/messages",
            params={"access_token": settings.messenger_page_access_token},
            json=body,
        )
        response.raise_for_status()


async def process_webhook(payload: dict) -> None:
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            if message.get("is_echo") or not message.get("text"):
                continue  # bỏ qua echo (tin của chính page) và tin không phải text
            user_id = str((event.get("sender") or {}).get("id", "") or "")
            if not user_id:
                continue
            incoming = IncomingMessage(channel="messenger", user_id=user_id, username=None, text=message["text"])
            enqueue(incoming)  # T58: worker sẽ handle + gửi reply


@router.get("/webhooks/messenger")
async def messenger_verify(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    if (
        hub_mode == "subscribe"
        and settings.messenger_verify_token
        and hub_verify_token
        and hub_challenge is not None
        and hmac.compare_digest(hub_verify_token, settings.messenger_verify_token)
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Xác minh webhook Messenger thất bại")


@router.post("/webhooks/messenger")
async def messenger_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    if not verify_hmac_signature(raw, request.headers.get("X-Hub-Signature-256"), settings.messenger_app_secret):
        raise HTTPException(status_code=403, detail="Chữ ký webhook Messenger không hợp lệ")
    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("Messenger webhook gửi body không phải JSON hợp lệ")
        return {"ok": False}
    try:
        await process_webhook(payload)
    except QueueFullError:
        raise HTTPException(status_code=503, detail="Hàng đợi tin nhắn đầy, thử lại sau")
    return {"ok": True}
