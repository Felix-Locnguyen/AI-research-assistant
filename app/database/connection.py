from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database.models import Base


def _require_database_url() -> str:
    """T66: fail-fast khi thiếu DATABASE_URL — cùng pattern llm.py GEMINI_API_KEY."""
    if not settings.database_url:
        raise RuntimeError("Thiếu DATABASE_URL trong .env (xem .env.example)")
    return settings.database_url


engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all không ALTER bảng cũ: thêm cột mới (T52) theo cách idempotent
        await conn.execute(
            text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS repeat VARCHAR(16) NOT NULL DEFAULT 'none'")
        )


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session