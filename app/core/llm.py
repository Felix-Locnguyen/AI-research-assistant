"""Kết nối tới Gemini API (Google AI Studio)."""

import asyncio
import logging

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.ratelimit import LLM_GATE

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1  # 1s, 2s, 4s
REQUEST_TIMEOUT_SECONDS = 30
TRANSIENT_CODES = {500, 502, 503, 504}  # 429 bỏ ra: quota hết thì retry chỉ tốn thêm quota

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    # lazy: app vẫn khởi động được khi chưa có API key
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("Thiếu GEMINI_API_KEY trong .env")
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
        )
    return _client


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, RuntimeError):  # lỗi cấu hình (thiếu key) thì thử lại vô ích
        return False
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code in TRANSIENT_CODES
    return True  # lỗi mạng/treo chưa phân loại: đáng thử lại


async def generate(
    system_prompt: str,
    contents: list[dict],
    tools: list[types.Tool] | None = None,
    response_schema: type | dict | None = None,
) -> types.GenerateContentResponse:
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools or [],
        response_schema=response_schema,
        response_mime_type="application/json" if response_schema else None,
    )
    for attempt in range(MAX_RETRIES):
        try:
            # Gate QUANH mỗi attempt API — KHÔNG bao quanh backoff sleep
            # (nếu bao quanh sleep, task đang retry sẽ giữ gate hàng giây và chặn cả world)
            async with LLM_GATE.acquire():
                return await _get_client().aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=config,
                )
        except Exception as exc:
            if attempt == MAX_RETRIES - 1 or not _is_transient(exc):
                raise
            wait = RETRY_BACKOFF_SECONDS * 2**attempt
            logger.warning("Gemini lỗi tạm thời (%s), thử lại sau %ss: %s", type(exc).__name__, wait, exc)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")
