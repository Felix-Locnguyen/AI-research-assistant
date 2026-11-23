import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from contextlib import asynccontextmanager

from app.channels.messenger import router as messenger_router
from app.channels.telegram import router as telegram_router
from app.channels.zalo import router as zalo_router
from app.core import queue
from app.database.connection import SessionLocal, init_db
from app.database.repository import MemoryRepository
from app.reminders import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 3600


async def _cleanup_expired() -> None:
    async with SessionLocal() as session:
        removed = await MemoryRepository(session).cleanup_expired()
        if removed:
            logger.info("Đã dọn %s ký ức hết hạn", removed)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await _cleanup_expired()
        except Exception:
            logger.exception("Lỗi khi dọn ký ức hết hạn")


@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db()          # tạo bảng khi app khởi động (T15: bỏ Alembic, dùng create_all)
    await _cleanup_expired()
    cleanup_task = asyncio.create_task(_cleanup_loop())      # T36: dọn ký ức hết hạn định kỳ
    reminder_task = asyncio.create_task(scheduler.run_loop())  # T50: quét lời nhắc đến hạn
    queue_task = asyncio.create_task(queue.worker())           # T58: worker xử lý tin nhắn nền
    try:
        yield
    finally:
        cleanup_task.cancel()
        reminder_task.cancel()
        queue_task.cancel()


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.include_router(telegram_router)
    application.include_router(zalo_router)
    application.include_router(messenger_router)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application
    

app = create_app()

#uvicorn app.main:app --reload