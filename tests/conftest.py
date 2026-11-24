import hashlib
import hmac
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

# ─────────────────────────────────────────────────────────────
# FORCE test database BEFORE any `app.*` import (engine binds at import).
# LUÔN luôn đổi tên DB sang nexus_ai_test — không bao giờ đụng nexus_ai dev.
# Credentials: TEST_DATABASE_URL env → DATABASE_URL env → .env → default.
# ─────────────────────────────────────────────────────────────
def _force_test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        os.environ["DATABASE_URL"] = explicit
        return explicit

    source = os.environ.get("DATABASE_URL", "")
    if not source:
        env_file = Path(__file__).resolve().parents[1] / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    source = line.split("=", 1)[1].strip()
                    break
    if not source:
        source = "postgresql+asyncpg://postgres:postgres@localhost:5432/nexus_ai"

    # Chỉ thay segment database cuối → nexus_ai_test (giữ user/pass/host/port)
    base, _, _db = source.rpartition("/")
    os.environ["DATABASE_URL"] = f"{base}/nexus_ai_test"
    return os.environ["DATABASE_URL"]


TEST_DATABASE_URL = _force_test_database_url()

# ── Imports app SAU khi env đã set ──
import asyncio  # noqa: E402
import asyncpg  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.database import connection  # noqa: E402

# Safety: KHÔNG BAO GIỜ đụng DB dev
assert connection.engine.url.database == "nexus_ai_test", f"Sai DB test: {connection.engine.url.database}"

# NullPool: mỗi checkout tạo kết nối MỚI trong loop hiện tại rồi đóng ngay —
# an toàn với mô hình asyncio.run() khác loop từng test (pool mặc định sẽ
# "attached to a different loop"). Đổi tại đây TRƯỚC khi mọi module app
# (queue/scheduler/extractor/main) import SessionLocal từ connection.
_TEST_ENGINE = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
_TEST_SESSION = async_sessionmaker(_TEST_ENGINE, expire_on_commit=False)
connection.engine = _TEST_ENGINE        # init_db()/get_session() lookup global lúc gọi
connection.SessionLocal = _TEST_SESSION  # các module import SAU conftest sẽ lấy bản này


class FakeRequest:
    """Request giả để gọi thẳng endpoint webhook (không cần TestClient/DB)."""

    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> dict:
        return json.loads(self._body)


def make_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def fake_session() -> MagicMock:
    return MagicMock()


# ═══════════════════════════════════════════════════════════
# DB fixtures (EPIC 10) — giữ DB cả session, TRUNCATE giữa các test
# ═══════════════════════════════════════════════════════════

_PG_OK: bool | None = None  # cache ping cả session


def _maintenance_dsn() -> tuple[str, str, str, int]:
    """Parse DATABASE_URL → asyncpg kwargs (bỏ phần tên DB — luôn trỏ db 'postgres')."""
    url = TEST_DATABASE_URL.replace("+asyncpg", "")
    rest = url.split("://", 1)[1]                 # user:pass@host:port/dbname
    creds, _, hostpart = rest.rpartition("@")     # creds="user:pass", hostpart="host:port/dbname"
    user, _, password = creds.partition(":")
    hostport = hostpart.split("/", 1)[0]          # "host:port"
    host, _, port = hostport.partition(":")
    return user, password, host, int(port or 5432)


def _postgres_reachable() -> bool:
    global _PG_OK
    if _PG_OK is not None:
        return _PG_OK
    user, password, host, port = _maintenance_dsn()

    async def _ping() -> bool:
        try:
            try:
                conn = await asyncpg.connect(
                    user=user, password=password, database="nexus_ai_test",
                    host=host, port=port, timeout=2,
                )
            except asyncpg.InvalidCatalogNameError:
                # DB chưa tồn tại nhưng PG đang chạy → vẫn coi là reachable
                conn = await asyncpg.connect(
                    user=user, password=password, database="postgres",
                    host=host, port=port, timeout=2,
                )
            await conn.close()
            return True
        except Exception:
            return False

    _PG_OK = asyncio.run(_ping())
    return _PG_OK


def _ensure_test_database() -> None:
    """Tạo nexus_ai_test nếu thiếu (Postgres không có CREATE DATABASE IF NOT EXISTS)."""
    user, password, host, port = _maintenance_dsn()

    async def _ensure() -> None:
        conn = await asyncpg.connect(
            user=user, password=password, database="postgres",
            host=host, port=port, timeout=5,
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", "nexus_ai_test"
            )
            if not exists:
                await conn.execute('CREATE DATABASE "nexus_ai_test"')
        except asyncpg.errors.DuplicateDatabaseError:
            pass  # race — chấp nhận được
        finally:
            await conn.close()

    asyncio.run(_ensure())


@pytest.fixture(scope="session", autouse=True)
def _db_ready():
    """Session-scoped: ping → CREATE DATABASE → init_db (create_all + ALTER)."""
    if not _postgres_reachable():
        yield
        return
    _ensure_test_database()
    asyncio.run(connection.init_db())  # engine đã swap sang NullPool test engine
    yield


@pytest.fixture(autouse=True)
def _skip_db_without_postgres(request):
    """Skip mọi test gắn marker `db` khi Postgres không khả dụng."""
    if request.node.get_closest_marker("db") and not _postgres_reachable():
        pytest.skip("Postgres không khả dụng")


_TABLES = (
    "users", "user_preferences", "conversations", "messages",
    "memories", "reminders", "subscriptions", "articles",
)  # đúng Base.metadata — TRUNCATE ... CASCADE tự lo FK


@pytest.fixture
def db_run(_db_ready):
    """Runner cho test [db]: chạy TOÀN BỘ scenario trong MỘT event loop.

    TRUNCATE trước/sau; mỗi test là `async def scenario(session)` — mọi thao tác
    DB (kể cả scheduler.run_once dùng SessionLocal nội bộ) cùng loop → không
    dính lỗi "attached to a different loop".
    """
    if not _postgres_reachable():
        pytest.skip("Postgres không khả dụng")

    async def _truncate() -> None:
        async with _TEST_ENGINE.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
            )

    def run(scenario) -> None:
        async def wrapper() -> None:
            await _truncate()
            try:
                async with _TEST_SESSION() as session:
                    await scenario(session)
            finally:
                await _truncate()

        asyncio.run(wrapper())

    return run
