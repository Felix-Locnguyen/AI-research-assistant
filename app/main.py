import asyncio
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from contextlib import asynccontextmanager

from app.channels.messenger import router as messenger_router
from app.channels.telegram import router as telegram_router
from app.channels.zalo import router as zalo_router
from app.core import alert
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
DB_PROBE_TIMEOUT_SECONDS = 2
_error_count = 0  # T67/T69: số lần lỗi 500 — expose qua /health


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


async def _db_ok() -> bool:
    """T67: probe SELECT 1 trong 2s — True nếu DB phản hồi."""
    try:
        async with asyncio.timeout(DB_PROBE_TIMEOUT_SECONDS):
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


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

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        # Bỏ /health: healthcheck compose mỗi 30s → spam log
        if request.url.path == "/health":
            return await call_next(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # ServerErrorMiddleware nằm NGOÀI middleware này: unhandled exception
            # raise ra ngoài — log rồi re-raise để handler giữ nguyên hành vi.
            logger.info("%s %s -> 500 (%.1fms)", request.method, request.url.path, (time.perf_counter() - start) * 1000)
            raise
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000,
        )
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        global _error_count
        _error_count += 1
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        await alert.send_alert(f"[Nexus AI] 500 {request.method} {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @application.get("/health")
    async def health() -> JSONResponse:
        db_ok = await _db_ok()
        content = {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "queue": queue.stats(),
            "errors": _error_count,
        }
        return JSONResponse(status_code=200 if db_ok else 503, content=content)

    return application
    

app = create_app()

#uvicorn app.main:app --reload
