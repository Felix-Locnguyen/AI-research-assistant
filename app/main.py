import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from contextlib import asynccontextmanager
from app.database.connection import init_db
from app.channels.telegram import router as telegram_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db()          # tạo bảng khi app khởi động (T15: bỏ Alembic, dùng create_all)
    yield


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.include_router(telegram_router)

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