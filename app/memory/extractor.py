"""Trích xuất ký ức tự động sau mỗi lượt trò chuyện (T32).

Chạy nền (fire-and-forget) để không tăng độ trễ phản hồi: gọi Gemini đọc
lượt trao đổi vừa kết thúc rồi lưu qua MemoryManager.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core import llm
from app.database.connection import SessionLocal
from app.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "memory-extractor.md"
MIN_TEXT_LENGTH = 15

RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "expires_in_days": {"type": "integer"},
        },
        "required": ["content"],
    },
}


def _load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def should_extract(user_text: str) -> bool:
    text = (user_text or "").strip()
    return len(text) >= MIN_TEXT_LENGTH and not text.startswith("/")


async def extract(user_id: int, user_text: str, assistant_text: str) -> None:
    """Phân tích lượt trao đổi và lưu các ký ức mới (bỏ qua nếu không có gì đáng nhớ)."""
    if not should_extract(user_text):
        return

    contents = [
        {
            "role": "user",
            "parts": [{"text": f"Người dùng: {user_text}\n\nTrợ lý: {assistant_text}"}],
        }
    ]
    response = await llm.generate(_load_prompt(), contents, response_schema=RESPONSE_SCHEMA)
    try:
        items = json.loads(response.text or "[]")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Extractor trả về JSON không hợp lệ: %r", response.text)
        return
    if not items:
        return

    async with SessionLocal() as session:
        manager = MemoryManager(session)
        for item in items:
            content = item.get("content", "")
            days = item.get("expires_in_days")
            expires_at = (
                datetime.now(UTC).replace(tzinfo=None) + timedelta(days=int(days))
                if days is not None
                else None
            )
            try:
                await manager.save(user_id, content, expires_at)
            except ValueError as exc:
                logger.info("Bỏ qua ký ức không hợp lệ: %s", exc)


_pending_tasks: set[asyncio.Task] = set()


def spawn(user_id: int, user_text: str, assistant_text: str) -> None:
    """Khởi chạy extraction nền, không chờ kết quả."""
    task = asyncio.create_task(_run(user_id, user_text, assistant_text))
    _pending_tasks.add(task)  # giữ tham chiếu để task không bị GC giữa chừng
    task.add_done_callback(_on_task_done)


async def _run(user_id: int, user_text: str, assistant_text: str) -> None:
    try:
        await extract(user_id, user_text, assistant_text)
    except Exception:
        logger.exception("Lỗi khi trích xuất ký ức cho user %s", user_id)


def _on_task_done(task: asyncio.Task) -> None:
    _pending_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Task trích xuất ký ức kết thúc với lỗi: %s", exc)
