"""Chạy local thay cho webhook: .venv/bin/python -m scripts.telegram_poll"""

import asyncio

import httpx

from app.channels.telegram import TELEGRAM_API, process_update
from app.core.config import settings
from app.database.connection import SessionLocal

async def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    offset = 0
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(
                f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/getUpdates",
                params={"offset": offset, "timeout": 30},
            )
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = update["update_id"] + 1
                async with SessionLocal() as session:
                    await process_update(update, session)
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())