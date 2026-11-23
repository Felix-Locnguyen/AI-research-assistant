"""Chạy local thay cho webhook: .venv/bin/python -m scripts.telegram_poll"""

import asyncio
import logging

import httpx

from app.channels.telegram import TELEGRAM_API, process_update
from app.core.config import settings
from app.core.queue import QueueFullError, worker

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    # Poll chạy KHÔNG qua lifespan FastAPI → phải tự spawn worker (T58)
    queue_task = asyncio.create_task(worker())
    offset = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                response = await client.get(
                    f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        await process_update(update)
                    except QueueFullError:
                        # hàng đợi đầy: bỏ update này (đã offset rồi — không redeliver local)
                        logger.warning("Hàng đợi đầy, bỏ update_id=%s", update.get("update_id"))
                await asyncio.sleep(1)
    finally:
        queue_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
